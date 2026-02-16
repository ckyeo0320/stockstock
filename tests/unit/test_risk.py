"""리스크 관리 테스트."""

from decimal import Decimal

from stockstock.broker.account import AccountBalance, Holding
from stockstock.strategy.risk import check_stop_loss, evaluate_signal
from stockstock.strategy.signals import SignalType, TradingSignal


def _make_balance(cash_usd: float = 10000, holdings: list | None = None) -> AccountBalance:
    return AccountBalance(
        total_value_krw=Decimal("15000000"),
        purchase_amount_krw=Decimal("14000000"),
        total_profit_krw=Decimal("1000000"),
        profit_rate=7.14,
        holdings=holdings or [],
        cash_usd=Decimal(str(cash_usd)),
    )


def _make_signal(symbol: str, signal_type: SignalType, confidence: float = 0.8) -> TradingSignal:
    return TradingSignal(
        symbol=symbol,
        signal=signal_type,
        confidence=confidence,
        prediction="UP" if signal_type == SignalType.BUY else "DOWN",
        reason="test",
    )


def test_buy_approved():
    balance = _make_balance(cash_usd=10000)
    signal = _make_signal("AAPL", SignalType.BUY)
    decision = evaluate_signal(signal, balance, current_price=150.0)
    assert decision.approved
    assert decision.quantity > 0


def test_buy_rejected_no_cash():
    balance = _make_balance(cash_usd=0)
    signal = _make_signal("AAPL", SignalType.BUY)
    decision = evaluate_signal(signal, balance, current_price=150.0)
    assert not decision.approved


def test_sell_approved_with_holding():
    holdings = [
        Holding(
            symbol="AAPL", market="NASDAQ", quantity=10, orderable_quantity=10,
            purchase_price=Decimal("140"), current_price=Decimal("150"),
            purchase_amount=Decimal("1400"), current_amount=Decimal("1500"),
            profit=Decimal("100"), profit_rate=7.14, exchange_rate=Decimal("1300"),
        )
    ]
    balance = _make_balance(holdings=holdings)
    signal = _make_signal("AAPL", SignalType.SELL)
    decision = evaluate_signal(signal, balance, current_price=150.0)
    assert decision.approved
    assert decision.quantity == 10


def test_sell_rejected_no_holding():
    balance = _make_balance()
    signal = _make_signal("AAPL", SignalType.SELL)
    decision = evaluate_signal(signal, balance, current_price=150.0)
    assert not decision.approved


def test_hold_always_approved():
    balance = _make_balance()
    signal = _make_signal("AAPL", SignalType.HOLD)
    decision = evaluate_signal(signal, balance, current_price=150.0)
    assert decision.approved
    assert decision.quantity == 0


def test_daily_loss_limit():
    balance = _make_balance(cash_usd=10000)
    signal = _make_signal("AAPL", SignalType.BUY)
    decision = evaluate_signal(
        signal, balance, current_price=150.0,
        max_daily_loss_usd=500.0, daily_loss_usd=600.0,
    )
    assert not decision.approved
    assert "일일 손실 한도" in decision.reason


def test_trading_halted():
    balance = _make_balance(cash_usd=10000)
    signal = _make_signal("AAPL", SignalType.BUY)
    decision = evaluate_signal(
        signal, balance, current_price=150.0, trading_halted=True,
    )
    assert not decision.approved


def test_stop_loss_triggered():
    assert check_stop_loss("AAPL", current_price=95.0, purchase_price=100.0, stop_loss_pct=0.05)


def test_stop_loss_not_triggered():
    assert not check_stop_loss("AAPL", current_price=98.0, purchase_price=100.0, stop_loss_pct=0.05)
