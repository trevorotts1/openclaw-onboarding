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

Tier 3 -- only when tiers 1 AND 2 both fail: cloud speech-to-text with word
timestamps, the CLIENT's own key only (env var DRAMA75_CLOUD_STT_API_KEY).
Operator key names (KIE_API_KEY, OPENAI_API_KEY, ...) are refused by name
and the value is never read or returned.

Receipt: every timing receipt carries ``source`` =
"suno-timestamped-lyrics" | "faster-whisper-local" | "cloud-stt" plus
``transcription_provider`` and ``local_model_loads``.

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

Run: python3 core/audio_c3/test_lyric_timing_f17.py
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

SCHEMA_VERSION = "blackceo.audio-c3/lyric-timing/v1"
TOOL_VERSION = "1.0.0"
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


class LyricTimingError(Exception):
    """Machine-code refusal; never a silent pass."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


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
    """
    size = model_size if model_size in WHISPER_SIZES else DEFAULT_WHISPER_SIZE
    model_gb = float(WHISPER_GB[size])
    need = float(reserve_gb) + model_gb
    probe = free_gb_probe or _free_ram_gb
    try:
        free = float(probe())
    except Exception as e:  # noqa: BLE001 - an unreadable machine refuses
        raise LyricTimingError(
            "LOCAL_MODEL_LOAD_REFUSED",
            "load guard cannot measure free RAM (%s); refused before any "
            "local load" % e) from e
    if free != free or free < 0:  # NaN (probe unusable) refuses fail-closed
        raise LyricTimingError(
            "LOCAL_MODEL_LOAD_REFUSED",
            "load guard could not read free RAM; refused before any local "
            "load")
    if free < need:
        raise LyricTimingError(
            "LOCAL_MODEL_LOAD_REFUSED",
            "free %.2f GB < needed %.2f GB (reserve %.1f + %s model %.1f "
            "headroom); a local model load would push the machine past its "
            "limit" % (free, need, reserve_gb, size, model_gb))
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
                "SUNO_ALIGNMENT_BAD", "alignedWords entry %d is not a word" % i)
        try:
            s_f, e_f = float(s), float(e)
        except (TypeError, ValueError):
            raise LyricTimingError(
                "SUNO_ALIGNMENT_BAD",
                "alignedWords entry %d has no numeric startS/endS" % i)
        if e_f + 1e-9 < s_f:
            raise LyricTimingError(
                "SUNO_ALIGNMENT_BAD", "alignedWords entry %d ends before start" % i)
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
        except (OSError, ValueError):
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
                                  attempt_id: str = "") -> Dict[str, Any]:
    """KIE Get Timestamped Lyrics through kie_dispatch (mocked in tests).

    Returns ``{'source': 'suno-alignedWords', 'words': [{word, startS,
    endS}], 'evidence': {...}}``. Every paid-call rule holds: the request
    rides the SAME dispatcher every other stage uses (ledger reserve,
    Skill 74 health/preflight/submit/wait/save), never a private KIE client.
    Raises LyricTimingError on any dispatch failure -- tier-2's trigger.
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
    request = {"model": KIE_MODEL_TIMESTAMPED_LYRICS,
               "input": {"task_id": task_id or "", "audio_id": audio_id or ""},
               "callBackUrl": (track or {}).get("callback_url", "")}
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

    The loader is injected (tests fake it; the real one is
    ``from faster_whisper import WhisperModel`` -- the only permitted import
    string). ``loads`` counts model loads; a multi-track run through ONE
    session shows exactly 1. Part D's load guard fires before the load and
    refuses with LOCAL_MODEL_LOAD_REFUSED when free RAM is short.
    """

    def __init__(self, *, loader: Optional[Callable[..., Any]] = None,
                 model_size: str = DEFAULT_WHISPER_SIZE,
                 compute_type: str = "int8",
                 free_gb_probe: Optional[Callable[[], float]] = None):
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
        self.model_size = model_size
        self.compute_type = compute_type
        self._free_gb_probe = free_gb_probe
        self.model: Any = None
        self.loads = 0

    def _ensure_loaded(self):
        self._guard()
        if self.model is None:
            if self._loader is None:
                raise LyricTimingError(
                    "LOCAL_MODEL_LOAD_REFUSED",
                    "no faster-whisper loader wired (PREREQS "
                    "faster-whisper-optional: install only when this "
                    "fallback is enabled)")
            self.model = self._loader(self.model_size, self.compute_type)
            self.loads += 1

    def _guard(self):
        memory_guard(self.model_size, free_gb_probe=self._free_gb_probe)

    def transcribe_all(self,
                       tracks: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Every track one after another in this single loaded model."""
        self._ensure_loaded()
        out = []
        for t in tracks or []:
            segs = self.model(t.get("audio_path", "") or dict(t))
            tx = {"task_id": (t or {}).get("task_id"),
                  "audio_id": (t or {}).get("audio_id"), "segments": segs}
            out.append(tx)
        return out

    @staticmethod
    def words_of(tx: Dict[str, Any]) -> List[Dict[str, Any]]:
        """faster-whisper segments -> [{word, start, end}] word timestamps."""
        return words_from_segments((tx or {}).get("segments"))


def words_from_segments(segments: Iterable[Any]) -> List[Dict[str, Any]]:
    """Segments shaped [{words:[{word,start,end}]}] or flat [{word,...}]
    -> one flat normalized word list."""
    out: List[Dict[str, Any]] = []
    for seg in segments or []:
        if isinstance(seg, dict) and isinstance(seg.get("words"), list):
            for w in seg["words"]:
                if isinstance(w, dict) and "word" in w:
                    out.append({"word": str(w["word"]).strip(),
                                "start": float(w.get("start", 0.0)),
                                "end": float(w.get("end", 0.0))})
        elif isinstance(seg, dict) and "word" in seg:
            out.append({"word": str(seg["word"]).strip(),
                        "start": float(seg.get("start", 0.0)),
                        "end": float(seg.get("end", 0.0))})
    return out


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
            "timings stay unanswered (fail-closed)")
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
                         ) -> Dict[str, Any]:
    """ONE transcription step for lyric check / captions / lip-sync windows /
    talk-sing split. Tier 1 -> 2 -> 3, receipt records the source.

    ``timing_map_hint``: a caller-kept timing map that already carries the
    Suno alignedWords (hint key "alignedWords" or normalized "words") -- a
    complete hint skips dispatch and still stamps
    ``source: suno-timestamped-lyrics`` with zero local loads.

    Returns ``{"ok": True, "timings": <receipt>}`` or
    ``{"ok": False, "error_code": ..., "next_action": ...}``; never raises to
    a consumer. Multi-track runs pass ONE ``whisper_session`` so tier 2 shows
    exactly one model load for the whole run.
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
                {"tier": 1, "payload": TIER1_PAYLOAD_SOURCE, "hint": True})}

    # ── tier 1 (dispatch path) ──
    try:
        got = fetch_suno_timestamped_lyrics(
            track, dispatcher=dispatcher, ledger_db=ledger_db, run_id=run_id)
        try:
            words = normalize_aligned_words(got["words"])
        except LyricTimingError:
            words = []  # alignment unusable -> counts as a tier-1 failure
        if words:
            return {"ok": True, "timings": _receipt(
                SOURCE_SUNO, words, track, dict(got["evidence"]))}
        t1_err = "SUNO_ALIGNMENT_MISSING"
    except LyricTimingError as e:
        t1_err = e.code

    # ── tier 2: exactly ONE local model per session, one track after another ──
    try:
        sess = whisper_session or WhisperSession(loader=whisper_loader)
        tx = sess.transcribe_all([_local_track(track)])
        words = sess.words_of(tx[-1])
        if not words:
            raise LyricTimingError(
                "WHISPER_EMPTY",
                "faster-whisper returned zero word timestamps; tier 3 is "
                "the last resort")
        return {"ok": True, "timings": _receipt(
            SOURCE_WHISPER_LOCAL, words, track,
            {"tier": 2, "loads": sess.loads, "model_size": sess.model_size,
             "compute_type": sess.compute_type, "tier1_error": t1_err})}
    except LyricTimingError as e:
        t2 = e
    except Exception as e:  # noqa: BLE001 - a crashing fallback is a failure
        t2 = LyricTimingError("WHISPER_CRASH", str(e)[:200])

    # ── tier 3: both earlier tiers failed ──
    if cloud is None:
        return {"ok": False, "error_code": t2.code,
                "evidence": {"tier1_error": t1_err, "tier2_error": t2.code},
                "next_action":
                    "tier 1 (%s) and tier 2 (%s) both failed; wire the "
                    "client's own cloud STT (word timestamps, client key "
                    "only) or re-run after the local fallback is enabled"
                    % (t1_err, t2.code)}
    try:
        return {"ok": True, "timings": cloud(track)}
    except LyricTimingError as e:
        return {"ok": False, "error_code": e.code,
                "evidence": {"tier1_error": t1_err, "tier2_error": t2.code},
                "next_action": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error_code": "CLOUD_STT_ERROR",
                "evidence": {"tier1_error": t1_err,
                             "tier2_error": t2.code},
                "next_action": str(e)[:200]}


def _local_track(track: Dict[str, Any]) -> Dict[str, Any]:
    t = dict(track or {})
    if not t.get("audio_path"):
        t["audio_path"] = t.get("path", "") or dict(t)
    return t


def _selftest():
    """One runnable check: the tier ladder holds on mocked data."""
    import json
    import tempfile

    tmp = tempfile.mkdtemp(prefix="lyric-timing-selftest-")
    doc = os.path.join(tmp, "aligned.json")
    with open(doc, "w", encoding="utf-8") as f:
        json.dump({"alignedWords": [{"word": "hello", "startS": 1.0,
                                     "endS": 1.4}]}, f)

    def fake_dispatcher(**kw):
        return {"outcome": "ok", "reason_code": "KIE_DISPATCH_OK",
                "evidence": {"saved_paths": [doc]}}

    got = provide_word_timings({"task_id": "t1", "audio_id": "a1"},
                               dispatcher=fake_dispatcher)
    assert got["ok"] and got["timings"]["source"] == SOURCE_SUNO
    assert got["timings"]["local_model_loads"] == 0
    assert got["timings"]["words"][0]["word"] == "hello"
    print("ok lyric_timing selftest: tier 1 without local loads")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())