# HIGH-1.1 Schema Deploy Runbook

**Story:** XCL-HIGH-1.1 — Schema foundation
**Sprint:** Sprint 2 (post-v1)
**Date:** 2026-04-22
**Owner:** @data-engineer (Tank) → @smith verify → @devops push
**Risk profile:** DEPLOY-SAFE (zero impacto runtime — schema-only, app code intacto)

---

## 0. Pre-flight (executar antes do push)

| # | Check | Como verificar |
|---|-------|----------------|
| 0.1 | Migration file pronto | `ls -la database/migrations/029_business_channels.sql` (~95 LOC) |
| 0.2 | Rollback file pronto | `ls -la database/migrations/rollback_029.sql` (~45 LOC) |
| 0.3 | Local tests PASS | Ver evidência em `stories/XCL-HIGH-1.1.story.md` Dev Agent Record |
| 0.4 | Smith verify CONTAINED | Aguardar veredict antes de prosseguir |
| 0.5 | Last stable commit identificado | `git log --oneline -1 origin/main` (anotar hash para rollback) |
| 0.6 | Railway env vars EVOLUTION_* presentes | `railway variables --service cleanclaw-api \| grep EVOLUTION` (todas devem existir e bater com qatest config) |
| 0.7 | DB backup criado | `pg_dump $DATABASE_URL > /tmp/xcleaners_pre_029_$(date +%Y%m%d_%H%M).sql` |

---

## 1. Apply migration

```bash
# 1.1. Verificar variável $DATABASE_URL aponta para Railway prod
echo $DATABASE_URL | grep railway

# 1.2. Apply migration via psql
psql $DATABASE_URL -f database/migrations/029_business_channels.sql

# Esperado:
#   BEGIN
#   CREATE TABLE
#   CREATE INDEX (3x)
#   DROP TRIGGER (NOTICE: does not exist, skipping na 1ª)
#   CREATE TRIGGER
#   INSERT 0 1
#   COMMIT
```

**Exit code 0 obrigatório.** Se erro:
- Verificar `pg_dump` rodou no passo 0.7
- Não rodar rollback automaticamente — investigar erro primeiro

---

## 2. Verify (AC3 + AC6 + AC7)

### 2.1 — AC3: Backfill correto (1 row qatest com IDs reais)

```sql
SELECT bc.channel_type, bc.provider, bc.instance_name, bc.phone_number,
       bc.status, bc.webhook_secret, bc.evolution_instance_id, bc.connected_at
FROM business_channels bc
JOIN businesses b ON b.id = bc.business_id
WHERE b.slug = 'qatest-cleaning-co';
```

**Esperado (exato):**
| campo | valor |
|-------|-------|
| channel_type | `whatsapp` |
| provider | `evolution_api` |
| instance_name | `xcleaners` |
| phone_number | `5512988368047` |
| status | `connected` |
| webhook_secret | `b4bb19dff1949fb1f26aa28010eb46ea3e13c4ab493eabb29f1ff6bc78eb3876` |
| evolution_instance_id | `7a873e27-2e7b-4e2a-9382-711f3febd2d9` |
| connected_at | `2026-04-21 22:37:00+00` |

### 2.2 — AC6: Webhook continua respondendo 200 (zero downtime)

```bash
# 2.2.a — curl /status endpoint
curl -sS https://app.xcleaners.app/api/v1/clean/qatest-cleaning-co/whatsapp/status

# Esperado: {"status": "CONNECTED", "business_id": "..."}
# NÃO deve retornar "not_configured" (significaria que env vars sumiram)
```

```bash
# 2.2.b — Manual WhatsApp ping
# Enviar mensagem real "ping smoke 029" para +5512988368047 via WhatsApp Business
# Esperado: AI responde dentro de 5-15s
```

### 2.3 — AC7: Smoke Playwright 11/11 PASS

```bash
cd /c/xcleaners
npx playwright test tests-e2e/smoke --reporter=list

# Esperado: 11 passed
# Tempo baseline: ~71s (deploy 2026-04-22)
```

### 2.4 — Railway logs 10 min monitor

```bash
railway logs --service cleanclaw-api --follow

# Procurar por:
#   - ZERO erros relacionados a "channels", "business_channels", "whatsapp"
#   - Webhooks inbound continuam processando normalmente
```

---

## 3. Rollback (apenas se AC2/AC3/AC6 FAIL)

### 3.1 — Pre-check OBRIGATÓRIO antes de rollback

```sql
SELECT COUNT(*) AS non_qatest_channels
FROM business_channels
WHERE business_id NOT IN (
    SELECT id FROM businesses WHERE slug = 'qatest-cleaning-co'
);
```

| Resultado | Ação |
|-----------|------|
| `0 rows` | SAFE → prosseguir step 3.2 |
| `>0 rows` | **NÃO rollback automático** — outros businesses configuraram canais (HIGH-1.3 já deployed). Coordenar com @devops para snapshot + plan de re-config. |

### 3.2 — Apply rollback

```bash
psql $DATABASE_URL -f database/migrations/rollback_029.sql

# Esperado:
#   BEGIN
#   DROP TABLE
#   COMMIT
```

### 3.3 — Verify rollback

```sql
SELECT tablename FROM pg_tables WHERE tablename='business_channels';
-- Esperado: (0 rows)
```

### 3.4 — Pós-rollback

- Confirmar `_resolve_business` continua funcionando (lê env, table não existia antes mesmo)
- AC6 webhook ping deve continuar OK (1.2 não foi deployed ainda)

---

## 4. Sign-off

- [ ] AC1 (apply OK): exit 0 confirmado
- [ ] AC2 (idempotência): rodar migration 2x em prod e confirmar zero erro
- [ ] AC3 (backfill correto): SELECT da seção 2.1 confirma todos 8 campos
- [ ] AC6 (webhook 200): curl + manual WhatsApp ping confirmam
- [ ] AC7 (Playwright smoke): 11/11 PASS
- [ ] Railway logs limpos por 10 min pós-deploy

**Pós sign-off:** atualizar `PROJECT-CHECKPOINT.md` marcando 1.1 deployed + iniciar XCL-HIGH-1.2 (Neo + Tank review).

---

## Anexos

### Local test evidence (2026-04-22, Tank)

Container ephemeral PG16 (`xcleaners-test-029` + `xcleaners-test-rb`). Resultados:

| Test | Status | Evidência |
|------|--------|-----------|
| T3.2 — Apply 029 | ✅ PASS | BEGIN → CREATE TABLE → 3 INDEXES → TRIGGER → INSERT 0 1 → COMMIT |
| T3.3 — AC3 Backfill correto | ✅ PASS | 8 campos batem com IDs reais (instance_name='xcleaners', evolution_instance_id='7a873e27-...', phone='5512988368047', secret='b4bb...', status='connected', connected_at='2026-04-21 22:37:00+00') |
| T3.4 — AC2 Idempotência | ✅ PASS | 2ª aplicação: INSERT 0 0 + contagem permanece 1 |
| T3.5 — AC4 UNIQUE constraint | ✅ PASS | Erro `23505` com mention exata `uq_business_channel_type` |
| T3.6 — AC5 Trigger updated_at | ✅ PASS | UPDATE → updated_at > created_at, delta 1.2s |
| T3.7 — AC8 Rollback cleanly | ✅ PASS | DROP TABLE limpo em DB separado, businesses intacta |

ACs validados localmente: 5 de 8 (AC2, AC3, AC4, AC5, AC8).
ACs pendentes (exigem prod): AC1, AC6, AC7 — verificados durante este runbook.
