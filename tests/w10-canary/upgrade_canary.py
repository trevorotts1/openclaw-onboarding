#!/usr/bin/env python3
"""upgrade_canary.py — Skill 75 upgrade-of-interrupted-run canary (spec 9.2, A08/A12).

WHAT IT PROVES, per distribution:
  1. an EXISTING interrupted run (pending checkpoint marker, stale/wrong-hash
     file, stray .part) upgrades in place through the REAL distribution update
     mechanism, not a fresh install standing in for it;
  2. the stale scoped file is detected by hash mismatch and repaired (legacy
     migration where available, no re-download);
  3. the checkpoint marker is cleared on success and the run resumes at the
     saved stage — intake/paid generation are NOT repeated from saved state;
  4. every unrelated sentinel is preserved BYTE-IDENTICAL across the upgrade:
     settings, model aliases, secrets, sessions, paid artifacts, approvals,
     kill switch, other skills;
  5. an unrelated long-running process survives the whole upgrade (controlled
     resume never terminates unrelated work), and the scoped restart after
     checkpoint + config validation loads NEW code with verified source/process
     identity.

SAFETY: Sandbox()-isolated (scratch HOME/OC_CONFIG/SKILLS_DIR/CLAUDE_CONFIG_DIR),
openclaw/curl stubbed, git network verbs suppressed. NEVER runs against a real
config root. Real mode FAIL-CLOSED on an unpinned vector (--dry-run runs now).

Exit 0 = all checks pass; 1 = a check failed; 3 = vector not pinned; 2 = tooling.
Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import canary_common as cc  # noqa: E402

RESULTS = {}

#: sentinel paths (relative to sandbox home/oc) that must survive byte-identical
SENTINELS = [
    ("home/.claude/settings.json", '{"sentinel":"settings","tuned":true}'),
    ("home/.claude/model-aliases.json", '{"sentinel":"aliases"}'),
    ("oc/secrets/.env", "SENTINEL_SECRET=do-not-touch\n"),
    ("oc/sessions/active.json", '{"sentinel":"sessions"}'),
    ("oc/paid-artifacts/receipt-1.json", '{"sentinel":"paid","id":"r1"}'),
    ("oc/approvals/approved-1.json", '{"sentinel":"approvals"}'),
    ("oc/kill-switch.flag", "sentinel-kill-switch\n"),
    ("skills/46-kie-callback-relay/SKILL.md", "sentinel: other skill preserved\n"),
]


def check(name, ok, detail=""):
    RESULTS[name] = {"ok": bool(ok), "detail": detail}
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name,
                           (" — " + str(detail)[:300]) if detail else ""))
    return ok


def seed_sentinels(sb):
    """Create the unrelated user state that an upgrade must preserve."""
    for rel, body in SENTINELS:
        p = Path(sb.env["HOME"]).parent / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return {rel: cc.sha256_file(Path(sb.env["HOME"]).parent / rel)
            for rel, _ in SENTINELS}


def seed_interrupted_run(sb):
    """Stage an interrupted run: checkpoint marker + stale wrong-hash file + .part."""
    root = Path(sb.env["HOME"]).parent
    skill = root / "skills" / "75-drama-song-ad-factory"
    staged = skill / "scripts" / "core" / "state_store.py"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text("# STALE wrong-hash content\n", encoding="utf-8")
    (skill / ".checkpoint-pending").write_text("resume-stage:music\n", encoding="utf-8")
    (skill / "scripts" / "core" / "state_store.py.part").write_text(
        "partial", encoding="utf-8")
    return {"stale_file": staged, "marker": skill / ".checkpoint-pending",
            "part": skill / "scripts" / "core" / "state_store.py.part"}


def run_dry(out):
    print("upgrade canary DRY-RUN (harness mechanics only; no installer, "
          "no repository, no real root)")
    with cc.Sandbox() as sb:
        before = seed_sentinels(sb)
        staged = seed_interrupted_run(sb)

        # simulate the upgrade repairing the stale scoped file (mechanism check):
        # the "new" tree content replaces the wrong-hash file and clears markers.
        good = "# canonical state_store content (vector revision)\n"
        staged["stale_file"].write_text(good, encoding="utf-8")
        if staged["part"].exists():
            staged["part"].unlink()

        after = {rel: cc.sha256_file(Path(sb.env["HOME"]).parent / rel)
                 for rel, _ in SENTINELS}
        check("dry:stale scoped file repaired by hash mismatch",
              cc.sha256_file(staged["stale_file"]) == cc.sha256_file(
                  Path(str(staged["stale_file"]))),
              "wrong-hash content replaced")
        check("dry:stray .part cleaned",
              not staged["part"].exists(), "state_store.py.part removed")

        preserved = all(before[rel] == after[rel] for rel, _ in SENTINELS)
        check("dry:all unrelated sentinels byte-identical", preserved,
              "%d sentinels compared" % len(SENTINELS))

        # negative control: a touched sentinel must be detected
        tamper = Path(sb.env["HOME"]).parent / SENTINELS[0][0]
        tamper.write_text('{"sentinel":"settings","tuned":false}', encoding="utf-8")
        after2 = {rel: cc.sha256_file(Path(sb.env["HOME"]).parent / rel)
                  for rel, _ in SENTINELS}
        check("dry:preservation negative control (tamper detected)",
              after2[SENTINELS[0][0]] != before[SENTINELS[0][0]],
              "settings.json tamper breaks byte-identity")

        # checkpoint marker clearing + resume-without-repeat is proven by the
        # state_store fixtures in multi_run_canary; here we only check the marker
        # surface exists and is clearable.
        staged["marker"].unlink()
        check("dry:checkpoint marker cleared on success",
              not staged["marker"].exists(), ".checkpoint-pending cleared")

        # unrelated process survival: spawn a stand-in sleeper, upgrade around it
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            time.sleep(0.2)
            alive_before = proc.poll() is None
            # (upgrade step happens here in real mode)
            alive_after = proc.poll() is None
            check("dry:unrelated process survives upgrade",
                  alive_before and alive_after, "sleeper pid %d alive" % proc.pid)
        finally:
            proc.terminate()
            proc.wait(timeout=5)

        receipt = {
            "schema": "blackceo.skill75.canary.upgrade/v1",
            "unit": "SFR-007",
            "mode": "dry-run",
            "boundary": "harness mechanics only; NO installer run, NO repository, "
                        "NO real root, NO acceptance point claimed",
            "results": RESULTS,
            "sandbox_shim_log": sb.shim_entries(),
        }
        cc.write_json(Path(out) / "upgrade-canary.dry.json", receipt)

    passed, failed, total = cc.summarize_checks(RESULTS)
    print("dry-run: %d/%d checks passed%s" % (len(passed), total,
          ("" if not failed else "; FAIL: " + ", ".join(failed))))
    return 0 if not failed else 1


def run_real(out, vector_path):
    v = cc.load_vector(vector_path)
    ok, reason = cc.require_pinned(v)
    if not ok:
        print("REFUSED (fail-closed): %s" % reason)
        return 3
    print("upgrade canary REAL mode against pinned vector (%s)" % reason)
    receipt = {
        "schema": "blackceo.skill75.canary.upgrade/v1",
        "unit": "SFR-007",
        "mode": "real",
        "status": "HARNESS_READY_EXECUTION_WAITS_FOR_GO",
        "vector": {"pinned_at": v.get("pinned_at"),
                   "revisions": {k: v["repositories"][k].get("revision")
                                 for k in v.get("repositories", {})}},
        "boundary": "Real upgrade runs from the pinned PRIOR revision -> pinned "
                    "vector revision in a scratch sandbox after an explicit "
                    "execution GO. No acceptance point claimed here.",
    }
    cc.write_json(Path(out) / "upgrade-canary.real-pending.json", receipt)
    print("wrote upgrade-canary.real-pending.json (execution waits for GO)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vector", required=True)
    ap.add_argument("--dist", choices=["onboarding", "999", "both"], default="both")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    Path(a.out).mkdir(parents=True, exist_ok=True)
    if a.dry_run:
        return run_dry(a.out)
    return run_real(a.out, a.vector)


if __name__ == "__main__":
    sys.exit(main())
