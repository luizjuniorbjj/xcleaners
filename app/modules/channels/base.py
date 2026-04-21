"""
Xcleaners — Channel Adapter Base
Abstract interface for channel adapters (WhatsApp, future: Telegram, Instagram).
Portado de clawtobusiness 2026-04-20 (AI Turbo Bloco 2.3).
Namespace adaptado: clawin.* -> xcleaners.*.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger("xcleaners.channels")


class IncomingMessage:
    """Normalized incoming message from any channel."""

    def __init__(
        self,
        channel_type: str,
        sender_id: str,
        sender_name: str,
        text: str,
        business_id: str,
        raw_payload: dict = None,
        audio_url: str = None,
        audio_mime: str = None,
    ):
        self.channel_type = channel_type
        self.sender_id = sender_id
        self.sender_name = sender_name
        self.text = text
        self.business_id = business_id
        self.raw_payload = raw_payload or {}
        self.audio_url = audio_url      # URL to download audio (if voice message)
        self.audio_mime = audio_mime    # e.g. "audio/ogg", "audio/mpeg"


class ChannelAdapter(ABC):
    """
    Abstract base class for channel adapters.
    Each adapter handles one channel type (WhatsApp, Telegram, etc).
    """

    channel_type: str = "unknown"

    def __init__(self, business_id: str, config: dict):
        self.business_id = business_id
        self.config = config

    @abstractmethod
    async def send_message(self, recipient_id: str, text: str) -> bool:
        """Send a text message to a recipient. Returns True on success."""
        ...

    @abstractmethod
    async def send_typing(self, recipient_id: str):
        """Send typing indicator (best effort, non-blocking)."""
        ...

    @abstractmethod
    def parse_webhook(self, payload: dict) -> Optional[IncomingMessage]:
        """
        Parse a raw webhook payload into an IncomingMessage.
        Returns None if the payload should be ignored (edit, reaction, etc).
        """
        ...

    @abstractmethod
    def validate_webhook(self, headers: dict, body: bytes) -> bool:
        """
        Validate webhook authenticity (secret token, signature, etc).
        Returns True if valid.
        """
        ...

    def synthetic_email(self, sender_id: str) -> str:
        """Generate a synthetic email for channel users (virtual accounts)."""
        return f"{self.channel_type}_{sender_id}@{self.channel_type}.xcleaners.internal"
