# Sprint Plan — AI Turbo 2 Dias

**Sprint ID:** `AI-TURBO-2026-04-20`
**Branch:** `feat/ai-fix-turbo` (a partir de `main` @ `3ee6e3f`)
**Motor:** OpenAI GPT-4.1 Mini (function calling)
**Pasta de trabalho:** `C:\xcleaners\` (exclusiva)
**Fonte de portagem (READ-ONLY):** `C:\clawtobusiness\app\`
**Deadline:** 2026-04-22 fim do Dia 2
**Arquiteto:** Aria | **Executor:** @dev (Neo) | **Verifier:** @smith

---

## Objetivo

IA conversacional cliente-first. Cliente logado conversa no portal, IA calcula preço real via pricing_engine, verifica disponibilidade real, cria draft (`status='draft'`), owner aprova com 1 clique no UI existente (tab Pending em `bookings.js`).

## Princípio arquitetural (INQUEBRÁVEL)

1. Todo trabalho EXCLUSIVAMENTE em `C:\xcleaners\`.
2. `C:\clawtobusiness\app\` é fonte READ-ONLY — zero escrita lá.
3. Toda tool IA passa pelo gateway `ai_tools.execute_tool` — nunca SQL direto.
4. Preço SEMPRE via `pricing_engine.calculate_booking_price`.
5. IA cria draft, **nunca** `status='scheduled'` diretamente nesta sprint (owner aprova).

## Escopo

### IN (esta sprint)
- Fix 2 bugs AI seed
- Switch OpenAI GPT-4.1 Mini como default
- Portagem: `circuit_breaker`, `moderation_service`, `rate_limiter` (parcial)
- Portagem: scheduler base (APScheduler)
- Portagem: chat frontend assets (`chat.js`, `chat.css`)
- Portagem: WhatsApp Evolution API adapter
- Tools novas: `check_availability`, `get_price_quote`, `get_services_catalog`, `propose_booking_draft`
- Endpoint `/api/v1/clean/{slug}/ai/chat` (homeowner role)
- System prompt scheduling customer

### OUT (backlog pós-turbo)
- Advisory lock PostgreSQL (usa `SELECT FOR UPDATE` simples)
- Classificador de risco automático
- Fix Caminho A `homeowner_routes.py` pricing
- Memory system completo (stub só)
- Language persistence PT/EN/ES (stub só — detect mas sem persistir)
- Observabilidade Grafana
- Testes automatizados
- Feature flag per-business

---

## Pre-flight (15 min — Dia 1 manhã)

```bash
# 1. Confirmar working tree limpo
cd C:\xcleaners
git status  # DEVE retornar vazio

# 2. Sync main
git fetch origin && git pull origin main

# 3. Criar branch feature
git checkout -b feat/ai-fix-turbo

