#!/usr/bin/env python3
"""upgrade_canary.py — Skill 75 upgrade-of-interrupted-run canary (spec 9.2, A08/A12).

WHAT IT PROVES, per distribution:
  1. an EXISTING install is upgraded IN PLACE through the REAL distribution
     mechanism: the OLD revision is materialized from git and installed with
     `update-skills.sh --only 75`, then the PINNED revision is materialized and
     installed over it. The installer is really invoked; the target root is the
     scratch sandbox only;
  2. the upgrade manifest is computed from ACTUAL BYTES either side of the
     upgrade: files added / changed / removed, each with its sha256, plus the
     old and new source revisions;
  3. preservation: whatever an upgrade must keep (user config, secrets, paid
     artifacts, approvals, kill switch, other skills) is digested BEFORE and
     AFTER and must be byte-identical;
  4. an unrelated long-running process survives the upgrade — proven by the
     SAME pid AND the SAME process start time after the upgrade, not by a poll;
  5. --dist selects a different installer mode and install root, and the two
     runs produce different manifests.

TYPED REFUSALS (non-zero exit, never a success receipt):
  MANIFEST_MISSING      the upgrade manifest could not be produced / is empty
  DIGEST_MISMATCH       an installed file's bytes differ from the pinned source
  UNPROVABLE_CHANGE     the source revision changed but no installed file did
  PRESERVATION_MISSING  a preservation artifact is absent or was not digested
  INSTALL_FAILED        the real installer returned non-zero
  INSTALLER_LOCKED      another update-skills.sh holds the global update lock
  PROCESS_LOST          the survive-the-upgrade process died or was replaced

SAFETY: Sandbox()-isolated (scratch HOME/OC_CONFIG/SKILLS_DIR/CLAUDE_CONFIG_DIR),
openclaw/curl stubbed, git network verbs suppressed. NEVER runs against a real
config root. Real mode FAIL-CLOSED on an unpinned vector (exit 3).

Exit 0 = all checks pass; 1 = check failed / typed refusal; 3 = vector not
pinned; 2 = tooling/usage. Stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import canary_common as cc  # noqa: E402

RESULTS = {}

SKILL = "75-drama-song-ad-factory"
ONB_REPO = "openclaw-onboarding"

#: the logical path used to prove a genuinely changed file is detectable
PROBE_FILE = "scripts/core/state_store.py"
#: a file the upgrade does not touch — the "provably identical" positive control
STABLE_FILE = "INSTRUCTIONS.md"

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

#: --dist -> (install root env key, installer extra args). Distinct on purpose.
DISTS = {
    "onboarding": ("SKILLS_DIR", ["--onboarding-only"]),
    "999": ("CLAUDE_CONFIG_DIR", []),
}


def check(name, ok, detail=""):
    RESULTS[name] = {"ok": bool(ok), "detail": detail}
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name,
                           (" — " + str(detail)[:300]) if detail else ""))
    return ok


class Refusal(Exception):
    """A typed, non-zero refusal. Never produces a success receipt."""

    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------- helpers ---
def tree_manifest(root):
    """{relpath: sha256} over every regular file under root, from real bytes."""
    root = Path(root)
    man = {}
    if not root.is_dir():
        return man
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink():
            man[str(p.relative_to(root))] = cc.sha256_file(p)
    return man


def materialize(repo, rev, dest, skill=SKILL):
    """Write the skill tree at an exact git revision into dest (real bytes)."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    arch = subprocess.run(["git", "-C", str(repo), "archive", rev, skill],
                          capture_output=True)
    if arch.returncode != 0:
        raise Refusal("SOURCE_MATERIALIZE_FAILED",
                      "git archive %s %s: %s" % (rev[:12], skill,
                                                 arch.stderr.decode()[-300:]))
    ext = subprocess.run(["tar", "-x", "-C", str(dest)], input=arch.stdout,
                         capture_output=True)
    if ext.returncode != 0:
        raise Refusal("SOURCE_MATERIALIZE_FAILED",
                      "tar -x: %s" % ext.stderr.decode()[-300:])
    return dest


