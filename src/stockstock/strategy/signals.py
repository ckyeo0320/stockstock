"""매매 시그널 생성 모듈.

ML 모델의 예측 결과를 BUY/SELL/HOLD 시그널로 변환합니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from stockstock.logging_config import get_logger

log = get_logger(__name__)


class SignalType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class TradingSignal:
    """매매 시그널."""

    symbol: str
    signal: SignalType
    confidence: float
    prediction: str  # 모델 원본 예측 (UP/DOWN/HOLD)
    reason: str


def generate_signal(
    symbol: str,
    prediction: str,
    confidence: float,
    confidence_threshold: float = 0.6,
) -> TradingSignal:
    """모델 예측을 매매 시그널로 변환합니다.

    Args:
        symbol: 종목 심볼
        prediction: 모델 예측 ("UP", "DOWN", "HOLD")
        confidence: 모델 확신도 (0.0~1.0)
        confidence_threshold: 시그널 생성을 위한 최소 확신도
    """
    # 확신도가 임계값 미만이면 HOLD
    if confidence < confidence_threshold:
        signal = TradingSignal(
            symbol=symbol,
            signal=SignalType.HOLD,
            confidence=confidence,
            prediction=prediction,
            reason=f"확신도 부족: {confidence:.2f} < {confidence_threshold:.2f}",
        )
        log.info("signal_generated", symbol=symbol, signal="HOLD", reason=signal.reason)
        return signal

    if prediction == "UP":
        signal_type = SignalType.BUY
        reason = f"상승 예측 (확신도: {confidence:.2f})"
    elif prediction == "DOWN":
        signal_type = SignalType.SELL
        reason = f"하락 예측 (확신도: {confidence:.2f})"
    else:
        signal_type = SignalType.HOLD
        reason = f"횡보 예측 (확신도: {confidence:.2f})"

    signal = TradingSignal(
        symbol=symbol,
        signal=signal_type,
        confidence=confidence,
        prediction=prediction,
        reason=reason,
    )

    log.info(
        "signal_generated",
        symbol=symbol,
        signal=signal_type.value,
        confidence=confidence,
        reason=reason,
    )

    return signal
