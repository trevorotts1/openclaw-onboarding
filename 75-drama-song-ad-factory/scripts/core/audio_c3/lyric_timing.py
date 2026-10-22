#!/usr/bin/env python3
"""F17 lyric timing: ONE transcription step, three tiers, owner order.

Owner order 2026-10-08 (manual Part F F17, Critical; PASTE ADDENDUM 5).
Cause: on 2026-10-08 08:55 six agent-written copies of the banned whisper stack ("medium.en")
copies (~3.5 GB each) started at once on a 24 GB Mac and the box crashed.
Every consumer that needs words or word timing (the lyric check
``music_qc``/``timing_guard``, captions, lip-sync line windows, the talk/sing
split) calls THIS module and nothing else for word timings.

Tier 1 -- DEFAULT. Suno's own timestamped lyrics via KIE "Get Timestamped
Lyrics" (ai-music-api/timeStamped-lyrics; returns alignedWords with
startS/endS per word), routed through ``core/kie_dispatch`` like every paid
call. This module never touches KIE endpoints itself (Skill 74 is the only
KIE path; F14's qc-no-direct-kie.sh holds). Tier 1 returns
``{'source': 'suno-alignedWords', 'words': [{word, startS, endS}]}`` -- no
local model.

Tier 2 -- FALLBACK, only when tier 1 fails or is insufficient:
faster-whisper, LOCAL, ONE model loaded AT A TIME. A run hands its tracks to
one ``WhisperSession`` and every track is transcribed one after another in
that single session while exactly one model stays loaded (the load counter
proves it). Smallest model that passes; start "small" or "medium", int8.
NEVER the banned OpenAI whisper stack -- the loader surface is refused here and
``scripts/qc-no-local-asr.sh`` fails a hand-written whisper/asr script in a
run folder. The only permitted import is ``faster_whisper`` (a
``faster-whisper-optional`` PREREQS entry, only when this fallback is
enabled).

Tier 2 production contract (D18 repair). ``WhisperSession()`` needs NO
injected test loader: ``WHISPER_LOADER_FACTORY`` (``default_whisper_loader_factory``)
builds the real supported ``faster_whisper.WhisperModel`` loader. The
supported load/call/segment-conversion contract is exactly the public
faster-whisper API:

* load: ``WhisperModel(model_size, device="cpu", compute_type=compute_type)``
* call: ``segments, info = model.transcribe(audio_path, word_timestamps=True)``
* conversion: ``segments`` is a generator of segment objects with a ``words``
  list; each word carries ``word``/``start``/``end`` (``probability`` when the
  source reports it). ``words_from_segments`` also accepts the flat/dict
  shapes the tests and saved records use.

The audio path is handed over as a REAL file path (``track["audio_path"]`` or
``track["path"]``); a track without one refuses with the distinct
``AUDIO_PATH_MISSING`` class -- it is never guessed or invented. Exactly one
model load per session, admitted by Part D's ``memory_guard`` and run under
``load_governor.heavy_slot("transcription")``.

Tier 3 -- only when tiers 1 AND 2 both fail: cloud speech-to-text with word
timestamps, the CLIENT's own key only (env var DRAMA75_CLOUD_STT_API_KEY).
Operator key names (KIE_API_KEY, OPENAI_API_KEY, ...) are refused by name
and the value is never read or returned.

Receipt: every timing receipt carries ``source`` =
"suno-timestamped-lyrics" | "faster-whisper-local" | "cloud-stt" plus
``transcription_provider`` and ``local_model_loads``.

Typed failure classes (D25 repair). Every refusal keeps its causal chain
(``raise ... from``; ``LyricTimingError.envelope()`` walks it) instead of
collapsing into one ambiguous code. The distinct classes are:
``missing-loader``, ``missing-dependency``, ``low-memory``,
``unreadable-resource-telemetry``, ``unwired-loader``,
``model-load-failure``, ``bad-call-signature``, ``missing-audio-path``,
``unavailable-timestamps``, ``malformed-qc-input`` (+ the crash class
``transcription-failed``). Diagnostics are bounded and redacted
(``_redact``; secret-shaped values never leave the machine). One compat pin:
``memory_guard`` refusals keep the externally-pinned umbrella code
``LOCAL_MODEL_LOAD_REFUSED`` (singing_detector consumes it) while the
envelope and every boundary carry the distinct ``failure_class`` and the
distinct boundary code (``LOCAL_MODEL_LOW_MEMORY`` /
``LOCAL_MODEL_TELEMETRY_UNREADABLE``). ``save_error_record`` persists the
whole envelope; the causal chain survives the save/readback.

Non-generating operations (D26 repair) -- exposed through THIS module's
CLI/controller and callable from the existing controllers:

    python3 core/audio_c3/lyric_timing.py selftest
    python3 core/audio_c3/lyric_timing.py validate  <record.json>|- [--out F]
    python3 core/audio_c3/lyric_timing.py migrate   <record.json>|- [--out F]
    python3 core/audio_c3/lyric_timing.py rejudge   <record.json>|- [--out F] [--floor X]
    python3 core/audio_c3/lyric_timing.py remeasure --audio A.wav [--record R.json] [--out F]
    python3 core/audio_c3/lyric_timing.py reconcile [--audio A.wav] <record.json>...

* validate/migrate: schema-shape check and version migration of saved
  timing/QC records through schema-specific object/list readers
  (``read_records`` accepts a record, a record list, or ``{"records": [...]}``;
  a wrong shape is an explicit ``MALFORMED_QC_INPUT``, never a silent skip).
  Migration preserves approved words and unknown fields and REPORTS any
  semantic difference requiring review; a record lacking provider-envelope
  fields is not thereby obsolete.
* rejudge: re-decides from SAVED measurements. Zero provider calls, zero
  model loads -- structurally impossible here (it takes no dispatcher or
  loader).
* remeasure: re-measures SAVED audio (sha256 before == after, provenance
  preserved). Zero music-generation requests, ever: the only paid call that
  can be involved is the existing timestamped-lyrics ANALYSIS through the
  authorized dispatcher (``allow_paid_analysis=True`` only), separately
  counted in ``counts.paid_analysis_calls``. ``counts.music_generation_calls``
  is 0 on every operation record and failure envelope.
* reconcile: compares saved records against the audio on disk (hash,
  provenance) and reports; it never rewrites and never re-measures.

Low confidence is never a definite creative failure: ``rejudge`` answers
``needs-review`` with the bounded next actions (ONE remeasure pass, or
independent media review), and a low-confidence tier-2 receipt says so
without discarding the measured words.

Part D load guard: BEFORE any local model load, ``memory_guard`` measures
free RAM with the numbers lane_size.py / scripts/capacity-monitor.sh already
rule by (RESERVE_GB 2.0 + GB_PER_AGENT 1.5 headroom) and refuses with
``LOCAL_MODEL_LOAD_REFUSED`` when loading would push the machine past its
limit. Tier 1 loads nothing and never reaches the guard; tier 3 loads
nothing local.

``provide_word_timings(track, timing_map_hint=None)`` is the single entry
every consumer calls. The one landing seam is
``timing_guard.validate(approved_lines, observed_words, ...)`` -- its
``observed_words`` are exactly the normalized words here; the other four
consumers wire in W-F-U18. stdlib only; no network of its own; tests mock
every tier, $0 spend.

CLI exit/result contract (an explicit refusal stays a refusal):
exit 0 = operation completed with an accepting result (validation passed,
verdict "pass", remeasurement produced words with an unchanged hash,
reconcile found no mismatch); exit 5 ("rejected") = the operation completed
but the RESULT refuses acceptance (any typed refusal envelope, verdict
"fail"/"needs-remeasure"/"needs-review", remeasure without words or with a
changed hash, reconcile mismatch); exit 1 ("error") = the operation itself
could not run (usage error, unreadable input file, unexpected crash). The
JSON printed on stdout always carries ``"ok"`` (the operation ran) plus the
verdict or the full typed error envelope -- a controller must read the
envelope/verdict, never just the process status.

Run: python3 core/audio_c3/test_lyric_timing_f17.py
"""
from __future__ import annotations

# Skill 75 load governor: every heavy local job goes through it (see load_governor/).
import os as _gos, sys as _gsys
_gcore = _gos.path.abspath(_gos.path.join(_gos.path.dirname(__file__), '..'))
if _gcore not in _gsys.path:
    _gsys.path.insert(0, _gcore)
import load_governor as _LG  # noqa: E402

import hashlib
import os
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

SCHEMA_VERSION = "blackceo.audio-c3/lyric-timing/v1"
TOOL_VERSION = "1.1.0"
TOOL_NAME = "lyric_timing"

# ── provenance (receipt ``source`` values, task-exact) ──────────────────────
SOURCE_SUNO = "suno-timestamped-lyrics"
SOURCE_WHISPER_LOCAL = "faster-whisper-local"
SOURCE_CLOUD_STT = "cloud-stt"
SOURCES = (SOURCE_SUNO, SOURCE_WHISPER_LOCAL, SOURCE_CLOUD_STT)
#: tier-1 payload form exactly as the owner order words it.
TIER1_PAYLOAD_SOURCE = "suno-alignedWords"

#: KIE model id for Suno Get Timestamped Lyrics (registry:
#: 74-kie-live-adapter/references/kie-model-registry.json, variant
#: "timestamped-lyrics", family "suno", 0.5 credits/request).
KIE_MODEL_TIMESTAMPED_LYRICS = "ai-music-api/timeStamped-lyrics"

#: Approved faster-whisper sizes (smallest that passes; never "large*").
WHISPER_SIZES = ("small", "medium")
DEFAULT_WHISPER_SIZE = "small"
#: int8 footprints the load guard assumes (GB; conservative, aligned with
#: lane_size.GB_PER_AGENT = 1.5).
WHISPER_GB = {"small": 1.5, "medium": 1.5}

