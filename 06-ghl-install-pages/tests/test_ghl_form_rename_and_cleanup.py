"""Regression tests for the v18.1.5 F3 rename + cleanup-verification overhaul
(fix/skill6-ghl-form-iframe-drag).

THE TWO LIVE 2026-07-07 DEFECTS THIS LOCKS OUT:

1. SILENT RENAME FAILURE → UNLABELED LIVE FORM. The form title is an in-iframe
   inline-edit surface; the old top-frame ``dblclick <xpath>`` + ``keyboard
   type`` walk could never reach it and reported only a cosmetic warning. A
   REAL form ("Form 55") was left default-named in the account. The rename now
   rides the frame-scoped ``ghl_iframe_drag.set_inline_title`` primitive, is
   FAIL-CLOSED by default (``rename_required``), and — success or failure —
   records the title the form ACTUALLY carries (``actual_title``) so cleanup
   can positively target it.

2. FALSE "no form was created" CLEANUP CLAIM. ``_walk_click_list`` captured the
   form id into a LOCAL that was thrown away when a later step raised
   StopAndReport, so cleanup saw form_id=='' and claimed nothing to delete —
   while the form sat live. The id/title are now recorded into a caller-owned
   ``walk_state`` dict AT CAPTURE TIME, and cleanup POSITIVELY verifies:
   present-before → delete → ZERO rendered leaf matches after (the search
   textbox echoing the query can never satisfy the check), refusing to claim
   success on anything unverifiable.

HERMETIC — NO network, NO live browser, NO GHL. Style, imports, and sys.path
handling mirror ``test_ghl_form_builder_capture.py`` so this runs under the
same pytest CI.
"""
from __future__ import annotations

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

import ghl_form_builder as fb  # noqa: E402


def _cp(rc: int, stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr="")


@pytest.fixture(autouse=True)
def _fast_polls_and_mute_shots(monkeypatch):
    monkeypatch.setattr(fb, "_TEXT_WAIT_TIMEOUT_S", 0.05)
    monkeypatch.setattr(fb, "_TEXT_WAIT_SUBCALL_S", 1)
    monkeypatch.setattr(fb, "_TEXT_WAIT_POLL_S", 0.005)
    monkeypatch.setattr(fb, "_screenshot", lambda session, path: None)
    monkeypatch.setattr(fb.time, "sleep", lambda s: None)


# ── a scriptable fake of the shared frame-scoped primitive ────────────────────
class _FakeIdgError(RuntimeError):
    def __init__(self, code, reason):
        self.code, self.reason = code, reason
        super().__init__(f"{code}: {reason}")


class _FakeIdg:
    DEFAULT_FORM_TITLE_SPECS = (r"re:^Form\s*\d+$", "text=Untitled")
    IframeDragError = _FakeIdgError

    def __init__(self, set_result=None, set_error=None, read_title=None,
                 read_error=None):
        self._set_result = set_result
        self._set_error = set_error
        self._read_title = read_title
        self._read_error = read_error
        self.set_calls = []
        self.read_calls = []

    def set_inline_title(self, cdp_url, *, iframe_selector, new_title,
                         title_specs, url_marker):
        self.set_calls.append({"iframe_selector": iframe_selector,
                               "new_title": new_title,
                               "title_specs": tuple(title_specs),
                               "url_marker": url_marker})
        if self._set_error is not None:
            raise self._set_error
        return self._set_result or {"ok": True, "old_title": "Form 55",
                                    "verified": True}

    def read_inline_title(self, cdp_url, *, iframe_selector, title_specs,
                          url_marker):
        self.read_calls.append({"title_specs": tuple(title_specs)})
        if self._read_error is not None:
            raise self._read_error
        return {"ok": True, "title": self._read_title or ""}


