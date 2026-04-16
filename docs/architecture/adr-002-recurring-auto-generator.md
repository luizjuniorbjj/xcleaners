---
type: adr
id: ADR-002
title: "Recurring Auto-Generator — Pricing Engine Integration + Scheduler Contract"
status: accepted
date: 2026-04-16
author: "@architect (Aria)"
project: xcleaners
supersedes: []
impacts:
  - Sprint D Track A (Recurring Auto-Generator)
  - ADR-001 Decision 2 (price_snapshot immutability — extended to recurring bookings)
  - Smith C1 finding M2 (pricing divergence em /schedule/generate)
  - R9 open question (cleaning_client_schedules.frequency_id)
  - daily_generator.py (_persist_assignments integration point)
  - booking_service.py (create_booking_with_pricing reuse)
tags:
  - project/xcleaners
  - adr
  - recurring
  - architecture
  - sprint-d
---

# ADR-002 — Recurring Auto-Generator

## Status

**Accepted** — 2026-04-16

## Context

Sprint D Track A: auto-gerador de bookings recorrentes. Nome sugere greenfield, mas auditoria do código revela que **infra ~80% JÁ EXISTE**:

| Componente | Status | Arquivo |
|-----------|--------|---------|
| Daily orchestrator (5-step) | ✅ FUNCIONA | `services/daily_generator.py` |
| Next-occurrence advancer | ✅ FUNCIONA | `services/recurrence_engine.py` |
| Frequency matcher (4 modes) | ✅ FUNCIONA | `services/frequency_matcher.py` |
| Schedule table + status lifecycle | ✅ EXISTE | `cleaning_client_schedules` (migration 012) |
| Booking+Pricing integration helper | ✅ EXISTE | `services/booking_service.py` (Task 6 Story 1.1) |
| Pricing engine | ✅ LIVE | `services/pricing_engine.py` (Story 1.1) |

### The real gap

`daily_generator._persist_assignments()` faz `INSERT INTO cleaning_bookings` **diretamente**, usando `schedule.agreed_price` como `quoted_price`. **Ignora o pricing engine completamente.** Resultado observado em produção:

- Smith C1 finding **M2**: "pricing divergence silenciosa em `/schedule/generate`" — price calculado pode divergir de `agreed_price`
- R9 aberto: `cleaning_client_schedules.frequency_id` não existe (FK foi adicionada só em `cleaning_recurring_schedules`, tabela legacy)
- Efeito: TODOS os bookings gerados hoje têm `price_snapshot = NULL`, `tax_amount = 0`, `discount_amount = 0`, `adjustment_amount = 0`

**Nome "Auto-Generator" é enganoso.** O gerador existe. O que falta é o *contrato de pricing* entre `cleaning_client_schedules` e `pricing_engine`. Track A é uma **integração cirúrgica**, não um sistema novo.

### Referência factual — booking real 3Sisters recorrente (Weekly 15%)

Uma cliente com schedule Weekly deveria gerar, ao longo de 4 semanas, 4 bookings. Hoje no xcleaners cada um seria criado com `quoted_price = agreed_price` (valor digitado manualmente pela Ana). No Launch27 cada um passa pelo cálculo completo (subtotal − discount + adjustment + tax). **Esses dois caminhos divergem por design.** O gate de ±$0.01 da Story 1.1 só vale se o recurring path também passa pelo engine.

---

## Decisões

### Decisão 1 — `cleaning_client_schedules` vira "pricing input carrier", `agreed_price` fica DEPRECATED

A schedule carrega **INPUTS** (tier, extras, frequency, adjustment, location), NÃO o preço final. O preço final é recalculado a cada geração pelo pricing engine e gravado imutavelmente em `cleaning_bookings.price_snapshot`.

**Mudanças em `cleaning_client_schedules`:**

