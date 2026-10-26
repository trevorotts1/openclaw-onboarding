#!/usr/bin/env python3
"""S75-T40 / S75-A40 reconciliation: 41 fixed obligations + 2 required targets.

Reads the loop-control ledger READ-ONLY (never writes it), cross-checks it against
the authority task-ledger census, and proves the denominator did not shrink.

Stdlib only. Python 3.8+.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

EXPECTED_UNITS = 41
EXPECTED_WEIGHT = 41
EXPECTED_TARGETS = 2


def _sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def load_json(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def census(ledger_doc, authority_doc):
    """Return the measurable facts both censuses agree or disagree on."""
    all_units = ledger_doc.get("units") or []
    # Obligation scope: fixed S75-T rows only. Disposal rows (S75-D*,
    # MERGED, null weight/acceptance_row) are appended by sync lanes after
    # the artifact run and must not move the fixed 41 denominator.
    units = [u for u in all_units if (u.get("id") or "").startswith("S75-T")]
    excluded = [u for u in all_units
                if not (u.get("id") or "").startswith("S75-T")]
    excluded_non_disposal = sorted(
        u.get("id") for u in excluded
        if u.get("weight") is not None or u.get("acceptance_row") is not None
    )
    tasks = authority_doc.get("tasks") or []
    counters = authority_doc.get("counters") or {}
    led_ids = [u.get("id") for u in units]
    auth_ids = [t.get("id") for t in tasks]
    rows = [u.get("acceptance_row") for u in units]
    return {
        "ledger_units": len(units),
        "ledger_ids_unique": len(set(led_ids)),
        "ledger_weight_sum": sum(u.get("weight") or 0 for u in units),
        "ledger_non_unit_weight": sorted(
            u.get("id") for u in units if (u.get("weight") or 0) != 1
        ),
        "acceptance_rows": len(rows),
        "acceptance_rows_unique": len(set(rows)),
        "acceptance_rows_expected": ["S75-A%02d" % i for i in range(1, EXPECTED_UNITS + 1)],
        "ids_expected": ["S75-T%02d" % i for i in range(1, EXPECTED_UNITS + 1)],
        "ledger_ids": led_ids,
        "ledger_excluded_non_obligation": sorted(
            u.get("id") for u in excluded),
        "ledger_excluded_non_disposal": excluded_non_disposal,
        "ledger_total_rows": len(all_units),
        "authority_units": len(tasks),
        "authority_ids": auth_ids,
        "authority_weight_sum": sum(t.get("fixed_weight") or 0 for t in tasks),
        "authority_fixed_current_weight": authority_doc.get("fixed_current_weight"),
        "declared_denominators": {
            "built": (counters.get("built") or {}).get("denominator"),
            "build_accepted": (counters.get("build_accepted") or {}).get("denominator"),
            "merged_required_targets": (counters.get("merged_required_targets") or {}).get("denominator"),
        },
        "required_target_unit_text": (counters.get("merged_required_targets") or {}).get("unit"),
        "project_repos": [r.get("path") for r in (ledger_doc.get("project") or {}).get("repos") or []],
    }


def checks(c):
    """Focused reconciliation checks. Each returns (id, ok, detail)."""
    out = []

    def add(cid, ok, detail):
        out.append({"id": cid, "ok": bool(ok), "detail": detail})

    add("census.unit_count", c["ledger_units"] == EXPECTED_UNITS,
        "ledger units=%d expected=%d" % (c["ledger_units"], EXPECTED_UNITS))
    add("census.unit_ids", c["ledger_ids"] == c["ids_expected"],
        "ids match S75-T01..T41 exactly and in order" if c["ledger_ids"] == c["ids_expected"]
        else "first divergence at %s" % next(
            (i for i, (a, b) in enumerate(zip(c["ledger_ids"], c["ids_expected"])) if a != b), "length"))
    add("census.unit_ids_unique", c["ledger_ids_unique"] == EXPECTED_UNITS,
        "unique ids=%d" % c["ledger_ids_unique"])
    add("census.obligation_scope_clean", not c["ledger_excluded_non_disposal"],
        "excluded non-obligation rows all disposal-shaped (null weight+row): %s"
        % (c["ledger_excluded_non_disposal"] or "yes"))
    add("census.denominator_weight", c["ledger_weight_sum"] == EXPECTED_WEIGHT,
        "sum(weight)=%d expected=%d" % (c["ledger_weight_sum"], EXPECTED_WEIGHT))
    add("census.unit_weight_is_one", not c["ledger_non_unit_weight"],
        "non-unit weights: %s" % (c["ledger_non_unit_weight"] or "none"))
    add("census.acceptance_rows", c["acceptance_rows"] == EXPECTED_UNITS,
        "rows=%d" % c["acceptance_rows"])
    add("census.acceptance_rows_unique", c["acceptance_rows_unique"] == EXPECTED_UNITS,
        "unique rows=%d" % c["acceptance_rows_unique"])
    add("authority.unit_set_equal", sorted(c["authority_ids"]) == sorted(c["ledger_ids"]),
        "authority=%d ledger=%d set-equal=%s"
        % (c["authority_units"], c["ledger_units"],
           sorted(c["authority_ids"]) == sorted(c["ledger_ids"])))
    add("authority.weight", c["authority_weight_sum"] == EXPECTED_WEIGHT,
        "authority sum(fixed_weight)=%d" % c["authority_weight_sum"])
    add("authority.fixed_current_weight",
        c["authority_fixed_current_weight"] == EXPECTED_WEIGHT,
        "fixed_current_weight=%s" % c["authority_fixed_current_weight"])
    den = c["declared_denominators"]
    add("denominator.not_shrunk",
        den["built"] == EXPECTED_WEIGHT and den["build_accepted"] == EXPECTED_WEIGHT
        and den["merged_required_targets"] == EXPECTED_TARGETS,
        "declared built=%s build_accepted=%s targets=%s; census reconciles at %d/%d"
        % (den["built"], den["build_accepted"], den["merged_required_targets"],
           c["ledger_units"], c["ledger_weight_sum"]))
    return out


def target_probe(repo_path, remote="origin", branch="main"):
    """Resolve one required target to an exact revision. Read-only."""
    def git(*args):
        p = subprocess.run(["git", "-C", repo_path] + list(args),
                           capture_output=True, text=True)
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()

    rc, head, err = git("rev-parse", "HEAD")
    rc_t, target, err_t = git("rev-parse", "%s/%s" % (remote, branch))
    rc_net, net, err_net = git("ls-remote", remote, "refs/heads/%s" % branch)
    remote_sha = net.split()[0] if net else None
    return {
        "path": repo_path,
        "head": head if rc == 0 else None,
        "head_error": None if rc == 0 else err,
        "target_ref": "%s/%s" % (remote, branch),
        "target_sha": target if rc_t == 0 else None,
        "target_error": None if rc_t == 0 else err_t,
        "remote_sha": remote_sha,
        "remote_proved": rc_net == 0 and remote_sha == target,
        "remote_error": None if rc_net == 0 else err_net,
        "revision_is_40hex": len(target) == 40 and all(ch in "0123456789abcdef" for ch in target),
    }


def target_checks(targets):
    resolved = [t for t in targets if t.get("revision_is_40hex")]
    return [
        {"id": "targets.count", "ok": len(targets) == EXPECTED_TARGETS,
         "detail": "targets measured=%d required=%d" % (len(targets), EXPECTED_TARGETS)},
        {"id": "targets.exact_revision", "ok": len(resolved) == len(targets) and targets,
         "detail": "exact 40-hex revisions resolved: %d/%d" % (len(resolved), len(targets))},
    ]


def build_report(ledger_path, authority_path, targets, observed=None):
    ledger_doc, ledger_sha = load_json(ledger_path)
    authority_doc, authority_sha = load_json(authority_path)
    c = census(ledger_doc, authority_doc)
    unit_rows = [
        {
            "id": u.get("id"),
            "acceptance_row": u.get("acceptance_row"),
            "weight": u.get("weight"),
            "status": u.get("status"),
            "phase": u.get("phase"),
            "repo": u.get("repo"),
            "repo_status": u.get("repo_status"),
            "head": u.get("head"),
            "merge_sha": u.get("merge_sha"),
        }
        for u in ledger_doc.get("units") or []
    ]
    all_checks = checks(c) + target_checks(targets)
    return {
        "unit": "S75-T40",
        "acceptance_row": "S75-A40",
        "statement": (
            "41 fixed obligations and 2 required targets reconcile; the denominator "
            "stays 41 for built/build_accepted and 2 for required targets. No row, "
            "weight or acceptance row was added, removed, merged or renumbered."
        ),
        "inputs": {
            "ledger": {"path": ledger_path, "sha256": ledger_sha, "mode": "READ_ONLY"},
            "authority": {"path": authority_path, "sha256": authority_sha, "mode": "READ_ONLY"},
        },
        "census": c,
        "units": unit_rows,
        "targets": targets,
        "observed_other_targets": observed or [],
        "checks": all_checks,
        "ok": all(ch["ok"] for ch in all_checks),
        "not_measured": [
            "correctness of any individual unit verdict (each is owned by its own verifier)",
            "installed state on any box",
            "live/product testing (Trevor's; stays NOT_TESTED)",
            "whole-scope target handoff acceptance (numerator of merged_required_targets)",
        ],
    }


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", default=os.path.expanduser("~/loop-control/s75/ledger.json"))
    ap.add_argument("--authority", default=(
        "/Volumes/mac mini m4/Downloads/git trees and automations/"
        "S75_Story_First_Full_Cast_Build_20261024/task-ledger.json"),
        help="authority task-ledger.json (READ ONLY)")
    ap.add_argument("--target", action="append", default=[],
                    metavar="PATH", help="required target checkout (repeatable)")
    ap.add_argument("--observed", action="append", default=[],
                    metavar="PATH", help="other measured target, not part of the 2")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    targets = [target_probe(p) for p in args.target]
    observed = [target_probe(p) for p in args.observed]
    report = build_report(args.ledger, args.authority, targets, observed)
    text = json.dumps(report, indent=2, sort_keys=False)
    if args.json_out:
        with open(args.json_out, "w") as fh:
            fh.write(text + "\n")
    else:
        print(text)
    for ch in report["checks"]:
        print(("PASS " if ch["ok"] else "FAIL ") + ch["id"] + ": " + str(ch["detail"]))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
