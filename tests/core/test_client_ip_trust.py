"""전달 헤더는 신뢰 proxy 설정이 있을 때만 접속 IP로 쓴다 (계획서 §8).

`X-Forwarded-For` / `X-Real-IP` 는 클라이언트가 마음대로 보낼 수 있는 값이다.
프록시 뒤가 아닌데도 이 값을 접속 IP 로 채택하면, 아무나 헤더 한 줄로 접속 로그의
IP 를 위조하고 IP 기반 조회(`/api/v1/home/access-logs/by-ip/...`)를 오염시킬 수 있다.
"""

import pytest

from app.core.middlewares.user_info_middleware import UserInfoMiddleware


class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeRequest:
    def __init__(self, headers=None, peer="203.0.113.9"):
        self.headers = headers or {}
        self.client = _FakeClient(peer) if peer else None


@pytest.fixture
def middleware():
    return UserInfoMiddleware(app=None)


@pytest.fixture
def trust_proxy(monkeypatch):
    def _set(value: bool):
        from app.core.middlewares import user_info_middleware as module

        monkeypatch.setattr(module.middleware_settings, "TRUST_PROXY_HEADERS", value)

    return _set


@pytest.mark.parametrize("header", ["X-Forwarded-For", "X-Real-IP"])
def test_forwarded_headers_are_ignored_by_default(middleware, trust_proxy, header):
    """기본값(신뢰 안 함)에서는 헤더를 무시하고 실제 접속 IP 를 쓴다."""
    trust_proxy(False)
    request = _FakeRequest({header: "1.2.3.4"}, peer="203.0.113.9")

    assert middleware._get_client_ip(request) == "203.0.113.9"


@pytest.mark.parametrize("header", ["X-Forwarded-For", "X-Real-IP"])
def test_forwarded_headers_are_used_when_proxy_is_trusted(middleware, trust_proxy, header):
    trust_proxy(True)
    request = _FakeRequest({header: "1.2.3.4"}, peer="203.0.113.9")

    assert middleware._get_client_ip(request) == "1.2.3.4"


def test_first_hop_is_taken_from_forwarded_chain(middleware, trust_proxy):
    trust_proxy(True)
    request = _FakeRequest({"X-Forwarded-For": "1.2.3.4, 10.0.0.1, 10.0.0.2"})

    assert middleware._get_client_ip(request) == "1.2.3.4"


def test_falls_back_to_unknown_without_peer(middleware, trust_proxy):
    trust_proxy(False)

    assert middleware._get_client_ip(_FakeRequest(peer=None)) == "unknown"


def test_default_setting_is_untrusting():
    """설정 기본값이 안전한 쪽이어야 한다 — 켜는 것이 명시적 선택."""
    from config import middleware_settings

    assert middleware_settings.TRUST_PROXY_HEADERS is False