| Coluna | Ação | Rationale |
|--------|------|-----------|
| `frequency_id UUID REFERENCES cleaning_frequencies(id)` | **ADD** | Preenche R9 — input para discount_pct |
| `frequency VARCHAR` | **MANTER** (soft-deprecate) | Backward compat do frequency_matcher; dropar em v2 |
| `adjustment_amount NUMERIC(10,2) DEFAULT 0` | **ADD** | Ajuste recorrente aplicado em TODOS bookings da série |
| `adjustment_reason VARCHAR(255)` | **ADD** | Auditabilidade |
| `location_id UUID REFERENCES cleaning_areas(id)` | **ADD** | Input para tax lookup |
| `agreed_price NUMERIC` | **MANTER** (soft-deprecate) | Source of truth desloca para engine; manter valor histórico para audit/UI comparison |

**Rationale:** Schedule-level inputs replicam o modelo mental do Launch27 (client assina um serviço com termos específicos: frequency + extras fixos + adjustment fixo). Bookings futuros re-cálculam usando estado atual (formula/extras/tax podem mudar). **Mudar a schedule ≠ alterar bookings passados** — o price_snapshot imutável garante isso (ADR-001 Decision 2 estendida).

**Alternativa rejeitada:** "snapshot de pricing inputs no schedule" — over-engineering. Pricing inputs são intencionais (Ana quer que TODOS bookings dessa cliente continuem com Weekly 15% + Stairs extra). Se pricing muda, ela muda o schedule, não booking-por-booking.

### Decisão 2 — Nova tabela `cleaning_client_schedule_extras` (schedule-level extras)

Extras de uma série recorrente são **fixos**. Não fazem sentido em `cleaning_booking_extras` (que é snapshot imutável por booking).

```sql
CREATE TABLE cleaning_client_schedule_extras (
    schedule_id UUID NOT NULL REFERENCES cleaning_client_schedules(id) ON DELETE CASCADE,
    extra_id UUID NOT NULL REFERENCES cleaning_extras(id) ON DELETE CASCADE,
    qty INTEGER NOT NULL DEFAULT 1 CHECK (qty >= 1),
    PRIMARY KEY (schedule_id, extra_id)
);
```

**Fluxo:** daily_generator busca extras via JOIN → passa como input ao pricing_engine → cria booking + `cleaning_booking_extras` (snapshot no momento da geração).

**Rationale:** Conceitualmente, schedule-extras são **template**, booking-extras são **snapshot**. Duas tabelas = duas semânticas claras.

### Decisão 3 — Nova tabela `cleaning_schedule_skips` (skip individual de uma ocorrência)

Owner pode querer pular uma data específica sem pausar a série inteira (cliente viaja, feriado, combinação).

```sql
CREATE TABLE cleaning_schedule_skips (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    schedule_id UUID NOT NULL REFERENCES cleaning_client_schedules(id) ON DELETE CASCADE,
    skip_date DATE NOT NULL,
    reason VARCHAR(255),
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (schedule_id, skip_date)
);

CREATE INDEX idx_cleaning_schedule_skips_lookup
    ON cleaning_schedule_skips(schedule_id, skip_date);
```

**Integração no daily_generator:** `_collect_jobs` acrescenta um LEFT JOIN/NOT EXISTS check — se existe skip row para `(schedule_id, target_date)`, pular. Adiciona 1 subquery, custo irrelevante.

**Rationale:** Simpler que criar `cleaning_business_holidays` global. Skip é per-schedule (respeita autonomia do cliente). Holidays podem ser criadas em lote via bulk skip UI, se owner quiser pular todos no mesmo dia — v2 feature.

### Decisão 4 — Status `'paused'` já existe, use-o corretamente (não skipar)

`cleaning_client_schedules.status` já suporta `'active'|'paused'|'cancelled'` (migration 012). Daily_generator atual filtra só `status='active'` — correto.

**Pausa vs skip — contrato semântico:**
- **paused:** série inteira suspensa indefinidamente (férias longas, cliente em transição) — nada é gerado
- **skip:** uma data específica é pulada, próximas ocorrências seguem normais
- **cancelled:** série terminada, nunca reativada (para reativar, owner cria nova schedule)

**Zero mudança de schema nesta decisão.** Apenas esclarecer contrato no documento de UX.

