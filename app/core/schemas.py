"""기능 스키마가 공유하는 기반 클래스."""

from typing import ClassVar, Self

from pydantic import BaseModel, model_validator


class PatchSchema(BaseModel):
    """부분 수정(PATCH) 요청 스키마의 기반.

    필드를 `X | None = None` 으로 선언하는 것은 "보내지 않아도 된다" 는 뜻이지
    "null 로 지울 수 있다" 는 뜻이 아니다. 보내지 않은 필드와 명시적 null 을
    `model_fields_set` 으로 가르고, `nullable_fields` 에 없는 필드의 명시적 null 은
    422 로 거부한다 — 그대로 두면 NOT NULL 컬럼에 None 이 들어가 DB 오류가 된다.

    하위 클래스는 DB 에서 NULL 을 허용하는 필드만 `nullable_fields` 에 적는다.
    """

    nullable_fields: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def _reject_null_for_required_columns(self) -> Self:
        rejected = sorted(
            name
            for name in self.model_fields_set
            if getattr(self, name) is None and name not in self.nullable_fields
        )
        if rejected:
            raise ValueError(f"null 로 바꿀 수 없는 필드입니다: {', '.join(rejected)}")
        return self
