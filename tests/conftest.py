"""테스트 공통 fixture."""

import os
import tempfile

import pandas as pd
import pytest

from stockstock.db.models import init_db


@pytest.fixture
def tmp_db():
    """임시 SQLite DB 세션 팩토리를 제공합니다."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    session_factory = init_db(db_path)
    yield session_factory

    os.unlink(db_path)


@pytest.fixture
def db_session(tmp_db):
    """DB 세션을 제공합니다."""
    session = tmp_db()
    yield session
    session.close()


@pytest.fixture
def sample_ohlcv_df():
    """테스트용 OHLCV DataFrame을 제공합니다."""
    import numpy as np

    np.random.seed(42)
    n = 300
    dates = pd.bdate_range(end="2025-12-31", periods=n)
    base_price = 150.0
    prices = base_price + np.cumsum(np.random.randn(n) * 2)

    df = pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": prices + np.random.randn(n) * 0.5,
        "high": prices + abs(np.random.randn(n)) * 2,
        "low": prices - abs(np.random.randn(n)) * 2,
        "close": prices,
        "volume": np.random.randint(1_000_000, 10_000_000, n),
    })

    return df
