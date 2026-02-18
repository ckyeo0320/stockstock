"""FRED API 클라이언트.

연방준비제도 경제 데이터(금리, 인플레이션, 고용)를 수집합니다.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import pandas as pd
from fredapi import Fred

from stockstock.logging_config import get_logger

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

log = get_logger(__name__)

# 기본 수집 대상 FRED 시리즈
DEFAULT_SERIES = [
    "T10Y2Y",        # 2-10년 국채 스프레드
    "BAMLH0A0HYM2",  # 하이일드 스프레드
    "FEDFUNDS",       # 연방기금금리
    "CPIAUCSL",       # CPI
    "UNRATE",         # 실업률
]


class FredClient:
    """FRED API 클라이언트."""

    def __init__(self, api_key: str, session_factory: sessionmaker[Session]) -> None:
        self._fred = Fred(api_key=api_key)
        self._session_factory = session_factory

    def fetch_series(
        self, series_id: str, lookback_days: int = 365
    ) -> pd.DataFrame:
        """FRED 시리즈 데이터를 가져옵니다.

        Returns:
            date, value 컬럼을 가진 DataFrame
        """
        start = datetime.now() - timedelta(days=lookback_days)
        try:
            data = self._fred.get_series(series_id, observation_start=start)
            if data is None or data.empty:
                log.warning("fred_empty_response", series_id=series_id)
                return pd.DataFrame(columns=["date", "value"])

            df = data.reset_index()
            df.columns = ["date", "value"]
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            df = df.dropna(subset=["value"])
            log.info("fred_fetched", series_id=series_id, rows=len(df))
            return df

        except Exception:
            log.error("fred_fetch_error", series_id=series_id, exc_info=True)
            return pd.DataFrame(columns=["date", "value"])

    def fetch_and_cache(
        self, series_ids: list[str] | None = None, lookback_days: int = 365
    ) -> dict[str, pd.DataFrame]:
        """여러 시리즈를 가져와 DB에 캐싱합니다.

        Returns:
            시리즈 ID → DataFrame 매핑
        """
        from stockstock.db.models import MacroData

        if series_ids is None:
            series_ids = DEFAULT_SERIES

        results: dict[str, pd.DataFrame] = {}
        for sid in series_ids:
            df = self.fetch_series(sid, lookback_days)
            if df.empty:
                results[sid] = df
                continue

            # DB에 캐싱
            with self._session_factory() as session:
                for _, row in df.iterrows():
                    existing = (
                        session.query(MacroData)
                        .filter_by(series_id=sid, dt=row["date"])
                        .first()
                    )
                    if existing:
                        existing.value = float(row["value"])
                    else:
                        session.add(
                            MacroData(
                                series_id=sid,
                                dt=row["date"],
                                value=float(row["value"]),
                                source="fred",
                            )
                        )
                session.commit()

            results[sid] = df
            log.info("fred_cached", series_id=sid, rows=len(df))

        return results

    def get_latest_value(self, series_id: str) -> float | None:
        """DB에서 가장 최근 값을 조회합니다."""
        from stockstock.db.models import MacroData

        with self._session_factory() as session:
            row = (
                session.query(MacroData)
                .filter_by(series_id=series_id)
                .order_by(MacroData.dt.desc())
                .first()
            )
            return row.value if row else None

    def get_series_df(self, series_id: str, limit: int = 252) -> pd.DataFrame:
        """DB에서 시리즈 데이터를 DataFrame으로 반환합니다."""
        from stockstock.db.models import MacroData

        with self._session_factory() as session:
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
