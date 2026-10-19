"""설정 일원화 계약 테스트.

두 가지 불변식을 지킨다:

1. **`.env` 의 모든 정보는 config.py 에 로드된다.**
   `.env.example` 에 적힌 키(주석 처리된 예시 포함)는 반드시 어떤 Settings 클래스의
   필드로 존재해야 한다. 반대로 config.py 의 모든 설정 필드는 `.env.example` 에
   문서화되어야 한다. 두 방향을 모두 검사해 문서와 코드가 갈라지지 않게 한다.

2. **config.py 외의 모듈은 환경변수를 직접 읽지 않는다.**
   설정이 필요한 모듈은 `from config import ...` 로 가져다 쓴다. `os.environ` /
   `os.getenv` 가 코드 여기저기 흩어지면 "이 값이 어디서 오는가"를 추적할 수 없고,
   `.env.example` 에 문서화되지 않은 숨은 설정이 생긴다.
"""

import inspect
import re
from pathlib import Path

from pydantic_settings import BaseSettings

import config as config_module

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"

# `KEY=value` 또는 주석 처리된 `# KEY=value` 형태의 설정 키만 뽑는다.
# (`# 예: ...`, `# - true: ...` 같은 산문 주석은 걸리지 않는다)
ENV_KEY_PATTERN = re.compile(r"^\s*(?:#\s*)?([A-Z][A-Z0-9_]*)\s*=")

# 환경변수 직접 접근 패턴
ENV_ACCESS_PATTERN = re.compile(r"os\.environ|os\.getenv")

# 환경변수 직접 접근을 검사할 소스 트리 (테스트 하네스는 제외)
SOURCE_ROOTS = ("app", "migrations", "scripts")
SOURCE_FILES = ("main.py",)


def _env_example_keys() -> set[str]:
    """`.env.example` 이 문서화한 설정 키 전체."""
    keys: set[str] = set()
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        match = ENV_KEY_PATTERN.match(line)
        if match:
            keys.add(match.group(1))
    return keys


def _config_setting_fields() -> set[str]:
    """config.py 의 모든 Settings 클래스가 로드하는 필드 전체."""
    fields: set[str] = set()
    for obj in vars(config_module).values():
        if inspect.isclass(obj) and issubclass(obj, BaseSettings) and obj is not BaseSettings:
            fields |= set(obj.model_fields)
    return fields


def _python_sources() -> list[Path]:
    """환경변수 직접 접근을 금지할 소스 파일 목록."""
    paths = [PROJECT_ROOT / name for name in SOURCE_FILES]
    for root in SOURCE_ROOTS:
        paths.extend((PROJECT_ROOT / root).rglob("*.py"))
    return [
        path
        for path in paths
        if path.exists() and "tests" not in path.parts and "__pycache__" not in path.parts
    ]


# =============================================================================
# 1. .env ↔ config.py 일원화
# =============================================================================
def test_every_env_example_key_is_loaded_in_config():
    """`.env.example` 의 모든 키는 config.py 의 Settings 필드로 로드되어야 한다."""
    missing = sorted(_env_example_keys() - _config_setting_fields())
    assert not missing, (
        f".env.example 에만 있고 config.py 가 로드하지 않는 키: {missing}\n"
        "설정은 반드시 config.py 를 거쳐야 합니다."
    )


def test_every_config_field_is_documented_in_env_example():
    """config.py 의 모든 설정 필드는 `.env.example` 에 문서화되어야 한다."""
    undocumented = sorted(_config_setting_fields() - _env_example_keys())
    assert not undocumented, (
        f"config.py 에만 있고 .env.example 에 문서화되지 않은 키: {undocumented}\n"
        ".env.example 은 지원하는 설정의 단일 목록입니다."
    )


def test_config_defines_at_least_one_setting_field():
    """위 두 테스트가 '필드를 하나도 못 찾아서' 통과하는 상황을 막는다."""
    assert len(_config_setting_fields()) > 20
    assert len(_env_example_keys()) > 20


