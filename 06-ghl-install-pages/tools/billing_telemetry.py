#!/usr/bin/env python3
"""billing_telemetry.py — real billing telemetry receipts for Skill 06 (P8).

One receipt per model call carries the real fields (checklist C9c, plan §15.1):

  provider, model, prompt_tokens, cache_tokens, output_tokens,
  reasoning_tokens, tool_calls, billed_dollars

REASONING DOUBLE-COUNT RULE (plan §15.1): when the provider includes reasoning
tokens inside its output-token totals (both OpenRouter and Ollama Cloud do),
reasoning_tokens is recorded for visibility and NEVER added on top again:
``billed_tokens_total = prompt_tokens + output_tokens``. Only when a provider
reports reasoning OUTSIDE its output total (``reasoning_in_output=False``) is
reasoning added. The receipt states which accounting was used.

BILLED DOLLARS ARE NEVER INVENTED: cost comes from the provider-reported cost
field (e.g. OpenRouter usage.cost) or from a caller-supplied price table;
otherwise ``billed_dollars`` is ``None`` with ``cost_source="unpriced"``.

B18: known deterministic procedures (scripted click/fill/wait recipes) need no
model selection per click — build their receipts with
``llm_calls_during_recipe=0`` and call no model router per action.

USAGE
  python3 tools/billing_telemetry.py --selftest     # offline, exits 0 on pass
  from billing_telemetry import build_receipt
  r = build_receipt(provider="openrouter", model="client/model",
                    raw_usage=resp_usage, tool_calls=2)
"""
from __future__ import annotations

import json
import sys
from typing import Optional

# Providers that report reasoning tokens INSIDE their output/completion totals.
# Everything not listed here is treated the same way unless the caller passes
# reasoning_in_output explicitly — the conservative direction for the
# double-count rule: reasoning is never added on top of an output total.
_REASONING_IN_OUTPUT_DEFAULT = True

# Keys accepted for each field across provider usage payload shapes
# (OpenAI/OpenRouter style, Ollama style). First present key wins.
_PROMPT_KEYS = ("prompt_tokens", "input_tokens", "prompt_eval_count")
_OUTPUT_KEYS = ("completion_tokens", "output_tokens", "eval_count")
_CACHE_KEYS = ("cache_read_tokens", "prompt_cache_hit_tokens", "cached_tokens")
_REASONING_KEYS = ("reasoning_tokens", "reasoning_output_tokens", "thoughts_token_count")
_COST_KEYS = ("cost", "total_cost", "usage_cost")

RECEIPT_SCHEMA = "skill06.billing_receipt.v1"


def _first(raw: dict, keys: tuple) -> Optional[float]:
    for k in keys:
        if isinstance(raw.get(k), (int, float)) and not isinstance(raw.get(k), bool):
            return raw[k]
    return None


def build_receipt(
    *,
    provider: str,
    model: str,
    raw_usage: Optional[dict] = None,
    tool_calls: int = 0,
    llm_calls_during_recipe: int = 0,
    price_table: Optional[dict] = None,
    reasoning_in_output: Optional[bool] = None,
) -> dict:
    """Build one real billing receipt.

    Parameters
    ----------
    provider, model:
        Actual serving provider and model slug used for the call.
    raw_usage:
        The provider's usage payload as reported (prompt/output/reasoning/
        cache/cost keys as the provider emits them). None → all token fields 0
        and the receipt is marked unpriced unless a price table is supplied.
    tool_calls:
        Number of tool calls the model made in this call (0 for pure text).
    llm_calls_during_recipe:
        B18: LLM calls made during a scripted click/fill/wait recipe — must be
        0 for deterministic procedures.
    price_table:
        Optional {"prompt_per_mtok": float, "output_per_mtok": float,
        "reasoning_per_mtok": float, "cache_per_mtok": float} in DOLLARS per
        million tokens. Never hardcoded here; supplied by the operator config.
    reasoning_in_output:
        Override: True when the provider includes reasoning inside
        output_tokens (default), False when reasoning_tokens is billed on top.
        Pass explicitly for providers with different accounting.

    Returns a receipt dict. ``billed_dollars`` is a float only when the
    provider reported cost or a price table was supplied; otherwise None.
    """
    raw = raw_usage or {}
    prompt = int(_first(raw, _PROMPT_KEYS) or 0)
    output = int(_first(raw, _OUTPUT_KEYS) or 0)
    reasoning = int(_first(raw, _REASONING_KEYS) or 0)
    cache = int(_first(raw, _CACHE_KEYS) or 0)
    reported_cost = _first(raw, _COST_KEYS)

    in_output = (
        _REASONING_IN_OUTPUT_DEFAULT if reasoning_in_output is None
        else bool(reasoning_in_output)
    )

    # Double-count guard: reasoning inside output totals is never added again.
    if in_output:
        billed_tokens_total = prompt + output
    else:
        billed_tokens_total = prompt + output + reasoning

    if reported_cost is not None:
        billed_dollars = float(reported_cost)
        cost_source = "provider-reported"
    elif price_table:
        mtok = 1_000_000.0
        billed_dollars = (
            prompt * float(price_table.get("prompt_per_mtok", 0.0))
            + output * float(price_table.get("output_per_mtok", 0.0))
            + cache * float(price_table.get("cache_per_mtok", 0.0))
            + (0.0 if in_output else reasoning)
            * float(price_table.get("reasoning_per_mtok", 0.0))
        ) / mtok
        cost_source = "price-table"
    else:
        billed_dollars = None
        cost_source = "unpriced"

    return {
        "schema": RECEIPT_SCHEMA,
        "provider": provider,
        "model": model,
        "prompt_tokens": prompt,
        "cache_tokens": cache,
        "output_tokens": output,
        "reasoning_tokens": reasoning,
        "tool_calls": int(tool_calls),
        "billed_dollars": billed_dollars,
        "cost_source": cost_source,
        "reasoning_included_in_output": in_output,
        "billed_tokens_total": billed_tokens_total,
        "llm_calls_during_recipe": int(llm_calls_during_recipe),
    }


