"""언더스코어로 시작하는 패키지 — 발견 대상에서 제외돼야 한다 (NFR-02).

작업용·비활성 디렉터리를 앱으로 오인해 import 하면, 미완성 코드가 부팅 경로에
끌려 들어온다. 이 패키지가 `INIT_CALLS` 에 나타나면 제외 규칙이 깨진 것이다.
"""

from tests.core._fakeapps import INIT_CALLS

INIT_CALLS.append("_hidden")
