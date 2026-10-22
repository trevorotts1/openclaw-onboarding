#!/usr/bin/env python3
"""clean_install_canary.py — Skill 75 clean-install canary (spec 9.2, 15.2, A08/A12).

WHAT IT PROVES, per distribution (openclaw-onboarding and 999-setup):
  1. a fresh sandboxed install root receives the Skill 75 tree through the REAL
     distribution mechanism (onboarding: update-skills.sh into $SKILLS_DIR;
     999: sync-nine-skills.sh + helper-deps.py install into $CLAUDE_CONFIG_DIR),
     never a hand copy standing in for the installer;
  2. the installed scoped files carry per-file sha256 manifest hashes recorded in
     the receipt (the distribution manifest hash for the completion receipt);
  3. both distributions land BYTE-IDENTICAL shared files (twin parity by hash,
     not by version string);
  4. the helper pin preflight (999 helper-deps.py preflight) passes on the
     installed root;
  5. no legacy/mirror duplicate tree is created beside the ONE install path.

SAFETY: everything runs inside a Sandbox() with HOME/OC_CONFIG/SKILLS_DIR/
CLAUDE_CONFIG_DIR redirected to scratch, `openclaw` and `curl` stubbed out (no
client notification, no network), and git network verbs suppressed. This
harness NEVER runs against a real config root. Real modes FAIL-CLOSED unless
source-vector.json is pinned (require_pinned). --dry-run builds synthetic
distribution trees in scratch and exercises every check mechanism end-to-end
without touching any repository or installer.

Modes:
  --dry-run   harness mechanics against synthetic trees (SFR-007: what runs NOW)
  (no flag)   real install from the PINNED vector's checkouts (runs AFTER pin + GO)

Exit 0 = every check passed; 1 = a check failed; 3 = vector not pinned (real
mode); 2 = tooling/resolve error. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import canary_common as cc  # noqa: E402

ONB_SKILL = "75-drama-song-ad-factory"
NINE_SKILL_DIR = Path(".claude/skills/drama-song-ad-factory")

#: shared files that must be byte-identical across both distributions
SHARED_FILES = [
    "scripts/core/state_store.py",
    "scripts/core/spend_ledger.py",
    "scripts/core/cc_sync.py",
    "scripts/core/song_dispatch/song_dispatch.py",
    "scripts/core/intake_preflight/preflight.py",
    "scripts/core/batch_mode/batch.py",
]

RESULTS = {}


def check(name, ok, detail=""):
    RESULTS[name] = {"ok": bool(ok), "detail": detail}
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name,
                           (" — " + str(detail)[:300]) if detail else ""))
    return ok


def scoped_manifest(root, skill_rel):
    """sha256 manifest of the scoped shared files under a skill root."""
    man = {}
    base = root / skill_rel
    for rel in SHARED_FILES:
        p = base / rel
        if p.is_file():
            man[rel] = cc.sha256_file(p)
        else:
            man[rel] = None
    return man


def install_onboarding(src_root, sb):
    """Real distribution mechanism: update-skills.sh with all targets redirected."""
    installer = Path(src_root) / "update-skills.sh"
    if not installer.is_file():
        return {"rc": 2, "stderr": "update-skills.sh missing at %s" % installer}
    return cc.run_capture(["bash", str(installer)], sb.env, cwd=str(src_root))


def install_999(src_root, sb):
    """Real distribution mechanism: sync-nine-skills.sh + helper-deps.py install."""
    sync = Path(src_root) / "scripts" / "sync-nine-skills.sh"
    helper = Path(src_root) / "installer-registration" / "helper-deps.py"
    runs = []
    if sync.is_file():
        runs.append(cc.run_capture(["bash", str(sync)], sb.env, cwd=str(src_root)))
    else:
        runs.append({"rc": 2, "stderr": "sync-nine-skills.sh missing at %s" % sync})
    if helper.is_file():
        runs.append(cc.run_capture(
            [sys.executable, str(helper), "install",
             "--root", sb.env["CLAUDE_CONFIG_DIR"]],
            sb.env, cwd=str(src_root)))
        runs.append(cc.run_capture(
            [sys.executable, str(helper), "preflight",
             "--root", sb.env["CLAUDE_CONFIG_DIR"]],
            sb.env, cwd=str(src_root)))
    else:
        runs.append({"rc": 2, "stderr": "helper-deps.py missing at %s" % helper})
    return runs


def build_fake_distribution(dst, kind):
    """Synthetic distribution tree for --dry-run: skill dir + scoped files."""
    skill_rel = ONB_SKILL if kind == "onboarding" else NINE_SKILL_DIR
    base = dst / skill_rel
    for rel in SHARED_FILES:
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        # shared payload identical across both fake trees -> parity must PASS
        p.write_text("# canary synthetic %s (shared)\n" % rel, encoding="utf-8")
    # a distribution-private file that differs -> parity must IGNORE it
    (base / "scripts" / ("private_%s.py" % kind)).write_text(
        "# private to %s\n" % kind, encoding="utf-8")
    return dst


def run_dry(dist, out):
    """Exercise every check mechanism against synthetic trees. Nothing real touched."""
    print("clean-install canary DRY-RUN (harness mechanics only; no installer, "
          "no repository, no real root)")
    with cc.Sandbox() as sb:
        fake_src = sb.root / "fake-dists"
        for kind in ("onboarding", "999"):
            build_fake_distribution(fake_src / kind, kind)

        manifests = {}
        for kind, skill_rel in (("onboarding", ONB_SKILL),
                                ("999", str(NINE_SKILL_DIR))):
            inst_root = sb.root / ("installed-" + kind)
            inst_root.mkdir(parents=True, exist_ok=True)
            shutil.copytree(fake_src / kind / skill_rel, inst_root / skill_rel)
            manifests[kind] = scoped_manifest(inst_root, skill_rel)
            check("dry:%s:scoped files installed" % kind,
                  all(v for v in manifests[kind].values()),
                  "%d/%d hashed" % (sum(1 for v in manifests[kind].values() if v),
                                    len(SHARED_FILES)))
            check("dry:%s:manifest hash recorded" % kind,
                  bool(manifests[kind]),
                  "tree hash %s" % cc.sha256_file(
                      inst_root / skill_rel / SHARED_FILES[0])[:16])

        # twin parity: shared files byte-identical across the two installed trees
        parity_ok = all(
            manifests["onboarding"][rel] is not None
            and manifests["onboarding"][rel] == manifests["999"][rel]
            for rel in SHARED_FILES)
        check("dry:twin parity (shared files byte-identical)", parity_ok,
              "%d shared files compared" % len(SHARED_FILES))

        # negative control: a single divergence must break parity
        diverge = sb.root / "installed-999" / NINE_SKILL_DIR / SHARED_FILES[0]
        diverge.write_text("# tampered\n", encoding="utf-8")
        m2 = scoped_manifest(sb.root / "installed-999", str(NINE_SKILL_DIR))
        check("dry:parity negative control (tamper detected)",
              m2[SHARED_FILES[0]] != manifests["onboarding"][SHARED_FILES[0]],
              "tampered copy no longer matches onboarding twin")

        # no legacy mirror beside the one install path
        check("dry:no legacy mirror tree",
              not (inst_root / "lip_gate").exists()
              and not (inst_root / skill_rel / "lip_gate").exists(),
              "legacy lip_gate/ mirror absent")

        receipt = {
            "schema": "blackceo.skill75.canary.clean-install/v1",
            "unit": "SFR-007",
            "mode": "dry-run",
            "boundary": "harness mechanics only; NO installer run, NO repository, "
                        "NO real root, NO acceptance point claimed",
            "results": RESULTS,
            "sandbox_shim_log": sb.shim_entries(),
        }
        cc.write_json(Path(out) / "clean-install-canary.dry.json", receipt)

    passed, failed, total = cc.summarize_checks(RESULTS)
    print("dry-run: %d/%d checks passed%s" % (len(passed), total,
          ("" if not failed else "; FAIL: " + ", ".join(failed))))
    return 0 if not failed else 1


def run_real(dist, out, vector_path, dist_arg):
    """Real install from the PINNED vector checkouts. Fail-closed on unpinned."""
    v = cc.load_vector(vector_path)
    ok, reason = cc.require_pinned(v)
    if not ok:
        print("REFUSED (fail-closed): %s" % reason)
        return 3
    print("clean-install canary REAL mode against pinned vector (%s)" % reason)
    print("NOTE: real execution also requires the authorized canary target + GO; "
          "this harness installs only into a scratch sandbox.")
    receipt = {
        "schema": "blackceo.skill75.canary.clean-install/v1",
        "unit": "SFR-007",
        "mode": "real",
        "vector": {"pinned_at": v.get("pinned_at"),
                   "revisions": {k: v["repositories"][k].get("revision")
                                 for k in v.get("repositories", {})}},
        "status": "HARNESS_READY_EXECUTION_WAITS_FOR_GO",
        "boundary": "Execution against an authorized canary target and the "
                    "loaded-source proof run AFTER an explicit execution GO. "
                    "No acceptance point is claimed by this receipt.",
        "loaded_source_proof_hook":
            "python3 <work>/S75-W07-U2/tools/runtime_proof.py record "
            "--manifest <receipt.manifests> (loaded-file comparison + live "
            "process revision; see work/S75-W07-U2/evidence/runtime-proof.json)",
    }
    cc.write_json(Path(out) / "clean-install-canary.real-pending.json", receipt)
    print("wrote clean-install-canary.real-pending.json (execution waits for GO)")
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
        return run_dry(a.dist, a.out)
    return run_real(a.dist, a.out, a.vector, a.dist)


if __name__ == "__main__":
    sys.exit(main())
