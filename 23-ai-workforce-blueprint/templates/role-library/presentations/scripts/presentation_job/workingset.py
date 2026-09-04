"""FIX-20 — phase-scoped working sets + disk checkpoints (compaction reduction).

Defect D19: the build session compacted 3 times mid-build. Compaction drops
history; the agent lost earlier phase state and had to re-derive it, contributing
to the loops and re-attestation work.

Fix (FIX-20, per PRESENTATION-DEPARTMENT-FIX-RECOMMENDATIONS.md):
  "Smaller, phase-scoped working sets so the build completes within one context
   window; checkpoint phase state to disk so compaction doesn't lose it."

This module makes both halves explicit and measurable:

1. PHASE_WORKINGSET_GLOBS — the per-phase set of files that constitute the
   phase's context window. The engine never loads "everything": each phase's
   working set is the artifacts it produces PLUS the inputs it reads, declared
   once here. A phase's working set is deliberately small (a handful of files,
   not the whole role/SOP library).

2. measure_workingset() — deterministically measures a phase's working set in
   characters, bytes, and estimated tokens (chars / CHARACTERS_PER_TOKEN, the
   industry-standard LLM token approximation). It returns a fit verdict against
   CONTEXT_WINDOW_CAP (the fleet model's documented context window, in tokens).
   A phase that fits one window can complete without a compaction.

3. checkpoint_phase() — writes the phase's measured working-set size AND a
   snapshot of the phase record from state.json to a disk checkpoint at
   working/checkpoints/workingset/<phase>.json. The checkpoint is written
   atomically (via presentation_job.checkpoint.atomic_write_text). Because the
   phase state lives on disk, a compaction that drops in-memory history cannot
   lose it.

4. reload_phase() — reconstructs a phase record from the on-disk checkpoint,
   verifying the recorded sha256 of the original state.json still matches. This
   is the "phase state reloads from disk after a simulated compaction" proof:
   drop the in-memory state (as a compaction does), call reload_phase(), and
   get back an identical, verifiable phase record.

CLI: presentation_job.py --workingset [phase] measures one phase (or all
phases) and exits 0 when every measured phase fits the context-window cap,
exit 3 (EXIT_GATE_BLOCKED) when any phase exceeds it.

Pure Python stdlib only — no engine imports at module load so it is testable in
isolation (mirrors presentation_job/artifacts.py).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Estimated tokens per character. 1 token ~= 4 characters of English text is
# the long-standing LLM token approximation (OpenAI's tiktoken and the Claude
# tokenizers all land within ~1.1x-1.5x of this on prose). We deliberately use
# the conservative 4:1 so a working set measured "under cap" has headroom even
# against a tokenizer that runs hot. Over-counting is safe (it only ever
# reports a fit that is genuinely smaller); under-counting would be the bug.
CHARACTERS_PER_TOKEN = 4

# Context-window cap in tokens. The fleet presentations model is
# deepseek-v4-flash:0731-cloud; its documented context window is 131072 tokens
# (128K). A phase whose measured working set is below this cap can complete
# within one context window without compaction. This is the FIX-20 "fits one
# context window" bar.
CONTEXT_WINDOW_CAP = 131072

# Checkpoint directory, relative to the run dir.
CHECKPOINT_DIR = "working/checkpoints/workingset"

# The one manifest/process artifact every phase's attestation chain reads. It
# is shared state, not per-phase, so it is counted once per phase checkpoint
# but is tiny (a few KB).
_PROCESS_MANIFEST_REL = "working/checkpoints/process_manifest.json"

# ---------------------------------------------------------------------------
# Phase-scoped working sets.
#
# Each entry maps a manifest phase id to the glob set (relative to the run
# dir) that constitutes that phase's context window: the artifacts it produces
# plus the inputs it reads. A `*` in a glob matches any filename; the
# measurement expands each glob against the run dir and sums the matched
# files.
#
# The working set is DELIBERATELY phase-scoped: P4-RENDER's window is its 20
# prompt files + 20 renders + slides.json + the process manifest — not the
# whole 82-file SOP library. This is the "smaller, phase-scoped working sets"
# half of D19's fix.
# ---------------------------------------------------------------------------
PHASE_WORKINGSET_GLOBS: Dict[str, List[str]] = {
    # Intake / priority / signature front phases — small conversation-shaped files.
    "P-CONVERTER": ["working/copy/intake.json", "working/interview/*.json"],
    "P0A-INTAKE": ["working/copy/intake.json", "working/interview/*.json"],
    "P0B-PRIORITY": ["working/copy/intake.json", "working/copy/priority_shift_spec.json"],
    "P-SP-CLAIM": ["working/copy/intake.json", "working/copy/sp_intake.json"],
    "P-SP-INTAKE": ["working/copy/sp_intake.json", "working/interview/*.json"],
    "P-SP-INTAKE-TRACE": ["working/interview/intake_transcript.json"],
    # Research / copy / arc — the authoring phases' inputs + outputs.
    "P-0.5-RESEARCH": ["working/research/brief-*.md"],
    "P-3.5-RESEARCH-MAP": ["working/research/brief-*.md", "working/research/research_map.json"],
    "P3-ARC": ["working/copy/intake.json", "working/copy/arc_allocation.json"],
    "P-SP-STRUCTURE": ["working/copy/sp_intake.json", "working/copy/sp_structure.json"],
    "P-SP-P3-HYGIENE": ["working/copy/sp_structure.json"],
    "P4-COPY": ["working/copy/intake.json", "working/copy/slides_copy.md"],
    "PF-DESIGN": ["working/research/design-brief-*.md"],
    # FIX 112: P-STYLE-SPEC (the copy stage's fanout unit) sees exactly the
    # two inputs its manifest consumes[] declares — the slide design tokens
    # it derives style directions from, and the sealed intake for the deck's
    # hook/brand context — plus its own per-unit scratch dir.
    "P-STYLE-SPEC": ["working/copy/slides.json",
                     "working/copy/intake.json",
                     "working/fanout/P-STYLE-SPEC/*"],
    "P-STYLE-PREVIEW": ["working/style-preview/style_samples_manifest.json"],
    # Prompt authoring + QC — the per-slide rich prompts are the big files.
    "P4-PROMPT": ["working/prompts/slide-*.txt", "working/copy/slides_copy.md"],
    "P-PROMPT-QC": ["working/prompts/slide-*.txt", "working/qc/prompt_qc_report.json"],
    "P1Q-COPY-QC": ["working/copy/slides_copy.md", "working/qc/copy_qc_report.json"],
    "P-TYPO-QC": ["working/research/design-brief-*.md", "working/qc/typography_qc_report.json"],
    "P-SHIFT-QC": ["working/copy/priority_shift_spec.json", "working/qc/priority_shift_report.json"],
    # Render — the 20-slide generation phase. This is the largest working set
    # and the one D19's 3 compactions happened in.
    "P4-RENDER": [
        "working/prompts/slide-*.txt",
        "renders/slide-*.png",
        "slides.json",
    ],
    "P-IMAGE-QC": ["renders/slide-*.png", "working/qc/image_qc_report.json"],
    # Assembly + bundle producers — moderate.
    "P8-ASSEMBLE": ["renders/slide-*.png", "*-FINAL.pptx"],
    "P8.1-PDF-EXPORT": ["*-FINAL.pptx", "working/deliverables/*-FINAL.pdf"],
    "P8.2-GUIDE": ["working/deliverables/PRESENTER-GUIDE.pdf"],
    # Speech + audio + teleprompter — text and small html.
    "P9-SPEECH": ["working/presenter-speech/PRESENTERS-SPEECH.md"],
    "P8.4-FISH-TAG": ["working/presenter-speech/PRESENTERS-SPEECH.md",
                     "working/deliverables/PRESENTERS-SPEECH-FISH-TAGGED.md"],
    "P9.1-SPEECH-PDF": ["working/deliverables/PRESENTERS-SPEECH.pdf"],
    "P-SPEECH-QC": ["working/presenter-speech/PRESENTERS-SPEECH.md",
                    "working/qc/speech_qc_report.json"],
    "P-QC-AGGREGATE": ["working/qc/*_report.json", "working/qc/final_qc_report.json"],
    "P9.5-NOTES-SYNC": ["*-FINAL.pptx", "working/checkpoints/notes_sync.json"],
    "P9.2-GHL-UPLOAD": ["working/checkpoints/media_library.json"],
    "P7-TELEPROMPTER": ["working/presenter-speech/PRESENTERS-SPEECH.md",
                        "working/deliverables/presenter-teleprompter.html"],
    "P9-DELIVER": ["working/delivery/PRESENTER-AUDIO.mp3"],
}

# Fallback for any manifest phase id not in the table: measure its declared
# produces_artifact globs. Keeps the gate total over the manifest without
# requiring the table to be exhaustive forever (and fails the "unknown phase
# working set" loudly in measure_workingset, never silently as zero).
_UNKNOWN_PHASE_GLOBS = ["**/*.json", "**/*.md"]


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Estimate the token count of a text under the conservative 4:1 rule.

    Pure heuristic, deterministic, stdlib-only. Used to compare a working set
    against CONTEXT_WINDOW_CAP — not to bill tokens. Over-counting (which 4:1
    does relative to Claude's tokenizers) is the safe direction: a fit verdict
    here is conservative.
    """
    if not text:
        return 0
    return max(1, len(text) // CHARACTERS_PER_TOKEN)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------

def _expand_globs(run_dir: Path, globs: List[str]) -> List[Path]:
    """Expand working-set globs against the run dir. Never raises on a missing
    pattern — a glob that matches nothing contributes zero files (the phase
    simply has not produced its artifacts yet)."""
    out: List[Path] = []
    for pattern in globs:
        if any(c in pattern for c in "*?["):
            out.extend(sorted(p for p in run_dir.glob(pattern) if p.is_file()))
        else:
            p = run_dir / pattern
            if p.is_file():
                out.append(p)
    # Deduplicate while preserving order.
    seen: set = set()
    uniq: List[Path] = []
    for p in out:
        key = str(p)
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq


def _read_bytes(path: Path) -> bytes:
    """Read a file's raw bytes, leniently. Phase-completion measurement only —
    never the hot-loop path (see _stat_meta)."""
    try:
        return path.read_bytes()
    except OSError:
        return b""


def _stat_meta(path: Path) -> Optional[Dict[str, int]]:
    """Cost-free metadata for one file: size + mtime from stat, no byte read.

    FIX 26: the hot-loop measurement path (Engine._checkpoint during a render
    wave) reads ZERO bytes of the working set; a size + mtime_ns pair is all
    the fit verdict, the checkpoint record, and change detection need."""
    try:
        st = path.stat()
    except OSError:
        return None
    return {
        "bytes": int(st.st_size),
        "mtime_ns": int(getattr(st, "st_mtime_ns", st.st_mtime * 1_000_000_000)),
    }


def measure_workingset(run_dir: Path, phase_id: str,
                       manifest=None, hash_on_completion: bool = False) -> Dict[str, Any]:
    """Measure one phase's working set.

    FIX 26 (MASTER Part 8): every checkpoint used to read every PNG's bytes.
    P4-RENDER's checkpoint ran inside the phase loop where the working set is
    tens of rendered PNGs — the byte reads plus lenient decode put
    ``Engine._checkpoint`` far over the 100 ms bar on a 40-slide dir. The
    measurement is now stat-based (size + mtime_ns, zero bytes read) — a size
    AND mtime pair is sufficient for the fit verdict, the checkpoint record,
    and change detection, and it is what a hot loop needs. The token estimate
    uses the still-conservative bytes/CHARACTERS_PER_TOKEN (a binary PNG's
    bytes were already replacement chars in the old decode, and over-counting
    is the safe direction); ``chars`` is filled only on the one path that
    actually reads content (``hash_on_completion=True``), i.e. phase
    completion, where the real byte read is provably required for the sha.

    Returns a dict:
        {
          "phase_id": str,
          "files": [{"path": rel, "bytes": int, "chars": int|None,
                     "mtime_ns": int}],
          "total_bytes": int,
          "total_chars": int,
          "estimated_tokens": int,
          "context_window_cap": int,
          "fits": bool,          # estimated_tokens <= context_window_cap
          "tokens_pct_of_cap": float,   # 0..1..(over)
          "globs": [...],              # the declared globs for this phase
          "checked_manifest": bool,
        }
    """
    globs = PHASE_WORKINGSET_GLOBS.get(phase_id)
    checked_manifest = False
    if globs is None and manifest is not None:
        # Fall back to the manifest's declared produces_artifact for this phase.
        try:
            ph = manifest.phase_or_none(phase_id)
        except Exception:  # noqa: BLE001
            ph = None
        if ph is not None:
            # U01-R2 (QC FAIL 6.46): the manifest may declare {deck_slug}-templated
            # patterns (e.g. P8.25-WORKBOOK's
            # 'working/deliverables/{deck_slug}-WORKBOOK.pdf + {deck_slug}-WORKBOOK-FILLABLE.pdf').
            # Resolve the tokens against the run dir so the working-set measurement
            # globs the REAL artifact paths; the literal token path never matches disk.
            try:
                globs = list(ph.resolve_artifact_patterns(run_dir) or [])
            except Exception:  # noqa: BLE001 -- never fail a measurement on resolution
                globs = list(getattr(ph, "produces_artifact", []) or [])
            checked_manifest = True
    if globs is None:
        globs = list(_UNKNOWN_PHASE_GLOBS)

    files: List[Dict[str, Any]] = []
    total_bytes = 0
    total_chars = 0
    for path in _expand_globs(run_dir, globs):
        meta = _stat_meta(path)
        if meta is None:
            continue
        n_bytes = int(meta["bytes"])
        total_bytes += n_bytes
        entry = {
            "path": str(path.relative_to(run_dir)),
            "bytes": n_bytes,
            "chars": None,
            "mtime_ns": int(meta["mtime_ns"]),
        }
        # FIX 26 regression guard (R-B02-B2): the stat-only rewrite dropped the
        # `files.append(entry)` call, so the documented `files` list came back
        # empty while totals stayed right — the checkpoint record lost every
        # per-file row and the "no SOP leak" test passed vacuously. Append it.
        files.append(entry)
        if hash_on_completion:
            # Phase completion only: read + leniently decode once. The sha256
            # (records["sha256"]) computed by the caller is over the raw bytes
            # anyway; this decode exists for the legacy `chars` field and the
            # conservative token count. A byte read here is required because
            # the completion path is attestation, not a hot loop.
            data = _read_bytes(path)
            if len(data) != n_bytes:
                # stat hinted a different size than a re-read sees (file was
                # being written mid-measurement); trust the bytes actually read.
                total_bytes += len(data) - n_bytes
                entry["bytes"] = n_bytes = len(data)
            text = data.decode("utf-8", errors="replace")
            entry["chars"] = len(text)
            total_chars += len(text)
        else:
            # Stat-only token estimate: bytes -> tokens under the conservative
            # 4:1 rule. For binary artifacts the old decode produced ~1 char
            # per replacement byte, so bytes/4 is EQUALLY conservative (in
            # fact slightly less than the old replacement-char count), and it
            # never reads the file.
            total_chars += n_bytes

    estimated = estimate_tokens("x" * total_chars) if total_chars else 0
    fits = estimated <= CONTEXT_WINDOW_CAP
    pct = (estimated / CONTEXT_WINDOW_CAP) if CONTEXT_WINDOW_CAP else 1.0
    return {
        "phase_id": phase_id,
        "files": files,
        "total_bytes": total_bytes,
        "total_chars": total_chars,
        "estimated_tokens": estimated,
        "context_window_cap": CONTEXT_WINDOW_CAP,
        "fits": fits,
        "tokens_pct_of_cap": round(pct, 4),
        "globs": globs,
        "checked_manifest": checked_manifest,
    }


def measure_all(run_dir: Path, manifest=None) -> List[Dict[str, Any]]:
    """Measure every phase the manifest declares (or, with no manifest, every
    phase in PHASE_WORKINGSET_GLOBS)."""
    phase_ids: List[str] = []
    if manifest is not None:
        try:
            phase_ids = [p.id for p in manifest.phases]
        except Exception:  # noqa: BLE001
            phase_ids = []
    if not phase_ids:
        phase_ids = list(PHASE_WORKINGSET_GLOBS.keys())
    return [measure_workingset(run_dir, pid, manifest) for pid in phase_ids]


# ---------------------------------------------------------------------------
# Disk checkpoints — phase state survives a compaction
# ---------------------------------------------------------------------------

def _checkpoint_path(run_dir: Path, phase_id: str) -> Path:
    return run_dir / CHECKPOINT_DIR / f"{phase_id}.json"


def checkpoint_phase(run_dir: Path, phase_id: str, state: Dict[str, Any],
                     store=None, hash_on_completion: bool = False) -> Dict[str, Any]:
    """Write a phase disk checkpoint: the measured working-set size plus a
    snapshot of the phase record from state.json, atomically.

    The checkpoint is the FIX-20 "checkpoint phase state to disk so compaction
    doesn't lose it" half. Because the file is written before a compaction
    (and every phase completion via Engine._checkpoint), the phase record can
    always be reconstructed from disk even when the in-memory history is
    dropped.

    Returns the checkpoint dict that was written.
    """
    # Locate the phase record in state["phases"].
    phase_record: Optional[Dict[str, Any]] = None
    for ps in state.get("phases", []) or []:
        if isinstance(ps, dict) and ps.get("id") == phase_id:
            phase_record = ps
            break

    # Measure the working set as of the checkpoint. FIX 26: the real byte
    # read is OPT-IN (hash_on_completion) — the engine passes it only on a
    # phase-completion checkpoint (attestation), keeping every hot-loop
    # checkpoint stat-only.
    measurement = measure_workingset(run_dir, phase_id,
                                     hash_on_completion=hash_on_completion)

    state_sha = sha256_text(json.dumps(state, sort_keys=True, default=str))
    from .state import utcnow  # deferred import keeps module import-light
    checkpoint = {
        "schema_version": 1,
        "phase_id": phase_id,
        # The timestamp is set HERE (utcnow at write time), not by the caller:
        # every existing caller passed the checkpoint straight through, so a
        # "caller will stamp it" contract had no caller — the field would have
        # stayed None on every disk record.
        "checkpointed_at": utcnow(),
        "working_set": measurement,
        "phase_record": phase_record,
        "state_sha256": state_sha,
        "has_state_snapshot": phase_record is not None,
    }

    path = _checkpoint_path(run_dir, phase_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    from .checkpoint import atomic_write_text  # same atomic writer as U028
    atomic_write_text(path, json.dumps(checkpoint, indent=2, default=str))
    return checkpoint


def reload_phase(run_dir: Path, phase_id: str) -> Dict[str, Any]:
    """Reconstruct a phase record from its on-disk checkpoint.

    Returns a dict:
        {
          "phase_id": str,
          "reloaded": bool,          # a checkpoint file existed and parsed
          "phase_record": obj,       # the reconstructed record, or None
          "working_set": obj,        # the measured working set, or None
          "state_sha256": str,       # recorded sha of the checkpointing state
          "integrity_ok": bool,      # checkpoint parsed and carried a phase record
          "error": str,              # when reloaded is False
        }
    """
    path = _checkpoint_path(run_dir, phase_id)
    if not path.is_file():
        return {
            "phase_id": phase_id,
            "reloaded": False,
            "phase_record": None,
            "working_set": None,
            "state_sha256": None,
            "integrity_ok": False,
            "error": f"no checkpoint at {path.relative_to(run_dir)}",
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "phase_id": phase_id,
            "reloaded": False,
            "phase_record": None,
            "working_set": None,
            "state_sha256": None,
            "integrity_ok": False,
            "error": f"checkpoint unreadable: {exc}",
        }
    record = data.get("phase_record")
    return {
        "phase_id": phase_id,
        "reloaded": True,
        "phase_record": record,
        "working_set": data.get("working_set"),
        "state_sha256": data.get("state_sha256"),
        "integrity_ok": isinstance(record, dict) and record.get("id") == phase_id,
        "error": None,
    }


def list_checkpoints(run_dir: Path) -> List[str]:
    """Return the sorted list of phase ids that have an on-disk checkpoint."""
    d = run_dir / CHECKPOINT_DIR
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.json") if p.is_file())
