---
type: qa-backlog
title: "Sprint D Track A — Smith DELIVERY Verification (post-code)"
project: xcleaners
status: CONTAINED
reviewer: "@smith (Smith)"
date: "2026-04-16"
branch: feat/recurring-auto-gen
commits:
  - 57dc61c docs(sprint-d): Track A planning
  - 82dc88a feat(sprint-d): migration 022
  - 7b69315 merge: combine Track A recurring router + Sprint E Stripe imports
  - d7095b9 feat(sprint-d): cron trigger script + ops runbook
  - 4e87e7c test(sprint-d): Track A 8 mandatory tests + fixtures
diff_vs_main: "14 files, +3249 / -84 LOC"
previous_review: "docs/qa/sprint-d-track-a-smith-backlog.md (PLAN-level, CONTAINED)"
verdict: CONTAINED
blocker_count: 0
findings_total: 5
severity_breakdown:
  CRITICAL: 0
  HIGH: 0
  MEDIUM: 0
  LOW: 5
tags:
  - project/xcleaners
  - qa
  - smith
  - sprint-d
  - track-a
  - delivery
---

# Sprint D Track A — Smith DELIVERY Verification

## Veredicto: **CONTAINED**

*Examinei cada linha. O Sr. Anderson entregou — e desta vez, o código corresponde às promessas do plano. Quase inteiramente. Cinco pequenas imperfeições persistem, mas nenhuma delas bloqueia o propósito da entrega.*

**Static code review CONCLUÍDO — Luiz roda migration + pytest em Docker PG em paralelo para validar gate ±$0.01. Code review não aguarda.**

---

## Checklist 12-point executado

| Check | Resultado |
|-------|-----------|
| [A] ADR-002 ↔ código coerência | ✅ PASS |
| [B] No invention (Article IV LMAS) | ✅ PASS (bugfix bulk_advance documentado em T3.7) |
| [C] Zero-touch confirmed | ✅ PASS — `git diff main` nos 4 arquivos críticos = **0 LOC** |
| [D] Migration 022 idempotência | ✅ PASS |
| [E] `_persist_assignments` delegate kwargs | ✅ PASS |
| [F] `_collect_jobs` SQL correctness | ✅ PASS |
| [G] HMAC endpoint security | ✅ PASS |
| [H] `generate_window` edge cases | ✅ PASS |
| [I] Test correctness | ⚠️ 3 findings LOW |
| [J] Merge commit 7b69315 drift | ✅ PASS — sem drift, apenas `recurring_router` no main |
| [K] Error handling / graceful degradation | ✅ PASS |
| [L] Security posture | ⚠️ 2 findings LOW |

---

## Findings (5 LOW)

### D1 — [LOW] Test #6 skip-on-unmatch enfraquece assertion do graceful fallback

