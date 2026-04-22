"""
Xcleaners — WhatsApp Channel Adapter (Evolution API v2 / Baileys).

Portado de clawtobusiness 2026-04-20 (AI Turbo Bloco 2.3).
Namespace adaptado: clawin.* -> xcleaners.*.

Evolution API docs: https://doc.evolution-api.com/

Config expected:
    api_url:        Evolution API base URL
    instance_name:  Instance name for this business
    phone_number:   WhatsApp phone number (for display)
    webhook_secret: Optional shared secret for webhook validation

Credentials expected:
    api_key:        Evolution API key (apikey header)
"""

import logging
from typing import Optional

import httpx

from app.modules.channels.base import ChannelAdapter, IncomingMessage

logger = logging.getLogger("xcleaners.channels.whatsapp")


class WhatsAppAdapter(ChannelAdapter):
    """WhatsApp adapter via Evolution API v2."""

    channel_type = "whatsapp"

    def __init__(self, business_id: str, config: dict):
        super().__init__(business_id, config)
        self.api_url = (config.get("api_url") or "").rstrip("/")
        self.api_key = config.get("api_key", config.get("secret_key", ""))
        self.instance_name = config.get("instance_name", config.get("session_name", ""))

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "apikey": self.api_key,
        }

    async def _request(self, method: str, path: str, **kwargs) -> Optional[httpx.Response]:
        """Make an authenticated request to Evolution API."""
        if not self.api_url:
            return None

        url = f"{self.api_url}{path}"
        timeout = kwargs.pop("timeout", 15)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.request(method, url, headers=self._headers(), **kwargs)
                return resp
        except Exception as e:
            logger.error(f"[WHATSAPP] Request error {method} {path}: {e}")
            return None

    async def get_session_status(self) -> dict:
        """Get instance connection state from Evolution API."""
        if not self.api_url or not self.instance_name:
            return {"status": "not_configured"}

        resp = await self._request("GET", f"/instance/connectionState/{self.instance_name}")
        if resp and resp.status_code == 200:
            data = resp.json()
            state = data.get("instance", {}).get("state", "unknown")
            status_map = {"open": "CONNECTED", "close": "CLOSED", "connecting": "CONNECTING"}
            return {"status": status_map.get(state, state.upper())}
        return {"status": "unknown"}

    async def send_message(self, recipient_id: str, text: str) -> bool:
        """Send text message via Evolution API."""
        if not self.api_url or not self.instance_name:
            logger.warning("[WHATSAPP] Not configured — cannot send message")
            return False

        # Handle both phone numbers and LID JIDs
        if "@lid" in recipient_id:
            payload = {"number": recipient_id, "text": text}
        else:
            phone = recipient_id.replace("+", "").replace("-", "").replace(" ", "")
            phone = phone.replace("@s.whatsapp.net", "").replace("@c.us", "")
            payload = {"number": phone, "text": text}

        resp = await self._request(
            "POST",
            f"/message/sendText/{self.instance_name}",
            json=payload,
            timeout=30,
        )
        if resp and resp.status_code in (200, 201):
            return True
        if resp:
            logger.error(f"[WHATSAPP] Send failed: {resp.status_code} {resp.text[:200]}")
        return False

    async def download_audio(self, raw_payload: dict) -> Optional[bytes]:
        """Download decrypted audio bytes for an incoming voice message.

        Strategy:
        1. Try Evolution's getBase64FromMediaMessage endpoint (always works for
           audio/ptt messages — Evolution decrypts and re-encodes server-side).
        2. Fallback to direct GET on the WA-CDN url if base64 endpoint refuses.

        Returns audio bytes (typically OGG/Opus container) or None on failure.
        """
        if not self.api_url or not self.instance_name:
            return None

        data = raw_payload.get("data", {})
        if not data:
            return None

        try:
            resp = await self._request(
                "POST",
                f"/chat/getBase64FromMediaMessage/{self.instance_name}",
                json={"message": data, "convertToMp4": False},
                timeout=30,
            )
            if resp and resp.status_code in (200, 201):
                body = resp.json()
                b64 = body.get("base64") or body.get("data") or ""
                if b64:
                    import base64 as _b64
                    return _b64.b64decode(b64)
            elif resp:
                logger.warning(
                    "[WHATSAPP] getBase64 failed %s: %s",
                    resp.status_code, resp.text[:200],
                )
        except Exception as e:
            logger.warning("[WHATSAPP] getBase64 error: %s", e)

        message = data.get("message", {})
        audio_msg = message.get("audioMessage") or {}
        media_url = data.get("mediaUrl") or audio_msg.get("url")
        if not media_url:
            return None

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(media_url)
                if resp.status_code == 200:
                    return resp.content
                logger.warning(
                    "[WHATSAPP] Direct audio download failed %s: %s",
                    resp.status_code, resp.text[:200],
                )
        except Exception as e:
            logger.warning("[WHATSAPP] Direct audio download error: %s", e)

        return None

    async def send_typing(self, recipient_id: str, delay_ms: int = 3000):
        """Send composing presence via Evolution API (best-effort, silent on failure)."""
        if "@lid" in recipient_id:
            number = recipient_id
        else:
            number = recipient_id.replace("+", "").replace("-", "").replace(" ", "")
            number = number.replace("@s.whatsapp.net", "").replace("@c.us", "")
        try:
            await self._request(
                "POST",
                f"/chat/sendPresence/{self.instance_name}",
                json={"number": number, "presence": "composing", "delay": delay_ms},
            )
        except Exception:
            pass  # Best effort

    def parse_webhook(self, payload: dict) -> Optional[IncomingMessage]:
        """
        Parse Evolution API v2 webhook payload.
        Evolution sends event='messages.upsert' for incoming messages.
        """
        event = payload.get("event", "")
        if event not in ("messages.upsert", "MESSAGES_UPSERT"):
            return None

        data = payload.get("data", {})
        key = data.get("key", {})

        # Ignore messages from us
        if key.get("fromMe"):
            return None

        remote_jid = key.get("remoteJid", "")
        if not remote_jid:
            return None

        # Ignore group messages
        if "@g.us" in remote_jid:
            return None

        # Clean sender ID — preserve @lid JIDs (cannot be converted to phone)
        if "@lid" in remote_jid:
            sender_id = remote_jid
        else:
            sender_id = (
                remote_jid
                .replace("@s.whatsapp.net", "")
                .replace("@c.us", "")
            )

        push_name = data.get("pushName", sender_id)

        # Extract text from message
        message = data.get("message", {})
        text = (
            message.get("conversation", "")
            or message.get("extendedTextMessage", {}).get("text", "")
            or ""
        ).strip()

        # Check for audio/voice message
        audio_url = None
        audio_mime = None
        audio_msg = message.get("audioMessage")
        if audio_msg and not text:
            media_url = data.get("mediaUrl") or audio_msg.get("url")
            if media_url:
                audio_url = media_url
                audio_mime = audio_msg.get("mimetype", "audio/ogg")
                text = ""  # will be transcribed later (future feature)

        if not text and not audio_url:
            return None

        return IncomingMessage(
            channel_type="whatsapp",
            sender_id=sender_id,
            sender_name=push_name,
            text=text,
            business_id=self.business_id,
            raw_payload=payload,
            audio_url=audio_url,
            audio_mime=audio_mime,
        )

    def validate_webhook(self, headers: dict, body: bytes) -> bool:
        """
        Evolution API webhook validation.
        If webhook_secret configured, requires matching x-webhook-secret header.
        If no secret configured, accepts (trust network-level restriction).
        """
        webhook_secret = self.config.get("webhook_secret", "")
        if not webhook_secret:
            return True
        # Header names are lowercase in FastAPI Request.headers
        received = headers.get("x-webhook-secret", "") or headers.get("X-Webhook-Secret", "")
        return received == webhook_secret

    async def get_qr_code(self) -> Optional[str]:
        """Get QR code for WhatsApp pairing (returns base64 data URI or None)."""
        if not self.api_url or not self.instance_name:
            return None

        resp = await self._request("GET", f"/instance/connect/{self.instance_name}")
        if resp and resp.status_code == 200:
            data = resp.json()
            return data.get("base64")
        return None

    async def create_instance(self, webhook_url: str = "") -> bool:
        """Create Evolution API instance with optional per-instance webhook."""
        if not self.api_url or not self.instance_name:
            return False

        payload = {
            "instanceName": self.instance_name,
            "integration": "WHATSAPP-BAILEYS",
            "qrcode": True,
        }

        if webhook_url:
            payload["webhook"] = {
                "url": webhook_url,
                "byEvents": False,
                "base64": False,
                "events": ["MESSAGES_UPSERT", "CONNECTION_UPDATE"],
            }

        resp = await self._request("POST", "/instance/create", json=payload)
        if resp and resp.status_code in (200, 201):
            logger.info(f"[WHATSAPP] Instance '{self.instance_name}' created")
            return True
        if resp and resp.status_code == 403 and "already in use" in resp.text:
            if webhook_url:
                await self.set_instance_webhook(webhook_url)
            return True
        if resp:
            logger.error(f"[WHATSAPP] Create instance failed: {resp.status_code} {resp.text[:200]}")
        return False

    async def set_instance_webhook(self, webhook_url: str) -> bool:
        """Set/update per-instance webhook on Evolution API."""
        if not self.api_url or not self.instance_name:
            return False

        payload = {
            "webhook": {
                "enabled": True,
                "url": webhook_url,
                "byEvents": False,
                "base64": False,
                "events": ["MESSAGES_UPSERT", "CONNECTION_UPDATE"],
            }
        }
        resp = await self._request("POST", f"/webhook/set/{self.instance_name}", json=payload)
        if resp and resp.status_code in (200, 201):
            logger.info(f"[WHATSAPP] Webhook set for '{self.instance_name}': {webhook_url}")
            return True
        if resp:
            logger.error(f"[WHATSAPP] Set webhook failed: {resp.status_code} {resp.text[:200]}")
        return False
