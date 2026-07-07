"""Regression tests for the v18.1.3 Skill-6 TEXT-VERB root-cause fix.

THE PROVEN BUG (live + hermetic data:-URL probe, 2026-07-07): agent-browser
0.27.0 treats a BARE positional on ``click`` / ``fill`` / ``wait`` /
``dblclick`` / ``type`` as a CSS selector / XPath / @ref — NEVER a text match
(per each verb's ``--help``). So the old helper forms

    wait -- "Start from Scratch"     -> rc=1 timeout (text visibly present)
    click "Create form"              -> rc=1 'Element not found'
    fill "Search by Name" <value>    -> label parsed as a selector

could not succeed even with the target text on screen. Every live run against
a real account failed at F2 ('Create form') because the click NEVER happened.
The CLI's real text verbs (proven rc=0 on the same probe) are:

    wait --text <text>                     (substring match)
    find text <text> click                 (visible-text click)
    find label|placeholder <x> fill <v>    (label-identified fill)
    keyboard type <text>                   (type into the FOCUSED element)

A second, compounding defect: ``ghl_builder.browser_cmd`` joins args into ONE
string with a plain ' '.join and the ``_ab`` / ``_run_cmd`` glue re-splits it
with ``shlex.split`` — so an unquoted multi-word arg ('Create form') would
ALSO shatter into separate CLI tokens. The fix shell-quotes every arg before
the join so it survives the round-trip as exactly one argv token.

These tests verify the ACTUAL COMMAND ARGV built by the helpers — the real
``browser_cmd`` emitter runs inside a hermetic ``browser_manager
.browser_session()`` bracket (emitter-only, spawns nothing) and the
``subprocess.run`` seam is replaced with a recorder — NOT merely that "some
command ran". HERMETIC: no network, no live browser, no GHL.

Style, imports, and sys.path handling mirror the sibling 06 tests
(``test_ghl_form_builder_capture.py`` / ``test_browser_manager_singleton.py``).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

# ── sys.path setup (mirrors the sibling 06 tests) ─────────────────────────────
_TESTS_DIR = Path(__file__).resolve().parent
_TOOLS_DIR = _TESTS_DIR.parent / "tools"
for _p in (str(_TOOLS_DIR), str(_TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import browser_manager as bm  # noqa: E402
import ghl_form_builder as fb  # noqa: E402
import ghl_survey_builder as sb  # noqa: E402

_SESSION = "sess-fake"


class _Recorder:
    """Stands in for ``subprocess.run`` at the ``_ab`` / ``_run_cmd`` seam.

    Records every argv EXACTLY as the glue would exec it (i.e. AFTER the
    browser_cmd join + shlex.split round-trip), returns a scripted returncode
    per call (default 0), and serves ``stdout_map[verb]`` so snapshot-gated
    paths (e.g. ``_try_rename``) can be driven hermetically."""

    def __init__(self, rc_queue=None, stdout_map=None):
        self.argvs: list[list[str]] = []
        self.rc_queue = list(rc_queue or [])
        self.stdout_map = dict(stdout_map or {})

    def run(self, argv, **kwargs):
        argv = list(argv)
        self.argvs.append(argv)
        rc = self.rc_queue.pop(0) if self.rc_queue else 0
        # The verb is the token right after `--session <name>` in the managed
        # prefix (`agent-browser --headed false --session <name> <verb> ...`).
        try:
            verb = argv[argv.index("--session") + 2]
        except (ValueError, IndexError):
            verb = ""
        return subprocess.CompletedProcess(
            args=argv, returncode=rc,
            stdout=self.stdout_map.get(verb, ""), stderr="")


@pytest.fixture()
def recorder(monkeypatch):
    """Install a fresh recorder at the shared subprocess seam (restored by
    pytest) — both tool modules resolve ``subprocess.run`` through the same
    module object."""
    rec = _Recorder()
    monkeypatch.setattr(subprocess, "run", rec.run)
    return rec


def _tail(argv, n):
    """The last n argv tokens (the verb + its args, after the headless/session
    prefix)."""
    return argv[-n:]


# ---------------------------------------------------------------------------
# The emitted argv must still ride the headless-forced singleton prefix.
# ---------------------------------------------------------------------------
def _assert_managed_prefix(argv):
    assert argv[0] == "agent-browser"
    assert argv[1:3] == ["--headed", "false"], "headless force (D6) must survive"
    assert "--session" in argv and argv[argv.index("--session") + 1] == _SESSION


# ---------------------------------------------------------------------------
# ghl_form_builder helpers
# ---------------------------------------------------------------------------
class TestFormBuilderTextVerbShapes:
    def test_wait_text_builds_wait_dash_dash_text(self, recorder):
        with bm.browser_session(_SESSION):
            cp = fb._wait_text(_SESSION, "Start from Scratch")
        assert cp.returncode == 0
        argv = recorder.argvs[-1]
        _assert_managed_prefix(argv)
        assert _tail(argv, 3) == ["wait", "--text", "Start from Scratch"], (
            "text wait MUST be `wait --text <text>`; a bare positional is a "
            f"CSS selector (rc=1 timeout even with the text present): {argv!r}")
        assert "--" not in argv, "the broken `wait -- <text>` form must be gone"

    def test_wait_text_multiword_text_is_one_argv_token(self, recorder):
        with bm.browser_session(_SESSION):
            fb._wait_text(_SESSION, "Start from Scratch")
        argv = recorder.argvs[-1]
        assert "Start from Scratch" in argv, "must survive quoting as ONE token"
        for shard in ("Start", "from", "Scratch"):
            assert shard not in argv, f"text shattered into tokens: {argv!r}"

    def test_click_builds_find_text_click(self, recorder):
        with bm.browser_session(_SESSION):
            cp = fb._click(_SESSION, "Create form")
        assert cp.returncode == 0
        argv = recorder.argvs[-1]
        _assert_managed_prefix(argv)
        assert _tail(argv, 4) == ["find", "text", "Create form", "click"], (
            "text click MUST be `find text <target> click`; a bare `click "
            f"<target>` positional is a CSS selector ('Element not found'): {argv!r}")

    def test_click_never_emits_bare_click_verb(self, recorder):
        with bm.browser_session(_SESSION):
            fb._click(_SESSION, "Create form")
        for argv in recorder.argvs:
            sess_i = argv.index("--session")
            verb = argv[sess_i + 2] if len(argv) > sess_i + 2 else ""
            assert verb != "click", (
                f"the F2 root-cause regression: bare `click` re-emitted: {argv!r}")

    def test_click_button_builds_find_role_button_name_exact(self, recorder):
        """The F2 modal-CONFIRM primitive (live 2026-07-07): THREE on-screen
        elements contain 'Create' at confirm time (header '+ Create form'
        button behind the overlay, modal title 'Create new form', blue
        confirm button), so the confirm MUST be role=button + EXACT
        accessible name — `find text Create click` resolves first-DOM-order
        to the WRONG element (rc=0, no navigation)."""
        with bm.browser_session(_SESSION):
            cp = fb._click_button(_SESSION, "Create")
        assert cp.returncode == 0
        argv = recorder.argvs[-1]
        _assert_managed_prefix(argv)
        assert _tail(argv, 7) == ["find", "role", "button", "click",
                                  "--name", "Create", "--exact"], (
            "the modal confirm MUST be `find role button click --name <n> "
            "--exact`; without role the modal TITLE matches, without --exact "
            f"the substring pulls in the header button: {argv!r}")
        assert "--exact" in argv, "--exact is REQUIRED (non-exact --name is a substring match)"

    def test_click_button_multiword_name_is_one_argv_token(self, recorder):
        with bm.browser_session(_SESSION):
            fb._click_button(_SESSION, "Create folder")
        argv = recorder.argvs[-1]
        assert "Create folder" in argv, "must survive quoting as ONE token"
        assert "folder" not in argv, f"name shattered into tokens: {argv!r}"

    def test_fill_binds_by_label_first(self, recorder):
        with bm.browser_session(_SESSION):
            cp = fb._fill(_SESSION, "Query Key", "podcast_rating")
        assert cp.returncode == 0
        assert len(recorder.argvs) == 1, "label hit must NOT try placeholder"
        argv = recorder.argvs[0]
        _assert_managed_prefix(argv)
        assert _tail(argv, 5) == ["find", "label", "Query Key", "fill",
                                  "podcast_rating"], (
            "label fill MUST be `find label <label> fill <value>`; a bare "
            f"`fill <label> <value>` parses the label as a selector: {argv!r}")

    def test_fill_falls_back_to_placeholder_on_label_miss(self, monkeypatch):
        rec = _Recorder(rc_queue=[1, 0])   # label miss -> placeholder hit
        monkeypatch.setattr(subprocess, "run", rec.run)
        with bm.browser_session(_SESSION):
            cp = fb._fill(_SESSION, "Search by Name", "Podcast Rating")
        assert cp.returncode == 0, "placeholder fallback result must be returned"
        assert len(rec.argvs) == 2
        assert _tail(rec.argvs[0], 5) == ["find", "label", "Search by Name",
                                          "fill", "Podcast Rating"]
        assert _tail(rec.argvs[1], 5) == ["find", "placeholder", "Search by Name",
                                          "fill", "Podcast Rating"], (
            "GHL search boxes are placeholder-identified — a label miss MUST "
            "retry `find placeholder <x> fill <v>`")

    def test_fill_reports_honest_failure_when_both_miss(self, monkeypatch):
        rec = _Recorder(rc_queue=[1, 1])
        monkeypatch.setattr(subprocess, "run", rec.run)
        with bm.browser_session(_SESSION):
            cp = fb._fill(_SESSION, "Nope", "x")
        assert cp.returncode != 0, "a double miss must stay rc!=0 (never fake ok)"
        assert len(rec.argvs) == 2

    def test_try_rename_uses_xpath_dblclick_and_keyboard_type(self, monkeypatch):
        rec = _Recorder(stdout_map={"snapshot": "Form 1 Untitled Podcast Signup"})
        monkeypatch.setattr(subprocess, "run", rec.run)
        with bm.browser_session(_SESSION):
            ok = fb._try_rename(_SESSION, "Podcast Signup")
        assert ok is True
        joined = [" ".join(a) for a in rec.argvs]
        assert any('dblclick //*[normalize-space(text())="Form 1"]' in j
                   for j in joined), (
            "title dblclick must bind by XPath TEXT (dblclick has no text mode "
            f"and 'Form 1' is not a selector): {joined!r}")
        assert any(_tail(a, 3) == ["keyboard", "type", "Podcast Signup"]
                   for a in rec.argvs), (
            "typing into the focused inline editor must be `keyboard type "
            f"<text>` (bare `type <text>` parses the text as a selector): {joined!r}")
        for a in rec.argvs:   # the bare `type` VERB itself must never be emitted
            assert a[a.index("--session") + 2] != "type", f"bare `type`: {a!r}"


# ---------------------------------------------------------------------------
# ghl_survey_builder helpers (same defect pattern, same fix)
# ---------------------------------------------------------------------------
class TestSurveyBuilderTextVerbShapes:
    def test_wait_builds_wait_dash_dash_text(self, recorder):
        with bm.browser_session(_SESSION):
            sb._wait(_SESSION, "Add custom field")
        argv = recorder.argvs[-1]
        _assert_managed_prefix(argv)
        assert _tail(argv, 3) == ["wait", "--text", "Add custom field"]
        assert "--" not in argv

    def test_click_builds_find_text_click(self, recorder):
        with bm.browser_session(_SESSION):
            sb._click(_SESSION, "Create folder")
        argv = recorder.argvs[-1]
        _assert_managed_prefix(argv)
        assert _tail(argv, 4) == ["find", "text", "Create folder", "click"]

    def test_fill_label_then_placeholder_fallback(self, monkeypatch):
        rec = _Recorder(rc_queue=[1, 0])
        monkeypatch.setattr(subprocess, "run", rec.run)
        with bm.browser_session(_SESSION):
            sb._fill(_SESSION, "Folder name", "Survey Fields")
        assert len(rec.argvs) == 2
        assert _tail(rec.argvs[0], 5) == ["find", "label", "Folder name",
                                          "fill", "Survey Fields"]
        assert _tail(rec.argvs[1], 5) == ["find", "placeholder", "Folder name",
                                          "fill", "Survey Fields"]

    def test_type_uses_keyboard_type_focused_element(self, recorder):
        with bm.browser_session(_SESSION):
            sb._type(_SESSION, "Welcome to the survey")
        argv = recorder.argvs[-1]
        _assert_managed_prefix(argv)
        assert _tail(argv, 3) == ["keyboard", "type", "Welcome to the survey"], (
            "bare `type <text>` parses the text as the SELECTOR of a "
            f"`type <sel> <text>` call missing its text: {argv!r}")

    def test_dblclick_binds_by_xpath_text(self, recorder):
        with bm.browser_session(_SESSION):
            sb._dblclick(_SESSION, "Survey 0")
        argv = recorder.argvs[-1]
        _assert_managed_prefix(argv)
        assert _tail(argv, 2) == ["dblclick",
                                  '//*[normalize-space(text())="Survey 0"]']


# ---------------------------------------------------------------------------
# XPath text-literal quoting (the dblclick text binder must be quote-safe)
# ---------------------------------------------------------------------------
class TestXPathTextLiteral:
    @pytest.mark.parametrize("xpath_text", [fb._xpath_text, sb._xpath_text])
    def test_plain_and_quoted_texts(self, xpath_text):
        assert xpath_text("Form 1") == '//*[normalize-space(text())="Form 1"]'
        assert xpath_text("O'Brien") == '//*[normalize-space(text())="O\'Brien"]'
        assert xpath_text('Say "hi"') == \
            "//*[normalize-space(text())='Say \"hi\"']"
        both = xpath_text('He said "don\'t"')
        assert both.startswith("//*[normalize-space(text())=concat(")
        assert '"He said "' in both


# ---------------------------------------------------------------------------
# Source-level regression lock: the broken bare forms must never come back.
# ---------------------------------------------------------------------------
class TestNoBareTextVerbInSource:
    @pytest.mark.parametrize("tool", ["ghl_form_builder.py", "ghl_survey_builder.py"])
    def test_no_wait_dash_dash_form_in_source(self, tool):
        src = (_TOOLS_DIR / tool).read_text(encoding="utf-8")
        assert re.search(r'"wait",\s*"--",', src) is None, (
            f"{tool}: the broken `wait -- <text>` emission is back")

    @pytest.mark.parametrize("tool,glue", [("ghl_form_builder.py", "_ab"),
                                           ("ghl_survey_builder.py", "_run_cmd")])
    def test_no_bare_click_or_fill_emission_in_source(self, tool, glue):
        src = (_TOOLS_DIR / tool).read_text(encoding="utf-8")
        assert re.search(glue + r'\(session,\s*"click",', src) is None, (
            f"{tool}: a bare `click <target>` emission is back (selector "
            "semantics — must use `find text <target> click`)")
        assert re.search(glue + r'\(session,\s*"fill",', src) is None, (
            f"{tool}: a bare `fill <label> <value>` emission is back (selector "
            "semantics — must use `find label|placeholder <x> fill <v>`)")

    def test_no_ambiguous_create_confirm_click_in_form_builder_source(self):
        """The F2 modal-confirm regression lock (live 2026-07-07): a bare
        substring click on 'Create' can never come back — at confirm time the
        header '+ Create form' button, the modal title 'Create new form', and
        the confirm button ALL contain that text, and first-DOM-order picks
        the wrong one (rc=0, SPA never navigates)."""
        src = (_TOOLS_DIR / "ghl_form_builder.py").read_text(encoding="utf-8")
        assert re.search(r'_click\(session,\s*"Create"\)', src) is None, (
            "ghl_form_builder.py: the ambiguous `_click(session, \"Create\")` "
            "substring emission is back — the modal confirm MUST go through "
            "_click_button (role=button + --exact accessible name)")

    def test_glue_layers_shell_quote_every_arg(self):
        for tool in ("ghl_form_builder.py", "ghl_survey_builder.py"):
            src = (_TOOLS_DIR / tool).read_text(encoding="utf-8")
            assert "shlex.quote(str(a)) for a in args" in src, (
                f"{tool}: the browser_cmd join must shell-quote every arg or "
                "multi-word text targets shatter across shlex.split")
