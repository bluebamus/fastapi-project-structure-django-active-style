"""
애플리케이션 설정 모듈

환경변수 기반의 설정을 Pydantic Settings로 관리합니다.

사용 방법:
    from config import app_settings, db_settings

    print(app_settings.DEBUG)
    print(db_settings.MYSQL_URL)

환경변수 우선순위:
    1. 시스템 환경변수
    2. .env 파일
    3. Field의 default 값
"""

import os
from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from zoneinfo import ZoneInfo

from dotenv import dotenv_values
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


# =============================================================================
# 타임존 설정
# =============================================================================
class TimezoneSettings(BaseSettings):
    """
    타임존 설정

    애플리케이션 전역 타임존을 관리합니다.
    로그 시간, 데이터 생성 시간 등에 적용됩니다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 타임존 문자열 (예: Asia/Seoul, UTC, America/New_York)
    TIME_ZONE: str = Field(
        default="Asia/Seoul",
        description="애플리케이션 전역 타임존",
    )

    @property
    def tz(self) -> ZoneInfo:
        """ZoneInfo 객체 반환"""
        return ZoneInfo(self.TIME_ZONE)

    def now(self) -> datetime:
        """현재 시간을 설정된 타임존으로 반환(로그 파일 날짜 등 지역 시각이 필요한 곳)."""
        return datetime.now(self.tz)

    def utc_now(self) -> datetime:
        """현재 시각(UTC aware). DB 에 저장하는 시각은 모두 여기서 만든다(ADR-007)."""
        return datetime.now(UTC)

    def local_dates_to_utc(self, start: date, end: date) -> tuple[datetime, datetime]:
        """지역 영업일 [start, end] 를 UTC 순간의 반열린 구간 [시작, 끝) 으로 바꾼다.

        시작 = start 의 지역 00:00, 끝 = end 다음 날의 지역 00:00. 둘 다 UTC aware.
        """
        lower = datetime.combine(start, time.min, self.tz).astimezone(UTC)
        upper = datetime.combine(end + timedelta(days=1), time.min, self.tz).astimezone(UTC)
        return lower, upper

    def utc_offset(self, at: datetime) -> str:
        """`at` 순간의 설정 타임존 오프셋을 MySQL `CONVERT_TZ` 형식(`+09:00`)으로 돌려준다."""
        offset = at.astimezone(self.tz).utcoffset() or timedelta(0)
        minutes = int(offset.total_seconds()) // 60
        sign = "-" if minutes < 0 else "+"
        hours, minutes = divmod(abs(minutes), 60)
        return f"{sign}{hours:02d}:{minutes:02d}"

    def localize(self, dt: datetime) -> datetime:
        """naive datetime을 설정된 타임존으로 변환"""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=self.tz)
        return dt.astimezone(self.tz)


# =============================================================================
# API 설명 (Scalar 문서에 표시)
# =============================================================================
API_DESCRIPTION = """
## FastAPI Project Structure — Django Active Style

Repository 패턴과 계층 분리를 적용한 FastAPI 프로젝트 골격입니다.
`app/features/<name>/` 디렉터리를 두면 라우터·모델·관리 화면이 자동으로 등록됩니다.

### 주요 기능

- **앱 자동 등록**: `AppRegistry` 가 `<name>_router` 를 `/api` 에 마운트
- **CRUD 예제**: blog · reply · sns · user · catalog(ORM 예제)
- **Raw SQL 예제**: reports 일별 매출 집계
- **인증**: OAuth2 password flow + JWT access/refresh
- **접속 로그**: User-Agent 파싱, 조회·통계 API (home)

### 아키텍처

```
Router → Depends(get_<name>_service) → Service → Repository → Database
   └ 쓰기 핸들러가 응답 DTO 검증 뒤 await service.commit() 한 번
```

### 기술 스택

- **FastAPI**: 고성능 비동기 웹 프레임워크
- **SQLAlchemy 2.0**: 비동기 ORM (aiomysql)
- **Pydantic v2**: 데이터 검증 및 설정 관리
- **Scalar**: API 문서 UI

### 환경 설정

| 설정 | 설명 |
|------|------|
| `DEBUG=true` | 개발 모드 (DEBUG 로그, 테이블 자동 생성, `/docs`) |
| `DEBUG=false` | 운영 모드 (INFO 로그, Alembic 마이그레이션, `/docs` 404) |
| Redis | 기동 시 `ping()` 필수 — 실패하면 서버가 시작하지 않는다 |
"""


# =============================================================================
# 기본 설정
# =============================================================================
class AppSettings(BaseSettings):
    """
    애플리케이션 기본 설정

    프로젝트 메타데이터와 전역 동작 모드를 관리합니다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 프로젝트 이름 (Scalar 문서 제목, 관리자 페이지 제목)
    PROJECT_NAME: str = Field(
        default="FastAPI Project",
        description="프로젝트 이름",
    )

    # 애플리케이션 버전 (헬스체크 응답에 포함)
    VERSION: str = Field(
        default="0.1.0",
        description="애플리케이션 버전",
    )

    # API 문서 설명 (Scalar에 표시)
    DESCRIPTION: str = Field(
        default=API_DESCRIPTION,
        description="API 문서 설명",
    )

    # 디버그 모드
    # True: DEBUG 로그, 테이블 자동 생성, uvicorn reload, /docs 활성화
    # False: INFO 로그, Alembic 마이그레이션, /docs 비활성화
    DEBUG: bool = Field(
        default=True,
        description="디버그 모드 활성화",
    )

    # 관리 화면(SQLAdmin, /admin)을 완전히 끈다 (DEBUG 와 독립적으로 동작).
    # false(기본): /admin 마운트  /  true: /admin 자체가 없음(404) — sqladmin·관리 세션
    # 미들웨어·인증 백엔드를 만들지 않고, 앱이 내보내는 어떤 응답·기동 로그에도 관리 경로가
    # 나오지 않는다(admin-login ADR-007). 관리 화면을 쓰지 않는 배포는 true 로 둔다.
    #
    # 기본값 false(켜짐)는 의도다 — 이 저장소는 개발을 우선 고려한 레퍼런스 구조라, 받자마자
    # /admin 으로 DB 를 들여다볼 수 있어야 한다(결정: 2026-08-12).
    #
    # /admin 은 **활성 슈퍼유저 로그인**이 필요하다(admin-login ADR-002 — 이전의 "인증 없음"
    # 결정을 대체한다). 계정은 `scripts/create_superuser.py` 로 만들고, 세션 쿠키
    # (`admin_session`, Path=/admin)에는 세션 ID 만 있고 내용은 Redis 에 있다(키 = SESSION_SECRET_KEY HMAC,
    # admin-session-hardening ADR-001). 그래서 배포 환경에서도
    # 켠 채 기동할 수 있다. 예전의 "무인증 허용" 확인 플래그는 없앴다(extra="ignore" 라
    # `.env` 에 남아도 무시된다). 예전 `ADMIN`(true=켬)은 이 설정으로 바뀌었고, 남아 있으면
    # 의미가 뒤집힌 채 무시되므로 `validate_renamed_settings()` 가 기동을 멈춘다.
    ADMIN_DISABLED: bool = Field(
        default=False,
        description="관리 화면(/admin) 끄기 — true 면 마운트·링크·로그 모두 없음 (켜면 슈퍼유저 로그인 필요)",
    )

    # 실행 환경. 로그 구성(핸들러·UTC)과 배포 안전 게이트가 따른다.
    ENV: Literal["development", "staging", "production", "test"] = Field(
        default="development",
        description="실행 환경",
    )

    # 개발용 `python main.py` 직접 실행 시 바인딩 호스트/포트.
    # 컨테이너·배포 환경에서 외부 접근을 허용하려면 0.0.0.0 이 기본이지만, 민감한
    # 환경에서는 SERVER_HOST=127.0.0.1 로 지정하고 리버스 프록시를 두는 것을 권장한다.
    SERVER_HOST: str = Field(
        default="0.0.0.0",  # nosec B104 - 컨테이너 실행 전제의 의도된 기본값(운영은 env 로 제한)
        description="개발 서버 바인딩 호스트",
    )

    # 개발 서버 바인딩 포트
    SERVER_PORT: int = Field(
        default=8000,
        description="개발 서버 바인딩 포트",
    )


