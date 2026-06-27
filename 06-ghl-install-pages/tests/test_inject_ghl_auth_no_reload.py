"""Goal-B defect tests — inject-ghl-auth.sh: no post-seed page reload.

The "DO NOT RELOAD" rule is documented in the script: a full page reload
re-runs the boot IIFE which calls firebase signOut() and wipes the seeded
record. The inject path MUST NEVER call `window.location.reload()`,
`location.reload()`, `navigate()` (full-page), or `AB ... navigate` after
the seed-and-activate sequence.

These tests are STATIC (grep-only). They verify the property by reading the
source file on disk — no shell subprocess, no agent-browser invocation.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path under test
# ---------------------------------------------------------------------------

_SCRIPT_PATH = (
    Path(__file__).parent.parent / "tools" / "inject-ghl-auth.sh"
)


def _script_text() -> str:
    assert _SCRIPT_PATH.exists(), f"Script not found: {_SCRIPT_PATH}"
    return _SCRIPT_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers — strip comments so assertions target executable code only
# ---------------------------------------------------------------------------

def _strip_comments(text: str) -> str:
    """Remove full-line bash comments (#…) and inline comments after code."""
    lines = []
    for line in text.splitlines():
        # Remove leading-whitespace + # comment lines
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        # Remove inline comments (heuristic: space + # not inside quotes).
        # This is a best-effort strip; will miss complex quoting but is
        # sufficient for the patterns we search for here.
        clean = re.sub(r"\s+#[^'\"]*$", "", line)
        lines.append(clean)
    return "\n".join(lines)


_CODE = _strip_comments(_script_text())
_FULL_TEXT = _script_text()   # raw (comments included) — used for positive checks


# ---------------------------------------------------------------------------
# TEST GROUP 1: No post-seed reload call in executable code
# ---------------------------------------------------------------------------

class TestNoPostSeedReload:
    """Executable code must not invoke any page-reload mechanism after seeding."""

    # Patterns that would cause a full-page reload / re-navigation.
    # NOTE: we match the `navigate` SUBCOMMAND, not the word "navigate" in prose.
    # The AB() wrapper invokes agent-browser subcommands: open, eval, wait, snapshot.
    # `navigate` as a bare subcommand (not inside a quoted string) would be a full
    # page load. We exclude lines whose entire non-comment content is a quoted echo
    # (prose documentation, not an executable call).
    _RELOAD_PATTERNS = [
        r"window\.location\.reload\s*\(",
        r"location\.reload\s*\(",
        r"document\.location\.reload\s*\(",
        # AB() navigate subcommand — full page navigation (matches `AB ... navigate`
        # but only when `navigate` is a bare word token, not inside double-quotes)
        r'^[^"]*\bAB\b[^"]*\bnavigate\b[^"]*$',
    ]

    @pytest.mark.parametrize("pattern", _RELOAD_PATTERNS)
    def test_no_reload_pattern_in_executable_code(self, pattern):
        """Pattern must not appear in non-comment script lines."""
        matches = re.findall(pattern, _CODE, re.IGNORECASE)
        assert not matches, (
            f"Forbidden pattern {pattern!r} found in executable code "
            f"of inject-ghl-auth.sh. Matches: {matches!r}\n"
            "Post-seed reload wipes the Firebase IndexedDB record (boot IIFE "
            "calls signOut()). Use $router.push() instead."
        )

    def test_no_location_reload_anywhere_in_code(self):
        """location.reload() must never appear in non-comment lines."""
        found = re.findall(r'\.reload\s*\(', _CODE, re.IGNORECASE)
        assert not found, (
            f".reload() found in executable code: {found!r}"
        )

    def test_inject_js_does_not_call_reload(self):
        """The JS injected into the browser via `eval` must not call reload."""
        # Extract JS blocks between heredoc markers
        js_blocks = re.findall(
            r"<<['\"]?(?:JS|AJS|EOF)['\"]?.*?\n(.*?)(?=^EOF$|^JS$|^AJS$)",
            _FULL_TEXT,
            re.DOTALL | re.MULTILINE,
        )
        for block in js_blocks:
            reload_calls = re.findall(
                r'\.reload\s*\(|window\.location\.reload|location\.reload',
                block,
                re.IGNORECASE,
            )
            assert not reload_calls, (
                f"JavaScript block in inject-ghl-auth.sh calls .reload(): "
                f"{reload_calls!r}\nBlock:\n{block[:400]}"
            )

    def test_activate_js_uses_router_push_not_navigate(self):
        """The activation JS must use $router.push (in-app) NOT a full navigate."""
        # The ACTIVATE_JS block must contain router.push.
        assert "router.push" in _FULL_TEXT, (
            "ACTIVATE_JS must use $router.push() for in-app navigation "
            "(not a full page navigate/reload)."
        )

    def test_no_full_page_navigate_after_seed(self):
        """AB ... open (full navigate) must not follow the inject eval calls."""
        # After the seed block (everything after the eval that writes __GHL_SEED__),
        # there must be no `AB --session ... open` call (which does a full navigate).
        # We check the post-seed region by splitting on the __GHL_SEED__ eval.
        parts = _CODE.split("__GHL_SEED__", maxsplit=1)
        if len(parts) < 2:
            # Fallback: just check there is no naked AB ... open after the seed lines.
            post_seed = _CODE
        else:
            post_seed = parts[1]

        # Allow the --pre-open AB open BEFORE the seed; reject any AB open AFTER.
        # The pre-open block is before __GHL_SEED__ injection, so post_seed is safe.
        forbidden = re.findall(r'AB\b.*\bopen\b', post_seed)
        assert not forbidden, (
            f"AB ... open (full page navigation) found after the seed injection. "
            f"Matches: {forbidden!r}. This would reload the page and wipe the "
            "seeded Firebase IndexedDB record."
        )


# ---------------------------------------------------------------------------
# TEST GROUP 2: Positive checks — correct post-seed pattern IS present
# ---------------------------------------------------------------------------

class TestCorrectActivationPattern:
    """The script must use in-app SPA routing, not page reload."""

    def test_store_dispatch_auth_get_present(self):
        """ACTIVATE_JS must dispatch auth/get to activate the seeded session."""
        assert "auth/get" in _FULL_TEXT, (
            "ACTIVATE_JS must call store.dispatch('auth/get') to read the "
            "seeded cookie and activate the session."
        )

    def test_router_push_present(self):
        """ACTIVATE_JS must call $router.push() for in-app navigation."""
        assert "router.push" in _FULL_TEXT, (
            "ACTIVATE_JS must use $router.push() — in-app navigation that "
            "does NOT trigger the boot IIFE."
        )

    def test_do_not_reload_comment_present(self):
        """The DO NOT RELOAD comment block must be present as documentation."""
        assert "DO NOT RELOAD" in _FULL_TEXT, (
            "The '# DO NOT RELOAD' guard comment is missing. "
            "This comment documents a critical correctness rule."
        )

    def test_never_reload_instruction_present(self):
        """The NEVER reload instruction must appear in the script."""
        assert "NEVER" in _FULL_TEXT and "reload" in _FULL_TEXT.lower(), (
            "The 'NEVER reload' instruction is missing from inject-ghl-auth.sh."
        )

    def test_next_hint_uses_snapshot_not_reload(self):
        """The NEXT hint printed at end must say 'snapshot' and 'do NOT reload'
        (instructs the caller to snapshot, then explicitly forbids reload)."""
        last_echo = ""
        for line in _FULL_TEXT.splitlines():
            stripped = line.strip()
            if stripped.startswith("echo") and "NEXT" in stripped:
                last_echo = stripped
        assert last_echo, "Expected a final 'echo NEXT:...' instruction line."
        assert "snapshot" in last_echo.lower(), (
            f"NEXT hint must mention 'snapshot'. Got: {last_echo!r}"
        )
        # The hint says "do NOT reload" — the word 'reload' appears but only in
        # a negative instruction ("do NOT reload"). Verify it is negated.
        if "reload" in last_echo.lower():
            assert "not reload" in last_echo.lower() or "do not reload" in last_echo.lower(), (
                f"NEXT hint mentions 'reload' but not in a prohibition context. "
                f"Got: {last_echo!r}"
            )


# ---------------------------------------------------------------------------
# TEST GROUP 3: P2-4 agent-browser version-pin guard (fail loud on drift)
# ---------------------------------------------------------------------------
class TestVersionPinGuard:
    """inject-ghl-auth.sh must fail loud when the agent-browser version drifts
    from the pin, BEFORE the seed, and must offer the documented override."""

    def test_pin_default_present(self):
        assert "GHL_AB_PINNED_VERSION" in _FULL_TEXT, (
            "version-pin guard missing GHL_AB_PINNED_VERSION."
        )
        assert "0.27.0" in _FULL_TEXT, "pinned agent-browser version 0.27.0 absent."

    def test_refuses_on_drift_with_exit_70(self):
        # The guard must REFUSE (non-zero) on drift, distinct from existing codes.
        assert re.search(r"REFUSE:.*version drift", _FULL_TEXT), (
            "guard must print a REFUSE message on version drift."
        )
        assert re.search(r"exit\s+70", _CODE), (
            "version-pin guard must exit 70 on drift (a code not reused elsewhere)."
        )

    def test_override_env_documented(self):
        assert "GHL_AB_ALLOW_VERSION_DRIFT" in _FULL_TEXT, (
            "operator override GHL_AB_ALLOW_VERSION_DRIFT must exist."
        )

    def test_guard_runs_before_seed(self):
        # The guard must appear before the __GHL_SEED__ staging (so a drifted
        # engine never even opens/seeds). Compare source positions.
        pin_pos = _FULL_TEXT.find("GHL_AB_PINNED_VERSION")
        seed_pos = _FULL_TEXT.find("window.__GHL_SEED__")
        assert pin_pos != -1 and seed_pos != -1
        assert pin_pos < seed_pos, (
            "version-pin guard must run BEFORE the seed injection."
        )

    def test_guard_does_not_open_browser(self):
        # The guard reads `--version` only; it must not `AB ... open` the browser.
        # Isolate the guard region and assert no open/navigate within it.
        start = _CODE.find("GHL_AB_PINNED_VERSION")
        # The guard block ends where the singleton-session wiring begins
        # (bm_assert_session). The legitimate --pre-open `AB ... open` happens
        # AFTER that, so it must fall OUTSIDE the guard region.
        end = _CODE.find("bm_assert_session", start)
        region = _CODE[start:end if end != -1 else len(_CODE)]
        assert "--version" in region, "guard must query agent-browser --version."
        assert not re.search(r"\bAB\b.*\bopen\b", region), (
            "version-pin guard must not open the browser."
        )
