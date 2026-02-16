"""시그널 생성 테스트."""

from stockstock.strategy.signals import SignalType, generate_signal


def test_buy_signal_high_confidence():
    signal = generate_signal("AAPL", "UP", 0.8, confidence_threshold=0.6)
    assert signal.signal == SignalType.BUY
    assert signal.confidence == 0.8


def test_sell_signal_high_confidence():
    signal = generate_signal("AAPL", "DOWN", 0.75, confidence_threshold=0.6)
    assert signal.signal == SignalType.SELL


def test_hold_on_low_confidence():
    signal = generate_signal("AAPL", "UP", 0.4, confidence_threshold=0.6)
    assert signal.signal == SignalType.HOLD
    assert "확신도 부족" in signal.reason


def test_hold_signal():
    signal = generate_signal("AAPL", "HOLD", 0.9, confidence_threshold=0.6)
    assert signal.signal == SignalType.HOLD


def test_signal_symbol():
    signal = generate_signal("NVDA", "UP", 0.8, confidence_threshold=0.6)
    assert signal.symbol == "NVDA"
