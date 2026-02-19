"""ML 모델 학습 스크립트.

DB에 저장된 과거 데이터를 사용하여 LightGBM 모델을 학습합니다.
매크로 활성 시 섹터 ETF 데이터 + 매크로 피처로 학습합니다.

사용법: python scripts/train_model.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd

from stockstock.config import AppConfig
from stockstock.db.models import init_db
from stockstock.db.repository import get_ohlcv
from stockstock.logging_config import setup_logging
from stockstock.strategy.backtest import run_backtest
from stockstock.strategy.features import compute_features
from stockstock.strategy.model import LGBMTradingModel


def _train_symbol_mode(config: AppConfig, session_factory) -> None:
    """개별 종목 모드 학습 (매크로 비활성 시)."""
    all_dfs = []
    for symbol in config.trading.symbols:
        print(f"[*] {symbol} 데이터 로드 중...")
        with session_factory() as session:
            df = get_ohlcv(session, symbol, limit=config.model.lookback_days)
        if len(df) >= 60:
            df["symbol"] = symbol
            all_dfs.append(df)
            print(f"    {symbol}: {len(df)}행 로드됨")
        else:
            print(f"    {symbol}: 데이터 부족 ({len(df)}행) - 건너뜀")

    if not all_dfs:
        print("[!] 학습할 데이터가 없습니다. seed_historical.py를 먼저 실행하세요.")
        return

    combined_df = pd.concat(all_dfs, ignore_index=True)
    _train_and_evaluate(config, combined_df, include_macro=False)


def _train_macro_mode(config: AppConfig, session_factory) -> None:
    """섹터 ETF + 매크로 피처 모드 학습."""
    from stockstock.macro.market_data import fetch_etf_ohlcv

    print("[*] 매크로 섹터 로테이션 모드 학습")
    print(f"    섹터 ETF: {config.macro.sector_etfs}")

    # 1. 매크로 데이터 수집 (FRED + Yahoo)
    fred_key = config.fred.api_key.get_secret_value()
    if fred_key:
        from stockstock.macro.fred_client import FredClient
        print("\n[*] FRED 데이터 수집 중...")
        fred = FredClient(fred_key, session_factory)
        fred.fetch_and_cache(config.macro.fred_series, lookback_days=365 * 3)
        print("    FRED 데이터 수집 완료")

    from stockstock.macro.market_data import fetch_and_cache_market_data
    print("[*] 시장 데이터(VIX, 원자재, 환율) 수집 중...")
    commodity_tickers = {t: t for t in config.macro.commodities}
    commodity_tickers["vix"] = "^VIX"
    fetch_and_cache_market_data(session_factory, commodity_tickers)
    print("    시장 데이터 수집 완료")

    # 2. 매크로 점수 계산
    from stockstock.macro.macro_score import compute_macro_score
    print("[*] 매크로 점수 계산 중...")
    macro_report = compute_macro_score(session_factory)
    print(f"    매크로 점수: {macro_report.score:.3f} ({macro_report.label})")

    # 3. 섹터 순위 계산
    from stockstock.macro.sector_rotation import (
        SECTOR_ETFS,
        compute_sector_rankings,
    )
    print("[*] 섹터 순위 계산 중...")
    sector_etf_map = {
        sector: ticker
        for sector, ticker in SECTOR_ETFS.items()
        if ticker in config.macro.sector_etfs
    }
    rankings = compute_sector_rankings(
        macro_signals=macro_report.macro_signals,
        sector_etfs=sector_etf_map,
    )
    for r in rankings[:3]:
        print(f"    {r.rank}. {r.etf_ticker} ({r.sector}) score={r.total_score:.4f}")

    # 4. 섹터 ETF OHLCV 수집 + 피처 계산
    print("\n[*] 섹터 ETF 데이터 수집 및 피처 계산 중...")
    all_dfs = []
    ranking_map = {r.etf_ticker: r for r in rankings}

    for ticker in config.macro.sector_etfs:
        print(f"    {ticker} 데이터 수집 중...")
        df = fetch_etf_ohlcv(ticker, period="3y")
        if len(df) < 60:
            print(f"    {ticker}: 데이터 부족 ({len(df)}행) - 건너뜀")
            continue

        try:
            sector_rank = ranking_map.get(ticker)
            featured = compute_features(
                df, macro_report=macro_report, sector_rank=sector_rank,
            )
            # 마지막 5행 제거 (미래 데이터 없는 구간)
            featured = featured.iloc[:-5]
            featured["symbol"] = ticker
            all_dfs.append(featured)
            print(f"    {ticker}: {len(featured)}행 피처 계산됨")
        except ValueError as e:
            print(f"    {ticker}: 피처 계산 실패 - {e}")

    if not all_dfs:
        print("[!] 피처 계산된 데이터가 없습니다.")
        return

    # 5. 모델 학습
    all_featured = pd.concat(all_dfs, ignore_index=True)
    print(f"\n[*] 총 학습 데이터: {len(all_featured)}행")

    model = LGBMTradingModel(include_macro=True)
    metrics = model.train(all_featured)

    print("\n[*] 학습 결과:")
    print(f"    CV 평균 정확도: {metrics['mean_cv_score']:.4f}")
    print(f"    CV 표준편차: {metrics['std_cv_score']:.4f}")
    print(f"    학습 샘플 수: {metrics['train_samples']}")
    print(f"    레이블 분포: {metrics['label_distribution']}")

    model.save(config.model.artifact_path)
    print(f"\n[*] 모델 저장됨: {config.model.artifact_path}")

    # 6. 백테스트 (첫 번째 ETF + SPY 벤치마크)
    _run_etf_backtest(config, all_dfs, macro_report, ranking_map)


def _train_and_evaluate(
    config: AppConfig, combined_df: pd.DataFrame, include_macro: bool,
) -> None:
    """통합 데이터로 모델 학습 + 평가."""
    print("\n[*] 모델 학습 시작...")

    featured_dfs = []
    for symbol in combined_df["symbol"].unique():
        symbol_df = combined_df[combined_df["symbol"] == symbol].copy()
        symbol_df = symbol_df.drop(columns=["symbol"])
        try:
            featured = compute_features(symbol_df)
            featured = featured.iloc[:-5]
            featured["symbol"] = symbol
            featured_dfs.append(featured)
        except ValueError as e:
            print(f"    {symbol}: 피처 계산 실패 - {e}")

    if not featured_dfs:
        print("[!] 피처 계산된 데이터가 없습니다.")
        return

    all_featured = pd.concat(featured_dfs, ignore_index=True)
    print(f"    총 학습 데이터: {len(all_featured)}행")

    model = LGBMTradingModel(include_macro=include_macro)
    metrics = model.train(all_featured)

    print("\n[*] 학습 결과:")
    print(f"    CV 평균 정확도: {metrics['mean_cv_score']:.4f}")
    print(f"    CV 표준편차: {metrics['std_cv_score']:.4f}")
    print(f"    학습 샘플 수: {metrics['train_samples']}")
    print(f"    레이블 분포: {metrics['label_distribution']}")

    model.save(config.model.artifact_path)
    print(f"\n[*] 모델 저장됨: {config.model.artifact_path}")

    # 백테스트
    print("\n[*] 백테스트 실행 중...")
    first_symbol = list(combined_df["symbol"].unique())[0]
    first_df = combined_df[combined_df["symbol"] == first_symbol].drop(
        columns=["symbol"],
    )

    if len(first_df) >= 200:
        result = run_backtest(
            first_df,
            confidence_threshold=config.model.confidence_threshold,
            include_macro=include_macro,
        )
        _print_backtest_result(first_symbol, result)
    else:
        print(f"    {first_symbol}: 백테스트에 데이터 부족 ({len(first_df)}행)")


def _run_etf_backtest(
    config: AppConfig, featured_dfs: list, macro_report=None, ranking_map=None,
) -> None:
    """ETF 백테스트 + SPY 벤치마크 비교."""
    from stockstock.macro.market_data import fetch_etf_ohlcv

    print("\n[*] 백테스트 + SPY 벤치마크 비교 실행 중...")

    # SPY 벤치마크 데이터
    spy_df = fetch_etf_ohlcv("SPY", period="3y")
    if len(spy_df) < 200:
        print("    SPY 데이터 부족 - 벤치마크 비교 불가")
        spy_df = None

    # 첫 번째 ETF로 백테스트
    if featured_dfs:
        first = featured_dfs[0]
        symbol = first["symbol"].iloc[0]

        # 원본 OHLCV가 필요하므로 다시 수집
        raw_df = fetch_etf_ohlcv(symbol, period="3y")
        if len(raw_df) >= 200:
            sector_rank = ranking_map.get(symbol) if ranking_map else None
            result = run_backtest(
                raw_df,
                confidence_threshold=config.model.confidence_threshold,
                include_macro=True,
                benchmark_df=spy_df,
                macro_report=macro_report,
                sector_rank=sector_rank,
            )
            _print_backtest_result(symbol, result)
        else:
            print(f"    {symbol}: 백테스트에 데이터 부족")


def _print_backtest_result(symbol: str, result) -> None:
    """백테스트 결과를 출력합니다."""
    print(f"\n[*] 백테스트 결과 ({symbol}):")
    print(f"    총 수익률: {result.total_return:.2%}")
    print(f"    연간 수익률: {result.annual_return:.2%}")
    print(f"    샤프 비율: {result.sharpe_ratio:.2f}")
    print(f"    최대 낙폭: {result.max_drawdown:.2%}")
    print(f"    승률: {result.win_rate:.2%}")
    print(f"    총 거래 수: {result.total_trades}")

    if result.benchmark_return is not None:
        print("\n    --- SPY 벤치마크 비교 ---")
        print(f"    SPY 총 수익률: {result.benchmark_return:.2%}")
        print(f"    SPY 연간 수익률: {result.benchmark_annual_return:.2%}")
        print(f"    SPY 샤프 비율: {result.benchmark_sharpe:.2f}")
        print(f"    SPY 최대 낙폭: {result.benchmark_max_drawdown:.2%}")
        print(f"    Alpha (초과수익): {result.alpha:.2%}")
        if result.alpha is not None and result.alpha < 0:
            print("    ⚠️  전략이 SPY 대비 초과수익을 내지 못했습니다!")


def main() -> None:
    config = AppConfig()
    setup_logging(level="INFO")

    session_factory = init_db(str(config.db_path))

    if config.macro.enabled:
        _train_macro_mode(config, session_factory)
    else:
        _train_symbol_mode(config, session_factory)

    print("\n[*] 완료!")


if __name__ == "__main__":
    main()