def installed_root(sb, dist):
    env_key, _ = DISTS[dist]
    return Path(sb.env[env_key]) / SKILL


def run_installer(sb, src_root, dist):
    """Really invoke update-skills.sh, scoped to skill 75, into the sandbox."""
    _env_key, extra = DISTS[dist]
    installer = Path(src_root) / "update-skills.sh"
    if not installer.is_file():
        raise Refusal("INSTALL_FAILED", "update-skills.sh missing at %s" % installer)
    r = cc.run_capture(["bash", str(installer), "--only", "75"] + extra,
                       sb.env, cwd=str(src_root), timeout=900)
    blob = (r.get("stdout") or "") + (r.get("stderr") or "")
    if "LOCK HELD" in blob:
        raise Refusal("INSTALLER_LOCKED",
                      "global update lock held by another update-skills.sh; "
                      "no upgrade performed")
    return r


def proc_start_time(pid):
    """Process start time from the OS. None when it cannot be measured."""
    try:
        p = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)],
                           capture_output=True, text=True)
        s = (p.stdout or "").strip()
        return s or None
    except OSError:
        return None


def start_survivor():
    """An unrelated long-running process that must outlive the upgrade."""
    p = subprocess.Popen([sys.executable, "-c",
                          "import time; time.sleep(300)"])
    time.sleep(0.2)
    return p, proc_start_time(p.pid)


def diff_manifests(before, after):
    added = {k: after[k] for k in after if k not in before}
    removed = {k: before[k] for k in before if k not in after}
    changed = {k: {"old": before[k], "new": after[k]}
               for k in after if k in before and before[k] != after[k]}
    return {"added": added, "changed": changed, "removed": removed}


def seed_sentinels(sb):
    """Create the unrelated user state that an upgrade must preserve."""
    root = Path(sb.env["HOME"]).parent
    out = {}
    for rel, body in SENTINELS:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        out[rel] = cc.sha256_file(p)
    return out


def digest_sentinels(sb):
    root = Path(sb.env["HOME"]).parent
    out = {}
    for rel, _ in SENTINELS:
        p = root / rel
        out[rel] = cc.sha256_file(p) if p.is_file() else None
    return out


def assert_preservation(before, after):
    missing = [rel for rel, d in after.items() if d is None]
    if missing:
        raise Refusal("PRESERVATION_MISSING",
                      "preservation artifact(s) gone: " + ", ".join(missing))
    drift = [rel for rel in before if before.get(rel) != after.get(rel)]
    if drift:
        raise Refusal("PRESERVATION_MISSING",
                      "preservation artifact(s) changed: " + ", ".join(drift))


def verify_against_source(inst_root, src_root):
    """Every installed file must equal the pinned source bytes, by path."""
    inst = tree_manifest(inst_root)
    src = tree_manifest(Path(src_root) / SKILL)
    if not inst:
        raise Refusal("MANIFEST_MISSING",
                      "installed tree empty at %s" % inst_root)
    bad = []
    for rel, digest in src.items():
        if rel not in inst:
            bad.append("%s (missing)" % rel)
        elif inst[rel] != digest:
            bad.append("%s (sha256 %s != %s)" % (rel, inst[rel][:16], digest[:16]))
    if bad:
        raise Refusal("DIGEST_MISMATCH",
                      "installed bytes differ from pinned source: " + "; ".join(bad[:5]))
    return len(src)


