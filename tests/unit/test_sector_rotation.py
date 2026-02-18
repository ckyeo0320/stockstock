"""섹터 로테이션 테스트."""

from unittest.mock import patch

import pandas as pd

from stockstock.macro.sector_rotation import (
    MACRO_SECTOR_SENSITIVITY,
    SECTOR_ETFS,
    SectorRank,
    _compute_momentum,
    _compute_relative_strength,
    compute_sector_rankings,
    save_sector_snapshot,
)


def _make_price_series(n: int = 100, start: float = 100.0, drift: float = 0.5):
    """테스트용 가격 시리즈 생성."""
    import numpy as np
    np.random.seed(42)
    prices = start + np.cumsum(np.random.randn(n) * 1 + drift / n)
    return pd.Series(prices)


def test_compute_momentum_basic():
    prices = pd.Series([100.0, 105.0, 110.0])
    mom = _compute_momentum(prices, 2)
    assert abs(mom - 0.1) < 1e-9  # (110 / 100) - 1 = 0.1


def test_compute_momentum_insufficient_data():
    prices = pd.Series([100.0])
    assert _compute_momentum(prices, 5) == 0.0


def test_compute_relative_strength():
    etf = pd.Series([100.0] * 20 + [110.0])  # +10%
    bench = pd.Series([100.0] * 20 + [105.0])  # +5%
    rs = _compute_relative_strength(etf, bench)
    # 1 + (0.10 - 0.05) = 1.05
    assert abs(rs - 1.05) < 1e-9


def test_compute_relative_strength_insufficient_data():
    etf = pd.Series([100.0] * 10)
    bench = pd.Series([100.0] * 10)
    assert _compute_relative_strength(etf, bench) == 1.0


def test_sector_rank_dataclass():
    rank = SectorRank(
        sector="기술", etf_ticker="XLK",
        momentum_20d=0.05, momentum_60d=0.12,
        relative_strength=1.03, macro_sector_score=0.1,
        total_score=0.08, rank=1,
    )
    assert rank.etf_ticker == "XLK"
    assert rank.rank == 1


def test_sector_etfs_mapping():
    """SECTOR_ETFS 상수 검증."""
    assert len(SECTOR_ETFS) == 9
    assert SECTOR_ETFS["기술"] == "XLK"
    assert SECTOR_ETFS["반도체"] == "SOXX"


def test_macro_sector_sensitivity_keys():
    """MACRO_SECTOR_SENSITIVITY 키 검증."""
    assert "rate_rising" in MACRO_SECTOR_SENSITIVITY
    assert "oil_rising" in MACRO_SECTOR_SENSITIVITY
    assert "dollar_weak" in MACRO_SECTOR_SENSITIVITY
    # 각 시그널은 모든 9개 ETF에 대한 가중치를 가짐
    for signal_name, weights in MACRO_SECTOR_SENSITIVITY.items():
        assert len(weights) == 9, f"{signal_name} has {len(weights)} weights"


def _mock_fetch_etf_ohlcv(ticker, period="6mo"):
    """fetch_etf_ohlcv를 모킹하여 가짜 데이터 반환."""
    import numpy as np
    np.random.seed(hash(ticker) % 2**31)
    n = 130
    dates = pd.bdate_range(end="2025-12-31", periods=n)
    base = 100.0 + (hash(ticker) % 50)
    close = base + np.cumsum(np.random.randn(n) * 1)
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": close + np.random.randn(n) * 0.5,
        "high": close + abs(np.random.randn(n)),
        "low": close - abs(np.random.randn(n)),
        "close": close,
        "volume": np.random.randint(100000, 1000000, n),
    })


@patch("stockstock.macro.sector_rotation.fetch_etf_ohlcv", side_effect=_mock_fetch_etf_ohlcv)
def test_compute_sector_rankings(mock_fetch):
    rankings = compute_sector_rankings(
        macro_signals={"rate_rising": 0.5, "dollar_weak": -0.3},
    )
    assert len(rankings) == 9
    # 순위가 1부터 시작하는지 확인
    assert rankings[0].rank == 1
    assert rankings[-1].rank == 9
    # 순위가 total_score 기준 내림차순인지 확인
    for i in range(len(rankings) - 1):
        assert rankings[i].total_score >= rankings[i + 1].total_score


@patch("stockstock.macro.sector_rotation.fetch_etf_ohlcv", side_effect=_mock_fetch_etf_ohlcv)
def test_compute_sector_rankings_subset(mock_fetch):
    """일부 섹터만 선택."""
    subset = {"기술": "XLK", "금융": "XLF", "에너지": "XLE"}
    rankings = compute_sector_rankings(sector_etfs=subset)
    assert len(rankings) == 3


@patch("stockstock.macro.sector_rotation.fetch_etf_ohlcv", side_effect=_mock_fetch_etf_ohlcv)
def test_compute_sector_rankings_no_macro(mock_fetch):
    """매크로 시그널 없이도 동작."""
    rankings = compute_sector_rankings(macro_signals=None)
    assert len(rankings) == 9
    for r in rankings:
        assert r.macro_sector_score == 0.0


def test_save_sector_snapshot(tmp_db):
    """섹터 스냅샷 DB 저장."""
    from stockstock.db.models import SectorSnapshot

    rankings = [
        SectorRank("기술", "XLK", 0.05, 0.12, 1.03, 0.1, 0.08, 1),
        SectorRank("금융", "XLF", 0.03, 0.08, 0.98, 0.2, 0.06, 2),
    ]
    save_sector_snapshot(tmp_db, rankings, "2025-12-01")

    with tmp_db() as session:
        rows = session.query(SectorSnapshot).all()
        assert len(rows) == 2
        assert rows[0].etf_ticker in ("XLK", "XLF")

    # 같은 날짜로 다시 저장 → 업데이트
    rankings[0] = SectorRank("기술", "XLK", 0.07, 0.14, 1.05, 0.15, 0.10, 1)
    save_sector_snapshot(tmp_db, rankings, "2025-12-01")

    with tmp_db() as session:
        rows = session.query(SectorSnapshot).all()
        assert len(rows) == 2  # 중복 삽입 아님
        xlk = next(r for r in rows if r.etf_ticker == "XLK")
        assert abs(xlk.momentum_20d - 0.07) < 1e-9
