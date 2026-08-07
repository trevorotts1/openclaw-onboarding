"""FIX-6 (T-07, R10) — fail-fast on kie.ai auth errors.

A 401/403 is a PERMANENT failure: the identical request can never succeed, so
backoff-resubmitting it is a guaranteed token furnace (the observed 164x
"backing off" 401 tailspin in the E2E run). Two things must be true:

  1. `_http_json` classifies HTTP 401/403 as `AuthError` (a PERMANENT-error class),
     never the generic `RuntimeError` the transient retry path catches.
  2. `render_slide` re-raises `AuthError` IMMEDIATELY — zero `time.sleep`,
     zero backoff re-submits — so the slide fails fast (< 2s).

Controls (so a negative verdict is proven against a working instrument):
  * a 429 still raises `RateLimited` (transient, retried — unchanged behaviour);
  * a non-auth HTTP error (e.g. 500) still raises `RuntimeError` and the retry
    loop still backoffs (transient path unchanged);
  * `_preflight_kie_auth` raises AuthError on a mocked 401 and passes on a good
    key (the one-shot auth proof converts a 401 storm into one clear block).

Standard library plus pytest and unittest.mock, no network, no real key.
"""
from __future__ import annotations

import io
import pathlib
import sys
import time
import urllib.error

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_deck as bd  # noqa: E402


def _http_error(code: int, url: str = "https://api.kie.ai/api/v1/jobs/createTask",
                body: bytes = b"{}") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, f"err {code}", {}, io.BytesIO(body))


def _valid_prompt() -> str:
    """A rich prompt that clears EVERY build_deck prompt gate. These are the
    module's own thresholds (structural blocks + 8-class negative block +
    spelling-lock + hex palette + 220 distinct words + 9,000-char floor), so the
    fixture is not a stub the gates would reject. FIX-6 is about the AUTH path,
    not prompt gating, so this fixture exists ONLY to get render_slide past its
    prompt preconditions untouched."""
    scaffold = (
        "[ARCHETYPE: executive webcast presenter in a modern boardroom]\n"
        "Typography: the headline is 40pt bold, the subhead is 24pt, the body is "
        "18pt. Brand palette HEX: #0B3D91 primary blue, #00A0DF accent, #F5F7FA "
        "background, #1A1A1A text, #FFB81C highlight.\n"
        "Scene: a modern boardroom with natural light, shallow depth of field, and "
        "a confident presenter addressing a camera. Composition keeps the speaker "
        "right-of-center with copy zones left. Render this exact string "
        "letter-for-letter: Growing your revenue with a predictable pipeline.\n"
        "Do not render text outside the specified zones. Do not crop the "
        "headline. Do not add watermarks.\n"
        "DO-NOT BLOCK (eight defect classes, paired):\n"
        "  - GARBLED/MISSPELLED TEXT: Do not render garbled or misspelled text; "
        "   every word must be spelled correctly, letter-for-letter.\n"
        "  - PLACEHOLDER/BASKET TOKENS: Do not render placeholder tokens, lorem "
        "   ipsum, or bracket stubs anywhere in the image.\n"
        "  - ANATOMICAL ARTIFACTS: Do not render extra fingers, warped hands, or "
        "   anatomical artifacts in any human figure.\n"
        "  - BACKGROUND vs TEXT: Do not let background clutter compete with or "
        "   occlude the headline or body copy.\n"
        "  - DEMOGRAPHIC/SKIN-TONE FIDELITY: render the spec'd presenter's "
        "   complexion and facial features faithfully, from the casting ledger.\n"
        "  - PHOTOREALISM: Do not stylize into illustration or flat vector.\n"
        "  - COLOR SHIFT: Do not oversaturate or shift the brand palette HEX "
        "   values.\n"
        "  - EXTRANEOUS ELEMENTS: Do not add logos, timestamps, or props not in "
        "   the spec.\n"
    )
    filler = (
        "The lighting stays consistent across the frame, the composition remains "
        "balanced, and the depth of field isolates the presenter from the "
        "background. The headline uses the primary blue, the accent shapes use "
        "the highlight yellow, and the body copy uses the dark text color on the "
        "light background for maximum readability in a webinar thumbnail. Every "
        "text element respects the typography hierarchy and the spelling-lock "
        "directive above.\n"
    )
    vocab = (
        "Elevating conversion, compounding quarterly retention, orchestrating "
        "cross-functional launch sequences, and articulating measurable outcomes "
        "for stakeholders, executives, prospects, and board members alike. "
        "Authentic testimonials, persuasive case studies, crisp value "
        "propositions, disciplined typography, deliberate whitespace, generous "
        "margins, coherent visual rhythm, complementary palettes, consistent "
        "iconography, legible captions, precise alignment, intuitive hierarchy, "
        "satisfying pacing, deliberate emphasis, restrained decoration, "
        "functional flourishes, clear navigation, durable design systems, "
        "accessible contrast, semantic color, honest data, explicit sources, "
        "concise summaries, vivid imagery, tactile texture, dimensional depth, "
        "optimistic framing, confident delivery, warm engagement, professional "
        "polish, thorough preparation, meticulous craftsmanship, collaborative "
        "iteration, decisive direction, empathetic listening, constructive "
        "feedback, graceful handling of ambiguity, resilient execution under "
        "deadlines, rigorous quality assurance, transparent reporting, "
        "accountable ownership, sustainable workflows, ethical persuasion, "
        "genuine storytelling, memorable moments, repeatable frameworks, "
        "scalable templates, flexible components, robust tooling, curated "
        "repertoires, and evergreen reference material assembled into an "
        "inspiring, actionable, and enduring presentation experience.\n"
    )
    # vocab adds hundreds of DISTINCT words to clear the AF-P-DENSITY floor (220);
    # filler*28 + vocab keeps the total between 9,000 and 18,000 chars.
    chunk = scaffold + filler * 28 + vocab
    assert len(chunk) >= bd.PROMPT_CHAR_FLOOR
    assert len(chunk) <= bd.PROMPT_CHAR_CEILING
    return chunk