# ---------------------------------------------------------------------------
# Offline self-test (--selftest)
# ---------------------------------------------------------------------------


def _selftest() -> int:
    errors: list = []

    # 1. Real fields present; reasoning inside output is NOT double-counted.
    r = build_receipt(
        provider="openrouter", model="client/model",
        raw_usage={"prompt_tokens": 1000, "completion_tokens": 400,
                   "reasoning_tokens": 250, "cached_tokens": 300, "cost": 0.0123},
        tool_calls=2,
    )
    for key in ("provider", "model", "prompt_tokens", "cache_tokens",
                "output_tokens", "reasoning_tokens", "tool_calls",
                "billed_dollars"):
        if key not in r:
            errors.append(f"receipt missing real field {key!r}")
    if r["billed_tokens_total"] != 1400:
        errors.append(
            f"reasoning inside output must NOT double-count: total must be "
            f"1400, got {r['billed_tokens_total']}"
        )
    if r["reasoning_tokens"] != 250:
        errors.append("reasoning tokens must still be recorded for visibility")
    if abs(r["billed_dollars"] - 0.0123) > 1e-12:
        errors.append("provider-reported cost must pass through exactly")

    # 2. Reasoning billed on top (explicit override) is added exactly once.
    r2 = build_receipt(
        provider="acme", model="m",
        raw_usage={"prompt_tokens": 10, "output_tokens": 5, "reasoning_tokens": 3},
        reasoning_in_output=False,
    )
    if r2["billed_tokens_total"] != 18:
        errors.append(f"separate reasoning must be added once, got {r2}")

    # 3. No cost source → billed_dollars is None and marked unpriced (never invented).
    r3 = build_receipt(provider="acme", model="m", raw_usage={"prompt_tokens": 1})
    if r3["billed_dollars"] is not None or r3["cost_source"] != "unpriced":
        errors.append(f"unpriced receipt must be explicit, got {r3}")

    # 4. Price table computes dollars without hardcoding prices here.
    r4 = build_receipt(
        provider="acme", model="m",
        raw_usage={"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000,
                   "reasoning_tokens": 500_000},
        price_table={"prompt_per_mtok": 2.0, "output_per_mtok": 8.0,
                     "reasoning_per_mtok": 8.0},
    )
    if abs(r4["billed_dollars"] - 10.0) > 1e-9:
        errors.append(f"price-table math must be 10.0, got {r4['billed_dollars']}")
    if r4["cost_source"] != "price-table":
        errors.append("price-table receipts must say cost_source=price-table")

    # 5. B18: deterministic recipes record zero LLM calls and need no selection.
    r5 = build_receipt(provider="none", model="deterministic-procedure",
                       llm_calls_during_recipe=0)
    if r5["llm_calls_during_recipe"] != 0:
        errors.append("B18: deterministic recipe must record 0 LLM calls")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"[billing_telemetry selftest] FAIL — {len(errors)} error(s)",
              file=sys.stderr)
        return 1
    print("[billing_telemetry selftest] PASS — receipt fields, no double-count, "
          "unpriced explicit, price table, B18 OK (offline)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selftest() if "--selftest" in sys.argv[1:] else 0)
