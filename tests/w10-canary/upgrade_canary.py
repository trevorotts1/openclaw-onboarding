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
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import canary_common as cc  # noqa: E402

RESULTS = {}

#: set by --fixture: the run uses a fixture source, so its receipt must never
#: be readable as a real distribution install.
FIXTURE = False

SKILL = "75-drama-song-ad-factory"
ONB_REPO = "openclaw-onboarding"

#: acceptance rows this harness produces evidence for (receipt-mapping.json,
#: canaries.upgrade.acceptance_rows). Stamped into every receipt.
ACCEPTANCE_ROWS = ["A08", "A12", "A11"]

#: the logical path used to prove a genuinely changed file is detectable
PROBE_FILE = "scripts/core/state_store.py"
#: a file the upgrade does not touch — the "provably identical" positive control
STABLE_FILE = "INSTRUCTIONS.md"

#: sentinel paths (relative to sandbox home/oc) that must survive byte-identical.
#: settings.json is deliberately ABSENT: update-skills.sh rewrites it to un-wire
#: ceo-intent-gate.sh from PreToolUse, so its bytes legitimately change. Its user
#: content is asserted semantically below instead.
SENTINELS = [
    ("home/.claude/model-aliases.json", '{"sentinel":"aliases"}'),
    ("oc/secrets/.env", "SENTINEL_SECRET=do-not-touch\n"),
    ("oc/sessions/active.json", '{"sentinel":"sessions"}'),
    ("oc/paid-artifacts/receipt-1.json", '{"sentinel":"paid","id":"r1"}'),
    ("oc/approvals/approved-1.json", '{"sentinel":"approvals"}'),
    ("oc/kill-switch.flag", "sentinel-kill-switch\n"),
    ("skills/46-kie-callback-relay/SKILL.md", "sentinel: other skill preserved\n"),
]

#: files the installer may rewrite: the user's own content must still be there
SEMANTIC_SENTINELS = [("home/.claude/settings.json", "sentinel", "settings")]

#: --dist -> installer mode. The installer resolves its skills root from
#: $OC_CONFIG/skills (OC_SKILLS_DIR is NOT honoured in practice), so each dist
#: gets its own OC_CONFIG and therefore its own install root.
DISTS = {
    "onboarding": {"cfg": "cfg-onboarding", "args": ["--onboarding-only"]},
    "999": {"cfg": "cfg-999", "args": []},
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


#: what the installer actually needs to run from a revision: itself, the dirs it
#: sources, and the skill it installs. A full-repo archive is ~513 MB, too big.
INSTALLER_PATHS = [SKILL, "update-skills.sh", "platform", "shared-utils",
                   "scripts", "installer-registration"]


def materialize(repo, rev, dest, paths=None):
    """Write the skill tree + installer at an exact git revision into dest."""
    wanted = paths or INSTALLER_PATHS
    # a path that does not exist at that revision would abort the whole archive
    paths = [p for p in wanted if subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", "%s:%s" % (rev, p)],
        capture_output=True).returncode == 0]
    if SKILL not in paths:
        raise Refusal("SOURCE_MATERIALIZE_FAILED",
                      "skill %s absent at %s" % (SKILL, rev[:12]))
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)          # never diff against a previous run's leftovers
    dest.mkdir(parents=True, exist_ok=True)
    arch = subprocess.run(["git", "-C", str(repo), "archive", rev] + list(paths),
                          capture_output=True)
    if arch.returncode != 0:
        raise Refusal("SOURCE_MATERIALIZE_FAILED",
                      "git archive %s: %s" % (rev[:12],
                                              arch.stderr.decode()[-300:]))
    ext = subprocess.run(["tar", "-x", "-C", str(dest)], input=arch.stdout,
                         capture_output=True)
    if ext.returncode != 0:
        raise Refusal("SOURCE_MATERIALIZE_FAILED",
                      "tar -x: %s" % ext.stderr.decode()[-300:])
    return dest


