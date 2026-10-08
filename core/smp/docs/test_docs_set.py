#!/usr/bin/env python3
"""test_docs_set.py — mocked structural tests for the SMP-W2-U3 docs set.

Unit SMP-W2-U3, wave 2 of the Skill 35 social media planner integration
(owner D27 / D35, 2026-10-07, plan section 6.15).

What these tests are:
  * STRUCTURAL — every check reads the staged files under this directory and
    asserts the weekly-planner integration is actually present, complete and
    self-consistent. No file outside this directory is read or written.
  * MOCKED — the shell fixtures run in a throwaway HOME with `curl`, `wget`
    and `nc` replaced by stubs that exit 99, so any network attempt fails the
    suite. The weekly step is a fake that only records its argv.
  * OFFLINE — no network client is imported, no KIE call is made, no media
    file is produced, no operator path is required.

Exit 0 when every check passes, 1 otherwise.

  python3 test_docs_set.py            run every check against this directory
  python3 test_docs_set.py --list     print check names
  python3 test_docs_set.py --root DIR run against another copy (control runs)
"""
from __future__ import annotations

import argparse
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

REQUIRED = [
    "README.md",
    "SKILL.md",
    "INSTRUCTIONS.md",
    "INSTALL.md",
    "QC.md",
    "qc-skill35.sh",
    "qc-social-media-planner.sh",
    "scripts/weekly-batch.sh",
    "scripts/run-publishing-cycle.sh",
    "scripts/kie_media_plan.py",
    "test_docs_set.py",
]
# The pipeline SOP is NOT staged under this directory: manual H1 git-moved it
# into the video department's role library, which is where 75-drama-song-ad-
# factory/SKILL.md:142 and INSTRUCTIONS.md:126 already point (and where this
# file's own README table has always named it as the destination). Keep the
# copy here gone — one canonical SOP, verified at its real home below.
SOP_NAME = "SOP--drama-song-ad-pipeline.md"
SOP_REL = ("../../../23-ai-workforce-blueprint/templates/role-library/"
           "video/sops/" + SOP_NAME)
EXECUTABLE = [
    "qc-skill35.sh",
    "qc-social-media-planner.sh",
    "scripts/weekly-batch.sh",
    "scripts/run-publishing-cycle.sh",
    "scripts/kie_media_plan.py",
]
SHELL_FILES = [
    "qc-skill35.sh",
    "qc-social-media-planner.sh",
    "scripts/weekly-batch.sh",
    "scripts/run-publishing-cycle.sh",
]
MEDIA_EXT = {
    ".mp4", ".mov", ".m4v", ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".srt",
}
# Tokens that would mean a second KIE client, or a direct KIE host, exists
# anywhere in the set. Skill 74 (74-kie-live-adapter) is the only KIE path.
# The literals are assembled from fragments so this detector file does not
# fail its own scan.
SECOND_KIE_CLIENT = [
    "api." + "kie.ai",
    "KIE_" + "BASE_URL",
    "record" + "Info",
    "kie.ai" + "/v1",
]
BANNED_PATHS = ["/Us" + "ers/", "/ho" + "me/", "black" + "ceomacmini"]
CORE_MODULES = [
    "core/smp/weekly_step/",
    "core/smp/initial_questions/",
    "core/smp/saturday_prompt/",
    "core/smp/length_routing/",
    "core/smp/stories_teaser/",
    "core/smp/sheet_schema_130/",
    "core/smp/sheet_migration/",
]

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


def read(root, rel):
    return (root / rel).read_text(encoding="utf-8")

def read_sop(root):
    """Read the pipeline SOP at its canonical video-department home."""
    return read(root, SOP_REL)


def lines_of(text):
    return [ln.strip() for ln in text.splitlines()]


# ---------------------------------------------------------------- structure ---


@check("required files present (11)")
def c_required(root):
    missing = [r for r in REQUIRED if not (root / r).is_file()]
    assert not missing, "missing: %s" % ", ".join(missing)


