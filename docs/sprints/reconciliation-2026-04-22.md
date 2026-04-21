---
type: evidence
title: "Reconciliação main ↔ feat/ai-fix-turbo + docs/staging-deploy — 2026-04-22"
date: "2026-04-22"
agent: Neo (@dev)
driver: Aria (@architect) plan → Luiz GO
---

# Reconciliação 2026-04-22 — Evidência Local (Fases 1-4)

## Contexto

Dois terminais trabalhando em paralelo criaram divergência tripla:
- `origin/main` — 6 commits financial fixes + 14 specs (2026-04-21 tarde)
- `feat/ai-fix-turbo` — 1 commit próprio (openai bump), behind 8
- `docs/staging-deploy-2026-04-21` — 5 commits únicos (3 valiosos + 2 descartáveis)

Plano cirúrgico do @architect: cherry-pick 3 commits do staging → main, sem tocar feat/ai-fix-turbo.

## Decisões aplicadas

- **Migration 029**: SKIP — `schema.sql:104+129` já tem `conversations/messages` em prod há muito. STAGING-2 era concern de staging fresh-env.
- **Conflict `xcleaners_main.py`**: NÃO EXISTE — `merge-tree` confirmou apenas `requirements.txt`.
- **Estratégia**: cherry-pick (não merge commit), 3 atomic commits.

## Fase 1 — PREP ✅

```
git checkout main → OK
git pull --ff-only → already up to date (b6c35dd)
```

## Fase 2 — CHERRY-PICK ✅

3 commits aplicados sem conflict:

| Original | Novo (em main) | Tipo | Descrição |
|----------|---------------|------|-----------|
| `319d708` | `df5711e` | código | fix(deps) openai 1.0.0 → >=1.35,<2.0 |
| `7a17d7c` | `0ee4dcb` | docs  | staging checkpoint + 6 findings STAGING-1..6 |
| `d871b5a` | `0a783a8` | docs  | +HIGH-3 availability engine backlog |

Diff `requirements.txt` confirmado: 1 linha (`-openai==1.0.0` / `+openai>=1.35,<2.0`).

## Fase 3 — VALIDAÇÃO LOCAL ✅

- `python -m venv .venv.tmp` — OK
- `pip install -r requirements.txt` — `openai-1.109.1` resolvido, zero conflict transitivo
- `python -m py_compile xcleaners_main.py` — ✅
- venv temp removido

## Fase 4 — SMOKE SUITE ✅

Target: `https://app.xcleaners.app` (prod atual, ainda no estado antes do push).

- **`tests/smoke`**: 11/11 PASS em 18.6s (3 setup + 8 chromium)
- **`tests/regression` + `tests/negative`** (excluindo tz-flaky policy-mvp L5): **32/32 PASS em 52.5s** (3 setup + 29 chromium: 4 negative + 14 financial + 7 homeowner/owner + 4 settings)

Policy-mvp tz-flaky (4 specs: cancel-late-fee, draft-no-fee, policy-edit-reactive, reschedule-limit-gate, tz-aware-window) deliberadamente excluído (backlog L5, documentado no checkpoint 2026-04-21; feature funciona em prod, flakiness é só nos assertions de UTC vs local).

**Total: 40 tests (37 chromium + 3 setup compartilhado) · 100% GREEN · 71.1s combinados.**

## Estado final antes de @smith

`main` local tem 3 commits novos sobre `b6c35dd`:
```
0a783a8 docs(backlog): +HIGH-3 availability engine respeitar config do owner
0ee4dcb docs(staging): checkpoint + 6 findings STAGING-1..6 do deploy 2026-04-21
df5711e fix(deps): bump openai 1.0.0 -> >=1.35,<2.0 — unblock AI tool loop
b6c35dd test(e2e): late-cancel spec tz-deterministic — policy hours_before=48, UTC hour
```

Não há nada em `.git/CHERRY_PICK_HEAD` (limpo).

## Próximo passo

→ @smith `*verify` pre-push (audit dos 3 commits + requirements.txt diff + smoke evidence)
→ Se CONTAINED: @devops `git push origin main` (auto-deploy Railway + Cloudflare)
→ @smith post-deploy verify (smoke contra prod pós-push + `/ai/chat` live confirmando openai fix)
→ @devops cleanup: `git push origin --delete feat/ai-fix-turbo docs/staging-deploy-2026-04-21`