#: Part D load-guard numbers -- REUSED from lane_size.py / capacity-monitor.sh
#: (lane_size.DEFAULTS: RESERVE_GB 2.0, GB_PER_AGENT 1.5).
LOCAL_MODEL_RESERVE_GB = 2.0    # OS + gateway + Command Center
LOCAL_MODEL_HEADROOM_GB = 1.5   # the model's own working-set headroom

#: The one env var tier 3 reads: the CLIENT's own cloud-STT key name.
CLIENT_KEY_ENV_NAME = "DRAMA75_CLOUD_STT_API_KEY"
#: Operator key env names tier 3 must never read (never operator keys).
OPERATOR_KEY_ENV_NAMES = frozenset({
    "KIE_API_KEY",           # KIE rides tier 1 via kie_dispatch only
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "MOONSHOT_API_KEY",
    "GOOGLE_API_KEY",
    "FISH_AUDIO_API_KEY",
})

EXIT = {"ok": 0, "error": 1, "rejected": 5}

#: Below this mean word probability, measurement confidence is LOW: trigger a
#: bounded remeasure or an independent media review -- never relabel the
#: classifier's uncertainty as a definite creative failure.
CONFIDENCE_FLOOR = 0.6
#: Bounded remeasure: at most ONE remeasure pass per decision (no loops).
MAX_REMEASURE_PASSES = 1


def _loud(kind, code, detail):
    """Named, visible failure/warning that reaches the receipt (loud_failure.py)."""
    import os as _os, sys as _sys
    d = _os.path.dirname(_os.path.abspath(__file__))
    while d != _os.path.dirname(d) and not _os.path.exists(_os.path.join(d, "loud_failure.py")):
        d = _os.path.dirname(d)
    if d not in _sys.path:
        _sys.path.insert(0, d)
    import loud_failure
    getattr(loud_failure, kind)(code, detail)


# ── typed failure classes (D25): distinct, never collapsed ──────────────────
#
# ``failure_class`` is the stable taxonomy label; ``code`` is the exact
# machine code on the exception. Every boundary (``envelope()``,
# ``provide_word_timings``'s failure record, ``save_error_record``) keeps
# code + failure_class + the chained cause.

CLASS_MISSING_LOADER = "missing-loader"
CLASS_DEPENDENCY_MISSING = "missing-dependency"
CLASS_LOW_MEMORY = "low-memory"
CLASS_TELEMETRY_UNREADABLE = "unreadable-resource-telemetry"
CLASS_UNWIRED_LOADER = "unwired-loader"
CLASS_MODEL_LOAD_FAILED = "model-load-failure"
CLASS_BAD_CALL_SIGNATURE = "bad-call-signature"
CLASS_AUDIO_PATH_MISSING = "missing-audio-path"
CLASS_TIMESTAMPS_UNAVAILABLE = "unavailable-timestamps"
CLASS_MALFORMED_INPUT = "malformed-qc-input"
CLASS_TRANSCRIBE_FAILED = "transcription-failed"

FAILURE_CLASSES = (
    CLASS_MISSING_LOADER, CLASS_DEPENDENCY_MISSING, CLASS_LOW_MEMORY,
    CLASS_TELEMETRY_UNREADABLE, CLASS_UNWIRED_LOADER, CLASS_MODEL_LOAD_FAILED,
    CLASS_BAD_CALL_SIGNATURE, CLASS_AUDIO_PATH_MISSING,
    CLASS_TIMESTAMPS_UNAVAILABLE, CLASS_MALFORMED_INPUT,
    CLASS_TRANSCRIBE_FAILED,
)

#: Canonical distinct code per class (D25: these are never collapsed).
CLASS_CODE = {
    CLASS_MISSING_LOADER: "WHISPER_LOADER_MISSING",
    CLASS_DEPENDENCY_MISSING: "WHISPER_DEPENDENCY_MISSING",
    CLASS_LOW_MEMORY: "LOCAL_MODEL_LOW_MEMORY",
    CLASS_TELEMETRY_UNREADABLE: "LOCAL_MODEL_TELEMETRY_UNREADABLE",
    CLASS_UNWIRED_LOADER: "WHISPER_LOADER_UNWIRED",
    CLASS_MODEL_LOAD_FAILED: "WHISPER_MODEL_LOAD_FAILED",
    CLASS_BAD_CALL_SIGNATURE: "WHISPER_BAD_CALL_SIGNATURE",
    CLASS_AUDIO_PATH_MISSING: "AUDIO_PATH_MISSING",
    CLASS_TIMESTAMPS_UNAVAILABLE: "WORD_TIMESTAMPS_UNAVAILABLE",
    CLASS_MALFORMED_INPUT: "MALFORMED_QC_INPUT",
    CLASS_TRANSCRIBE_FAILED: "WHISPER_TRANSCRIBE_FAILED",
}

#: D25 repair-class taxonomy: prerequisite / resource / request / provider /
#: evaluation / delivery -- classify BEFORE selecting a repair.
CLASS_CATEGORY = {
    CLASS_MISSING_LOADER: "prerequisite",
    CLASS_DEPENDENCY_MISSING: "prerequisite",
    CLASS_UNWIRED_LOADER: "prerequisite",
    CLASS_LOW_MEMORY: "resource",
    CLASS_TELEMETRY_UNREADABLE: "resource",
    CLASS_BAD_CALL_SIGNATURE: "request",
    CLASS_AUDIO_PATH_MISSING: "request",
    CLASS_MALFORMED_INPUT: "request",
    CLASS_MODEL_LOAD_FAILED: "provider",
    CLASS_TRANSCRIBE_FAILED: "provider",
    CLASS_TIMESTAMPS_UNAVAILABLE: "evaluation",
}

#: memory_guard keeps the umbrella code singing_detector pins, but every
#: boundary maps its failure_class to the distinct code here.
GUARD_BOUNDARY_CODE = {
    CLASS_LOW_MEMORY: CLASS_CODE[CLASS_LOW_MEMORY],
    CLASS_TELEMETRY_UNREADABLE: CLASS_CODE[CLASS_TELEMETRY_UNREADABLE],
}

#: legacy alias (old name for the unavailable-timestamps refusal)
WHISPER_EMPTY = CLASS_CODE[CLASS_TIMESTAMPS_UNAVAILABLE]

_DIAG_BOUND = 200
_SECRET_PAT = re.compile(
    r"(?i)\b(sk|api[-_]?key|key|token|secret|password|bearer)[-_=: ]+[A-Za-z0-9_\-]{4,}")
_TOKEN_PAT = re.compile(r"\b[A-Za-z0-9_\-]{40,}\b")


def _redact(value: Any, bound: int = _DIAG_BOUND) -> str:
    """Bounded, redacted operator diagnostic: secret-shaped values never
    leave the machine, long opaque tokens are dropped, length is capped."""
    s = "" if value is None else str(value)
    s = _SECRET_PAT.sub(lambda m: "%s=[REDACTED]" % m.group(1), s)
    s = _TOKEN_PAT.sub("[REDACTED]", s)
    if len(s) > bound:
        s = s[:bound] + "...(truncated)"
    return s


class LyricTimingError(Exception):
    """Machine-code refusal; never a silent pass.

    Carries its causal chain (``raise ... from cause`` / ``__cause__``) and a
    ``failure_class`` taxonomy label. ``envelope()`` produces the bounded
    redacted saved record; ``boundary_code()`` is the distinct code consumers
    see on failure envelopes.
    """

    def __init__(self, code, message, failure_class: Optional[str] = None,
                 cause: Optional[BaseException] = None):
        super().__init__(message)
        self.code = code
        self.failure_class = failure_class
        if cause is not None and self.__cause__ is None:
            self.__cause__ = cause

    def boundary_code(self) -> str:
        """Distinct code at a boundary. Guard refusals keep their pinned
        umbrella ``code`` on the exception but surface their distinct class
        code here; every other refusal already carries its distinct code."""
        return GUARD_BOUNDARY_CODE.get(self.failure_class or "", self.code)

    def envelope(self, depth: int = 4) -> Dict[str, Any]:
        """The durable, bounded, redacted causal envelope (D25)."""
        env: Dict[str, Any] = {
            "code": self.code,
            "failure_class": self.failure_class,
            "category": CLASS_CATEGORY.get(self.failure_class or ""),
            "error_type": type(self).__name__,
            "detail": _redact(self.args[0] if self.args else ""),
        }
        if self.failure_class and self.boundary_code() != self.code:
            env["boundary_code"] = self.boundary_code()
        cause = self.__cause__
        if cause is not None and depth > 0:
            if isinstance(cause, LyricTimingError):
                env["cause"] = cause.envelope(depth - 1)
            else:
                env["cause"] = {"error_type": type(cause).__name__,
                                "detail": _redact(cause)}
        return env


def save_error_record(path: str, err: Any) -> Dict[str, Any]:
    """Persist the FULL typed refusal envelope to the durable attempt record.

    ``err`` is a LyricTimingError or an already-built envelope. The causal
    chain survives the save (and ``read_error_record`` reads it back). Bounded
    and redacted by construction (``envelope``/``_redact``)."""
    env = err.envelope() if isinstance(err, LyricTimingError) else dict(err)
    env.setdefault("schema_version", SCHEMA_VERSION)
    env.setdefault("tool", TOOL_NAME)
    env.setdefault("tool_version", TOOL_VERSION)
    import json as _json
    with open(path, "w", encoding="utf-8") as fh:
        _json.dump(env, fh, indent=2, sort_keys=True)
    return env


def read_error_record(path: str) -> Dict[str, Any]:
    """Read back a saved refusal envelope (round-trip proof: the causal chain
    is still there)."""
    import json as _json
    with open(path, "r", encoding="utf-8") as fh:
        return _json.load(fh)
