"""매크로 리포트 메시지 포맷팅 테스트."""

from stockstock.macro.macro_score import MacroReport
from stockstock.macro.sector_rotation import SectorRank
from stockstock.notifications.messages import format_macro_report


def test_format_macro_report_basic():
    report = MacroReport(
        score=0.35,
        label="약한 강세",
        equity_pct=70,
        yield_spread=0.45,
        yield_spread_change=0.02,
        vix=18.5,
        vix_percentile=35.0,
    )
    rankings = [
        SectorRank("기술", "XLK", 0.05, 0.12, 1.03, 0.1, 0.08, 1),
        SectorRank("금융", "XLF", 0.03, 0.08, 0.98, 0.2, 0.06, 2),
        SectorRank("에너지", "XLE", 0.01, 0.04, 0.95, 0.05, 0.03, 3),
    ]

    msg = format_macro_report("2025-12-01", report, rankings)

    assert "거시경제 리포트" in msg
    assert "2025-12-01" in msg
    assert "+0.35" in msg
    assert "약한 강세" in msg
    assert "70%" in msg
    assert "XLK" in msg
    assert "XLF" in msg
    assert "VIX" in msg


def test_format_macro_report_with_rebalance():
    report = MacroReport(score=-0.2, label="약한 약세", equity_pct=40)
    rankings = []
    rebalance = ["🟢 BUY XLK 10주 @ $200.00", "🔴 SELL XLE 5주 @ $80.00"]

    msg = format_macro_report("2025-12-01", report, rankings, rebalance)

    assert "리밸런싱" in msg
    assert "BUY XLK" in msg
    assert "SELL XLE" in msg


def test_format_macro_report_negative_score():
    report = MacroReport(score=-0.7, label="약세", equity_pct=20)
    msg = format_macro_report("2025-12-01", report, [])

    assert "-0.70" in msg
    assert "약세" in msg
    assert "20%" in msg


def test_format_macro_report_commodities():
    report = MacroReport(
        score=0.1,
        label="약한 강세",
        equity_pct=70,
        copper_gold_ratio_change=0.03,
        dxy_change=-0.02,
        oil_price=75.50,
    )
    msg = format_macro_report("2025-12-01", report, [])

    assert "원자재" in msg
    assert "구리/금" in msg
    assert "달러 인덱스" in msg
    assert "$75.50" in msg