# ---------------------------------------------------------------------------
# 1. _rename_form_title — the frame-scoped rename receipt
# ---------------------------------------------------------------------------
class TestRenameFormTitle:
    def test_success_records_target_as_actual_title(self, monkeypatch):
        idg = _FakeIdg()
        monkeypatch.setattr(fb, "ghl_iframe_drag", idg)
        monkeypatch.setattr(fb, "_get_cdp_url", lambda s: "ws://live")
        r = fb._rename_form_title("s", "ZHC TEST Form")
        assert r["renamed"] is True
        assert r["actual_title"] == "ZHC TEST Form"
        assert r["old_title"] == "Form 55"
        assert idg.set_calls[0]["iframe_selector"] == fb.GHL_FORM_IFRAME_SELECTOR
        assert idg.set_calls[0]["url_marker"] == "form-builder"

    def test_failure_reads_back_the_title_the_form_really_carries(self, monkeypatch):
        """THE ORPHAN FIX: when the rename fails, cleanup must still learn the
        form's REAL name ('Form 55') instead of assuming the intended one."""
        idg = _FakeIdg(set_error=_FakeIdgError("title-not-editable", "no editor"),
                       read_title="Form 55")
        monkeypatch.setattr(fb, "ghl_iframe_drag", idg)
        monkeypatch.setattr(fb, "_get_cdp_url", lambda s: "ws://live")
        r = fb._rename_form_title("s", "ZHC TEST Form")
        assert r["renamed"] is False
        assert r["actual_title"] == "Form 55"
        assert "title-not-editable" in r["reason"]
        # the read-back must ALSO try the target name (idempotent retry runs)
        assert any(s == "exact=ZHC TEST Form" for s in idg.read_calls[0]["title_specs"])

    def test_already_renamed_form_counts_as_renamed(self, monkeypatch):
        """Idempotency: on a retry run the title patterns ('Form <n>') no longer
        match, but the read-back returns the TARGET name → renamed."""
        idg = _FakeIdg(set_error=_FakeIdgError("title-not-found", "no default title"),
                       read_title="ZHC TEST Form")
        monkeypatch.setattr(fb, "ghl_iframe_drag", idg)
        monkeypatch.setattr(fb, "_get_cdp_url", lambda s: "ws://live")
        r = fb._rename_form_title("s", "ZHC TEST Form")
        assert r["renamed"] is True
        assert r["actual_title"] == "ZHC TEST Form"

    def test_primitive_absent_and_no_cdp_fail_honestly(self, monkeypatch):
        monkeypatch.setattr(fb, "ghl_iframe_drag", None)
        r = fb._rename_form_title("s", "X")
        assert r["renamed"] is False and "not importable" in r["reason"]
        monkeypatch.setattr(fb, "ghl_iframe_drag", _FakeIdg())
        monkeypatch.setattr(fb, "_get_cdp_url", lambda s: "")
        r2 = fb._rename_form_title("s", "X")
        assert r2["renamed"] is False and "cdp" in r2["reason"].lower()

    def test_read_back_failure_never_raises(self, monkeypatch):
        idg = _FakeIdg(set_error=_FakeIdgError("title-not-set", "verify miss"),
                       read_error=RuntimeError("frame gone"))
        monkeypatch.setattr(fb, "ghl_iframe_drag", idg)
        monkeypatch.setattr(fb, "_get_cdp_url", lambda s: "ws://live")
        r = fb._rename_form_title("s", "X")
        assert r["renamed"] is False
        assert r["actual_title"] == ""
        assert "read-back also failed" in r["reason"]


# ---------------------------------------------------------------------------
# 2. Walk F3 — fail-closed rename + walk_state capture
# ---------------------------------------------------------------------------
def _plan(**over) -> dict:
    p = {"location_id": "TESTLOCATION12345678", "form_name": "ZHC Test Form",
         "default_fields_keep": [], "fields": [], "rename_required": True}
    p.update(over)
    return p


_F3_STEPS = {"steps": [{"phase": "F3", "action": "click", "target": "Form 1"}]}


class TestWalkF3:
    def test_rename_success_recorded_in_steps_and_state(self, monkeypatch):
        monkeypatch.setattr(fb, "_rename_form_title",
                            lambda s, n: {"renamed": True, "actual_title": n,
                                          "old_title": "Form 55", "reason": ""})
        state, steps = {}, []
        fb._walk_click_list("s", _F3_STEPS, _plan(), "/tmp/ev", [0], [], steps, state)
        assert any(s.startswith("F3:rename:") for s in steps)
        assert state["actual_title"] == "ZHC Test Form"

    def test_rename_failure_stops_by_default_with_actual_title(self, monkeypatch):
        monkeypatch.setattr(fb, "_rename_form_title",
                            lambda s, n: {"renamed": False, "actual_title": "Form 55",
                                          "old_title": "", "reason": "title-not-editable"})
        state = {}
        with pytest.raises(fb.StopAndReport) as ei:
            fb._walk_click_list("s", _F3_STEPS, _plan(), "/tmp/ev", [0], [], [], state)
        assert ei.value.step == "F3.rename"
        assert "Form 55" in ei.value.reason
        assert state["actual_title"] == "Form 55", \
            "cleanup must still see the REAL title after the STOP"

    def test_rename_failure_downgrades_when_not_required(self, monkeypatch):
        monkeypatch.setattr(fb, "_rename_form_title",
                            lambda s, n: {"renamed": False, "actual_title": "Form 55",
                                          "old_title": "", "reason": "x"})
        warnings, state = [], {}
        fb._walk_click_list("s", _F3_STEPS, _plan(rename_required=False),
                            "/tmp/ev", [0], warnings, [], state)
        assert any("rename" in w for w in warnings)
        assert state["actual_title"] == "Form 55"

    def test_plan_defaults_rename_required_true(self):
        plan = fb._build_form_plan({"form_name": "X", "location_id": "L"}, [],
                                   fb.plan_dependencies([], {}))
        assert plan["rename_required"] is True
        plan_off = fb._build_form_plan(
            {"form_name": "X", "location_id": "L", "rename_required": False},
            [], fb.plan_dependencies([], {}))
        assert plan_off["rename_required"] is False


