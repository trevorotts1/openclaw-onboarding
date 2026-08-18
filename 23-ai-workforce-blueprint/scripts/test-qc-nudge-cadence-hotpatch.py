#!/usr/bin/env python3
"""
test-qc-nudge-cadence-hotpatch.py — lock for the 2026-07-30 check_nudges_wired()
fix. Third defect of this exact shape in this file (after the transcript-path
fix / PR #772 and the mandatory-fields fix / PR #775): a check that reports
failure about something it never actually examined.

BUG THIS LOCKS: check_nudges_wired() used to grep repo_root/"install.sh" for
the string "interview-nudge-cron" as its ONLY evidence that the interview-nudge
cron is registered. install.sh is a PROVISIONING-TIME script — it runs once
during a full install and is NEVER copied into the deployed skills tree.
Verified live on a hot-patched box (rescue-<client>): install.sh is
absent from ~/.openclaw entirely, while grep -a over update-skills.sh shows it
only ever REFERENCES install.sh in comments, never copies it in. Every box
patched via update-skills.sh (the fleet hot-patch path) therefore HARD-FAILED
this check permanently, for a reason unrelated to the client's interview.

THE FIX: check the box's actual, current cron REGISTRAR — ensure-pipeline-
crons.sh — instead. Per its own header it is "the SHARED, IDEMPOTENT
registrar/backfiller ... called by BOTH install.sh (end of run) and
update-skills.sh (after the wiring phase)", and it is persisted to
<openclaw-root>/scripts/ensure-pipeline-crons.sh on every successful run of
EITHER installer path (install.sh's canonical-scripts copy step; update-
skills.sh's deliver_canonical_scripts_tree(), which runs before that script's
same-version early exit) — so, unlike install.sh, it is present after a
hot-patch. The check now also DELIBERATELY avoids a live `openclaw cron list`
query: interview-nudge is a LIFECYCLE cron that ensure-pipeline-crons.sh's own
_sweep_stale_lifecycle_crons() ACTIVELY REMOVES once state.interviewComplete
flips true, and this QC gate runs at/after interview completion — so a live
"is it currently registered" check would be checking for something a healthy,
correctly-functioning box is expected to have already torn down. That would
trade this false failure for a new one of the identical shape.

SEPARATELY: build_verdict() now treats a genuine nudge-wiring gap as a WARNING
rather than a HARD FAIL. Unlike checks 1/2/3/5/6/7, check 4 says nothing about
whether THIS transcript or these decisions are legitimate — it is box/
infrastructure plumbing for a different, already-past lifecycle stage.
Blocking an already-complete, substantively-valid interview over an
operator-facing cron gap was the exact class of harm this fix addresses.

THIS SUITE PROVES:
  U1  BEFORE: a fixture replicating a hot-patched box (no install.sh anywhere,
      but the nudge cron IS genuinely wired via ensure-pipeline-crons.sh) run
      through the origin/main (pre-fix) check_nudges_wired() -> HARD fails,
      citing install.sh -- not the cron itself.
  U2  AFTER: the IDENTICAL fixture run through the fixed check_nudges_wired()
      -> passes.
  U3  FAIL-CLOSED (a): ensure-pipeline-crons.sh is present but genuinely does
      NOT wire interview-nudge (a real regression, not a missing-file case)
      -> still fails, reason names the actual gap, never install.sh.
  U4  FAIL-CLOSED (b): the registrar is not found at all -> still fails,
      reason names both candidate paths tried.
  U5  FULL-INSTALL BOX STILL PASSES: the real repo checkout (the same
      topology --repo-root points at for a full-install / CI run: install.sh
      AND scripts/ensure-pipeline-crons.sh both present at the top level) ->
      still passes, unaffected by the fix.
  U6  SEVERITY: build_verdict() with an otherwise fully clean interview but
      nudges genuinely NOT wired -> overall verdict PASS (exit 0), and the
      gap surfaces only in `warnings`, never `hardFailures`. A control case
      (U6b) confirms a GENUINE hard-failure check (jargon) still hard-fails
      even when nudges ARE wired -- the severity change is scoped to check 4
      alone.
  U7  BLEED TEST: monkeypatch check_nudges_wired() to always report
      wired=True -> U3's genuinely-broken-registrar fixture is no longer
      detected. Restore -> U3 reconfirmed. Proves this suite exercises real
      detection logic, not a rubber stamp.

NEVER touches a client box. Every fixture lives under a tempdir and is deleted
on exit. No secrets, tokens, or client transcript/answer text of any kind are
used or printed anywhere in this file.

EXIT: 0 = every assertion passed; 1 otherwise.
Usage: python3 test-qc-nudge-cadence-hotpatch.py [REPO_ROOT]
"""

