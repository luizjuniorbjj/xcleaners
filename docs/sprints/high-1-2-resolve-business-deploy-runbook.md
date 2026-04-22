# HIGH-1.2 _resolve_business Refactor Deploy Runbook

**Story:** XCL-HIGH-1.2 — Adapter integration: `_resolve_business` reads from `business_channels` with env fallback
**Sprint:** Sprint 2 (post-v1)
**Date:** 2026-04-22
**Owner:** @dev (Neo) → @smith verify → @devops push + flag flip
**Risk profile:** **Phase 1 deploy = ZERO impact** (flag default 'env' = legacy behavior). Phase 2 flip to 'db' = controlled cutover with instant rollback.

---

## 0. Pre-deploy (CRÍTICO — confirmar antes de push)

| # | Check | Como verificar |
|---|-------|----------------|
| 0.1 | XCL-HIGH-1.1 deployed em prod | `docker run --rm postgres:16-alpine psql "$DATABASE_PUBLIC_URL" -c "SELECT count(*) FROM business_channels;"` retorna ≥1 |
| 0.2 | qatest backfill OK | SELECT da row qatest com IDs corretos (ver story 1.1) |
| 0.3 | `whatsapp_routes.py` modificado conforme spec | grep `_load_channel_config` em `app/modules/cleaning/routes/whatsapp_routes.py` |
| 0.4 | Tests unitários passing local | `pytest tests/test_resolve_business.py -v` (10 testes esperados) |
| 0.5 | `.env.example` documenta `WHATSAPP_CONFIG_SOURCE=env` | `grep WHATSAPP_CONFIG_SOURCE .env.example` |
| 0.6 | Smith verify CONTAINED | Aguardar veredict |

---

## 1. Phase 1 — Deploy code com flag=env (ZERO impacto)

### 1.1 Garantir que flag NÃO está como 'db' em prod

```bash
railway variables --service cleanclaw-api --kv | grep WHATSAPP_CONFIG_SOURCE
```

| Resultado | Ação |
|-----------|------|
| **Vazio (não existe)** | ✅ OK — default 'env' aplicado pelo código |
| **`WHATSAPP_CONFIG_SOURCE=env`** | ✅ OK — explicitamente env |
| **`WHATSAPP_CONFIG_SOURCE=db`** | 🛑 STOP — flag não pode estar 'db' antes do código novo deployar; remover via `railway variables --service cleanclaw-api --remove WHATSAPP_CONFIG_SOURCE` |

### 1.2 Push commit (após Smith CONTAINED)

```bash
cd /c/xcleaners
git push origin main 2>&1 | tail -5
```

GitHub Actions trigger → Railway redeploy automático. Aguardar healthcheck ~2-3min.

### 1.3 Smoke pós-deploy (Phase 1 validation)

```bash
# AC1 byte-equal: webhook continua igual ao pré-refactor
curl -sS https://app.xcleaners.app/api/v1/clean/qatest-cleaning-co/whatsapp/status

# Esperado: {"status":"CONNECTED","business_id":"af168a02-be55-4714-bbe2-9c979943f89c"}
```

```bash
# Logs Railway: confirmar que helper NÃO foi chamado (Phase 1 = env mode)
railway logs --service cleanclaw-api --tail 50 | grep CHANNELS

# Esperado: ZERO linhas com "[CHANNELS] Loaded config from business_channels"
# Esperado: ZERO linhas com "[CHANNELS] falling back to env" (helper nem é chamado)
# Se aparecer alguma → flag está 'db' inadvertidamente, voltar para 'env' imediatamente
```

```bash
# Manual ping (opcional mas recomendado): enviar mensagem real WhatsApp para +5512988368047
# Esperado: AI responde dentro de 5-15s (baseline atual)
```

---

## 2. Phase 2 — Flip flag para 'db' (janela controlada)

**Pré-requisito:** Phase 1 estável por pelo menos 10min sem regressão.

### 2.1 Flip com Luiz acompanhando logs em tempo real

