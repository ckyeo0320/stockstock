"""백테스팅 엔진.

Walk-forward 방식으로 매매 전략의 과거 성과를 검증합니다.
SPY Buy & Hold 벤치마크와 비교하여 초과수익을 측정합니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from stockstock.logging_config import get_logger
from stockstock.strategy.features import compute_features
from stockstock.strategy.model import LGBMTradingModel

log = get_logger(__name__)


@dataclass
class BacktestResult:
    """백테스트 결과."""

    total_return: float
    annual_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float
    trades: list[dict] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)

    # 벤치마크 비교
    benchmark_return: float | None = None
    benchmark_annual_return: float | None = None
    benchmark_sharpe: float | None = None
    benchmark_max_drawdown: float | None = None
    alpha: float | None = None  # 전략 연환산수익률 - 벤치마크 연환산수익률


def _compute_metrics(
    equity_curve: list[float], initial_capital: float, trading_days: int,
) -> dict:
    """equity curve에서 성과 지표를 계산합니다."""
    if not equity_curve:
        return {
            "total_return": 0.0, "annual_return": 0.0,
            "sharpe_ratio": 0.0, "max_drawdown": 0.0,
        }

    final_equity = equity_curve[-1]
    total_return = (final_equity - initial_capital) / initial_capital
    annual_return = (1 + total_return) ** (252 / max(trading_days, 1)) - 1

    # MDD
    max_drawdown = 0.0
    peak = equity_curve[0]
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        drawdown = (peak - eq) / peak
        if drawdown > max_drawdown:
            max_drawdown = drawdown

    # 샤프 비율
    sharpe_ratio = 0.0
    if len(equity_curve) > 1:
        returns = pd.Series(equity_curve).pct_change().dropna()
        if returns.std() > 0:
            sharpe_ratio = float(returns.mean() / returns.std() * np.sqrt(252))

    return {
        "total_return": total_return,
        "annual_return": annual_return,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": max_drawdown,
    }


def _compute_buy_and_hold(
    df: pd.DataFrame,
    start_idx: int,
    initial_capital: float,
) -> list[float]:
    """Buy & Hold 전략의 equity curve를 계산합니다."""
    prices = df["close"].iloc[start_idx:].values
    if len(prices) == 0:
        return []
    shares = initial_capital / prices[0]
    return [float(shares * p) for p in prices]


def run_backtest(
    df: pd.DataFrame,
    train_window: int = 180,
    test_window: int = 20,
    confidence_threshold: float = 0.6,
    initial_capital: float = 100_000.0,
    include_macro: bool = False,
    benchmark_df: pd.DataFrame | None = None,
) -> BacktestResult:
    """Walk-forward 백테스트를 실행합니다.

    Args:
        df: OHLCV 원본 DataFrame
        train_window: 학습 윈도우 크기 (거래일)
        test_window: 테스트 윈도우 크기 (거래일)
        confidence_threshold: 시그널 생성 최소 확신도
        initial_capital: 초기 자본금 (USD)
        include_macro: 매크로 피처 포함 여부
        benchmark_df: 벤치마크(SPY) OHLCV DataFrame (None이면 비교 안 함)
    """
    featured_df = compute_features(df)

    capital = initial_capital
    position = 0  # 보유 수량
    entry_price = 0.0
    trades: list[dict] = []
    equity_curve: list[float] = []

    i = train_window
    while i + test_window <= len(featured_df):
        # 학습
        train_data = featured_df.iloc[i - train_window : i]
        model = LGBMTradingModel(include_macro=include_macro)
        model.train(train_data)

        # 테스트 윈도우 내 각 날짜에 대해 예측
        for j in range(i, min(i + test_window, len(featured_df))):
            test_slice = featured_df.iloc[: j + 1]
            prediction, confidence = model.predict(test_slice)

            close_price = float(featured_df.iloc[j]["close"])
            equity = capital + position * close_price
            equity_curve.append(equity)

            if confidence < confidence_threshold:
                continue

            if prediction == "UP" and position == 0:
                # 매수: 자본의 100% 투입
                quantity = int(capital / close_price)
                if quantity > 0:
                    position = quantity
                    entry_price = close_price
                    capital -= quantity * close_price
                    trades.append({
                        "type": "BUY",
                        "price": close_price,
                        "quantity": quantity,
                        "index": j,
                    })

            elif prediction == "DOWN" and position > 0:
                # 매도: 전량 매도
                capital += position * close_price
                pnl = (close_price - entry_price) * position
                trades.append({
                    "type": "SELL",
                    "price": close_price,
                    "quantity": position,
                    "pnl": pnl,
                    "index": j,
                })
                position = 0

        i += test_window

    # 미청산 포지션 정리
    if position > 0:
        final_price = float(featured_df.iloc[-1]["close"])
        capital += position * final_price
        pnl = (final_price - entry_price) * position
        trades.append({
            "type": "SELL (CLOSE)",
            "price": final_price,
            "quantity": position,
            "pnl": pnl,
            "index": len(featured_df) - 1,
        })
        position = 0

    # 성과 지표 계산
    sell_trades = [t for t in trades if "pnl" in t]
    winning = [t for t in sell_trades if t["pnl"] > 0]
    losing = [t for t in sell_trades if t["pnl"] <= 0]

    win_rate = len(winning) / len(sell_trades) if sell_trades else 0
    avg_win = float(np.mean([t["pnl"] for t in winning])) if winning else 0.0
    avg_loss = float(np.mean([t["pnl"] for t in losing])) if losing else 0.0

    trading_days = len(equity_curve) if equity_curve else len(featured_df)
    metrics = _compute_metrics(equity_curve, initial_capital, trading_days)

    # 벤치마크 비교
    bench_return = None
    bench_annual = None
    bench_sharpe = None
    bench_mdd = None
    alpha = None

    if benchmark_df is not None and len(benchmark_df) > train_window:
        bench_equity = _compute_buy_and_hold(
            benchmark_df, train_window, initial_capital,
        )
        bench_days = len(bench_equity)
        if bench_equity:
            bench_metrics = _compute_metrics(
                bench_equity, initial_capital, bench_days,
            )
            bench_return = bench_metrics["total_return"]
            bench_annual = bench_metrics["annual_return"]
            bench_sharpe = bench_metrics["sharpe_ratio"]
            bench_mdd = bench_metrics["max_drawdown"]
            alpha = metrics["annual_return"] - bench_annual

    result = BacktestResult(
        total_return=metrics["total_return"],
        annual_return=metrics["annual_return"],
        sharpe_ratio=metrics["sharpe_ratio"],
        max_drawdown=metrics["max_drawdown"],
        win_rate=win_rate,
        total_trades=len(sell_trades),
        winning_trades=len(winning),
        losing_trades=len(losing),
        avg_win=avg_win,
        avg_loss=avg_loss,
        trades=trades,
        equity_curve=equity_curve,
        benchmark_return=bench_return,
        benchmark_annual_return=bench_annual,
        benchmark_sharpe=bench_sharpe,
        benchmark_max_drawdown=bench_mdd,
        alpha=alpha,
    )

    log.info(
        "backtest_completed",
        total_return=f"{metrics['total_return']:.2%}",
        sharpe_ratio=f"{metrics['sharpe_ratio']:.2f}",
        max_drawdown=f"{metrics['max_drawdown']:.2%}",
        win_rate=f"{win_rate:.2%}",
        total_trades=len(sell_trades),
        alpha=f"{alpha:.2%}" if alpha is not None else "N/A",
    )

    return result
