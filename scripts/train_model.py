"""ML 모델 학습 스크립트.

DB에 저장된 과거 데이터를 사용하여 LightGBM 모델을 학습합니다.

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


def main() -> None:
    config = AppConfig()
    setup_logging(level="INFO")

    session_factory = init_db(str(config.db_path))

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

    # 종목별 학습 및 통합 모델 학습
    print("\n[*] 모델 학습 시작...")

    # 전체 데이터 통합 (다중 종목 학습)
    combined_df = pd.concat(all_dfs, ignore_index=True)

    # 종목별로 피처 계산 후 통합
    featured_dfs = []
    for symbol in combined_df["symbol"].unique():
        symbol_df = combined_df[combined_df["symbol"] == symbol].copy()
        symbol_df = symbol_df.drop(columns=["symbol"])
        try:
            featured = compute_features(symbol_df)
            featured["symbol"] = symbol
            featured_dfs.append(featured)
        except ValueError as e:
            print(f"    {symbol}: 피처 계산 실패 - {e}")

    if not featured_dfs:
        print("[!] 피처 계산된 데이터가 없습니다.")
        return

    all_featured = pd.concat(featured_dfs, ignore_index=True)
    print(f"    총 학습 데이터: {len(all_featured)}행")

    model = LGBMTradingModel()
    metrics = model.train(all_featured)

    print(f"\n[*] 학습 결과:")
    print(f"    CV 평균 정확도: {metrics['mean_cv_score']:.4f}")
    print(f"    CV 표준편차: {metrics['std_cv_score']:.4f}")
    print(f"    학습 샘플 수: {metrics['train_samples']}")
    print(f"    레이블 분포: {metrics['label_distribution']}")

    # 모델 저장
    model.save(config.model.artifact_path)
    print(f"\n[*] 모델 저장됨: {config.model.artifact_path}")

    # 백테스트 (첫 번째 종목으로)
    print("\n[*] 백테스트 실행 중...")
    first_symbol = list(combined_df["symbol"].unique())[0]
    first_df = combined_df[combined_df["symbol"] == first_symbol].drop(columns=["symbol"])

    if len(first_df) >= 200:
        result = run_backtest(first_df, confidence_threshold=config.model.confidence_threshold)
        print(f"\n[*] 백테스트 결과 ({first_symbol}):")
        print(f"    총 수익률: {result.total_return:.2%}")
        print(f"    연간 수익률: {result.annual_return:.2%}")
        print(f"    샤프 비율: {result.sharpe_ratio:.2f}")
        print(f"    최대 낙폭: {result.max_drawdown:.2%}")
        print(f"    승률: {result.win_rate:.2%}")
        print(f"    총 거래 수: {result.total_trades}")
    else:
        print(f"    {first_symbol}: 백테스트에 데이터가 부족합니다 ({len(first_df)}행)")

    print("\n[*] 완료!")


if __name__ == "__main__":
    main()
