"""컨벤션 라우터 — 변수명은 `<앱이름>_router` 여야 한다."""

from fastapi import APIRouter

alpha_router = APIRouter()


@alpha_router.get("/ping")
async def ping() -> dict[str, str]:
    return {"pong": "alpha"}
