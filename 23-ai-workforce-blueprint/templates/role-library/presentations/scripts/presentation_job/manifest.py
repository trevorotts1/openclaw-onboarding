from __future__ import annotations

import hashlib
import json
import os
import re
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
    "P8.25-WORKBOOK": 30,      # Feature L2-D: kie.ai page design (parallel) + reportlab assembly
    "P8.4-FISH-TAG": 15,
    "P9-SPEECH": 45,
    "P9.1-SPEECH-PDF": 15,
    "P9.2-GHL-UPLOAD": 30,
    "P9.5-NOTES-SYNC": 20,
    "P9.6-WEBINAR-VIDEO": 240,  # Feature L2-G: per-slide ffmpeg Ken Burns clips + xfade chain + 500MB GHL v3 upload
    "P9-SPEECH-WEBINAR-INTRO": 240,  # Feature L2-G: webinar intro/outro video build (ffmpeg + render)
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
# HARDEN G3 — heartbeat_minutes sanity ceiling.
# ---------------------------------------------------------------------------
# GAP G3's first fix (sync_check.py check E3, 2026-08-13) asserted heartbeat_minutes is
# PRESENT and > 0 on every phase. An adversarial re-attack proved presence-and-positivity
# is not a range: setting heartbeat_minutes to 999999999 on all 33 non-long-running phases
# still passes E3 (present, positive) with zero drift, and heartbeat_interval_minutes below
# used to hand that value straight to the watchdog/reaper untouched -- a ~2,853-year stall
# threshold (999999999 min x 1.5 grace) that reports a 12-hour-silent job HEALTHY. The fix
# that closed the ORIGINAL gap (deletion) was strictly milder than this one: with the field
# absent, the budget-minutes fallback below still fired and the stall was still detected.
#
# The ceiling is not an arbitrary round number -- that would just be a bigger number to
# guess past. It is this engine's own PHASE_BUDGET_MINUTES table above, which already
# declares, for every phase, the longest time that phase is EVER allowed to run before the
# engine kills it outright (the subprocess timeout enforced in phases.py). The single
# largest entry in that table -- 240 minutes, shared by P4-RENDER (62-slide image render),
# P9.6-WEBINAR-VIDEO and P9-SPEECH-WEBINAR-INTRO (ffmpeg assembly + a 500MB GHL upload) --
# is the slowest legitimate unit of work this engine EVER performs. A checkpoint cadence
# looser than the slowest thing the whole system does is not "this phase checkpoints
# rarely", it can only be a watchdog being blinded. Every real phase's declared
# heartbeat_minutes is well inside this ceiling (15-120 across all 36 phases; see
# universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json), so the ceiling costs the
# legitimate path nothing.
MAX_HEARTBEAT_INTERVAL_MINUTES = max(PHASE_BUDGET_MINUTES.values())  # 240 as of this table


