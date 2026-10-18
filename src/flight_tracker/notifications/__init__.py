"""Notification channels and the dispatcher that fans out to the enabled ones."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

import httpx

from flight_tracker.config import Config
from flight_tracker.models import AppSettings
from flight_tracker.notifications.base import Notification, NotificationError, Notifier
from flight_tracker.notifications.desktop import DesktopNotifier
from flight_tracker.notifications.mail import EmailNotifier
from flight_tracker.notifications.telegram import TelegramNotifier

logger = logging.getLogger(__name__)

__all__ = ["Notification", "NotificationDispatcher", "NotificationError", "Notifier"]


class NotificationDispatcher:
    """Sends a notification to every channel enabled in the current settings."""

    def __init__(
        self, config: Config, client: httpx.AsyncClient, settings_provider: Callable[[], AppSettings]
    ) -> None:
        self._settings_provider = settings_provider
        self._desktop = DesktopNotifier()
        self._telegram: TelegramNotifier | None = None
        self._email: EmailNotifier | None = None
        if config.telegram_configured:
            self._telegram = TelegramNotifier(
                client, config.telegram_bot_token.get_secret_value(), config.telegram_chat_id
            )
        if config.email_configured:
            self._email = EmailNotifier(
                host=config.smtp_host,
                port=config.smtp_port,
                user=config.smtp_user,
                password=config.smtp_password.get_secret_value(),
                sender=config.email_from,
                recipient=config.email_to,
            )

    @property
    def available_channels(self) -> dict[str, bool]:
        return {"desktop": True, "telegram": self._telegram is not None, "email": self._email is not None}

    def _enabled_channels(self) -> list[Notifier]:
        settings = self._settings_provider()
        channels: list[Notifier] = []
        if settings.notify_desktop:
            channels.append(self._desktop)
        if settings.notify_telegram and self._telegram:
            channels.append(self._telegram)
        if settings.notify_email and self._email:
            channels.append(self._email)
        return channels

    async def dispatch(self, notification: Notification) -> dict[str, str]:
        """Send to all enabled channels concurrently. Returns ``{channel: "ok" | error}``."""
        channels = self._enabled_channels()
        results = await asyncio.gather(*(c.send(notification) for c in channels), return_exceptions=True)
        report: dict[str, str] = {}
        for channel, result in zip(channels, results, strict=True):
            if isinstance(result, BaseException):
                logger.error("Notification via %s failed: %s", channel.name, result)
                report[channel.name] = str(result)
            else:
                report[channel.name] = "ok"
        return report
