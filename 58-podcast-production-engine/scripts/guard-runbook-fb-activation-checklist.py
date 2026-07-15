#!/usr/bin/env python3
# =============================================================================
# 58-PODCAST-PRODUCTION-ENGINE :: GUARD-RUNBOOK-FB-ACTIVATION-CHECKLIST
# -----------------------------------------------------------------------------
# DETERMINISTIC, NO-AI, FAIL-CLOSED. Repo QC gate (grep-anchored, not semantic)
# proving the per-client Facebook-ads workflow activation script
# (scripts/activate-podcast-fb-workflows.py) is an explicit checklist item,
# naming the script AND its exact invocation, inside the podcast
# client-onboarding runbook (universal-sops/podcast-craft/
# SOP-PODCAST-02-CLIENT-ONBOARDING.md) -- never left as tribal knowledge.
#
# Unit: Skill 6 blended-persona-kanban v2, U68 / GK-06.
#
# RIDES THE SAME REPO-QC GATE FAMILY as guard-cron-inventory.py and
# guard-no-anthropic-runtime.py (see the Enforcement pointers table in
# SKILL.md): a rule without a gate is a suggestion.
#
# WHAT IT CHECKS (all three must be present in the runbook text; a runbook
# edit that drops any one of them fails this gate closed rather than drifting
# silently out of sync):
#   1. the script's repo-relative path
#        58-podcast-production-engine/scripts/activate-podcast-fb-workflows.py
#   2. the exact invocation this SOP directs the operator to run (kept
#      byte-identical to the runbook line on purpose, so a paraphrased or
#      edited invocation fails loudly instead of drifting)
#   3. a checklist-shaped anchor (the numbered SOP subsection heading) so a
#      bare mention buried in unrelated prose does not satisfy the gate
#
# EXIT: 0 PASS / 2 AUTOFAIL / 3 USAGE-IO
# USAGE:
#   python3 guard-runbook-fb-activation-checklist.py [--runbook PATH] [--json]
#   python3 guard-runbook-fb-activation-checklist.py --self-test
# =============================================================================
"""Grep-anchored QC gate: the FB-ads activation script must be an explicit
checklist item, naming the script and its exact invocation, in the podcast
client-onboarding runbook (never tribal knowledge)."""

import argparse
import json
import sys
from pathlib import Path

EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

_SELF = Path(__file__).resolve()
_SKILL_ROOT = _SELF.parent.parent  # 58-podcast-production-engine/
_REPO_ROOT = _SKILL_ROOT.parent
_DEFAULT_RUNBOOK = (
    _REPO_ROOT / "universal-sops" / "podcast-craft" / "SOP-PODCAST-02-CLIENT-ONBOARDING.md"
)

_SCRIPT_PATH = "58-podcast-production-engine/scripts/activate-podcast-fb-workflows.py"
_REQUIRED_INVOCATION = (
    "python3 58-podcast-production-engine/scripts/activate-podcast-fb-workflows.py "
    "--location <location-id> --execute --fb-account act_XXXX --fb-audience <audience-id> "
    "--fb-pixel <pixel-id> --fb-token <capi-token>"
)
_CHECKLIST_ANCHOR = "### 2.9"

AF_MISSING_SCRIPT_REF = "AF-PPE-RUNBOOK-NO-SCRIPT-REF"
AF_MISSING_INVOCATION = "AF-PPE-RUNBOOK-NO-INVOCATION"
AF_MISSING_ANCHOR = "AF-PPE-RUNBOOK-NO-CHECKLIST-ANCHOR"


def audit(text):
    """Return a list of (code, class) findings; empty means PASS."""
    findings = []
    if _SCRIPT_PATH not in text:
        findings.append((AF_MISSING_SCRIPT_REF, "runbook does not name %s" % _SCRIPT_PATH))
    if _REQUIRED_INVOCATION not in text:
        findings.append((AF_MISSING_INVOCATION, "runbook does not carry the exact invocation"))
    if _CHECKLIST_ANCHOR not in text:
        findings.append((AF_MISSING_ANCHOR, "runbook has no %s checklist subsection" % _CHECKLIST_ANCHOR))
    return findings


def _emit(findings, as_json, target):
    passed = not findings
    if as_json:
        print(json.dumps({
            "gate": "podcast-guard-runbook-fb-activation-checklist",
            "target": target,
            "pass": passed,
            "findings": [{"code": c, "class": cl} for c, cl in findings],
        }, indent=2))
    else:
        print("== Podcast Production Engine :: guard-runbook-fb-activation-checklist ==")
        print("  runbook: %s" % target)
        if passed:
            print("RESULT: PASS - the FB-ads activation script is an explicit, exact-invocation checklist item.")
        else:
            print("RESULT: FAIL (fail-closed) - %d finding(s):" % len(findings))
            for c, cl in findings:
                print("  [%s] %s" % (c, cl))
    return EXIT_PASS if passed else EXIT_AUTOFAIL


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runbook", default=str(_DEFAULT_RUNBOOK),
                    help="path to the podcast client-onboarding runbook")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    path = Path(args.runbook)
    if not path.is_file():
        print("FATAL: runbook not found: %s" % path, file=sys.stderr)
        return EXIT_USAGE
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print("FATAL: cannot read runbook: %s" % type(exc).__name__, file=sys.stderr)
        return EXIT_USAGE

    findings = audit(text)
    return _emit(findings, args.json, str(path))


# --------------------------------------------------------------------------- #
# Self-test
# --------------------------------------------------------------------------- #
def self_test():
    ok = True

    def check(label, cond):
        nonlocal ok
        ok = ok and cond
        print("  [%s] %s" % ("PASS" if cond else "MISS", label))

    print("== self-test: a clean checklist item passes ==")
    good = "### 2.9 Facebook-ads workflow activation\n\n    %s\n" % _REQUIRED_INVOCATION
    check("clean-runbook-passes", audit(good) == [])

    print("== self-test: each missing piece is caught ==")
    missing_script = "### 2.9\n\n    python3 some-other-script.py --execute\n"
    check("missing-script-ref-caught",
          any(c == AF_MISSING_SCRIPT_REF for c, _ in audit(missing_script)))

    missing_invocation = "### 2.9\n\nSee %s for details.\n" % _SCRIPT_PATH
    check("missing-invocation-caught",
          any(c == AF_MISSING_INVOCATION for c, _ in audit(missing_invocation)))

    missing_anchor = "%s\n\n    %s\n" % (_SCRIPT_PATH, _REQUIRED_INVOCATION)
    check("missing-anchor-caught",
          any(c == AF_MISSING_ANCHOR for c, _ in audit(missing_anchor)))

    check("empty-runbook-fails-all-three", len(audit("")) == 3)

    print("== self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
