"""
Xcleaners — AI prompts registry.
Each prompt is a separate module with a clear purpose:
  - scheduling_customer: chat IA para customer logado (web + WhatsApp futuro)
"""

from app.prompts.scheduling_customer import SCHEDULING_CUSTOMER_SYSTEM_PROMPT

__all__ = ["SCHEDULING_CUSTOMER_SYSTEM_PROMPT"]
