# Sprint D — Recurring Auto-Generator + Payroll 60% Split

**Criado:** 2026-04-16 (apos validacao Stripe Connect)
**Objetivo:** Fechar os 2 verdadeiros blockers de cutover 3Sisters.
**Duracao estimada:** 3-5 dias totais (paralelizaveis).

---

## Estrategia: 2 tracks independentes em VS Code

Track A e Track B sao 100% independentes (zero overlap de arquivos). Abra 2 sessoes Claude Code em VS Code (2 terminais) e deixe rodar em paralelo. Smith verifica cada entrega.

### Regras de paralelismo

- Ambos os terminais cwd em `C:/xcleaners`
- Cada track modifica arquivos diferentes (ver tabela abaixo) → zero conflito de merge
- Se um track precisar de migration, numere: Track A usa `022_recurring_*.sql`, Track B usa `023_payroll_*.sql`
- Commit por track em branch propria (`feat/recurring-auto-gen`, `feat/payroll-split`) e merge no fim

---

## Track A — Recurring Auto-Generator

> ⚠️ **REVISADO 2026-04-16 pos ADR-002** — substitui versao anterior (insuficiente: nao fechava Smith C1 M2 + R9)
> **Reference:** `C:/xcleaners/docs/architecture/adr-002-recurring-auto-generator.md` (PRIMARY)
> **Format:** baseado em `docs/stories/1.1.pricing-engine-hybrid.md`

**Agente:** @dev (Neo)
**Branch:** `feat/recurring-auto-gen` (isolada de Track B `feat/payroll-split`)
**Duracao estimada:** 1.5-2 dias
**Risco:** BAIXO (infra ~80% feita; cirurgia pontual em `_persist_assignments`)
**Depends on:** ADR-002 accepted ✓ · Story 1.1 Tasks 2+6 Ready for Review ✓ · Migration 021 aplicada ✓

---

### Business Context

**3Sisters migra para xcleaners Semana 7.** Bookings recorrentes (Weekly/Biweekly/Monthly) representam **>80% da receita** — validado no competitive analysis (71 completed bookings de cliente real via Launch27). Se o pricing recorrente divergir do Launch27 em **qualquer booking** alem de $0.01, o cutover falha e Ana perde confianca.

**Paradoxo do nome "Auto-Generator":** a infra existe. `daily_generator.py` (1200 LOC, 5-step orchestrator com Redis lock) + `recurrence_engine.py` + `frequency_matcher.py` + `booking_service.create_booking_with_pricing` (Story 1.1 C1) — tudo funcional.

**Gap real (descoberto por Aria na auditoria do codigo):** `daily_generator._persist_assignments` faz `INSERT INTO cleaning_bookings` **direto**, usando `schedule.agreed_price` como `quoted_price`. **Ignora o pricing_engine da Story 1.1 completamente.** Cada booking recorrente gerado hoje tem `price_snapshot = NULL`, `tax_amount = 0`, `discount_amount = 0`, `adjustment_amount = 0`.

Isso e:
- **Smith C1 finding M2** — "pricing divergence silenciosa em /schedule/generate"
- **R9 aberto** — `cleaning_client_schedules.frequency_id` nao existe (FK foi adicionada so em tabela legacy `cleaning_recurring_schedules`)

Mesmo problema, duas caras. **Track A fecha ambos com uma integracao cirurgica** — sem sistema novo, sem reescrita.

---

### User Story

**As** Ana Afonso (owner 3Sisters Cleaning NYC),
**I want** que bookings gerados automaticamente a partir de recurring schedules usem **exatamente o mesmo pricing** que bookings manuais (Story 1.1: formula + override + discount + adjustment + tax com snapshot imutavel),
**So that** quando eu migrar do Launch27 para xcleaners, todos os meus 20+ clientes Weekly continuem pagando os mesmos valores que pagam hoje, o IRS recebe sales tax correto automaticamente, e eu tenho audit trail JSONB para qualquer disputa.

**Example 30-day window pos-cutover (3Sisters Weekly Basic cliente F1):**

