#!/usr/bin/env python3
"""
Unit tests for the Bug 1 + Bug 2 prevention fixes.

BUG 1 — library gate trusted a marker instead of verifying content:
  A prior fill stamped "<!-- Filled from role-library v... -->" onto thin
  hand-written stubs (e.g. 156 bytes).  qc-completeness.sh counted those as
  library_filled=True, driving library_pct=100%, so verify-library-gate.sh
  passed rfilled=True while verify-wiring.sh (which checks file size >= 3072 B)
  correctly failed the same file.  The fix: a how-to.md is only counted as
  library-filled when BOTH the marker is present AND the file is >= LIBRARY_MIN_BYTES
  (3072 B).  The fill scripts (build-workforce.py / create_role_workspaces.py) now
  refuse to stamp the marker on thin output, returning None to trigger the
  PENDING-stub path.

BUG 2 — department-floor.py sys.path order made shared-utils win over lib/:
  resolve_departments_dir() called sys.path.insert(0, ...) for lib/, then for
  shared-utils, so shared-utils ended up at position 0 (last insert wins).
  The shared-utils detect_platform returns company_dir=None on the ~/clawd layout
  (it expects ~/Downloads/openclaw-master-files), causing a false rc=7 "no
  workforce / cannot resolve company".  Fix: insert lib/ LAST so it sits at
  position 0, matching how qc-completeness.sh resolves detect_platform.

Run:
    python3 tests/unit/library-gate-content.test.py
    pytest tests/unit/library-gate-content.test.py
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo layout helpers
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent          # tests/unit/
_REPO_ROOT = _HERE.parent.parent       # repo root
_SCRIPTS = _REPO_ROOT / "23-ai-workforce-blueprint" / "scripts"

assert _SCRIPTS.is_dir(), f"23-ai-workforce-blueprint/scripts not found at {_SCRIPTS}"

# ---------------------------------------------------------------------------
# Dynamic import helpers — load the modules without __main__ side effects
# ---------------------------------------------------------------------------
def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None, f"Could not find {path}"
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)  # type: ignore
    return mod


# Constants replicated from the fixed scripts (authoritative source = scripts).
LIBRARY_MIN_BYTES = 3072          # HOW_TO_MIN_BYTES in verify-wiring.sh
MARKER_FILLED      = "<!-- Filled from role-library v1.0 on 2026-06-15 -->\n"
MARKER_WS2         = ("<!-- WS-2: instantiated from role-library v1.0 "
                       "(marketing-director) on 2026-06-15. Pre-written "
                       "Section-9 SOPs included - not LLM-regenerated. -->\n")
PENDING_STUB_BODY  = "# Director - how-to.md  [PENDING - FILL FROM LIBRARY]\n"


def _make_howto(tmp: Path, name: str, content: str) -> Path:
    p = tmp / name
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Inline reimplementation of the gate logic from qc-completeness.sh
# (the Python snippet embedded in the bash heredoc)
# ---------------------------------------------------------------------------
LIBRARY_MARKER_RE = re.compile(
    r"<!--\s*(?:WS-2: instantiated|Filled) from role-library v",
    re.IGNORECASE,
)

def gate_is_library_filled(howto_path: Path) -> bool:
    """
    Replicate the BUG-1-FIXED check from qc-completeness.sh:
      marker present in first 4096 bytes AND file size >= LIBRARY_MIN_BYTES.
    """
    try:
        howto_size = howto_path.stat().st_size
        with howto_path.open(encoding="utf-8", errors="ignore") as fh:
            head = fh.read(4096)
        return LIBRARY_MARKER_RE.search(head) is not None and howto_size >= LIBRARY_MIN_BYTES
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Inline reimplementation of the fill-gate from build-workforce.py /
# create_role_workspaces.py (the size-guard before stamping the marker).
# ---------------------------------------------------------------------------
def fill_guard_would_stamp(content: str) -> bool:
    """
    Return True if the fill script would stamp the marker (content >= floor).
    Return False if it would refuse and return None (thin content).
    """
    return len(content.encode("utf-8")) >= LIBRARY_MIN_BYTES


# ---------------------------------------------------------------------------
# BUG 1 TESTS — library gate content check
# ---------------------------------------------------------------------------

class TestLibraryGateContentCheck(unittest.TestCase):
    """Bug 1: gate must check size, not just the marker."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    # — FAIL cases (thin stubs that used to pass) ——————————————————————————

    def test_thin_stub_with_filled_marker_fails(self):
        """A 156-byte file with the 'Filled' marker MUST fail (thin-stub bug)."""
        content = MARKER_FILLED + "# Director\n\nThin stub.\n"
        self.assertLess(len(content.encode()), LIBRARY_MIN_BYTES,
                        "Precondition: test content is thin")
        p = _make_howto(self.tmp, "thin-filled.md", content)
        self.assertFalse(
            gate_is_library_filled(p),
            "Thin stub with 'Filled' marker should NOT count as library-filled",
        )

    def test_thin_stub_with_ws2_marker_fails(self):
        """A thin file with the 'WS-2: instantiated' marker MUST fail."""
        content = MARKER_WS2 + "# Director\n\nThin stub.\n"
        self.assertLess(len(content.encode()), LIBRARY_MIN_BYTES)
        p = _make_howto(self.tmp, "thin-ws2.md", content)
        self.assertFalse(
            gate_is_library_filled(p),
            "Thin stub with WS-2 marker should NOT count as library-filled",
        )

    def test_stub_without_any_marker_fails(self):
        """A file with no marker at all fails regardless of size."""
        content = "# Director\n\n" + ("x" * 4000)
        p = _make_howto(self.tmp, "no-marker.md", content)
        self.assertFalse(
            gate_is_library_filled(p),
            "File without any library marker should NOT count as library-filled",
        )

    def test_pending_stub_fails(self):
        """A PENDING stub with the marker fails (thin and has pending header)."""
        content = MARKER_FILLED + PENDING_STUB_BODY
        p = _make_howto(self.tmp, "pending.md", content)
        self.assertFalse(
            gate_is_library_filled(p),
            "PENDING stub with marker should NOT count as library-filled",
        )

    # — PASS cases (real canonical content) ———————————————————————————————

    def test_real_filled_content_passes(self):
        """A >= 3072-byte file with the 'Filled' marker MUST pass."""
        content = MARKER_FILLED + "# Director - how-to.md\n\n" + ("A" * 4000)
        self.assertGreaterEqual(len(content.encode()), LIBRARY_MIN_BYTES,
                                "Precondition: test content meets floor")
        p = _make_howto(self.tmp, "real-filled.md", content)
        self.assertTrue(
            gate_is_library_filled(p),
            "Substantive file with 'Filled' marker SHOULD count as library-filled",
        )

    def test_real_ws2_content_passes(self):
        """A >= 3072-byte file with the WS-2 marker MUST pass."""
        content = MARKER_WS2 + "# Director - how-to.md\n\n" + ("B" * 4000)
        self.assertGreaterEqual(len(content.encode()), LIBRARY_MIN_BYTES)
        p = _make_howto(self.tmp, "real-ws2.md", content)
        self.assertTrue(
            gate_is_library_filled(p),
            "Substantive file with WS-2 marker SHOULD count as library-filled",
        )

    def test_exactly_at_floor_passes(self):
        """A file exactly at the 3072-byte floor MUST pass."""
        base = MARKER_FILLED
        pad_bytes = LIBRARY_MIN_BYTES - len(base.encode("utf-8"))
        content = base + ("C" * pad_bytes)
        self.assertEqual(len(content.encode("utf-8")), LIBRARY_MIN_BYTES)
        p = _make_howto(self.tmp, "exact-floor.md", content)
        self.assertTrue(
            gate_is_library_filled(p),
            "File at exactly 3072 bytes with marker SHOULD count as library-filled",
        )

    def test_one_byte_below_floor_fails(self):
        """A file one byte below the 3072-byte floor MUST fail even with marker."""
        base = MARKER_FILLED
        pad_bytes = LIBRARY_MIN_BYTES - len(base.encode("utf-8")) - 1
        content = base + ("D" * pad_bytes)
        self.assertEqual(len(content.encode("utf-8")), LIBRARY_MIN_BYTES - 1)
        p = _make_howto(self.tmp, "one-below-floor.md", content)
        self.assertFalse(
            gate_is_library_filled(p),
            "File one byte below floor with marker should NOT count as library-filled",
        )


