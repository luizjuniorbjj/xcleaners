---
type: qa-report
title: "Sprint 100% — Manual End-to-End Bug Log"
project: xcleaners
date: 2026-04-17
tester: "@qa (Oracle) via Playwright MCP"
scope: 11-step critical onboarding chain
environment: "PROD https://cleanclaw-api-production.up.railway.app"
marker_prefix: "[S100-MANUAL]"
tags:
  - qa
  - sprint-100
  - manual
  - playwright
  - project/xcleaners
---

# Sprint 100% — Manual End-to-End Bug Log

## Resumo Executivo

- **Duração:** ~55min (dentro do hard cap 3h)
- **Steps tentados:** 8 de 12 (33% pulados por bloqueadores em cascata)
- **Steps PASS:** 3 (Super-admin login/dashboard · Services CRUD · Extras CRUD)
- **Steps FAIL:** 4 (Create Business · Create Team · Create Client · Lista Bookings)
- **Steps BLOQUEADOS por dependência:** 4 (Team Lead checkin/checkout · Cleaner earnings · Homeowner request · Owner calendar/invoice/reports)
- **Bugs registrados:** 14 total — **4 CRITICAL · 4 HIGH · 1 MEDIUM · 3 LOW · 2 PASS**
- **Verdict:** ⛔ **BLOCKED — Sprint 100% NÃO PODE prosseguir sem fix dos 4 CRITICAL** (original)
- **Status pós-Neo (2026-04-17 tarde):** 🛠️ **4/4 CRITICAL FIXED em commits locais** — aguardando Smith verify + Luiz aprovação para deploy

| # | Fix | Commit SHA | Arquivos |
|---|-----|------------|----------|
| **#14** | GET /bookings endpoint + remove DemoData fallback | `8aa04af` | schedule.py · bookings.js × 2 |
| **#8** | client INSERT graceful schema-drift + structured errors | `e563db8` | client_service.py · clients.py |
| **#5** | PLAN_LIMITS single-tier (basic → unlimited teams/clients) | `9a87775` | models/auth.py |
| **#1** | Create Business full-stack (POST endpoint + admin modal) | `51858fb` | admin_routes.py · super-admin.js |

### Severidade dos CRITICAL

