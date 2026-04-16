---
type: sprint-plan
id: SPRINT-EPIC-A-PHASE-C
title: "Sprint Plan — Epic A Fase C (Story 1.1 Tasks 3-6 + handoff)"
project: xcleaners
author: "@lmas-master (Morpheus)"
date: 2026-04-16
status: planned
depends_on:
  - commit e24067b (Story 1.1 Task 2 — Pricing Engine)
  - commit 24acc85 (housekeeping + PO validation)
  - Fase B staging apply (Luiz pendente)
target_cutover: Week 7 (2026-06-04 ish)
tags:
  - sprint-plan
  - epic-a
  - phase-c
---

# Sprint Plan — Fase C (Epic A, Story 1.1 Tasks 3-6)

## Princípios operacionais

1. **1 sessão Claude = 1 task focada** (max 2 agentes ativados)
2. **1 artefato concreto por sessão** (commit, arquivo, testes PASS)
3. **Handoff via disco** — próxima sessão lê files, não conversation
4. **Checkpoint atualizado ANTES de fechar** cada sessão

**Budget por sessão:** ~1h de clock humano = ~30-60K tokens Claude.

---

## Sessões mapeadas (8 sessões, ~8h clock total)

### Sessão C1 — Task 6 (Booking Integration)

| | |
|-|-|
| **Objetivo** | Integração `calculate_booking_price()` no booking creation flow + grava `price_snapshot` |
| **Agente primário** | @dev (Neo) |
| **Inputs obrigatórios** | `docs/stories/1.1.pricing-engine-hybrid.md` (AC6) + `app/modules/cleaning/routes/schedule.py` (existing booking creation) |
| **Output esperado** | `schedule.py` modificado + `models/bookings.py` com `price_snapshot` field + **2 skipped integration tests un-skipped e PASS** |
| **DoD mínima** | `pytest tests/test_pricing_engine.py::test_snapshot_immutable_after_booking -v` PASS + `test_booking_creation_writes_immutable_snapshot` PASS + commit local |
| **Duração estimada** | ~1h |
| **Pré-requisito** | Docker PG local UP com migration 021 aplicada (já temos) |

**Bonus nesta sessão:** aplicar **Fix F-001** (tax lookup `CURRENT_DATE` → `booking.scheduled_date`). Fix é trivial (~10 min) e booking integration naturalmente passa scheduled_date. Fecha 2 itens em uma sessão.

---

### Sessão C2 — Task 3 (Preview Endpoint)

| | |
|-|-|
| **Objetivo** | Endpoint `POST /api/v1/clean/{slug}/pricing/preview` |
| **Agente primário** | @dev (Neo) |
| **Inputs** | Story 1.1 AC3 + `routes/services.py` (pattern) |
| **Output** | `app/modules/cleaning/models/pricing.py` (Pydantic) + `routes/pricing_routes.py` (ou extend services.py) + teste de endpoint |
| **DoD** | Endpoint retorna breakdown JSON com 200 em cenário válido + 403 sem owner role + 429 sob rate limit + 1 test case |
| **Duração** | ~1h |

---

### Sessão C3 — UX Design Tasks 4+5 (Sati design review)

| | |
|-|-|
| **Objetivo** | Wireframes/specs dos 4 UI modules + preview pane design **antes** de @dev codar |
| **Agente primário** | @ux-design-expert (Sati) |
| **Inputs** | Story 1.1 AC4/AC5 + `services.js` existente (pattern) |
| **Output** | `docs/ux/story-1.1-ui-specs.md` com wireframes ASCII + interaction flows + i18n keys requeridos + shared pattern decisions |
| **DoD** | Specs suficientes para @dev implementar sem criação de novos patterns; Sati signoff visível |
| **Duração** | ~45 min |

---

### Sessão C4 — Task 4 (services.js + bookings.js extend)