# ---------------------------------------------------------------------------
# BUG 1 TESTS — fill-script marker stamp guard
# ---------------------------------------------------------------------------

class TestFillScriptMarkerGuard(unittest.TestCase):
    """The fill scripts must refuse to stamp the marker on thin output."""

    def test_thin_output_not_stamped(self):
        """fill_guard_would_stamp returns False for thin content."""
        content = "# Director\n\nThin stub.\n"
        self.assertFalse(
            fill_guard_would_stamp(content),
            "Fill script should refuse to stamp marker on thin content",
        )

    def test_substantive_output_is_stamped(self):
        """fill_guard_would_stamp returns True for substantive content."""
        content = "# Director\n\n" + ("X" * 5000)
        self.assertTrue(
            fill_guard_would_stamp(content),
            "Fill script should stamp marker on substantive content",
        )

    def test_exactly_at_floor_is_stamped(self):
        """fill_guard_would_stamp returns True at exactly the floor."""
        content = "X" * LIBRARY_MIN_BYTES
        self.assertTrue(fill_guard_would_stamp(content))

    def test_one_below_floor_not_stamped(self):
        """fill_guard_would_stamp returns False one byte below floor."""
        content = "X" * (LIBRARY_MIN_BYTES - 1)
        self.assertFalse(fill_guard_would_stamp(content))


