#!/usr/bin/env python3
# =============================================================================
# BOOK WRITER MINI-APP — U13 TRANSCRIPTION ENGINE (provider-neutral)
# -----------------------------------------------------------------------------
# mini-app/bridge/media_textractor.py
#
# Box-side extraction + transcription engine for the Book Writer mini-app
# (MASTER-PLAN section 4). The edge Worker is a DUMB RELAY: it stages media
# bytes to R2 and the job row to KV, but NEVER transcribes. This engine is the
# box-side worker that turns a staged source into the durable job record:
#
#   {intake_id, answer_id, channel, source_uri, source_sha256,
#    status: queued|processing|done|failed, text, transcript_json,
#    still_frame, error, created_at_utc, done_at_utc}
#
# PROVIDER-NEUTRAL, HARD NON-ANTHROPIC (MASTER-PLAN section 4 + section 9 U13):
#   * default transcription  -> `npx hyperframes transcribe <media> --model small`
#     (`small` is whisper multilingual auto-detect). NEVER `.en` models unless
#     the client STATES English — `.en` models silently TRANSLATE non-English
#     speech, destroying the original language.
#   * language rules         -> client states English -> small.en; client states
#     a non-English code    -> --model small --language <code>; unknown -> --model
#     small (auto-detect, no .en, no --language).
#   * client-provider ASR    -> optional per-client resolver fallback keyed by
#     name in capability-map.json["resolvers"] (e.g. Skill 30 Fish Audio or the
#     client's configured speech provider). The resolved model_id is RE-CHECKED
#     against /anthropic|claude/i and hard-fails if it matches.
#   * pdf/txt box-side       -> pdftotext primary, pandoc fallback for PDF;
#     .txt direct read. Browser pdf.js is the FIRST path (U09); this box-side
#     fallback only runs when pdf.js yields nothing.
#   * EXTRACT-NO-TEXT        -> a scanned/image-only PDF (pdftotext/pandoc yield
#     empty) is job `failed` with AF-BW-MA-EXTRACT-NO-TEXT — NOT done-with-empty.
#   * ffmpeg still frame     -> best-effort for video; a still failure never
#     fails the job, a transcript failure does.
#   * capability probe       -> reads capability-map.json (U12 mirror of
#     preflight.sh); a REQUIRED capability absent locally AND no client-provider
#     resolver -> hard-fail the job (AF-BW-MA-CAPABILITY, exit-7 pattern),
#     never silent skip.
#
# NEW AF CODES (MASTER-PLAN section 4, prefixed AF-BW-MA-*):
#   AF-BW-MA-EXTRACT-NO-TEXT  scanned/image-only PDF -> failed (never empty-done)
#   AF-BW-MA-ANTHROPIC        resolved transcription model id matches
#                             /anthropic|claude/i  (hard-fail)
#   AF-BW-MA-CAPABILITY       required capability absent locally AND no client
#                             resolver (hard-fail the job, exit-7 pattern)
#   AF-BW-MA-REJECT-FORMAT    source extension not on the allowlist
#   AF-BW-MA-REJECT-SIZE      source size over the per-channel cap
#
# EXIT CODES (prover convention via _bw_common):
#   0  PASS / self-test green
#   2  AUTOFAIL — an AF-BW-MA-* violation fired (fail-closed)
#   3  USAGE/IO — missing file / unreadable / bad arguments
#   7  capability hard-fail (required capability absent, no resolver)
#
# USAGE:
#   python3 media_textractor.py <job.json> [--capability-map cap.json]
#       [--client-resolver name] [--out OUT.json] [--selftest] [--json]
#
# The job.json input is a partial job record (the durable stage row from KV,
# {intake_id, answer_id, channel, source_uri, source_sha256}) plus an optional
# client_language hint and an optional capabilities read. The engine fills the
# rest: status, text, transcript_json, still_frame, error, done_at_utc.
# No Anthropic ids anywhere in this file by construction.
# =============================================================================
"""Provider-neutral, hard non-Anthropic media extraction/transcription engine."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# _bw_common lives in 53-book-writer/scripts/ — reach it from the bridge dir.
_HERE = Path(__file__).resolve().parent
_SCRIPTS = (_HERE.parent.parent / "scripts")
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import _bw_common as c  # noqa: E402

# ---- AF codes (MASTER-PLAN section 4) --------------------------------------
AF_EXTRACT_NO_TEXT = "AF-BW-MA-EXTRACT-NO-TEXT"
AF_ANTHROPIC = "AF-BW-MA-ANTHROPIC"
AF_CAPABILITY = "AF-BW-MA-CAPABILITY"
AF_REJECT_FORMAT = "AF-BW-MA-REJECT-FORMAT"
AF_REJECT_SIZE = "AF-BW-MA-REJECT-SIZE"

# ---- job model --------------------------------------------------------------
JOB_STATUS = ("queued", "processing", "done", "failed")

# A field counts as PRESENT for the intake gate ONLY when its job is done with
# non-empty text (or explicit N/A). queued/processing parks; failed surfaces
# retry. Never a silent blank (MASTER-PLAN section 4).
_JOB_FIELDS = (
    "intake_id", "answer_id", "channel", "source_uri", "source_sha256",
    "status", "text", "transcript_json", "still_frame", "error",
    "created_at_utc", "done_at_utc",
)

# ---- format / size allowlists (mirror U04 media-lib.js) ---------------------
ALLOWED_EXTENSIONS = {
    "audio": ["mp3", "m4a", "opus", "webm", "ogg", "wav"],
    "video": ["mp4", "webm", "mov", "m4v"],
    "pdf": ["pdf"],
    "txt": ["txt"],
}
SIZE_CAPS_BYTES = {
    "audio": 100 * 1024 * 1024,  # 100 MB (matches U04)
    "video": 500 * 1024 * 1024,  # 500 MB (matches U04)
    "pdf": 25 * 1024 * 1024,     # 25 MB (text only, browser-first)
    "txt": 1 * 1024 * 1024,
}
TEXT_CAPS = {
    "default": 50_000,   # 50k chars/field
    "long": 200_000,     # book_about + book_stories
}

# Explicitly NOT supported in v1 (MASTER-PLAN section 4): `.docx` — rejected
# with an offer to type or record instead.
UNSUPPORTED_EXTENSIONS = {"docx", "doc"}

# ---- regexes ----------------------------------------------------------------
# Anthropic / claude model-id family — the SAME expression the no-Anthropic
# prover (prove_bw_noanthropic.py) uses, kept in sync here for the resolved
# transcription model id re-check.
_ANTHROPIC_RE = re.compile(r"anthropic|claude", re.IGNORECASE)
# Control chars stripped from extracted text (C0 + DEL + C1, keep \n \t \r).
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]")
# Music-note tokens whisper emits on instrumental passages — not speech.
_MUSIC_NOTE_RE = re.compile(r"[♪♫♬♭♮♯�]+")
# Placeholder/template tokens never shipped.
_PLACEHOLDER_RE = re.compile(r"\{\{[^}]*\}\}|\$\(\s*['\"][^'\"]*['\"]\s*\)")

# ---- language rules ---------------------------------------------------------
# whisper model families. `.en` models TRANSLATE non-English speech into
# English instead of transcribing it — they silently destroy the original
# language. Rule (hyperframes-media skill, non-negotiable):
#   1. language known and non-English -> --model small --language <code>
#   2. language known and English     -> --model small.en
#   3. language unknown               -> --model small (auto-detect)
_WHISPER_MODEL_MULTILINGUAL = "small"
_WHISPER_MODEL_ENGLISH = "small.en"
_ENGLISH_TOKENS = {"en", "en-us", "en-gb", "english"}


def _now_utc() -> str:
    """ISO-8601 UTC timestamp (naive, deterministic for the job record)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# text cleaning (control chars stripped; the ONE normalization boundary)
