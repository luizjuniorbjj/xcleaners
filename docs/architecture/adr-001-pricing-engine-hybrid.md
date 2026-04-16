---
type: adr
id: ADR-001
title: "Pricing Engine Hybrid — Formula + Override Conflict Resolution"
status: accepted
date: 2026-04-16
author: "@architect (Aria)"
project: xcleaners
supersedes: []
impacts:
  - Story 1.1 (Pricing Engine)
  - Story 1.2 (Extras Catalog)
  - Story 1.3 (Frequency Discount)
  - Story 1.4 (Sales Tax + Adjustment)
  - Story 1.5 (Multi-Location)
  - Story 1.6 (Payroll Revenue Split)
  - Migration path from Launch27 to xcleaners
tags:
  - project/xcleaners
  - adr
  - pricing
  - architecture
---

# ADR-001 — Pricing Engine Hybrid Conflict Resolution

## Status
**Accepted** — 2026-04-16

## Context

Xcleaners está migrando 3Sisters Cleaning NYC de Launch27. Launch27 usa **lookup table pura** (32 entries manuais). Xcleaners adotou **modelo híbrido**: fórmula default + override por entry.

Fórmula alvo:
```
price = (base + bedrooms × α + bathrooms × β) × tier_multiplier
      + sum(extras)
      − frequency_discount_pct
      ± manual_adjustment
      + sales_tax
```

Esta ADR resolve 7 edge cases que bloqueiam Story 1.1 e determina o schema de dados para Stories 1.2-1.6.

**Gate crítico:** 10 bookings reais em Launch27 vs xcleaners devem bater com tolerância **±$0.01**. Ordem de operações, arredondamento e snapshot de preço histórico são requisitos para esse gate.

**Referência factual (booking real 3Sisters observado):**

| Etapa | Valor |
|-------|-------|
| Service (2R×1BA Basic) | $275.00 |
| + Extras (Stairs) | $30.00 |
| **Subtotal** | **$305.00** |
| − Discount (Weekly 15%) | −$45.75 |
| ± Adjustment (manual) | −$29.58 |
| **Amount before tax** | **$229.67** |
| + Sales tax (4.50% NYC) | +$10.34 |
| **Final** | **$240.01** |

Esta sequência é a **ordem canônica** que xcleaners DEVE replicar.

---

## Decisões

### Decisão 1 — Quando fórmula base muda, overrides existentes ficam STALE

Quando owner altera a fórmula default (ex: `α` de $20 → $30 por bedroom), **overrides existentes permanecem com o valor antigo**.

**Racional:**
- Override é intenção explícita do owner ("este combo tem ESTE preço, não o da fórmula")
- Recalcular automaticamente quebra a expectativa de quem criou o override
- Owner vê indicador visual (Decisão 4) de que override pode estar defasado; pode revogar com 1 click

**Alternativa rejeitada:** recalcular proporcionalmente ao delta — violação do princípio "override = intenção, não derivação".

**Alternativa rejeitada:** prompt "overwrite overrides?" na edição da fórmula — friction alta, decisão destrutiva escondida.

### Decisão 2 — Preço histórico dos bookings é IMUTÁVEL via snapshot

Toda criação de booking grava `cleaning_bookings.price_snapshot JSONB` contendo decomposição completa. Bookings passados **nunca** recalculam.

**Schema:**
```json
{
  "formula_id": "uuid",
  "service_id": "uuid",
  "tier": "basic",
  "tier_multiplier": 1.0,
  "base_amount": 155.00,
  "bedrooms": 2,
  "bedroom_delta": 20.00,
  "bathrooms": 1,
  "bathroom_delta": 15.00,
  "override_applied": false,
  "subtotal_service": 275.00,
  "extras": [{"id": "uuid", "name": "Stairs", "qty": 1, "price": 30.00}],
  "extras_sum": 30.00,
  "subtotal": 305.00,
  "frequency_id": "uuid",
  "frequency_name": "Weekly 15%",
  "discount_pct": 15.00,
  "discount_amount": 45.75,
  "adjustment_amount": -29.58,
  "adjustment_reason": "Complaint refund",
  "amount_before_tax": 229.67,
  "tax_pct": 4.50,
  "tax_amount": 10.34,
  "final_amount": 240.01,
  "calculated_at": "2026-04-16T12:34:56Z"
}
```

