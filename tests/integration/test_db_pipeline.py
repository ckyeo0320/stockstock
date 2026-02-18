"""DB 파이프라인 통합 테스트.

DB CRUD → 피처 계산, 시그널/거래 기록, 시스템 상태 등 DB 경유 흐름을 검증합니다.
"""

import numpy as np
import pandas as pd

from stockstock.db.repository import (
    get_ohlcv,
    get_recent_trades,
    get_system_state,
    log_risk_event,
    log_signal,
    log_trade,
    save_portfolio_snapshot,
    set_system_state,
    update_trade_status,
    upsert_ohlcv,
)
from stockstock.strategy.features import compute_features


class TestOhlcvPipeline:
    """OHLCV upsert → get → compute_features 파이프라인."""

    def _make_ohlcv_df(self, n=100):
        np.random.seed(42)
        dates = pd.bdate_range(end="2025-12-31", periods=n)
        prices = 150.0 + np.cumsum(np.random.randn(n) * 2)
        return pd.DataFrame({
            "date": dates.strftime("%Y-%m-%d"),
            "open": prices + np.random.randn(n) * 0.5,
            "high": prices + abs(np.random.randn(n)) * 2,
            "low": prices - abs(np.random.randn(n)) * 2,
            "close": prices,
            "volume": np.random.randint(1_000_000, 10_000_000, n),
        })

    def test_upsert_and_get_roundtrip(self, tmp_db):
        df = self._make_ohlcv_df(100)
        with tmp_db() as session:
            inserted = upsert_ohlcv(session, "AAPL", df)
            assert inserted == 100

            loaded = get_ohlcv(session, "AAPL", limit=200)
            assert len(loaded) == 100
            assert list(loaded.columns) == ["date", "open", "high", "low", "close", "volume"]

    def test_upsert_updates_existing(self, tmp_db):
        df = self._make_ohlcv_df(10)
        with tmp_db() as session:
            upsert_ohlcv(session, "AAPL", df)

            # 같은 데이터 재삽입 → 0건 삽입 (업데이트)
            inserted = upsert_ohlcv(session, "AAPL", df)
            assert inserted == 0

            loaded = get_ohlcv(session, "AAPL")
            assert len(loaded) == 10

    def test_ohlcv_to_features(self, tmp_db):
        """DB에서 읽은 OHLCV로 피처 계산 성공."""
        df = self._make_ohlcv_df(100)
        with tmp_db() as session:
            upsert_ohlcv(session, "MSFT", df)
            loaded = get_ohlcv(session, "MSFT", limit=252)

        featured = compute_features(loaded)
        assert len(featured) > 30  # 지표 워밍업으로 앞쪽 행 제거됨
        assert "rsi_14" in featured.columns
        assert "macd" in featured.columns


class TestSignalTradePipeline:
    """시그널 기록 → 거래 기록 → 상태 업데이트 → 조회 파이프라인."""

    def test_signal_to_trade_flow(self, tmp_db):
        with tmp_db() as session:
            # 시그널 기록
            signal_id = log_signal(
                session, "AAPL", "BUY",
                confidence=0.75,
                features={"rsi": 35.0},
                model_version="lgbm_v1",
            )
            assert signal_id > 0

            # 거래 기록 (시그널 FK 연결)
            trade_id = log_trade(
                session, "AAPL", "BUY", quantity=10,
                order_type="MARKET",
                requested_price=150.0,
                signal_id=signal_id,
            )
            assert trade_id > 0

            # 상태 업데이트: PENDING → FILLED
            update_trade_status(
                session, trade_id,
                status="FILLED",
                filled_price=150.50,
                filled_quantity=10,
            )

            # 조회 확인
            trades = get_recent_trades(session, symbol="AAPL")
            assert len(trades) == 1
            assert trades[0].status == "FILLED"
            assert trades[0].filled_price == 150.50
            assert trades[0].filled_at is not None
            assert trades[0].signal_id == signal_id

    def test_multiple_trades_ordering(self, tmp_db):
        """최근 거래가 먼저 반환."""
        with tmp_db() as session:
            for i in range(5):
                log_trade(session, "NVDA", "BUY", quantity=i + 1)

            trades = get_recent_trades(session, limit=3)
            assert len(trades) == 3
            # 최신순 (quantity 5, 4, 3)
            assert trades[0].quantity == 5
            assert trades[1].quantity == 4


class TestSystemState:
    """시스템 상태 키-밸류 저장."""

    def test_set_and_get(self, tmp_db):
        with tmp_db() as session:
            assert get_system_state(session, "trading_active") is None

            set_system_state(session, "trading_active", "true")
            assert get_system_state(session, "trading_active") == "true"

    def test_upsert_semantics(self, tmp_db):
        with tmp_db() as session:
            set_system_state(session, "mode", "paper")
            set_system_state(session, "mode", "live")

            assert get_system_state(session, "mode") == "live"


class TestPortfolioAndRisk:
    """포트폴리오 스냅샷 + 리스크 이벤트."""

    def test_portfolio_snapshot_upsert(self, tmp_db):
        with tmp_db() as session:
            save_portfolio_snapshot(
                session, "2025-12-01",
                total_value_usd=100_000.0,
                cash_usd=30_000.0,
                holdings=[{"symbol": "AAPL", "qty": 50}],
                daily_pnl_usd=500.0,
            )
            # 같은 날짜 업데이트
            save_portfolio_snapshot(
                session, "2025-12-01",
                total_value_usd=101_000.0,
                cash_usd=31_000.0,
                holdings=[{"symbol": "AAPL", "qty": 50}],
                daily_pnl_usd=1_500.0,
            )

            from stockstock.db.models import PortfolioSnapshot
            rows = session.query(PortfolioSnapshot).all()
            assert len(rows) == 1  # 중복 삽입 아님
            assert rows[0].total_value_usd == 101_000.0

    def test_risk_event_logging(self, tmp_db):
        with tmp_db() as session:
            log_risk_event(
                session, "STOP_LOSS",
                symbol="AAPL",
                details={"entry_price": 150.0, "exit_price": 142.5},
            )

            from stockstock.db.models import RiskEvent
            events = session.query(RiskEvent).all()
            assert len(events) == 1
            assert events[0].event_type == "STOP_LOSS"
            assert events[0].symbol == "AAPL"
