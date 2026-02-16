"""레이트 리미터 테스트."""

import time

from stockstock.broker.rate_limiter import TokenBucketRateLimiter


def test_initial_tokens():
    limiter = TokenBucketRateLimiter(rate=5)
    assert limiter.available_tokens == 5.0


def test_acquire_reduces_tokens():
    limiter = TokenBucketRateLimiter(rate=5)
    limiter.acquire()
    assert limiter.available_tokens < 5.0


def test_rate_limiting():
    """레이트 리미터가 요청 속도를 제한하는지 확인."""
    limiter = TokenBucketRateLimiter(rate=10, period=1.0)

    start = time.monotonic()
    for _ in range(10):
        limiter.acquire()
    elapsed = time.monotonic() - start

    # 10개 토큰을 소비하는 데 1초 미만이어야 함 (초기 토큰 사용)
    assert elapsed < 1.5


def test_refill():
    """시간 경과 후 토큰이 리필되는지 확인."""
    limiter = TokenBucketRateLimiter(rate=10, period=1.0)

    # 모든 토큰 소비
    for _ in range(10):
        limiter.acquire()

    # 잠시 대기 후 토큰 확인
    time.sleep(0.2)
    assert limiter.available_tokens > 0