**Racional:** audit + compliance + recálculo defensivo em disputas. Custo: JSONB ~500 bytes/booking = irrelevante (23 tables × 318 bookings = <200KB para 3Sisters).

### Decisão 3 — Override é ATOMIC por campo (v1: apenas `price`)

Owner pode customizar **apenas o price final** de uma entry específica. Demais atributos (duration, extras whitelist) permanecem derivados da fórmula + tier.

**Schema:**
```sql
cleaning_service_overrides (
  id UUID PRIMARY KEY,
  service_id UUID REFERENCES cleaning_services(id),
  tier VARCHAR(20) CHECK (tier IN ('basic', 'deep', 'premium')),
  price_override NUMERIC(10,2) NOT NULL,
  reason VARCHAR(255),
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  is_active BOOLEAN DEFAULT TRUE,
  UNIQUE(service_id, tier)
)
```

**Racional v1:**
- `price_override` resolve 90% dos casos práticos ("este combo custa mais por complexidade")
- Override granular de `duration_override` fica para v2 (se owner reclamar, adicionamos)
- `UNIQUE(service_id, tier)` previne duplicação

**Lookup precedence:**
```
IF override exists AND is_active:
    use override.price_override
ELSE:
    compute from formula + tier_multiplier
```

### Decisão 4 — UI distingue override vs derivado com badge + revert

Na listagem de services no painel do owner:
- Entries com override: **badge laranja "OVERRIDE"** ao lado do preço
- Tooltip no badge: `"Fórmula calcula $X. Você customizou para $Y. Motivo: ..."`
- Botão inline `↩ Revert to formula` ao lado do badge

Na edição do service:
- Campo de preço mostra dois valores: `Formula: $X` (readonly, cinza) + `Override: $Y` (editável)
- Clear button no override → apaga override, campo volta a calcular from formula

**Racional:** transparency impede confusão quando fórmula muda e override fica defasado (Decisão 1).

### Decisão 5 — Tier multiplier aplica SÓ em (base + BR + BA), NÃO em extras

Ordem:
```
service_amount = (base + bedrooms × α + bathrooms × β) × tier_multiplier
extras_amount  = sum(extra.price × extra.qty)  // flat, independente de tier
subtotal       = service_amount + extras_amount
```

**Evidência factual:** Launch27 cobra extras flat $25-$30 independente de tier (Basic/Deep/Premium).

**Racional:** extras são custo operacional linear (tempo extra de trabalho). Tier representa qualidade/intensidade do clean base, não dos add-ons.

### Decisão 6 — Sales tax aplica sobre (subtotal − discount − adjustment)

Base tributável:
```
amount_before_tax = subtotal − discount_amount − adjustment_amount
tax_amount        = round(amount_before_tax × tax_pct / 100, 2)
final_amount      = amount_before_tax + tax_amount
```

**Validação contra 3Sisters:**
- amount_before_tax = 305 − 45.75 − 29.58 = **$229.67** ✓
- tax_amount = 229.67 × 0.045 = 10.33515 → round = **$10.34** ✓
- final_amount = 229.67 + 10.34 = **$240.01** ✓

**Racional:** tax aplicada sobre valor LÍQUIDO (pós-desconto pós-ajuste) é o padrão legal US sales tax e bate com Launch27.

### Decisão 7 — Adjustment aplica ANTES do tax

Ordem canônica validada:
```
1. service_amount   = (base + BR + BA) × tier_multiplier
2. extras_amount    = sum(extras)
3. subtotal         = service_amount + extras_amount
4. discount_amount  = subtotal × (frequency_discount_pct / 100)
5. adjustment       = manual ±$ (signed)
6. amount_before_tax = subtotal − discount_amount + adjustment
7. tax_amount       = round(amount_before_tax × tax_pct / 100, 2)
8. final_amount     = amount_before_tax + tax_amount
```