# ---------------------------------------------------------------- dry run ---
def run_dry(out):
    print("upgrade canary DRY-RUN (harness mechanics only; no installer, "
          "no repository, no real root)")
    with cc.Sandbox() as sb:
        before = seed_sentinels(sb)
        root = Path(sb.env["HOME"]).parent
        staged = root / "skills" / SKILL / PROBE_FILE
        staged.parent.mkdir(parents=True, exist_ok=True)
        stale = "# STALE wrong-hash content\n"
        staged.write_text(stale, encoding="utf-8")
        old_digest = cc.sha256_file(staged)          # artifact A: the OLD bytes
        (root / "skills" / SKILL / ".checkpoint-pending").write_text(
            "resume-stage:music\n", encoding="utf-8")

        good = "# canonical state_store content (vector revision)\n"
        staged.write_text(good, encoding="utf-8")
        new_digest = cc.sha256_file(staged)          # artifact B: the NEW bytes

        check("dry:old->new digests are meaningfully distinct",
              old_digest != new_digest,
              "old=%s new=%s" % (old_digest[:16], new_digest[:16]))
        check("dry:stale scoped file repaired to pinned bytes",
              new_digest == hashlib.sha256(good.encode()).hexdigest(),
              "installed bytes hash to the repaired content")

        after = digest_sentinels(sb)
        try:
            assert_preservation(before, after)
            check("dry:all unrelated sentinels byte-identical", True,
                  "%d sentinels compared" % len(SENTINELS))
        except Refusal as e:
            check("dry:all unrelated sentinels byte-identical", False, e.detail)

        tamper = root / SENTINELS[0][0]
        tamper.write_text('{"sentinel":"settings","tuned":false}', encoding="utf-8")
        after2 = digest_sentinels(sb)
        try:
            assert_preservation(before, after2)
            check("dry:preservation negative control (tamper detected)", False,
                  "tamper was NOT detected")
        except Refusal as e:
            check("dry:preservation negative control (tamper detected)", True,
                  e.detail)

        proc, start_before = start_survivor()
        try:
            time.sleep(0.2)
            alive = proc.poll() is None
            start_after = proc_start_time(proc.pid)
            check("dry:survivor identity is measurable (pid + start time)",
                  bool(alive and start_before and start_after == start_before),
                  "pid %d start %r" % (proc.pid, start_before))
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


