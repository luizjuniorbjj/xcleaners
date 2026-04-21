"""
Xcleaners — AI prompts registry.
Each prompt is a separate module with a clear purpose:
  - scheduling_customer: chat IA para customer logado (web + WhatsApp)
  - scheduling_public_visitor: chat IA visitante anonimo no site publico (lead capture)
"""

from app.prompts.scheduling_customer import SCHEDULING_CUSTOMER_SYSTEM_PROMPT
from app.prompts.scheduling_public_visitor import SCHEDULING_PUBLIC_SYSTEM_PROMPT

__all__ = [
    "SCHEDULING_CUSTOMER_SYSTEM_PROMPT",
    "SCHEDULING_PUBLIC_SYSTEM_PROMPT",
]
