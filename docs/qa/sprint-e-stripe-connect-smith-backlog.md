# Sprint E Item 1 — Stripe Connect REST — Smith Backlog (2026-04-16)

**Smith Verdict:** CONTAINED (allow-commit)
**Fixes aplicados nesta entrega:** 3 (#3 warn 0 rows, #4 narrow SignatureVerificationError, #5 generic error detail)
**Backlog:** 4 findings

---

## Fixed in this commit

| # | Sev | File | Fix |
|---|-----|------|-----|
| #3 | MED | stripe_connect_routes.py webhook | WARN log se UPDATE 0 rows (stale env wiring diagnosable) |
| #4 | LOW | stripe_connect_routes.py webhook | Catch especifico de SignatureVerificationError (nao clobber outros bugs) |
| #5 | LOW | stripe_connect_routes.py multiple | HTTPException detail generico ("Upstream payment provider error") — nao leak Stripe error text |

---

## Backlog (follow-up Sprint E antes de item 2: auto-charge webhooks)

### #1 [MEDIUM] Webhook idempotency / replay protection

**Issue:** Stripe retries `account.updated` on timeouts. Hoje cada retry re-roda UPDATE (idempotente por conteudo no caso atual). Quando adicionarmos `payout.paid`/`charge.succeeded` em Sprint E item 2, sem dedup vai processar o mesmo evento varias vezes → cobrancas duplas, estado corrompido.

**Fix proposto:**
- Migration 024: tabela `stripe_webhook_events` (event_id UUID PRIMARY KEY, event_type, received_at, processed_at, payload_hash)
- No handler: `INSERT ... ON CONFLICT (event_id) DO NOTHING RETURNING id` — skip se nada retornou
- TTL opcional: CRON noturno limpa eventos > 30 dias

**Story proposta:** XCL-E.1 "Webhook event dedup ledger" (0.5 dia). PRIORITIZE antes de adicionar handlers de charge/payout.

---

### #2 [MEDIUM] Race em create-account: dois owners = duas Express accounts

**Issue:** Check `stripe_account_id IS NULL` → `stripe.Account.create` → UPDATE. Dois cliques simultaneos criam DUAS contas Express no Stripe, orphan do perdedor cobra LPJ sem gerar receita.

**Fix proposto (ordem de preferencia):**
1. Advisory lock Postgres: `SELECT pg_advisory_xact_lock(hashtext(business_id::text))` no inicio da transaction
2. OR: `SELECT ... FOR UPDATE` + re-check dentro da transaction
3. OR: UNIQUE index parcial `CREATE UNIQUE INDEX ... ON businesses(id) WHERE stripe_account_id IS NOT NULL`

**Story proposta:** XCL-E.2 "Atomic Stripe account creation" (0.25 dia). MEDIUM urgency — so manifesta com 2 owners ativos simultaneos (raro na pratica 3Sisters solo-owner).

---

### #6 [LOW] Secrets lidos em import-time — requer restart para rotate

**Issue:** `STRIPE_SECRET_KEY = os.getenv(...)` no module scope. Ops rotating key precisa redeploy.

**Fix proposto:** Ler dentro de cada função (cache em Redis/memoria se performance for issue). Ou documentar no runbook que rotate = redeploy.

**Prioridade:** BAIXA. Stripe nao rotaciona keys frequentemente.

---

### #7 [INFO] Dead assignment em stripe_connect_service.py:164

**Issue:** `currently_due = reqs.get("currently_due", [])` (linha 163) sobrescrito por `currently_due = reqs.currently_due or []` (linha 164-165) quando hasattr funciona. Nao e bug, so confuso.

**Fix proposto:** Simplificar para uma tentativa unica com `getattr(reqs, "currently_due", None) or reqs.get("currently_due", []) if hasattr(reqs, "get") else []`.

**Prioridade:** COSMETICA.

---

## Total backlog

4 items, ~1 dia total. #1 e #2 devem ser fechados antes de Sprint E item 2 (auto-charge hooks). #6 e #7 sao polish.
