"""P3-04 (c)4 — iframe failure TAXONOMY regression tests.

THE BUG (2026-07-11 investigation, Skill-6 spec): every :class:`IframeDragError`
raised by ``ghl_iframe_drag.py`` (the shared frame-scoped drag/rename/remove
primitive) reached its callers' catch-alls and was flattened into a GENERIC
stall — e.g. ``ghl_survey_builder.build_survey``'s top-level
``except Exception as exc:`` posted the Kanban note
``f"Build exception: {type(exc).__name__}: {exc}"``, which does NOT start with
any of cc_board.py's ``_CC_BLOCK_REASONS`` prefixes (AUTH-STOP / SELECTOR-MISS /
RATE-LIMIT / TOKEN-CONTEXT / PARKED / VERIFY-FAIL). Every OTHER rail failure in
this skill (403 -> TOKEN-CONTEXT, a missing DOM anchor -> SELECTOR-MISS, ...) is
diagnosable on the board via ``note.startswith("<REASON>: ")``
(cc_board.py's own ``CCTask.fail()``/``u9`` selftest asserts exactly that
pattern) — an iframe failure alone was not, so it read as a generic stall
instead of a queryable, diagnosable card.

THE FIX: ``ghl_iframe_drag.classify_board_reason()``/``board_note()`` classify
every ``IframeDragError.code`` this module raises into the SAME 6-value
taxonomy (never inventing a 7th), and prefix the resulting board note with the
cross-origin FRAME the failure happened inside. ``IframeDragStop`` carries that
classified note (``str(exc)`` IS the note) so a caller's generic catch-all needs
no per-caller special-casing to produce a diagnosable card.

FAIL-FIRST PROOF (2.1 law): ``test_pre_fix_generic_wrapping_hides_the_taxonomy``
below reproduces the OLD wrapping shape verbatim and proves it does NOT start
with any taxonomy prefix — i.e. it is exactly the bug this fix removes. Every
other test in this file proves the NEW shape does.

HERMETIC — NO network, NO live browser, NO GHL.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_TOOLS_DIR = _TESTS_DIR.parent / "tools"
for _p in (str(_TOOLS_DIR), str(_TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cc_board  # noqa: E402
import ghl_iframe_drag as idg  # noqa: E402
import ghl_survey_builder as sb  # noqa: E402


# ---------------------------------------------------------------------------
# 0. FAIL-FIRST — the exact pre-fix wrapping shape, proven broken
# ---------------------------------------------------------------------------
def test_pre_fix_generic_wrapping_hides_the_taxonomy():
    """Reproduces build_survey's OLD catch-all note format VERBATIM
    (``f"Build exception: {type(exc).__name__}: {exc}"`` around a bare
    ``RuntimeError(f"STOP (survey iframe-drag:{code}): {reason}")``) and proves
    it does NOT start with any cc_board.py taxonomy prefix — i.e. this
    reproduces the bug. If this assertion ever STARTS failing (the pre-fix
    shape suddenly looks classified), the fixture drifted from the real old
    code and must be re-derived, not the assertion loosened."""
    exc = RuntimeError("STOP (survey iframe-drag:source-not-found): "
                        "drag SOURCE 'City' was not found/visible")
    old_note = f"Build exception: {type(exc).__name__}: {exc}"
    assert not old_note.startswith(tuple(f"{r}: " for r in cc_board._CC_BLOCK_REASONS)), (
        f"pre-fix note unexpectedly carries a taxonomy prefix already: {old_note!r}")


# ---------------------------------------------------------------------------
# 1. classify_board_reason — every code this module raises maps into the
#    cc_board.py taxonomy, never a 7th value
# ---------------------------------------------------------------------------
# Every literal `IframeDragError(...)` code this module raises (v1.3.0), kept
# as an explicit list so a future new code is caught by (b) below rather than
# silently defaulting without a test ever having looked at it.
_ALL_KNOWN_CODES = (
    "bad-role-locator", "cdp-connect-failed", "empty-iframe-selector",
    "empty-locator", "empty-title", "field-not-found", "field-not-removed",
    "field-not-selectable", "no-cdp-url", "no-page", "not-placed",
    "null-bounding-box", "playwright-unavailable", "remove-click-failed",
    "remove-link-not-found", "scroll-hint-not-found", "select-all-failed",
    "source-no-box", "source-not-found", "source-scroll-failed",
    "target-no-box", "target-not-found", "target-scroll-failed",
    "title-commit-failed", "title-not-clickable", "title-not-editable",
    "title-not-found", "title-not-readable", "title-not-set",
    "unknown-iframe-kind",
)


def test_every_known_code_classifies_into_the_cc_taxonomy():
    for code in _ALL_KNOWN_CODES:
        reason = idg.classify_board_reason(code)
        assert reason in cc_board._CC_BLOCK_REASONS, (
            f"classify_board_reason({code!r}) = {reason!r} is NOT one of "
            f"cc_board._CC_BLOCK_REASONS {cc_board._CC_BLOCK_REASONS} — "
            "never invent a 7th taxonomy value")


def test_verify_fail_codes_are_the_interactions_that_landed_but_did_not_verify():
    """The VERIFY-FAIL bucket is specifically: a control WAS resolved/clicked,
    but the resulting state change never verified — never a bare locate miss."""
    for code in ("not-placed", "field-not-removed", "field-not-selectable",
                 "remove-click-failed", "select-all-failed",
                 "title-commit-failed", "title-not-clickable",
                 "title-not-editable", "title-not-readable", "title-not-set"):
        assert idg.classify_board_reason(code) == "VERIFY-FAIL", code


def test_locate_miss_codes_are_selector_miss():
    for code in ("source-not-found", "target-not-found", "empty-locator",
                 "null-bounding-box", "no-cdp-url", "no-page",
                 "playwright-unavailable", "remove-link-not-found",
                 "scroll-hint-not-found", "title-not-found",
                 "unknown-iframe-kind"):
        assert idg.classify_board_reason(code) == "SELECTOR-MISS", code


def test_unknown_future_code_defaults_to_selector_miss_not_a_crash():
    """A code this module has not been taught about yet must still classify
    (degrade to the more common bucket) rather than raise or invent a value."""
    assert idg.classify_board_reason("some-brand-new-code-2027") == "SELECTOR-MISS"


# ---------------------------------------------------------------------------
# 2. board_note — taxonomy prefix at position 0, frame-origin embedded
# ---------------------------------------------------------------------------
def test_board_note_starts_with_the_taxonomy_prefix_and_names_the_frame():
    exc = idg.IframeDragError("source-not-found", "drag SOURCE 'City' was not found")
    note = idg.board_note(exc, iframe_selector='iframe[src*="survey-builder-v2"]')
    assert note.startswith("SELECTOR-MISS: "), note
    assert 'iframe(iframe[src*="survey-builder-v2"])' in note, note
    assert "source-not-found" in note and "was not found" in note


def test_board_note_without_a_selector_still_prefixes_cleanly():
    exc = idg.IframeDragError("title-not-set", "verify miss")
    note = idg.board_note(exc)   # no iframe_selector supplied
    assert note == "VERIFY-FAIL: title-not-set — verify miss", note


def test_cc_board_startswith_classification_actually_matches(monkeypatch):
    """The literal consumer contract: cc_board.py's own CCTask.fail()/u9
    selftest asserts ``note.startswith(f"{REASON}: ")`` — prove board_note()'s
    output satisfies that exact check for every taxonomy value it can produce."""
    for code, expect in (("source-not-found", "SELECTOR-MISS"),
                          ("title-not-set", "VERIFY-FAIL")):
        exc = idg.IframeDragError(code, "x")
        note = idg.board_note(exc, iframe_selector="iframe[src*=x]")
        assert note.startswith(f"{expect}: ")
        assert note.split(":")[0] in cc_board._CC_BLOCK_REASONS


# ---------------------------------------------------------------------------
# 3. IframeDragStop — str(exc) IS the classified note; details ride along
# ---------------------------------------------------------------------------
def test_iframe_drag_stop_str_is_the_classified_note():
    exc = idg.IframeDragError("source-not-found", "not found",
                              details={"strategy": "text=City"})
    stop = idg.IframeDragStop(exc, iframe_selector="iframe[src*=survey]",
                              context="survey iframe-drag")
    assert stop.board_reason == "SELECTOR-MISS"
    assert stop.board_note.startswith("SELECTOR-MISS: ")
    assert str(stop) == f"{stop.board_note} [survey iframe-drag]"
    assert stop.details == {"strategy": "text=City"}
    assert stop.code == "source-not-found"


def test_iframe_drag_stop_tolerates_a_duck_typed_error_without_details():
    """A caller-supplied error-like object (test doubles, or a future variant)
    that carries .code/.reason but NOT .details must not crash construction."""
    class _Bare(RuntimeError):
        def __init__(self, code, reason):
            self.code, self.reason = code, reason
            super().__init__(f"{code}: {reason}")
    stop = idg.IframeDragStop(_Bare("title-not-editable", "no focus"))
    assert stop.details is None
    assert stop.board_reason == "VERIFY-FAIL"


# ---------------------------------------------------------------------------
# 4. Integration — the survey builder's catch-all posts the classified note,
#    not the generic "Build exception: ..." wrapper
# ---------------------------------------------------------------------------
def test_board_fail_note_posts_classified_note_verbatim():
    exc = idg.IframeDragError("source-not-found", "not found")
    stop = idg.IframeDragStop(exc, iframe_selector='iframe[src*="survey-builder-v2"]',
                              context="survey iframe-drag")
    note = sb._board_fail_note(stop)
    # `.board_note` (what a caller posts to the board) omits the trailing
    # "[context]" tag that str(stop) (the human/log message) carries.
    assert note == stop.board_note
    assert note.startswith("SELECTOR-MISS: ")


def test_board_fail_note_falls_back_to_generic_wrapper_for_ordinary_exceptions():
    """A plain exception with no .board_note (every OTHER exception type in the
    build) is UNCHANGED — still wrapped, so this fix never masks a real
    unclassified failure as something it is not."""
    exc = ValueError("something else entirely")
    note = sb._board_fail_note(exc)
    assert note == "Build exception: ValueError: something else entirely"
    assert not note.startswith(tuple(f"{r}: " for r in cc_board._CC_BLOCK_REASONS))


def test_perform_iframe_drag_raises_classified_stop(monkeypatch):
    """sb._perform_iframe_drag's IframeDragError catch must raise an
    IframeDragStop whose str() carries the SELECTOR-MISS/frame-origin note —
    the exact object build_survey's catch-all now special-cases."""
    def fake_coordinate_drag(cdp_url, *, iframe_selector, source, target,
                             url_marker, verify_text):
        raise idg.IframeDragError("source-not-found", "drag SOURCE 'Rating' was not found")

    monkeypatch.setattr(sb, "_get_cdp_url", lambda session: "ws://live")
    monkeypatch.setattr(sb._ghl_iframe_drag, "coordinate_drag", fake_coordinate_drag)

    with pytest.raises(idg.IframeDragStop) as ei:
        sb._perform_iframe_drag("s", "Rating", "Slide 2", verify_text="Rating")
    assert str(ei.value).startswith("SELECTOR-MISS: iframe(")
    assert sb.GHL_SURVEY_IFRAME_SELECTOR in str(ei.value)
    # And the board note the catch-all would post is the classified `.board_note`
    # (str(exc) additionally carries the "[survey iframe-drag]" context tag).
    assert sb._board_fail_note(ei.value) == ei.value.board_note
    assert sb._board_fail_note(ei.value).startswith("SELECTOR-MISS: ")


