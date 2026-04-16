---
type: ux-spec
title: "Story 1.1 — UI Specs (Pricing Engine Hybrid)"
project: xcleaners
story_id: XCL-1.1
author: "@ux-design-expert (Sati)"
date: 2026-04-16
sprint: Fase C · Sessão C3
consumed_by:
  - XCL-1.1 Task 4 (UI extend — services.js + bookings.js)
  - XCL-1.1 Task 5a (pricing-manager + extras-manager)
  - XCL-1.1 Task 5b (frequencies-manager + taxes-manager)
status: final
tags:
  - project/xcleaners
  - ux-spec
  - story/XCL-1.1
  - epic-a
---

# Story 1.1 — UI Specs (Pricing Engine Hybrid)

Specs concretas para @dev (Neo) implementar as Tasks 4 + 5 sem inventar padrões novos. Cada módulo herda do pattern `services.js` (card list + modal form) + tokens `--cc-*`. Zero novos componentes atômicos: reutilizamos `cc-card`, `cc-btn`, `cc-badge`, `cc-modal-backdrop`, `cc-toggle`, `cc-empty-state`, `cc-loading-overlay-spinner`.

## Índice

1. [Princípios e Shared Patterns](#1-princípios-e-shared-patterns)
2. [services.js — EXTEND (tier/BR/BA + OVERRIDE badge)](#2-servicesjs--extend)
3. [bookings.js — EXTEND (preview pane reativo)](#3-bookingsjs--extend)
4. [pricing-manager.js — NEW](#4-pricing-managerjs--new)
5. [extras-manager.js — NEW](#5-extras-managerjs--new)
6. [frequencies-manager.js — NEW](#6-frequencies-managerjs--new)
7. [taxes-manager.js — NEW](#7-taxes-managerjs--new)
8. [Sidebar nav integration](#8-sidebar-nav-integration)
9. [i18n keys completas EN/ES/PT](#9-i18n-keys-completas)
10. [Acceptance checklist](#10-acceptance-checklist-para-dev)

---

## 1. Princípios e Shared Patterns

### 1.1 Stack confirmada (sem novidades)

| Camada | Tech |
|---|---|
| UI framework | Vanilla JS (zero React/Vue/etc.) |
| API client | `CleanAPI.cleanGet / cleanPost / cleanPatch / cleanDelete` (shared) |
| i18n | `window.I18n.t('namespace.key')` via `i18n.js` |
| Tokens CSS | `var(--cc-space-*)`, `var(--cc-primary-500)`, `var(--cc-neutral-700)`, etc. — **nunca hardcode** |
| Illustrations (empty states) | `XcleanersIllustrations.<name>` (reuse) |
| Toast/notificação | `CleanAPI.toast.success(msg)` / `.error(msg)` — shared |
| Loading | `<div class="cc-loading-overlay-spinner"></div>` |

### 1.2 Pattern base (herdado de services.js)

Todo módulo novo segue a **mesma estrutura canônica**:

```
MODULE = {
  _container, _items, _editingId, _categories (opcional)

  async render(container) { load → _renderPage() }
  _renderPage() { header + grid of cards + modal container }
  _renderItemCard(item) { cc-card com actions inline }
  _showCreateModal() { _renderFormModal({}) }
  _showEditModal(id) { find → _renderFormModal(data) }
  _renderFormModal(data) { cc-modal-header + form + cc-modal-footer }
  async _save() { CleanAPI.cleanPost/cleanPatch → toast → reload }
  async _toggleActive/_archive(id) { confirmação → API → reload }
  _closeModal(event) { hide overlay }
  _esc(str) { HTML-escape utility }
}
```

Convenção de nome global: `window.Owner{ModuleName}` (ex.: `window.OwnerPricingManager`). Router `app.js` chama `render(container)`.

### 1.3 Layout grid (consistência)

```css
/* Grid de cards — IDÊNTICO ao services.js */
display: grid;
grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
gap: var(--cc-space-4);
```

### 1.4 Botão OVERRIDE (reutilizado em 3 lugares)

Um único badge visual define "esta entrada quebra o pattern automático":

```html
<span class="cc-badge cc-badge-sm"
      style="background:var(--cc-warning-500)20;color:var(--cc-warning-500);cursor:pointer;"
      title="Formula calculates $X. Custom override: $Y. Reason: {reason}"
      onclick="OwnerXxx._showOverrideRevertModal(id)">
  OVERRIDE
</span>
```

Usado em:
- services.js lista (quando `cleaning_service_overrides` tem row ativa)
- pricing-manager.js (lista de overrides ativos)
- bookings.js preview pane (quando snapshot usou override)

### 1.5 Tokens de status (unificados)

| Status semântico | Token color | Uso |
|---|---|---|
| Default (neutro) | `--cc-neutral-500` | One Time, archived |
| Success (ativo/default) | `--cc-success-500` | is_default=true, is_active=true |
| Warning (attention) | `--cc-warning-500` | OVERRIDE badge, stale formula warning |
| Danger (destructive) | `--cc-danger-500` | Revert, archive, delete actions |
| Info (informativo) | `--cc-info-500` | Recalculate hint, timeline rows |

---

## 2. services.js — EXTEND

### 2.1 Mudanças obrigatórias no form modal

Adicionar 3 campos obrigatórios ANTES de `base_price`:

```
┌─ Add / Edit Service ─────────────────────────────────┐
│                                                      │
│  Name *              [ Standard Cleaning         ]  │
│  Category *          [ Residential             ▼]   │
│  Description         [ ...                       ]  │
│                                                      │
│  ┌─ PRICING MODEL ─────────────────────────────┐    │
│  │ Tier *            ( ) Basic  ( ) Deep  ( ) Premium │
│  │ Bedrooms *        [ 2 ]   (0 = studio)      │    │
│  │ Bathrooms *       [ 1 ]                     │    │
│  │                                             │    │
│  │ Formula price:    $175.00  (read-only)      │    │
│  │ Override price:   [ 200.00 ]  (optional)    │    │
│  │                   × revert to formula       │    │
│  └─────────────────────────────────────────────┘    │
│                                                      │
│  Duration (min) *    [ 120 ]                        │
│  Min team size *     [ 2  ]                         │
│  [ ] Active                                          │
│                                                      │
│              [ Cancel ]  [ Save Changes ]            │
└──────────────────────────────────────────────────────┘
```

**Regras dinâmicas:**
- "Formula price" é read-only, calculado via **endpoint preview** (C2) chamado com debounce de 300ms quando tier/BR/BA mudam: `CleanAPI.cleanPost('/pricing/preview', { service_id: 'preview-only', tier, bedrooms, bathrooms, extras: [], frequency_id: null })`. Durante create, `service_id` não existe ainda — endpoint preview ACEITA payload abstrato sem service_id (ver spec C2).
- "Override price" vazio → usa formula. Preenchido → save grava em `cleaning_service_overrides` (tier-atomic, Decision 3 v1).
- Revert clear button aparece APENAS quando override preenchido.

### 2.2 Card da lista — OVERRIDE badge

```
┌─ Standard Cleaning ──────────────────────[TOGGLE]─┐
│ 🏠 Residential    [OVERRIDE] ← badge warning      │
│                                                    │
│ Deep Clean for 2BR / 1BA houses.                  │
│                                                    │
│ $200  per visit   2.0 hrs   2 cleaners            │
│                                                    │
│ [Edit]  [Checklist]  [Deactivate]                 │
└────────────────────────────────────────────────────┘
```

**OVERRIDE badge** aparece quando o service tem `cleaning_service_overrides.is_active=TRUE` para o tier do service. Hover mostra tooltip `"Formula: $175. Override: $200. Reason: Historical legacy pricing"`. Click abre modal de revert:

```
┌─ Revert Override? ──────────────────────────┐
│                                             │
│  Formula price: $175.00                     │
│  Override:      $200.00                     │
│  Reason:        Historical legacy pricing   │
│                                             │
│  Reverting deletes the override and this    │
│  service will use the formula going forward.│
│                                             │
│  [ Cancel ]   [ ↩ Revert to Formula ]       │
└─────────────────────────────────────────────┘
```

Após revert: `CleanAPI.cleanDelete(/pricing/overrides/{override_id})` → toast → reload list.

### 2.3 Interaction Flow — Service Creation

```
1. Owner clica "+ Add Service"
2. Modal abre com form vazio
3. Owner preenche Name, Category, Description
4. Owner escolhe Tier (radio): "Basic" selecionado
5. Owner digita Bedrooms=2
   → debounce 300ms → chama /pricing/preview(tier=basic, BR=2, BA=0)
   → "Formula price: $155.00" aparece (read-only)
6. Owner digita Bathrooms=1
   → debounce 300ms → recalcula → "Formula price: $170.00"
7. Owner opcionalmente digita Override: "200.00"
   → UI mostra clear button (×)
8. Owner clica Save
   → POST /services {name, tier, bedrooms, bathrooms, ...}
   → Se override preenchido: POST /pricing/overrides {service_id, tier, price_override: 200, reason: ""}
   → Toast success → modal fecha → list reload → OVERRIDE badge visível
```

---

## 3. bookings.js — EXTEND

### 3.1 Preview pane reativo no booking form

Inserir **painel lateral/inferior** no modal de criar/editar booking:

```
┌─ Create Booking ─────────────────────────────────────────────────┐
│                                                                   │
│  Client *     [ Sarah Johnson                                 ▼]  │
│  Service *    [ Standard Cleaning (Basic, 2BR/1BA)           ▼]  │
│  Date *       [ 2026-05-15 ]    Start *  [ 09:00 ]              │
│  Team         [ Team A                                        ▼]  │
│                                                                   │
│  ┌─ EXTRAS ────────────────────────────────────────┐            │
│  │ [x] Stairs                   $30.00  qty [1]    │            │
│  │ [ ] Inside Oven             $25.00  qty [ ]    │            │
│  │ [x] Interior Windows         $40.00  qty [1]    │            │
│  └─────────────────────────────────────────────────┘            │
│                                                                   │
│  Frequency    [ Weekly (−15%)                                ▼]  │
│  Adjustment   [ -29.58 ]     Reason [ Complaint refund       ]  │
│                                                                   │
│ ╔═ PRICING BREAKDOWN (live) ═══════════════════════╗             │
│ ║                                                   ║             │
│ ║  Service (Basic, 2BR/1BA)         $200.00  [OVR] ║ ← badge    │
│ ║  + Stairs                          $30.00         ║             │
│ ║  + Interior Windows                $40.00         ║             │
│ ║  ─────────────────────────────────────────        ║             │
│ ║  SUBTOTAL                         $270.00         ║             │
│ ║                                                   ║             │
│ ║  − Discount (Weekly 15%)         −$40.50          ║             │
│ ║  ± Adjustment                    −$29.58          ║             │
│ ║  ─────────────────────────────────────────        ║             │
│ ║  AMOUNT BEFORE TAX                $199.92         ║             │
│ ║                                                   ║             │
│ ║  + Sales Tax (NYC 4.50%)          $9.00           ║             │
│ ║  ─────────────────────────────────────────        ║             │
│ ║  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓     ║             │
│ ║  ┃ FINAL                       $208.92        ┃     ║             │
│ ║  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛     ║             │
│ ║                                                   ║             │
│ ║  (updating…)  ← spinner 300ms após última edição ║             │
│ ╚═══════════════════════════════════════════════════╝             │
│                                                                   │
│                            [ Cancel ]  [ Confirm Booking ]        │
└───────────────────────────────────────────────────────────────────┘
```

### 3.2 Regras do preview pane

- **Dispara em:** mudança de service, tier (se editável), extras (checkbox ou qty), frequency, adjustment, date (para tax correto F-001), location.
- **Debounce:** 300ms após última mudança antes de chamar endpoint. Visualmente: "(updating…)" aparece junto ao spinner inline.
- **Payload enviado:** `POST /api/v1/clean/{slug}/pricing/preview` com `{ service_id, tier, extras: [{extra_id, qty}], frequency_id, adjustment_amount, adjustment_reason, location_id, scheduled_date }`.
- **Resposta consumida:** `{ breakdown: {...}, formatted: {subtotal, discount, adjustment, amount_before_tax, tax, final} }`. Mostrar valores de `formatted`; se algum faltar, fallback para render com `$--.--`.
- **Erro do endpoint:** mostrar card `cc-card` com `⚠ Could not compute price — {error}. Proceeding will use the service base_price.` + botão retry. Confirm Booking continua habilitado.
- **FINAL destacado:** tipografia `var(--cc-text-2xl)`, bold, cor `var(--cc-primary-500)`, dentro de box com border.

### 3.3 Payload de confirmação

Ao clicar "Confirm Booking":

```javascript
// O preview já tem o breakdown; inclui hash do snapshot como idempotency-key soft
CleanAPI.cleanPost('/bookings', {
  client_id, service_id, scheduled_date, scheduled_start, scheduled_end,
  team_id, tier, bedrooms, bathrooms,
  extras: [{extra_id, qty}],
  frequency_id, adjustment_amount, adjustment_reason, location_id,
  // NOTE: backend re-invoca calculate_booking_price (source of truth);
  // preview só serve pro owner VER. price_snapshot é gravado server-side.
});
```

### 3.4 Interaction Flow — Booking Creation

```
1. Owner abre "+ New Booking"
2. Seleciona Client → preview vazio ("Select service to calculate price")
3. Seleciona Service (Standard, Basic, 2BR/1BA)
   → debounce 300ms → preview renderiza com extras[] vazio → SUBTOTAL + TAX + FINAL
4. Marca extra "Stairs" (qty=1)
   → debounce 300ms → preview atualiza mostrando linha Stairs
5. Marca extra "Interior Windows" (qty=1)
   → debounce 300ms → preview atualiza
6. Seleciona frequency "Weekly (−15%)"
   → debounce 300ms → discount aparece; FINAL recalcula
7. Digita adjustment "-29.58", reason "Complaint refund"
   → debounce 300ms → adjustment line aparece; FINAL recalcula
8. Seleciona date 2026-05-15
   → debounce 300ms → preview recalcula (pode mudar tax se rate history)
9. Clica "Confirm Booking"
   → POST /bookings → toast success → modal fecha
10. List reload mostra novo booking com final_price = FINAL do preview
```

### 3.5 Edit booking — Recalculate explícito

Em editar booking existente:

- Preview pane mostra `price_snapshot` do booking (não re-chama engine).
- Acima do pane aparece hint info:
  ```
  ℹ Snapshot locked at booking creation (2026-05-15 09:00).
     [ ↻ Recalculate pricing ]
  ```
- Click em "Recalculate" abre confirm dialog:
  ```
  ┌─ Recalculate Pricing? ──────────────────────────┐
  │                                                 │
  │  This will overwrite the original price         │
  │  snapshot with current formula + override +     │
  │  extras catalog values.                         │
  │                                                 │
  │  Original final: $208.92                        │
  │  New final:      $212.40  (preview)             │
  │  Difference:     +$3.48                         │
  │                                                 │
  │  This action is logged in audit trail.          │
  │                                                 │
  │  [ Cancel ]   [ ⚠ Recalculate Anyway ]           │
  └─────────────────────────────────────────────────┘
  ```
- Após confirm: `POST /bookings/{id}/recalculate` → toast + reload.

Bookings em status `completed`, `cancelled`, `no_show` **não mostram botão Recalculate** (read-only per AC6.3).

---

## 4. pricing-manager.js — NEW

### 4.1 Propósito

CRUD de `cleaning_pricing_formulas` + visualização de `cleaning_service_overrides` ativos. Owner cria/edita a fórmula global (ou location-specific) e gerencia overrides em um único lugar.

### 4.2 Wireframe

```
┌─ Pricing Formulas ──────────────────────────────────────[+ Add]─┐
│                                                                  │
│ ┌─ Standard (default) ─────────────────────[is_active] [✏]──────┐│
│ │ Business-wide default formula                                ││
│ │                                                              ││
│ │ Base: $115.00   + Bedroom: $20.00   + Bathroom: $15.00       ││
│ │ Tier multipliers: Basic 1.0× · Deep 1.8× · Premium 2.8×      ││
│ │                                                              ││
│ │ Example: 2BR/1BA Basic = (115 + 40 + 15) × 1.0 = $170.00     ││
│ │                                                              ││
│ │ Last updated: 2026-04-10                                     ││
│ │ ⚠ 3 overrides created BEFORE last update — may be stale      ││
│ │    [ Review Stale Overrides ]                                ││
│ └──────────────────────────────────────────────────────────────┘│
│                                                                  │
│ ┌─ NYC Premium Formula (location) ────────[is_active] [✏]──────┐│
│ │ Location: New York City                                      ││
│ │ Base: $200.00   + BR: $30.00   + BA: $20.00                  ││
│ │ Tiers: Basic 1.0 · Deep 2.0 · Premium 3.0                    ││
│ │ ...                                                          ││
│ └──────────────────────────────────────────────────────────────┘│
│                                                                  │
│ ═══════════════════════════════════════════════════════════════ │
│                                                                  │
│ ACTIVE OVERRIDES (3)                                             │
│                                                                  │
│ ┌─ Standard Cleaning (Basic) ─── $200 ──[Revert]──────────────┐ │
│ │ Formula: $170 → Override: $200 (+$30)                       │ │
│ │ Reason: Historical legacy pricing (Ana 2026-04-10)          │ │
│ │ ⚠ Formula updated 2026-04-10 — this override was not reviewed│ │
│ └──────────────────────────────────────────────────────────────┘ │
│                                                                  │
│ ┌─ Move-Out Deep (Premium) ──── $550 ──[Revert]───────────────┐ │
│ │ Formula: $518 → Override: $550 (+$32)                       │ │
│ │ Reason: Packaging premium                                    │ │
│ └──────────────────────────────────────────────────────────────┘ │
│                                                                  │
│ ...                                                              │
└──────────────────────────────────────────────────────────────────┘
```

### 4.3 Form modal (formula create/edit)

```
┌─ Add / Edit Formula ────────────────────────────────┐
│                                                     │
│  Name *             [ NYC Premium Formula       ]   │
│  Scope              ( ) Business-wide default       │
│                     (•) Location-specific           │
│  Location           [ New York City             ▼]  │
│                                                     │
│  ┌─ FORMULA COMPONENTS ─────────────────────┐      │
│  │ Base amount *       $ [ 200.00 ]          │      │
│  │ Bedroom delta *     $ [  30.00 ] per BR  │      │
│  │ Bathroom delta *    $ [  20.00 ] per BA  │      │
│  │                                           │      │
│  │ Tier multipliers (applied to base+BR+BA): │      │
│  │   Basic *           × [ 1.0 ]             │      │
│  │   Deep *            × [ 2.0 ]             │      │
│  │   Premium *         × [ 3.0 ]             │      │
│  └───────────────────────────────────────────┘      │
│                                                     │
│  [✓] Active (inactive = fallback to default)        │
│                                                     │
│  ┌─ LIVE PREVIEW ───────────────────────────┐      │
│  │ 2BR/1BA Basic:    (200 + 60 + 20)×1 = $280│      │
│  │ 2BR/1BA Deep:     (200 + 60 + 20)×2 = $560│      │
│  │ 2BR/1BA Premium:  (200 + 60 + 20)×3 = $840│      │
│  └───────────────────────────────────────────┘      │
│                                                     │
│  ⚠ Warning: Existing overrides created before this  │
│    update will remain unchanged. Review them        │
│    individually in the overrides list.              │
│                                                     │
│            [ Cancel ]  [ Save Formula ]             │
└─────────────────────────────────────────────────────┘
```

### 4.4 Stale overrides warning

Para cada formula card, se `MAX(overrides.created_at WHERE service.business_id=biz) < formula.updated_at`, mostrar:

```
⚠ 3 overrides created BEFORE last update — may be stale
   [ Review Stale Overrides ]
```

Click abre modal listando os overrides com comparação `override_price vs formula_price_now` e botão "Revert" individual ou "Revert all stale".

### 4.5 API endpoints consumidos

| Ação | Endpoint |
|---|---|
| List formulas | `GET /api/v1/clean/{slug}/pricing/formulas` |
| Create | `POST /api/v1/clean/{slug}/pricing/formulas` |
| Update | `PATCH /api/v1/clean/{slug}/pricing/formulas/{id}` |
| Deactivate | `PATCH /api/v1/clean/{slug}/pricing/formulas/{id}` com `{is_active: false}` |
| List overrides | `GET /api/v1/clean/{slug}/pricing/overrides?is_active=true` |
| Revert override | `DELETE /api/v1/clean/{slug}/pricing/overrides/{id}` |
| Live preview (in form) | `POST /api/v1/clean/{slug}/pricing/preview` (reuse C2 endpoint) |

> **Nota @dev:** endpoints `/pricing/formulas` e `/pricing/overrides` ainda NÃO existem em C2. Esta spec assume Task 3 expandida OU esses endpoints criados em sessão futura. **Mínimo para C5a**: implementar ao menos GET e POST das formulas e GET/DELETE dos overrides.

### 4.6 Interaction Flow — Stale Override Review

```
1. Owner abre pricing-manager
2. Vê card "Standard formula" com "⚠ 3 overrides ... stale"
3. Clica "Review Stale Overrides"
4. Modal abre com tabela:
   | Service       | Tier | Override | Formula now | Diff  | Action |
   | Std Cleaning  | basic| $200     | $170        | +$30  | [Keep][Revert]|
   | Deep XL       |deep  | $500     | $540        | -$40  | [Keep][Revert]|
   | ...
5. Owner clica Revert em 1 linha → DELETE override → linha some → toast
6. Ou clica "Revert all" → confirm → DELETE em batch
7. Modal fecha → pricing-manager recarrega sem o warning
```

---

## 5. extras-manager.js — NEW

### 5.1 Propósito

CRUD de `cleaning_extras` (catálogo) + whitelist por service (`cleaning_service_extras`). Owner define "quais extras são permitidos em quais services" — usado no booking preview para filtrar o que aparece.

### 5.2 Wireframe (aba dupla)

```
┌─ Extras ─────────────────[Tab: Catalog | Whitelist]──[+ Add]──┐
│                                                                │
│  TAB ATIVA: CATALOG                                            │
│                                                                │
│  ┌─ Stairs ─────────────────────── $30.00 ──[active]───[✏]──┐ │
│  │ Order: 1                                                 │ │
│  │ Allowed in 8 services                                    │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  ┌─ Inside Oven ─────────────────── $25.00 ──[active]──[✏]──┐ │
│  │ Order: 2                                                 │ │
│  │ Allowed in 12 services                                   │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  ┌─ Interior Windows ─────────────── $40.00 ──[active]─[✏]──┐ │
│  │ Order: 3                                                 │ │
│  │ Allowed in 5 services                                    │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  ...                                                           │
└────────────────────────────────────────────────────────────────┘

TAB 2: WHITELIST (per service):

┌─ Service Extras Whitelist ─────────────────────────────────────┐
│                                                                 │
│  Service [ Standard Cleaning (Basic, 2BR/1BA)              ▼] │
│                                                                 │
│  Allowed extras (5 / 12 in catalog):                           │
│                                                                 │
│  [✓] Stairs              $30.00                                │
│  [✓] Inside Oven         $25.00                                │
│  [✓] Interior Windows    $40.00                                │
│  [ ] Inside Cabinets     $35.00                                │
│  [ ] Inside Fridge       $30.00                                │
│  [✓] Laundry Wash/Fold   $20.00                                │
│  [✓] Wall Cleaning       $45.00                                │
│  [ ] Move-out Packaging  $150.00                               │
│  ...                                                            │
│                                                                 │
│               [ Cancel ]  [ Save Whitelist ]                   │
└─────────────────────────────────────────────────────────────────┘
```

### 5.3 Form modal (extra create/edit)

```
┌─ Add / Edit Extra ───────────────────────┐
│                                          │
│  Name *         [ Stairs             ]   │
│  Price *        $ [ 30.00 ]              │
│  Sort order     [ 1 ]                    │
│  [✓] Active                              │
│                                          │
│         [ Cancel ]  [ Save ]             │
└──────────────────────────────────────────┘
```

### 5.4 API endpoints

| Ação | Endpoint |
|---|---|
| List extras | `GET /api/v1/clean/{slug}/pricing/extras?include_inactive=true` |
| Create | `POST /api/v1/clean/{slug}/pricing/extras` |
| Update | `PATCH /api/v1/clean/{slug}/pricing/extras/{id}` |
| Archive | `PATCH /api/v1/clean/{slug}/pricing/extras/{id}` com `{is_active: false}` |
| List whitelist (per service) | `GET /api/v1/clean/{slug}/services/{service_id}/extras` |
| Update whitelist | `PUT /api/v1/clean/{slug}/services/{service_id}/extras` com `{extra_ids: [uuid, uuid]}` |

### 5.5 Interaction Flow — Whitelist Update

```
1. Owner vai em extras-manager → Tab "Whitelist"
2. Seleciona service "Standard Cleaning"
3. GET /services/{id}/extras → checkboxes pre-marked com extras atuais
4. Owner desmarca "Inside Cabinets", marca "Wall Cleaning"
5. Clica Save
6. PUT /services/{id}/extras com novo array de IDs
7. Toast success → "Este service permite 6 extras" atualiza
```

---

## 6. frequencies-manager.js — NEW

### 6.1 Propósito

CRUD de `cleaning_frequencies`. Owner define os ritmos recorrentes que o business oferece (One Time, Weekly, Biweekly, Monthly, Custom...) e o discount % associado. Apenas **1 frequency** pode ser `is_default=TRUE` por business (regra UI enforced antes do backend).

### 6.2 Wireframe

```
┌─ Frequencies ────────────────────────────────────[+ Add]───────┐
│                                                                 │
│  ┌─ One Time ─────────────────── 0% discount ──[default]──[✏]─┐ │
│  │ Interval: —                                               │ │
│  │ Used in 45 active schedules                                │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌─ Weekly ─────────────────────15% discount ─────────────[✏]─┐ │
│  │ Interval: 1 week                                           │ │
│  │ Used in 12 active schedules                                │ │
│  │                                    [ Set as Default ]      │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌─ Biweekly ───────────────────10% discount ────────────[✏]──┐ │
│  │ Interval: 2 weeks                                          │ │
│  │ Used in 8 active schedules                                 │ │
│  │                                    [ Set as Default ]      │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌─ Monthly ────────────────────5% discount ─────────────[✏]──┐ │
│  │ Interval: 4 weeks                                          │ │
│  │ Used in 3 active schedules                                 │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ═══════════════════════════════════════════════════════════  │
│  ARCHIVED (2) [ Show ]                                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 6.3 Form modal

```
┌─ Add / Edit Frequency ──────────────────────┐
│                                             │
│  Name *              [ Weekly            ]  │
│  Interval (weeks)    [ 1 ]  (blank = once)  │
│  Discount %          [ 15.00 ]              │
│  [ ] Set as default                         │
│                                             │
│            [ Cancel ]  [ Save ]             │
└─────────────────────────────────────────────┘
```

### 6.4 Regras especiais

- **Default validation (UI-side):** se owner marca "Set as default" em um frequency X, aviso: `"This will unmark 'Weekly' as default. Continue?"` — depois UI dispara 2 calls: unset antigo + set novo.
- **Archive em vez de delete:** DELETE em frequency que tem `usage_count > 0` é bloqueado; UI oferece só "Archive" → sets `is_archived=TRUE`, row permanece para snapshots de bookings históricos.
- **Default não-archivável:** botão Archive disabled em frequency com `is_default=TRUE` (tooltip: "Set another frequency as default first").

### 6.5 API endpoints

| Ação | Endpoint |
|---|---|
| List frequencies | `GET /api/v1/clean/{slug}/pricing/frequencies?include_archived=false` |
| Create | `POST /api/v1/clean/{slug}/pricing/frequencies` |
| Update | `PATCH /api/v1/clean/{slug}/pricing/frequencies/{id}` |
| Archive | `PATCH .../{id}` com `{is_archived: true}` |
| Set default (atomic) | `POST /api/v1/clean/{slug}/pricing/frequencies/{id}/set-default` (unset antigo + set novo numa transação) |

### 6.6 Usage count

Cada card mostra `"Used in N active schedules"` — contagem de `cleaning_client_schedules WHERE frequency_id = freq.id AND status = 'active'`. Backend deve retornar esse count no list (JOIN ou subquery).

---

## 7. taxes-manager.js — NEW

### 7.1 Propósito

CRUD de `cleaning_sales_taxes` — tax rate por location com efeito temporal. Mudar tax não UPDATE: cria nova row com novo `effective_date`. Rows antigas preservadas para bookings históricos (F-001).

### 7.2 Wireframe

```
┌─ Sales Taxes ─────────────────────────────────[+ Add Rate]─────┐
│                                                                 │
│  Location  [ New York City                                  ▼] │
│                                                                 │
│  RATE HISTORY (newest first)                                    │
│                                                                 │
│  ┌─ 4.50% ──── effective 2025-09-01 ──── current ──────[archive]┐│
│  │ Added by Ana · 2025-08-20                                    ││
│  │ Used in 89 bookings                                          ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─ 4.25% ──── effective 2024-01-01 ── 2025-08-31 ─────────────┐│
│  │ Added by Ana · 2023-12-15                                    ││
│  │ Used in 234 bookings                                         ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─ 4.00% ──── effective 2022-01-01 ── 2023-12-31 ─────────────┐│
│  │ Added by Mario · 2021-11-30                                  ││
│  │ Used in 156 bookings                                         ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ═══════════════════════════════════════════════════════════   │
│                                                                  │
│  LOCATIONS WITHOUT TAX CONFIG (1)                                │
│  ┌─ Dallas ───────────────────[ Add First Rate ]──────────────┐│
│  │ No sales tax configured. Bookings here default to tax=0%.  ││
│  └────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────┘
```

### 7.3 Form modal (add new rate)

```
┌─ Add Sales Tax Rate ──────────────────────────┐
│                                               │
│  Location *          [ New York City      ▼]  │
│  Tax rate *          [ 4.50 ] %               │
│  Effective date *    [ 2025-09-01 ]           │
│                                               │
│  ⚠ Changing tax rate CREATES A NEW ROW with   │
│    this effective date. Previous rates stay   │
│    for bookings scheduled before this date.   │
│                                               │
│  If there is already a rate with effective    │
│  date >= this one, saving will FAIL. Archive  │
│  the later row first if you want to supersede.│
│                                               │
│            [ Cancel ]  [ Save ]               │
└───────────────────────────────────────────────┘
```

### 7.4 Regras especiais

- **Immutable after bookings:** tax row com `usage_count > 0` não pode editar `tax_pct` nem `effective_date`. Apenas archive. Tooltip explica why.
- **Chronological enforcement:** no Save, backend valida que não existe row com `effective_date >= new_date` NOT archived. Se existir, retorna 409 + UI mostra erro.
- **Current indicator:** row com maior `effective_date <= CURRENT_DATE` AND NOT archived recebe badge `"current"`.
- **Effective ranges:** UI calcula e exibe `effective 2025-09-01 ─── current` ou `effective 2024-01-01 ─── 2025-08-31` (a partir do próximo effective_date − 1 dia).

### 7.5 API endpoints

| Ação | Endpoint |
|---|---|
| List locations | `GET /api/v1/clean/{slug}/locations` |
| List rates (per location) | `GET /api/v1/clean/{slug}/pricing/taxes?location_id={id}&include_archived=false` |
| Create rate | `POST /api/v1/clean/{slug}/pricing/taxes` |
| Archive rate | `PATCH /api/v1/clean/{slug}/pricing/taxes/{id}` com `{is_archived: true}` |
| Edit (meta only, se 0 usos) | `PATCH .../{id}` com `{tax_pct, effective_date}` |

---

## 8. Sidebar nav integration

### 8.1 Nova seção no sidebar (app.js)

Agrupar os 4 novos módulos sob label "Pricing":

```
Sidebar (existing)
├── Dashboard
├── Schedule
├── Clients
├── Services
├── Teams
├── Invoices
├── Messages
│
├── ─── PRICING ────       ← novo group label
│   ├── Formulas          → #/owner/pricing     (pricing-manager)
│   ├── Extras            → #/owner/extras      (extras-manager)
│   ├── Frequencies       → #/owner/frequencies (frequencies-manager)
│   └── Taxes             → #/owner/taxes       (taxes-manager)
│
├── Settings
└── Logout
```

### 8.2 Router registration

```javascript
// app.js router (novo)
'#/owner/pricing':     () => OwnerPricingManager.render(mountPoint),
'#/owner/extras':      () => OwnerExtrasManager.render(mountPoint),
'#/owner/frequencies': () => OwnerFrequenciesManager.render(mountPoint),
'#/owner/taxes':       () => OwnerTaxesManager.render(mountPoint),
```

### 8.3 Mobile behavior

Em viewport < 768px, o group "Pricing" vira um único item expansível (acordeão) para economizar altura. Clicar "Pricing" no mobile revela os 4 sub-items com indent. Padrão idêntico ao atual do sidebar (herda `cc-sidebar-group-collapsible`).

---

## 9. i18n keys completas

Adicionar em `frontend/cleaning/static/i18n/{en,es,pt}.json`:

### 9.1 Namespace `pricing` (compartilhado por todos os 4 módulos + extends)

```json
{
  "pricing": {
    "formulas": {
      "title": "Pricing Formulas",
      "add": "Add Formula",
      "edit": "Edit Formula",
      "name": "Name",
      "scope": "Scope",
      "scope_default": "Business-wide default",
      "scope_location": "Location-specific",
      "location": "Location",
      "base_amount": "Base amount",
      "bedroom_delta": "Bedroom delta",
      "bedroom_delta_hint": "per bedroom",
      "bathroom_delta": "Bathroom delta",
      "bathroom_delta_hint": "per bathroom",
      "tier_multipliers": "Tier multipliers",
      "multiplier_hint": "applied to base+BR+BA",
      "tier_basic": "Basic",
      "tier_deep": "Deep",
      "tier_premium": "Premium",
      "active": "Active (inactive = fallback to default)",
      "live_preview": "Live preview",
      "preview_example": "{br}BR/{ba}BA {tier}",
      "stale_warning": "Existing overrides before this update may be stale",
      "stale_count": "{count} overrides created BEFORE last update — may be stale",
      "review_stale": "Review Stale Overrides",
      "saved": "Formula saved",
      "example_calc": "Example: {br}BR/{ba}BA {tier} = ({base} + {br_val} + {ba_val}) × {mult} = {result}",
      "last_updated": "Last updated"
    },
    "overrides": {
      "title": "Active Overrides",
      "badge": "OVERRIDE",
      "badge_tooltip": "Formula calculates {formula}. Custom override: {override}. Reason: {reason}",
      "stale_formula_warning": "Formula updated {date} — this override was not reviewed",
      "revert_title": "Revert Override?",
      "revert_description": "Reverting deletes the override and this service will use the formula going forward.",
      "revert_action": "↩ Revert to Formula",
      "revert_all": "Revert All Stale",
      "keep": "Keep",
      "reverted": "Override reverted",
      "formula_price": "Formula price",
      "override_price": "Override price",
      "diff": "Difference",
      "reason_placeholder": "Why this override? (audit trail)"
    },
    "extras": {
      "title": "Extras",
      "tab_catalog": "Catalog",
      "tab_whitelist": "Whitelist",
      "add": "Add Extra",
      "edit": "Edit Extra",
      "name": "Name",
      "price": "Price",
      "sort_order": "Sort order",
      "active": "Active",
      "allowed_in": "Allowed in {count} services",
      "whitelist_title": "Service Extras Whitelist",
      "whitelist_hint": "Allowed extras ({selected} / {total} in catalog):",
      "select_service": "Select service",
      "whitelist_saved": "Whitelist updated",
      "allowed_n": "This service allows {count} extras"
    },
    "frequencies": {
      "title": "Frequencies",
      "add": "Add Frequency",
      "edit": "Edit Frequency",
      "name": "Name",
      "interval_weeks": "Interval (weeks)",
      "interval_hint": "blank = once (no recurrence)",
      "discount_pct": "Discount %",
      "set_default": "Set as default",
      "default_badge": "default",
      "used_in_schedules": "Used in {count} active schedules",
      "archived_section": "Archived",
      "show_archived": "Show",
      "default_warning": "This will unmark '{prev}' as default. Continue?",
      "default_required": "Set another frequency as default first",
      "archive_blocked_usage": "Cannot delete — used in {count} schedules. Archive instead.",
      "archived": "Frequency archived"
    },
    "taxes": {
      "title": "Sales Taxes",
      "add": "Add Rate",
      "location": "Location",
      "rate_history": "Rate History (newest first)",
      "tax_pct": "Tax rate",
      "effective_date": "Effective date",
      "current_badge": "current",
      "used_in_bookings": "Used in {count} bookings",
      "added_by": "Added by {user} · {date}",
      "no_config_title": "Locations without tax config",
      "no_config_hint": "No sales tax configured. Bookings here default to tax=0%.",
      "add_first_rate": "Add First Rate",
      "immutable_warning": "New rate CREATES A NEW ROW. Previous rates stay for bookings scheduled before this date.",
      "chronology_error": "A later rate exists. Archive it first to supersede.",
      "edit_blocked": "Cannot edit — row is referenced by {count} bookings. Archive and add new rate instead.",
      "archived": "Rate archived"
    },
    "preview": {
      "title": "Pricing Breakdown (live)",
      "updating": "updating…",
      "subtotal": "SUBTOTAL",
      "discount": "Discount",
      "adjustment": "Adjustment",
      "adjustment_reason": "Reason",
      "amount_before_tax": "AMOUNT BEFORE TAX",
      "tax": "Sales Tax",
      "final": "FINAL",
      "recalculate_hint": "Snapshot locked at booking creation ({date}).",
      "recalculate_button": "↻ Recalculate pricing",
      "recalculate_title": "Recalculate Pricing?",
      "recalculate_description": "This will overwrite the original price snapshot with current formula + override + extras catalog values.",
      "recalculate_original": "Original final",
      "recalculate_new": "New final",
      "recalculate_diff": "Difference",
      "recalculate_audit_note": "This action is logged in audit trail.",
      "recalculate_confirm": "⚠ Recalculate Anyway",
      "no_service_hint": "Select service to calculate price",
      "error_fallback": "Could not compute price — {error}. Proceeding will use the service base_price."
    },
    "service_extend": {
      "tier": "Tier",
      "bedrooms": "Bedrooms",
      "bedrooms_hint": "0 = studio",
      "bathrooms": "Bathrooms",
      "formula_price": "Formula price",
      "override_price": "Override price",
      "override_hint": "optional",
      "revert_inline": "revert to formula"
    },
    "sidebar_group": "Pricing",
    "nav_formulas": "Formulas",
    "nav_extras": "Extras",
    "nav_frequencies": "Frequencies",
    "nav_taxes": "Taxes"
  }
}
```

### 9.2 Tradução ES (tom: profissional latino-americano)

Principais substituições (exemplos chave — @dev completa o resto seguindo os mesmos valores de `en`):

```json
{
  "pricing": {
    "formulas": {
      "title": "Fórmulas de Precio",
      "add": "Añadir Fórmula",
      "tier_basic": "Básico",
      "tier_deep": "Profundo",
      "tier_premium": "Premium",
      "base_amount": "Monto base",
      "bedroom_delta": "Adicional por habitación",
      "bathroom_delta": "Adicional por baño",
      "active": "Activa (inactiva = usa la predeterminada)"
    },
    "overrides": {
      "badge": "OVERRIDE",
      "revert_title": "¿Revertir Override?",
      "revert_action": "↩ Revertir a la Fórmula"
    },
    "extras": {
      "title": "Extras",
      "tab_catalog": "Catálogo",
      "tab_whitelist": "Autorizados"
    },
    "frequencies": {
      "title": "Frecuencias",
      "default_badge": "predeterminada"
    },
    "taxes": {
      "title": "Impuestos sobre Ventas",
      "current_badge": "vigente"
    },
    "preview": {
      "title": "Desglose de Precio (en vivo)",
      "subtotal": "SUBTOTAL",
      "final": "TOTAL"
    },
    "sidebar_group": "Precios"
  }
}
```

### 9.3 Tradução PT (tom: português brasileiro, formal)

```json
{
  "pricing": {
    "formulas": {
      "title": "Fórmulas de Preço",
      "add": "Adicionar Fórmula",
      "tier_basic": "Básica",
      "tier_deep": "Profunda",
      "tier_premium": "Premium",
      "base_amount": "Valor base",
      "bedroom_delta": "Adicional por quarto",
      "bathroom_delta": "Adicional por banheiro",
      "active": "Ativa (inativa = usa a padrão)"
    },
    "overrides": {
      "badge": "OVERRIDE",
      "revert_title": "Reverter Override?",
      "revert_action": "↩ Reverter para Fórmula"
    },
    "extras": {
      "title": "Extras",
      "tab_catalog": "Catálogo",
      "tab_whitelist": "Permitidos"
    },
    "frequencies": {
      "title": "Frequências",
      "default_badge": "padrão"
    },
    "taxes": {
      "title": "Impostos sobre Vendas",
      "current_badge": "atual"
    },
    "preview": {
      "title": "Detalhamento do Preço (ao vivo)",
      "subtotal": "SUBTOTAL",
      "final": "TOTAL"
    },
    "sidebar_group": "Preços"
  }
}
```

> **@dev:** completar ES/PT seguindo a lista completa do EN. Se dúvida em termo técnico, marcar `// TODO(i18n)` e preservar EN até revisão.

### 9.4 Convenção de uso em JS

```javascript
const t = window.I18n.t.bind(window.I18n);

// Simples:
t('pricing.formulas.title');  // "Pricing Formulas"

// Com interpolação (se I18n support):
t('pricing.overrides.stale_count', { count: 3 });  // "3 overrides..."

// Fallback manual se I18n não suportar interpolation ainda:
t('pricing.overrides.stale_count').replace('{count}', 3);
```

---

## 10. Acceptance checklist (para @dev)

### Para Task 4 (services.js + bookings.js extend)

- [ ] services.js form modal: radio tier + inputs BR/BA obrigatórios
- [ ] services.js form modal: Formula price read-only chamando `/pricing/preview` com debounce 300ms
- [ ] services.js form modal: Override price optional + clear button
- [ ] services.js card list: badge OVERRIDE warning-colored quando override ativo
- [ ] services.js: modal de revert funcional (DELETE override + reload)
- [ ] bookings.js: preview pane dentro do modal de create/edit booking
- [ ] bookings.js: debounce 300ms em service/extras/frequency/adjustment/date changes
- [ ] bookings.js: breakdown cards empilhados render subtotal → discount → adjustment → before tax → tax → FINAL
- [ ] bookings.js: FINAL destacado com token typography 2xl + border
- [ ] bookings.js: hint "Snapshot locked" + botão Recalculate em bookings editados
- [ ] bookings.js: Recalculate confirm modal com diff old vs new + audit note
- [ ] bookings.js: read-only em bookings completed/cancelled/no_show
- [ ] i18n keys `pricing.service_extend.*` + `pricing.preview.*` em EN/ES/PT
- [ ] Zero valores hardcoded — todos via tokens `--cc-*`

### Para Task 5a (pricing-manager + extras-manager)

- [ ] pricing-manager.js: list formulas com card + business-wide + location-specific
- [ ] pricing-manager.js: form modal com base/BR/BA/tiers + live preview local
- [ ] pricing-manager.js: active overrides section com revert individual e batch
- [ ] pricing-manager.js: stale overrides warning em formula card
- [ ] extras-manager.js: tab Catalog com CRUD + allowed_in count
- [ ] extras-manager.js: tab Whitelist com service selector + multi-check save
- [ ] i18n keys `pricing.formulas.*` `pricing.overrides.*` `pricing.extras.*` em EN/ES/PT
- [ ] Sidebar nav: group "Pricing" com 4 entries adicionado no app.js
- [ ] Routes `#/owner/pricing` e `#/owner/extras` registradas
- [ ] Mobile: group colapsável em < 768px

### Para Task 5b (frequencies-manager + taxes-manager)

- [ ] frequencies-manager.js: CRUD com discount_pct + interval_weeks
- [ ] frequencies-manager.js: "Set as default" atomic (unset prev + set new)
- [ ] frequencies-manager.js: archive bloqueado se usage_count > 0 em default
- [ ] frequencies-manager.js: archived section collapsible
- [ ] taxes-manager.js: location selector + rate history cronológica
- [ ] taxes-manager.js: "current" badge no rate ativo (maior effective_date <= CURRENT_DATE)
- [ ] taxes-manager.js: form com chronology validation + immutable warning
- [ ] taxes-manager.js: "Locations without tax config" section
- [ ] taxes-manager.js: edit bloqueado se usage_count > 0 (só archive)
- [ ] i18n keys `pricing.frequencies.*` `pricing.taxes.*` em EN/ES/PT
- [ ] Routes `#/owner/frequencies` e `#/owner/taxes` registradas

### Qualidade transversal

- [ ] Todos os modules seguem convenção `window.Owner{ModuleName}`
- [ ] Todos os renders usam grid `auto-fill, minmax(320px, 1fr)` (consistência com services.js)
- [ ] Empty states com illustration via `XcleanersIllustrations` (reuse)
- [ ] Loading states com `cc-loading-overlay-spinner`
- [ ] Error states com retry button + error description
- [ ] Toast notifications via `CleanAPI.toast.success/error`
- [ ] ARIA labels em botões sem texto (revert, archive, set-default)
- [ ] Focus trap em modals
- [ ] Keyboard: Esc fecha modal; Enter em input submete form
- [ ] `_esc()` utility aplicada em TODO user-generated content renderizado

---

## 11. Non-goals desta spec

- **Backend endpoints não implementados** listados em cada módulo — @dev cria endpoints que ainda não existem (em C2 ou sessão específica) OU mock temporário.
- **Storybook / component docs separados** — documentação live fica nos próprios módulos via `*document` futuro.
- **Testes E2E** — responsabilidade de @qa em C6.
- **Design tokens novos** — zero novos tokens; tudo reusa o existente.

---

## Change log

| Data | Versão | Mudança | Autor |
|------|--------|---------|-------|
| 2026-04-16 | 1.0 | Specs iniciais derivadas de Story 1.1 AC4/AC5 + validação de pattern services.js/cleaning-api.js/i18n | @ux-design-expert (Sati) |

---

*"Cada componente é um amanhecer: pequeno, previsível, consistente — e quando os quatro se somam, o owner tem controle real do sistema."*

— Sati, desenhando a luz antes de Neo erguer as paredes 🎨
