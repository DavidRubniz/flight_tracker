"""Notification channel interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar


class NotificationError(Exception):
    """A channel failed to deliver a message."""


@dataclass(frozen=True, slots=True)
class Notification:
    title: str
    body: str
    url: str | None = None


class Notifier(ABC):
    name: ClassVar[str]

    @abstractmethod
    async def send(self, notification: Notification) -> None:
        """Deliver the notification or raise :class:`NotificationError`."""
