"""매크로 피처 통합 테스트."""

from stockstock.macro.macro_score import MacroReport
from stockstock.macro.sector_rotation import SectorRank
from stockstock.strategy.features import (
    compute_features,
    get_feature_columns,
    get_macro_feature_columns,
)


def test_get_macro_feature_columns():
    cols = get_macro_feature_columns()
    assert len(cols) == 10
    assert "macro_score" in cols
    assert "vix" in cols
    assert "sector_momentum_20d" in cols


def test_get_feature_columns_with_macro():
    basic = get_feature_columns(include_macro=False)
    full = get_feature_columns(include_macro=True)
    assert len(full) == len(basic) + 10


def test_compute_features_with_macro_report(sample_ohlcv_df):
    report = MacroReport(
        score=0.3, label="약한 강세", equity_pct=70,
        yield_spread=0.5, yield_spread_change=0.02,
        high_yield_spread=4.2, vix=18.0, vix_percentile=40.0,
        copper_gold_ratio_change=0.01, dxy_change=-0.015,
    )
    result = compute_features(sample_ohlcv_df, macro_report=report)

    # 매크로 피처가 추가되었는지 확인
    assert "macro_score" in result.columns
    assert "vix" in result.columns
    assert "yield_spread_2_10" in result.columns
    assert "sector_momentum_20d" in result.columns

    # 값 확인
    assert (result["macro_score"] == 0.3).all()
    assert (result["vix"] == 18.0).all()
    # macro_report만 있고 sector_rank 없으면 기본값
    assert (result["sector_momentum_20d"] == 0.0).all()
    assert (result["sector_relative_strength"] == 1.0).all()


def test_compute_features_with_sector_rank(sample_ohlcv_df):
    report = MacroReport(score=0.1, label="약한 강세", equity_pct=70)
    rank = SectorRank(
        sector="기술", etf_ticker="XLK",
        momentum_20d=0.05, momentum_60d=0.12,
        relative_strength=1.03, macro_sector_score=0.1,
        total_score=0.08, rank=1,
    )
    result = compute_features(sample_ohlcv_df, macro_report=report, sector_rank=rank)

    assert (result["sector_momentum_20d"] == 0.05).all()
    assert (result["sector_relative_strength"] == 1.03).all()


def test_compute_features_without_macro(sample_ohlcv_df):
    """매크로 없이 기존 동작 유지."""
    result = compute_features(sample_ohlcv_df)
    assert "macro_score" not in result.columns
    assert "vix" not in result.columns