# ---------------------------------------------------------------------------
# P3-04 (c)4 fix-loop item 6 — the PRE-FLIGHT stops (primitive-missing /
# CDP-url-missing) fire BEFORE any IframeDragError can exist, so they could
# never be caught by the `except _ghl_iframe_drag.IframeDragError` blocks
# above. Before this fix-loop item they raised a bare
# `RuntimeError("STOP (survey iframe-drag): ...")` with no `.board_note`,
# which `_board_fail_note()` posts as a generic
# `"Build exception: RuntimeError: STOP (survey iframe-drag): ..."` card —
# reproduced verbatim by the FAIL-FIRST assertions below (each proves what
# the OLD raise site would have produced), then the NEW `_InfraStop`-raising
# behavior is proven to carry the SELECTOR-MISS classification instead.
# ---------------------------------------------------------------------------
def test_pre_fix_primitive_missing_would_have_hidden_the_taxonomy():
    """FAIL-FIRST: reproduces the OLD bare-RuntimeError shape for the
    primitive-missing case verbatim and proves it does NOT classify."""
    old_shape = RuntimeError(
        "STOP (survey iframe-drag): the shared ghl_iframe_drag primitive is not "
        "importable, and agent-browser 0.27.0 alone cannot locate a non-interactive "
        "field row across the cross-origin survey-builder iframe. Ship "
        "ghl_iframe_drag.py + Playwright (scoped to Skill 6)."
    )
    note = sb._board_fail_note(old_shape)
    assert note == f"Build exception: RuntimeError: {old_shape}"
    assert not note.startswith(tuple(f"{r}: " for r in cc_board._CC_BLOCK_REASONS))


