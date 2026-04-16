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
- Se um track precisar de migration, numere: Track A usa `022_*.sql` se precisar, Track B usa `023_cleaner_earnings.sql`
- Commit por track em branch propria (`feat/recurring-auto-gen`, `feat/payroll-split`) e merge no fim

---

## Track A — Recurring Auto-Generator

**Agente:** @dev (Neo)
**Duracao:** 1-2 dias
**Risco:** BAIXO (infra 80% feita)
**Branch:** `feat/recurring-auto-gen`

### Contexto tecnico existente

- Schema: `cleaning_recurring_schedules` (mig 011) + `cleaning_client_schedules` (mig 012) com `frequency`, `custom_interval_days`, `next_occurrence`, `paused`
- Engine: `app/modules/cleaning/services/schedule_service.py::compute_next_occurrence()` (weekly/biweekly/monthly/sporadic)
- Engine: `app/modules/cleaning/services/recurrence_engine.py` avanca `next_occurrence`
- Factory: `app/modules/cleaning/services/booking_service.py::create_booking_with_pricing()` (criado em Story 1.1 C1)
- Gap: **nao existe cron diario** que escaneia schedules e dispara materializacao

### Escopo

1. Criar `app/modules/cleaning/services/recurring_generator.py` com `run_daily_generation(db)`:
   - Query schedules WHERE `next_occurrence <= CURRENT_DATE AND paused=FALSE`
   - Para cada schedule: idempotencia (verificar se ja existe booking para aquele dia), criar via `create_booking_with_pricing()`, avancar `next_occurrence` via engine
   - Structured logging por schedule (success/skip/error)
2. Wire no startup FastAPI (lifespan) — usar `asyncio` task ou APScheduler com cron diario 03:00 local (ou endpoint `/admin/run-daily-gen` para Railway cron externo)
3. Endpoint manual `POST /api/v1/clean/{slug}/schedule/run-daily-gen` (role=owner) para rodar sob demanda
4. Testes integration: fixture com 3 schedules (weekly/biweekly/monthly) → rodar generator N vezes simulando 30 dias → assert bookings criados sem duplicatas

### Arquivos tocados

- NEW `app/modules/cleaning/services/recurring_generator.py`
- MODIFIED `xcleaners_main.py` (lifespan hook)
- MODIFIED `app/modules/cleaning/routes/schedule.py` (endpoint manual)
- NEW `tests/test_recurring_generator.py`

### Gate de aceitacao

- 30-day simulation: bookings gerados corretamente (weekly + biweekly + monthly) sem duplicatas, sem drift de `next_occurrence`
- Smith adversarial: edge cases (schedule pausado mid-cycle, timezone DST, frequency=custom com custom_interval_days)

---

## Track B — Payroll 60% Commission Split

**Agente:** @dev (Neo) + @data-engineer (Tank) para schema review
**Duracao:** 2-3 dias
**Risco:** MEDIO
**Branch:** `feat/payroll-split`

### Contexto tecnico existente

- Schema: `cleaning_team_members.wage_pct` (default 60.00, mig 021)
- Bookings tem `final_price` + `price_snapshot` JSONB imutavel (Story 1.1)
- Cleaner check-out em `cleaner_service.py::check_out_job()` linha ~326 marca `status='completed'`
- Nao existia tabela earnings, service ou endpoints

### Escopo

1. **Migration 023** `cleaning_cleaner_earnings` (booking_id UNIQUE snapshot: gross, commission_pct, net, status pending/paid/void)
2. **Service** `payroll_service.py` — calculate / list / summary / mark_paid / void (idempotent via UNIQUE)
3. **Routes** `payroll_routes.py` — `/payroll/earnings`, `/payroll/summary`, `/payroll/mark-paid`, `/payroll/{id}/void` (owner) + `/my-earnings` (cleaner)
4. **Hook** em `cleaner_service.check_out_job()` — chama calculate apos UPDATE status=completed
5. **Frontend** `payroll-manager.js` + entry Finance → Payroll no sidebar

### Gate de aceitacao

- Booking de $311.10 completed + wage_pct=60 → earnings gross=311.10, pct=60, net=186.66, status=pending
- Mark-paid idempotente (mesmo payout_ref não duplica)
- Cleaner so ve suas proprias earnings
- Snapshot imutavel: wage_pct mudado apos booking → earnings NAO muda

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