def _make_run_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    """A run dir with a valid rich prompt for slide 1 and a clean checkpoint state."""
    run_dir = tmp_path / "run"
    prompts = run_dir / "working" / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    (prompts / "slide-01.txt").write_text(_valid_prompt())
    # No pending_tasks.json => render_slide's resume path is a clean no-op.
    return run_dir


def _slide() -> dict:
    return {"slide": 1, "scene": "boardroom", "layout": "hero", "logo": ""}


# ---------------------------------------------------------------------------
# 1 & 2 — _http_json raises AuthError on 401 (NOT RuntimeError), and on 403 too.
# ---------------------------------------------------------------------------
class TestHttpJsonAuthClassification:

    def test_401_raises_auth_error(self, monkeypatch):
        def fake_urlopen(req, timeout=None):
            raise _http_error(401, body=b'{"code":401,"msg":"Unauthorized"}')
        monkeypatch.setattr(bd.urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(bd.AuthError) as exc_info:
            bd._http_json("POST", bd.CREATE_URL, "deadbeef", body={})
        assert "401" in str(exc_info.value)
        assert "Permanent auth failure" in str(exc_info.value)

    def test_403_raises_auth_error(self, monkeypatch):
        def fake_urlopen(req, timeout=None):
            raise _http_error(403, body=b"forbidden")
        monkeypatch.setattr(bd.urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(bd.AuthError):
            bd._http_json("POST", bd.CREATE_URL, "deadbeef", body={})

    def test_429_raises_rate_limited_not_auth(self, monkeypatch):
        def fake_urlopen(req, timeout=None):
            raise _http_error(429)
        monkeypatch.setattr(bd.urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(bd.RateLimited):
            bd._http_json("POST", bd.CREATE_URL, "deadbeef", body={})

    def test_500_raises_runtime_error_not_auth(self, monkeypatch):
        def fake_urlopen(req, timeout=None):
            raise _http_error(500, body=b"oops")
        monkeypatch.setattr(bd.urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(RuntimeError) as exc_info:
            bd._http_json("POST", bd.CREATE_URL, "deadbeef", body={})
        assert "500" in str(exc_info.value)
        assert not isinstance(exc_info.value, bd.AuthError)


# ---------------------------------------------------------------------------
# 3 — render_slide fails fast on a 401: AuthError propagates immediately, zero
# time.sleep, zero re-submits, and the elapsed wall time is well under 2s.
# ---------------------------------------------------------------------------
class TestRenderSlideFailsFast:

    def test_401_fails_fast_with_zero_sleep(self, monkeypatch, tmp_path):
        run_dir = _make_run_dir(tmp_path)
        renders_dir = tmp_path / "renders"
        renders_dir.mkdir(parents=True, exist_ok=True)

        sleeps = []

        def fake_urlopen(req, timeout=None):
            raise _http_error(401, body=b'{"code":401}')

        def no_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr(bd.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setattr(bd.time, "sleep", no_sleep)

        started = time.monotonic()
        with pytest.raises(bd.AuthError):
            bd.render_slide(_slide(), "deadbeef", renders_dir, run_dir)
        elapsed = time.monotonic() - started

        # The core FIX-6 assertion: a 401 must NEVER trigger a backoff re-submit.
        assert sleeps == [], (
            f"render_slide must not call time.sleep on a 401 — it must fail fast. "
            f"saw {len(sleeps)} sleeps: {sleeps}")
        assert elapsed < 2.0, (
            f"render_slide must fail the slide in < 2s on a 401; took {elapsed:.3f}s")

    def test_401_propagates_before_any_resubmit_attempt(self, monkeypatch, tmp_path):
        """A 401 on attempt 1 must NOT be followed by attempts 2..N — the AuthError
        aborts the loop entirely, so submit_task is reached exactly once."""
        run_dir = _make_run_dir(tmp_path)
        renders_dir = tmp_path / "renders"
        renders_dir.mkdir(parents=True, exist_ok=True)

        submit_calls = {"n": 0}

        def fake_submit_task(prompt, api_key, logo_url=None):
            submit_calls["n"] += 1
            raise bd.AuthError("HTTP 401 createTask — permanent auth failure")

        monkeypatch.setattr(bd, "submit_task", fake_submit_task)
        monkeypatch.setattr(bd.time, "sleep", lambda s: None)

        with pytest.raises(bd.AuthError):
            bd.render_slide(_slide(), "deadbeef", renders_dir, run_dir)
        assert submit_calls["n"] == 1, (
            f"a 401 must abort render_slide after ONE submission, not retry; "
            f"saw {submit_calls['n']} submits")

    def test_transient_500_still_retries_with_backoff(self, monkeypatch, tmp_path):
        """CONTROL — the transient path is UNCHANGED by FIX-6: a non-auth error
        still backoffs and re-submits against SLIDE_MAX_ATTEMPTS."""
        run_dir = _make_run_dir(tmp_path)
        renders_dir = tmp_path / "renders"
        renders_dir.mkdir(parents=True, exist_ok=True)

        sleeps = []

        def fake_urlopen(req, timeout=None):
            raise _http_error(500, body=b"server error")

        def no_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr(bd.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setattr(bd.time, "sleep", no_sleep)

        with pytest.raises(RuntimeError) as exc_info:
            bd.render_slide(_slide(), "deadbeef", renders_dir, run_dir)
        assert not isinstance(exc_info.value, bd.AuthError)
        # A transient failure still retries: at least one backoff sleep happened.
        assert len(sleeps) >= 1, (
            f"a transient 500 must still backoff-re-submit; saw {len(sleeps)} sleeps")
        assert sleeps[0] == min(bd.SLIDE_BACKOFF_CAP_S,
                                bd.SLIDE_BACKOFF_BASE * (2 ** 0))


# ---------------------------------------------------------------------------
# 4 — _preflight_kie_auth: a mocked 401 raises AuthError (one clear block, no
# render), and a good key passes with the credit printed.
# ---------------------------------------------------------------------------
class TestPreflightAuth:

    def test_preflight_401_raises_auth_error(self, monkeypatch, capsys):
        def fake_balance(api_key):
            raise bd.AuthError("Kie credit endpoint returned HTTP 401")
        monkeypatch.setattr(bd, "_fetch_kie_balance", fake_balance)
        with pytest.raises(bd.AuthError):
            bd._preflight_kie_auth("deadbeef")
        out = capsys.readouterr().out
        assert "preflight passed" not in out

    def test_preflight_good_key_passes(self, monkeypatch, capsys):
        monkeypatch.setattr(bd, "_fetch_kie_balance", lambda k: 866.0)
        bd._preflight_kie_auth("good-key")  # must not raise
        out = capsys.readouterr().out
        assert "preflight passed" in out
        assert "866" in out

    def test_preflight_network_error_raises_runtime(self, monkeypatch):
        def fake_balance(api_key):
            raise RuntimeError("Kie credit endpoint unreachable")
        monkeypatch.setattr(bd, "_fetch_kie_balance", fake_balance)
        with pytest.raises(RuntimeError) as exc_info:
            bd._preflight_kie_auth("deadbeef")
        assert not isinstance(exc_info.value, bd.AuthError)
        assert "AF-KIE-AUTH" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 5 — AuthError is exported at module level (the FIX-6 contract: a distinct,
# importable permanent-error class) and is distinct from the transient classes.
# ---------------------------------------------------------------------------
class TestAuthErrorClass:

    def test_auth_error_is_distinct_permanent_class(self):
        assert issubclass(bd.AuthError, Exception)
        assert not issubclass(bd.AuthError, bd.RateLimited)
        assert not issubclass(bd.RateLimited, bd.AuthError)
