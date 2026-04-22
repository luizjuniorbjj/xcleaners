"""
Eval harness — runs one case end-to-end against the live scheduling prompt.

Flow per case:
  1. Build system prompt via SCHEDULING_CUSTOMER_SYSTEM_PROMPT.format(...)
  2. Replay the case's conversation history into messages.
  3. Patch execute_tool to return the case's mock_tools fixtures, recording
     every (tool_name, args) call.
  4. Run _run_openai_tools with the case's user_message.
  5. Apply checks (regex must_pass / must_not, tool_called assertions, judge).
  6. Return a CaseResult — passed bool + per-check breakdown.

Zero DB hits. Zero real WhatsApp. The OpenAI generation call IS real (we want
the actual LLM behavior under test) — set OPENAI_API_KEY before running.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional
from unittest.mock import patch


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class CaseResult:
    case_id: str
    category: str
    passed: bool
    response_text: str
    tool_calls: list = field(default_factory=list)
    checks: list = field(default_factory=list)
    judge_score: Optional[int] = None
    judge_rationale: str = ""

    def summary(self) -> str:
        marker = "PASS" if self.passed else "FAIL"
        head = f"[{marker}] {self.case_id} ({self.category})"
        if not self.passed:
            failed = [c for c in self.checks if not c.passed]
            head += f" — {len(failed)} check(s) failed"
        return head


def _build_system_prompt(case_overrides: dict) -> str:
    """Render the live SCHEDULING_CUSTOMER_SYSTEM_PROMPT with safe defaults."""
    from app.prompts.scheduling_customer import SCHEDULING_CUSTOMER_SYSTEM_PROMPT

    defaults = {
        "business_name": "QATEST Cleaning Co",
        "business_id": "af168a02-be55-4714-bbe2-9c979943f89c",
        "business_timezone": "America/New_York",
        "client_id": "25981776-b72d-4e99-80b6-9fbd5f4276e2",
        "client_name": "Test Customer",
        "client_address": "123 Test St",
        "client_zip": "33073",
        "today_local": "2026-04-22 (Wednesday)",
    }
    defaults.update(case_overrides.get("prompt_vars", {}))

    base = SCHEDULING_CUSTOMER_SYSTEM_PROMPT.format(**defaults)

    history = case_overrides.get("history", [])
    if history:
        history_text = "\n".join(f"{m['role']}: {m['content']}" for m in history)
        base += (
            f"\n\n--- Conversa anterior (últimos {len(history)} turnos) ---\n"
            f"{history_text}\n"
            f"--- Fim da conversa anterior ---\n\n"
            f"Use o contexto acima para manter coerência. NÃO repita perguntas já respondidas."
        )
    return base


def _make_mock_execute_tool(mock_tools: dict, recorder: list):
    """Build an async patch for execute_tool that returns case fixtures."""

    async def _mock(tool_name, args, business_id, db, auth_context=None):
        recorder.append({"name": tool_name, "args": dict(args)})
        if tool_name not in mock_tools:
            return {"error": "mock_missing", "message": f"no fixture for {tool_name}"}
        return mock_tools[tool_name]

    return _mock


def _apply_check(check: dict, response_text: str, tool_calls: list) -> CheckResult:
    kind = check.get("kind")
    if kind == "regex_present":
        pattern = check["pattern"]
        ok = bool(re.search(pattern, response_text, re.IGNORECASE))
        return CheckResult(name=f"regex_present:{pattern}", passed=ok)
    if kind == "regex_absent":
        pattern = check["pattern"]
        ok = not re.search(pattern, response_text, re.IGNORECASE)
        return CheckResult(
            name=f"regex_absent:{pattern}",
            passed=ok,
            detail="" if ok else "matched (should NOT)",
        )
    if kind == "tool_called":
        name = check["tool"]
        args_subset = check.get("args_contain", {})
        for tc in tool_calls:
            if tc["name"] != name:
                continue
            if all(tc["args"].get(k) == v for k, v in args_subset.items()):
                return CheckResult(name=f"tool_called:{name}", passed=True)
        return CheckResult(
            name=f"tool_called:{name}",
            passed=False,
            detail=f"want args_contain={args_subset}, got={tool_calls}",
        )
    if kind == "tool_not_called":
        name = check["tool"]
        called = any(tc["name"] == name for tc in tool_calls)
        return CheckResult(
            name=f"tool_not_called:{name}",
            passed=not called,
            detail="" if not called else "tool was called",
        )
    return CheckResult(name=f"unknown:{kind}", passed=False, detail=f"unknown check kind: {kind}")


JUDGE_MODEL = "gpt-4.1-mini"
JUDGE_MODEL_FALLBACK = "gpt-4.1"


async def _judge(judge_prompt: str, response_text: str, judge_threshold: int = 2) -> tuple[int, str]:
    """LLM-as-judge soft check. Returns (score 0-3, rationale).

    Uses gpt-4.1-mini as primary (matches prod scheduling model). If the judge
    parses to score=0 with no clear rationale (often a sign the small model
    misread the criterion), retries once with gpt-4.1 for higher precision.
    """
    import os
    from openai import AsyncOpenAI

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return 0, "OPENAI_API_KEY missing — judge skipped"

    system = (
        "You are a strict evaluator. Read the criterion carefully — note any "
        "explicit IGNORE / EXCEPT clauses — then judge the assistant's reply. "
        "Reply ONLY with a JSON object: "
        '{"score": 0|1|2|3, "rationale": "<one sentence quoting the relevant '
        'phrase from the reply>"}. '
        "Score: 3=perfectly satisfies criterion, 2=mostly satisfies, "
        "1=partially satisfies, 0=fails the criterion."
    )
    user = f"CRITERION:\n{judge_prompt}\n\nASSISTANT REPLY:\n{response_text}"

    async def _call(model: str) -> tuple[int, str]:
        client = AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0,
            response_format={"type": "json_object"},
            max_tokens=200,
        )
        body = resp.choices[0].message.content or "{}"
        data = json.loads(body)
        return int(data.get("score", 0)), str(data.get("rationale", ""))

    try:
        score, rationale = await _call(JUDGE_MODEL)
        if score < judge_threshold:
            try:
                score2, rationale2 = await _call(JUDGE_MODEL_FALLBACK)
                if score2 != score:
                    return score2, f"[{JUDGE_MODEL_FALLBACK}] {rationale2}"
            except Exception:
                pass
        return score, rationale
    except Exception as e:
        return 0, f"judge error: {e}"


async def run_case(case: dict) -> CaseResult:
    """Execute one case and return a CaseResult."""
    from app.modules.cleaning.services import ai_scheduling

    system_prompt = _build_system_prompt(case)
    user_message = case["user_message"]
    mock_tools = case.get("mock_tools", {})
    recorder: list = []

    mock = _make_mock_execute_tool(mock_tools, recorder)

    with patch.object(ai_scheduling, "execute_tool", mock):
        ai_client, provider = ai_scheduling._get_ai_client()
        if provider == "anthropic":
            response_text = await ai_scheduling._run_anthropic_tools(
                ai_client, system_prompt, user_message,
                "af168a02-be55-4714-bbe2-9c979943f89c", None,
                {"authenticated_client_id": "25981776-b72d-4e99-80b6-9fbd5f4276e2"},
            )
        else:
            response_text = await ai_scheduling._run_openai_tools(
                ai_client, system_prompt, user_message,
                "af168a02-be55-4714-bbe2-9c979943f89c", None, provider,
                {"authenticated_client_id": "25981776-b72d-4e99-80b6-9fbd5f4276e2"},
            )

    checks: list = []
    for chk in case.get("checks", []):
        checks.append(_apply_check(chk, response_text, recorder))

    judge_score = None
    judge_rationale = ""
    if case.get("judge_prompt"):
        judge_score, judge_rationale = await _judge(case["judge_prompt"], response_text)
        threshold = int(case.get("judge_threshold", 2))
        checks.append(CheckResult(
            name=f"judge>={threshold}",
            passed=judge_score >= threshold,
            detail=f"score={judge_score} — {judge_rationale}",
        ))

    passed = all(c.passed for c in checks)

    return CaseResult(
        case_id=case["id"],
        category=case.get("category", "uncategorized"),
        passed=passed,
        response_text=response_text,
        tool_calls=recorder,
        checks=checks,
        judge_score=judge_score,
        judge_rationale=judge_rationale,
    )
