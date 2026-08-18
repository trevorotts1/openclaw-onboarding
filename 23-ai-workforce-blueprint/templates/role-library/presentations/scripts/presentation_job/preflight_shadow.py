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

SCOPED ATTESTATION-EXPLAINED DIVERGENCES (retried/resumed phases, see
`_attested_artifact_shas_for` and `record()`'s `artifact_spec` param): a bare
hash divergence cannot tell "the pipeline itself legitimately rewrote this
artifact between admission and this gate reading it" (a QC send-back loop's
re-author-and-remeasure retry — `run_signature_deck.run_copy_qc_loop` /
`run_prompt_qc_loop` — or a resumed phase re-dispatched via `--phase`) apart
from "something changed it that shouldn't have" — both are, at the byte
level, just "different content than what was sealed". Verified empirically
(driving real retries through the actual `run_signature_deck.py` phase
harness, not simulated): every legitimate phase completion computes
`sha256(current artifact bytes)` via `run_signature_deck._compute_artifact_sha`
and writes it as `attest_phase()`'s `artifact_sha` into
`process_manifest.json`'s `phase_attestations`, keyed by that phase's own
`phase_id`, BEFORE this preflight pass can observe the new content.

A REJECTED earlier version of this fix explained a divergence whenever
`hash_at_check` matched ANY artifact_sha EVER attested for the WHOLE run,
regardless of which artifact or phase attested it — an unscoped global pool.
That traded the false positive for a worse defect: real tampering of artifact
B is silently laundered as "explained" the moment its bytes happen to match
something legitimately attested for a completely different artifact A under a
different phase (proven — see `test_preflight_shadow_scoped.py`'s
`case_scoping_closes_cross_artifact_laundering`). THIS version never makes
that mistake: `_attested_artifact_shas_for(run_dir, artifact_spec)` first
resolves, from `PIPELINE-MANIFEST.json`'s own `phases[].produces_artifact`
declarations (the SAME authoritative spec `_compute_artifact_sha` resolves
against when a real attestation is written), the SET of phase_id(s) the
manifest actually names as THIS artifact's producer — then only collects
`artifact_sha` values from `phase_attestations` entries whose `phase_id` is in
that set. A hash attested for a different artifact's phase can never explain
THIS gate's divergence, no matter how it got there. A hand-edit that bypasses
the phase harness entirely (no attestation exists under any owning phase_id)
is unaffected and still flags exactly as before.

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

# Single source of truth for these four literals — see
# trust_boundary_prefixes.py's module docstring for why this changed from a
# locally-hardcoded copy (the parser, trust_boundary_observability.py, had
# its own independent copy that omitted the `-PREFLIGHT-` infix entirely and
# silently parsed none of this module's output as a result).
from trust_boundary_prefixes import (  # noqa: E402
    PREFLIGHT_DIVERGENCE_PREFIX as DIVERGENCE_PREFIX,
    PREFLIGHT_WOULD_BLOCK_PREFIX as WOULD_BLOCK_PREFIX,
    PREFLIGHT_ERROR_PREFIX as ERROR_PREFIX,
    PREFLIGHT_SUMMARY_PREFIX as SUMMARY_PREFIX,
)

SHADOW_LEDGER_REL = Path("working") / "checkpoints" / "preflight-shadow.jsonl"


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


def _find_manifest_path() -> Optional[Path]:
    """Locate PIPELINE-MANIFEST.json the SAME way `manifest_source.resolve_manifest()`
    does (installed `sops/` dir, cluster walk-up, legacy fallback paths) WITHOUT ever
    calling that function directly: `resolve_manifest()` calls its own `refuse()` ->
    `sys.exit(2)` on ANY resolution failure (missing manifest, or a
    MANIFEST-SOURCE.txt content_sha256 mismatch) — a hard process exit that would
    violate this module's report-only, can-never-abort-the-process contract the
    instant this function ran inside `record()`.

    Deliberately skips `resolve_manifest()`'s provenance-hash ENFORCEMENT (the
    content_sha256 comparison that triggers `refuse()`) — irrelevant for what this
    function is used for (a read-only, best-effort lookup of which phase_id owns
    an artifact spec, purely to scope attestation reuse). A stale-hash manifest
    can only make ownership resolution LESS available here, same as every other
    failure mode in this module — the SAFE direction, never the reverse.

    Never raises. Returns None on any failure (repo root not found, no manifest
    file exists at any candidate path)."""
    try:
        # Same HERE run_signature_deck.py resolves against: this module lives one
        # directory deeper (presentation_job/), so .parent.parent lands on the
        # shared `presentations/scripts` directory.
        here = Path(__file__).resolve().parent.parent
        sops_dir = here.parent / "sops"
        installed = sops_dir / "PIPELINE-MANIFEST.json"
        if (sops_dir / "MANIFEST-SOURCE.txt").is_file() and installed.is_file():
            return installed
        from manifest_source import find_repo_root  # noqa: PLC0415
        root = find_repo_root(here)
        if root is not None:
            cluster = root / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
            if cluster.is_file():
                return cluster
        if installed.is_file():
            return installed
        legacy = here.parent / "PIPELINE-MANIFEST.json"
        if legacy.is_file():
            return legacy
        return None
    except Exception:  # noqa: BLE001
        return None