def test_infra_stop_carries_selector_miss_board_note():
    """_InfraStop (the fix) carries a pre-classified .board_note SELECTOR-MISS
    is the correct bucket — ghl_iframe_drag.classify_board_reason()'s own
    bucket doc names "the CDP endpoint/Playwright itself could not be
    resolved or reached" as SELECTOR-MISS, never a 7th taxonomy value."""
    exc = sb._InfraStop(
        "primitive-unavailable", "the shared primitive is not importable",
        iframe_selector=sb.GHL_SURVEY_IFRAME_SELECTOR,
    )
    assert exc.board_reason == "SELECTOR-MISS"
    assert exc.board_note.startswith("SELECTOR-MISS: iframe(")
    assert sb.GHL_SURVEY_IFRAME_SELECTOR in exc.board_note
    assert sb._board_fail_note(exc) == exc.board_note


def test_perform_iframe_drag_primitive_missing_raises_classified_infra_stop(monkeypatch):
    """_perform_iframe_drag's `_ghl_iframe_drag is None` branch must raise a
    classified _InfraStop, not a bare RuntimeError -- fixes the P3-04 (c)4
    fix-loop item 6 residual."""
    monkeypatch.setattr(sb, "_ghl_iframe_drag", None)
    with pytest.raises(sb._InfraStop) as ei:
        sb._perform_iframe_drag("s", "Rating", "Slide 2", verify_text="Rating")
    assert ei.value.board_note.startswith("SELECTOR-MISS: ")
    assert "primitive-unavailable" in ei.value.board_note
    assert sb._board_fail_note(ei.value).startswith("SELECTOR-MISS: ")