```
Dia 1: Generator roda 02:00 UTC → varre schedules next 14d → cria 4 bookings para cliente F1
       Cada booking: price_snapshot JSONB imutavel com { final=240.01, tax=10.34, discount=45.75, adj=-29.58 }
Dia 8: Generator roda, cliente ainda tem mais 4 bookings gerados (next 14d window rolling)
Dia 15: Ana muda adjustment de -29.58 para -30.00 no schedule
       Proximos bookings gerados refletem novo valor; bookings ja no banco permanecem em -29.58 (imutavel)
Dia 22: Cliente F1 viaja 2 semanas — Ana cria 2 skips em cleaning_schedule_skips
       Generator ignora esses dias; bookings ja criados ficam (Ana cancela manualmente se quiser)
```

---

### Contexto tecnico existente

| Componente | Status | Arquivo | Observacao |
|-----------|--------|---------|-----------|
| Daily orchestrator (5-step) | ✅ FUNCIONA | `services/daily_generator.py` | Redis lock, idempotent |
| Next-occurrence advancer | ✅ FUNCIONA | `services/recurrence_engine.py` | 4 modes: weekly/biweekly/monthly/sporadic |
| Frequency matcher | ✅ FUNCIONA | `services/frequency_matcher.py` | `matches_date()` + `compute_next_occurrence()` |
| Schedule table | ✅ EXISTE | `cleaning_client_schedules` (mig 012) | status: active/paused/cancelled; **FALTAM pricing inputs** |
| Booking+Pricing factory | ✅ EXISTE | `services/booking_service.py` | `create_booking_with_pricing` materializa snapshot |
| Pricing engine | ✅ LIVE | `services/pricing_engine.py` | Story 1.1 gate 91.88% coverage |

**Gap real:** `daily_generator._persist_assignments` (linha ~672) insere booking sem passar pelo pricing engine. Fix = delegar a `booking_service.create_booking_with_pricing`.

---

### Acceptance Criteria

#### AC1 — Database Migration 022 (idempotente, additive)

Arquivo: `database/migrations/022_recurring_pricing_inputs.sql`

**Must include (all `IF NOT EXISTS` / `ON CONFLICT`):**

- `ALTER TABLE cleaning_client_schedules` ADD:
  - `frequency_id UUID REFERENCES cleaning_frequencies(id) ON DELETE SET NULL`
  - `adjustment_amount NUMERIC(10,2) DEFAULT 0.00`
  - `adjustment_reason VARCHAR(255)`
  - `location_id UUID REFERENCES cleaning_areas(id) ON DELETE SET NULL`
- `CREATE TABLE cleaning_client_schedule_extras (schedule_id UUID, extra_id UUID, qty INT DEFAULT 1 CHECK >=1, PRIMARY KEY(schedule_id, extra_id))` com CASCADE FKs
- `CREATE TABLE cleaning_schedule_skips (id UUID PK, schedule_id UUID, skip_date DATE, reason VARCHAR(255), created_by UUID, created_at TIMESTAMPTZ, UNIQUE(schedule_id, skip_date))`
- `CREATE INDEX idx_cleaning_schedule_skips_lookup ON cleaning_schedule_skips(schedule_id, skip_date)`
- **Backfill `frequency_id`:** `UPDATE cleaning_client_schedules SET frequency_id = f.id FROM cleaning_frequencies f WHERE crs.frequency_id IS NULL AND f.business_id=crs.business_id AND LOWER(crs.frequency)=LOWER(f.name)`
- **Backfill `location_id`:** = `cleaning_areas WHERE is_default=TRUE` per business_id
- `RAISE NOTICE` para rows nao-mapeadas (ex: `frequency='sporadic'` sem match — esperado)
- `COMMENT ON COLUMN cleaning_client_schedules.agreed_price IS 'DEPRECATED 2026-04-16 — price calculado por pricing_engine em runtime; manter para audit historical. Nao usado em bookings gerados post-migration 022.'`

Rollback: `database/migrations/rollback_022.sql` — destructive com warnings, reverte 4 ALTER + 2 DROP TABLE.

**Migration deve ser safe to re-run** (teste: aplicar 2x seguidas sem erro).

#### AC2 — `daily_generator._persist_assignments` delega a `booking_service.create_booking_with_pricing`

Modificar `app/modules/cleaning/services/daily_generator.py`:

