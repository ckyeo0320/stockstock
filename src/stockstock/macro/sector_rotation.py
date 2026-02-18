"""섹터 로테이션 모듈.

섹터 ETF의 모멘텀, 상대강도를 계산하고 상위 섹터를 선정합니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd

from stockstock.logging_config import get_logger
from stockstock.macro.market_data import fetch_etf_ohlcv

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

log = get_logger(__name__)

# 섹터 ETF 매핑
SECTOR_ETFS: dict[str, str] = {
    "기술": "XLK",
    "헬스케어": "XLV",
    "금융": "XLF",
    "에너지": "XLE",
    "필수소비재": "XLP",
    "임의소비재": "XLY",
    "산업재": "XLI",
    "유틸리티": "XLU",
    "반도체": "SOXX",
}

BENCHMARK = "SPY"

# 매크로-섹터 상관관계 가중치 (금리 상승, 유가 상승, 달러 약세 각각에 대한 섹터 민감도)
# 양수 = 유리, 음수 = 불리
MACRO_SECTOR_SENSITIVITY: dict[str, dict[str, float]] = {
    "rate_rising": {  # 금리 상승기
        "XLF": 0.3, "XLE": 0.1, "XLI": 0.0,
        "XLK": -0.2, "XLY": -0.2, "SOXX": -0.2,
        "XLV": 0.0, "XLP": 0.1, "XLU": -0.3,
    },
    "oil_rising": {  # 유가 상승
        "XLE": 0.4, "XLI": 0.1, "XLF": 0.0,
        "XLK": 0.0, "XLY": -0.2, "XLP": -0.1,
        "XLV": 0.0, "SOXX": 0.0, "XLU": -0.1,
    },
    "dollar_weak": {  # 달러 약세
        "XLI": 0.2, "XLK": 0.1, "XLE": 0.1,
        "SOXX": 0.1, "XLF": 0.0, "XLY": 0.0,
        "XLV": 0.0, "XLP": -0.1, "XLU": -0.1,
    },
}


@dataclass
class SectorRank:
    """섹터 순위 결과."""

    sector: str
    etf_ticker: str
    momentum_20d: float
    momentum_60d: float
    relative_strength: float
    macro_sector_score: float
    total_score: float
    rank: int


def _compute_momentum(prices: pd.Series, days: int) -> float:
    """N일 모멘텀(수익률)을 계산합니다."""
    if len(prices) < days + 1:
        return 0.0
    return float((prices.iloc[-1] / prices.iloc[-days - 1]) - 1)


def _compute_relative_strength(etf_prices: pd.Series, benchmark_prices: pd.Series) -> float:
    """벤치마크 대비 상대 강도를 계산합니다."""
    if len(etf_prices) < 21 or len(benchmark_prices) < 21:
        return 1.0
    etf_ret = (etf_prices.iloc[-1] / etf_prices.iloc[-21]) - 1
    bench_ret = (benchmark_prices.iloc[-1] / benchmark_prices.iloc[-21]) - 1
    if bench_ret == 0:
        return 1.0
    return float(1 + (etf_ret - bench_ret))


def compute_sector_rankings(
    macro_signals: dict[str, float] | None = None,
    sector_etfs: dict[str, str] | None = None,
    top_n: int = 3,
) -> list[SectorRank]:
    """섹터 ETF 순위를 계산합니다.

    Args:
        macro_signals: {"rate_rising": -1~1, "oil_rising": -1~1, "dollar_weak": -1~1}
        sector_etfs: 섹터명 → ETF 티커 매핑
        top_n: 상위 N개 반환 (순위는 전체 계산)

    Returns:
        전체 섹터 순위 리스트 (rank 1부터)
    """
    if sector_etfs is None:
        sector_etfs = SECTOR_ETFS
    if macro_signals is None:
        macro_signals = {}

    # 벤치마크 데이터 가져오기
    bench_df = fetch_etf_ohlcv(BENCHMARK, period="6mo")
    bench_prices = bench_df["close"] if not bench_df.empty else pd.Series(dtype=float)

    rankings: list[SectorRank] = []
    for sector, ticker in sector_etfs.items():
        df = fetch_etf_ohlcv(ticker, period="6mo")
        if df.empty or len(df) < 21:
            log.warning("insufficient_etf_data", ticker=ticker, rows=len(df))
            continue

        prices = df["close"]
        mom_20 = _compute_momentum(prices, 20)
        mom_60 = _compute_momentum(prices, 60) if len(prices) > 60 else 0.0
        rs = _compute_relative_strength(prices, bench_prices)

        # 매크로-섹터 상관 점수
        macro_score = 0.0
        for signal_name, signal_value in macro_signals.items():
            sensitivity = MACRO_SECTOR_SENSITIVITY.get(signal_name, {})
            macro_score += signal_value * sensitivity.get(ticker, 0.0)

        # 종합 점수: 모멘텀 50% + 상대강도 30% + 매크로 20%
        total = mom_20 * 0.5 + (rs - 1.0) * 0.3 + macro_score * 0.2

        rankings.append(
            SectorRank(
                sector=sector,
                etf_ticker=ticker,
                momentum_20d=mom_20,
                momentum_60d=mom_60,
                relative_strength=rs,
                macro_sector_score=macro_score,
                total_score=total,
                rank=0,
            )
        )

    # 순위 매기기
    rankings.sort(key=lambda x: x.total_score, reverse=True)
    for i, r in enumerate(rankings):
        r.rank = i + 1

    log.info(
        "sector_rankings_computed",
        top=[f"{r.etf_ticker}({r.total_score:.3f})" for r in rankings[:top_n]],
    )
    return rankings


def save_sector_snapshot(
    session_factory: sessionmaker[Session],
    rankings: list[SectorRank],
    snapshot_date: str,
) -> None:
    """섹터 분석 스냅샷을 DB에 저장합니다."""
    from stockstock.db.models import SectorSnapshot

    with session_factory() as session:
        for r in rankings:
            existing = (
                session.query(SectorSnapshot)
                .filter_by(snapshot_date=snapshot_date, sector=r.sector)
                .first()
            )
            if existing:
                existing.etf_ticker = r.etf_ticker
                existing.momentum_20d = r.momentum_20d
                existing.momentum_60d = r.momentum_60d
                existing.relative_strength = r.relative_strength
                existing.macro_sector_score = r.macro_sector_score
                existing.rank = r.rank
            else:
                session.add(
                    SectorSnapshot(
                        snapshot_date=snapshot_date,
                        sector=r.sector,
                        etf_ticker=r.etf_ticker,
                        momentum_20d=r.momentum_20d,
                        momentum_60d=r.momentum_60d,
                        relative_strength=r.relative_strength,
                        macro_sector_score=r.macro_sector_score,
                        rank=r.rank,
                    )
                )
        session.commit()

    log.info("sector_snapshot_saved", date=snapshot_date, count=len(rankings))
