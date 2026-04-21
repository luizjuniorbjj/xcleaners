# xcleaners — Project Checkpoint

**Ultima atualizacao:** 2026-04-21 (fim da sessao Staging Deploy + openai bump)

---

## Contexto Ativo

- **Branch atual:** `feat/ai-fix-turbo` (HEAD: `319d708`)
- **Staging:** https://cleanclaw-api-staging-bde0.up.railway.app ✅ VERDE
- **Producao:** Railway env `production` — ainda rodando codigo antigo (sem AI Turbo, sem webchat publico, sem openai bump)
- **Bloqueio pra merge pra prod:** STAGING-2 (criar migration 029 com `conversations`+`messages`)

## Status das Stories (Sprint AI Turbo)

| Bloco | Descricao | Status |
|-------|-----------|--------|
| Bloco 2.1 | AI chat widget autenticado (homeowner) | ✅ Done |
| Bloco 2.2 | APScheduler jobs (daily_schedule, 24h_reminders, draft_ttl) | ✅ Done |
| Bloco 2.3 | WhatsApp Evolution API webhook + pipeline | ✅ Done |
| Ext 2026-04-21 | Webchat publico anonimo + capture_lead | ✅ Done |
| Fix staging | openai 1.0.0 -> >=1.35,<2.0 | ✅ Done (319d708) |
| STAGING-2 | Migration 029 (conversations, messages) | ⏳ Pendente — bloqueia prod |

## Decisoes Tomadas

- **Motor de IA (producao):** OpenAI GPT-4.1 Mini via `chat.completions.create(tools=...)` function calling. Claude mantido como fallback opcional (existing code).
- **Deploy strategy:** staging isolado via Railway `environmentCreate` com clone do Postgres service. Overrides aplicados em `EVOLUTION_INSTANCE_NAME=xcleaners-staging`, `STRIPE_WEBHOOK_SECRET=placeholder`, `DEBUG=true`, `LOG_LEVEL=DEBUG`.
- **Auth context pattern:** `propose_booking_draft` tem duas gates — Gate 1 cross-business (client scoped to business), Gate 2 intra-business (`authenticated_client_id` match). Visitante anonimo no webchat publico nao tem auth_context — Gate 1 protege mesmo assim.
- **Tool registry:** 11 tools em `AI_TOOLS` (ai_tools.py). `capture_lead` novo, escopo publico. `TOOLS_REQUIRING_AUTH_CONTEXT = {"propose_booking_draft"}`.
- **Smith calibrated findings:** severity honesta, no inflation pra "minimum 10". Commit `319d708` recebeu CONTAINED inline (2 linhas) — pattern correto pra bumps triviais.

## Ambiente Configurado

### Staging (Railway env `505e45d6-0df0-480c-9599-f924921dde6c`)
- URL publica: `https://cleanclaw-api-staging-bde0.up.railway.app`
- DB: Postgres clonado do prod, schema bootstrapado via `pg_dump --schema-only` (49 tabelas) + seed manual
- Seed business: slug `xcleaners-staging-demo`, owner `staging-owner@xcleaners.test`, 1 servico "Regular Cleaning" $120
- Overrides criticos: Evolution instance separada, Stripe webhook placeholder, DEBUG=true
- Redis: AUSENTE (fallback in-memory — ver STAGING-4)

### Producao (Railway env `1b26aba0-f3ef-4135-a543-3482d0874ddc`)
- URL: `https://` (setado em APP_URL prod — dominio privado do cliente)
- Stripe: `sk_test_51T5...` (test mode confirmed)
- OPENAI_API_KEY, RESEND_API_KEY, EVOLUTION_API_KEY: setados
- **NAO MEXIDO nesta sessao.** Producao rodando codigo de antes do sprint AI Turbo.

## Ultimo Trabalho Realizado

### Sessao 2026-04-21 — Staging Deploy + openai fix

**Commits pushed em `feat/ai-fix-turbo`:**
- `e5735f5` — feat(webchat-public): visitante anonimo + capture_lead — AI Turbo extensao (Smith CONTAINED)
- `319d708` — fix(deps): bump openai 1.0.0 -> >=1.35,<2.0 — unblock AI tool loop (Smith CONTAINED)