- Substituir o bloco de `INSERT INTO cleaning_bookings` (~linha 672-703) pela chamada a `create_booking_with_pricing(...)` com kwargs derivados do `assignment` dict + schedule-level inputs (tier, extras, frequency_id, adjustment_amount, adjustment_reason, location_id)
- Para UPDATE path (booking unconfirmed ja existe), manter UPDATE direto OU delete+recreate para garantir snapshot fresh
- **NAO mexer** em bookings com `status IN ('confirmed', 'in_progress', 'completed')` — o filtro atual ja protege isso

**Error handling:**
- `PricingConfigError` durante `create_booking_with_pricing` → log WARNING, skip schedule, continuar com proximas. Booking NAO criado nesse caso.
- Registrar em lista `pricing_failures` incluida no response do orchestrator.

#### AC3 — `daily_generator._collect_jobs` expõe pricing inputs do schedule

Modificar `app/modules/cleaning/services/daily_generator.py`:

- Expandir query SQL de recurring schedules para incluir: `cs.frequency_id`, `cs.adjustment_amount`, `cs.adjustment_reason`, `cs.location_id`, `s.tier AS service_tier`
- LEFT JOIN `cleaning_client_schedule_extras` + `cleaning_extras` (aggregate extras como JSON_AGG ou fetch separado)
- LEFT JOIN NOT EXISTS check em `cleaning_schedule_skips (schedule_id, skip_date=target_date)` — pular schedules com skip ativo
- Cada job dict retornado inclui os novos campos: `schedule_extras[]`, `frequency_id`, `adjustment_amount`, `adjustment_reason`, `location_id`, `service_tier`

#### AC4 — Novo endpoint `POST /internal/recurring/generate-window`

Arquivo: `app/modules/cleaning/routes/schedule.py` (ADICIONAR endpoint)

```
POST /api/v1/clean/internal/recurring/generate-window
Headers: X-Internal-Signature: {HMAC_SHA256(body, INTERNAL_CRON_SECRET)}
Body: { "business_id": "uuid", "days": 14 }

Response 200:
{
  "generated": 28,
  "skipped_by_skip_table": 3,
  "pricing_failures": [{"schedule_id": "uuid", "reason": "..."}],
  "summary": {"window_days": 14, "total_schedules_scanned": 42}
}
```

**Auth:** HMAC via env `INTERNAL_CRON_SECRET` (nao JWT — cron externo). Body signed.
**Rate limit:** 1 req/min por business_id (cron normal roda 1x/dia).
**Idempotencia:** Redis lock per `(business_id, date)` ja garantido pelo `daily_generator`.

#### AC5 — Novo service `recurring_generator.py` (window orchestrator)

Arquivo NEW: `app/modules/cleaning/services/recurring_generator.py`

```python
async def generate_window(
    db: Database,
    business_id: UUID,
    start_date: date,
    end_date: date,
) -> dict:
    """
    Itera daily_generator.generate_daily_schedule de start_date a end_date inclusive.
    Agrega pricing_failures de cada dia.
    """
```

- Itera `daily_generator.generate_daily_schedule` para cada data em [start_date, end_date]
- Agrega resultados (total gerados, skipped, pricing_failures)
- Log estruturado por dia + summary final
- ~80 LOC

#### AC6 — Skip mechanism funcional (cleaning_schedule_skips)

- `_collect_jobs` filtra via `NOT EXISTS (SELECT 1 FROM cleaning_schedule_skips WHERE schedule_id=cs.id AND skip_date=target_date)`
- Bookings ja gerados para data com skip posterior **NAO sao auto-cancelados** (owner decide manualmente) — documentado em comment no codigo
- UI da skips-manager fica para Story futura (v1: owner insere via admin query ou endpoint minimo se Luiz priorizar)

#### AC7 — Observability obrigatoria

Logs estruturados com prefix `[RECURRING]`:

```python
# Em recurring_generator.generate_window
logger.info("[RECURRING] Starting window %s → %s for business=%s", start_date, end_date, business_id)

# Em daily_generator._collect_jobs (apos fetch)
logger.info("[RECURRING] Scanned %d schedules, skipped %d via cleaning_schedule_skips", scanned, skipped)

# Em _persist_assignments (success)
logger.info("[RECURRING] Generated booking=%s schedule=%s client=%s final=$%s tier=%s override=%s",
            booking_id, schedule_id, client_id, final_amount, tier, override_applied)

# Em _persist_assignments (PricingConfigError)
logger.warning("[RECURRING] Pricing failure for schedule=%s: %s. Booking SKIPPED.", schedule_id, error)
```