**Em terminal A (logs streaming — abrir ANTES do flip):**
```bash
railway logs --service cleanclaw-api --follow | grep CHANNELS
```

**Em terminal B (flip):**
```bash
railway variables --service cleanclaw-api --set WHATSAPP_CONFIG_SOURCE=db
```

Railway aplica sem restart (env var hot-reload em containers Python). Próxima request webhook usa DB-first path.

### 2.2 Verify Phase 2 (DB-first ativo)

**Em terminal A, esperar primeira request webhook + observar:**

Esperado (sucesso DB-first):
```
[CHANNELS] Loaded config from business_channels for slug=qatest-cleaning-co (instance=xcleaners, status=connected)
```

Se aparecer (problema):
```
[CHANNELS] No business_channels row for slug=qatest-cleaning-co (or status invalid), falling back to env config
```
→ **STOP, executar rollback (seção 3) imediatamente.** Investigar por quê backfill não foi encontrado.

### 2.3 Smoke real Phase 2

```bash
# AC5 — webhook real continua respondendo (mesmo número, mesma instance, agora via DB)
curl -sS https://app.xcleaners.app/api/v1/clean/qatest-cleaning-co/whatsapp/status

# Esperado: {"status":"CONNECTED",...}
```

Manual: enviar mensagem WhatsApp para `+5512988368047` → AI responde normalmente.

### 2.4 AC8 — Playwright smoke (opcional mas recomendado)

```bash
cd /c/xcleaners && npx playwright test tests-e2e/smoke --reporter=list
# Esperado: 11 passed
```

---

## 3. Rollback (instant — Phase 2 → Phase 1)

Se Phase 2 mostrar regressão:

```bash
railway variables --service cleanclaw-api --set WHATSAPP_CONFIG_SOURCE=env
```

Próxima request usa env path. Zero código revertido necessário. Pós-rollback:
- Webhook funciona como antes do flip
- Investigar root cause (backfill incorreto? row removida? código tem bug?)
- NÃO re-flip até root cause identificado e corrigido

### Rollback completo (se Phase 1 também regrediu — improvável)

```bash
cd /c/xcleaners
git revert {commit-hash-XCL-HIGH-1.2}
git push origin main
# Railway redeploy revert ~3min
```

---

## 4. Sign-off

### Phase 1
- [ ] `WHATSAPP_CONFIG_SOURCE` env var = `env` (ou ausente) confirmado
- [ ] Push + Railway redeploy sucesso
- [ ] curl `/status` retorna CONNECTED
- [ ] Logs SEM `[CHANNELS] Loaded config` (helper não chamado em env mode)
- [ ] Manual WhatsApp ping (opcional) responde

### Phase 2 (após Phase 1 estável 10min+)
- [ ] Logs streaming aberto (terminal A)
- [ ] Flag flipada para `db`
- [ ] Primeira request webhook mostra `[CHANNELS] Loaded config from business_channels for slug=qatest-cleaning-co (instance=xcleaners, status=connected)`
- [ ] curl `/status` continua CONNECTED
- [ ] Manual WhatsApp ping continua respondendo
- [ ] Playwright smoke 11/11 PASS (se rodado)

**Pós sign-off:** atualizar `PROJECT-CHECKPOINT.md` marcando 1.2 deployed Phase 1 + Phase 2 + iniciar próxima story.

---

## 5. Anexo — AC5 E2E local SKIP rationale

T4 (E2E local mock webhook payload) foi SKIPPED nesta entrega. Mitigação:
- AC5 é validado em prod via real WhatsApp ping (seções 1.3 e 2.3 acima)
- Tests unitários em `tests/test_resolve_business.py` cobrem todos os paths lógicos
- Mock E2E local seria re-trabalho do que prod smoke já valida

Risk aceito: se houver bug de integração que mocks unitários não pegam, será detectado em Phase 1 smoke (antes do flip Phase 2). Phase 1 é zero-impacto, qualquer bug é caught sem dano a clientes.
