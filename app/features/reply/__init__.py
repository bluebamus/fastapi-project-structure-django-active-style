"""reply 기능 패키지.

이 파일은 **가볍게 유지한다**. 라우터·모델을 여기서 import 하지 않는다.

``AppRegistry`` 가 발견(``discover()``)과 결선(``install_routers()`` /
``import_models()`` / ``install_admin()``)을 분리해 두었고, 결선은 컨벤션 경로
(``api/routers/router.py``, ``models/``, ``admin.py``)를 직접 import 한다.
여기서 미리 끌어오면 "앱이 있는지" 만 알고 싶은 경로(Alembic·ADMIN=false 등)까지
라우팅 트리와 DB 모듈을 통째로 메모리에 올린다.

경계는 ``tests/core/test_import_boundary.py`` 가 깨끗한 서브프로세스에서 지킨다.
"""
