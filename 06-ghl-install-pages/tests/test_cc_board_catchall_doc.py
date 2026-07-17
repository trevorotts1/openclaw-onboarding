# test_cc_board_catchall_doc.py — cc_board.py producer-doc conformance for
# the funnel -> Marketing routing fix (2026-07-16).
#
# HISTORY: an earlier correction (C-13(e)/U44) fixed a STALE claim that an
# unrecognized department_slug (e.g. the fake 'funnels' slug) "mis-resolves
# to the CEO catch-all" — the real behavior is INGEST-06
# (src/app/api/tasks/ingest/route.ts's resolveWorkspaceId(), the
# "EXPLICIT-but-unrecognized department slug" tier) routing it to the honest
# `general-task` catch-all instead. That correction's own comments then went
# on to (wrongly) claim a 'marketing' slug ALSO hits that same
# unrecognized-slug/general-task path — it does not: 'marketing' IS a
# registered floor department (departments.config.ts id 'marketing'; #1 in
# department-floor.py's HARDCODED_MANDATORY) that every box seeds with a bare
# workspaces.slug, so INGEST's TIER-1 exact slug match resolves it directly.
#
# THE FIX THIS TEST PINS: the job_type=='funnel' branch now stamps
# department_slug='marketing' (not the fake 'funnels' slug), and both
# producer-side doc sites (the funnel-branch NOTE and the department_slug
# kwarg docstring) now describe the REAL tier-1 direct-match routing instead
# of the general-task fallback the old fake 'funnels' slug used to hit.
#
# This is a doc + one-line-stamp conformance test — it pins cc_board.py's own
# producer-side documentation (and the literal slug it stamps) against the
# real CC consumer behavior so the two never drift apart again silently.
#
# Proven to FAIL on the pre-fix tree: `department_slug = "funnels"` is the
# literal in the source (the anchor below), the funnel-branch NOTE talks
# about the general-task/unrecognized-slug path (not tier-1/HARDCODED_MANDATORY),
# and the department_slug kwarg docstring still claims 'marketing' "has not
# yet registered" and falls to general-task — every assertion below failed.
# PASSES post-fix.
from __future__ import annotations

import os

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
_CC_BOARD_PATH = os.path.join(_TOOLS_DIR, "cc_board.py")


def _read_source() -> str:
    with open(_CC_BOARD_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _funnel_branch_note() -> str:
    """The contiguous ``#`` comment block immediately preceding the funnel
    branch's ``department_slug = "marketing"`` assignment — i.e. THE producer
    NOTE that documents where a funnel card actually lands.

    Site-anchored on purpose: a file-global substring check would still pass
    if this NOTE were deleted outright (the sibling docstring site mentions
    the same tokens), which would silently un-document the exact code path
    this fix corrects.
    """
    src = _read_source()
    anchor = src.index('        department_slug = "marketing"')
    block = []
    for line in reversed(src[:anchor].splitlines()):
        if line.strip().startswith("#"):
            block.append(line)
        else:
            break
    assert block, (
        "the funnel branch's producer NOTE (the contiguous comment block above "
        '`department_slug = "marketing"`) is MISSING — this fix requires that '
        "code path document the real tier-1 direct-match routing"
    )
    return "\n".join(reversed(block))


def _department_slug_docstring() -> str:
    """The ``department_slug:`` kwarg's docstring section (up to the next
    ``source:`` kwarg) — the second site this fix touches."""
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

    def test_funnels_fake_slug_is_not_stamped(self):
        """The historical fake slug must not be the literal stamped for a
        funnel card. `'funnels'` may still appear in prose (citing the
        historical bug) but never as the assigned value."""
        src = _read_source()
        assert 'department_slug = "funnels"' not in src, (
            "the fake 'funnels' slug is still being stamped for job_type="
            "'funnel' — the funnel-misroute fix did not land"
        )
        assert 'department_slug = "marketing"' in src, (
            "the funnel branch does not stamp the real 'marketing' floor "
            "department"
        )

    def test_funnel_note_documents_tier1_marketing_routing(self):
        """The job_type=='funnel' branch's producer NOTE must name the REAL
        routing mechanism (tier-1 exact slug match landing on the real
        Marketing workspace) and the historical bug it replaces, so the
        producer's own comment matches the consumer's real behavior."""
        note = _funnel_branch_note()
        for token in (
            "marketing",
            "HARDCODED_MANDATORY",
            "tier-1",
            "unrecognized-slug->general",
        ):
            assert token in note, (
                f"the funnel branch's producer NOTE does not mention {token!r} — "
                "this fix requires THAT site (not merely some other comment "
                "elsewhere in the file) describe the real tier-1 routing and "
                "the historical bug it replaces"
            )

    def test_department_slug_docstring_updated_to_match(self):
        """The department_slug kwarg's docstring used to claim an
        unregistered 'marketing' slug also falls to general-task — that was
        never true. It must now say 'marketing' IS a registered floor
        department resolved by INGEST's tier-1 exact slug match."""
        doc = _department_slug_docstring()
        for token in ("registered floor department", "HARDCODED_MANDATORY", "tier-1"):
            assert token in doc, (
                f"the department_slug kwarg docstring does not mention {token!r} "
                "— this fix requires THAT site carry the correction too"
            )
        assert "has not yet registered" not in doc, (
            "the stale 'has not yet registered' claim about 'marketing' is "
            "still present in the department_slug kwarg docstring"
        )

    def test_ceo_master_orchestrator_distinction_is_explicit(self):
        """BOTH corrected sites must explicitly say the CEO/master-orchestrator
        fallback is a DIFFERENT, later tier than tier-1's direct slug match —
        the exact distinction whose absence made the original comment wrong.
        Asserted per-site: a file-global count would stay green if either
        site silently lost the distinction."""
        assert "master-orchestrator" in _funnel_branch_note(), (
            "the funnel branch's producer NOTE lost the CEO/master-orchestrator "
            "vs tier-1 distinction"
        )
        assert "master-orchestrator" in _department_slug_docstring(), (
            "the department_slug kwarg docstring lost the CEO/master-orchestrator "
            "vs tier-1 distinction"
        )

    def test_module_still_compiles_clean(self):
        """The fix must not have broken the module's syntax."""
        import py_compile

        py_compile.compile(_CC_BOARD_PATH, doraise=True)
