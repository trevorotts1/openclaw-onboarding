"""parallel_prompt_worker.py -- FIX 2: the missing parallel P4-PROMPT authoring worker.

SPEC: PRESENTATION-DEPT-FIX-SPEC.md, FIX 2 (binding worker contract). The serial
per-slide loop inside presentation_job/dispatcher.py (_dispatch_prompt_phase) stays
as the documented rollback path behind the PRESENTATION_PROMPT_PARALLEL flag (default
ON; =0 selects the serial loop). This module owns NO phase policy of its own: the
dispatcher P4-PROMPT branch remains the owner of slide selection and routing, and it
invokes this worker once per dispatch with a normalized prompt-wave-input.json.

Binding contract implemented here (verbatim from spec lines 27-35):

  * CLI: --input <abs prompt-wave-input.json> --output-dir <abs working/prompts>
    [--workers N] [--resume] [--result-file <abs path>]. --workers may lower, never
    raise, the measured limit. Default result file <run_dir>/working/checkpoints/
    prompt-worker-results.json. Invalid/missing absolute paths, unknown schema
    versions, or a worker request above measured capacity exit non-zero BEFORE any
    provider call.
  * Input schema (schema_version: 1): run_id, run_dir (abs), phase_id (== P4-PROMPT),
    routing{provider, model, mode, measured_capacity (positive int)},
    prompt_constraints{min_chars, max_chars, required_blocks (non-empty)}, slides
    (non-empty) with the exact per-slide field set; slide_id and ordinal unique;
    whole input rejected pre-dispatch on any validation failure.
  * Concurrency: multiprocessing spawn model, one slide task per process slot,
    default worker count min(measured_capacity, 8). Processes share no mutable
    output file; each child receives only its slide payload plus an immutable
    routing snapshot.
  * Per-slide result: {slide_id, ordinal, status, prompt_path, prompt_sha256,
    char_count, model_used, attempts, started_at, ended_at, duration_s,
    verify{passed, codes}, error_class, error_message, retryable}. Failed results
    null the artifact-only fields. Provider exceptions are sanitized; credentials
    and raw response headers never enter any result.
  * Retry: at most 3 attempts per slide; retry only timeouts, 429s, 5xxs, and
    verify_prompt failures; exponential backoff before attempts 2 and 3 (2s, then
    4s) plus bounded 0-500ms jitter. Auth/permission errors and invalid input are
    non-retryable (fail fast). Attempt-level telemetry rows carry NO secrets and
    NO full provider payloads.
  * Partial failure: successful slides are kept and never regenerated because a
    peer failed. After a wave each failed slide is re-dispatched under its own
    remaining attempt budget. A slide still failed after attempt 3 is reported
    precisely and P4-PROMPT fails only AFTER all other slides finished. Two
    consecutive FULL-WAVE failures (zero successful slides in two successive
    multi-slide dispatches) abort immediately with the complete sanitized report;
    no third full wave is launched.
  * Artifacts: prompts written atomically (same-directory temp + os.replace) to
    <run_dir>/working/prompts/slide-NN-prompt.txt (three digits for ordinals >=100),
    then SHA-256/read-back verified. The aggregate result is atomically written to
    the result file. An incomplete process may leave temp files but never a
    canonical prompt path. If the real deterministic gate already certifies a
    slide's on-disk prompt, that slide is skipped with zero provider spend (the
    serial loop's resume property).
  * No second prompt schema, no second verifier: per-slide verification reuses
    dispatcher._verify_single_prompt, which IS build_deck.check_prompt_qc_deterministic.

Transport seam (REQUIRED for proofs, no network in tests): the provider call is
injectable through the module attribute `provider_call` -- the single seam every
invocation goes through. The production default reuses the EXISTING DeepSeek-direct
authoring path dispatcher.py already uses today (dispatcher.compose_prompt +
dispatcher.deepseek_complete); credentials handling is never duplicated. In spawn
children the attribute resolves through _resolve_provider(), which honors the
PRESENTATION_PROMPT_PROVIDER_STUB env var (absolute path to a stub-spec JSON) so
spawn children stub deterministically; absent that env it calls the real
dispatcher path. Stub kinds are local-only mocks: "succeed" (generates a
gate-passing prompt from the slide payload itself), "fail_429", "fail_500",
"fail_timeout" (retryable), "fail_auth" (non-retryable), "fail_verify" /
"fail_verify_then_succeed" (verify_prompt failure path), "fail_empty", "fail_all".

Exit codes: 0 = every slide succeeded; 1 = one or more slides failed (result file
still written); 2 = usage/schema validation failure BEFORE any provider call.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import tempfile
import time
import multiprocessing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

SCHEMA_VERSION = 1
PHASE_ID = "P4-PROMPT"
DEFAULT_MAX_WORKERS = 8          # first safe operating default (spec: cap 8 even
                                 # when a provider advertises more; FIX 11 may pick
                                 # a different mode cap later)
RETRY_CAP = 3                    # attempts per slide, total, all rounds
BACKOFF_S = {2: 2.0, 3: 4.0}     # sleep BEFORE attempt N (spec: 2s then 4s)
JITTER_MAX_S = 0.5               # bounded 0-500ms jitter on every retry sleep
DEFAULT_MIN_CHARS = 9000
DEFAULT_MAX_CHARS = 18000

RESULT_FILENAME = "prompt-worker-results.json"
ATTEMPTS_LOG_SUFFIX = "-attempts.jsonl"
INPUT_RELNAME = "prompt-wave-input.json"


class WorkerUsageError(RuntimeError):
    """Pre-dispatch validation failure. Exit code 2, zero provider spend."""


def _now_iso() -> str:
    # Same shape as presentation_job.state.utcnow (kept dependency-free so the
    # spawn child import stays light and never touches the engine state store).
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Same-directory temp file + os.replace. A crash may leave the temp file,
    never a torn canonical file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.partial-", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001 -- cleanup is best-effort
            pass
        raise


def _atomic_write_json(path: Path, obj: Any) -> None:
    _atomic_write_bytes(path, (json.dumps(obj, ensure_ascii=False, indent=2,
                                         sort_keys=True) + "\n").encode("utf-8"))


def _append_attempt_log(log_path: Path, record: Dict[str, Any]) -> None:
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        pass  # telemetry never breaks the run (FIX 5 doctrine)


# ---------------------------------------------------------------------------
# Input validation -- whole-input reject BEFORE any dispatch (spec-mandated).
# ---------------------------------------------------------------------------
def validate_input(data: Any, source: str) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise WorkerUsageError(f"{source}: input must be a JSON object")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise WorkerUsageError(
            f"{source}: unsupported schema_version {data.get('schema_version')!r} "
            f"(this worker speaks version {SCHEMA_VERSION} only)")
    run_id = data.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise WorkerUsageError(f"{source}: run_id must be a non-empty string")
    run_dir_raw = data.get("run_dir")
    if not isinstance(run_dir_raw, str) or not run_dir_raw.strip():
        raise WorkerUsageError(f"{source}: run_dir must be a non-empty string")
    run_dir = Path(run_dir_raw).expanduser()
    if not run_dir.is_absolute():
        raise WorkerUsageError(
            f"{source}: run_dir must be an ABSOLUTE path (got {run_dir_raw!r})")
    if data.get("phase_id") != PHASE_ID:
        raise WorkerUsageError(
            f"{source}: phase_id must be {PHASE_ID!r} (got {data.get('phase_id')!r})")

    routing = data.get("routing")
    if not isinstance(routing, dict):
        raise WorkerUsageError(f"{source}: routing must be an object")
    for key in ("provider", "model", "mode"):
        if not isinstance(routing.get(key), str) or not routing[key].strip():
            raise WorkerUsageError(
                f"{source}: routing.{key} must be a non-empty string")
    cap = routing.get("measured_capacity")
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
        raise WorkerUsageError(
            f"{source}: routing.measured_capacity must be a positive integer "
            f"(got {cap!r})")

    pc = data.get("prompt_constraints")
    if not isinstance(pc, dict):
        raise WorkerUsageError(f"{source}: prompt_constraints must be an object")
    min_chars = pc.get("min_chars", DEFAULT_MIN_CHARS)
    max_chars = pc.get("max_chars", DEFAULT_MAX_CHARS)
    if isinstance(min_chars, bool) or not isinstance(min_chars, int) or min_chars < 1:
        raise WorkerUsageError(
            f"{source}: prompt_constraints.min_chars must be a positive integer")
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars < 1:
        raise WorkerUsageError(
            f"{source}: prompt_constraints.max_chars must be a positive integer")
    if max_chars <= min_chars:
        raise WorkerUsageError(
            f"{source}: prompt_constraints.max_chars ({max_chars}) must exceed "
            f"min_chars ({min_chars})")
    blocks = pc.get("required_blocks")
    if not isinstance(blocks, list) or not blocks or \
            not all(isinstance(b, str) and b.strip() for b in blocks):
        raise WorkerUsageError(
            f"{source}: prompt_constraints.required_blocks must be a non-empty "
            "array of non-empty strings")

    slides = data.get("slides")
    if not isinstance(slides, list) or not slides:
        raise WorkerUsageError(f"{source}: slides must be a non-empty array")
    seen_ids = set()
    seen_ordinals = set()
    for idx, slide in enumerate(slides):
        where = f"{source}: slides[{idx}]"
        if not isinstance(slide, dict):
            raise WorkerUsageError(f"{where}: each slide must be an object")
        slide_id = slide.get("slide_id")
        if not isinstance(slide_id, str) or not slide_id.strip():
            raise WorkerUsageError(f"{where}: slide_id must be a non-empty string")
        ordinal = slide.get("ordinal")
        if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 1:
            raise WorkerUsageError(
                f"{where}: ordinal must be an integer >= 1 (got {ordinal!r})")
        copy = slide.get("copy")
        if not isinstance(copy, list) or not all(isinstance(c, str) for c in copy):
            raise WorkerUsageError(f"{where}: copy must be an array of strings")
        if not isinstance(slide.get("archetype"), str):
            raise WorkerUsageError(f"{where}: archetype must be a string")
        anchors = slide.get("research_anchors")
        if not isinstance(anchors, list) or \
                not all(isinstance(a, str) for a in anchors):
            raise WorkerUsageError(
                f"{where}: research_anchors must be an array of strings")
        if not isinstance(slide.get("design_tokens"), dict):
            raise WorkerUsageError(f"{where}: design_tokens must be an object")
        negs = slide.get("negative_requirements")
        if not isinstance(negs, list) or not all(isinstance(n, str) for n in negs):
            raise WorkerUsageError(
                f"{where}: negative_requirements must be an array of strings")
        if slide_id in seen_ids:
            raise WorkerUsageError(f"{where}: duplicate slide_id {slide_id!r}")
        if ordinal in seen_ordinals:
            raise WorkerUsageError(f"{where}: duplicate ordinal {ordinal}")
        seen_ids.add(slide_id)
        seen_ordinals.add(ordinal)

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "run_dir": run_dir,
        "phase_id": PHASE_ID,
        "routing": {
            "provider": routing["provider"],
            "model": routing["model"],
            "mode": routing["mode"],
            "measured_capacity": cap,
        },
        "prompt_constraints": {
            "min_chars": min_chars,
            "max_chars": max_chars,
            "required_blocks": list(blocks),
        },
        "slides": [dict(s) for s in slides],
    }


def load_input(path: Path) -> Dict[str, Any]:
    if not path.is_absolute():
        raise WorkerUsageError(
            f"--input must be an ABSOLUTE path (got {path!r})")
    if not path.is_file():
        raise WorkerUsageError(f"--input file does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkerUsageError(f"cannot read prompt-wave input {path}: {exc}")
    return validate_input(data, str(path))


# ---------------------------------------------------------------------------
# Transport seam. `provider_call` is the module attribute EVERY invocation goes
# through; tests may rebind it in-process, and spawn children resolve the same
# seam through _resolve_provider() (env stub spec or the real dispatcher path).
# ---------------------------------------------------------------------------
ProviderCall = Callable[[Dict[str, Any], Dict[str, Any], int, Path, str, int], str]

provider_call: Optional[ProviderCall] = None   # None -> resolve per-process


_STUB_ENV = "PRESENTATION_PROMPT_PROVIDER_STUB"


class _StubSpec:
    """Local-only provider stub resolved from a JSON spec file (no code exec)."""

    def __init__(self, spec_path: str):
        try:
            raw = json.loads(Path(spec_path).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 -- fail fast, non-retryable
            raise RuntimeError(f"provider stub {spec_path} unreadable: {exc}")
        if not isinstance(raw, dict):
            raise RuntimeError(f"provider stub {spec_path} must be a JSON object")
        self.default = raw.get("default", "succeed")
        by_ordinal = raw.get("by_ordinal") or {}
        if not isinstance(by_ordinal, dict):
            raise RuntimeError("stub by_ordinal must be an object")
        self.by_ordinal = {str(k): v for k, v in by_ordinal.items()}

    def _plan(self, slide: Dict[str, Any]):
        key = str(slide.get("ordinal"))
        return self.by_ordinal.get(key, self.default)

    def __call__(self, slide: Dict[str, Any], routing: Dict[str, Any], attempt: int,
                 run_dir: Path, owning_role: str, n_slides: int) -> str:
        plan = self._plan(slide)
        kind = plan
        if isinstance(plan, list):
            if attempt - 1 >= len(plan):
                kind = plan[-1]
            else:
                kind = plan[attempt - 1]
        if kind == "succeed":
            return _stub_rich_prompt(slide, routing, n_slides)
        if kind == "fail_429":
            raise RuntimeError("HTTP 429: stub rate limit")
        if kind == "fail_500":
            raise RuntimeError("HTTP 500: stub server error")
        if kind == "fail_timeout":
            raise RuntimeError("TimeoutError: stub timed out after 600s")
        if kind == "fail_auth":
            raise RuntimeError("HTTP 401 (non-transient): invalid credentials stub")
        if kind == "fail_verify":
            return "too-short stub"
        if kind == "fail_verify_then_succeed":
            if attempt < 2:
                return "too-short stub"
            return _stub_rich_prompt(slide, routing, n_slides)
        if kind == "fail_empty":
            return "   "
        if kind == "fail_all":
            raise RuntimeError("HTTP 503: stub permanent outage")
        raise RuntimeError(f"HTTP 400 (non-transient): unknown stub kind {kind!r}")


def _pad_lexicon(target_chars: int) -> str:
    """Deterministic nonce-word lexicon used ONLY by the local stub to reach the
    9,000-char floor with >=400 distinct words (the excellence target)."""
    letters = "abcdefghijklmnopqrstuvwxyz"
    vowels = "aeiou"
    words: List[str] = []
    idx = 0
    while sum(len(w) + 1 for w in words) < target_chars:
        words.append(
            letters[idx % 26] + letters[(idx // 26) % 26] +
            letters[(idx // 676) % 26] + vowels[(idx // 17576) % 5] + "ta")
        idx += 1
    return " ".join(words)


_RICH_SHEET = """CROP PLAN: full-bleed 1600x900 with a 4% edge bleed allowance on every side; the safe margin inset is 96px; text confined to the left third against a flat ground; the right two-thirds hold the graphic motif.
TYPE SYSTEM: display face set at 96pt with 2% tracking; kicker line 24pt uppercase; supporting line 32pt light; numerals tabular; baseline grid 8px; optical alignment overrides mechanical centers; hyphenation banned; rag controlled to 45 characters per line; widow lines forbidden; ligatures retained.
COLOR SCIENCE: primary #0B3D91 carries 62% of ink coverage; accent #E8B23A limited to 12%; ground #F7F5F0 holds the remaining 26%; contrast ratio of headline against ground measures 8.7:1; accent contrast 4.6:1; every swatch is sRGB with embedded profile; print conversion targets coated stock with 6% dot gain compensation.
GEOMETRY: baseline grid aligned to 12 columns; gutter width 24px; module size 128px square; the motif rotates in 6-degree increments; circles derive from Fibonacci ratios; the diagonal sweep crosses at 31 degrees; corners rounded 4px; strokes 2px uniform.
MATERIAL FEEL: matte laminate; ink density 3.1; grain amplitude 4%; paper tooth visible under raking light; no gloss highlights; printed blacks keep 88% density rather than pure black.
HIERARCHY: headline is first read; supporting line second; small caps kicker third; nothing else competes; eye path enters top-left, drops to the headline, sweeps right, exits bottom-right; dwell emphasis achieved with weight, never with boxes.
BRAND DISCIPLINE: the mark clears 48px of clear space on all sides; the reference mark never shrinks below 32px; the tagline lockup stays horizontal; brand curves keep their vector purity; no gradient mesh on the emblem.
RENDER DISCIPLINE: export at 300 DPI; embed fonts as outlines; no compression artifacts above 2%; banding controlled with 1.2% dither; chromatic subsampling disabled on text layers; kerning pairs preserved.

