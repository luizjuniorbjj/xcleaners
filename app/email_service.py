"""
app.email_service — Platform email sender (account lifecycle).

Ownership split:
  - app.email_service (this module)                       → auth / account-lifecycle
                                                            (password reset, welcome)
  - app.modules.cleaning.services.email_service           → cleaning business domain
                                                            (booking, invoice, team_invite,
                                                             homeowner_invite, etc.)

Both modules share the same Resend transport. This module delegates the actual
send to `send_email()` in the cleaning module and reuses `_base_template()` for
consistent branding. No transport/SMTP duplication.

Public API:
    from app.email_service import email_service

    await email_service.send_password_reset_email(
        to="user@example.com",
        nome="Jane",
        reset_token="<opaque-token>",
        language="en",   # one of: pt | en | es
    )

    await email_service.send_welcome_email(
        to="user@example.com",
        nome="Jane",
        language="en",
    )

Return shape: `{"sent": bool, "id"?: str, "error"?: str}` (inherited from send_email).
"""

from __future__ import annotations

import logging
from typing import Dict

from app.modules.cleaning.services.email_service import (
    send_email,
    _base_template,
)
from app.config import APP_URL, APP_NAME

logger = logging.getLogger("xcleaners.email_service.platform")


# ============================================
# SUBJECT LINES (i18n)
# ============================================

def _reset_subject(language: str) -> str:
    return {
        "pt": f"{APP_NAME} — Redefinir senha",
        "en": f"{APP_NAME} — Reset your password",
        "es": f"{APP_NAME} — Restablecer contraseña",
    }.get(language, f"{APP_NAME} — Reset your password")


def _welcome_subject(language: str) -> str:
    return {
        "pt": f"Bem-vindo ao {APP_NAME}!",
        "en": f"Welcome to {APP_NAME}!",
        "es": f"¡Bienvenido a {APP_NAME}!",
    }.get(language, f"Welcome to {APP_NAME}!")


# ============================================
# HTML BODY BUILDERS
# ============================================

_RESET_STRINGS: Dict[str, Dict[str, str]] = {
    "pt": {
        "hello": "Olá, {nome}",
        "line1": "Recebemos uma solicitação para redefinir a senha da sua conta no {app}.",
        "cta": "Redefinir senha",
        "expires": "Este link expira em 1 hora.",
        "line2": "Se você não solicitou, ignore este email — sua senha permanecerá a mesma.",
    },
    "en": {
        "hello": "Hi {nome},",
        "line1": "We received a request to reset the password for your {app} account.",
        "cta": "Reset password",
        "expires": "This link expires in 1 hour.",
        "line2": "If you didn't request this, ignore this email — your password will stay the same.",
    },
    "es": {
        "hello": "Hola {nome},",
        "line1": "Recibimos una solicitud para restablecer la contraseña de tu cuenta de {app}.",
        "cta": "Restablecer contraseña",
        "expires": "Este enlace expira en 1 hora.",
        "line2": "Si no lo solicitaste, ignora este correo — tu contraseña seguirá igual.",
    },
}

_WELCOME_STRINGS: Dict[str, Dict[str, str]] = {
    "pt": {
        "hello": "Bem-vindo ao {app}, {nome}!",
        "line1": "Sua conta foi criada com sucesso.",
        "line2": "Começar agora:",
        "cta": "Abrir {app}",
    },
    "en": {
        "hello": "Welcome to {app}, {nome}!",
        "line1": "Your account has been created successfully.",
        "line2": "Get started:",
        "cta": "Open {app}",
    },
    "es": {
        "hello": "¡Bienvenido a {app}, {nome}!",
        "line1": "Tu cuenta fue creada con éxito.",
        "line2": "Comienza ahora:",
        "cta": "Abrir {app}",
    },
}


def _reset_body(nome: str, reset_url: str, language: str) -> str:
    s = _RESET_STRINGS.get(language) or _RESET_STRINGS["en"]
    content = f"""
      <h2 style="margin:0 0 16px 0;color:#202124;font-size:20px;font-weight:600;">
        {s['hello'].format(nome=nome)}
      </h2>
      <p style="margin:0 0 16px 0;color:#3c4043;font-size:15px;line-height:1.5;">
        {s['line1'].format(app=APP_NAME)}
      </p>
      <p style="margin:24px 0;text-align:center;">
        <a href="{reset_url}"
           style="display:inline-block;padding:12px 28px;background-color:#1a73e8;color:#ffffff;
                  text-decoration:none;border-radius:6px;font-size:15px;font-weight:500;">
          {s['cta']}
        </a>
      </p>
      <p style="margin:0 0 8px 0;color:#5f6368;font-size:13px;line-height:1.5;">
        {s['expires']}
      </p>
      <p style="margin:0;color:#5f6368;font-size:13px;line-height:1.5;">
        {s['line2']}
      </p>
    """
    return _base_template(s['cta'], content)


def _welcome_body(nome: str, language: str) -> str:
    s = _WELCOME_STRINGS.get(language) or _WELCOME_STRINGS["en"]
    content = f"""
      <h2 style="margin:0 0 16px 0;color:#202124;font-size:20px;font-weight:600;">
        {s['hello'].format(app=APP_NAME, nome=nome)}
      </h2>
      <p style="margin:0 0 8px 0;color:#3c4043;font-size:15px;line-height:1.5;">
        {s['line1']}
      </p>
      <p style="margin:0 0 16px 0;color:#3c4043;font-size:15px;line-height:1.5;">
        {s['line2']}
      </p>
      <p style="margin:24px 0;text-align:center;">
        <a href="{APP_URL}"
           style="display:inline-block;padding:12px 28px;background-color:#1a73e8;color:#ffffff;
                  text-decoration:none;border-radius:6px;font-size:15px;font-weight:500;">
          {s['cta'].format(app=APP_NAME)}
        </a>
      </p>
    """
    return _base_template(s['cta'].format(app=APP_NAME), content)


# ============================================
# PUBLIC SERVICE
# ============================================

class _PlatformEmailService:
    """Auth / account-lifecycle email sender.

    Instance exposed as `email_service` for the import pattern used in auth.py.
    """

    async def send_password_reset_email(
        self,
        to: str,
        nome: str,
        reset_token: str,
        language: str = "pt",
    ) -> dict:
        """Send a password-reset email with a one-hour link.

        Returns the `send_email` result dict. Errors are logged but not raised —
        the caller (`/auth/password-reset`) intentionally returns success to
        avoid email-enumeration, so raising here would break that contract.
        """
        reset_url = f"{APP_URL}/reset-password?token={reset_token}"
        result = await send_email(
            to=to,
            subject=_reset_subject(language),
            html_body=_reset_body(nome, reset_url, language),
            category="noreply",
        )
        if result.get("sent"):
            logger.info("Password reset email sent to %s", to)
        else:
            logger.error(
                "Failed to send password reset email to %s: %s",
                to, result.get("error"),
            )
        return result

    async def send_welcome_email(
        self,
        to: str,
        nome: str,
        language: str = "pt",
    ) -> dict:
        """Send welcome email after account creation.

        Returns the `send_email` result dict. Errors are logged only — welcome
        email failure must never block registration or OAuth callbacks.
        """
        result = await send_email(
            to=to,
            subject=_welcome_subject(language),
            html_body=_welcome_body(nome, language),
            category="welcome",
        )
        if result.get("sent"):
            logger.info("Welcome email sent to %s", to)
        else:
            logger.warning(
                "Welcome email failed for %s (non-blocking): %s",
                to, result.get("error"),
            )
        return result


email_service = _PlatformEmailService()