def _phase_ids_for_artifact_spec(artifact_spec: Optional[str]) -> frozenset:
    """Resolve which phase_id(s) `PIPELINE-MANIFEST.json` names as the legitimate
    producer of `artifact_spec` — the EXACT `rel` string a PREFLIGHT_REQUIRED entry
    carries (a plain path or an unexpanded glob, e.g. `working/qc/copy_qc_report.json`
    or `working/research/brief-*.md`). Matched by literal string equality against
    each phase's own `produces_artifact` field, split on `' + '` for the one
    paired-artifact phase (`P8.25-WORKBOOK`) — the SAME spec string
    `run_signature_deck._compute_artifact_sha` resolves when a real attestation is
    written, so this is a direct read of the single source of truth `attest_phase()`
    itself is grounded in, not a guessed or hand-maintained mapping. More than one
    phase_id may legitimately own the same spec (e.g. `working/copy/intake.json` is
    produced by `P-CONVERTER`, `P0A-INTAKE`, AND `P-SP-CLAIM` in the manifest as of
    this writing) — all are returned; ownership is a set membership test, not a
    single winner.

    Never raises. Degrades to an empty frozenset on any failure (manifest
    unreadable, `artifact_spec` falsy/None, no phase declares this spec) — the SAFE
    direction: no resolved owner means no hash can ever explain a divergence on
    this artifact, so a failure here can only leave `record()` MORE likely to flag,
    never less."""
    if not artifact_spec:
        return frozenset()
    try:
        manifest_path = _find_manifest_path()
        if manifest_path is None:
            return frozenset()
        obj = json.loads(manifest_path.read_text(encoding="utf-8", errors="replace"))
        if not isinstance(obj, dict):
            return frozenset()
        owners = set()
        for ph in obj.get("phases", []) or []:
            if not isinstance(ph, dict):
                continue
            art = ph.get("produces_artifact", "")
            if not isinstance(art, str) or not art:
                continue
            members = [m.strip() for m in art.split(" + ") if m.strip()]
            if artifact_spec in members:
                pid = ph.get("id")
                if isinstance(pid, str) and pid:
                    owners.add(pid)
        return frozenset(owners)
    except Exception:  # noqa: BLE001
        return frozenset()


