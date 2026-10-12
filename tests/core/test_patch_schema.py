"""PATCH 의 명시적 null 은 nullable 컬럼에만 허용된다 (F-011, ADR-005).

`X | None = None` 은 "보내지 않아도 된다" 는 뜻이다. 이걸 "null 로 지울 수 있다" 로
받아 주면 NOT NULL 컬럼에 None 이 들어가 DB 무결성 오류가 되고, 응답은 409 "충돌" 이었다.
"""

import pkgutil
from importlib import import_module

import pytest
from pydantic import ValidationError

import app.features as features_pkg
from app.core.schemas import PatchSchema
from app.features.blog.models.models import Post
from app.features.blog.schemas.blog_schema import PostUpdate
from app.features.catalog.models.models import Product
from app.features.catalog.schemas.catalog_schema import ProductUpdate
from app.features.reply.models.models import Reply
from app.features.reply.schemas.reply_schema import ReplyUpdate
from app.features.sns.models.models import SnsPost
from app.features.sns.schemas.sns_schema import SnsPostUpdate
from app.features.user.models.models import User
from app.features.user.schemas.user_schema import UserUpdate

UPDATE_SCHEMAS = {
    PostUpdate: Post,
    ProductUpdate: Product,
    ReplyUpdate: Reply,
    SnsPostUpdate: SnsPost,
    UserUpdate: User,
}


class _Sample(PatchSchema):
    nullable_fields = frozenset({"note"})

    name: str | None = None
    note: str | None = None


def test_omitted_fields_are_not_rejected():
    assert _Sample().model_fields_set == set()


def test_explicit_null_on_required_field_is_rejected():
    with pytest.raises(ValidationError, match="name"):
        _Sample.model_validate({"name": None})


def test_explicit_null_on_nullable_field_is_allowed():
    assert _Sample.model_validate({"note": None}).model_dump(exclude_unset=True) == {"note": None}


def test_every_update_schema_in_features_is_a_patch_schema():
    """기능 스키마 모듈의 `*Update` 클래스는 모두 PatchSchema 를 상속한다(새 기능 포함)."""
    found = []
    for module_info in pkgutil.walk_packages(features_pkg.__path__, "app.features."):
        if ".schemas." not in module_info.name or ".tests" in module_info.name:
            continue
        module = import_module(module_info.name)
        for name, obj in vars(module).items():
            if (
                name.endswith("Update")
                and isinstance(obj, type)
                and obj.__module__ == module.__name__
            ):
                found.append(obj)
                assert issubclass(obj, PatchSchema), f"{module.__name__}.{name}"
    assert set(UPDATE_SCHEMAS) <= set(found)


@pytest.mark.parametrize("schema", list(UPDATE_SCHEMAS), ids=lambda s: s.__name__)
def test_nullable_fields_match_model_columns(schema):
    """허용 목록은 모델의 nullable 컬럼과 정확히 같다 — 둘이 어긋나면 DB 오류가 새어 나간다."""
    columns = UPDATE_SCHEMAS[schema].__table__.c
    nullable = {name for name in schema.model_fields if columns[name].nullable}

    assert schema.nullable_fields == nullable


@pytest.mark.parametrize("schema", list(UPDATE_SCHEMAS), ids=lambda s: s.__name__)
def test_null_is_rejected_for_each_not_null_column(schema):
    columns = UPDATE_SCHEMAS[schema].__table__.c
    for name in schema.model_fields:
        if columns[name].nullable:
            schema.model_validate({name: None})
        else:
            with pytest.raises(ValidationError):
                schema.model_validate({name: None})