@check("no unexpected files, no media, no .git inside the set")
def c_no_extra(root):
    allowed = set(REQUIRED)
    bad, media = [], []
    for p in root.rglob("*"):
        if "__pycache__" in p.parts or p.name == ".pytest_cache":
            continue
        if ".git" in p.parts:
            bad.append(str(p.relative_to(root)))
            continue
        if p.is_dir():
            continue
        rel = str(p.relative_to(root))
        if p.suffix.lower() in MEDIA_EXT:
            media.append(rel)
        if rel not in allowed:
            bad.append(rel)
    assert not media, "media files: %s" % media
    assert not bad, "unexpected entries: %s" % bad


@check("the five entry-point scripts are executable")
def c_exec(root):
    notx = [r for r in EXECUTABLE if not os.access(root / r, os.X_OK)]
    assert not notx, "not executable: %s" % ", ".join(notx)


# ------------------------------------------------------------------- syntax ---


@check("bash -n on every staged shell script")
def c_bash_syntax(root):
    for rel in SHELL_FILES:
        proc = subprocess.run(["bash", "-n", str(root / rel)],
                              capture_output=True, text=True)
        assert proc.returncode == 0, "%s: %s" % (rel, proc.stderr.strip())


@check("py_compile on kie_media_plan.py and this test file")
def c_py_syntax(root):
    for rel in ("scripts/kie_media_plan.py", "test_docs_set.py"):
        py_compile.compile(str(root / rel), doraise=True)


# -------------------------------------------------------- SKILL.md contract ---


@check("SKILL.md version bumped to 3.7.0")
def c_skill_version(root):
    assert 'version: "3.7.0"' in read(root, "SKILL.md")


@check("SKILL.md carries the Weekly Drama Song Ad section")
def c_skill_section(root):
    text = read(root, "SKILL.md")
    assert "## Weekly Drama Song Ad" in text
    for needle in ("core/smp/weekly_step/", "74-kie-live-adapter",
                   "drama-song-skipped.json", "59.0", "88.0-95.0",
                   "15-second teaser", "Google Business Profile",
                   "1.3.0", "private KIE client", "drama-song-style.json"):
        assert needle in text, "SKILL.md missing %r" % needle


@check("SKILL.md lists the weekly ad as a weekly content type and in the owner Q&A")
def c_skill_content_types(root):
    text = read(root, "SKILL.md")
    assert "Weekly drama song ad" in text, "weekly content-type bullet missing"
    assert "one 9:16 drama song video from the Theme of the Week" in text, \
        "owner Q&A content-types statement missing the weekly ad"
    assert "> - One 9:16 drama song video built from the Theme of the Week" in text, \
        "owner Q&A example bullet missing the weekly ad"


@check("SKILL.md keeps the enabled-channels model (no stale platform list)")
def c_skill_no_stale(root):
    text = read(root, "SKILL.md")
    assert not re.search(
        r"8 platforms.*WordPress.*Medium.*Substack.*LinkedIn.*GHL blog",
        text), "stale platform list reintroduced"
    for name in ("Instagram", "TikTok", "Pinterest", "Google Business Profile"):
        assert name in text, "primary channel %s dropped" % name


# ------------------------------------------------- INSTRUCTIONS.md contract ---


@check("INSTRUCTIONS.md version bumped to 10.16.0")
def c_ins_version(root):
    assert "v10.16.0" in read(root, "INSTRUCTIONS.md")


@check("INSTRUCTIONS.md has the weekly drama-song step section + module table")
def c_ins_section(root):
    text = read(root, "INSTRUCTIONS.md")
    assert "## Weekly drama-song step" in text
    for mod in CORE_MODULES:
        assert mod in text, "module %s not wired in INSTRUCTIONS.md" % mod


@check("INSTRUCTIONS.md states gate, cap, window, routing, skip artifact")
def c_ins_rules(root):
    text = read(root, "INSTRUCTIONS.md")
    for needle in ("drama-song-skipped.json", "59.0", "88.0-95.0",
                   "private KIE client", "Google Business Profile",
                   "15-second teaser", "active",
                   "social-planner-row-append", "1.3.0"):
        assert needle in text, "INSTRUCTIONS.md missing %r" % needle