# ── Part D load guard (tier 2 only; fires BEFORE any local model load) ──────

def memory_guard(model_size: str = DEFAULT_WHISPER_SIZE, *,
                 free_gb_probe: Optional[Callable[[], float]] = None,
                 reserve_gb: float = LOCAL_MODEL_RESERVE_GB,
                 headroom_gb: float = LOCAL_MODEL_HEADROOM_GB) -> Dict[str, Any]:
    """Refuse a local model load that would push the machine past its limit.

    Free-RAM rule reads from lane_size.ram_avail_gb when importable (same
    numbers capacity-monitor.sh rules by: Darwin vm_stat free+inactive+
    speculative, Linux MemAvailable, cgroup cap wins); tests inject the
    probe. Needed = RESERVE_GB (OS/gateway) + the model's own headroom
    (WHISPER_GB, the lane_size GB_PER_AGENT calibration).

    Typed causes stay distinct (D25): a raising/unreadable probe is
    ``unreadable-resource-telemetry``, free < needed is ``low-memory``. The
    umbrella ``code`` (LOCAL_MODEL_LOAD_REFUSED) is externally pinned
    (singing_detector); the distinct class rides ``failure_class`` and
    ``boundary_code()``.
    """
    size = model_size if model_size in WHISPER_SIZES else DEFAULT_WHISPER_SIZE
    model_gb = float(WHISPER_GB[size])
    need = float(reserve_gb) + model_gb
    probe = free_gb_probe or _free_ram_gb
    try:
        free = float(probe())
    except LyricTimingError:
        raise   # a typed probe refusal is already a typed refusal: never re-wrap
    except Exception as e:  # noqa: BLE001 - an unreadable machine refuses
        raise LyricTimingError(
            "LOCAL_MODEL_LOAD_REFUSED",
            "load guard cannot measure free RAM (%s); refused before any "
            "local load" % e, CLASS_TELEMETRY_UNREADABLE, cause=e) from e
    if free != free or free < 0:  # NaN (probe unusable) refuses fail-closed
        raise LyricTimingError(
            "LOCAL_MODEL_LOAD_REFUSED",
            "load guard could not read free RAM; refused before any local "
            "load", CLASS_TELEMETRY_UNREADABLE)
    if free < need:
        raise LyricTimingError(
            "LOCAL_MODEL_LOAD_REFUSED",
            "free %.2f GB < needed %.2f GB (reserve %.1f + %s model %.1f "
            "headroom); a local model load would push the machine past its "
            "limit" % (free, need, reserve_gb, size, model_gb),
            CLASS_LOW_MEMORY)
    return {"checked": True, "free_gb": round(free, 3), "needed_gb": round(need, 3),
            "reserve_gb": reserve_gb, "model_size": size}


def _free_ram_gb() -> float:
    """Free RAM in GB from lane_size's rule (same numbers as capacity-monitor).
    Returns NaN when lane_size is unavailable -- the guard refuses on NaN."""
    try:  # sibling module in the same core/ tree
        import lane_size  # noqa: PLC0415

        avail = lane_size.ram_avail_gb()
        if isinstance(avail, (int, float)) and avail >= 0:
            return float(avail)
    except Exception:  # noqa: BLE001
        pass
    return float("nan")


# ── tier 1: Suno timestamped lyrics via kie_dispatch ────────────────────────

def normalize_aligned_words(aligned_words: Iterable[Any]) -> List[Dict[str, Any]]:
    """KIE alignedWords -> [{word, start, end}] numeric, ordered, fail-closed.

    Accepts raw KIE dicts ({word, startS, endS}), normalized dicts
    ({word, start, end}), and (word, start, end) triples. Raises
    SUNO_ALIGNMENT_BAD on any non-numeric timestamp (invented precision is
    never an option; tier 2/3 is the answer).
    """
    words: List[Dict[str, Any]] = []
    for i, aw in enumerate(aligned_words or []):
        if isinstance(aw, dict):
            w = aw.get("word", "")
            s, e = aw.get("startS", aw.get("start")), aw.get("endS", aw.get("end"))
        elif isinstance(aw, (tuple, list)) and len(aw) == 3:
            w, s, e = aw
        else:
            raise LyricTimingError(
                "SUNO_ALIGNMENT_BAD", "alignedWords entry %d is not a word" % i,
                CLASS_MALFORMED_INPUT)
        try:
            s_f, e_f = float(s), float(e)
        except (TypeError, ValueError) as exc:
            raise LyricTimingError(
                "SUNO_ALIGNMENT_BAD",
                "alignedWords entry %d has no numeric startS/endS" % i,
                CLASS_MALFORMED_INPUT, cause=exc) from exc
        if e_f + 1e-9 < s_f:
            raise LyricTimingError(
                "SUNO_ALIGNMENT_BAD", "alignedWords entry %d ends before start" % i,
                CLASS_MALFORMED_INPUT)
        words.append({"word": str(w), "start": round(s_f, 3), "end": round(e_f, 3)})
    return words


def _aligned_from_doc(doc: Any) -> List[Dict[str, Any]]:
    """Find alignedWords wherever the KIE response carries it (recursing
    through typical wrapper keys)."""
    if not isinstance(doc, dict):
        return []
    for key in ("alignedWords", "aligned_words"):
        if isinstance(doc.get(key), list) and doc[key]:
            return normalize_aligned_words(doc[key])
    for key in ("data", "music", "result", "response"):
        sub = doc.get(key)
        if isinstance(sub, dict):
            got = _aligned_from_doc(sub)
            if got:
                return got
    return []


