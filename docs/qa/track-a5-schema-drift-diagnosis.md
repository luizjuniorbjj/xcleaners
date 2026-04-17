---
type: dba-diagnosis
title: "Track A.5 — Schema Drift Diagnosis (Dev Local vs Migrations)"
project: xcleaners
sprint: "Track A — fix 7 pre-existing tests (backlog-v2)"
agent: "@data-engineer (Tank)"
date: "2026-04-17"
status: PARTIAL_RESOLUTION
parent_track: A
---

# Track A.5 — Schema Drift Diagnosis

## TL;DR

| Métrica | Antes | Depois |
|---|:---:|:---:|
| `tests/test_config.py` passing | 1/2 | **2/2** ✅ |
| `tests/test_recurring_generator.py` passing | 2/8 | **6/8** ✅ |
| **Total dos 10 tests targets** | **3/10** | **8/10** |
| Tests resolvidos por mim (Tank) | — | **+4** |
| Tests resolvidos por Neo previamente | — | **+1** (test_config) |
| Tests ainda failing (NÃO schema drift) | — | **2** |

**Migration 022 estava ausente no DB local** — única causa do schema drift confirmada. Aplicada idempotente. As 2 falhas restantes são bugs de aplicação/test, NÃO infraestrutura de dados.

---

## 1. Inventário de migrations

| # | Nome | Status local (pré-Track A.5) | Status pós-apply |
|:-:|---|:---:|:---:|
| 011-019 | (módulo cleaning, persona, etc.) | ✅ aplicadas | ✅ |
| 020 | `xcleaners_schema_fixes` | ✅ aplicada | ✅ |
| 021 | `pricing_engine_hybrid` | ✅ aplicada | ✅ |
| **022** | **`recurring_pricing_inputs`** | ❌ **ausente** | ✅ **aplicada agora** |
| 023 | `cleaner_earnings` | ✅ aplicada | ✅ |
| 024 | `client_stripe_customer` | ✅ aplicada | ✅ |
| 025 | `booking_payment_tracking` | ✅ aplicada | ✅ |
| 026 | `payment_status_add_processing` | ✅ aplicada | ✅ |

**Não há tabela `schema_migrations`** no DB local — tracking é manual via scripts. Recomendação ops abaixo.

---

## 2. Apply de migration 022 (executado)

**Snapshot baseline:**
- 59 tabelas, `cleaning_client_schedules` com 18 colunas

**Apply (transação completa, idempotente):**
- ✅ +2 tabelas: `cleaning_client_schedule_extras`, `cleaning_schedule_skips`
- ✅ +4 colunas em `cleaning_client_schedules`: `frequency_id`, `adjustment_amount`, `adjustment_reason`, `location_id`
- ✅ +3 índices: `idx_cleaning_client_schedules_frequency`, `idx_cleaning_client_schedules_location`, `idx_cleaning_client_schedule_extras_schedule`, `idx_cleaning_schedule_skips_lookup`
- ✅ Backfill executado: 0 schedules para reescrever (DB local é vazio de dados de prod)
- ✅ COMMENT ON em 5 colunas/tabelas

**Snapshot post:**
- 61 tabelas (+2), `cleaning_client_schedules` com 22 colunas (+4) — alinhado com migration spec

---

## 3. Reescrita cirúrgica da fixture (NÃO era resolvida por migration)

A fixture `tests/fixtures/recurring_schedules.py` foi escrita contra o schema do **ClaWtoBusiness** (CTBu), não do xcleaners. Migration nenhuma vai criar essas colunas porque elas NUNCA existiram em `xcleaners.businesses`.

**`businesses` schema real (xcleaners):**
```
id, slug, name, timezone, cleaning_settings(jsonb), logo_url, status,
stripe_account_id, stripe_account_status, stripe_charges_enabled,
stripe_payouts_enabled, stripe_connected_at, created_at, updated_at
```

**Colunas-fantasma que a fixture tentava inserir** (CTBu legacy):
- `user_id`, `whatsapp_phone`, `phone`, `business_type`, `primary_color`, `welcome_message`, `plan`

**Reescrita aplicada** (Tank, dentro do escopo Track A.5):
- `create_test_business`: INSERT `businesses` simplificado (id/slug/name/timezone/status). Owner user permanece criado mas não-FK.
- `tear_down_business`: DELETE business + best-effort DELETE users WHERE email LIKE 'owner-%@test.local' (cleanup pattern, idempotente)
- `create_test_service`: adicionado campo `slug` (NOT NULL no schema, ausente na fixture original)
- `users` INSERT (já corrigido por Neo): `password_hash → hashed_password`, `name → nome`, `status → is_active TRUE`, `'user' → 'subscriber'`