# ---------------------------------------------------------------------------
# BUG 2 TESTS — department-floor.py sys.path resolver order
# ---------------------------------------------------------------------------

class TestDepartmentFloorSysPathOrder(unittest.TestCase):
    """
    Bug 2: lib/ must win over shared-utils/ in sys.path so the correct
    detect_platform is loaded.

    We cannot import department-floor.py at module level (it has module-level
    side effects that scan the real filesystem).  Instead we inspect the
    source text to assert the fix is in place and that the path order is
    correct (lib last = first in sys.path after the loop).
    """

    def setUp(self):
        self.src = (_SCRIPTS / "department-floor.py").read_text(encoding="utf-8")

    def test_lib_inserted_last_in_loop(self):
        """
        The sys.path.insert loop must insert lib/ LAST so it ends at position 0.
        Pattern: shared-utils appears before lib/ in the tuple literal.
        """
        # Find the for-loop tuple inside resolve_departments_dir
        match = re.search(
            r"for\s+libp\s+in\s+\(([^)]+)\)",
            self.src,
        )
        self.assertIsNotNone(match, "Could not find the sys.path insert loop tuple")
        tuple_body = match.group(1)
        shared_pos = tuple_body.find("shared-utils")
        lib_pos    = tuple_body.rfind('"lib"')  # last occurrence = SKILL_DIR/"lib"
        if lib_pos == -1:
            lib_pos = tuple_body.rfind("/ \"lib\"")
        if lib_pos == -1:
            # try single-quotes or path concatenation
            lib_pos = tuple_body.rfind("'lib'")
        if lib_pos == -1:
            lib_pos = tuple_body.find("lib")
        self.assertGreater(
            lib_pos, shared_pos,
            "lib/ must appear AFTER shared-utils in the loop tuple "
            "(last insert = position 0 in sys.path = highest priority)",
        )

    def test_comment_documents_fix(self):
        """The BUG 2 FIX comment must be present in resolve_departments_dir."""
        self.assertIn(
            "BUG 2 FIX",
            self.src,
            "resolve_departments_dir must contain 'BUG 2 FIX' comment",
        )

    def test_lib_is_last_tuple_element(self):
        """
        A stricter check: the final element of the tuple must reference 'lib'.
        """
        match = re.search(
            r"for\s+libp\s+in\s+\(([^)]+)\)\s*:",
            self.src,
        )
        self.assertIsNotNone(match, "Could not find the sys.path insert loop")
        tuple_body = match.group(1)
        # Split on comma, strip whitespace
        elements = [e.strip() for e in tuple_body.split(",") if e.strip()]
        last = elements[-1]
        self.assertIn(
            "lib",
            last,
            f"The last element of the sys.path insert tuple must be lib/; got: {last!r}",
        )


# ---------------------------------------------------------------------------
# BUG 1 REGRESSION — verify the actual source files contain the fix
# ---------------------------------------------------------------------------

