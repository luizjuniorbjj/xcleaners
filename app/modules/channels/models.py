"""
Xcleaners — Channels Pydantic Models.
Portado de clawtobusiness 2026-04-20 (AI Turbo Bloco 2.3).
"""

from typing import Optional
from pydantic import BaseModel


class ChannelConnect(BaseModel):
    """Request to connect/configure a channel for a business."""
    bot_token: Optional[str] = None          # Telegram bot token (future)
    api_url: Optional[str] = None            # WhatsApp API URL (Evolution API)
    api_key: Optional[str] = None            # WhatsApp API key
    instance_name: Optional[str] = None      # WhatsApp instance name
    phone_number: Optional[str] = None       # WhatsApp phone number
    webhook_secret: Optional[str] = None     # Webhook verification secret


class ChannelStatus(BaseModel):
    channel_type: str
    status: str  # active, disconnected, error, not_configured
    business_id: str
    webhook_url: Optional[str] = None
    last_activity_at: Optional[str] = None
    error: Optional[str] = None


class ChannelListResponse(BaseModel):
    channels: list[ChannelStatus]
    total: int