# =============================================================================
# 데이터베이스 설정
# =============================================================================
def bare_host(host: str) -> str:
    """DSN 에 넣을 호스트 값 — IPv6 를 감싼 대괄호를 벗긴다.

    ``URL.create`` 는 렌더링할 때 IPv6 에 스스로 대괄호를 씌운다. 대괄호째 넘기면
    ``[[::1]]`` 이 되므로 여기서는 주소만 넘긴다. IPv4·도메인은 그대로다.
    """
    host = host.strip()
    if host.startswith("[") and host.endswith("]"):
        return host[1:-1]
    return host


def split_host_port(entry: str, default_port: int) -> tuple[str, int]:
    """``"host"`` / ``"host:port"`` 항목을 (호스트, 포트)로 분해한다.

    허용 형식:
        - IPv4      : ``10.0.0.11``            / ``10.0.0.11:3307``
        - 도메인    : ``replica.example.com``  / ``replica.example.com:3307``
        - IPv6      : ``[::1]``                / ``[2001:db8::10]:3307``

    IPv6 는 반드시 대괄호로 감싸야 한다. 감싸지 않으면 어디까지가 주소이고 어디부터가
    포트인지 구분할 수 없어 조용히 깨진 DSN 이 된다 — 그래서 여기서 명시적으로 거부한다.
    돌려주는 호스트는 대괄호를 벗긴 주소다(``URL.create`` 가 렌더링 때 다시 씌운다).
    """
    entry = entry.strip()

    if entry.startswith("["):
        host, closing, rest = entry.partition("]")
        if not closing:
            raise ValueError(f"replica 호스트 '{entry}' 의 대괄호가 닫히지 않았습니다.")
        host = host[1:]
        if rest and not rest.startswith(":"):
            raise ValueError(f"replica 호스트 '{entry}' 형식이 잘못되었습니다 (기대: [주소]:포트).")
        port = rest[1:]
    else:
        if entry.count(":") > 1:
            raise ValueError(
                f"IPv6 주소 '{entry}' 는 대괄호로 감싸야 합니다 (예: [2001:db8::10]:3307)."
            )
        host, _, port = entry.partition(":")

    if not host:
        raise ValueError(f"replica 호스트가 비어 있습니다: '{entry}'")
    if port and not port.isdigit():
        raise ValueError(f"replica 호스트 '{entry}' 의 포트가 숫자가 아닙니다.")

    return host, int(port) if port else default_port


