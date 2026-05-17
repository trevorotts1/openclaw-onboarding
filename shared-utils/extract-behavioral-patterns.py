#!/usr/bin/env python3
"""
Extract behavioral patterns from raw interview answers (Questions B-1 through B-5).

Writes a structured profile to USER.md under `## Behavioral Identity Profile`.
This is the data Layer 2 (Owner Values) of persona scoring reads.

Usage:
    python3 shared-utils/extract-behavioral-patterns.py --answers-json /path/to/answers.json
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from detect_platform import get_openclaw_paths

# Use the existing select_model.py infrastructure if available
SELECT_MODEL_AVAILABLE = False
try:
    sys.path.insert(0, str(Path(__file__).parent))
    from select_model import call_model_with_fallback  # type: ignore
    SELECT_MODEL_AVAILABLE = True
except Exception:
    pass


EXTRACTION_PROMPT = """You are extracting BEHAVIORAL patterns from a business owner's answers
to scenario-based interview questions. You are NOT extracting their stated values.
You are extracting how they actually behave under pressure.

Read the answers below and produce a structured profile. Each section must be 1-3 sentences,
written in the third person, focusing on observable behavior.

If an answer is generic or evasive (e.g., "I just have a hard conversation"), say
"insufficient signal" in that section. Do NOT invent.

Answers:
{answers}

Produce the profile in this exact format:

## Communication Style Under Pressure
[What does this person actually do when delivering hard news? Direct? Through analogy?
Quick or slow? Emotional or restrained?]

## Decision Process
[How do they actually decide? Gut, data, prayer, consensus, instinct?]

## Money / Risk Posture
[What signals do they trust with money? Aggressive? Conservative? Pattern-matcher?]

## Natural Voice
[Quote 1-2 phrases from the BBQ-style answer that show how they actually speak]

## Conflict Resolution Pattern
[How do they engage when two parties disagree? Mediator? Adjudicator? Avoider?]

## Anti-Mentors
[List the 1-2 people they actively disagree with]

## Mentors
[List the 2-3 mentors they cited]

## Persona Matching Signal Summary
[2-3 sentences summarizing this owner in a form a persona-matching algorithm can use.
Focus on tone, decision style, value signals, things to avoid.]
"""


def extract_patterns(answers: dict) -> str:
    """
    answers: dict with keys B-1 through B-5, values are owner's raw answers.
    Returns: formatted markdown profile.
    """
    formatted_answers = "\n\n".join(
        f"### B-{i}: {answers.get(f'B-{i}', '(no answer)')}" for i in range(1, 6)
    )
    prompt = EXTRACTION_PROMPT.replace("{answers}", formatted_answers)

    if SELECT_MODEL_AVAILABLE:
        try:
            response = call_model_with_fallback(
                tier="heavy",
                prompt=prompt,
                max_tokens=2000,
                timeout=300,
            )
            return response.strip()
        except Exception as e:
            print(f"WARNING: model call failed ({e}), falling back to passthrough profile", file=sys.stderr)

    # Fallback: emit a structurally-correct profile using raw answers directly
    # This keeps USER.md valid even without an LLM call available
    return _fallback_profile(answers)


def _fallback_profile(answers: dict) -> str:
    def short(s: str, n: int = 200) -> str:
        s = (s or "").strip()
        if len(s) <= n:
            return s
        return s[: n - 3].rstrip() + "..."

    b1 = short(answers.get("B-1", ""), 300)
    b2 = short(answers.get("B-2", ""), 300)
    b3 = short(answers.get("B-3", ""), 300)
    b4 = short(answers.get("B-4", ""), 200)
    b5 = answers.get("B-5", "")

    # Try to parse mentors and anti-mentors from B-5
    mentors = "insufficient signal"
    anti_mentors = "insufficient signal"
    if b5:
        # Naive split on "disagree" / "don't like"
        split_kw = re.split(r"(?:disagree|don'?t like|actively disagree)", b5, maxsplit=1, flags=re.IGNORECASE)
        if len(split_kw) == 2:
            mentors = split_kw[0].strip().rstrip(",.;:")
            anti_mentors = split_kw[1].strip().rstrip(",.;:")
        else:
            mentors = b5.strip()

    return f"""## Communication Style Under Pressure
Owner's own words (B-1): "{b1}"

## Decision Process
Owner's own words (B-2): "{b2}"

## Money / Risk Posture
Owner's own words (B-3): "{b3}"

## Natural Voice
Owner's own words (BBQ-style description from B-4): "{b4}"

## Conflict Resolution Pattern
Not explicitly captured in B-1 to B-5. Inferred from B-1 hard-conversation pattern: "{short(b1, 100)}"

## Anti-Mentors
{short(anti_mentors, 200)}

## Mentors
{short(mentors, 200)}

## Persona Matching Signal Summary
This owner provided raw scenario answers but no LLM model was available to synthesize a profile. Raw answers preserved verbatim in the "## Behavioral Identity Source Answers" section. Persona matching should weight Layer 2 (Owner Values) with reduced confidence until a profile can be re-extracted with a heavy-tier model."""


def write_to_user_md(profile: str, answers: dict, paths: dict):
    user_md = paths["user_md"]
    existing = user_md.read_text(encoding="utf-8") if user_md.exists() else ""

    raw_section = "\n## Behavioral Identity Source Answers\n" + "\n\n".join(
        f"### B-{i}\n{answers.get(f'B-{i}', '(no answer)')}" for i in range(1, 6)
    ) + "\n"

    new_section = "\n## Behavioral Identity Profile\n*Generated by AI Workforce Interview — Skill 23 v10.4.0*\n\n" + profile + "\n" + raw_section

    if "## Behavioral Identity Profile" in existing:
        # Replace existing block (and its source-answers block)
        new_content = re.sub(
            r"\n## Behavioral Identity Profile.*?(?=\n## (?!Behavioral Identity Source)|$)",
            new_section.lstrip("\n"),
            existing,
            count=1,
            flags=re.DOTALL,
        )
        user_md.write_text(new_content, encoding="utf-8")
    else:
        if existing and not existing.endswith("\n"):
            existing += "\n"
        user_md.write_text(existing + new_section, encoding="utf-8")

    print(f"Behavioral profile written to: {user_md}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--answers-json", required=True, help="Path to JSON file with B-1..B-5 answers")
    args = parser.parse_args()

    with open(args.answers_json, encoding="utf-8") as f:
        answers = json.load(f)

    paths = get_openclaw_paths()
    profile = extract_patterns(answers)
    write_to_user_md(profile, answers, paths)
    print()
    print(profile)


if __name__ == "__main__":
    main()