DO-NOT BLOCK:
- garbled/misspelled text: render every quoted text string exactly as written, letter-for-letter; never garbled or misspelled glyph runs.
- logo mutation: never redraw, recolor, restyle, or reinterpret the logo, monogram, tagline lockup, reference mark.
- placeholder/bracket tokens: no bracketed placeholder tokens, no square bracket, nothing owner to confirm, none marked pending, no insert, no build note.
- image narration/presenter/meta: no presenter line, no spoken-script, no stage direction, no telegraphing, no self-talk, never the word webinar; do not describe-the-picture inside the image.
- anatomical artifacts: no fused hand, no malformed digit, no extra limb, no distorted facial, no mismatched eye, no asymmetric eye, no distorted teeth, no over-smoothed skin, natural body proportion; keep every finger clean and anatom.
- background competing with text: never a busy, cluttered, high-detail background behind any text; the text zone stays clean; preserve legibility and negative space; the background must never compete.
- demographic/skin-tone fidelity: render demographic and skin tone faithfully; never lighten, ashen, desaturate, mono-cast; representation_mix stays as captured; deep skin renders deep.
- carried-forward universal baseline: no watermark, no emoji, no clipart, no default font, no calibri, no arial, no times new roman, no system default, no user-interface or ui artifact, no pure-black fills, no em dash.

