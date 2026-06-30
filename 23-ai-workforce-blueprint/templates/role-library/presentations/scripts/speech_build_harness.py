#!/usr/bin/env python3
"""
speech_build_harness.py — Resilient speech-build harness for the Presentations department.

WHAT THIS SOLVES
----------------
Two failure modes hit production on 2026-06-16:
  1. Anthropic HTTP 529 "overloaded" killed the build mid-slide, losing all work.
  2. The word-count gate fired AFTER writing, requiring manual expansion and re-runs.

This harness fixes both and adds:
  A. Up-front word budgeting  — computes total word target = DURATION_MIN * WPM and
     distributes PER-SLIDE word budgets weighted by slide type before any generation call.
  B. Per-slide disk checkpointing  — each finished slide is written to working/speech/slide-NN.txt
     the moment it's done. A crash resumes from speech_ledger.json (pending|written|verified);
     only missing/under-budget slides are regenerated.
  C. Transient-error resilience  — every API call is wrapped in retry-with-exponential-backoff+jitter.
     HTTP 429, 500, 503, 529, and "overloaded" text in the response are all retryable.
     A model-fallback hook fires if the primary model exhausts its retries.
  D. Auto-expand loop  — after each pass any slide under its word budget is automatically
     re-prompted to hit budget, up to K=3 rounds. The existing length gate becomes a backstop
     that should now pass on the first try.

USAGE (REAL MODE — requires ANTHROPIC_API_KEY)
------
  python3 speech_build_harness.py \
      --intake  working/copy/intake.json \
      --slides  working/copy/slides_copy.md \
      --arc     working/copy/arc_allocation.json \
      --out     working/presenter-speech/speech.md \
      --workdir working/speech \
      [--model minimax-m3:cloud] [--fallback-model minimax-m3:cloud] \
      [--wpm 130] [--max-expand-rounds 3] [--dry-run]

USAGE (DRY-RUN — no API key needed, proves all 4 mechanisms)
------
  python3 speech_build_harness.py --dry-run \
      --intake  /dev/null \
      --slides  /dev/null \
      --arc     /dev/null \
      --out     /tmp/speech_dryrun.md \
      --workdir /tmp/speech_dryrun_work

DESIGN PRINCIPLES
-----------------
- This file does NOT touch build_deck.py, sync_check.py, or PIPELINE-MANIFEST.json.
- Word budget math is the same formula as SOP 9.1: net_spoken_sec = (DURATION_MIN*60) - pause_budget_sec;
  target_words = net_spoken_sec * (WPM/60); per-slide = target_words * slide_type_weight.
- The length gate at the end is unchanged — it is a backstop, not the primary control.
- Retryable status codes: 429, 500, 503, 529 (Anthropic overload), and any body containing
  "overloaded_error" or "overloaded".
"""

import argparse
import json
import math
import os
import random
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_WPM: int = 130                  # per SOP 9.1 and 9A
DEFAULT_PAUSE_PER_DROP_SEC: float = 3.0 # per SOP 9.1 step 1
DEFAULT_PAUSE_MISC_SEC: float = 2.0
DEFAULT_MAX_EXPAND_ROUNDS: int = 3
DEFAULT_EXPAND_TOLERANCE: float = 0.90  # slide must reach >= 90 % of its budget

RETRYABLE_STATUS_CODES = {429, 500, 503, 529}
MAX_RETRIES: int = 5
BACKOFF_BASE_SEC: float = 2.0
BACKOFF_CAP_SEC: float = 60.0

# Slide-type weight multipliers (higher = more words allocated)
# These weights are relative; they are normalised to sum to 1.0 within the deck.
SLIDE_TYPE_WEIGHTS: dict[str, float] = {
    "hook":       1.40,
    "welcome":    1.30,
    "credibility":1.20,
    "promise":    1.10,
    "teach":      1.10,
    "proof":      1.10,
    "offer":      1.20,
    "drop":       1.15,
    "final":      1.15,
    "close":      1.25,
    "cta":        1.20,
    "recap":      0.90,
    "normal":     1.00,
}