**Nota sobre sign convention:** `adjustment_amount` é signed no schema (pode ser negativo ou positivo). Na fórmula soma diretamente — se owner digita "−$30", adjustment = −30; amount_before_tax diminui.

---

## Decisão de Schema — substituir `cleaning_pricing_rules`

A tabela `cleaning_pricing_rules` existente é over-engineered (JSONB conditions complexas), sem código usando, e não serve o modelo híbrido desta ADR.

**Decisão:** manter `cleaning_pricing_rules` inerte (soft-deprecate com comentário), criar schema novo focado.

**Novo schema (Stories 1.1-1.5):**

```sql
-- Formula default per business (+ optional per location)
CREATE TABLE cleaning_pricing_formulas (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    location_id UUID REFERENCES cleaning_locations(id) ON DELETE CASCADE, -- NULL = default
    name VARCHAR(100) NOT NULL,
    base_amount NUMERIC(10,2) NOT NULL,                  -- e.g., 115.00
    bedroom_delta NUMERIC(10,2) NOT NULL,                -- e.g., 20.00 (α)
    bathroom_delta NUMERIC(10,2) NOT NULL,               -- e.g., 15.00 (β)
    tier_multipliers JSONB NOT NULL,                     -- {"basic": 1.0, "deep": 1.8, "premium": 2.8}
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Per-service override (granular: price only in v1)
CREATE TABLE cleaning_service_overrides (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    service_id UUID NOT NULL REFERENCES cleaning_services(id) ON DELETE CASCADE,
    tier VARCHAR(20) NOT NULL CHECK (tier IN ('basic', 'deep', 'premium')),
    price_override NUMERIC(10,2) NOT NULL,
    reason VARCHAR(255),
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    UNIQUE(service_id, tier)
);

-- Add tier column to existing services
ALTER TABLE cleaning_services
    ADD COLUMN tier VARCHAR(20) CHECK (tier IN ('basic', 'deep', 'premium')),
    ADD COLUMN bedrooms INT,
    ADD COLUMN bathrooms INT;

-- Extras catalog (global per business)
CREATE TABLE cleaning_extras (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    price NUMERIC(10,2) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    sort_order INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Extras whitelist per service (which extras are allowed for which service)
CREATE TABLE cleaning_service_extras (
    service_id UUID REFERENCES cleaning_services(id) ON DELETE CASCADE,
    extra_id UUID REFERENCES cleaning_extras(id) ON DELETE CASCADE,
    PRIMARY KEY (service_id, extra_id)
);

-- Booking-level extras (snapshot of price at time of booking)
CREATE TABLE cleaning_booking_extras (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    booking_id UUID NOT NULL REFERENCES cleaning_bookings(id) ON DELETE CASCADE,
    extra_id UUID REFERENCES cleaning_extras(id) ON DELETE SET NULL,
    name_snapshot VARCHAR(100) NOT NULL,
    price_snapshot NUMERIC(10,2) NOT NULL,
    qty INT NOT NULL DEFAULT 1
);

-- Frequencies (recurring intervals with discount)
CREATE TABLE cleaning_frequencies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    name VARCHAR(50) NOT NULL,                  -- "Weekly 15%"
    interval_weeks INT,                          -- 1, 2, 4, NULL for one-time
    discount_pct NUMERIC(5,2) DEFAULT 0,         -- 15.00
    is_default BOOLEAN DEFAULT FALSE,
    is_archived BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Sales taxes (per location, temporal)
CREATE TABLE cleaning_sales_taxes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    location_id UUID REFERENCES cleaning_locations(id) ON DELETE CASCADE,
    tax_pct NUMERIC(5,2) NOT NULL,
    effective_date DATE NOT NULL,
    is_archived BOOLEAN DEFAULT FALSE
);

-- Locations (multi-location support — blocks 3Sisters NYC + Dallas)
CREATE TABLE cleaning_locations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    postal_codes TEXT[],
    is_default BOOLEAN DEFAULT FALSE,
    is_archived BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Booking additions
ALTER TABLE cleaning_bookings
    ADD COLUMN tax_amount NUMERIC(10,2) DEFAULT 0,
    ADD COLUMN adjustment_amount NUMERIC(10,2) DEFAULT 0,
    ADD COLUMN adjustment_reason VARCHAR(255),
    ADD COLUMN frequency_id UUID REFERENCES cleaning_frequencies(id) ON DELETE SET NULL,
    ADD COLUMN location_id UUID REFERENCES cleaning_locations(id) ON DELETE SET NULL,
    ADD COLUMN price_snapshot JSONB;

-- Team wage for payroll (Story 1.6)
ALTER TABLE cleaning_team_members
    ADD COLUMN wage_pct NUMERIC(5,2) DEFAULT 60.00;  -- 3Sisters default
```

