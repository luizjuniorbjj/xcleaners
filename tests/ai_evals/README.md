# AI EVAL Suite — Scheduling Assistant

Mede o comportamento do prompt + tool dispatch da AI WhatsApp/chat de scheduling.

## Como rodar

```bash
# Pré-requisito: OPENAI_API_KEY no ambiente (cada case dispara 1 chamada real ao GPT)
export OPENAI_API_KEY=sk-...

# Todos os cases
pytest tests/ai_evals/ -v

# Filtrar por categoria
pytest tests/ai_evals/ -v -k pricing
pytest tests/ai_evals/ -v -k closing

# Ver response_text + tool_calls completos (debug)
pytest tests/ai_evals/ -v -s
```

## Custo aproximado

- Cada case = ~1 chamada ao modelo de scheduling (gpt-4o-mini ou gpt-4.1-mini) + 1 chamada ao judge (gpt-4o-mini)
- 8 cases × ~2K tokens × $0.15/1M ≈ **$0.005 por run completo**

## O que mede

| # | Categoria | Bug real que motivou o case |
|---|-----------|-----------------------------|
| 1 | tier_mapping (deep) | AI quotou $115 quando era Deep Clean ($207) |
| 2 | tier_mapping (consistency) | Preço flutuou $207→$115 entre turnos |
| 3 | honest_confirmation | AI mentiu "está confirmada" sem tool retornar success |
| 4 | no_double_confirm | AI pediu "confirma?" 2x — cliente "Já disse que sim" |
| 5 | grounding | AI passou `service_id="deep_clean"` (slug inventado) ou business_id |
| 6 | narrative (auto-confirm) | AI dizia "owner confirmará em breve" |
| 7 | no_internal_leak | AI vazou UUID e nome de tool no chat |
| 8 | closing | AI re-perguntou "do que precisa?" depois de "Não" do cliente |

## Anatomia de um case

Cada case é um JSON em `cases/`:

```json
{
  "id": "pricing-tier-deep",
  "category": "tier_mapping",
  "description": "AI must quote $207 for Deep Clean, not $115",

  "history": [...],           // turnos anteriores no system_prompt
  "user_message": "Limpeza profunda 23/04 9h",

  "mock_tools": {             // o que execute_tool retorna (sem hit DB)
    "get_price_quote": {"final_amount": 207.0, "tier": "deep"},
    ...
  },

  "checks": [                 // determinísticos
    {"kind": "tool_called", "tool": "get_price_quote", "args_contain": {"tier": "deep"}},
    {"kind": "regex_present", "pattern": "\\$\\s?207"},
    {"kind": "regex_absent",  "pattern": "R\\$"}
  ],

  "judge_prompt": "...",      // soft check via LLM-as-judge
  "judge_threshold": 2        // score 0-3, ≥ threshold = pass
}
```

### Tipos de check

- `regex_present` / `regex_absent` — pattern no `response_text`
- `tool_called` — tool foi chamado (opcionalmente com args contendo subset)
- `tool_not_called` — tool NÃO foi chamado

### Judge

LLM avalia se o `response_text` satisfaz o `judge_prompt` numa escala 0-3. Falha se `score < threshold`.

## Como adicionar um case quando bug novo aparecer

1. Identifica o input + tool fixtures que reproduzem o bug.
2. Cria `cases/NN_short_name.json` com checks que falham na versão buggada.
3. Roda `pytest tests/ai_evals/ -v -k short_name` — confirma FAIL.
4. Ajusta o prompt em `app/prompts/scheduling_customer.py`.
5. Re-roda — confirma PASS.
6. Commita o case + prompt change juntos.

## Próximos passos (Sprint 2)

- Multilíngue (variantes EN/ES dos mesmos cases)
- Edge cases (slot conflict, cliente sem authenticated_id, mensagem vazia)
- HTML report com diff vs run anterior
- GitHub Action nightly + pre-deploy gate
