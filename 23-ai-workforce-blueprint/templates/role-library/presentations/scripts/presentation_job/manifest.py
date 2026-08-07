from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .state import (
    die, sha256_file, EXIT_MANIFEST_MISMATCH, EXIT_USAGE,
)

# ---------------------------------------------------------------------------
# Phase-budget table. These are TOTAL per-phase timeouts in minutes.
# ---------------------------------------------------------------------------
# Default per-phase budget when the manifest declares no heartbeat_minutes.
# The live v18 manifest declares client_report on 0/20 phases and heartbeat_minutes on 0/20;
# the canonical v25 declares client_report on 26/26 and heartbeat_minutes on only 3/26
# (the three long_running phases, at 10 minutes). So most phases need a default, and the
# table below supplies one per phase class rather than leaving 23 phases with no threshold.
DEFAULT_PHASE_BUDGET_MINUTES = 20

DEFAULT_PHASE_BUDGET_MINUTES = 20

PHASE_BUDGET_MINUTES: Dict[str, int] = {
    # long_running in the canonical manifest
    "P-0.5-RESEARCH": 45,
    "P-3.5-RESEARCH-MAP": 30,
    "P4-RENDER": 240,          # 62 slides of image generation is genuinely slow
    # scripted, fast
    "P0A-INTAKE": 60,          # human-paced: one question per turn
    "P-SP-INTAKE": 60,
    "P-SP-INTAKE-TRACE": 60,
    "P-SP-CLAIM": 10,
    "P-STYLE-PREVIEW": 45,
    "P8-ASSEMBLE": 30,
    "P8.1-PDF-EXPORT": 15,
    "P8.2-GUIDE": 20,
    "P8.4-FISH-TAG": 15,
    "P9-SPEECH": 45,
    "P9.1-SPEECH-PDF": 15,
    "P9.2-GHL-UPLOAD": 30,
    "P9.5-NOTES-SYNC": 20,
    # These five phase ids do not exist in manifest v25 (26 phases). U012 creates them.
    # Budgets are pre-seeded here on purpose so U012 does not have to touch this table.
    "P7-TELEPROMPTER": 10,
    "P9-DELIVER": 30,
    # agent-authored authoring phases
    "P-CONVERTER": 40,
    "P0B-PRIORITY": 30,
    "P3-ARC": 30,
    "P4-COPY": 60,
    "P-SP-STRUCTURE": 45,
    "P-SP-P3-HYGIENE": 20,
    "PF-DESIGN": 30,
    "P4-PROMPT": 90,           # 9,000+ chars per slide, authored
    # QC phases
    "P1Q-COPY-QC": 20,
    "P-TYPO-QC": 20,
    "P-PROMPT-QC": 20,
    "P-IMAGE-QC": 30,
    "P-SHIFT-QC": 20,
    "P-SPEECH-QC": 20,
    # Final QC Aggregation -- purely mechanical (read six small JSON files, run the
    # existing qc_generator_guard.py sweep, write one JSON file); no agent authoring,
    # no render, no network call.
    "P-QC-AGGREGATE": 10,
}

# ---------------------------------------------------------------------------
# Manifest. Pinned per job (invariant 4).
# ---------------------------------------------------------------------------
@dataclass
class Phase:
    id: str
    order: float
    owning_role: str
    produces_artifact: List[str]
    executor_kind: str                  # "script" | "agent" | "none"
    executor_cmd: Optional[str]
    verifier: Optional[str]
    client_report: Dict[str, Any] = field(default_factory=dict)
    heartbeat_minutes: Optional[int] = None
    long_running: bool = False

    @property
    def budget_minutes(self) -> int:
        """
        TOTAL time this phase may take, in minutes. Feeds the subprocess timeout.

        DO NOT derive this from the manifest's `heartbeat_minutes`. They are different concepts and
        conflating them is a render-killing bug: the canonical manifest sets heartbeat_minutes=10 on
        P4-RENDER, so returning it here would kill a 62-slide render after 10 minutes. The budget is
        240. See `heartbeat_interval_minutes` below for the watchdog's separate value.
        """
        return PHASE_BUDGET_MINUTES.get(self.id, DEFAULT_PHASE_BUDGET_MINUTES)

    @property
    def heartbeat_interval_minutes(self) -> int:
        """
        How often this phase is expected to CHECKPOINT — the watchdog's comparison value, not a
        timeout. The watchdog compares last-checkpoint AGE against this, never total elapsed.
        Falls back to the full budget for phases that checkpoint only on completion.
        """
        if self.heartbeat_minutes:
            return int(self.heartbeat_minutes)
        return self.budget_minutes



