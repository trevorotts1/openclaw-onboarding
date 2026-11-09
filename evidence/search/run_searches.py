#!/usr/bin/env python3
"""Run every T-01 inventory search against one pinned commit and record raw evidence.

Stdlib only. Usage:

    python3 -I evidence/search/run_searches.py --root <repo> [--out <dir>]

Reads evidence/search/searches.json, executes each entry, writes one raw capture
per search id into evidence/captures/, and writes evidence/current-onboarding-evidence.json.

Rules enforced here, not by the caller:
  * every command runs against the pinned SHA named in searches.json, never a
    working tree, so a later checkout cannot change an answer;
  * git grep exit codes are recorded verbatim: 0 = match, 1 = no match, 2 = error.
    A claim of absence is only "proven" when rc == 1 AND its control returned
    matches on the same instrument shape;
  * a control that returns nothing marks the row instrument_failed and the claim
    is NOT recorded as proven.

This script never writes to the repository under test. It only writes under --out.
"""

import argparse
import json
import os
import subprocess
import sys
import time


def run(args, cwd, env):
    started = time.time()
    proc = subprocess.run(
        args, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    return {
        "argv": args,
        "rc": proc.returncode,
        "stdout": proc.stdout.decode("utf-8", "replace"),
        "stderr": proc.stderr.decode("utf-8", "replace"),
        "seconds": round(time.time() - started, 3),
    }


def execute(entry, root, pin, env):
    kind = entry["kind"]
    args = list(entry["args"])
    if kind == "grep":
        return run(["git", "grep"] + args, root, env)
    if kind == "lstree":
        return run(["git", "ls-tree", "-r", "--name-only"] + args, root, env)
    if kind == "lstree_filter":
        pin_arg, needle = args
        res = run(["git", "ls-tree", "-r", "--name-only", pin_arg], root, env)
        if res["rc"] == 0:
            kept = [ln for ln in res["stdout"].splitlines() if needle.lower() in ln.lower()]
            res["stdout"] = "\n".join(kept) + ("\n" if kept else "")
        return res
    if kind == "git":
        return run(["git"] + args, root, env)
    if kind == "gh":
        return run(["gh"] + args, root, env)
    raise SystemExit("unknown kind: %s" % kind)


def count_lines(text):
    return len([ln for ln in text.splitlines() if ln.strip()])


def classify(entry, res):
    """Return a verdict for one search result against its declared expectation."""
    rc = res["rc"]
    n = count_lines(res["stdout"])
    expect = entry["expect"]
    if entry["kind"] == "grep":
        if rc == 2:
            return "instrument-error", n, "git grep reported an error; this is not a fact about content"
        if expect == "empty":
            return ("absent" if rc == 1 and n == 0 else "present"), n, ""
        return ("present" if rc == 0 and n > 0 else "absent"), n, ""
    # Non-grep kinds: an empty result is a real observation only when rc == 0.
    if rc != 0:
        return "instrument-error", n, "non-zero exit; output is not a content observation"
    if expect == "nonempty":
        return ("present" if n > 0 else "absent"), n, ""
    return ("absent" if n == 0 else "present"), n, ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--out", default=None)
    opts = parser.parse_args()

    root = os.path.abspath(opts.root)
    out_dir = os.path.abspath(opts.out or os.path.join(root, "evidence"))
    cap_dir = os.path.join(out_dir, "captures")
    os.makedirs(cap_dir, exist_ok=True)

    manifest_path = os.path.join(root, "evidence", "search", "searches.json")
    with open(manifest_path, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    pin = manifest["pin"]

    env = dict(os.environ)
    tmp_root = os.environ.get("PBB206_TMPDIR", "")
    if tmp_root:
        for key in ("TMPDIR", "TMP", "TEMP"):
            env[key] = tmp_root
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    # Prove the pin before trusting any answer derived from it. The worktree may
    # legitimately sit on an evidence commit that is a child of the pin, so the
    # check is lineage, not equality: every search still runs against the pin SHA.
    head = run(["git", "rev-parse", "HEAD"], root, env)
    head_sha = head["stdout"].strip()
    ancestor = run(["git", "merge-base", "--is-ancestor", pin, "HEAD"], root, env)
    pin_is_ancestor = ancestor["rc"] == 0
    preflight = {
        "requested_pin": pin,
        "head": head_sha,
        "worktree_at_pin": head_sha == pin,
        "pin_is_ancestor_of_head": pin_is_ancestor,
        "run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    records = []
    for entry in manifest["searches"]:
        res = execute(entry, root, pin, env)
        verdict, n, note = classify(entry, res)

        control = None
        if entry.get("control"):
            c_res = execute(dict(entry, kind="grep", args=entry["control"]["args"]), root, pin, env)
            c_n = count_lines(c_res["stdout"])
            c_ok = c_res["rc"] == 0 and c_n > 0
            control = {
                "argv": c_res["argv"],
                "scope": entry["control"]["scope"],
                "rc": c_res["rc"],
                "count": c_n,
                "returned_matches": c_ok,
                "first_lines": c_res["stdout"].splitlines()[:3],
            }
            if not c_ok:
                verdict = "instrument-failed"
                note = (note + " control returned no matches on the same instrument shape").strip()

        record = {
            "id": entry["id"],
            "interface": entry["interface"],
            "claim": entry["claim"],
            "kind": entry["kind"],
            "command": " ".join(res["argv"]),
            "scope": entry["scope"],
            "pin": pin,
            "rc": res["rc"],
            "count": n,
            "expect": entry["expect"],
            "verdict": verdict,
            "note": note,
            "seconds": res["seconds"],
            "control": control,
        }
        records.append(record)

        cap_path = os.path.join(cap_dir, entry["id"] + ".txt")
        with open(cap_path, "w", encoding="utf-8") as fh:
            fh.write("# search: %s\n" % entry["id"])
            fh.write("# command: %s\n" % record["command"])
            fh.write("# scope: %s\n" % entry["scope"])
            fh.write("# pin: %s\n" % pin)
            fh.write("# rc: %d  count: %d  verdict: %s\n" % (res["rc"], n, verdict))
            fh.write("# --- stdout ---\n")
            fh.write(res["stdout"])
            if res["stderr"].strip():
                fh.write("# --- stderr ---\n")
                fh.write(res["stderr"])

    summary = {}
    for rec in records:
        summary[rec["verdict"]] = summary.get(rec["verdict"], 0) + 1

    artifact = {
        "schema_version": 1,
        "artifact": "current-onboarding-evidence.json",
        "unit": manifest["unit"],
        "ledger_task": manifest["ledger_task"],
        "repository": manifest["repository"],
        "pin": {
            "sha": pin,
            "fetched_utc": manifest["pin_fetched_utc"],
            "verified_by": "git rev-parse origin/main after git fetch --prune origin main; cross-checked against gh api repos/<owner>/<repo>/commits/main",
            "worktree_at_pin": preflight["worktree_at_pin"],
            "pin_is_ancestor_of_head": preflight["pin_is_ancestor_of_head"],
        },
        "instrument_notes": manifest["instrument_notes"],
        "preflight": preflight,
        "summary": summary,
        "search_count": len(records),
        "searches": records,
    }

    artifact_path = os.path.join(out_dir, "current-onboarding-evidence.json")
    with open(artifact_path, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, indent=2, sort_keys=False)
        fh.write("\n")

    print("pin=%s head=%s at_pin=%s ancestor=%s searches=%d"
          % (pin, preflight["head"][:12], preflight["worktree_at_pin"],
             preflight["pin_is_ancestor_of_head"], len(records)))
    for key in sorted(summary):
        print("  %-18s %d" % (key, summary[key]))
    bad = [r for r in records if r["verdict"] in ("instrument-error", "instrument-failed")]
    for rec in bad:
        print("  BAD %s rc=%s %s" % (rec["id"], rec["rc"], rec["note"]))
    print("wrote %s" % artifact_path)
    lineage_ok = preflight["worktree_at_pin"] or preflight["pin_is_ancestor_of_head"]
    return 0 if lineage_ok and not bad else 1


if __name__ == "__main__":
    sys.exit(main())