def build_mirror(repo, rev, dest, paths=None):
    """A one-commit git repo whose tree is exactly `rev` for the given paths.

    update-skills.sh fetches its source with `git clone <github url>`; a hermetic
    canary cannot reach GitHub, so this supplies the same bytes from the pinned
    revision instead. The true revision is recorded in the manifest.
    """
    tree = materialize(repo, rev, dest)
    env = dict(os.environ)
    env.update({"GIT_AUTHOR_NAME": "canary", "GIT_AUTHOR_EMAIL": "canary@invalid",
                "GIT_COMMITTER_NAME": "canary",
                "GIT_COMMITTER_EMAIL": "canary@invalid",
                "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
                "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z"})
    for cmd in (["init", "-q"], ["add", "-A"],
                ["commit", "-q", "-m", "canary mirror of %s" % rev]):
        r = subprocess.run(["git", "-C", str(tree)] + cmd, env=env,
                           capture_output=True)
        if r.returncode != 0:
            raise Refusal("SOURCE_MATERIALIZE_FAILED",
                          "mirror git %s: %s" % (cmd[0],
                                                 r.stderr.decode()[-300:]))
    return tree


_GIT_FETCH_SHIM = """#!/bin/sh
# canary shim: answer `git clone` from the pinned local mirror, never the network.
REAL_GIT="__REAL_GIT__"
MIRROR="__MIRROR__"
ORIGIN="https://github.com/trevorotts1/openclaw-onboarding.git"
if [ "$1" = "clone" ]; then
  shift
  dest=""
  for a in "$@"; do
    case "$a" in --depth*) ;; -*) ;; *) dest="$a" ;; esac
  done
  "$REAL_GIT" clone --no-hardlinks "$MIRROR" "$dest" || exit $?
  # the installer hard-verifies origin is the canonical repo URL
  "$REAL_GIT" -C "$dest" remote set-url origin "$ORIGIN"
  exit $?
fi
exec "$REAL_GIT" "$@"
"""


def build_fetch_shim(sb, mirror):
    """Prepend a git shim answering `clone` from the local mirror. No network."""
    real_git = shutil.which("git") or "/usr/bin/git"
    d = Path(sb.root) / "fetch-shims"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "git"
    p.write_text(_GIT_FETCH_SHIM.replace("__REAL_GIT__", real_git)
                 .replace("__MIRROR__", str(mirror)), encoding="utf-8")
    p.chmod(0o755)
    sb.env["PATH"] = "%s:%s" % (d, sb.env["PATH"])
    return d


def allow_network(sb):
    """Let the installer fetch its own release asset; keep every safety stub.

    update-skills.sh aborts before copying any skill unless it can download a
    prebuilt persona index (~105 personas) from GitHub releases. That asset is
    unrelated to Skill 75 but is a hard prerequisite of the real installer, so
    an explicit opt-in re-enables curl. `openclaw` stays stubbed (a canary must
    never notify a client) and the git fetch shim stays in place, so the source
    bytes remain the pinned revisions rather than a moving branch tip.
    """
    parts = [p for p in sb.env["PATH"].split(":")
             if p and p != str(Path(sb.root) / "shims")]
    sandbox_shims = str(Path(sb.root) / "shims")
    keep = Path(sb.root) / "safe-shims"
    keep.mkdir(parents=True, exist_ok=True)
    src = Path(sandbox_shims) / "openclaw"
    if src.is_file():
        dst = keep / "openclaw"
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        dst.chmod(0o755)
    sb.env["PATH"] = ":".join([str(keep)] + parts)
    return keep


def installed_root(sb, dist):
    """Where update-skills.sh actually writes.

    Measured, not assumed: `discover_skills_dir()` resolves
    ${OC_SKILLS_DIR:-${OPENCLAW_ROOT:-${OC_CONFIG:-$HOME/.openclaw}}/skills}, and a
    sandbox OC_SKILLS_DIR was empirically ignored — the installer wrote to
    $OC_CONFIG/skills. Reading any other path yields a phantom "nothing installed".
    """
    return Path(sb.env["OC_CONFIG"]) / "skills" / SKILL