**Racional:**
- `cleaning_pricing_formulas` separado de `cleaning_pricing_rules` existente — zero risco de quebrar código legado inativo
- `cleaning_service_overrides` atomic, indexável, auditável
- `cleaning_booking_extras` com snapshot evita `extras.price` ser mutável alterando bookings passados
- `cleaning_locations` como first-class (antes era só `cleaning_areas` com zip codes)
- Todos os novos campos em `cleaning_bookings` têm DEFAULT para backfill seguro

---

## Seção 5 — Compatibilidade com Schema Existente (revisão 2026-04-16)

Primeira versão desta ADR foi greenfield demais. Revisão harmoniza com código/schema já em produção no xcleaners.

### 5.1 Campos JÁ existentes em `cleaning_bookings` — preservar + coexistir

| Campo existente | Comportamento |
|-----------------|---------------|
| `quoted_price NUMERIC(10,2)` | **Mantido** — preço mostrado ao customer na preview (pré-adjustment) |
| `final_price NUMERIC(10,2)` | **Mantido** — resultado da fórmula completa (= `final_amount` do snapshot) |
| `discount_amount NUMERIC(10,2) DEFAULT 0.00` | **Mantido** — captura SÓ frequency/discount-code based (pct) |
| `discount_reason VARCHAR(255)` | **Mantido** — nome da frequency ou código aplicado |
| `scheduled_start + scheduled_end TIME` | **Mantido** — arrival window já funciona |

**Novos campos (ADIÇÃO, não substituição):**
- `tax_amount NUMERIC(10,2) DEFAULT 0`
- `adjustment_amount NUMERIC(10,2) DEFAULT 0` — separado de `discount_amount` para transparência semântica (discount = pct-based; adjustment = flat one-off)
- `adjustment_reason VARCHAR(255)`
- `frequency_id UUID REFERENCES cleaning_frequencies(id) ON DELETE SET NULL`
- `location_id UUID REFERENCES cleaning_areas(id) ON DELETE SET NULL` (ver 5.2)
- `price_snapshot JSONB`

### 5.2 `cleaning_areas` JÁ existe — **expandir, não duplicar**

Descartar proposta de criar `cleaning_locations` nova. Em vez disso:

```sql
ALTER TABLE cleaning_areas
    ADD COLUMN is_default BOOLEAN DEFAULT FALSE,
    ADD COLUMN is_archived BOOLEAN DEFAULT FALSE;
```

`cleaning_areas` é usada como **locations** (business units com zip codes). Renomeação cosmética em UI ("Locations") sem mexer em código/schema reduz carry cost. Todas as referências de `location_id` em novas tables apontam para `cleaning_areas.id`.

### 5.3 `cleaning_recurring_schedules.frequency` VARCHAR precisa MIGRAR para FK

Schema atual:
```sql
cleaning_recurring_schedules (
    ...
    frequency VARCHAR(...)  -- "weekly", "biweekly", "monthly", etc.
    ...
)
```

