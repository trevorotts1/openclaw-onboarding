# test_cc_board_catchall_doc.py — cc_board.py producer-doc conformance for
# Skill-6 funnel routing (2026-07-16, operator-ruling REVERSAL).
#
# HISTORY (three layers, oldest first):
#   1. C-13(e)/U44 fixed a STALE claim that an unrecognized department_slug
#      (the fake 'funnels' slug) "mis-resolves to the CEO catch-all" — the
#      real behavior is INGEST-06 (src/app/api/tasks/ingest/route.ts's
#      resolveWorkspaceId(), the "EXPLICIT-but-unrecognized department slug"
#      tier) routing it to the honest `general-task` catch-all instead.
#   2. A same-day follow-up correction fixed a SEPARATE stale claim in the
#      SAME comment block: that a 'marketing' override slug was ALSO
#      unregistered and fell to general-task like 'funnels' — that was never
#      true; 'marketing' IS a registered floor department. This correction
#      STANDS regardless of what job_type='funnel' stamps by default (see
#      _department_slug_docstring / test_department_slug_docstring_correct
#      below) — it describes the FIX-COPY-01 explicit-override path, not the
#      funnel branch's default.
#   3. A same-day direction change proposed rerouting job_type='funnel' to
#      stamp 'marketing' instead of 'funnels'. THE OPERATOR REVERSED THIS:
#      keep stamping 'funnels'; register 'funnels' as its OWN floor
#      department instead of folding funnel work into Marketing. That
#      registration is NOT done (a real suggested-roles catalog + floor entry
#      is an operator content decision, out of scope for this pass) — the
#      funnel-branch NOTE documents the OPEN GAP honestly instead of
#      claiming a fix that hasn't landed.
#
# This is a doc + stamp conformance test — it pins cc_board.py's own
# producer-side documentation (and the literal slug it stamps) against
# reality so the two never drift apart silently. It does NOT claim the
# routing bug is fixed — see test_cc_board_funnel_department_registration_gap.py
# for the open-gap trace.
from __future__ import annotations

import os

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
_CC_BOARD_PATH = os.path.join(_TOOLS_DIR, "cc_board.py")


def _read_source() -> str:
    with open(_CC_BOARD_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _funnel_branch_note() -> str:
    """The contiguous ``#`` comment block immediately preceding the funnel
    branch's ``department_slug = "funnels"`` assignment — i.e. THE producer
    NOTE that documents where a funnel card actually lands.

    Site-anchored on purpose: a file-global substring check would still pass
    if this NOTE were deleted outright (the sibling docstring site mentions
    some of the same tokens), which would silently un-document the exact
    code path this file tracks.
    """
    src = _read_source()
    anchor = src.index('        department_slug = "funnels"')
    block = []
    for line in reversed(src[:anchor].splitlines()):
        if line.strip().startswith("#"):
            block.append(line)
        else:
            break
    assert block, (
        "the funnel branch's producer NOTE (the contiguous comment block above "
        '`department_slug = "funnels"`) is MISSING — it must document the '
        "current open-gap routing state"
    )
    return "\n".join(reversed(block))


def _department_slug_docstring() -> str:
    """The ``department_slug:`` kwarg's docstring section (up to the next
    ``source:`` kwarg) — the FIX-COPY-01 explicit-override site."""
    src = _read_source()
    start = src.index("        department_slug: ")
    end = src.index("        source:  ", start)
    return src[start:end]


class TestCatchAllProducerDocConformance:
    def test_stale_ceo_catch_all_claim_is_gone(self):
        """The bare, unqualified claim that an unrecognized department_slug
        resolves to 'the CEO catch-all' must not appear anywhere — the old
        C-13(e)/U44 stale wording this repo has already corrected once."""
        src = _read_source()
        assert "mis-resolves to the CEO catch-all" not in src, (
            "stale unqualified claim ('mis-resolves to the CEO catch-all') "
            "still present in cc_board.py"
        )
        assert "resolves to the CEO catch-all column server-side" not in src, (
            "stale unqualified claim ('resolves to the CEO catch-all column "
            "server-side') still present in cc_board.py"
        )

    def test_funnels_slug_is_stamped_per_operator_ruling(self):
        """The operator's 2026-07-16 ruling: keep stamping the historical
        'funnels' slug (do NOT reroute to 'marketing') while the department
        is registered separately."""
        src = _read_source()
        assert 'department_slug = "funnels"' in src, (
            "the funnel branch no longer stamps 'funnels' — this contradicts "
            "the operator's ruling to keep the slug and register the "
            "department separately"
        )
        assert 'department_slug = "marketing"' not in src, (
            "the funnel branch stamps 'marketing' — the operator explicitly "
            "reversed this direction; funnel cards must NOT be rerouted to "
            "Marketing"
        )

    def test_funnel_note_documents_open_registration_gap(self):
        """The job_type=='funnel' branch's producer NOTE must honestly
        document that 'funnels' is NOT YET a registered department (the open
        gap), not claim a resolution that hasn't landed."""
        note = _funnel_branch_note()
        for token in (
            "not a registered",
            "HARDCODED_MANDATORY",
            "unrecognized-slug->general",
            "OPEN GAP",
        ):
            assert token in note, (
                f"the funnel branch's producer NOTE does not mention {token!r} — "
                "it must honestly document the current open routing gap, not "
                "a fix that hasn't landed"
            )

    def test_funnel_note_flags_marketing_role_catalog_overlap(self):
        """The NOTE must flag the overlap with Marketing's existing funnel
        roles (Funnel Strategist, Signature Funnel Specialist) — the exact
        reason registering 'funnels' as a standalone department is an
        operator content decision, not a mechanical one."""
        note = _funnel_branch_note()
        for token in ("Funnel Strategist", "Signature Funnel Specialist"):
            assert token in note, (
                f"the funnel branch's producer NOTE does not mention the "
                f"existing Marketing role {token!r} — the overlap this "
                "registration decision must reconcile is undocumented"
            )

    def test_department_slug_docstring_correct(self):
        """The department_slug kwarg's docstring (FIX-COPY-01 explicit
        override site) must say 'marketing' IS a registered floor department
        resolved by INGEST's tier-1 exact slug match — this correction is
        independent of which slug the funnel branch defaults to."""
        doc = _department_slug_docstring()
        for token in ("registered floor department", "HARDCODED_MANDATORY", "tier-1"):
            assert token in doc, (
                f"the department_slug kwarg docstring does not mention {token!r} "
                "— the 'marketing IS registered' correction must carry here"
            )
        assert "has not yet registered" not in doc, (
            "the stale 'has not yet registered' claim about 'marketing' is "
            "still present in the department_slug kwarg docstring"
        )

    def test_ceo_master_orchestrator_distinction_is_explicit(self):
        """BOTH sites must explicitly say the CEO/master-orchestrator
        fallback is a DIFFERENT, later tier than the general-task catch-all —
        the exact distinction whose absence made the original comment wrong.
        Asserted per-site: a file-global count would stay green if either
        site silently lost the distinction."""
        assert "master-orchestrator" in _funnel_branch_note(), (
            "the funnel branch's producer NOTE lost the CEO/master-orchestrator "
            "vs general-task tier distinction"
        )
        assert "master-orchestrator" in _department_slug_docstring(), (
            "the department_slug kwarg docstring lost the CEO/master-orchestrator "
            "vs tier-1 distinction"
        )

    def test_module_still_compiles_clean(self):
        """Doc changes must not have broken the module's syntax."""
        import py_compile

        py_compile.compile(_CC_BOARD_PATH, doraise=True)
