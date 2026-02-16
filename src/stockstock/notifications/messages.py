"""Telegram 메시지 포맷팅 모듈."""

from __future__ import annotations

from stockstock.strategy.signals import TradingSignal
from stockstock.utils import format_pct, format_usd


def format_trade_alert(
    signal: TradingSignal,
    quantity: int,
    price: float,
    order_type: str,
    is_paper: bool,
) -> str:
    """매매 체결 알림 메시지를 생성합니다."""
    mode = "[모의투자]" if is_paper else "[실전투자]"
    emoji_map = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪"}
    emoji = emoji_map.get(signal.signal.value, "⚪")

    total = price * quantity
    return (
        f"{mode} {emoji} {signal.signal.value} 체결\n"
        f"━━━━━━━━━━━━━━━\n"
        f"종목: {signal.symbol}\n"
        f"방향: {signal.signal.value}\n"
        f"수량: {quantity}주\n"
        f"가격: {format_usd(price)}\n"
        f"총액: {format_usd(total)}\n"
        f"주문유형: {order_type}\n"
        f"확신도: {signal.confidence:.1%}\n"
        f"사유: {signal.reason}"
    )


def format_signal_alert(signal: TradingSignal, current_price: float) -> str:
    """시그널 생성 알림 메시지를 생성합니다."""
    emoji_map = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪"}
    emoji = emoji_map.get(signal.signal.value, "⚪")

    return (
        f"{emoji} 시그널: {signal.symbol}\n"
        f"방향: {signal.signal.value} | 확신도: {signal.confidence:.1%}\n"
        f"현재가: {format_usd(current_price)}\n"
        f"사유: {signal.reason}"
    )


def format_portfolio_summary(
    holdings: list[dict],
    total_value: float,
    cash: float,
    daily_pnl: float | None = None,
) -> str:
    """포트폴리오 요약 메시지를 생성합니다."""
    lines = ["📊 포트폴리오 현황", "━━━━━━━━━━━━━━━"]
    lines.append(f"총 자산: {format_usd(total_value)}")
    lines.append(f"현금(USD): {format_usd(cash)}")

    if daily_pnl is not None:
        pnl_emoji = "📈" if daily_pnl >= 0 else "📉"
        lines.append(f"금일 손익: {pnl_emoji} {format_usd(daily_pnl)}")

    if holdings:
        lines.append("\n📋 보유 종목:")
        for h in holdings:
            pnl_str = format_pct(h.get("profit_rate", 0))
            lines.append(
                f"  {h['symbol']}: {h.get('quantity', 0)}주 "
                f"| {format_usd(h.get('current_price', 0))} "
                f"| P&L: {pnl_str}"
            )
    else:
        lines.append("\n보유 종목이 없습니다.")

    return "\n".join(lines)


def format_daily_summary(
    date_str: str,
    total_value: float,
    daily_pnl: float,
    trades_today: int,
    signals_today: list[dict],
) -> str:
    """일일 마감 요약 메시지를 생성합니다."""
    pnl_emoji = "📈" if daily_pnl >= 0 else "📉"

    lines = [
        f"📋 일일 마감 요약 ({date_str})",
        "━━━━━━━━━━━━━━━",
        f"총 자산: {format_usd(total_value)}",
        f"금일 손익: {pnl_emoji} {format_usd(daily_pnl)}",
        f"금일 거래: {trades_today}건",
    ]

    if signals_today:
        lines.append("\n🔔 금일 시그널:")
        for s in signals_today:
            lines.append(f"  {s['symbol']}: {s['signal']} ({s.get('confidence', 0):.1%})")

    return "\n".join(lines)


def format_error_alert(error_type: str, message: str) -> str:
    """에러 알림 메시지를 생성합니다."""
    return f"⚠️ 오류 발생\n━━━━━━━━━━━━━━━\n유형: {error_type}\n내용: {message}"


def format_risk_alert(event_type: str, symbol: str | None, details: str) -> str:
    """리스크 이벤트 알림 메시지를 생성합니다."""
    lines = ["🛑 리스크 알림", "━━━━━━━━━━━━━━━", f"유형: {event_type}"]
    if symbol:
        lines.append(f"종목: {symbol}")
    lines.append(f"내용: {details}")
    return "\n".join(lines)


def format_status(
    mode: str,
    is_active: bool,
    last_run: str | None,
    next_run: str | None,
    symbols: list[str],
) -> str:
    """시스템 상태 메시지를 생성합니다."""
    status = "🟢 활성" if is_active else "🔴 비활성"
    mode_str = "모의투자" if mode == "paper" else "실전투자"

    lines = [
        "⚙️ 시스템 상태",
        "━━━━━━━━━━━━━━━",
        f"모드: {mode_str}",
        f"상태: {status}",
        f"마지막 실행: {last_run or '없음'}",
        f"다음 실행: {next_run or '미정'}",
        f"추적 종목: {', '.join(symbols)}",
    ]
    return "\n".join(lines)
