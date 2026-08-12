"""모델·Admin 만 있고 라우터는 없는 가짜 앱.

models 를 여기서 import 하지 않는다 — `AppRegistry.import_models()` 가 실제로
일하는지 확인해야 하기 때문이다.
"""

from tests.core._fakeapps import INIT_CALLS

INIT_CALLS.append("beta")