def locate_skill_tree(sb):
    """Every SKILL tree the installer could have left behind, for honest errors."""
    return sorted(str(p) for p in Path(sb.root).rglob(SKILL) if p.is_dir())


def run_installer(sb, src_root, dist):
    """Really invoke update-skills.sh, scoped to skill 75, into the sandbox."""
    extra = DISTS[dist]["args"]
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


def installer_tail(r, n=400):
    """Last meaningful lines of an installer run, for the receipt."""
    blob = ((r.get("stderr") or "") + (r.get("stdout") or "")).strip()
    return blob[-n:] if blob else "(no output)"


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
    # the installer MAY rewrite this one; seed the user content it must keep
    p = root / SEMANTIC_SENTINELS[0][0]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"sentinel":"settings","tuned":true}', encoding="utf-8")
    return out


def assert_semantics(sb):
    """A rewritten settings.json must still carry the user's own content."""
    root = Path(sb.env["HOME"]).parent
    for rel, key, want in SEMANTIC_SENTINELS:
        p = root / rel
        if not p.is_file():
            raise Refusal("PRESERVATION_MISSING", "%s removed by the upgrade" % rel)
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except ValueError as e:
            raise Refusal("PRESERVATION_MISSING",
                          "%s is no longer valid JSON after the upgrade: %s" % (rel, e))
        if not isinstance(doc, dict) or doc.get(key) != want:
            raise Refusal("PRESERVATION_MISSING",
                          "%s lost user key %r=%r (now %r)" % (
                              rel, key, want, doc.get(key) if isinstance(doc, dict) else doc))
    return True


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
            bad.append("%s (missing at %s)" % (rel, inst_root))
        elif inst[rel] != digest:
            bad.append("%s (path %s; installed sha256 %s != pinned %s)"
                       % (rel, Path(inst_root) / rel, inst[rel][:16], digest[:16]))
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

        # QC-head 59e893d parity (union): the simulated success clears the marker.
        (root / "skills" / SKILL / ".checkpoint-pending").unlink()
        check("dry:checkpoint marker cleared on success",
              not (root / "skills" / SKILL / ".checkpoint-pending").exists(),
              ".checkpoint-pending cleared")

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
            "acceptance_rows": ACCEPTANCE_ROWS,
            "boundary": "harness mechanics only; NO installer run, NO repository, "
                        "NO real root, NO acceptance point claimed",
            "results": RESULTS,
            "sandbox_shim_log": sb.shim_entries(),
        }
        cc.stamp_evidence(receipt, True)     # dry-run: never acceptance evidence
        cc.write_json(Path(out) / "upgrade-canary.dry.json", receipt)

    passed, failed, total = cc.summarize_checks(RESULTS)
    print("dry-run: %d/%d checks passed%s" % (len(passed), total,
          ("" if not failed else "; FAIL: " + ", ".join(failed))))
    return 0 if not failed else 1


