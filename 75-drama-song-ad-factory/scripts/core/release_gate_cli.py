#!/usr/bin/env python3
"""S75-X11 wiring seam: the call an installer/updater makes before it touches a box.

`apply_release_gate.py` is the check; nothing in the product called it. This is
the one call site: a caller that is about to APPLY a change (before it creates
any backup or copies any file) or to RELEASE one runs this and honours the exit
status. Stdlib only. No backup, no copy, no write: it reads records a caller
hands it and returns the gate's decision.

  python3 scripts/core/release_gate_cli.py apply   --records DIR
  python3 scripts/core/release_gate_cli.py release --records DIR

DIR may hold these JSON files; a missing file is passed to the gate as None,
which is a named refusal, never a default allow:

  target.json                 {repository, skill_root, target_id, kind, tree_digest}
  backup-authorization.json   s75.x11.backup-authorization/v1
  preservation.json           s75.x11.targeted-preservation/v1
  reviewed-manifest.json      s75.x11.reviewed-manifest/v1
  applied-verification.json   s75.x11.applied-tree-verification/v1  (release only)
  operator-decision.json      {installed_apply: bool}               (installed only)

Exit: 0 allow; 3 PER_FILE_SHA_MISMATCH; 4 BACKUP_MISSING_CHANGED_FILE;
5 ORIGINAL_WORK_DELETED; 2 any other refusal or unusable input.

Not wired into install.sh / update-skills.sh: those are fleet-wide shared
controls and flipping them fail-closed is an owner decision (see the PR).
"""
import argparse
import importlib.util
import json
import os
import sys

EXITS = {
    "PER_FILE_SHA_MISMATCH": 3,
    "BACKUP_MISSING_CHANGED_FILE": 4,
    "ORIGINAL_WORK_DELETED": 5,
}
TARGET_FIELDS = ("repository", "skill_root", "target_id", "kind", "tree_digest")
HERE = os.path.dirname(os.path.abspath(__file__))


def load_gate(path):
    spec = importlib.util.spec_from_file_location("apply_release_gate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_record(records_dir, name):
    path = os.path.join(records_dir, name)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("apply", "release"))
    parser.add_argument("--records", required=True,
                        help="directory holding the target and record files")
    parser.add_argument("--gate-module",
                        default=os.path.join(HERE, "apply_release_gate.py"))
    args = parser.parse_args(argv)

    gate = load_gate(args.gate_module)
    target_doc = read_record(args.records, "target.json")
    if not isinstance(target_doc, dict) or not all(k in target_doc for k in TARGET_FIELDS):
        print("REFUSED MISSING_TARGET: no usable target.json in %s"
              % args.records, file=sys.stderr)
        return 2

    try:
        target = gate.Target(*(target_doc[k] for k in TARGET_FIELDS))
        common = {
            "operator_decision": read_record(args.records, "operator-decision.json"),
            "preservation": read_record(args.records, "preservation.json"),
            "reviewed_manifest": read_record(args.records, "reviewed-manifest.json"),
        }
        backup_authorization = read_record(args.records, "backup-authorization.json")
        if args.command == "apply":
            decision = gate.check_apply(target, backup_authorization, **common)
        else:
            decision = gate.check_release(
                target, backup_authorization,
                read_record(args.records, "applied-verification.json"), **common)
    except gate.GateRefusal as refusal:
        print("REFUSED %s: %s" % (refusal.code, refusal.detail), file=sys.stderr)
        return EXITS.get(refusal.code, 2)

    print(json.dumps(decision, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