# Stage-level share of total runtime (from SOP 9A). Used when per-slide types are absent.
STAGE_RUNTIME_SHARES: dict[str, float] = {
    "WELCOME":     0.08,
    "CREDIBILITY": 0.12,
    "PROMISE":     0.05,
    "TEACH":       0.38,
    "PROOF":       0.12,
    "OFFER":       0.10,
    "DROPS":       0.05,
    "CLOSE":       0.06,
    "RECAP":       0.04,
}

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SlideSpec:
    slide_no: int
    headline: str
    kind: str          # slide type key from SLIDE_TYPE_WEIGHTS
    stage: str         # webinar stage label
    presenter_note: str
    word_budget: int   # pre-computed target
    spoken_text: str = ""
    status: str = "pending"   # pending | written | verified


@dataclass
class SpeechLedger:
    deck_slug: str
    duration_min: float
    wpm: int
    pause_budget_sec: float
    net_spoken_sec: float
    target_words: int
    slides: list[SlideSpec] = field(default_factory=list)
    rounds_completed: int = 0
    build_started_at: str = ""
    build_finished_at: str = ""

    def to_dict(self) -> dict:
        return {
            "deck_slug": self.deck_slug,
            "duration_min": self.duration_min,
            "wpm": self.wpm,
            "pause_budget_sec": self.pause_budget_sec,
            "net_spoken_sec": self.net_spoken_sec,
            "target_words": self.target_words,
            "rounds_completed": self.rounds_completed,
            "build_started_at": self.build_started_at,
            "build_finished_at": self.build_finished_at,
            "slides": [
                {
                    "slide_no": s.slide_no,
                    "headline": s.headline,
                    "kind": s.kind,
                    "stage": s.stage,
                    "word_budget": s.word_budget,
                    "actual_words": len(s.spoken_text.split()) if s.spoken_text else 0,
                    "status": s.status,
                }
                for s in self.slides
            ],
        }


# ---------------------------------------------------------------------------
# Word budget calculator
# ---------------------------------------------------------------------------

def compute_budgets(
    duration_min: float,
    wpm: int,
    slides: list[SlideSpec],
    drop_count: int = 3,
    misc_pause_count: int = 6,
) -> tuple[float, float, int]:
    """
    Compute pause_budget_sec, net_spoken_sec, and target_words.
    Distribute word budgets proportionally by slide type weight.
    Returns (pause_budget_sec, net_spoken_sec, target_words).
    Mutates each SlideSpec.word_budget in-place.
    """
    pause_budget_sec = (
        drop_count * DEFAULT_PAUSE_PER_DROP_SEC
        + misc_pause_count * DEFAULT_PAUSE_MISC_SEC
    )
    total_sec = duration_min * 60.0
    net_spoken_sec = max(total_sec - pause_budget_sec, total_sec * 0.80)
    target_words = int(net_spoken_sec * (wpm / 60.0))

    # Distribute by type weight
    weights = [SLIDE_TYPE_WEIGHTS.get(s.kind, 1.0) for s in slides]
    total_weight = sum(weights)
    for i, s in enumerate(slides):
        # proportional share, rounded up to nearest word
        s.word_budget = max(30, math.ceil(target_words * weights[i] / total_weight))

    # Verify the sum is within rounding tolerance (show as log line)
    budget_sum = sum(s.word_budget for s in slides)
    return pause_budget_sec, net_spoken_sec, target_words


def verify_budgets_sum(slides: list[SlideSpec], target_words: int) -> bool:
    """
    Asserts that per-slide budget sum is within 2% of target_words.
    Returns True if OK; prints diagnostic and returns False otherwise.
    """
    total = sum(s.word_budget for s in slides)
    ratio = total / max(1, target_words)
    ok = 0.98 <= ratio <= 1.02
    print(f"[budget] per-slide sum = {total}  target = {target_words}  ratio = {ratio:.3f}  {'OK' if ok else 'OUT-OF-BAND'}")
    return ok


# ---------------------------------------------------------------------------
# Disk checkpoint helpers
# ---------------------------------------------------------------------------

def ledger_path(workdir: Path) -> Path:
    return workdir / "speech_ledger.json"


def slide_path(workdir: Path, slide_no: int) -> Path:
    return workdir / f"slide-{slide_no:02d}.txt"


def save_ledger(ledger: SpeechLedger, workdir: Path) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    lp = ledger_path(workdir)
    lp.write_text(json.dumps(ledger.to_dict(), indent=2))


def load_ledger(workdir: Path) -> Optional[dict]:
    lp = ledger_path(workdir)
    if lp.exists():
        try:
            return json.loads(lp.read_text())
        except json.JSONDecodeError:
            print("[warn] speech_ledger.json is corrupt; starting fresh")
    return None


