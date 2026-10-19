"""관리 목록 created_at 날짜 필터 (security-ops-hardening ADR-004).

실제 ``UTCDateTime`` 컬럼(blog ``Post``)을 in-memory SQLite 에 만들고 필터가 만든 쿼리를 실행한다.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.admin_filters import LocalDateFilter
from app.core.db.session import Base
from app.features.blog.models.models import Post

SEOUL = ZoneInfo("Asia/Seoul")
NEW_YORK = ZoneInfo("America/New_York")
# 서울 2026-10-19 자정 = 2026-10-18T15:00Z
LOCAL_MIDNIGHT = datetime(2026, 10, 19, tzinfo=SEOUL)
NEXT_MIDNIGHT = datetime(2026, 10, 20, tzinfo=SEOUL)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        stamps = {
            "prev-day-last-second": LOCAL_MIDNIGHT - timedelta(seconds=1),
            "midnight": LOCAL_MIDNIGHT,
            "first-second": LOCAL_MIDNIGHT + timedelta(seconds=1),
            "day-last-second": NEXT_MIDNIGHT - timedelta(seconds=1),
            "next-midnight": NEXT_MIDNIGHT,
        }
        for key, at in stamps.items():
            s.add(Post(id=key, title=key, content="c", author="a", created_at=at))
        await s.commit()
        yield s
    await engine.dispose()


async def _ids(session, operation, value, tz=SEOUL) -> list[str]:
    query = await LocalDateFilter(Post.created_at, tz=tz).get_filtered_query(
        select(Post), operation, value, Post
    )
    rows = await session.execute(query.order_by(Post.created_at))
    return [post.id for post in rows.scalars().all()]


def test_day_bounds_are_local_midnights_in_utc():
    start, end = LocalDateFilter(Post.created_at, tz=SEOUL).day_bounds("2026-10-19")

    assert start == datetime(2026, 10, 18, 15, 0, tzinfo=UTC) and start.tzinfo is UTC
    assert end == datetime(2026, 10, 19, 15, 0, tzinfo=UTC)


def test_day_bounds_follow_dst_day_length():
    """미국 서머타임 시작일은 23시간이다 — 고정 오프셋으로 계산하면 경계가 1시간 어긋난다."""
    start, end = LocalDateFilter(Post.created_at, tz=NEW_YORK).day_bounds("2026-03-08")

    assert end - start == timedelta(hours=23)


def test_default_timezone_is_the_business_time_zone(monkeypatch):
    from app.core import admin_filters

    monkeypatch.setattr(admin_filters.timezone_settings, "TIME_ZONE", "Asia/Seoul")
    start, _ = LocalDateFilter(Post.created_at).day_bounds("2026-10-19")

    assert start == datetime(2026, 10, 18, 15, 0, tzinfo=UTC)


async def test_on_matches_the_local_day_only(session):
    assert await _ids(session, "on", "2026-10-19") == [
        "midnight",
        "first-second",
        "day-last-second",
    ]


async def test_on_or_after_includes_local_midnight(session):
    assert await _ids(session, "on_or_after", "2026-10-19") == [
        "midnight",
        "first-second",
        "day-last-second",
        "next-midnight",
    ]


async def test_before_excludes_local_midnight(session):
    assert await _ids(session, "before", "2026-10-19") == ["prev-day-last-second"]


@pytest.mark.parametrize(
    ("operation", "value"),
    [
        ("on", "2026-13-01"),
        ("on", "not-a-date"),
        ("on", "20261019"),
        ("on", "2026-10-19T00:00"),
        ("equals", "2026-10-19"),  # 이 필터에 없는 연산
        ("on", ""),
    ],
)
async def test_invalid_input_leaves_the_query_unfiltered(session, operation, value):
    assert len(await _ids(session, operation, value)) == 5


def test_offers_exactly_the_four_date_operations():
    flt = LocalDateFilter(Post.created_at)

    assert [op for op, _ in flt.get_operation_options_for_model(Post)] == [
        "on",
        "on_or_after",
        "before",
        "range",
    ]
    assert flt.parameter_name == "created_at"
    assert "YYYY-MM-DD" in flt.title


# =============================================================================
# 기간(range) — admin-session-hardening ADR-005
# =============================================================================
async def test_range_includes_both_ends(session):
    """시작일 자정 포함, 종료일 마지막 순간 포함, 종료일 다음 자정 제외."""
    assert await _ids(session, "range", "2026-10-19~2026-10-19") == [
        "midnight",
        "first-second",
        "day-last-second",
    ]


async def test_range_includes_the_last_microsecond_of_the_end_day(session):
    async with session.begin_nested():
        session.add(
            Post(
                id="last-micro",
                title="t",
                content="c",
                author="a",
                created_at=NEXT_MIDNIGHT - timedelta(microseconds=1),
            )
        )
    assert "last-micro" in await _ids(session, "range", "2026-10-18~2026-10-19")


async def test_range_over_several_days(session):
    assert await _ids(session, "range", "2026-10-18~2026-10-20") == [
        "prev-day-last-second",
        "midnight",
        "first-second",
        "day-last-second",
        "next-midnight",
    ]


async def test_range_with_only_start_is_open_ended(session):
    assert await _ids(session, "range", "2026-10-20~") == ["next-midnight"]


async def test_range_with_only_end_is_open_started(session):
    assert await _ids(session, "range", "~2026-10-18") == ["prev-day-last-second"]


async def test_range_bounds_follow_dst(session):
    """미국 서머타임 시작일 하루 기간은 23시간 — 지역 자정 두 개를 각각 UTC 로 바꾼다."""
    start, end = LocalDateFilter(Post.created_at, tz=NEW_YORK).range_bounds("2026-03-08~2026-03-08")

    assert start == datetime(2026, 3, 8, 5, 0, tzinfo=UTC)
    assert end - start == timedelta(hours=23)


@pytest.mark.parametrize(
    "value",
    [
        "2026-10-20~2026-10-19",  # 역순
        "2026-10-19",  # 구분자 없음
        "~",  # 둘 다 비었다
        "2026-10-19~not-a-date",
        "2026-13-01~2026-10-19",
        "2026-10-01~2026-10-02~2026-10-03",
    ],
)
async def test_invalid_range_leaves_the_query_unfiltered_with_a_warning(session, value, caplog):
    import logging

    with caplog.at_level(logging.WARNING):
        assert len(await _ids(session, "range", value)) == 5
    assert any("잘못된 날짜 필터" in r.getMessage() for r in caplog.records)


def test_quick_ranges_are_range_values_ending_today(monkeypatch):
    flt = LocalDateFilter(Post.created_at, tz=SEOUL)
    labels = dict(flt.quick_ranges())
    today = datetime.now(SEOUL).date()

    assert labels["오늘"] == f"{today}~{today}"
    assert labels["최근 7일"] == f"{today - timedelta(days=6)}~{today}"
    assert labels["최근 30일"] == f"{today - timedelta(days=29)}~{today}"
    assert all(flt.range_bounds(value) is not None for value in labels.values())


def test_filter_has_its_own_template_file():
    from app.features.admin import ADMIN_TEMPLATES_DIR

    flt = LocalDateFilter(Post.created_at)
    assert (ADMIN_TEMPLATES_DIR / flt.template).is_file()
