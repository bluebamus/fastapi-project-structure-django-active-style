"""공통 모델 mixin 조합 (계획서 §4).

`Base` + `UUIDPrimaryKeyMixin` / `CreatedAtMixin` / `UpdatedAtMixin` 의 작은 조합으로
공통 컬럼을 구성한다. 지금까지는 mixin 이 정의만 되어 있고 모델마다 같은 컬럼을
복사해 두고 있었다 — 한쪽만 고치면 조용히 어긋나는 구조였다.
"""

import pytest

from app.core.models import models_base

MODELS_WITH_UPDATED_AT = ["blog_posts", "replies", "sns_posts", "users"]


@pytest.mark.parametrize("name", ["UUIDPrimaryKeyMixin", "CreatedAtMixin", "UpdatedAtMixin"])
def test_canonical_mixin_exists(name):
    assert hasattr(models_base, name), f"정식 mixin {name} 이 없습니다."


@pytest.mark.parametrize(
    "canonical,alias",
    [("UUIDPrimaryKeyMixin", "UUID" + "Mixin"), ("CreatedAtMixin", "Timestamp" + "Mixin")],
)
def test_deprecated_alias_is_same_object(canonical, alias):
    assert getattr(models_base, alias) is getattr(models_base, canonical)


def _model(table_name):
    from app.core.db.models_registry import import_all_models
    from app.core.models.models_base import Base

    import_all_models()
    for mapper in Base.registry.mappers:
        if mapper.class_.__tablename__ == table_name:
            return mapper.class_
    raise AssertionError(f"{table_name} 모델을 찾지 못했습니다.")


@pytest.mark.parametrize(
    "table", ["blog_posts", "replies", "sns_posts", "user_access_logs", "users"]
)
def test_models_use_the_shared_pk_mixin(table):
    """모델이 PK 컬럼을 각자 복사하지 않고 공통 mixin 에서 받는다."""
    assert issubclass(_model(table), models_base.UUIDPrimaryKeyMixin)


@pytest.mark.parametrize(
    "table", ["blog_posts", "replies", "sns_posts", "user_access_logs", "users"]
)
def test_models_use_the_shared_created_at_mixin(table):
    assert issubclass(_model(table), models_base.CreatedAtMixin)


@pytest.mark.parametrize("table", MODELS_WITH_UPDATED_AT)
def test_models_with_updated_at_use_that_mixin(table):
    assert issubclass(_model(table), models_base.UpdatedAtMixin)


def test_access_log_has_no_updated_at():
    """updated_at 을 갖지 않던 모델에 mixin 전환이 컬럼을 새로 만들지 않는다."""
    model = _model("user_access_logs")

    assert not issubclass(model, models_base.UpdatedAtMixin)
    assert "updated_at" not in model.__table__.columns