# =============================================================================
# 2. config.py 만이 환경변수를 읽는다
# =============================================================================
def test_only_config_reads_environment_directly():
    """config.py 외의 모듈은 os.environ / os.getenv 를 쓰지 않는다."""
    offenders = []
    for path in _python_sources():
        if ENV_ACCESS_PATTERN.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert not offenders, (
        f"환경변수를 직접 읽는 모듈: {sorted(offenders)}\n"
        "설정은 config.py 에서 로드하고 `from config import ...` 로 가져다 쓰세요."
    )


def test_environment_access_check_scans_real_files():
    """검사 대상 파일 목록이 비어 있어 위 테스트가 헛통과하는 것을 막는다."""
    sources = _python_sources()
    assert len(sources) > 10
    assert any(path.name == "env.py" and "migrations" in path.parts for path in sources)


# =============================================================================
# 3. 설정 필드는 어딘가에서 읽힌다 (config-cleanup)
# =============================================================================
# 읽는 코드가 없는 설정은 "있는 기능처럼 보이는 빈 손잡이"다 — SMTP_*·UPLOAD_*·
# SESSION_EXPIRE_SECONDS 가 그렇게 남아 있다가 지워졌다. 다시 생기지 않게 막는다.
#
# 읽는 방식은 속성 접근(`settings.X`, config.py 안의 `self.X` 포함)과 `getattr(settings, "X")` 두 가지다.
# 한계: config.py 의 validator 만 읽는 필드도 "읽힘" 으로 센다.
REMOVED_SETTINGS = {
    "SMTP_SERVER": "smtp.example.com",
    "SMTP_PASSWORD": "your-app-password",
    "SMTP_TLS": "true",
    "SMTP_SSL": "true",  # 예전 validator 는 TLS+SSL 동시 활성을 거부했다 — 이제 무시돼야 한다
    "UPLOAD_DIR": "uploads",
    "UPLOAD_ALLOWED_EXTENSIONS": "not-json",
    "SESSION_EXPIRE_SECONDS": "not-an-int",
    "API_VERSION": "v2",  # config-cleanup-2 — URL prefix 는 코드에 고정("/v1/...")
}


def _unread_fields() -> set[str]:
    # 환경변수 검사와 같은 소스(app·migrations·scripts·main.py) + config.py(프로퍼티가 self.X 로 읽는다)
    paths = [*_python_sources(), PROJECT_ROOT / "config.py"]
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    return {
        name
        for name in _config_setting_fields()
        if not re.search(rf"\.{name}\b|getattr\([^,()]+,\s*[\"']{name}[\"']", text)
    }


def test_every_setting_field_is_read_somewhere():
    """config.py 의 설정 필드는 app·scripts·migrations·main.py·config.py 어딘가에서 읽혀야 한다."""
    unread = sorted(_unread_fields())
    assert not unread, (
        f"읽는 코드가 없는 설정 필드: {unread}\n"
        "쓰지 않는 설정은 지웁니다 — 예외 목록은 없습니다(config-cleanup-2 에서 비웠다)."
    )


def test_removed_settings_are_ignored_when_left_in_environment(monkeypatch):
    """지운 설정이 `.env`·환경 변수에 남아 있어도 기동은 깨지지 않고 속성도 생기지 않는다.

    레거시 `ADMIN` 과 달리 거부하지 않는다 — 효과 없는 값일 뿐 보안 위험이 아니다(extra="ignore").
    """
    for key, value in REMOVED_SETTINGS.items():
        monkeypatch.setenv(key, value)

    classes = [
        obj
        for obj in vars(config_module).values()
        if inspect.isclass(obj) and issubclass(obj, BaseSettings) and obj is not BaseSettings
    ]
    assert len(classes) >= 9
    for cls in classes:
        assert cls.model_config.get("extra") == "ignore", cls.__name__
        instance = cls(_env_file=None)
        for key in REMOVED_SETTINGS:
            assert not hasattr(instance, key), f"{cls.__name__}.{key}"