Response do endpoint DEVE incluir `pricing_failures` array para owner revisar.

#### AC8 — Test Gate NAO-NEGOCIAVEL (±$0.01)

**Fixture F1 da Story 1.1 (3Sisters real booking $240.01) deve replicar via path recurring.**

Criar schedule com pricing inputs equivalentes aos de F1 (Weekly 15% + Stairs + adjustment -$29.58 + tax 4.5% NYC). Gerar booking via `recurring_generator.generate_window`. Assert `booking.price_snapshot.final_amount == 240.01 ± 0.01`.

Se nao bater → **FAIL imediato**. Story NAO vai para QA ate bater.

---

### Tasks / Subtasks

#### Task 1 — Migration 022 (0.3 day) [AC1]

- [x] T1.1 — Criar `database/migrations/022_recurring_pricing_inputs.sql` com BEGIN/COMMIT ✓
- [x] T1.2 — `ALTER TABLE cleaning_client_schedules` ADD 4 colunas (all IF NOT EXISTS) ✓
- [x] T1.3 — `CREATE TABLE cleaning_client_schedule_extras` + index ✓
- [x] T1.4 — `CREATE TABLE cleaning_schedule_skips` + index ✓
- [x] T1.5 — Backfill `frequency_id` via LOWER matching ✓
- [x] T1.6 — Backfill `location_id` via default area ✓
- [x] T1.7 — DO $$ block com RAISE NOTICE para rows nao-mapeadas ✓ (duas notices — frequency + location)
- [x] T1.8 — COMMENT ON COLUMN agreed_price DEPRECATED ✓
- [x] T1.9 — Criar `rollback_022.sql` com warnings destructive ✓
- [ ] T1.10 — Testar idempotencia: aplicar 2x em Docker PG local — **PENDING (requer Docker PG)**
- [ ] T1.11 — Aplicar em Docker PG local + validar backfill coverage — **PENDING (requer Docker PG)**

#### Task 2 — `daily_generator._collect_jobs` pricing inputs (0.3 day) [AC3, AC6]

- [x] T2.1 — Expandir query SQL de recurring schedules com pricing inputs ✓
- [x] T2.2 — Adicionar fetch de schedule_extras (ANY($1::uuid[])) + group by schedule_id ✓
- [x] T2.3 — Adicionar `NOT EXISTS cleaning_schedule_skips` na query ✓
- [x] T2.4 — Expor novos campos no dict `jobs[i]`: schedule_extras, frequency_id, adjustment_amount, adjustment_reason, location_id, service_tier ✓
- [x] T2.5 — Log `[RECURRING] Scanned X, skipped Y via skip_table` ✓

#### Task 3 — `daily_generator._persist_assignments` delega a booking_service (0.3 day) [AC2, AC7]

- [x] T3.1 — Importar `create_booking_with_pricing` + `PricingConfigError` ✓
- [x] T3.2 — Substituir INSERT bruto por chamada a `create_booking_with_pricing` (schedule branch) ✓
- [x] T3.3 — **Smith L2**: DELETE+recreate em existing unconfirmed (garantir snapshot fresh) ✓
- [x] T3.4 — try/except PricingConfigError → log warning + append a pricing_failures ✓
- [x] T3.5 — Log `[RECURRING] Generated booking=...` com tier + override + extras ✓
- [x] T3.6 — Retornar (persisted, pricing_failures) tupla + propagar em summary ✓
- [x] T3.7 — **Bugfix bonus**: `bulk_advance` apenas para schedules com booking gerado com sucesso (evita schedule com erro persistente perder ocorrências) ✓

#### Task 4 — New `recurring_generator.py` window orchestrator (0.3 day) [AC5]

- [x] T4.1 — Criar `app/modules/cleaning/services/recurring_generator.py` ✓
- [x] T4.2 — `async generate_window(db, business_id, start_date, end_date) -> dict` ✓
- [x] T4.3 — Loop interno iterando `daily_generator.generate_daily_schedule` ✓
- [x] T4.4 — Agregar: generated, skipped_by_skip_table, pricing_failures (com date tag), unassigned, conflicts ✓
- [x] T4.5 — Log summary final `[RECURRING] Window complete:` com stats ✓

