#!/usr/bin/env python3
"""quarantine_ledger.py - acknowledge files as OUT of the pipeline (Skill 71, 1.3.44).

  quarantine_ledger.py add --run DIR --path REL --reason TEXT --approver NAME [--key-file F]
  quarantine_ledger.py add --run DIR --paths-file LIST --reason TEXT --approver NAME
  quarantine_ledger.py acknowledge-input --run DIR --path REL --old-sha256 H --new-sha256 H
                       --reason TEXT --approver NAME [--key-file F]
  quarantine_ledger.py seal --run DIR [--adopt-legacy [--yes]] [--key-file F]
  quarantine_ledger.py reanchor --run DIR --confirm-recreated-run --reason TEXT --approver NAME
                       [--key-file F]
  quarantine_ledger.py rebind --run DIR --path REL --stage STAGE --reason TEXT --approver NAME
                       [--key-file F]
  quarantine_ledger.py release-quarantine --run DIR --path REL --stage STAGE --reason TEXT
                       --approver NAME [--key-file F]
  quarantine_ledger.py reown --run DIR --path REL --owner-stage STAGE --reason TEXT
                       --approver NAME [--key-file F]
  quarantine_ledger.py status --run DIR

1.3.48 (SWB-250): every signed record (quarantine entry, seal, release, reown, rebind,
acknowledgement, admission row) names its RUN inside the signed payload (the resolved run root
and the run_id private/state.json holds) and is void in any other run. When the operator's seal
anchor outside the run exists, an absent ledger, an absent or unreadable seal refuses; it is never
read as "nothing quarantined". `rebind` is the owner's signed re-attestation of a REGISTERED file
whose bytes changed since the gate attested them (the copy file): bound to run, path, old and new
sha256, owning stage, reason, approver, time and an evidence note; void when the sha256 changes;
an owner decision that every admission decision lists. A pre-1.3.48 ledger is adopted once with
`seal --adopt-legacy`; pre-1.3.48 release, reown and acknowledgement records are void and re-signed.

1.3.49 (SWB-260): the operator's anchor outside the run is KEY-SIGNED and holds the run_id taken
from state.json at its first creation (plus a generation and the serial). state.json's run_id must
equal the anchor's, and every record's own run_id; rewriting state.json to another value cannot
revive a planted record of an old run. A run recreated at the same path is refused until the
operator runs `reanchor --confirm-recreated-run` (prints old run_id/serial/generation and the new
run_id; writes generation+1 and a signed retired list that voids every record of the old run_id);
verifiers never create or replace an anchor. `seal --adopt-legacy` prints every path and sha256 it
re-signs and, run non-interactively, refuses unless `--yes` is given (interactive: asks y/N).

`add` signs each entry (HMAC-SHA256) with the operator key named by
SF_PIN_AUTHORITY_KEY_FILE (or --key-file); the key is read by path and never printed.
A quarantined file is acknowledged as out-of-pipeline and STAYS out: it can never be
registered, closed or delivered, and a changed or unsigned entry leaves it ungoverned.
THREAT MODEL M (1.3.47): an actor can write any file in the run folder but does not hold the
operator key, so only key-signed records and the gate's pass-stage receipts are trusted.
`seal` (once, for a ledger made before 1.3.47) signs the exact set of ledger entries; a ledger
that disagrees with its seal, or is older than the operator's anchor, honours nothing.
`release-quarantine` signs that STAGE may register and close the quarantined path over the
bytes on disk now (sign it AFTER the stage regenerated the file; the note prints the executor
record row it saw as evidence only). `reown` signs that a registered file, as it is now,
belongs to OWNER-STAGE. Both records are valid only while the file's sha256 equals the one signed.
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
    sl = sub.add_parser("seal")
    sl.add_argument("--run", required=True)
    sl.add_argument("--adopt-legacy", action="store_true")
    sl.add_argument("--yes", action="store_true",
                    help="with --adopt-legacy: re-sign without an interactive question")
    sl.add_argument("--key-file")
    ra = sub.add_parser("reanchor")
    ra.add_argument("--run", required=True)
    ra.add_argument("--confirm-recreated-run", action="store_true")
    ra.add_argument("--reason", required=True)
    ra.add_argument("--approver", required=True)
    ra.add_argument("--key-file")
    rb = sub.add_parser("rebind")
    rb.add_argument("--run", required=True)
    rb.add_argument("--path", required=True)
    rb.add_argument("--stage", required=True)
    rb.add_argument("--reason", required=True)
    rb.add_argument("--approver", required=True)
    rb.add_argument("--key-file")
    rl = sub.add_parser("release-quarantine")
    rl.add_argument("--run", required=True)
    rl.add_argument("--path", required=True)
    rl.add_argument("--stage", required=True)
    rl.add_argument("--reason", required=True)
    rl.add_argument("--approver", required=True)
    rl.add_argument("--key-file")
    ro = sub.add_parser("reown")
    ro.add_argument("--run", required=True)
    ro.add_argument("--path", required=True)
    ro.add_argument("--owner-stage", required=True)
    ro.add_argument("--reason", required=True)
    ro.add_argument("--approver", required=True)
    ro.add_argument("--key-file")
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
        if args.cmd == "reanchor":
            r = governed_runner.reanchor(args.run, confirm_recreated_run=args.confirm_recreated_run,
                                         reason=args.reason, approver=args.approver,
                                         key_file=args.key_file)
            print(r["listing"])
            print("reanchored: generation %d; every record bound to run_id %r is void"
                  % (r["generation"], r["old_run_id"]))
            return 0
        if args.cmd == "seal":
            if args.adopt_legacy:
                plan = governed_runner.seal_ledger(args.run, key_file=args.key_file,
                                                   adopt_legacy=True, dry_run=True)
                print("adopting %d legacy (1.3.47) ledger entries; each is re-signed bound to "
                      "this run:" % plan["adopted"])
                for row in plan["adopted_entries"]:
                    print("  re-signing %s sha256=%s" % (row["path"], row["sha256"]))
                if plan["adopted"]:
                    if not args.yes:
                        if sys.stdin.isatty():
                            if input("re-sign these entries? [y/N] ").strip().lower() != "y":
                                print("refused: not confirmed; nothing was signed", file=sys.stderr)
                                return 1
                        else:
                            print("refused: non-interactive run; nothing was signed (review the "
                                  "list above and pass --yes)", file=sys.stderr)
                            return 1
            r = governed_runner.seal_ledger(args.run, key_file=args.key_file,
                                            adopt_legacy=args.adopt_legacy)
            for row in r.get("adopted_entries", ()):
                print("re-signed %s sha256=%s" % (row["path"], row["sha256"]))
            print("sealed %d ledger entries, serial %d (%d adopted from 1.3.47)"
                  % (r["entries"], r["serial"], r.get("adopted", 0)))
            return 0
        if args.cmd == "rebind":
            e = governed_runner.rebind(args.run, args.path, stage=args.stage, reason=args.reason,
                                       approver=args.approver, key_file=args.key_file)
            print("rebound %s (stage %s) %s -> %s" % (e["path"], e["stage"], e["old_sha256"], e["sha256"]))
            print(e["note"])
            print("OWNER DECISION: this is not a pipeline pass; it is void if the file's sha256 changes.")
            return 0
        if args.cmd == "release-quarantine":
            e = governed_runner.release_quarantine(
                args.run, args.path, stage=args.stage, reason=args.reason,
                approver=args.approver, key_file=args.key_file)
            print("released %s to %s over sha256=%s" % (e["path"], e["stage"], e["sha256"]))
            print(e["note"])
            return 0
        if args.cmd == "reown":
            e = governed_runner.reown(
                args.run, args.path, owner_stage=args.owner_stage, reason=args.reason,
                approver=args.approver, key_file=args.key_file)
            print("re-owned %s to %s over sha256=%s" % (e["path"], e["owner_stage"], e["sha256"]))
            print(e["note"])
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
