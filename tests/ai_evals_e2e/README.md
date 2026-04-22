# AI EVAL E2E — real LLM, real DB, real services

Sister suite to `tests/ai_evals/` (which uses tool mocks for fast unit-level
checks). This one runs the **whole pipeline against the real DB**: AI calls
the real `propose_booking_draft` which inserts a real row, and the homeowner
service really mutates it.

## Safety

Every booking row created here is tagged with `special_instructions` starting
`[AI_EVAL_E2E]`. The autouse `cleanup_e2e` fixture in `conftest.py` deletes
those rows **before AND after** every test. Cleanup is idempotent.

The qatest business (`af168a02-...`) is treated as the test playground —
this is a hard project assumption (Luiz, 2026-04-22: "tudo que temos no
sistema é teste, nada é real").

## Run

```bash
export OPENAI_API_KEY=sk-...
export DATABASE_URL="postgresql://...:5432/railway"   # prod URL is fine
pytest tests/ai_evals_e2e/ -v
```

To run a single case:
```bash
pytest tests/ai_evals_e2e/test_e2e_lifecycle.py::test_ai_books_real_slot -v -s
```

## Cases

| # | Test | What it covers |
|---|------|----------------|
| 1 | `test_ai_books_real_slot` | Customer message -> real LLM -> propose_booking_draft -> DB row exists, status=scheduled, team_id assigned, price=$207 (deep tier × 1.8), source=ai_chat |
| 2 | `test_homeowner_reschedules` | Seed booking -> homeowner_service.reschedule_booking -> date/time updated in DB |
| 3 | `test_homeowner_cancels` | Seed booking -> homeowner_service.cancel_booking -> status flips to 'cancelled' |

## Cost

~3 LLM calls + ~10 DB roundtrips per full run (~$0.05, ~30s).

## Backlog

- AI-driven reschedule (currently homeowner_service direct — need a
  reschedule_booking AI tool)
- AI-driven cancel (same)
- Email assertion via Resend webhook log (currently asserted only via DB
  row state; email send is best-effort and logged in WARNING)
- Stripe charge confirmation flow
- Conflict / no-show / late-cancel paths