### Decisão 5 — Cron/Scheduler: **look-ahead 14 dias, execução diária às 02:00 UTC**

O daily_generator atual gera 1 dia por vez. Para UX de owner/cliente/team, precisamos visualizar 1-2 semanas à frente.

**Contrato:**
- **Novo endpoint interno** `POST /internal/recurring/generate-window` que itera `daily_generator.generate_daily_schedule` para `today → today + 14`
- **Trigger:** cron externo (Railway cron ou GitHub Actions) chama o endpoint com HMAC auth diariamente às **02:00 UTC**
- **Cadência:** diária (não-hourly) — recurring não muda de hora em hora, 1x/dia basta
- **Look-ahead window:** **14 dias** — suficiente para SMS reminders (7d), team planning (7d), homeowner mobile calendar (14d)
- **Idempotência:** garantida pelo Redis distributed lock + UPSERT-ish logic em `_persist_assignments` (skip if booking confirmed/completed existe)

**Timezone caveat (aberto):** daily_generator usa `date` sem tz. Para 3Sisters NYC (UTC-5), rodar às 02:00 UTC = 21:00 local dia anterior — aceitável. Se no futuro businesses em tz diferente precisarem de granularidade, ADD `businesses.timezone VARCHAR(50) DEFAULT 'America/New_York'` + cron roda em UTC e cada business calcula `target_date = now(business.tz).date()`. **Deferrable v2.**

**Alternativa rejeitada:** APScheduler embedded no FastAPI process. Risco de race em multi-worker deploy. Cron externo = mais simples e explícito.

### Decisão 6 — `daily_generator._persist_assignments` delega a `booking_service.create_booking_with_pricing`

**Este é o core da Track A.** Uma única mudança cirúrgica fecha o gap Smith M2 + R9.

**Antes (atual):**
```python
# daily_generator.py line ~672
await db.pool.fetchrow(
    """INSERT INTO cleaning_bookings (..., quoted_price, ...)
       VALUES (..., $16, ...) RETURNING id""",
    ..., assignment.get("agreed_price"), ...  # ← gap: skips pricing engine
)
```

**Depois (Track A):**
```python
# daily_generator.py
from app.modules.cleaning.services.booking_service import create_booking_with_pricing

result = await create_booking_with_pricing(
    db=db,
    business_id=business_id,
    client_id=assignment["client_id"],
    service_id=assignment["service_id"],
    scheduled_date=target_date,
    scheduled_start=assignment["scheduled_start"],
    estimated_duration_minutes=assignment["estimated_duration_minutes"],
    team_id=assignment["team_id"],
    recurring_schedule_id=assignment["schedule_id"],
    # Pricing inputs pulled from schedule (new JOIN in _collect_jobs):
    tier=assignment.get("service_tier"),  # from cleaning_services.tier
    extras=assignment.get("schedule_extras", []),  # from cleaning_client_schedule_extras
    frequency_id=assignment.get("frequency_id"),  # from schedule (Decisão 1)
    adjustment_amount=assignment.get("adjustment_amount", Decimal("0")),
    adjustment_reason=assignment.get("adjustment_reason"),
    location_id=assignment.get("location_id"),
    source="recurring",
    status="scheduled",
    address_line1=assignment.get("address_line1"),
    special_instructions=assignment.get("notes"),
)
assignment["booking_id"] = result["booking_id"]
```

**Side effects automáticos (já implementados em `booking_service`):**
- `price_snapshot JSONB` preenchido ✓
- `tax_amount`, `discount_amount`, `adjustment_amount` corretos ✓
- `cleaning_booking_extras` rows criadas (snapshot) ✓
- `final_price` = `breakdown["final_amount"]` (compatível com UI atual) ✓
- `quoted_price` = mesmo valor (compatibilidade) ✓

**Update path (booking já existia unconfirmed):** análogo — precisa chamar `booking_service.recalculate_booking_snapshot` ou repetir a query. **Decisão:** delete + recreate é simpler para unconfirmed. Para confirmed/in_progress/completed, **NÃO tocar** (já é o comportamento atual via filter `status NOT IN ('confirmed', 'in_progress', 'completed')`).

