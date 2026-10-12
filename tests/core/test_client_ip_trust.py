"""클라이언트 IP 는 신뢰 프록시 홉 수만큼만 전달 헤더를 믿는다 (INV-6, ADR-005).

`X-Forwarded-For` / `X-Real-IP` 는 클라이언트가 마음대로 보낼 수 있는 값이다. 각 프록시는
XFF 의 **오른쪽 끝**에 자기가 받은 피어를 덧붙이므로, 믿을 수 있는 것은 우리 프록시가
붙인 오른쪽 값뿐이다. 왼쪽 값을 채택하면 아무나 헤더 한 줄로 접속 로그의 IP 를 위조하고
IP 기반 조회(`/api/v1/home/access-logs/by-ip/...`)를 오염시킨다.
"""

import pytest
from starlette.requests import Request

from app.core.middlewares.client_ip import ClientIPResolver


def _request(headers=(), peer: str | None = "203.0.113.9") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
        "client": (peer, 12345) if peer else None,
    }
    return Request(scope)


@pytest.mark.parametrize("header", ["X-Forwarded-For", "X-Real-IP"])
def test_forwarded_headers_are_ignored_with_zero_hops(header):
    """기본값(0홉)에서는 헤더를 무시하고 실제 접속 IP 를 쓴다."""
    request = _request([(header, "1.2.3.4")])

    assert ClientIPResolver(0).resolve(request) == "203.0.113.9"


def test_one_hop_takes_the_value_appended_by_our_proxy():
    """클라이언트가 왼쪽에 위조 값을 넣어도, 우리 프록시가 붙인 오른쪽 값이 채택된다."""
    request = _request([("X-Forwarded-For", "6.6.6.6, 198.51.100.7")], peer="10.0.0.1")

    assert ClientIPResolver(1).resolve(request) == "198.51.100.7"


def test_two_hops_take_the_second_value_from_the_right():
    request = _request(
        [("X-Forwarded-For", "6.6.6.6, 198.51.100.7, 10.0.0.2")],
        peer="10.0.0.1",
    )

    assert ClientIPResolver(2).resolve(request) == "198.51.100.7"


def test_repeated_forwarded_headers_form_one_list():
    """XFF 헤더가 여러 줄이면 순서대로 이은 하나의 목록이다."""
    request = _request(
        [("X-Forwarded-For", "6.6.6.6"), ("X-Forwarded-For", "198.51.100.7")],
        peer="10.0.0.1",
    )

    assert ClientIPResolver(1).resolve(request) == "198.51.100.7"


def test_shorter_chain_than_hops_falls_back_to_peer():
    request = _request([("X-Forwarded-For", "198.51.100.7")], peer="10.0.0.1")

    assert ClientIPResolver(2).resolve(request) == "10.0.0.1"


@pytest.mark.parametrize("value", ["not-an-ip", "1.2.3.4:5678", "<script>"])
def test_non_ip_value_falls_back_to_peer(value):
    request = _request([("X-Forwarded-For", f"6.6.6.6, {value}")], peer="10.0.0.1")

    assert ClientIPResolver(1).resolve(request) == "10.0.0.1"


def test_ipv6_value_is_accepted_and_normalized():
    request = _request([("X-Forwarded-For", "2001:DB8:0:0::1")], peer="10.0.0.1")

    assert ClientIPResolver(1).resolve(request) == "2001:db8::1"


def test_real_ip_is_used_only_without_forwarded_for():
    resolver = ClientIPResolver(1)

    assert resolver.resolve(_request([("X-Real-IP", "198.51.100.7")])) == "198.51.100.7"
    both = _request([("X-Real-IP", "6.6.6.6"), ("X-Forwarded-For", "198.51.100.8")])
    assert resolver.resolve(both) == "198.51.100.8"


def test_no_headers_with_hops_falls_back_to_peer():
    assert ClientIPResolver(1).resolve(_request()) == "203.0.113.9"


def test_falls_back_to_unknown_without_peer():
    assert ClientIPResolver(0).resolve(_request(peer=None)) == "unknown"


def test_negative_hops_are_rejected():
    with pytest.raises(ValueError):
        ClientIPResolver(-1)


def test_default_setting_is_untrusting():
    """설정 기본값이 안전한 쪽이어야 한다 — 프록시를 세는 것이 명시적 선택."""
    from config import MiddlewareSettings

    assert MiddlewareSettings.model_fields["TRUSTED_PROXY_HOPS"].default == 0


def test_middleware_uses_the_injected_resolver():
    """미들웨어는 판정기를 생성자로 받는다 — 설정을 직접 읽지 않는다."""
    from app.core.middlewares.user_info_middleware import UserInfoMiddleware

    middleware = UserInfoMiddleware(app=None, ip_resolver=ClientIPResolver(1))
    request = _request([("X-Forwarded-For", "6.6.6.6, 198.51.100.7")], peer="10.0.0.1")

    assert middleware._collect_request_info(request)["ip_address"] == "198.51.100.7"