Migration path:
1. Criar `cleaning_frequencies` (catálogo)
2. Seed 4 frequencies default por business: One Time, Weekly, Biweekly, Monthly (com discount_pct configurável)
3. Adicionar `cleaning_recurring_schedules.frequency_id UUID REFERENCES cleaning_frequencies(id)`
4. Backfill `frequency_id` baseado em matching do VARCHAR `frequency`
5. Deprecate (não drop) `frequency` VARCHAR — pode remover em cleanup futuro

### 5.4 Frontend owner modules existentes — **EXTEND, não substituir**

Modules atuais que devem ser **expandidos**, não recriados:
- `services.js` → adicionar campos `tier`, `bedrooms`, `bathrooms`, badge OVERRIDE + revert button
- `bookings.js` → adicionar preview realtime do pricing breakdown durante criação

Modules **novos** (P0):
- `pricing-manager.js` → CRUD formulas + overrides
- `extras-manager.js` → CRUD extras + whitelist per service
- `frequencies-manager.js` → CRUD frequencies com discount_pct
- `taxes-manager.js` → CRUD sales taxes per location com effective_date

**Nota:** todos os novos modules seguem o padrão arquitetural de `services.js` (vanilla JS, API client shared, i18n aware). Zero novo framework.

### 5.5 `cleaning_pricing_rules` legado — comment-only deprecate

Adicionar comentário no schema:
```sql
COMMENT ON TABLE cleaning_pricing_rules IS
'DEPRECATED 2026-04-16 — superseded by cleaning_pricing_formulas + cleaning_service_overrides (ADR-001). No code paths active. Candidate for DROP in future cleanup migration.';
```

Não drop agora — evita risco em migração 3Sisters.

---

## Seção 6 — Impacto nas Acceptance Criteria da Story 1.1

Ajustes em função da Seção 5:

- AC 2 revisado: migration aplica **sobre schema existente** (ALTER TABLE para áreas/bookings/recurring) + **CREATE TABLE apenas** para genuinely novas (formulas, overrides, extras, service_extras, booking_extras, frequencies, sales_taxes)
- AC 4 revisado: UI owner **estende** `services.js` + **cria** 4 modules novos (pricing, extras, frequencies, taxes) em vez de criar tudo do zero
- AC 5 revisado: `bookings.js` **estende** com preview — sem quebrar fluxo atual (backward compatible)
- AC 7 (gate $0.01): **inalterado** — regressão test é agnóstica ao schema

---

**Implementação:**

1. Função Python `calculate_booking_price(business_id, service_id, tier, extras[], frequency_id, adjustment, location_id)` em novo módulo `app/modules/cleaning/services/pricing_engine.py` retorna objeto com breakdown completo (schema da Decisão 2).
2. Schema migration aplicada (11 novas tabelas/colunas conforme Schema Decision acima).
3. Endpoint `POST /api/v1/clean/{slug}/pricing/preview` recebe `{service_id, tier, extras[], frequency_id, adjustment, location_id}` e retorna o objeto breakdown — para preview realtime no UI.
4. UI owner (`services.js` + novo módulo `pricing-manager.js`):
   - Cadastrar/editar `cleaning_pricing_formulas` (base, BR delta, BA delta, tier multipliers)
   - Cadastrar/editar services com `tier + bedrooms + bathrooms` obrigatórios
   - Override price por entry com badge OVERRIDE + revert
   - CRUD `cleaning_extras` + whitelist per service
   - CRUD `cleaning_frequencies` com discount_pct
   - CRUD `cleaning_sales_taxes` per location (com effective_date)
5. UI booking creation (`bookings.js`):
   - Preview realtime do preço conforme owner seleciona tier/extras/frequency/adjustment
   - Mostra breakdown SUB-TOTAL → DISCOUNT → ADJUSTMENT → AMOUNT BEFORE TAX → TAX → FINAL
   - Ao salvar booking, grava `price_snapshot` com decomposição completa
