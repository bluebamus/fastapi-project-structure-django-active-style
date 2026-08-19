"""staging/production 배포 안전성 fail-fast (ledger F-006).

이 프로젝트는 SQLAdmin 에 인증 백엔드를 붙이지 않기로 확정했다(영구 비목표,
결정 2026-08-12). 따라서 방어선은 "인증을 붙인다" 가 아니라 **무인증 /admin 이
운영·스테이징에서 기동하지 못하게 막는다** 이다. DEBUG, placeholder secret,
와일드카드 CORS 도 같은 게이트에서 함께 거부한다.
"""

import pytest

import config as config_module


class _Stub:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _install(
    monkeypatch, *, env, debug=False, admin=False, origins=None, secrets=None, sql_echo=False
):
    secrets = secrets or {}
    monkeypatch.setattr(config_module, "app_settings", _Stub(ENV=env, DEBUG=debug, ADMIN=admin))
    monkeypatch.setattr(
        config_module, "cors_settings", _Stub(CORS_ALLOW_ORIGINS=origins or ["https://example.com"])
    )
    monkeypatch.setattr(
        config_module,
        "jwt_settings",
        _Stub(
            ACCESS_TOKEN_SECRET_KEY=secrets.get("access", "real-access-key"),
            REFRESH_TOKEN_SECRET_KEY=secrets.get("refresh", "real-refresh-key"),
        ),
    )
    monkeypatch.setattr(
        config_module,
        "session_settings",
        _Stub(SESSION_SECRET_KEY=secrets.get("session", "real-session-key")),
    )
    monkeypatch.setattr(config_module, "log_settings", _Stub(LOG_SQL_ECHO_ENABLED=sql_echo))


@pytest.mark.parametrize("env", ["development", "test"])
def test_non_production_env_is_untouched(monkeypatch, env):
    """개발·테스트 환경은 ADMIN=true, DEBUG=true 여도 막지 않는다(의도된 기본값)."""
    _install(monkeypatch, env=env, debug=True, admin=True, origins=["*"])
    config_module.validate_deployment_safety()  # 예외가 없어야 한다


@pytest.mark.parametrize("env", ["staging", "production"])
def test_admin_true_is_rejected(monkeypatch, env):
    """무인증 /admin 이 열린 채로는 staging/production 기동을 허용하지 않는다."""
    _install(monkeypatch, env=env, admin=True)
    with pytest.raises(RuntimeError, match="ADMIN"):
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
        secrets={"access": "key-a", "refresh": "key-b"},
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
