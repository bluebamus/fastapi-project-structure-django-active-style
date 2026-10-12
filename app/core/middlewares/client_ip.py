"""클라이언트 IP 판정 (신뢰 프록시 홉 수 기준).

`X-Forwarded-For` 는 각 프록시가 **오른쪽 끝에** 자기가 받은 피어 주소를 덧붙인다.
그래서 왼쪽 값은 클라이언트가 처음부터 써 보낸 임의 문자열일 수 있고, 믿을 수 있는
것은 우리가 운영하는 프록시가 붙인 **오른쪽 값들**뿐이다. 신뢰 프록시가 N 개이면
직접 피어(가장 안쪽 프록시)를 제외한 XFF 목록의 오른쪽에서 N번째가 클라이언트다
(XFF 목록 + 직접 피어를 이은 체인에서는 오른쪽에서 N+1번째 — 직접 피어가 0번째).

[배포 전 확인] 홉 수는 설정 `TRUSTED_PROXY_HOPS` 로 받는다. 프록시 뒤 배포면 앞단 프록시 단 수로
설정한다 — 0 이면 모든 클라이언트가 프록시 IP 하나로 보여 접속 로그와 로그인 rate limit(API·
/admin)이 전체 사용자를 한 사람으로 취급하고, 실제보다 크게 잡으면 클라이언트가 XFF 로 IP 를
위조한다.
"""

import ipaddress

from starlette.requests import Request

UNKNOWN_CLIENT = "unknown"


class ClientIPResolver:
    """요청의 클라이언트 IP 를 신뢰 프록시 홉 수로 판정한다.

    - hops=0: 전달 헤더를 보지 않고 직접 피어(`request.client.host`).
    - hops=N: XFF 의 오른쪽에서 N번째. XFF 가 없으면 X-Real-IP(프록시가 설정한 값).
    - 채택한 값이 IP 가 아니거나 XFF 가 N 개보다 짧으면 직접 피어로 돌아간다.
    """

    def __init__(self, trusted_proxy_hops: int = 0) -> None:
        if trusted_proxy_hops < 0:
            raise ValueError("trusted_proxy_hops 는 0 이상이어야 합니다.")
        self.trusted_proxy_hops = trusted_proxy_hops

    def resolve(self, request: Request) -> str:
        peer = request.client.host if request.client else UNKNOWN_CLIENT
        if self.trusted_proxy_hops == 0:
            return peer

        # 여러 줄로 온 XFF 헤더는 순서대로 이어 붙인 하나의 목록과 같다(RFC 7230 §3.2.2).
        forwarded = [
            hop.strip()
            for header in request.headers.getlist("X-Forwarded-For")
            for hop in header.split(",")
            if hop.strip()
        ]
        if forwarded:
            if len(forwarded) < self.trusted_proxy_hops:
                return peer
            candidate = forwarded[-self.trusted_proxy_hops]
        else:
            candidate = request.headers.get("X-Real-IP", "").strip()

        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            return peer