@check("INSTRUCTIONS.md documents where the step runs (weekly-batch + cron marker)")
def c_ins_runs(root):
    text = read(root, "INSTRUCTIONS.md")
    assert "weekly-batch.sh" in text
    assert "weekly-theme-last-run.json" in text
    assert "DRAMA_SONG_THEME" in text


# --------------------------------------------------------- INSTALL.md contract ---


@check("INSTALL.md carries Step 8.6 and the style-file checklist item")
def c_install_step(root):
    text = read(root, "INSTALL.md")
    assert "### Step 8.6" in text, "Step 8.6 missing"
    assert "drama-song-style.json" in text, "style file path missing"
    assert text.count("drama-song-style.json") >= 2, "style file not in checklist"


@check("INSTALL.md keeps the furnace guard and adds no heartbeat drama block")
def c_install_furnace(root):
    text = read(root, "INSTALL.md")
    assert "FURNACE RULE" in text, "furnace rule removed"
    assert "openclaw cron add" in text or "register-weekly-cron.sh" in text
    assert not re.search(r"###.*Saturday 8:00 AM.*Social Media", text), \
        "ungated Saturday HEARTBEAT block reintroduced"
    assert not re.search(r"###.*[Dd]rama [Ss]ong.*HEARTBEAT", text), \
        "drama-song heartbeat block introduced"


# ------------------------------------------------------------ QC.md contract ---


@check("QC.md has the Weekly Drama Song Ad checklist")
def c_qc_section(root):
    text = read(root, "QC.md")
    assert "## Weekly Drama Song Ad" in text
    for needle in ("59.0", "88.0-95.0", "Google Business Profile",
                   "15-second teaser", "drama-song-skipped.json",
                   "1.3.0", "Skill 74", "only KIE path",
                   "no network call", "price + 20%"):
        assert needle in text, "QC.md missing %r" % needle


@check("QC.md adds the cross-file documentation-integrity checks")
def c_qc_integrity(root):
    text = read(root, "QC.md")
    assert "one 9:16 ad per week from the Theme of the Week" in text
    assert ("module the weekly step wires (weekly_step, initial_questions, "
            "saturday_prompt, length_routing, stories_teaser, "
            "sheet_schema_130, sheet_migration)") in text


# ------------------------------------------------------- QC shell scripts ---


@check("qc-skill35.sh has Section J with the drama-song assertions")
def c_qc_section_j(root):
    text = read(root, "qc-skill35.sh")
    assert "Section J: weekly drama-song integration" in text
    for needle in ("core/smp/weekly_step", "74-kie-live-adapter",
                   "drama-song-skipped.json", "private KIE client",
                   "1.3.0", "Weekly Drama Song Ad", "15-second teaser",
                   "drama-song-style.json", "run_drama_song_step",
                   "drama_song"):
        assert needle in text, "qc-skill35.sh Section J missing %r" % needle
    assert text.count("Section J: weekly drama-song integration") == 1


@check("qc-skill35.sh Sections A-I and the Fix #1/#2/#3 guards survive")
def c_qc_no_regression(root):
    text = read(root, "qc-skill35.sh")
    for needle in ("Section A: Prerequisites", "Section B: GHL credentials",
                   "Section I: Fix assertions", "Fix #1", "Fix #2", "Fix #3",
                   "skill35-weekly-theme", "FURNACE",
                   "Result: $PASS passed | $FAIL failed"):
        assert needle in text, "qc-skill35.sh lost %r" % needle
    assert text.rstrip().endswith("fi"), "qc-skill35.sh tail damaged"


@check("qc-social-media-planner.sh still delegates to qc-skill35.sh")
def c_qc_shim(root):
    text = read(root, "qc-social-media-planner.sh")
    assert 'exec bash "$CANON" "$@"' in text
    assert "Section J" in text, "shim does not point at Section J"


# ---------------------------------------------------- weekly cycle scripts ---


@check("weekly-batch.sh defines and calls run_drama_song_step exactly once")
def c_batch_function(root):
    text = read(root, "scripts/weekly-batch.sh")
    assert "run_drama_song_step() {" in text, "function not defined"
    calls = [i for i, ln in enumerate(text.splitlines())
             if ln.strip() == "run_drama_song_step"]
    assert len(calls) == 1, "expected exactly 1 call, found %d" % len(calls)
    gate = text.find("# ---------- ensure calendar exists ----------")
    assert gate != -1, "calendar gate anchor missing"
    assert calls[0] < text[:gate].count("\n"), \
        "drama-song step must run before the calendar gate"