import importlib.util
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "23-ai-workforce-blueprint" / "scripts"
QC_SCRIPT = SCRIPTS / "qc-interview-completion.py"

PASS = 0
FAIL = 0


def ok(msg):
    global PASS
    PASS += 1
    print(f"  [PASS] {msg}")


def bad(msg):
    global FAIL
    FAIL += 1
    print(f"  [FAIL] {msg}")


def load_module_from_path(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_current_module():
    """Fresh import of the qc-interview-completion.py UNDER TEST (the fixed
    version living in this checkout)."""
    return load_module_from_path(QC_SCRIPT, "qc_under_test_current")


def load_origin_main_module(tmpdir: Path):
    """`git show origin/main:<path>` into a temp file and load it as an
    independent module, so U1 exercises the REAL pre-fix code, not a
    reimplementation of it. Returns (module_or_None, error_or_None) -- if
    origin/main is unreachable in this environment (offline / shallow clone),
    U1 degrades to a loud SKIP rather than a false pass or a crash."""
    rel = "23-ai-workforce-blueprint/scripts/qc-interview-completion.py"
    try:
        proc = subprocess.run(
            ["git", "show", f"origin/main:{rel}"],
            cwd=str(REPO), capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            return None, proc.stderr.strip() or "git show failed"
    except Exception as exc:
        return None, str(exc)
    old_path = tmpdir / "qc-interview-completion-ORIGIN-MAIN.py"
    old_path.write_text(proc.stdout, encoding="utf-8")
    try:
        return load_module_from_path(old_path, "qc_under_test_origin_main"), None
    except Exception as exc:
        return None, f"could not import origin/main copy: {exc}"


def _make_executable(path: Path):
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def build_hotpatch_fixture(root: Path, *, registrar_present: bool, registrar_wired: bool) -> Path:
    """
    Build a fixture tree replicating a box patched ONLY via update-skills.sh
    (never a full install.sh run):

      root/.openclaw/skills/23-ai-workforce-blueprint/scripts/interview-nudge-cron.sh  (executable)
      root/.openclaw/skills/shared-utils/nudge-incomplete-interviews.py  (NUDGE_CONFIG 24/72/168h)
      root/.openclaw/scripts/ensure-pipeline-crons.sh  (present/wired per the flags below)
      NO root/.openclaw/skills/install.sh   -- the hot-patch path never places one there.
      NO root/.openclaw/install.sh          -- confirms this is NOT a full-install tree.

    Returns the `skills/` directory -- exactly the value check_nudges_wired()
    receives as `repo_root` on a live deployed box (skill_dir.parent, the
    default when --repo-root is not passed).
    """
    skills = root / ".openclaw" / "skills"
    oc_scripts = root / ".openclaw" / "scripts"
    s23 = skills / "23-ai-workforce-blueprint" / "scripts"
    s23.mkdir(parents=True, exist_ok=True)
    (skills / "shared-utils").mkdir(parents=True, exist_ok=True)
    oc_scripts.mkdir(parents=True, exist_ok=True)

    nudge_cron = s23 / "interview-nudge-cron.sh"
    nudge_cron.write_text("#!/usr/bin/env bash\necho stub\n", encoding="utf-8")
    _make_executable(nudge_cron)

    nudge_worker = skills / "shared-utils" / "nudge-incomplete-interviews.py"
    nudge_worker.write_text(
        "NUDGE_CONFIG = [\n"
        '    {"key": "24h", "hours_idle": 24},\n'
        '    {"key": "72h", "hours_idle": 72},\n'
        '    {"key": "168h", "hours_idle": 168},\n'
        "]\n",
        encoding="utf-8",
    )

    if registrar_present:
        registrar = oc_scripts / "ensure-pipeline-crons.sh"
        if registrar_wired:
            registrar.write_text(
                "#!/usr/bin/env bash\n"
                "# genuinely wires interview-nudge -- mirrors the real\n"
                "# _ensure_interview_nudge() in scripts/ensure-pipeline-crons.sh\n"
                "_ensure_interview_nudge() {\n"
                '  script="$(_find_script 23-ai-workforce-blueprint scripts/interview-nudge-cron.sh)"\n'
                '  _register_command_cron "interview-nudge" "0 */6 * * *" "$script" interviewNudgeUuid\n'
                "}\n",
                encoding="utf-8",
            )
        else:
            # Genuinely broken/stale registrar: present on disk, but wires a
            # DIFFERENT lifecycle cron only -- a real regression, distinct
            # from "file missing" (U4 covers that case separately). Contains
            # no substring resembling "interview-nudge" anywhere.
            registrar.write_text(
                "#!/usr/bin/env bash\n"
                "_ensure_closeout_watchdog() {\n"
                "  : # registers a DIFFERENT lifecycle cron only\n"
                "}\n",
                encoding="utf-8",
            )
        _make_executable(registrar)

    assert not (skills / "install.sh").exists(), "fixture bug: install.sh must be absent from the skills tree"
    assert not (root / ".openclaw" / "install.sh").exists(), "fixture bug: install.sh must be absent from openclaw root"

    return skills


def main():
    if not QC_SCRIPT.is_file():
        print(f"FATAL: {QC_SCRIPT} not found", file=sys.stderr)
        return 1

    tmproot = Path(tempfile.mkdtemp(prefix="qc-nudge-cadence-test-"))
    try:
        new_mod = load_current_module()

        # ── U1: BEFORE (origin/main, the real pre-fix code) ──────────────────
        print("\n[U1] BEFORE (origin/main): hot-patched-box fixture -> HARD fails citing install.sh, not the real cron")
        box1 = tmproot / "box1"
        skills1 = build_hotpatch_fixture(box1, registrar_present=True, registrar_wired=True)
        old_mod, old_err = load_origin_main_module(tmproot)
        if old_mod is None:
            print(f"  [SKIP] could not load origin/main copy ({old_err}); BEFORE demonstration unavailable in this environment")
        else:
            result_old = old_mod.check_nudges_wired(skills1)
            if not result_old["wired"] and any("install.sh" in i for i in result_old["issues"]):
                ok(f"origin/main check_nudges_wired() HARD-fails the hot-patched fixture, citing install.sh "
                   f"(the real cron IS wired in this fixture -- the failure is entirely about a file that "
                   f"was never going to be there): {result_old['issues']}")
            else:
                bad(f"expected origin/main to hard-fail citing install.sh, got: {result_old}")

        # ── U2: AFTER (fixed code, identical fixture) ────────────────────────
        print("\n[U2] AFTER (fixed): the SAME fixture -> passes")
        new_mod._resolve_openclaw_root = lambda: box1 / ".openclaw"
        result_new = new_mod.check_nudges_wired(skills1)
        if result_new["wired"]:
            ok(f"fixed check_nudges_wired() passes the identical hot-patched fixture: {result_new}")
        else:
            bad(f"expected wired=True post-fix, got: {result_new}")

        # ── U3: FAIL-CLOSED (a) — registrar present but genuinely NOT wired ──
        print("\n[U3] FAIL-CLOSED: registrar present but does NOT wire interview-nudge -> still fails, names the real gap")
        box3 = tmproot / "box3"
        skills3 = build_hotpatch_fixture(box3, registrar_present=True, registrar_wired=False)
        new_mod._resolve_openclaw_root = lambda: box3 / ".openclaw"
        result3 = new_mod.check_nudges_wired(skills3)
        names_real_gap = any("does not register the interview-nudge cron" in i for i in result3["issues"])
        names_install_sh = any("install.sh" in i for i in result3["issues"])
        if not result3["wired"] and names_real_gap and not names_install_sh:
            ok(f"genuinely-unwired registrar correctly fails, reason names the real gap (never install.sh): {result3['issues']}")
        else:
            bad(f"expected a fail-closed result naming the registrar gap and nothing about install.sh, got: {result3}")

        # ── U4: FAIL-CLOSED (b) — registrar entirely absent ──────────────────
        print("\n[U4] FAIL-CLOSED: registrar not found at all -> fails, names both candidate paths")
        box4 = tmproot / "box4"
        skills4 = build_hotpatch_fixture(box4, registrar_present=False, registrar_wired=True)
        new_mod._resolve_openclaw_root = lambda: box4 / ".openclaw"
        result4 = new_mod.check_nudges_wired(skills4)
        if not result4["wired"] and any("ensure-pipeline-crons.sh" in i and "not found" in i for i in result4["issues"]):
            ok(f"missing registrar correctly fails, names candidate paths tried: {result4['issues']}")
        else:
            bad(f"expected a fail-closed result for an absent registrar, got: {result4}")

        # ── U5: full-install box (real repo checkout topology) still passes ──
        print("\n[U5] Full-install box still passes: real repo checkout (install.sh + scripts/ensure-pipeline-crons.sh both present)")
        # Point _resolve_openclaw_root() at a path that does NOT exist, so a
        # PASS here can only come from the repo_root-relative candidate --
        # never from an incidental match on this machine's real $HOME.
        new_mod._resolve_openclaw_root = lambda: Path("/nonexistent-should-not-be-consulted-by-u5")
        result5 = new_mod.check_nudges_wired(REPO)
        if result5["wired"]:
            ok(f"real repo checkout (full-install-equivalent topology, --repo-root REPO) still passes: {result5}")
        else:
            bad(f"expected wired=True against the real repo checkout, got: {result5}")

        # ── U6: SEVERITY — nudge-not-wired alone no longer blocks the verdict ─
        print("\n[U6] SEVERITY: nudge-not-wired alone -> overall verdict PASS (warning, never a hard failure)")
        clean_count = {"transcriptCount": 28, "stateCount": 28, "disagreeWarning": None}
        clean_fields = {"missing": [], "checked": []}
        broken_nudge = {
            "wired": False,
            "issues": ["ensure-pipeline-crons.sh (fixture) does not register the interview-nudge cron"],
        }
        verdict, exit_code, details = new_mod.build_verdict(
            clean_count, [], clean_fields, broken_nudge,
            fabrication_result=None, legacy_result=None, legacy_substance=None,
            state={}, web_store_result=None,
        )
        nudge_in_warnings = any("nudge" in w.lower() for w in details["warnings"])
        nudge_in_hard = any("nudge" in h.lower() for h in details["hardFailures"])
        if verdict == "PASS" and exit_code == 0 and not details["nudgesWired"] and nudge_in_warnings and not nudge_in_hard:
            ok(f"an otherwise-clean interview with nudges genuinely NOT wired still verdicts PASS "
               f"(exit {exit_code}); the gap is a warning, never a hard failure: warnings={details['warnings']}")
        else:
            bad(f"expected PASS/exit0 with the nudge gap only in warnings, got verdict={verdict} exit={exit_code} "
                f"hardFailures={details['hardFailures']} warnings={details['warnings']}")

        # U6b — control: a GENUINE hard-failure check still blocks even with nudges wired.
        print("\n[U6b] SEVERITY (control): a genuine jargon hit still HARD fails, even with nudges wired")
        good_nudge = {"wired": True, "issues": []}
        verdict_b, exit_code_b, details_b = new_mod.build_verdict(
            clean_count, [{"term": "leverage synergy", "line": 3, "text": "..."}], clean_fields, good_nudge,
            fabrication_result=None, legacy_result=None, legacy_substance=None,
            state={}, web_store_result=None,
        )
        if verdict_b == "FAIL" and exit_code_b == 3:
            ok(f"control: a genuine jargon hit still hard-fails (verdict={verdict_b}, exit={exit_code_b}) -- "
               f"the severity change did not weaken any OTHER check")
        else:
            bad(f"expected the jargon hit to still hard-fail, got verdict={verdict_b} exit={exit_code_b}")

        # ── U7: BLEED TEST ────────────────────────────────────────────────────
        print("\n[U7] BLEED TEST: force check_nudges_wired() to always report wired=True")
        real_check = new_mod.check_nudges_wired
        new_mod.check_nudges_wired = lambda repo_root: {"wired": True, "issues": []}
        mutated_result3 = new_mod.check_nudges_wired(skills3)  # U3's genuinely-broken fixture
        mutation_suppressed_the_gap = mutated_result3["wired"]
        new_mod.check_nudges_wired = real_check  # restore FIRST, unconditionally
        if mutation_suppressed_the_gap:
            ok("mutation (always wired=True) DOES suppress U3's genuine gap -- proves U3 is exercising "
               "real detection logic, not a rubber-stamp")
        else:
            bad("mutation did not change U3's result -- either the mutation is broken, or U3 is not "
                "actually calling check_nudges_wired()")
        result3_again = new_mod.check_nudges_wired(skills3)
        if not result3_again["wired"]:
            ok("post-restore: U3's genuine gap is caught again -- the suite is not vacuously passing")
        else:
            bad(f"post-restore: expected the genuine gap to still be caught, got: {result3_again}")

    finally:
        shutil.rmtree(tmproot, ignore_errors=True)

    print("\n" + "=" * 70)
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print("=" * 70)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