**Error handling:**
- Se `PricingConfigError` (ex: schedule não tem `frequency_id` após migração 022): LOG WARNING, skip essa schedule, continuar com outras. **Não abortar a geração inteira.**
- Registrar em lista `pricing_failures` incluída no response do endpoint para owner revisar.

### Decisão 7 — Migration 022 estratégia: additive, idempotente, com backfill de frequency_id

Novo arquivo: `database/migrations/022_recurring_pricing_inputs.sql`

**Changes:**
1. `ALTER TABLE cleaning_client_schedules` ADD 4 colunas (frequency_id, adjustment_amount, adjustment_reason, location_id) — todas `IF NOT EXISTS`
2. `CREATE TABLE` 2 novas (schedule_extras, schedule_skips) — todas `IF NOT EXISTS`
3. **Backfill `cleaning_client_schedules.frequency_id`** via matching de `LOWER(frequency)` vs `cleaning_frequencies.name`:
   ```sql
   UPDATE cleaning_client_schedules crs
   SET frequency_id = f.id
   FROM cleaning_frequencies f
   WHERE crs.frequency_id IS NULL
     AND f.business_id = crs.business_id
     AND LOWER(crs.frequency) = LOWER(f.name);
   -- Edge: 'sporadic' não tem match → frequency_id fica NULL → pricing engine usa 0% discount
   ```
4. **Backfill `cleaning_client_schedules.location_id`** = `cleaning_areas WHERE is_default = TRUE AND business_id = crs.business_id`
5. `RAISE NOTICE` para rows não-mapeadas (ops visibility)
6. `COMMENT ON COLUMN agreed_price IS 'DEPRECATED 2026-04-16 — price calculado por pricing_engine em runtime; manter apenas para audit historical. Nao usado em bookings gerados post-migration 022.'`

**Rollback `rollback_022.sql`:** destrutivo com warnings — DROP colunas novas, DROP tables novas. Validado manualmente com backup antes.

### Decisão 8 — Integração com ADR-001 Decision 1 (overrides STALE)

**Cenário:** Ana tem 20 clientes em Weekly Basic com override de $200 (formula calcula $175). Owner muda a formula: base +$10. Overrides continuam em $200 (Decision 1).

**Impacto no recurring:**
- Todos os bookings futuros desses 20 clientes continuam gerados com $200 (override ainda ativo)
- UI do pricing-manager já mostra badge "stale" (formula.updated_at > override.created_at)
- **Zero mudança no auto-generator** — pricing_engine já aplica override precedence corretamente

**Cenário secundário:** Ana reverte o override de um cliente específico. Próximo booking recorrente gerado para esse cliente usa a formula nova (service_amount + $10). O snapshot desse booking reflete o novo preço. Bookings passados da mesma cliente permanecem em $200 (price_snapshot imutável).

**Conclusão:** ADR-001 Decision 1 + price_snapshot imutável = comportamento correto automático para recurring. Zero decisão nova aqui.

### Decisão 9 — Holidays e backfill histórico

**Holidays (business-level):** Deferred para v2. V1: apenas skips per-schedule via Decisão 3.

**Backfill de bookings Launch27:** NÃO fazer. Migration path B (ADR-001 + checkpoint): migração de services + active customers, bookings Launch27 ficam read-only lá. Xcleaners começa recurring do zero pós-cutover.

### Decisão 10 — Observability mínima obrigatória

Track A é um caminho crítico para receita. Log mínimo:

```python
# Em _collect_jobs
logger.info("[RECURRING] Collected %d schedules for %s (skipped %d via cleaning_schedule_skips)",
            matched_count, target_date, skipped_count)

# Em delegate to booking_service (success)
logger.info("[RECURRING] Generated booking=%s schedule=%s client=%s final=%s",
            booking_id, schedule_id, client_id, final_amount)

# Em PricingConfigError
logger.warning("[RECURRING] Pricing failure for schedule=%s: %s. Booking SKIPPED.",
               schedule_id, error)
```