class DatabaseSettings(BaseSettings):
    """
    데이터베이스 연결 설정

    MySQL 비동기 연결을 위한 aiomysql 드라이버를 사용합니다.

    읽기/쓰기 분리(DB 라우터):
        DB_ROUTER_ENABLED=false  → 단일 서버. 모든 쿼리가 primary 로 간다(기본값).
        DB_ROUTER_ENABLED=true   → 라우터 활성. replica 가 없으면 여전히 primary 로 간다.
        + DB_REPLICATION_ENABLED=true
                                 → SELECT 는 replica, 쓰기는 primary 로 분리된다.

    라우팅 구현은 ``app/core/db/router.py`` 를 참고하세요.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # === primary(쓰기) 서버 ===
    # MySQL 서버 호스트 (IP 또는 도메인)
    MYSQL_HOST: str = Field(
        default="localhost",
        description="MySQL 서버 호스트",
    )

    # MySQL 서버 포트
    MYSQL_PORT: int = Field(
        default=3306,
        description="MySQL 서버 포트",
    )

    # MySQL 접속 사용자명
    MYSQL_USER: str = Field(
        default="root",
        description="MySQL 사용자명",
    )

    # MySQL 접속 비밀번호
    MYSQL_PASSWORD: str = Field(
        default="",
        description="MySQL 비밀번호",
    )

    # 사용할 데이터베이스 이름
    MYSQL_DATABASE: str = Field(
        default="fastapi_db",
        description="데이터베이스 이름",
    )

    # === DB 라우터 (읽기/쓰기 분리) ===
    # 라우터 사용 여부. false 면 세션이 단일 엔진에 직접 바인딩된다(기존 동작).
    DB_ROUTER_ENABLED: bool = Field(
        default=False,
        description="DB 읽기/쓰기 라우터 활성화",
    )

    # 복제(replication) 사용 여부. true 면 SELECT 를 replica 로 보낸다.
    # DB_ROUTER_ENABLED=true 와 MYSQL_REPLICA_HOSTS 지정이 함께 필요하다.
    DB_REPLICATION_ENABLED: bool = Field(
        default=False,
        description="읽기 복제본(replica) 사용",
    )

    # 쓰기가 일어난 세션의 이후 SELECT 를 primary 로 고정할지 여부.
    # 복제 지연으로 방금 쓴 데이터가 replica 에서 안 보이는 것을 막는다(권장: true).
    DB_READ_STICKY_AFTER_WRITE: bool = Field(
        default=True,
        description="쓰기 이후 읽기를 primary 에 고정(read-after-write 일관성)",
    )

    # === replica(읽기) 서버 ===
    # replica 호스트 목록. "host" 또는 "host:port" 형식.
    # 예: ["replica-a", "replica-b:3307"]
    MYSQL_REPLICA_HOSTS: list[str] = Field(
        default=[],
        description="replica 호스트 목록 (host 또는 host:port)",
    )

    # 포트를 명시하지 않은 replica 에 적용할 기본 포트
    MYSQL_REPLICA_PORT: int = Field(
        default=3306,
        description="replica 기본 포트",
    )

    # replica 전용 자격증명. 미설정(None) 시 primary 값을 재사용한다.
    # 읽기 전용 계정을 분리해 두면 실수로 replica 에 쓰는 사고를 DB 권한 수준에서 막는다.
    MYSQL_REPLICA_USER: str | None = Field(
        default=None,
        description="replica 사용자명 (미설정 시 primary 재사용)",
    )

    MYSQL_REPLICA_PASSWORD: str | None = Field(
        default=None,
        description="replica 비밀번호 (미설정 시 primary 재사용)",
    )

    MYSQL_REPLICA_DATABASE: str | None = Field(
        default=None,
        description="replica 데이터베이스 이름 (미설정 시 primary 재사용)",
    )

    # === 마이그레이션 ===
    # Alembic 이 사용할 DSN 을 직접 지정한다 (로컬·CI 에서 SQLite 로 갈아끼울 때 유용).
    # 미설정 시 primary DSN 의 비동기 드라이버를 동기 드라이버로 바꿔 쓴다.
    ALEMBIC_DATABASE_URL: str | None = Field(
        default=None,
        description="Alembic 전용 DSN (미설정 시 primary DSN 에서 자동 유도)",
    )

    @property
    def ALEMBIC_URL(self) -> URL:
        """Alembic 마이그레이션이 사용할 동기 DSN.

        Alembic 은 동기로 실행되므로 aiomysql(비동기 드라이버)을 쓸 수 없다.
        primary DSN 의 드라이버만 pymysql 로 바꿔서 같은 서버를 가리킨다.
        마이그레이션은 항상 primary 에서 실행한다 — replica 는 읽기 전용이다.
        """
        if self.ALEMBIC_DATABASE_URL:
            return make_url(self.ALEMBIC_DATABASE_URL)
        return self.MYSQL_WRITER_URL.set(drivername="mysql+pymysql")

    @property
    def MYSQL_URL(self) -> URL:
        """SQLAlchemy 비동기 연결 URL (aiomysql 드라이버) — primary(쓰기) 서버

        문자열로 이어 붙이지 않고 ``URL.create`` 로 만든다. 비밀번호의 ``@ / : # %`` 는
        렌더링 때 인코딩되고, 호스트는 IP·도메인 모두 가능하며 IPv6 는 렌더링 때 대괄호가
        씌워진다. f-string 조립은 이런 비밀번호에서 접속 정보 파싱을 깨는데, 그 실패는
        운영 비밀번호에서만 드러난다(service-hardening F-003). 로그에는
        ``render_as_string(hide_password=True)`` 로 남긴다.
        """
        return URL.create(
            "mysql+aiomysql",
            username=self.MYSQL_USER,
            password=self.MYSQL_PASSWORD,
            host=bare_host(self.MYSQL_HOST),
            port=self.MYSQL_PORT,
            database=self.MYSQL_DATABASE,
        )

    @property
    def MYSQL_WRITER_URL(self) -> URL:
        """primary(쓰기) 서버 URL — ``MYSQL_URL`` 의 의미를 드러낸 별칭"""
        return self.MYSQL_URL

    @property
    def _replica_entries(self) -> list[str]:
        """공백을 정리한 유효 replica 항목만 추린다."""
        return [entry.strip() for entry in self.MYSQL_REPLICA_HOSTS if entry.strip()]

    @property
    def MYSQL_REPLICA_URLS(self) -> list[URL]:
        """replica(읽기) 서버 URL 목록. 복제가 비활성이면 빈 목록."""
        if not self.replication_active:
            return []

        user = self.MYSQL_REPLICA_USER or self.MYSQL_USER
        password = self.MYSQL_REPLICA_PASSWORD or self.MYSQL_PASSWORD
        database = self.MYSQL_REPLICA_DATABASE or self.MYSQL_DATABASE

        urls = []
        for entry in self._replica_entries:
            host, port = split_host_port(entry, self.MYSQL_REPLICA_PORT)
            urls.append(
                URL.create(
                    "mysql+aiomysql",
                    username=user,
                    password=password,
                    host=host,
                    port=port,
                    database=database,
                )
            )
        return urls

    @property
    def replication_active(self) -> bool:
        """읽기/쓰기를 실제로 다른 서버로 보내는 상태인가."""
        return self.DB_ROUTER_ENABLED and self.DB_REPLICATION_ENABLED

    @property
    def routing_mode(self) -> Literal["single", "router-single", "router-replicated"]:
        """현재 라우팅 모드 (로그·헬스체크 표시용).

        - single:            라우터 미사용. 모든 쿼리 → primary
        - router-single:     라우터 사용, replica 없음. 모든 쿼리 → primary
        - router-replicated: 라우터 사용 + 복제. SELECT → replica / 쓰기 → primary
        """
        if not self.DB_ROUTER_ENABLED:
            return "single"
        return "router-replicated" if self.replication_active else "router-single"

    def describe_routing(self) -> dict[str, object]:
        """기동 시 로그로 남길 라우팅 구성 요약 (비밀번호는 마스킹)."""
        return {
            "mode": self.routing_mode,
            "router_enabled": self.DB_ROUTER_ENABLED,
            "replication_enabled": self.DB_REPLICATION_ENABLED,
            "sticky_after_write": self.DB_READ_STICKY_AFTER_WRITE,
            "writer": self.MYSQL_WRITER_URL.render_as_string(hide_password=True),
            "readers": [
                url.render_as_string(hide_password=True) for url in self.MYSQL_REPLICA_URLS
            ],
        }

    @model_validator(mode="after")
    def _validate_routing(self) -> "DatabaseSettings":
        """모순된 라우팅 설정을 기동 시점에 차단한다(fail-fast).

        조용히 무시하면 '복제를 켰다고 믿는데 실제로는 primary 만 쓰는' 상태가
        운영에서 성능 문제로만 드러난다. 설정 단계에서 실패시키는 편이 안전하다.
        """
        if self.DB_REPLICATION_ENABLED and not self.DB_ROUTER_ENABLED:
            raise ValueError(
                "DB_REPLICATION_ENABLED=true 는 DB_ROUTER_ENABLED=true 를 필요로 합니다. "
                "라우터를 켜지 않으면 읽기/쓰기를 분리할 수 없습니다."
            )
        if self.DB_REPLICATION_ENABLED and not self._replica_entries:
            raise ValueError(
                "DB_REPLICATION_ENABLED=true 인데 MYSQL_REPLICA_HOSTS 가 비어 있습니다. "
                '읽기 복제본을 최소 1대 지정하세요 (예: MYSQL_REPLICA_HOSTS=["replica-a"]).'
            )

        # 호스트 표기 오류는 엔진 생성 시점의 난해한 예외가 아니라 여기서 잡는다.
        for entry in self._replica_entries:
            split_host_port(entry, self.MYSQL_REPLICA_PORT)

        return self


# =============================================================================
# CORS 설정
# =============================================================================
class CORSSettings(BaseSettings):
    """
    CORS (Cross-Origin Resource Sharing) 설정

    프론트엔드와 백엔드가 다른 도메인에서 실행될 때 필요합니다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 허용할 Origin 목록 (["*"]는 모든 Origin 허용)
    CORS_ALLOW_ORIGINS: list[str] = Field(
        default=["*"],
        description="허용할 Origin 목록",
    )

    # 자격 증명 허용 여부 (쿠키, Authorization 헤더)
    # 주의: allow_origins=["*"]와 allow_credentials=True는 CORS 스펙상
    #       유효하지 않은 조합이다. credentials를 사용하려면 구체적인 Origin을 지정해야 한다.
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=False,
        description="자격 증명 허용 여부",
    )

    # 허용할 HTTP 메서드
    CORS_ALLOW_METHODS: list[str] = Field(
        default=["*"],
        description="허용할 HTTP 메서드",
    )

    # 허용할 HTTP 헤더
    CORS_ALLOW_HEADERS: list[str] = Field(
        default=["*"],
        description="허용할 HTTP 헤더",
    )

    # 브라우저에 노출할 응답 헤더
    CORS_EXPOSE_HEADERS: list[str] = Field(
        default=[],
        description="노출할 응답 헤더",
    )

    # Preflight 요청 캐시 시간 (초)
    CORS_MAX_AGE: int = Field(
        default=600,
        description="Preflight 캐시 시간(초)",
    )

    @model_validator(mode="after")
    def _reject_wildcard_with_credentials(self) -> "CORSSettings":
        """`allow_origins=["*"]` 와 `allow_credentials=True` 조합을 거부한다.

        이 조합은 CORS 스펙상 무효일 뿐 아니라, Starlette 은 이때 요청 Origin 을 그대로
        반영해 '자격증명 포함 임의 출처 허용'이라는 취약 상태가 된다. 잘못된 운영 설정을
        기동 시점에 차단한다(fail-fast).
        """
        if self.CORS_ALLOW_CREDENTIALS and "*" in self.CORS_ALLOW_ORIGINS:
            raise ValueError(
                "CORS_ALLOW_CREDENTIALS=True 와 CORS_ALLOW_ORIGINS=['*'] 는 함께 쓸 수 없습니다. "
                "자격증명을 허용하려면 구체적인 Origin 을 지정하세요."
            )
        return self


