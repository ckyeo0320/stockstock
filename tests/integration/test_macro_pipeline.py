"""매크로 파이프라인 통합 테스트.

FRED 캐시 → 매크로 점수 → 섹터 순위 → DB 스냅샷 저장까지 흐름을 검증합니다.
"""

from unittest.mock import patch

import numpy as np
import pandas as pd

from stockstock.db.models import MacroData, SectorSnapshot
from stockstock.macro.macro_score import MacroReport, compute_macro_score
from stockstock.macro.sector_rotation import (
    compute_sector_rankings,
    save_sector_snapshot,
)


def _seed_macro_data(session_factory, series_id, n=60, base=1.0, drift=0.01):
    """DB에 매크로 시계열 데이터를 시딩합니다."""
    np.random.seed(hash(series_id) % 2**31)
    dates = pd.bdate_range(end="2025-12-31", periods=n)
    values = base + np.cumsum(np.random.randn(n) * 0.1 + drift)

    with session_factory() as session:
        for dt, val in zip(dates, values):
            session.add(MacroData(
                series_id=series_id,
                dt=dt.strftime("%Y-%m-%d"),
                value=float(val),
                source="test",
            ))
        session.commit()


def _mock_fetch_etf(ticker, period="6mo"):
    """fetch_etf_ohlcv 모킹."""
    np.random.seed(hash(ticker) % 2**31)
    n = 130
    dates = pd.bdate_range(end="2025-12-31", periods=n)
    close = 100 + np.cumsum(np.random.randn(n) * 1.0)
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": close + np.random.randn(n) * 0.5,
        "high": close + abs(np.random.randn(n)),
        "low": close - abs(np.random.randn(n)),
        "close": close,
        "volume": np.random.randint(100_000, 1_000_000, n),
    })


class TestMacroScorePipeline:
    """DB 시딩 → compute_macro_score 전체 흐름."""

    def test_macro_score_with_seeded_data(self, tmp_db):
        # 모든 필요한 시리즈 시딩
        _seed_macro_data(tmp_db, "T10Y2Y", base=0.5)
        _seed_macro_data(tmp_db, "BAMLH0A0HYM2", base=3.0)
        _seed_macro_data(tmp_db, "FEDFUNDS", base=4.5)
        _seed_macro_data(tmp_db, "^VIX", base=18.0, drift=-0.01)
        _seed_macro_data(tmp_db, "HG=F", base=4.0)
        _seed_macro_data(tmp_db, "GC=F", base=2000.0)
        _seed_macro_data(tmp_db, "DX-Y.NYB", base=104.0)
        _seed_macro_data(tmp_db, "CL=F", base=70.0)

        report = compute_macro_score(tmp_db)

        assert isinstance(report, MacroReport)
        assert -1.0 <= report.score <= 1.0
        assert report.label in ("강세", "약한 강세", "약한 약세", "약세")
        assert report.equity_pct in (20, 40, 70, 90)
        assert isinstance(report.macro_signals, dict)

    def test_macro_score_empty_db(self, tmp_db):
        """데이터 없이도 기본값으로 동작."""
        report = compute_macro_score(tmp_db)
        assert report.score == 0.0
        assert report.equity_pct == 70


class TestSectorRankingPipeline:
    """매크로 점수 → 섹터 순위 → DB 저장."""

    @patch(
        "stockstock.macro.sector_rotation.fetch_etf_ohlcv",
        side_effect=_mock_fetch_etf,
    )
    def test_full_sector_pipeline(self, mock_fetch, tmp_db):
        # 1. 매크로 점수 (기본값)
        report = MacroReport(score=0.3, label="약한 강세", equity_pct=70)

        # 2. 섹터 순위 계산
        rankings = compute_sector_rankings(
            macro_signals=report.macro_signals,
            sector_etfs={"기술": "XLK", "금융": "XLF", "에너지": "XLE"},
        )

        assert len(rankings) == 3
        assert rankings[0].rank == 1
        assert rankings[-1].rank == 3

        # 3. DB 저장
        save_sector_snapshot(tmp_db, rankings, "2025-12-01")

        with tmp_db() as session:
            rows = session.query(SectorSnapshot).all()
            assert len(rows) == 3

    @patch(
        "stockstock.macro.sector_rotation.fetch_etf_ohlcv",
        side_effect=_mock_fetch_etf,
    )
    def test_sector_rankings_with_macro_signals(self, mock_fetch, tmp_db):
        """매크로 시그널이 섹터 점수에 영향을 준다."""
        # 시그널 없이
        rankings_no_macro = compute_sector_rankings(macro_signals=None)
        # 시그널 있이
        rankings_with_macro = compute_sector_rankings(
            macro_signals={"rate_rising": 0.8, "oil_rising": 0.5, "dollar_weak": -0.3},
        )

        # 매크로 시그널이 있으면 macro_sector_score가 0이 아닌 값
        has_nonzero = any(r.macro_sector_score != 0.0 for r in rankings_with_macro)
        assert has_nonzero
        # 매크로 시그널 없으면 모두 0
        assert all(r.macro_sector_score == 0.0 for r in rankings_no_macro)


class TestMacroToFeatures:
    """매크로 리포트 → 피처 계산 통합."""

    def test_features_with_macro_and_sector(self):
        from stockstock.macro.sector_rotation import SectorRank
        from stockstock.strategy.features import compute_features

        np.random.seed(42)
        n = 100
        dates = pd.bdate_range(end="2025-12-31", periods=n)
        prices = 150.0 + np.cumsum(np.random.randn(n) * 2)
        df = pd.DataFrame({
            "date": dates.strftime("%Y-%m-%d"),
            "open": prices,
            "high": prices + 1,
            "low": prices - 1,
            "close": prices,
            "volume": np.random.randint(1_000_000, 5_000_000, n),
        })

        report = MacroReport(
            score=0.4, label="약한 강세", equity_pct=70,
            yield_spread=0.5, yield_spread_change=0.02,
            high_yield_spread=3.2, vix=18.0, vix_percentile=35.0,
            copper_gold_ratio_change=0.01, dxy_change=-0.015,
        )
        sector = SectorRank("기술", "XLK", 0.05, 0.12, 1.03, 0.1, 0.08, 1)

        featured = compute_features(df, macro_report=report, sector_rank=sector)

        assert "macro_score" in featured.columns
        assert "vix" in featured.columns
        assert "sector_momentum_20d" in featured.columns
        assert "sector_relative_strength" in featured.columns
        assert len(featured) > 30  # 지표 워밍업으로 앞쪽 행 제거됨
