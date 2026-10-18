"""Local OS notifications (Windows toast / macOS / Linux) via ``plyer``."""

from __future__ import annotations

import asyncio

from flight_tracker.notifications.base import Notification, NotificationError, Notifier


class DesktopNotifier(Notifier):
    name = "desktop"

    async def send(self, notification: Notification) -> None:
        await asyncio.to_thread(self._send_sync, notification)

    @staticmethod
    def _send_sync(notification: Notification) -> None:
        try:
            from plyer import notification as plyer_notification  # noqa: PLC0415 - optional, slow import
        except ImportError as exc:
            raise NotificationError("plyer is not installed") from exc
        try:
            plyer_notification.notify(
                title=notification.title[:63],
                message=notification.body[:255],
                app_name="Flight Tracker",
                timeout=10,
            )
        except Exception as exc:  # plyer raises backend-specific errors
            raise NotificationError(f"desktop notification failed: {exc}") from exc