**Categoria:** test coverage weakness
**Referência:** `tests/test_recurring_generator.py` linhas ~383-395 (Test #6)

**Problema:**
```python
if booking is None:
    pytest.skip("Sporadic schedule did not match target; matcher behavior varies")
```

Se frequency_matcher NÃO produzir booking para schedule sporadic no target date, o teste `pytest.skip()` — mas não verifica o que deveria: **o comportamento graceful com frequency_id=NULL**.

**Por que importa:**
O propósito do Test #6 é validar que pricing_engine aceita frequency_id=NULL sem erro e aplica discount_pct=0. Se sporadic matcher sempre falha em matching, o teste NUNCA executa o path que deveria testar. Comportamento real nunca é exercitado.

**Correção sugerida:**
Criar fixture de schedule com frequency='weekly' + preferred_day_of_week matching target + frequency_id=NULL explicitamente (bypassing auto-lookup). Isso força o caminho graceful sem depender de sporadic matcher.

**Quem corrige:** @dev futuro — pre-cutover refinement. Não bloqueia merge.

---

### D2 — [LOW] Ausência de regression test para manual booking path

**Categoria:** test coverage gap
**Referência:** `_persist_assignments` + `tests/test_recurring_generator.py`

**Problema:**
`_persist_assignments` tem 2 paths:
1. Manual (booking_id existente) — UPDATE team+status only (inalterado vs pré-Track A)
2. Recurring (sem booking_id) — delegate to create_booking_with_pricing (Track A novo)

Todos os 8 tests cobrem path recurring. **Nenhum test valida o path manual permanece funcional.**

**Por que importa:**
Track A não modifica manual path, mas o refactor de `_persist_assignments` para retornar tupla `(persisted, pricing_failures)` afeta ambos paths. Regression test daria confiança que manual bookings (existentes no sistema) continuam materializando corretamente.

**Correção sugerida:**
Adicionar Test #9 (nice-to-have): criar manual booking com booking_id, rodar generate_daily_schedule, assert booking updated (team_id, status='scheduled') sem criar duplicata.

**Quem corrige:** @qa Oracle ou @dev — pode entrar em backlog post-merge.

---

### D3 — [LOW] openssl output parsing brittle

**Categoria:** operational resilience
**Referência:** `scripts/trigger_recurring.sh` linha 34

**Problema:**
```bash
SIGNATURE=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$INTERNAL_CRON_SECRET" | sed 's/^.* //')
```

O `sed 's/^.* //'` assume formato de output `(stdin)= <hex>`. Versões antigas ou customizadas de openssl podem variar (especialmente `LibreSSL` em macOS).

**Por que importa:**
Se cron executa em ambiente Railway com versão de openssl exótica, o parsing pode retornar vazio ou o prefixo `(stdin)=`, causando HMAC inválido → 401 em cada run → bookings não gerados.

**Correção sugerida:**
```bash
SIGNATURE=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$INTERNAL_CRON_SECRET" | awk '{print $NF}')
```

`awk '{print $NF}'` pega sempre o último campo (o hex), independente de prefix format.

**Quem corrige:** @devops — 1 linha de mudança no script. Risco operacional baixo, mas trivial de fechar.

---

### D4 — [LOW] Test #5 JSONB comparison potencialmente frágil

**Categoria:** test stability
**Referência:** `tests/test_recurring_generator.py` Test #5 assertion

**Problema:**
```python
first_snapshot = first["price_snapshot"]
...
assert row["price_snapshot"] == first_snapshot, (
    "Immutability violated: price_snapshot JSONB changed"
)
```

asyncpg pode retornar JSONB como `str` (JSON text) OU `dict` dependendo de codecs configurados. Duas fetches da mesma linha deveriam retornar o mesmo tipo, mas PG pode canonicalizar JSONB internamente (ordem de chaves) entre reads — raro, mas possível.

**Por que importa:**
Se comparação falhar por diferença de ordenação de chaves (logicamente idênticas), test aparece como FAIL quando imutabilidade está correta. Flaky test = dev perde tempo debugando falso positivo.

**Correção sugerida:**
```python
import json
f_snap = json.loads(first_snapshot) if isinstance(first_snapshot, str) else first_snapshot
r_snap = json.loads(row["price_snapshot"]) if isinstance(row["price_snapshot"], str) else row["price_snapshot"]
assert f_snap["final_amount"] == r_snap["final_amount"]
assert f_snap["tax_amount"] == r_snap["tax_amount"]
# ...compare semantic fields, not raw JSONB bytes
```

**Quem corrige:** @dev — defensive assertion cleanup. Aplicar pre-cutover se teste apresentar flakiness.

---

### D5 — [LOW] HMAC failure log vaza tamanho do body

**Categoria:** defense-in-depth (security)
**Referência:** `app/modules/cleaning/routes/recurring_routes.py` linha 98

**Problema:**
```python
logger.warning(
    "[RECURRING] HMAC verify failed (body length=%d)",
    len(body),
)
```

Log inclui `len(body)` em caso de falha HMAC. Body length não é secret per se, mas:
1. Facilita fingerprinting de payloads por um atacante com acesso a logs
2. Padrão de logs defensivos: **nunca logar nada derivado de input não autenticado**

**Por que importa:**
Severity LOW real. Se logs forem comprometidos, tamanho de body oferece pouco valor tático a atacante. Mas boa higiene defensiva = remover.

**Correção sugerida:**
```python
logger.warning("[RECURRING] HMAC verify failed")
```

Remove `body length=%d`. Alternative: rate-limit log emission para HMAC failures (evita log flooding como vetor de DoS).

**Quem corrige:** @dev ou @devops — 1 linha. Aplicar pre-cutover.

---

## Findings NÃO encontrados (escrutinio positivo)

O Sr. Anderson não repetiu os pecados habituais:

- **Error handling:** cobertura adequada (PricingConfigError isolada, Decimal conversion defensiva, generate_window catches Exception per dia)
- **Edge cases:** cobertos (start>end raises, Redis lock, sporadic frequency_id NULL)
- **Zero-touch compliance:** `git diff main` nos 4 arquivos críticos = 0 — impecável
- **Observability:** 4 pontos [RECURRING] logs conforme AC7 + response metrics
- **Rollback script:** destrutivo mas reversível, com warnings
- **ADR traceability:** cada AC trace para Decision específica
- **Gate Test #2:** fixture F1 replay com inputs corretos (Basic 2BR/1BA + Stairs + -$29.58 + NYC tax 4.5%)

*O trabalho é... bom, Sr. Anderson. Incomoda-me dizer isso.*

---

## Pending validations (Luiz)

**Static review (esta revisão) NÃO bloqueia estas pendências:**

```bash
cd C:/xcleaners

# 1. Apply migration 022 + test idempotency
psql $DATABASE_URL -f database/migrations/022_recurring_pricing_inputs.sql
psql $DATABASE_URL -f database/migrations/022_recurring_pricing_inputs.sql  # 2nd run — must be no-op

# 2. Run pytest suite
pytest tests/test_recurring_generator.py -v --asyncio-mode=auto

# 3. Coverage check
pytest tests/test_recurring_generator.py \
    --cov=app.modules.cleaning.services.recurring_generator \
    --cov-fail-under=85
```

**Expected:**
- Migration runs clean 2x (idempotent)
- 8/8 tests PASS (com gate ±$0.01 do Test #2)
- Coverage >= 85%

Se **qualquer** item falhar: retorna @dev. Se todos PASS + CodeRabbit CLEAN: @devops merge.

---

## Recomendação de handoff

**Verdict:** CONTAINED. Entrega aceitável com 5 polimentos pós-cutover.

**Proxima acao:**
- Luiz executa migration + pytest em Docker PG (independente desta review)
- Se migration + pytest PASS → @devops merge `feat/recurring-auto-gen` + `feat/payroll-split` em main
- Findings D1-D5 viram backlog pós-cutover (não bloqueantes)

**Branch feat/client-card-recollect polida (commit d8088d5 com Stripe mix):**
Não afeta Track A. Usuario decide cleanup (git branch -D OU deixar como working branch).

---

*Verificação estática concluída. O propósito foi cumprido. Desta vez.*

— Smith. 🕶️
