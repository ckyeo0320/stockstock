"""토큰 버킷 레이트 리미터.

KIS API 레이트 제한을 준수합니다:
- Live: 20 requests/sec
- Paper: 5 requests/sec
"""

from __future__ import annotations

import threading
import time


class TokenBucketRateLimiter:
    """스레드 안전한 토큰 버킷 레이트 리미터."""

    def __init__(self, rate: int, period: float = 1.0) -> None:
        """
        Args:
            rate: 기간 내 허용되는 최대 요청 수.
            period: 토큰이 리필되는 기간 (초).
        """
        self._rate = rate
        self._period = period
        self._tokens = float(rate)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """토큰 1개를 획득합니다. 토큰이 없으면 대기합니다."""
        while True:
            with self._lock:
                self._refill()

                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return

                wait_time = (1.0 - self._tokens) * (self._period / self._rate)

            # lock 해제 후 대기 (다른 스레드 차단 방지)
            time.sleep(wait_time)

    def _refill(self) -> None:
        """경과 시간에 따라 토큰을 리필합니다."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            float(self._rate),
            self._tokens + elapsed * (self._rate / self._period),
        )
        self._last_refill = now

    @property
    def available_tokens(self) -> float:
        """현재 사용 가능한 토큰 수를 반환합니다."""
        with self._lock:
            self._refill()
            return self._tokens