E métrica estruturada no response do endpoint:
```json
{
  "generated": 28,
  "skipped_by_skip_table": 3,
  "pricing_failures": [{"schedule_id": "uuid", "reason": "..."}],
  "summary": {"window_days": 14, "total_schedules_scanned": 42}
}
```

---

## Schema Summary (Migration 022)

```sql
-- ALTER cleaning_client_schedules
ALTER TABLE cleaning_client_schedules
    ADD COLUMN IF NOT EXISTS frequency_id UUID REFERENCES cleaning_frequencies(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS adjustment_amount NUMERIC(10,2) DEFAULT 0.00,
    ADD COLUMN IF NOT EXISTS adjustment_reason VARCHAR(255),
    ADD COLUMN IF NOT EXISTS location_id UUID REFERENCES cleaning_areas(id) ON DELETE SET NULL;

-- Two new tables (see Decisões 2, 3 for full DDL)
CREATE TABLE IF NOT EXISTS cleaning_client_schedule_extras (...);
CREATE TABLE IF NOT EXISTS cleaning_schedule_skips (...);

-- Backfill frequency_id + location_id per decisão 7
UPDATE cleaning_client_schedules SET frequency_id = ... WHERE frequency_id IS NULL;
UPDATE cleaning_client_schedules SET location_id = ... WHERE location_id IS NULL;

-- Soft-deprecate agreed_price
COMMENT ON COLUMN cleaning_client_schedules.agreed_price IS 'DEPRECATED...';
```

**Impacto total:** 4 colunas ADD + 2 tables NEW + 2 backfill UPDATE + 1 COMMENT. Zero DROP, zero DESTRUCTIVE. Reversible.

---

## Integration Contract — Arquivos afetados (input para @pm)

| Arquivo | Mudança | Complexidade |
|---------|---------|--------------|
| `database/migrations/022_recurring_pricing_inputs.sql` | NEW | M (~150 LOC SQL) |
| `database/migrations/rollback_022.sql` | NEW | S (~50 LOC) |
| `app/modules/cleaning/services/daily_generator.py` | MODIFY `_collect_jobs` + `_persist_assignments` | M (~80 LOC delta) |
| `app/modules/cleaning/routes/schedule.py` | NEW endpoint `POST /internal/recurring/generate-window` | S (~50 LOC) |
| `app/modules/cleaning/services/recurring_generator.py` | NEW — orchestrator 14-day window | S (~80 LOC) |
| `tests/test_recurring_generator.py` | NEW — integration tests | M (~400 LOC) |
| `tests/fixtures/recurring_schedules.py` | NEW — schedule fixtures | S (~100 LOC) |
| `scripts/trigger_recurring.sh` OR `.github/workflows/recurring-cron.yml` | NEW — cron trigger | S (~30 LOC) |

**Total estimado:** ~900 LOC novas/modificadas. Alinhado com "1-2 dias risco BAIXO" do checkpoint.

---

## Edge Cases — Checklist para @pm derivar ACs

1. **Formula muda mid-série:** snapshot passado imutável, snapshot futuro reflete nova formula. Verificado via test: criar series → gerar 2 bookings → alterar formula → gerar próximos 2 → assert primeiros 2 intactos.
2. **Frequency trocada no schedule (Weekly → Biweekly):** próximas gerações usam novo frequency_id + novo discount_pct. Bookings já gerados NÃO recalculam. UI warns owner antes de salvar ("Changing frequency affects future bookings only").
3. **Extras adicionados no schedule:** próximas gerações incluem. Já gerados não. Mesmo warning UI.
4. **Schedule pausado:** `status='paused'`, daily_generator filtra out, zero novos bookings. Bookings já agendados (não confirmed) **permanecem** em `cleaning_bookings`. Owner pode cancelá-los manualmente se quiser.
5. **Skip date específico:** `cleaning_schedule_skips` INSERT → próxima geração pula. Se booking já foi gerado para aquela data (status='scheduled'), **NÃO é automaticamente deletado** — owner cancela manualmente. UI da skips-manager mostra warning "Existing scheduled booking on YYYY-MM-DD will not be auto-cancelled; cancel manually if desired."
6. **PricingConfigError durante geração:** log warning, skip schedule, continuar com outras. Response do endpoint lista falhas para owner revisar.
7. **Multi-ocorrência no mesmo dia (weekly hits 2x em 14d window):** cada dia é independente, daily_generator roda 14 vezes, cada vez emite 0-1 booking por schedule. Zero duplicate.
8. **Cliente cancelled no meio da série:** `status='cancelled'` → zero novos, bookings existentes ficam. Owner decide o destino deles (cancel/keep).
9. **Timezone drift:** hardcoded UTC para v1. Para businesses em PDT, bookings gerados às 02:00 UTC = 19:00 local dia anterior. Aceitável — geração rotaciona 24h pra frente; não afeta correção do `scheduled_date`.
10. **Idempotência dupla (cron dispara 2x):** Redis lock por `(business_id, target_date)` garante single-execution por dia. Se lock não adquirir, retorna `{"error": "already in progress"}`.

