"""Telegram Bot API notifications (https://core.telegram.org/bots/api#sendmessage)."""

from __future__ import annotations

import html

import httpx

from flight_tracker.notifications.base import Notification, NotificationError, Notifier


class TelegramNotifier(Notifier):
    name = "telegram"

    def __init__(self, client: httpx.AsyncClient, bot_token: str, chat_id: str) -> None:
        self._client = client
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._chat_id = chat_id

    async def send(self, notification: Notification) -> None:
        text = f"<b>{html.escape(notification.title)}</b>\n{html.escape(notification.body)}"
        if notification.url:
            text += f'\n<a href="{html.escape(notification.url, quote=True)}">לפרטים והזמנה</a>'
        try:
            response = await self._client.post(
                self._url,
                json={
                    "chat_id": self._chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
        except httpx.HTTPError as exc:
            raise NotificationError(f"telegram: network error: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise NotificationError(f"telegram: HTTP {response.status_code}: {response.text[:200]}")