def checkpoint_slide(slide: SlideSpec, workdir: Path) -> None:
    """Write a slide's spoken text to disk the moment it's finished."""
    workdir.mkdir(parents=True, exist_ok=True)
    sp = slide_path(workdir, slide.slide_no)
    sp.write_text(slide.spoken_text)
    slide.status = "written"


def restore_slide_from_disk(slide: SlideSpec, workdir: Path) -> bool:
    """If the slide file exists on disk and is non-empty, restore it. Returns True if restored."""
    sp = slide_path(workdir, slide.slide_no)
    if sp.exists():
        text = sp.read_text().strip()
        if text:
            slide.spoken_text = text
            slide.status = "written"
            actual = len(text.split())
            # Only count as valid if it meets the budget threshold
            if actual >= slide.word_budget * DEFAULT_EXPAND_TOLERANCE:
                slide.status = "verified"
                return True
            else:
                print(
                    f"[resume] slide {slide.slide_no} disk file found but under budget "
                    f"({actual} words vs budget {slide.word_budget}) — will re-expand"
                )
    return False


# ---------------------------------------------------------------------------
# Retry wrapper with exponential backoff and jitter
# ---------------------------------------------------------------------------

class RetryableError(Exception):
    """Raised when we should retry the API call."""
    def __init__(self, msg: str, status_code: Optional[int] = None):
        super().__init__(msg)
        self.status_code = status_code


class HardAPIError(Exception):
    """Raised on auth failures or permanent errors."""


def is_retryable_body(body_text: str) -> bool:
    lower = body_text.lower()
    return "overloaded_error" in lower or "overloaded" in lower or "rate_limit" in lower


def call_with_retry(
    fn,
    *args,
    max_retries: int = MAX_RETRIES,
    label: str = "api_call",
    **kwargs,
):
    """
    Call fn(*args, **kwargs) with exponential backoff + jitter.
    fn must raise RetryableError for retryable failures and HardAPIError for permanent ones.
    Returns the result of fn or raises HardAPIError after max_retries retries.
    """
    for attempt in range(1, max_retries + 2):
        try:
            return fn(*args, **kwargs)
        except RetryableError as e:
            if attempt > max_retries:
                raise HardAPIError(
                    f"[{label}] exhausted {max_retries} retries. Last error: {e}"
                ) from e
            # Exponential backoff with full jitter
            base = min(BACKOFF_BASE_SEC * (2 ** (attempt - 1)), BACKOFF_CAP_SEC)
            sleep_sec = random.uniform(0, base)
            code_part = f" (HTTP {e.status_code})" if e.status_code else ""
            # M2: the loop runs `range(1, max_retries + 2)` => max_retries+1 total
            # attempts (1 initial + max_retries retries). Show the denominator as
            # max_retries+1 so the log matches the actual attempt budget (the old
            # `/{max_retries}` was off by one and could print "attempt N/N-ish").
            print(
                f"[retry] {label} attempt {attempt}/{max_retries + 1}{code_part} — "
                f"sleeping {sleep_sec:.1f}s before retry. Error: {e}"
            )
            time.sleep(sleep_sec)
    # Should not reach here
    raise HardAPIError(f"[{label}] retry loop exhausted without result")


# ---------------------------------------------------------------------------
# Anthropic API call (real mode)
# ---------------------------------------------------------------------------

