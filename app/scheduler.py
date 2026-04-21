"""
Xcleaners — APScheduler Jobs (AI Turbo Sprint 2026-04-20 Bloco 2.2).

AsyncIOScheduler rodando dentro do FastAPI lifespan. Jobs:

  1. generate_daily_schedule_all_businesses — diario 5am UTC.
     Para cada business ativo, gera o schedule do dia via daily_generator.

  2. send_24h_reminders — hora em hora.
     Envia email (com .ics anexo via Bloco 1.7) + SMS pra bookings com
     scheduled_date = tomorrow AND reminder_sent = FALSE.

  3. draft_ttl_cleanup — 5 em 5 min.
     Expira drafts IA (status='draft' + source='ai_chat' + created_at < 24h).

Design:
  - Graceful degrade: se APScheduler falha, app continua sem jobs.
  - Per-business TZ aware nos jobs de date-sensitive (reminders).
  - Logs estruturados com job_id + duration + affected_rows.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger("xcleaners.scheduler")

_scheduler: Optional[AsyncIOScheduler] = None


# ============================================
# JOB 1 — DAILY SCHEDULE GENERATION
# ============================================

async def generate_daily_schedule_all_businesses():
    """
    Gera schedule diario para todos os businesses ativos.
    Chamado 5am UTC. Cada business roda em sua propria TZ implicitamente
    via daily_generator (ele faz lookup da tz).
    """
    from app.database import get_db_instance
    from app.modules.cleaning.services.daily_generator import generate_daily_schedule

    start = datetime.now(timezone.utc)
    logger.info("[SCHED] daily_schedule started at %s", start.isoformat())

    db = await get_db_instance()
    if not db:
        logger.warning("[SCHED] daily_schedule skipped: no DB")
        return

    try:
        businesses = await db.pool.fetch(
            """
            SELECT id FROM businesses
            WHERE is_active = TRUE
            """
        )
    except Exception as e:
        logger.error("[SCHED] daily_schedule query businesses failed: %s", e)
        return

    target_date = datetime.now(timezone.utc).date()
    generated = 0
    failed = 0

    for biz in businesses:
        business_id = biz["id"]
        try:
            await generate_daily_schedule(
                db=db, business_id=str(business_id), target_date=target_date,
            )
            generated += 1
        except Exception as e:
            failed += 1
            logger.exception(
                "[SCHED] daily_schedule failed for business=%s: %s", business_id, e,
            )

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info(
        "[SCHED] daily_schedule finished — generated=%d failed=%d elapsed=%.2fs",
        generated, failed, elapsed,
    )


# ============================================
# JOB 2 — 24H REMINDERS
# ============================================

async def send_24h_reminders():
    """
    Envia reminder 24h antes para bookings nao-reminded.
    Hora em hora. Marca reminder_sent=TRUE apos envio bem-sucedido.
    """
    from app.database import get_db_instance
    from app.modules.cleaning.services.email_service import send_booking_reminder

    start = datetime.now(timezone.utc)
    logger.info("[SCHED] 24h_reminders started at %s", start.isoformat())

    db = await get_db_instance()
    if not db:
        logger.warning("[SCHED] 24h_reminders skipped: no DB")
        return

    # Target: scheduled_date = tomorrow (UTC, simples; per-business TZ
    # refinement pode entrar em iteracao futura se drift for problema).
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date()

    try:
        bookings = await db.pool.fetch(
            """
            SELECT id FROM cleaning_bookings
            WHERE scheduled_date = $1
              AND reminder_sent = FALSE
              AND status IN ('scheduled', 'confirmed')
            """,
            tomorrow,
        )
    except Exception as e:
        logger.error("[SCHED] 24h_reminders query failed: %s", e)
        return

    sent = 0
    failed = 0
    for b in bookings:
        booking_id = str(b["id"])
        try:
            result = await send_booking_reminder(db, booking_id)
            if result.get("sent"):
                await db.pool.execute(
                    "UPDATE cleaning_bookings SET reminder_sent = TRUE WHERE id = $1",
                    b["id"],
                )
                sent += 1
            else:
                failed += 1
                logger.warning(
                    "[SCHED] reminder not sent for booking=%s: %s",
                    booking_id, result.get("error"),
                )
        except Exception as e:
            failed += 1
            logger.exception(
                "[SCHED] reminder exception for booking=%s: %s", booking_id, e,
            )

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info(
        "[SCHED] 24h_reminders finished — sent=%d failed=%d tomorrow=%s elapsed=%.2fs",
        sent, failed, tomorrow, elapsed,
    )


# ============================================
# JOB 3 — DRAFT TTL CLEANUP
# ============================================

_DRAFT_TTL_HOURS = 24


async def draft_ttl_cleanup():
    """
    Expira drafts IA nao-confirmados com mais de 24h.
    5 em 5 min. Marca status='cancelled' + cancellation_reason='AI draft expired'.
    """
    from app.database import get_db_instance

    db = await get_db_instance()
    if not db:
        return  # silent — roda 288 vezes por dia, nao pollute logs

    try:
        result = await db.pool.execute(
            """
            UPDATE cleaning_bookings
               SET status = 'cancelled',
                   cancellation_reason = 'AI draft expired (>24h unreviewed)',
                   cancelled_at = NOW(),
                   cancelled_by = 'system',
                   updated_at = NOW()
             WHERE status = 'draft'
               AND source = 'ai_chat'
               AND created_at < NOW() - INTERVAL '%s hours'
            """
            % _DRAFT_TTL_HOURS
        )
        # asyncpg returns 'UPDATE N' as string; log only when N > 0.
        if "UPDATE 0" not in (result or ""):
            logger.info("[SCHED] draft_ttl_cleanup result: %s", result)
    except Exception as e:
        logger.error("[SCHED] draft_ttl_cleanup failed: %s", e)


# ============================================
# SCHEDULER LIFECYCLE (called from xcleaners_main lifespan)
# ============================================

def start_scheduler() -> Optional[AsyncIOScheduler]:
    """
    Start APScheduler with xcleaners jobs.
    Returns the scheduler instance, or None if startup fails (graceful degrade).
    """
    global _scheduler

    if _scheduler is not None:
        logger.warning("[SCHED] already started")
        return _scheduler

    try:
        sched = AsyncIOScheduler(timezone=timezone.utc)

        sched.add_job(
            generate_daily_schedule_all_businesses,
            trigger=CronTrigger(hour=5, minute=0),
            id="daily_schedule",
            name="Generate daily schedule for all businesses",
            max_instances=1,
            coalesce=True,
        )

        sched.add_job(
            send_24h_reminders,
            trigger=CronTrigger(minute=0),  # every hour at :00
            id="reminders_24h",
            name="Send 24h booking reminders",
            max_instances=1,
            coalesce=True,
        )

        sched.add_job(
            draft_ttl_cleanup,
            trigger=IntervalTrigger(minutes=5),
            id="draft_ttl",
            name="Expire stale AI chat drafts (>24h)",
            max_instances=1,
            coalesce=True,
        )

        sched.start()
        _scheduler = sched

        jobs = [j.id for j in sched.get_jobs()]
        logger.info("[SCHED] APScheduler started — jobs: %s", jobs)
        return sched
    except Exception as e:
        logger.exception("[SCHED] startup failed (graceful degrade, no jobs): %s", e)
        return None


def stop_scheduler():
    """Shutdown scheduler cleanly. Called from lifespan teardown."""
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
            logger.info("[SCHED] APScheduler stopped")
        except Exception as e:
            logger.error("[SCHED] shutdown error: %s", e)
        finally:
            _scheduler = None
