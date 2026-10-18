"""SMTP e-mail notifications (STARTTLS)."""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage

from flight_tracker.notifications.base import Notification, NotificationError, Notifier


class EmailNotifier(Notifier):
    name = "email"

    def __init__(  # noqa: PLR0913 - plain SMTP settings
        self, *, host: str, port: int, user: str, password: str, sender: str, recipient: str
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._sender = sender or user
        self._recipient = recipient

    async def send(self, notification: Notification) -> None:
        await asyncio.to_thread(self._send_sync, notification)

    def _send_sync(self, notification: Notification) -> None:
        message = EmailMessage()
        message["Subject"] = notification.title
        message["From"] = self._sender
        message["To"] = self._recipient
        body = notification.body + (f"\n\n{notification.url}" if notification.url else "")
        message.set_content(body)
        try:
            with smtplib.SMTP(self._host, self._port, timeout=30) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(self._user, self._password)
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            raise NotificationError(f"email: {exc}") from exc
