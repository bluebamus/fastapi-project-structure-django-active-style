"""Celery prefork 워커의 자원 생명주기 (계획서 §8, ADR-005).

## 지원 범위 — prefork 만

이 저장소는 Celery 를 **prefork 풀에서만** 지원한다(사용자 확정, REQ-009).
gevent/eventlet 은 그린스레드 모델이라 `run_async()` 의 asyncio 루프와 동시성
모델이 충돌하고, 제대로 쓰려면 태스크를 동기 드라이버로 다시 써야 한다.

    운영(Linux):  celery -A app.celery.app worker -l info          # 기본 = prefork
    로컬(Windows): celery -A app.celery.app worker --pool=solo -l info

Celery 는 4.0 부터 Windows 를 공식 지원하지 않는다. `solo` 는 fork 를 하지 않으므로
아래에서 다루는 커넥션 상속 문제 자체가 없다(신호도 오지 않는다 — 정상이다).

이 저장소의 Celery 는 태스크 하나짜리 **구조 예시**이며, 검증 범위도 그 수준이다
(residual-risk R-101).

## fork 가 왜 위험한가

prefork 는 이름 그대로 부모 프로세스를 **복제(fork)** 한다. 이때 열려 있던 **네트워크
소켓까지 그대로 복제된다** — 부모와 자식이 같은 파일 디스크립터를 가리킨다.

    부모: MySQL 소켓 #7 (커넥션 풀에 캐시)
       └─ fork ─→ 자식: 소켓 #7 을 그대로 물려받음

둘이 같은 소켓에 동시에 쿼리를 보내면 MySQL 프로토콜의 패킷 순서가 엉킨다
(`Commands out of sync`, `Packet sequence number wrong`). 최악의 경우 A 요청의 응답을
B 가 받는다.

**이 결함은 동시 실행이 겹쳐야 재현된다.** 개발에서는 태스크가 하나씩 도니까 멀쩡하고,
운영에서 처음 터진다. 그래서 테스트가 아니라 **구조**로 막는다: fork 직후 상속받은
풀을 통째로 버리고 자식 전용으로 다시 만든다.

## 왜 dispose 가 아니라 dispose(close=False) 인가

`AsyncEngine.dispose()` 는 기본적으로 풀의 커넥션을 **실제로 닫는다**. 자식이 그렇게
하면 **부모가 쓰고 있는 소켓이 닫힌다** — 고치려던 문제를 정확히 반대 방향으로 일으킨다.
`close=False` 는 커넥션을 닫지 않고 풀에서 **버리기만** 한다. 소켓은 부모 것으로 남고,
자식은 새 커넥션을 만든다. 이것이 fork-safe 한 유일한 방법이다.
"""

from __future__ import annotations

from typing import Any

from app.utils.logs import get_logger

logger = get_logger("celery_lifecycle")

__all__ = ["on_worker_process_init", "on_worker_process_shutdown", "register_worker_signals"]


def on_worker_process_init(**_: Any) -> None:
    """fork 직후 자식 프로세스에서 실행된다.

    부모에게 물려받은 커넥션 풀을 버린다. 커넥션 자체는 **닫지 않는다** — 부모가
    같은 소켓을 쓰고 있다. 자식은 다음 쿼리에서 자기 커넥션을 새로 만든다.

    루프도 초기화한다. `run_async()` 의 모듈 전역 루프는 fork 로 복제되는데,
    부모의 루프 객체를 자식이 이어 쓰면 그 루프에 묶인(부모의) 커넥션을 참조하게
    된다. 자식에서는 처음부터 다시 만들게 비운다.
    """
    from app.celery import task as task_module
    from app.core.db.session import background_engine, engine, read_engines

    for name, target in [
        ("writer", engine),
        *((f"reader#{index}", item) for index, item in enumerate(read_engines)),
        ("background", background_engine),
    ]:
        try:
            # `Engine.dispose(close=False)` 는 풀을 **새것으로 교체**하되 옛 풀의
            # 커넥션은 닫지 않는다. SQLAlchemy 가 문서에서 fork 직후 자식용으로
            # 지목하는 바로 그 형태다. close=True 면 부모가 쓰는 소켓을 닫아버린다.
            #
            # async 엔진이 아니라 `sync_engine` 을 쓰는 이유는 이 지점이 **동기**
            # 컨텍스트(fork 직후 신호 핸들러)라 await 할 루프가 없기 때문이다.
            target.sync_engine.dispose(close=False)
        except Exception as error:
            # 정리 실패로 워커 기동을 막지 않는다. 다음 커넥션 요청에서 새로 만든다.
            logger.warning(
                "[celery] 상속 pool 폐기 실패 engine=%s error_type=%s",
                name,
                type(error).__name__,
            )

    task_module.reset_worker_loop()
    logger.info("[celery] 자식 프로세스 자원 초기화 완료 — 상속 pool 폐기, 루프 재설정")


def on_worker_process_shutdown(**_: Any) -> None:
    """자식 프로세스 종료 시 실행된다. **멱등**이다.

    Celery 는 상황에 따라 이 신호를 두 번 보낼 수 있고, 정리는 두 번 불려도
    안전해야 한다. 루프 종료만 다루고 엔진 dispose 는 하지 않는다 — 자식이 만든
    커넥션은 프로세스 종료와 함께 OS 가 회수하며, 여기서 async dispose 를 돌리려면
    이미 닫는 중인 루프가 필요해 순환이 생긴다.
    """
    from app.celery import task as task_module

    closed = task_module.close_worker_loop()
    logger.info("[celery] 자식 프로세스 종료 정리 완료 (loop_closed=%s)", closed)


def register_worker_signals() -> None:
    """prefork 신호에 위 핸들러를 연결한다(멱등).

    `celery_app` 모듈이 import 될 때 호출한다. solo/threads 풀에서는 이 신호가
    발생하지 않으므로 연결해 두어도 아무 일도 일어나지 않는다.
    """
    from celery.signals import worker_process_init, worker_process_shutdown

    # `weak=False`: 핸들러가 모듈 전역 함수라 참조가 유지되지만, Celery 의 signal 은
    # 기본이 약한 참조라 등록이 조용히 사라지는 사고가 잦다. 명시적으로 강한 참조.
    worker_process_init.connect(on_worker_process_init, weak=False)
    worker_process_shutdown.connect(on_worker_process_shutdown, weak=False)
