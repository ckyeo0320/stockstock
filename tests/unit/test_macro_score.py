"""매크로 점수 계산 테스트."""

import pandas as pd

from stockstock.macro.macro_score import (
    MacroReport,
    _pct_change_n,
    _percentile,
    compute_macro_score,
)


def test_pct_change_n_basic():
    s = pd.Series([100.0, 110.0])
    assert abs(_pct_change_n(s, 1) - 0.1) < 1e-9


def test_pct_change_n_insufficient_data():
    s = pd.Series([100.0])
    assert _pct_change_n(s, 1) == 0.0


def test_pct_change_n_zero_old():
    s = pd.Series([0.0, 10.0])
    assert _pct_change_n(s, 1) == 0.0


def test_percentile_basic():
    s = pd.Series(range(1, 101))  # 1~100
    pctile = _percentile(s, 100)
    # 현재 값 100은 99개보다 큼 → ~99%
    assert pctile > 90


def test_percentile_single_value():
    s = pd.Series([50.0])
    assert _percentile(s, 60) == 50.0


def test_macro_report_dataclass():
    report = MacroReport(score=0.5, label="강세", equity_pct=90)
    assert report.score == 0.5
    assert report.label == "강세"
    assert report.equity_pct == 90
    assert report.vix is None
    assert report.macro_signals == {}


def test_macro_report_with_signals():
    report = MacroReport(
        score=-0.3,
        label="약한 약세",
        equity_pct=40,
        vix=28.5,
        macro_signals={"rate_rising": 0.5, "dollar_weak": -0.3},
    )
    assert report.vix == 28.5
    assert len(report.macro_signals) == 2


def test_compute_macro_score_empty_db(tmp_db):
    """DB에 데이터가 없을 때 기본값 반환."""
    report = compute_macro_score(tmp_db)
    assert report.score == 0.0
    assert report.label == "약한 강세"
    assert report.equity_pct == 70


def test_compute_macro_score_with_data(tmp_db):
    """DB에 데이터가 있을 때 점수 계산."""
    from datetime import datetime, timedelta

    from stockstock.db.models import MacroData

    with tmp_db() as session:
        # VIX 데이터 삽입 (낮은 VIX → 긍정적)
        for i in range(90):
            dt = (datetime.now() - timedelta(days=90 - i)).strftime("%Y-%m-%d")
            session.add(MacroData(
                series_id="^VIX", dt=dt, value=15.0 + i * 0.01, source="yahoo",
            ))

        # T10Y2Y (양수 스프레드 → 긍정적)
        for i in range(90):
            dt = (datetime.now() - timedelta(days=90 - i)).strftime("%Y-%m-%d")
            session.add(MacroData(
                series_id="T10Y2Y", dt=dt, value=0.5 + i * 0.001, source="fred",
            ))

        session.commit()

    report = compute_macro_score(tmp_db)
    # VIX ~15-16 → 긍정적, T10Y2Y 양수 & 확대 → 긍정적
    assert report.score > 0
    assert report.vix is not None
    assert report.yield_spread is not None
