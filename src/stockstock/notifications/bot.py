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
        self._app.add_handler(CommandHandler("ping", self._cmd_ping))

        self._loop.run_until_complete(self._app.run_polling(allowed_updates=Update.ALL_TYPES))

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

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        cb = self._callbacks.get("start")
        if callable(cb):
            cb()
        await update.message.reply_text("🟢 자동매매를 시작합니다.")  # type: ignore[union-attr]

    async def _cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        cb = self._callbacks.get("stop")
        if callable(cb):
            cb()
        await update.message.reply_text("🔴 자동매매를 중지합니다.")  # type: ignore[union-attr]

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        cb = self._callbacks.get("status")
        msg = cb() if callable(cb) else "상태 정보를 가져올 수 없습니다."
        await update.message.reply_text(msg)  # type: ignore[union-attr]

    async def _cmd_portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        cb = self._callbacks.get("portfolio")
        msg = cb() if callable(cb) else "포트폴리오 정보를 가져올 수 없습니다."
        await update.message.reply_text(msg)  # type: ignore[union-attr]

    async def _cmd_pnl(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        cb = self._callbacks.get("pnl")
        msg = cb() if callable(cb) else "손익 정보를 가져올 수 없습니다."
        await update.message.reply_text(msg)  # type: ignore[union-attr]

    async def _cmd_trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        cb = self._callbacks.get("trades")
        msg = cb() if callable(cb) else "거래 내역을 가져올 수 없습니다."
        await update.message.reply_text(msg)  # type: ignore[union-attr]

    async def _cmd_signals(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        cb = self._callbacks.get("signals")
        msg = cb() if callable(cb) else "시그널 정보를 가져올 수 없습니다."
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
            asyncio.run_coroutine_threadsafe(self._app.stop(), self._loop)
        log.info("telegram_bot_stopped")