def _attested_artifact_shas_for(run_dir: Path, artifact_spec: Optional[str]) -> frozenset:
    """Read `working/checkpoints/process_manifest.json`'s `phase_attestations`
    (written ONLY by `run_signature_deck.attest_phase` — the same harness every
    phase, QC send-back loop retry, and resumed run goes through on legitimate
    completion) and return the set of `artifact_sha` values attested by a phase_id
    that `PIPELINE-MANIFEST.json` names as `artifact_spec`'s OWN legitimate
    producer (`_phase_ids_for_artifact_spec`) — SCOPED, never a global pool across
    every artifact in the run.

    This is the fix for the laundering hole a REJECTED earlier version of this
    module had: that version's `_attested_artifact_shas()` collected artifact_sha
    from EVERY attestation in the whole run with no phase/artifact filter at all,
    so a hash legitimately attested for artifact A's phase could wrongly explain a
    divergence on a completely unrelated artifact B. Filtering `att.get("phase_id")`
    against the owner set resolved for THIS SPECIFIC artifact_spec closes that: a
    hash can only explain this gate's divergence if it was attested BY THE
    PHASE(S) THE MANIFEST NAMES AS THIS ARTIFACT'S OWN producer.

    If no owner phase_id resolves for `artifact_spec` (manifest unreadable, or
    this spec isn't a declared `produces_artifact` at all), returns an empty
    frozenset immediately — there is no legitimate-rewrite explanation available,
    and nothing in `phase_attestations` should be trusted to supply one.

    `attest_phase()` REFUSES to attest with an empty `artifact_sha` (FATAL, exits
    2 — see its own docstring) and always uses `"no-artifact-spec"` as the marker
    for phases with no concrete artifact; that marker is excluded here so it can
    never accidentally "explain" a real file's divergence.

    Never raises. Missing/unparseable/absent `process_manifest.json`, or any
    attestation entry missing/malformed, degrades to an empty set — the SAFE
    direction, matching `_phase_ids_for_artifact_spec`'s own contract."""
    owners = _phase_ids_for_artifact_spec(artifact_spec)
    if not owners:
        return frozenset()
    try:
        pm_path = run_dir / "working" / "checkpoints" / "process_manifest.json"
        if not pm_path.is_file():
            return frozenset()
        obj = json.loads(pm_path.read_text(encoding="utf-8", errors="replace"))
        if not isinstance(obj, dict):
            return frozenset()
        shas = set()
        for att in obj.get("phase_attestations", []) or []:
            if not isinstance(att, dict):
                continue
            if att.get("phase_id") not in owners:
                continue
            sha = att.get("artifact_sha")
            if isinstance(sha, str) and sha and sha != "no-artifact-spec":
                shas.add(sha)
        return frozenset(shas)
    except Exception:  # noqa: BLE001
        return frozenset()


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
           resolved_path: Optional[Path], legacy_reason,
           artifact_spec: Optional[str] = None) -> None:
    """Call ONCE per PREFLIGHT_REQUIRED entry, immediately after the loop's own
    `check(...)` call has already produced `legacy_reason` — this function
    never receives the check callable itself and therefore can never call
    it, delay it, skip it, or change its result. `legacy_reason` is exactly
    whatever the real gate returned (falsy/empty-string on pass, a reason
    string on fail — the same value run_preflight()'s own `if reason:`
    branch already tests, so this module's PASS/FAIL bookkeeping can never
    disagree with what the real loop just decided with that same value).

    `artifact_spec` is the entry's OWN `rel` value from PREFLIGHT_REQUIRED (the
    literal path/glob string build_deck.py already has in scope in its loop) —
    passed explicitly, never inferred from `display` (which happens to equal
    `rel` today only by call-site convention, too fragile a coupling to lean on
    for a scoping decision this security-relevant). Defaults to None so any
    existing/older call site that omits it degrades to the SAFE behavior: no
    artifact_spec means no attestation lookup can ever explain a divergence for
    that call, i.e. behaves exactly like the pre-attestation-aware baseline.

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
        # SCOPED attestation check (see module docstring's "SCOPED
        # ATTESTATION-EXPLAINED DIVERGENCES" section and
        # _attested_artifact_shas_for's own docstring for the full rationale
        # and the laundering hole this closes). hash_at_check is the only side
        # ever matched (never hash_at_seal) — the question is always "is the
        # CURRENT content something the phase(s) that own THIS artifact
        # (per PIPELINE-MANIFEST.json) themselves vouch for", not the stale
        # seal, and never "does this hash appear ANYWHERE in the run".
        explained = False
        if diverged and hash_at_check is not None:
            explained = hash_at_check in _attested_artifact_shas_for(ctx.run_dir, artifact_spec)
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
            # A real divergence, but PIPELINE-MANIFEST.json-scoped
            # phase_attestations independently corroborate the CURRENT bytes
            # as a legitimate completion of THE PHASE(S) THAT OWN THIS
            # ARTIFACT — a retried/resumed phase rewriting its own output, not
            # tamper. Recorded in the ledger for audit (nothing hidden), but
            # never counted as a divergence/would-have-blocked and never
            # shouted to stderr as one.
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
                # AND no manifest-scoped phase attestation vouches for the new
                # bytes either.
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
        # WIRE FORMAT IS A CONTRACT, NOT COSMETIC: trust_boundary_observability.py's
        # _PREFLIGHT_SUMMARY_RE is a strict, field-order-and-adjacency regex parsing
        # this EXACT line shape (run_dir=... entries=... divergences=...
        # would_have_blocked=... ledger=...), proven by
        # tests/test_trust_boundary_observability.py's
        # test_clean_run_summary_line_is_parsed. Inserting a new field here (an
        # earlier draft of this fix added `explained_divergences=` between
        # divergences= and would_have_blocked=) silently breaks that parser to
        # "UNRECOGNISED-SHAPE" — this module's OWN docstring warns this exact
        # failure mode already happened once (trust_boundary_observability.py's
        # prefix-constant drift). explained_divergence_count is NOT dropped —
        # it's a real field on `ctx` and every explained divergence already has
        # its own full JSONL ledger line (explained_by_attestation=true) via
        # record(), which is the durable per-gate audit trail this one-line
        # human-skim summary was never meant to duplicate. Do not add fields to
        # this f-string without updating trust_boundary_observability.py's
        # _PREFLIGHT_SUMMARY_RE and its test in the SAME change.
        _safe_print(
            f"{SUMMARY_PREFIX} run_dir={ctx.run_dir} entries={ctx.entry_count} "
            f"divergences={ctx.divergence_count} "
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
