"""메시지 포맷팅 테스트."""

from stockstock.notifications.messages import (
    format_error_alert,
    format_portfolio_summary,
    format_status,
    format_trade_alert,
)
from stockstock.strategy.signals import SignalType, TradingSignal


def test_format_trade_alert():
    signal = TradingSignal(
        symbol="AAPL", signal=SignalType.BUY, confidence=0.85,
        prediction="UP", reason="상승 예측",
    )
    msg = format_trade_alert(signal, quantity=5, price=150.0, order_type="MARKET", is_paper=True)
    assert "AAPL" in msg
    assert "BUY" in msg
    assert "모의투자" in msg
    assert "5주" in msg
    assert "$150.00" in msg


def test_format_portfolio_summary():
    holdings = [
        {"symbol": "AAPL", "quantity": 10, "current_price": 150.0, "profit_rate": 5.0},
    ]
    msg = format_portfolio_summary(holdings, total_value=11500.0, cash=500.0, daily_pnl=200.0)
    assert "AAPL" in msg
    assert "포트폴리오" in msg


def test_format_error_alert():
    msg = format_error_alert("API 오류", "연결 실패")
    assert "오류" in msg
    assert "API 오류" in msg


def test_format_status():
    msg = format_status(
        mode="paper", is_active=True, last_run="2025-01-01",
        next_run="2025-01-01 10:00", symbols=["AAPL", "MSFT"],
    )
    assert "모의투자" in msg
    assert "활성" in msg
    assert "AAPL" in msg