**Infraestrutura:**
- Railway env `staging` criado via GraphQL `environmentCreate` (clone do production)
- Postgres staging bootstrapado: drop schema public → `pg_dump` prod + `psql` restore → seed `xcleaners-staging-demo`
- Tabelas `conversations` + `messages` criadas manualmente no staging (gap descoberto: nao estao em migrations)
- Railway domain gerado: `cleanclaw-api-staging-bde0.up.railway.app`

**Smoke test:**
- `/health` 200 OK
- `/api/v1/clean/xcleaners-staging-demo/ai/demo-chat` 200 OK, IA respondendo real com contexto do seed ($120, "Staging Demo Cleaning")
- `conversation_id` retornado, persistence funcionando

**Arquivos:**
- `requirements.txt` (bump openai)
- `docs/sprints/backlog-ai-turbo-postsprint.md` (+6 findings STAGING-1..6)
- `docs/PROJECT-CHECKPOINT.md` (criado)

### Sessao 2026-04-20/21 madrugada — Sprint AI Turbo

- Bloco 2.1 (chat widget autenticado), 2.2 (scheduler), 2.3 (WhatsApp), Extension (webchat publico)
- 11 tools no registry, auth_context flow end-to-end, Smith C-1/C-2/H-1/M-2D corrigidos
- Ver `docs/sprints/ai-turbo-sprint-2026-04-20.md` e `day-2-complete-handoff.md`

## Proximos Passos

**Hotfix critico antes de merge pra prod:**
- [ ] STAGING-2 — criar `database/migrations/029_ai_chat_tables.sql` com `conversations` + `messages` (30 min)

**Ciclo de merge pra prod (proxima sessao do Luiz):**
- [ ] Run `git merge feat/ai-fix-turbo` em main OU PR review (Luiz decide strategy)
- [ ] @smith re-verify global `main..feat/ai-fix-turbo`
- [ ] @devops deploy em prod
- [ ] Smoke test prod: /health + criar 1 lead via demo-chat real
- [ ] Plan de rollback pronto

**Backlog pos-launch (sem urgencia):**
- [ ] STAGING-3 (repatriar migrations 005-010 do monolito)
- [ ] STAGING-4 (Redis service staging)
- [ ] STAGING-5 (Stripe webhook staging dashboard)
- [ ] HIGH-1 (business_channels multi-tenant)
- [ ] HIGH-2 (Evolution HTTPS — ja OK, https://evo.clawtobusiness.com)
- [ ] Ver backlog completo em `docs/sprints/backlog-ai-turbo-postsprint.md`

## Git Recente

```
319d708 fix(deps): bump openai 1.0.0 -> >=1.35,<2.0 — unblock AI tool loop
adf3280 docs(backlog): mark M1 Dashboard + L2 LTV as FIXED; defer M2 Reports rewrite
9195580 fix(clients): aggregate LTV from paid invoices in listing
87380a8 fix(dashboard): KPIs stuck at $0 — legacy field check fell into fallback
e5735f5 feat(webchat-public): visitante anonimo + capture_lead — AI Turbo extensao
398b4ac docs(sprints): handoff atualizado — env vars setadas no Railway
```

## Railway Resources

| Recurso | Prod | Staging |
|---------|------|---------|
| Project | `006be8f9-c53b-4cbb-b409-47eeafd9a372` | (mesmo) |
| Env | `1b26aba0-...` | `505e45d6-0df0-480c-9599-f924921dde6c` |
| Service cleanclaw-api | `acc566f3-15f3-4a43-b7c8-0c197675f44c` | (mesmo — env isola) |
| Postgres | `3bc407f9-7b7a-4d5c-8050-3128f07a41b7` | (mesmo — env tem volume proprio) |
| Domain | (prod privado) | `cleanclaw-api-staging-bde0.up.railway.app` |

## Business Slugs em Uso

- **Produção:** AllBritePainting (primerstarcorp e outros registrados em `.lmas-core/` global)
- **Staging teste:** `xcleaners-staging-demo`