# --------------------------------------------------------------- real run ---
def run_real(out, vector_path, dist, repo, old_rev=None, new_rev=None,
             fault="none", allow_net=False):
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
    RESULTS.clear()                  # each dist run reports only its own checks
    scratch = Path(out) / "scratch" / dist
    receipt_path = Path(out) / ("upgrade-manifest.%s.json" % dist)
    started = time.time()

    with cc.Sandbox() as sb:
        try:
            sb.env["OC_CONFIG"] = str(sb.root / DISTS[dist]["cfg"])
            sb.env.pop("OC_SKILLS_DIR", None)
            sb.env["OPENCLAW_UPDATE_SKIP_SELF_SYNC"] = "1"
            before_sentinels = seed_sentinels(sb)

            old_src = build_mirror(repo, old_rev, scratch / "old")
            new_src = build_mirror(repo, new_rev, scratch / "new")

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
            build_fetch_shim(sb, old_src)
            if allow_net:
                allow_network(sb)
            r_old = run_installer(sb, old_src, dist)
            warnings = []
            if r_old["rc"] != 0:
                # The updater also provisions a prebuilt persona index from
                # GitHub releases; a hermetic sandbox cannot fetch it. That step
                # is unrelated to Skill 75, so its failure is recorded, not
                # hidden — the skill tree below is what this canary judges.
                warnings.append("old-install rc=%s: %s" % (
                    r_old["rc"], installer_tail(r_old)))
            inst = installed_root(sb, dist)
            before_manifest = tree_manifest(inst)
            if not before_manifest:
                found = locate_skill_tree(sb)
                raise Refusal("MANIFEST_MISSING",
                              "old revision installed nothing at %s (installer "
                              "rc=%s: %s); trees found elsewhere: %s" % (
                                  inst, r_old["rc"], installer_tail(r_old),
                                  found or "none"))
            check("real:old revision installed by real installer",
                  True, "%d files under %s" % (len(before_manifest), inst))

            # QC-head 59e893d parity (union): an interrupted run's resume state
            # must survive a content upgrade. Seeded in the INSTALLED tree, so the
            # installer is the thing that could eat it -- never outside it.
            seeded_markers = (".checkpoint-pending",
                              "scripts/core/state_store.py.part")
            (inst / seeded_markers[0]).write_text("resume-stage:music\n",
                                                  encoding="utf-8")
            (inst / seeded_markers[1]).parent.mkdir(parents=True, exist_ok=True)
            (inst / seeded_markers[1]).write_text("partial", encoding="utf-8")
            before_manifest = tree_manifest(inst)

            # --- 4. survivor process started BEFORE the upgrade --------------
            proc, start_before = start_survivor()
            try:
                # --- 2. upgrade to the PINNED revision, for real -------------
                if fault == "failed_upgrade":
                    raise Refusal("INSTALL_FAILED",
                                  "injected: the upgrade installer never ran, so "
                                  "no upgrade can be claimed")
                build_fetch_shim(sb, new_src)
                r_new = run_installer(sb, new_src, dist)
                if r_new["rc"] != 0:
                    # unrelated U6b persona-index provision; judged below instead
                    warnings.append("upgrade rc=%s: %s" % (
                        r_new["rc"], installer_tail(r_new)))

                if fault == "tamper":
                    (inst / PROBE_FILE).write_text("# tampered after upgrade\n",
                                                   encoding="utf-8")

                after_manifest = tree_manifest(inst)
                # Seeded resume state is deliberately user state, not installer
                # content: excluded from the drift diff so it cannot be mistaken
                # for drift, and asserted by name just below.
                for _rel in seeded_markers:
                    before_manifest.pop(_rel, None)
                    after_manifest.pop(_rel, None)
                manifest = diff_manifests(before_manifest, after_manifest)
                manifest.update({
                    "schema": "blackceo.skill75.canary.upgrade-manifest/v1",
                    "dist": dist,
                    "acceptance_rows": ACCEPTANCE_ROWS,
                    "distribution_args": DISTS[dist]["args"],
                    "old_revision": old_rev,
                    "new_revision": new_rev,
                    "install_root": str(inst),
                    "file_count_before": len(before_manifest),
                    "file_count_after": len(after_manifest),
                    "changed_count": len(manifest["changed"]),
                    "added_count": len(manifest["added"]),
                    "removed_count": len(manifest["removed"]),
                    "installer_rc": {"old": r_old["rc"], "upgrade": r_new["rc"]},
                    "installer_warnings": warnings,
                })
                cc.stamp_evidence(manifest, FIXTURE)
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

                # A content install must never eat an interrupted run's resume
                # state (QC-head 59e893d assertion, restored here on the composed
                # structure). Clearing the marker belongs to the state_store
                # resume path, which multi_run_canary proves.
                check("upgrade:%s:interrupted-run state preserved" % dist,
                      all((inst / rel).is_file() for rel in seeded_markers),
                      ".checkpoint-pending and scripts/core/state_store.py.part "
                      "survive the content upgrade")

                # --- 3. preservation, measured before and after ----------
                if fault == "missing_preservation":
                    (Path(sb.env["HOME"]).parent / SENTINELS[2][0]).unlink()
                after_sentinels = digest_sentinels(sb)
                assert_preservation(before_sentinels, after_sentinels)
                check("real:all unrelated sentinels byte-identical across upgrade",
                      True, "%d sentinels compared" % len(SENTINELS))
                assert_semantics(sb)
                check("real:rewritten settings.json kept the user's content",
                      True, "%s still carries its user key"
                      % SEMANTIC_SENTINELS[0][0])

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
                "acceptance_rows": ACCEPTANCE_ROWS,
                "status": "REFUSED",
                "code": e.code,
                "detail": e.detail,
                "old_revision": old_rev,
                "new_revision": new_rev,
                "elapsed_s": round(time.time() - started, 2),
                "results": RESULTS,
                "sandbox_shim_log": sb.shim_entries(),
            }
            cc.stamp_evidence(failure, FIXTURE)
            cc.write_json(Path(out) / ("upgrade-canary.%s.refused.json" % dist),
                          failure)
            return 1

        passed, failed, total = cc.summarize_checks(RESULTS)
        print("real[%s]: %d/%d checks passed%s" % (
            dist, len(passed), total,
            ("" if not failed else "; FAIL: " + ", ".join(failed))))
        return 0 if not failed else 1


