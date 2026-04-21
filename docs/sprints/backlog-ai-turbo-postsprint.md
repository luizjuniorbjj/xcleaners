# Backlog Post-Sprint — AI Turbo (2026-04-20/21)

**Sprint:** `feat/ai-fix-turbo`
**Status sprint:** todos os blocos P0 entregues. Backlog abaixo = findings registrados pelo Smith + constraints de tempo conhecidas.
**Criterio de priorizacao:** LOW nao bloqueia launch. MEDIUM deveria entrar em Sprint 2. HIGH bloqueia abrir pro cliente final.

---

## HIGH — endereçar antes de abrir chat pro cliente final em producao

### HIGH-1 · `business_channels` table + per-business WhatsApp config

**Origem:** auto-verify 2026-04-21. Clawtobusiness usa `business_channels` table com `config` JSONB + `credentials_encrypted` BYTEA (Fernet). Xcleaners implementou WhatsApp com **env vars globais** (1 instance compartilhada) por MVP. Nao escala pra multiplos businesses com WhatsApp proprio.

**Arquivos afetados:**
- `database/migrations/029_business_channels.sql` (criar)
- `app/modules/channels/service.py` (portar de clawtobusiness — CRUD + Fernet credentials)
- `app/modules/cleaning/routes/whatsapp_routes.py` (refactor: ler config via service em vez de env)
- `app/modules/cleaning/routes/channels_routes.py` (criar — owner connect WhatsApp via QR)
- Frontend `/owner/settings/channels` UI (QR display + status)

**Effort:** 3-4 dias

**Sprint sugerido:** 2

---

### HIGH-2 · Evolution API em HTTPS + webhook signature obrigatoria

**Origem:** 2026-04-21. Servidor Evolution atual e HTTP na porta 8443 (cleartext). Webhook signature aceita clear text passa por intermediarios.

**Mitigacao:**
- Colocar Evolution atras de Cloudflare/Caddy com Let's Encrypt
- Ou provisionar cert direto no container Evolution
- Tornar `EVOLUTION_WEBHOOK_SECRET` obrigatoria quando `GATES_FAIL_CLOSED=true`

**Effort:** 4-6h (infra-side)

**Sprint sugerido:** 2

---

## MEDIUM — endereçar em Sprint 2

### MEDIUM-1 · authenticated_client_id enforcement para reschedule/cancel tools

**Origem:** Smith C-1 follow-up. Quando `propose_reschedule` e `propose_cancel` forem adicionadas ao `AI_TOOLS` registry, precisam do mesmo pattern do `propose_booking_draft` (Gate 2 auth_context).

**Arquivo:** `app/modules/cleaning/services/ai_tools.py`

**Fix:** adicionar tool name em `TOOLS_REQUIRING_AUTH_CONTEXT = {"propose_booking_draft", "propose_reschedule", "propose_cancel"}` e replicar validacao nos handlers.

**Effort:** 1-2h por tool nova

---

### MEDIUM-2 · Fernet encryption de `messages.content_encrypted`

**Origem:** Smith backlog Dia 1. Schema ja tem coluna BYTEA mas estamos gravando plaintext UTF-8. `app.security.encrypt_data` existe herdado do fork mas nao foi wired.

**Arquivo:** `app/modules/cleaning/routes/ai_routes.py` (linha ~344, 380) + `whatsapp_routes.py:_persist_conversation`

**Fix:**
```python
from app.security import encrypt_data
...
content_encrypted = encrypt_data(message, user_id)  # Fernet com salt user_id
```

**Effort:** 30min + validar decrypt no admin view

---

### MEDIUM-3 · `db.log_audit` stub em app/database.py

**Origem:** Smith M-4 Dia 1. Endpoint `/ai/chat` nao grava audit log porque `db.log_audit` nao existe em xcleaners (herdado, mas stub nao implementado).

**Arquivo:** `app/database.py` + `app/modules/cleaning/routes/ai_routes.py` + `whatsapp_routes.py`

**Fix:**
1. Adicionar metodo `log_audit(user_id, action, details)` em `Database` class
2. Pode persistir em tabela `audit_log` OU apenas `logger.info` estruturado como primeiro step
3. Chamar apos INSERT de messages

**Effort:** 2-3h (schema migration + wiring)

---

### MEDIUM-4 · Migration `conversations.business_id` column

**Origem:** Smith N-2 Dia 1. Tabela herdada do clawtobusiness nao tem `business_id`. Fix M-3 (EXISTS cleaning_clients) bloqueia o caso principal mas deixa residual: user multi-business pode cruzar conversas entre seus proprios contexts.