Do not begin the composition with any decorative flourish; build note discipline applies throughout; the slide remains a still image only. This prompt is grounded because the palette, grid, and type scales are the client's captured brand system — believable, true to life, lived-in, not a luxury artifact, actual print production constraints apply."""


def _stub_rich_prompt(slide: Dict[str, Any], routing: Dict[str, Any],
                      n_slides: int) -> str:
    """Deterministic LOCAL stub completion that passes the real deterministic
    prompt gate (proven against build_deck.check_prompt_qc_deterministic)."""
    ordinal = slide["ordinal"]
    copy_lines = list(slide.get("copy") or [f"Slide {ordinal} headline"])
    copy_quoted = ", ".join(f'"{c}"' for c in copy_lines if c.strip()) or \
        '"standby"'
    lex = _pad_lexicon(6800)
    body = f"""[ARCHETYPE: A2 recognition layout for slide {ordinal} of {n_slides}]
LAYOUT: rule-of-thirds grid; headline occupies the left third; focal point anchored where the upper-third and left-third zone intersect; generous negative space reserved right of the fold; safe margin 96px all edges; composition balanced on a 12-column grid.

PEOPLE: no. Pure typographic beat plus abstract geometry; no people element omitted language applies.

PALETTE: brand primary #0B3D91, accent #E8B23A, ground #F7F5F0. Typography: headline 96pt, kickers 24pt, body 32pt, letter-spacing 2%. Texture: matte paper grain at 4% opacity, subtle ink-bleed on glyph edges, gradient wash 8 degrees.

VERBATIM COPY: the headline reads exactly {copy_quoted} — spelling-lock: this exact string renders letter-for-letter; the subhead renders every quoted text string exactly as written, with per-line spelling lock pinned to the client's captured type system.

DECK-CONSTANT SPEC SHEET (identical every slide; the variable is only the approved copy above):
ART DIRECTION LEXICON: {lex}
{_RICH_SHEET}"""
    return body