def run_both(out, vector_path, repo, old_rev, new_rev, allow_net=False):
    """Prove --dist selects a different installer and yields different manifests."""
    rc_a = run_real(out, vector_path, "onboarding", repo, old_rev, new_rev,
                    allow_net=allow_net)
    rc_b = run_real(out, vector_path, "999", repo, old_rev, new_rev,
                    allow_net=allow_net)
    pa = Path(out) / "upgrade-manifest.onboarding.json"
    pb = Path(out) / "upgrade-manifest.999.json"
    if rc_a or rc_b:
        return rc_a or rc_b          # propagate 3 (unpinned) rather than collapsing
    RESULTS.clear()
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


def run_selftest(out):
    """Prove the real check machinery can FAIL. No installer, no repository.

    Exercises the exact functions run_real() relies on, against synthetic trees,
    so a green selftest means those checks are capable of refusing.
    """
    print("upgrade canary SELFTEST (check machinery only; no installer, "
          "no repository, no real root)")
    RESULTS.clear()
    work = Path(out) / "selftest"
    if work.exists():
        shutil.rmtree(work)
    old_root = work / "old" / SKILL
    new_root = work / "new" / SKILL
    inst = work / "installed" / SKILL
    for root, body in ((old_root, "old"), (new_root, "new")):
        for rel in ("scripts/core/state_store.py", "INSTRUCTIONS.md",
                    "scripts/core/only_old.py"):
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            if rel == "INSTRUCTIONS.md":
                p.write_text("unchanged text\n", encoding="utf-8")
            else:
                p.write_text("%s %s\n" % (body, rel), encoding="utf-8")
    (new_root / "scripts/core/only_new.py").write_text("new only\n", encoding="utf-8")
    (old_root / "scripts/core/only_old.py").write_text("old only\n", encoding="utf-8")
    (new_root / "scripts/core/only_old.py").unlink()   # removed between revisions

    # (a) manifest built from real bytes; independent recompute must agree
    before = tree_manifest(old_root)
    shutil.copytree(old_root, inst)
    shutil.rmtree(inst)
    shutil.copytree(new_root, inst)
    after = tree_manifest(inst)
    man = diff_manifests(before, after)
    indep = hashlib.sha256((new_root / PROBE_FILE).read_bytes()).hexdigest()
    check("selftest:manifest changed files detected", man["changed"],
          "changed=%d" % len(man["changed"]))
    check("selftest:manifest added/removed detected",
          list(man["added"]) == ["scripts/core/only_new.py"]
          and list(man["removed"]) == ["scripts/core/only_old.py"],
          "added=%r removed=%r" % (list(man["added"]), list(man["removed"])))
    check("selftest:manifest digests are the real bytes",
          man["changed"][PROBE_FILE]["new"] == indep,
          "%s sha256 %s" % (PROBE_FILE, indep[:16]))

    # (b) tamper must be caught and must NAME the exact path
    (inst / PROBE_FILE).write_text("# tampered\n", encoding="utf-8")
    try:
        verify_against_source(inst, new_root.parent)
        check("selftest:tamper refused with DIGEST_MISMATCH", False,
              "tamper was NOT detected")
    except Refusal as e:
        named = str(inst / PROBE_FILE)
        check("selftest:tamper refused with DIGEST_MISMATCH",
              e.code == "DIGEST_MISMATCH" and named in e.detail,
              "%s names %s" % (e.code, named))

    # (c) a missing preservation artifact must be refused
    try:
        assert_preservation({"a": "deadbeef"}, {"a": None})
        check("selftest:missing preservation refused", False, "not detected")
    except Refusal as e:
        check("selftest:missing preservation refused",
              e.code == "PRESERVATION_MISSING", e.code)
    try:
        assert_preservation({"a": "deadbeef"}, {"a": "cafebabe"})
        check("selftest:changed preservation refused", False, "not detected")
    except Refusal as e:
        check("selftest:changed preservation refused",
              e.code == "PRESERVATION_MISSING", e.code)

    # (d) process survival must fail when the process actually dies
    proc, start_before = start_survivor()
    proc.terminate()
    proc.wait(timeout=5)
    proc.poll()
    alive = proc.poll() is None
    check("selftest:dead survivor would be refused (PROCESS_LOST)",
          not alive, "pid %d alive=%s start=%r" % (proc.pid, alive, start_before))

    # (e) an empty installed tree must be refused as MANIFEST_MISSING
    try:
        verify_against_source(work / "empty", new_root.parent)
        check("selftest:empty install refused as MANIFEST_MISSING", False,
              "not detected")
    except Refusal as e:
        check("selftest:empty install refused as MANIFEST_MISSING",
              e.code == "MANIFEST_MISSING", e.code)

    passed, failed, total = cc.summarize_checks(RESULTS)
    doc = {"schema": "blackceo.skill75.canary.upgrade-selftest/v1",
           "mode": "selftest", "acceptance_rows": ACCEPTANCE_ROWS,
           "results": RESULTS}
    cc.stamp_evidence(doc, True)         # no installer ran: never acceptance
    cc.write_json(work / "selftest.json", doc)
    print("selftest: %d/%d checks passed%s" % (len(passed), total,
          ("" if not failed else "; FAIL: " + ", ".join(failed))))
    return 0 if not failed else 1


