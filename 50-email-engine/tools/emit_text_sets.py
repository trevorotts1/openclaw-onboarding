#!/usr/bin/env python3
# =============================================================================
# SKILL 50 — EMAIL ENGINE :: TEXT-SET COPY EMITTER  (approved SMS copy for Skill 44)
# -----------------------------------------------------------------------------
# Skill 50 is the copy owner for launch texts (text-profile/launch-text.profile.md);
# Skill 44 owns the send-SMS steps. This is the handoff: for every text_sets[] unit of
# the shared launch plan it writes working/text/<set_id>.sms.json
#
#   {"set_id", "messages": [{"step_id", "body", "category"}], "profile_sha256"}
#
# and refuses to write ANY file unless every set has approved copy that passes the
# text profile (reply invitation + STOP, <=320 chars, <=1 link, no "unsubscribe"), has
# exactly the message count the plan promises, and the promotional sets stay within the
# profile's cap. `category` comes from the plan's `promotional` flag, never from the author.
# launch-c/plan_reader.py --text-copy-dir binds these files into the Skill 44 builds; a text
# set with no file there blocks its builds, so a launch that elected texts cannot be built
# with the copy left pending.
#
# Deterministic, stdlib only, no model, no network, DRAFT-ONLY (it sends nothing).
#
# USAGE
#   emit_text_sets.py --launch-plan plan.json --copy texts.json --out-dir working/text
#     texts.json: {"sets": {"<set_id>": [{"step_id": "...", "body": "..."}]}}
#   emit_text_sets.py --selftest
#
# EXIT CODES: 0 ok / 2 refused (nothing written) / 3 usage or IO
# =============================================================================
"""Deterministic Skill 50 emitter of the per-text-set approved SMS copy files."""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_REFUSED = 2
EXIT_USAGE = 3

SKILL_DIR = Path(__file__).resolve().parents[1]
PROFILE_DIR = SKILL_DIR / "text-profile"
PROFILE = PROFILE_DIR / "launch-text.profile.json"


def _validator():
    spec = importlib.util.spec_from_file_location("_skill50_validate_profile",
                                                  PROFILE_DIR / "validate_profile.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_sets(plan, copy):
    """{set_id: sms document}, or raise ValueError listing every reason nothing can be written."""
    if not isinstance(plan, dict):
        raise ValueError("the launch plan is not a JSON object")
    vp = _validator()
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    cap = profile["rules"].get("promotional_cap_per_launch")
    sets = [s for s in plan.get("text_sets") or [] if isinstance(s, dict)]
    authored = (copy or {}).get("sets") if isinstance(copy, dict) else None
    authored = authored if isinstance(authored, dict) else {}
    errors, out = [], {}
    promo = sum(1 for s in sets if s.get("promotional"))
    if isinstance(cap, int) and promo > cap:
        errors.append("%d promotional text sets exceed the profile cap of %d" % (promo, cap))
    for extra in sorted(set(authored) - {s.get("id") for s in sets}):
        errors.append("copy names %r, which is not a text set of the launch plan" % extra)
    sha = vp.profile_sha256(PROFILE)
    for s in sets:
        set_id = s.get("id")
        rows = authored.get(set_id)
        if not isinstance(rows, list) or not rows:
            errors.append("%s: no approved copy supplied" % set_id)
            continue
        if isinstance(s.get("messages"), int) and len(rows) != s["messages"]:
            errors.append("%s: %d message(s) supplied, the plan promises %d"
                          % (set_id, len(rows), s["messages"]))
            continue
        category = "marketing" if s.get("promotional") else "operational"
        doc = {"set_id": set_id, "profile_sha256": sha,
               "messages": [{"step_id": r.get("step_id"), "body": r.get("body"), "category": category}
                            for r in rows if isinstance(r, dict)]}
        fails = vp.check_sms_set(doc, profile, PROFILE)
        if len(doc["messages"]) != len(rows):
            fails.append("a message is not an object")
        errors += ["%s: %s" % (set_id, f) for f in fails]
        out[set_id] = doc
    if errors:
        raise ValueError("; ".join(errors))
    return out


def emit(plan, copy, out_dir):
    docs = build_sets(plan, copy)  # nothing is written unless EVERY set is valid
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for set_id, doc in docs.items():
        (out_dir / ("%s.sms.json" % set_id)).write_text(json.dumps(doc, indent=2) + "\n",
                                                        encoding="utf-8")
    return sorted(docs)


def _selftest():
    plan = {"text_sets": [{"id": "text_doors_open", "messages": 1, "promotional": True}]}
    good = {"sets": {"text_doors_open": [{"step_id": "s1", "body":
            "Doors are open. Take a look: {link}\nReply YES and I'll send the details. Reply STOP to opt out."}]}}
    assert build_sets(plan, good)["text_doors_open"]["messages"][0]["category"] == "marketing"
    bad = {"sets": {"text_doors_open": [{"step_id": "s1", "body": "Buy now {link}"}]}}
    try:
        build_sets(plan, bad)
        raise AssertionError("a text with no STOP was accepted")
    except ValueError:
        pass
    print("selftest ok")
    return EXIT_OK


def main(argv=None):
    ap = argparse.ArgumentParser(description="Emit working/text/<set_id>.sms.json for every launch text set.")
    ap.add_argument("--launch-plan")
    ap.add_argument("--copy", help="the approved SMS copy (texts.json)")
    ap.add_argument("--out-dir", help="where the <set_id>.sms.json files go (working/text)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not (args.launch_plan and args.copy and args.out_dir):
        ap.error("--launch-plan, --copy and --out-dir are required (or --selftest)")
    try:
        plan = json.loads(Path(args.launch_plan).read_text(encoding="utf-8"))
        copy = json.loads(Path(args.copy).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("emit_text_sets: cannot read input: %s" % exc, file=sys.stderr)
        return EXIT_USAGE
    try:
        written = emit(plan, copy, args.out_dir)
    except ValueError as exc:
        print("emit_text_sets: REFUSED (nothing written): %s" % exc, file=sys.stderr)
        return EXIT_REFUSED
    print("emit_text_sets: wrote %d set(s): %s" % (len(written), ", ".join(written)))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
