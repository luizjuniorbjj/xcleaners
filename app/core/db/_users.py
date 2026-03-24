"""
UsersMixin — USERS + USER PROFILES sections.
"""

import logging
from typing import Optional

from app.core.db._base import _uuid

logger = logging.getLogger("clawin.database")


class UsersMixin:
    """User and user profile database operations."""

    # ============================================
    # USERS
    # ============================================

    async def create_user(
        self,
        email: str,
        senha_hash: Optional[str] = None,
        nome: Optional[str] = None,
        oauth_provider: Optional[str] = None,
        oauth_id: Optional[str] = None,
        ref_code: Optional[str] = None,
        role: str = "lead"
    ) -> dict:
        """Create new user"""
        async with self._conn() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO users (
                    email, senha_hash, nome, oauth_provider, oauth_id,
                    ref_code, role
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id, email, nome, role, is_active, created_at
                """,
                email, senha_hash, nome, oauth_provider, oauth_id,
                ref_code, role
            )
            return dict(row)

    async def get_user_by_email(self, email: str) -> Optional[dict]:
        """Get user by email"""
        async with self._conn() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE email = $1",
                email
            )
            return dict(row) if row else None

    async def get_user_by_id(self, user_id: str) -> Optional[dict]:
        """Get user by ID"""
        async with self._conn() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE id = $1",
                _uuid(user_id)
            )
            return dict(row) if row else None

    async def get_user_by_oauth(self, provider: str, oauth_id: str) -> Optional[dict]:
        """Get user by OAuth provider and ID"""
        async with self._conn() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE oauth_provider = $1 AND oauth_id = $2",
                provider, oauth_id
            )
            return dict(row) if row else None

    async def update_last_login(self, user_id: str):
        """Update last login timestamp"""
        async with self._conn() as conn:
            await conn.execute(
                "UPDATE users SET last_login = NOW() WHERE id = $1",
                _uuid(user_id)
            )

    async def increment_message_count(self, user_id: str):
        """Increment user message counter"""
        async with self._conn() as conn:
            await conn.execute(
                "UPDATE users SET message_count = message_count + 1 WHERE id = $1",
                _uuid(user_id)
            )

    async def update_user_password(self, user_id: str, senha_hash: str):
        """Update user password"""
        async with self._conn() as conn:
            await conn.execute(
                "UPDATE users SET senha_hash = $2 WHERE id = $1",
                _uuid(user_id), senha_hash
            )

    async def update_user_role(self, user_id: str, role: str):
        """Update user role (admin, affiliate, subscriber, lead)"""
        async with self._conn() as conn:
            await conn.execute(
                "UPDATE users SET role = $2 WHERE id = $1",
                _uuid(user_id), role
            )

    async def update_user_stripe_customer(self, user_id: str, stripe_customer_id: str):
        """Set Stripe customer ID on user"""
        async with self._conn() as conn:
            await conn.execute(
                "UPDATE users SET stripe_customer_id = $2 WHERE id = $1",
                _uuid(user_id), stripe_customer_id
            )

    async def update_user_profile_photo(self, user_id: str, url: str):
        """Update user profile photo URL"""
        async with self._conn() as conn:
            await conn.execute(
                "UPDATE users SET profile_photo_url = $2 WHERE id = $1",
                _uuid(user_id), url
            )

    # ============================================
    # USER PROFILES
    # ============================================

    async def create_user_profile(
        self,
        user_id: str,
        nome: Optional[str] = None,
        language: str = "pt"
    ) -> dict:
        """Create user profile with defaults"""
        async with self._conn() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO user_profiles (user_id, nome, language, tom_preferido)
                VALUES ($1, $2, $3, 'friendly')
                RETURNING *
                """,
                _uuid(user_id), nome, language
            )
            return dict(row)

    async def get_user_profile(self, user_id: str) -> Optional[dict]:
        """Get user profile"""
        async with self._conn() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM user_profiles WHERE user_id = $1",
                _uuid(user_id)
            )
            return dict(row) if row else None

    async def update_user_profile(self, user_id: str, **kwargs) -> dict:
        """Update user profile fields"""
        if not kwargs:
            return {}

        set_clauses = []
        values = []
        for i, (key, value) in enumerate(kwargs.items(), 1):
            set_clauses.append(f"{key} = ${i}")
            values.append(value)

        values.append(_uuid(user_id))

        async with self._conn() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE user_profiles
                SET {', '.join(set_clauses)}
                WHERE user_id = ${len(values)}
                RETURNING *
                """,
                *values
            )
            return dict(row) if row else {}
