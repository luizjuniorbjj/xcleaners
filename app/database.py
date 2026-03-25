"""
ClaWin1Click - Database Layer (re-export from app.core.db)
Backward-compatible: all existing imports continue to work.

PostgreSQL abstraction via asyncpg — single-platform (NOT multi-tenant)
Forked from SegurIA, adapted for OpenClaw deploy platform
"""

from app.core.db import Database, UUIDEncoder, _uuid  # noqa: F401

# Keep module-level connection pool management here
import logging
import pathlib
from typing import Optional

import asyncpg

from app.config import DATABASE_URL

logger = logging.getLogger("clawin.database")

# ============================================
# CONNECTION POOL
# ============================================

_pool: Optional[asyncpg.Pool] = None


async def _init_connection(conn):
    """
    Pool setup callback — runs once per new connection.
    Sets the application role to enforce RLS policies.
    NOTE: Role name 'xcleaners_app' was renamed from the legacy role in migration 020.
    """
    try:
        await conn.execute("SET ROLE xcleaners_app")
    except Exception as e:
        logger.warning(f"[DB] Could not SET ROLE xcleaners_app (role may not exist): {e}")


async def init_db():
    """Initialize connection pool and ensure schema exists"""
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=5, max_size=20, init=_init_connection)

    async with _pool.acquire() as conn:
        version = await conn.fetchval("SELECT version()")
        logger.info(f"[DB] Connected to PostgreSQL")

        # Check if schema exists, apply if not
        table_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='users')"
        )
        if not table_exists:
            logger.info("[DB] Tables not found, applying schema...")
            schema_path = pathlib.Path(__file__).parent.parent / "database" / "schema.sql"
            if schema_path.exists():
                schema_sql = schema_path.read_text()
                await conn.execute(schema_sql)
                logger.info("[DB] Schema applied successfully")
            else:
                logger.warning("[DB] schema.sql not found, skipping migration")

        try:
            user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
            logger.info(f"[DB] {user_count} user(s) found")
        except Exception:
            logger.warning("[DB] Could not count users (table may not exist yet)")

        # Ensure broadcast_history table exists
        try:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS broadcast_history (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    subject VARCHAR(200) NOT NULL,
                    message TEXT NOT NULL,
                    email_type VARCHAR(20) DEFAULT 'promotion',
                    audience VARCHAR(20) DEFAULT 'all',
                    language VARCHAR(5) DEFAULT 'en',
                    recipients_count INTEGER DEFAULT 0,
                    sent_count INTEGER DEFAULT 0,
                    failed_count INTEGER DEFAULT 0,
                    sent_by VARCHAR(255),
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_broadcast_history_created ON broadcast_history(created_at DESC);
            """)
            logger.info("[DB] broadcast_history table ensured")
        except Exception as e:
            logger.warning(f"[DB] broadcast_history creation: {e}")

        # Ensure marketing module tables exist (Migration 009)
        try:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS marketing_blog_schedule (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
                    enabled BOOLEAN DEFAULT FALSE,
                    posts_per_day INTEGER DEFAULT 2,
                    publish_hour INTEGER DEFAULT 8,
                    auto_publish BOOLEAN DEFAULT TRUE,
                    cities TEXT[] DEFAULT '{}',
                    services TEXT[] DEFAULT '{}',
                    last_run_at TIMESTAMPTZ,
                    posts_generated_today INTEGER DEFAULT 0,
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(business_id)
                );
                ALTER TABLE marketing_blog_schedule ADD COLUMN IF NOT EXISTS cities TEXT[] DEFAULT '{}';
                ALTER TABLE marketing_blog_schedule ADD COLUMN IF NOT EXISTS services TEXT[] DEFAULT '{}';
                CREATE TABLE IF NOT EXISTS marketing_seo_terms (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
                    term VARCHAR(300) NOT NULL,
                    city VARCHAR(100) NOT NULL,
                    state VARCHAR(50) DEFAULT '',
                    target_url VARCHAR(500),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_seo_terms_biz ON marketing_seo_terms(business_id, is_active);
                CREATE TABLE IF NOT EXISTS marketing_seo_rankings (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
                    search_term_id UUID NOT NULL REFERENCES marketing_seo_terms(id) ON DELETE CASCADE,
                    position INTEGER,
                    page INTEGER,
                    snippet TEXT,
                    clicks INTEGER DEFAULT 0,
                    impressions INTEGER DEFAULT 0,
                    ctr NUMERIC(5,4) DEFAULT 0,
                    source VARCHAR(20) DEFAULT 'scrape',
                    checked_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_seo_rankings_biz ON marketing_seo_rankings(business_id, checked_at DESC);
                CREATE TABLE IF NOT EXISTS marketing_review_responses (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
                    platform VARCHAR(50) NOT NULL,
                    reviewer_name VARCHAR(200),
                    review_text TEXT NOT NULL,
                    rating INTEGER,
                    ai_response TEXT NOT NULL,
                    status VARCHAR(20) DEFAULT 'draft',
                    created_by UUID,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_reviews_biz ON marketing_review_responses(business_id, status);
                CREATE TABLE IF NOT EXISTS marketing_content (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
                    content_type VARCHAR(50) NOT NULL,
                    city VARCHAR(100),
                    service VARCHAR(100),
                    platform VARCHAR(50),
                    content_text TEXT NOT NULL,
                    status VARCHAR(20) DEFAULT 'draft',
                    created_by UUID,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_content_biz ON marketing_content(business_id, content_type);
                CREATE TABLE IF NOT EXISTS marketing_landing_pages (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
                    city VARCHAR(100) NOT NULL,
                    service VARCHAR(100) NOT NULL,
                    slug VARCHAR(200) NOT NULL,
                    html_content TEXT NOT NULL,
                    meta_title VARCHAR(200),
                    meta_description VARCHAR(320),
                    ai_model VARCHAR(50),
                    views INTEGER DEFAULT 0,
                    is_published BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(business_id, slug)
                );
            """)
            # ALTER TABLE for blog posts extension (safe: IF NOT EXISTS)
            for col_sql in [
                "ALTER TABLE business_blog_posts ADD COLUMN IF NOT EXISTS meta_description VARCHAR(320)",
                "ALTER TABLE business_blog_posts ADD COLUMN IF NOT EXISTS excerpt VARCHAR(500)",
                "ALTER TABLE business_blog_posts ADD COLUMN IF NOT EXISTS category VARCHAR(100)",
                "ALTER TABLE business_blog_posts ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}'",
                "ALTER TABLE business_blog_posts ADD COLUMN IF NOT EXISTS city VARCHAR(100)",
                "ALTER TABLE business_blog_posts ADD COLUMN IF NOT EXISTS service VARCHAR(100)",
                "ALTER TABLE business_blog_posts ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'published'",
                "ALTER TABLE business_blog_posts ADD COLUMN IF NOT EXISTS ai_model VARCHAR(50)",
                "ALTER TABLE business_blog_posts ADD COLUMN IF NOT EXISTS views INTEGER DEFAULT 0",
                "ALTER TABLE business_blog_posts ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ",
            ]:
                await conn.execute(col_sql)
            logger.info("[DB] Marketing module tables ensured (migration 009)")
        except Exception as e:
            logger.warning(f"[DB] Marketing tables creation: {e}")

        # Ensure social module tables exist (Migration 010)
        try:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS social_posts (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
                    theme VARCHAR(500) NOT NULL,
                    x_text TEXT,
                    ig_caption TEXT,
                    hashtags TEXT[] DEFAULT '{}',
                    cta TEXT,
                    image_prompt TEXT,
                    image_path TEXT,
                    video_path TEXT,
                    platforms TEXT[] DEFAULT '{"x","instagram"}',
                    language VARCHAR(5) DEFAULT 'pt',
                    status VARCHAR(20) DEFAULT 'pending',
                    priority INTEGER DEFAULT 0,
                    scheduled_at TIMESTAMPTZ,
                    posted_at TIMESTAMPTZ,
                    error_message TEXT,
                    platform_post_id VARCHAR(200),
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_social_posts_biz_status
                    ON social_posts(business_id, status);
                CREATE INDEX IF NOT EXISTS idx_social_posts_scheduled
                    ON social_posts(business_id, status, scheduled_at);

                CREATE TABLE IF NOT EXISTS social_accounts (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
                    platform VARCHAR(20) NOT NULL,
                    username VARCHAR(100) NOT NULL,
                    status VARCHAR(20) DEFAULT 'active',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(business_id, platform)
                );

                CREATE TABLE IF NOT EXISTS social_comments (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
                    platform VARCHAR(20) NOT NULL,
                    post_id_external VARCHAR(200),
                    comment_text TEXT NOT NULL,
                    commenter_name VARCHAR(200),
                    reply_text TEXT,
                    status VARCHAR(20) DEFAULT 'pending',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_social_comments_biz
                    ON social_comments(business_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS social_schedule (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
                    enabled BOOLEAN DEFAULT FALSE,
                    posts_per_day INTEGER DEFAULT 2,
                    publish_hours INTEGER[] DEFAULT '{9,12,18}',
                    platforms TEXT[] DEFAULT '{"x","instagram"}',
                    themes TEXT[] DEFAULT '{}',
                    worker_type VARCHAR(20) DEFAULT 'shared',
                    posts_generated_today INTEGER DEFAULT 0,
                    last_run_at TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(business_id)
                );
            """)
            logger.info("[DB] Social module tables ensured (migration 010)")
        except Exception as e:
            logger.warning(f"[DB] Social tables creation: {e}")

        # Persona structured data (Migration 016 - Story 1.1)
        try:
            await conn.execute("ALTER TABLE business_personas ADD COLUMN IF NOT EXISTS structured_data JSONB DEFAULT NULL")
            await conn.execute("ALTER TABLE business_personas ADD COLUMN IF NOT EXISTS prompt_manually_edited BOOLEAN DEFAULT FALSE")
            logger.info("[DB] Persona structured_data columns ensured (migration 016)")
        except Exception as e:
            logger.warning(f"[DB] Persona migration 016: {e}")

    return _pool


async def close_db():
    """Close connection pool"""
    global _pool
    if _pool:
        await _pool.close()


async def get_db() -> Database:
    """FastAPI dependency injection for database"""
    if not _pool:
        await init_db()
    return Database(_pool)


async def get_db_pool():
    """Get connection pool directly (for background tasks)"""
    global _pool
    if not _pool:
        await init_db()
    return _pool


async def get_db_instance() -> Database:
    """Get Database instance directly (outside FastAPI dependencies)"""
    global _pool
    if not _pool:
        await init_db()
    return Database(_pool) if _pool else None
