"""
Pytest entry for the AI EVAL suite.

Discovers every JSON case in ./cases/, runs it through eval_harness.run_case,
and asserts passed=True. Failure messages include per-check breakdown so the
diff to fix is immediate.

Run:
    pytest tests/ai_evals/ -v
    pytest tests/ai_evals/ -v -k pricing
    pytest tests/ai_evals/ -v -s   # see full response_text + tool_calls
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.ai_evals.eval_harness import run_case

CASES_DIR = Path(__file__).parent / "cases"


def _load_cases():
    files = sorted(CASES_DIR.glob("*.json"))
    return [(f.stem, json.loads(f.read_text(encoding="utf-8"))) for f in files]


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set — eval requires real LLM call",
)
@pytest.mark.asyncio
@pytest.mark.parametrize("case_id, case", _load_cases(), ids=[c[0] for c in _load_cases()])
async def test_eval_case(case_id, case, capsys):
    result = await run_case(case)

    if not result.passed:
        with capsys.disabled():
            print()
            print("=" * 80)
            print(f"FAIL — {result.case_id} ({result.category})")
            print(f"Description: {case.get('description', '(none)')}")
            print()
            print("RESPONSE TEXT:")
            print(result.response_text or "(empty)")
            print()
            print(f"TOOL CALLS ({len(result.tool_calls)}):")
            for tc in result.tool_calls:
                print(f"  - {tc['name']}({json.dumps(tc['args'])[:200]})")
            print()
            print("CHECKS:")
            for c in result.checks:
                marker = "OK" if c.passed else "FAIL"
                print(f"  [{marker}] {c.name}{(' — ' + c.detail) if c.detail else ''}")
            if result.judge_score is not None:
                print(f"\nJUDGE: score={result.judge_score} — {result.judge_rationale}")
            print("=" * 80)

    assert result.passed, result.summary()