# --------------------------------------------------------------- real run ---
def run_real(out, vector_path, dist, repo, old_rev=None, new_rev=None,
             fault="none"):
    v = cc.load_vector(vector_path)
    ok, reason = cc.require_pinned(v)
    if not ok:
        print("REFUSED (fail-closed): %s" % reason)
        return 3

    onb = v["repositories"][ONB_REPO]
    old_rev = old_rev or onb.get("audited_baseline")
    new_rev = new_rev or onb.get("revision")
    if not old_rev or not new_rev:
        print("REFUSED (fail-closed): prior/pinned revision not recorded "
              "(old=%r new=%r)" % (old_rev, new_rev))
        return 3
    if old_rev == new_rev and fault == "none":
        print("REFUSED UNPROVABLE_CHANGE: prior revision equals pinned revision; "
              "an upgrade from a revision to itself proves nothing")
        return 1

    print("upgrade canary REAL mode dist=%s (%s)" % (dist, reason))
    scratch = Path(out) / "scratch" / dist
    receipt_path = Path(out) / ("upgrade-manifest.%s.json" % dist)
    started = time.time()

    with cc.Sandbox() as sb:
        try:
            before_sentinels = seed_sentinels(sb)

            old_src = materialize(repo, old_rev, scratch / "old")
            new_src = materialize(repo, new_rev, scratch / "new")

            # --- tautology fix: two MEANINGFULLY DISTINCT artifacts -----------
            old_probe = cc.sha256_file(old_src / SKILL / PROBE_FILE)
            new_probe = cc.sha256_file(new_src / SKILL / PROBE_FILE)
            check("real:probe file old->new digest is distinct",
                  old_probe != new_probe,
                  "%s old=%s new=%s" % (PROBE_FILE, old_probe[:16], new_probe[:16]))
            old_stable = cc.sha256_file(old_src / SKILL / STABLE_FILE)
            new_stable = cc.sha256_file(new_src / SKILL / STABLE_FILE)
            check("real:unchanged file is provably identical old->new",
                  old_stable == new_stable,
                  "%s %s" % (STABLE_FILE, old_stable[:16]))

            # --- 1. install the OLD revision for real -----------------------
            r_old = run_installer(sb, old_src, dist)
            if r_old["rc"] != 0:
                raise Refusal("INSTALL_FAILED",
                              "old-revision install rc=%s: %s" % (
                                  r_old["rc"], (r_old.get("stderr") or
                                                r_old.get("stdout") or "")[-300:]))
            inst = installed_root(sb, dist)
            before_manifest = tree_manifest(inst)
            if not before_manifest:
                raise Refusal("MANIFEST_MISSING",
                              "old revision installed nothing at %s" % inst)
            check("real:old revision installed by real installer",
                  True, "%d files under %s" % (len(before_manifest), inst))

            # --- 4. survivor process started BEFORE the upgrade --------------
            proc, start_before = start_survivor()
            try:
                # --- 2. upgrade to the PINNED revision, for real -------------
                if fault == "failed_upgrade":
                    r_new = {"rc": 1, "stderr": "injected: installer failed",
                             "stdout": ""}
                else:
                    r_new = run_installer(sb, new_src, dist)
                if r_new["rc"] != 0:
                    raise Refusal("INSTALL_FAILED",
                                  "upgrade rc=%s: %s" % (
                                      r_new["rc"],
                                      (r_new.get("stderr") or
                                       r_new.get("stdout") or "")[-300:]))

                if fault == "tamper":
                    victim = inst / PROBE_FILE
                    victim.write_text("# tampered after upgrade\n",
                                      encoding="utf-8")
                    tampered = str(Path(SKILL) / PROBE_FILE)

                after_manifest = tree_manifest(inst)
                manifest = diff_manifests(before_manifest, after_manifest)
                manifest.update({
                    "schema": "blackceo.skill75.canary.upgrade-manifest/v1",
                    "dist": dist,
                    "old_revision": old_rev,
                    "new_revision": new_rev,
                    "install_root": str(inst),
                    "file_count_before": len(before_manifest),
                    "file_count_after": len(after_manifest),
                    "changed_count": len(manifest["changed"]),
                    "added_count": len(manifest["added"]),
                    "removed_count": len(manifest["removed"]),
                })
                cc.write_json(receipt_path, manifest)
                check("real:upgrade manifest written with real digests",
                      receipt_path.is_file() and manifest["file_count_after"] > 0,
                      "%d changed / %d added / %d removed -> %s" % (
                          manifest["changed_count"], manifest["added_count"],
                          manifest["removed_count"], receipt_path.name))

                changed_n = (manifest["changed_count"] + manifest["added_count"]
                             + manifest["removed_count"])
                if fault == "none":
                    check("real:upgrade produced >0 changed files",
                          changed_n > 0,
                          "changed=%d added=%d removed=%d" % (
                              manifest["changed_count"], manifest["added_count"],
                              manifest["removed_count"]))
                    if changed_n == 0:
                        raise Refusal("UNPROVABLE_CHANGE",
                                      "source revisions %s -> %s differ but the "
                                      "installer changed no installed file" % (
                                          old_rev[:12], new_rev[:12]))

                # --- installed bytes must match the pinned source --------
                verified = verify_against_source(inst, new_src)
                check("real:installed bytes match pinned source revision",
                      True, "%d files verified by sha256" % verified)

                # --- 3. preservation, measured before and after ----------
                if fault == "missing_preservation":
                    (Path(sb.env["HOME"]).parent / SENTINELS[2][0]).unlink()
                after_sentinels = digest_sentinels(sb)
                assert_preservation(before_sentinels, after_sentinels)
                check("real:all unrelated sentinels byte-identical across upgrade",
                      True, "%d sentinels compared" % len(SENTINELS))

                # --- 4. process survival, by pid AND start time ----------
                alive = proc.poll() is None
                start_after = proc_start_time(proc.pid) if alive else None
                same = bool(alive and start_before and
                            start_after == start_before)
                if not same:
                    raise Refusal("PROCESS_LOST",
                                  "survivor pid=%d alive=%s start_before=%r "
                                  "start_after=%r" % (proc.pid, alive,
                                                      start_before, start_after))
                check("real:unrelated process survived the upgrade",
                      True, "pid %d start %r unchanged" % (proc.pid, start_before))

                manifest["preservation"] = {
                    "before": before_sentinels,
                    "after": after_sentinels,
                    "survivor": {"pid": proc.pid, "start_time": start_before,
                                 "alive_after": alive},
                    "probe": {"path": PROBE_FILE, "old": old_probe,
                              "new": new_probe, "distinct": old_probe != new_probe},
                }
                cc.write_json(receipt_path, manifest)
                receipt = manifest
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

        except Refusal as e:
            print("REFUSED %s: %s" % (e.code, e.detail))
            RESULTS["refused:%s" % e.code] = {"ok": False, "detail": e.detail}
            failure = {
                "schema": "blackceo.skill75.canary.upgrade/v1",
                "unit": "SFR-007",
                "mode": "real",
                "dist": dist,
                "status": "REFUSED",
                "code": e.code,
                "detail": e.detail,
                "old_revision": old_rev,
                "new_revision": new_rev,
                "elapsed_s": round(time.time() - started, 2),
                "results": RESULTS,
                "sandbox_shim_log": sb.shim_entries(),
            }
            cc.write_json(Path(out) / ("upgrade-canary.%s.refused.json" % dist),
                          failure)
            return 1

        passed, failed, total = cc.summarize_checks(RESULTS)
        print("real[%s]: %d/%d checks passed%s" % (
            dist, len(passed), total,
            ("" if not failed else "; FAIL: " + ", ".join(failed))))
        return 0 if not failed else 1


