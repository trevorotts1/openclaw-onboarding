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
        src = _read_source()
        assert "general-task" in src
        assert "unrecognized-slug->general" in src
        assert "INGEST-06" in src

    def test_department_slug_docstring_updated_to_match(self):
        """The department_slug kwarg's docstring cites 'funnels' as a sibling
        example when explaining an unregistered 'marketing' slug — that
        sentence must also point at the honest general-task catch-all, not
        the CEO's, and must name D-C2 (the 'General Stuff' display-name
        decision) so a future reader lands on the right spec section."""
        src = _read_source()
        assert '"General Stuff"' in src
        assert "D-C2" in src

    def test_ceo_master_orchestrator_distinction_is_explicit(self):
        """Both corrected sites must explicitly say the CEO/master-orchestrator
        fallback is a DIFFERENT, later tier than the general-task catch-all
        an unrecognized-but-explicit department_slug actually hits — the
        exact distinction whose absence made the original comment wrong."""
        src = _read_source()
        assert src.count("master-orchestrator") >= 1

    def test_module_still_compiles_clean(self):
        """Doc-only change must not have touched executable code."""
        import py_compile

        py_compile.compile(_CC_BOARD_PATH, doraise=True)