**Arquivo:** `database/migrations/030_conversations_business_id.sql`

**Fix:**
```sql
ALTER TABLE conversations ADD COLUMN business_id UUID REFERENCES businesses(id);
-- backfill: pra cada conversation, inferir business_id via cleaning_clients
UPDATE conversations c SET business_id = (
  SELECT cc.business_id FROM cleaning_clients cc WHERE cc.user_id = c.user_id LIMIT 1
);
-- enforce NOT NULL apos backfill
```

Adicionar `business_id` em todos INSERT/SELECT de conversations em ai_routes.py + whatsapp_routes.py.

**Effort:** 2-3h

---

### MEDIUM-5 · Race TOCTOU entre check_availability e propose_booking_draft

**Origem:** Smith backlog Dia 1. `availability_service.is_slot_available` usa SELECT simples sem lock. Entre o check e o INSERT do draft, outra request pode criar conflito.

**Mitigacao atual:** `propose_booking_draft` re-chama `is_slot_available` antes do INSERT (defense-in-depth).

**Fix definitivo:**
- Advisory lock PostgreSQL em `propose_booking_draft`: `SELECT pg_advisory_xact_lock(hashtextextended(business_id || scheduled_date || scheduled_start, 0))`
- Ou UNIQUE partial index: `CREATE UNIQUE INDEX ON cleaning_bookings (business_id, client_id, scheduled_date, scheduled_start) WHERE status IN ('draft', 'scheduled', 'confirmed')`

**Effort:** 2-3h

---

### MEDIUM-6 · `chat_pipeline` helper extraido

**Origem:** Bloco 2.3 WhatsApp. `whatsapp_routes._run_ai_pipeline_whatsapp` duplica parte do pipeline de `/ai/chat`. Deliberadamente duplicado pra nao tocar ai_routes.py durante turbo.

**Arquivo novo:** `app/modules/cleaning/services/chat_pipeline.py`

Fix: extrair helper `run_chat_pipeline(db, business_id, client, message, channel, conversation_id=None)` que faz:
- Moderation
- Rate limit (channel-aware key)
- Build system prompt
- Invoke AI tool loop com auth_context
- Save messages

Tanto `/ai/chat` quanto `/whatsapp/webhook` chamam o helper.

**Effort:** 3-4h (exige re-testar Smith C-1/H-1/M-3 apos refactor)

---

## Added 2026-04-21 — webchat público extension

### MEDIUM-7 · Lead notifier email/SMS pro owner quando lead captured

**Origem:** webchat público Bloco extensão. Visitante anônimo conversa -> IA
cria lead via `capture_lead`. Owner só vê se abrir dashboard — sem notificação
ativa. Clawtobusiness tem `lead_notifier.py` que envia email + SMS pro owner.

**Arquivos:** portar `app/modules/channels/lead_notifier.py` + wire no
`_capture_lead` handler pra fire-and-forget após INSERT.

**Effort:** 1-2h

### MEDIUM-8 · `validate_service_area` tool

**Origem:** system prompt `scheduling_public_visitor.py` menciona a tool,
mas ela não existe ainda. IA pode pedir zip e usar conhecimento próprio —
menos preciso.

**Fix:** criar tool que consulta `cleaning_areas.zip_codes[]` do business e
retorna covered/nearby/outside.

**Effort:** 1-2h

### LOW-10 · HTML embed snippet pro webchat público

**Origem:** widget `ai-demo-chat.js` existe mas owner não tem exemplo de
como incluir no site do business.

**Fix:** criar `docs/guides/embed-chat-widget.md` com snippet copy-paste.

**Effort:** 30min

### LOW-11 · Bot protection / captcha no webchat público

**Origem:** atualmente só rate limit por IP (10/60s). Atacante rotating IPs
pode floodar leads spam.

**Fix:** integrar hCaptcha/Cloudflare Turnstile no widget ou honeypot field.

**Effort:** 2-3h

### LOW-12 · Telegram canal

**Origem:** explicitamente descartado do sprint AI Turbo pela escolha do
Luiz (Opção 2 só webchat público). Clawtobusiness tem `telegram.py`
(185 linhas) + `telegram_webhook.py` prontos pra portar.

**Effort:** 1-2h (portagem direta)

---

## LOW — polish, entra em sprints futuros conforme demanda

### LOW-1 · `_compute_end` overnight overflow

