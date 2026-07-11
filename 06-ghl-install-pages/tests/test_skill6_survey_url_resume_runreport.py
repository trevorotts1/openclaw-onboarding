"""Skill-6 units U6 / U8 / U10 — survey-URL receipt, phase-granular resume, RUN REPORT.

No network, no browser, no GHL. Every browser-touching leaf is stubbed; what is
under test is the ORCHESTRATION (which phases run, which are skipped, what is
written to disk, what is printed at exit) plus the URL-capture contract.

  * **U6 (AUD-52)** — `_p2_save_and_get_url` derives the survey id from
    `location.href`, CONSTRUCTS `…/widget/survey/<id>`, and returns it ONLY after a
    fetch proves 200. The two old escape hatches — the `a[href]` scan and the
    "read from the integrate-panel screenshot" fallback — must be UNREACHABLE, and
    that is asserted against the module SOURCE, not just its behaviour.

  * **U8 (AUD-53)** — a run killed at phase N resumes AT PHASE N. Proven two ways:
    a real SIGKILL of a real subprocess mid-phase (the ledger must survive it), and
    a full `build_survey` live walk that is stopped at a phase and resumed.

  * **U10 (AUD-54)** — every Skill-6 builder prints a RUN REPORT at exit whose
    printed resume command, when pasted into a shell, ACTUALLY RUNS.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile

import pytest

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
sys.path.insert(0, TOOLS)

import ghl_run_state as rs  # noqa: E402
import ghl_survey_builder as sb  # noqa: E402
import ghl_form_builder as fb  # noqa: E402

SURVEY_SRC = os.path.join(TOOLS, "ghl_survey_builder.py")

# The five OBJECT builders (the things that have a run to report on). ghl_builder.py
# is the mechanical-helper CLI and is covered separately, below.
OBJECT_BUILDERS = [
    "ghl_survey_builder",
    "ghl_form_builder",
    "ghl_course_builder",
    "ghl_community_builder",
    "ghl_pipeline_builder",
]


def _read_survey_source() -> str:
    with open(SURVEY_SRC, encoding="utf-8") as fh:
        return fh.read()


def _survey_code_only() -> str:
    """The survey builder's source with `#` comment lines removed.

    The AUD-52 guard must fire on CODE that could still scrape `a[href]` or defer to
    a screenshot — not on a comment that explains why those were deleted. Asserting
    against raw source would make the module un-documentable: writing down what was
    removed would trip the check that it was removed.
    """
    lines = []
    for ln in _read_survey_source().splitlines():
        if ln.lstrip().startswith("#"):
            continue
        lines.append(ln)
    return "\n".join(lines)


# ===========================================================================
# U6 / AUD-52 — the survey URL is derived from location.href and receipted 200
# ===========================================================================
class TestU6SurveyUrlReceipt:

    def test_anchor_scan_and_screenshot_fallback_are_gone_from_the_source(self):
        """The two things AUD-52 says must die, must actually be dead.

        Behavioural tests alone cannot prove a fallback is unreachable — a dead
        branch still passes every test that never enters it. So this asserts on the
        SOURCE: neither the `a[href]` scan nor the screenshot fallback exists to be
        reached at all.
        """
        code = _survey_code_only()
        assert "querySelectorAll('a[href]')" not in code, (
            "the a[href] anchor scan is still LIVE CODE in ghl_survey_builder — AUD-52 "
            "requires the survey URL to come from location.href, not from scraping links"
        )
        assert "read from integrate-panel screenshot" not in code, (
            "the 'read from the integrate-panel screenshot' fallback is still present "
            "— AUD-52 requires it deleted entirely"
        )
        assert "survey URL not captured via eval" not in code

        # And the replacement really is a fetch-200 receipt, not a renamed no-op.
        assert "_fetch_url_receipt" in code
        assert "survey-url-receipt.json" in code

    def test_capture_js_reads_location_href(self):
        assert "location.href" in sb._SURVEY_ID_CAPTURE_JS, (
            "the id must be read from location.href (AUD-52)"
        )
        assert "survey-builder-v2" in sb._SURVEY_ID_CAPTURE_JS

    def test_public_url_is_constructed_from_the_id(self):
        assert sb.survey_public_url("ExAPmAV3Llo0tREenfJy") == (
            "https://link.msgsndr.com/widget/survey/ExAPmAV3Llo0tREenfJy"
        )

    def test_returns_url_and_stores_a_fetch_200_receipt(self, monkeypatch, tmp_path):
        """The happy path: id from the URL → constructed widget URL → fetch 200 →
        receipt on disk showing the 200."""
        sid = "ExAPmAV3Llo0tREenfJy"
        calls = {}

        monkeypatch.setattr(sb, "_click", lambda *a, **k: None)
        monkeypatch.setattr(sb, "_wait", lambda *a, **k: None)
        monkeypatch.setattr(sb, "_screenshot", lambda *a, **k: None)
        monkeypatch.setattr(sb, "_eval", lambda s, js, timeout=15: sid)

        def fake_get(url, timeout=15.0):
            calls["url"] = url
            return 200, url, ""

        monkeypatch.setattr(sb, "_http_get_status", fake_get)

        ev = str(tmp_path)
        url = sb._p2_save_and_get_url("sess", _Gov(), ev, [0], survey_name="ZHC Demo")

        assert url == f"https://link.msgsndr.com/widget/survey/{sid}"
        assert calls["url"] == url, "the receipt must fetch the URL it returns"

        receipt = json.loads(
            open(os.path.join(ev, "routing", "survey-url-receipt.json")).read())
        assert receipt["http_status"] == 200
        assert receipt["ok"] is True
        assert receipt["survey_id"] == sid
        assert receipt["public_url"] == url

        # …and it is mirrored into the F6 per-object receipts store, so the run
        # summary (a pure reduction of receipts on disk) can see it.
        eco = os.path.join(ev, "ecosystem")
        f6 = [json.loads(open(os.path.join(eco, f)).read()) for f in os.listdir(eco)]
        survey_receipts = [r for r in f6 if r["object_type"] == "survey"]
        assert len(survey_receipts) == 1
        assert survey_receipts[0]["verify"]["http"] == 200
        assert survey_receipts[0]["verify"]["ok"] is True
        assert survey_receipts[0]["created"] is True

    def test_non_200_stops_the_build_and_receipts_the_failure(self, monkeypatch, tmp_path):
        """A URL that does not 200 is NOT a deliverable. Fail closed — and record why."""
        sid = "ExAPmAV3Llo0tREenfJy"
        monkeypatch.setattr(sb, "_click", lambda *a, **k: None)
        monkeypatch.setattr(sb, "_wait", lambda *a, **k: None)
        monkeypatch.setattr(sb, "_screenshot", lambda *a, **k: None)
        monkeypatch.setattr(sb, "_eval", lambda s, js, timeout=15: sid)
        monkeypatch.setattr(sb, "_http_get_status",
                            lambda url, timeout=15.0: (404, url, "HTTPError 404"))

        ev = str(tmp_path)
        with pytest.raises(sb.SurveyUrlCaptureStop) as exc:
            sb._p2_save_and_get_url("sess", _Gov(), ev, [0], survey_name="ZHC Demo",
                                    )
        assert "404" in str(exc.value)

        receipt = json.loads(
            open(os.path.join(ev, "routing", "survey-url-receipt.json")).read())
        assert receipt["http_status"] == 404
        assert receipt["ok"] is False

        eco = os.path.join(ev, "ecosystem")
        f6 = [json.loads(open(os.path.join(eco, f)).read()) for f in os.listdir(eco)]
        assert f6[0]["action"] == "failed"
        assert f6[0]["created"] is False

    def test_missing_id_stops_instead_of_falling_back(self, monkeypatch, tmp_path):
        """No id in the URL → STOP. The old code logged 'read it off the screenshot'
        and returned '' — i.e. it reported success with no deliverable."""
        monkeypatch.setattr(sb, "_click", lambda *a, **k: None)
        monkeypatch.setattr(sb, "_wait", lambda *a, **k: None)
        monkeypatch.setattr(sb, "_screenshot", lambda *a, **k: None)
        monkeypatch.setattr(sb, "_eval", lambda s, js, timeout=15: "")
        monkeypatch.setattr(sb, "_http_get_status",
                            lambda url, timeout=15.0: pytest.fail(
                                "must not fetch anything when no id was captured"))

        ev = str(tmp_path)
        with pytest.raises(sb.SurveyUrlCaptureStop):
            sb._p2_save_and_get_url("sess", _Gov(), ev, [0], survey_name="ZHC Demo")

        receipt = json.loads(
            open(os.path.join(ev, "routing", "survey-url-receipt.json")).read())
        assert receipt["ok"] is False
        assert receipt["survey_id"] == ""

    def test_a_malformed_id_is_rejected_not_trusted(self, monkeypatch):
        """Raw eval output is never trusted as an id (shape gate)."""
        monkeypatch.setattr(sb, "_eval", lambda s, js, timeout=15: "../../etc/passwd")
        assert sb._capture_survey_id("sess") == ""

    def test_fetch_receipt_polls_until_200(self, monkeypatch):
        """A just-saved survey can take a beat to become publicly routable: a single
        instant GET would report a false 404 on a perfectly good survey."""
        seq = [(404, "u", "HTTPError 404"), (404, "u", "HTTPError 404"), (200, "u", "")]
        monkeypatch.setattr(sb, "_http_get_status", lambda url, timeout=15.0: seq.pop(0))
        rec = sb._fetch_url_receipt("SID", "https://x/widget/survey/SID",
                                    timeout_s=10.0, poll_s=0.0)
        assert rec["ok"] is True
        assert rec["http_status"] == 200
        assert rec["attempts"] == 3

    def test_fetch_receipt_is_bounded_and_gives_up_honestly(self, monkeypatch):
        monkeypatch.setattr(sb, "_http_get_status",
                            lambda url, timeout=15.0: (500, url, "HTTPError 500"))
        rec = sb._fetch_url_receipt("SID", "https://x/widget/survey/SID",
                                    timeout_s=0.0, poll_s=0.0)
        assert rec["ok"] is False
        assert rec["http_status"] == 500
        assert rec["attempts"] == 1, "a zero budget must still make exactly one attempt"


class _Gov:
    """Stand-in RateGovernor."""
    def before(self, *a, **k):
        return None


# ===========================================================================
# U8 / AUD-53 — phase-granular resume on the survey AND form builders
# ===========================================================================
class TestU8ResumeExists:

    def test_both_builders_expose_resume(self):
        """The spec's literal DONE-MEANS: `grep -c -- --resume` > 0 in BOTH builders
        (it was 0 in both)."""
        for mod in ("ghl_survey_builder.py", "ghl_form_builder.py"):
            src = open(os.path.join(TOOLS, mod), encoding="utf-8").read()
            assert "--resume" in src, f"{mod} still has no --resume (AUD-53)"

    def test_resume_flag_is_accepted_by_both_clis(self, tmp_path):
        for b in ("ghl_survey_builder", "ghl_form_builder"):
            out = subprocess.run(
                [sys.executable, os.path.join(TOOLS, f"{b}.py"), "--help"],
                capture_output=True, text=True, timeout=60)
            assert "--resume" in out.stdout, f"{b} --help does not advertise --resume"
            assert "RUN_ID" in out.stdout, f"{b}'s --resume must take a run id"


class TestU8KillAndResume:

    def test_a_real_sigkill_leaves_a_resumable_ledger(self, tmp_path):
        """The premise resume rests on: a process KILLED mid-phase must leave a state
        file that says exactly which phases completed — not a torn file, not a lie.

        This is a real SIGKILL (signal 9, uncatchable) of a real subprocess, not a
        simulated one.
        """
        state_root = str(tmp_path / "state")
        script = tmp_path / "killer.py"
        script.write_text(
            "import os, signal, sys\n"
            f"sys.path.insert(0, {TOOLS!r})\n"
            "import ghl_run_state as rs\n"
            "specs = [rs.PhaseSpec('a'), rs.PhaseSpec('b'), rs.PhaseSpec('c'),\n"
            "         rs.PhaseSpec('d')]\n"
            f"st = rs.RunState.start('demo', specs, run_id='KILLME', state_root={state_root!r})\n"
            "rs.run_phase(st, 'a', lambda: 'a-done')\n"
            "rs.run_phase(st, 'b', lambda: 'b-done')\n"
            "# die HARD in the middle of phase c — no cleanup, no finally, no mercy\n"
            "rs.run_phase(st, 'c', lambda: os.kill(os.getpid(), signal.SIGKILL))\n"
        )
        proc = subprocess.run([sys.executable, str(script)], capture_output=True,
                              timeout=60)
        assert proc.returncode == -9, f"expected SIGKILL, got rc={proc.returncode}"

        specs = [rs.PhaseSpec("a"), rs.PhaseSpec("b"), rs.PhaseSpec("c"),
                 rs.PhaseSpec("d")]
        st = rs.RunState.load("KILLME", "demo", state_root=state_root, specs=specs)

        # The ledger survived the kill and tells the truth: a,b done; c never finished.
        assert st.completed_phases() == ["a", "b"]
        assert st.is_done("c") is False
        assert st.first_incomplete_mutating_phase() == "c", (
            "resume must restart at phase c — the phase the kill interrupted"
        )

        # …and a resume genuinely SKIPS a and b and restarts at c.
        ran = []
        for p in ("a", "b", "c", "d"):
            rs.run_phase(st, p, lambda p=p: ran.append(p))
        assert ran == ["c", "d"], (
            f"resume re-ran {ran}; it must skip the completed phases and restart at c"
        )

    def test_survey_live_walk_stops_at_phase_n_then_resumes_at_phase_n(
            self, monkeypatch, tmp_path):
        """The acceptance test, against the REAL `build_survey` live walk.

        Run 1 stops after `p2d_welcome`. Run 2 (`--resume <run_id>`) must NOT redo
        the mutating phases run 1 completed, and must restart at `p2e_fields`.
        """
        executed = []
        _stub_survey_browser(monkeypatch, executed)

        ev = str(tmp_path / "ev")
        state_root = str(tmp_path / "state")
        task = _survey_task()

        specs = sb.SURVEY_PHASES
        st1 = rs.RunState.start("ghl_survey_builder", specs, run_id="RUN1",
                                state_root=state_root, evidence_root=ev)
        task["stop_after_phase"] = "p2d_welcome"
        res1 = sb.build_survey(task, ev, dry_run=False, state=st1)
        assert res1["stopped_after_phase"] == "p2d_welcome"

        # Run 1 walked the mutating phases up to and including the welcome slide.
        assert "p2b_rename" in executed
        assert "p2c_slides" in executed
        assert "p2d_welcome" in executed
        assert "p2e_fields" not in executed, "run 1 must stop BEFORE phase E"
        assert st1.completed_phases()[-1] == "p2d_welcome"

        # ── the resume ──────────────────────────────────────────────────────────
        executed.clear()
        st2 = rs.RunState.load("RUN1", "ghl_survey_builder", state_root=state_root,
                               specs=specs)
        assert st2.first_incomplete_mutating_phase() == "p2e_fields", (
            "the resume point must be phase E — the phase after the last completed one"
        )

        task2 = _survey_task()
        task2["stop_after_phase"] = ""
        res2 = sb.build_survey(task2, ev, dry_run=False, state=st2)

        # THE ACCEPTANCE ASSERTION: the mutating phases already done are NOT redone…
        for already_done in ("p1_fields", "p2_smoke", "p2b_rename", "p2c_slides",
                             "p2d_welcome"):
            assert already_done not in executed, (
                f"resume RE-RAN {already_done} — a resumed run must not redo a phase "
                f"it already completed (that is a restart at 0, not a resume)"
            )
        # …and the walk restarts at exactly phase N.
        mutating = [p for p in executed if p.startswith("p2") and p != "p2a_create"]
        assert mutating[0] == "p2e_fields", (
            f"resume restarted at {mutating[0]!r}, expected 'p2e_fields'"
        )
        assert executed[-1] == "p2k_save_url"
        assert res2["survey_url"] == "https://link.msgsndr.com/widget/survey/ExAPmAV3Llo0tREenfJy"

        # The navigation/entry phase DOES re-run (you cannot skip walking back in),
        # and it is idempotent — it reuses the survey rather than creating a second.
        assert "p2a_create" in executed

    def test_preflight_gate_always_reruns_on_resume(self, monkeypatch, tmp_path):
        """A gate a resume skips is not a gate. Preflight must re-run every time."""
        executed = []
        _stub_survey_browser(monkeypatch, executed)
        ev = str(tmp_path / "ev")
        state_root = str(tmp_path / "state")

        seen = {"preflight": 0}
        real_preflight = sb._run_preflight

        def counting_preflight(task, evidence_root):
            seen["preflight"] += 1
            return real_preflight(task, evidence_root)

        monkeypatch.setattr(sb, "_run_preflight", counting_preflight)

        specs = sb.SURVEY_PHASES
        st1 = rs.RunState.start("ghl_survey_builder", specs, run_id="RUNG",
                                state_root=state_root, evidence_root=ev)
        t = _survey_task()
        t["stop_after_phase"] = "p2c_slides"
        sb.build_survey(t, ev, dry_run=False, state=st1)
        assert seen["preflight"] == 1

        st2 = rs.RunState.load("RUNG", "ghl_survey_builder", state_root=state_root,
                               specs=specs)
        t2 = _survey_task()
        sb.build_survey(t2, ev, dry_run=False, state=st2)
        assert seen["preflight"] == 2, (
            "preflight is a GATE — a resumed run must re-run it, not inherit its pass"
        )

    def test_form_resume_reenters_the_existing_form_instead_of_duplicating_it(
            self, monkeypatch, tmp_path):
        """The form-specific hazard: a naive resume re-walks F2 and creates a SECOND
        form. It must route straight into the one it already made."""
        state_root = str(tmp_path / "state")
        pushed = []

        monkeypatch.setattr(fb, "_pre_phase_check", lambda *a, **k: None)
        monkeypatch.setattr(fb, "_screenshot", lambda *a, **k: None)
        monkeypatch.setattr(fb, "_shot", lambda *a, **k: "/dev/null")
        monkeypatch.setattr(fb, "_router_push",
                            lambda s, path, expect_contains="": pushed.append(path) or "ok")
        created = []
        monkeypatch.setattr(fb, "_click",
                            lambda s, t, timeout=15: created.append(t))

        specs = fb.FORM_PHASES
        st = rs.RunState.start("ghl_form_builder", specs, run_id="FRUN",
                               state_root=state_root, evidence_root=str(tmp_path))
        # Pretend a previous run created the form and died right after F2.
        st.mark_done("F1")
        st.mark_done("F2")
        st.carry_set("form_id", "FORMabc123456789xy")

        plan = {"location_id": "LOC1", "form_name": "ZHC T",
                "default_fields_keep": [], "fields": [], "embed": {}}
        click_list = {"steps": [
            {"n": 1, "phase": "F2", "action": "click", "target": "Create form"},
            {"n": 2, "phase": "F3", "action": "rename", "target": "ZHC T"},
        ]}
        st2 = rs.RunState.load("FRUN", "ghl_form_builder", state_root=state_root,
                               specs=specs)
        monkeypatch.setattr(fb, "_rename_form_title",
                            lambda s, n: {"ok": True, "actual_title": n})

        fb._walk_click_list("sess", click_list, plan, str(tmp_path), [0], [], [],
                            {}, state=st2)

        assert not any("create form" in c.lower() for c in created), (
            "resume re-walked F2 and clicked 'Create form' — that builds a DUPLICATE form"
        )
        assert any("form-builder-v2/FORMabc123456789xy" in p for p in pushed), (
            "resume must route straight into the already-created form"
        )

    def test_form_resume_fails_closed_when_the_ledger_lost_the_form_id(
            self, monkeypatch, tmp_path):
        """F2 done but no id carried = we cannot re-enter and must not re-create.
        Fail closed rather than silently build a duplicate."""
        state_root = str(tmp_path / "state")
        monkeypatch.setattr(fb, "_pre_phase_check", lambda *a, **k: None)
        specs = fb.FORM_PHASES
        st = rs.RunState.start("ghl_form_builder", specs, run_id="FBAD",
                               state_root=state_root, evidence_root=str(tmp_path))
        st.mark_done("F2")   # …but no carry_set("form_id")

        st2 = rs.RunState.load("FBAD", "ghl_form_builder", state_root=state_root,
                               specs=specs)
        plan = {"location_id": "LOC1", "form_name": "ZHC T",
                "default_fields_keep": [], "fields": [], "embed": {}}
        cl = {"steps": [{"n": 1, "phase": "F3", "action": "rename", "target": "x"}]}
        with pytest.raises(fb.StopAndReport):
            fb._walk_click_list("s", cl, plan, str(tmp_path), [0], [], [], {}, state=st2)


class TestU8RunStateSemantics:

    def test_resuming_with_the_wrong_builder_is_refused(self, tmp_path):
        root = str(tmp_path)
        specs = [rs.PhaseSpec("a")]
        st = rs.RunState.start("ghl_survey_builder", specs, run_id="X1", state_root=root)
        with pytest.raises(rs.RunStateCorrupt):
            rs.RunState.load("X1", "ghl_form_builder", state_root=root, specs=specs)

    def test_unknown_run_id_fails_loudly(self, tmp_path):
        with pytest.raises(rs.RunStateNotFound):
            rs.RunState.load("nope", "x", state_root=str(tmp_path), specs=[])

    def test_resume_of_an_unknown_run_exits_2_not_0(self, tmp_path):
        """A --resume that cannot find its run must NOT quietly start a fresh build."""
        out = subprocess.run(
            [sys.executable, os.path.join(TOOLS, "ghl_survey_builder.py"),
             "--resume", "does-not-exist", "--state-root", str(tmp_path)],
            capture_output=True, text=True, timeout=120)
        assert out.returncode == 2
        assert "nothing to resume" in out.stderr

    def test_a_failing_phase_is_recorded_and_reraised(self, tmp_path):
        specs = [rs.PhaseSpec("a")]
        st = rs.RunState.start("b", specs, run_id="F1", state_root=str(tmp_path))
        with pytest.raises(RuntimeError):
            rs.run_phase(st, "a", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        st2 = rs.RunState.load("F1", "b", state_root=str(tmp_path), specs=specs)
        assert st2.doc["phases"]["a"]["status"] == rs.PHASE_FAILED
        assert "boom" in st2.doc["phases"]["a"]["error"]
        assert st2.is_done("a") is False, "a failed phase must NOT count as done"

    def test_module_selftest_passes(self):
        out = subprocess.run(
            [sys.executable, os.path.join(TOOLS, "ghl_run_state.py"), "--selftest"],
            capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr


# ===========================================================================
# U10 / AUD-54 — the uniform RUN REPORT, and a resume command that really runs
# ===========================================================================
RESUME_ROW = re.compile(r"^resume\s+:\s+(.+)$", re.M)


def _run_builder(builder: str, tmp_path, extra=()):
    ev = str(tmp_path / f"ev-{builder}")
    sr = str(tmp_path / "state")
    cmd = [sys.executable, os.path.join(TOOLS, f"{builder}.py"),
           "--dry-run", "--location-id", "LOC123",
           "--evidence-root", ev, "--state-root", sr, *extra]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=180)


class TestU10RunReport:

    @pytest.mark.parametrize("builder", OBJECT_BUILDERS)
    def test_every_builder_emits_a_run_report_at_exit(self, builder, tmp_path):
        out = _run_builder(builder, tmp_path)
        assert "RUN REPORT" in out.stderr, (
            f"{builder} printed no RUN REPORT (AUD-54)\nstderr tail:\n{out.stderr[-800:]}"
        )

    @pytest.mark.parametrize("builder", OBJECT_BUILDERS)
    def test_the_report_is_identically_shaped(self, builder, tmp_path):
        out = _run_builder(builder, tmp_path)
        block = out.stderr.split("RUN REPORT")[1]
        for row in ("builder", "run_id", "status", "dry_run", "evidence_root",
                    "duration_s", "phases_done", "last_phase", "resume"):
            assert re.search(rf"^{row}\s+:", block, re.M), (
                f"{builder}'s RUN REPORT is missing the '{row}' row — the whole point "
                f"of U10 is that all six reports have the SAME shape"
            )

    @pytest.mark.parametrize("builder", OBJECT_BUILDERS)
    def test_the_report_goes_to_stderr_and_stdout_stays_valid_json(self, builder, tmp_path):
        """Every builder's stdout is a machine-readable JSON contract (the dispatcher
        and the CC board hooks parse it). A human report on stdout would break all of
        them — so the report must be on stderr and stdout must still parse."""
        out = _run_builder(builder, tmp_path)
        assert "RUN REPORT" not in out.stdout
        json.loads(out.stdout)   # raises if the report leaked into the JSON

    @pytest.mark.parametrize("builder", OBJECT_BUILDERS)
    def test_the_printed_resume_command_actually_runs(self, builder, tmp_path):
        """THE acceptance test for AUD-54: take the command the builder PRINTED,
        paste it, and it must run."""
        first = _run_builder(builder, tmp_path)
        m = RESUME_ROW.search(first.stderr)
        assert m, f"{builder} printed no resume command"
        cmd = shlex.split(m.group(1).strip())

        assert "--resume" in cmd, f"{builder}'s printed command is not a resume: {cmd}"

        second = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        assert second.returncode in (0, 1), (
            f"{builder}'s PRINTED resume command did not run.\n"
            f"cmd: {m.group(1)}\nrc={second.returncode}\nstderr:\n{second.stderr[-900:]}"
        )
        assert "RUN REPORT" in second.stderr
        # It really did resume the SAME run, not silently start a new one.
        run_id = cmd[cmd.index("--resume") + 1]
        assert re.search(rf"^run_id\s+:\s+{re.escape(run_id)}$", second.stderr, re.M), (
            f"{builder}'s resume started a DIFFERENT run instead of resuming {run_id}"
        )

    def test_ghl_builder_helper_cli_also_reports(self, tmp_path):
        """ghl_builder.py is the mechanical-helper CLI rather than an object builder,
        but it owns the funnel-page run ledger — so it reports too."""
        out = subprocess.run(
            [sys.executable, os.path.join(TOOLS, "ghl_builder.py"), "gates", "--runtime"],
            capture_output=True, text=True, timeout=60)
        assert out.returncode == 0
        assert "RUN REPORT" in out.stderr
        m = RESUME_ROW.search(out.stderr)
        assert m
        again = subprocess.run(shlex.split(m.group(1).strip()),
                               capture_output=True, text=True, timeout=60)
        assert again.returncode == 0, "ghl_builder's printed command must run"

    def test_report_names_the_phases_a_resume_skipped(self, monkeypatch, tmp_path):
        """The cockpit is only honest if it says what it SKIPPED, not just what it did."""
        specs = [rs.PhaseSpec("gate", resumable=False), rs.PhaseSpec("a"),
                 rs.PhaseSpec("b"), rs.PhaseSpec("c")]
        root = str(tmp_path)
        st = rs.RunState.start("demo", specs, run_id="R9", state_root=root)
        for p in ("gate", "a", "b"):
            rs.run_phase(st, p, lambda: None)

        st2 = rs.RunState.load("R9", "demo", state_root=root, specs=specs)
        for p in ("gate", "a", "b", "c"):
            rs.run_phase(st2, p, lambda: None)

        block = rs.format_run_report(
            builder="demo", run_id="R9", status=rs.STATUS_OK, dry_run=True,
            evidence_root="/tmp/x", duration_s=1.0, script_path=__file__,
            state=st2, state_root=root)
        assert "phases_skipped : a, b" in block
        assert "R9" in block


# ---------------------------------------------------------------------------
# Stubs — the browser leaves. What is under test is the WALK, not agent-browser.
# ---------------------------------------------------------------------------
SURVEY_ID = "ExAPmAV3Llo0tREenfJy"


def _survey_task() -> dict:
    """A task the builder's own preflight accepts.

    Deliberately uses the module's REFERENCE fields + REFERENCE conditional rules
    (by omitting both keys) rather than hand-rolled ones: those two sets are designed
    against each other, and preflight's topology gate correctly rejects a task whose
    rules reference fields it does not define. What this suite is testing is the
    PHASE WALK, not the field model.
    """
    return {
        "id": "t1",
        "survey_name": "ZHC Demo Survey",
        "title": "ZHC Demo Survey",
        "brief": {"source": "test"},
        "location_id": "LOC123",
        "folder_name": "Sample Survey",
        "field_creation": "browser",   # exercise p1_fields too
        "build_method": "browser",
    }


class _FakeSession:
    def __enter__(self):
        return "ghl-skill6-LOC123"

    def __exit__(self, *a):
        return False


def _stub_survey_browser(monkeypatch, executed):
    """Replace every browser-touching leaf of the survey walk with a recorder."""
    monkeypatch.setattr(sb.browser_manager, "browser_session",
                        lambda loc: _FakeSession())
    monkeypatch.setattr(sb, "_pre_phase_check", lambda *a, **k: None)
    monkeypatch.setattr(sb, "_screenshot", lambda *a, **k: None)
    monkeypatch.setattr(sb, "_eval", lambda *a, **k: SURVEY_ID)
    monkeypatch.setattr(sb, "_board_move", lambda *a, **k: None)
    monkeypatch.setattr(sb, "_board_activity", lambda *a, **k: None)
    monkeypatch.setattr(sb, "_board_register_deliverable", lambda *a, **k: None)

    def rec(name, ret=None):
        def _f(*a, **k):
            executed.append(name)
            return ret
        return _f

    monkeypatch.setattr(sb, "_p1_create_folder", rec("p1_folder"))
    monkeypatch.setattr(sb, "_p1_create_field", rec("p1_field"))
    monkeypatch.setattr(sb, "_p2_navigate_create", rec("p2a_create", SURVEY_ID))
    monkeypatch.setattr(sb, "_p2_smoke_test_drag", rec("p2_smoke", {"ok": True}))
    monkeypatch.setattr(sb, "_p2_rename_survey", rec("p2b_rename"))
    monkeypatch.setattr(sb, "_p2_add_slides", rec("p2c_slides"))
    monkeypatch.setattr(sb, "_p2_welcome_slide", rec("p2d_welcome"))
    monkeypatch.setattr(sb, "_p2_pull_object_fields", rec("p2e_fields"))
    monkeypatch.setattr(sb, "_p2_rename_question_slides", rec("p2f_rename_slides"))
    monkeypatch.setattr(sb, "_p2_conditional_logic", rec("p2g_conditional"))
    monkeypatch.setattr(sb, "_p2_required_toggles", rec("p2h_required"))
    monkeypatch.setattr(sb, "_p2_capture_slide", rec("p2j_capture"))

    def fake_save_url(*a, **k):
        executed.append("p2k_save_url")
        return sb.survey_public_url(SURVEY_ID)

    monkeypatch.setattr(sb, "_p2_save_and_get_url", fake_save_url)

    # p1_fields is a wrapper phase; record its own name when either leaf fires.
    orig_folder = sb._p1_create_folder

    def folder(*a, **k):
        executed.append("p1_fields")
        return orig_folder(*a, **k)

    monkeypatch.setattr(sb, "_p1_create_folder", folder)
