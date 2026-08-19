"""스키마 스냅샷 고정 — mixin 전환이 컬럼을 바꾸지 않았음을 증명한다 (Phase 3 게이트).

계획서 §4 는 "기존 모델 전환 후 Alembic schema diff 는 없어야 한다" 를 요구한다.
autogenerate 비교는 실제 DB 를 요구하므로(그건 Phase 5 의 MySQL 게이트다), 여기서는
`Base.metadata` 에서 뽑은 정규 서명을 리팩터링 **이전**에 떠 둔 골든과 대조한다.
컬럼 이름·타입·nullable·PK·default/onupdate 유무·index·unique 가 모두 같아야 한다.
"""

import json
from pathlib import Path

import pytest

from app.core.db.models_registry import import_all_models
from app.core.models.models_base import Base

GOLDEN = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "crp"
    / "groups"
    / "orm-raw-repository"
    / "baseline"
    / "schema.json"
)


def _signature() -> dict:
    import_all_models()
    return {
        name: [
            {
                "name": column.name,
                "type": str(column.type),
                "nullable": column.nullable,
                "primary_key": column.primary_key,
                "has_default": column.default is not None,
                "has_onupdate": column.onupdate is not None,
                "index": bool(column.index),
                "unique": bool(column.unique),
            }
            for column in sorted(table.columns, key=lambda c: c.name)
        ]
        for name, table in sorted(Base.metadata.tables.items())
    }


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_table_set_is_unchanged(golden):
    assert sorted(_signature()) == sorted(golden)


@pytest.mark.parametrize(
    "table",
    ["blog_posts", "replies", "sns_posts", "user_access_logs", "users"],
)
def test_each_table_signature_is_unchanged(golden, table):
    assert (
        _signature()[table] == golden[table]
    ), f"{table} 의 컬럼 서명이 골든과 다릅니다 — Alembic schema diff 가 생깁니다."