def is_sane_heartbeat_minutes(value: Any, phase_budget_minutes: Optional[int] = None) -> bool:
    """True iff `value` is a heartbeat_minutes a consumer may trust as-is (present, a real
    int -- not bool -- strictly positive, and no larger than the applicable ceiling).

    HARDEN G3 follow-up (RCA §1.5, §7): MAX_HEARTBEAT_INTERVAL_MINUTES (240) is the
    slowest phase in the WHOLE engine, not a bound on any one phase. Applied globally to
    every phase it let a 15-minute phase declare heartbeat_minutes=240 and pass this
    check, blinding the stall detector for that phase even though it can never
    legitimately run that long. When the caller passes `phase_budget_minutes` (that
    phase's OWN Phase.budget_minutes), the ceiling is tightened to
    min(MAX_HEARTBEAT_INTERVAL_MINUTES, phase_budget_minutes) so no phase can declare a
    heartbeat looser than its own total timeout. `phase_budget_minutes=None` (the
    default) falls back to the flat global ceiling for callers with no phase context.

    Used directly by Phase.heartbeat_interval_minutes below (the runtime source that writes
    state.json's heartbeat.interval_minutes) and by sync_check.py's E3 manifest check, which
    imports this module's MAX_HEARTBEAT_INTERVAL_MINUTES rather than re-declaring its own copy.
    watchdog.py and process_reaper.py read heartbeat.interval_minutes back OFF state.json as
    defense in depth (a pre-fix or foreign-written state.json could still carry a poisoned
    value) and mirror this same per-phase ceiling inline rather than calling this function,
    because they also tolerate a bare float there (state.json is parsed JSON, not
    manifest-authored input) -- one ceiling FORMULA, applied everywhere it is checked, so
    no consumer can silently diverge on WHERE the line is, even where the surrounding type
    check differs by design.
    """
    ceiling = MAX_HEARTBEAT_INTERVAL_MINUTES
    if phase_budget_minutes is not None:
        ceiling = min(MAX_HEARTBEAT_INTERVAL_MINUTES, phase_budget_minutes)
    return (isinstance(value, int) and not isinstance(value, bool)
            and 0 < value <= ceiling)

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
    # P8.25-WORKBOOK fix: the manifest declares the " + " pair with the directory
    # on the FIRST pattern only ("working/deliverables/{deck_slug}-WORKBOOK.pdf +
    # {deck_slug}-WORKBOOK-FILLABLE.pdf"). A token-bearing bare filename inherits
    # this directory context at resolution time so the fillable resolves to the
    # directory the builder actually writes to. Set by Manifest._parse_phases.
    _dir_context: Optional[str] = None

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
        Falls back to the full budget for phases that checkpoint only on completion, OR for a
        heartbeat_minutes that fails is_sane_heartbeat_minutes — absent, non-int, <= 0, or past
        min(MAX_HEARTBEAT_INTERVAL_MINUTES, this phase's OWN budget_minutes) (HARDEN G3 +
        per-phase follow-up, see the block above). This is the runtime SOURCE that
        _checkpoint() in phases.py writes into state.json's heartbeat.interval_minutes, so
        refusing an insane value here means it can never reach the watchdog/reaper at all —
        independent of whether the manifest that produced it ever passed through sync_check.
        """
        if is_sane_heartbeat_minutes(self.heartbeat_minutes, self.budget_minutes):
            return int(self.heartbeat_minutes)
        return self.budget_minutes

    # -----------------------------------------------------------------------
    # {deck_slug} / {run_dir} token resolution (fix P8.25-WORKBOOK).
    #
    # The canonical manifest declares P8.25-WORKBOOK's produces_artifact as
    #   "working/deliverables/{deck_slug}-WORKBOOK.pdf + {deck_slug}-WORKBOOK-FILLABLE.pdf"
    # The literal token must be substituted with the run's deck slug before the
    # engine's artifact-presence check globs for it -- otherwise it looks for a
    # file literally named "{deck_slug}-WORKBOOK.pdf" and hard-blocks the phase
    # even though both real workbook PDFs exist and pass the substance verifier.
    # Resolution chain mirrors curate._resolve_deck_slug (curate.py:593):
    #   1. working/copy/intake.json["deck_slug"]   -- engine-upkept (LIVE)
    #   2. working/copy/intake.json["title"]        -- fallback for slugless decks
    #   3. state.json["intake"]["deck_slug"]         -- frozen snapshot (STALE)
    #   4. state.json["intake"]["title"]             -- last fallback
    #   5. run_dir.name                              -- ultimate fallback
    # After resolution the string is slugified to [a-z0-9-]. The {run_dir} token
    # (used by the phase executor cmd) resolves to run_dir.name.
    # -----------------------------------------------------------------------
    def resolve_artifact_pattern(self, rel: str, run_dir: Optional[Path] = None) -> str:
        """Substitute {deck_slug} / {run_dir} tokens in ONE artifact pattern.

        No run_dir (or an unreadable intake/state) leaves the pattern untouched --
        never a crash, never a guessed slug. The engine's artifact-presence check
        passes the run dir it already holds, so a live run resolves to real paths.
        """
        if run_dir is None or "{deck_slug}" not in rel and "{run_dir}" not in rel:
            return rel
        slug = _resolve_deck_slug(run_dir)
        resolved = rel.replace("{deck_slug}", slug).replace("{run_dir}", run_dir.name)
        # A token-bearing bare filename inherits the phase's declared directory
        # context ("working/deliverables/{deck_slug}-WORKBOOK.pdf + {deck_slug}-...
        # FILLABLE.pdf" declares the directory on the first pattern only).
        if self._dir_context and "/" not in resolved and not resolved.startswith("{deck_slug}"):
            resolved = f"{self._dir_context}/{resolved}"
        return resolved

    def resolve_artifact_patterns(self, run_dir: Optional[Path] = None) -> List[str]:
        """Token-substitute every pattern in produces_artifact (see resolve_artifact_pattern)."""
        return [self.resolve_artifact_pattern(rel, run_dir) for rel in self.produces_artifact]



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
            patterns = _split_artifact_patterns(_as_list(p.get("produces_artifact")))
            dir_context = _common_dir_prefix(patterns)
            out.append(Phase(
                id=p["id"],
                order=float(p.get("order", 0)),
                owning_role=p.get("owning_role") or "",
                # P8.25-WORKBOOK fix: the canonical manifest declares produces_artifact with a
                # literal "{deck_slug}" token (and the " + " separator between the two workbook
                # PDFs). Both must be normalized at phase-definition time: split " + " into the
                # two patterns, keep the {deck_slug} token for lazy substitution by
                # resolve_artifact_patterns() at artifact-presence-check time (run_dir is not
                # available here -- callers construct Manifest before the run dir is passed on).
                produces_artifact=patterns,
                _dir_context=dir_context,
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


def _split_artifact_patterns(patterns: List[str]) -> List[str]:
    """Split " + "-separated artifact patterns into individual entries.

    P8.25-WORKBOOK fix: the canonical manifest declares
      "working/deliverables/{deck_slug}-WORKBOOK.pdf + {deck_slug}-WORKBOOK-FILLABLE.pdf"
    as a single string. The engine's presence check treats each entry as ONE path,
    so an unsplit pair could never both exist. No real phase pattern uses " + " as
    a glob metacharacter, so splitting is safe for every shipped phase.
    """
    out: List[str] = []
    for rel in patterns:
        for piece in rel.split(" + "):
            piece = piece.strip()
            if piece:
                out.append(piece)
    return out


def _common_dir_prefix(patterns: List[str]) -> Optional[str]:
    """Directory context shared by a phase's artifact patterns.

    P8.25-WORKBOOK fix: the manifest declares the pair with the directory on the
    first pattern only. A token-bearing bare filename ("{deck_slug}-WORKBOOK-
    FILLABLE.pdf") inherits the common directory of the phase's own patterns so
    it resolves where the builder actually writes it. Returns None when the
    patterns do not share one directory.
    """
    dirs = [str(Path(p).parent) for p in patterns if p and str(Path(p).parent) != "."]
    unique = sorted(set(dirs))
    if len(unique) == 1:
        return unique[0]
    return None


def _resolve_deck_slug(run_dir: Path) -> str:
    """Resolve the deck slug for {deck_slug} pattern substitution.

    Mirrors curate._resolve_deck_slug (curate.py:593): prefer the engine-upkept
    working/copy/intake.json, fall back to the frozen state.json snapshot, then to
    run_dir.name. Slugified to [a-z0-9-] so a deck title can never produce a path
    with characters the shell or the filesystem would mangle.
    """
    slug = None

    # Pass 1: engine-upkept copy (LIVE).
    engine_copy = run_dir / "working" / "copy" / "intake.json"
    try:
        obj = json.loads(engine_copy.read_text(encoding="utf-8"))
        if isinstance(obj, dict):
            slug = obj.get("deck_slug") or obj.get("title") or None
    except (json.JSONDecodeError, OSError):
        pass

    # Pass 2: frozen state.json (STALE -- fallback only).
    if not slug:
        state_file = run_dir / "state.json"
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            intake = state.get("intake") or {}
            slug = intake.get("deck_slug") or intake.get("title") or None
        except (json.JSONDecodeError, OSError):
            pass

    # Pass 3: ultimate fallback.
    if not slug:
        slug = run_dir.name

    slug = str(slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-") or "deck"
    return slug


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
# 38 -> 39: Feature L2-D (Gauntlet Loop 2, Feature B) adds P8.25-WORKBOOK — the fillable
# PDF workbook phase (kie.ai gpt-image-2 backgrounds + reportlab AcroForm assembly,
# scripts/workbook_builder.py) — raising manifest_version to 39 in the same commit.
# 39 -> 40: Feature L2-G (Gauntlet Loop 2, Feature C) adds P9.6-WEBINAR-VIDEO — the
# webinar video phase (ffmpeg Ken Burns + xfade slideshow + GHL v3 500MB video upload,
# scripts/build_webinar_video.py) + AF-WEBINAR-SIZE autofail — raising manifest_version
# to 40 in the same commit.
# 46 -> 47: wave-2 integrate 56d18ad2 — PIPELINE-MANIFEST.json bumped to 47 in the same commit; MIN follows so the U019 floor moves WITH the manifest (proven by the repo-manifest guard test in test_client_package.py).
# 47 -> 48: swarm integration 0612bbc5 — T2 stack bumped PIPELINE-MANIFEST.json to 48; MIN follows.
# 48 -> 49: heartbeat-ceiling repair — 13 of 36 phases declared heartbeat_minutes greater
# than that phase's own PHASE_BUDGET_MINUTES entry (E3 drift; a heartbeat interval longer
# than the whole phase can never detect a stall inside it). Precedent for bumping on a
# heartbeat_minutes-only content edit: WI-10 (CHANGELOG v22.0.5) bumped 44 -> 45 for the
# same class of change (heartbeat_minutes values across all 36 phases, no new phase/AF
# code). Tightened via heartbeat_minutes = min(old_value, PHASE_BUDGET_MINUTES[id]) on
# those 13 phases only; MIN follows to 49 in the same commit per U019 step 8.
# 49 -> 50: min_bytes split-brain reconciliation (2026-08-18) -- speech_pdf and
# teleprompter_html carried orphaned pre-doctrine values (20480 / 10240, dated
# 2026-06-17, predating the 2026-07-12 SOP reconciliation) that disagreed with
# deliverables.py / build_deck.py's already-reconciled floors (3000 / 20000).
# Content-only edit to two existing entries, same class of change as WI-10
# (44 -> 45, heartbeat_minutes-only); MIN follows the manifest in the same commit.
MIN_MANIFEST_VERSION = 50  # MUST EQUAL PIPELINE-MANIFEST.json's manifest_version. U019 step 8
    # (42 = WORKBOOK REDESIGN 2026-08-07: AF-WORKBOOK-PROMPT-NO-CONTENT / AF-WORKBOOK-EMPTY /
    #  AF-WORKBOOK-BOTH autofails + the P8.25-WORKBOOK phase rework)
    # (43 = F-H WEBINARIZED SPEECH 2026-08-07: P9-SPEECH-WEBINAR-INTRO phase + AF-WEBINAR-INTRO)
MIN_MANIFEST_PHASES = 36

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

