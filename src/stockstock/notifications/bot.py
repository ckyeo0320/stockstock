"""Telegram 봇 모듈.

매매 알림 전송 및 명령어 인터페이스를 제공합니다.
"""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from stockstock.logging_config import get_logger

if TYPE_CHECKING:
    from stockstock.config import TelegramConfig

log = get_logger(__name__)


class TelegramBot:
    """Telegram 봇 클라이언트."""

    def __init__(self, config: TelegramConfig) -> None:
        self._config = config
        self._chat_id = config.chat_id
        self._app: Application | None = None  # type: ignore[type-arg]
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._callbacks: dict[str, object] = {}
        self._ready = threading.Event()

    def register_callback(self, command: str, callback: object) -> None:
        """명령어 콜백을 등록합니다."""
        self._callbacks[command] = callback

    def start(self) -> None:
        """봇을 별도 스레드에서 시작합니다."""
        if not self._config.enabled:
            log.info("telegram_bot_disabled")
            return

        self._thread = threading.Thread(target=self._run_bot, daemon=True)
        self._thread.start()
        # 봇이 준비될 때까지 최대 10초 대기
        self._ready.wait(timeout=10)
        log.info("telegram_bot_started")

    def _run_bot(self) -> None:
        """봇 이벤트 루프를 실행합니다."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        self._app = (
            Application.builder()
            .token(self._config.bot_token.get_secret_value())
            .build()
        )

        # 명령어 핸들러 등록
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("stop", self._cmd_stop))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("portfolio", self._cmd_portfolio))
        self._app.add_handler(CommandHandler("pnl", self._cmd_pnl))
        self._app.add_handler(CommandHandler("trades", self._cmd_trades))
        self._app.add_handler(CommandHandler("signals", self._cmd_signals))
        self._app.add_handler(CommandHandler("macro", self._cmd_macro))
        self._app.add_handler(CommandHandler("ping", self._cmd_ping))

        # 준비 완료 시그널
        self._ready.set()

        # run_polling()은 메인 스레드에서만 동작하므로,
        # 별도 스레드에서는 initialize + start + start_polling을 직접 호출
        self._loop.run_until_complete(self._start_polling_async())

    async def _start_polling_async(self) -> None:
        """비메인 스레드에서 안전하게 폴링을 시작합니다."""
        await self._app.initialize()  # type: ignore[union-attr]
        await self._app.start()  # type: ignore[union-attr]
        await self._app.updater.start_polling(  # type: ignore[union-attr]
            allowed_updates=Update.ALL_TYPES,
        )
        # 무한 대기 (스레드가 종료되지 않도록)
        self._stop_event = asyncio.Event()
        await self._stop_event.wait()

    def _is_authorized(self, update: Update) -> bool:
        """메시지 발신자가 인증된 사용자인지 확인합니다."""
        if update.effective_chat is None:
            return False
        authorized = str(update.effective_chat.id) == self._chat_id
        if not authorized:
            log.warning(
                "unauthorized_telegram_access",
                chat_id=str(update.effective_chat.id),
                username=getattr(update.effective_user, "username", None),
                command=update.message.text if update.message else None,
            )
        return authorized

    async def _run_callback(self, name: str) -> str | None:
        """동기 콜백을 스레드풀에서 실행합니다 (이벤트 루프 차단 방지)."""
        cb = self._callbacks.get(name)
        if callable(cb):
            try:
                result = await asyncio.to_thread(cb)
                return result
            except Exception:
                log.error("telegram_callback_error", command=name, exc_info=True)
                return "명령 처리 중 오류가 발생했습니다."
        return None

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        await self._run_callback("start")
        await update.message.reply_text("🟢 자동매매를 시작합니다.")  # type: ignore[union-attr]

    async def _cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        await self._run_callback("stop")
        await update.message.reply_text("🔴 자동매매를 중지합니다.")  # type: ignore[union-attr]

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        msg = await self._run_callback("status") or "상태 정보를 가져올 수 없습니다."
        await update.message.reply_text(msg)  # type: ignore[union-attr]

    async def _cmd_portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        msg = await self._run_callback("portfolio") or "포트폴리오 정보를 가져올 수 없습니다."
        await update.message.reply_text(msg)  # type: ignore[union-attr]

    async def _cmd_pnl(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        msg = await self._run_callback("pnl") or "손익 정보를 가져올 수 없습니다."
        await update.message.reply_text(msg)  # type: ignore[union-attr]

    async def _cmd_trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        msg = await self._run_callback("trades") or "거래 내역을 가져올 수 없습니다."
        await update.message.reply_text(msg)  # type: ignore[union-attr]

    async def _cmd_signals(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        msg = await self._run_callback("signals") or "시그널 정보를 가져올 수 없습니다."
        await update.message.reply_text(msg)  # type: ignore[union-attr]

    async def _cmd_macro(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        msg = await self._run_callback("macro") or "매크로 분석 정보를 가져올 수 없습니다."
        await update.message.reply_text(msg)  # type: ignore[union-attr]

    async def _cmd_ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        await update.message.reply_text("🏓 Pong! StockStock is alive.")  # type: ignore[union-attr]

    def send_message(self, text: str) -> None:
        """메시지를 전송합니다 (동기 호출용)."""
        if not self._config.enabled:
            return

        if self._loop is None or self._app is None:
            log.warning("telegram_not_ready", message_preview=text[:50])
            return

        asyncio.run_coroutine_threadsafe(
            self._app.bot.send_message(chat_id=self._chat_id, text=text),
            self._loop,
        )

    def stop(self) -> None:
        """봇을 중지합니다."""
        if self._app and self._loop:
            asyncio.run_coroutine_threadsafe(self._stop_async(), self._loop)
        log.info("telegram_bot_stopped")

    async def _stop_async(self) -> None:
        """비동기 종료 처리."""
        if self._app:
            if self._app.updater and self._app.updater.running:
                await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        if hasattr(self, "_stop_event"):
            self._stop_event.set()
