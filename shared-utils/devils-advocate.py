#!/usr/bin/env python3
"""
Devil's Advocate challenge generator.

Surfaces blind spots in agent-generated work or owner-approved decisions BEFORE
they cause real-world damage. Generates ONE specific, data-cited challenge per call.

Trigger types:
- critical_task         : task with priority=critical moving to done
- strategic_decision    : any task flagged decision=true
- consecutive_approval  : owner approved 5 outputs in a row (anti-yes-man)
- kpi_swing             : KPI moved >20% on a campaign-tied metric
- sensitive_dept        : task in legal, finance, or compliance dept

Usage:
    python3 shared-utils/devils-advocate.py --trigger critical_task --context-json /tmp/ctx.json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from detect_platform import get_openclaw_paths  # noqa: F401

SELECT_MODEL_AVAILABLE = False
try:
    from select_model import call_model_with_fallback  # type: ignore
    SELECT_MODEL_AVAILABLE = True
except Exception:
    pass


DA_PROMPT = """You are the Devil's Advocate. You surface blind spots in agent-generated
work or owner-approved decisions BEFORE they cause real-world damage.

Your rules:
1. Be specific, not generic. "This is risky" is BANNED.
   Required form: "This assumes 30% email open rates but the industry average is 21%."
2. Frame challenges as questions: "What would have to be true for this to succeed?"
3. Cite ONE data point, principle, or pattern per challenge.
4. Do NOT propose solutions.
5. Never apologize, never sugar-coat.
6. ONE concern per challenge — do not stack multiple.

Context (JSON):
{context}

Generate ONE Devil's Advocate challenge in this exact format:

## Challenge
[The question, 1-2 sentences]

## Specific Concern
[The exact assumption being challenged, with data point or principle]

## What Would Have to Be True
[3-5 bullet points listing assumptions that must hold for the original plan to succeed]

## Severity
[low | medium | high]

## Confidence
[A number between 0.0 and 1.0, your confidence in this challenge]
"""


def generate_challenge(trigger_type: str, context: dict) -> dict:
    formatted_context = json.dumps(context, indent=2)
    prompt = DA_PROMPT.replace("{context}", formatted_context)

    if SELECT_MODEL_AVAILABLE:
        try:
            response = call_model_with_fallback(
                tier="heavy",
                prompt=prompt,
                max_tokens=800,
                timeout=120,
            )
        except Exception as e:
            print(f"WARNING: model call failed ({e}), using template-only fallback", file=sys.stderr)
            response = _fallback_response(trigger_type, context)
    else:
        response = _fallback_response(trigger_type, context)

    # Parse the response sections
    sections = {}
    current_section = None
    for line in response.split("\n"):
        if line.startswith("## "):
            current_section = line[3:].strip().lower().replace(" ", "_")
            sections[current_section] = ""
        elif current_section:
            sections[current_section] += line + "\n"

    try:
        confidence = float(sections.get("confidence", "0.7").strip() or "0.7")
    except ValueError:
        confidence = 0.7

    return {
        "trigger_type": trigger_type,
        "challenge": sections.get("challenge", "").strip(),
        "specific_concern": sections.get("specific_concern", "").strip(),
        "assumptions": sections.get("what_would_have_to_be_true", "").strip(),
        "severity": sections.get("severity", "medium").strip().lower() or "medium",
        "confidence": confidence,
        "raw_response": response,
    }


def _fallback_response(trigger_type: str, context: dict) -> str:
    """Template-only response when no LLM is available. Generic but structurally valid."""
    task = context.get("title") or context.get("task_title") or "(unknown task)"
    return f"""## Challenge
What would have to be true for "{task}" to succeed exactly as currently scoped?

## Specific Concern
This was flagged by the {trigger_type} trigger but no LLM model was available to generate
a specific data-cited challenge. Treat with skepticism until a human reviews.

## What Would Have to Be True
- All upstream inputs are accurate
- The target audience matches the assumptions in the brief
- The KPI signal you're tracking is the right signal
- No major competitor is doing the same thing within the same time window
- The owner's stated values still match the approach

## Severity
medium

## Confidence
0.5
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--trigger",
        required=True,
        choices=["critical_task", "strategic_decision", "consecutive_approval", "kpi_swing", "sensitive_dept"],
    )
    parser.add_argument("--context-json", required=True)
    parser.add_argument("--format", default="json", choices=["json", "human"])
    args = parser.parse_args()

    with open(args.context_json, encoding="utf-8") as f:
        context = json.load(f)

    result = generate_challenge(args.trigger, context)

    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        print(f"Trigger: {result['trigger_type']}")
        print(f"Severity: {result['severity']}  Confidence: {result['confidence']:.2f}")
        print(f"\nChallenge:\n  {result['challenge']}")
        print(f"\nSpecific concern:\n  {result['specific_concern']}")
        print(f"\nAssumptions:\n{result['assumptions']}")


if __name__ == "__main__":
    main()
