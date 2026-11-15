#!/usr/bin/env python3
"""test_pd_bank_032_after_intake.py -- PD-032: tell the client what happens next.

WHAT THIS PINS
--------------
The front door gains one key and changes nothing else. Under `frontdoor`,
`after_intake` carries the exact sentence the client hears once intake is
complete -- what is coming, that they must do nothing until the style
samples arrive, and that they will hear at each big step.

This test is the definition-level guard: it fails in milliseconds if a later
edit renames the key, rewords the promise, or removes it. The build-time
acceptance (the parsed object minus the new key is byte-identical to the
pre-change object) is proven in the unit's build report against the base
blob; it is not re-pinned here, so a sibling unit may edit another key of
this file without tripping this test.

House style: flat file in tests/, direct calls, no network, no spend, no
media dependency (this file must never skip).
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent

TEMPLATES = SCRIPTS / "conversation_templates.json"

AFTER_INTAKE = (
    "That is everything I need. Here is what happens now: I research your "
    "topic, write the slides, and then send you 3 style samples to pick from "
    "(A, B or C). You do not need to do anything until you see those samples. "
    "I will message you at each big step and the moment anything needs you."
)

# Keys the front door carried before PD-032. PD-032 adds after_intake; it
# removes none of these.
FRONTDOOR_KEYS = {"greeting", "handoff", "not_qualified", "qualification"}

TOP_LEVEL_KEYS = {
    "copy_rules",
    "delivery_followup",
    "doctrine",
    "format",
    "frontdoor",
    "owner",
    "park_notice",
    "version",
}


def load() -> dict:
    return json.loads(TEMPLATES.read_text(encoding="utf-8"))


def test_file_parses() -> None:
    assert isinstance(load(), dict)


def test_after_intake_present_and_exact() -> None:
    frontdoor = load()["frontdoor"]
    assert "after_intake" in frontdoor, "frontdoor.after_intake is missing"
    value = frontdoor["after_intake"]
    assert isinstance(value, str), f"after_intake must be a string, got {type(value).__name__}"
    assert value == AFTER_INTAKE, f"after_intake wording drifted:\n{value!r}"


def test_no_frontdoor_key_removed() -> None:
    frontdoor = load()["frontdoor"]
    missing = FRONTDOOR_KEYS - set(frontdoor)
    assert not missing, f"frontdoor lost key(s): {sorted(missing)}"


def test_no_top_level_key_added_or_removed() -> None:
    got = set(load())
    assert got == TOP_LEVEL_KEYS, (
        f"top-level keys changed: added={sorted(got - TOP_LEVEL_KEYS)} "
        f"removed={sorted(TOP_LEVEL_KEYS - got)}"
    )


def main() -> int:
    failures = 0
    for fn in (
        test_file_parses,
        test_after_intake_present_and_exact,
        test_no_frontdoor_key_removed,
        test_no_top_level_key_added_or_removed,
    ):
        try:
            fn()
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {fn.__name__}: {exc}")
        else:
            print(f"PASS {fn.__name__}")
    print(f"\n{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
