#!/usr/bin/env python3
"""clean_install_canary.py — Skill 75 clean-install canary (spec 9.2, 15.2, A08/A12).

WHAT IT PROVES, per distribution (openclaw-onboarding and 999-setup):
  1. a fresh sandboxed install root receives the Skill 75 tree through the REAL
     distribution mechanism (onboarding: update-skills.sh --only 75 into
     $SKILLS_DIR; 999: nine-router-setup --skills-only into $CLAUDE_CONFIG_DIR),
     never a hand copy standing in for the installer;
  2. the installed tree is exactly the tree at the PINNED source revision — every
     installed file's sha256 is checked against the same path in the pinned
     checkout, so no placeholder or stale content can pass;
  3. a REAL distribution manifest is written: every installed file with its
     sha256, the installed real path, and the source revision per repository;
  4. the loaded-source proof hook refuses a missing, empty or tampered manifest
     (digests are recomputed here) before handing anything to runtime_proof.py.

SAFETY: everything runs inside a Sandbox() with HOME/OC_CONFIG/SKILLS_DIR/
CLAUDE_CONFIG_DIR redirected to scratch, `openclaw` and `curl` stubbed out (no
client notification, no network). `git clone` is answered from a tree already
materialized at the pinned revision, so the installer's real clone path runs
with zero network. Real modes FAIL-CLOSED unless source-vector.json is pinned
(require_pinned). This harness NEVER runs against a real config root.

A11 stays blocked: no paid provider call and no live channel send is reachable.
--allow-paid / --allow-live-send exist only to be REFUSED with a typed code.

Modes:
  --dry-run   harness mechanics against synthetic trees (SFR-007: what runs NOW)
  (no flag)   real install from the PINNED vector's checkouts into scratch
  --verify-manifest M --verify-root R
              loaded-source proof hook: recompute M's digests against R
  --self-test fail-closed battery: unpinned refusal, real run, tamper, broken
              installer (add --dist to widen it)

Exit 0 = every check passed; 1 = a check failed; 2 = tooling/resolve error;
3 = vector not pinned (real mode); 4 = refused by policy (A11). Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import canary_common as cc  # noqa: E402

ONB_SKILL = "75-drama-song-ad-factory"
NINE_SKILL_DIR = Path(".claude/skills/drama-song-ad-factory")

#: acceptance rows this harness produces evidence for (receipt-mapping.json,
#: canaries.clean_install.acceptance_rows). Stamped into every receipt.
ACCEPTANCE_ROWS = ["A08", "A12", "A11"]

#: shared files that must be byte-identical across both distributions
SHARED_FILES = [
    "scripts/core/state_store.py",
    "scripts/core/spend_ledger.py",
    "scripts/core/cc_sync.py",
    "scripts/core/song_dispatch/song_dispatch.py",
    "scripts/core/intake_preflight/preflight.py",
    "scripts/core/batch_mode/batch.py",
]

#: dist -> its real installer, source subtree, and install destination
DISTS = {
    "onboarding": {
        "repo": "openclaw-onboarding",
        "source_subdir": ONB_SKILL,
        "install_rel": ONB_SKILL,
        # real installer: clones the pinned tree, copies numbered skill folders
        "installer": "update-skills.sh",
        "installer_args": ["--only", "75"],
    },
    "999": {
        "repo": "999-setup",
        "source_subdir": str(NINE_SKILL_DIR),
        "install_rel": "drama-song-ad-factory",
        # real installer: bundled-skills content sync into an existing skills root
        "installer": str(Path(".claude/skills/nine-router-setup/scripts")
                         / "setup-macos.sh"),
        "installer_args": ["--skills-only"],
    },
}

#: typed refusal codes. A canary never fails with a bare "it broke".
REFUSALS = {
    "VECTOR_UNPINNED": 3,
    "SOURCE_CHECKOUT_UNRESOLVED": 2,
    "REVISION_NOT_LOCAL": 2,
    "INSTALLER_MISSING": 2,
    "INSTALLER_LOCK_HELD": 2,
    "INSTALLER_FAILED": 1,
    "A11_PAID_PROVIDER_CALL": 4,
    "A11_LIVE_CHANNEL_SEND": 4,
}

#: a canary must never reach a paid provider or a live channel
PAID_MARKERS = ("kie.ai", "api.kie", "openrouter.ai/api", "deepseek.com/chat",
                "generativelanguage.googleapis", "elevenlabs", "podbean.com/api")
LIVE_SEND_MARKERS = ("openclaw message send", "openclaw send", "telegram",
                     "sendMessage")

RESULTS = {}

#: set by --fixture: the run uses a fixture source, so its receipt must never
#: be readable as a real distribution install.
FIXTURE = False


def check(name, ok, detail=""):
    RESULTS[name] = {"ok": bool(ok), "detail": detail}
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name,
                           (" — " + str(detail)[:300]) if detail else ""))
    return ok


def refuse(code, detail, out=None, mode="real"):
    """Typed refusal: print the code, record it, exit with its own status."""
    if code not in REFUSALS:
        code = "INSTALLER_FAILED"
    print("REFUSED [%s]: %s" % (code, detail))
    if out:
        doc = {
            "schema": "blackceo.skill75.canary.clean-install/v1",
            "unit": "SFR-007",
            "mode": mode,
            "status": "REFUSED",
            "acceptance_rows": ACCEPTANCE_ROWS,
            "refusal": {"code": code, "detail": detail},
        }
        cc.stamp_evidence(doc, FIXTURE)
        cc.write_json(Path(out) / ("clean-install-canary.%s.refused.json" % mode), doc)
    return REFUSALS[code]


def a11_guard(commands):
    """Refuse anything that would make a paid call or a live channel send."""
    for cmd in commands:
        line = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        low = line.lower()
        for m in PAID_MARKERS:
            if m in low:
                return "A11_PAID_PROVIDER_CALL", "command reaches a paid provider: %s" % line
        for m in LIVE_SEND_MARKERS:
            if m in low:
                return "A11_LIVE_CHANNEL_SEND", "command would send on a live channel: %s" % line
    return None, ""


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


# ------------------------------------------------------------- installers ----
def install_onboarding(src_root, sb, timeout=900):
    """REAL distribution mechanism: update-skills.sh --only 75.

    The script clones the repo itself; the sandbox git shim answers that clone
    from the pinned tree, so this is the installer's own install path.
    """
    installer = Path(src_root) / DISTS["onboarding"]["installer"]
    if not installer.is_file():
        return {"rc": 2, "stderr": "update-skills.sh missing at %s" % installer,
                "cmd": ["bash", str(installer)]}
    return cc.run_capture(["bash", str(installer)] + DISTS["onboarding"]["installer_args"],
                          sb.env, cwd=str(src_root), timeout=timeout)


def install_999(src_root, sb, timeout=900):
    """REAL 999 distribution mechanism: bundled-skills content sync.

    `setup-macos.sh --skills-only` is the deterministic installer that writes
    every skill listed in CONTROL/bundled-skills.txt from the checkout into an
    EXISTING skills root. helper-deps.py preflight then proves the helper pins
    on the installed root.
    """
    setup = Path(src_root) / DISTS["999"]["installer"]
    runs = []
    if not setup.is_file():
        runs.append({"rc": 2, "stderr": "setup-macos.sh missing at %s" % setup,
                     "cmd": ["bash", str(setup)]})
        return runs
    runs.append(cc.run_capture(["bash", str(setup)] + DISTS["999"]["installer_args"],
                               sb.env, cwd=str(src_root), timeout=timeout))
    helper = Path(src_root) / "installer-registration" / "helper-deps.py"
    if helper.is_file():
        runs.append(cc.run_capture(
            [sys.executable, str(helper), "preflight",
             "--root", sb.env["CLAUDE_CONFIG_DIR"]],
            sb.env, cwd=str(src_root), timeout=180))
    else:
        runs.append({"rc": 2, "stderr": "helper-deps.py missing at %s" % helper,
                     "cmd": ["python3", str(helper)]})
    return runs


def install(dist, src_root, sb, timeout=900):
    if dist == "onboarding":
        return [install_onboarding(src_root, sb, timeout)]
    return install_999(src_root, sb, timeout)


def prepare_sandbox(dist, sb):
    """Stage the preconditions the real installer legitimately expects."""
    if dist == "999":
        # `--skills-only` is for a box that already runs 9Router and already has
        # a skills root: both are simulated here, nothing is installed for them.
        (Path(sb.env["HOME"]) / ".9router").mkdir(parents=True, exist_ok=True)
        (Path(sb.env["CLAUDE_CONFIG_DIR"]) / "skills").mkdir(parents=True,
                                                             exist_ok=True)


def install_root(dist, sb):
    """Where the installer ACTUALLY writes, resolved the way the installer does.

    onboarding's `discover_skills_dir()` recomputes the root as
    ${OC_SKILLS_DIR:-${OPENCLAW_ROOT:-${OC_CONFIG:-$HOME/.openclaw}}/skills} and
    ignores $SKILLS_DIR, so reading $SKILLS_DIR here would look at the wrong tree
    and report a phantom "nothing installed".
    """
    if dist == "onboarding":
        base = (sb.env.get("OC_SKILLS_DIR") or sb.env.get("OPENCLAW_ROOT")
                or sb.env["OC_CONFIG"])
        return Path(base) / "skills" / DISTS[dist]["install_rel"]
    return (Path(sb.env["CLAUDE_CONFIG_DIR"]) / "skills"
            / DISTS[dist]["install_rel"])


# ------------------------------------------------------------- resolution ----
def repo_checkout(name, vector, overrides):
    """Resolve the local checkout for a vector repo. Returns (path, how)."""
    if name in overrides:
        return Path(overrides[name]).expanduser(), "--repo-root"
    declared = (vector.get("repositories", {}).get(name) or {}).get("path")
    if declared:
        return Path(declared).expanduser(), "vector.path"
    sibling = Path(__file__).resolve().parents[2].parent / name
    if sibling.is_dir():
        return sibling, "sibling-checkout"
    return None, "unresolved"


def run_real(dist_arg, out, vector_path, timeout=900,
             sandbox_base=None, repo_roots=None, keep=False):
    """Real install from the PINNED vector checkouts. Fail-closed on unpinned."""
    mode = "real"
    v = cc.load_vector(vector_path)
    ok, reason = cc.require_pinned(v)
    if not ok:
        print("REFUSED (fail-closed): %s" % reason)
        return 3
    print("clean-install canary REAL mode against pinned vector (%s)" % reason)

    dists = ["onboarding", "999"] if dist_arg == "both" else [dist_arg]
    repo_roots = repo_roots or {}
    plans = []
    for d in dists:
        repo = DISTS[d]["repo"]
        rev = v["repositories"][repo].get("revision")
        path, how = repo_checkout(repo, v, repo_roots)
        if not path:
            return refuse("SOURCE_CHECKOUT_UNRESOLVED",
                          "%s: no local checkout named by the vector, --repo-root "
                          "or a sibling directory" % repo, out, mode)
        plans.append((d, repo, rev, path, how))

    receipt = {
        "schema": "blackceo.skill75.canary.clean-install/v1",
        "unit": "SFR-007",
        "mode": mode,
        "acceptance_rows": ACCEPTANCE_ROWS,
        "vector": {"pinned_at": v.get("pinned_at"),
                   "pinned_by": v.get("pinned_by"),
                   "revisions": {k: v["repositories"][k].get("revision")
                                 for k in v.get("repositories", {})}},
        "distributions": {},
        "loaded_source_proof_hook": {},
        "boundary": ("Real install executed into a scratch sandbox only. No paid "
                     "provider call, no live channel send, no client box, no real "
                     "config root. The loaded-source proof still needs a live "
                     "process and an explicit execution GO."),
    }

    for d, repo, rev, checkout, how in plans:
        spec = DISTS[d]
        print("\n[%s] installing from %s @ %s (resolved by %s)"
              % (d, checkout, rev[:12] if rev else "?", how))
        with cc.Sandbox(keep=keep, base_dir=sandbox_base) as sb:
            staged = sb.root / "pinned" / repo
            ok, detail = cc.materialize_revision(checkout, rev, staged)
            if not ok:
                return refuse("REVISION_NOT_LOCAL", "%s: %s" % (repo, detail),
                              out, mode)
            sb.clone_source = (str(staged), rev,
                               "https://github.com/trevorotts1/%s.git" % repo)
            # rebuild the git shim with the clone source now that it is staged
            cc.build_shims(sb.root / "shims", sb.shim_log,
                           clone_source=sb.clone_source)
            prepare_sandbox(d, sb)

            cmds = [["bash", str(staged / spec["installer"])]
                    + spec["installer_args"]]
            code, why = a11_guard(cmds)
            if code:
                return refuse(code, why, out, mode)

            runs = install(d, staged, sb, timeout=timeout)
            lock = any("LOCK HELD" in (r.get("stdout", "") + r.get("stderr", ""))
                       for r in runs)
            if lock:
                return refuse("INSTALLER_LOCK_HELD",
                              "another update-skills.sh holds /tmp/openclaw-update.lock",
                              out, mode)

            root = install_root(d, sb)
            files = cc.manifest_tree(root)
            src_files = cc.manifest_tree(staged / spec["source_subdir"])
            source = {"repo": repo, "revision": rev, "checkout": str(checkout),
                      "resolved_by": how, "subdir": spec["source_subdir"]}
            manifest = cc.distribution_manifest(d, root, files, source)
            manifest_path = Path(out) / ("clean-install-%s.manifest.json" % d)
            # never leave an empty manifest behind for a downstream reader; the
            # proof hook below then refuses it as missing, which is the point.
            if files:
                cc.write_json(manifest_path, manifest)

            check("real:%s:installer delivered the skill tree" % d, bool(files),
                  "installer rc=%s; %d files at %s"
                  % ([r.get("rc") for r in runs], len(files), root))
            check("real:%s:skill tree installed" % d, root.is_dir(), str(root))
            check("real:%s:manifest has files" % d, len(files) > 0,
                  "%d files, digest %s" % (len(files), manifest["manifest_sha256"][:16]))

            # installed content must be exactly the pinned source content
            same, same_detail = cc.compare_to_source(files, src_files)
            check("real:%s:installed tree matches pinned source" % d,
                  same, same_detail)

            vok, problems = cc.verify_manifest(root, files)
            check("real:%s:manifest digests verified" % d, vok,
                  "recomputed %d files" % len(files) if vok else problems[:3])

            proof_ok, proof_detail, proof_cmd = cc.loaded_source_proof(
                manifest_path, root)
            check("real:%s:loaded-source proof hook accepts manifest" % d,
                  proof_ok, proof_detail)
            receipt["loaded_source_proof_hook"][d] = {
                "command": proof_cmd, "ok": proof_ok, "detail": proof_detail}

            receipt["distributions"][d] = {
                "installer": [{"cmd": r.get("cmd"), "rc": r.get("rc"),
                               "stdout_tail": (r.get("stdout") or "")[-1200:],
                               "stderr_tail": (r.get("stderr") or "")[-1200:]}
                              for r in runs],
                "installed_path": str(root),
                "source": source,
                "manifest_path": str(manifest_path),
                "manifest": manifest,
                "loaded_source_proof_hook": {
                    "command": proof_cmd, "ok": proof_ok, "detail": proof_detail},
                "sandbox": str(sb.root),
            }
            if keep:
                sb.keep = True

    passed, failed, total = cc.summarize_checks(RESULTS)
    receipt["results"] = RESULTS
    receipt["status"] = "EXECUTED" if not failed else "FAILED"
    cc.stamp_evidence(receipt, FIXTURE)
    name = ("clean-install-canary.real.json" if not failed
            else "clean-install-canary.real.failed.json")
    cc.write_json(Path(out) / name, receipt)
    print("\nreal: %d/%d checks passed%s" % (len(passed), total,
          ("" if not failed else "; FAIL: " + ", ".join(failed))))
    print("wrote %s" % name)
    return 0 if not failed else 1


# ---------------------------------------------------------------- dry-run ----
def build_fake_distribution(dst, kind):
    """Synthetic distribution tree for --dry-run: skill dir + scoped files."""
    skill_rel = ONB_SKILL if kind == "onboarding" else str(NINE_SKILL_DIR)
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
            "acceptance_rows": ACCEPTANCE_ROWS,
            "boundary": "harness mechanics only; NO installer run, NO repository, "
                        "NO real root, NO acceptance point claimed",
            "results": RESULTS,
            "sandbox_shim_log": sb.shim_entries(),
        }
        cc.stamp_evidence(receipt, True)     # dry-run: never acceptance evidence
        cc.write_json(Path(out) / "clean-install-canary.dry.json", receipt)

    passed, failed, total = cc.summarize_checks(RESULTS)
    print("dry-run: %d/%d checks passed%s" % (len(passed), total,
          ("" if not failed else "; FAIL: " + ", ".join(failed))))
    return 0 if not failed else 1


# --------------------------------------------------------------- self-test ----
def run_self_test(a):
    """Prove the harness FAILS: unpinned, real, tampered, broken installer."""
    print("clean-install canary SELF-TEST (fail-closed battery)")
    here = Path(__file__).resolve()
    out = Path(a.out) / "self-test"
    out.mkdir(parents=True, exist_ok=True)

    # (a) unpinned vector -> exit 3, unchanged contract
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
          not (out / "unpinned" / "clean-install-canary.real.json").exists(),
          str(out / "unpinned"))

    # (b) real run with a pinned vector -> real manifest, digests verified
    real_out = out / "real"
    rc = run_real("onboarding", real_out, a.vector, timeout=a.timeout,
                  sandbox_base=a.sandbox_base, repo_roots=a.repo_root, keep=True)
    check("self-test:pinned real run exit 0", rc == 0, "rc=%d" % rc)
    manifest_path = None
    sandbox = None
    body = {}
    rec_path = real_out / "clean-install-canary.real.json"
    if rec_path.is_file():
        body = json.loads(rec_path.read_text(encoding="utf-8"))
        first = sorted(body.get("distributions", {}))[0]
        manifest_path = Path(body["distributions"][first]["manifest_path"])
        sandbox = Path(body["distributions"][first]["installed_path"])
    check("self-test:real manifest has >0 files",
          bool(manifest_path and manifest_path.is_file()
               and json.loads(manifest_path.read_text())["file_count"] > 0),
          str(manifest_path))

    # (b2) a MISSING manifest must be refused by the same hook
    r = subprocess.run([sys.executable, str(here), "--verify-manifest",
                        str(out / "does-not-exist.json"),
                        "--verify-root", str(sandbox or out)],
                       capture_output=True, text=True)
    check("self-test:missing manifest -> non-zero", r.returncode != 0,
          "rc=%d %s" % (r.returncode, (r.stdout or "").strip().splitlines()[-1:]))

    # (b3) ONE plausible file is not an install. A manifest carrying only the
    # seeded fixture file must be refused even though it is non-empty and its
    # digest matches the bytes on disk.
    if sandbox and (sandbox / "SKILL.md").is_file():
        one = out / "manifest-one-file.json"
        cc.write_json(one, {
            "schema": "blackceo.skill75.distribution-manifest/v1",
            "distribution": "onboarding",
            "installed_path": str(sandbox),
            "source": {"repo": "openclaw-onboarding", "revision": "0" * 40},
            "file_count": 1,
            "manifest_sha256": cc.manifest_digest({"SKILL.md": cc.sha256_file(sandbox / "SKILL.md")}),
            "files": {"SKILL.md": cc.sha256_file(sandbox / "SKILL.md")},
        })
        r = subprocess.run([sys.executable, str(here), "--verify-manifest",
                            str(one), "--verify-root", str(sandbox)],
                           capture_output=True, text=True)
        line = [l for l in (r.stdout or "").splitlines() if "[FAIL]" in l]
        check("self-test:one-file manifest -> refused", r.returncode != 0,
              "rc=%d %s" % (r.returncode, line[-1:] or [""]))
        check("self-test:one-file refusal names the shape problem",
              "below the" in (r.stdout or ""),
              (line[-1:] or [""])[0][:160])
    if manifest_path and sandbox:
        ok, detail, _cmd = cc.loaded_source_proof(manifest_path, sandbox)
        check("self-test:loaded-source proof verifies manifest", ok, detail)

        # (c) tamper one installed file -> hook exits non-zero, names the file
        victim = sorted(json.loads(manifest_path.read_text())["files"])[0]
        (sandbox / victim).write_text("# tampered by self-test\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(here),
                            "--verify-manifest", str(manifest_path),
                            "--verify-root", str(sandbox), "--out", str(out / "tamper")],
                           capture_output=True, text=True)
        check("self-test:tampered file -> non-zero", r.returncode != 0,
              "rc=%d" % r.returncode)
        check("self-test:tamper names the file", victim in (r.stdout + r.stderr),
              victim)

    # (d) broken installer -> non-zero, no success receipt. The checkout is a
    # real git repo at a real revision, so only the INSTALLER is broken.
    broken = out / "broken-tree"
    broken.mkdir(parents=True, exist_ok=True)
    (broken / "update-skills.sh").write_text(
        "#!/bin/sh\necho 'simulated installer failure' >&2\nexit 7\n",
        encoding="utf-8")
    (broken / "75-drama-song-ad-factory").mkdir(exist_ok=True)
    (broken / "75-drama-song-ad-factory" / "SKILL.md").write_text(
        "# broken fixture\n", encoding="utf-8")
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "-c", "user.email=canary@example.invalid",
                 "-c", "user.name=canary", "commit", "-q", "-m", "broken fixture"]):
        subprocess.run(cmd, cwd=str(broken), check=False,
                       capture_output=True, text=True)
    rev = subprocess.run(["git", "-C", str(broken), "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    bv = {"schema": cc.VECTOR_SCHEMA, "pinned": True, "pinned_at": "self-test",
          "pinned_by": "self-test",
          "repositories": {n: {"revision": rev, "path": str(broken)}
                           for n in cc.VECTOR_REPOS}}
    bv_path = out / "vector-broken.json"
    cc.write_json(bv_path, bv)
    broken_out = out / "broken"
    r = subprocess.run([sys.executable, str(here), "--vector", str(bv_path),
                        "--out", str(broken_out), "--dist", "onboarding"],
                       capture_output=True, text=True)
    check("self-test:broken installer -> non-zero", r.returncode != 0,
          "rc=%d %s" % (r.returncode, (r.stdout or "").strip().splitlines()[-1:]))
    check("self-test:broken installer writes no success receipt",
          not (broken_out / "clean-install-canary.real.json").exists(),
          str(broken_out))

    passed, failed, total = cc.summarize_checks(RESULTS)
    print("\nself-test: %d/%d checks passed%s" % (len(passed), total,
          ("" if not failed else "; FAIL: " + ", ".join(failed))))
    return 0 if not failed else 1


def main():
    global FIXTURE
    ap = argparse.ArgumentParser()
    ap.add_argument("--vector")
    ap.add_argument("--dist", choices=["onboarding", "999", "both"], default="both")
    ap.add_argument("--out")
    ap.add_argument("--fixture", action="store_true",
                    help="label the receipt FIXTURE: the source is a fixture, not "
                         "a real distribution install; never acceptance evidence")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--timeout", type=int, default=900,
                    help="per-installer timeout in seconds (fail closed)")
    ap.add_argument("--sandbox-base", default=None,
                    help="parent dir for the scratch sandbox (default: --out)")
    ap.add_argument("--repo-root", action="append", default=[],
                    metavar="NAME=PATH", help="local checkout for a vector repo")
    ap.add_argument("--keep", action="store_true", help="keep the sandbox for inspection")
    ap.add_argument("--verify-manifest", metavar="MANIFEST")
    ap.add_argument("--verify-root", metavar="INSTALL_ROOT")
    ap.add_argument("--allow-paid", action="store_true",
                    help="REFUSED — A11 stays blocked")
    ap.add_argument("--allow-live-send", action="store_true",
                    help="REFUSED — A11 stays blocked")
    a = ap.parse_args()
    FIXTURE = bool(a.fixture)

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
        if a.out:
            # this path never invokes an installer, so it is always a FIXTURE
            doc = {"schema": "blackceo.skill75.canary.verify-manifest/v1",
                   "unit": "SFR-007", "mode": "verify-manifest",
                   "acceptance_rows": ACCEPTANCE_ROWS,
                   "manifest": str(a.verify_manifest),
                   "root": str(a.verify_root), "ok": bool(ok), "detail": detail}
            cc.stamp_evidence(doc, True)
            cc.write_json(Path(a.out) / "verify-manifest.receipt.json", doc)
        if not ok:
            print("  [FAIL] loaded-source proof: %s" % detail)
            return 1
        print("  [PASS] loaded-source proof: %s" % detail)
        return 0

    if not a.vector or not a.out:
        ap.error("--vector and --out are required (except with --verify-manifest)")

    a.repo_root = dict(kv.split("=", 1) for kv in a.repo_root if "=" in kv)
    if a.sandbox_base is None:
        a.sandbox_base = a.out
    if a.dry_run:
        return run_dry(a.dist, a.out)
    if a.self_test:
        return run_self_test(a)
    return run_real(a.dist, a.out, a.vector, timeout=a.timeout,
                    sandbox_base=a.sandbox_base, repo_roots=a.repo_root,
                    keep=a.keep)


if __name__ == "__main__":
    sys.exit(main())