def _default_provider_call(slide: Dict[str, Any], routing: Dict[str, Any],
                           attempt: int, run_dir: Path, owning_role: str,
                           n_slides: int) -> str:
    """PRODUCTION transport: reuse the existing DeepSeek-direct authoring path the
    serial loop uses today (dispatcher.compose_prompt + deepseek_complete). Lazy
    import inside the child keeps the spawn import payload light; credentials are
    handled ONLY by dispatcher (_load_deepseek_key), never here, never printed."""
    import presentation_job.dispatcher as dispatcher  # spawn-safe: file import only
    ordinal = int(slide["ordinal"])
    slide_order = {
        "owning_role": owning_role,
        "phase_id": PHASE_ID,
        "produces_artifact": [f"working/prompts/{_prompt_filename(ordinal)}"],
        "_prompt_slide_ordinal": ordinal,
        "_prompt_slide_total": n_slides,
        "slide": dict(slide),
    }
    prior_reasons = None
    if attempt > 1:
        prior_reasons = [
            f"attempt {attempt - 1} failed verification; re-author slide {ordinal}"]
    system_prompt, user_prompt = dispatcher.compose_prompt(
        phase_id=PHASE_ID, owning_role=owning_role,
        dept_root=_dept_root_from(run_dir), run_dir=run_dir, order=slide_order,
        attempt=attempt, prior_reasons=prior_reasons)
    user_prompt = (
        f"=== THIS CALL AUTHORS EXACTLY ONE FILE: SLIDE {ordinal} OF {n_slides} ===\n"
        f"Find slide {ordinal}'s block in slides_copy.md above (the line reading "
        f"exactly `SLIDE {ordinal}`) and author ONLY its rich image-generation "
        f"prompt. Output ONLY that one slide's complete prompt body (9,000 to "
        f"18,000 characters) -- no slide-number header, no preamble, no other "
        f"slide's content.\n\n" + user_prompt)
    # FIX 7: routed completion. The worker owns NO transport: it asks the
    # dispatcher's dispatch_complete, which resolves the route from the
    # client resource profile (DeepSeek-direct stays the default/rollback
    # path) and returns (content, usage, route_dict).
    _content, _usage, _route = dispatcher.dispatch_complete(
        system_prompt, user_prompt, phase_id=PHASE_ID, run_dir=run_dir)
    return dispatcher._clean_payload(_content)


def _dept_root_from(run_dir: Path) -> Path:
    """Presentations dept root = the scripts dir's parent (same rule as
    dispatcher.resolve_dept_root). Derived from THIS module's location so the
    spawn child never needs an extra input field."""
    import presentation_job.dispatcher as dispatcher
    return dispatcher.resolve_dept_root(dispatcher._OWN_SCRIPTS_DIR)


def _resolve_provider() -> Callable:
    """Per-process seam resolution. Order: (1) module attribute bound in-process
    by tests (spawn inheritance not relied on), (2) env stub spec for spawn
    children, (3) production dispatcher path."""
    if provider_call is not None:
        return provider_call
    env_spec = os.environ.get(_STUB_ENV)
    if env_spec:
        return _StubSpec(env_spec)
    return _default_provider_call