# ---------------------------------------------------------------------------
# 3. walk_state form-id capture survives a later-step STOP (the false
#    'no form was created' fix)
# ---------------------------------------------------------------------------
class TestWalkStateFormId:
    def test_form_id_survives_later_stop(self, monkeypatch):
        monkeypatch.setattr(fb, "_click", lambda session, target, timeout=15: _cp(0))
        monkeypatch.setattr(fb, "_click_button", lambda session, name, timeout=15: _cp(0))
        monkeypatch.setattr(fb, "_wait_text", lambda session, text, timeout=20: _cp(0))
        monkeypatch.setattr(fb, "_wait_text_polling", lambda session, text, **k: True)
        monkeypatch.setattr(fb, "_capture_form_id", lambda session: "liveFormId0123456789")
        monkeypatch.setattr(
            fb, "_rename_form_title",
            lambda s, n: {"renamed": False, "actual_title": "Form 55",
                          "old_title": "", "reason": "mock"})
        click_list = {"steps": [
            {"phase": "F2", "action": "click", "target": "Create"},
            {"phase": "F3", "action": "click", "target": "Form 1"},
        ]}
        state = {}
        with pytest.raises(fb.StopAndReport):
            fb._walk_click_list("s", click_list, _plan(), "/tmp/ev", [0], [], [], state)
        assert state["form_id"] == "liveFormId0123456789", (
            "the captured id must survive the F3 STOP — the old locals-only flow "
            "made cleanup claim 'no form was created' about a real form")


# ---------------------------------------------------------------------------
# 4. _delete_form — positive present→delete→absent verification
# ---------------------------------------------------------------------------
class _ListWorld:
    """Scriptable Forms-list world for _delete_form: rendered leaf counts per
    name (a queue per name, consumed per evaluation), Actions-button count, and
    rc scripting for the three delete clicks."""

    def __init__(self, leaf_counts, actions=1, rc_actions=0, rc_menuitem=0,
                 rc_confirm=0, dialog_appears=True, menu_appears=True):
        self.leaf_counts = {k: list(v) for k, v in leaf_counts.items()}
        self.actions = actions
        self.rc_actions = rc_actions
        self.rc_menuitem = rc_menuitem
        self.rc_confirm = rc_confirm
        self.dialog_appears = dialog_appears
        self.menu_appears = menu_appears
        self.searched = []
        self.clicked_buttons = []
        self.clicked_menuitems = []

    def wire(self, monkeypatch):
        monkeypatch.setattr(fb, "_router_push",
                            lambda session, path, expect_contains="": "nav:" + path)
        monkeypatch.setattr(fb, "_wait_text_polling", self._wait_text_polling)
        monkeypatch.setattr(fb, "_fill", self._fill)
        monkeypatch.setattr(fb, "_eval_leaf_count", self._leaf_count)
        monkeypatch.setattr(fb, "_eval_actions_button_count", lambda session: self.actions)
        monkeypatch.setattr(fb, "_click_button", self._click_button)
        monkeypatch.setattr(fb, "_click_menuitem", self._click_menuitem)

    def _wait_text_polling(self, session, text, **kw):
        if text == "Delete" and not self.menu_appears:
            return False
        if text == "Delete form" and not self.dialog_appears:
            return False
        return True

    def _fill(self, session, label, value, timeout=15):
        self.searched.append(value)
        return _cp(0)

    def _leaf_count(self, session, text):
        q = self.leaf_counts.get(text)
        if not q:
            return 0
        return q.pop(0) if len(q) > 1 else q[0]

    def _click_button(self, session, name, timeout=15):
        self.clicked_buttons.append(name)
        if name == "Actions":
            return _cp(self.rc_actions)
        return _cp(self.rc_confirm)

    def _click_menuitem(self, session, name, timeout=15):
        self.clicked_menuitems.append(name)
        return _cp(self.rc_menuitem)


