"""주문 실행 모듈.

미국주식 매수/매도 주문을 처리합니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from stockstock.broker.client import BrokerClient
from stockstock.logging_config import get_logger

log = get_logger(__name__)


@dataclass
class OrderResult:
    """주문 실행 결과."""

    symbol: str
    side: str  # BUY or SELL
    order_type: str  # MARKET or LIMIT
    quantity: int
    price: Decimal | None  # None for market orders
    pending: bool
    order_ref: object  # KisOrder 원본 객체


def place_buy_order(
    client: BrokerClient,
    symbol: str,
    quantity: int,
    price: float | None = None,
) -> OrderResult:
    """매수 주문을 실행합니다.

    Args:
        symbol: 종목 심볼 (예: "AAPL")
        quantity: 매수 수량
        price: 지정가 (None이면 시장가)
    """
    if quantity <= 0:
        raise ValueError(f"매수 수량은 양수여야 합니다: {quantity}")

    stock = client.stock(symbol)
    client.throttle()

    order_type = "LIMIT" if price is not None else "MARKET"

    log.info(
        "placing_buy_order",
        symbol=symbol,
        quantity=quantity,
        price=price,
        order_type=order_type,
        virtual=client.is_virtual,
    )

    if price is not None:
        order = stock.buy(price=price, qty=quantity)
    else:
        order = stock.buy(qty=quantity)

    result = OrderResult(
        symbol=symbol,
        side="BUY",
        order_type=order_type,
        quantity=quantity,
        price=Decimal(str(price)) if price else None,
        pending=bool(order.pending),
        order_ref=order,
    )

    log.info(
        "buy_order_placed",
        symbol=symbol,
        quantity=quantity,
        order_type=order_type,
        pending=result.pending,
    )

    return result


def place_sell_order(
    client: BrokerClient,
    symbol: str,
    quantity: int,
    price: float | None = None,
) -> OrderResult:
    """매도 주문을 실행합니다.

    Args:
        symbol: 종목 심볼 (예: "AAPL")
        quantity: 매도 수량
        price: 지정가 (None이면 시장가)
    """
    if quantity <= 0:
        raise ValueError(f"매도 수량은 양수여야 합니다: {quantity}")

    stock = client.stock(symbol)
    client.throttle()

    order_type = "LIMIT" if price is not None else "MARKET"

    log.info(
        "placing_sell_order",
        symbol=symbol,
        quantity=quantity,
        price=price,
        order_type=order_type,
        virtual=client.is_virtual,
    )

    if price is not None:
        order = stock.sell(price=price, qty=quantity)
    else:
        order = stock.sell(qty=quantity)

    result = OrderResult(
        symbol=symbol,
        side="SELL",
        order_type=order_type,
        quantity=quantity,
        price=Decimal(str(price)) if price else None,
        pending=bool(order.pending),
        order_ref=order,
    )

    log.info(
        "sell_order_placed",
        symbol=symbol,
        quantity=quantity,
        order_type=order_type,
        pending=result.pending,
    )

    return result


def cancel_order(order_result: OrderResult) -> bool:
    """주문을 취소합니다."""
    try:
        order_result.order_ref.cancel()
        log.info("order_cancelled", symbol=order_result.symbol, side=order_result.side)
        return True
    except Exception as e:
        log.error("order_cancel_failed", symbol=order_result.symbol, error=str(e))
        return False