# =============================================================================
# 로깅 설정
# =============================================================================
class LogSettings(BaseSettings):
    """
    로깅 설정

    콘솔 및 파일 로깅을 설정합니다.
    DEBUG 모드에 따라 로그 레벨이 자동 결정됩니다.

    로그 레벨:
        - DEBUG: 디버깅용 상세 정보
        - INFO: 일반 정보 메시지
        - WARNING: 경고 (작은 문제)
        - ERROR: 오류 (큰 문제)
        - CRITICAL: 심각한 문제
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # === 출력 대상 설정 ===
    # 선언만 있고 로깅 구성(build_dictconfig)이 읽지 않는다 — false 로 둬도 콘솔
    # 핸들러는 항상 붙는다. 켜고 끄는 기능이 필요해지면 그때 연결한다.
    LOG_CONSOLE_ENABLED: bool = Field(
        default=True,
        description="콘솔 로그 활성화 (현재 미사용 — 콘솔 핸들러는 항상 붙는다)",
    )

    # 파일 로그 출력 활성화 (staging/production 에서만 파일 핸들러를 붙인다)
    LOG_FILE_ENABLED: bool = Field(
        default=True,
        description="파일 로그 활성화",
    )

    # SQL/드라이버 DEBUG·INFO 로그 opt-in.
    #
    # 기본은 차단이다. SQLAlchemy 의 echo 계열 로그는 SQL 본문과 **바인딩된 파라미터**를
    # 그대로 찍는데, 거기에는 사용자 식별자·검색어·이메일이 들어 있다. RedactingFilter 는
    # 알려진 키워드만 마스킹하므로 SQL 전문 노출을 막지 못한다.
    #
    # development/test 에서만 유효하다. staging/production 에서 true 면 기동이 실패한다
    # (validate_deployment_safety) — 환경 제한이 없으면 "잠깐 켜둔" 설정이 운영에 남는다.
    LOG_SQL_ECHO_ENABLED: bool = Field(
        default=False,
        description="SQL/드라이버 DEBUG·INFO 로그 허용 (development/test 전용)",
    )

    # === 로그 레벨 설정 ===
    # None이면 DEBUG 설정에 따라 자동 결정
    LOG_LEVEL: str | None = Field(
        default=None,
        description="전역 로그 레벨 (미설정 시 DEBUG 따라 자동 결정)",
    )

    # 콘솔 로그 레벨 (None이면 DEBUG 설정에 따라 자동 결정)
    LOG_CONSOLE_LEVEL: str | None = Field(
        default=None,
        description="콘솔 로그 레벨",
    )

    # 파일 로그 레벨
    LOG_FILE_LEVEL: str = Field(
        default="INFO",
        description="파일 로그 레벨",
    )

    # === 파일 설정 ===
    # 로그 파일 저장 디렉토리
    LOG_DIR: str = Field(
        default="logs",
        description="로그 디렉토리 경로",
    )

    # 앱 로그 파일명 패턴 ({date}는 YYYY-MM-DD로 치환)
    LOG_APP_FILENAME: str = Field(
        default="{date}_app.log",
        description="앱 로그 파일명 패턴",
    )

    # 에러 로그 파일명 패턴 ({date}는 YYYY-MM-DD로 치환)
    LOG_ERROR_FILENAME: str = Field(
        default="{date}_error.log",
        description="에러 로그 파일명 패턴",
    )

    # 단일 로그 파일 최대 크기 (MB)
    LOG_MAX_SIZE_MB: int = Field(
        default=10,
        description="로그 파일 최대 크기(MB)",
    )

    # 보관할 백업 로그 파일 개수
    LOG_BACKUP_COUNT: int = Field(
        default=5,
        description="백업 로그 파일 개수",
    )

    # === 포맷 설정 ===
    # 콘솔 로그 출력 형식
    LOG_CONSOLE_FORMAT: str = Field(
        default="[{asctime}] {levelname:8} [{name}:{funcName}:{lineno}] {message}",
        description="콘솔 로그 포맷",
    )

    # 파일 로그 출력 형식
    LOG_FILE_FORMAT: str = Field(
        default="[{asctime}] {levelname:8} [{name}:{funcName}:{lineno}] {message}",
        description="파일 로그 포맷",
    )

    # 날짜 출력 형식
    LOG_DATE_FORMAT: str = Field(
        default="%Y-%m-%d %H:%M:%S",
        description="날짜 포맷",
    )

    def get_log_dir(self) -> Path:
        """로그 디렉토리 경로 반환 (없으면 생성)"""
        log_dir = Path(self.LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir

    def get_effective_log_level(self, debug: bool) -> str:
        """
        실제 적용할 로그 레벨 반환

        LOG_LEVEL이 설정되면 해당 값 사용,
        미설정 시 debug=True면 DEBUG, False면 INFO
        """
        if self.LOG_LEVEL is not None:
            return self.LOG_LEVEL
        return "DEBUG" if debug else "INFO"

    def get_effective_console_level(self, debug: bool) -> str:
        """
        실제 적용할 콘솔 로그 레벨 반환

        LOG_CONSOLE_LEVEL이 설정되면 해당 값 사용,
        미설정 시 debug=True면 DEBUG, False면 INFO
        """
        if self.LOG_CONSOLE_LEVEL is not None:
            return self.LOG_CONSOLE_LEVEL
        return "DEBUG" if debug else "INFO"


# =============================================================================
# 미들웨어 설정
# =============================================================================
class MiddlewareSettings(BaseSettings):
    """
    미들웨어 설정

    접속 로그 수집 등 미들웨어 관련 설정을 관리합니다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 앱 앞에 둔 신뢰 프록시의 수(ClientIPResolver 가 쓴다).
    #
    # [배포 전 확인] 프록시(로드밸런서·nginx 등) 뒤에 배포하면 앞단 프록시 단 수로 설정한다.
    # 0 으로 두면 모든 클라이언트가 프록시 IP 하나로 보여 접속 로그와 로그인 rate limit
    # (API·/admin)이 전체 사용자를 한 사람으로 취급한다. 실제보다 크게 잡으면 클라이언트가
    # X-Forwarded-For 로 IP 를 위조해 한도를 우회한다.
    #
    # 기본값 0 은 의도다 — 전달 헤더(X-Forwarded-For / X-Real-IP)는 클라이언트가 그냥
    # 보낼 수 있는 값이라, 프록시 뒤가 아닌데 신뢰하면 아무나 헤더 한 줄로 접속 로그의
    # IP 를 위조한다. N 이면 XFF 의 오른쪽에서 N번째(우리 프록시가 붙인 값)만 채택하고,
    # 왼쪽(클라이언트가 써 보낸 값)은 보지 않는다. 예전 bool `TRUST_PROXY_HEADERS` 를
    # 대체한다(true ≈ 1).
    #
    # ponytail: 홉 "수" 만 센다. 경로마다 프록시 수가 다르거나 신뢰할 프록시를 CIDR
    # 목록으로 좁혀야 할 만큼 토폴로지가 복잡해지면 그때 목록 설정으로 올린다.
    TRUSTED_PROXY_HOPS: int = Field(
        default=0,
        ge=0,
        description=(
            "앱 앞의 신뢰 리버스 프록시 수 (0=전달 헤더 무시, N=XFF 오른쪽에서 N번째). "
            "프록시 뒤 배포면 반드시 앞단 프록시 단 수로 설정"
        ),
    )

    # 접속 로그의 query_string 에서 값을 `***` 로 가릴 키(대소문자 무시).
    ACCESS_LOG_SENSITIVE_QUERY_KEYS: list[str] = Field(
        default=[
            "password",
            "token",
            "access_token",
            "refresh_token",
            "secret",
            "api_key",
            "code",
        ],
        description="접속 로그 query_string 에서 값을 가릴 키",
    )

    # 접속 로그 수집 활성화
    ACCESS_LOG_ENABLED: bool = Field(
        default=True,
        description="접속 로그 수집 활성화",
    )

    # 접속 로그 보존 일수. 이보다 오래된 행은 Celery beat 가 매일 03:30(TIME_ZONE) 배치로 지운다
    # (app/features/home/tasks.py). 0 = 지우지 않음. 음수는 기동 시 검증 오류.
    ACCESS_LOG_RETENTION_DAYS: int = Field(
        default=365,
        ge=0,
        description="접속 로그 보존 일수 (0=삭제하지 않음)",
    )

    # 접속 로그 수집 제외 경로
    ACCESS_LOG_EXCLUDE_PATHS: list[str] = Field(
        default=["/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico"],
        description="로그 수집 제외 경로",
    )

    # 접속 로그 수집 제외 확장자
    ACCESS_LOG_EXCLUDE_EXTENSIONS: list[str] = Field(
        default=[".css", ".js", ".ico", ".png", ".jpg", ".jpeg", ".gif", ".svg"],
        description="로그 수집 제외 확장자",
    )


