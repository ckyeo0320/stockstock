"""SQLAlchemy ORM 모델.

거래 내역, 시세 캐시, ML 시그널, 포트폴리오 스냅샷 등을 관리합니다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


class OHLCV(Base):
    """시세 캐시 (API 호출 절감 + 백테스팅 데이터)."""

    __tablename__ = "ohlcv"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)
    dt = Column(String(10), nullable=False)  # YYYY-MM-DD
    timeframe = Column(String(10), nullable=False, default="daily")
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Integer, nullable=False)
    fetched_at = Column(DateTime, default=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint("symbol", "dt", "timeframe", name="uq_ohlcv_symbol_dt_tf"),
        Index("idx_ohlcv_symbol_dt", "symbol", "dt"),
    )


class Signal(Base):
    """ML 모델이 생성한 매매 시그널."""

    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)
    generated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    signal = Column(String(4), nullable=False)  # BUY, SELL, HOLD
    confidence = Column(Float)
    features = Column(Text)  # JSON blob
    model_version = Column(String(50))

    __table_args__ = (Index("idx_signals_symbol_dt", "symbol", "generated_at"),)


class Trade(Base):
    """실행된 거래 내역 (감사 추적)."""

    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_id = Column(Integer, nullable=True)
    symbol = Column(String(20), nullable=False)
    side = Column(String(4), nullable=False)  # BUY, SELL
    order_type = Column(String(10), nullable=False, default="MARKET")
    quantity = Column(Integer, nullable=False)
    requested_price = Column(Float, nullable=True)
    filled_price = Column(Float, nullable=True)
    filled_quantity = Column(Integer, nullable=True)
    status = Column(String(10), nullable=False, default="PENDING")
    kis_order_id = Column(String(50), nullable=True)
    submitted_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    filled_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_trades_symbol", "symbol"),
        Index("idx_trades_status", "status"),
        Index("idx_trades_submitted", "submitted_at"),
    )


class PortfolioSnapshot(Base):
    """일일 포트폴리오 스냅샷."""

    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_date = Column(String(10), nullable=False, unique=True)  # YYYY-MM-DD
    total_value_usd = Column(Float, nullable=False)
    cash_usd = Column(Float, nullable=False)
    holdings = Column(Text, nullable=False)  # JSON
    daily_pnl_usd = Column(Float, nullable=True)
    cumulative_pnl_usd = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))


class RiskEvent(Base):
    """리스크 관리 이벤트 기록."""

    __tablename__ = "risk_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(30), nullable=False)  # STOP_LOSS, MAX_DAILY_LOSS, POSITION_LIMIT
    symbol = Column(String(20), nullable=True)
    details = Column(Text, nullable=True)  # JSON
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))


class SystemState(Base):
    """시스템 상태 키-밸류 저장소."""

    __tablename__ = "system_state"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC))


def create_db_engine(db_path: str, echo: bool = False):
    """SQLite 엔진을 생성합니다."""
    from sqlalchemy import event as sa_event

    engine = create_engine(
        f"sqlite:///{db_path}",
        echo=echo,
        connect_args={"timeout": 30},
    )

    # WAL 모드 활성화 (동시 읽기/쓰기 지원)
    @sa_event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    return engine


def init_db(db_path: str, echo: bool = False) -> sessionmaker[Session]:
    """데이터베이스를 초기화하고 세션 팩토리를 반환합니다."""
    engine = create_db_engine(db_path, echo=echo)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)