class TestDeleteFormPositiveVerify:
    def test_happy_path_present_then_absent(self, monkeypatch):
        w = _ListWorld({"Form 55": [1, 0]})
        w.wire(monkeypatch)
        out = fb._delete_form("s", "L", "id1234567890abcdef", "ZHC Test Form",
                              actual_title="Form 55")
        assert out["deleted"] is True and out["verified_gone"] is True
        assert out["matched_name"] == "Form 55"
        assert out["pre_delete_rows"] == 1 and out["post_delete_rows"] == 0
        assert out["residue_in_list"] is False
        # the REAL title is searched FIRST (rename may have failed)
        assert w.searched[0] == "Form 55"
        # role-scoped exact clicks: row button, menu item, dialog confirm
        assert w.clicked_buttons == ["Actions", "Delete"]
        assert w.clicked_menuitems == ["Delete"]

    def test_falls_back_to_intended_name(self, monkeypatch):
        w = _ListWorld({"Form 55": [0], "ZHC Test Form": [1, 0]})
        w.wire(monkeypatch)
        out = fb._delete_form("s", "L", "id1", "ZHC Test Form", actual_title="Form 55")
        assert out["deleted"] is True
        assert out["matched_name"] == "ZHC Test Form"
        assert w.searched[:2] == ["Form 55", "ZHC Test Form"]

    def test_no_match_never_claims_deletion(self, monkeypatch):
        w = _ListWorld({})
        w.wire(monkeypatch)
        out = fb._delete_form("s", "L", "id1", "ZHC Test Form", actual_title="Form 55")
        assert out["deleted"] is False and out["verified_gone"] is False
        assert "NOT claiming deletion" in out["reason"]
        assert w.clicked_buttons == [], "must not click anything without a positive match"

    def test_multiple_rows_fail_closed(self, monkeypatch):
        w = _ListWorld({"Form 55": [2]})
        w.wire(monkeypatch)
        out = fb._delete_form("s", "L", "id1", "X", actual_title="Form 55")
        assert out["deleted"] is False
        assert "EXACTLY ONE" in out["reason"]
        assert w.clicked_buttons == []

    def test_multiple_actions_buttons_fail_closed(self, monkeypatch):
        """One title match but several rendered rows (partial-name matches in the
        filtered list) → clicking 'Actions' could hit the WRONG form. Refuse."""
        w = _ListWorld({"Form 55": [1]}, actions=3)
        w.wire(monkeypatch)
        out = fb._delete_form("s", "L", "id1", "X", actual_title="Form 55")
        assert out["deleted"] is False
        assert w.clicked_buttons == []

    def test_menuitem_click_rc_checked(self, monkeypatch):
        w = _ListWorld({"Form 55": [1]}, rc_menuitem=1)
        w.wire(monkeypatch)
        out = fb._delete_form("s", "L", "id1", "X", actual_title="Form 55")
        assert out["deleted"] is False
        assert "menuitem" in out["reason"]

    def test_missing_confirm_dialog_fails_closed(self, monkeypatch):
        w = _ListWorld({"Form 55": [1]}, dialog_appears=False)
        w.wire(monkeypatch)
        out = fb._delete_form("s", "L", "id1", "X", actual_title="Form 55")
        assert out["deleted"] is False
        assert "confirm dialog" in out["reason"]

    def test_lingering_row_is_residue_not_success(self, monkeypatch):
        w = _ListWorld({"Form 55": [1, 1]})
        w.wire(monkeypatch)
        out = fb._delete_form("s", "L", "id1", "X", actual_title="Form 55")
        assert out["deleted"] is False
        assert out["residue_in_list"] is True
        assert "did NOT verify" in out["reason"]

    def test_unknown_count_is_never_gone(self, monkeypatch):
        """-1 (leaf count unevaluable) must read as UNKNOWN, not as deleted."""
        w = _ListWorld({"Form 55": [1, -1]})
        w.wire(monkeypatch)
        out = fb._delete_form("s", "L", "id1", "X", actual_title="Form 55")
        assert out["deleted"] is False
        assert out["residue_in_list"] is True

    def test_list_not_rendering_fails_closed(self, monkeypatch):
        w = _ListWorld({"Form 55": [1, 0]})
        w.wire(monkeypatch)
        monkeypatch.setattr(fb, "_wait_text_polling", lambda session, text, **k: False)
        out = fb._delete_form("s", "L", "id1", "X", actual_title="Form 55")
        assert out["deleted"] is False
        assert "did not render" in out["reason"]