def test_perform_iframe_drag_cdp_url_missing_raises_classified_infra_stop(monkeypatch):
    """_perform_iframe_drag's empty-cdp_url branch must raise a classified
    _InfraStop, not a bare RuntimeError."""
    monkeypatch.setattr(sb, "_get_cdp_url", lambda session: "")
    with pytest.raises(sb._InfraStop) as ei:
        sb._perform_iframe_drag("s", "Rating", "Slide 2", verify_text="Rating")
    assert ei.value.board_note.startswith("SELECTOR-MISS: ")
    assert "cdp-url-missing" in ei.value.board_note
    assert sb._board_fail_note(ei.value).startswith("SELECTOR-MISS: ")


def test_rename_survey_primitive_missing_raises_classified_infra_stop(monkeypatch, tmp_path):
    """_p2_rename_survey's `_ghl_iframe_drag is None` branch must raise a
    classified _InfraStop, not a bare RuntimeError."""
    monkeypatch.setattr(sb, "_ghl_iframe_drag", None)
    with pytest.raises(sb._InfraStop) as ei:
        sb._p2_rename_survey("s", "My Survey", str(tmp_path), [0])
    assert ei.value.board_note.startswith("SELECTOR-MISS: ")
    assert "primitive-unavailable" in ei.value.board_note
    assert sb.GHL_SURVEY_IFRAME_SELECTOR in ei.value.board_note
    assert sb._board_fail_note(ei.value).startswith("SELECTOR-MISS: ")


def test_rename_survey_cdp_url_missing_raises_classified_infra_stop(monkeypatch, tmp_path):
    """_p2_rename_survey's empty-cdp_url branch must raise a classified
    _InfraStop, not a bare RuntimeError."""
    monkeypatch.setattr(sb, "_get_cdp_url", lambda session: "")
    with pytest.raises(sb._InfraStop) as ei:
        sb._p2_rename_survey("s", "My Survey", str(tmp_path), [0])
    assert ei.value.board_note.startswith("SELECTOR-MISS: ")
    assert "cdp-url-missing" in ei.value.board_note
    assert sb._board_fail_note(ei.value).startswith("SELECTOR-MISS: ")