#### Task 5 — New endpoint + HMAC auth (0.2 day) [AC4]

- [x] T5.1 — Rota `POST /api/v1/clean/internal/recurring/generate-window` em **novo arquivo** `recurring_routes.py` (isolamento de business-slug-scoped routes) ✓
- [x] T5.2 — Pydantic `GenerateWindowRequest {business_id: UUID, days: int Field(1..90)=14}` + `GenerateWindowResponse` ✓
- [x] T5.3 — HMAC verify via `_verified_body` dependency + `hmac.compare_digest` ✓
- [x] T5.4 — Response model completo com `pricing_failures[]` ✓
- [x] T5.5 — Env var `INTERNAL_CRON_SECRET` em `.env.example` ✓
- [x] T5.6 — Registrar router em `xcleaners_main.py` (import + include_router) ✓

#### Task 6 — Cron trigger (0.1 day) [AC4]

- [x] T6.1 — Opção A escolhida: Railway cron (primeira) + Opção B documentada (GitHub Actions fallback) ✓
- [x] T6.2 — `scripts/trigger_recurring.sh` com openssl HMAC + curl + exit codes ✓
- [x] T6.3 — Schedule `0 2 * * *` (02:00 UTC) documentado ✓
- [x] T6.4 — `docs/ops/recurring-cron-setup.md` (~220 LOC — inclui troubleshooting, monitoring, alerts) ✓

#### Task 7 — Tests integration + unit (0.4 day) [AC8]

- [x] T7.1 — `tests/fixtures/recurring_schedules.py` — builders completos (business, client, service, extras, location, schedule, skip, team) ✓
- [x] T7.2 — `tests/test_recurring_generator.py` ✓
- [x] T7.3 — 8 mandatory tests implementados ✓
  - Test 1: end_to_end (3 frequencies × 14d window)
  - Test 2: F1 replay **±$0.01 GATE** (Weekly Basic + Stairs + adj −$29.58 + 4.5% tax = $240.01)
  - Test 3: skip date exclude (**Smith L3**: INSERT skip via raw SQL `add_schedule_skip` helper, NO endpoint)
  - Test 4: pause stops new bookings
  - Test 5: formula change does NOT affect past booking (snapshot immutability)
  - Test 6: frequency_id NULL graceful fallback (discount=0)
  - Test 7: unit — `_collect_jobs` JOIN schedule_extras (mock db)
  - Test 8: unit — `_persist_assignments` calls `create_booking_with_pricing` (mock patch)
- [ ] T7.4 — `pytest tests/test_recurring_generator.py -v` execucao — **PENDING (requer Docker PG + migrations 021+022 aplicadas)**
- [ ] T7.5 — Coverage `recurring_generator.py` >= 85% — **PENDING (requer execução)**

### Smith L1-L4 in-flight application status

- **L1** ✓ — AC2 + T3.2 mencionam função `_persist_assignments` por nome (linha 602 real), nao linha numérica antiga
- **L2** ✓ — T3.3 delete+recreate implementado (sem ambiguidade UPDATE)
- **L3** ✓ — Test 3 usa `add_schedule_skip` helper (raw SQL fixture, zero endpoint novo)
- **L4** ✓ — Migration 022 backfill usa LOWER matching (aproveitando seeds migration 021)

---

### File List

#### NEW (Track A)

**Backend/DB:**
- `database/migrations/022_recurring_pricing_inputs.sql` (~150 LOC SQL)
- `database/migrations/rollback_022.sql` (~50 LOC SQL)
- `app/modules/cleaning/services/recurring_generator.py` (~80 LOC)
- `scripts/trigger_recurring.sh` (~30 LOC)
- `docs/ops/recurring-cron-setup.md` (~50 LOC)

**Tests:**
- `tests/fixtures/recurring_schedules.py` (~100 LOC)
- `tests/test_recurring_generator.py` (~400 LOC)

#### MODIFIED (Track A)