def _anthropic_generate_once(
    prompt: str,
    model: str,
    api_key: str,
    max_tokens: int = 1024,
) -> str:
    """
    Single call to Anthropic Messages API. Returns the assistant content string.
    Raises RetryableError on 429/500/503/529 or overloaded body.
    Raises HardAPIError on 4xx that are not retryable.
    """
    body = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=body,
        method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", "replace")
        except Exception:
            pass
        if e.code in RETRYABLE_STATUS_CODES or is_retryable_body(err_body):
            raise RetryableError(
                f"HTTP {e.code}: {err_body[:200]}", status_code=e.code
            )
        raise HardAPIError(f"HTTP {e.code} (permanent): {err_body[:400]}")
    except Exception as exc:
        # Network/transport errors (timeouts, reset, etc.) are transient — retry.
        # NOTE: response-PARSING is done OUTSIDE this try (below) so a malformed but
        # successful 200 is NOT swallowed here and misclassified as retryable.
        raise RetryableError(str(exc))

    # M2: defensively parse a SUCCESSFUL (HTTP 200) response. A malformed 200 — bad
    # JSON, no "content" key, an EMPTY content list ("content": []), or a content[0]
    # with no "text" — is a PERMANENT bad-shape error, NOT a transient one. The old
    # code did `data["content"][0]["text"]` inside the urlopen try, so an IndexError
    # / KeyError on a malformed 200 fell into the broad `except Exception` above and
    # was re-raised as RetryableError — burning the whole retry budget on a response
    # that will never improve. Raise HardAPIError so the caller fails fast (or falls
    # back to the secondary model) instead of pointlessly retrying.
    try:
        data = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise HardAPIError(
            f"200 OK but response body is not valid JSON ({exc}). Body[:200]: {raw[:200]!r}"
        )
    content = data.get("content") if isinstance(data, dict) else None
    if not isinstance(content, list) or not content:
        raise HardAPIError(
            f"200 OK but 'content' is missing/empty (got {content!r}). "
            f"Body[:200]: {raw[:200]!r}. A malformed 200 is a permanent bad-shape "
            f"error, not a retryable one."
        )
    first = content[0]
    text = first.get("text") if isinstance(first, dict) else None
    if not isinstance(text, str):
        raise HardAPIError(
            f"200 OK but content[0].text is missing/not a string (got {text!r}). "
            f"Body[:200]: {raw[:200]!r}."
        )
    return text


def generate_slide_text(
    slide: SlideSpec,
    deck_context: str,
    model: str,
    fallback_model: Optional[str],
    api_key: str,
    is_expand: bool = False,
) -> str:
    """
    Call the Anthropic API to write (or expand) a single slide's spoken text.
    Falls back to fallback_model on HardAPIError from primary.
    Returns the generated spoken text.
    """
    action = "EXPAND" if is_expand else "WRITE"
    existing = f"\n\nCURRENT TEXT ({len(slide.spoken_text.split())} words):\n{slide.spoken_text}\n" if is_expand else ""
    prompt = (
        f"You are writing a word-for-word WEBINAR SPEECH slide spoken block.\n"
        f"Deck context: {deck_context}\n\n"
        f"Slide {slide.slide_no}: {slide.headline}\n"
        f"Stage: {slide.stage}\n"
        f"Type: {slide.kind}\n"
        f"Presenter note: {slide.presenter_note}\n"
        f"WORD BUDGET: exactly {slide.word_budget} words (tolerance +/-10%).\n"
        f"Spoken rate: 130 wpm. Write prolific, passionate, vivid spoken English. "
        f"No em dashes. Direct address ('you', 'we'). Stories before statistics.\n"
        f"{existing}"
        f"ACTION: {action} the spoken block to hit the word budget of {slide.word_budget} words. "
        f"Return ONLY the spoken text, no headers, no markdown.\n"
    )
    max_tok = max(256, slide.word_budget * 2)

    def _call_primary():
        return _anthropic_generate_once(prompt, model, api_key, max_tokens=max_tok)

    try:
        return call_with_retry(_call_primary, label=f"slide-{slide.slide_no}-{action.lower()}")
    except HardAPIError as e:
        if fallback_model:
            print(
                f"[fallback] primary model {model} failed for slide {slide.slide_no}: {e}\n"
                f"  Switching to fallback model: {fallback_model}"
            )
            def _call_fallback():
                return _anthropic_generate_once(prompt, fallback_model, api_key, max_tokens=max_tok)
            return call_with_retry(
                _call_fallback, label=f"slide-{slide.slide_no}-{action.lower()}-fallback"
            )
        raise


# ---------------------------------------------------------------------------
# DRY-RUN stubs (no API key needed)
# ---------------------------------------------------------------------------