@check("weekly-batch.sh step is fail-soft: warn + return 0, no exit")
def c_batch_failsoft(root):
    text = read(root, "scripts/weekly-batch.sh")
    body = text.split("run_drama_song_step() {", 1)[1].split(
        "\n}\n", 1)[0]
    assert "return 0" in body
    assert not re.search(r"^\s*exit\s", body, re.M), \
        "drama-song step must never exit the batch"
    assert "private KIE client" in body, "KIE-only-path note missing"
    assert "drama-song-skipped.json" in body, "skip artifact not named"


@check("weekly-batch.sh keeps its exit contract and version is 10.16.0")
def c_batch_version(root):
    text = read(root, "scripts/weekly-batch.sh")
    assert 'SCRIPT_VERSION="v10.16.0"' in text
    assert "ZERO_WORK_EXIT=10" in text
    assert "exit 4" in text and "exit 6" in text


@check("run-publishing-cycle.sh manifest carries the drama_song block")
def c_cycle_manifest(root):
    text = read(root, "scripts/run-publishing-cycle.sh")
    assert '"drama_song": {' in text
    for needle in ('"kie_path": "skill-74"', '"one_per_week": True',
                   '"second_kie_client": False', '"hard_cap_s": 59.0',
                   '"ninety_window_s": [88.0, 95.0]',
                   '"sheet_schema_version": "1.3.0"',
                   '"style chosen", "status", "KIE cost", "video link", '
                   '"channels posted"'):
        assert needle in text, "manifest missing %s" % needle
    assert 'SCRIPT_VERSION="v10.16.0"' in text


@check("run-publishing-cycle.sh row-append note names the schema owners")
def c_cycle_row_append(root):
    text = read(root, "scripts/run-publishing-cycle.sh")
    assert "social-planner-row-append" in text
    assert "SMP-W2-U1" in text and "SMP-W2-U2" in text
    assert "never invents a column name" in text


# ------------------------------------------------------- kie_media_plan.py ---


@check("kie_media_plan.py reports the drama_song route, stdlib only")
def c_kie_plan(root):
    text = read(root, "scripts/kie_media_plan.py")
    assert '"drama_song": {' in text
    for needle in ('"kie_path": "skill-74"',
                   '"paid_calls_when_skipped": 0',
                   '"second_kie_client": False',
                   '"kie_mode_required": "active"',
                   '"sheet_schema_version": "1.3.0"'):
        assert needle in text, "kie_media_plan missing %s" % needle
    for banned in ("import urllib", "import socket", "import requests",
                   "import httpx", "import aiohttp", "http.client"):
        assert banned not in text, "network import in kie_media_plan.py: %s" % banned


# ------------------------------------------------------------------- SOP ---


@check("SOP carries the Weekly planner integration section")
def c_sop(root):
    text = read_sop(root)
    assert "## Weekly planner integration" in text
    for needle in ("core/smp/weekly_step/", "59.0", "88.0-95.0",
                   "15-second teaser", "Google Business Profile",
                   "drama-song-style.json", "drama-song-skipped.json",
                   "Skill 74 stays the only", "1.3.0",
                   "approved price plus the 20% retake allowance"):
        assert needle in text, "SOP missing %r" % needle


@check("SOP keeps its original doctrine sections")
def c_sop_no_regression(root):
    text = read_sop(root)
    for needle in ("## DMAIC Coverage Map", "## Define", "### DS-1",
                   "## Measure", "## Analyze", "## Improve", "## Control",
                   "### DS-11", "## Hand-offs", "## Batch mode"):
        assert needle in text, "SOP lost %r" % needle


# ------------------------------------------------------------------ hygiene ---


@check("no operator paths, no box slug anywhere in the set")
def c_no_operator_paths(root):
    for rel in list(REQUIRED) + [SOP_REL]:
        text = read(root, rel)
        for banned in BANNED_PATHS:
            assert banned not in text, "%s carries %r" % (rel, banned)