---

## 4. Estado final dos testes (8/10 PASS)

### ✅ PASSING (resolvidos)
1. `test_secret_key_required` (Neo)
2. `test_secret_key_present` (sempre passou)
3. `test_collect_jobs_joins_schedule_extras` (sempre passou — unit/mock)
4. `test_persist_assignments_calls_create_booking_with_pricing` (sempre passou — unit/mock)
5. `test_skip_date_excludes_booking` (Tank — schema sync resolveu)
6. `test_pause_stops_new_bookings` (Tank — schema sync resolveu)
7. `test_formula_change_does_not_affect_past_bookings` (Tank — schema sync resolveu)
8. `test_frequency_id_missing_graceful_fallback` (Tank — schema sync resolveu)

### ❌ STILL FAILING (NÃO são schema drift)

#### F-1: `test_recurring_generator_end_to_end`
**Erro:** `CheckViolationError: cleaning_client_schedules_preferred_day_of_week_check`
**Constraint:** `CHECK (preferred_day_of_week >= 0 AND preferred_day_of_week <= 6)`
**Causa raiz:** test linha 125 calcula `dom = min(28, today.day + 3)` (ex: 20) e passa como `preferred_day_of_week` no schedule mensal. Comentário do test (linha 120) diz: *"Monthly (preferred_day_of_week repurposed as day-of-month in matcher)"* — ou seja, o test ABUSA da semântica da coluna day-of-week para representar day-of-month no fluxo monthly.
**Tipo:** bug de design do test (Sprint D Track A) OR constraint do schema precisa ser relaxado para suportar reuso. Decisão arquitetural — NÃO é Tank.

#### F-2: `test_pricing_matches_schedule_inputs` (GATE NON-NEGOTIABLE ±$0.01)
**Erro:** `expected $240.01, got $170.00 (delta $70.01). Breakdown: tax=0.00 discount=0.00 adjustment=0.00`
**Causa raiz:** pricing engine retorna apenas o base price + extras, IGNORANDO frequency discount, sales tax, e adjustment_amount. A fixture seeda corretamente: NYC area com tax 4.5% (linha 116-123 da fixture), Weekly frequency 15% disc, adjustment -$29.58. Algo no fluxo `recurring_generator → create_booking_with_pricing` não está propagando `frequency_id`, `location_id`, `adjustment_amount` para o pricing engine.
**Tipo:** bug de aplicação CRÍTICO (Sprint D Track A — gate ±$0.01 nunca foi atendido). NÃO é schema drift. Domínio: @dev (Neo) ou @architect (Aria).

---

## 5. Recomendações

### Para esta sessão
1. **Commit do que está resolvido:** test_config + fixture rewriteada + migration 022 ledger. Total: +5 tests passing (de 142/149 para 147/149). 2 failing isolados em backlog claro.
2. **F-1 e F-2:** documentar como **backlog-v3** (não bloqueia cutover 3Sisters). F-2 merece atenção @architect — pode ser bug latente em produção se recurring auto-gen estiver ativo.

### Para próximas sessões (ops/processo)
3. **Criar tabela `schema_migrations`** no padrão `(version INT PK, applied_at TIMESTAMPTZ)` para tracking automático. Útil para evitar gaps tipo este (022 órfã localmente).
4. **Migration applicator script** que lê diretório, faz diff vs `schema_migrations`, dry-run por default, apply opcional. Padrão da sessão tarde 2026-04-17 já estabeleceu Python+asyncpg como veículo.
5. **Pre-test hook** que verifica `SELECT version FROM schema_migrations WHERE version >= 020` antes de rodar suite — falha rápida com mensagem clara em vez de descascar cebola test-a-test.

---

## 6. Garantia de reversibilidade

Migration 022 tem rollback dedicado: `database/migrations/rollback_022.sql`. Para reverter localmente:
```bash
cd C:/xcleaners
python -c "import asyncio,asyncpg,os;from dotenv import load_dotenv;load_dotenv()
async def m():
  c=await asyncpg.connect(os.getenv('DATABASE_URL'))
  with open('database/migrations/rollback_022.sql') as f: await c.execute(f.read())
  await c.close()
asyncio.run(m())"
```

Fixture rewrite é em working tree (não commitada ainda). `git checkout tests/fixtures/recurring_schedules.py` reverte instantaneamente.

---

*— Tank, the Sage. Programs loaded, schemas alinhados, verdade documentada.*
