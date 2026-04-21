"""
Xcleaners - Configuration
Environment variables and global settings.
Cleaned from ClaWtoBusiness monolith on 2026-04-09 (C-4 security fix).
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ============================================
# DATABASE
# ============================================
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/xcleaners")

# ============================================
# REDIS
# ============================================
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ============================================
# SECURITY
# ============================================
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("CRITICAL: SECRET_KEY not set. Set it in .env")

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    raise RuntimeError(
        "[CRITICAL] ENCRYPTION_KEY not set! "
        "Required for data encryption. Set it in .env before starting."
    )

JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_HOURS = 1
JWT_REFRESH_TOKEN_DAYS = 30

# ============================================
# APP SETTINGS
# ============================================
APP_NAME = "Xcleaners"
APP_VERSION = "1.0.0"
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
MAINTENANCE_MODE = os.getenv("MAINTENANCE_MODE", "False").lower() == "true"

# ============================================
# AI SETTINGS (used by ai_scheduling.py)
# ============================================
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Provider: "proxy" | "openai" | "anthropic"
AI_PROVIDER = os.getenv("AI_PROVIDER", "openai")
AI_MODEL_PRIMARY = os.getenv("AI_MODEL_PRIMARY", "gpt-4.1-mini")
AI_MODEL_FALLBACK = os.getenv("AI_MODEL_FALLBACK", "gpt-4.1-mini")
AI_MODEL_EXTRACTION = os.getenv("AI_MODEL_EXTRACTION", "gpt-4.1-mini")

# Proxy settings (optional)
PROXY_URL = os.getenv("AI_PROXY_URL", "")

# Proxy model aliases (used by ai_scheduling.py)
PROXY_MODEL_PRIMARY = AI_MODEL_PRIMARY
PROXY_MODEL_EXTRACTION = AI_MODEL_EXTRACTION

MAX_TOKENS_RESPONSE = 2000
MAX_CONTEXT_TOKENS = 4000

# Moderation (OpenAI Moderation API — free, used in /ai/chat pipeline)
MODERATION_ENABLED = os.getenv("MODERATION_ENABLED", "true").lower() == "true"
MODERATION_MODEL = os.getenv("MODERATION_MODEL", "omni-moderation-latest")

# Security gates fail policy: when True, failures in moderation / rate-limit
# reject the request (503). When False, log and continue (fail-open).
# Default True (safe for production). Disable only in dev local without Redis/OpenAI.
GATES_FAIL_CLOSED = os.getenv("GATES_FAIL_CLOSED", "true").lower() == "true"

# ============================================
# STRIPE (H-6 fix: no hardcoded price IDs)
# ============================================
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# Xcleaners subscription plan price IDs (MUST be set in env)
STRIPE_PRICE_BASIC = os.getenv("STRIPE_PRICE_BASIC", "")
STRIPE_PRICE_INTERMEDIATE = os.getenv("STRIPE_PRICE_INTERMEDIATE", "")
STRIPE_PRICE_MAXIMUM = os.getenv("STRIPE_PRICE_MAXIMUM", "")

# Legacy ClaWtoBusiness price IDs — removed (H-6 fix)
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
STRIPE_BUSINESS_PRICE_ID = os.getenv("STRIPE_BUSINESS_PRICE_ID", "")
STRIPE_SETUP_PRICE_ID = os.getenv("STRIPE_SETUP_PRICE_ID", "")
STRIPE_MONTHLY_PRICE_ID = os.getenv("STRIPE_MONTHLY_PRICE_ID", "")

# ============================================
# OAUTH
# ============================================
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8003/auth/google/callback")

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI", "http://localhost:8003/auth/github/callback")

# ============================================
# CORS
# ============================================
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else []
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
CORS_ALLOW_HEADERS = ["*"]

PRODUCTION_ORIGINS = [
    "https://xcleaners.com",
    "https://www.xcleaners.com",
]

# ============================================
# EMAIL (Resend)
# ============================================
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "Xcleaners <noreply@xcleaners.com>")
EMAIL_REPLY_TO = os.getenv("EMAIL_REPLY_TO", "support@xcleaners.com")
APP_URL = os.getenv("APP_URL", "https://xcleaners.com")

# ============================================
# ADMIN
# ============================================
ADMIN_EMAILS = os.getenv("ADMIN_EMAILS", "admin@xcleaners.com").split(",")

# ============================================
# PUSH NOTIFICATIONS (VAPID)
# ============================================
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_CLAIMS_EMAIL = os.getenv("VAPID_CLAIMS_EMAIL", "support@xcleaners.com")

# ============================================
# TWILIO (SMS notifications)
# ============================================
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")

# ============================================
# XCLEANERS MODULE
# ============================================
XCLEANERS_DEFAULT_PLAN = os.getenv("XCLEANERS_DEFAULT_PLAN", "basic")
XCLEANERS_AUTO_SCHEDULE_TIME = os.getenv("XCLEANERS_AUTO_SCHEDULE_TIME", "18:00")
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:support@xcleaners.com")