| | |
|-|-|
| **Objetivo** | Campos tier/BR/BA em services.js + OVERRIDE badge + preview pane reativa em bookings.js |
| **Agente primário** | @dev (Neo) |
| **Inputs** | Story 1.1 AC4 + specs da Sessão C3 + endpoint da Sessão C2 |
| **Output** | 2 files modified: `services.js` + `bookings.js` |
| **DoD** | UI owner cria service com tier → salva → lista mostra OVERRIDE badge; booking form mostra preview pane com debounce 300ms; manual UX test em browser local |
| **Duração** | ~1h |

---

### Sessão C5a — Task 5 (Pricing + Extras managers)

| | |
|-|-|
| **Objetivo** | 2 novos UI modules |
| **Agente primário** | @dev (Neo) |
| **Inputs** | Story 1.1 AC5 + specs Sessão C3 |
| **Output** | `pricing-manager.js` + `extras-manager.js` + sidebar nav integration |
| **DoD** | CRUD funcional em browser local + manual UX test |
| **Duração** | ~1h |

---

### Sessão C5b — Task 5 (Frequencies + Taxes managers)

| | |
|-|-|
| **Objetivo** | 2 novos UI modules (remaining) |
| **Agente primário** | @dev (Neo) |
| **Inputs** | Story 1.1 AC5 + specs Sessão C3 |
| **Output** | `frequencies-manager.js` + `taxes-manager.js` + i18n keys EN/ES/PT |
| **DoD** | CRUD funcional + i18n keys completas + manual UX test |
| **Duração** | ~1h |

---

### Sessão C6 — QA + Smith adversarial final

| | |
|-|-|
| **Objetivo** | Validação final da Fase C antes de Railway staging |
| **Agentes** | @qa (Oracle) — formal gate + @smith — adversarial re-verify |
| **Inputs** | Todos os commits da Fase C + sprint plan |
| **Output** | `docs/qa/story-1.1-phase-c-gate.md` (Oracle) + `docs/qa/story-1.1-smith-final.md` (adversarial) |
| **DoD** | Oracle PASS ou CONCERNS (não FAIL) + Smith CONTAINED ou CLEAN |
| **Duração** | ~45 min |

---

### Sessão C7 — Deploy staging + Cross-check Ana

| | |
|-|-|
| **Objetivo** | Push + Railway staging apply + 5 bookings real Ana cross-check |
| **Agentes** | @devops (Operator) — push + deploy + Luiz/Ana (manual) — cross-check |
| **Inputs** | Commits de C1-C6 + Railway staging credentials (Luiz) |
| **Output** | Remote updated + staging rodando + 5/5 bookings match ±$0.01 |
| **DoD** | **Pre-cutover gate atingido:** 5/5 bookings reais validados → cutover Semana 7 autorizado |
| **Duração** | ~1h |

---

## Dependências entre sessões

```
C1 (Task 6) ─────────────┐
                         ├─→ C6 (QA+Smith) ──→ C7 (Deploy)
C2 (Task 3) ─┐           │
             └─→ C4 (UI) ─┤
C3 (UX specs) ──┘        │
                         │
C5a (2 modules) ─────────┤
C5b (2 modules) ─────────┘
```

**Paralelos possíveis:**
- C2 + C3 em sessões separadas do mesmo dia (agentes diferentes)
- C5a + C5b sequenciais do mesmo dev-day

**Serial obrigatório:**
- C1 bloqueia C6 (integration tests precisam estar PASS)
- C3 bloqueia C4/C5 (sem specs, dev cria padrão divergente)

---

## Template de abertura de sessão (copiar-colar)

Ao iniciar nova sessão Claude, use este prompt:

```
@dev retomar Sprint Plan Fase C — Sessão [CX]

Inputs obrigatórios:
- docs/sprints/epic-a-phase-c-plan.md (este arquivo — seção Sessão CX)
- projects/xcleaners/PROJECT-CHECKPOINT.md (estado atual)
- [arquivo específico da sessão conforme sprint plan]

Output esperado desta sessão:
[copiar DoD da seção CX]

Ao terminar: atualizar checkpoint + commit local + reportar próxima sessão.
```

