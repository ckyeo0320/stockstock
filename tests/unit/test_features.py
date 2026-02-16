"""기술적 지표 계산 테스트."""

import pytest

from stockstock.strategy.features import compute_features, get_feature_columns


def test_compute_features_returns_expected_columns(sample_ohlcv_df):
    result = compute_features(sample_ohlcv_df)
    expected_cols = get_feature_columns()

    for col in expected_cols:
        assert col in result.columns, f"Missing column: {col}"


def test_compute_features_no_nan(sample_ohlcv_df):
    result = compute_features(sample_ohlcv_df)
    feature_cols = get_feature_columns()
    for col in feature_cols:
        assert result[col].isna().sum() == 0, f"Column {col} has NaN values"


def test_compute_features_insufficient_data():
    import pandas as pd

    small_df = pd.DataFrame({
        "date": ["2025-01-01"] * 10,
        "open": [100.0] * 10,
        "high": [101.0] * 10,
        "low": [99.0] * 10,
        "close": [100.5] * 10,
        "volume": [1000000] * 10,
    })

    with pytest.raises(ValueError, match="최소 50개"):
        compute_features(small_df)


def test_rsi_range(sample_ohlcv_df):
    result = compute_features(sample_ohlcv_df)
    assert result["rsi_14"].min() >= 0
    assert result["rsi_14"].max() <= 100
