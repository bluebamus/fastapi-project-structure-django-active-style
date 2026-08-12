"""라우터만 있는 가짜 앱. 초기화 훅이 실행됐음을 기록한다."""

from tests.core._fakeapps import INIT_CALLS

INIT_CALLS.append("alpha")
