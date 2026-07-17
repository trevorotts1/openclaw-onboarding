# test_cc_board_catchall_doc.py — U44(e) / C-13(e): cc_board.py producer-doc
# conformance (the STALE "CEO catch-all" comment fix).
#
# MASTER SPEC v2 C-13 (Catch-all department conformance) point (e) / C+I.0
# point 13: cc_board.py's producer-side comments claimed an unrecognized
# department_slug (e.g. 'funnels', which has no registered department in
# departments.config.ts) "mis-resolves to the CEO catch-all". That was
# VERIFIED STALE at CC main: INGEST-06 (src/app/api/tasks/ingest/route.ts's
# resolveWorkspaceId(), the "EXPLICIT-but-unrecognized department slug" tier,
# ~line 260-281 at CC HEAD aa34b724) routes an explicit-but-unrecognized slug
# to the honest `general-task` catch-all (display "General Stuff" per D-C2),
# tagged resolvedBy='unrecognized-slug->general' — it NEVER falls through to
# the CEO/master-orchestrator workspace for that case. The CEO fallback is a
# SEPARATE, later tier (resolveWorkspaceId tier 3) that only fires for a BARE
# task with no department_slug supplied at all — a different code path this
# producer's funnel/website ingest calls never hit (ingest_task always sets
# department_slug via the job_type mapping or an explicit override).
#
# This is a doc-only source-text conformance test — no functional behavior
# changed (the fix is comment-text only), so there is no runtime seam to
# exercise. It pins cc_board.py's own producer-side documentation against the
# real consumer behavior so the two never drift apart again silently.
#
# Proven to FAIL on the pre-fix tree: both sites literally read "...mis-
# resolves to the CEO catch-all..." / "...resolves to the CEO catch-all
# column server-side..." with no 'general-task' or 'unrecognized-slug'
# mention anywhere in the file — every assertion below failed. PASSES
# post-fix.
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
    the same tokens), which would silently un-document the exact code path
    C-13(e) exists to correct.
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
        '`department_slug = "funnels"`) is MISSING — C-13(e)/U44 requires that '
        "code path document the real INGEST-06 general-task routing"
    )
    return "\n".join(reversed(block))


def _department_slug_docstring() -> str:
    """The ``department_slug:`` kwarg's docstring section (up to the next
    ``source:`` kwarg) — the second site the C-13(e) correction touches."""
    src = _read_source()
    start = src.index("        department_slug: ")
    end = src.index("        source:  ", start)
    return src[start:end]


class TestCatchAllProducerDocConformance:
    def test_stale_ceo_catch_all_claim_is_gone(self):
        """The bare, unqualified claim that an unrecognized department_slug
        resolves to 'the CEO catch-all' must not appear. The phrase may still
        appear ONLY inside a "was stale ... 'CEO catch-all'" correction note
        (a citation of the retired wording, not a live claim) — so this
        checks for the specific stale ASSERTION patterns, not the bare
        substring (which the correction note itself legitimately quotes)."""
        src = _read_source()
        assert "mis-resolves to the CEO catch-all" not in src, (
            "stale unqualified claim ('mis-resolves to the CEO catch-all') "
            "still present — C-13(e)/U44 requires cc_board.py describe the "
            "real INGEST-06 general-task routing instead"
        )
        assert "resolves to the CEO catch-all column server-side" not in src, (
            "stale unqualified claim ('resolves to the CEO catch-all column "
            "server-side') still present — C-13(e)/U44 requires cc_board.py "
            "describe the real INGEST-06 general-task routing instead"
        )

    def test_funnels_note_documents_ingest06_general_task_routing(self):
        """The job_type=='funnel' branch's producer NOTE must name the REAL
        catch-all (general-task / 'General Stuff') and the REAL resolvedBy
        tag INGEST-06 actually stamps, so the producer's own comment matches
        the consumer's real behavior."""
        note = _funnel_branch_note()
        for token in ("general-task", "unrecognized-slug->general", "INGEST-06"):
            assert token in note, (
                f"the funnel branch's producer NOTE does not mention {token!r} — "
                "C-13(e)/U44 requires THAT site (not merely some other comment "
                "elsewhere in the file) describe the real INGEST-06 routing"
            )

    def test_department_slug_docstring_updated_to_match(self):
        """The department_slug kwarg's docstring cites 'funnels' as a sibling
        example when explaining an unregistered 'marketing' slug — that
        sentence must also point at the honest general-task catch-all, not
        the CEO's, and must name D-C2 (the 'General Stuff' display-name
        decision) so a future reader lands on the right spec section."""
        doc = _department_slug_docstring()
        for token in ("general-task", '"General Stuff"', "D-C2"):
            assert token in doc, (
                f"the department_slug kwarg docstring does not mention {token!r} "
                "— C-13(e)/U44 requires THAT site carry the correction too"
            )

    def test_ceo_master_orchestrator_distinction_is_explicit(self):
        """BOTH corrected sites must explicitly say the CEO/master-orchestrator
        fallback is a DIFFERENT, later tier than the general-task catch-all
        an unrecognized-but-explicit department_slug actually hits — the
        exact distinction whose absence made the original comment wrong.
        Asserted per-site: a file-global count would stay green if either
        site silently lost the distinction."""
        assert "master-orchestrator" in _funnel_branch_note(), (
            "the funnel branch's producer NOTE lost the CEO/master-orchestrator "
            "vs general-task tier distinction"
        )
        assert "master-orchestrator" in _department_slug_docstring(), (
            "the department_slug kwarg docstring lost the CEO/master-orchestrator "
            "vs general-task tier distinction"
        )

    def test_module_still_compiles_clean(self):
        """Doc-only change must not have touched executable code."""
        import py_compile

        py_compile.compile(_CC_BOARD_PATH, doraise=True)