---

## Test Strategy — Input para @pm compor AC7 gate

**Mandatory tests (Track A AC gate):**

1. **Integration `test_recurring_generator_end_to_end`:** criar 3 schedules Weekly + 1 Biweekly + 1 Monthly, rodar `generate_window(today, today+14)`, assert 14 bookings para Weekly × 2, 7 para Biweekly, 0 ou 1 para Monthly conforme dia da semana. Cada booking tem `price_snapshot` não-NULL.

2. **Integration `test_pricing_matches_schedule_inputs`:** schedule com frequency_id=Weekly15%, extra=Stairs, adjustment=−$29.58, location_id=NYC → gerar booking → assert `breakdown.final_amount` bate ±$0.01 com fixture `F1_3sisters_240_01` da Story 1.1.

3. **Integration `test_skip_date_excludes_booking`:** schedule Weekly Monday + skip row para 2026-05-05 (Monday) → gerar window cobrindo 2026-05-05 → assert zero booking nesse dia + assert booking para 2026-05-12 gerado normalmente.

4. **Integration `test_pause_stops_new_bookings`:** schedule `status='active'` → gerar → 2 bookings. Pause schedule (`status='paused'`) → gerar próximo window → 0 novos bookings.

5. **Integration `test_formula_change_does_not_affect_past_bookings`:** gerar booking → snapshot capturado. Alterar pricing_formula.base_amount +$50. Re-gerar mesmo booking (via regenerate_daily_schedule). Assert snapshot original intacto se status != draft. Novo booking (próxima ocorrência) reflete novo preço.

6. **Integration `test_frequency_id_missing_graceful_fallback`:** schedule com `frequency_id=NULL` e `frequency='sporadic'`. Assert pricing_engine usa `discount_pct=0` sem erro, log warning emitido.

7. **Unit `test_collect_jobs_joins_schedule_extras`:** mock db, verificar JOIN em cleaning_client_schedule_extras emite extras no job dict.

8. **Unit `test_persist_assignments_calls_booking_service`:** mock create_booking_with_pricing, assert called com kwargs corretos (tier, extras, frequency_id, adjustment_amount, location_id).

**Nice-to-have (não-bloqueante):**

- `test_concurrent_generate_via_redis_lock` — lock impede double-generation
- `test_pricing_config_error_skips_schedule` — erro não aborta geração inteira

---

## Consequences

### Positivas

- **Unificação do pricing path:** recurring e manual bookings agora seguem o mesmo cálculo → test gate ±$0.01 da Story 1.1 vale para TUDO
- **R9 fechado** (frequency_id em cleaning_client_schedules)
- **Smith C1 M2 fechado** (pricing divergence silenciosa eliminada)
- **Schedule-level inputs** refletem modelo mental do Launch27 (client subscription com termos)
- **Auditabilidade completa:** cada recurring booking tem price_snapshot imutável para disputa/compliance
- **Skip + pause dual-mechanism** cobre 95% dos casos de "temporário" vs "permanente"
- **Zero rewrite do daily_generator** — mudança cirúrgica de ~80 LOC em `_persist_assignments`