# =============================================================================
# Redis 설정
# =============================================================================
class RedisSettings(BaseSettings):
    """
    Redis 연결 설정

    캐시, 세션, 메시지 큐 등에 사용됩니다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Redis 서버 호스트
    REDIS_HOST: str = Field(
        default="localhost",
        description="Redis 서버 호스트",
    )

    # Redis 서버 포트
    REDIS_PORT: int = Field(
        default=6379,
        description="Redis 서버 포트",
    )

    # Redis 데이터베이스 번호 (0-15)
    REDIS_DB: int = Field(
        default=0,
        description="Redis 데이터베이스 번호",
    )

    # Redis 비밀번호 (None이면 인증 없이 접속)
    REDIS_PASSWORD: str | None = Field(
        default=None,
        description="Redis 비밀번호",
    )

    @property
    def REDIS_URL(self) -> str:
        """Redis 연결 URL

        비밀번호는 퍼센트 인코딩한다 — 그대로 넣으면 ``@ / : #`` 가 URL 구분자로 읽혀
        호스트·포트가 엉뚱하게 파싱된다(service-hardening F-003). redis-py 는 파싱할 때
        다시 디코딩한다.
        """
        if self.REDIS_PASSWORD:
            password = quote(self.REDIS_PASSWORD, safe="")
            return f"redis://:{password}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


# =============================================================================
# JWT 인증 설정
# =============================================================================
class JWTSettings(BaseSettings):
    """JWT 토큰(access/refresh) 설정.

    OAuth2 password flow 기반 인증에 사용됩니다.
    비밀 키는 운영 환경에서 반드시 안전한 값으로 교체하세요.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Access Token 서명 키
    ACCESS_TOKEN_SECRET_KEY: str = Field(
        default="change-this-access-token-secret-key",
        description="Access Token 서명 키",
    )
    # Refresh Token 서명 키 (access 와 다른 키 권장)
    REFRESH_TOKEN_SECRET_KEY: str = Field(
        default="change-this-refresh-token-secret-key",
        description="Refresh Token 서명 키",
    )
    # Access Token 만료 (분). access 는 만료 전 즉시 폐기 수단이 없으므로 짧게 둔다
    # (service-hardening ADR-011·R-201 — 폐기는 refresh family 로 한다).
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=15,
        gt=0,
        description="Access Token 만료 시간(분)",
    )
    # Refresh Token 만료 (일)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=7,
        description="Refresh Token 만료 시간(일)",
    )
    # JWT 서명 알고리즘. 대칭 키(HS 계열)만 허용한다 — 자유 문자열이면 `none` 이나
    # 키 형식이 다른 비대칭 알고리즘이 설정 실수로 들어온다(F-021).
    JWT_ALGORITHM: Literal["HS256", "HS384", "HS512"] = Field(
        default="HS256",
        description="JWT 서명 알고리즘(HS256/HS384/HS512)",
    )
    # 발급자(iss)·대상(aud). 검증 시 둘 다 일치해야 한다 — 다른 서비스가 같은 키로
    # 서명한 토큰을 이 API 가 받아들이지 않게 한다.
    JWT_ISSUER: str = Field(
        default="fastapi-project-structure",
        min_length=1,
        description="JWT 발급자(iss) claim",
    )
    JWT_AUDIENCE: str = Field(
        default="fastapi-project-structure-api",
        min_length=1,
        description="JWT 대상(aud) claim",
    )
    # 서버 간 시계 차이 허용(초). exp·nbf·iat 검증에 적용된다.
    JWT_LEEWAY_SECONDS: int = Field(
        default=10,
        ge=0,
        description="JWT 시각 검증 허용 오차(초)",
    )

    # 로그인·가입 rate limit (Redis 고정 창 — service-hardening ADR-013).
    # 로그인은 "IP + 사용자명" 과 "IP" 두 기준으로 센다. 앞쪽은 한 계정에 대한 추측,
    # 뒤쪽은 한 IP 가 여러 계정을 훑는 시도(credential stuffing)를 막는다.
    AUTH_LOGIN_MAX_ATTEMPTS: int = Field(
        default=5,
        gt=0,
        description="창 안에서 IP+사용자명 기준 최대 로그인 시도 수",
    )
    AUTH_LOGIN_IP_MAX_ATTEMPTS: int = Field(
        default=20,
        gt=0,
        description="창 안에서 IP 기준 최대 로그인 시도 수",
    )
    AUTH_LOGIN_WINDOW_SECONDS: int = Field(
        default=60,
        gt=0,
        description="로그인 rate limit 창 길이(초)",
    )
    AUTH_REGISTER_MAX_ATTEMPTS: int = Field(
        default=5,
        gt=0,
        description="창 안에서 IP 기준 최대 가입 시도 수",
    )
    AUTH_REGISTER_WINDOW_SECONDS: int = Field(
        default=3600,
        gt=0,
        description="가입 rate limit 창 길이(초)",
    )