6. `cleaning_booking_extras` criado no momento da confirmação (não na preview).

**Gate de DoD (não-negociável):**

7. **Pricing regression test** em `tests/test_pricing_engine.py`:
   - 10 bookings reais do 3Sisters Launch27 (observados) reproduzidos como fixtures
   - `calculate_booking_price()` deve retornar final_amount com **tolerância ≤ $0.01** em 10/10 casos
   - Teste dos 7 edge cases desta ADR:
     - a. Formula change não mexe em overrides existentes
     - b. Booking snapshot imutável após criação
     - c. Override precedence (override > formula)
     - d. Tier multiplier aplica só em base, não extras
     - e. Tax base = subtotal − discount − adjustment
     - f. Adjustment negativo reduz amount_before_tax
     - g. Zero extras, zero frequency, zero adjustment funciona

**Tests unitários mínimos:** 10 test cases cobrindo os 7 edge cases + 3 happy paths.

**Observability:** log estruturado da cada `calculate_booking_price` chamada (business_id, service_id, inputs, final_amount) — permite auditar disputas.

---

## Consequências

### Positivas

- **Test-gated migration**: ±$0.01 contra Launch27 dá confiança para Ana migrar
- **Preço histórico imutável**: sem risco de recálculo acidental em disputa legal
- **Schema pragmatic**: separado de `cleaning_pricing_rules` legacy — zero risco de quebra
- **UI owner-friendly**: override + revert em 1 click, transparência sobre fórmula
- **Multi-location ready**: `cleaning_locations` as first-class, formula per location opcional
- **Payroll-ready**: `wage_pct` em `cleaning_team_members` desbloqueia Story 1.6

### Negativas / Aceitas

- **Schema complexity +11 tables/columns**: carry cost de manutenção. Mitigado por naming consistente e migration atomic.
- **Override granularity limitada (v1 só price)**: se owner reclamar de duration override, precisa v2. Aceitável — 3Sisters não requer hoje.
- **JSONB `tier_multipliers` em `cleaning_pricing_formulas`**: não-normalizado. Aceitável pela simplicidade operacional (owner edita 3 valores, não 3 rows).
- **`cleaning_pricing_rules` fica inerte**: debt técnico visível. Adicionar comentário `DEPRECATED — replaced by cleaning_pricing_formulas + cleaning_service_overrides` e remover em cleanup futuro.

### Riscos & Mitigações

| Risco | Mitigação |
|-------|-----------|
| Rounding difere de Launch27 em casos específicos | Test gate 10/10 detecta ANTES do cutover |
| Override stale confunde owner | UI badge + tooltip + revert inline |
| Migration backfill de bookings existentes sem `price_snapshot` | Migration B (services + active customers, sem histórico) — bookings Launch27 ficam lá read-only |
| Tier multipliers mudados quebram analytics históricos | Snapshot em `price_snapshot` preserva o cálculo original |

---

## Próximo Passo — Handoff para @pm

@pm (Trinity): usar esta ADR como input para detalhar **Story 1.1 — Pricing Engine Hybrid**.

**Inputs para Story 1.1:**
- Acceptance criteria desta ADR (items 1-7 acima)
- Schema changes listados
- Migration path B confirmed (services + active customers, sem histórico)
- Test gate 10/10 bookings Launch27 vs xcleaners ±$0.01

**Estimate de effort (refinar com @pm):**
- Migration + schema: 1 dia
- Pricing engine Python: 1.5 dias
- Endpoint preview: 0.5 dia
- UI owner (formulas + services + extras + frequencies + taxes): 2 dias
- UI booking preview: 0.5 dia
- Pricing regression tests (10 cases): 1 dia

**Total Story 1.1: ~5-6 dias dev.**

Em paralelo, @data-engineer valida schema e escreve migration file.

---

*ADR-001 closed. Arquitetura definida. Fórmula hibrida + overrides atomics + snapshot imutável + ordem canônica validada contra Launch27. Pronto para coding.*

— Aria, arquitetando o futuro 🏗️