@check("no second KIE client and Skill 74 is named as the only KIE path")
def c_skill74_only(root):
    for rel in list(REQUIRED) + [SOP_REL]:
        text = read(root, rel)
        for banned in SECOND_KIE_CLIENT:
            assert banned not in text, "%s names a second KIE client (%s)" % (
                rel, banned)
    # Every file that talks about the weekly ad's KIE route names Skill 74.
    for rel in ("SKILL.md", "INSTRUCTIONS.md", "QC.md",
                "scripts/run-publishing-cycle.sh", "scripts/kie_media_plan.py",
                SOP_REL):
        text = read(root, rel)
        assert ("74-kie-live-adapter" in text or "skill-74" in text
                or "Skill 74" in text), "%s never names Skill 74" % rel


@check("README states ships-only-via-batch-train and no PR/merge")
def c_batch_train(root):
    text = read(root, "README.md")
    assert "Ships only via the onboarding batch train" in text
    assert "not merged" in text or "no pull" in text.lower()
    assert "SMP-W2-U3" in text
    assert not (root / ".git").exists()


# ------------------------------------------------- zero paid calls (mocked) ---


def _path_with_dead_net(tmp):
    """PATH whose curl/wget/nc exit 99 — any network attempt fails loudly."""
    bin_dir = Path(tmp) / "deadnet-bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name in ("curl", "wget", "nc", "ncat", "ssh"):
        p = bin_dir / name
        p.write_text("#!/bin/sh\necho \"NETWORK CALL BANNED: $0 $*\" >&2\nexit 99\n")
        p.chmod(0o755)
    return str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


def _run_batch(root, tmp, extra_env=None, step_rc=None, with_step=True,
               with_theme=True):
    """Run a staged copy of weekly-batch.sh in an isolated HOME."""
    work = Path(tmp) / "skill35"
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(root, work)
    home = Path(tmp) / "home"
    if home.exists():
        shutil.rmtree(home)
    (home / ".openclaw").mkdir(parents=True)

    if with_step:
        step = Path(tmp) / "core" / "smp" / "weekly_step" / "weekly_step.py"
        step.parent.mkdir(parents=True, exist_ok=True)
        step.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "json.dump({'argv': sys.argv[1:]},\n"
            "          open(os.environ['FAKE_STEP_RECORD'], 'w'))\n"
            "sys.exit(int(os.environ.get('FAKE_STEP_RC', '0')))\n")
        step.chmod(0o755)

    record = Path(tmp) / "step-record.json"
    if record.exists():
        record.unlink()

    env = dict(os.environ)
    env["HOME"] = str(home)
    env["PATH"] = _path_with_dead_net(tmp)
    env["FAKE_STEP_RECORD"] = str(record)
    if step_rc is not None:
        env["FAKE_STEP_RC"] = str(step_rc)
    if with_theme:
        env["DRAMA_SONG_THEME"] = "Test Theme of the Week"
    if extra_env:
        env.update(extra_env)
    for k in ("DRAMA_SONG_THEME",):
        if not with_theme:
            env.pop(k, None)

    proc = subprocess.run(
        ["bash", str(work / "scripts" / "weekly-batch.sh")],
        capture_output=True, text=True, env=env, timeout=60)
    return proc, record, home


@check("zero paid calls: kie_media_plan builds offline with sockets blocked")
def c_zero_paid_kie_plan(root):
    scripts = root / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        import kie_media_plan  # noqa: E402
    finally:
        try:
            sys.path.remove(str(scripts))
        finally:
            sys.modules.pop("kie_media_plan", None)

    import socket

    def boom(*_a, **_k):
        raise AssertionError("network call attempted")

    saved = (socket.socket, socket.create_connection, socket.getaddrinfo)
    socket.socket = boom
    socket.create_connection = boom
    socket.getaddrinfo = boom
    try:
        plan = kie_media_plan.build_plan(None, None, str(root), "/nonexistent")
    finally:
        socket.socket, socket.create_connection, socket.getaddrinfo = saved

    assert plan["drama_song"]["kie_path"] == "skill-74"
    assert plan["drama_song"]["paid_calls_when_skipped"] == 0
    assert plan["drama_song"]["second_kie_client"] is False
    assert json.dumps(plan)  # round-trips


