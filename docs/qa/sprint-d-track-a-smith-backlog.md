---
type: qa-backlog
title: "Sprint D Track A — Smith Adversarial Review Backlog"
project: xcleaners
status: CONTAINED
reviewer: "@smith (Smith)"
date: "2026-04-16"
artifact_reviewed: "C:/xcleaners/docs/sprints/sprint-d-recurring-payroll.md (secao Track A linhas 22-402)"
adr_reference: "C:/xcleaners/docs/architecture/adr-002-recurring-auto-generator.md"
verdict: CONTAINED
blocker_count: 0
findings_total: 4
severity_breakdown:
  CRITICAL: 0
  HIGH: 0
  MEDIUM: 0
  LOW: 4
tags:
  - project/xcleaners
  - qa
  - smith
  - sprint-d
  - track-a
---

# Sprint D Track A — Smith Adversarial Review Backlog

## Veredicto: **CONTAINED**

*O Sr. Morgan produziu um plano... quase limpo. Quase. Mas "quase" nunca e suficiente na Matrix. Esses quatro pequenos defeitos podem ser tolerados — ou corrigidos em-linha pelo Sr. Anderson durante execucao. Nenhum bloqueia o codigo.*

**Decisao:** @dev pode executar Track A. Findings abaixo viram polimentos in-flight ou backlog pos-implementacao.

---

## Checklist executado (10-point)

| Check | Status |
|-------|--------|
| [A] Coerencia ADR-002 ↔ sprint plan | ✅ PASS |
| [B] No invention (Article IV LMAS) | ✅ PASS |
| [C] File List accuracy | ✅ PASS (941 LOC real vs 990 claimed vs 900 ADR — gap 4.5%) |
| [D] Test gate ±$0.01 clarity | ✅ PASS |
| [E] Track B preservado | ✅ PASS (linhas 406-474 intactas) |
| [F] DoD zero-regression explicit | ✅ PASS |
| [G] Ambiguidades | ⚠️ 2 findings LOW |
| [H] Dependencias ocultas | ⚠️ 1 finding LOW |
| [I] Timezone caveat | ✅ PASS |
| [J] agreed_price deprecation | ✅ PASS |

---

## Findings

### L1 — [LOW] Linha incorreta em AC2 referência a `_persist_assignments`

**Severidade:** LOW
**Categoria:** documentation accuracy
**Referencia:** `sprint-d-recurring-payroll.md` linha 116 (AC2)

**Problema:**
AC2 diz: *"Substituir o bloco de `INSERT INTO cleaning_bookings` (~linha 672-703)..."*

Verificado via Grep: `_persist_assignments` define-se em `daily_generator.py` linha **602**, nao 672. O INSERT real esta entre linhas ~672-703 dentro da função, mas a referência principal (header da função) e 602.

**Por que importa:**
Quando @dev abrir o arquivo e procurar "linha 672" para entender o contexto, vai estar no meio da funcao, nao no topo. Perda de contexto minor. Nao quebra execucao — dev inevitavelmente le a funcao inteira.

**Correcao sugerida:**
Alterar linha 116 do sprint plan de:
```
- Substituir o bloco de `INSERT INTO cleaning_bookings` (~linha 672-703) pela chamada...
```
Para:
```
- Substituir o bloco de `INSERT INTO cleaning_bookings` (dentro de `_persist_assignments`, funcao em ~linha 602) pela chamada...
```

**Quem corrige:** @dev durante T3.2 (trivial — 1 palavra de ajuste em comment) OU @pm pre-execucao.

---

### L2 — [LOW] AC2 ambiguidade: UPDATE direto vs delete+recreate

**Severidade:** LOW
**Categoria:** ambiguity
**Referencia:** `sprint-d-recurring-payroll.md` linha 117 (AC2)

**Problema:**
AC2 linha 117 diz:
> *"Para UPDATE path (booking unconfirmed ja existe), manter UPDATE direto OU delete+recreate para garantir snapshot fresh"*

**OR** sem decisao clara deixa @dev escolher. As duas opcoes tem tradeoffs:
- **UPDATE direto:** preserva `booking_id` (bom para audit), mas `price_snapshot` pode ficar stale se extras/formula mudaram entre primeira e segunda geracao
- **Delete+recreate:** garante snapshot fresh sempre, mas muda `booking_id` (potencial quebra se algo externo FK-referencia)

**Por que importa:**
Sr. Anderson tem historico de escolher o caminho "mais facil" sem avaliar semantica — UPDATE seria escolhido por inercia, mas e a opcao com bug latente.

**Correcao sugerida:**
Tomar decisao arquitetural e documentar:
```
- Para UPDATE path (booking unconfirmed ja existe): DELETE existing + chamar create_booking_with_pricing
  (garante snapshot fresh; booking_id muda mas nenhum caminho externo FK-referencia recurring-generated
  bookings unconfirmed — verificado via Grep em 2026-04-16)
```