# 4. Confirmar app/config.py tem AI_PROVIDER, OPENAI_API_KEY, OPENAI_MODEL_PRIMARY
grep -E "AI_PROVIDER|OPENAI_API_KEY|OPENAI_MODEL" app/config.py
```

Se `app/config.py` não tiver `OPENAI_MODEL_PRIMARY`, **STOP** e adicionar antes de continuar (é config, não refactor — 5 min).

---

## DIA 1 — Backend + Portagem (8h)

### Bloco 1.1 — Fix AI seed (30 min) — P0

**Arquivo:** `app/modules/cleaning/services/ai_scheduling.py`

**Mudanças:**

1. **Linhas 322-335** (`suggest_team_assignment`):
   - Trocar `LEFT JOIN cleaning_client_schedules cs ON cs.id = b.client_id` por `LEFT JOIN cleaning_clients c ON c.id = b.client_id`
   - Trocar `LEFT JOIN cleaning_service_types st` por `LEFT JOIN cleaning_services s`
   - Trocar `b.service_type_id` por `b.service_id`
   - Trocar `cs.client_name` por `c.first_name || ' ' || COALESCE(c.last_name, '')`
   - Trocar `cs.preferred_team_id` por subquery em `cleaning_client_schedules` OU remover (coluna já vive em client schedule, não em client)
   - Trocar `st.name` por `s.name`

2. **Linhas 389-503** (`predict_duration`):
   - Remover `b.actual_duration_minutes` (coluna não existe)
   - Substituir por `EXTRACT(EPOCH FROM (b.actual_end - b.actual_start)) / 60 AS actual_duration_minutes`
   - Adicionar filtro `AND b.actual_start IS NOT NULL AND b.actual_end IS NOT NULL`
   - Trocar `cleaning_service_types` por `cleaning_services`
   - Trocar `service_type_id` por `service_id`
   - Ajustar `st_row` para `cleaning_services.estimated_duration_minutes` (já existe)

**Gate de aceitação:** curl dos endpoints `/ai/suggest-team/{booking_id}` e `/ai/predict-duration` retornam JSON coerente com dados do banco (não mais "Booking not found" falso positivo).

---

### Bloco 1.2 — Switch OpenAI GPT-4.1 Mini (30 min) — P0

**Arquivos:**
- `app/config.py` — confirmar/adicionar:
  - `AI_PROVIDER = os.getenv("AI_PROVIDER", "openai")` (default openai)
  - `OPENAI_MODEL_PRIMARY = os.getenv("OPENAI_MODEL_PRIMARY", "gpt-4.1-mini")`
- `.env.example` — adicionar:
  ```
  AI_PROVIDER=openai
  OPENAI_API_KEY=sk-...
  OPENAI_MODEL_PRIMARY=gpt-4.1-mini
  MODERATION_ENABLED=true
  MODERATION_MODEL=omni-moderation-latest
  ```
- `app/modules/cleaning/services/ai_scheduling.py:194` — trocar `"gpt-4o-mini"` por `OPENAI_MODEL_PRIMARY` do config

**Gate:** config centralizada, `.env.example` atualizado, import funciona.

---

### Bloco 1.3 — Portagem infra (1.5h) — P0

Copiar de `C:\clawtobusiness\app\` para `C:\xcleaners\app\` e ajustar imports (substituir `clawin.` por `xcleaners.`):

| De | Para | Notas |
|---|---|---|
| `app/core/circuit_breaker.py` | `app/core/circuit_breaker.py` (criar `app/core/` se não existir) | Usado por ai_scheduling quando refatorado |
| `app/moderation_service.py` | `app/moderation_service.py` | Classe `ModerationService.check(text)` |
| `app/security.py` (só função `rate_limiter`) | Mesclar com `app/xcleaners_main.py` middleware OU novo `app/rate_limit.py` | Rate limit por user_id |

Após portagem:
```bash
python -c "from app.core.circuit_breaker import cb_primary, cb_fallback; print('ok')"
python -c "from app.moderation_service import ModerationService; print('ok')"
```

**Gate:** imports rodam sem erro. Dependência nova em requirements.txt se `apscheduler` não estiver (`apscheduler>=3.10.0`).

---

### Bloco 1.4 — Tools novas (2h) — P0

**Arquivo novo:** `app/modules/cleaning/services/availability_service.py`

Função `is_slot_available(db, business_id, scheduled_date, scheduled_start, duration_minutes, team_id=None) -> dict`:
- Usa `SELECT FOR UPDATE` sobre `cleaning_bookings` no intervalo `[scheduled_start, scheduled_end]` (end = start + duration)
- Retorna `{available: bool, conflicts: [...], end_time, buffer_violations}`
- Reusa `conflict_resolver.detect_time_overlaps` + `detect_travel_buffer_violations`

**Arquivo:** `app/modules/cleaning/services/ai_tools.py` — adicionar 4 tools ao `AI_TOOLS` registry:

1. `check_availability` — wrapper sobre `availability_service.is_slot_available`
2. `get_price_quote` — wrapper sobre `pricing_engine.calculate_booking_price`
3. `get_services_catalog` — query `cleaning_services` + `cleaning_extras` + `cleaning_frequencies` ativos por `business_id`
4. `propose_booking_draft` — chama `booking_service.create_booking_with_pricing` com `status='draft'`, `source='ai_chat'`

Adicionar dispatch no `execute_tool(tool_name, tool_input, business_id, db)`.

**Gate:** `from app.modules.cleaning.services.ai_tools import AI_TOOLS; assert len(AI_TOOLS) == 10` (6 existentes + 4 novas).

---

### Bloco 1.5 — Endpoint `/ai/chat` (1.5h) — P0

**Arquivo:** `app/modules/cleaning/routes/ai_routes.py` — adicionar endpoint:

```
POST /api/v1/clean/{slug}/ai/chat
Auth: require_role("homeowner")
Body: { message: str, conversation_id: str? }
Response: { response: str, conversation_id: str, proposed_draft_id: str? }
```

Pipeline interno:
1. Moderation check (skip se disabled)
2. Rate limit 30/60s por user
3. Carregar/criar conversation em `conversations` table (já existe no schema)
4. Salvar user message em `messages` (encrypted via Fernet — ver schema)
5. Chamar `_run_openai_tools` (já existe em `ai_scheduling.py`) com system prompt de scheduling customer + tools
6. Salvar assistant message
7. Retornar response + draft_id se IA criou via `propose_booking_draft`

**System prompt** (inline no endpoint ou novo arquivo `app/prompts/scheduling_customer.py`):
```
You are the scheduling assistant for {business_name}. You help homeowners book cleaning services. 
Use tools to check availability, get prices, and propose bookings. 
Never invent prices or times — always call tools. 
Confirm with customer before proposing the booking draft. 
After proposing, tell the customer the owner will confirm within [X hours].
```

**Gate:** curl autenticado como homeowner retorna response coerente + cria entry em `conversations`.

---

### Bloco 1.6 — Smith + commit Dia 1 (1h) — P0

1. `@smith *verify` sobre os 5 blocos (1.1-1.5)
2. Fix qualquer CRITICAL/HIGH
3. Commit atômico por bloco:
   ```
   fix(ai): corrigir JOINs schema em suggest_team e predict_duration
   feat(ai): switch para OpenAI GPT-4.1 Mini como motor primario
   feat(ai): portar circuit_breaker + moderation + rate_limiter do clawtobusiness
   feat(ai): availability_service + 4 novas tools para pricing/catalog/draft
   feat(ai): endpoint /ai/chat com tool_use loop + conversation persistence
   ```
4. Atualizar `projects/xcleaners/PROJECT-CHECKPOINT.md` — seção "Último Trabalho"

**Smith gate:** verdict CONTAINED ou CLEAN. Se INFECTED/COMPROMISED, parar e fixar.

---

## DIA 2 — Frontend + Canais + Polish (8h)

### Bloco 2.1 — Frontend chat widget (2.5h) — P0

**Portagem:**
- `C:\clawtobusiness\frontend\static\js\chat.js` → `C:\xcleaners\frontend\cleaning\static\js\homeowner\ai-chat.js`
- `C:\clawtobusiness\frontend\static\css\chat.css` → `C:\xcleaners\frontend\cleaning\static\css\ai-chat.css`

Ajustes:
- Endpoint: `/api/v1/clean/{slug}/ai/chat` (homeowner-authenticated)
- Remover referências sales-specific (CTAs de upgrade, etc.)
- Integrar no portal homeowner existente (`frontend/cleaning/app.html` OU similar)
- Quando response contém `proposed_draft_id`, mostrar card "Solicitação enviada — aguardando confirmação"

**Gate:** cliente logado abre portal, vê widget de chat, digita, recebe response, vê draft card.

---

### Bloco 2.2 — Scheduler APScheduler (1h) — P1

**Portagem:**
- `C:\clawtobusiness\app\scheduler.py` → `C:\xcleaners\app\scheduler.py`
- Adaptar jobs:
  - Remove Telegram follow-up (não aplicável)
  - Adicionar `generate_daily_schedule` diário às 5am (business timezone-aware)
  - Adicionar 24h reminder sweep a cada hora
  - Adicionar draft TTL cleanup a cada 5 min (drafts com > 24h em `status='draft'` → notificar owner)

Wire-in no `xcleaners_main.py` via FastAPI lifespan.

**Gate:** scheduler inicia com app, jobs registrados visíveis nos logs.

---

### Bloco 2.3 — WhatsApp Evolution API (2h) — P1

**Portagem:**
- `C:\clawtobusiness\app\modules\channels\whatsapp.py` → `C:\xcleaners\app\modules\channels\whatsapp.py`
- `C:\clawtobusiness\app\modules\channels\message_buffer.py` → mesma estrutura
- `C:\clawtobusiness\app\modules\channels\abuse_guard.py` → mesma estrutura
- `C:\clawtobusiness\app\modules\channels\base.py` → idem
- `C:\clawtobusiness\app\modules\channels\models.py` → idem

Wire-in:
- Rota webhook `/api/v1/clean/{slug}/whatsapp/webhook` em `app/modules/cleaning/routes/`
- Ao receber mensagem, resolver `client` via phone → `cleaning_clients.phone`
- Chamar mesmo pipeline do `/ai/chat` com `channel='whatsapp'`
- Enviar response via Evolution API adapter

**Env vars necessárias** em `.env.example`:
```
EVOLUTION_API_URL=https://...
EVOLUTION_API_KEY=...
EVOLUTION_INSTANCE_NAME=xcleaners
```

**Se env vars não existirem em prod:** canal WhatsApp fica disabled. Não bloqueia deploy. Chat web funciona independente.

**Gate:** webhook responde 200 a ping. Fluxo end-to-end só testado se env configurado.

---

### Bloco 2.4 — Teste end-to-end manual (1.5h) — P0

Cenários obrigatórios:

1. **Happy path web:** homeowner logado abre portal → chat → pede "cleaning this Friday 10am" → IA consulta services + availability + price → propõe draft → owner vê em Pending tab → aprova → `status='scheduled'` + email enviado.

2. **Conflito:** pede horário ocupado → IA propõe 3 alternativas.

3. **Fora da área:** pede em zip code não coberto → IA informa zips atendidos.

4. **Preço:** compara quote IA vs `POST /api/v1/clean/{slug}/pricing/preview` — tem que bater.

5. **Cliente fora do sistema:** phone não encontrado (WhatsApp) → mensagem genérica de onboarding.

**Smith gate final:** verdict CONTAINED ou CLEAN sobre todo o sprint.

---

### Bloco 2.5 — Deploy staging + checkpoint (1h) — P0

1. `@devops *push` para branch `feat/ai-fix-turbo`
2. Deploy staging Railway (ou ambiente equivalente)
3. Smoke test no staging
4. Atualizar `projects/xcleaners/PROJECT-CHECKPOINT.md` — marcar sprint como COMPLETO
5. Criar PR `feat/ai-fix-turbo` → `main`

**Merge pra main:** só após validação do Luiz no staging.

---

## Rollback (se algo der errado)

1. Branch isolada — não afeta `main`
2. `git checkout main && git branch -D feat/ai-fix-turbo` limpa tudo
3. Nenhuma migration destrutiva nesta sprint (só leitura + INSERT `status='draft'`)
4. Env vars novas são aditivas — não quebram existente

## Dependências externas

| Item | Obrigatório? | Fallback |
|---|---|---|
| `OPENAI_API_KEY` | SIM | Sem chave → endpoint `/ai/chat` retorna 503 |
| `MODERATION_ENABLED=true` | Não | `false` pula moderation |
| `EVOLUTION_API_URL`+`EVOLUTION_API_KEY` | Não | Sem chave → canal WhatsApp disabled, web funciona |
| `apscheduler>=3.10.0` | SIM pra Bloco 2.2 | Sem lib → scheduler skipped |

## Arquivos tocados (resumo)

### Novos (criar em `C:\xcleaners\`)
- `app/core/__init__.py` (se não existir)
- `app/core/circuit_breaker.py`
- `app/moderation_service.py`
- `app/scheduler.py`
- `app/modules/cleaning/services/availability_service.py`
- `app/modules/channels/__init__.py`
- `app/modules/channels/whatsapp.py`
- `app/modules/channels/message_buffer.py`
- `app/modules/channels/abuse_guard.py`
- `app/modules/channels/base.py`
- `app/modules/channels/models.py`
- `app/prompts/__init__.py` (se não existir)
- `app/prompts/scheduling_customer.py`
- `frontend/cleaning/static/js/homeowner/ai-chat.js`
- `frontend/cleaning/static/css/ai-chat.css`
- `docs/sprints/ai-turbo-sprint-2026-04-20.md` (este arquivo)

### Editados
- `app/config.py` (AI vars)
- `app/xcleaners_main.py` (wire scheduler + router chat)
- `.env.example`
- `app/modules/cleaning/services/ai_scheduling.py` (fix 2 bugs + switch model)
- `app/modules/cleaning/services/ai_tools.py` (+4 tools)
- `app/modules/cleaning/routes/ai_routes.py` (+endpoint /ai/chat)
- `requirements.txt` (+apscheduler)
- `frontend/cleaning/app.html` ou portal homeowner (integrar chat widget)

---

## Checkpoint triggers

@dev DEVE atualizar `C:\clawtobusiness\projects\xcleaners\PROJECT-CHECKPOINT.md` após:
- Fim do Dia 1 (5 blocos concluídos + smith verify)
- Fim do Dia 2 (todos blocos + deploy staging)
- Qualquer falha que bloqueie sprint (detalhar reason)

---

**Status:** AUTHORIZED — aguardando @dev iniciar Bloco 1.1
**Criado por:** Aria (architect)
**Timestamp:** 2026-04-20