# ---------------------------------------------------------------------------
# Error classification -- retry only timeouts/429/5xx/verify failures.
# ---------------------------------------------------------------------------
_RETRYABLE_CODES = ("timeout", "rate_limited", "server_error", "verify_failed")
_NONRETRYABLE_CODES = ("auth_error", "permission_error", "invalid_input",
                       "empty_response", "usage_error")


def _classify(exc: BaseException) -> Tuple[str, bool]:
    """Returns (error_class, retryable). Text matching is deliberately strict:
    only explicit status codes or timeout markers count; everything unknown is
    non-retryable so garbage never consumes the provider budget."""
    text = f"{type(exc).__name__}: {exc}"
    if isinstance(exc, WorkerUsageError):
        return "usage_error", False
    if re.search(r"\b40[13]\b|invalid[ _]credentials|authentication|unauthorized",
                 text, re.IGNORECASE):
        return "auth_error", False
    if re.search(r"\b403\b|permission", text, re.IGNORECASE):
        return "permission_error", False
    if "429" in text or "rate limit" in text.lower():
        return "rate_limited", True
    if re.search(r"\b5\d\d\b|server error|outage", text, re.IGNORECASE):
        return "server_error", True
    if "timeout" in text.lower() or "timed out" in text.lower() or \
            isinstance(exc, TimeoutError):
        return "timeout", True
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return "verify_failed", True
    return "provider_error", False


def _sanitize(msg: str) -> str:
    """No credentials, tokens, or headers ever reach a result row."""
    cleaned = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._-]+", r"\1<redacted>", msg)
    cleaned = re.sub(
        r"(?i)(api[-_ ]?key|authorization|sk-[a-z0-9]{8,})[=: ]+\S+",
        r"\1=<redacted>", cleaned)
    return cleaned[:400]


# ---------------------------------------------------------------------------
# Artifact naming + atomic write + read-back verify.
# ---------------------------------------------------------------------------
def _prompt_filename(ordinal: int) -> str:
    if ordinal >= 100:
        return f"slide-{ordinal:03d}-prompt.txt"  # 3 digits for 3+ digit ordinals
    return f"slide-{ordinal:02d}-prompt.txt"


def _prompt_path(run_dir: Path, ordinal: int) -> Path:
    return run_dir / "working" / "prompts" / _prompt_filename(ordinal)


