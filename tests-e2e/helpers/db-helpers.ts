/**
 * DB Helpers — direct PostgreSQL access for test fixtures.
 *
 * Used by fixtures to:
 *   - Seed test bookings with controlled dates/prices
 *   - Reset cancellation_policy between tests
 *   - Cleanup created data after suite
 *   - Verify backend state without going through UI
 *
 * WARNING: points at prod Railway. Never run destructive queries
 * that touch anything outside business_id = E2E Testing Co.
 */
import { Pool } from 'pg';
import * as dotenv from 'dotenv';
import * as path from 'path';

const envName = process.env.TEST_ENV || 'prod';
dotenv.config({ path: path.resolve(__dirname, `../.env.${envName}`) });

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
  max: 5,
  idleTimeoutMillis: 30_000,
});

/** Resolve once and cache the E2E business UUID so fixtures don't re-query every run. */
let _bizIdCache: string | null = null;
export async function getE2EBusinessId(): Promise<string> {
  if (_bizIdCache) return _bizIdCache;
  const res = await pool.query<{ id: string }>(
    "SELECT id::text AS id FROM businesses WHERE slug = $1",
    [process.env.BUSINESS_SLUG || 'e2e-testing-co']
  );
  if (res.rows.length === 0) {
    throw new Error(
      `E2E business "${process.env.BUSINESS_SLUG}" not found. Run seed script first.`
    );
  }
  _bizIdCache = res.rows[0].id;
  return _bizIdCache;
}

/** Resolve user ID by email — safe lookup used in auth/role assertions. */
export async function getUserId(email: string): Promise<string> {
  const res = await pool.query<{ id: string }>(
    "SELECT id::text AS id FROM users WHERE email = $1",
    [email]
  );
  if (res.rows.length === 0) throw new Error(`User ${email} not found`);
  return res.rows[0].id;
}

/** Resolve homeowner's cleaning_client row (created when they accepted invite). */
export async function getHomeownerClientId(email: string): Promise<string | null> {
  const bizId = await getE2EBusinessId();
  const userId = await getUserId(email);
  const res = await pool.query<{ id: string }>(
    "SELECT id::text AS id FROM cleaning_clients WHERE business_id = $1 AND user_id = $2",
    [bizId, userId]
  );
  return res.rows[0]?.id ?? null;
}

/**
 * Reset cancellation_policy for E2E business to a known state.
 * Call in test setup to ensure deterministic baseline.
 */
export async function resetPolicy(policy?: {
  hours_before?: number;
  fee_percentage?: number;
  max_reschedules_per_booking?: number;
}): Promise<void> {
  const bizId = await getE2EBusinessId();
  const resolved = {
    hours_before: policy?.hours_before ?? 24,
    fee_percentage: policy?.fee_percentage ?? 50,
    max_reschedules_per_booking: policy?.max_reschedules_per_booking ?? 1,
  };
  await pool.query(
    `UPDATE businesses
       SET cleaning_settings = jsonb_set(
         COALESCE(cleaning_settings, '{}'::jsonb),
         '{cancellation_policy}',
         $1::jsonb
       ),
       updated_at = NOW()
     WHERE id = $2`,
    [JSON.stringify(resolved), bizId]
  );
}

/** Read the currently effective policy (merged — we read the raw stored value). */
export async function readPolicy(): Promise<Record<string, unknown>> {
  const bizId = await getE2EBusinessId();
  const res = await pool.query<{ p: unknown }>(
    `SELECT cleaning_settings->'cancellation_policy' AS p
       FROM businesses WHERE id = $1`,
    [bizId]
  );
  return (res.rows[0]?.p as Record<string, unknown>) ?? {};
}

export interface TestBookingSeed {
  clientId: string;
  scheduledDate: string;   // 'YYYY-MM-DD'
  scheduledStart: string;  // 'HH:MM:SS'
  scheduledEnd?: string;
  status?: 'scheduled' | 'confirmed' | 'draft' | 'rescheduled';
  quotedPrice?: number;
  rescheduleCount?: number;
  serviceName?: string;
}