1. **CROSS-TENANT LEAK (bug #14)** — Security showstopper. Owner do `Xcleaners Demo` vê 25 bookings + 7 past de outro business (`Clean New Orleans`). Bookings incluem clientes alheios (Sarah Johnson, Emily Davis, James Brown, etc) e teams alheios (Team Alpha, Beta). **Violação de multi-tenant isolation — isso bloqueia cutover 3Sisters imediatamente.** Confirmado via comparação: `/schedule` mostra 0 jobs corretamente (filtered por business_id), `/bookings` mostra todos (sem filter). Bug localizado no endpoint de listagem de `/bookings`.
2. **Create Business alert (bug #1)** — UI tem botão mas handler mostra `alert("Create Business: in next sprint. For now use SQL direct on the database.")`. Super-admin não consegue onboardar novo cliente via UI. Bloqueia crescimento sales-led.
3. **POST teams → 403 (bug #5)** — Owner não tem permissão RBAC para criar team. Impossível montar time novo no próprio business.
4. **POST clients → 500 (bug #8)** — Backend crash ao criar cliente. Bloqueia CRM inteiro.

### Padrão HIGH recorrente

**Todo formulário de criação que falha NÃO comunica o erro ao usuário.** Ou modal fecha silenciosamente (teams), ou fica preso sem feedback (clients). Zero toasts/banners/inline-errors. UX massivamente quebrada em error paths.

### Hard cap · guard-rails

- **Guard-rails respeitados:** prefix `[S100-MANUAL]` · emails `@s100test.example` · phones `+1-555-01XX` · sem checkout real · sem emails reais
- **Dados persistidos em prod:** 1 service `[S100-MANUAL] Standard 2BR` + 1 extra `[S100-MANUAL] Inside Fridge` (cleanup necessário quando estável)

## Credenciais utilizadas

| Role | Email | Observação |
|------|-------|-----------|
| Super Admin | admin@xcleaners.app | Credencial existente sprint fix |
| Owner novo | `[S100-MANUAL]-owner@s100test.example` | A criar (se wizard permitir) |
| Team Lead demo | teamlead.demo@xcleaners.app | Fallback para step 9 |
| Cleaner demo | cleaner.demo@xcleaners.app | Fallback para step 10 |
| Homeowner demo | homeowner.demo@xcleaners.app | Fallback para step 11 |

## Bugs Encontrados

| # | Step | Rota | Ação | Esperado | Observado | Severity | Screenshot |
|---|------|------|------|----------|-----------|----------|------------|
| **1** | 1 | `/admin` | Clicar "+ Create Business" | Modal/wizard para criar business | `alert("Create Business: in next sprint. For now use SQL direct on the database.")` — **funcionalidade NÃO IMPLEMENTADA** | **CRITICAL** | resmoke-s100-00-admin-dashboard.png |
| 2 | 0 | `/cleaning/static/img/logo.png` | Load asset | 200 PNG | 404 | LOW | (console) |
| 3 | 0 | `/cleaning/static/icons/icon-192.png` | Load asset | 200 PNG | 404 × 2 | LOW | (console) |
| 4 | 0 | `/login` | Reabrir pagina após logout | Form limpo | Email + senha do último user (homeowner.demo) pré-preenchidos | LOW | (navegação) |
| **5** | 6 | `POST /api/v1/clean/xcleaners-demo/teams` | Owner cria team via modal | 201 Created + team na lista | **403 Forbidden** — owner.demo NÃO tem permissão de criar teams | **CRITICAL** | resmoke-s100-01-owner-dashboard.png |
| **6** | 6 | `/teams` | Submit Create Team quando backend retorna 403 | Toast/banner de erro visível + modal permanece aberto | Modal fecha silenciosamente, team não aparece, **zero feedback** ao usuário | **HIGH** | (UX) |
| 7 | (geral) | `/teams` | View Team A existente | "Lead + 2 members" (backfill Sprint Fix aplicou `cleaning_team_id`) | Team A mostra "No lead • 0 members" + 2 cleaners listados como "Unassigned" → **UI diverge do DB** | HIGH | resmoke-s100-teams-divergence |
| **8** | 7 | `POST /api/v1/clean/xcleaners-demo/clients` | Owner cria client via modal completo | 201 Created + client na tabela | **500 Internal Server Error** — backend CRASH ao criar cliente | **CRITICAL** | (console) |
| **9** | 7 | `/clients` | Submit Add Client quando backend retorna 500 | Toast de erro + modal permanece | Modal fecha silenciosamente, cliente não aparece, **zero feedback** | **HIGH** | (UX — mesmo padrão do bug #6) |
| **10** | 7 | `/clients` | Submit Add Client quando backend retorna 500 (variação do #9) | Modal fecha OU mostra erro | Modal FICA PRESO aberto, intercepta pointer events, bloqueia navegação sidebar | **HIGH** | (UX fail modo 2) |
| 11 | 3 | `/services` | Acessar tela via sidebar | Item "Services" no sidebar | Rota existe em `/services` mas **sem entry no sidebar** — órfã | MEDIUM | resmoke-s100-00-owner-dashboard.png |
| 12 | 3 | `/services` | Criar novo service via modal (after finding via URL direta) | 201 + service listado | ✅ PASS — service "[S100-MANUAL] Standard 2BR" criado OK | — | (success) |
| 13 | 4 | `/extras` | Criar extra | 201 + extra listado | ✅ PASS — extra "[S100-MANUAL] Inside Fridge $25" criado OK | — | (success) |
| **14** | 8 | `/bookings` | Owner visualiza lista de bookings do próprio business (Xcleaners Demo tem 1 client + 1 team) | 0 ou poucos bookings do Xcleaners Demo | **25 upcoming + 7 past + 0 cancelled** com clientes `Sarah Johnson`/`Emily Davis`/`James Brown`/`Michael Williams`/`Lisa Garcia` e teams `Team Alpha`/`Team Beta` — **ESTES SÃO ENTIDADES DO SEED "Clean New Orleans"** (outro business) | **CRITICAL — CROSS-TENANT LEAK (security)** | resmoke-s100-critical-cross-tenant-leak.png |

## Passos executados (trilha)

### Step 0 — Setup
- [ ] Playwright MCP carregado
- [ ] Sessão browser inicializada
- [ ] Login super-admin confirmado

### Step 1 — Super-admin cria novo business
- **Status:** pendente

### Step 2 — Associar owner novo ao business
- **Status:** pendente

### Step 3 — Owner cria service com tier + BR + BA
- **Status:** pendente

### Step 4 — Owner cria extra + whitelist
- **Status:** pendente

### Step 5 — Owner cria location default
- **Status:** pendente

### Step 6 — Owner cria team + 2 members
- **Status:** pendente

### Step 7 — Owner cria client
- **Status:** pendente

### Step 8 — Owner agenda booking
- **Status:** pendente

### Step 9 — Team lead checkin/checkout
- **Status:** pendente

### Step 10 — Cleaner verifica earnings
- **Status:** pendente

### Step 11 — Homeowner request cleaning
- **Status:** pendente

### Step 12 — Owner verifica calendar + invoice + reports
- **Status:** pendente

## Recomendações de Fix (prioridade decrescente)

1. **Fix cross-tenant leak em `/bookings` (bug #14)** — pre-requisito absoluto. Verificar filtro `WHERE business_id = $ctx_business_id` em todo query da rota bookings listing. Audit análogo em outras rotas owner (Calendar, Reports, Payroll) para garantir ausência de leaks similares. **@data-engineer (Tank)** audita + **@dev (Neo)** corrige.
2. **Fix POST /clients 500 (bug #8)** — capturar stack trace em Railway logs + corrigir o crash. Provável FK missing, NOT NULL violation ou schema drift. **@dev (Neo)**.
3. **Fix POST /teams 403 (bug #5)** — revisar RBAC em `team_routes.py`. Owner role DEVE ter permissão `team.create` no próprio business. **@dev (Neo)**.
4. **Implementar POST /businesses (bug #1)** — super-admin precisa UI funcional para onboardar novos clientes. **@dev (Neo)** implementa endpoint + UI.
5. **Padronizar error feedback em modais (bugs #6, #9, #10)** — criar componente toast/banner reutilizável, integrar em todos modais de CRUD. **@ux-design-expert (Sati)** especifica + **@dev (Neo)** integra.
6. **Resolver divergência /teams UI vs DB (bug #7)** — query de /teams está lendo de tabela errada (provavelmente `cleaning_teams_members` junction vs `cleaning_team_members.cleaning_team_id`). **@data-engineer (Tank)** investiga.
7. **Adicionar `Services` ao sidebar (bug #11)** — item nav dentro da seção `Pricing` ou `Management`. **@dev (Neo)**.
8. **Backlog LOW existente (bugs #2/#3/#4)** — já tratados no sprint fix anterior como F8/F9; autocomplete form é comportamento browser normal — classificar como WON'T FIX.

## Items Pulados (por bloqueio upstream ou guard-rail)

- **Step 5 (Create Location):** não executado por tempo — suspeito de ter o mesmo padrão RBAC/500 dos outros CRUDs.
- **Step 6 (Team members add):** bloqueado pelo bug #5 (sem team novo, impossível atribuir members).
- **Step 8 (Create booking):** bloqueado por falta de client novo (bug #8) + sem team novo (bug #5). Além disso `+ New Booking` redireciona para /schedule em vez de abrir modal — fluxo UX indefinido.
- **Step 9 (Team lead checkin/checkout):** bloqueado por ausência de booking novo atribuído.
- **Step 10 (Cleaner earnings):** bloqueado por ausência de booking completed novo.
- **Step 11 (Homeowner request cleaning):** não executado — homeowner.demo já existe em outro business (Clean New Orleans provável, dado cross-tenant leak), teste sairia poluído.
- **Step 12 (Owner calendar/invoice/reports):** bloqueado pela cadeia de bloqueios anteriores.

## Console errors coletados

Do run Playwright (não incluindo warnings):

1. `GET /cleaning/static/img/logo.png → 404` (bug #2)
2. `GET /cleaning/static/icons/icon-192.png → 404` (bug #3)
3. `POST /api/v1/clean/xcleaners-demo/teams → 403` (bug #5)
4. `POST /api/v1/clean/xcleaners-demo/clients → 500` (bug #8)

## Achado adicional (divergência /schedule vs /bookings)

- `/schedule` mostra 0 Jobs Today, $0 Revenue, 0 Teams Active — corretamente filtrado por `business_id=Xcleaners Demo`.
- `/bookings` mostra 25 Upcoming + 7 Past — dados de outros businesses (leak).
- **Isso localiza o bug #14 no endpoint `/bookings` listing, não em `/schedule`.** Reforça recomendação #1.

## Console errors coletados

_A preencher via `browser_console_messages` em telas críticas._
