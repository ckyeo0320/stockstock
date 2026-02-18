"""애플리케이션 오케스트레이터.

설정, 브로커, 전략, 스케줄러, 알림을 통합하여 트레이딩 루프를 실행합니다.
매크로 분석 + 섹터 로테이션 기반 일일 리밸런싱을 수행합니다.
"""

from __future__ import annotations

import signal
import sys
import threading
import time

from stockstock.broker.account import AccountBalance, fetch_balance
from stockstock.broker.client import BrokerClient
from stockstock.broker.market_data import fetch_daily_ohlcv, fetch_quote
from stockstock.broker.orders import place_buy_order, place_sell_order
from stockstock.config import AppConfig
from stockstock.db.models import init_db
from stockstock.db.repository import (
    get_recent_trades,
    get_system_state,
    log_risk_event,
    log_signal,
    log_trade,
    save_portfolio_snapshot,
    set_system_state,
    update_trade_status,
)
from stockstock.logging_config import get_logger, setup_logging
from stockstock.macro.fred_client import FredClient
from stockstock.macro.macro_score import MacroReport, compute_macro_score
from stockstock.macro.market_data import fetch_and_cache_market_data
from stockstock.macro.sector_rotation import (
    SECTOR_ETFS,
    SectorRank,
    compute_sector_rankings,
    save_sector_snapshot,
)
from stockstock.notifications.bot import TelegramBot
from stockstock.notifications.messages import (
    format_daily_summary,
    format_error_alert,
    format_macro_report,
    format_portfolio_summary,
    format_risk_alert,
    format_status,
    format_trade_alert,
)
from stockstock.scheduler.jobs import TradingScheduler
from stockstock.strategy.features import compute_features
from stockstock.strategy.model import LGBMTradingModel
from stockstock.strategy.risk import check_stop_loss, evaluate_signal
from stockstock.strategy.signals import SignalType, TradingSignal, generate_signal
from stockstock.utils import is_market_open, now_et

log = get_logger(__name__)


