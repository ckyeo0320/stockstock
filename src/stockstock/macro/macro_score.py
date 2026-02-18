"""종합 매크로 점수 계산 모듈.

금리, VIX, 원자재/환율 데이터를 종합하여 -1.0 ~ +1.0 사이의 점수를 산출합니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pandas as pd

from stockstock.logging_config import get_logger

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

log = get_logger(__name__)


@dataclass
class MacroReport:
    """거시경제 분석 리포트."""

    score: float  # -1.0 ~ +1.0
    label: str  # "강세", "약한 강세", "약한 약세", "약세"
    equity_pct: int  # 주식 비중 (%)

    yield_spread: float | None = None
    yield_spread_change: float | None = None
    high_yield_spread: float | None = None
    fed_funds_rate: float | None = None
    vix: float | None = None
    vix_percentile: float | None = None
    copper_gold_ratio_change: float | None = None
    dxy_change: float | None = None
    oil_price: float | None = None

    # 매크로 시그널 (섹터 로테이션에 전달)
    macro_signals: dict[str, float] = field(default_factory=dict)


def _pct_change_n(series: pd.Series, n: int) -> float:
    """N일 변화율을 계산합니다."""
    if len(series) < n + 1:
        return 0.0
    old = series.iloc[-(n + 1)]
    new = series.iloc[-1]
    if old == 0:
        return 0.0
    return float((new - old) / abs(old))


def _percentile(series: pd.Series, window: int = 60) -> float:
    """현재 값의 N일 백분위를 계산합니다."""
    if len(series) < 2:
        return 50.0
    recent = series.tail(window)
    current = series.iloc[-1]
    return float((recent < current).sum() / len(recent) * 100)


def compute_macro_score(
    session_factory: sessionmaker[Session],
) -> MacroReport:
    """종합 매크로 점수를 계산합니다.

    각 지표의 개별 점수(-1~+1)를 가중 평균하여 종합 점수를 산출합니다.
    """
    from stockstock.macro.market_data import get_cached_series

    scores: list[tuple[float, float]] = []  # (score, weight)
    report_kwargs: dict = {}
    macro_signals: dict[str, float] = {}

    # --- 1. 2-10년 스프레드 ---
    spread_df = get_cached_series(session_factory, "T10Y2Y")
    if not spread_df.empty:
        spread_val = float(spread_df["value"].iloc[-1])
        spread_change = _pct_change_n(spread_df["value"], 20)
        report_kwargs["yield_spread"] = spread_val
        report_kwargs["yield_spread_change"] = spread_change

        # 스프레드 역전(-) = 매우 부정적, 양수 & 확대 추세 = 긍정적
        if spread_val < 0:
            s = -0.8
        elif spread_change < -0.1:
            s = -0.3
        elif spread_change > 0.1:
            s = 0.3
        else:
            s = 0.0
        scores.append((s, 0.25))

        # 금리 상승 시그널 (스프레드 축소 = 단기 금리 상승 > 장기)
        macro_signals["rate_rising"] = max(-1.0, min(1.0, -spread_change * 5))

    # --- 2. 하이일드 스프레드 ---
    hy_df = get_cached_series(session_factory, "BAMLH0A0HYM2")
    if not hy_df.empty:
        hy_val = float(hy_df["value"].iloc[-1])
        report_kwargs["high_yield_spread"] = hy_val

        # 하이일드 스프레드: 낮을수록 긍정적 (정상 3~5%)
        if hy_val > 6:
            s = -0.8
        elif hy_val > 5:
            s = -0.3
        elif hy_val < 3.5:
            s = 0.3
        else:
            s = 0.0
        scores.append((s, 0.15))

    # --- 3. 연방기금금리 ---
    ff_df = get_cached_series(session_factory, "FEDFUNDS")
    if not ff_df.empty:
        report_kwargs["fed_funds_rate"] = float(ff_df["value"].iloc[-1])

    # --- 4. VIX ---
    vix_df = get_cached_series(session_factory, "^VIX")
    if not vix_df.empty:
        vix_val = float(vix_df["value"].iloc[-1])
        vix_pctile = _percentile(vix_df["value"], 60)
        report_kwargs["vix"] = vix_val
        report_kwargs["vix_percentile"] = vix_pctile

        # VIX: < 20 긍정, 20~30 중립, > 30 부정
        if vix_val > 30:
            s = -0.8
        elif vix_val > 25:
            s = -0.4
        elif vix_val > 20:
            s = -0.1
        elif vix_val < 15:
            s = 0.4
        else:
            s = 0.2
        scores.append((s, 0.25))

    # --- 5. 구리/금 비율 ---
    copper_df = get_cached_series(session_factory, "HG=F")
    gold_df = get_cached_series(session_factory, "GC=F")
    if not copper_df.empty and not gold_df.empty:
        # 날짜 기준 병합
        merged = pd.merge(
            copper_df.rename(columns={"value": "copper"}),
            gold_df.rename(columns={"value": "gold"}),
            on="date",
            how="inner",
        )
        if len(merged) > 20:
            merged["ratio"] = merged["copper"] / merged["gold"]
            ratio_change = _pct_change_n(merged["ratio"], 20)
            report_kwargs["copper_gold_ratio_change"] = ratio_change

            # 구리/금 비율 상승 = 경기 확장
            s = max(-0.5, min(0.5, ratio_change * 10))
            scores.append((s, 0.15))

    # --- 6. 달러 인덱스 ---
    dxy_df = get_cached_series(session_factory, "DX-Y.NYB")
    if not dxy_df.empty and len(dxy_df) > 20:
        dxy_change = _pct_change_n(dxy_df["value"], 20)
        report_kwargs["dxy_change"] = dxy_change

        # 달러 약세 = 주식에 긍정적 (수출 수혜, 유동성 증가)
        s = max(-0.5, min(0.5, -dxy_change * 10))
        scores.append((s, 0.10))

        macro_signals["dollar_weak"] = max(-1.0, min(1.0, -dxy_change * 10))

    # --- 7. 원유 ---
    oil_df = get_cached_series(session_factory, "CL=F")
    if not oil_df.empty:
        oil_price = float(oil_df["value"].iloc[-1])
        report_kwargs["oil_price"] = oil_price

        if len(oil_df) > 20:
            oil_change = _pct_change_n(oil_df["value"], 20)
            macro_signals["oil_rising"] = max(-1.0, min(1.0, oil_change * 5))

    # --- 종합 점수 계산 ---
    if scores:
        total_weight = sum(w for _, w in scores)
        weighted_sum = sum(s * w for s, w in scores)
        final_score = weighted_sum / total_weight if total_weight > 0 else 0.0
    else:
        final_score = 0.0

    # -1 ~ +1 범위 클램핑
    final_score = max(-1.0, min(1.0, final_score))

    # 레이블 & 주식 비중 결정
    if final_score >= 0.5:
        label = "강세"
        equity_pct = 90
    elif final_score >= 0:
        label = "약한 강세"
        equity_pct = 70
    elif final_score >= -0.5:
        label = "약한 약세"
        equity_pct = 40
    else:
        label = "약세"
        equity_pct = 20

    report = MacroReport(
        score=round(final_score, 3),
        label=label,
        equity_pct=equity_pct,
        macro_signals=macro_signals,
        **report_kwargs,
    )

    log.info(
        "macro_score_computed",
        score=report.score,
        label=report.label,
        equity_pct=report.equity_pct,
    )
    return report