**Origem:** Smith M-1. `app/modules/cleaning/services/availability_service.py:61-63` usa `.time()` que perde `+1 day` se `start + duration` ultrapassa meia-noite. Cleaning raramente passa meia-noite mas fix e 5 linhas.

**Fix:** trabalhar com datetime completo em vez de time isolado.

**Effort:** 30min

---

### LOW-2 · `str.format()` prompt injection via `business.name`

**Origem:** Smith M-2. `app/modules/cleaning/routes/ai_routes.py:365` usa `.format()` com campos `business_name`, `client_name`, `client_address` que podem conter `{` literal -> crash KeyError. Prompt injection limitado.

**Fix:** usar `string.Template.safe_substitute` ou escape `{` / `}` nos campos dinamicos.

**Effort:** 30min

---

### LOW-3 · HTTP 503 sem Retry-After header

**Origem:** Smith N-1. RFC 7231 7.1.3 recomenda `Retry-After` em 503.

**Fix:** adicionar `headers={"Retry-After": "60"}` nas HTTPException(503) em `ai_routes.py` + `whatsapp_routes.py`.

**Effort:** 15min

---

### LOW-4 · 5 tools legadas com bugs de schema em ai_tools.py

**Origem:** Smith L-2. Tools `get_schedule_for_date`, `get_team_availability`, `get_client_history`, `get_team_workload_summary`, `get_cancellation_patterns` referenciam `cleaning_client_schedules` em JOIN por client_id (errado — correto e `cleaning_clients`) e `cleaning_service_types` (nao existe — e `cleaning_services`).

**Mitigacao atual:** system prompt do chat customer instrui IA a NAO usar essas tools.

**Fix:** aplicar mesmo padrao dos fixes commit `2218fb2` em cada uma das 5.

**Effort:** 2-3h (5 queries + testes)

---

### LOW-5 · Audio message transcription no WhatsApp

**Origem:** Bloco 2.3. `WhatsAppAdapter.parse_webhook` detecta audio_url mas pipeline responde "nao suportado por enquanto". Cliente tem que redigitar.

**Fix:** OpenAI Whisper API via `download_media_base64` + `client.audio.transcriptions.create`. Pricing: $0.006/minuto.

**Effort:** 2-3h

---

### LOW-6 · Cross-message conversation threading no WhatsApp

**Origem:** Bloco 2.3. Atualmente cada mensagem WhatsApp cria nova conversation. Cliente perde contexto da conversa anterior se mandar follow-up depois de 5 min.

**Fix:** reutilizar mesma logica do BusinessChatService do clawtobusiness (`_get_recent_conversation` com idle window 24h pra WhatsApp vs 2h pra web).

**Effort:** 1-2h

---

### LOW-7 · message_buffer + abuse_guard portagem

**Origem:** Bloco 2.3 scope cut. message_buffer agrupa mensagens consecutivas do mesmo sender (500ms debounce) em 1 intent. abuse_guard bloqueia spam/flood.

**Fix:** portar de clawtobusiness com ajustes de namespace.

**Effort:** 3-4h

---

### LOW-8 · Per-business TZ awareness no 24h reminder job

**Origem:** Bloco 2.2. `send_24h_reminders` usa `datetime.now(UTC).date() + 1 day` — nao respeita TZ de cada business individualmente. Se business em EST, reminder pode disparar "noon do dia seguinte UTC" (= 7am local).

**Fix:** SELECT bookings agrupados por `businesses.timezone`, calcular `tomorrow` per-business TZ, disparar batches separados.

**Effort:** 1-2h

---

### LOW-9 · CRUD owner UI `/owner/settings/channels`

**Origem:** Bloco 2.3 scope cut. Owner hoje nao tem interface pra ver status WhatsApp / regenerar QR / desconectar.

**Dependencias:** HIGH-1 (business_channels table) primeiro.

**Effort:** 4-6h (endpoints + UI)

---

## Resumo de prioridade

| Priority | Items | Effort total |
|---|---|---|
| HIGH | 2 (business_channels multi-tenant + Evolution HTTPS) | ~4 dias |
| MEDIUM | 6 (auth ext, Fernet, audit, conversations.business_id, race lock, chat_pipeline helper) | ~15-20h |
| LOW | 9 (polish, features extras) | ~20-25h |

**Launch minimo pro cliente final:** fechar HIGH + MEDIUM-2 (Fernet) + MEDIUM-3 (audit).
**Launch pleno multi-tenant:** todo HIGH + MEDIUM.
