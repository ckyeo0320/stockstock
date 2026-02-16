"""유틸리티 모듈.

마켓 캘린더, 타임존 헬퍼 등을 제공합니다.
"""

from __future__ import annotations

from datetime import date, datetime

import exchange_calendars as xcals
import pytz

ET = pytz.timezone("US/Eastern")
KST = pytz.timezone("Asia/Seoul")
UTC = pytz.UTC


def get_nyse_calendar() -> xcals.ExchangeCalendar:
    """NYSE 캘린더를 반환합니다."""
    return xcals.get_calendar("XNYS")


def is_market_open() -> bool:
    """현재 NYSE 마켓이 열려있는지 확인합니다."""
    now_et = datetime.now(ET)
    cal = get_nyse_calendar()

    try:
        if not cal.is_session(now_et.date()):
            return False
    except ValueError:
        return False

    # exchange-calendars는 tz-naive timestamp를 기대
    now_naive = now_et.replace(tzinfo=None)
    try:
        return cal.is_open_on_minute(now_naive)
    except ValueError:
        return False


def is_trading_day(d: date | None = None) -> bool:
    """주어진 날짜가 NYSE 거래일인지 확인합니다."""
    if d is None:
        d = datetime.now(ET).date()
    cal = get_nyse_calendar()
    try:
        return cal.is_session(d)
    except ValueError:
        return False


def now_et() -> datetime:
    """현재 미국 동부 시간을 반환합니다."""
    return datetime.now(ET)


def now_kst() -> datetime:
    """현재 한국 시간을 반환합니다."""
    return datetime.now(KST)


def now_utc() -> datetime:
    """현재 UTC 시간을 반환합니다."""
    return datetime.now(UTC)


def format_usd(amount: float) -> str:
    """달러 금액을 포맷팅합니다."""
    if amount >= 0:
        return f"${amount:,.2f}"
    return f"-${abs(amount):,.2f}"


def format_pct(value: float) -> str:
    """퍼센트를 포맷팅합니다."""
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"
