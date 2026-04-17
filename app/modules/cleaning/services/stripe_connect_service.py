"""
Xcleaners — Stripe Connect Express Service

Owner (Ana) conecta sua conta bancária via Express onboarding — cria
Stripe Account embedded com KYC mínimo, recebe payouts T+1 direto.
Xcleaners é a platform (LPJ Services LLC) mas não fica com dinheiro
do cliente (owner recebe 100%); receita LPJ vem de subscription do SaaS.

Approach: AccountLink API (modern) — zero OAuth flow needed. Single
STRIPE_SECRET_KEY (platform) cria Express accounts via stripe.Account.create.

Flow:
  1. POST /stripe/connect/create-account
     → stripe.Account.create(type='express', capabilities=card_payments+transfers)
     → stripe_account_id salvo em businesses
     → AccountLink gerado (onboarding URL)
     → owner clica, completa KYC no Stripe (SSN last 4, bank, etc), volta
  2. GET /stripe/connect/status
     → stripe.Account.retrieve() → charges_enabled, payouts_enabled
     → atualiza flags no DB
  3. POST /stripe/connect/dashboard-link
     → stripe.Account.create_login_link() → Express dashboard URL (owner ve payouts)
  4. Webhook account.updated → update status no DB automaticamente

Usage no auto-charge / payment_link:
  stripe.PaymentIntent.create(
      amount=X,
      currency='usd',
      customer=CUSTOMER_ID_ON_CONNECTED_ACCOUNT,
      off_session=True, confirm=True,
      stripe_account=business.stripe_account_id,  # charge on behalf of
  )

Author: @dev (Neo), 2026-04-16 — Story 1.2 Stripe Connect
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import stripe

logger = logging.getLogger("xcleaners.stripe_connect")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
APP_URL = os.getenv("APP_URL", "https://app.xcleaners.app")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


# ============================================
# CREATE EXPRESS ACCOUNT + ONBOARDING LINK
# ============================================

async def create_express_account(
    business_id: str,
    business_name: str,
    owner_email: str,
    country: str = "US",
) -> dict:
    """
    Create Stripe Express account for a cleaning business.

    Returns: {
        'account_id': 'acct_xxx',
        'onboarding_url': 'https://connect.stripe.com/setup/e/...',
    }

    Raises: ValueError if Stripe not configured.
    """
    if not STRIPE_SECRET_KEY:
        raise ValueError("Stripe not configured (STRIPE_SECRET_KEY missing)")

    account = stripe.Account.create(
        type="express",
        country=country,
        email=owner_email,
        capabilities={
            "card_payments": {"requested": True},
            "transfers": {"requested": True},
        },
        business_type="company",  # default; owner can change in onboarding
        business_profile={
            "name": business_name,
            "mcc": "7349",  # Cleaning & Maintenance Services
            "product_description": "Residential and commercial cleaning services",
        },
        metadata={
            "xcleaners_business_id": business_id,
            "xcleaners_business_name": business_name,
        },
    )

    link = stripe.AccountLink.create(
        account=account.id,
        refresh_url=f"{APP_URL}/settings/payments?refresh=true",
        return_url=f"{APP_URL}/settings/payments?connected=true",
        type="account_onboarding",
    )

    logger.info(
        "stripe_connect: created Express account %s for business %s",
        account.id, business_id,
    )

    return {
        "account_id": account.id,
        "onboarding_url": link.url,
    }


# ============================================
# REFRESH ONBOARDING LINK (after expiry)
# ============================================

async def refresh_onboarding_link(account_id: str) -> str:
    """
    Owner didn't complete onboarding first time — generate fresh link.

    Account links expire after a short period; this re-generates a new one.
    """
    if not STRIPE_SECRET_KEY:
        raise ValueError("Stripe not configured")

    link = stripe.AccountLink.create(
        account=account_id,
        refresh_url=f"{APP_URL}/settings/payments?refresh=true",
        return_url=f"{APP_URL}/settings/payments?connected=true",
        type="account_onboarding",
    )
    return link.url


# ============================================
# STATUS CHECK
# ============================================

async def retrieve_account_status(account_id: str) -> dict:
    """
    Pull current status from Stripe.

    Returns: {
        'charges_enabled': bool,
        'payouts_enabled': bool,
        'details_submitted': bool,
        'requirements_due': list[str],
        'status': 'pending' | 'active' | 'restricted' | 'rejected',
    }
    """
    if not STRIPE_SECRET_KEY:
        raise ValueError("Stripe not configured")

    account = stripe.Account.retrieve(account_id)

    charges_enabled = bool(account.charges_enabled)
    payouts_enabled = bool(account.payouts_enabled)
    details_submitted = bool(account.details_submitted)

    reqs = account.requirements or {}
    currently_due = reqs.get("currently_due", []) if hasattr(reqs, "get") else []
    if hasattr(reqs, "currently_due"):
        currently_due = reqs.currently_due or []
    disabled_reason = None
    if hasattr(reqs, "disabled_reason"):
        disabled_reason = reqs.disabled_reason

    if charges_enabled and payouts_enabled:
        status = "active"
    elif disabled_reason == "rejected.fraud":
        status = "rejected"
    elif disabled_reason:
        status = "restricted"
    else:
        status = "pending"

    return {
        "charges_enabled": charges_enabled,
        "payouts_enabled": payouts_enabled,
        "details_submitted": details_submitted,
        "requirements_due": list(currently_due),
        "disabled_reason": disabled_reason,
        "status": status,
    }


# ============================================
# EXPRESS DASHBOARD LOGIN LINK
# ============================================

async def create_dashboard_link(account_id: str) -> str:
    """
    Owner clicks this URL → lands inside Stripe Express dashboard where
    they can see payouts, update bank info, download statements.
    Link is single-use and expires in ~5 minutes.
    """
    if not STRIPE_SECRET_KEY:
        raise ValueError("Stripe not configured")

    link = stripe.Account.create_login_link(account_id)
    return link.url


# ============================================
# SETUP INTENT (card on file on connected account)
# ============================================

async def create_setup_intent_for_client(
    connected_account_id: str,
    client_email: str,
    client_name: str,
    client_metadata: Optional[dict] = None,
    existing_customer_id: Optional[str] = None,
) -> dict:
    """
    Create SetupIntent on the connected account so the client's
    PaymentMethod is saved to THE BUSINESS's Stripe Customer
    (not the platform).

    If `existing_customer_id` is provided, reuses that customer
    (no new Customer.create call). Otherwise creates a new one.

    Returns: {
        'customer_id': 'cus_xxx',  # stripe customer on connected account
        'setup_intent_id': 'seti_xxx',
        'client_secret': 'seti_xxx_secret_xxx',  # use in Stripe Elements
    }
    """
    if not STRIPE_SECRET_KEY:
        raise ValueError("Stripe not configured")

    if existing_customer_id:
        customer_id = existing_customer_id
    else:
        customer = stripe.Customer.create(
            email=client_email,
            name=client_name,
            metadata=client_metadata or {},
            stripe_account=connected_account_id,
        )
        customer_id = customer.id

    setup_intent = stripe.SetupIntent.create(
        customer=customer_id,
        payment_method_types=["card"],
        usage="off_session",  # for future charges without customer present
        stripe_account=connected_account_id,
    )

    return {
        "customer_id": customer_id,
        "setup_intent_id": setup_intent.id,
        "client_secret": setup_intent.client_secret,
    }


# ============================================
# LIST SAVED CARDS
# ============================================

async def list_saved_payment_methods(
    connected_account_id: str, customer_id: str,
) -> list[dict]:
    """List cards on file for a customer (connected account scope)."""
    if not STRIPE_SECRET_KEY:
        raise ValueError("Stripe not configured")

    methods = stripe.PaymentMethod.list(
        customer=customer_id,
        type="card",
        stripe_account=connected_account_id,
    )
    return [
        {
            "id": pm.id,
            "brand": pm.card.brand,
            "last4": pm.card.last4,
            "exp_month": pm.card.exp_month,
            "exp_year": pm.card.exp_year,
        }
        for pm in methods.data
    ]


# ============================================
# DETACH (remove card)
# ============================================

async def detach_payment_method(
    connected_account_id: str, payment_method_id: str,
) -> None:
    if not STRIPE_SECRET_KEY:
        raise ValueError("Stripe not configured")
    stripe.PaymentMethod.detach(
        payment_method_id, stripe_account=connected_account_id
    )
