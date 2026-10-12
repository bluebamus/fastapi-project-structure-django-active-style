"""DSN 조립 계약 테스트 (service-hardening F-003).

DSN 을 f-string 으로 이어 붙이면 비밀번호의 ``@ / : # ?`` 가 URL 구분자로 읽혀 접속
정보가 엉뚱하게 파싱되고, ``%`` 는 Alembic 의 ConfigParser 보간에서 ``ValueError`` 를 낸다.
이 실패는 **운영 비밀번호에서만** 드러난다 — 개발 기본값에는 특수문자가 없기 때문이다.
그래서 일부러 고약한 비밀번호로 왕복을 고정한다.
"""

from alembic.config import Config
from redis.connection import parse_url
from sqlalchemy.engine import make_url

from config import DatabaseSettings, RedisSettings

# 구분자(@ : / # ?)와 보간 문자(%)를 한 번에 담는다.
NASTY_PASSWORD = "p@ss:w/rd%#?"  # noqa: S105 - 테스트 픽스처 값


def _db(**overrides) -> DatabaseSettings:
    return DatabaseSettings(_env_file=None, **overrides)


def test_writer_url_round_trips_a_password_with_separators():
    url = _db(MYSQL_PASSWORD=NASTY_PASSWORD, MYSQL_HOST="db.internal").MYSQL_WRITER_URL

    parsed = make_url(url.render_as_string(hide_password=False))
    assert parsed.password == NASTY_PASSWORD
    assert (parsed.host, parsed.port, parsed.database) == ("db.internal", 3306, "fastapi_db")


def test_replica_url_round_trips_a_password_with_separators():
    settings = _db(
        DB_ROUTER_ENABLED=True,
        DB_REPLICATION_ENABLED=True,
        MYSQL_REPLICA_HOSTS=["[2001:db8::10]:3307"],
        MYSQL_REPLICA_PASSWORD=NASTY_PASSWORD,
    )

    (url,) = settings.MYSQL_REPLICA_URLS
    parsed = make_url(url.render_as_string(hide_password=False))
    assert parsed.password == NASTY_PASSWORD
    assert (parsed.host, parsed.port) == ("2001:db8::10", 3307)


def test_ipv6_primary_host_round_trips():
    url = _db(MYSQL_HOST="::1").MYSQL_URL

    assert url.render_as_string(hide_password=False).startswith(
        "mysql+aiomysql://root:@[::1]:3306/"
    )
    assert make_url(url.render_as_string(hide_password=False)).host == "::1"


def test_alembic_url_switches_only_the_driver():
    settings = _db(MYSQL_PASSWORD=NASTY_PASSWORD)

    alembic_url = settings.ALEMBIC_URL
    assert alembic_url.drivername == "mysql+pymysql"
    assert alembic_url.set(drivername="mysql+aiomysql") == settings.MYSQL_WRITER_URL


def test_alembic_override_is_parsed_as_a_url():
    url = _db(ALEMBIC_DATABASE_URL="sqlite:///./local.db").ALEMBIC_URL

    assert url.drivername == "sqlite"
    assert url.database == "./local.db"


def test_alembic_config_survives_percent_in_the_password():
    """env.py 가 넘기는 값은 ConfigParser 보간을 통과해 원래 비밀번호로 돌아와야 한다."""
    url = _db(MYSQL_PASSWORD=NASTY_PASSWORD).ALEMBIC_URL
    config = Config()

    # migrations/env.py 와 같은 변환이다.
    config.set_main_option(
        "sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%")
    )

    assert make_url(config.get_main_option("sqlalchemy.url")).password == NASTY_PASSWORD


def test_env_py_escapes_percent_for_alembic():
    """env.py 의 변환이 빠지면 위 테스트는 의미가 없다 — 그 줄 자체를 고정한다."""
    from pathlib import Path

    env_py = Path(__file__).resolve().parents[2] / "migrations" / "env.py"
    text = env_py.read_text(encoding="utf-8")

    assert 'render_as_string(hide_password=False).replace("%", "%%")' in text


def test_describe_routing_hides_the_password_but_keeps_the_location():
    summary = _db(MYSQL_PASSWORD=NASTY_PASSWORD, MYSQL_HOST="db.internal").describe_routing()

    assert NASTY_PASSWORD not in summary["writer"]
    assert "p%40ss" not in summary["writer"]  # 인코딩된 형태로도 새지 않는다
    assert summary["writer"] == "mysql+aiomysql://root:***@db.internal:3306/fastapi_db"


def test_redis_url_round_trips_a_password_with_separators():
    settings = RedisSettings(
        _env_file=None, REDIS_HOST="cache.internal", REDIS_PASSWORD=NASTY_PASSWORD
    )

    kwargs = parse_url(settings.REDIS_URL)
    assert kwargs["password"] == NASTY_PASSWORD
    assert (kwargs["host"], kwargs["port"], kwargs["db"]) == ("cache.internal", 6379, 0)


def test_redis_url_without_password_has_no_credentials():
    kwargs = parse_url(RedisSettings(_env_file=None).REDIS_URL)

    assert "password" not in kwargs