# ---------------------------------------------------------------------------
# Per-slide verify through the EXISTING gate (no second verifier).
# ---------------------------------------------------------------------------
def _verify_prompt(slide: Dict[str, Any], prompt_text: str, run_dir: Path,
                   constraints: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Write the completion atomically to the canonical prompt path, then run the
    REAL per-slide gate (dispatcher._verify_single_prompt ->
    build_deck.check_prompt_qc_deterministic). No second verifier exists."""
    import presentation_job.dispatcher as dispatcher
    target = _prompt_path(run_dir, int(slide["ordinal"]))
    _atomic_write_bytes(target, prompt_text.encode("utf-8"))
    ok, reasons = dispatcher._verify_single_prompt(run_dir, int(slide["ordinal"]))
    return ok, list(reasons)


# ---------------------------------------------------------------------------
# One slide task: runs in a spawn child OR inline (n==1 / forkless probes).
# ---------------------------------------------------------------------------
def _execute_slide(task: Dict[str, Any]) -> Dict[str, Any]:
    slide = task["slide"]
    routing = task["routing"]
    run_dir = Path(task["run_dir"])
    constraints = task.get("prompt_constraints") or {}

    n_slides = task["n_slides"]
    owning_role = task["owning_role"]
    ordinal = int(slide["ordinal"])
    slide_id = str(slide["slide_id"])
    attempts_log = Path(task["attempts_log"])
    attempt_log_path = attempts_log.with_name(
        attempts_log.name + ATTEMPTS_LOG_SUFFIX) if attempts_log.name != \
        RESULT_FILENAME else attempts_log

    started = _now_iso()
    t0 = time.monotonic()
    base = {
        "slide_id": slide_id,
        "ordinal": ordinal,
        "status": "failed",
        "prompt_path": None,
        "prompt_sha256": None,
        "char_count": None,
        "model_used": routing.get("model"),
        "attempts": 0,
        "started_at": started,
        "ended_at": None,
        "duration_s": None,
        "verify": {"passed": False, "codes": []},
        "error_class": None,
        "error_message": None,
        "retryable": None,
        "_reasons": [],
    }
    attempt = 0
    pcall = _resolve_provider()
    while attempt < RETRY_CAP:
        attempt += 1
        try:
            text = pcall(slide, routing, attempt, run_dir, owning_role, n_slides)
        except Exception as exc:  # noqa: BLE001 -- classified below
            eclass, retryable = _classify(exc)
            base["attempts"] = attempt
            base["error_class"] = eclass
            base["error_message"] = _sanitize(str(exc))
            base["retryable"] = retryable
            base["_reasons"].append(f"attempt {attempt}: {eclass}")
            _append_attempt_log(attempt_log_path, {
                "slide_id": slide_id, "ordinal": ordinal, "attempt": attempt,
                "error_class": eclass, "retryable": retryable,
                "at": _now_iso()})
            if not retryable or attempt >= RETRY_CAP:
                break
            backoff = BACKOFF_S[attempt + 1] if (attempt + 1) in BACKOFF_S \
                else BACKOFF_S.get(attempt, 2.0)
            time.sleep(backoff + random.uniform(0.0, JITTER_MAX_S))
            continue
        if not text or not text.strip():
            base["attempts"] = attempt
            base["error_class"] = "empty_response"
            base["error_message"] = "provider returned empty payload"
            base["retryable"] = True
            base["_reasons"].append(f"attempt {attempt}: empty response")
            if attempt >= RETRY_CAP:
                break
            time.sleep((BACKOFF_S.get(attempt + 1, 2.0)) +
                       random.uniform(0.0, JITTER_MAX_S))
            continue
        ok, reasons = _verify_prompt(slide, text, run_dir, constraints)
        base["attempts"] = attempt
        if ok:
            base["_verified_on_attempt"] = attempt
            break
        base["_reasons"].append(
            f"attempt {attempt}: verify failed ({'; '.join(reasons) or 'unknown'})")
        _append_attempt_log(attempt_log_path, {
            "slide_id": slide_id, "ordinal": ordinal, "attempt": attempt,
            "error_class": "verify_failed", "retryable": True,
            "codes": reasons[:5], "at": _now_iso()})
        if attempt >= RETRY_CAP:
            base["error_class"] = "verify_failed"
            base["error_message"] = _sanitize(
                "did not pass deterministic prompt QC: " +
                "; ".join(reasons[:3]))
            base["retryable"] = True
            break
        time.sleep((BACKOFF_S.get(attempt + 1, 2.0)) +
                   random.uniform(0.0, JITTER_MAX_S))
    # finalize
    base["ended_at"] = _now_iso()
    base["duration_s"] = round(time.monotonic() - t0, 3)
    base["verify"] = {"passed": bool(base.get("verify", {}).get("passed")),
                      "codes": list(base.get("verify", {}).get("codes", []))}
    reasons_left = base.pop("_reasons", None) or []
    if not base.get("error_message") and reasons_left:
        base["error_message"] = _sanitize("; ".join(reasons_left[-2:]))
    return base


def _finalize_success(result: Dict[str, Any], run_dir: Path,
                      routing: Dict[str, Any]) -> Dict[str, Any]:
    """Fill in artifact-only fields after the on-disk prompt verified clean."""
    ordinal = int(result["ordinal"])
    target = _prompt_path(run_dir, ordinal)
    result["status"] = "succeeded"
    result["prompt_path"] = str(target)
    result["prompt_sha256"] = _sha256_file(target)
    result["char_count"] = len(target.read_text(encoding="utf-8"))
    result["model_used"] = routing.get("model")
    result["verify"] = {"passed": True, "codes": []}
    result["error_class"] = None
    result["error_message"] = None
    result["retryable"] = False
    return result


def _finalize_failure(result: Dict[str, Any]) -> Dict[str, Any]:
    """Spec: failed results are null artifact-only fields."""
    result["status"] = "failed"
    result["prompt_path"] = None
    result["prompt_sha256"] = None
    result["char_count"] = None
    result["verify"] = {"passed": False, "codes": []}
    if not result.get("error_class"):
        result["error_class"] = "provider_error"
    if result.get("error_message") is None and result.get("_reasons"):
        result["error_message"] = _sanitize("; ".join(result["_reasons"]))
    if result.get("retryable") is None:
        result["retryable"] = result.get("error_class") in _RETRYABLE_CODES
    return result


def _run_one(task: Dict[str, Any]) -> Dict[str, Any]:
    """One slide task end-to-end. Success is decided from DISK: the canonical
    prompt file must exist and clear the real per-slide gate at read-back -- an
    in-memory pass is never trusted over the on-disk artifact."""
    run_dir = Path(task["run_dir"])
    base = _execute_slide(task)
    verified = base.pop("_verified_on_attempt", None) is not None
    if not verified:
        # Re-derive success from disk (covers resumed/already-good slides too).
        target = _prompt_path(run_dir, int(task["slide"]["ordinal"]))
        if target.is_file():
            try:
                ok, _reasons = _verify_prompt_readback(run_dir, int(
                    task["slide"]["ordinal"]))
                verified = ok
            except Exception as exc:  # noqa: BLE001
                base["error_message"] = _sanitize(f"read-back failed: {exc}")
    if verified:
        base = _finalize_success(base, run_dir, task["routing"])
    else:
        base = _finalize_failure(base)
    base.pop("_reasons", None)
    return base


def _verify_prompt_readback(run_dir: Path, ordinal: int) -> Tuple[bool, List[str]]:
    import presentation_job.dispatcher as dispatcher
    return dispatcher._verify_single_prompt(run_dir, ordinal)


# ---------------------------------------------------------------------------
# Wave planning: failed slides get their own re-dispatch under remaining budget.
# ---------------------------------------------------------------------------
def _plan_wave(results: List[Dict[str, Any]], all_slides: List[Dict[str, Any]],
               consumed_attempts: Dict[int, int]) -> List[Dict[str, Any]]:
    failed_ordinals = {int(r["ordinal"]) for r in results
                       if r["status"] != "succeeded"}
    wave: List[Dict[str, Any]] = []
    by_ord = {int(s["ordinal"]): s for s in all_slides}
    for ordinal in sorted(failed_ordinals & set(by_ord)):
        slide = dict(by_ord[ordinal])
        slide["_consumed_attempts"] = consumed_attempts.get(ordinal, 0)
        wave.append(slide)
    return wave


def _workers_for(slides: int, capacity: int, requested: Optional[int]) -> int:
    effective = min(max(1, capacity), DEFAULT_MAX_WORKERS)
    if requested is not None:
        if requested < 1:
            raise WorkerUsageError("--workers must be >= 1")
        if requested > capacity:
            raise WorkerUsageError(
                f"--workers {requested} exceeds measured_capacity {capacity}; "
                "the flag may lower, never raise, the measured limit")
        effective = min(requested, effective)
    return max(1, min(effective, slides if slides >= 1 else 1)) \
        if slides >= 1 else 1


def _run_wave(wave_slides: List[Dict[str, Any]], cfg: Dict[str, Any],
              consumed: Dict[int, int]) -> List[Dict[str, Any]]:
    """One dispatch wave: up to N workers, one slide task per slot."""
    if not wave_slides:
        return []
    results: List[Dict[str, Any]] = []
    tasks: List[Dict[str, Any]] = []
    total_slides = cfg["n_slides"]
    for slide in wave_slides:
        tasks.append({
            "slide": slide,
            "routing": cfg["routing"],
            "run_dir": str(cfg["run_dir"]),
            "n_slides": total_slides,
            "owning_role": cfg["owning_role"],
            "attempts_log": str(cfg["attempts_log"]),
            "prompt_constraints": cfg["prompt_constraints"],
            "_consumed_attempts": slide.get("_consumed_attempts", 0),
        })
    procs = _workers_for(len(wave_slides), cfg["routing"]["measured_capacity"],
                         cfg["requested_workers"])
    ctx = multiprocessing.get_context("spawn")
    # Inline fallback avoids spawn for single-slide waves in constrained envs.
    if procs <= 1 or cfg.get("inline"):
        for task in tasks:
            results.append(_run_one(task))
        return results
    with ctx.Pool(processes=procs) as pool:
        results = pool.map(_run_one, tasks)
    return results


# ---------------------------------------------------------------------------
# Orchestration: retry waves, partial keep-good, two-zero-wave abort, resume.
# ---------------------------------------------------------------------------
def run_worker(data: Dict[str, Any], *, workers_requested: Optional[int] = None,
               resume: bool = False, result_file_override: Optional[str] = None,
               inline: bool = False) -> Tuple[int, Dict[str, Any]]:
    """Entry used by both the CLI and the dispatcher integration. Returns
    (exit_code, result_document). Input is validated here too -- the whole-input
    reject gate runs BEFORE any provider call regardless of entry point."""
    data = validate_input(data, "run_worker")
    run_dir: Path = Path(data["run_dir"])
    routing = data["routing"]
    slides_all: List[Dict[str, Any]] = data["slides"]
    constraints = data["prompt_constraints"]

    checkpoints = run_dir / "working" / "checkpoints"
    checkpoints.mkdir(parents=True, exist_ok=True)
    result_path = Path(result_file_override) if result_file_override else \
        checkpoints / RESULT_FILENAME
    result_path.parent.mkdir(parents=True, exist_ok=True)
    attempts_log = result_path.with_name(result_path.stem)
    prompts_dir = run_dir / "working" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    cfg = {
        "run_dir": run_dir,
        "routing": routing,
        "n_slides": len(slides_all),
        "owning_role": data.get("owning_role") or
        "Presentation Manager (Deck Author)",
        "attempts_log": attempts_log,
        "prompt_constraints": constraints,
        "requested_workers": workers_requested,
        "inline": inline,
    }

    # --- resume: keep already-certified slides out of the spend entirely.
    succeeded: Dict[int, Dict[str, Any]] = {}
    pending: List[Dict[str, Any]] = []
    existing_results: Dict[int, Dict[str, Any]] = {}
    if resume and result_path.is_file():
        try:
            prior = json.loads(result_path.read_text(encoding="utf-8"))
            for row in prior.get("slides", []):
                existing_results[int(row["ordinal"])] = row
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            existing_results = {}
    for slide in slides_all:
        ordinal = int(slide["ordinal"])
        prior = existing_results.get(ordinal)
        if resume and prior and prior.get("status") == "succeeded":
            target = _prompt_path(run_dir, ordinal)
            disk_ok = False
            if target.is_file() and prior.get("prompt_sha256"):
                disk_ok = _sha256_file(target) == prior["prompt_sha256"]
            if not disk_ok:
                try:
                    ok, _r = _verify_prompt_readback(run_dir, ordinal)
                    disk_ok = ok
                except Exception:  # noqa: BLE001
                    disk_ok = False
            if disk_ok:
                row = dict(prior)
                row["prompt_path"] = str(target)
                row["resumed"] = True
                succeeded[ordinal] = row
                continue
        # skip a slide whose on-disk prompt ALREADY passes the real gate,
        # regardless of the resume flag (same resume property as the serial loop)
        else:
            target_existing = _prompt_path(run_dir, ordinal)
            already = False
            if target_existing.is_file():
                try:
                    ok, _r = _verify_prompt_readback(run_dir, ordinal)
                    already = ok
                except Exception:  # noqa: BLE001
                    already = False
                if already:
                    succeeded[ordinal] = {
                        "slide_id": slide["slide_id"], "ordinal": ordinal,
                        "status": "succeeded", "prompt_path": str(target_existing),
                        "prompt_sha256": _sha256_file(target_existing),
                        "char_count": len(target_existing.read_text("utf-8")),
                        "model_used": routing.get("model"), "attempts": 0,
                        "started_at": _now_iso(), "ended_at": _now_iso(),
                        "duration_s": 0.0,
                        "verify": {"passed": True, "codes": []},
                        "error_class": None, "error_message": None,
                        "retryable": False, "resumed": True,
                    }
                    continue
        pending.append(slide)

    # --- waves
    wave_no = 0
    consumed: Dict[int, int] = {int(s["ordinal"]): 0 for s in slides_all}
    zero_success_waves = 0
    all_results: List[Dict[str, Any]] = list(succeeded.values())

    while pending:
        wave_no += 1
        # take only slides with remaining attempt budget from the pending set
        budget = [(s, RETRY_CAP - consumed[int(s["ordinal"])])
                  for s in pending]
        wave_slides = [s for s, left in budget if left > 0]
        if not wave_slides:
            break
        wave_results = _run_wave(wave_slides, cfg, consumed)
        # merge: succeeded replace pending; failed carry forward consumed count
        for row in wave_results:
            ordinal = int(row["ordinal"])
            consumed[ordinal] = consumed.get(ordinal, 0) + \
                int(row.get("attempts") or 0)
            if row["status"] == "succeeded":
                succeeded[ordinal] = row
            else:
                all_results = [r for r in all_results
                               if int(r["ordinal"]) != ordinal] + [row]
        all_results = [r for r in all_results
                       if int(r["ordinal"]) not in succeeded]
        # a NON-retryable failure (auth/permission/invalid input) is terminal for
        # that slide: no further wave re-spends it (retry only retryable classes).
        dead = {int(r["ordinal"]) for r in wave_results
                if r["status"] == "failed" and r.get("retryable") is False}
        pending = [s for s in pending
                   if int(s["ordinal"]) not in succeeded
                   and int(s["ordinal"]) not in dead]
        good = sum(1 for r in wave_results if r["status"] == "succeeded")
        if len(wave_slides) > 1 and good == 0:
            zero_success_waves += 1
            if zero_success_waves >= 2:
                # two consecutive FULL-wave failures (zero succeeded in two
                # successive multi-slide dispatches): abort, no third wave
                break
        else:
            zero_success_waves = 0

    # --- final result document
    failed_ordinals = [int(s["ordinal"]) for s in slides_all
                       if int(s["ordinal"]) not in succeeded]
    wave_failed = {int(r["ordinal"]): r for r in all_results
                   if r["status"] != "succeeded"}
    for s in slides_all:
        o = int(s["ordinal"])
        if o in failed_ordinals:
            row = wave_failed.get(o) or existing_results.get(o)
            if not isinstance(row, dict) or row.get("status") == "succeeded":
                row = {
                    "slide_id": s["slide_id"], "ordinal": o, "status": "failed",
                    "prompt_path": None, "prompt_sha256": None, "char_count": None,
                    "model_used": routing.get("model"),
                    "attempts": consumed.get(o, 0),
                    "started_at": _now_iso(), "ended_at": _now_iso(),
                    "duration_s": 0.0,
                    "verify": {"passed": False, "codes": []},
                    "error_class": "not_scheduled", "error_message":
                    "attempt budget exhausted before dispatch",
                    "retryable": True}
            _finalize_failure(row)
            row.pop("_reasons", None)
            all_results = [r for r in all_results if int(r["ordinal"]) != o] + [row]
    all_results = list(succeeded.values()) + [
        r for r in all_results if int(r["ordinal"]) not in succeeded]

    document = {
        "schema_version": SCHEMA_VERSION,
        "run_id": data["run_id"],
        "run_dir": str(run_dir),
        "phase_id": PHASE_ID,
        "routing": routing,
        "prompt_constraints": constraints,
        "total_slides": len(slides_all),
        "succeeded_count": len(succeeded),
        "failed_count": len(slides_all) - len(succeeded),
        "status": "succeeded" if not failed_ordinals else "partial",
        "zero_success_waves": zero_success_waves,
        "wave_count": wave_no,
        "slides": sorted(all_results, key=lambda r: int(r["ordinal"])),
        "started_at": min((r.get("started_at") or _now_iso()
                           for r in all_results), default=_now_iso()),
        "ended_at": _now_iso(),
        "worker_count": _workers_for(
            max(1, len(slides_all)),
            routing["measured_capacity"], workers_requested),
        "inline": bool(inline),
        "resume": bool(resume),
        "provider_seam": _seam_name(),
        # the canonical ordinal set the dispatcher's ingest must see
        "missing_ordinals": sorted(failed_ordinals),
    }
    _atomic_write_json(result_path, document)
    exit_code = 0 if not failed_ordinals else 1
    return exit_code, document


def _seam_name() -> str:
    if provider_call is not None:
        return getattr(provider_call, "__name__",
                       repr(provider_call))[:80]
    if os.environ.get(_STUB_ENV):
        return f"env-stub:{_STUB_ENV}"
    return "dispatcher.deepseek_complete"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="parallel_prompt_worker",
        description="FIX 2 parallel P4-PROMPT authoring worker (binding worker "
                    "contract; the serial dispatcher loop stays as rollback)")
    ap.add_argument("--input", required=True,
                    help="absolute path to prompt-wave-input.json")
    ap.add_argument("--output-dir", required=True,
                    help="absolute working/prompts directory")
    ap.add_argument("--workers", type=int, default=None,
                    help="may lower, never raise, measured_capacity")
    ap.add_argument("--resume", action="store_true",
                    help="reuse prior succeeded slides without re-spend")
    ap.add_argument("--result-file", default=None,
                    help="abs path (default <run_dir>/working/checkpoints/"
                         f"{RESULT_FILENAME})")
    return ap.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    try:
        input_path = Path(args.input).expanduser()
        if not input_path.is_absolute():
            raise WorkerUsageError(
                f"--input must be ABSOLUTE (got {args.input!r})")
        out_dir = Path(args.output_dir).expanduser()
        if not out_dir.is_absolute():
            raise WorkerUsageError(
                f"--output-dir must be ABSOLUTE (got {args.output_dir!r})")
        if args.result_file:
            rf = Path(args.result_file).expanduser()
            if not rf.is_absolute():
                raise WorkerUsageError(
                    f"--result-file must be ABSOLUTE (got {args.result_file!r})")
        else:
            rf = None
        data = load_input(input_path)
        # cross-check output-dir against run_dir-derived prompts dir
        expect = str(_prompt_path(data["run_dir"], 1).parent)
        if out_dir.resolve() != Path(expect).resolve():
            raise WorkerUsageError(
                f"--output-dir {out_dir} does not match run_dir prompts "
                f"directory {expect}")
        if data["run_dir"].parent.name not in ("runs", ".") and \
                not data["run_dir"].is_dir():
            raise WorkerUsageError(f"run_dir does not exist: {data['run_dir']}")
        exit_code, _doc = run_worker(
            data, workers_requested=args.workers, resume=args.resume,
            result_file_override=str(rf) if rf else None)
        return exit_code
    except WorkerUsageError as exc:
        print(f"parallel_prompt_worker: usage error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
