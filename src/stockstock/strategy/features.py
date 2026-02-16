"""기술적 지표 계산 모듈.

ta 라이브러리를 사용하여 RSI, MACD, 볼린저밴드 등을 계산합니다.
"""

from __future__ import annotations

import pandas as pd
import ta


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """OHLCV DataFrame에 기술적 지표를 추가합니다.

    Args:
        df: date, open, high, low, close, volume 컬럼을 가진 DataFrame

    Returns:
        기술적 지표가 추가된 DataFrame (NaN 행 제거됨)
    """
    if len(df) < 50:
        raise ValueError(f"최소 50개 이상의 데이터가 필요합니다 (현재: {len(df)})")

    result = df.copy()

    # --- Trend Indicators ---
    # SMA (Simple Moving Average)
    result["sma_5"] = ta.trend.sma_indicator(result["close"], window=5)
    result["sma_20"] = ta.trend.sma_indicator(result["close"], window=20)
    result["sma_60"] = ta.trend.sma_indicator(result["close"], window=60)

    # EMA (Exponential Moving Average)
    result["ema_12"] = ta.trend.ema_indicator(result["close"], window=12)
    result["ema_26"] = ta.trend.ema_indicator(result["close"], window=26)

    # MACD
    macd = ta.trend.MACD(result["close"])
    result["macd"] = macd.macd()
    result["macd_signal"] = macd.macd_signal()
    result["macd_diff"] = macd.macd_diff()

    # --- Momentum Indicators ---
    # RSI
    result["rsi_14"] = ta.momentum.rsi(result["close"], window=14)

    # Stochastic Oscillator
    stoch = ta.momentum.StochasticOscillator(result["high"], result["low"], result["close"])
    result["stoch_k"] = stoch.stoch()
    result["stoch_d"] = stoch.stoch_signal()

    # --- Volatility Indicators ---
    # Bollinger Bands
    bb = ta.volatility.BollingerBands(result["close"], window=20, window_dev=2)
    result["bb_upper"] = bb.bollinger_hband()
    result["bb_middle"] = bb.bollinger_mavg()
    result["bb_lower"] = bb.bollinger_lband()
    result["bb_width"] = bb.bollinger_wband()
    result["bb_pband"] = bb.bollinger_pband()

    # ATR (Average True Range)
    result["atr_14"] = ta.volatility.average_true_range(
        result["high"], result["low"], result["close"], window=14
    )

    # --- Volume Indicators ---
    # Volume ratio (current / 20-day average)
    result["volume_sma_20"] = result["volume"].rolling(window=20).mean()
    result["volume_ratio"] = result["volume"] / result["volume_sma_20"]

    # --- Derived Features ---
    # 가격 변화율
    result["return_1d"] = result["close"].pct_change(1)
    result["return_5d"] = result["close"].pct_change(5)
    result["return_20d"] = result["close"].pct_change(20)

    # SMA 크로스오버 시그널
    result["sma_cross_5_20"] = (result["sma_5"] > result["sma_20"]).astype(int)
    result["ema_cross_12_26"] = (result["ema_12"] > result["ema_26"]).astype(int)

    # 가격 대비 볼린저밴드 위치
    result["price_vs_bb_upper"] = (result["close"] - result["bb_upper"]) / result["bb_upper"]
    result["price_vs_bb_lower"] = (result["close"] - result["bb_lower"]) / result["bb_lower"]

    # NaN 행 제거 (지표 계산에 필요한 초기 구간)
    result = result.dropna().reset_index(drop=True)

    return result


def get_feature_columns() -> list[str]:
    """ML 모델에 입력될 피처 컬럼 목록을 반환합니다."""
    return [
        "sma_5", "sma_20", "sma_60",
        "ema_12", "ema_26",
        "macd", "macd_signal", "macd_diff",
        "rsi_14",
        "stoch_k", "stoch_d",
        "bb_upper", "bb_middle", "bb_lower", "bb_width", "bb_pband",
        "atr_14",
        "volume_ratio",
        "return_1d", "return_5d", "return_20d",
        "sma_cross_5_20", "ema_cross_12_26",
        "price_vs_bb_upper", "price_vs_bb_lower",
    ]