# ---------------------------------------------------------------------------

def clean_text(raw: str, cap: int) -> str:
    """Strip control chars, trim, enforce the per-field char cap.

    Raises ValueError with AF-BW-MA-REJECT-SIZE when the cleaned text exceeds
    the cap (a length-checked text per MASTER-PLAN section 4).
    """
    cleaned = _CONTROL_CHAR_RE.sub("", raw or "").strip()
    if len(cleaned) > cap:
        raise ValueError(
            "%s: extracted text %d chars exceeds the %d-char cap"
            % (AF_REJECT_SIZE, len(cleaned), cap)
        )
    return cleaned


# ---------------------------------------------------------------------------
# capability probe (reads capability-map.json written by U12/preflight mirror)
# ---------------------------------------------------------------------------

_DEFAULT_CAPABILITY_MAP_CANDIDATES = (
    _HERE / "capability-map.json",
    _HERE.parent / "capability-map.json",
    _HERE.parent.parent / "capability-map.json",
)


def load_capability_map(path):
    """Read capability-map.json (U12 / preflight.sh mirror). A missing or
    unreadable map -> {} (capabilities unknown; the local hyperframes probe is
    still attempted so a healthy box is not blocked by a stale map)."""
    p = Path(path) if path else None
    if p is None or not p.exists():
        for cand in _DEFAULT_CAPABILITY_MAP_CANDIDATES:
            if cand.exists():
                p = cand
                break
    if p is None or not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _resolver_from_map(capability_map, client_resolver):
    """Return the per-client ASR resolver entry, or None.

    capability-map.json shape:
        { "transcribe": true|false,
          "resolvers": { "<resolver-name>": {provider, model_id, engine, argv} } }
    The resolver is the CLIENT's OWN configured speech provider (never an
    operator key). Returns None when the name is unknown or unconfigured.
    """
    if not client_resolver or not isinstance(capability_map, dict):
        return None
    resolvers = capability_map.get("resolvers")
    if not isinstance(resolvers, dict):
        return None
    entry = resolvers.get(client_resolver)
    return entry if isinstance(entry, dict) else None


