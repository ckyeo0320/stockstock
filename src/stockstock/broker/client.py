"""KIS API 브로커 클라이언트.

python-kis(PyKis) 래퍼로 인증, 토큰 관리, 레이트 리밋을 처리합니다.
"""

from __future__ import annotations

from pykis import PyKis

from stockstock.broker.rate_limiter import TokenBucketRateLimiter
from stockstock.config import BrokerConfig, TradingConfig
from stockstock.logging_config import get_logger

log = get_logger(__name__)


class BrokerClient:
    """KIS API 클라이언트 래퍼."""

    def __init__(self, broker_config: BrokerConfig, trading_config: TradingConfig) -> None:
        self._config = broker_config
        self._trading_config = trading_config
        self._is_virtual = trading_config.mode == "paper"

        # 레이트 리미터: paper 5req/s, live 20req/s
        rate = 5 if self._is_virtual else 20
        self._rate_limiter = TokenBucketRateLimiter(rate=rate)

        # PyKis 초기화
        self._kis = PyKis(
            id=broker_config.hts_id,
            account=broker_config.account_number,
            appkey=broker_config.app_key.get_secret_value(),
            secretkey=broker_config.app_secret.get_secret_value(),
            virtual=self._is_virtual,
            keep_token=True,
        )

        mode_str = "Paper" if self._is_virtual else "Live"
        log.info(
            "broker_client_initialized",
            mode=mode_str,
            rate_limit=rate,
            account=broker_config.account_number,
        )

    def throttle(self) -> None:
        """API 호출 전 레이트 리밋을 적용합니다."""
        self._rate_limiter.acquire()

    def stock(self, symbol: str):
        """종목 객체를 반환합니다."""
        self.throttle()
        return self._kis.stock(symbol)

    def account(self):
        """계좌 객체를 반환합니다."""
        self.throttle()
        return self._kis.account()

    @property
    def is_virtual(self) -> bool:
        return self._is_virtual

    @property
    def kis(self) -> PyKis:
        """내부 PyKis 인스턴스에 직접 접근합니다 (고급 사용)."""
        return self._kis