- `app/modules/cleaning/services/daily_generator.py` (~80 LOC delta em `_collect_jobs` + `_persist_assignments`)
- `app/modules/cleaning/routes/schedule.py` (~50 LOC NEW endpoint)
- `.env.example` (1 LOC: `INTERNAL_CRON_SECRET=change-me`)

#### NO-TOUCH (isolado)

- `services/pricing_engine.py` — zero mudanca
- `services/booking_service.py` — zero mudanca (apenas usado como consumidor)
- `services/recurrence_engine.py` — zero mudanca
- `services/frequency_matcher.py` — zero mudanca
- Track B files (payroll_service, payroll_routes, payroll-manager.js, migration 023) — zero overlap

**Total:** 8 arquivos NEW + 3 MODIFIED, ~990 LOC novas/modificadas. Alinhado com estimativa ADR-002 (~900 LOC +/- 10%).

---

### Testing

#### 8 Mandatory Tests (AC8 Gate)

1. **`test_recurring_generator_end_to_end`** — criar 3 schedules (Weekly Monday, Biweekly Wednesday, Monthly 15th), rodar `generate_window(today, today+14)`. Assert: Weekly produz 2 bookings (Mondays na janela), Biweekly produz 1 (Wed da semana 1), Monthly produz 0-1 (dependendo do mes). Total fixtures: corretos dentro da janela. Todos com `price_snapshot != NULL`.

2. **`test_pricing_matches_schedule_inputs`** ⚠️ **GATE ±$0.01** — criar schedule com inputs equivalentes a fixture F1 (`frequency=Weekly15%`, extra=Stairs, adjustment=-$29.58, location=NYC 4.5% tax). Gerar booking via `generate_window`. Assert `breakdown.final_amount == Decimal('240.01') ± Decimal('0.01')`. **FALHA aqui = FAIL story.**

3. **`test_skip_date_excludes_booking`** — schedule Weekly Monday + INSERT skip para 2026-05-05 (Monday) → gerar window cobrindo 2026-05-05 a 2026-05-12 → assert zero booking em 2026-05-05 + 1 booking em 2026-05-12.

4. **`test_pause_stops_new_bookings`** — schedule `status='active'` → gerar window → N bookings. Pause (`status='paused'`) → gerar proximo window → 0 novos bookings. Bookings ja gerados permanecem.

5. **`test_formula_change_does_not_affect_past_bookings`** — gerar booking → snapshot capturado (final=$X). Alterar `cleaning_pricing_formulas.base_amount +$50`. Re-gerar mesmo dia. Assert snapshot do booking primeiro intacto (ADR-001 Decision 2 Decision 2 + ADR-002 Decision 8).

6. **`test_frequency_id_missing_graceful_fallback`** — schedule com `frequency_id=NULL` (edge post-backfill: 'sporadic' ou 'custom'). Gerar window → assert booking criado com `discount_pct=0` + log warning emitido.

7. **`test_collect_jobs_joins_schedule_extras`** — (unit com mock db) — verificar query emite extras no job dict quando schedule tem linhas em `cleaning_client_schedule_extras`.

8. **`test_persist_assignments_calls_create_booking_with_pricing`** — (unit com mock) — mock `create_booking_with_pricing`. Rodar `_persist_assignments`. Assert called com kwargs corretos: `tier`, `extras`, `frequency_id`, `adjustment_amount`, `location_id`, `source='recurring'`, `recurring_schedule_id` preenchido.

#### Nice-to-have (nao-bloqueante)

- `test_concurrent_generate_via_redis_lock` — 2 calls simultaneas a `generate_window` mesmo dia → segunda retorna `{"error": "already in progress"}`
- `test_pricing_config_error_skips_schedule_continues_others` — schedule sem tier/bedrooms (pre-migracao) → error logado, outras schedules processam normal, summary inclui em `pricing_failures[]`

#### Edge Cases (derivados ADR-002)

Documentados em ADR-002 secao "Edge Cases". Resumo: formula change mid-serie, frequency trocada, extras adicionados, pausa, skip, PricingConfigError, multi-ocorrencia 14d, cancellation mid-series, timezone drift, idempotencia dupla (Redis lock).

---

### Estimated Effort

