"""ML 파이프라인 통합 테스트.

OHLCV → 피처 계산 → 모델 학습 → 예측 → 시그널 생성까지의 전체 흐름을 검증합니다.
"""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stockstock.strategy.backtest import BacktestResult, run_backtest
from stockstock.strategy.features import compute_features
from stockstock.strategy.model import LGBMTradingModel
from stockstock.strategy.signals import SignalType, generate_signal


@pytest.fixture
def large_ohlcv_df():
    """학습에 충분한 크기의 OHLCV DataFrame (300행)."""
    np.random.seed(42)
    n = 300
    dates = pd.bdate_range(end="2025-12-31", periods=n)
    base = 150.0
    prices = base + np.cumsum(np.random.randn(n) * 2)

    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": prices + np.random.randn(n) * 0.5,
        "high": prices + abs(np.random.randn(n)) * 2,
        "low": prices - abs(np.random.randn(n)) * 2,
        "close": prices,
        "volume": np.random.randint(1_000_000, 10_000_000, n),
    })


class TestFeaturesToPrediction:
    """OHLCV → features → model train → predict → signal 파이프라인."""

    def test_full_pipeline(self, large_ohlcv_df):
        # 1. 피처 계산 (지표 워밍업으로 앞쪽 행이 제거됨)
        featured = compute_features(large_ohlcv_df)
        assert len(featured) > 200  # 300행 중 워밍업 제외하고 충분한 행 존재
        assert not featured.isna().all(axis=1).any()

        # 2. 모델 학습
        model = LGBMTradingModel(include_macro=False)
        metrics = model.train(featured)

        assert "mean_cv_score" in metrics
        assert metrics["train_samples"] > 0
        assert metrics["mean_cv_score"] > 0

        # 3. 예측
        prediction, confidence = model.predict(featured)

        assert prediction in ("UP", "DOWN", "HOLD")
        assert 0.0 <= confidence <= 1.0

        # 4. 시그널 생성
        signal = generate_signal("AAPL", prediction, confidence, 0.6)

        assert signal.symbol == "AAPL"
        assert signal.signal in (SignalType.BUY, SignalType.SELL, SignalType.HOLD)
        assert signal.prediction == prediction

    def test_model_save_load_roundtrip(self, large_ohlcv_df):
        """모델 저장 → 로드 → 동일 예측 확인."""
        featured = compute_features(large_ohlcv_df)

        # 학습 + 저장
        model = LGBMTradingModel(include_macro=False)
        model.train(featured)
        pred_orig, conf_orig = model.predict(featured)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "model.txt")
            model.save(path)

            # 새 인스턴스로 로드
            model2 = LGBMTradingModel()
            model2.load(path)
            pred_loaded, conf_loaded = model2.predict(featured)

        assert pred_orig == pred_loaded
        assert abs(conf_orig - conf_loaded) < 0.01

    def test_model_save_load_with_macro(self, large_ohlcv_df):
        """매크로 모델 저장 → 로드 시 include_macro 플래그 복원."""
        from stockstock.macro.macro_score import MacroReport

        macro_report = MacroReport(score=0.3, label="약한 강세", equity_pct=70)
        featured = compute_features(large_ohlcv_df, macro_report=macro_report)

        model = LGBMTradingModel(include_macro=True)
        model.train(featured)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "macro_model.txt")
            model.save(path)

            model2 = LGBMTradingModel()
            model2.load(path)

            assert model2._include_macro is True
            assert len(model2._feature_cols) > 24  # 매크로 피처 포함


class TestBacktest:
    """백테스팅 엔진 통합 테스트."""

    def test_backtest_basic(self, large_ohlcv_df):
        result = run_backtest(
            large_ohlcv_df,
            train_window=60,
            test_window=10,
            confidence_threshold=0.5,
        )

        assert isinstance(result, BacktestResult)
        assert result.total_trades >= 0
        assert result.winning_trades + result.losing_trades == result.total_trades
        assert len(result.equity_curve) > 0
        assert result.benchmark_return is None  # 벤치마크 미제공

    def test_backtest_with_benchmark(self, large_ohlcv_df):
        """SPY 벤치마크 비교."""
        np.random.seed(99)
        n = 300
        dates = pd.bdate_range(end="2025-12-31", periods=n)
        spy_prices = 400 + np.cumsum(np.random.randn(n) * 1.5)

        spy_df = pd.DataFrame({
            "date": dates.strftime("%Y-%m-%d"),
            "open": spy_prices,
            "high": spy_prices + 1,
            "low": spy_prices - 1,
            "close": spy_prices,
            "volume": np.random.randint(50_000_000, 100_000_000, n),
        })

        result = run_backtest(
            large_ohlcv_df,
            train_window=60,
            test_window=10,
            benchmark_df=spy_df,
        )

        assert result.benchmark_return is not None
        assert result.benchmark_annual_return is not None
        assert result.benchmark_sharpe is not None
        assert result.benchmark_max_drawdown is not None
        assert result.alpha is not None
        # alpha = strategy annual return - benchmark annual return
        expected_alpha = result.annual_return - result.benchmark_annual_return
        assert abs(result.alpha - expected_alpha) < 1e-9

    def test_backtest_equity_curve_monotonic_start(self, large_ohlcv_df):
        """equity curve 첫 값은 초기 자본에 가까워야 한다."""
        result = run_backtest(
            large_ohlcv_df,
            train_window=60,
            test_window=10,
            initial_capital=50_000.0,
        )

        if result.equity_curve:
            # 첫 날에는 포지션이 없으므로 초기 자본과 동일
            assert abs(result.equity_curve[0] - 50_000.0) < 1.0
