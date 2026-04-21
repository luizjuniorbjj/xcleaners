# AI Turbo Sprint — Day 2 COMPLETE (Handoff)

**Data:** 2026-04-21
**Branch:** `feat/ai-fix-turbo`
**HEAD remote:** `7621948` (commit topo do outro terminal testes E2E)
**Meu HEAD:** `4c49a73` (Smith Dia 2 fix-forward, logo abaixo)
**Status:** ✅ Código completo no GitHub — aguardando decisão Luiz sobre deploy

---

## Resumo executivo

Sprint AI Turbo concluído. **12 commits meus** na branch (Dia 1 + Dia 2 + 2 fix-forwards Smith). 1 commit adicional do outro terminal (32 testes E2E Playwright PASS). Smith verdict final: **CONTAINED**.

**Código está pushed no GitHub:**
👉 https://github.com/luizjuniorbjj/xcleaners/tree/feat/ai-fix-turbo  
👉 PR sugerido: https://github.com/luizjuniorbjj/xcleaners/pull/new/feat/ai-fix-turbo

**Deploy staging NÃO foi executado** — requer sua decisão arquitetural. Ver seção "Decisão pendente" abaixo.

---

## O que está na branch

### Blocos completos (12 commits meus)

| Bloco | Commit | Entrega |
|---|---|---|
| Dia 1.1 | `2218fb2` | Fix JOINs schema `ai_scheduling.py` + switch OpenAI GPT-4.1 Mini |
| Dia 1.3 | `c9f0337` | Portagem `circuit_breaker` + `moderation_service` + `rate_limiter` de clawtobusiness |
| Dia 1.4 | `1971adb` | `availability_service` + 4 tools novas (check_availability, get_price_quote, get_services_catalog, propose_booking_draft) |
| Dia 1.5 | `a3dc161` | Endpoint `POST /api/v1/clean/{slug}/ai/chat` + system prompt scheduling customer |
| Plan | `5364718` | sprint plan executável |
| Dia 1 fix | `7f13327` | Smith C-1 CRITICAL (client_id ownership via auth_context) + H-1 HIGH (fail-closed gates) + M-3 MEDIUM (conversation reuse) |
| Dia 1.7 | `54fb961` | ICS attachment Google Calendar + fix schema em booking emails |
| Dia 2.2 | `c5221e8` | APScheduler 3 jobs (daily_schedule 5am / reminders_24h / draft_ttl 5min) |
| Dia 2.1 | `087d231` | Frontend chat widget homeowner (portado + 7 adaptações de clawtobusiness) |
| Dia 2.3 | `057fa6a` | WhatsApp Evolution API adapter + webhook `/whatsapp/webhook` |
| Docs | `cfbc55c` | E2E test plan (10 cenários) + backlog pos-sprint (17 items) |
| Dia 2 fix | `4c49a73` | Smith C-2 CRITICAL (missing `await` em scheduler) + M-2D MEDIUM (WhatsApp moderation + rate_limit) |

### Arquivos novos
- `app/utils/ics_generator.py` (RFC 5545 compliant)
- `app/scheduler.py` (APScheduler)
- `app/moderation_service.py` (OpenAI Moderation wrapper)
- `app/rate_limiter.py` (Redis primary + memory fallback)
- `app/modules/cleaning/services/availability_service.py`
- `app/modules/channels/{__init__,base,models,whatsapp}.py`
- `app/modules/cleaning/routes/whatsapp_routes.py`
- `app/prompts/{__init__,scheduling_customer}.py`
- `frontend/cleaning/static/js/homeowner/ai-chat.js`
- `frontend/cleaning/static/css/ai-chat.css`
- `docs/sprints/ai-turbo-sprint-2026-04-20.md` (plan)
- `docs/sprints/backlog-ai-turbo-postsprint.md` (17 items)
- `docs/qa/day-2-e2e-test-plan.md` (10 cenários)

### Arquivos editados
- `app/config.py` (+ AI vars + MODERATION + GATES_FAIL_CLOSED)
- `app/core/circuit_breaker.py` (logger namespace)
- `.env.example` (+ AI + Evolution + gates)
- `app/modules/cleaning/services/ai_scheduling.py` (fixes schema + auth_context flow)
- `app/modules/cleaning/services/ai_tools.py` (+ 4 tools + TOOLS_REQUIRING_AUTH_CONTEXT)
- `app/modules/cleaning/routes/ai_routes.py` (+ /ai/chat endpoint + Smith fixes)
- `app/modules/cleaning/services/email_service.py` (ICS attachment + fix schema)
- `xcleaners_main.py` (+ scheduler + whatsapp_router)
- `frontend/cleaning/app.html` (+ chat CSS + JS)

---

## ⚠️ Decisão pendente — DEPLOY

Descoberta crítica durante pre-flight:

| Campo | Valor |
|---|---|
| Railway project | `xcleaners` (ID `006be8f9-c53b-4cbb-b409-47eeafd9a372`) |
| Railway environment | **`production`** |
| Domínios servidos | `https://app.xcleaners.app`, `https://xcleaners.app`, `https://cleanclaw-api-production.up.railway.app` |

**Implicação:** o único environment do Railway é `production`. Deploy via `railway up` impacta **diretamente o site ao vivo dos clientes**. Não há environment `staging` separado.

**Por isso NÃO fiz deploy** — minha rule de devops exige User Confirmation Required antes de operações irreversíveis. Prefiro que você acorde e decida.

### 3 opções para você escolher

