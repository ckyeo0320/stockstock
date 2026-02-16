"""시장 데이터 조회 모듈.

현재 시세, 과거 OHLCV 데이터를 조회합니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd

from stockstock.broker.client import BrokerClient
from stockstock.logging_config import get_logger

log = get_logger(__name__)


@dataclass
class Quote:
    """현재 시세 정보."""

    symbol: str
    price: Decimal
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    change: Decimal
    change_rate: float
    prev_close: Decimal
    is_halted: bool


def fetch_quote(client: BrokerClient, symbol: str) -> Quote:
    """종목의 현재 시세를 조회합니다."""
    stock = client.stock(symbol)
    client.throttle()
    q = stock.quote()

    result = Quote(
        symbol=symbol,
        price=Decimal(str(q.price)),
        open=Decimal(str(q.open)),
        high=Decimal(str(q.high)),
        low=Decimal(str(q.low)),
        close=Decimal(str(q.close)),
        volume=int(q.volume),
        change=Decimal(str(q.change)),
        change_rate=float(q.rate),
        prev_close=Decimal(str(q.prev_price)),
        is_halted=bool(q.halt),
    )

    log.info(
        "quote_fetched", symbol=symbol, price=str(result.price), change=result.change_rate
    )
    return result


def fetch_daily_ohlcv(
    client: BrokerClient,
    symbol: str,
    days: int = 252,
    end_date: date | None = None,
) -> pd.DataFrame:
    """일봉 OHLCV 데이터를 DataFrame으로 반환합니다.

    Returns:
        DataFrame with columns: date, open, high, low, close, volume
    """
    stock = client.stock(symbol)
    client.throttle()

    chart = stock.daily_chart(start=timedelta(days=days), period="day")
    df = chart.df()

    if df.empty:
        log.warning("empty_chart_data", symbol=symbol, days=days)
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

    df = df.reset_index()
    if "time" in df.columns:
        df = df.rename(columns={"time": "date"})

    # 필요한 컬럼만 유지
    expected_cols = ["date", "open", "high", "low", "close", "volume"]
    available_cols = [c for c in expected_cols if c in df.columns]
    df = df[available_cols]

    # float 변환
    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            df[col] = df[col].astype(float)

    if "volume" in df.columns:
        df["volume"] = df["volume"].astype(int)

    df = df.sort_values("date").reset_index(drop=True)

    log.info("daily_ohlcv_fetched", symbol=symbol, rows=len(df))
    return df
