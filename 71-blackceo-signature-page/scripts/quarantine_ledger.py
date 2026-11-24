#!/usr/bin/env python3
"""quarantine_ledger.py - acknowledge files as OUT of the pipeline (Skill 71, 1.3.44).

  quarantine_ledger.py add --run DIR --path REL --reason TEXT --approver NAME [--key-file F]
  quarantine_ledger.py add --run DIR --paths-file LIST --reason TEXT --approver NAME
  quarantine_ledger.py acknowledge-input --run DIR --path REL --old-sha256 H --new-sha256 H
                       --reason TEXT --approver NAME [--key-file F]
  quarantine_ledger.py status --run DIR

`add` signs each entry (HMAC-SHA256) with the operator key named by
SF_PIN_AUTHORITY_KEY_FILE (or --key-file); the key is read by path and never printed.
A quarantined file is acknowledged as out-of-pipeline and STAYS out: it can never be
registered, closed or delivered, and a changed or unsigned entry leaves it ungoverned.
`acknowledge-input` (1.3.46) signs a record in private/input-acknowledgements.json that a declared
input (the brand profile named by intake.json brand_file) legitimately changed; a paid dispatch
with a changed input is refused without one, and the record is valid only while the file's
sha256 equals --new-sha256. Nothing is moved, deleted or edited. `status` prints the scan counts, quarantined included.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import governed_runner  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add")
    add.add_argument("--run", required=True)
    add.add_argument("--path", action="append", default=[])
    add.add_argument("--paths-file")
    add.add_argument("--reason", required=True)
    add.add_argument("--approver", required=True)
    add.add_argument("--key-file")
    ack = sub.add_parser("acknowledge-input")
    ack.add_argument("--run", required=True)
    ack.add_argument("--path", required=True)
    ack.add_argument("--old-sha256", required=True)
    ack.add_argument("--new-sha256", required=True)
    ack.add_argument("--reason", required=True)
    ack.add_argument("--approver", required=True)
    ack.add_argument("--key-file")
    st = sub.add_parser("status")
    st.add_argument("--run", required=True)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "add":
            paths = list(args.path)
            if args.paths_file:
                paths += [ln.strip() for ln in Path(args.paths_file).read_text(
                    encoding="utf-8").splitlines() if ln.strip()]
            if not paths:
                print("no path given", file=sys.stderr)
                return 2
            for rel in paths:
                e = governed_runner.quarantine(args.run, rel, reason=args.reason,
                                               approver=args.approver, key_file=args.key_file)
                print("quarantined %s sha256=%s size=%d" % (e["path"], e["sha256"], e["size"]))
            return 0
        if args.cmd == "acknowledge-input":
            e = governed_runner.acknowledge_input(
                args.run, args.path, old_sha256=args.old_sha256, new_sha256=args.new_sha256,
                reason=args.reason, approver=args.approver, key_file=args.key_file)
            print("acknowledged %s %s -> %s" % (e["path"], e["old_sha256"], e["new_sha256"]))
            return 0
        result = governed_runner.scan(args.run)
        print(json.dumps({
            "ok": result["ok"], "governed": len(result["governed"]),
            "ungoverned": len(result["ungoverned"]),
            "content_mismatch": len(result["content_mismatch"]),
            "quarantined": len(result.get("quarantined", ())),
        }, sort_keys=True))
        return 0
    except (ValueError, OSError) as exc:
        print("refused: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
