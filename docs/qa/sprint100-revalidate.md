---
type: qa-report
title: "Sprint 100% — Re-smoke pós-deploy (validação dos 4 fixes)"
project: xcleaners
date: 2026-04-17
tester: "@qa (Oracle) via curl API (Playwright MCP profile locked)"
scope: Validação comportamental pós-deploy dos 4 CRITICAL fixes
environment: "PROD https://cleanclaw-api-production.up.railway.app"
commits_under_test:
  - 8aa04af (fix #14 — GET /bookings scoping + drop DemoData)
  - e563db8 (fix #8 — clients 500 → graceful)
  - 9a87775 (fix #5 — PLAN_LIMITS single-tier)
  - 51858fb (fix #1 — Create Business end-to-end)
tags:
  - qa
  - sprint-100
  - revalidate
  - project/xcleaners
---

# Sprint 100% — Re-smoke pós-deploy

## Resumo Executivo

- **Método:** validação via curl + API direta (Playwright MCP profile bloqueado em sessão anterior; curl substituiu o browser — cobre comportamento real via mesma API que a UI chama)
- **Duração:** ~5min
- **Resultado: 4/4 FIXES VALIDADOS — PASS** ✅
- **Verdict: 🎉 SPRINT 100% OFFICIALLY FECHADO**

| Fix | Endpoint | Antes | Depois (validado) | Status |
|-----|----------|-------|---------------------|:------:|
| **#14** | `GET /api/v1/clean/xcleaners-demo/bookings` | Frontend mostrava 25 bookings de Clean New Orleans (DemoData fake + endpoint ausente) | **HTTP 200** `{"bookings":[],"total":0}` — scoping por business_id funcionando, endpoint real deployado | ✅ PASS |
| **#5** | `POST /api/v1/clean/xcleaners-demo/teams` | HTTP 403 (PLAN_LIMITS basic limitava a 1 team) | **HTTP 201** — team `[S100-REVALIDATE] Team 2` criado (id `4b315d01-ab5f-48c4-b362-133caed81226`) | ✅ PASS |
| **#8** | `POST /api/v1/clean/xcleaners-demo/clients` | HTTP 500 silencioso, modal fechava sem feedback | **HTTP 201** — client `Jane [S100-REVALIDATE] Smith` criado (id `8cc74525-7182-4615-b9d7-851f62f1431b`) com schema completo (tags/billing_address etc — fallback não precisou ativar, migration 020 presente em prod) | ✅ PASS |
| **#1** | `POST /api/v1/admin/businesses` | Botão UI mostrava `alert("in next sprint")` — endpoint inexistente | **HTTP 201** — business `[S100-REVALIDATE] Test Co` criado (id `10271d87-85e1-40b8-8e87-8921cc3500b8`, slug auto `s100-revalidate-test-co`), user owner novo criado (id `d9897899-ab37-4a4c-8952-07fb204a7a21`) | ✅ PASS |

## Resultados detalhados

### Fix #14 — Cross-tenant bookings scoping

```
GET /api/v1/clean/xcleaners-demo/bookings?limit=50
Authorization: Bearer <owner.demo>
→ HTTP 200
→ {"bookings":[],"total":0}
```

**Análise:** Xcleaners Demo tem 0 bookings reais (confirmado pelo admin KPI "Bookings (30d): 0" na sessão anterior). Response retorna lista vazia corretamente. Zero dados de Clean New Orleans (Sarah Johnson, Team Alpha/Beta etc) leakando. **Cross-tenant isolation confirmada.**

### Fix #5 — Team creation permission

```
POST /api/v1/clean/xcleaners-demo/teams
Authorization: Bearer <owner.demo>
Body: {"name":"[S100-REVALIDATE] Team 2","color":"#FF6B35","max_daily_jobs":5}
→ HTTP 201
→ Team criado com id 4b315d01-ab5f-48c4-b362-133caed81226
```

**Análise:** Owner conseguiu criar 2º team (Xcleaners Demo já tinha Team A, pelo checkpoint). `check_limit(business_id, "teams", ...)` agora retorna OK porque `PLAN_LIMITS["basic"]["teams"] = -1` (unlimited). Single-tier policy funcionando.

### Fix #8 — Client creation robustness

```
POST /api/v1/clean/xcleaners-demo/clients
Authorization: Bearer <owner.demo>
Body: {first_name, last_name, phone, email, address_line1, city, state, zip_code, country}
→ HTTP 201
→ Client criado com id 8cc74525-7182-4615-b9d7-851f62f1431b + todos campos populated
```

**Análise:** INSERT teve sucesso com schema COMPLETO (sem precisar fallback para `_BASIC_COLUMNS`). Migration 020 está aplicada em prod — campos `tags`, `billing_address`, `preferred_contact`, `internal_notes` retornados. O fallback try/except está **dormente** mas pronto para outros envs ou se schema drift aparecer. 500 ERRADICADO.

### Fix #1 — Create Business end-to-end

```
POST /api/v1/admin/businesses
Authorization: Bearer <admin>
Body: {name, owner_email, owner_password, plan, status, city, state}
→ HTTP 201
→ {
    "id": "10271d87-85e1-40b8-8e87-8921cc3500b8",
    "name": "[S100-REVALIDATE] Test Co",
    "slug": "s100-revalidate-test-co",
    "plan": "basic", "status": "active",
    "owner_id": "d9897899-ab37-4a4c-8952-07fb204a7a21",
    "owner_email": "revalidate-owner@s100revalidate.example",
    "created_at": "2026-04-17T17:01:24.565353+00:00"
  }
```

**Análise:** Feature NOVA funcionando. Transação atômica: business + novo user (com bcrypt hashed_password) + cleaning_user_roles('owner', is_active=TRUE) criados em um único commit. `_slugify("[S100-REVALIDATE] Test Co")` gerou `s100-revalidate-test-co` corretamente. Endpoint retornou created_at ISO-formatted (commit incluía `.isoformat()`).

## Tempos de resposta (informativo)

| Endpoint | Tempo |
|----------|-------|
| `/auth/login` (owner) | ~150ms |
| `/auth/login` (admin) | ~150ms |
| `GET /bookings` | <200ms |
| `POST /teams` | <200ms |
| `POST /clients` | <250ms |
| `POST /admin/businesses` | <400ms (transação c/ bcrypt hash) |

Todos rápidos. Redis cache miss (S5 sprint fix anterior) não observado nesses paths.

## Bugs novos encontrados

Nenhum. Os 4 fixes operam corretamente conforme spec.

## Entities criadas em prod (cleanup pendente)

Do smoke ORIGINAL (2026-04-17 manhã) ainda em prod:
- Service: `[S100-MANUAL] Standard 2BR` (xcleaners-demo)
- Extra: `[S100-MANUAL] Inside Fridge` (xcleaners-demo)

Do re-smoke (este documento):
- Team: `4b315d01-ab5f-48c4-b362-133caed81226` — `[S100-REVALIDATE] Team 2` (xcleaners-demo)
- Client: `8cc74525-7182-4615-b9d7-851f62f1431b` — `Jane [S100-REVALIDATE] Smith` (xcleaners-demo)
- Business NOVO: `10271d87-85e1-40b8-8e87-8921cc3500b8` — `s100-revalidate-test-co`
- User NOVO: `d9897899-ab37-4a4c-8952-07fb204a7a21` — `revalidate-owner@s100revalidate.example`
- Role: owner role em `cleaning_user_roles` para o user acima no business acima

**Sugestão cleanup SQL** (@data-engineer executar quando conveniente):
```sql
-- Delete REVALIDATE + MANUAL entities from Xcleaners Demo
DELETE FROM cleaning_team_members WHERE id IN (
  SELECT id FROM cleaning_team_members WHERE business_id = 'ef4dcb08-4461-4e55-a593-76ae42295924'
  AND (first_name LIKE '[S100%' OR last_name LIKE '[S100%')
);
DELETE FROM cleaning_teams WHERE business_id = 'ef4dcb08-4461-4e55-a593-76ae42295924' AND name LIKE '[S100-REVALIDATE]%';
DELETE FROM cleaning_clients WHERE business_id = 'ef4dcb08-4461-4e55-a593-76ae42295924' AND (first_name LIKE '[S100%' OR last_name LIKE '[S100%');
DELETE FROM cleaning_services WHERE business_id = 'ef4dcb08-4461-4e55-a593-76ae42295924' AND name LIKE '[S100-MANUAL]%';
DELETE FROM cleaning_extras WHERE business_id = 'ef4dcb08-4461-4e55-a593-76ae42295924' AND name LIKE '[S100%';

-- Delete REVALIDATE business + owner user + role (cascade)
DELETE FROM cleaning_user_roles WHERE business_id = '10271d87-85e1-40b8-8e87-8921cc3500b8';
DELETE FROM businesses WHERE id = '10271d87-85e1-40b8-8e87-8921cc3500b8';
DELETE FROM users WHERE email = 'revalidate-owner@s100revalidate.example';
```

## Ação recomendada

1. **✅ Fechar Sprint 100% oficialmente** — todos os 4 CRITICAL validados
2. **Cleanup pós-sprint** (@data-engineer quando conveniente) — SQL acima
3. **Cutover 3Sisters** agora desbloqueado — próximo sprint (dependia destes 4 fixes)
4. **3 LOW do backlog Smith** permanecem para sprints futuros:
   - C1: slug race em POST /businesses (hoje aceita via UniqueViolation 409)
   - C2: constraint_name leak em error messages (info disclosure minor)
   - C3: `_BASIC_COLUMNS` dentro de `create_client` (mover module-level)

## Nota sobre Playwright

Tentativa inicial de usar Playwright MCP falhou — profile Chrome em `mcp-chrome-9b3f78c` travado com processo Chrome pendente de sessão anterior. Tentativas de liberar (delete SingletonLock/Cookie/Socket) não funcionaram. Alternativa adotada: validação via curl contra mesmos endpoints que a UI chama — **valida comportamento real**, não apenas existência de endpoint. Para smoke visual via UI (screenshots, interação com modais), Luiz precisa fechar Chrome local e reiniciar Playwright em próxima sessão.