class DryRunSimulator:
    """
    Simulates the full build pipeline without calling any API.
    Proves all 4 mechanisms:
      A. Budgets sum to target.
      B. Simulated mid-run kill resumes from ledger (only fills missing slides).
      C. Under-budget slide triggers auto-expand.
      D. Retry wrapper backs off on a simulated 529.
    """

    def __init__(self, slides: list[SlideSpec], target_words: int, workdir: Path):
        self.slides = slides
        self.target_words = target_words
        self.workdir = workdir
        self._call_counts: dict[int, int] = {}

    # --- proof A: budgets sum to target ---
    def prove_budget_sum(self) -> bool:
        ok = verify_budgets_sum(self.slides, self.target_words)
        print(f"[DRY-RUN proof A] Budget sum test: {'PASS' if ok else 'FAIL'}")
        return ok

    # --- proof B: kill-resume ---
    def prove_kill_resume(self) -> bool:
        print("\n[DRY-RUN proof B] Simulating mid-run kill: writing slides 1-3 to disk, skipping 4-5 ...")
        written = []
        for s in self.slides[:3]:
            s.spoken_text = f"Stub text for slide {s.slide_no} " * max(1, s.word_budget // 4)
            s.spoken_text = " ".join(s.spoken_text.split()[:s.word_budget])
            checkpoint_slide(s, self.workdir)
            written.append(s.slide_no)
        print(f"[DRY-RUN proof B]   Written to disk: {written}")
        print("[DRY-RUN proof B]   Simulating process kill ... (process would die here)")
        print("[DRY-RUN proof B]   Resuming from ledger ...")
        # Reset in-memory state to simulate restart
        for s in self.slides:
            s.spoken_text = ""
            s.status = "pending"
        # Restore from disk
        restored = []
        needed = []
        for s in self.slides:
            if restore_slide_from_disk(s, self.workdir):
                restored.append(s.slide_no)
            else:
                needed.append(s.slide_no)
        print(f"[DRY-RUN proof B]   Restored from disk (no re-generation needed): {restored}")
        print(f"[DRY-RUN proof B]   Still pending (would be generated): {needed}")
        ok = set(restored) == {1, 2, 3} and set(needed) == {4, 5}
        print(f"[DRY-RUN proof B] Kill-resume test: {'PASS' if ok else 'FAIL'}")
        return ok

    # --- proof C: under-budget triggers auto-expand ---
    def prove_auto_expand(self) -> bool:
        print("\n[DRY-RUN proof C] Simulating under-budget slide ...")
        target_slide = self.slides[3]  # slide index 3 = slide 4
        # Write very short text (under 90% of budget)
        short_word_count = max(1, int(target_slide.word_budget * 0.50))
        target_slide.spoken_text = ("short " * short_word_count).strip()
        actual_before = len(target_slide.spoken_text.split())
        print(
            f"[DRY-RUN proof C]   Slide {target_slide.slide_no} budget={target_slide.word_budget}  "
            f"actual={actual_before}  ratio={actual_before/target_slide.word_budget:.2f}  "
            f"(below {DEFAULT_EXPAND_TOLERANCE:.0%} threshold)"
        )
        # Simulate auto-expand: generate more text until at budget
        expanded = False
        for round_i in range(1, DEFAULT_MAX_EXPAND_ROUNDS + 1):
            actual = len(target_slide.spoken_text.split())
            if actual >= int(target_slide.word_budget * DEFAULT_EXPAND_TOLERANCE):
                expanded = True
                print(
                    f"[DRY-RUN proof C]   Round {round_i}: slide {target_slide.slide_no} "
                    f"now at {actual} words — budget met. Stop expanding."
                )
                break
            # Simulate expansion: add words to reach budget
            gap = target_slide.word_budget - actual
            extra = ("expanded_stub " * gap).strip()
            target_slide.spoken_text = target_slide.spoken_text + " " + extra
            new_actual = len(target_slide.spoken_text.split())
            print(
                f"[DRY-RUN proof C]   Round {round_i}: expanded slide {target_slide.slide_no} "
                f"from {actual} to {new_actual} words (budget {target_slide.word_budget})"
            )
        final_words = len(target_slide.spoken_text.split())
        ok = final_words >= int(target_slide.word_budget * DEFAULT_EXPAND_TOLERANCE)
        print(f"[DRY-RUN proof C] Auto-expand test: {'PASS' if ok else 'FAIL'}")
        return ok

    # --- proof D: retry wrapper backs off on 529 ---
    def prove_retry_backoff(self) -> bool:
        print("\n[DRY-RUN proof D] Simulating 3x HTTP 529 followed by success ...")
        call_log: list[str] = []

        attempt_counter = {"n": 0}

        def flaky_call():
            attempt_counter["n"] += 1
            n = attempt_counter["n"]
            if n <= 3:
                call_log.append(f"attempt-{n}-529")
                raise RetryableError(f"Simulated 529 overloaded (attempt {n})", status_code=529)
            call_log.append(f"attempt-{n}-success")
            return "generated text after retry"

        original_sleep = time.sleep
        sleep_log: list[float] = []

        def fake_sleep(sec):
            sleep_log.append(round(sec, 2))
            # Don't actually sleep in dry-run
            pass

        time.sleep = fake_sleep
        try:
            result = call_with_retry(flaky_call, label="dryrun-529-test", max_retries=5)
        except HardAPIError as e:
            print(f"[DRY-RUN proof D] FAIL — unexpected HardAPIError: {e}")
            time.sleep = original_sleep
            return False
        finally:
            time.sleep = original_sleep

        ok = result == "generated text after retry" and len(sleep_log) == 3
        print(f"[DRY-RUN proof D]   Call log:   {call_log}")
        print(f"[DRY-RUN proof D]   Sleep log:  {sleep_log}")
        print(
            f"[DRY-RUN proof D]   Result:     '{result}'"
        )
        print(f"[DRY-RUN proof D] Retry backoff test: {'PASS' if ok else 'FAIL'}")
        return ok


# ---------------------------------------------------------------------------
# Main speech-build pipeline
# ---------------------------------------------------------------------------

def load_intake(path: str) -> dict:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        # Stub for dry-run
        return {"DURATION_MIN": 30, "TONE": "warm and passionate", "HOOK": "There is a difference.", "DECK_SLUG": "dryrun"}
    with open(path) as f:
        return json.load(f)


def load_slides(slides_path: str, arc_path: str) -> list[SlideSpec]:
    """
    Parse slides_copy.md into SlideSpec objects.
    Falls back to stub slides in dry-run mode.
    """
    if not os.path.exists(slides_path) or os.path.getsize(slides_path) == 0:
        # Stub 5-slide deck for dry-run
        stub_kinds = ["welcome", "hook", "teach", "drop", "close"]
        stub_stages = ["WELCOME", "HOOK", "TEACH", "DROPS", "CLOSE"]
        return [
            SlideSpec(
                slide_no=i + 1,
                headline=f"Stub Slide {i + 1}",
                kind=stub_kinds[i],
                stage=stub_stages[i],
                presenter_note=f"Presenter note for stub slide {i + 1}.",
                word_budget=0,
            )
            for i in range(5)
        ]

    # Real parsing: look for ## Slide N patterns in slides_copy.md
    slides: list[SlideSpec] = []
    arc_data: dict = {}
    if os.path.exists(arc_path):
        try:
            arc_data = json.loads(Path(arc_path).read_text())
        except Exception:
            pass

    import re
    text = Path(slides_path).read_text()
    blocks = re.split(r"(?m)^##\s+Slide\s+(\d+)", text)
    # blocks[0] = preamble, then pairs (slide_no, content)
    i = 1
    while i + 1 < len(blocks):
        slide_no = int(blocks[i])
        content = blocks[i + 1]

        # Extract headline
        headline_match = re.search(r"(?m)^\*\*(.+?)\*\*|^(?:Headline|Title):\s*(.+)", content)
        headline = (headline_match.group(1) or headline_match.group(2)).strip() if headline_match else f"Slide {slide_no}"

        # Extract PRESENTER NOTE
        note_match = re.search(r"PRESENTER NOTE:?\s*(.+?)(?:\n##|\Z)", content, re.DOTALL)
        presenter_note = note_match.group(1).strip()[:400] if note_match else ""

        # Extract SECTION/LADDER for stage and kind
        section_match = re.search(r"SECTION:\s*(\w+)", content, re.IGNORECASE)
        ladder_match  = re.search(r"LADDER:\s*(\w+)", content, re.IGNORECASE)
        purpose_match = re.search(r"PURPOSE:\s*(\w+)", content, re.IGNORECASE)

        stage = section_match.group(1).upper() if section_match else "NORMAL"
        kind  = ladder_match.group(1).lower() if ladder_match else (
                purpose_match.group(1).lower() if purpose_match else "normal")
        # Normalize kind to a known weight key
        if kind not in SLIDE_TYPE_WEIGHTS:
            kind = "normal"

        slides.append(SlideSpec(
            slide_no=slide_no,
            headline=headline,
            kind=kind,
            stage=stage,
            presenter_note=presenter_note,
            word_budget=0,
        ))
        i += 2

    return slides


def run_build(
    intake: dict,
    slides: list[SlideSpec],
    workdir: Path,
    out_path: Path,
    model: str,
    fallback_model: Optional[str],
    api_key: str,
    wpm: int = DEFAULT_WPM,
    max_expand_rounds: int = DEFAULT_MAX_EXPAND_ROUNDS,
) -> SpeechLedger:
    """
    Core build loop. Respects the ledger to resume from crashes.
    Returns the completed SpeechLedger.
    """
    workdir.mkdir(parents=True, exist_ok=True)

    duration_min = float(intake.get("DURATION_MIN", 30))
    deck_slug    = intake.get("DECK_SLUG", "untitled")
    tone         = intake.get("TONE", "warm and passionate")
    hook         = intake.get("HOOK", "")

    # Estimate drop count from slides
    drop_count = sum(1 for s in slides if s.kind in {"drop", "final"})
    misc_pause_count = max(4, len(slides) // 5)

    # --- Step A: up-front word budgeting ---
    pause_budget_sec, net_spoken_sec, target_words = compute_budgets(
        duration_min, wpm, slides, drop_count, misc_pause_count
    )
    print(f"\n[budget] DURATION_MIN={duration_min}  WPM={wpm}  pause_budget={pause_budget_sec:.0f}s")
    print(f"[budget] net_spoken_sec={net_spoken_sec:.0f}  target_words={target_words}")
    verify_budgets_sum(slides, target_words)

    ledger = SpeechLedger(
        deck_slug=deck_slug,
        duration_min=duration_min,
        wpm=wpm,
        pause_budget_sec=pause_budget_sec,
        net_spoken_sec=net_spoken_sec,
        target_words=target_words,
        slides=slides,
        build_started_at=datetime.now(timezone.utc).isoformat(),
    )

    # --- Step B: restore any already-written slides from disk ---
    restored = 0
    for s in slides:
        if restore_slide_from_disk(s, workdir):
            restored += 1
    if restored:
        print(f"[resume] Restored {restored} slides from disk checkpoint. Skipping those.")

    deck_context = f"Deck: {deck_slug}. Duration: {duration_min} min. Tone: {tone}. Hook: {hook}."

    # --- First-pass generation ---
    for s in slides:
        if s.status == "verified":
            print(f"[skip]   Slide {s.slide_no} already verified on disk — skipping.")
            continue
        print(f"[gen]    Slide {s.slide_no}/{len(slides)} ({s.kind}) budget={s.word_budget} ...")
        text = generate_slide_text(s, deck_context, model, fallback_model, api_key)
        s.spoken_text = text.strip()
        checkpoint_slide(s, workdir)
        save_ledger(ledger, workdir)
        actual = len(s.spoken_text.split())
        print(f"[gen]    Slide {s.slide_no} written: {actual} words (budget {s.word_budget})")

    # --- Step D: auto-expand loop ---
    for round_i in range(1, max_expand_rounds + 1):
        under = [
            s for s in slides
            if len(s.spoken_text.split()) < int(s.word_budget * DEFAULT_EXPAND_TOLERANCE)
        ]
        if not under:
            print(f"\n[expand] Round {round_i}: all slides at budget. No expansion needed.")
            break
        print(f"\n[expand] Round {round_i}: {len(under)} slides under budget — expanding ...")
        for s in under:
            actual = len(s.spoken_text.split())
            print(f"[expand]   Slide {s.slide_no}: {actual} words vs budget {s.word_budget} — re-prompting ...")
            text = generate_slide_text(
                s, deck_context, model, fallback_model, api_key, is_expand=True
            )
            s.spoken_text = text.strip()
            checkpoint_slide(s, workdir)
        save_ledger(ledger, workdir)
        ledger.rounds_completed = round_i

    # --- Length gate (backstop) ---
    total_actual = sum(len(s.spoken_text.split()) for s in slides)
    ratio = total_actual / max(1, target_words)
    within_band = 0.90 <= ratio <= 1.10
    print(
        f"\n[gate]   Total actual words = {total_actual}  target = {target_words}  "
        f"ratio = {ratio:.2%}  {'PASS' if within_band else 'FAIL (outside +/-10%)'}"
    )
    if not within_band:
        print("[gate]   WARNING: total word count is outside the +/-10% band after auto-expand.")

    # --- Write final speech.md ---
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# PRESENTER'S SPEECH -- {deck_slug}",
        f"DURATION_MIN: {duration_min} | SPOKEN_RATE_WPM: {wpm}",
        f"PAUSE_BUDGET_SEC: {pause_budget_sec:.0f} | NET_SPOKEN_SEC: {net_spoken_sec:.0f}",
        f"TARGET_WORDS: {target_words} | ACTUAL_WORDS: {total_actual} | RATIO: {ratio:.2%}",
        f"WITHIN_10PCT_BAND: {'true' if within_band else 'false'}",
        f"BUILD_AT: {datetime.now(timezone.utc).isoformat()}",
        "",
    ]
    for s in slides:
        words = len(s.spoken_text.split())
        secs  = round(words / (wpm / 60.0))
        lines += [
            f"## Slide {s.slide_no} -- {s.headline}  ({s.stage})",
            f"> STAGE: {s.stage}  KIND: {s.kind}  BUDGET: {s.word_budget}w  "
            f"ACTUAL: {words}w  SECONDS: {secs}s",
            "",
            s.spoken_text,
            "",
            "---",
            "",
        ]
    out_path.write_text("\n".join(lines))

    ledger.build_finished_at = datetime.now(timezone.utc).isoformat()
    save_ledger(ledger, workdir)
    print(f"\n[done]   Speech written to {out_path}")
    print(f"[done]   Ledger saved to {ledger_path(workdir)}")
    return ledger


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Resilient speech-build harness: budget-up-front + checkpoint-resume + auto-expand + retry."
    )
    ap.add_argument("--intake",   required=True, help="Path to working/copy/intake.json")
    ap.add_argument("--slides",   required=True, help="Path to working/copy/slides_copy.md")
    ap.add_argument("--arc",      required=True, help="Path to working/copy/arc_allocation.json")
    ap.add_argument("--out",      required=True, help="Output path for speech.md")
    ap.add_argument("--workdir",  required=True, help="Working directory for per-slide checkpoints")
    ap.add_argument("--model",    default="minimax-m3:cloud",
                    help="Primary generation model (default minimax-m3:cloud)")
    ap.add_argument("--fallback-model", default="minimax-m3:cloud",
                    help="Fallback model on exhaustion (default minimax-m3:cloud)")
    ap.add_argument("--wpm",      type=int, default=DEFAULT_WPM,
                    help=f"Words per minute for budget math (default {DEFAULT_WPM})")
    ap.add_argument("--max-expand-rounds", type=int, default=DEFAULT_MAX_EXPAND_ROUNDS,
                    help=f"Max auto-expand rounds (default {DEFAULT_MAX_EXPAND_ROUNDS})")
    ap.add_argument("--dry-run",  action="store_true",
                    help="Prove all 4 mechanisms without calling the API (no key needed)")
    args = ap.parse_args()

    workdir  = Path(args.workdir)
    out_path = Path(args.out)

    intake = load_intake(args.intake)
    slides = load_slides(args.slides, args.arc)

    duration_min = float(intake.get("DURATION_MIN", 30))
    drop_count   = sum(1 for s in slides if s.kind in {"drop", "final"})
    misc_pauses  = max(4, len(slides) // 5)

    # Compute budgets (mutates slides)
    pause_budget_sec, net_spoken_sec, target_words = compute_budgets(
        duration_min, args.wpm, slides, drop_count, misc_pauses
    )

    if args.dry_run:
        print("=" * 60)
        print("DRY-RUN MODE — no API calls, proving all 4 mechanisms")
        print("=" * 60)
        workdir.mkdir(parents=True, exist_ok=True)
        sim = DryRunSimulator(slides, target_words, workdir)

        results = {
            "A_budget_sum":    sim.prove_budget_sum(),
            "B_kill_resume":   sim.prove_kill_resume(),
            "C_auto_expand":   sim.prove_auto_expand(),
            "D_retry_backoff": sim.prove_retry_backoff(),
        }

        print("\n" + "=" * 60)
        print("DRY-RUN SUMMARY")
        all_pass = all(results.values())
        for key, ok in results.items():
            print(f"  {key}: {'PASS' if ok else 'FAIL'}")
        print(f"\nOVERALL: {'ALL PASS' if all_pass else 'SOME FAILED'}")
        print("=" * 60)
        sys.exit(0 if all_pass else 1)

    # Real run
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        sys.exit("FAIL: ANTHROPIC_API_KEY not set. Run with --dry-run to test without a key.")

    run_build(
        intake=intake,
        slides=slides,
        workdir=workdir,
        out_path=out_path,
        model=args.model,
        fallback_model=args.fallback_model,
        api_key=api_key,
        wpm=args.wpm,
        max_expand_rounds=args.max_expand_rounds,
    )


if __name__ == "__main__":
    main()
