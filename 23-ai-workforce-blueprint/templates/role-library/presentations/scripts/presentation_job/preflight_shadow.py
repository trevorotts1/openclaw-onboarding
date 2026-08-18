"""presentation_job/preflight_shadow.py — trust-boundary Phase 1, surface A.

Report-only shadow instrumentation for the ONE dispatch loop that invokes all
53 `_chk_*` gates (plus 7 non-`_chk_`-named checks — 60 entries total) that
guard `build_deck.py`'s render/assembly: the
`for rel, label, phase, check in PREFLIGHT_REQUIRED:` loop inside
`run_preflight()` (`build_deck.py:9795`, dispatching `PREFLIGHT_REQUIRED`,
`build_deck.py:9095-9623`). See `CONTROL/TRUST-BOUNDARY-BUILD-SPEC.md` §7.2
for the design this module implements.

WHAT THIS IS: a generic, gate-agnostic wrapper. It has ZERO knowledge of what
any individual `_chk_*` gate means — it only knows the shape every entry in
PREFLIGHT_REQUIRED already shares: a resolved artifact path (or the whole run
dir, for the handful of run-dir-scoped checks) and a legacy pass/fail
verdict. What it adds, for every one of the 60 entries, for free, with ZERO
edits to any gate body:

  1. A TOCTOU integrity check: hash+mtime the resolved path ONCE, up front,
     before `run_preflight()`'s loop has called a single gate (the "seal");
     hash it again the moment that gate's own legacy check has just run (the
     "read"). A divergence means the file changed WHILE this preflight pass
     was running — a same-process-lifetime race/tamper signal that needs no
     domain knowledge of what the file is supposed to contain.
  2. An append-only ledger, `working/checkpoints/preflight-shadow.jsonl`, one
     JSON line per gate per `run_preflight()` call, naming: which gate
     (`gate_label`), which artifact (`resolved_path`), the legacy result,
     both hashes, and whether `PRES_TRUST_BOUNDARY_ENFORCE` was set (for
     audit only — Phase 1 never reads that flag to change behavior here).
  3. A `would_have_blocked` tally: any entry where the legacy check PASSED
     but the artifact it just read had already changed since the seal —
     exactly the shape a future Stage-1 enforcement would refuse. Phase 1
     records it. It never blocks.

FALSE-POSITIVE FIX (retried phases / resumed runs, see `_attested_artifact_shas`
and `record()`): a bare hash divergence cannot tell "the pipeline itself
rewrote this artifact in the normal course of work" (a QC send-back loop's
re-author-and-remeasure retry — `run_signature_deck.run_copy_qc_loop` /
`run_prompt_qc_loop` — or a resumed phase re-dispatched via `--phase`) apart
from "something changed it that shouldn't have" — both are, at the byte
level, just "different content than what was sealed". Verified empirically
(driving real retries through the actual `run_signature_deck.py` phase
harness, not simulated): every legitimate phase completion — first pass OR a
retry — computes `sha256(current artifact bytes)` via
`run_signature_deck._compute_artifact_sha` and writes it as
`attest_phase()`'s `artifact_sha` into `process_manifest.json`'s
`phase_attestations`, BEFORE this preflight pass can observe the new
content. `record()` checks whether the CURRENT hash it just computed
(`hash_at_check`) appears in that attested set; if so, the divergence is
`explained_by_attestation` — still recorded in the ledger (nothing hidden),
but never added to `divergence_count` / `would_have_blocked` and never
shouted to stderr, because it IS the pipeline's own legitimate output, not
tamper. A hand-edit that bypasses the phase harness (the pipeline never
attested it) has no matching `artifact_sha` and still flags exactly as
before. Shares this module's honest limit with the rest of this
trust-boundary work (see `runfacts.py`'s docstring): same-UID
tamper-evidence, not a cryptographic guarantee against an adversary who
could also forge an attestation by going through `attest_phase()` itself.

REPORT-ONLY, BY CONSTRUCTION, NOT BY DISCIPLINE:
  - Every public function here returns None, or a value the caller already
    had before calling it — nothing this module computes is consulted by
    run_preflight()'s if/else branching. There is no `if enforcing(): return
    worse_result` branch anywhere in this file for surface A (per the build
    spec's §7.2 last bullet: "Never blocks. No enforcing() branch at all in
    Phase 1 for this surface"). The single `PRES_TRUST_BOUNDARY_ENFORCE` flag
    (owned by `presentation_job.runfacts`, read here ONLY to stamp it into
    each ledger line for audit) cannot change what `run_preflight()` does,
    even when set — the only thing set-and-look-at-this-file-later changes
    is what a human reviewing the ledger sees next to each divergence.
  - Every public function is wrapped in `try/except Exception` and degrades
    to a no-op on any failure. A bug in this module must never be able to
    turn into a build failure or change a legacy gate's verdict — matches
    the existing `shadow_compare()` / `seal()` contract elsewhere in this
    trust-boundary work (`presentation_job/runfacts.py`).

Consumed by `build_deck.py` at exactly two points inside `run_preflight()`:
one call before the loop (`open_run`), one call inside the loop right after
each gate's legacy result is already decided (`record`). `close_run` is
optional (a one-line summary to stderr); nothing downstream depends on it.
See `build_deck.py`'s own comments at those call sites for the exact diff —
this module is the entire wrapper; `build_deck.py` gets one import line plus
three call lines inside `run_preflight()`, and zero edits to any of the 53
`_chk_*` (or 7 other) gate bodies.

Deliberately NOT done here (out of scope for this module, see the build
spec's §4 "extend, don't rebuild" and §7.2's own scoping note):
  - No domain-specific `Fact`/`Verdict` modeling of what any artifact's
    *content* should say (that's Phase 2, gate-by-gate, using
    `presentation_job.runfacts` / `verifier_registry.py` — untouched by this
    module, which only ever calls the single already-public
    `presentation_job.runfacts.enforcing()` read, never edits that file).
  - No new env var. Reuses the one flag the rest of this trust-boundary work
    already established (`PRES_TRUST_BOUNDARY_ENFORCE`), per the build
    spec's §7.4 ("one flag, recorded twice, for two different reasons").
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SHADOW_LEDGER_REL = Path("working") / "checkpoints" / "preflight-shadow.jsonl"

DIVERGENCE_PREFIX = "TRUST-BOUNDARY-PREFLIGHT-DIVERGENCE"
WOULD_BLOCK_PREFIX = "TRUST-BOUNDARY-PREFLIGHT-WOULD-BLOCK"
ERROR_PREFIX = "TRUST-BOUNDARY-PREFLIGHT-SHADOW-ERROR"
SUMMARY_PREFIX = "TRUST-BOUNDARY-PREFLIGHT-SUMMARY"


def _hash_and_mtime(path: Optional[Path]) -> Tuple[Optional[str], Optional[float]]:
    """sha256 hex + mtime for a real file, (None, None) for anything else
    (path is None, doesn't exist, unreadable, is a directory). Never raises —
    this is a report-only probe, not a gate; an unreadable file is itself a
    fact (recorded as a None/None pair, distinguishable from a real hash),
    never an exception that could propagate into run_preflight()."""
    if path is None:
        return None, None
    try:
        p = Path(path)
        if not p.is_file():
            return None, None
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest(), p.stat().st_mtime
    except Exception:  # noqa: BLE001 — a hashing failure is data, not a crash
        return None, None


def _enforcing_flag() -> bool:
    """Read the ONE existing PRES_TRUST_BOUNDARY_ENFORCE flag — owned by
    presentation_job.runfacts, not duplicated here — for RECORDING ONLY
    (stamped into each ledger line). Lazy import, defensive: any failure
    (module missing, import cycle, whatever) degrades to False, i.e. to the
    report-only reading — an import error must never make this MORE strict
    than the flag being unset would."""
    try:
        from presentation_job import runfacts as _rf  # noqa: PLC0415
        return _rf.enforcing()
    except Exception:  # noqa: BLE001
        return False


def _attested_artifact_shas(run_dir: Path) -> frozenset:
    """FALSE-POSITIVE FIX (see module docstring addendum below _resolve_entry_path):
    read working/checkpoints/process_manifest.json's `phase_attestations` (written
    ONLY by run_signature_deck.attest_phase — the same harness every phase, QC
    send-back loop retry, and resumed run goes through on legitimate completion,
    verified empirically: run_copy_qc_loop/run_prompt_qc_loop call
    `_compute_artifact_sha` then `attest_phase` on every pass including after
    re-authoring, and the plain per-phase dispatch path
    (run_signature_deck.py's `--phase` handling) does the same) and return the
    set of every `artifact_sha` value it has ever recorded for this run_dir.

    attest_phase() REFUSES to attest with an empty artifact_sha (FATAL, exits 2 —
    see its own docstring), and `_compute_artifact_sha` computes it as sha256 of
    the artifact's OWN current bytes at attestation time — for a single, non-glob
    file this is byte-identical to this module's own `_hash_and_mtime`'s hash
    (both are plain `hashlib.sha256(file_bytes).hexdigest()`), so a hash minted by
    THIS module matching one already vouched for by attest_phase is proof that
    exact content was independently produced and hashed by the pipeline's own
    phase-completion machinery — not merely present on disk.

    Never raises. Missing/unparseable/absent process_manifest.json, or any
    attestation entry missing/malformed, degrades to an empty set — the SAFE
    direction: a read failure here can only leave record() MORE likely to flag
    a divergence, never less, matching this module's existing report-only,
    never-more-permissive-on-error contract."""
    try:
        pm_path = run_dir / "working" / "checkpoints" / "process_manifest.json"
        if not pm_path.is_file():
            return frozenset()
        obj = json.loads(pm_path.read_text(encoding="utf-8", errors="replace"))
        if not isinstance(obj, dict):
            return frozenset()
        shas = set()
        for att in obj.get("phase_attestations", []) or []:
            if isinstance(att, dict):
                sha = att.get("artifact_sha")
                if isinstance(sha, str) and sha and sha != "no-artifact-spec":
                    shas.add(sha)
        return frozenset(shas)
    except Exception:  # noqa: BLE001 — degrade to "nothing attested", never raise
        return frozenset()


def _resolve_entry_path(run_dir: Path, rel: Optional[str]) -> Optional[Path]:
    """Mirror run_preflight()'s OWN artifact-resolution semantics exactly (same
    glob-if-'*'-in-rel-else-direct-exists-check, build_deck.py:9810-9815) so
    the up-front snapshot resolves the identical path the real loop resolves
    moments later. rel=None (the run-dir-scoped entries, e.g. _chk_coverage)
    has no single artifact to hash; those entries key into the same seal dict
    with a (None, None) baseline so they can never register a false
    divergence — surface A's run-dir-scoped entries are out of scope for this
    generic per-file check by construction, not by omission. Never raises."""
    try:
        if rel is None:
            return None
        if "*" in rel:
            matches = sorted(run_dir.glob(rel))
            return matches[0] if matches else None
        p = run_dir / rel
        return p if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


@dataclass
class PreflightShadowContext:
    """One instance per run_preflight() call — created by open_run(), threaded
    through every record() call in the loop, discarded (or passed to
    close_run() for a summary line) when the loop ends. Holds the admission-
    time ("seal") snapshot for every entry, keyed by gate label. Labels are
    verified unique across all 60 PREFLIGHT_REQUIRED entries as of this
    writing (60 entries, 60 unique labels — checked directly against the
    live list, not assumed); a future duplicate label would degrade to the
    second entry's seal overwriting the first's in this dict — never a
    crash, at worst a slightly stale seal for one of the two, still strictly
    report-only."""

    run_dir: Path
    sealed_at: str
    seal: Dict[str, Tuple[Optional[str], Optional[float]]] = field(default_factory=dict)
    ledger_path: Optional[Path] = None
    entry_count: int = 0
    divergence_count: int = 0
    explained_divergence_count: int = 0
    would_have_blocked: List[dict] = field(default_factory=list)


def open_run(run_dir: Path, entries) -> Optional[PreflightShadowContext]:
    """Call ONCE, at the top of run_preflight(), BEFORE the dispatch loop
    starts. `entries` is PREFLIGHT_REQUIRED itself, passed in as plain data —
    this function never imports build_deck and never calls any `_chk_*`
    function; it only reads `rel`/`label` off each 4-tuple. Snapshots every
    resolved artifact-scoped path's hash+mtime up front (the "seal" every
    later record() call compares against).

    Returns None on ANY failure (never raises) — callers must treat None as
    "shadow disabled for this run" and skip the later record()/close_run()
    calls' effects (both already no-op safely on ctx=None), never as an
    error that should surface to the operator or change run_preflight()'s
    own behavior."""
    try:
        run_dir = Path(run_dir)
        ctx = PreflightShadowContext(
            run_dir=run_dir,
            sealed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            ledger_path=run_dir / SHADOW_LEDGER_REL,
        )
        for entry in entries:
            try:
                rel, label = entry[0], entry[1]
            except Exception:  # noqa: BLE001 — a malformed entry just isn't sealed
                continue
            path = _resolve_entry_path(run_dir, rel)
            ctx.seal[label] = _hash_and_mtime(path)
        return ctx
    except Exception as exc:  # noqa: BLE001
        _safe_print(f"{ERROR_PREFIX} open_run: {exc!r} (report-only — shadow disabled this run)")
        return None


def record(ctx: Optional[PreflightShadowContext], *, label: str, display: str,
           resolved_path: Optional[Path], legacy_reason) -> None:
    """Call ONCE per PREFLIGHT_REQUIRED entry, immediately after the loop's own
    `check(...)` call has already produced `legacy_reason` — this function
    never receives the check callable itself and therefore can never call
    it, delay it, skip it, or change its result. `legacy_reason` is exactly
    whatever the real gate returned (falsy/empty-string on pass, a reason
    string on fail — the same value run_preflight()'s own `if reason:`
    branch already tests, so this module's PASS/FAIL bookkeeping can never
    disagree with what the real loop just decided with that same value).

    NEVER raises. NEVER returns a value the caller could act on — this is a
    pure side effect (one JSONL ledger line + at most two stderr lines)."""
    if ctx is None:
        return
    try:
        ctx.entry_count += 1
        hash_at_seal, mtime_at_seal = ctx.seal.get(label, (None, None))
        hash_at_check, mtime_at_check = _hash_and_mtime(resolved_path)
        legacy_ok = not bool(legacy_reason)
        # Both None (run-dir-scoped entry, or an artifact absent on both
        # sides) never counts as a divergence — only "we hashed something
        # different than what we sealed" does.
        diverged = (hash_at_seal is not None or hash_at_check is not None) and (
            hash_at_seal != hash_at_check
        )
        # FALSE-POSITIVE FIX: a diverged hash alone cannot tell "the pipeline
        # itself legitimately rewrote this between admission and this gate
        # reading it" (a QC send-back loop's re-author-and-remeasure retry, a
        # resumed phase) apart from "something changed it that shouldn't
        # have" -- both look identical as a bare byte-content diff. The
        # discriminator is process_manifest.json's phase_attestations (see
        # _attested_artifact_shas): every legitimate completion of the phase
        # that owns this artifact -- first pass OR a retry -- computes
        # sha256(current bytes) via run_signature_deck._compute_artifact_sha
        # and writes it as attest_phase()'s artifact_sha BEFORE this preflight
        # pass can observe the new content. A hand-edit that bypasses that
        # harness (the pipeline never touched it) leaves no such record.
        # hash_at_check is only ever matched (never hash_at_seal) — the
        # question is always "is the CURRENT content something the pipeline
        # itself vouches for", not the stale seal.
        explained = False
        if diverged and hash_at_check is not None:
            explained = hash_at_check in _attested_artifact_shas(ctx.run_dir)
        enforcing_now = _enforcing_flag()
        entry = {
            "gate_label": label,
            "display": display,
            "resolved_path": str(resolved_path) if resolved_path else None,
            "legacy_result": "PASS" if legacy_ok else "FAIL",
            "legacy_reason": (str(legacy_reason)[:500] if legacy_reason else None),
            "sealed_at": ctx.sealed_at,
            "hash_at_seal": hash_at_seal,
            "hash_at_check": hash_at_check,
            "mtime_at_seal": mtime_at_seal,
            "mtime_at_check": mtime_at_check,
            "toctou_divergence": diverged,
            "explained_by_attestation": explained,
            "enforcing_flag_set": enforcing_now,
        }
        _append_ledger(ctx.ledger_path, entry)
        if diverged and explained:
            # A real divergence, but process_manifest.json's own
            # phase_attestations independently corroborate the CURRENT bytes
            # as a legitimate phase completion -- a retried/resumed phase
            # rewriting its own output, not tamper. Recorded for audit
            # (nothing is hidden), but never counted as a divergence/
            # would-have-blocked and never shouted to stderr as one -- this
            # is exactly the "flag never flips on for honest work" fix.
            ctx.explained_divergence_count += 1
        elif diverged:
            ctx.divergence_count += 1
            _safe_print(
                f"{DIVERGENCE_PREFIX} gate={label} run_dir={ctx.run_dir} "
                f"path={entry['resolved_path']} "
                f"hash_at_seal={hash_at_seal} hash_at_check={hash_at_check} "
                f"legacy={entry['legacy_result']} enforcing_flag_set={enforcing_now}"
            )
            if legacy_ok:
                # The exact shape Stage-1 enforcement would refuse: the legacy
                # gate said PASS, but the artifact it just read is provably
                # NOT the same bytes this preflight pass sealed at admission,
                # AND no phase attestation vouches for the new bytes either.
                # Phase 1 records this and STILL lets the run proceed.
                ctx.would_have_blocked.append(entry)
                _safe_print(
                    f"{WOULD_BLOCK_PREFIX} gate={label} run_dir={ctx.run_dir} "
                    f"fact={label!r} source={entry['resolved_path']} "
                    f"reason='artifact changed between preflight admission and "
                    f"this gate reading it, and the new content is not an "
                    f"attested phase output' (report-only — run proceeds, no "
                    f"block issued)"
                )
    except Exception as exc:  # noqa: BLE001
        _safe_print(f"{ERROR_PREFIX} record gate={label}: {exc!r} (report-only — ignored)")


def close_run(ctx: Optional[PreflightShadowContext]) -> None:
    """Call ONCE after the dispatch loop finishes. Purely a one-line stderr
    summary for a human skimming a build log — every individual gate already
    got its own ledger line via record() regardless of whether this is ever
    called. Safe to skip on an early return/exception path; safe to call from
    a `finally`. Never raises."""
    if ctx is None:
        return
    try:
        _safe_print(
            f"{SUMMARY_PREFIX} run_dir={ctx.run_dir} entries={ctx.entry_count} "
            f"divergences={ctx.divergence_count} "
            f"explained_divergences={ctx.explained_divergence_count} "
            f"would_have_blocked={len(ctx.would_have_blocked)} "
            f"ledger={ctx.ledger_path}"
        )
    except Exception:  # noqa: BLE001
        pass


def _append_ledger(path: Optional[Path], entry: dict) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(entry, sort_keys=True, default=str) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _safe_print(msg: str) -> None:
    try:
        print(msg, file=sys.stderr)
    except Exception:  # noqa: BLE001
        pass
