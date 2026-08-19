"""파일 로깅을 event loop 밖으로 밀어내는 bounded queue (계획서 §8, ADR-003).

## 왜 필요한가

`RotatingFileHandler` 를 root 에 직접 붙이면 **로그를 남기는 코루틴이 파일 쓰기를
직접 수행한다**. 디스크가 느리거나 로테이션(파일 rename + 새 파일 생성)이 걸리는
순간, 그 시간만큼 event loop 전체가 멈춘다. 요청 처리가 로그 I/O 뒤에서 대기한다.

해법은 표준적이다: 로그 레코드를 큐에 넣고(빠름), **별도 스레드**가 꺼내서 파일에
쓴다. `QueueHandler`/`QueueListener` 가 그 구조다.

## 왜 무한 큐가 아닌가

큐를 무한으로 두면 블로킹이 사라지는 대신 **메모리 증가**로 문제가 옮겨간다.
디스크가 계속 느리면 큐가 끝없이 자라고, 결국 OOM 으로 죽는다. 그건 개선이 아니라
증상의 이동이다. 그래서 상한을 두고, 넘치면 **버리되 세어서 드러낸다**.

조용한 드롭은 최악이다 — 로그가 없어진 줄도 모른다. 그래서 `BoundedQueueHandler`
는 클래스 단위 카운터를 노출하고, listener 종료 시 누적 드롭 수를 남긴다.

## 이 파일이 하지 않는 것

앱별 로거를 등록하지 않는다. `config.py` 의 설계(핸들러는 root 에만, `app=` 은 경로에서
산출)를 그대로 유지한다 — SQL 소음 차단도 `loggers` 항목이 아니라 **필터**로 한다
(`filters.SQLNoiseFilter`). 새 기능을 추가할 때 로깅 설정에 손댈 곳이 0 이라는 성질을
깨지 않기 위해서다.
"""

from __future__ import annotations

import queue
import threading
from logging.handlers import QueueHandler, QueueListener
from typing import Any

__all__ = [
    "LOG_QUEUE_MAXSIZE",
    "BoundedQueueHandler",
    "make_log_queue",
    "start_queue_listener",
    "stop_queue_listener",
]

# 큐 상한. 정상 트래픽의 순간 버스트는 흡수하되 무제한 증가는 막는 크기.
LOG_QUEUE_MAXSIZE = 10_000


def make_log_queue() -> queue.Queue[Any]:
    """dictConfig 가 호출하는 큐 팩토리."""
    return queue.Queue(maxsize=LOG_QUEUE_MAXSIZE)


class BoundedQueueHandler(QueueHandler):
    """큐가 가득 차면 **버리고 센다**.

    기본 `QueueHandler` 는 `put_nowait` 가 실패하면 `handleError` 로 넘겨 stderr 에
    트레이스백을 찍는다. 로그가 밀리는 상황에서 stderr 에 트레이스백을 쏟으면
    상황이 더 나빠진다. 여기서는 조용히 세고 넘어가되, 그 수를 노출한다.
    """

    # 클래스 단위 카운터. 핸들러 인스턴스는 dictConfig 가 만들었다 버렸다 하므로
    # 인스턴스에 두면 재설정 때마다 0 이 된다.
    dropped = 0

    def enqueue(self, record: Any) -> None:
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            type(self).dropped += 1


# 프로세스당 하나. `python main.py` 와 `uvicorn main:app` 양쪽에서 bootstrap 이
# **정확히 한 번** 일어나야 하므로 모듈 전역에 둔다.
_listener: QueueListener | None = None
_lock = threading.Lock()


def start_queue_listener(handler: BoundedQueueHandler | None) -> bool:
    """큐 뒤의 listener 를 시작한다(멱등).

    Args:
        handler: dictConfig 가 만든 queue handler. `None` 이면 큐 로깅이 구성되지
            않은 환경(development/test)이므로 아무것도 하지 않는다.

    Returns:
        이번 호출이 listener 를 **새로 시작했으면** True.
    """
    global _listener
    if handler is None:
        return False
    with _lock:
        if _listener is not None:
            return False
        listener = getattr(handler, "listener", None)
        if listener is None:
            return False
        listener.start()
        _listener = listener
        return True


async def stop_queue_listener() -> None:
    """listener 를 멈추고 남은 레코드를 flush 한다(멱등).

    `ResourceManager` 가 종료 시 부른다. 코루틴 시그니처인 이유는 관리자가 정리
    함수를 `await` 하기 때문이다 — 실제 작업은 동기이고 짧다(큐를 비우고 스레드
    join). 자원 정리 **마지막**에 와야 앞선 자원들의 종료 로그가 파일에 남는다.
    """
    global _listener
    with _lock:
        listener = _listener
        _listener = None
    if listener is None:
        return

    listener.stop()

    if BoundedQueueHandler.dropped:
        # listener 가 멈춘 뒤라 로깅으로 남길 수 없다. 드롭이 있었다는 사실 자체는
        # 반드시 드러나야 하므로 stderr 로 직접 쓴다.
        import sys

        print(
            f"[logging] 큐 상한 초과로 버린 로그 레코드: {BoundedQueueHandler.dropped}건",
            file=sys.stderr,
        )