def run_both(out, vector_path, repo, old_rev, new_rev):
    """Prove --dist selects a different installer and yields different manifests."""
    rc_a = run_real(out, vector_path, "onboarding", repo, old_rev, new_rev)
    rc_b = run_real(out, vector_path, "999", repo, old_rev, new_rev)
    pa = Path(out) / "upgrade-manifest.onboarding.json"
    pb = Path(out) / "upgrade-manifest.999.json"
    if rc_a or rc_b:
        return 1 if (rc_a or rc_b) else 0
    a = json.loads(pa.read_text(encoding="utf-8"))
    b = json.loads(pb.read_text(encoding="utf-8"))
    differ = (a["file_count_after"] != b["file_count_after"]
              or a["install_root"] != b["install_root"]
              or a["changed"] != b["changed"])
    check("both:--dist produced different manifests",
          differ,
          "onboarding root=%s files=%d | 999 root=%s files=%d"
          % (a["install_root"], a["file_count_after"],
             b["install_root"], b["file_count_after"]))
    passed, failed, total = cc.summarize_checks(RESULTS)
    print("both: %d/%d checks passed%s" % (len(passed), total,
          ("" if not failed else "; FAIL: " + ", ".join(failed))))
    return 0 if not failed else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vector", required=True)
    ap.add_argument("--dist", choices=["onboarding", "999", "both"], default="both")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]),
                    help="git checkout to materialize revisions from")
    ap.add_argument("--old-rev", default=None)
    ap.add_argument("--new-rev", default=None)
    ap.add_argument("--fault", default="none",
                    choices=["none", "tamper", "failed_upgrade",
                             "missing_preservation"],
                    help="fault injection, used to prove the checks can FAIL")
    a = ap.parse_args()
    Path(a.out).mkdir(parents=True, exist_ok=True)
    if a.dry_run:
        return run_dry(a.out)
    if a.dist == "both":
        return run_both(a.out, a.vector, a.repo, a.old_rev, a.new_rev)
    return run_real(a.out, a.vector, a.dist, a.repo, a.old_rev, a.new_rev,
                    a.fault)


if __name__ == "__main__":
    sys.exit(main())
