"""계좌 잔고 및 포트폴리오 조회 모듈."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from stockstock.broker.client import BrokerClient
from stockstock.logging_config import get_logger

log = get_logger(__name__)


def _safe_decimal(value: object, default: Decimal = Decimal("0")) -> Decimal:
    """API 응답 값을 안전하게 Decimal로 변환합니다."""
    if value is None:
        return default
    s = str(value).strip()
    if not s or s == "None":
        return default
    try:
        return Decimal(s)
    except InvalidOperation:
        log.warning("decimal_conversion_failed", raw_value=repr(value))
        return default


def _safe_float(value: object, default: float = 0.0) -> float:
    """API 응답 값을 안전하게 float로 변환합니다."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        log.warning("float_conversion_failed", raw_value=repr(value))
        return default


@dataclass
class Holding:
    """보유 종목 정보."""

    symbol: str
    market: str
    quantity: int
    orderable_quantity: int
    purchase_price: Decimal
    current_price: Decimal
    purchase_amount: Decimal
    current_amount: Decimal
    profit: Decimal
    profit_rate: float
    exchange_rate: Decimal


@dataclass
class AccountBalance:
    """계좌 잔고 요약."""

    total_value_krw: Decimal
    purchase_amount_krw: Decimal
    total_profit_krw: Decimal
    profit_rate: float
    holdings: list[Holding]
    cash_usd: Decimal | None = None


def fetch_balance(client: BrokerClient, country: str = "US") -> AccountBalance:
    """계좌 잔고와 보유 종목을 조회합니다.

    Args:
        client: BrokerClient 인스턴스
        country: 국가 코드 (US, KR, HK, JP, VN, CN)
    """
    account = client.account()
    client.throttle()
    balance = account.balance(country=country)

    holdings = []
    for stock in balance.stocks:
        holdings.append(
            Holding(
                symbol=stock.symbol,
                market=str(getattr(stock, "market", "")),
                quantity=int(getattr(stock, "qty", 0) or 0),
                orderable_quantity=int(getattr(stock, "orderable", 0) or 0),
                purchase_price=_safe_decimal(stock.purchase_price),
                current_price=_safe_decimal(stock.current_price),
                purchase_amount=_safe_decimal(stock.purchase_amount),
                current_amount=_safe_decimal(stock.current_amount),
                profit=_safe_decimal(stock.profit),
                profit_rate=_safe_float(stock.profit_rate),
                exchange_rate=_safe_decimal(getattr(stock, "exchange_rate", 0)),
            )
        )

    # USD 캐시 잔고 추출
    cash_usd = None
    if hasattr(balance, "deposits"):
        usd_deposit = balance.deposits.get("USD")
        if usd_deposit is not None:
            cash_usd = _safe_decimal(usd_deposit)

    result = AccountBalance(
        total_value_krw=_safe_decimal(balance.current_amount),
        purchase_amount_krw=_safe_decimal(balance.purchase_amount),
        total_profit_krw=_safe_decimal(balance.profit),
        profit_rate=_safe_float(balance.profit_rate),
        holdings=holdings,
        cash_usd=cash_usd,
    )

    log.info(
        "balance_fetched",
        total_value_krw=str(result.total_value_krw),
        holdings_count=len(holdings),
        profit_rate=result.profit_rate,
    )

    return result