class StockStockApp:
    """메인 애플리케이션."""

    def __init__(self) -> None:
        # 설정 로드
        self.config = AppConfig()

        # 로깅 초기화
        setup_logging(
            level=self.config.logging.level,
            log_file=self.config.logging.file,
            max_bytes=self.config.logging.max_bytes,
            backup_count=self.config.logging.backup_count,
        )

        log.info(
            "app_initializing",
            mode=self.config.trading.mode,
            symbols=self.config.trading.symbols,
            macro_enabled=self.config.macro.enabled,
        )

        # DB 초기화
        self._session_factory = init_db(str(self.config.db_path))

        # 브로커 클라이언트
        self._broker = BrokerClient(self.config.broker, self.config.trading)

        # ML 모델
        self._model = LGBMTradingModel()
        self._load_model()

        # 매크로 분석 클라이언트
        self._fred_client: FredClient | None = None
        if self.config.macro.enabled:
            fred_key = self.config.fred.api_key.get_secret_value()
            if fred_key:
                self._fred_client = FredClient(fred_key, self._session_factory)
                log.info("fred_client_initialized")
            else:
                log.warning("fred_api_key_missing", message="FRED 데이터 수집이 비활성화됩니다.")

        # 최근 매크로 리포트 캐시
        self._last_macro_report: MacroReport | None = None
        self._last_sector_rankings: list[SectorRank] = []

        # Telegram 봇
        self._bot = TelegramBot(self.config.telegram)
        self._setup_bot_callbacks()

        # 스케줄러
        self._scheduler = TradingScheduler(
            interval_minutes=self.config.trading.check_interval_minutes
        )
        self._scheduler.set_trading_job(self._trading_loop)
        self._scheduler.set_daily_summary_job(
            self._daily_summary, hour=self.config.telegram.daily_summary_hour
        )

        # 일일 손실 추적 (스레드 안전)
        self._daily_loss_lock = threading.Lock()
        self._daily_loss_usd = 0.0
        self._daily_loss_date: str | None = None

        log.info("app_initialized")

    def _load_model(self) -> None:
        """ML 모델을 로드합니다."""
        try:
            self._model.load(self.config.model.artifact_path)
            log.info("model_loaded", path=self.config.model.artifact_path)
        except Exception:
            log.warning(
                "model_not_found",
                path=self.config.model.artifact_path,
                message="모델 학습이 필요합니다. scripts/train_model.py를 실행하세요.",
            )

    def _setup_bot_callbacks(self) -> None:
        """Telegram 봇 명령어 콜백을 등록합니다."""
        self._bot.register_callback("start", self._on_start)
        self._bot.register_callback("stop", self._on_stop)
        self._bot.register_callback("status", self._on_status)
        self._bot.register_callback("portfolio", self._on_portfolio)
        self._bot.register_callback("pnl", self._on_pnl)
        self._bot.register_callback("trades", self._on_trades)
        self._bot.register_callback("macro", self._on_macro)

    def _on_start(self) -> None:
        self._scheduler.resume_trading()
        with self._session_factory() as session:
            set_system_state(session, "trading_active", "true")

    def _on_stop(self) -> None:
        self._scheduler.pause_trading()
        with self._session_factory() as session:
            set_system_state(session, "trading_active", "false")

    def _on_status(self) -> str:
        with self._session_factory() as session:
            is_active = get_system_state(session, "trading_active") != "false"
            last_run = get_system_state(session, "last_run_time")
        # 매크로 활성 시 섹터 ETF 목록, 아니면 개별 종목 목록
        if self.config.macro.enabled:
            symbols = self.config.macro.sector_etfs
        else:
            symbols = self.config.trading.symbols
        return format_status(
            mode=self.config.trading.mode,
            is_active=is_active,
            last_run=last_run,
            next_run=self._scheduler.get_next_run_time(),
            symbols=symbols,
        )

    def _on_portfolio(self) -> str:
        try:
            balance = fetch_balance(self._broker)
            holdings = [
                {
                    "symbol": h.symbol,
                    "quantity": h.quantity,
                    "current_price": float(h.current_price),
                    "profit_rate": h.profit_rate,
                }
                for h in balance.holdings
            ]
            return format_portfolio_summary(
                holdings=holdings,
                total_value=float(balance.total_value_krw),
                cash=float(balance.cash_usd or 0),
            )
        except Exception as e:
            log.error("portfolio_fetch_failed", error=str(e))
            return "포트폴리오 조회 중 오류가 발생했습니다."

    def _on_pnl(self) -> str:
        with self._session_factory() as session:
            trades = get_recent_trades(session, limit=20)
        if not trades:
            return "최근 거래 내역이 없습니다."

        # 매도 거래의 실현 손익 합산 (filled_price - requested_price는 슬리피지)
        # 실제 P&L은 포트폴리오 스냅샷에서 추적하는 것이 정확함
        sell_count = sum(1 for t in trades if t.side == "SELL" and t.filled_price)
        buy_count = sum(1 for t in trades if t.side == "BUY")
        return (
            f"📊 최근 거래 요약\n"
            f"매수: {buy_count}건 | 매도: {sell_count}건\n"
            f"(정확한 P&L은 /portfolio 명령어를 사용하세요)"
        )

    def _on_trades(self) -> str:
        with self._session_factory() as session:
            trades = get_recent_trades(session, limit=10)
        if not trades:
            return "최근 거래 내역이 없습니다."

        lines = ["📋 최근 거래 내역", "━━━━━━━━━━━━━━━"]
        for t in trades:
            status_emoji = "✅" if t.status == "FILLED" else "⏳"
            lines.append(
                f"{status_emoji} {t.side} {t.symbol} {t.quantity}주 "
                f"| {t.status} | {str(t.submitted_at)[:16]}"
            )
        return "\n".join(lines)

    def _on_macro(self) -> str:
        """최근 매크로 분석 결과를 반환합니다."""
        if not self.config.macro.enabled:
            return "매크로 분석이 비활성화 상태입니다."
        if self._last_macro_report is None:
            return "매크로 분석 데이터가 아직 없습니다. 다음 트레이딩 루프 실행 후 확인하세요."
        today = now_et().strftime("%Y-%m-%d")
        return format_macro_report(
            date_str=today,
            report=self._last_macro_report,
            rankings=self._last_sector_rankings,
        )

    def _collect_macro_data(self) -> None:
        """FRED + Yahoo Finance 매크로 데이터를 수집하고 DB에 캐싱합니다."""
        log.info("macro_data_collection_started")

        # FRED 데이터 수집
        if self._fred_client:
            self._fred_client.fetch_and_cache(self.config.macro.fred_series)

        # Yahoo Finance 시장 데이터 수집 (VIX, 원자재, 환율)
        commodity_tickers = {t: t for t in self.config.macro.commodities}
        commodity_tickers["vix"] = "^VIX"
        fetch_and_cache_market_data(self._session_factory, commodity_tickers)

        log.info("macro_data_collection_completed")

    def _run_macro_analysis(self) -> tuple[MacroReport, list[SectorRank]]:
        """매크로 점수 계산 + 섹터 순위 산출."""
        # 매크로 점수 계산
        report = compute_macro_score(self._session_factory)

        # 섹터 ETF → 한국어명 매핑 (config의 ETF 목록 기준)
        sector_etf_map = {
            sector: ticker
            for sector, ticker in SECTOR_ETFS.items()
            if ticker in self.config.macro.sector_etfs
        }

        # 섹터 순위 산출
        rankings = compute_sector_rankings(
            macro_signals=report.macro_signals,
            sector_etfs=sector_etf_map,
            top_n=self.config.macro.top_sectors,
        )

        # DB 저장
        today = now_et().strftime("%Y-%m-%d")
        save_sector_snapshot(self._session_factory, rankings, today)

        # 캐시 업데이트
        self._last_macro_report = report
        self._last_sector_rankings = rankings

        log.info(
            "macro_analysis_completed",
            score=report.score,
            label=report.label,
            top_sectors=[r.etf_ticker for r in rankings[:self.config.macro.top_sectors]],
        )
        return report, rankings

    def _compute_rebalance_actions(
        self, balance: AccountBalance, top_etfs: list[str],
    ) -> list[dict]:
        """리밸런싱 액션(매수/매도)을 계산합니다.

        Returns:
            [{"symbol": "XLK", "action": "BUY"|"SELL", "quantity": int, "price": float}, ...]
        """
        actions: list[dict] = []

        # 현재 보유 ETF 목록
        held_symbols = {h.symbol: h for h in balance.holdings}
        all_sector_etfs = set(self.config.macro.sector_etfs)

        # 1. 보유 중이지만 상위 섹터에서 빠진 ETF → 매도
        for symbol, holding in held_symbols.items():
            if symbol in all_sector_etfs and symbol not in top_etfs:
                qty = holding.orderable_quantity
                if qty > 0:
                    quote = fetch_quote(self._broker, symbol)
                    actions.append({
                        "symbol": symbol,
                        "action": "SELL",
                        "quantity": qty,
                        "price": float(quote.price),
                    })

        # 2. 상위 섹터 ETF 중 미보유 → 매수 (균등 배분)
        total_value = float(balance.total_value_krw)
        cash = float(balance.cash_usd or 0)
        # 매도 후 예상 현금 추가
        sell_proceeds = sum(
            a["price"] * a["quantity"] for a in actions if a["action"] == "SELL"
        )
        available_cash = cash + sell_proceeds

        # 상위 N개 ETF에 균등 배분
        target_per_etf = (total_value * self.config.trading.max_position_pct)

        for symbol in top_etfs:
            if symbol in held_symbols:
                # 이미 보유 중이면 추가 매수 없음 (비중 조절은 향후 개선)
                continue
            if available_cash < 100:
                break

            quote = fetch_quote(self._broker, symbol)
            price = float(quote.price)
            if price <= 0:
                continue

            buy_amount = min(target_per_etf, available_cash)
            qty = int(buy_amount / price)
            if qty > 0:
                actions.append({
                    "symbol": symbol,
                    "action": "BUY",
                    "quantity": qty,
                    "price": price,
                })
                available_cash -= price * qty

        return actions

    def _execute_rebalance(self, actions: list[dict]) -> list[str]:
        """리밸런싱 주문을 실행합니다. 매도 먼저, 매수는 그 다음."""
        summaries: list[str] = []

        # 매도 먼저
        sell_actions = [a for a in actions if a["action"] == "SELL"]
        buy_actions = [a for a in actions if a["action"] == "BUY"]

        for action in sell_actions + buy_actions:
            symbol = action["symbol"]
            qty = action["quantity"]
            price = action["price"]
            side = action["action"]

            try:
                if side == "SELL":
                    place_sell_order(self._broker, symbol, qty)
                else:
                    place_buy_order(self._broker, symbol, qty)

                with self._session_factory() as session:
                    log_trade(
                        session,
                        symbol=symbol,
                        side=side,
                        quantity=qty,
                        order_type="MARKET",
                        requested_price=price,
                        status="SUBMITTED",
                        notes="REBALANCE",
                    )

                emoji = "🔴" if side == "SELL" else "🟢"
                summaries.append(f"{emoji} {side} {symbol} {qty}주 @ ${price:.2f}")
                log.info("rebalance_order", side=side, symbol=symbol, quantity=qty)

            except Exception as e:
                log.error("rebalance_order_failed", symbol=symbol, side=side, error=str(e))
                summaries.append(f"⚠️ {side} {symbol} 실패")

        return summaries

    def _reset_daily_loss_if_needed(self) -> None:
        """날짜가 바뀌면 일일 손실을 초기화합니다."""
        today = now_et().strftime("%Y-%m-%d")
        with self._daily_loss_lock:
            if self._daily_loss_date != today:
                self._daily_loss_usd = 0.0
                self._daily_loss_date = today

    def _trading_loop(self) -> None:
        """트레이딩 루프 (매크로 활성 시 섹터 로테이션, 아니면 기존 개별 종목 처리)."""
        try:
            # 마켓 오픈 체크
            if not is_market_open():
                log.info("market_closed_skipping")
                return

            # 매매 중단 상태 체크
            with self._session_factory() as session:
                if get_system_state(session, "trading_active") == "false":
                    log.info("trading_paused_skipping")
                    return

            self._reset_daily_loss_if_needed()

            if self.config.macro.enabled:
                self._macro_trading_loop()
            else:
                self._symbol_trading_loop()

            # 마지막 실행 시간 기록
            with self._session_factory() as session:
                set_system_state(session, "last_run_time", now_et().isoformat())

            log.info("trading_loop_completed")

        except Exception as e:
            log.error("trading_loop_error", error=str(e), exc_info=True)
            self._bot.send_message(
                format_error_alert("트레이딩 루프 오류", "내부 오류 발생. 로그를 확인하세요.")
            )

    def _macro_trading_loop(self) -> None:
        """매크로 분석 + 섹터 ETF 로테이션 기반 트레이딩."""
        log.info("macro_trading_loop_started")

        # 1. 매크로 데이터 수집
        self._collect_macro_data()

        # 2. 매크로 분석 + 섹터 순위 산출
        report, rankings = self._run_macro_analysis()

        # 3. 상위 N개 섹터 ETF 선정
        top_n = self.config.macro.top_sectors
        top_etfs = [r.etf_ticker for r in rankings[:top_n]]
        log.info("top_sector_etfs", etfs=top_etfs, equity_pct=report.equity_pct)

        # 4. 잔고 조회
        balance = fetch_balance(self._broker)

        # 5. 보유 ETF 손절 체크
        all_sector_etfs = set(self.config.macro.sector_etfs)
        for holding in balance.holdings:
            if holding.symbol in all_sector_etfs:
                quote = fetch_quote(self._broker, holding.symbol)
                current_price = float(quote.price)
                purchase_price = float(holding.purchase_price)
                if check_stop_loss(
                    symbol=holding.symbol,
                    current_price=current_price,
                    purchase_price=purchase_price,
                    stop_loss_pct=self.config.trading.stop_loss_pct,
                ):
                    qty = holding.orderable_quantity
                    loss = (purchase_price - current_price) * qty
                    self._execute_stop_loss(holding.symbol, qty, current_price)
                    with self._daily_loss_lock:
                        self._daily_loss_usd += max(0, loss)

        # 6. 리밸런싱 (잔고 다시 조회 — 손절 후 변동 반영)
        balance = fetch_balance(self._broker)
        actions = self._compute_rebalance_actions(balance, top_etfs)

        rebalance_summaries: list[str] = []
        if actions:
            rebalance_summaries = self._execute_rebalance(actions)
        else:
            log.info("no_rebalance_needed")

        # 7. 매크로 리포트 Telegram 전송
        today = now_et().strftime("%Y-%m-%d")
        msg = format_macro_report(
            date_str=today,
            report=report,
            rankings=rankings,
            rebalance_actions=rebalance_summaries if rebalance_summaries else None,
        )
        self._bot.send_message(msg)

        log.info("macro_trading_loop_completed", rebalance_count=len(actions))

    def _symbol_trading_loop(self) -> None:
        """기존 개별 종목 기반 트레이딩 루프 (매크로 비활성 시)."""
        # 모델 로드 확인
        if not self._model.is_loaded:
            log.warning("model_not_loaded_skipping")
            return

        log.info("symbol_trading_loop_started", symbols=self.config.trading.symbols)

        # 잔고 조회
        balance = fetch_balance(self._broker)

        # 기존 보유 종목 손절 체크
        for holding in balance.holdings:
            if holding.symbol in self.config.trading.symbols:
                quote = fetch_quote(self._broker, holding.symbol)
                current_price = float(quote.price)
                purchase_price = float(holding.purchase_price)
                if check_stop_loss(
                    symbol=holding.symbol,
                    current_price=current_price,
                    purchase_price=purchase_price,
                    stop_loss_pct=self.config.trading.stop_loss_pct,
                ):
                    qty = holding.orderable_quantity
                    loss = (purchase_price - current_price) * qty
                    self._execute_stop_loss(holding.symbol, qty, current_price)
                    with self._daily_loss_lock:
                        self._daily_loss_usd += max(0, loss)

        # 각 종목에 대해 시그널 생성 및 실행
        for symbol in self.config.trading.symbols:
            try:
                self._process_symbol(symbol, balance)
            except Exception as e:
                log.error("symbol_processing_error", symbol=symbol, error=str(e))
                self._bot.send_message(
                    format_error_alert("종목 처리 오류", f"{symbol} 처리 중 오류 발생")
                )

    def _process_symbol(self, symbol: str, balance: AccountBalance) -> None:
        """개별 종목을 처리합니다."""
        # 1. 데이터 조회
        df = fetch_daily_ohlcv(self._broker, symbol, days=self.config.model.lookback_days)
        if len(df) < 60:
            log.warning("insufficient_data", symbol=symbol, rows=len(df))
            return

        # 2. 피처 계산
        featured_df = compute_features(df)

        # 3. 예측
        prediction, confidence = self._model.predict(featured_df)

        # 4. 시그널 생성
        signal = generate_signal(
            symbol=symbol,
            prediction=prediction,
            confidence=confidence,
            confidence_threshold=self.config.model.confidence_threshold,
        )

        # 5. DB에 시그널 기록
        with self._session_factory() as session:
            signal_id = log_signal(
                session,
                symbol=symbol,
                signal=signal.signal.value,
                confidence=signal.confidence,
                model_version=LGBMTradingModel.VERSION,
            )

        # 6. 리스크 평가
        quote = fetch_quote(self._broker, symbol)

        with self._session_factory() as session:
            trading_halted = get_system_state(session, "trading_halted") == "true"

        decision = evaluate_signal(
            signal=signal,
            balance=balance,
            current_price=float(quote.price),
            max_position_pct=self.config.trading.max_position_pct,
            stop_loss_pct=self.config.trading.stop_loss_pct,
            max_daily_loss_usd=self.config.trading.max_daily_loss_usd,
            daily_loss_usd=self._daily_loss_usd,
            trading_halted=trading_halted,
        )

        if not decision.approved or decision.quantity == 0:
            log.info("signal_not_executed", symbol=symbol, reason=decision.reason)
            return

        # 7. 주문 실행
        self._execute_order(signal, decision.quantity, float(quote.price), signal_id)

    def _execute_order(
        self, signal: TradingSignal, quantity: int, price: float, signal_id: int
    ) -> None:
        """주문을 실행합니다."""
        order_type = self.config.trading.order_type
        limit_price = price if order_type == "LIMIT" else None

        try:
            if signal.signal == SignalType.BUY:
                result = place_buy_order(
                    self._broker, signal.symbol, quantity, limit_price
                )
            else:
                result = place_sell_order(
                    self._broker, signal.symbol, quantity, limit_price
                )

            # DB에 거래 기록
            with self._session_factory() as session:
                trade_id = log_trade(
                    session,
                    symbol=signal.symbol,
                    side=signal.signal.value,
                    quantity=quantity,
                    order_type=order_type,
                    requested_price=price,
                    status="SUBMITTED",
                    signal_id=signal_id,
                )

                # 주문 완료 시 상태 업데이트
                if not result.pending:
                    update_trade_status(session, trade_id, "FILLED", price, quantity)

            # Telegram 알림
            msg = format_trade_alert(
                signal=signal,
                quantity=quantity,
                price=price,
                order_type=order_type,
                is_paper=self.config.is_paper_trading,
            )
            self._bot.send_message(msg)

        except Exception as e:
            log.error(
                "order_execution_failed",
                symbol=signal.symbol,
                side=signal.signal.value,
                error=str(e),
            )
            self._bot.send_message(
                format_error_alert(
                    "주문 실행 실패",
                    f"{signal.symbol} {signal.signal.value} 주문 실패",
                )
            )

    def _execute_stop_loss(
        self, symbol: str, quantity: int, current_price: float | None = None,
    ) -> None:
        """손절 매도를 실행합니다."""
        log.warning("executing_stop_loss", symbol=symbol, quantity=quantity)

        try:
            place_sell_order(self._broker, symbol, quantity)

            with self._session_factory() as session:
                log_trade(
                    session,
                    symbol=symbol,
                    side="SELL",
                    quantity=quantity,
                    order_type="MARKET",
                    requested_price=current_price,
                    status="SUBMITTED",
                    notes="STOP_LOSS",
                )
                log_risk_event(
                    session,
                    event_type="STOP_LOSS",
                    symbol=symbol,
                    details={"quantity": quantity},
                )

            self._bot.send_message(
                format_risk_alert("STOP_LOSS", symbol, f"{quantity}주 손절 매도 실행")
            )

        except Exception as e:
            log.error("stop_loss_failed", symbol=symbol, error=str(e))
            self._bot.send_message(
                format_error_alert("손절 매도 실패", f"{symbol} 손절 주문 실패. 로그를 확인하세요.")
            )

    def _daily_summary(self) -> None:
        """일일 마감 요약을 전송합니다."""
        try:
            balance = fetch_balance(self._broker)
            today = now_et().strftime("%Y-%m-%d")

            holdings = [
                {
                    "symbol": h.symbol,
                    "quantity": h.quantity,
                    "value": float(h.current_amount),
                }
                for h in balance.holdings
            ]

            with self._session_factory() as session:
                save_portfolio_snapshot(
                    session,
                    snapshot_date=today,
                    total_value_usd=float(balance.total_value_krw),
                    cash_usd=float(balance.cash_usd or 0),
                    holdings=holdings,
                    daily_pnl_usd=self._daily_loss_usd * -1,
                )

                today_trades = get_recent_trades(session, limit=50)
                trades_today = sum(
                    1 for t in today_trades if str(t.submitted_at)[:10] == today
                )

            msg = format_daily_summary(
                date_str=today,
                total_value=float(balance.total_value_krw),
                daily_pnl=-self._daily_loss_usd,
                trades_today=trades_today,
                signals_today=[],
            )
            self._bot.send_message(msg)

        except Exception as e:
            log.error("daily_summary_error", error=str(e))

    def run(self) -> None:
        """애플리케이션을 시작합니다."""
        log.info("app_starting", mode=self.config.trading.mode)

        # 시그널 핸들러 등록
        signal.signal(signal.SIGINT, self._shutdown_handler)
        signal.signal(signal.SIGTERM, self._shutdown_handler)

        # 시스템 상태 초기화
        with self._session_factory() as session:
            set_system_state(session, "trading_active", "true")

        # Telegram 봇 시작
        self._bot.start()

        # 시작 알림
        mode_str = "모의투자" if self.config.is_paper_trading else "실전투자"
        if self.config.macro.enabled:
            etfs = ", ".join(self.config.macro.sector_etfs)
            self._bot.send_message(
                f"🚀 StockStock 시작됨 (섹터 로테이션)\n"
                f"모드: {mode_str}\n"
                f"섹터 ETF: {etfs}\n"
                f"상위 {self.config.macro.top_sectors}개 섹터 투자\n"
                f"리밸런싱: {self.config.macro.rebalance_frequency}"
            )
        else:
            self._bot.send_message(
                f"🚀 StockStock 시작됨\n"
                f"모드: {mode_str}\n"
                f"추적 종목: {', '.join(self.config.trading.symbols)}\n"
                f"체크 간격: {self.config.trading.check_interval_minutes}분"
            )

        # 스케줄러 시작
        self._scheduler.start()

        # 첫 실행
        self._trading_loop()

        # 메인 루프 (스케줄러가 백그라운드에서 동작)
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            self.shutdown()

    def shutdown(self) -> None:
        """애플리케이션을 종료합니다."""
        log.info("app_shutting_down")
        self._bot.send_message("⏹️ StockStock이 종료됩니다.")
        self._scheduler.shutdown()
        self._bot.stop()
        log.info("app_stopped")

    def _shutdown_handler(self, signum, frame) -> None:
        """시그널 핸들러."""
        log.info("shutdown_signal_received", signal=signum)
        self.shutdown()
        sys.exit(0)