# =============================================================================
# API 설정
# =============================================================================
class ApiSettings(BaseSettings):
    """REST API 관련 설정."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # REST API 버전. 선언만 있고 라우터 prefix 는 각 앱 router.py 의 "/v1/..." 가
    # 정한다 — 이 값을 바꿔도 URL 은 바뀌지 않는다.
    API_VERSION: str = Field(
        default="v1",
        description="REST API 버전",
    )


# =============================================================================
# 세션 설정
# =============================================================================
class SessionSettings(BaseSettings):
    """세션 쿠키 설정.

    Note:
        API 인증은 JWT(Bearer) 기반이다. 쿠키 세션은 `/admin` 로그인만 쓴다 —
        `SESSION_SECRET_KEY` 가 그 관리 세션(쿠키 `admin_session`, Path=/admin)의 Redis 키 HMAC 키다
        (admin-login ADR-003). `SESSION_COOKIE_NAME` 은 접속 로그 미들웨어가 session_id 를
        읽을 쿠키 이름이며 `/admin` 세션 쿠키와는 별개다. 설정 자체는 `.env` 에
        있으므로 config 가 로드해 둔다(설정의 단일 출처 유지).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 세션 쿠키 이름 (접속 로그의 session_id 가 이 이름의 쿠키를 읽는다)
    SESSION_COOKIE_NAME: str = Field(
        default="session",
        description="세션 쿠키 이름",
    )

    # 세션 키 (운영 환경에서 반드시 교체). /admin 관리 세션의 Redis 키를 만든다 —
    # admin:sess:{HMAC-SHA256(SESSION_SECRET_KEY, 세션 ID)} (admin-session-hardening ADR-001).
    # 바꾸면 기존 /admin 로그인 세션이 모두 끊긴다(새 키로는 옛 Redis 키를 찾지 못한다).
    SESSION_SECRET_KEY: str = Field(
        default="change-this-session-secret-key",
        description="세션 키 (/admin 관리 세션 Redis 키 HMAC)",
    )

    # /admin 관리 세션의 절대 만료(초). 로그인 시각부터 세고 연장되지 않는다. 쿠키 Max-Age 도 같다.
    ADMIN_SESSION_MAX_AGE_SECONDS: int = Field(
        default=28800,
        ge=60,
        description="/admin 관리 세션 절대 만료(초, 연장 불가)",
    )

    # /admin 관리 세션의 미사용 만료(초). 요청마다 Redis TTL 을 다시 이 값으로(절대 만료 이내) 맞춘다.
    ADMIN_SESSION_IDLE_SECONDS: int = Field(
        default=1800,
        ge=60,
        description="/admin 관리 세션 미사용 만료(초, 절대 만료 이하)",
    )

    @model_validator(mode="after")
    def _idle_within_max_age(self) -> "SessionSettings":
        """미사용 만료가 절대 만료보다 길면 미사용 만료는 의미가 없다 — 설정 실수로 본다."""
        if self.ADMIN_SESSION_IDLE_SECONDS > self.ADMIN_SESSION_MAX_AGE_SECONDS:
            raise ValueError(
                "ADMIN_SESSION_IDLE_SECONDS 는 ADMIN_SESSION_MAX_AGE_SECONDS 이하여야 합니다."
            )
        return self


