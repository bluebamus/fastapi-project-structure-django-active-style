"""가짜 앱의 ORM 모델.

애플리케이션의 `Base` 를 쓰지 않고 **전용 DeclarativeBase** 를 둔다. 앱 Base 에
붙이면 이 테스트용 테이블이 실제 `Base.metadata` 와 Alembic autogenerate 에
섞여 들어가, 테이블 inventory 검증(BC-02)을 오염시킨다.
"""

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class FakeBase(DeclarativeBase):
    """이 가짜 앱 전용 메타데이터."""


class Widget(FakeBase):
    __tablename__ = "fake_widgets"

    id: Mapped[int] = mapped_column(primary_key=True)


class Gadget(FakeBase):
    __tablename__ = "fake_gadgets"

    id: Mapped[int] = mapped_column(primary_key=True)