/**
 * Create a test booking with controlled parameters.
 * Returns booking UUID so teardown can delete it precisely.
 */
export async function createTestBooking(seed: TestBookingSeed): Promise<string> {
  const bizId = await getE2EBusinessId();
  const end = seed.scheduledEnd ?? addHours(seed.scheduledStart, 2);

  // First resolve or create a default service for the business
  let svcId = (await pool.query<{ id: string }>(
    "SELECT id::text AS id FROM cleaning_services WHERE business_id = $1 AND is_active = true LIMIT 1",
    [bizId]
  )).rows[0]?.id;

  if (!svcId) {
    svcId = (await pool.query<{ id: string }>(
      `INSERT INTO cleaning_services (business_id, name, slug, category, base_price, is_active)
         VALUES ($1, 'E2E Standard', 'e2e-standard', 'residential', 115, true)
         RETURNING id::text AS id`,
      [bizId]
    )).rows[0].id;
  }

  const res = await pool.query<{ id: string }>(
    `INSERT INTO cleaning_bookings (
       business_id, client_id, service_id,
       scheduled_date, scheduled_start, scheduled_end,
       status, quoted_price, reschedule_count,
       estimated_duration_minutes
     )
     VALUES ($1,$2,$3,$4::date,$5::time,$6::time,$7,$8,$9,120)
     RETURNING id::text AS id`,
    [
      bizId,
      seed.clientId,
      svcId,
      seed.scheduledDate,
      seed.scheduledStart,
      end,
      seed.status ?? 'scheduled',
      seed.quotedPrice ?? 115,
      seed.rescheduleCount ?? 0,
    ]
  );
  return res.rows[0].id;
}

function addHours(time: string, hours: number): string {
  const [h, m, s] = time.split(':').map(Number);
  let totalSec = h * 3600 + m * 60 + (s || 0) + hours * 3600;
  // Clamp at 23:59:00 instead of overflowing past midnight — TIME column
  // rejects > 24h. The exact end hour is irrelevant for our gate logic.
  if (totalSec >= 24 * 3600) totalSec = 23 * 3600 + 59 * 60;
  const hh = String(Math.floor(totalSec / 3600)).padStart(2, '0');
  const mm = String(Math.floor((totalSec % 3600) / 60)).padStart(2, '0');
  return `${hh}:${mm}:00`;
}

/** Delete a test booking after test completes. */
export async function deleteBooking(bookingId: string): Promise<void> {
  const bizId = await getE2EBusinessId();
  // Defense: only delete bookings inside E2E business — never touch real data.
  await pool.query(
    "DELETE FROM cleaning_bookings WHERE id = $1 AND business_id = $2",
    [bookingId, bizId]
  );
}

/** Nuke every booking in E2E business. Called in global teardown. */
export async function cleanupAllE2EBookings(): Promise<number> {
  const bizId = await getE2EBusinessId();
  const res = await pool.query(
    "DELETE FROM cleaning_bookings WHERE business_id = $1",
    [bizId]
  );
  return res.rowCount || 0;
}

/** Ensure test homeowner has a cleaning_client row + a default team for bookings. */
export async function ensureHomeownerClientLink(email: string): Promise<string> {
  const bizId = await getE2EBusinessId();
  const userId = await getUserId(email);

  let clientId = await getHomeownerClientId(email);
  if (clientId) return clientId;

  clientId = (await pool.query<{ id: string }>(
    `INSERT INTO cleaning_clients (
       business_id, user_id, first_name, last_name, email, phone,
       status, address_line1, city, state, zip_code, source
     ) VALUES ($1,$2,'E2E','Homeowner',$3,'+15555550100','active','123 Test Ave','Chicago','IL','60601','manual')
     RETURNING id::text AS id`,
    [bizId, userId, email]
  )).rows[0].id;
  return clientId;
}

export async function closeDb(): Promise<void> {
  await pool.end();
}

export { pool };
