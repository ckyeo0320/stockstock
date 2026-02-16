"""과거 OHLCV 데이터를 다운로드하여 DB에 저장하는 스크립트.

사용법: python scripts/seed_historical.py
"""

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from stockstock.broker.client import BrokerClient
from stockstock.broker.market_data import fetch_daily_ohlcv
from stockstock.config import AppConfig
from stockstock.db.models import init_db
from stockstock.db.repository import upsert_ohlcv
from stockstock.logging_config import setup_logging


def main() -> None:
    config = AppConfig()
    setup_logging(level="INFO")

    session_factory = init_db(str(config.db_path))
    broker = BrokerClient(config.broker, config.trading)

    for symbol in config.trading.symbols:
        print(f"[*] {symbol} 과거 데이터 다운로드 중...")
        try:
            df = fetch_daily_ohlcv(broker, symbol, days=config.model.lookback_days)
            with session_factory() as session:
                inserted = upsert_ohlcv(session, symbol, df)
            print(f"    {symbol}: {len(df)}행 조회, {inserted}행 신규 삽입")
        except Exception as e:
            print(f"    {symbol}: 오류 - {e}")

    print("[*] 완료!")


if __name__ == "__main__":
    main()