### Negativas / Aceitas

- **Schema complexity +2 tables +4 columns:** carry cost. Mitigado: naming explícito (schedule_extras ≠ booking_extras), comentários CONSTRAINT, migration idempotente.
- **`agreed_price` fica zombie:** pricing_engine é source of truth, mas campo persiste. Cleanup pós-cutover Semana 8+.
- **Timezone hardcoded UTC v1:** operações 3Sisters (NYC, UTC-5) geram à noite local — aceitável, não bloqueia cutover. V2 add `businesses.timezone`.
- **Holidays sem suporte nativo:** owner usa skips 1-a-1. Acceptable v1 — 3Sisters prob tem 5-10 holidays/ano × 20 clientes = 100-200 skips, gerenciável via bulk UI em v2.

### Riscos & Mitigações

| Risco | Mitigação |
|-------|-----------|
| Backfill frequency_id falha para 'sporadic' → pricing com 0% discount | Aceitável — sporadic não tem discount padrão no modelo 3Sisters. Log warning para ops visibility. |
| Cron externo não dispara (Railway downtime) | Monitor via health endpoint + backfill manual via `*regenerate-schedule` se 1+ dia perdido |
| Schedule-level extras muda e owner esperava afetar bookings existentes | UI warning explícito "Changes affect future bookings only" + tooltip linkando a Recalculate manual |
| Pricing_engine lento no caminho recurring (N bookings × lookup) | Connection pool reuse + lookup index em `cleaning_sales_taxes(location_id, effective_date DESC)`. P95 esperado <100ms por booking × 42 schedules × 14 dias = ~60s full window — aceitável. Se virar hot path, cache formula+frequency per request em v2. |
| Luiz decide que `agreed_price` é importante (legacy snapshot por cliente) | Reabrir ADR com nova Decisão: promover `agreed_price` a "client-level override" — v2 scope. |

---

## Próximo Passo — Handoff para @pm (Morgan)

**Inputs para sprint plan `sprint-d-recurring-payroll.md` Track A:**

1. **Escopo Track A:** 3 layers (migration 022, service integration, cron+endpoint)
2. **ACs derivadas desta ADR:**
   - AC1: Migration 022 idempotente com 4 ALTER + 2 CREATE + 2 backfill + 1 COMMENT
   - AC2: `daily_generator._persist_assignments` delega a `booking_service.create_booking_with_pricing`
   - AC3: `daily_generator._collect_jobs` JOIN com `cleaning_client_schedule_extras` + inclui schedule-level pricing inputs no job dict
   - AC4: Novo endpoint `POST /internal/recurring/generate-window?days=14` com HMAC auth
   - AC5: Novo service `recurring_generator.py` orquestrando window iteration
   - AC6: Schedule skips verificados em `_collect_jobs` (NOT EXISTS subquery)
   - AC7: 6 mandatory integration tests (listados acima) + 2 unit tests, todos PASS
3. **File List estimado:** 8 arquivos (1 NEW service, 1 NEW endpoint, 1 NEW migration + rollback, 2 NEW test files, 2 MODIFIED — daily_generator + schedule routes)
4. **Estimated effort:** 1.5-2 dias @dev — alinhado com checkpoint "risco BAIXO"
5. **Test gate não-negociável:** test #2 (`test_pricing_matches_schedule_inputs`) deve PASS — é o equivalente recurring do ±$0.01 da Story 1.1

**Zero overlap com Track B (Payroll 60%):** confirmed — Track B modifica `cleaner_earnings`/`payroll_service`, zero arquivo compartilhado com Track A. Paralelizável.

**Dependências bloqueantes:** nenhuma. Story 1.1 já em Ready for Review + migration 021 aplicada. Track A é additive sobre a base existente.

---

*ADR-002 closed. Não era sistema novo — era um ponto de integração esquecido. Às vezes a melhor arquitetura é a que revela que 80% do trabalho já estava feito.*

— Aria, arquitetando o futuro 🏗️
