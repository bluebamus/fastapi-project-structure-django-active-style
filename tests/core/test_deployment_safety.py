"""설정 검사 fail-fast (ledger F-006 → 2026-10-07 확장).

- 비밀값(placeholder·짧은 키·같은 JWT 키·예시 비밀번호)은 test 를 뺀 **모든 ENV** 에서 거부한다.
  기본값·예시 값 그대로는 개발 환경에서도 `.env` 를 채우라는 신호다.
- staging/production 은 추가로 DEBUG·와일드카드 CORS·SQL echo·LOG_LEVEL=DEBUG 를 거부한다.
- SQLAdmin 에는 인증 백엔드를 붙이지 않는다(영구 비목표, 결정 2026-08-12). 무인증 /admin 은
  배포 환경에서도 쓸 수 있지만 `ADMIN_ALLOW_UNAUTHENTICATED=true` 확인이 있어야 기동한다.
- `.env` 가 없으면 필수 값이 환경 변수로 와야 한다(`validate_env_source`).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import config as config_module


class _Stub:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _install(
    monkeypatch,
    *,
    env,
    debug=False,
    admin=False,
    admin_ack=False,
    origins=None,
    secrets=None,
    sql_echo=False,
    log_level=None,
    passwords=None,
):
    secrets = secrets or {}
    passwords = passwords or {}
    monkeypatch.setattr(
        config_module,
        "app_settings",
        _Stub(ENV=env, DEBUG=debug, ADMIN=admin, ADMIN_ALLOW_UNAUTHENTICATED=admin_ack),
    )
    monkeypatch.setattr(
        config_module, "cors_settings", _Stub(CORS_ALLOW_ORIGINS=origins or ["https://example.com"])
    )
    monkeypatch.setattr(
        config_module,
        "jwt_settings",
        _Stub(
            # 기본값은 32자 이상(SECRET_KEY_MIN_LENGTH) — 길이 검사가 다른 판정을 가리지 않게.
            ACCESS_TOKEN_SECRET_KEY=secrets.get("access", "real-access-key-k9Qz0vL3mX7pR2tY5wB8n"),
            REFRESH_TOKEN_SECRET_KEY=secrets.get(
                "refresh", "real-refresh-key-Xr2Tq8Wm4Np6Lk0Jh3Gf"
            ),
        ),
    )
    monkeypatch.setattr(
        config_module,
        "session_settings",
        _Stub(SESSION_SECRET_KEY=secrets.get("session", "real-session-key-Pz7Ol5Ik3Uj1Yh9Tg7Rf")),
    )
    monkeypatch.setattr(
        config_module,
        "log_settings",
        _Stub(LOG_SQL_ECHO_ENABLED=sql_echo, LOG_LEVEL=log_level),
    )
    monkeypatch.setattr(
        config_module,
        "db_settings",
        _Stub(MYSQL_PASSWORD=passwords.get("mysql", "real-mysql-password")),
    )
    monkeypatch.setattr(
        config_module,
        "redis_settings",
        _Stub(REDIS_PASSWORD=passwords.get("redis", None)),
    )
    monkeypatch.setattr(
        config_module,
        "smtp_settings",
        _Stub(SMTP_PASSWORD=passwords.get("smtp", "")),
    )


@pytest.mark.parametrize("env", ["development", "test"])
def test_non_production_env_is_untouched(monkeypatch, env):
    """개발·테스트 환경은 ADMIN=true, DEBUG=true, CORS '*' 여도 막지 않는다(의도된 기본값)."""
    _install(monkeypatch, env=env, debug=True, admin=True, origins=["*"])
    config_module.validate_deployment_safety()  # 예외가 없어야 한다


@pytest.mark.parametrize("env", ["staging", "production"])
def test_admin_true_without_ack_is_rejected(monkeypatch, env):
    """기본값 ADMIN=true 를 그대로 들고 온 배포는 기동하지 않는다 — 해결책 둘을 함께 알린다."""
    _install(monkeypatch, env=env, admin=True)
    with pytest.raises(RuntimeError, match="ADMIN_ALLOW_UNAUTHENTICATED"):
        config_module.validate_deployment_safety()


@pytest.mark.parametrize("env", ["staging", "production"])
def test_admin_true_with_ack_passes(monkeypatch, env):
    """인증 없는 /admin 을 알고 켠 배포는 기동한다(매 기동 WARNING 은 main.py 가 남긴다)."""
    _install(monkeypatch, env=env, admin=True, admin_ack=True)
    config_module.validate_deployment_safety()


@pytest.mark.parametrize("env", ["staging", "production"])
def test_debug_true_is_rejected(monkeypatch, env):
    _install(monkeypatch, env=env, debug=True)
    with pytest.raises(RuntimeError, match="DEBUG"):
        config_module.validate_deployment_safety()


@pytest.mark.parametrize("key", ["access", "refresh", "session"])
def test_placeholder_secret_is_rejected(monkeypatch, key):
    _install(monkeypatch, env="production", secrets={key: "change-this-whatever"})
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        config_module.validate_deployment_safety()


def test_identical_jwt_keys_are_rejected(monkeypatch):
    """access 와 refresh 서명 키가 같으면 refresh 토큰이 access 로 통과할 수 있다."""
    _install(
        monkeypatch,
        env="production",
        secrets={"access": "same-signing-key", "refresh": "same-signing-key"},
    )
    with pytest.raises(RuntimeError, match="동일"):
        config_module.validate_deployment_safety()


def test_distinct_jwt_keys_pass(monkeypatch):
    _install(
        monkeypatch,
        env="production",
        secrets={
            "access": "key-a-k9Qz0vL3mX7pR2tY5wB8nC1dF4gH",
            "refresh": "key-b-Xr2Tq8Wm4Np6Lk0Jh3Gf5Ds7Az9",
        },
    )
    config_module.validate_deployment_safety()


def test_wildcard_cors_is_rejected(monkeypatch):
    _install(monkeypatch, env="production", origins=["*"])
    with pytest.raises(RuntimeError, match="CORS"):
        config_module.validate_deployment_safety()


def test_safe_production_config_passes(monkeypatch):
    _install(monkeypatch, env="production")
    config_module.validate_deployment_safety()


def test_error_lists_every_problem_at_once(monkeypatch):
    """한 번에 모든 위반을 보고한다 — 고치고 재기동을 반복하지 않도록."""
    _install(
        monkeypatch,
        env="production",
        debug=True,
        admin=True,
        origins=["*"],
        secrets={"access": "change-this-access-token-secret-key"},
    )
    with pytest.raises(RuntimeError) as excinfo:
        config_module.validate_deployment_safety()

    message = str(excinfo.value)
    for expected in ("DEBUG", "ADMIN", "CORS", "SECRET_KEY"):
        assert expected in message


def test_error_message_does_not_leak_secret_values(monkeypatch):
    """오류 메시지에 secret 값 자체를 담지 않는다 (C-5)."""
    _install(monkeypatch, env="production", secrets={"session": "change-this-super-sensitive"})
    with pytest.raises(RuntimeError) as excinfo:
        config_module.validate_deployment_safety()

    assert "change-this-super-sensitive" not in str(excinfo.value)


# ---------------------------------------------------------------- Phase 1-R2
# INV-8 — SQL echo 는 운영에서 켤 수 없다.


@pytest.mark.parametrize("env", ["staging", "production"])
def test_sql_echo_is_rejected_in_deployed_envs(monkeypatch, env):
    """SQL 로그에는 바인딩된 파라미터가 그대로 실린다 — 운영에서 켤 이유가 없다.

    설정 하나로 사용자 식별자·검색어·이메일이 로그 파일에 쌓인다. "잠깐 켜두고
    잊는" 것이 가장 흔한 경로라, 잊을 수 있게 두지 않고 기동을 막는다.
    """
    _install(monkeypatch, env=env, sql_echo=True)

    with pytest.raises(RuntimeError, match="LOG_SQL_ECHO_ENABLED"):
        config_module.validate_deployment_safety()


@pytest.mark.parametrize("env", ["development", "test"])
def test_sql_echo_is_allowed_in_development(monkeypatch, env):
    """개발·테스트에서는 SQL 을 봐야 할 때가 있다."""
    _install(monkeypatch, env=env, sql_echo=True)

    config_module.validate_deployment_safety()  # 예외가 없어야 한다


def test_sql_echo_off_passes_in_production(monkeypatch):
    _install(monkeypatch, env="production", sql_echo=False)

    config_module.validate_deployment_safety()


# ------------------------------------------------------------------ debug 로그
# 롤백 로그의 SQL·바인딩 값 전문은 DEBUG 레코드로만 나간다(C-4). 그래서 유효
# 로그 레벨을 DEBUG 로 올리는 두 경로(DEBUG=true, LOG_LEVEL=DEBUG)를 모두 막아야
# 한다. DEBUG=true 는 test_debug_true_is_rejected 가 이미 지킨다.


@pytest.mark.parametrize("env", ["staging", "production"])
@pytest.mark.parametrize("value", ["DEBUG", "debug", "Debug"])
def test_debug_log_level_is_rejected_in_deployed_envs(monkeypatch, env, value):
    """유효 레벨이 DEBUG 면 롤백 상세(SQL·바인딩 값)가 파일 로그에 쌓인다."""
    _install(monkeypatch, env=env, log_level=value)

    with pytest.raises(RuntimeError, match="LOG_LEVEL"):
        config_module.validate_deployment_safety()


@pytest.mark.parametrize("value", [None, "INFO", "WARNING"])
def test_non_debug_log_level_passes_in_production(monkeypatch, value):
    _install(monkeypatch, env="production", log_level=value)

    config_module.validate_deployment_safety()


@pytest.mark.parametrize("env", ["development", "test"])
def test_debug_log_level_is_allowed_in_development(monkeypatch, env):
    _install(monkeypatch, env=env, log_level="DEBUG")

    config_module.validate_deployment_safety()


# ---------------------------------------------------------------- secret guard
# placeholder 판정은 config.is_placeholder_secret 하나가 소유한다:
# strip·lower 후 "change-this" 포함, "your-" 로 시작, 또는 빈 문자열.

_SECRET_NAMES = ("ACCESS_TOKEN_SECRET_KEY", "REFRESH_TOKEN_SECRET_KEY", "SESSION_SECRET_KEY")


def test_env_example_secrets_are_rejected_without_leaking_values(monkeypatch):
    """`.env.example` 을 그대로 복사해 운영에 올리면 세 키가 모두 거부된다."""
    from pathlib import Path

    from dotenv import dotenv_values

    example = dotenv_values(Path(config_module.__file__).parent / ".env.example")
    values = {
        "access": example["ACCESS_TOKEN_SECRET_KEY"],
        "refresh": example["REFRESH_TOKEN_SECRET_KEY"],
        "session": example["SESSION_SECRET_KEY"],
    }
    _install(monkeypatch, env="production", secrets=values)

    with pytest.raises(RuntimeError) as excinfo:
        config_module.validate_deployment_safety()

    message = str(excinfo.value)
    for name in _SECRET_NAMES:
        assert f"{name} 이 기본 placeholder" in message
    for value in values.values():
        assert value not in message


@pytest.mark.parametrize(
    "value",
    [
        "your-access-token-secret-key-change-this",
        "CHANGE-THIS-access-token-secret-key",
        "prefix-Change-This-suffix",
        "  Your-secret  ",
        "",
        "   ",
    ],
    ids=["old-your-style", "upper", "infix", "your-padded", "empty", "blank"],
)
@pytest.mark.parametrize("key", ["access", "refresh", "session"])
def test_placeholder_variants_are_rejected(monkeypatch, key, value):
    _install(monkeypatch, env="staging", secrets={key: value})
    with pytest.raises(RuntimeError, match="기본 placeholder"):
        config_module.validate_deployment_safety()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("change-this-x", True),
        ("x-CHANGE-THIS", True),
        (" your-key", True),
        ("", True),
        ("  ", True),
        ("my-your-key", False),
        ("kQ9v3xR7_strong_random_value", False),
    ],
)
def test_is_placeholder_secret(value, expected):
    assert config_module.is_placeholder_secret(value) is expected


def test_distinct_strong_secrets_pass(monkeypatch):
    import secrets as secrets_module

    generated = {k: secrets_module.token_urlsafe(48) for k in ("access", "refresh", "session")}
    _install(monkeypatch, env="production", secrets=generated)
    config_module.validate_deployment_safety()


def test_placeholder_secrets_are_not_checked_in_test_env(monkeypatch):
    _install(
        monkeypatch,
        env="test",
        secrets={"access": "", "refresh": "", "session": "your-session-change-this"},
    )
    config_module.validate_deployment_safety()


@pytest.mark.parametrize("key", ["access", "refresh", "session"])
def test_placeholder_secret_is_rejected_in_development(monkeypatch, key):
    """기본값·예시 값 그대로는 개발 환경에서도 기동하지 않는다 — `.env` 를 채우라는 신호."""
    _install(monkeypatch, env="development", secrets={key: "change-this-whatever"})
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        config_module.validate_deployment_safety()


@pytest.mark.parametrize("env", ["development", "staging", "production"])
def test_short_secret_is_rejected(monkeypatch, env):
    short = "k9Qz0vL3mX7pR2tY5wB8nC1dF4g"  # 27자
    _install(monkeypatch, env=env, secrets={"session": short})
    with pytest.raises(RuntimeError, match="SESSION_SECRET_KEY") as excinfo:
        config_module.validate_deployment_safety()
    assert short not in str(excinfo.value)


# -------------------------------------------------------------- 비밀번호 3종
# 서명 키만 보고 MYSQL·REDIS·SMTP 비밀번호를 놓치면, `.env.example` 을 그대로 복사한
# 배포가 예시 비밀번호로 기동한다. 같은 판정 함수(is_placeholder_secret)로 함께 막는다.
#
# 빈 문자열의 의미는 설정마다 다르다:
#   - MYSQL_PASSWORD : 빈 값 = 비밀번호 없는 DB 계정. 운영에서 그 자체로 사고라 **위반**.
#   - REDIS_PASSWORD : 빈 값/None = 인증 없는 사설망 Redis. 코드가 지원하는 정상 구성이라 허용.
#   - SMTP_PASSWORD  : 빈 값 = 메일 미사용. 메일 안 쓰는 배포를 막을 이유가 없어 허용.


@pytest.mark.parametrize("env", ["staging", "production"])
@pytest.mark.parametrize(
    ("key", "name"),
    [("mysql", "MYSQL_PASSWORD"), ("redis", "REDIS_PASSWORD"), ("smtp", "SMTP_PASSWORD")],
)
def test_placeholder_password_is_rejected(monkeypatch, env, key, name):
    _install(monkeypatch, env=env, passwords={key: "your-password-change-this"})

    with pytest.raises(RuntimeError, match=name):
        config_module.validate_deployment_safety()


def test_empty_mysql_password_is_rejected(monkeypatch):
    """빈 MySQL 비밀번호 = 무인증 DB 계정. 운영에서 허용할 구성이 아니다."""
    _install(monkeypatch, env="production", passwords={"mysql": ""})

    with pytest.raises(RuntimeError, match="MYSQL_PASSWORD"):
        config_module.validate_deployment_safety()


@pytest.mark.parametrize("value", [None, ""])
def test_empty_redis_password_passes(monkeypatch, value):
    """인증 없는 사설망 Redis 는 정상 구성이다 — REDIS_URL 이 그 경로를 직접 지원한다."""
    _install(monkeypatch, env="production", passwords={"redis": value})

    config_module.validate_deployment_safety()


def test_empty_smtp_password_passes(monkeypatch):
    """메일을 쓰지 않는 배포를 SMTP 비밀번호가 비었다는 이유로 막지 않는다."""
    _install(monkeypatch, env="production", passwords={"smtp": ""})

    config_module.validate_deployment_safety()


def test_placeholder_passwords_are_not_checked_in_test_env(monkeypatch):
    _install(
        monkeypatch,
        env="test",
        passwords={"mysql": "", "redis": "your-redis-password", "smtp": "change-this"},
    )

    config_module.validate_deployment_safety()


@pytest.mark.parametrize(
    ("key", "value", "name"),
    [
        ("mysql", "", "MYSQL_PASSWORD"),
        ("mysql", "change-this-mysql-password", "MYSQL_PASSWORD"),
        ("smtp", "your-smtp-password", "SMTP_PASSWORD"),
    ],
)
def test_placeholder_password_is_rejected_in_development(monkeypatch, key, value, name):
    _install(monkeypatch, env="development", passwords={key: value})

    with pytest.raises(RuntimeError, match=name):
        config_module.validate_deployment_safety()


def test_password_error_message_does_not_leak_values(monkeypatch):
    """오류 메시지에 비밀번호 값 자체를 담지 않는다 (C-5)."""
    _install(monkeypatch, env="production", passwords={"mysql": "change-this-db-p4ssw0rd"})

    with pytest.raises(RuntimeError) as excinfo:
        config_module.validate_deployment_safety()

    assert "change-this-db-p4ssw0rd" not in str(excinfo.value)


def test_env_example_passwords_are_rejected_without_leaking_values(monkeypatch):
    """`.env.example` 을 그대로 복사해 운영에 올리면 비밀번호도 거부된다.

    REDIS_PASSWORD 는 예시가 비어 있고 그게 정당한 구성이라 여기서 빠진다.
    """
    from pathlib import Path

    from dotenv import dotenv_values

    example = dotenv_values(Path(config_module.__file__).parent / ".env.example")
    values = {"mysql": example["MYSQL_PASSWORD"], "smtp": example["SMTP_PASSWORD"]}
    _install(monkeypatch, env="production", passwords=values)

    with pytest.raises(RuntimeError) as excinfo:
        config_module.validate_deployment_safety()

    message = str(excinfo.value)
    for name in ("MYSQL_PASSWORD", "SMTP_PASSWORD"):
        assert f"{name} 이 기본 placeholder" in message
    for value in values.values():
        assert value not in message


# -------------------------------------------------------------- 설정의 출처
# `.env` 가 없으면 필수 값이 환경 변수로 와야 한다. 컨테이너처럼 파일 없이 주입하는 배포는 통과.

PROJECT_ROOT = Path(config_module.__file__).resolve().parent
FULL_ENVIRON = {
    "ENV": "production",
    "ACCESS_TOKEN_SECRET_KEY": "k9Qz0vL3mX7pR2tY5wB8nC1dF4gH6jK0aS3eU7iO9lZ",
    "REFRESH_TOKEN_SECRET_KEY": "Xr2Tq8Wm4Np6Lk0Jh3Gf5Ds7Az9Sx1Cv4Bn6Mm8Qw2Er",
    "SESSION_SECRET_KEY": "Pz7Ol5Ik3Uj1Yh9Tg7Rf5Ed3Ws1Qa8Zx6Cv4Bn2Mm0Lk",
    "MYSQL_HOST": "db",
    "MYSQL_USER": "app",
    "MYSQL_PASSWORD": "Gt4Hn8Qz2Lp6Xw0Rb3Vy",
    "MYSQL_DATABASE": "app",
}


def test_missing_env_file_without_environ_is_rejected(tmp_path):
    with pytest.raises(RuntimeError) as excinfo:
        config_module.validate_env_source("development", tmp_path / ".env", {})
    message = str(excinfo.value)
    assert ".env" in message
    for name in config_module.REQUIRED_WITHOUT_ENV_FILE:
        assert name in message


def test_missing_env_file_names_only_what_is_missing(tmp_path):
    environ = {k: v for k, v in FULL_ENVIRON.items() if k != "MYSQL_PASSWORD"}
    with pytest.raises(RuntimeError) as excinfo:
        config_module.validate_env_source("production", tmp_path / ".env", environ)
    message = str(excinfo.value)
    assert "MYSQL_PASSWORD" in message
    assert "MYSQL_HOST" not in message
    for value in environ.values():
        assert value not in message


def test_injected_environ_without_env_file_passes(tmp_path):
    config_module.validate_env_source("production", tmp_path / ".env", FULL_ENVIRON)


def test_existing_env_file_passes(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ENV=development\n", encoding="utf-8")
    config_module.validate_env_source("development", env_file, {})


def test_test_env_skips_source_check(tmp_path):
    config_module.validate_env_source("test", tmp_path / ".env", {})


def _run(code: str, env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=cwd,
        env={**env, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )


def test_import_fails_without_env_file_and_environ(tmp_path):
    """검사는 import 시점에 실제로 돈다 — `.env` 없는 작업 디렉터리, 필수 값 없음."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in config_module.REQUIRED_WITHOUT_ENV_FILE and k != "PYTHONPATH"
    }
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    result = _run("import config", env, tmp_path)
    assert result.returncode != 0
    assert ".env 파일이 없고" in result.stderr


def _deployed_env(**overrides: str) -> dict[str, str]:
    return {
        **os.environ,
        **FULL_ENVIRON,
        "DEBUG": "false",
        "LOG_LEVEL": "INFO",
        "LOG_SQL_ECHO_ENABLED": "false",
        "CORS_ALLOW_ORIGINS": '["https://example.com"]',
        "REDIS_PASSWORD": "",
        "SMTP_PASSWORD": "",
        **overrides,
    }


def test_import_fails_in_production_with_admin_default():
    result = _run("import config", _deployed_env(ADMIN="true"), PROJECT_ROOT)
    assert result.returncode != 0
    assert "ADMIN_ALLOW_UNAUTHENTICATED" in result.stderr


def test_deployed_admin_with_ack_logs_warning_on_startup():
    """확인 플래그로 연 /admin 은 기동마다 WARNING 을 남긴다 — 운영 로그에서 놓치지 않게."""
    result = _run(
        "import main",
        _deployed_env(ADMIN="true", ADMIN_ALLOW_UNAUTHENTICATED="true"),
        PROJECT_ROOT,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    output = result.stdout + result.stderr
    assert "WARNING" in output
    assert "SQLAdmin 이 인증 없이 열려 있습니다" in output
