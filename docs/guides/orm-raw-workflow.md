# ORM / Raw 데이터 접근 워크플로

> **이 문서를 읽는 사람:** 이 구조로 새 기능을 만들려는 개발자.
> **이 문서가 답하는 것:** 언제 ORM 을 쓰고 언제 Raw SQL 을 쓰는가, 그리고 각각 어떤 순서로 어떤
> 파일을 만드는가.

이 저장소에는 두 접근 방식이 **각각 완결된 예제**로 들어 있습니다. 설명을 읽는 것보다
그 코드를 읽는 편이 빠릅니다 — 이 문서는 어디를 어떤 순서로 볼지 안내합니다.

| | ORM 예제 | Raw 예제 |
|---|---|---|
| 기능 | `app/features/catalog/` (상품 CRUD) | `app/features/reports/` (일별 매출) |
| 공개 API | `GET/POST /api/v1/catalog/products` 외 3개 | `GET /api/v1/reports/sales/daily` |
| 핵심 파일 | `repositories/product_repository.py` | `repositories/sales_report_repository.py` |

---

## 1. 무엇을 고를 것인가

**기본값은 ORM 입니다.** Raw SQL 은 ORM 을 우회하는 일반 수단이 아니라, 아래 네 상황에서
**선택하는** 도구입니다.

| Raw 를 고르는 상황 | 이유 |
|---|---|
| 복잡한 집계·윈도 함수·CTE | ORM 표현이 SQL 보다 길어지고 의도가 흐려진다 |
| SQL 계약이 더 명확한 리포트 | 결과 형태가 엔티티가 아니라 "행" 이다 |
| 실행 계획으로 관리해야 하는 성능 민감 조회 | 생성되는 SQL 을 통제해야 한다 |
| 저장 프로시저·DB 전용 기능 연계 | ORM 이 표현하지 못한다 |

**일반 단일 테이블 CRUD 는 예외 없이 ORM 입니다.**

### 판단이 애매할 때의 기준 하나

돌려주는 것이 **엔티티**인가 **계산 결과**인가를 보세요.
`Product` 한 건은 식별자와 수명주기가 있는 엔티티 — ORM 입니다.
`GROUP BY` 로 나온 일자별 합계는 식별자도 수명주기도 없는 계산 결과 — Raw 입니다.

reports 예제가 집계 전용 ORM 모델을 만들지 **않은** 이유가 이것입니다. 원본
`SalesOrder` 모델은 있지만(테이블 소유권·Admin 조회용), 집계는 Raw SQL 이 합니다.

---

## 2. 공통 계층 규칙 (ORM·Raw 둘 다)

두 방식은 **데이터 접근 방법만** 다르고 계층 규칙은 같습니다.

```
View(Router)  →  Dependency  →  Service  →  Repository  →  DB
   HTTP 만        조립만        업무 규칙     데이터 접근
```

| 계층 | 한다 | 하지 않는다 |
|---|---|---|
| **View** | 파라미터 수신, 응답 변환, **쓰기면 commit 1회** | SQL, 업무 분기 |
| **Dependency** | Service 조립, 세션 선택 | commit, Service 메서드 실행 |
| **Service** | 업무 규칙, DTO 변환 | HTTP 객체 인지, commit 결정 |
| **Repository** | 데이터 접근 | **commit** |

**commit 은 쓰기 View 가 응답 직전에 한 번만** 합니다. Repository 도 Dependency 도
commit 하지 않습니다 — 커밋 주체가 둘이 되면 실패 시 어디까지 남았는지 알 수 없습니다.

### 세션은 두 종류

| 용도 | Dependency | 규칙 |
|---|---|---|
| 조회 | `get_read_only_db_session` | 쓰기를 시도하면 예외. commit 없음 |
| 변경 | `get_writer_db_session` | 첫 쿼리부터 writer 고정 |

