# test_cc_board_catchall_doc.py — cc_board.py producer-doc conformance for
# Skill-6 funnel routing (2026-07-16 operator-ruling reversal + registration).
#
# HISTORY (oldest first):
#   1. C-13(e)/U44 corrected a stale claim that an explicit but unrecognized
#      department_slug misrouted to the CEO fallback. The consumer instead
#      sends that case to the general-task catch-all.
#   2. A separate stale claim said a 'marketing' override was unregistered and
#      fell to the same catch-all. That was never true: Marketing is a real
#      mandatory floor department and resolves through the consumer's tier-1
#      exact slug/id lookup.
#   3. A temporary direction proposed changing the funnel producer stamp to
#      'marketing'. The operator reversed that direction: keep the dedicated
#      'funnels' slug and register Funnels as its own mandatory department.
#   4. The ONB registration in this change adds mandatory.funnels, includes it
#      in department-floor.py's HARDCODED_MANDATORY, and ships its roles and
#      templates. The separate consuming-repository companion is outside this
#      test's mutation scope; the sibling registration-gap test mirrors the
#      consumer's tier-1 query to prove the producer/registration contract.
#
# This test pins the producer's comments and literal stamp against that state
# so the executable route and its documentation cannot drift silently.
from __future__ import annotations

import os

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
_CC_BOARD_PATH = os.path.join(_TOOLS_DIR, "cc_board.py")


def _read_source() -> str:
    with open(_CC_BOARD_PATH, "r", encoding="utf-8") as file_handle:
        return file_handle.read()


def _funnel_branch_note() -> str:
    """Return the contiguous comment immediately above the funnel assignment."""
    src = _read_source()
    anchor = src.index('        department_slug = "funnels"')
    block = []
    for line in reversed(src[:anchor].splitlines()):
        if line.strip().startswith("#"):
            block.append(line)
        else:
            break
    assert block, (
        "the funnel branch's producer NOTE is missing — it must document the "
        "current registered routing state"
    )
    return "\n".join(reversed(block))


def _department_slug_docstring() -> str:
    """Return the explicit department_slug override section of the docstring."""
    src = _read_source()
    start = src.index("        department_slug: ")
    end = src.index("        source:  ", start)
    return src[start:end]


class TestCatchAllProducerDocConformance:
    def test_stale_ceo_catch_all_claim_is_gone(self):
        """The retired unqualified CEO-fallback claims must not reappear."""
        src = _read_source()
        assert "mis-resolves to the CEO catch-all" not in src, (
            "stale unqualified CEO catch-all claim is still present in cc_board.py"
        )
        assert "resolves to the CEO catch-all column server-side" not in src, (
            "stale unqualified CEO catch-all column claim is still present"
        )

    def test_funnels_slug_is_stamped_per_operator_ruling(self):
        """The producer must retain the dedicated Funnels slug."""
        src = _read_source()
        assert 'department_slug = "funnels"' in src, (
            "the funnel branch no longer stamps 'funnels'"
        )
        assert 'department_slug = "marketing"' not in src, (
            "the funnel branch was incorrectly rerouted to Marketing"
        )

    def test_funnel_note_documents_registration_landed(self):
        """The funnel-branch note must describe the registered state."""
        note = _funnel_branch_note()
        for token in (
            "REGISTERED",
            "HARDCODED_MANDATORY",
            "unrecognized-slug->general",
        ):
            assert token in note, (
                f"the funnel branch note does not mention {token!r}"
            )
        assert "OPEN GAP" not in note, (
            "the funnel branch note still claims an open registration gap"
        )

    def test_funnel_note_documents_deliberate_catalog_overlap(self):
        """The three-department funnel-role overlap must stay explicit."""
        note = _funnel_branch_note()
        for token in (
            "Funnel Strategist",
            "Signature Funnel Specialist",
            "Web Development",
        ):
            assert token in note, (
                f"the funnel branch note does not mention {token!r}"
            )

    def test_department_slug_docstring_correct(self):
        """The explicit Marketing override must be documented as registered."""
        doc = _department_slug_docstring()
        for token in (
            "registered floor department",
            "HARDCODED_MANDATORY",
            "tier-1",
        ):
            assert token in doc, (
                f"the department_slug docstring does not mention {token!r}"
            )
        assert "has not yet registered" not in doc, (
            "the docstring still claims Marketing is unregistered"
        )

    def test_ceo_master_orchestrator_distinction_is_explicit(self):
        """Both documentation sites must distinguish the later CEO fallback."""
        assert "master-orchestrator" in _funnel_branch_note(), (
            "the funnel branch note lost the master-orchestrator distinction"
        )
        assert "master-orchestrator" in _department_slug_docstring(), (
            "the department_slug docstring lost the master-orchestrator distinction"
        )

    def test_module_still_compiles_clean(self):
        """Documentation changes must not break Python syntax."""
        import py_compile

        py_compile.compile(_CC_BOARD_PATH, doraise=True)