# ---------------------------------------------------------------------------
# 5. _verify_no_residue — the no-form-id path must still PROVE cleanliness
# ---------------------------------------------------------------------------
class TestVerifyNoResidue:
    def _wire(self, monkeypatch, leaf, delete_out=None):
        monkeypatch.setattr(fb, "_router_push",
                            lambda session, path, expect_contains="": "nav")
        monkeypatch.setattr(fb, "_wait_text_polling", lambda session, text, **k: True)
        monkeypatch.setattr(fb, "_fill", lambda session, label, value, timeout=15: _cp(0))
        monkeypatch.setattr(fb, "_eval_leaf_count", lambda session, text: leaf)
        if delete_out is not None:
            monkeypatch.setattr(fb, "_delete_form",
                                lambda *a, **k: delete_out)

    def test_zero_rows_is_a_positive_clean_proof(self, monkeypatch):
        self._wire(monkeypatch, leaf=0)
        out = fb._verify_no_residue("s", "L", "ZHC Test Form", False)
        assert out["deleted"] is True and out["verified_gone"] is True
        assert "POSITIVELY absent" in out["note"]

    def test_found_row_gets_actually_deleted(self, monkeypatch):
        self._wire(monkeypatch, leaf=1,
                   delete_out={"deleted": True, "verified_gone": True,
                               "matched_name": "ZHC Test Form"})
        out = fb._verify_no_residue("s", "L", "ZHC Test Form", False)
        assert out["deleted"] is True and out["matched_name"] == "ZHC Test Form"

    def test_unknown_count_not_claimed_clean(self, monkeypatch):
        self._wire(monkeypatch, leaf=-1)
        out = fb._verify_no_residue("s", "L", "ZHC Test Form", False)
        assert out["deleted"] is False
        assert "NOT claiming clean" in out["reason"]

    def test_possible_unnamed_orphan_flagged_loudly(self, monkeypatch):
        """A walk that stopped between create-confirm and id-capture may have
        left a DEFAULT-named form — flag it for the operator, never silently."""
        self._wire(monkeypatch, leaf=0)
        out = fb._verify_no_residue("s", "L", "ZHC Test Form", True)
        assert out["possible_unnamed_orphan"] is True
        assert "OPERATOR REVIEW REQUIRED" in out["orphan_note"]


# ---------------------------------------------------------------------------
# 6. leaf-count evidence helpers
# ---------------------------------------------------------------------------
class TestLeafCountHelpers:
    def test_parses_counts_and_fails_closed(self, monkeypatch):
        monkeypatch.setattr(fb, "_eval", lambda session, js, timeout=12: "3")
        assert fb._eval_leaf_count("s", "X") == 3
        monkeypatch.setattr(fb, "_eval", lambda session, js, timeout=12: "garbage")
        assert fb._eval_leaf_count("s", "X") == -1
        monkeypatch.setattr(fb, "_eval",
                            lambda session, js, timeout=12: (_ for _ in ()).throw(RuntimeError()))
        assert fb._eval_leaf_count("s", "X") == -1

    def test_leaf_count_js_counts_rendered_text_not_input_values(self):
        """The JS must count LEAF textContent — an <input> value (the search box
        echoing the query) has no textContent and can never satisfy the check."""
        js = fb._LEAF_COUNT_JS
        assert "childElementCount === 0" in js
        assert "textContent" in js
        assert ".value" not in js, "input values must never count as list rows"

    def test_menuitem_click_shape(self, monkeypatch):
        calls = []

        def fake_ab(session, *args, timeout=30, stdin=None):
            calls.append(args)
            return _cp(0)

        monkeypatch.setattr(fb, "_ab", fake_ab)
        fb._click_menuitem("s", "Delete")
        assert calls[0] == ("find", "role", "menuitem", "click",
                            "--name", "Delete", "--exact"), (
            "menu Delete must be role-scoped + exact (SELECTORS §3, conf 9.5) — "
            f"got {calls[0]!r}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
