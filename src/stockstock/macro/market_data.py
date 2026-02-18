"""시장 데이터 수집 모듈.

Yahoo Finance를 통해 VIX, 원자재, 환율 데이터를 수집합니다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import yfinance as yf

from stockstock.logging_config import get_logger

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

log = get_logger(__name__)

# 기본 수집 대상 티커
DEFAULT_TICKERS = {
    "vix": "^VIX",
    "gold": "GC=F",
    "oil": "CL=F",
    "dollar": "DX-Y.NYB",
    "copper": "HG=F",
}


def fetch_ticker_history(
    ticker: str, period: str = "6mo", interval: str = "1d"
) -> pd.DataFrame:
    """Yahoo Finance에서 티커 히스토리를 가져옵니다.

    Returns:
        date, close 컬럼을 가진 DataFrame
    """
    try:
        data = yf.download(ticker, period=period, interval=interval, progress=False)
        if data is None or data.empty:
            log.warning("yfinance_empty", ticker=ticker)
            return pd.DataFrame(columns=["date", "close"])

        df = data[["Close"]].reset_index()
        df.columns = ["date", "close"]
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df = df.dropna()
        log.info("yfinance_fetched", ticker=ticker, rows=len(df))
        return df

    except Exception:
        log.error("yfinance_fetch_error", ticker=ticker, exc_info=True)
        return pd.DataFrame(columns=["date", "close"])


def fetch_etf_ohlcv(
    ticker: str, period: str = "6mo", interval: str = "1d"
) -> pd.DataFrame:
    """Yahoo Finance에서 ETF OHLCV 데이터를 가져옵니다.

    Returns:
        date, open, high, low, close, volume 컬럼을 가진 DataFrame
    """
    try:
        data = yf.download(ticker, period=period, interval=interval, progress=False)
        if data is None or data.empty:
            log.warning("yfinance_empty", ticker=ticker)
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

        df = data[["Open", "High", "Low", "Close", "Volume"]].reset_index()
        df.columns = ["date", "open", "high", "low", "close", "volume"]
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df = df.dropna()
        log.info("yfinance_ohlcv_fetched", ticker=ticker, rows=len(df))
        return df

    except Exception:
        log.error("yfinance_ohlcv_error", ticker=ticker, exc_info=True)
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])


def fetch_and_cache_market_data(
    session_factory: sessionmaker[Session],
    tickers: dict[str, str] | None = None,
) -> dict[str, pd.DataFrame]:
    """시장 데이터를 가져와 DB에 캐싱합니다.

    Returns:
        이름 → DataFrame 매핑
    """
    from stockstock.db.models import MacroData

    if tickers is None:
        tickers = DEFAULT_TICKERS

    results: dict[str, pd.DataFrame] = {}
    for name, ticker in tickers.items():
        df = fetch_ticker_history(ticker)
        if df.empty:
            results[name] = df
            continue

        with session_factory() as session:
            for _, row in df.iterrows():
                existing = (
                    session.query(MacroData)
                    .filter_by(series_id=ticker, dt=row["date"])
                    .first()
                )
                if existing:
                    existing.value = float(row["close"])
                else:
                    session.add(
                        MacroData(
                            series_id=ticker,
                            dt=row["date"],
                            value=float(row["close"]),
                            source="yahoo",
                        )
                    )
            session.commit()

        results[name] = df
        log.info("market_data_cached", name=name, ticker=ticker, rows=len(df))

    return results


def get_cached_value(
    session_factory: sessionmaker[Session], series_id: str
) -> float | None:
    """DB에서 가장 최근 값을 조회합니다."""
    from stockstock.db.models import MacroData

    with session_factory() as session:
        row = (
            session.query(MacroData)
            .filter_by(series_id=series_id)
            .order_by(MacroData.dt.desc())
            .first()
        )
        return row.value if row else None


def get_cached_series(
    session_factory: sessionmaker[Session], series_id: str, limit: int = 252
) -> pd.DataFrame:
    """DB에서 시리즈 데이터를 DataFrame으로 반환합니다."""
    from stockstock.db.models import MacroData

    with session_factory() as session:
        rows = (
            session.query(MacroData)
            .filter_by(series_id=series_id)
            .order_by(MacroData.dt.desc())
            .limit(limit)
            .all()
        )

    if not rows:
        return pd.DataFrame(columns=["date", "value"])

    data = [{"date": r.dt, "value": r.value} for r in reversed(rows)]
    return pd.DataFrame(data)
