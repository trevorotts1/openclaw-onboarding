#!/usr/bin/env python3
"""tone_persona_autopick.py — deterministic N/A tone-slot auto-pick (F4.3).

The shared tone-writing-core (skills 52 brand / 53 book / 54 anthology) blends
FOUR tone-style slots into one voice. A slot may be a CLIENT-NAMED figure or
``N/A``. Historically an N/A slot was filled by a raw prompt-level instruction
("choose a relevant well-known person in harmony with the avatar") — no scoring,
no logging, no persistence: the exact ad-hoc pattern the canonical 5-layer
selector was built to replace.

This helper routes ONLY the N/A slots through the shared entry point
``shared-utils/persona_for_job.py`` (canonical selector), so the auto-pick is
avatar/task-aware, deterministic, and LOGGED to the persona learning loop. It
returns a canonical persona whose blueprint seeds the tone-analysis stage.

INVARIANTS (do not regress):
  * CLIENT-NAMED slots are NEVER touched — pass them through as-is. Client
    sovereignty is absolute; the selector is only consulted for N/A slots.
  * The 4-slot blend is preserved — this resolves each N/A slot independently and
    returns four slot results in order; the blend at stage 08 is unchanged.
  * Skill 53's optional fictional palette becomes an explicit FALLBACK tier: it
    is only relevant when a client wants a fictional voice; the deterministic
    selector pick is the default for N/A.

stdlib-only.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
# shared-utils is the parent of tone-writing-core.
_SHARED_UTILS = _HERE.parent

_NA_TOKENS = {"", "n/a", "na", "none", "-", "tbd"}


def _load_pfj():
    for d in (str(_SHARED_UTILS),
              os.environ.get("SHARED_UTILS_DIR", "").strip(),
              str(Path.home() / ".openclaw" / "skills" / "shared-utils"),
              "/data/.openclaw/skills/shared-utils"):
        if d and (Path(d) / "persona_for_job.py").exists():
            sys.path.insert(0, d)
            try:
                import persona_for_job as pfj  # type: ignore
                return pfj
            except Exception:
                continue
    return None


def is_na(slot_value: "str | None") -> bool:
    return str(slot_value or "").strip().lower() in _NA_TOKENS


def autopick_slot(slot_value, avatar_context: str, *, department: str = "content",
                  record: bool = True) -> dict:
    """Resolve ONE tone slot.

    Returns a dict:
      {slot, resolved: bool, mode: "client-named"|"auto-pick", persona_id,
       persona_name, section4_excerpt, source}

    * A client-named slot passes through untouched (resolved via the library only
      for the Section-4 excerpt; the selector is NEVER consulted — client
      sovereignty).
    * An N/A slot is routed through persona_for_job (canonical selection, LOGGED).
    """
    pfj = _load_pfj()
    if is_na(slot_value):
        if pfj is None:
            return {"slot": slot_value, "resolved": False, "mode": "auto-pick",
                    "persona_id": None, "persona_name": None,
                    "section4_excerpt": "", "source": "unavailable",
                    "warning": "persona_for_job not reachable; keep prompt-level N/A instruction"}
        sel = pfj.persona_for_job(avatar_context or "brand voice tone analysis",
                                  department, record=record)
        return {"slot": slot_value, "resolved": bool(sel.get("persona_id")),
                "mode": "auto-pick", "persona_id": sel.get("persona_id"),
                "persona_name": sel.get("persona_name"),
                "section4_excerpt": sel.get("section4_excerpt", ""),
                "source": sel.get("source")}
    # CLIENT-NAMED — pass through; selector NEVER consulted.
    named = str(slot_value).strip()
    excerpt = ""
    if pfj is not None:
        # Only if the client's named figure happens to match a canonical library id
        # do we surface its Section-4 excerpt; otherwise the name is used as-is.
        try:
            if named in set(pfj.available_personas()):
                excerpt = pfj.section4_excerpt(named)
        except Exception:
            excerpt = ""
    return {"slot": slot_value, "resolved": True, "mode": "client-named",
            "persona_id": named, "persona_name": named,
            "section4_excerpt": excerpt, "source": "client-named"}


def autopick(slots: list, avatar_context: str, *, department: str = "content",
             record: bool = True) -> list:
    """Resolve all four tone slots in order (client-named untouched, N/A auto-picked).
    Returns one result per slot; the 4-slot blend downstream is unchanged."""
    return [autopick_slot(s, avatar_context, department=department, record=record)
            for s in slots]


def _self_test() -> int:
    ok = True

    def check(label, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "FAIL", label))

    check("is_na basic", is_na("N/A") and is_na("") and is_na("na") and not is_na("Oprah"))

    os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(
        {"persona_id": "covey-7-habits", "persona_name": "Covey", "score": 0.8})
    slots = ["Michelle Obama", "N/A", "na", "Simon Sinek"]
    res = autopick(slots, "an audience of ambitious founders")
    check("four slots resolved", len(res) == 4)
    check("client-named slot #1 untouched (not selector value)",
          res[0]["mode"] == "client-named" and res[0]["persona_id"] == "Michelle Obama")
    check("client-named slot #4 untouched",
          res[3]["mode"] == "client-named" and res[3]["persona_id"] == "Simon Sinek")
    check("N/A slot #2 routed through selector",
          res[1]["mode"] == "auto-pick" and res[1]["persona_id"] == "covey-7-habits")
    check("N/A slot #3 routed through selector",
          res[2]["mode"] == "auto-pick" and res[2]["persona_id"] == "covey-7-habits")
    check("no naked N/A slot",
          all(r["persona_id"] for r in res if r["mode"] == "auto-pick"))
    os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)

    print("== tone_persona_autopick self-test: %s ==" % ("ALL PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Deterministic N/A tone-slot auto-pick (F4.3).")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    ap.add_argument("--slots", help="comma-separated slot values (N/A allowed)")
    ap.add_argument("--avatar", default="", help="avatar context text")
    ap.add_argument("--department", default="content")
    a = ap.parse_args()
    if a.self_test:
        raise SystemExit(_self_test())
    if not a.slots:
        ap.error("--slots is required (or use --self-test)")
    print(json.dumps(autopick([s.strip() for s in a.slots.split(",")],
                              a.avatar, department=a.department), indent=2))
