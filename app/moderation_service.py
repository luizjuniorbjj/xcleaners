"""
Xcleaners - Moderation Service
OpenAI Moderation API for content safety checks.
Free API (up to 1000 req/min), ~100-200ms latency.

Portado de clawtobusiness em 2026-04-20 (AI Turbo Sprint).
Ajustes: namespace do logger + docstring.
"""

import logging
from typing import Optional, Dict
from dataclasses import dataclass, field

from openai import AsyncOpenAI

from app.config import OPENAI_API_KEY, MODERATION_ENABLED, MODERATION_MODEL

logger = logging.getLogger("xcleaners.moderation")


@dataclass
class ModerationResult:
    """Result of moderation check"""
    flagged: bool = False
    self_harm: bool = False
    violence: bool = False
    hate: bool = False
    harassment: bool = False
    sexual: bool = False
    categories: Dict[str, bool] = field(default_factory=dict)
    scores: Dict[str, float] = field(default_factory=dict)
    error: Optional[str] = None


class ModerationService:
    """
    Content moderation via OpenAI Moderation API.
    Detects: self-harm, violence, hate, harassment, sexual content.

    Graceful degradation: if MODERATION_ENABLED=false or OPENAI_API_KEY missing,
    returns empty (non-flagged) result — IA chat continues without blocking.
    """

    def __init__(self):
        self.client = None
        self.enabled = MODERATION_ENABLED

        if self.enabled and OPENAI_API_KEY:
            self.client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            logger.info("[MODERATION] Service initialized")
        else:
            logger.info("[MODERATION] Service disabled (MODERATION_ENABLED=False or no OpenAI key)")

    async def check(self, text: str) -> ModerationResult:
        """Check text against OpenAI Moderation API"""
        if not self.enabled or not self.client:
            return ModerationResult()

        try:
            response = await self.client.moderations.create(
                model=MODERATION_MODEL,
                input=text,
            )

            result = response.results[0]

            flagged_categories = {}
            for category, is_flagged in vars(result.categories).items():
                if is_flagged and not category.startswith('_'):
                    flagged_categories[category] = True

            scores = {}
            for category, score in vars(result.category_scores).items():
                if not category.startswith('_'):
                    scores[category] = score

            mod_result = ModerationResult(
                flagged=result.flagged,
                self_harm=getattr(result.categories, 'self_harm', False),
                violence=getattr(result.categories, 'violence', False),
                hate=getattr(result.categories, 'hate', False),
                harassment=getattr(result.categories, 'harassment', False),
                sexual=getattr(result.categories, 'sexual', False),
                categories=flagged_categories,
                scores=scores,
            )

            if mod_result.flagged:
                logger.warning(f"[MODERATION] Flagged: {list(flagged_categories.keys())}")

            return mod_result

        except Exception as e:
            logger.error(f"[MODERATION] API error: {e}")
            return ModerationResult(error=str(e))

    async def is_safe(self, text: str) -> bool:
        """Returns True if text passes moderation"""
        result = await self.check(text)
        return not result.flagged


# Global singleton
_service: Optional[ModerationService] = None


def get_moderation_service() -> ModerationService:
    global _service
    if _service is None:
        _service = ModerationService()
    return _service