조회에 쓰기 세션을 재사용하지 마세요. 불필요한 COMMIT 왕복이 생기고, read-only 세션이
주는 안전망을 잃습니다. **Raw 라는 이유로 쓰기 세션을 쓰지 않습니다** — Raw 는 접근
방식이지 권한이 아닙니다.

---

## 3. ORM 워크플로 — catalog 예제 따라 읽기

새 기능을 만들 때의 파일 순서입니다. `app/features/catalog/` 를 같은 순서로 열어 보세요.

```bash
python -m scripts.new_app <name> --with-admin   # 1. 뼈대 생성
```

| # | 파일 | catalog 에서 볼 것 |
|---|---|---|
| 2 | `models/models.py` | mixin 조합(`UUIDPrimaryKeyMixin`+`CreatedAtMixin`+`UpdatedAtMixin`), 금액은 `Numeric` |
| 3 | `models/__init__.py` | 모델 재export |
| 4 | `migrations/versions/*.py` | `alembic revision` 후 **downgrade 도 구현** |
| 5 | `admin.py` | `admin_views` 리스트 — 중앙 등록 불필요 |
| 6 | `schemas/*.py` | 입력/출력 모델 분리, 모든 필드에 `description` |
| 7 | `repositories/*.py` | `BaseRepository[Model, PK타입]` 상속 |
| 8 | `services/*.py` | 업무 규칙. 지금은 얇지만 규칙이 생기면 여기 쌓인다 |
| 9 | `dependencies/*.py` | 조회용·변경용 **둘 다** 만든다 |
| 10 | `api/routers/v1/*.py` | operation_id 명시, 쓰기는 commit 1회 |
| 11 | `api/routers/router.py` | `<name>_router` — 이 이름이어야 자동 발견된다 |

### ORM 에서 자주 틀리는 것

**응답 DTO 검증은 commit 앞에서** 합니다.

```python
product = await service.create_product(payload)
response = ProductResponse.model_validate(product)   # 먼저
await service.commit()                               # 그다음
return response
```

commit 뒤에 검증하면 만료된 속성을 다시 읽으려다 lazy I/O 가 나고, 그 I/O 가 실패하면
**이미 커밋된 트랜잭션 위에서 500** 이 납니다 — 클라이언트는 실패로 보는데 데이터는
저장돼 있습니다.

**빈 PATCH 는 오류가 아닙니다.** 존재 확인 후 현재 상태를 그대로 돌려줍니다.
`BaseRepository.update()` 가 그렇게 동작하며, 전달하지 않은 필드는 건드리지 않습니다.

---

## 4. Raw 워크플로 — reports 예제 따라 읽기

계층은 같고 Repository 만 다릅니다.

```python
# app/features/reports/repositories/sales_report_repository.py
_DAILY_SALES = text("""
    SELECT DATE(o.created_at) AS sales_date, COUNT(*) AS order_count, ...
    WHERE o.created_at >= :start_date
      AND o.created_at < DATE_ADD(:end_date, INTERVAL 1 DAY)
""")

class SalesReportRawRepository(RawRepositoryBase):
    async def daily_sales(self, *, start_date, end_date):
        rows = await self.fetch_all(
            _DAILY_SALES,
            {"start_date": start_date, "end_date": end_date},
            query_name="sales_report.daily_sales",
        )
        return list(rows)
```

### 지켜야 하는 5가지

**① SQL 은 모듈/클래스 상수입니다.** 요청 값으로 SQL 을 **조립하지 않습니다**.

```python
text(f"SELECT * FROM t WHERE id = {user_id}")   # 금지 — 정적 검사가 막는다
text("SELECT * FROM t WHERE id = :id")          # 허용
```

`tests/core/test_raw_sql_static_guard.py` 가 `app/`·`scripts/`·`migrations/` 를 AST 로 훑어
조립된 SQL 을 거부합니다. 리뷰가 아니라 **코드가 막습니다**.

**② 모든 외부 값은 named bind 입니다.** `IN` 목록은 `bindparam(expanding=True)` 를 씁니다.