# =============================================================================
# 설정 인스턴스 팩토리 (싱글톤)
# =============================================================================
@lru_cache
def get_timezone_settings() -> TimezoneSettings:
    """타임존 설정 인스턴스 반환 (캐싱)"""
    return TimezoneSettings()


@lru_cache
def get_app_settings() -> AppSettings:
    """앱 설정 인스턴스 반환 (캐싱)"""
    return AppSettings()


@lru_cache
def get_db_settings() -> DatabaseSettings:
    """DB 설정 인스턴스 반환 (캐싱)"""
    return DatabaseSettings()


@lru_cache
def get_cors_settings() -> CORSSettings:
    """CORS 설정 인스턴스 반환 (캐싱)"""
    return CORSSettings()


@lru_cache
def get_log_settings() -> LogSettings:
    """로그 설정 인스턴스 반환 (캐싱)"""
    return LogSettings()


@lru_cache
def get_redis_settings() -> RedisSettings:
    """Redis 설정 인스턴스 반환 (캐싱)"""
    return RedisSettings()


@lru_cache
def get_middleware_settings() -> MiddlewareSettings:
    """미들웨어 설정 인스턴스 반환 (캐싱)"""
    return MiddlewareSettings()


@lru_cache
def get_jwt_settings() -> JWTSettings:
    """JWT 설정 인스턴스 반환 (캐싱)"""
    return JWTSettings()


@lru_cache
def get_api_settings() -> ApiSettings:
    """API 설정 인스턴스 반환 (캐싱)"""
    return ApiSettings()


@lru_cache
def get_session_settings() -> SessionSettings:
    """세션 설정 인스턴스 반환 (캐싱)"""
    return SessionSettings()


# =============================================================================
# 편의를 위한 전역 설정 인스턴스
# =============================================================================
# 모듈 import 시 바로 사용 가능한 설정 인스턴스
# 예: from config import app_settings
timezone_settings = get_timezone_settings()
app_settings = get_app_settings()
db_settings = get_db_settings()
cors_settings = get_cors_settings()
log_settings = get_log_settings()
redis_settings = get_redis_settings()
middleware_settings = get_middleware_settings()
jwt_settings = get_jwt_settings()
api_settings = get_api_settings()
session_settings = get_session_settings()


# =============================================================================
# 설정 검사 — 출처(.env 또는 환경 변수)와 내용(예시 값·약한 키·배포 금지 조합)
# =============================================================================
# 잘못된 설정은 조용히 넘어가지 않고 기동 실패로 드러나야 한다 — 개발자는 오류 메시지를
# 보고 `.env` 를 고친다. 비밀값 검사는 test 를 뺀 모든 ENV, 운영 조합 검사는
# staging/production 에만 적용한다.
#
# /admin 은 슈퍼유저 로그인이 필요하므로(admin-login ADR-002) 관리 화면을 켠 배포
# (ADMIN_DISABLED=false)도 위반이 아니다. 개발·테스트 환경은 편의 기본값(관리 화면 켬,
# DEBUG=true)을 그대로 둔다.
def is_placeholder_secret(value: str) -> bool:
    """서명·세션 키가 자리표시자(placeholder)인지 판정한다.

    앞뒤 공백을 지우고 소문자로 바꾼 뒤 다음 중 하나면 placeholder 다.
        - ``change-this`` 를 포함한다 (위치·대소문자 무관)
        - ``your-`` 로 시작한다 (옛 예시 파일의 ``your-...-change-this`` 형식 포함)
        - 빈 문자열이다
    """
    v = value.strip().lower()
    return "change-this" in v or v.startswith("your-") or v == ""


# 서명·세션 키의 최소 길이. `secrets.token_urlsafe(48)` 은 64자다.
SECRET_KEY_MIN_LENGTH = 32

# `.env` 파일이 없을 때 환경 변수로 **직접** 들어와야 하는 값. 컨테이너처럼 파일 없이
# 주입하는 배포는 이것들이 모두 있으면 통과한다. 하나라도 없으면 코드 기본값으로 뜨게 되므로
# (예: ENV 가 없으면 development 로 간주돼 배포 게이트가 꺼진다) 기동을 멈춘다.
REQUIRED_WITHOUT_ENV_FILE = (
    "ENV",
    "ACCESS_TOKEN_SECRET_KEY",
    "REFRESH_TOKEN_SECRET_KEY",
    "SESSION_SECRET_KEY",
    "MYSQL_HOST",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "MYSQL_DATABASE",
)


def validate_env_source(
    env: str,
    env_file: Path = Path(".env"),
    environ: Mapping[str, str] = os.environ,
) -> None:
    """`.env` 가 없고 필수 값이 환경 변수로도 오지 않았으면 기동을 멈춘다.

    `env_file` 은 Settings 들의 ``env_file=".env"`` 와 같은 기준(작업 디렉터리)이다.
    test 는 검사하지 않는다(pytest 가 ENV=test 를 준다). 메시지에는 빠진 설정 **이름**만 담는다.

    Raises:
        RuntimeError: `.env` 도 없고 필수 환경 변수도 빠졌을 때.
    """
    if env == "test" or env_file.is_file():
        return
    missing = [name for name in REQUIRED_WITHOUT_ENV_FILE if name not in environ]
    if missing:
        raise RuntimeError(
            ".env 파일이 없고, 필수 설정이 환경 변수로도 주어지지 않았습니다: "
            + ", ".join(missing)
            + ". 로컬에서는 `cp .env.example .env` 후 값을 채우고, 배포에서는 환경 변수로 "
            "주입하세요."
        )