# ---------------------------------------------------------------------------
# Anthropic re-check on the resolved transcription model id
# ---------------------------------------------------------------------------

def recheck_resolved_model(model_id, result: c.Result) -> bool:
    """AF-BW-MA-ANTHROPIC re-check on a RESOLVED transcription model id.

    Any model id matching /anthropic|claude/i hard-fails — the same rule the
    no-Anthropic prover applies to RUN-LEDGER model ids, now applied at the
    resolved transcription call. Returns True on violation (fail-closed).
    """
    if model_id and _ANTHROPIC_RE.search(str(model_id)):
        result.fail(AF_ANTHROPIC, "resolved transcription model id %r matches "
                   "/anthropic|claude/i (client boxes never run Anthropic)"
                   % model_id)
        return True
    return False


# ---------------------------------------------------------------------------
# ffmpeg still frame (video best-effort)
# ---------------------------------------------------------------------------

def extract_still_frame(video_path: Path, out_path: Path) -> str | None:
    """Best-effort ffmpeg still frame (`-ss 1 -frames:v 1`). Returns the output
    path on success, None on any failure. A still failure NEVER fails the job;
    a transcript failure does (MASTER-PLAN section 4)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    try:
        subprocess.run(
            [ffmpeg, "-ss", "1", "-y", "-i", str(video_path),
             "-frames:v", "1", str(out_path)],
            capture_output=True, timeout=60, check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None
    return str(out_path) if out_path.exists() and out_path.stat().st_size > 0 else None


# ---------------------------------------------------------------------------
# hyperframes transcribe (default, provider-neutral) + client-provider ASR
# ---------------------------------------------------------------------------

def build_transcribe_argv(media_path: str, language, engine=None,
                          extra_args=()) -> list:
    """Build the `npx hyperframes transcribe <media>` argv with the language
    rules enforced: NEVER `.en` models unless the client states English.

    language: None -> unknown -> --model small (auto-detect, no .en).
    language == "en"/"en-us"/"en-gb"/"english" -> --model small.en.
    anything else (e.g. "es", "ja") -> --model small --language <code>.
    """
    lang = (str(language).strip().lower() if language else "")
    argv = ["transcribe", media_path, "--model", _WHISPER_MODEL_MULTILINGUAL]
    if lang in _ENGLISH_TOKENS:
        argv = ["transcribe", media_path, "--model", _WHISPER_MODEL_ENGLISH]
    elif lang:
        argv = ["transcribe", media_path, "--model", _WHISPER_MODEL_MULTILINGUAL,
                "--language", lang]
    if engine:
        argv += ["--engine", engine]
    if extra_args:
        argv += list(extra_args)
    return argv


def _run_hyperframes_transcribe(media_path: Path, language, engine=None,
                                extra_args=(), timeout_sec: int = 1800) -> tuple:
    """Run `npx hyperframes transcribe`. Returns (transcript_json, text);
    (None, None) on any failure (non-zero exit, timeout, unparsable output)."""
    npx = shutil.which("npx")
    if not npx:
        return None, None
    argv = build_transcribe_argv(str(media_path), language, engine, extra_args)
    try:
        proc = subprocess.run([npx, "hyperframes"] + argv,
                              capture_output=True, timeout=timeout_sec)
    except (subprocess.TimeoutExpired, OSError):
        return None, None
    if proc.returncode != 0:
        return None, None

    # The CLI writes a transcript.json sidecar next to the input.
    for sc in (media_path.with_name("transcript.json"),
               media_path.with_suffix(".json")):
        if sc.exists():
            try:
                data = json.loads(sc.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            return data, join_transcript_text(data)
    # Robustness fallback: parse stdout JSON (--json word array) if present.
    stdout = (proc.stdout or b"").decode("utf-8", "replace").strip()
    if stdout:
        try:
            data = json.loads(stdout)
        except ValueError:
            return None, None
        if isinstance(data, (dict, list)):
            return data, join_transcript_text(data)
    return None, None


def join_transcript_text(transcript) -> str:
    """Join a hyperframes/whisper transcript into plain text.

    Accepts the flat word array [{"text","start","end"}, ...], a wrapper
    {segments:[...]} / {words:[...]} / {text:"..."}. Words joined with a single
    space; empty entries and lone music-note tokens are skipped.
    """
    words = None
    if isinstance(transcript, list):
        words = transcript
    elif isinstance(transcript, dict):
        if isinstance(transcript.get("segments"), list):
            words = transcript["segments"]
        elif isinstance(transcript.get("words"), list):
            words = transcript["words"]
        elif isinstance(transcript.get("text"), str):
            return transcript["text"].strip()
    if not words:
        return ""

    parts = []
    for w in words:
        if not isinstance(w, dict):
            continue
        t = w.get("text")
        if not isinstance(t, str):
            continue
        t = t.strip()
        if not t:
            continue
        if _MUSIC_NOTE_RE.fullmatch(t):
            continue  # music note token — not speech
        parts.append(t)
    return " ".join(parts)


# ---------------------------------------------------------------------------
# pdf/txt extraction (box-side fallback; browser pdf.js is the FIRST path)
# ---------------------------------------------------------------------------

def extract_txt(txt_path: Path, cap: int, result: c.Result) -> str:
    """Direct .txt read, length-checked, control-chars stripped."""
    try:
        raw = txt_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        result.fail(AF_REJECT_FORMAT, "unreadable .txt source %s: %s"
                    % (txt_path, exc))
        return ""
    try:
        return clean_text(raw, cap)
    except ValueError as exc:
        result.fail(AF_REJECT_SIZE, str(exc))
        return ""


def extract_pdf(pdf_path: Path, cap: int, result: c.Result) -> str:
    """Box-side PDF text extraction: pdftotext primary, pandoc fallback.

    A scanned/image-only PDF (both tools yield empty) is job `failed` with
    AF-BW-MA-EXTRACT-NO-TEXT — NEVER done-with-empty (MASTER-PLAN section 4).
    """
    text = _pdftotext_extract(pdf_path)
    if not text.strip():
        text = _pandoc_extract(pdf_path)
    if not text.strip():
        result.fail(AF_EXTRACT_NO_TEXT, "no extractable text in %s (scanned or "
                   "image-only PDF). Type it or record it instead." % pdf_path)
        return ""
    try:
        return clean_text(text, cap)
    except ValueError as exc:
        result.fail(AF_REJECT_SIZE, str(exc))
        return ""


def _pdftotext_extract(pdf_path: Path) -> str:
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        return ""
    try:
        proc = subprocess.run([pdftotext, "-layout", str(pdf_path), "-"],
                              capture_output=True, timeout=120)
    except (subprocess.TimeoutExpired, OSError):
        return ""
    if proc.returncode != 0:
        return ""
    return (proc.stdout or b"").decode("utf-8", "replace")


def _pandoc_extract(pdf_path: Path) -> str:
    pandoc = shutil.which("pandoc")
    if not pandoc:
        return ""
    try:
        proc = subprocess.run([pandoc, str(pdf_path), "-t", "plain"],
                              capture_output=True, timeout=120)
    except (subprocess.TimeoutExpired, OSError):
        return ""
    if proc.returncode != 0:
        return ""
    return (proc.stdout or b"").decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# the job machine
# ---------------------------------------------------------------------------

def extract(job: dict, capability_map=None, client_resolver=None,
            now_utc=None, transcribe_impl=None) -> dict:
    """Run one job through the engine. Returns the COMPLETED job record.

    On success: {..., status: done, text, transcript_json, still_frame,
    error: null, done_at_utc}. On failure: {..., status: failed, error} with an
    AF-BW-MA-* code in the error message. Fail-closed: a job can only reach
    `done` via a transition carrying non-empty text (or explicit N/A).

    transcribe_impl: injectable media->(transcript_json, text) function for
    offline tests (defaults to the provider-neutral hyperframes path).
    """
    result = c.Result("media_textractor")
    now = now_utc or _now_utc()
    out = dict(job)
    out.setdefault("status", "processing")
    out.setdefault("text", None)
    out.setdefault("transcript_json", None)
    out.setdefault("still_frame", None)
    out.setdefault("error", None)
    out.setdefault("created_at_utc", now)
    out["done_at_utc"] = None

    # -- channel must be known ------------------------------------------------
    channel = out.get("channel")
    if channel not in ("audio", "video", "pdf", "txt"):
        result.fail(AF_REJECT_FORMAT, "unknown channel %r (audio|video|pdf|txt)"
                    % channel)
        return _finish(out, result, now)

    # -- source uri -> local path ---------------------------------------------
    source_uri = out.get("source_uri")
    source_path = Path(source_uri)
    if not source_path.exists():
        result.fail(AF_REJECT_FORMAT, "source %s not found on this box"
                    % source_uri)
        return _finish(out, result, now)

    # -- extension allowlist + size cap ---------------------------------------
    ext = source_path.suffix.lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS.get(channel, []):
        if ext in UNSUPPORTED_EXTENSIONS:
            result.fail(AF_REJECT_FORMAT, ".%s is not supported in v1 — type "
                        "it or record it instead" % ext)
        else:
            result.fail(AF_REJECT_FORMAT, ".%s not on the %s allowlist"
                        % (ext, channel))
        return _finish(out, result, now)
    size = source_path.stat().st_size
    cap_size = SIZE_CAPS_BYTES.get(channel, 0)
    if cap_size and size > cap_size:
        result.fail(AF_REJECT_SIZE, "%s is %d bytes over the %d-byte %s cap"
                    % (source_uri, size, cap_size, channel))
        return _finish(out, result, now)

    # -- text channels ---------------------------------------------------------
    if channel == "txt":
        text = extract_txt(source_path, TEXT_CAPS["default"], result)
        if result.passed and text:
            out["text"] = text
        return _finish(out, result, now)

    if channel == "pdf":
        text = extract_pdf(source_path, TEXT_CAPS["default"], result)
        if result.passed and text:
            out["text"] = text
        return _finish(out, result, now)

    # -- media channels (audio / video) ---------------------------------------
    return _extract_media(out, source_path, capability_map, client_resolver,
                          result, now, transcribe_impl)


def _extract_media(out: dict, source_path: Path, capability_map,
                   client_resolver, result: c.Result, now: str,
                   transcribe_impl=None) -> dict:
    channel = out.get("channel")
    language = out.get("client_language") or out.get("language")

    # video best-effort still frame (never fails the job)
    if channel == "video":
        still = extract_still_frame(source_path,
                                    source_path.with_suffix(".still.jpg"))
        if still:
            out["still_frame"] = still

    # the effective transcription implementation (injectable for tests)
    def _transcribe(p, language, engine=None, extra_args=()):
        if transcribe_impl is not None:
            return transcribe_impl(p, language, engine=engine,
                                   extra_args=extra_args)
        return _run_hyperframes_transcribe(p, language, engine, extra_args)

    # -- client-provider ASR fallback keyed per client -------------------------
    # A resolver is the CLIENT's OWN speech provider (e.g. Skill 30 Fish Audio).
    # When one is configured for this client, it is the FIRST path.
    resolver = _resolver_from_map(capability_map, client_resolver) \
        if client_resolver else None
    if resolver:
        provider = resolver.get("provider")
        model_id = resolver.get("model_id")
        # AF-BW-MA-ANTHROPIC re-check on the RESOLVED model id — hard-fail.
        if recheck_resolved_model(model_id, result):
            return _finish(out, result, now)
        # provider-neutral default is `hyperframes`; anything else is not wired
        # in this unit (resolver wiring/live tests live in U15).
        if provider == "hyperframes":
            tjson, text = _transcribe(
                source_path, language, resolver.get("engine"),
                tuple(resolver.get("argv") or ()))
            if tjson is not None:
                out["transcript_json"] = tjson
                out["text"] = text
                return _finish(out, result, now)
            result.fail(AF_CAPABILITY, "client resolver %r failed to "
                        "transcribe %s" % (client_resolver, source_path))
            return _finish(out, result, now)
        result.fail(AF_CAPABILITY, "client resolver %r provider %r is not "
                    "wired in this unit (hyperframes is the provider-neutral "
                    "default)" % (client_resolver, provider))
        return _finish(out, result, now)

    # -- default hyperframes path ---------------------------------------------
    # capability gate: a REQUIRED capability absent locally AND no client
    # resolver -> hard-fail the job (AF-BW-MA-CAPABILITY, exit-7 pattern).
    cap = None
    if isinstance(capability_map, dict):
        cap = capability_map.get("transcribe")
    if cap is False:
        result.fail(AF_CAPABILITY, "transcription capability absent locally "
                    "(capability-map transcribe=false) and no client-provider "
                    "resolver configured")
        return _finish(out, result, now)

    tjson, text = _transcribe(source_path, language)
    if tjson is None:
        result.fail(AF_CAPABILITY, "default transcription failed for %s "
                    "(hyperframes/whisper unavailable or no transcript "
                    "produced) and no client-provider resolver configured"
                    % source_path)
        return _finish(out, result, now)
    if not (text or "").strip():
        result.fail(AF_EXTRACT_NO_TEXT, "transcription produced no speech text "
                    "for %s" % source_path)
        return _finish(out, result, now)
    out["transcript_json"] = tjson
    out["text"] = text
    return _finish(out, result, now)


def _finish(out: dict, result: c.Result, now: str) -> dict:
    """Write status/error/done_at_utc and return the completed job record."""
    if result.passed:
        out["status"] = "done"
        out["done_at_utc"] = now
        out["error"] = None
    else:
        out["status"] = "failed"
        out["done_at_utc"] = now
        out["error"] = "; ".join("%s: %s" % (code, msg)
                                 for code, msg in result.violations)
        out.setdefault("text", None)
    return out


def _exit_for_job(out: dict) -> int:
    """Exit-code class for a completed job: 0 done, 7 capability hard-fail,
    2 any other AF-BW-MA-* violation (fail-closed)."""
    if out.get("status") == "done":
        return 0
    err = out.get("error") or ""
    if AF_CAPABILITY in err:
        return 7
    return 2


# ---------------------------------------------------------------------------
# CLI + self-test
# ---------------------------------------------------------------------------

def self_test() -> int:
    checks = []

    # 1. clean_text strips C0/DEL control chars and caps length.
    t = clean_text("  hello\x00\x1f world\n  ", TEXT_CAPS["default"])
    checks.append(("clean_text strips C0/DEL control chars", t == "hello world"))
    try:
        clean_text("x" * (TEXT_CAPS["default"] + 10), TEXT_CAPS["default"])
        checks.append(("clean_text enforces the char cap", False))
    except ValueError:
        checks.append(("clean_text enforces the char cap", True))

    # 2. language rules: unknown -> multilingual small, no .en, no --language.
    argv = build_transcribe_argv("a.mp3", None)
    checks.append(("unknown language -> --model small (auto-detect, no .en)",
                   argv == ["transcribe", "a.mp3", "--model", "small"]))
    # 3. English stated -> small.en.
    argv = build_transcribe_argv("a.mp3", "en")
    checks.append(("English stated -> --model small.en",
                   argv == ["transcribe", "a.mp3", "--model", "small.en"]))
    # 4. known non-English -> multilingual small + --language code.
    argv = build_transcribe_argv("a.mp3", "es")
    checks.append(("known non-English -> --model small --language es",
                   argv == ["transcribe", "a.mp3", "--model", "small",
                            "--language", "es"]))
    # 5. NEVER .en for non-English / unknown paths.
    checks.append(("multilingual paths never use .en models",
                   ".en" not in build_transcribe_argv("a.mp3", "es")
                   and ".en" not in build_transcribe_argv("a.mp3", None)
                   and ".en" not in build_transcribe_argv("a.mp3", "ja")))

    # 6. transcript joining: word array -> plain text; music notes skipped.
    words = [{"text": "Hello"}, {"text": "world."},
             {"text": "♪"}, {"text": ""}]
    joined = join_transcript_text(words)
    checks.append(("transcript word array joins to plain text (music notes "
                   "skipped)", joined == "Hello world."))
    checks.append(("wrapper {segments} joins too",
                   join_transcript_text({"segments": [{"text": "A"}, {"text": "B"}]})
                   == "A B"))
    checks.append(("wrapper {text} passthrough",
                   join_transcript_text({"text": "single line"}) == "single line"))

    # 7. Anthropic re-check on the resolved model id.
    r = c.Result("st")
    recheck_resolved_model("openrouter/deepseek", r)
    checks.append(("non-Anthropic model id passes the re-check", r.passed))
    r2 = c.Result("st")
    hit = recheck_resolved_model("anthropic/claude-opus-4", r2)
    checks.append(("anthropic/claude-opus-4 triggers AF-BW-MA-ANTHROPIC",
                   hit and not r2.passed
                   and any(code == AF_ANTHROPIC for code, _ in r2.violations)))
    r3 = c.Result("st")
    hit3 = recheck_resolved_model("whisper-claude", r3)
    checks.append(("bare 'claude' in a model id triggers AF-BW-MA-ANTHROPIC",
                   hit3 and not r3.passed))

    # 8. EXTRACT-NO-TEXT for scanned/image-only PDF (fail, never done-with-empty).
    tmpdir = Path("/tmp/ma-u13-selftest")
    tmpdir.mkdir(exist_ok=True)
    blank_pdf = tmpdir / "blank.pdf"
    blank_pdf.write_bytes(
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 300]>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
        b"0000000052 00000 n \n0000000101 00000 n \n"
        b"trailer<</Root 1 0 R/Size 4>>\nstartxref\n172\n%%EOF\n"
    )
    job = {"intake_id": "i1", "answer_id": "a1", "channel": "pdf",
           "source_uri": str(blank_pdf), "source_sha256": "x"}
    out = extract(job)
    checks.append(("scanned/image-only PDF -> job failed (EXTRACT-NO-TEXT)",
                   out["status"] == "failed"
                   and AF_EXTRACT_NO_TEXT in (out.get("error") or "")))
    checks.append(("scanned PDF is NEVER done-with-empty",
                   not (out["status"] == "done"
                        and not (out.get("text") or ""))))

    # 9. .txt direct extraction.
    txt = tmpdir / "notes.txt"
    txt.write_text("  my story\x00 ideas\n", encoding="utf-8")
    job = {"intake_id": "i1", "answer_id": "a1", "channel": "txt",
           "source_uri": str(txt), "source_sha256": "x"}
    out = extract(job)
    checks.append((".txt direct read -> done with trimmed text",
                   out["status"] == "done"
                   and out.get("text") == "my story ideas"))

    # 10. .docx explicit rejection.
    docx = tmpdir / "notes.docx"
    docx.write_bytes(b"PK\x03\x04")
    job = {"intake_id": "i1", "answer_id": "a1", "channel": "txt",
           "source_uri": str(docx), "source_sha256": "x"}
    out = extract(job)
    checks.append((".docx rejected with REJECT-FORMAT (type-or-record offer)",
                   out["status"] == "failed"
                   and AF_REJECT_FORMAT in (out.get("error") or "")
                   and "type it or record it" in (out.get("error") or "")))

    # 11. missing source -> failed (never a silent blank).
    job = {"intake_id": "i1", "answer_id": "a1", "channel": "txt",
           "source_uri": "/nonexistent/na.txt", "source_sha256": "x"}
    out = extract(job)
    checks.append(("missing source -> job failed", out["status"] == "failed"
                   and "not found" in (out.get("error") or "")))

    # 12. unknown channel -> rejected.
    job = {"intake_id": "i1", "answer_id": "a1", "channel": "slides",
           "source_uri": str(txt), "source_sha256": "x"}
    out = extract(job)
    checks.append(("unknown channel -> rejected fail-closed",
                   out["status"] == "failed"
                   and AF_REJECT_FORMAT in (out.get("error") or "")))

    # 13. media paths. A real (tiny) media file exists so the engine reaches
    #     the resolver/transcription layer; the transcription call is injected
    #     with a fixture for the positive path so the self-test stays
    #     deterministic, offline, and fast (no model downloads).
    dummy_mp3 = tmpdir / "speech.mp3"
    dummy_mp3.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 512)
    base_job = {"intake_id": "i1", "answer_id": "a1", "channel": "audio",
                "source_uri": str(dummy_mp3), "source_sha256": "x"}

    cap_map = {"transcribe": False,
               "resolvers": {"fish-audio": {"provider": "hyperframes",
                                            "model_id": "client-whisper",
                                            "engine": None, "argv": []}}}
    bad_cap_map = {"transcribe": False,
                   "resolvers": {"bad": {"provider": "hyperframes",
                                         "model_id": "anthropic/claude-haiku",
                                         "engine": None, "argv": []}}}
    out = extract(dict(base_job), capability_map=bad_cap_map,
                  client_resolver="bad")
    checks.append(("client resolver model id re-checked for Anthropic "
                   "(AF-BW-MA-ANTHROPIC)",
                   out["status"] == "failed"
                   and AF_ANTHROPIC in (out.get("error") or "")))

    # positive hyperframes-resolver path (injected fixture).
    ok_impl = lambda p, lang, engine=None, extra_args=(): (  # noqa: E731
        {"words": [{"text": "hello"}, {"text": "from"}, {"text": "the"},
                   {"text": "client"}]}, "hello from the client")
    out = extract(dict(base_job), capability_map=cap_map,
                  client_resolver="fish-audio", transcribe_impl=ok_impl)
    checks.append(("client hyperframes resolver -> done with transcript text",
                   out["status"] == "done"
                   and out.get("text") == "hello from the client"
                   and out.get("transcript_json") is not None))

    # default path (no resolver) with a working transcribe -> done.
    out = extract(dict(base_job), capability_map={"transcribe": True},
                  client_resolver=None, transcribe_impl=ok_impl)
    checks.append(("default hyperframes path -> done with transcript text",
                   out["status"] == "done"
                   and out.get("text") == "hello from the client"))

    # capability-map transcribe=false + NO resolver -> hard-fail (exit-7).
    out = extract(dict(base_job), capability_map={"transcribe": False},
                  client_resolver=None)
    checks.append(("capability-map transcribe=false + no resolver -> "
                   "AF-BW-MA-CAPABILITY hard-fail",
                   out["status"] == "failed"
                   and AF_CAPABILITY in (out.get("error") or "")))
    checks.append(("capability hard-fail -> exit-7 class",
                   _exit_for_job(out) == 7))

    # unknown client resolver name -> falls through to the default path; with
    # transcription failing, that is a capability hard-fail.
    fail_impl = lambda p, lang, engine=None, extra_args=(): (None, None)  # noqa: E731
    out = extract(dict(base_job), capability_map={"transcribe": True},
                  client_resolver="does-not-exist", transcribe_impl=fail_impl)
    checks.append(("unknown resolver name + default transcribe failure -> "
                   "AF-BW-MA-CAPABILITY hard-fail",
                   out["status"] == "failed"
                   and AF_CAPABILITY in (out.get("error") or "")))

    # 14. no double-brace / dollar-paren template tokens in shipped code.
    src = Path(__file__).read_text(encoding="utf-8")
    ph = _PLACEHOLDER_RE.search(src)
    checks.append(("no double-brace or dollar-paren template tokens in "
                   "shipped code", ph is None))

    return c.selftest_report("media_textractor", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Book Writer mini-app U13 transcription engine "
                    "(provider-neutral, hard non-Anthropic).")
    ap.add_argument("job", nargs="?", help="job.json (partial job record)")
    ap.add_argument("--capability-map", help="capability-map.json path")
    ap.add_argument("--client-resolver", help="per-client ASR resolver name")
    ap.add_argument("--out", help="write the completed job record to OUT")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return self_test()
    if not args.job:
        ap.error("a job.json path is required (or use --selftest)")

    try:
        job = c.read_json(args.job)
    except SystemExit:
        return c.EXIT_USAGE
    capability_map = load_capability_map(args.capability_map)
    out = extract(job, capability_map=capability_map,
                  client_resolver=args.client_resolver)
    if args.out:
        Path(args.out).write_text(json.dumps(out, indent=2, default=str),
                                  encoding="utf-8")
    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        status = out.get("status")
        if status == "done":
            print("PASS [media_textractor]: job %s done (%d chars)"
                  % (out.get("answer_id"), len(out.get("text") or "")))
            if out.get("still_frame"):
                print("  still_frame: %s" % out["still_frame"])
        else:
            print("FAIL [media_textractor]: job %s %s — %s"
                  % (out.get("answer_id"), status, out.get("error")))
    return _exit_for_job(out)


if __name__ == "__main__":
    sys.exit(main())