| Task | Days |
|------|------|
| T1 — Migration 022 | 0.3 |
| T2 — `_collect_jobs` expand | 0.3 |
| T3 — `_persist_assignments` delegate | 0.3 |
| T4 — `recurring_generator.py` window | 0.3 |
| T5 — Endpoint + HMAC | 0.2 |
| T6 — Cron trigger + docs | 0.1 |
| T7 — Tests | 0.4 |
| **Total** | **1.9 days** |

Contingency: +0.3 dia se HMAC setup em Railway exigir troubleshooting.

---

### Definition of Done (NAO-NEGOCIAVEL)

- [ ] AC1-AC8 todas verified passing
- [ ] **Test #2 (`test_pricing_matches_schedule_inputs` ±$0.01) PASS** — gate bloqueador
- [ ] 8/8 mandatory tests PASS (7 others)
- [ ] Code coverage `recurring_generator.py` >= 85%
- [ ] Migration 022 aplicada em Docker PG local + idempotente (2 runs sem erro)
- [ ] `pricing_engine.py`, `booking_service.py`, `recurrence_engine.py`, `frequency_matcher.py` **ZERO modificacao**
- [ ] No breaking change em Track B branch (`feat/payroll-split` branch isolada)
- [ ] No breaking change em Story 1.1 paths (pricing preview endpoint + manual booking creation)
- [ ] Log `[RECURRING]` estruturado aplicado em 4 pontos (collect, generate, failure, summary)
- [ ] Story file update (checkboxes + File List + Change Log)
- [ ] Checkpoint atualizado inline
- [ ] @smith adversarial review: veredicto CONTAINED ou CLEAN (ver Smith backlog Track B como referencia de formato)
- [ ] @devops push (apos Luiz autorizar merge `feat/recurring-auto-gen` → main)

---

### Dependencies

**Blocked by (must be resolved before coding):**
- ✅ ADR-002 accepted (2026-04-16)
- ✅ Story 1.1 Tasks 2+6 Ready for Review (pricing_engine + booking_service live)
- ✅ Migration 021 applied in Docker PG local

**Blocks:**
- Cutover Semana 7 (pre-cutover requires Track A + Track B both merged)

**Zero overlap with Track B:** confirmed — arquivos totalmente isolados. Track A modifica `daily_generator.py` + cria `recurring_generator.py`; Track B mexeu em `cleaner_earnings`/`payroll_service`/`payroll_routes`. Paralelizavel (e ja foi paralelizado: Track B commit `90048c8`).

---

### Next Steps (handoff)

1. **@smith** — verify este sprint plan revisado (coerencia ADR-002 ↔ ACs ↔ Tasks + File List accuracy) antes de @dev comecar
2. **@dev (Neo)** — apos Smith CONTAINED/CLEAN, executar Tasks T1-T7 em branch `feat/recurring-auto-gen`
3. **@smith** — verify delivery apos @dev concluir (gate ±$0.01 non-negotiable)
4. **@devops** — merge `feat/recurring-auto-gen` + `feat/payroll-split` → main apos Luiz autorizar

*Track A revisado. Arquitetura Aria → Estrategia Morgan → Execucao Neo → Verify Smith. A cadeia da realidade.*

— Morgan, planejando o futuro 📊

---

## Track B — Payroll 60% Commission Split

**Agente:** @dev (Neo) + @data-engineer (Tank) para schema review
**Duracao:** 2-3 dias
**Risco:** MEDIO (schema novo + service + endpoints + UI)

### Contexto tecnico existente

- Schema: `cleaning_team_members.wage_pct` (default 60.00, mig 021)
- Bookings tem `final_price` + `price_snapshot` JSONB imutavel (Story 1.1)
- Nao existe tabela `cleaner_earnings`, service de calculo, nem endpoint `/payroll`

### Escopo

1. **Migration 023:**
   ```sql
   CREATE TABLE cleaning_cleaner_earnings (
       id UUID PK,
       business_id UUID FK businesses,
       booking_id UUID FK cleaning_bookings UNIQUE,
       cleaner_id UUID FK cleaning_team_members,
       gross_amount DECIMAL(10,2) NOT NULL,  -- booking.final_price
       commission_pct DECIMAL(5,2) NOT NULL, -- snapshot de wage_pct
       net_amount DECIMAL(10,2) NOT NULL,    -- gross * commission_pct / 100
       status VARCHAR(20) DEFAULT 'pending', -- pending | paid | void
       paid_at TIMESTAMPTZ NULL,
       payout_ref VARCHAR(100) NULL,
       created_at TIMESTAMPTZ DEFAULT NOW(),
       updated_at TIMESTAMPTZ DEFAULT NOW()
   );
   CREATE INDEX ON cleaning_cleaner_earnings (business_id, cleaner_id, status);
   CREATE INDEX ON cleaning_cleaner_earnings (business_id, paid_at);
   ```