def _read_saved_docs(saved_paths: Sequence[str]) -> List[Dict[str, Any]]:
    """Read each saved KIE file as JSON (unparsable ones are skipped -- the
    alignedWords finder decides whether anything usable survived)."""
    import json as _json

    from pathlib import Path as _Path

    docs = []
    for p in saved_paths or []:
        try:
            docs.append(_json.loads(_Path(p).read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            _loud("warn", "SAVED_KIE_FILE_UNREADABLE", "%s: %r" % (p, exc))
            continue
    return docs


def _suno_track_ids(track: Dict[str, Any]) -> Any:
    """(task_id, audio_id) provenance of the one Suno generation."""
    task_id = (track or {}).get("task_id") or (track or {}).get("generation_id")
    audio_id = (track or {}).get("audio_id") or (track or {}).get("generation_id")
    if not task_id and not audio_id:
        raise LyricTimingError(
            "SUNO_TRACK_MISSING",
            "track carries no Suno task_id/audio_id; tier 1 cannot ask for "
            "its timestamped lyrics")
    return task_id, audio_id


def fetch_suno_timestamped_lyrics(track: Dict[str, Any], *,
                                  dispatcher: Optional[Callable[..., Dict[str, Any]]] = None,
                                  ledger_db: str = "", run_id: str = "",
                                  attempt_id: str = "",
                                  card_receipt: Optional[Dict[str, Any]] = None,
                                  ) -> Dict[str, Any]:
    """KIE Get Timestamped Lyrics through kie_dispatch (mocked in tests).

    Returns ``{'source': 'suno-alignedWords', 'words': [{word, startS,
    endS}], 'evidence': {...}}``. Every paid-call rule holds: the request
    rides the SAME dispatcher every other stage uses (ledger reserve,
    Skill 74 health/preflight/submit/wait/save), never a private KIE client.
    Raises LyricTimingError on any dispatch failure -- tier-2's trigger.

    This is the timestamped-lyrics ANALYSIS call (0.5 credits); it is never a
    music-generation request.

    ``card_receipt``: the run's recorded F15 choice-card receipt (argument,
    else ``track["card_receipt"]``), threaded into ``request["card_receipt"]``
    exactly as picture_gate.make_regenerate does. kie_dispatch's card gate
    validates it; with none, that gate still refuses CARD_UNANSWERED.
    """
    task_id, audio_id = _suno_track_ids(track)
    if dispatcher is None:
        try:
            from kie_dispatch import kie_dispatch as KD  # sibling core package
        except ImportError as e:  # pragma: no cover - packaging bug, not runtime
            raise LyricTimingError(
                "DISPATCHER_UNAVAILABLE",
                "core kie_dispatch is not importable: %s" % e) from e
        dispatcher = KD.dispatch
    # Skill 74's ``_cb_check`` validates any PRESENT callBackUrl as an
    # http(s) URL and refuses "" as bad_request before submit, so the key is
    # OMITTED when there is none. This operation returns its aligned words
    # synchronously anyway: there is nothing to call back to.
    request = {"model": KIE_MODEL_TIMESTAMPED_LYRICS,
               "input": {"task_id": task_id or "", "audio_id": audio_id or ""}}
    _cb = (track or {}).get("callback_url")
    if _cb:
        request["callBackUrl"] = _cb
    receipt = card_receipt if card_receipt is not None \
        else (track or {}).get("card_receipt")
    if receipt is not None:  # never fabricated: absent stays absent -> gate refuses
        request["card_receipt"] = receipt
    env = dispatcher(
        model=request["model"], request=request,
        save_dir=(track or {}).get("save_dir", "word-timings"),
        ledger_db=ledger_db, run_id=run_id or "lyric-timing",
        logical_key="word-timings:%s" % (audio_id or task_id),
        attempt_id=attempt_id or "att-1",
        estimated_cost=1, prompt="", stage="word-timings",
        owner="lyric-timing")
    if env.get("outcome") != "ok":
        raise LyricTimingError(
            "SUNO_TIMING_DISPATCH_FAILED",
            "kie_dispatch outcome %s (%s): %s"
            % (env.get("outcome"), env.get("reason_code"),
               env.get("next_action")))
    saved = env.get("evidence", {}).get("saved_paths") or []
    aligned = _aligned_from_doc_first(_read_saved_docs(saved))
    if not aligned:
        raise LyricTimingError(
            "SUNO_ALIGNMENT_MISSING",
            "dispatch saved %d file(s) but none carried alignedWords"
            % len(saved))
    words = [{"word": w["word"], "startS": w["start"], "endS": w["end"]}
             for w in aligned]
    return {"source": TIER1_PAYLOAD_SOURCE, "words": words,
            "evidence": {"tier": 1, "payload": TIER1_PAYLOAD_SOURCE,
                         "kie_model": request["model"],
                         "reason_code": env.get("reason_code"),
                         "saved_paths": list(saved)}}


def _aligned_from_doc_first(docs: Sequence[Dict[str, Any]]):
    for d in docs:
        got = _aligned_from_doc(d)
        if got:
            return got
    return []
# ── tier 2: faster-whisper, LOCAL, ONE model at a time ──────────────────────

def default_whisper_loader_factory() -> Callable[[str, str], Any]:
    """Production tier-2 loader factory: the REAL supported faster-whisper
    load contract. The ``faster_whisper`` import below is the only permitted
    local-ASR import (scripts/qc-no-local-asr.sh fails a second importer).

    Distinct failures (D25): the import failing is ``missing-dependency``
    (never "low memory"); a constructor failure is ``model-load-failure``
    with its cause chained."""
    try:
        from faster_whisper import WhisperModel  # noqa: PLC0415
    except ImportError as e:
        raise LyricTimingError(
            CLASS_CODE[CLASS_DEPENDENCY_MISSING],
            "faster_whisper is not installed in the selected interpreter "
            "(PREREQS faster-whisper-optional: install only when this "
            "fallback is enabled): %s" % e,
            CLASS_DEPENDENCY_MISSING, cause=e) from e

    def load(model_size: str, compute_type: str = "int8") -> Any:
        try:
            return WhisperModel(model_size, device="cpu",
                                compute_type=compute_type)
        except Exception as e:  # noqa: BLE001 - a load failure is a load failure
            raise LyricTimingError(
                CLASS_CODE[CLASS_MODEL_LOAD_FAILED],
                "faster-whisper model load failed (%s, %s): %s"
                % (model_size, compute_type, e),
                CLASS_MODEL_LOAD_FAILED, cause=e) from e

    return load


#: The production loader factory. Present in a healthy build; a deployment
#: that registers None here reports ``missing-loader`` (distinct from the
#: factory's own ``missing-dependency``).
WHISPER_LOADER_FACTORY: Optional[Callable[[], Callable[..., Any]]] = \
    default_whisper_loader_factory


def _banned_asr_loader(loader: Callable) -> bool:
    """True when the injected loader's name/module surface names the banned
    ASR stack (the banned import surfaces the qc scan names). faster_whisper passes."""
    if loader is None:
        return False
    text = "%s %s" % (getattr(loader, "__name__", ""),
                      getattr(loader, "__module__", "") or "")
    lowered = text.lower()
    if "faster_whisper" in lowered:
        return False
    return ("openai" in lowered or "whisper." in lowered
            or lowered.strip().endswith("whisper")
            or lowered.startswith("whisper "))


class WhisperSession:
    """ONE faster-whisper model per run, tracks transcribed one after another.

    NO injected test loader is required: with ``loader=None`` the session
    resolves ``WHISPER_LOADER_FACTORY`` (the real ``faster_whisper.WhisperModel``
    loader). Tests may still inject a loader; the banned-ASR surface check
    runs on whatever is wired. ``loads`` counts model loads; a multi-track run
    through ONE session shows exactly 1. Part D's load guard fires before the
    load and refuses (typed) when free RAM is short.

    Supported call contract (the real faster-whisper API):
    ``segments, info = model.transcribe(audio_path, word_timestamps=True)``.
    """

    def __init__(self, *, loader: Optional[Callable[..., Any]] = None,
                 model_size: str = DEFAULT_WHISPER_SIZE,
                 compute_type: str = "int8",
                 free_gb_probe: Optional[Callable[[], float]] = None,
                 use_default_loader: bool = True):
        if model_size not in WHISPER_SIZES:
            raise LyricTimingError(
                "WHISPER_SIZE_FORBIDDEN",
                "%r is outside the approved sizes %s (smallest that passes; "
                "never larger, never the banned whisper stack)"
                % (model_size, WHISPER_SIZES))
        if _banned_asr_loader(loader):
            raise LyricTimingError(
                "LOCAL_ASR_FORBIDDEN",
                "loader names the banned whisper stack; tier 2 loads "
                "faster-whisper only")
        self._loader = loader
        self._use_default = bool(use_default_loader)
        self.model_size = model_size
        self.compute_type = compute_type
        self._free_gb_probe = free_gb_probe
        self.model: Any = None
        self.loads = 0

    def _resolve_loader(self) -> Callable[..., Any]:
        if self._loader is not None:
            return self._loader
        if not self._use_default:
            raise LyricTimingError(
                CLASS_CODE[CLASS_UNWIRED_LOADER],
                "no faster-whisper loader wired to this session and the "
                "default loader is disabled (use_default_loader=False)",
                CLASS_UNWIRED_LOADER)
        factory = WHISPER_LOADER_FACTORY
        if factory is None:
            raise LyricTimingError(
                CLASS_CODE[CLASS_MISSING_LOADER],
                "no production faster-whisper loader factory is registered "
                "in this build (WHISPER_LOADER_FACTORY is None)",
                CLASS_MISSING_LOADER)
        loader = factory()
        if loader is None or not callable(loader):
            raise LyricTimingError(
                CLASS_CODE[CLASS_UNWIRED_LOADER],
                "the production loader factory returned no callable loader",
                CLASS_UNWIRED_LOADER)
        return loader

    def _ensure_loaded(self):
        self._guard()
        if self.model is None:
            loader = self._resolve_loader()
            self._loader = loader
            try:
                model = loader(self.model_size, self.compute_type)
            except LyricTimingError:
                raise
            except Exception as e:  # noqa: BLE001 - load failure is typed
                raise LyricTimingError(
                    CLASS_CODE[CLASS_MODEL_LOAD_FAILED],
                    "faster-whisper loader raised while loading %s/%s: %s"
                    % (self.model_size, self.compute_type, e),
                    CLASS_MODEL_LOAD_FAILED, cause=e) from e
            if model is None:
                raise LyricTimingError(
                    CLASS_CODE[CLASS_MODEL_LOAD_FAILED],
                    "faster-whisper loader returned no model",
                    CLASS_MODEL_LOAD_FAILED)
            self.model = model
            self.loads += 1

    def _guard(self):
        memory_guard(self.model_size, free_gb_probe=self._free_gb_probe)

    def _transcribe_track(self, track: Dict[str, Any]) -> Dict[str, Any]:
        """One track through the supported call contract. The audio path is a
        REAL file path -- a track without one refuses
        (``missing-audio-path``), it is never invented."""
        path = _audio_path_of(track)
        transcribe = getattr(self.model, "transcribe", None)
        if not callable(transcribe):
            raise LyricTimingError(
                CLASS_CODE[CLASS_BAD_CALL_SIGNATURE],
                "loaded model %r exposes no callable "
                "transcribe(audio_path, word_timestamps=True)"
                % type(self.model).__name__, CLASS_BAD_CALL_SIGNATURE)
        try:
            result = transcribe(path, word_timestamps=True)
        except TypeError as e:  # wrong call shape is its own class (D25)
            raise LyricTimingError(
                CLASS_CODE[CLASS_BAD_CALL_SIGNATURE],
                "model.transcribe call signature refused: %s" % e,
                CLASS_BAD_CALL_SIGNATURE, cause=e) from e
        except LyricTimingError:
            raise
        except Exception as e:  # noqa: BLE001 - decode failure is typed
            raise LyricTimingError(
                CLASS_CODE[CLASS_TRANSCRIBE_FAILED],
                "transcription failed for %s: %s"
                % (os.path.basename(path), _redact(e, 120)),
                CLASS_TRANSCRIBE_FAILED, cause=e) from e
        segs = _segments_from_result(result)
        return {"task_id": (track or {}).get("task_id"),
                "audio_id": (track or {}).get("audio_id"),
                "audio_path": path, "segments": segs}

    def transcribe_all(self,
                       tracks: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Every track one after another in this single loaded model."""
        with _LG.heavy_slot("transcription"):      # machine-wide gate: model load + decode
            self._ensure_loaded()
            out = []
            for t in tracks or []:
                out.append(self._transcribe_track(t))
            return out

    @staticmethod
    def words_of(tx: Dict[str, Any]) -> List[Dict[str, Any]]:
        """faster-whisper segments -> [{word, start, end}] word timestamps."""
        return words_from_segments((tx or {}).get("segments"))


def _segments_from_result(result: Any) -> List[Any]:
    """``transcribe`` returns ``(segments, info)`` (a generator of segment
    objects); an injected double may return the segment list directly. The
    segments are materialized once so the receipt can carry them."""
    if isinstance(result, tuple) and len(result) == 2:
        result = result[0]
    if result is None:
        return []
    try:
        return list(result)
    except TypeError as e:
        raise LyricTimingError(
            CLASS_CODE[CLASS_BAD_CALL_SIGNATURE],
            "transcribe returned %r, not a (segments, info) pair or a "
            "segment iterable" % type(result).__name__,
            CLASS_BAD_CALL_SIGNATURE, cause=e) from e


def _audio_path_of(track: Any) -> str:
    """The real audio-path handoff: a usable FILE path or a typed refusal.
    Nothing is ever guessed (the old ``dict(t)`` handoff is gone)."""
    t = track if isinstance(track, dict) else {}
    path = t.get("audio_path") or t.get("path")
    try:
        path = os.fspath(path) if isinstance(path, os.PathLike) else path
    except TypeError as e:
        raise LyricTimingError(
            CLASS_CODE[CLASS_AUDIO_PATH_MISSING],
            "track audio path is not a path: %r" % type(path).__name__,
            CLASS_AUDIO_PATH_MISSING, cause=e) from e
    if not isinstance(path, str) or not path.strip():
        raise LyricTimingError(
            CLASS_CODE[CLASS_AUDIO_PATH_MISSING],
            "track carries no audio path (audio_path/path); tier 2 cannot "
            "transcribe without the saved audio",
            CLASS_AUDIO_PATH_MISSING)
    if not os.path.isfile(path):
        raise LyricTimingError(
            CLASS_CODE[CLASS_AUDIO_PATH_MISSING],
            "audio path %s is not a readable file" % _redact(path, 120),
            CLASS_AUDIO_PATH_MISSING)
    return path


def _word_row(w: Any, seg_i: int, row_i: int) -> Dict[str, Any]:
    """One segment/word row -> normalized {word, start, end[, probability]}.

    Accepts dict rows ({word,start,end} / {word,startS,endS}) and real
    faster-whisper word objects (``Word(start, end, word, probability)``).
    Missing or non-numeric timestamps are ``malformed-qc-input`` -- precision
    is never invented."""
    if isinstance(w, dict):
        word = w.get("word")
        s = w.get("start", w.get("startS"))
        e = w.get("end", w.get("endS"))
        p = w.get("probability")
    else:
        word = getattr(w, "word", None)
        s = getattr(w, "start", None)
        e = getattr(w, "end", None)
        p = getattr(w, "probability", None)
    if word is None or s is None or e is None:
        raise LyricTimingError(
            CLASS_CODE[CLASS_MALFORMED_INPUT],
            "word row segment %d word %d carries no word/start/end" % (seg_i, row_i),
            CLASS_MALFORMED_INPUT)
    try:
        s_f, e_f = float(s), float(e)
    except (TypeError, ValueError) as exc:
        raise LyricTimingError(
            CLASS_CODE[CLASS_MALFORMED_INPUT],
            "word row segment %d word %d has non-numeric timestamps"
            % (seg_i, row_i), CLASS_MALFORMED_INPUT, cause=exc) from exc
    row = {"word": str(word).strip(), "start": round(s_f, 3), "end": round(e_f, 3)}
    if isinstance(p, (int, float)):
        row["probability"] = float(p)
    return row


def words_from_segments(segments: Iterable[Any]) -> List[Dict[str, Any]]:
    """Segments shaped [{words:[{word,start,end}]}], real faster-whisper
    segment/word objects, or flat [{word,...}] -> one flat normalized word
    list. A segment carrying no word rows contributes nothing; a word row
    that claims to be a word but is malformed is ``malformed-qc-input``."""
    out: List[Dict[str, Any]] = []
    for i, seg in enumerate(segments or []):
        rows: Optional[List[Any]] = None
        if isinstance(seg, dict):
            if isinstance(seg.get("words"), list):
                rows = seg["words"]
            elif "word" in seg:
                rows = [seg]
        else:
            w = getattr(seg, "words", None)
            if isinstance(w, (list, tuple)):
                rows = list(w)
            elif getattr(seg, "word", None) is not None:
                rows = [seg]
        if rows is None:
            continue
        for j, wr in enumerate(rows):
            out.append(_word_row(wr, i, j))
    return out


def word_confidence(words: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Bounded confidence of measured words (mean source-reported word
    probability). None when the source reports no probabilities -- absence of
    confidence is NOT low confidence."""
    probs = [float(w["probability"]) for w in (words or [])
             if isinstance(w, dict) and isinstance(w.get("probability"),
                                                   (int, float))]
    if not words or not probs:
        return None
    mean = sum(probs) / len(probs)
    return {"mean": round(mean, 3),
            "coverage": round(len(probs) / float(len(words)), 3),
            "floor": CONFIDENCE_FLOOR, "low": mean < CONFIDENCE_FLOOR}


def _confidence_next_actions() -> List[Dict[str, Any]]:
    """Bounded recovery actions for low confidence: ONE remeasure pass, or an
    independent media review. Never regeneration, never a fabricated pass."""
    return [{"action": "remeasure", "bounded": True,
             "max_passes": MAX_REMEASURE_PASSES,
             "note": "re-measure the saved audio; zero music-generation calls"},
            {"action": "independent-media-review",
             "note": "a named reviewer's finding is review evidence, never a "
                     "fabricated measurement"}]
# ── tier 3: cloud speech-to-text, CLIENT key only ───────────────────────────

def client_stt_key(*, key_name: str = "",
                   env: Optional[Dict[str, str]] = None) -> str:
    """Accept only the CLIENT's own cloud-STT key name; refuse operator keys.

    Reads presence only -- the value is never returned. Any operator key
    name handed in refuses by name (OPERATOR_KEY_REFUSED, never its value);
    an unset client key refuses with CLIENT_KEY_MISSING.
    """
    cur = dict(os.environ)
    cur.update(env or {})
    if key_name and key_name != CLIENT_KEY_ENV_NAME:
        raise LyricTimingError(
            "OPERATOR_KEY_REFUSED",
            "%s is not the client's own STT key env var; tier 3 reads %s "
            "only and never an operator key"
            % (key_name or "(empty)", CLIENT_KEY_ENV_NAME))
    if key_name in OPERATOR_KEY_ENV_NAMES or \
            (not key_name and any(k in OPERATOR_KEY_ENV_NAMES for k in cur)
             and not cur.get(CLIENT_KEY_ENV_NAME)):
        named = key_name or ",".join(
            sorted(k for k in OPERATOR_KEY_ENV_NAMES if cur.get(k))[:3])
        raise LyricTimingError(
            "OPERATOR_KEY_REFUSED",
            "tier 3 takes the CLIENT's own cloud speech key (%s only); "
            "operator keys %s are refused by name and value"
            % (CLIENT_KEY_ENV_NAME, named))
    if not cur.get(CLIENT_KEY_ENV_NAME):
        raise LyricTimingError(
            "CLIENT_KEY_MISSING",
            "%s is not set: tier 3 needs the client's own cloud speech "
            "key (word timestamps); set it in the client's secrets env "
            "before this fallback fires" % CLIENT_KEY_ENV_NAME)
    return CLIENT_KEY_ENV_NAME


def cloud_stt_word_timings(track: Dict[str, Any], *, key_name: str = "",
                           env: Optional[Dict[str, str]] = None,
                           provider_fn: Optional[Callable[
                               [str, Dict[str, Any]], List[Dict[str, Any]]]] = None,
                           ) -> Dict[str, Any]:
    """Tier 3 receipt: client-key gate first, then the injected provider."""
    name = client_stt_key(key_name=key_name, env=env)
    if provider_fn:
        words = provider_fn(name, track)
    else:
        words = words_from_segments((track or {}).get("segments"))
    if not words:
        raise LyricTimingError(
            "CLOUD_STT_EMPTY",
            "cloud speech-to-text returned zero word timestamps; word "
            "timings stay unanswered (fail-closed)",
            CLASS_TIMESTAMPS_UNAVAILABLE)
    return _receipt(SOURCE_CLOUD_STT, words, track,
                    {"tier": 3, "stt_key_env": name,
                     "cloud_provider": "client-configured"})


# ── receipt shaping ──────────────────────────────────────────────────────────

def _provider(source: str) -> str:
    return {"suno-timestamped-lyrics": "suno (KIE timeStamped-lyrics)",
            "faster-whisper-local": "faster-whisper",
            "cloud-stt": "client cloud STT"}.get(source, source)


def _receipt(source: str, words: List[Dict[str, Any]], track: Any,
             detail: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The step's receipt: which source produced the timing, the words, and
    how many local models loaded (0 for tiers 1 and 3)."""
    rec = {"schema_version": SCHEMA_VERSION, "tool": TOOL_NAME,
           "tool_version": TOOL_VERSION, "source": source,
           "transcription_provider": _provider(source),
           "words": list(words or []),
           "local_model_loads": 1 if source == SOURCE_WHISPER_LOCAL else 0,
           "track": {"task_id": track.get("task_id")
                     if isinstance(track, dict) else None,
                     "audio_id": track.get("audio_id")
                     if isinstance(track, dict) else None}}
    if detail:
        rec["evidence"] = dict(detail)
    return rec


# ── the ONE entry every consumer calls ───────────────────────────────────────

def provide_word_timings(track: Dict[str, Any], *,
                         timing_map_hint: Optional[Dict[str, Any]] = None,
                         dispatcher: Optional[Callable[..., Dict[str, Any]]] = None,
                         whisper_loader: Optional[Callable[..., Any]] = None,
                         whisper_session: Optional[WhisperSession] = None,
                         cloud: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
                         ledger_db: str = "", run_id: str = "",
                         card_receipt: Optional[Dict[str, Any]] = None,
                         ) -> Dict[str, Any]:
    """ONE transcription step for lyric check / captions / lip-sync windows /
    talk-sing split. Tier 1 -> 2 -> 3, receipt records the source.

    ``timing_map_hint``: a caller-kept timing map that already carries the
    Suno alignedWords (hint key "alignedWords" or normalized "words") -- a
    complete hint skips dispatch and still stamps
    ``source: suno-timestamped-lyrics`` with zero local loads.

    Returns ``{"ok": True, "timings": <receipt>}`` or
    ``{"ok": False, "error_code": ..., "next_action": ...}``; never raises to
    a consumer. A failure carries the FULL typed envelope under ``"error"``
    (causal chain preserved, bounded and redacted) plus the distinct
    ``failure_class``; ``error_code`` is the distinct boundary code (D25).
    ``counts.music_generation_calls`` is 0 on every outcome -- this step
    never generates music. Multi-track runs pass ONE ``whisper_session`` so
    tier 2 shows exactly one model load for the whole run.
    """
    # ── tier 1 (complete hint path: zero dispatch, zero local loads) ──
    if timing_map_hint:
        try:
            words = _aligned_from_doc(timing_map_hint) or \
                normalize_aligned_words((timing_map_hint or {}).get("words"))
        except LyricTimingError:
            words = []
        if words:
            return {"ok": True, "timings": _receipt(
                SOURCE_SUNO, words, track,
                {"tier": 1, "payload": TIER1_PAYLOAD_SOURCE, "hint": True,
                 "counts": {"music_generation_calls": 0,
                            "paid_analysis_calls": 0}})}

    # ── tier 1 (dispatch path) ──
    t1_err: Optional[LyricTimingError] = None
    try:
        got = fetch_suno_timestamped_lyrics(
            track, dispatcher=dispatcher, ledger_db=ledger_db, run_id=run_id,
            card_receipt=card_receipt)
        try:
            words = normalize_aligned_words(got["words"])
        except LyricTimingError as e:
            words = []  # alignment unusable -> counts as a tier-1 failure
            t1_err = e
        if words:
            return {"ok": True, "timings": _receipt(
                SOURCE_SUNO, words, track, dict(got["evidence"], counts={
                    "music_generation_calls": 0, "paid_analysis_calls": 1}))}
        if t1_err is None:
            t1_err = LyricTimingError(
                "SUNO_ALIGNMENT_MISSING",
                "tier 1 returned no usable alignedWords", CLASS_MALFORMED_INPUT)
    except LyricTimingError as e:
        t1_err = e
    t1_code = t1_err.code if t1_err else "SUNO_ALIGNMENT_MISSING"

    # ── tier 2: exactly ONE local model per session, one track after another ──
    try:
        sess = whisper_session or WhisperSession(loader=whisper_loader)
        tx = sess.transcribe_all([track or {}])
        words = sess.words_of(tx[-1])
        if not words:
            raise LyricTimingError(
                CLASS_CODE[CLASS_TIMESTAMPS_UNAVAILABLE],
                "faster-whisper returned zero word timestamps; tier 3 is "
                "the last resort", CLASS_TIMESTAMPS_UNAVAILABLE)
        conf = word_confidence(words)
        ev = {"tier": 2, "loads": sess.loads, "model_size": sess.model_size,
              "compute_type": sess.compute_type, "tier1_error": t1_code,
              "confidence": conf,
              "counts": {"music_generation_calls": 0,
                         "paid_analysis_calls": 0}}
        out = {"ok": True, "timings": _receipt(
            SOURCE_WHISPER_LOCAL, words, track, ev)}
        if conf and conf.get("low"):
            # Classifier uncertainty is NOT a definite creative failure:
            # keep the measured words, trigger bounded recovery (D25/D26).
            out["low_confidence"] = True
            out["next_actions"] = _confidence_next_actions()
        return out
    except LyricTimingError as e:
        t2 = e
    except Exception as e:  # noqa: BLE001 - a crashing fallback is a failure
        t2 = LyricTimingError(
            CLASS_CODE[CLASS_TRANSCRIBE_FAILED],
            "tier 2 crashed: %s" % _redact(e, 160),
            CLASS_TRANSCRIBE_FAILED, cause=e)

    # ── tier 3: both earlier tiers failed ──
    fail = {"ok": False, "error_code": t2.boundary_code(),
            "failure_class": t2.failure_class,
            "error": t2.envelope(),
            "counts": {"music_generation_calls": 0, "paid_analysis_calls": 0},
            "evidence": {"tier1_error": t1_code,
                         "tier2_error": t2.code,
                         "tier1_error_envelope":
                             t1_err.envelope() if t1_err else None,
                         "tier2_error_envelope": t2.envelope()}}
    if cloud is None:
        fail["next_action"] = (
            "tier 1 (%s) and tier 2 (%s: %s) both failed; NO paid music was "
            "generated for this failure (music_generation_calls 0). Recover "
            "without generation: remeasure the saved audio (one bounded "
            "pass), request an independent media review, wire the client's "
            "own cloud STT (word timestamps, client key only), or enable the "
            "local fallback (PREREQS faster-whisper-optional)"
            % (t1_code, t2.code, t2.failure_class or "unknown"))
        return fail
    try:
        got = cloud(track)
        return {"ok": True, "timings": got,
                "counts": {"music_generation_calls": 0,
                           "paid_analysis_calls": 0}}
    except LyricTimingError as e:
        fail["error_code"] = e.boundary_code()
        fail["failure_class"] = e.failure_class
        fail["error"] = e.envelope()
        fail["evidence"]["tier3_error"] = e.code
        fail["next_action"] = str(e)
        return fail
    except Exception as e:  # noqa: BLE001
        fail["error_code"] = "CLOUD_STT_ERROR"
        fail["failure_class"] = CLASS_TRANSCRIBE_FAILED
        fail["error"] = {"code": "CLOUD_STT_ERROR",
                         "error_type": type(e).__name__,
                         "detail": _redact(e)}
        fail["evidence"]["tier3_error"] = "CLOUD_STT_ERROR"
        fail["next_action"] = _redact(e)
        return fail
# ── non-generating operations (D26): validate / migrate / remeasure /
#    rejudge / reconcile over EXISTING artifacts ─────────────────────────────

def audio_sha256(path: str) -> str:
    """sha256 of the audio file bytes -- the identity a remeasure must leave
    unchanged."""
    apath = _audio_path_of({"audio_path": path})
    h = hashlib.sha256()
    try:
        with open(apath, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError as e:
        raise LyricTimingError(
            CLASS_CODE[CLASS_AUDIO_PATH_MISSING],
            "audio path %s cannot be read: %s" % (_redact(apath, 120), e),
            CLASS_AUDIO_PATH_MISSING, cause=e) from e
    return h.hexdigest()


def _qc_bad(where: str, why: str, cause: Optional[BaseException] = None):
    raise LyricTimingError(
        CLASS_CODE[CLASS_MALFORMED_INPUT],
        "malformed QC input at %s: %s" % (where, why),
        CLASS_MALFORMED_INPUT, cause=cause)


def validate_record(record: Any) -> Dict[str, Any]:
    """Schema-shape validation of ONE saved timing/QC record at its own
    boundary. Wrong shape -> ``malformed-qc-input`` naming the exact spot.
    Content problems (inverted spans) survive as data -- ``rejudge`` judges
    them; validation never silently rewrites."""
    if not isinstance(record, dict):
        _qc_bad("record", "expected an object, got %s"
                % type(record).__name__)
    words = record.get("words", [])
    if not isinstance(words, list):
        _qc_bad("words", "expected a list, got %s" % type(words).__name__)
    for i, w in enumerate(words):
        if not isinstance(w, dict):
            _qc_bad("words[%d]" % i, "expected an object, got %s"
                    % type(w).__name__)
        for key in ("word", "start", "end"):
            if key not in w:
                _qc_bad("words[%d]" % i, "missing %r" % key)
        for key in ("start", "end"):
            if not isinstance(w[key], (int, float)) or isinstance(w[key], bool):
                try:
                    float(w[key])
                except (TypeError, ValueError) as exc:
                    _qc_bad("words[%d].%s" % (i, key),
                            "non-numeric timestamp %r" % (w[key],), exc)
    audio = record.get("audio")
    if audio is not None:
        if not isinstance(audio, dict):
            _qc_bad("audio", "expected an object, got %s"
                    % type(audio).__name__)
        if "path" in audio and not isinstance(audio["path"], str):
            _qc_bad("audio.path", "expected a string path")
        if "sha256" in audio and audio["sha256"] is not None \
                and not isinstance(audio["sha256"], str):
            _qc_bad("audio.sha256", "expected a hex digest string")
    source = record.get("source")
    if source is not None and not isinstance(source, str):
        _qc_bad("source", "expected a string provenance tag")
    return record


def read_records(payload: Any) -> List[Dict[str, Any]]:
    """Schema-specific object/list reader (D25: a dict-only helper cannot
    read a list of QC records). Accepts one record, a LIST of records, or
    ``{"records": [...]}``; anything else is an explicit
    ``malformed-qc-input`` naming the shapes it accepts. An empty list is
    valid."""
    if isinstance(payload, list):
        return [validate_record(r) for r in payload]
    if isinstance(payload, dict):
        if "records" in payload:
            rows = payload["records"]
            if not isinstance(rows, list):
                _qc_bad("records", "expected a list, got %s"
                        % type(rows).__name__)
            return [validate_record(r) for r in rows]
        return [validate_record(payload)]
    _qc_bad("payload",
            "expected a record object, a record list, or "
            '{"records": [...]}, got %s' % type(payload).__name__)


def migrate_record(record: Any) -> Dict[str, Any]:
    """Version migration of one saved record through the canonical shape.

    Preserves approved words, performance tags and unknown fields verbatim;
    maps legacy ``startS``/``endS`` rows to ``start``/``end`` (values
    unchanged). Any semantic difference that needs a human (conflicting
    keys, coercions) is REPORTED in ``semantic_differences``, never silently
    resolved. A record lacking provider-envelope fields is not thereby
    obsolete -- absence of optional fields is never an error here."""
    if not isinstance(record, dict):
        _qc_bad("record", "expected an object, got %s"
                % type(record).__name__)
    out = dict(record)
    semantic: List[str] = []
    rows = out.get("words", [])
    if not isinstance(rows, list):
        _qc_bad("words", "expected a list, got %s" % type(rows).__name__)
    new_rows: List[Dict[str, Any]] = []
    for i, w in enumerate(rows):
        if isinstance(w, (tuple, list)) and len(w) == 3:
            w = {"word": w[0], "start": w[1], "end": w[2]}
            semantic.append("words[%d]: triple form mapped to canonical keys"
                            % i)
        if not isinstance(w, dict):
            _qc_bad("words[%d]" % i, "expected an object, got %s"
                    % type(w).__name__)
        row = dict(w)
        for old, new in (("startS", "start"), ("endS", "end")):
            if old in row:
                if new in row and row[new] != row[old]:
                    semantic.append(
                        "words[%d].%s: %r conflicts with %s %r; canonical "
                        "%s kept -- review" % (i, old, row[old], new,
                                               row[new], new))
                else:
                    row.setdefault(new, row[old])
                    semantic.append(
                        "words[%d].%s mapped to %s (values unchanged)"
                        % (i, old, new))
                row.pop(old, None)
        for key in ("word", "start", "end"):
            if key not in row:
                _qc_bad("words[%d]" % i, "missing %r after migration" % key)
        for key in ("start", "end"):
            try:
                val = float(row[key])
            except (TypeError, ValueError) as exc:
                _qc_bad("words[%d].%s" % (i, key),
                        "non-numeric timestamp %r" % (row[key],), exc)
            if val != row[key]:
                semantic.append(
                    "words[%d].%s: coerced %r to %r (value unchanged)"
                    % (i, key, row[key], val))
            row[key] = round(val, 3)
        new_rows.append(row)
    out["words"] = new_rows
    from_version = out.get("schema_version")
    out["schema_version"] = SCHEMA_VERSION
    if from_version not in (None, SCHEMA_VERSION):
        out["migrated_from_schema_version"] = from_version
        semantic.append("schema_version %r migrated to %r"
                        % (from_version, SCHEMA_VERSION))
    out["migration"] = {"tool_version": TOOL_VERSION,
                        "changed": bool(semantic) or from_version != SCHEMA_VERSION,
                        "semantic_differences": semantic}
    return out


def remeasure_saved_audio(audio_path: str, *,
                          record: Optional[Dict[str, Any]] = None,
                          whisper_session: Optional[WhisperSession] = None,
                          model_size: str = DEFAULT_WHISPER_SIZE,
                          free_gb_probe: Optional[Callable[[], float]] = None,
                          dispatcher: Optional[Callable[..., Dict[str, Any]]] = None,
                          allow_paid_analysis: bool = False,
                          ledger_db: str = "", run_id: str = "remeasure-analysis",
                          card_receipt: Optional[Dict[str, Any]] = None,
                          ) -> Dict[str, Any]:
    """Re-measure EXISTING audio (D26). Zero new music-generation requests,
    ever: nothing in this path can generate music, and
    ``counts.music_generation_calls`` is 0 on the receipt.

    Uses the saved audio (sha256 before == after; a changed hash refuses with
    ``AUDIO_HASH_CHANGED``) and the record's provider provenance
    (task_id/audio_id). ONE local model load, governed (memory_guard +
    heavy_slot). The only paid call that can be involved is the existing
    timestamped-lyrics ANALYSIS through the authorized dispatcher, and only
    when ``allow_paid_analysis=True`` AND a dispatcher is wired (separately
    counted as ``counts.paid_analysis_calls``, never a generation)."""
    if record is not None:
        record = validate_record(record)
    before = audio_sha256(audio_path)
    track: Dict[str, Any] = {"audio_path": audio_path}
    if record:
        prov = record.get("track") or record.get("provenance") or {}
        for k in ("task_id", "audio_id", "generation_id", "card_receipt",
                  "save_dir", "callback_url"):
            if prov.get(k) is not None:
                track[k] = prov[k]
    session = whisper_session or WhisperSession(
        model_size=model_size, free_gb_probe=free_gb_probe)
    tx = session.transcribe_all([track])
    words = session.words_of(tx[-1])
    paid_analysis = 0
    if not words and allow_paid_analysis and dispatcher is not None:
        # Necessary paid ANALYSIS on the existing generation -- authorized,
        # separately ledgered (stage "word-timings"), never generation.
        got = fetch_suno_timestamped_lyrics(
            track, dispatcher=dispatcher, ledger_db=ledger_db, run_id=run_id,
            card_receipt=card_receipt)
        words = normalize_aligned_words(got["words"])
        paid_analysis = 1
    after = audio_sha256(audio_path)
    if after != before:
        raise LyricTimingError(
            "AUDIO_HASH_CHANGED",
            "saved audio changed during remeasure (sha256 %s -> %s); the "
            "measurement is refused and nothing is overwritten"
            % (before[:12], after[:12]), CLASS_MALFORMED_INPUT)
    if not words:
        raise LyricTimingError(
            CLASS_CODE[CLASS_TIMESTAMPS_UNAVAILABLE],
            "remeasure produced zero word timestamps for %s"
            % _redact(os.path.basename(audio_path), 80),
            CLASS_TIMESTAMPS_UNAVAILABLE)
    conf = word_confidence(words)
    receipt = {
        "schema_version": SCHEMA_VERSION, "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION, "operation": "remeasure",
        "source": SOURCE_WHISPER_LOCAL,
        "transcription_provider": _provider(SOURCE_WHISPER_LOCAL),
        "words": words, "local_model_loads": session.loads,
        "audio": {"path": audio_path, "sha256_before": before,
                  "sha256_after": after, "unchanged": True},
        "provenance": {"task_id": track.get("task_id"),
                       "audio_id": track.get("audio_id"),
                       "provider":
                           (record or {}).get("transcription_provider")},
        "counts": {"music_generation_calls": 0,
                   "paid_analysis_calls": paid_analysis,
                   "local_model_loads": session.loads},
        "confidence": conf,
    }
    if conf and conf.get("low"):
        receipt["low_confidence"] = True
        receipt["next_actions"] = _confidence_next_actions()
    return receipt


def rejudge_saved(record: Any, *,
                  confidence_floor: float = CONFIDENCE_FLOOR
                  ) -> Dict[str, Any]:
    """Re-decide from SAVED measurements (D26): zero provider calls, zero
    model loads -- this function takes no dispatcher and no loader at all.

    Verdicts: ``pass``; ``fail`` ONLY for a definite structural defect
    (inverted span); ``needs-remeasure`` when no measurement exists (bounded,
    one pass); ``needs-review`` on LOW CONFIDENCE -- classifier uncertainty
    is never relabeled as a definite creative failure."""
    rec = validate_record(record)
    words = rec.get("words") or []
    inverted = [i for i, w in enumerate(words)
                if float(w["end"]) + 1e-9 < float(w["start"])]
    if inverted:
        return {"verdict": "fail", "reason_code": "SPAN_INVERTED",
                "detail": "words %s end before start (definite measurement "
                          "defect)" % inverted[:5],
                "confidence": word_confidence(words),
                "provider_calls": 0, "music_generation_calls": 0}
    if not words:
        return {"verdict": "needs-remeasure",
                "reason_code": "NO_WORD_TIMESTAMPS",
                "detail": "no saved word measurements; remeasure the saved "
                          "audio (one bounded pass) -- absence of a "
                          "measurement is not a creative failure",
                "next_actions": _confidence_next_actions(),
                "provider_calls": 0, "music_generation_calls": 0}
    conf = word_confidence(words)
    if conf and conf["mean"] < confidence_floor:
        return {"verdict": "needs-review", "reason_code": "LOW_CONFIDENCE",
                "detail": "mean word probability %.3f < floor %.2f; "
                          "classifier uncertainty is NOT a definite creative "
                          "failure" % (conf["mean"], confidence_floor),
                "confidence": conf,
                "next_actions": _confidence_next_actions(),
                "provider_calls": 0, "music_generation_calls": 0}
    return {"verdict": "pass", "reason_code": "MEASUREMENT_ACCEPTED",
            "confidence": conf, "words_checked": len(words),
            "provider_calls": 0, "music_generation_calls": 0}


def reconcile_records(records: Any,
                      audio_path: Optional[str] = None) -> Dict[str, Any]:
    """Compare EXISTING records against the audio on disk (hash + provenance)
    and REPORT. Never rewrites, never re-measures, never generates. A hash
    mismatch is reported as data for the operator, not silently repaired."""
    rows = read_records(records)
    out_rows: List[Dict[str, Any]] = []
    mismatches = 0
    for i, rec in enumerate(rows):
        audio = rec.get("audio") or {}
        path = audio.get("path") or (audio_path or "")
        stored = audio.get("sha256") or rec.get("audio_sha256")
        row: Dict[str, Any] = {"index": i, "path": path or None,
                               "stored_sha256": stored,
                               "provenance": rec.get("track")
                               or rec.get("provenance")}
        if not path:
            row["status"] = "no-audio-path"
        elif not os.path.isfile(path):
            row["status"] = "audio-missing"
        else:
            current = audio_sha256(path)
            row["current_sha256"] = current
            if not stored:
                row["status"] = "no-stored-hash"
            elif stored == current:
                row["status"] = "match"
            else:
                row["status"] = "mismatch"
        if row["status"] in ("mismatch", "audio-missing"):
            mismatches += 1
        out_rows.append(row)
    return {"operation": "reconcile", "rows": out_rows,
            "checked": len(out_rows), "mismatches": mismatches,
            "counts": {"music_generation_calls": 0,
                       "paid_analysis_calls": 0}}
# ── the module CLI (the non-generating operations above, exposed) ──────────

_CLI_USAGE = """usage: lyric_timing.py <command> [args]

  selftest
  validate  <record.json>|- [--out F]
  migrate   <record.json>|- [--out F]
  rejudge   <record.json>|- [--out F] [--floor X]
  remeasure --audio A.wav [--record R.json] [--out F] [--model-size S]
            [--allow-paid-analysis]
  reconcile [--audio A.wav] <record.json> [<record.json> ...]

exit contract: 0 accepting result, 5 ("rejected") the result refuses
acceptance (typed refusal, verdict fail/needs-remeasure/needs-review,
remeasure without words or with a changed hash, reconcile mismatch),
1 ("error") the operation itself could not run. Every run prints JSON with
"ok" plus the verdict or the full typed error envelope."""


def _read_json_arg(path: str) -> Any:
    import json as _json
    if path == "-":
        return _json.load(sys.stdin)
    with open(path, "r", encoding="utf-8") as fh:
        return _json.load(fh)


def _emit(obj: Any, out_path: str = "") -> None:
    import json as _json
    text = _json.dumps(obj, indent=2, sort_keys=True)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)


def _cli(argv: Sequence[str]) -> int:
    args = list(argv[1:])
    if not args or args[0] in ("-h", "--help", "help"):
        print(_CLI_USAGE)
        return EXIT["ok"] if args else EXIT["error"]
    cmd, rest = args[0], args[1:]
    out_path, floor, audio, record_path, model_size = "", None, "", "", \
        DEFAULT_WHISPER_SIZE
    allow_paid = False
    positional: List[str] = []
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--out" and i + 1 < len(rest):
            out_path = rest[i + 1]; i += 2
        elif a == "--floor" and i + 1 < len(rest):
            floor = float(rest[i + 1]); i += 2
        elif a == "--audio" and i + 1 < len(rest):
            audio = rest[i + 1]; i += 2
        elif a == "--record" and i + 1 < len(rest):
            record_path = rest[i + 1]; i += 2
        elif a == "--model-size" and i + 1 < len(rest):
            model_size = rest[i + 1]; i += 2
        elif a == "--allow-paid-analysis":
            allow_paid = True; i += 1
        elif a.startswith("--"):
            raise SystemExit("unknown option %s\n%s" % (a, _CLI_USAGE))
        else:
            positional.append(a); i += 1
    try:
        if cmd == "selftest":
            return _selftest()
        if cmd == "validate":
            if not positional:
                raise SystemExit("validate needs <record.json>|-\n" + _CLI_USAGE)
            rec = validate_record(_read_json_arg(positional[0]))
            _emit({"ok": True, "verdict": "pass", "record": rec}, out_path)
            return EXIT["ok"]
        if cmd == "migrate":
            if not positional:
                raise SystemExit("migrate needs <record.json>|-\n" + _CLI_USAGE)
            rec = migrate_record(_read_json_arg(positional[0]))
            mig = rec.pop("migration", {})
            _emit({"ok": True, "record": rec, "changed": mig.get("changed"),
                   "semantic_differences": mig.get("semantic_differences")},
                  out_path)
            return EXIT["ok"]
        if cmd == "rejudge":
            if not positional:
                raise SystemExit("rejudge needs <record.json>|-\n" + _CLI_USAGE)
            kw = {} if floor is None else {"confidence_floor": floor}
            res = rejudge_saved(_read_json_arg(positional[0]), **kw)
            _emit({"ok": True, "rejudge": res}, out_path)
            return EXIT["ok"] if res["verdict"] == "pass" else EXIT["rejected"]
        if cmd == "remeasure":
            if not audio:
                raise SystemExit("remeasure needs --audio\n" + _CLI_USAGE)
            rec = _read_json_arg(record_path) if record_path else None
            got = remeasure_saved_audio(
                audio, record=rec, model_size=model_size,
                allow_paid_analysis=allow_paid, dispatcher=None)
            _emit({"ok": True, "remeasure": got}, out_path)
            return EXIT["ok"]
        if cmd == "reconcile":
            if not positional:
                raise SystemExit("reconcile needs <record.json>...\n" + _CLI_USAGE)
            payload = []
            for p in positional:
                payload.extend(read_records(_read_json_arg(p)))
            res = reconcile_records(payload, audio_path=audio or None)
            _emit({"ok": True, "reconcile": res}, out_path)
            return EXIT["ok"] if res["mismatches"] == 0 else EXIT["rejected"]
        raise SystemExit("unknown command %r\n%s" % (cmd, _CLI_USAGE))
    except SystemExit:
        raise
    except LyricTimingError as e:
        # A typed refusal stays a refusal (exit 5), with the causal envelope.
        _emit({"ok": False, "error_code": e.boundary_code(),
               "failure_class": e.failure_class, "error": e.envelope(),
               "counts": {"music_generation_calls": 0,
                          "paid_analysis_calls": 0}}, out_path)
        return EXIT["rejected"]
    except Exception as e:  # noqa: BLE001 - the operation could not run
        _emit({"ok": False, "error_code": "CLI_ERROR",
               "error": {"error_type": type(e).__name__,
                         "detail": _redact(e)}}, out_path)
        return EXIT["error"]


def _selftest():
    """One runnable check: the tier ladder holds on mocked data, the typed
    causal envelope survives the saved record, and rejudge never turns
    classifier uncertainty into a definite failure."""
    import json
    import sys
    import tempfile
    import types

    tmp = tempfile.mkdtemp(prefix="lyric-timing-selftest-")
    doc = os.path.join(tmp, "aligned.json")
    with open(doc, "w", encoding="utf-8") as f:
        json.dump({"alignedWords": [{"word": "hello", "startS": 1.0,
                                     "endS": 1.4}]}, f)

    sent = []

    def fake_dispatcher(**kw):
        sent.append(kw["request"])
        return {"outcome": "ok", "reason_code": "KIE_DISPATCH_OK",
                "evidence": {"saved_paths": [doc]}}

    got = provide_word_timings({"task_id": "t1", "audio_id": "a1"},
                               dispatcher=fake_dispatcher)
    assert got["ok"] and got["timings"]["source"] == SOURCE_SUNO
    assert got["timings"]["local_model_loads"] == 0
    assert got["timings"]["words"][0]["word"] == "hello"
    print("ok lyric_timing selftest: tier 1 without local loads")

    # Card receipt threads into the timing request; the real card gate
    # passes it, and a receipt-less request still refuses CARD_UNANSWERED.
    from kie_dispatch import kie_dispatch as KD
    card = {"answers": {"video_style": "Lifelike 3D", "audio_style": "Soul Ballad",
                        "length": 60, "video_model": "MiniMax H3 768P"},
            "who": "selftest", "at": "2026-10-08T09:00:00Z"}
    provide_word_timings({"task_id": "t1", "audio_id": "a1"},
                         dispatcher=fake_dispatcher, card_receipt=card)
    assert sent[-1]["card_receipt"] is card
    assert KD.card_gate_refusal(sent[-1]) is None
    assert "card_receipt" not in sent[0]
    assert KD.card_gate_refusal(sent[0])["reason_code"] == "CARD_UNANSWERED"
    print("ok lyric_timing selftest: card receipt threaded; gate still refuses without one")

    # Typed causal chain survives the saved record (D25).
    probe = LyricTimingError("LOCAL_MODEL_LOAD_REFUSED", "free 1.00 GB",
                             CLASS_LOW_MEMORY)
    cause = LyricTimingError(CLASS_CODE[CLASS_DEPENDENCY_MISSING],
                             "faster_whisper missing", CLASS_DEPENDENCY_MISSING)
    err = LyricTimingError(CLASS_CODE[CLASS_MODEL_LOAD_FAILED], "load blew up",
                           CLASS_MODEL_LOAD_FAILED, cause=cause)
    saved = save_error_record(os.path.join(tmp, "err.json"), err)
    back = read_error_record(os.path.join(tmp, "err.json"))
    assert back["failure_class"] == CLASS_MODEL_LOAD_FAILED
    assert back["cause"]["failure_class"] == CLASS_DEPENDENCY_MISSING
    assert probe.boundary_code() == "LOCAL_MODEL_LOW_MEMORY"
    assert saved["category"] == "provider"
    print("ok lyric_timing selftest: typed causal chain survives the saved record")

    # Rejudge: low confidence is needs-review, never a definite failure.
    low = rejudge_saved({"words": [{"word": "a", "start": 0.0, "end": 0.4,
                                    "probability": 0.2}]})
    assert low["verdict"] == "needs-review" and low["music_generation_calls"] == 0
    ok = rejudge_saved({"words": [{"word": "a", "start": 0.0, "end": 0.4,
                                   "probability": 0.95}]})
    assert ok["verdict"] == "pass"
    print("ok lyric_timing selftest: low confidence -> needs-review, never fail")

    # The production fallback loader runs on an actual audio path with NO
    # injected test loader (the D18 counterexample).
    audio = os.path.join(tmp, "take.wav")
    with open(audio, "wb") as f:
        f.write(b"RIFF....WAVEfmt ")

    class _Word:
        def __init__(self, w, s, e, p):
            self.word, self.start, self.end, self.probability = w, s, e, p

    class _Seg:
        def __init__(self, words):
            self.words = words

    class _Model:
        def transcribe(self, path, word_timestamps=False):
            assert word_timestamps is True and path == audio
            return iter([_Seg([_Word("hello", 1.0, 1.4, 0.9)])]), object()

    mod = types.ModuleType("faster_whisper")
    mod.WhisperModel = lambda size, device="cpu", compute_type="int8": _Model()
    sys.modules["faster_whisper"] = mod
    try:
        sess = WhisperSession(free_gb_probe=lambda: 16.0)
        tx = sess.transcribe_all([{"task_id": "t1", "audio_path": audio}])
        words = sess.words_of(tx[0])
        assert sess.loads == 1 and [w["word"] for w in words] == ["hello"]
        assert words[0]["probability"] == 0.9
    finally:
        sys.modules.pop("faster_whisper", None)
    print("ok lyric_timing selftest: production fallback API, actual audio "
          "path, word conversions, ONE governed load")
    return 0


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] not in ("selftest",):
        sys.exit(_cli(sys.argv))
    sys.exit(_selftest())
