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
- [ ] C2 — Task 3 Preview Endpoint
- [ ] C3 — UX Specs (Sati)
- [ ] C4 — UI Extend (services.js + bookings.js)
- [ ] C5a — Pricing + Extras managers
- [ ] C5b — Frequencies + Taxes managers
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

## Change log

| Date | Version | Change | Author |
|------|---------|--------|--------|
| 2026-04-16 | 1.0 | Initial sprint plan for Fase C (8 sessions mapped) | @lmas-master (Morpheus) |
| 2026-04-16 | 1.1 | C1 executed: booking_service + schedule.py integration + F-001 fix + 2 integration tests PASS | @dev (Neo) |

---

*Sprint plan ativo. Abrir próxima sessão = ler este arquivo + executar a próxima box unchecked. Sem sessões de 3h queimando contexto. Sem "vou fazer tudo agora" que nunca termina.*

— Morpheus 🎯
