"""
Tests for CSV import endpoint [3S-3].

Integration with DB. Uses UploadFile stub to simulate multipart upload.

Covers:
  - happy path: import 10 new clients
  - skip duplicate emails (not a hard failure)
  - validation error on bad row (e.g., missing required first_name)
  - 400 when required header missing
  - empty file (header only) → imported=0

Author: @dev (Neo), 2026-04-17 — Feature 3S-3
"""

from __future__ import annotations

import io
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers


pytest.importorskip(
    "app.modules.cleaning.routes.clients",
    reason="cleaning.clients routes not available.",
)

from app.modules.cleaning.routes.clients import (  # noqa: E402
    api_import_clients_csv,
    api_download_import_template,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def biz_import(db):
    biz_id = await db.pool.fetchval(
        """
        INSERT INTO businesses (slug, name)
        VALUES ('import_biz_' || gen_random_uuid()::text, 'Import Test Biz')
        RETURNING id
        """
    )
    yield biz_id
    # Cleanup clients first (FK), then business
    await db.pool.execute("DELETE FROM cleaning_clients WHERE business_id = $1", biz_id)
    await db.pool.execute("DELETE FROM businesses WHERE id = $1", biz_id)


def _user(business_id):
    return {
        "user_id": str(uuid.uuid4()),
        "email": "owner@test.com",
        "business_id": business_id,
        "business_slug": "import-test",
        "role": "owner",
    }


def _make_upload(csv_text: str, filename: str = "clients.csv") -> UploadFile:
    """Build a FastAPI UploadFile from in-memory CSV text."""
    file_obj = io.BytesIO(csv_text.encode("utf-8"))
    upload = UploadFile(file=file_obj, filename=filename, headers=Headers({"content-type": "text/csv"}))
    return upload


_HEADER = "first_name,last_name,email,phone,address_line1,city,state,zip_code,country"


# ============================================================================
# POST /import
# ============================================================================


@pytest.mark.asyncio
async def test_import_happy_10_clients(db, biz_import):
    """10 unique rows → imported=10, skipped=0, errors=0."""
    rows = [_HEADER]
    for i in range(10):
        rows.append(
            f"Import{i},Test{i},import_{i}@test.example,+1555010{i:04d},"
            f"{100 + i} Main St,New Orleans,LA,70112,US"
        )
    upload = _make_upload("\n".join(rows))

    result = await api_import_clients_csv(
        slug="import-test",
        file=upload,
        user=_user(biz_import),
        db=db,
    )

    assert result["imported"] == 10
    assert result["skipped"] == []
    assert result["errors"] == []
    assert result["total_rows"] == 10

    count = await db.pool.fetchval(
        "SELECT COUNT(*) FROM cleaning_clients WHERE business_id = $1", biz_import
    )
    assert count == 10


@pytest.mark.asyncio
async def test_import_skips_duplicate_emails(db, biz_import):
    """Client with email X exists → CSV row with same email is skipped (not error)."""
    # Pre-existing client with email 'dup@test.example'
    await db.pool.execute(
        """
        INSERT INTO cleaning_clients (business_id, first_name, last_name, email, phone)
        VALUES ($1, 'Pre', 'Existing', 'dup@test.example', '+15551230000')
        """,
        biz_import,
    )

    csv_text = "\n".join([
        _HEADER,
        "New,Person,new@test.example,+15559991111,10 A St,NOLA,LA,70112,US",
        "Dup,Attempt,dup@test.example,+15550001234,20 B St,NOLA,LA,70112,US",
    ])
    upload = _make_upload(csv_text)

    result = await api_import_clients_csv(
        slug="import-test",
        file=upload,
        user=_user(biz_import),
        db=db,
    )

    assert result["imported"] == 1
    assert len(result["skipped"]) == 1
    assert result["skipped"][0]["email"] == "dup@test.example"
    assert "duplicate" in result["skipped"][0]["reason"]
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_import_validation_error_on_missing_first_name(db, biz_import):
    """Row with empty first_name → validation error captured, not crashed."""
    csv_text = "\n".join([
        _HEADER,
        "Valid,Person,ok@test.example,+15551111111,1 A St,NOLA,LA,70112,US",
        ",BadRow,bad@test.example,+15552222222,2 B St,NOLA,LA,70112,US",
    ])
    upload = _make_upload(csv_text)

    result = await api_import_clients_csv(
        slug="import-test",
        file=upload,
        user=_user(biz_import),
        db=db,
    )

    assert result["imported"] == 1
    assert len(result["errors"]) == 1
    assert result["errors"][0]["row"] == 3
    assert "first_name" in result["errors"][0]["reason"].lower()


@pytest.mark.asyncio
async def test_import_missing_required_header_returns_400(db, biz_import):
    """CSV sem coluna 'email' → 400 com detalhe."""
    bad_header = "first_name,last_name,phone,address_line1,city,state,zip_code,country"
    csv_text = "\n".join([
        bad_header,
        "A,B,+15555550000,1 A St,NOLA,LA,70112,US",
    ])
    upload = _make_upload(csv_text)

    with pytest.raises(HTTPException) as exc:
        await api_import_clients_csv(
            slug="import-test",
            file=upload,
            user=_user(biz_import),
            db=db,
        )
    assert exc.value.status_code == 400
    assert "email" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_import_empty_file_header_only(db, biz_import):
    """Arquivo só com header → imported=0, zero errors."""
    upload = _make_upload(_HEADER)

    result = await api_import_clients_csv(
        slug="import-test",
        file=upload,
        user=_user(biz_import),
        db=db,
    )

    assert result == {
        "imported": 0,
        "skipped": [],
        "errors": [],
        "total_rows": 0,
    }


# ============================================================================
# GET /import/template
# ============================================================================


@pytest.mark.asyncio
async def test_import_template_returns_csv(biz_import):
    """Template endpoint returns CSV with headers + example row."""
    resp = await api_download_import_template(
        slug="import-test",
        user=_user(biz_import),
    )
    assert resp.media_type == "text/csv"
    body = resp.body.decode("utf-8")
    # Header + at least 1 row
    lines = body.strip().split("\n")
    assert len(lines) >= 2
    # Required headers all present
    header_line = lines[0].lower()
    for required in ("first_name", "last_name", "email", "phone", "city", "state"):
        assert required in header_line
    # Content-Disposition attachment set
    assert resp.headers.get("content-disposition", "").startswith("attachment")