**③ 식별자는 allowlist 로.** 정렬 컬럼처럼 bind 할 수 없는 것은 코드가 소유한 목록에서
고릅니다(`ensure_identifier()`).

**④ 결과는 `RowMapping` 이고 DTO 변환은 Service 가 합니다.** View 가 `RowMapping` 을 직접
돌려주면 SQL 컬럼 변경이 곧바로 공개 API 변경이 됩니다.

```python
return [DailySalesItem.model_validate(dict(row)) for row in rows]
```

DTO 필드 이름과 SQL 의 컬럼 alias 가 어긋나면 **그 자리에서 실패**합니다. 이게 의도된
안전망입니다.

**⑤ `query_name` 은 필수입니다.** Base 가 질의 이름·소요 시간·성공 여부만 로그로 남기고
**SQL 본문과 파라미터는 남기지 않습니다**. 파라미터에는 사용자 식별자·검색어가 그대로
들어 있습니다.

### 결과 API 의 의미 (임의로 바꾸지 마세요)

| 메서드 | 0행 | 1행 | 복수 행 |
|---|---|---|---|
| `fetch_one` | `None` | `RowMapping` | **오류** |
| `fetch_all` | `[]` | 1개 목록 | 목록 |
| `fetch_scalar` | `None` | 값 (SQL `NULL` 도 `None`) | **오류** |
| `execute` | 영향 행 수(`int`), 드라이버 미제공 시 `None` | | |

`fetch_scalar` 는 "0행" 과 "값이 NULL" 을 구분하지 못합니다. 구분이 필요하면 `fetch_one`
을 쓰세요.

### DB 방언은 실제 DB 에서 검증합니다

reports 의 집계 SQL 은 MySQL 문법(`DATE_ADD(..., INTERVAL 1 DAY)`)입니다.
**SQLite 통과는 MySQL 승인 근거가 되지 못합니다.** 그래서:

```bash
docker compose -f compose.test.yaml up -d --wait
pytest -m mysql
docker compose -f compose.test.yaml down -v
```

기능 테스트는 MySQL 에 의존하는 **한 지점만** 대체하고, 실제 SQL 은
`tests/integration/test_sales_report_mysql.py` 가 MySQL 8.4 에 대고 확인합니다.
운영 SQL 을 테스트 편의로 문자열 치환하지 않습니다.

---

## 5. Raw 로 쓰기(DML)를 해야 한다면

공개 endpoint 를 만들지 않는 것이 이 저장소의 선택입니다. 필요하면 **Service/UoW 가
writer 세션의 commit/rollback 을 소유**하고 Repository 는 rowcount 만 돌려줍니다.
형태는 `tests/integration/test_sales_report_mysql.py` 하단 `_SalesOrderWriteService` 를
보세요.

read-only 세션에서 Raw DML 을 시도하면 `ReadOnlyRoutingError` 로 거부됩니다.
`DB_ROUTER_ENABLED` 설정과 **무관하게** 그렇습니다.

---

## 6. 더 깊이

| 문서 | 내용 |
|---|---|
| [`../orm-raw-repository/2026-08-13/workflow-guide.md`](../orm-raw-repository/2026-08-13/workflow-guide.md) | 원본 지침서 — 코드 예시 전문, 보안 규칙, 테스트 지침 |
| [`../orm-raw-repository/2026-08-13/requirements.md`](../orm-raw-repository/2026-08-13/requirements.md) | 요구 명세 — 각 규칙의 수용 기준 |
| [`../../README.md#앱-자동-등록-규약`](../../README.md) | 앱 자동 등록 규약 |

위 두 문서는 이 구조를 만들 때의 **설계 기준선**입니다. 규칙의 근거를 확인하거나
"왜 이렇게 정했는가" 가 궁금할 때 보세요. 일상적인 개발에는 이 문서와 두 예제 코드로
충분합니다.

> 규칙이 실제로 지켜지는지는 테스트가 강제합니다. 위반하면 `pytest` 가 막습니다 —
> 문서를 안 읽어도 틀린 코드는 통과하지 못하게 되어 있습니다.
