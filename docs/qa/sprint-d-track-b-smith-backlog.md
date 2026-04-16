# Sprint D Track B — Smith Backlog (2026-04-16)

**Smith Verdict:** CONTAINED (allow-commit)
**Fixes aplicados nesta entrega:** 3 (findings #4, #5, #8)
**Backlog:** 5 findings para follow-up

---

## Fixed in this commit

| # | Sev | Arquivo | Fix |
|---|-----|---------|-----|
| #4 | MED | payroll_service.py void_earning | Removido write de reason em payout_ref; reason so vai pro log |
| #5 | MED | payroll_service.py mark_paid | Agora wrappa SELECT + UPDATE em `async with conn.transaction()` + `FOR UPDATE` |
| #8 | LOW | payroll-manager.js row display | payout_ref agora tem `max-width` + ellipsis + title tooltip |

---

## Backlog (seguir pre-cutover 3Sisters)

### #1 [HIGH] Hook creates window: booking=completed but no earnings row

**Where:** `cleaner_service.py::check_out_job` ~line 326-368
**Issue:** Se `calculate_cleaner_earnings` raise `PayrollError` (ex: NULL `final_price`), booking ja esta marcado completed mas sem earnings. Legitimate scenario: owner nao precificou booking.
**Fix proposto:**
- Adicionar `payroll_service.backfill_missing(business_id)` — escaneia completed bookings sem earnings
- Endpoint `GET /api/v1/clean/{slug}/payroll/missing` (owner)
- Notificacao visual no sidebar "Payroll" quando ha missing
- Alternativa (mais complexa): envolver UPDATE status + calculate em transacao atomica

**Story proposta:** XCL-D.B1 "Payroll backfill + missing earnings view" (1 dia)

---

### #2 [HIGH] `/my-earnings` assume single team_member per (user_id, business)

**Where:** `payroll_routes.py::get_my_earnings` linha 181-192
**Issue:** `fetchrow` retorna arbitrary row se um user_id tem multiplas memberships na mesma business. Slug mismatch nao e cross-validado.
**Fix proposto:**
- Verificar que existe UNIQUE(business_id, user_id) em cleaning_team_members (provavelmente ja existe)
- Assert na query: `SELECT id FROM ... WHERE business_id=$1 AND user_id=$2` — se retorna mais de 1, log WARN e retorna 409
- Cross-validate `slug` resolves ao `user["business_id"]` da session

**Story proposta:** XCL-D.B2 "Multi-tenant team_member safety on /my-earnings" (0.5 dia)

---

### #3 [MEDIUM] `ON DELETE RESTRICT` em cleaner_id bloqueia delecao de cleaner

**Where:** `023_cleaner_earnings.sql:35`
**Issue:** Owner nao consegue deletar cleaner que ja teve earnings. UX dead-end.
**Fix proposto (2 opcoes):**
- Opcao A (simples, doc-only): documentar que cleaners devem ser `status='inactive'`, nunca deletados. Atualizar UI para esconder botao "Delete" e oferecer "Deactivate".
- Opcao B (robusto): ALTER TABLE → `ON DELETE SET NULL` + adicionar `cleaner_name_snapshot VARCHAR(200)` para display historico.

**Recomendacao:** Opcao A primeiro (MVP), Opcao B quando tivermos historico relevante.

**Story proposta:** XCL-D.B3 "Cleaner deactivation flow + UI protection" (0.5 dia)

---

### #6 [LOW] `list_earnings` filter-by-date usa `created_at::date` que bypassa index

**Where:** `payroll_service.py` linhas ~205, 249
**Issue:** `idx_earnings_business_created_at` e BTREE em `(business_id, created_at DESC)`, mas query usa `created_at::date >= $n` — functional cast nao usa indice.
**Fix proposto:** Trocar para `created_at >= $n::timestamptz AND created_at < ($n+1)::date::timestamptz`.
**Impacto:** BAIXO em dev (ms), pode importar em prod com >10k earnings.

**Story proposta:** XCL-D.B4 "Index-friendly date filters" (0.25 dia)

---

### #7 [LOW] Tests nao cobrem integracao do hook check_out → calculate

**Where:** `tests/test_payroll_service.py`
**Issue:** 19 unit tests no service, mas nenhum valida que `cleaner_service.check_out_job` efetivamente dispara o hook sem quebrar. Regressao possivel se alguem refatorar `check_out_job` e remover o `try/except`.
**Fix proposto:** Adicionar `test_checkout_triggers_earnings_calc` e `test_checkout_swallows_payroll_error` em um arquivo `tests/test_cleaner_service_integration.py`.

**Story proposta:** XCL-D.B5 "Integration tests hook check_out" (0.25 dia)

---

## Total backlog

5 stories, ~2.5 dias estimados. Nenhuma bloqueia cutover 3Sisters porque:
- #1/#2: edge cases raros (Ana precifica todos bookings; cada cleaner 1 user_id 1 membership)
- #3: workaround = inactive-em-vez-de-delete, documentavel
- #6/#7: tecnica, nao funcional

Plano: incluir no Sprint E ou sprint tecnico pos-cutover.
