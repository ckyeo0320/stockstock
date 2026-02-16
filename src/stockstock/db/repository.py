"""데이터베이스 CRUD 연산 모듈."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy.orm import Session

from stockstock.db.models import OHLCV, PortfolioSnapshot, RiskEvent, Signal, SystemState, Trade


def upsert_ohlcv(session: Session, symbol: str, df: pd.DataFrame, timeframe: str = "daily") -> int:
    """OHLCV 데이터를 upsert합니다. 삽입된 행 수를 반환합니다."""
    inserted = 0
    for _, row in df.iterrows():
        dt_str = str(row["date"])[:10]
        existing = (
            session.query(OHLCV)
            .filter_by(symbol=symbol, dt=dt_str, timeframe=timeframe)
            .first()
        )
        if existing:
            existing.open = float(row["open"])
            existing.high = float(row["high"])
            existing.low = float(row["low"])
            existing.close = float(row["close"])
            existing.volume = int(row["volume"])
            existing.fetched_at = datetime.now(UTC)
        else:
            session.add(
                OHLCV(
                    symbol=symbol,
                    dt=dt_str,
                    timeframe=timeframe,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"]),
                )
            )
            inserted += 1
    session.commit()
    return inserted


def get_ohlcv(
    session: Session, symbol: str, timeframe: str = "daily", limit: int = 252
) -> pd.DataFrame:
    """DB에서 OHLCV 데이터를 DataFrame으로 반환합니다."""
    rows = (
        session.query(OHLCV)
        .filter_by(symbol=symbol, timeframe=timeframe)
        .order_by(OHLCV.dt.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

    data = [
        {
            "date": r.dt,
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "volume": r.volume,
        }
        for r in reversed(rows)
    ]
    return pd.DataFrame(data)


def log_signal(
    session: Session,
    symbol: str,
    signal: str,
    confidence: float | None = None,
    features: dict | None = None,
    model_version: str | None = None,
) -> int:
    """ML 시그널을 기록하고 ID를 반환합니다."""
    s = Signal(
        symbol=symbol,
        signal=signal,
        confidence=confidence,
        features=json.dumps(features) if features else None,
        model_version=model_version,
    )
    session.add(s)
    session.commit()
    return s.id  # type: ignore[return-value]


def log_trade(
    session: Session,
    symbol: str,
    side: str,
    quantity: int,
    order_type: str = "MARKET",
    requested_price: float | None = None,
    filled_price: float | None = None,
    filled_quantity: int | None = None,
    status: str = "PENDING",
    kis_order_id: str | None = None,
    signal_id: int | None = None,
    notes: str | None = None,
) -> int:
    """거래를 기록하고 ID를 반환합니다."""
    t = Trade(
        signal_id=signal_id,
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        requested_price=requested_price,
        filled_price=filled_price,
        filled_quantity=filled_quantity,
        status=status,
        kis_order_id=kis_order_id,
        notes=notes,
    )
    session.add(t)
    session.commit()
    return t.id  # type: ignore[return-value]


def update_trade_status(
    session: Session,
    trade_id: int,
    status: str,
    filled_price: float | None = None,
    filled_quantity: int | None = None,
) -> None:
    """거래 상태를 업데이트합니다."""
    trade = session.get(Trade, trade_id)
    if trade:
        trade.status = status
        if filled_price is not None:
            trade.filled_price = filled_price
        if filled_quantity is not None:
            trade.filled_quantity = filled_quantity
        if status == "FILLED":
            trade.filled_at = datetime.now(UTC)
        session.commit()


def get_recent_trades(session: Session, limit: int = 10, symbol: str | None = None) -> list[Trade]:
    """최근 거래 내역을 반환합니다."""
    query = session.query(Trade)
    if symbol:
        query = query.filter_by(symbol=symbol)
    return query.order_by(Trade.submitted_at.desc()).limit(limit).all()


def save_portfolio_snapshot(
    session: Session,
    snapshot_date: str,
    total_value_usd: float,
    cash_usd: float,
    holdings: list[dict],
    daily_pnl_usd: float | None = None,
    cumulative_pnl_usd: float | None = None,
) -> None:
    """포트폴리오 스냅샷을 저장합니다."""
    existing = session.query(PortfolioSnapshot).filter_by(snapshot_date=snapshot_date).first()
    if existing:
        existing.total_value_usd = total_value_usd
        existing.cash_usd = cash_usd
        existing.holdings = json.dumps(holdings)
        existing.daily_pnl_usd = daily_pnl_usd
        existing.cumulative_pnl_usd = cumulative_pnl_usd
    else:
        session.add(
            PortfolioSnapshot(
                snapshot_date=snapshot_date,
                total_value_usd=total_value_usd,
                cash_usd=cash_usd,
                holdings=json.dumps(holdings),
                daily_pnl_usd=daily_pnl_usd,
                cumulative_pnl_usd=cumulative_pnl_usd,
            )
        )
    session.commit()


def log_risk_event(
    session: Session, event_type: str, symbol: str | None = None, details: dict | None = None
) -> None:
    """리스크 이벤트를 기록합니다."""
    session.add(
        RiskEvent(
            event_type=event_type,
            symbol=symbol,
            details=json.dumps(details) if details else None,
        )
    )
    session.commit()


def get_system_state(session: Session, key: str) -> str | None:
    """시스템 상태 값을 조회합니다."""
    state = session.query(SystemState).filter_by(key=key).first()
    return state.value if state else None


def set_system_state(session: Session, key: str, value: str) -> None:
    """시스템 상태 값을 설정합니다."""
    state = session.query(SystemState).filter_by(key=key).first()
    if state:
        state.value = value
        state.updated_at = datetime.now(UTC)
    else:
        session.add(SystemState(key=key, value=value))
    session.commit()
