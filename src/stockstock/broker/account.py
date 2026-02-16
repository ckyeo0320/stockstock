"""계좌 잔고 및 포트폴리오 조회 모듈."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from stockstock.broker.client import BrokerClient
from stockstock.logging_config import get_logger

log = get_logger(__name__)


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


def fetch_balance(client: BrokerClient) -> AccountBalance:
    """계좌 잔고와 보유 종목을 조회합니다."""
    account = client.account()
    client.throttle()
    balance = account.balance()

    holdings = []
    for stock in balance.stocks:
        holdings.append(
            Holding(
                symbol=stock.symbol,
                market=str(getattr(stock, "market", "")),
                quantity=int(stock.qty),
                orderable_quantity=int(stock.orderable),
                purchase_price=Decimal(str(stock.purchase_price)),
                current_price=Decimal(str(stock.current_price)),
                purchase_amount=Decimal(str(stock.purchase_amount)),
                current_amount=Decimal(str(stock.current_amount)),
                profit=Decimal(str(stock.profit)),
                profit_rate=float(stock.profit_rate),
                exchange_rate=Decimal(str(getattr(stock, "exchange_rate", 0))),
            )
        )

    # USD 캐시 잔고 추출
    cash_usd = None
    if hasattr(balance, "deposits"):
        usd_deposit = balance.deposits.get("USD")
        if usd_deposit is not None:
            cash_usd = Decimal(str(usd_deposit))

    result = AccountBalance(
        total_value_krw=Decimal(str(balance.current_amount)),
        purchase_amount_krw=Decimal(str(balance.purchase_amount)),
        total_profit_krw=Decimal(str(balance.profit)),
        profit_rate=float(balance.profit_rate),
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