@check("zero paid calls: --help of both shell scripts runs with net blocked")
def c_zero_paid_help(root):
    with tempfile.TemporaryDirectory(prefix="smp-w2-u3-help-") as tmp:
        env = dict(os.environ)
        env["PATH"] = _path_with_dead_net(tmp)
        for rel in ("scripts/weekly-batch.sh", "scripts/run-publishing-cycle.sh"):
            proc = subprocess.run(["bash", str(root / rel), "--help"],
                                  capture_output=True, text=True, env=env,
                                  timeout=60)
            assert proc.returncode == 0, "%s --help rc=%s %s" % (
                rel, proc.returncode, proc.stderr[-400:])


@check("weekly-batch stays idle (exit 10) when the weekly step is not staged")
def c_batch_no_step(root):
    with tempfile.TemporaryDirectory(prefix="smp-w2-u3-nostep-") as tmp:
        proc, _record, _home = _run_batch(root, tmp, with_step=False)
        out = proc.stdout + proc.stderr
        assert proc.returncode == 10, "expected 10, got %s\n%s" % (
            proc.returncode, out[-1500:])
        assert "not staged on this box yet" in out
        assert "NETWORK CALL BANNED" not in out


@check("weekly-batch runs the weekly step once with the resolved theme")
def c_batch_runs_step(root):
    with tempfile.TemporaryDirectory(prefix="smp-w2-u3-run-") as tmp:
        proc, record, _home = _run_batch(root, tmp)
        out = proc.stdout + proc.stderr
        assert proc.returncode == 10, "batch exit contract broke: %s\n%s" % (
            proc.returncode, out[-1500:])
        assert record.is_file(), "weekly step never invoked:\n%s" % out[-1500:]
        argv = json.loads(record.read_text())["argv"]
        assert argv[:2] == ["--theme", "Test Theme of the Week"], argv
        assert "--out-dir" in argv, argv
        assert "drama-song step finished" in out
        assert "NETWORK CALL BANNED" not in out


@check("weekly-batch skips (not fails) when no Theme of the Week exists")
def c_batch_no_theme(root):
    with tempfile.TemporaryDirectory(prefix="smp-w2-u3-notheme-") as tmp:
        proc, record, _home = _run_batch(root, tmp, with_theme=False)
        out = proc.stdout + proc.stderr
        assert proc.returncode == 10, "expected 10, got %s\n%s" % (
            proc.returncode, out[-1500:])
        assert "no Theme of the Week" in out
        assert not record.exists(), "step ran without a theme"


@check("weekly-batch survives a failing weekly step (fail-soft, still exit 10)")
def c_batch_step_fails(root):
    with tempfile.TemporaryDirectory(prefix="smp-w2-u3-fail-") as tmp:
        proc, record, _home = _run_batch(root, tmp, step_rc=4)
        out = proc.stdout + proc.stderr
        assert record.is_file(), "step should still have been attempted"
        assert proc.returncode == 10, "a failing step broke the batch: %s\n%s" % (
            proc.returncode, out[-1500:])
        assert "drama-song step rc=4" in out
        assert "NETWORK CALL BANNED" not in out


# ----------------------------------------------------------------- runner ---


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(HERE),
                    help="docs set root to test (default: this directory)")
    ap.add_argument("--list", action="store_true", help="print check names")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    if args.list:
        for name, _fn in CHECKS:
            print(name)
        print("TOTAL %d" % len(CHECKS))
        return 0

    passed = failed = 0
    for name, fn in CHECKS:
        try:
            fn(root)
        except Exception as exc:  # noqa: BLE001 — every failure is reported
            failed += 1
            print("  FAIL  %s\n        %s: %s"
                  % (name, type(exc).__name__, exc))
        else:
            passed += 1
            print("  ok    %s" % name)

    print("")
    print("DOCS-SET TESTS: %d ok / %d failed / %d total"
          % (passed, failed, passed + failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