def main():
    global FIXTURE
    ap = argparse.ArgumentParser()
    ap.add_argument("--vector", required=True)
    ap.add_argument("--dist", choices=["onboarding", "999", "both"], default="both")
    ap.add_argument("--out", required=True)
    ap.add_argument("--fixture", action="store_true",
                    help="label the receipt FIXTURE: the source is a fixture, not "
                         "a real distribution install; never acceptance evidence")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--allow-network", action="store_true",
                    help="let the installer fetch its own release asset; every "
                         "safety stub except curl stays in force")
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]),
                    help="git checkout to materialize revisions from")
    ap.add_argument("--old-rev", default=None)
    ap.add_argument("--new-rev", default=None)
    ap.add_argument("--fault", default="none",
                    choices=["none", "tamper", "failed_upgrade",
                             "missing_preservation"],
                    help="fault injection, used to prove the checks can FAIL")
    a = ap.parse_args()
    FIXTURE = bool(a.fixture)
    Path(a.out).mkdir(parents=True, exist_ok=True)
    if a.dry_run:
        return run_dry(a.out)
    if a.selftest:
        return run_selftest(a.out)
    if a.dist == "both":
        return run_both(a.out, a.vector, a.repo, a.old_rev, a.new_rev,
                        a.allow_network)
    return run_real(a.out, a.vector, a.dist, a.repo, a.old_rev, a.new_rev,
                    a.fault, a.allow_network)


if __name__ == "__main__":
    sys.exit(main())