class TestSourceFilesContainFix(unittest.TestCase):
    """Grep the actual scripts to confirm the fix text is present."""

    def _read(self, rel_path: str) -> str:
        return (_SCRIPTS / rel_path).read_text(encoding="utf-8")

    def test_qc_completeness_has_size_check(self):
        src = self._read("qc-completeness.sh")
        self.assertIn(
            "LIBRARY_MIN_BYTES",
            src,
            "qc-completeness.sh must define LIBRARY_MIN_BYTES",
        )
        self.assertIn(
            "howto_size >= LIBRARY_MIN_BYTES",
            src,
            "qc-completeness.sh must check howto_size >= LIBRARY_MIN_BYTES",
        )

    def test_qc_completeness_marker_matches_both_formats(self):
        src = self._read("qc-completeness.sh")
        self.assertIn(
            "WS-2: instantiated",
            src,
            "qc-completeness.sh LIBRARY_MARKER must match the WS-2 header format",
        )

    def test_build_workforce_has_fill_guard(self):
        src = self._read("build-workforce.py")
        self.assertIn(
            "_LIBRARY_FILL_MIN_BYTES",
            src,
            "build-workforce.py must define _LIBRARY_FILL_MIN_BYTES",
        )
        self.assertIn(
            "Returning None so caller uses",
            src,
            "build-workforce.py must document the None-return path",
        )

    def test_create_role_workspaces_has_fill_guard(self):
        src = self._read("create_role_workspaces.py")
        self.assertIn(
            "LIBRARY_FILL_MIN_BYTES",
            src,
            "create_role_workspaces.py must define LIBRARY_FILL_MIN_BYTES",
        )
        self.assertIn(
            "treating as NO MATCH",
            src,
            "create_role_workspaces.py must log the rejection when content is thin",
        )

    # The client roster is EXTERNALIZED to an operator-local, gitignored file so
    # no real client name is hardcoded in this test. Load order:
    #   $OPENCLAW_CLIENT_ROSTER  →  ~/.openclaw/client-roster.txt
    # Template (placeholders only, tracked): scripts/client-roster.example.txt.
    _SCANNED_RELS = ("qc-completeness.sh", "build-workforce.py",
                     "create_role_workspaces.py", "department-floor.py")
    # Obviously-fake placeholders from the roster template. A hit means the
    # template leaked into real source — always checked so this never fails open.
    _PLACEHOLDER_NAMES = ("exampleclientalpha", "exampleclientbeta",
                          "placeholderco", "testclient sentinel")

    @staticmethod
    def _roster_path() -> "Path | None":
        env = os.environ.get("OPENCLAW_CLIENT_ROSTER")
        if env:
            return Path(env)
        home = os.environ.get("HOME") or os.path.expanduser("~")
        return Path(home) / ".openclaw" / "client-roster.txt"

    @classmethod
    def _load_forbidden_names(cls):
        """Return a lowercased list of roster name-tokens, or None if absent.

        Each roster line is an ERE pattern; for this substring check we strip the
        \\b word-boundary anchors and lowercase. Blank/comment lines are ignored.
        """
        p = cls._roster_path()
        if p is None or not p.is_file():
            return None
        names = []
        for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            names.append(line.replace(r"\b", "").lower())
        return names or None

    def test_no_placeholder_names_in_changed_files(self):
        """Never-fail-open: the roster-template placeholders must not appear in
        any scanned source file, regardless of whether the real roster exists."""
        for rel in self._SCANNED_RELS:
            src = self._read(rel).lower()
            for name in self._PLACEHOLDER_NAMES:
                self.assertNotIn(
                    name, src,
                    f"{rel} must not contain roster-template placeholder '{name}'",
                )

    def test_no_client_names_in_changed_files(self):
        """Fleet-wide policy: no real client names in repo files. Uses the
        externalized roster; skips (never silently passes) when it is absent."""
        forbidden = self._load_forbidden_names()
        if not forbidden:
            sys.stderr.write(
                "WARNING: client-name roster not found (looked in "
                "$OPENCLAW_CLIENT_ROSTER, then ~/.openclaw/client-roster.txt); "
                "SKIPPING the roster-specific client-name check. The placeholder "
                "leak check still ran. See scripts/client-roster.example.txt.\n"
            )
            self.skipTest("client-name roster not present; see "
                          "scripts/client-roster.example.txt")
        for rel in self._SCANNED_RELS:
            src = self._read(rel).lower()
            for name in forbidden:
                self.assertNotIn(
                    name, src,
                    f"{rel} must not contain client name '{name}'",
                )


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    unittest.main(verbosity=2)