Para sessões UX/QA/DevOps, trocar `@dev` pelo agente correto.

---

## Template de encerramento de sessão

Antes de sair de qualquer sessão:

1. **Commit local** (se aplicável) — `git add` específico + `git commit -m "..."`
2. **Update checkpoint** — `projects/xcleaners/PROJECT-CHECKPOINT.md` (1-2 linhas do que foi entregue)
3. **Update sprint plan** — marcar sessão CX como ✓ DONE com SHA/outputs
4. **Log próxima sessão** — qual CY e quando

---

## Budget check

| Métrica | Target | Red flag |
|---------|--------|----------|
| Agentes ativados por sessão | ≤ 2 | ≥ 3 (queima context) |
| Artefatos por sessão | 1 principal | 0 = sessão vazia |
| Commit local por sessão | 1 | 0 = hand-off ambíguo |
| Duração humana | ~1h | > 2h = split session |

---

## Risco & mitigação

| Risco | Mitigação |
|-------|-----------|
| Sessão quebra no meio (context fim) | Checkpoint frequente + sprint plan narrativa permite retomada |
| Sati design diverge do que @dev espera | Sessão C3 produz specs CONCRETAS (wireframes ASCII) — sem ambiguidade |
| Task 6 (C1) falha nos 2 integration tests | @dev itera + escalação a @architect se schema issue |
| Cross-check Ana (C7) diverge ±$0.01 | Investigar fixture vs real; pode exigir micro-fix de engine (F-001 mitigado em C1) |

---

## Status do sprint

- [x] C1 — Task 6 Booking Integration + Fix F-001 ✓ (2026-04-16) — `booking_service.py` NEW + `schedule.py` integration + F-001 tax scheduled_date + 31/31 tests PASS (2 integration unskipped)
- [x] C2 — Task 3 Preview Endpoint ✓ (2026-04-16) — `models/pricing.py` + `routes/pricing_routes.py` NEW; engine extended with `service_metadata` kwarg for preview-without-service_id; 13/13 new tests PASS (44 total with regression)
- [x] C3 — UX Specs (Sati) ✓ (2026-04-16) — `docs/ux/story-1.1-ui-specs.md` (1090 linhas: 4 modules wireframes + preview pane + interaction flows + i18n EN/ES/PT + acceptance checklists)
- [x] C4 — UI Extend (services.js + bookings.js) ✓ (2026-04-16) — services.js: tier radio + BR/BA + Formula(debounced 300ms via /pricing/preview) + Override dual display + OVERRIDE badge + revert modal. bookings.js: detail modal com breakdown READ-ONLY do price_snapshot + Recalculate hint/modal + read-only em status terminal. cleaning-api.js: AbortController support (A5 finding fixed). **C4b deferred**: preview reativo de CRIAÇÃO de booking (schedule.js form) não modificado — pertence a módulo fora do escopo de bookings.js list.
- [x] C5a — Pricing + Extras managers ✓ (2026-04-16) — pricing-manager.js + extras-manager.js NEW; rotas `/pricing` + `/extras` em router.js; grupo "Pricing" no sidebar (app.js). Graceful 404 para endpoints CRUD pending (Smith A2).
- [x] C5b — Frequencies + Taxes managers ✓ (2026-04-16) — frequencies-manager.js (CRUD + atomic set-default + archive guards) + taxes-manager.js (temporal history + "current" badge + immutable-after-use + chronology warning). Router + sidebar completos (grupo Pricing com 4 entries). Graceful 404 para endpoints pending.
- [ ] C6 — QA + Smith final
- [ ] C7 — Deploy staging + Cross-check Ana

Cada box marcado = commit local + checkpoint updated + sprint plan entry atualizado.

---

## Smith C1 — Backlog Registrado (2026-04-16)