#### Opção 1 — Criar environment `staging` no Railway (RECOMENDADA, ~15 min)
```bash
cd C:\xcleaners
railway environment new staging
railway environment staging        # link CLI ao env staging
# Setar env vars específicas de staging
railway variables set AI_PROVIDER=openai
railway variables set OPENAI_API_KEY=<sua-key>
railway variables set AI_MODEL_PRIMARY=gpt-4.1-mini
railway variables set MODERATION_ENABLED=true
railway variables set GATES_FAIL_CLOSED=true
railway variables set EVOLUTION_API_URL=http://204.168.134.70:8443
railway variables set EVOLUTION_API_KEY=<sua-key>
railway variables set EVOLUTION_INSTANCE_NAME=xcleaners
railway variables set EVOLUTION_WEBHOOK_SECRET=$(openssl rand -hex 32)
# Deploy
railway up --environment staging
```

Vantagens: testa tudo sem risco em prod. Pode iterar à vontade. Depois de validado via `docs/qa/day-2-e2e-test-plan.md`, mergea `feat/ai-fix-turbo` → `main` → deploy automático em prod.

#### Opção 2 — Merge direto + deploy production (após validação local)
Se confiar no sprint e tiver feito smoke test local:
```bash
gh pr create --title "feat: AI Turbo Sprint — chat scheduling + WhatsApp + ICS" --body "Ver docs/sprints/day-2-complete-handoff.md" --base main
# Review + merge manual no GitHub
# Deploy automático dispara se Railway ligado pra main
```

Risco: bugs em prod afetam clientes reais. Sprint teve **1 CRITICAL + 1 HIGH** que Smith achou — tratados, mas Smith não testa em runtime real.

#### Opção 3 — Manter em branch até você validar (mais conservadora)
```bash
# Nada a fazer agora
# Rodar app local C:\xcleaners uvicorn xcleaners_main:app
# Validar docs/qa/day-2-e2e-test-plan.md cenários 1-10 local
# Depois decidir Opção 1 ou 2
```

---

## Env vars críticas que VÃO FALTAR

`railway variables` listou o environment production atual. As seguintes **NÃO existem** e a IA/WhatsApp falham sem elas:

| Variável | Obrigatória? | Efeito se falta |
|---|---|---|
| `AI_PROVIDER=openai` | Recomendada | Default é openai no config.py; OK |
| `OPENAI_API_KEY` | **SIM** | `/ai/chat` retorna 503 "AI service unavailable" |
| `AI_MODEL_PRIMARY=gpt-4.1-mini` | Recomendada | Default já é gpt-4.1-mini no config.py |
| `MODERATION_ENABLED=true` | Recomendada | Default true |
| `GATES_FAIL_CLOSED=true` | **SIM em prod** | Sem isso, gates falham silenciosos (anti-Smith H-1) |
| `EVOLUTION_API_URL=http://204.168.134.70:8443` | Opcional | Sem isso, canal WhatsApp fica disabled (não quebra) |
| `EVOLUTION_API_KEY` | Opcional (só se WA) | Sem isso, WhatsApp endpoint `/status` retorna not_configured |
| `EVOLUTION_INSTANCE_NAME=xcleaners` | Opcional | Default xcleaners no route |
| `EVOLUTION_WEBHOOK_SECRET=<rand-hex-32>` | Opcional | Sem isso, webhook valida=true sem secret |

**Ação:** antes de deploy (Opção 1 ou 2), setar `OPENAI_API_KEY` + `GATES_FAIL_CLOSED=true` no mínimo.

---

## Smoke test pós-deploy

Quando você deployar (Opção 1 ou 2), verificar logs:

```bash
railway logs --tail
```

Deve aparecer:
```
[OK] Xcleaners API ready
[SCHED] APScheduler started — jobs: ['daily_schedule', 'reminders_24h', 'draft_ttl']
```

Depois rodar cenários em `docs/qa/day-2-e2e-test-plan.md`:
- C1 Happy path web (P0)
- C2 Conflito de horario (P0)
- C4 Prompt injection (P0 SECURITY — valida Smith C-1)
- C6 Moderation fail-closed (P1 SECURITY — valida Smith H-1)
- C8 Scheduler logs (P1 — valida Smith C-2)

---

## Backlog pós-sprint (não bloqueia launch)

Todos documentados em `docs/sprints/backlog-ai-turbo-postsprint.md`:

- **HIGH (2)**: business_channels multi-tenant + Evolution HTTPS — endereçar antes de abrir chat pro cliente final em produção.
- **MEDIUM (6)**: auth extensions, Fernet encryption de messages, audit log, conversations.business_id migration, race lock, chat_pipeline helper dedup.
- **LOW (9)**: overnight overflow, str.format, Retry-After, 5 tools legadas, audio WhatsApp, cross-msg threading, message_buffer, per-business TZ reminders, owner channels UI.

---

## Rollback plan (se algo der errado pós-deploy)

1. **Revert do código em prod:**
   ```bash
   git checkout main
   git revert <merge-commit>
   git push origin main   # só @devops/Operator
   ```
   Railway auto-deploya rollback.

2. **Ou rollback instant via Railway dashboard:**
   - Dashboard → Deploys → Previous deploy → "Redeploy"

3. **Sem migrations destrutivas neste sprint** — nenhum risco de dados.

---

## Próximo passo concreto

1. **Você lê este doc** (você está lendo).
2. Decide entre Opção 1, 2 ou 3.
3. Executa os comandos da opção escolhida OU passa comando pro @devops via Claude Code.
4. Roda smoke test + cenários E2E.
5. Se tudo OK, merge `feat/ai-fix-turbo` → `main`.

---

**Operator assinando.** Código no GitHub. Deploy na sua mão.

— Operator, deployando com confiança (quando autorizado) 🚀
