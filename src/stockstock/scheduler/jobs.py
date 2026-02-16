"""스케줄러 작업 정의 모듈.

APScheduler를 사용하여 1시간 간격으로 트레이딩 루프를 실행합니다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from apscheduler.schedulers.background import BackgroundScheduler

from stockstock.logging_config import get_logger

if TYPE_CHECKING:
    pass

log = get_logger(__name__)


class TradingScheduler:
    """트레이딩 작업 스케줄러."""

    def __init__(self, interval_minutes: int = 60) -> None:
        self._scheduler = BackgroundScheduler()
        self._interval_minutes = interval_minutes
        self._trading_job_func: Callable | None = None
        self._daily_summary_func: Callable | None = None

    def set_trading_job(self, func: Callable) -> None:
        """트레이딩 루프 작업을 등록합니다."""
        self._trading_job_func = func

    def set_daily_summary_job(self, func: Callable, hour: int = 17, minute: int = 0) -> None:
        """일일 요약 작업을 등록합니다 (cron 기반)."""
        self._daily_summary_func = func
        self._scheduler.add_job(
            func,
            "cron",
            hour=hour,
            minute=minute,
            timezone="US/Eastern",
            id="daily_summary",
            replace_existing=True,
        )
        log.info("daily_summary_scheduled", hour=hour, minute=minute, tz="US/Eastern")

    def start(self) -> None:
        """스케줄러를 시작합니다."""
        if self._trading_job_func:
            self._scheduler.add_job(
                self._trading_job_func,
                "interval",
                minutes=self._interval_minutes,
                id="trading_loop",
                replace_existing=True,
            )
            log.info("trading_loop_scheduled", interval_minutes=self._interval_minutes)

        self._scheduler.start()
        log.info("scheduler_started")

    def pause_trading(self) -> None:
        """트레이딩 작업을 일시중지합니다."""
        self._scheduler.pause_job("trading_loop")
        log.info("trading_loop_paused")

    def resume_trading(self) -> None:
        """트레이딩 작업을 재개합니다."""
        self._scheduler.resume_job("trading_loop")
        log.info("trading_loop_resumed")

    def shutdown(self) -> None:
        """스케줄러를 종료합니다."""
        self._scheduler.shutdown(wait=False)
        log.info("scheduler_shutdown")

    @property
    def is_running(self) -> bool:
        return self._scheduler.running

    def get_next_run_time(self) -> str | None:
        """다음 트레이딩 루프 실행 시간을 반환합니다."""
        job = self._scheduler.get_job("trading_loop")
        if job and job.next_run_time:
            return job.next_run_time.isoformat()
        return None
