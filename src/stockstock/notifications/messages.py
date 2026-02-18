"""Telegram 메시지 포맷팅 모듈."""

from __future__ import annotations

from typing import TYPE_CHECKING

from stockstock.strategy.signals import TradingSignal
from stockstock.utils import format_pct, format_usd

if TYPE_CHECKING:
    from stockstock.macro.macro_score import MacroReport
    from stockstock.macro.sector_rotation import SectorRank


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


def format_macro_report(
    date_str: str,
    report: MacroReport,
    rankings: list[SectorRank],
    rebalance_actions: list[str] | None = None,
) -> str:
    """거시경제 분석 리포트 메시지를 생성합니다."""
    # 점수 부호
    sign = "+" if report.score >= 0 else ""

    lines = [
        f"📊 거시경제 리포트 ({date_str})",
        "",
        f"■ 매크로 점수: {sign}{report.score:.2f} ({report.label})",
        f"  → 주식 비중: {report.equity_pct}%",
    ]

    # 금리 환경
    lines.append("")
    lines.append("■ 금리 환경")
    if report.yield_spread is not None:
        arrow = "▲" if (report.yield_spread_change or 0) >= 0 else "▼"
        change_str = f"{abs(report.yield_spread_change or 0):.2f}"
        lines.append(f"  2-10Y 스프레드: {report.yield_spread:.2f}% ({arrow}{change_str})")
    if report.high_yield_spread is not None:
        lines.append(f"  하이일드 스프레드: {report.high_yield_spread:.2f}%")
    if report.fed_funds_rate is not None:
        lines.append(f"  연방기금금리: {report.fed_funds_rate:.2f}%")

    # 변동성
    if report.vix is not None:
        lines.append("")
        lines.append("■ 시장 변동성")
        pctile_str = (
            f" (60일 백분위: {report.vix_percentile:.0f}%)"
            if report.vix_percentile else ""
        )
        lines.append(f"  VIX: {report.vix:.1f}{pctile_str}")

    # 원자재/환율
    has_commodity = any([
        report.copper_gold_ratio_change, report.dxy_change, report.oil_price,
    ])
    if has_commodity:
        lines.append("")
        lines.append("■ 원자재/환율")
        if report.copper_gold_ratio_change is not None:
            arrow = "▲" if report.copper_gold_ratio_change >= 0 else "▼"
            signal = "경기 확장 신호" if report.copper_gold_ratio_change > 0 else "경기 수축 신호"
            lines.append(
                f"  구리/금 비율: {arrow}{abs(report.copper_gold_ratio_change):.1%} ({signal})"
            )
        if report.dxy_change is not None:
            arrow = "▲" if report.dxy_change >= 0 else "▼"
            lines.append(f"  달러 인덱스: {arrow}{abs(report.dxy_change):.1%} (20일)")
        if report.oil_price is not None:
            lines.append(f"  원유 WTI: ${report.oil_price:.2f}")

    # 섹터 순위
    if rankings:
        lines.append("")
        lines.append(f"■ 섹터 순위 (상위 {min(3, len(rankings))} → 매수)")
        for r in rankings:
            marker = "  " if r.rank <= 3 else "  "
            mom_str = format_pct(r.momentum_20d * 100)
            rs_str = f"RS {r.relative_strength:.2f}"
            lines.append(
                f"{marker}{r.rank}. {r.etf_ticker} ({r.sector})"
                f" {mom_str} | {rs_str}"
            )
            if r.rank == 3 and len(rankings) > 3:
                lines.append("  ---")

    # 리밸런싱
    if rebalance_actions:
        lines.append("")
        lines.append("■ 리밸런싱")
        for action in rebalance_actions:
            lines.append(f"  {action}")

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