2. **Service** `app/modules/cleaning/services/payroll_service.py`:
   - `calculate_cleaner_earnings(db, booking_id)` — chamado quando booking muda para `status='completed'`. Usa `lead_cleaner_id` (ou split se multi-cleaner — v1: single cleaner por booking). Snapshot de `wage_pct` no momento da criacao (imutavel depois).
   - `list_earnings(db, business_id, cleaner_id=None, from_date=None, to_date=None, status=None)` — paginacao simples
   - `mark_paid(db, earnings_ids[], payout_ref)` — idempotente, atualiza status + paid_at
   - `get_cleaner_summary(db, business_id, cleaner_id, period)` — totals por periodo

3. **Routes** `app/modules/cleaning/routes/payroll_routes.py`:
   - `GET /api/v1/clean/{slug}/payroll/earnings` (role=owner) — lista com filtros
   - `GET /api/v1/clean/{slug}/payroll/summary?period=month` (role=owner) — agregacao por cleaner
   - `POST /api/v1/clean/{slug}/payroll/mark-paid` (role=owner) — body: `{earnings_ids[], payout_ref}`
   - `GET /api/v1/clean/{slug}/my-earnings` (role=cleaner) — cleaner ve so as proprias

4. **Hook**: modificar endpoint que marca booking como completed (schedule.py ou bookings.py) para chamar `calculate_cleaner_earnings()` — idempotente via UNIQUE constraint em booking_id.

5. **Frontend:** nova entry Payroll no sidebar owner. Tela simples: tabela (cleaner, period, gross, net, status) + botao "Mark as paid".

### Arquivos tocados

- NEW `database/migrations/023_cleaner_earnings.sql`
- NEW `app/modules/cleaning/services/payroll_service.py`
- NEW `app/modules/cleaning/routes/payroll_routes.py`
- MODIFIED `xcleaners_main.py` (register router)
- MODIFIED `app/modules/cleaning/routes/schedule.py` ou bookings (hook on complete)
- NEW `frontend/cleaning/static/js/payroll-manager.js`
- MODIFIED `frontend/cleaning/app.html` (sidebar entry)
- NEW `tests/test_payroll_service.py`

### Gate de aceitacao

- Booking de $311.10 completed + cleaner com wage_pct=60 → earnings row com gross=311.10, commission_pct=60.00, net=186.66, status=pending
- Listar earnings filtrando por cleaner + periodo
- Mark-paid idempotente (chamar 2x com mesmo payout_ref nao duplica)
- Cleaner logado vê so as suas earnings
- Smith adversarial: wage_pct mudado no member apos booking → earnings NAO mudam (snapshot imutavel)

---

## Ordem de execucao recomendada

1. Abrir VS Code em `C:/xcleaners` com 2 terminais Claude Code
2. Terminal 1 → `@dev` → "execute Sprint D Track A (recurring auto-generator) conforme docs/sprints/sprint-d-recurring-payroll.md"
3. Terminal 2 → `@dev` → "execute Sprint D Track B (payroll 60% split) conforme docs/sprints/sprint-d-recurring-payroll.md"
4. Cada track cria sua branch, commita ao fim. @smith verify por track.
5. Merge de ambas as branches em main apos Smith CONTAINED/CLEAN.
6. @devops push + deploy quando Luiz autorizar.

## Retomada de contexto

- Checkpoint projeto: `C:/clawtobusiness/projects/xcleaners/PROJECT-CHECKPOINT.md`
- Memory: `session_2026_04_16_stripe_connect_xcleaners.md`, `xcleaners_launch27_parity_gap.md`
- Stripe Connect: PRONTO service layer, endpoints REST pendentes (Sprint E)
- Story 1.1 Pricing Engine: READY FOR REVIEW (aguarda push staging + cross-check 5 bookings Ana)