def validate_renamed_settings(
    env: str,
    env_file: Path = Path(".env"),
    environ: Mapping[str, str] = os.environ,
) -> None:
    """이름이 바뀐 설정이 `.env`·환경 변수에 남아 있으면 기동을 멈춘다.

    예전 ``ADMIN``(true=켬)은 ``ADMIN_DISABLED``(true=끔)로 바뀌었다. Settings 는
    ``extra="ignore"`` 라 남은 ``ADMIN=false`` 를 조용히 버리고 관리 화면을 **켠다** — 끄려던
    의도가 뒤집히므로 무시하지 않는다(admin-login ADR-006). test 는 검사하지 않는다(다른 검사와
    같다 — pytest 가 ENV=test 를 준다). 메시지에는 값을 담지 않는다.

    Raises:
        RuntimeError: ``ADMIN`` 이 남아 있을 때.
    """
    if env == "test":
        return
    names = {name.upper() for name in environ}
    if env_file.is_file():
        names |= {name.upper() for name in dotenv_values(env_file)}
    if "ADMIN" in names:
        raise RuntimeError(
            "설정 ADMIN 은 ADMIN_DISABLED 로 바뀌었습니다(의미가 반대입니다). "
            "ADMIN=false 였다면 ADMIN_DISABLED=true 로, 아니면 ADMIN 줄을 지우세요."
        )


def validate_deployment_safety() -> None:
    """안전하지 않은 설정이면 기동을 멈춘다.

    test 를 뺀 **모든 ENV**(개발 환경 포함) — 기본값·예시 값 그대로는 `.env` 를 채우라는 신호다:
        - placeholder secret  : ``is_placeholder_secret`` 가 참인 서명·세션 키
        - 짧은 secret         : 서명·세션 키가 ``SECRET_KEY_MIN_LENGTH`` 미만
        - 같은 JWT 키         : access == refresh
        - placeholder 비밀번호  : ``MYSQL_PASSWORD``(빈 값 포함) · ``REDIS_PASSWORD``.
          뒤의 것은 빈 값이 정당한 구성(인증 없는 사설망 Redis)이라 **값이 있을 때만** 본다.

    staging/production 만:
        - ``DEBUG=true``      : 상세 오류·문서 노출
        - 와일드카드 CORS     : ``CORS_ALLOW_ORIGINS`` 에 ``*``
        - SQL echo           : ``LOG_SQL_ECHO_ENABLED=true`` (파라미터가 로그에 남는다)
        - DEBUG 로그 레벨      : ``LOG_LEVEL=DEBUG`` (롤백 상세에 SQL·바인딩 값이 남는다)

    위반은 **한 번에 모두** 모아서 보고한다. 하나 고치고 재기동하는 왕복을
    줄이기 위해서다. 오류 메시지에는 설정 이름만 담고 값은 담지 않는다.

    Raises:
        RuntimeError: 위반이 하나라도 있을 때.
    """
    if app_settings.ENV == "test":
        return
    deployed = app_settings.ENV in ("staging", "production")

    problems: list[str] = []

    if deployed and app_settings.DEBUG:
        problems.append("DEBUG=true — 상세 오류와 API 문서가 노출됩니다. false 로 두세요.")
    for name, value in (
        ("ACCESS_TOKEN_SECRET_KEY", jwt_settings.ACCESS_TOKEN_SECRET_KEY),
        ("REFRESH_TOKEN_SECRET_KEY", jwt_settings.REFRESH_TOKEN_SECRET_KEY),
        ("SESSION_SECRET_KEY", session_settings.SESSION_SECRET_KEY),
        # 빈 MySQL 비밀번호는 무인증 DB 계정이다 — placeholder 와 같은 무게로 막는다.
        ("MYSQL_PASSWORD", db_settings.MYSQL_PASSWORD),
    ):
        if is_placeholder_secret(value):
            # 값 자체는 절대 메시지에 담지 않는다 (C-5).
            problems.append(f"{name} 이 기본 placeholder 입니다. 실제 키로 교체하세요.")
        elif name != "MYSQL_PASSWORD" and len(value.strip()) < SECRET_KEY_MIN_LENGTH:
            problems.append(f"{name} 이 {SECRET_KEY_MIN_LENGTH}자보다 짧습니다. 새로 생성하세요.")

    # Redis 비밀번호는 비어 있는 것이 정상 구성일 수 있다(인증 없는 사설망 Redis).
    # 빈 값을 위반으로 보면 멀쩡한 배포가 막히므로, **설정된 값이 예시일 때만** 잡는다.
    redis_password = redis_settings.REDIS_PASSWORD
    if redis_password and is_placeholder_secret(redis_password):
        problems.append(
            "REDIS_PASSWORD 이 기본 placeholder 입니다. 실제 값으로 바꾸거나, 쓰지 않으면 비우세요."
        )

    if jwt_settings.ACCESS_TOKEN_SECRET_KEY == jwt_settings.REFRESH_TOKEN_SECRET_KEY:
        # 같은 키로 서명하면 refresh 토큰이 access 토큰으로도 검증을 통과한다.
        problems.append(
            "ACCESS_TOKEN_SECRET_KEY 와 REFRESH_TOKEN_SECRET_KEY 가 동일합니다. "
            "서로 다른 키를 사용하세요."
        )

    if deployed and "*" in cors_settings.CORS_ALLOW_ORIGINS:
        problems.append("CORS_ALLOW_ORIGINS 에 와일드카드('*') 가 있습니다. 출처를 명시하세요.")

    if deployed and log_settings.LOG_SQL_ECHO_ENABLED:
        # SQL 로그에는 바인딩된 파라미터가 그대로 실린다. 운영에서 켤 이유가 없다.
        problems.append(
            "LOG_SQL_ECHO_ENABLED=true — SQL 본문과 파라미터가 로그에 남습니다. "
            "development/test 에서만 사용하세요."
        )

    if deployed and (log_settings.LOG_LEVEL or "").upper() == "DEBUG":
        # 롤백 로그의 SQL·바인딩 값 전문은 DEBUG 레코드로만 나간다(app/core/db/session.py).
        # DEBUG=true 와 달리 LOG_LEVEL 은 단독으로도 유효 레벨을 DEBUG 로 올린다.
        problems.append(
            "LOG_LEVEL=DEBUG — 롤백 상세에 SQL 본문과 바인딩된 값이 남습니다. "
            "INFO 이상으로 두세요."
        )

    if problems:
        raise RuntimeError(
            f"ENV={app_settings.ENV} 에서 안전하지 않은 설정으로 기동할 수 없습니다:\n  - "
            + "\n  - ".join(problems)
            + "\n`.env`(또는 환경 변수)를 고치세요. 키 생성: "
            'uv run python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )


validate_env_source(app_settings.ENV)
validate_renamed_settings(app_settings.ENV)
validate_deployment_safety()