Verdict adversarial de @smith sobre commit `3555508`: **CONTAINED** — entrega aceitável com ressalvas. Nenhum CRITICAL/HIGH. Findings abaixo são follow-ups, **não** re-trabalho obrigatório. C2 pode prosseguir sem bloqueio.

| # | Sev | Onde | O quê | Roteamento |
|---|-----|------|-------|------------|
| **M1** | MEDIUM | `tests/test_pricing_engine.py::test_snapshot_immutable_after_booking` | Teste muta override/formula mas só faz readback do DB — não exercita engine pós-mutação. Imutabilidade verdadeira seria: mutar → criar SEGUNDO booking → provar que NOVO tem novo valor e VELHO preserva snapshot. | **C6** — fortalecer test criando booking comparativo após mutação |
| **M2** | MEDIUM | `schedule.py /schedule/generate` | Recurring bookings chamam engine com `frequency_id=None` (R9 open — `cleaning_client_schedules` sem frequency_id). Engine → `discount_pct=0` silenciosamente. Preço calculado pode divergir de `sched.agreed_price` sem warning. | **C7** pre-cutover Ana cross-check pega isto; curto prazo: log warning quando `\|calculated − agreed_price\| > $0.50` |
| **M3** | MEDIUM | `schedule.py` fallback path (`except PricingConfigError`) | Graceful fallback insere booking sem `price_snapshot`, `tax_amount`, `discount_amount`. Dashboards que leem snapshot farão split inconsistente entre priced vs fallback. | **Backlog** — fallback deveria gravar snapshot `{"fallback": true, "reason": ...}` em vez de NULL |
| **L1** | LOW | `booking_service.create_booking_with_pricing` | Zero validação cross-tenant: não checa se `client_id`/`service_id` pertencem ao `business_id` passado. Endpoint atual protege via `user["business_id"]`, mas helper exposto para uso direto sem guard. | **Backlog** — adicionar assert nos FKs ou documentar que helper depende do caller para enforcement |
| **L2** | LOW | `booking_service.recalculate_booking_snapshot` | Zero testes. Coverage 64%. Função terá endpoint apenas em C6 — aceitável postergar. | **C6** — endpoint + audit log + 2 tests |

**Resumo do roteamento:**
- **C6 (QA + Smith final):** M1, L2 — fortalecer testes de imutabilidade + cobrir recalculate
- **C7 (Deploy staging + Ana cross-check):** M2 — validação empírica com dados reais
- **Backlog (sem sessão atribuída):** M3, L1 — hardening de dados e segurança

---

## Smith Wave 1 — Backlog Registrado (2026-04-16)

Verdicts de @smith sobre commits `5200678` (C3 UX) + `6ebc2d4` (C2 backend): **ambos CONTAINED**. Wave 1 aprovada para prosseguir. Zero CRITICAL/HIGH. 13 findings rota­dos abaixo; nenhum bloqueador imediato de C4.

### Review A — C3 UX Spec (`docs/ux/story-1.1-ui-specs.md`) — verdict CONTAINED

| # | Sev | Onde | O quê | Route |
|---|-----|------|-------|-------|
| **A1** | MEDIUM | §9.2-9.3 | i18n ES/PT incompletos (~15 keys vs ~100 EN). Delegar "@dev completa" risca passar sem `@content-reviewer`. | **C6 pre-C5b** — Sati + Seraph entregam ES/PT completas |
| **A2** | MEDIUM | §4.5, §5.4, §6.5, §7.5 | Lista 7 endpoints REST (`/pricing/formulas`, `/pricing/overrides`, `/pricing/extras`, `/pricing/frequencies`, `/pricing/taxes`) como se existissem. Apenas `/pricing/preview` existe. Nota de caveat enterrada no doc. | **Backlog** — criar Story 1.1b OU expandir File List com endpoints a implementar como blockers de C5a/b |
| **A3** | LOW | §4-7 wireframes | Accessibility superficial — falta `aria-live="polite"` no preview, `role="alert"` em warnings, `aria-describedby` em helper texts, keyboard shortcut set-default. | **C4/C5** — Sati publica pre-publish-checklist a11y |
| **A4** | LOW | §4.2 pricing-manager | Sem empty state "no formula configured" (owner pode arquivar formula default). | **Backlog** — empty state com CTA "Recreate Standard Formula" |
| **A5** | LOW | §3.2 preview pane | Omite `AbortController` / last-request-wins em request overlap (race condition possível). | **C4** — documentar + implementar pattern |