class Manifest:
    """
    Loads PIPELINE-MANIFEST.json and REFUSES to fall back silently.

    The bug this replaces: run_signature_deck.load_manifest() (:239-252) walks up looking for a
    `universal-sops` directory; from the materialized department tree no ancestor has one, so it
    silently loads the stale local v18 copy. Four separate resolvers share that shape
    (gate_integrity_check.py:77, runner_gate_integrity_check.py:86, sync_check.py:98).
    Here: resolve, then verify against MANIFEST-SOURCE.txt, then hard-fail on mismatch.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.sha256 = sha256_file(path)
        try:
            self.raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            die(EXIT_MANIFEST_MISMATCH, f"cannot parse manifest {path}: {exc}")
        self.version = self.raw.get("manifest_version")
        self.phases = self._parse_phases()
        self.deliverables = self.raw.get("deliverables_required", [])
        self.client_package = self.raw.get("client_package_files", [])

    def _parse_phases(self) -> List[Phase]:
        out: List[Phase] = []
        for p in self.raw.get("phases", []):
            ex = p.get("executor") or {}
            out.append(Phase(
                id=p["id"],
                order=float(p.get("order", 0)),
                owning_role=p.get("owning_role") or "",
                produces_artifact=_as_list(p.get("produces_artifact")),
                # NOTE: no phase in either shipped manifest declares an executor, and `verifier`
                # is not a field at all. Until the phase contract lands (fix A3), everything
                # resolves to "agent" — which is exactly why A3 must ship in warn-mode first.
                executor_kind=(ex.get("kind") or "agent"),
                executor_cmd=ex.get("cmd"),
                verifier=p.get("verifier"),
                client_report=p.get("client_report") or {},
                heartbeat_minutes=p.get("heartbeat_minutes"),
                long_running=bool(p.get("long_running")),
            ))
        out.sort(key=lambda x: x.order)
        return out

    def verify_pin(self, pinned_sha: str) -> None:
        if pinned_sha and pinned_sha != self.sha256:
            die(EXIT_MANIFEST_MISMATCH,
                "manifest changed under a running job.\n"
                f"  pinned : {pinned_sha}\n  on disk: {self.sha256}\n"
                f"  file   : {self.path}\n"
                "A job started under one manifest must finish under it. Resume with the pinned "
                "copy, or start a new job.")

    def verify_source(self) -> None:
        """Assert the installed manifest matches its recorded upstream (fix A1 step 3)."""
        src = self.path.parent / "MANIFEST-SOURCE.txt"
        if not src.is_file():
            print(f"WARN: no MANIFEST-SOURCE.txt beside {self.path.name} — provenance unverifiable "
                  "(fix A1 installs it)", file=sys.stderr)
            return
        recorded = {}
        for line in src.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                recorded[k.strip()] = v.strip()
        if recorded.get("content_sha256") and recorded["content_sha256"] != self.sha256:
            die(EXIT_MANIFEST_MISMATCH,
                f"installed manifest does not match its recorded source.\n"
                f"  recorded: {recorded['content_sha256']}\n  actual  : {self.sha256}")

    def phase(self, phase_id: str) -> Phase:
        for p in self.phases:
            if p.id == phase_id:
                return p
        die(EXIT_USAGE, f"unknown phase id {phase_id!r} in manifest v{self.version} "
                        f"({len(self.phases)} phases). Known: {', '.join(p.id for p in self.phases)}")

    def phase_or_none(self, phase_id: str) -> Optional[Phase]:
        """Non-fatal lookup. Returns None for an unknown id -- never dies.

        The --phase command-line path depends on phase() hard-failing with the full
        known-id list, so this is a separate method.  The engine's _checkpoint uses
        this to write interval metadata into state without crashing on a phase id
        it cannot resolve.
        """
        for p in self.phases:
            if p.id == phase_id:
                return p
        return None


def _as_list(v: Any) -> List[str]:
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple)) else [str(v)]


# The canonical manifest as of this writing. A resolved manifest below this version is
# the stale fork and MUST NOT be run: it lacks the six signature phases and all sixteen
# AF-SP-* codes, so a job would pass every gate it knows about while skipping the gates
# it has never heard of.


# (SPEC/units/U019.md:409-410, :440-441, :1093): "set MIN_MANIFEST_VERSION to that same new value,
# in the same commit" — the floor and the manifest move TOGETHER. A floor one behind the manifest is
# the split-brain that step 8 exists to prevent: the engine keeps accepting the older, fewer-key
# manifest while the delivery gate already demands the newer keys. Whoever bumps manifest_version
# bumps this line in the same commit; test_client_package.py::
# test_assert_manifest_current_accepts_bumped_and_rejects_one_version_below fails the build if not.
# (31 -> 32: U012 added the six missing manifest phases — P7-TELEPROMPTER,
# P8.1-PDF-EXPORT, P8.2-GUIDE, P8.4-FISH-TAG, P9.1-SPEECH-PDF, P9.2-GHL-UPLOAD — and their
# executor blocks, raising manifest_version to 32 in the same commit.
# 32 -> 33: SOP-SLIDE-06 wiring of the U027 OCR-readback postflight gate — added the
# AF-OCR-READBACK autofails[] entry (enforced_by:build_deck, py_symbol:check_ocr_readback),
# raising manifest_version to 33 in the same commit.
# 33 -> 34: fix/ocr-engine-preflight-real-path added AF-OCR-ENGINE-MISSING — the
# MASTER-SPEC 7.4 Phase-0 OCR-engine-availability pre-flight on the REAL render path
# (build_deck.ocr_engine_preflight / run_signature_deck.phase0_preflight) — raising
# manifest_version to 34 in the same commit.
# 34 -> 35: merging fix/qc-gate-fail-closed adds P-QC-AGGREGATE (the aggregation phase that reads
# the six domain QC reports, verifies provenance, and writes final_qc_report.json) while main's
# v34 carries AF-OCR-ENGINE-MISSING — neither parent had both features at v34, so the combined
# manifest is bumped to 35 to keep the floor and the manifest in lockstep.
# 35 -> 36: FIX-8 registers AF-BUNDLE-INCOMPLETE (the full 9-deliverable bundle gate,
# fix_bundle_complete.py) in PIPELINE-MANIFEST.autofails. The floor moves WITH the manifest.
# 36 -> 37: FIX-14 registers AF-AGENT-ENV-MISSING / AF-AGENT-ENV-UNMANAGED /
# AF-AGENT-ENV-UNKNOWN (the MC_API_TOKEN regression guard) in PIPELINE-MANIFEST.autofails.
# 37 -> 38: FIX-18 registers AF-TOOL-SCHEMA-LOOP (tool-schema hardening: normalized schema
# hint + 5-consecutive-failure loop alert) in PIPELINE-MANIFEST.autofails.

# 37 -> 38: FIX-23(c) registers AF-KIE-AUTH (auth preflight) + AF-FORGED-APPROVAL
# (authentic skip approvals) in PIPELINE-MANIFEST.autofails so sync_check lockstep
# passes (the repo-side half of the 27-drift-item repair). Floor moves WITH the manifest.
MIN_MANIFEST_VERSION = 38  # MUST EQUAL PIPELINE-MANIFEST.json's manifest_version. U019 step 8
MIN_MANIFEST_PHASES = 26

def _assert_manifest_current(path: Path) -> None:
    """Refuse to run on a stale manifest. Exit 7, never a warning."""
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        die(EXIT_MANIFEST_MISMATCH, f"cannot parse manifest {path}: {exc}")
    version = obj.get("manifest_version")
    phases = len(obj.get("phases") or [])
    af_sp = [a for a in (obj.get("autofails") or [])
             if str(a.get("code", "")).startswith("AF-SP-")]
    if not isinstance(version, int) or version < MIN_MANIFEST_VERSION or phases < MIN_MANIFEST_PHASES:
        die(EXIT_MANIFEST_MISMATCH,
            f"STALE MANIFEST — refusing to run.\n"
            f"  file    : {path}\n"
            f"  found   : version {version}, {phases} phases, {len(af_sp)} AF-SP-* codes\n"
            f"  required: version >= {MIN_MANIFEST_VERSION}, >= {MIN_MANIFEST_PHASES} phases\n"
            "  The department copy is a stale fork that omits the signature-presentation\n"
            "  phases and every AF-SP-* gate. Running it would report completeness while\n"
            "  silently skipping those gates. Install the canonical manifest (fix A1), or\n"
            "  pass --manifest pointing at universal-sops/presentation-slide-craft/.")
    src = path.parent / "MANIFEST-SOURCE.txt"
    if src.is_file():
        want = ""
        for line in src.read_text(encoding="utf-8").splitlines():
            if line.startswith("content_sha256="):
                want = line.split("=", 1)[1].strip()
        if want and want != sha256_file(path):
            die(EXIT_MANIFEST_MISMATCH,
                f"manifest does not match its recorded source.\n"
                f"  recorded: {want}\n  actual  : {sha256_file(path)}\n  file    : {path}")



def resolve_manifest(explicit: Optional[str], run_dir: Path, scripts_dir: Path) -> Path:
    """
    Resolution order, and it NEVER guesses past this list:
      1. --manifest
      2. <scripts_dir>/../sops/PIPELINE-MANIFEST.json   (the materialized department)
      3. $PRESENTATION_MANIFEST
    No walk-up search. A missing manifest is a hard error, not a fallback.

    ⚠️ RESOLVING IS NOT ENOUGH — THE RESOLVED FILE MUST ALSO BE CURRENT.
    On a real box, candidate 2 is the STALE v18 fork: 20 phases, 126 autofails, and ZERO
    of the six signature phases or sixteen AF-SP-* codes. Simply returning it would make
    this engine silently run a 20-phase pipeline while reporting completeness — the exact
    failure it was written to prevent. So every resolved manifest is version-gated by
    _assert_manifest_current() below, and a stale one is a hard error (exit 7), not a
    warning. Fix A1 installs the canonical manifest; until then this refuses to run.
    """
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.is_file():
            die(EXIT_USAGE, f"--manifest {p} does not exist")
        _assert_manifest_current(p)
        return p
    cand = (scripts_dir.parent / "sops" / "PIPELINE-MANIFEST.json").resolve()
    if cand.is_file():
        _assert_manifest_current(cand)
        return cand
    env = os.environ.get("PRESENTATION_MANIFEST")
    if env and Path(env).is_file():
        p = Path(env).resolve()
        _assert_manifest_current(p)
        return p
    die(EXIT_USAGE,
        "cannot locate PIPELINE-MANIFEST.json. Pass --manifest explicitly.\n"
        f"  tried: {cand}\n"
        "  This engine refuses to search upward — a silent fallback to a stale manifest is the "
        "bug it exists to prevent.")


# ---------------------------------------------------------------------------
# Reporting. Announce BEFORE retrying (invariant 6).
# ---------------------------------------------------------------------------

