# Xcleaners E2E — Working State (session memory)

> **Propósito:** este arquivo é a **memória persistente** do trabalho de construção da suite E2E. Sobrevive a compaction e nova sessão. SEMPRE atualizado após cada marco. **Primeiro arquivo a ler no início de qualquer sessão nova.**

## Status atual

- **Sessão ativa:** 2026-04-20 (night → 21 morning autonomous build)
- **Agent:** Oracle (QA) — sem troca de persona até entrega final
- **Fase corrente:** 01-setup

## Marcos (checklist progressivo)

- [x] 00. Análise / arquitetura decidida (TypeScript + Playwright + POM + multi-env)
- [x] 01. Seed DB prod: business `e2e-testing-co` + 3 users `test-e2e-*@xcleaners-e2e.com`
- [x] 02. Estrutura pastas `tests-e2e/`
- [x] 03. `package.json` + `tsconfig.json` + `.env.{prod,staging,example}` + `.gitignore`
- [x] 04. `playwright.config.ts` multi-env com reporter + trace/screenshot on failure
- [x] 05. `npm install` + `npx playwright install chromium`
- [x] 06. Fixtures (auth.fixture + auth.setup + policy.fixture)
- [x] 07. Page Objects (11 POMs: LoginPage + 7 owner + 3 homeowner + 1 cleaner)
- [x] 08. Helpers (api-client + db-helpers + assertions)
- [x] 09. Tests — Smoke (3 files, 9 specs) — ALL PASS
- [x] 10. Tests — Policy MVP (5 specs) — ALL PASS
- [x] 11. Tests — Regression (7 specs) — ALL PASS
- [x] 12. Tests — Negativos (2 specs) — ALL PASS
- [x] 13. Primeiro run completo + fixes
- [x] 14. Bug fixes autorizados (addHours overflow, hydrate timing, selectors)
- [x] 15. `.github/workflows/e2e.yml` CI matriz
- [x] 16. `README.md` + `CONTRIBUTING.md` + `BACKLOG.md`
- [x] 17. `REPORT-2026-04-21.md` resultado final
- [x] 18. Commits progressivos no git local (push → @devops de manhã)

**TOTAL: 32/32 specs passing em 56.4s.**

## Ambiente criado (prod Railway)

| Recurso | ID/Slug | Detalhes |
|---|---|---|
| Business | `e2e-testing-co` (id=329f590d) | plan=maximum, tz=America/Chicago, cleaning_settings={} (defaults) |
| Owner | `test-e2e-owner@xcleaners.test` (id=a6e2932f) | role=owner |
| Homeowner | `test-e2e-homeowner@xcleaners.test` (id=2db41193) | role=homeowner |
| Cleaner | `test-e2e-cleaner@xcleaners.test` (id=66c1868a) | role=cleaner |
| Senha all | `E2eTest2026!` | bcrypt hash |

## Decisões arquiteturais (não revogar sem ultrathink)

1. **TypeScript** — typings nativos Playwright, zero overhead
2. **Business dedicado E2E Testing Co** — isolar de QATEST (Paola usa QATEST real)
3. **`fullyParallel: false`** default — alguns testes mutam policy do business (shared state). Specs independentes em smoke/ podem ligar parallel local.
4. **storageState por role** — auth fixture faz 1 login por role, salva storage, reusa em N testes (fast)
5. **Não mexer em checkpoint LMAS** (`projects/xcleaners/PROJECT-CHECKPOINT.md`) — outro terminal do Luiz escreve ali
6. **Commit progressivo em git local** — @devops push de manhã, user valida
7. **Trace + video + screenshot on failure** via playwright default config
8. **Tentativa conservadora de bug fix** apenas em bugs isolados (ex: query sem `business_id`). Refatorações complexas (Reports mock) → BACKLOG.md

## Findings da validação manual (pré-suite) que viram specs

| ID | Descoberta | Spec que valida |
|---|---|---|
| F1 MEDIUM | Dashboard KPIs zerados | `tests/regression/owner-dashboard.spec.ts` (TODO: fix + assert) |
| F2 MEDIUM | Reports page mostra dados MOCK (Michael Williams, $9922) | BACKLOG (rabbit hole) + `tests/negative/reports-not-mock.spec.ts` |
| F3 LOW | `/formulas` deep-link 404 | `tests/negative/direct-url-routes.spec.ts` |
| F4 LOW | LTV=$0 em Clients page | BACKLOG |
| F5 PASS | Policy MVP end-to-end | `tests/regression/policy-mvp/*.spec.ts` (5 specs) |

## Próximo passo imediato

**ENTREGA 100% CONCLUÍDA — 32/32 specs PASSING em 56.4s.**

Todos os fixes necessários já aplicados:
- `addHours` com clamp em 23:59 (evita overflow TIME)
- `MyBookingsPage.goto()` com hydrate sync (network idle + card/empty-state wait)
- `CancelModal` seletors do banner via div parent (não cross-text regex)
- `OwnerSettingsPage.savePolicy` com `waitForResponse` no PUT /settings
- DB helpers: schema alinhado (`status` vs `is_active`, `slug`, `category` enum)
- users com domain `.com` (não `.test` reserved)

## Rule do reload de contexto (diretriz Luiz 2026-04-20)

- Se esta sessão for compactada OU nova sessão começar, o **primeiro read** deve ser este arquivo
- Verificar `git log --oneline -20` em `C:/xcleaners` pra ver último commit E2E
- Retomar do primeiro marco `[ ]` não checado
- NUNCA refazer marco já `[x]` (loop infinito = bloqueado)

## Log de sessão (append-only)

### 2026-04-20 ~22:30 UTC — Oracle sessão inicial
- Validação manual owner + homeowner (11 tasks) → GO FOR CUTOVER
- Luiz pediu suite Playwright estruturada + autonomia noturna
- DB seeded, estrutura criada, config multi-env pronto
- Próximo: npm install + fixtures