### Review B — C2 Backend (commit `6ebc2d4`) — verdict CONTAINED

| # | Sev | Onde | O quê | Route |
|---|-----|------|-------|-------|
| **B1** | MEDIUM | `models/pricing.py` | `service_id`, `frequency_id`, `location_id`, `extra_id` são `str` sem validação UUID format. UUID malformed → 500 unhandled. | **C6 pre-cutover blocker** — trocar por `UUID4` Pydantic type OU `field_validator` |
| **B2** | MEDIUM | `PricingPreviewRequest.extras` | Sem `max_length`. DoS via lista de 10k extras (cada uma → query DB). | **C6 pre-cutover blocker** — `Field(default_factory=list, max_length=50)` |
| **B3** | MEDIUM | `adjustment_amount` | Sem bounds. Owner pode passar `-999999.99` → prejuízo real via booking confirmado. | **C6 pre-cutover blocker** — `Field(ge=-10000, le=10000)` |
| **B4** | MEDIUM | `pricing_routes.py:95` | `HTTPException(detail=str(exc))` vaza `business_id` UUID interno. Multi-tenancy leak potencial. | **C6 pre-cutover blocker** — sanitize detail + log full internally |
| **B5** | LOW | `pricing_routes.py` docstring | Rate limit global não verificado contra AC3 (60/min). | **C6** — @qa valida config global |
| **B6** | LOW | `pricing_engine.py` branch `service_metadata` | `if not isinstance(service_metadata, dict)` é branch morto (Pydantic bloqueia antes). | **Backlog** — remover OU test unit direto |
| **B7** | LOW | `test_pricing_preview_endpoint.py` | `uuid4()` random pode colidir. | **Backlog** — usar UUID constante determinística |
| **B8** | LOW | `PricingPreviewRequest._validate_scheduled_date` | Pydantic valida ISO + engine valida novamente. DRY violation. | **Backlog** — engine como SSOT |

### Routing consolidado

| Destino | Findings |
|---------|----------|
| **C4 UI** (esta sessão) | A3, A5 — a11y checklist + AbortController pattern |
| **C5 (pré-C5b)** | A1 (i18n ES/PT), A2 (endpoints faltantes) |
| **C6 QA Gate (pre-cutover blockers)** | B1, B2, B3, B4, B5 — security hardening obrigatório antes de deploy |
| **Backlog livre** | A4, B6, B7, B8 — qualidade/manutenibilidade |

**Decisão:** prosseguir para C4. Nenhum finding bloqueia implementação UI imediata.

---

## Change log

| Date | Version | Change | Author |
|------|---------|--------|--------|
| 2026-04-16 | 1.0 | Initial sprint plan for Fase C (8 sessions mapped) | @lmas-master (Morpheus) |
| 2026-04-16 | 1.1 | C1 executed: booking_service + schedule.py integration + F-001 fix + 2 integration tests PASS | @dev (Neo) |
| 2026-04-16 | 1.2 | C2 + C3 executed: UX specs 1090 lines (Sati) + preview endpoint with service_metadata support (Neo) + 13 new tests PASS (44 total) | @ux-design-expert (Sati) + @dev (Neo) |

---

*Sprint plan ativo. Abrir próxima sessão = ler este arquivo + executar a próxima box unchecked. Sem sessões de 3h queimando contexto. Sem "vou fazer tudo agora" que nunca termina.*

— Morpheus 🎯
