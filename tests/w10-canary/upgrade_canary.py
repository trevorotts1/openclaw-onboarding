#!/usr/bin/env python3
"""upgrade_canary.py — Skill 75 upgrade-of-interrupted-run canary (spec 9.2, A08/A12).

WHAT IT PROVES, per distribution:
  1. an EXISTING installed tree at the PRIOR revision upgrades in place to the
     PINNED revision through the REAL distribution update mechanism, not a fresh
     install standing in for it;
  2. the upgrade delivers exactly the file difference between the two pinned
     source revisions — added / changed / removed sets with digests — and the
     installed result equals the pinned source;
  3. every unrelated sentinel is preserved BYTE-IDENTICAL across the upgrade:
     settings, model aliases, secrets, sessions, paid artifacts, approvals,
     kill switch, other skills;
  4. an unrelated long-running process that really exists survives the whole
     upgrade (controlled resume never terminates unrelated work).

The old harness hashed the SAME path on both sides at :102-105, so that check
could never fail. Here the two sides are DIFFERENT artifacts: the installed file
BEFORE the upgrade against the PINNED SOURCE file AFTER it, plus the recomputed
installed manifest. Process survival is measured around an upgrade that actually
runs.

SAFETY: Sandbox()-isolated (scratch HOME/OC_CONFIG/SKILLS_DIR/CLAUDE_CONFIG_DIR),
openclaw/curl stubbed, `git clone` answered from a tree materialized at the exact
revision. NEVER runs against a real config root. Real mode FAIL-CLOSED on an
unpinned vector (--dry-run runs now). A11 stays blocked: no paid provider call,
no live channel send, both refused with a typed code.

Exit 0 = all checks pass; 1 = a check failed; 2 = tooling/resolve; 3 = vector
not pinned; 4 = refused by policy (A11). Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import canary_common as cc  # noqa: E402
import clean_install_canary as ci  # noqa: E402  (same lane, same installers)

RESULTS = {}

#: sentinel paths (relative to the sandbox root) that must survive byte-identical
SENTINELS = [
    ("home/.claude/settings.json", '{"sentinel":"settings","tuned":true}'),
    ("home/.claude/model-aliases.json", '{"sentinel":"aliases"}'),
    ("oc/secrets/.env", "SENTINEL_SECRET=do-not-touch\n"),
    ("oc/sessions/active.json", '{"sentinel":"sessions"}'),
    ("oc/paid-artifacts/receipt-1.json", '{"sentinel":"paid","id":"r1"}'),
    ("oc/approvals/approved-1.json", '{"sentinel":"approvals"}'),
    ("oc/kill-switch.flag", "sentinel-kill-switch\n"),
]

REFUSALS = {
    "VECTOR_UNPINNED": 3,
    "SOURCE_CHECKOUT_UNRESOLVED": 2,
    "REVISION_NOT_LOCAL": 2,
    "PRIOR_REVISION_UNRESOLVED": 2,
    "INSTALLER_LOCK_HELD": 2,
    "INSTALLER_FAILED": 1,
    "A11_PAID_PROVIDER_CALL": 4,
    "A11_LIVE_CHANNEL_SEND": 4,
}


def check(name, ok, detail=""):
    RESULTS[name] = {"ok": bool(ok), "detail": detail}
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name,
                           (" — " + str(detail)[:300]) if detail else ""))
    return ok


def refuse(code, detail, out=None, mode="real"):
    if code not in REFUSALS:
        code = "INSTALLER_FAILED"
    print("REFUSED [%s]: %s" % (code, detail))
    if out:
        cc.write_json(Path(out) / ("upgrade-canary.%s.refused.json" % mode), {
            "schema": "blackceo.skill75.canary.upgrade/v1",
            "unit": "SFR-007",
            "mode": mode,
            "status": "REFUSED",
            "refusal": {"code": code, "detail": detail},
        })
    return REFUSALS[code]


# --------------------------------------------------------------- fixtures ----
def seed_sentinels(sb, skills_root=None):
    """Create the unrelated user state that an upgrade must preserve.

    `skills_root` is the real installed skills root for this distribution, so the
    "another skill" sentinel sits inside the tree the installer actually writes
    to instead of beside it.
    """
    entries = list(SENTINELS)
    if skills_root is not None:
        rel = Path(skills_root) / "46-kie-callback-relay" / "SKILL.md"
        entries.append((str(rel), "sentinel: other skill preserved\n"))
    for rel, body in entries:
        p = Path(rel) if Path(rel).is_absolute() else Path(sb.root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return {rel: cc.sha256_file(Path(rel) if Path(rel).is_absolute()
                                else Path(sb.root) / rel)
            for rel, _ in entries}, [rel for rel, _ in entries]


def sentinel_digests(sb, rels):
    return {rel: cc.sha256_file(Path(rel) if Path(rel).is_absolute()
                                else Path(sb.root) / rel) for rel in rels}


def seed_interrupted_run(sb, install_root):
    """Stage an interrupted run inside the real install root: checkpoint marker,
    stale wrong-hash file, stray .part."""
    skill = Path(install_root)
    staged = skill / "scripts" / "core" / "state_store.py"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text("# STALE wrong-hash content\n", encoding="utf-8")
    (skill / ".checkpoint-pending").write_text("resume-stage:music\n", encoding="utf-8")
    (skill / "scripts" / "core" / "state_store.py.part").write_text(
        "partial", encoding="utf-8")
    return {"stale_file": staged, "marker": skill / ".checkpoint-pending",
            "part": skill / "scripts" / "core" / "state_store.py.part"}


def prior_revision(checkout, pinned, explicit=None):
    """The revision installed BEFORE the upgrade: explicit, else the parent."""
    if explicit:
        return explicit, "--prior"
    r = subprocess.run(["git", "-C", str(checkout), "rev-parse", "--verify",
                        pinned + "^"], capture_output=True, text=True)
    if r.returncode != 0:
        return None, "no parent of %s in %s" % (pinned[:12], checkout)
    return r.stdout.strip(), "pinned^"


def set_clone_source(sb, tree, rev, repo):
    """Point the sandbox git shim at a tree materialized at `rev`."""
    sb.clone_source = (str(tree), rev,
                       "https://github.com/trevorotts1/%s.git" % repo)
    cc.build_shims(sb.root / "shims", sb.shim_log, clone_source=sb.clone_source)


# ---------------------------------------------------------------- dry-run ----
def run_dry(out):
    print("upgrade canary DRY-RUN (harness mechanics only; no installer, "
          "no repository, no real root)")
    with cc.Sandbox() as sb:
        fake_root = Path(sb.root) / "skills" / "75-drama-song-ad-factory"
        before, rels = seed_sentinels(sb, fake_root.parent)
        staged = seed_interrupted_run(sb, fake_root)

        # simulate the upgrade repairing the stale scoped file (mechanism check):
        # the "new" tree content replaces the wrong-hash file and clears markers.
        good = "# canonical state_store content (vector revision)\n"
        old_digest = cc.sha256_file(staged["stale_file"])
        staged["stale_file"].write_text(good, encoding="utf-8")
        if staged["part"].exists():
            staged["part"].unlink()

        after = sentinel_digests(sb, rels)
        # DIFFERENT artifacts on each side: installed-before vs source-after
        check("dry:stale scoped file repaired by hash mismatch",
              old_digest != cc.sha256_file(staged["stale_file"]),
              "wrong-hash content %s != repaired %s"
              % (old_digest[:12], cc.sha256_file(staged["stale_file"])[:12]))
        check("dry:stray .part cleaned",
              not staged["part"].exists(), "state_store.py.part removed")

        preserved = all(before[rel] == after[rel] for rel in rels)
        check("dry:all unrelated sentinels byte-identical", preserved,
              "%d sentinels compared" % len(rels))

        # negative control: a touched sentinel must be detected
        tamper = Path(sb.root) / rels[0]
        tamper.write_text('{"sentinel":"settings","tuned":false}', encoding="utf-8")
        after2 = sentinel_digests(sb, rels)
        check("dry:preservation negative control (tamper detected)",
              after2[rels[0]] != before[rels[0]],
              "settings.json tamper breaks byte-identity")

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


# ------------------------------------------------------------------ real ----
def upgrade_one(d, repo, pin_rev, prior_rev, checkout, sb, timeout):
    """Install prior_rev, upgrade to pin_rev, and prove the difference."""
    spec = ci.DISTS[d]
    pinned_tree = sb.root / "pinned" / repo
    prior_tree = sb.root / "prior" / repo
    ok, detail = cc.materialize_revision(checkout, pin_rev, pinned_tree)
    if not ok:
        return refuse("REVISION_NOT_LOCAL", "%s: %s" % (repo, detail))
    ok, detail = cc.materialize_revision(checkout, prior_rev, prior_tree)
    if not ok:
        return refuse("PRIOR_REVISION_UNRESOLVED", "%s: %s" % (repo, detail))

    root = ci.install_root(d, sb)
    src_old = cc.manifest_tree(prior_tree / spec["source_subdir"])
    src_new = cc.manifest_tree(pinned_tree / spec["source_subdir"])
    s_added, s_changed, s_removed = cc.diff_manifests(src_old, src_new)
    check("upgrade:%s:source revisions differ" % d,
          bool(s_added or s_changed or s_removed),
          "source diff: +%d ~%d -%d between %s and %s"
          % (len(s_added), len(s_changed), len(s_removed),
             prior_rev[:12], pin_rev[:12]))

    ci.prepare_sandbox(d, sb)

    # ---- install the PRIOR revision with the real installer
    set_clone_source(sb, prior_tree, prior_rev, repo)
    runs_old = ci.install(d, prior_tree, sb, timeout=timeout)
    old_manifest = cc.manifest_tree(root)
    old_same, old_detail = cc.compare_to_source(old_manifest, src_old)
    check("upgrade:%s:prior install delivered the prior tree" % d,
          old_same, "installer rc=%s; %s"
          % ([r.get("rc") for r in runs_old], old_detail))

    # ---- user state that the upgrade promises to keep
    before, rels = seed_sentinels(sb, root.parent)
    staged = seed_interrupted_run(sb, root)

    # ---- an unrelated process that really exists across the upgrade. It must
    # outlive the whole install (a real onboarding upgrade takes minutes), or the
    # check would measure the sleeper's own timeout instead of the upgrade.
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(3600)"])
    time.sleep(0.2)
    alive_before = proc.poll() is None
    try:
        # ---- upgrade to the PINNED revision through the same real installer
        set_clone_source(sb, pinned_tree, pin_rev, repo)
        runs_new = ci.install(d, pinned_tree, sb, timeout=timeout)
        alive_after = proc.poll() is None
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    new_manifest = cc.manifest_tree(root)
    # The interrupted-run artifacts are deliberately seeded user state, not
    # installer content: they stay in the tree (preservation check below) and are
    # excluded from the content comparison so they cannot be mistaken for drift.
    for rel in (".checkpoint-pending", "scripts/core/state_store.py.part"):
        new_manifest.pop(rel, None)
    added, changed, removed = cc.diff_manifests(old_manifest, new_manifest)
    diff_detail = {
        "added": {k: new_manifest[k] for k in added},
        "changed": {k: {"from": old_manifest[k], "to": new_manifest[k]}
                    for k in changed},
        "removed": {k: old_manifest[k] for k in removed},
    }
    after = sentinel_digests(sb, rels)
    all_runs = runs_old + runs_new
    lock_held = any("LOCK HELD" in (r.get("stdout", "") + r.get("stderr", ""))
                    for r in all_runs)

    # installed result must equal the PINNED source, file for file
    new_same, new_detail = cc.compare_to_source(new_manifest, src_new)
    check("upgrade:%s:upgrade delivered the pinned tree" % d,
          new_same, "installer rc=%s; %s"
          % ([r.get("rc") for r in runs_new], new_detail))
    check("upgrade:%s:applied the source difference" % d,
          set(added) | set(changed) == set(s_added) | set(s_changed),
          "+%d ~%d -%d installed vs source +%d ~%d -%d"
          % (len(added), len(changed), len(removed),
             len(s_added), len(s_changed), len(s_removed)))

    # the old tautology, killed: installed-BEFORE vs pinned-SOURCE-AFTER must differ
    genuinely_changed = [k for k in changed if old_manifest.get(k) != src_new.get(k)]
    check("upgrade:%s:pre-upgrade bytes differ from pinned source" % d,
          bool(changed) and len(genuinely_changed) == len(changed),
          "%d/%d changed files carry a different pre-upgrade digest"
          % (len(genuinely_changed), len(changed)))

    check("upgrade:%s:sentinels preserved byte-identical" % d,
          all(before[rel] == after[rel] for rel in rels),
          "%d sentinels compared" % len(rels))
    check("upgrade:%s:unrelated process survived upgrade" % d,
          alive_before and alive_after,
          "pid %d alive before=%s after=%s" % (proc.pid, alive_before, alive_after))
    # A content install must never eat an interrupted run's resume state. The
    # clearing of the marker belongs to the state_store resume path, which
    # multi_run_canary proves; asserting it here would be a claim this harness
    # does not exercise.
    check("upgrade:%s:interrupted-run state preserved" % d,
          staged["marker"].is_file() and staged["part"].is_file(),
          ".checkpoint-pending and .part survive the content upgrade")

    seeded = (".checkpoint-pending", "scripts/core/state_store.py.part")
    vok, problems = cc.verify_manifest(root, new_manifest, ignore=seeded)
    check("upgrade:%s:manifest digests verified" % d, vok,
          "recomputed %d files" % len(new_manifest) if vok else problems[:3])

    source = {"repo": repo, "pinned_revision": pin_rev,
              "prior_revision": prior_rev, "checkout": str(checkout),
              "subdir": spec["source_subdir"]}
    manifest = cc.distribution_manifest(d, root, new_manifest, source)
    manifest_path = Path(sb.root) / ("upgrade-%s.manifest.json" % d)
    cc.write_json(manifest_path, manifest)
    proof_ok, proof_detail, proof_cmd = cc.loaded_source_proof(
        manifest_path, root, ignore=seeded)
    check("upgrade:%s:loaded-source proof hook accepts manifest" % d,
          proof_ok, proof_detail)

    return {
        "installer_prior": [{"cmd": r.get("cmd"), "rc": r.get("rc")}
                            for r in runs_old],
        "installer_pinned": [{"cmd": r.get("cmd"), "rc": r.get("rc")} for r in runs_new],
        "lock_held": lock_held,
        "installed_path": str(root),
        "source": source,
        "prior": {"file_count": len(old_manifest),
                  "manifest_sha256": cc.manifest_digest(old_manifest)},
        "pinned": {"file_count": len(new_manifest),
                   "manifest_sha256": cc.manifest_digest(new_manifest)},
        "diff": diff_detail,
        "source_diff": {"added": s_added, "changed": s_changed, "removed": s_removed},
        "ignored_paths": list(seeded),
        "manifest_path": str(manifest_path),
        "loaded_source_proof_hook": {"command": proof_cmd, "ok": proof_ok,
                                     "detail": proof_detail},
    }


def run_real(dist_arg, out, vector_path, timeout=900, sandbox_base=None,
             repo_roots=None, keep=False, prior=None):
    """Real prior->pinned upgrade from the PINNED vector. Fail-closed when unpinned."""
    v = cc.load_vector(vector_path)
    ok, reason = cc.require_pinned(v)
    if not ok:
        print("REFUSED (fail-closed): %s" % reason)
        return 3
    print("upgrade canary REAL mode against pinned vector (%s)" % reason)

    dists = ["onboarding", "999"] if dist_arg == "both" else [dist_arg]
    repo_roots = repo_roots or {}
    plans = []
    for d in dists:
        repo = ci.DISTS[d]["repo"]
        pin_rev = v["repositories"][repo].get("revision")
        path, how = ci.repo_checkout(repo, v, repo_roots)
        if not path:
            return refuse("SOURCE_CHECKOUT_UNRESOLVED",
                          "%s: no local checkout named by the vector, --repo-root "
                          "or a sibling directory" % repo, out)
        pr, pr_how = prior_revision(path, pin_rev, (prior or {}).get(d))
        if not pr:
            return refuse("PRIOR_REVISION_UNRESOLVED", "%s: %s" % (repo, pr_how), out)
        plans.append((d, repo, pin_rev, pr, path, how, pr_how))

    receipt = {
        "schema": "blackceo.skill75.canary.upgrade/v1",
        "unit": "SFR-007",
        "mode": "real",
        "vector": {"pinned_at": v.get("pinned_at"),
                   "pinned_by": v.get("pinned_by"),
                   "revisions": {k: v["repositories"][k].get("revision")
                                 for k in v.get("repositories", {})}},
        "distributions": {},
        "boundary": ("Real prior->pinned upgrade executed into a scratch sandbox "
                     "only. No paid provider call, no live channel send, no client "
                     "box, no real config root. The loaded-source proof still needs "
                     "a live process and an explicit execution GO."),
    }

    for d, repo, pin_rev, pr, checkout, how, pr_how in plans:
        print("\n[%s] upgrading %s @ %s -> %s (checkout resolved by %s, prior by %s)"
              % (d, repo, pr[:12], pin_rev[:12], how, pr_how))
        cmds = [["bash", str(checkout / ci.DISTS[d]["installer"])]
                + ci.DISTS[d]["installer_args"]]
        code, why = ci.a11_guard(cmds)
        if code:
            return refuse(code, why, out)
        with cc.Sandbox(keep=keep, base_dir=sandbox_base) as sb:
            data = upgrade_one(d, repo, pin_rev, pr, checkout, sb, timeout)
            if isinstance(data, int):
                return data
            if data.get("lock_held"):
                return refuse("INSTALLER_LOCK_HELD",
                              "another update-skills.sh holds /tmp/openclaw-update.lock",
                              out)
            data["sandbox"] = str(sb.root)
            receipt["distributions"][d] = data
            if keep:
                sb.keep = True

    passed, failed, total = cc.summarize_checks(RESULTS)
    receipt["results"] = RESULTS
    receipt["status"] = "EXECUTED" if not failed else "FAILED"
    name = ("upgrade-canary.real.json" if not failed
            else "upgrade-canary.real.failed.json")
    cc.write_json(Path(out) / name, receipt)
    print("\nreal: %d/%d checks passed%s" % (len(passed), total,
          ("" if not failed else "; FAIL: " + ", ".join(failed))))
    print("wrote %s" % name)
    return 0 if not failed else 1


# --------------------------------------------------------------- self-test ----
def run_self_test(a):
    """Prove the harness FAILS: unpinned refusal, real upgrade, preservation."""
    print("upgrade canary SELF-TEST (fail-closed battery)")
    here = Path(__file__).resolve()
    out = Path(a.out) / "self-test"
    out.mkdir(parents=True, exist_ok=True)

    unpinned = {"schema": cc.VECTOR_SCHEMA, "pinned": False,
                "repositories": {n: {"revision": None} for n in cc.VECTOR_REPOS}}
    up_path = out / "vector-unpinned.json"
    cc.write_json(up_path, unpinned)
    r = subprocess.run([sys.executable, str(here), "--vector", str(up_path),
                        "--out", str(out / "unpinned")],
                       capture_output=True, text=True)
    check("self-test:unpinned vector -> exit 3", r.returncode == 3,
          "rc=%d %s" % (r.returncode, (r.stdout or "").strip().splitlines()[-1:]))
    check("self-test:unpinned writes no success receipt",
          not (out / "unpinned" / "upgrade-canary.real.json").exists(),
          str(out / "unpinned"))

    rc = run_real("onboarding", out / "real", a.vector, timeout=a.timeout,
                  sandbox_base=a.sandbox_base, repo_roots=a.repo_root,
                  keep=True, prior={})
    check("self-test:pinned real upgrade exit 0", rc == 0, "rc=%d" % rc)
    body = {}
    rec = out / "real" / "upgrade-canary.real.json"
    if rec.is_file():
        body = json.loads(rec.read_text(encoding="utf-8"))
    dist = body.get("distributions", {}).get("onboarding", {})
    check("self-test:upgrade recorded a non-empty diff",
          bool(dist.get("diff", {}).get("added") or dist.get("diff", {}).get("changed")),
          "%s" % (dist.get("diff") or {}))

    # tampered manifest must be refused by the proof hook
    mp = dist.get("manifest_path")
    root = dist.get("installed_path")
    if mp and root:
        doc = json.loads(Path(mp).read_text(encoding="utf-8"))
        victim = sorted(doc["files"])[0]
        (Path(root) / victim).write_text("# tampered by self-test\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(here), "--verify-manifest", mp,
                            "--verify-root", root, "--out", str(out / "tamper")],
                           capture_output=True, text=True)
        check("self-test:tampered file -> non-zero", r.returncode != 0,
              "rc=%d" % r.returncode)
        check("self-test:tamper names the file", victim in (r.stdout + r.stderr),
              victim)

    passed, failed, total = cc.summarize_checks(RESULTS)
    print("\nself-test: %d/%d checks passed%s" % (len(passed), total,
          ("" if not failed else "; FAIL: " + ", ".join(failed))))
    return 0 if not failed else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vector")
    ap.add_argument("--dist", choices=["onboarding", "999", "both"], default="both")
    ap.add_argument("--out")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--sandbox-base", default=None)
    ap.add_argument("--repo-root", action="append", default=[], metavar="NAME=PATH")
    ap.add_argument("--prior", action="append", default=[], metavar="DIST=REV",
                    help="revision to install before upgrading (default: pinned^)")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--verify-manifest", metavar="MANIFEST")
    ap.add_argument("--verify-root", metavar="INSTALL_ROOT")
    ap.add_argument("--allow-paid", action="store_true",
                    help="REFUSED — A11 stays blocked")
    ap.add_argument("--allow-live-send", action="store_true",
                    help="REFUSED — A11 stays blocked")
    a = ap.parse_args()

    if a.allow_paid:
        return refuse("A11_PAID_PROVIDER_CALL",
                      "A11 stays blocked: a canary never makes a paid provider call")
    if a.allow_live_send:
        return refuse("A11_LIVE_CHANNEL_SEND",
                      "A11 stays blocked: a canary never sends on a live channel")

    if a.out:
        Path(a.out).mkdir(parents=True, exist_ok=True)
    if a.verify_manifest:
        if not a.verify_root:
            print("--verify-root is required with --verify-manifest")
            return 2
        ok, detail, cmd = cc.loaded_source_proof(a.verify_manifest, a.verify_root)
        print("loaded-source proof command: %s" % cmd)
        if not ok:
            print("  [FAIL] loaded-source proof: %s" % detail)
            return 1
        print("  [PASS] loaded-source proof: %s" % detail)
        return 0

    if not a.vector or not a.out:
        ap.error("--vector and --out are required (except with --verify-manifest)")

    a.repo_root = dict(kv.split("=", 1) for kv in a.repo_root if "=" in kv)
    a.prior = dict(kv.split("=", 1) for kv in a.prior if "=" in kv)
    if a.sandbox_base is None:
        a.sandbox_base = a.out
    if a.dry_run:
        return run_dry(a.out)
    if a.self_test:
        return run_self_test(a)
    return run_real(a.dist, a.out, a.vector, timeout=a.timeout,
                    sandbox_base=a.sandbox_base, repo_roots=a.repo_root,
                    keep=a.keep, prior=a.prior)


if __name__ == "__main__":
    sys.exit(main())