**Quem corrige:** @dev decide in-flight durante T3.2-T3.3 (pode documentar decisao em commit message). Nao bloqueia.

---

### L3 — [LOW] AC6 + Test #3 — metodo de INSERT skip nao especificado

**Severidade:** LOW
**Categoria:** missing detail
**Referencia:** `sprint-d-recurring-payroll.md` linhas 178-181 (AC6) + linha 321 (Test #3)

**Problema:**
AC6 diz: *"UI da skips-manager fica para Story futura (v1: owner insere via admin query ou endpoint minimo se Luiz priorizar)"*

Test #3 (linha 321) diz: *"schedule Weekly Monday + INSERT skip para 2026-05-05..."*

Como o test INSERT? Duas opcoes validas:
1. Raw SQL direto no test (`INSERT INTO cleaning_schedule_skips VALUES (...)`)
2. Helper function em test fixtures

Sem especificar, @dev pode criar uma API endpoint que v1 nao precisa (scope creep) ou escrever raw SQL sem comment (puzzle para futuro leitor).

**Por que importa:**
Scope creep: @dev cria endpoint POST `/schedule/{id}/skips` pensando que e necessario → adiciona 50 LOC + test endpoint → expande escopo sem approval.

**Correcao sugerida:**
Adicionar 1 linha em T7.3 (subtask de Task 7):
```
- Test #3 INSERT skip via raw SQL fixture (nao criar endpoint v1 — defer to future story)
```

**Quem corrige:** @dev clarifica durante T7 OU @pm adiciona 1 linha pre-execucao.

---

### L4 — [LOW] AC1 backfill nao menciona que `cleaning_frequencies` ja seed

**Severidade:** LOW
**Categoria:** hidden dependency
**Referencia:** `sprint-d-recurring-payroll.md` linhas 103-105 (AC1 backfill step)

**Problema:**
AC1 descreve o backfill:
> *"UPDATE cleaning_client_schedules SET frequency_id = f.id FROM cleaning_frequencies f WHERE... LOWER(crs.frequency)=LOWER(f.name)"*

Mas NAO menciona que `cleaning_frequencies` JA TEM 4 seeds per business (One Time, Weekly, Biweekly, Monthly — seeded em migration 021 linhas 286-319).

**Por que importa:**
@dev pode:
1. Assumir seeds nao existem → propor NEW seed em migration 022 (redundante, collision com migration 021)
2. Rodar migration 022 em ambiente vazio (sem businesses) → backfill UPDATE 0 rows → achar que ha bug
3. Nao entender por que `LOWER('weekly') = LOWER('Weekly')` funciona (case normalization e necessaria porque seeds sao capitalizados "Weekly" mas schedules legacy tem "weekly" lowercase)

**Por que importa (real):**
Sem essa nota, @dev pode perder 30-60 min debugando "por que backfill nao preenche frequency_id?" quando na verdade o ambiente esta ok mas nao tem schedules de teste suficientes.

**Correcao sugerida:**
Adicionar nota em AC1 acima do bullet de backfill:
```
> **Pre-condition:** migration 021 ja seed 4 frequencies (One Time, Weekly, Biweekly, Monthly) per business
> com capitalizacao title-case. Backfill usa LOWER() matching para acomodar legacy lowercase.
```

**Quem corrige:** @pm adiciona 2 linhas OU @dev descobre empiricamente (custo: 30-60 min debug).

---

## Findings NAO encontrados (escrutinio positivo)

Normalmente apontaria:
- "ACs vagas" — **todas 8 sao especificas e testaveis**
- "File list com placeholders" — **todos os arquivos tem LOC estimate realista**
- "DoD genrico" — **DoD cita 4 arquivos especificos como zero-touch explicit**
- "Test gate sem fixture clear" — **Test #2 cita fixture F1 da Story 1.1 com valor exato $240.01 ±$0.01**

Sr. Morgan *surpreendeu-me.* Isto e raro.

---

## Recomendacao de handoff

**Verdict:** CONTAINED. Entrega aceitavel com ressalvas.

**Proxima acao:**
- @dev (Neo) pode comecar Task 1-7 em branch `feat/recurring-auto-gen`
- Findings L1-L4 sao polimentos in-flight durante execucao (total ~15 min para ajustar todos)
- Se @pm quiser pre-cleanup: 5 min de edit inline no sprint plan resolve L1+L2+L3+L4

**Nao bloquear execucao.** *Esses quatro defeitos sao triviais — o Sr. Anderson sobrevive. Dessa vez.*

---

*Verificacao concluida. E inevitavel.*

— Smith. 🕶️
