"""리스크 관리 모듈.

포지션 사이징, 손절, 일일 손실 한도를 관리합니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from stockstock.broker.account import AccountBalance
from stockstock.logging_config import get_logger
from stockstock.strategy.signals import SignalType, TradingSignal

log = get_logger(__name__)


@dataclass
class RiskDecision:
    """리스크 평가 결과."""

    approved: bool
    signal: TradingSignal
    quantity: int
    reason: str


def evaluate_signal(
    signal: TradingSignal,
    balance: AccountBalance,
    current_price: float,
    max_position_pct: float = 0.10,
    stop_loss_pct: float = 0.05,
    max_daily_loss_usd: float = 500.0,
    daily_loss_usd: float = 0.0,
    trading_halted: bool = False,
) -> RiskDecision:
    """매매 시그널에 대한 리스크 평가를 수행합니다.

    Args:
        signal: 매매 시그널
        balance: 현재 계좌 잔고
        current_price: 현재 주가 (USD)
        max_position_pct: 단일 종목 최대 포지션 비율
        stop_loss_pct: 손절 기준 비율
        max_daily_loss_usd: 일일 최대 손실 한도 (USD)
        daily_loss_usd: 금일 누적 손실 (USD)
        trading_halted: 매매 중단 상태
    """
    # HOLD 시그널은 무조건 승인 (아무것도 안 함)
    if signal.signal == SignalType.HOLD:
        return RiskDecision(approved=True, signal=signal, quantity=0, reason="HOLD 시그널")

    # 매매 중단 상태 체크
    if trading_halted:
        return RiskDecision(
            approved=False, signal=signal, quantity=0,
            reason="매매가 중단된 상태입니다",
        )

    # 일일 손실 한도 체크
    if daily_loss_usd >= max_daily_loss_usd:
        return RiskDecision(
            approved=False, signal=signal, quantity=0,
            reason=f"일일 손실 한도 초과: ${daily_loss_usd:.2f} >= ${max_daily_loss_usd:.2f}",
        )

    # 매수 시그널 평가
    if signal.signal == SignalType.BUY:
        return _evaluate_buy(
            signal, balance, current_price, max_position_pct
        )

    # 매도 시그널 평가
    if signal.signal == SignalType.SELL:
        return _evaluate_sell(signal, balance)

    return RiskDecision(approved=False, signal=signal, quantity=0, reason="알 수 없는 시그널")


def _evaluate_buy(
    signal: TradingSignal,
    balance: AccountBalance,
    current_price: float,
    max_position_pct: float,
) -> RiskDecision:
    """매수 리스크 평가."""
    # 매수 가능 금액 (USD) 확인
    available_cash = float(balance.cash_usd or 0)
    if available_cash <= 0:
        return RiskDecision(
            approved=False, signal=signal, quantity=0,
            reason="매수 가능한 USD 현금이 없습니다",
        )

    # 총 포트폴리오 가치 산출 (USD 기준 근사치)
    total_portfolio_usd = available_cash
    current_position_value = Decimal(0)

    for h in balance.holdings:
        holding_usd = float(h.current_amount)
        total_portfolio_usd += holding_usd
        if h.symbol == signal.symbol:
            current_position_value = h.current_amount

    # 최대 포지션 비율 체크
    max_position_usd = total_portfolio_usd * max_position_pct
    remaining_position = max_position_usd - float(current_position_value)

    if remaining_position <= 0:
        return RiskDecision(
            approved=False, signal=signal, quantity=0,
            reason=f"{signal.symbol} 최대 포지션 한도 도달 ({max_position_pct*100:.0f}%)",
        )

    # 매수 가능 수량 계산
    max_buy_usd = min(available_cash, remaining_position)
    quantity = int(max_buy_usd / current_price)

    if quantity <= 0:
        return RiskDecision(
            approved=False, signal=signal, quantity=0,
            reason=f"매수 가능 수량이 0입니다 (가격: ${current_price:.2f})",
        )

    log.info(
        "buy_risk_approved",
        symbol=signal.symbol,
        quantity=quantity,
        current_price=current_price,
        max_buy_usd=max_buy_usd,
    )

    return RiskDecision(
        approved=True, signal=signal, quantity=quantity,
        reason=f"매수 승인: {quantity}주 @ ${current_price:.2f}",
    )


def _evaluate_sell(signal: TradingSignal, balance: AccountBalance) -> RiskDecision:
    """매도 리스크 평가."""
    # 보유 중인 종목 찾기
    holding = None
    for h in balance.holdings:
        if h.symbol == signal.symbol:
            holding = h
            break

    if holding is None or holding.orderable_quantity <= 0:
        return RiskDecision(
            approved=False, signal=signal, quantity=0,
            reason=f"{signal.symbol}을(를) 보유하고 있지 않습니다",
        )

    quantity = holding.orderable_quantity

    log.info(
        "sell_risk_approved",
        symbol=signal.symbol,
        quantity=quantity,
    )

    return RiskDecision(
        approved=True, signal=signal, quantity=quantity,
        reason=f"매도 승인: {quantity}주 전량 매도",
    )


def check_stop_loss(
    symbol: str,
    current_price: float,
    purchase_price: float,
    stop_loss_pct: float = 0.05,
) -> bool:
    """손절 조건을 확인합니다. True면 손절 필요."""
    if purchase_price <= 0:
        return False
    loss_pct = (purchase_price - current_price) / purchase_price
    if loss_pct >= stop_loss_pct:
        log.warning(
            "stop_loss_triggered",
            symbol=symbol,
            current_price=current_price,
            purchase_price=purchase_price,
            loss_pct=f"{loss_pct:.2%}",
        )
        return True
    return False
