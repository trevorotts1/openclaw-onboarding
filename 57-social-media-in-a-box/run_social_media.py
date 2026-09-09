#!/usr/bin/env python3
"""run_social_media.py — the deterministic state machine over SOCIAL-MANIFEST.json.

Walks the phases for the requested MODE IN ORDER with NO phase skips. Each
phase's preflight is checked against the run directory's artifacts; the QC
phases shell out to the fail-closed provers (preflight_gate.py, validate_
contract.py, prove_bands.py, scrub_gate.py) and refuse to advance on ANY
AF-SM-* violation. P6 shells to build_manifest.py which mints the process
certificate (a plain SHA-256 over the run's proven inputs — tamper-EVIDENT,
not a signature) proving ZERO Anthropic per run; the publisher (P7) refuses
to run without that certificate.

FRONT-DOOR NONCE: like the Email Engine / Presentations orchestrators, this
refuses to run unless OC_SMIB_ENTRY_NONCE matches the run-scoped nonce minted
by social-media-entry.sh (the ONE sanctioned entry). Model-free, provider-
neutral: it calls NO LLM and NO provider — it only sequences the gates.

EXIT CODES:
  0  all requested phases passed (certificate issued on a full run)
  2  a phase gate failed (fail-closed)
  3  usage / manifest error
  4  front-door nonce missing/mismatch (run through social-media-entry.sh)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

EXIT_PASS = 0
EXIT_GATE = 2
EXIT_USAGE = 3
EXIT_NONCE = 4

_SKILL_DIR = Path(__file__).resolve().parent
MANIFEST = _SKILL_DIR / "SOCIAL-MANIFEST.json"
SCRIPTS = _SKILL_DIR / "scripts"

# ===========================================================================
# F08 — EXPLICIT EXECUTION MODE (replaces _live_mode's heuristic)
# ---------------------------------------------------------------------------
# The OLD _live_mode() inferred live-vs-offline from RUN CONTENT: a nonempty
# `probes` object in the config OR a staged offline token OR a nonempty
# SMIB_PREFLIGHT_OFFLINE value flipped the run to a dry-run posture. Leftover
# test configuration on a client box therefore SILENTLY DISABLED live
# verification, and any nonempty value (including "0", the string for FALSE)
# counted as offline. Both are removed:
#
#   * execution_mode is EXPLICIT and IMMUTABLE. It is stamped ONCE at run
#     start by the trusted entry path (social-media-entry.sh writes
#     working/execution_mode.json AFTER its gates pass; the orchestrator
#     refuses to run when the stamp is absent/self-contradictory). The run
#     directory is the ONLY source — SMIB_PREFLIGHT_OFFLINE and staged probe
#     data no longer influence mode at all.
#   * PRODUCTION (mode "production") REJECTS any nonempty probes object with
#     a CONFIGURATION ERROR (fail closed) — probes are offline fixture data
#     and never belong in an installed client configuration.
#   * The offline escape hatch is the trusted TEST entry only: the test entry
#     stamps mode "test" (with the strict-parsed boolean it approved), and
#     only THEN do the legacy signals (a staged owner token / an explicitly
#     true SMIB_PREFLIGHT_OFFLINE) retain meaning as EVIDENCE of the posture.
#     SMIB_PREFLIGHT_OFFLINE parses strictly: "0"/"false"/""/absent -> false;
#     "1"/"true"/"yes"/"on" -> true; ANYTHING ELSE -> a configuration error
#     rather than a silent offline flip.
#   * DRY-RUN ARTIFACTS ARE STAMPED simulated=true (publish receipts, the
#     execution-mode record). Simulated receipts, offline exceptions and
#     test-run IDs can NEVER satisfy a LIVE completion or a published state:
#     the live gates (_chk_publish) consume ONLY execution_mode=production
#     evidence, and simulated evidence carries `simulated: true` which the
#     completion paths treat as intrinsically unsatisfying for live claims.
#   * Exceptional offline runs (owner-token-authorized) are recorded
#     SEPARATELY (working/execution_offline_exception.json), never inside a
#     simulated receipt masquerading as live.
# ===========================================================================
EXECUTION_PRODUCTION = "production"
EXECUTION_TEST = "test"
_TRUSTED_ENV_OFFLINE = "SMIB_PREFLIGHT_OFFLINE"


def _strict_bool(raw, field, run_dir):
    """F08 strict boolean parsing for a trusted-entry flag.
    "0"/"false"/"" (and unset) -> False; "1"/"true"/"yes"/"on" -> True;
    ANY other nonempty value -> raises ConfigurationError (never a silent
    offline flip)."""
    if raw is None:
        return False
    s = str(raw).strip().lower()
    if s in ("", "0", "false", "no", "off"):
        return False
    if s in ("1", "true", "yes", "on"):
        return True
    raise ConfigurationError(
        "AF-SM-EXEC-MODE: %s has a non-boolean value (%d chars, value never printed); "
        "allowed: 0/false/no/off/empty or 1/true/yes/on (run_dir=%s)"
        % (field, len(str(raw)), run_dir))


class ConfigurationError(Exception):
    """F08: a configuration that cannot safely run (e.g. probes present in
    production, or a non-boolean SMIB_PREFLIGHT_OFFLINE value). Fail-closed."""


def _read_execution_mode(run_dir):
    """Read the trusted entry's execution-mode stamp.
    Returns (mode:str, detail:dict). NEVER falls back to run content: a run
    without a stamp raises ConfigurationError (the orchestrator is started
    through social-media-entry.sh, which stamps it after its gates pass)."""
    rec = _json(run_dir, "working/execution_mode.json")
    if not isinstance(rec, dict) or not str(rec.get("mode", "")).strip():
        raise ConfigurationError(
            "AF-SM-EXEC-MODE: no trusted execution-mode stamp at working/execution_mode.json — "
            "run THROUGH social-media-entry.sh (the trusted entry stamps the mode after its gates pass)")
    mode = str(rec["mode"]).strip().lower()
    if mode not in (EXECUTION_PRODUCTION, EXECUTION_TEST):
        raise ConfigurationError(
            "AF-SM-EXEC-MODE: execution_mode %r is not one of (%s, %s)"
            % (mode, EXECUTION_PRODUCTION, EXECUTION_TEST))
    # IMMUTABILITY: the entry stamps set_by=trusted-entry; a stamp that claims
    # some other writer (or was rewritten mid-run with a contradicting
    # boolean) is refused.
    if str(rec.get("set_by", "trusted-entry")) != "trusted-entry":
        raise ConfigurationError(
            "AF-SM-EXEC-MODE: execution_mode stamp was not written by the trusted entry "
            "(set_by=%r) — refuse to trust" % rec.get("set_by"))
    return mode, rec


def _write_execution_mode(run_dir, mode, offline_reason=None):
    """Stamp the execution mode at run start. CALLED BY THE TRUSTED ENTRY
    PATH ONLY (social-media-entry.sh). The strict-parsed legacy signals are
    recorded as EVIDENCE of the posture, never as its CAUSE."""
    env_true = _strict_bool(os.environ.get(_TRUSTED_ENV_OFFLINE), _TRUSTED_ENV_OFFLINE, run_dir) \
        if os.environ.get(_TRUSTED_ENV_OFFLINE) is not None else False
    rec = {"mode": mode, "set_by": "trusted-entry", "simulated": mode != EXECUTION_PRODUCTION,
           "env_%s_resolved" % _TRUSTED_ENV_OFFLINE.lower(): env_true}
    if offline_reason:
        rec["offline_reason"] = str(offline_reason)
    p = Path(run_dir) / "working" / "execution_mode.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return rec


def _run_is_simulated(run_dir):
    """True when this run's execution mode is NOT production (a dry-run/test
    posture). Simulated runs stamp simulated=true on their artifacts."""
    mode, _rec = _read_execution_mode(run_dir)
    return mode != EXECUTION_PRODUCTION


def _assert_no_probes_in_production(run_dir):
    """F08 CORE REJECTION: production mode REJECTS any nonempty probes object
    in the client configuration (a configuration error, fail-closed)."""
    mode, _rec = _read_execution_mode(run_dir)
    if mode != EXECUTION_PRODUCTION:
        return
    cfg_obj = _json(run_dir, "working/copy/config.json", {}) or {}
    probes = cfg_obj.get("probes")
    if isinstance(probes, dict) and probes:
        raise ConfigurationError(
            "AF-SM-EXEC-MODE: probes present in a production configuration (%d key(s): %s) — "
            "offline fixture data must be removed from the installed client config; run "
            "the trusted test entry for a dry-run posture"
            % (len(probes), ", ".join(sorted(str(k) for k in list(probes)[:8]))))
    if probes not in (None, {}):
        raise ConfigurationError(
            "AF-SM-EXEC-MODE: probes present (non-object) in a production configuration — remove it")


def _stamp_simulated(obj, run_dir):
    """Return obj with simulated=true (F08: every dry-run artifact/receipt is
    labeled). Production runs return obj unchanged (a production receipt never
    carries a simulated flag)."""
    if not isinstance(obj, dict):
        return obj
    if _run_is_simulated(run_dir):
        obj["simulated"] = True
    return obj


def _record_offline_exception(run_dir, reason):
    """F08: an exceptional OFFLINE run (owner-token-authorized, production
    mode) is recorded SEPARATELY — never as a simulated live receipt."""
    rec = {"offline_exception": True, "reason": str(reason or ""),
           "recorded_at": _utc_now_iso()}
    p = Path(run_dir) / "working" / "execution_offline_exception.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return rec


def _offline_exception_on_record(run_dir):
    rec = _json(run_dir, "working/execution_offline_exception.json")
    return isinstance(rec, dict) and rec.get("offline_exception") is True


# ===========================================================================
# F05 — PRODUCER ADAPTER LAYER (behind the phase gates, never replacing them)
# ---------------------------------------------------------------------------
# run_social_media.py is the DETERMINISTIC STATE MACHINE: it checks artifacts,
# it does not author them. The MISSING HALF was the producer: a fresh run with
# valid config + an approved theme failed on missing working/plan/plan.json
# with nothing invoking production. Now every manifest phase can name a
# producer ADAPTER; the orchestrator invokes the phase's adapter BEFORE its
# gate when the gate's artifact is absent (or its inputs changed), so missing
# files TRIGGER PRODUCTION — or a specific dependency failure — and never a
# claim that production occurred.
#
# ADAPTER INTERFACE (one adapter per manifest phase):
#     def produce(run_dir, phase, ctx) -> {"ok": bool, "error"?: str, ...}
#   * ok=False fails the phase CLOSED with a specific message (a failed
#     producer is never a gate pass and never a fabricated artifact).
#   * The adapter owns HOW production happens (real adapters dispatch work
#     through the F33 execution policy / worker pool; stub/fake adapters used
#     in tests stamp receipts simulated=true and can NEVER satisfy a live
#     completion — the F08 gate contract already refuses simulated evidence).
#   * The gate (_chk_*) ALWAYS runs after the producer: the producer layer
#     sits BEHIND the gates, not replacing them. Every deterministic validator
#     is untouched.
#
# RECEIPTS (working/producers/receipts.json, one row per producer invocation):
#     phase, adapter, assigned_agent, execution_id, input_hashes (sha256 of
#     the adapter's declared inputs), output_hashes (sha256 of produced
#     artifacts), receipt (per-phase completion receipt), simulated flag.
# RESUME: on re-run a phase's outputs are reused ONLY when its declared input
# hashes still match; an edited input (e.g. a changed theme hash) reruns the
# producer and every downstream phase after it.
# ===========================================================================
PRODUCERS_RECEIPTS = "working/producers/receipts.json"


def _sha256_text(data):
    import hashlib
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _sha256_path(path):
    import hashlib
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


class ProducerError(Exception):
    """A producer adapter failed. Specific, never a fabricated success."""


class ProducerRegistry:
    """Adapter registry: real adapters register under their manifest phase id
    (the registry hook the F33 execution policy dispatches work through);
    register("stub", ...) replaces entries with a fake for tests."""

    def __init__(self):
        self._adapters = {}

    def register(self, phase_id, adapter, *, assigned_agent=None, inputs=None,
                 replaces=False):
        if phase_id in self._adapters and not replaces:
            raise ProducerError(
                "producer adapter for %r already registered (pass replaces=True "
                "to override — e.g. a stub in tests)" % phase_id)
        self._adapters[phase_id] = {
            "adapter": adapter, "assigned_agent": assigned_agent or "",
            "inputs": list(inputs or []),
        }
        return adapter

    def register_stub(self, phase_id, adapter, *, assigned_agent=None, inputs=None):
        return self.register(phase_id, adapter, assigned_agent=assigned_agent,
                             inputs=inputs, replaces=True)

    def get(self, phase_id):
        rec = self._adapters.get(phase_id)
        if rec is None:
            return None
        return dict(rec, phase_id=phase_id)

    def registered(self):
        return sorted(self._adapters)


#: The ONE default registry (real adapters register here; tests inject stubs
#: with replaces=True or build their own registry and pass it to run()).
PRODUCER_REGISTRY = ProducerRegistry()


def _producer_receipts(run_dir):
    rows = _json(run_dir, PRODUCERS_RECEIPTS, [])
    return rows if isinstance(rows, list) else []


def _write_producer_receipt(run_dir, rec):
    rows = [r for r in _producer_receipts(run_dir)
            if not (isinstance(r, dict) and r.get("phase") == rec.get("phase"))]
    rows.append(rec)
    p = Path(run_dir) / "working" / "producers" / "receipts.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return p


def _producer_input_hashes(run_dir, entry):
    """sha256 over the adapter's declared input files (theme, config, plan...).
    An input that cannot be hashed fails the producer CLOSED (unknown inputs
    can never justify reusing stale output)."""
    hashes = {}
    for rel in entry["inputs"]:
        p = Path(run_dir) / rel
        sha = _sha256_path(p)
        if sha is None:
            raise ProducerError(
                "producer input %s is missing/unreadable (fail-closed)" % rel)
        hashes[rel] = sha
    return hashes


def _outputs_reusable(run_dir, entry, input_hashes):
    """Resume contract: reuse ONLY outputs whose input hashes still match the
    receipt AND whose produced outputs still exist with matching output hashes.
    Any drift -> rerun (and downstream phases rerun after it)."""
    rows = [r for r in _producer_receipts(run_dir)
            if isinstance(r, dict) and r.get("phase") == entry["phase_id"]]
    if not rows:
        return False
    rec = rows[-1]
    if rec.get("input_hashes") != input_hashes:
        return False
    out = rec.get("output_hashes") or {}
    if not out:
        return False
    for rel, sha in out.items():
        if _sha256_path(Path(run_dir) / rel) != sha:
            return False
    return True


def _invoke_producer(run_dir, entry, *, execution_mode_simulated):
    """Invoke ONE phase's producer adapter and record its receipt. Returns
    (ok, msg). The gate ALWAYS still runs after this."""
    import datetime
    adapter = entry["adapter"]
    try:
        input_hashes = _producer_input_hashes(run_dir, entry)
    except ProducerError as exc:
        _write_producer_receipt(run_dir, {
            "phase": entry["phase_id"],
            "adapter": getattr(adapter, "__name__", repr(adapter)),
            "assigned_agent": entry["assigned_agent"],
            "input_hashes": {}, "output_hashes": {},
            "ok": False, "error": str(exc),
            "recorded_at": _utc_now_iso(),
        })
        return False, ("producer %s FAILED: %s — production did NOT occur (specific "
                       "dependency failure, never a fabricated completion)"
                       % (entry["phase_id"], exc))
    if _outputs_reusable(run_dir, entry, input_hashes):
        rows = [r for r in _producer_receipts(run_dir)
                if isinstance(r, dict) and r.get("phase") == entry["phase_id"]]
        rec = rows[-1]
        return True, ("producer %s REUSED (input hashes unchanged, outputs verified: %d "
                      "artifact(s))" % (entry["phase_id"], len(rec.get("output_hashes") or {})))
    ctx = {
        "phase_id": entry["phase_id"],
        "run_dir": run_dir,
        "input_hashes": input_hashes,
        "simulated": bool(execution_mode_simulated),
    }
    try:
        result = adapter(run_dir, entry["phase_id"], ctx)
    except Exception as exc:  # noqa: BLE001 — a producer crash is a producer failure
        _write_producer_receipt(run_dir, {
            "phase": entry["phase_id"], "adapter": getattr(adapter, "__name__", repr(adapter)),
            "assigned_agent": entry["assigned_agent"],
            "input_hashes": input_hashes, "output_hashes": {},
            "ok": False, "error": "producer raised: %s" % exc,
            "recorded_at": _utc_now_iso(),
        })
        return False, ("producer %s FAILED (raised %s) — production did NOT occur; "
                       "fix and re-run" % (entry["phase_id"], type(exc).__name__))
    result = result if isinstance(result, dict) else {"ok": bool(result)}
    ok = result.get("ok") is True
    outputs = result.get("outputs") or {}
    output_hashes = {}
    for rel in (outputs if isinstance(outputs, (list, dict)) else []):
        rel_path = rel if isinstance(rel, str) else str(rel)
        sha = _sha256_path(Path(run_dir) / rel_path)
        if sha is None:
            return False, ("producer %s declared output %s but it is missing on disk — "
                           "never a claim that production occurred"
                           % (entry["phase_id"], rel_path))
        output_hashes[rel_path] = sha
    rec = {
        "phase": entry["phase_id"],
        "adapter": getattr(adapter, "__name__", repr(adapter)),
        "assigned_agent": entry["assigned_agent"],
        "execution_id": result.get("execution_id") or ctx.get("execution_id") or "",
        "input_hashes": input_hashes,
        "output_hashes": output_hashes,
        "ok": bool(ok),
        "receipt": result.get("receipt"),
        "simulated": bool(result.get("simulated", execution_mode_simulated)),
        "recorded_at": _utc_now_iso(),
    }
    if not ok:
        rec["error"] = str(result.get("error") or "producer reported failure (no detail)")
        _write_producer_receipt(run_dir, rec)
        return False, ("producer %s FAILED: %s — production did NOT occur (specific "
                       "dependency failure, never a fabricated completion)"
                       % (entry["phase_id"], rec["error"]))
    _write_producer_receipt(run_dir, rec)
    return True, ("producer %s completed (%d artifact(s), %s)"
                  % (entry["phase_id"], len(output_hashes),
                     "SIMULATED=true" if rec["simulated"] else "live"))


def run_with_producers(manifest, mode, run_dir, *, registry=None):
    """F05 run loop: per phase, invoke the phase's producer adapter (when one is
    registered) BEFORE its gate, then run the unchanged deterministic gate.
    A producer failure BLOCKS with a specific message (exit 2, same as a gate
    failure) — the gate itself is untouched and still decides pass/fail."""
    reg = registry if registry is not None else PRODUCER_REGISTRY
    try:
        simulated = _run_is_simulated(run_dir)
    except ConfigurationError as exc:
        print("FATAL: %s" % exc, file=sys.stderr)
        return EXIT_GATE
    phases = manifest.get("modes", {}).get(mode)
    if not phases:
        print("FATAL: unknown mode %r" % mode, file=sys.stderr)
        return EXIT_USAGE
    gates = {}
    for pid in phases:
        ph = _phase(manifest, pid)
        if not ph:
            print("FATAL: phase %s missing from manifest" % pid, file=sys.stderr)
            return EXIT_USAGE
        checker = (ph.get("preflight") or {}).get("checker")
        print("=== PHASE %s — %s ===" % (pid, ph.get("name", "")))
        entry = reg.get(pid)
        if entry is not None:
            ok, msg = _invoke_producer(run_dir, entry, execution_mode_simulated=simulated)
            print("   [%s] producer: %s" % ("OK" if ok else "FAIL", msg))
            if not ok:
                gates[pid] = {"passed": False}
                _write_gates(run_dir, gates)
                _LAST_BLOCK.clear()
                _LAST_BLOCK.update({"phase_id": pid, "note": msg})
                print("BLOCKED at %s (producer failed; fail-closed). Fix and re-run." % pid,
                      file=sys.stderr)
                return EXIT_GATE
        ok, msg = _run_checker(checker, run_dir)
        print("   [%s] %s: %s" % ("OK" if ok else "FAIL", checker, msg))
        gates[pid] = {"passed": bool(ok)}
        # Persist gates BEFORE the manifest phase so build_manifest can read P0..P5.
        if pid != "P6-MANIFEST":
            _write_gates(run_dir, gates)
        if not ok:
            _write_gates(run_dir, gates)
            _LAST_BLOCK.clear()
            _LAST_BLOCK.update({"phase_id": pid, "note": msg})
            print("BLOCKED at %s (fail-closed). No phase skips; fix and re-run." % pid, file=sys.stderr)
            return EXIT_GATE
    _write_gates(run_dir, gates)
    print("ALL REQUESTED PHASES PASSED for mode '%s'." % mode)
    cert = run_dir / "delivery" / "PROCESS-CERTIFICATE.json"
    if cert.is_file():
        try:
            sha = json.loads(cert.read_text())["certificate_sha"]
            print("CERTIFICATE: %s (sha %s)" % (cert, sha[:12]))
        except (ValueError, KeyError):
            pass
    return EXIT_PASS


def _utc_now_iso():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

PLANNER_COLUMNS = ["Week Of", "Theme", "Research", "Core Content", "Images", "Videos",
                   "Facebook", "Instagram", "LinkedIn", "YouTube", "TikTok", "Pinterest",
                   "Carousels", "Blog", "Podcast", "Email", "QC", "Scheduled", "Overall", "Notes"]

# The failing (phase_id, note) captured at a gate failure so the fail-soft board
# seam (_mc_board_blocked, FIX-XC-06) can move the card to `blocked` with the AF
# code as the note. Mutated in place (no `global`) — read only by the board seam.
_LAST_BLOCK: dict = {}


def _load_manifest():
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("FATAL: cannot read SOCIAL-MANIFEST.json: %s" % exc, file=sys.stderr)
        sys.exit(EXIT_USAGE)


def _phase(manifest, pid):
    for ph in manifest.get("phases", []):
        if ph.get("id") == pid:
            return ph
    return None


def _nonce_ok(run_dir: Path) -> bool:
    want = os.environ.get("OC_SMIB_ENTRY_NONCE", "")
    nf = run_dir / "working" / "checkpoints" / ".smib-entry-nonce"
    if not want or not nf.is_file():
        return False
    try:
        return nf.read_text(encoding="utf-8").strip() == want.strip()
    except OSError:
        return False


def _run_script(script, args):
    """Run a prover and return its exit code. FIX-S36-62: the child's stdout+stderr
    are captured and, on FAILURE, re-printed to this process's stderr so the exact
    AF-SM-* code(s) reach the operator (the old DEVNULL redirects swallowed them,
    leaving only a bare 'FAILED (exit 2)'). Success stays quiet to keep the phase
    log readable."""
    cmd = [sys.executable, str(SCRIPTS / script)] + [str(a) for a in args]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True)
    if proc.returncode != 0 and proc.stdout:
        sys.stderr.write("--- %s output (exit %d) ---\n%s\n" % (script, proc.returncode, proc.stdout.rstrip()))
    return proc.returncode


def _json(run_dir, rel, default=None):
    try:
        return json.loads((run_dir / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


# ---- per-phase checkers -----------------------------------------------------
def _offline_token_ok(run_dir):
    """A LOGGED owner token that authorizes an OFFLINE preflight (dry-run posture)
    on a box that would otherwise probe live. Fail-closed shape: a dict with
    owner_approved/approved true + a non-empty reason. Absent/malformed -> no token."""
    tok = _json(run_dir, "working/copy/preflight-offline-token.json")
    if not isinstance(tok, dict):
        return False
    return (tok.get("owner_approved") is True or tok.get("approved") is True) \
        and bool(str(tok.get("reason", "")).strip())


def _chk_preflight(run_dir):
    """P0 readiness gate. FIX-S36-59 + F08:
      * ALWAYS pass --report so the Owner Q&A source-of-truth (credits/balance/token
        + the C2 connected-accounts reconcile) is written to disk, never memorized.
      * The run posture comes from the TRUSTED ENTRY's execution-mode stamp (F08):
        production runs preflight --live with NO probe fixtures (probes in a
        production config are a configuration error); test/simulated runs run the
        offline preflight against the staged probe data. A production run whose
        credentials cannot be probed live is NOT switchable to offline by leftover
        test configuration — an exceptional offline posture requires the logged
        owner token AND is recorded separately (execution_offline_exception.json)."""
    cfg = run_dir / "working" / "copy" / "config.json"
    if not cfg.is_file():
        return False, "missing working/copy/config.json"
    try:
        _assert_no_probes_in_production(run_dir)
        live = not _run_is_simulated(run_dir)
    except ConfigurationError as exc:
        return False, str(exc)
    if not live:
        token_ok = _offline_token_ok(run_dir)
        if not token_ok:
            return False, ("AF-SM-EXEC-MODE: a simulated/test run requires a logged owner "
                           "offline token (working/copy/preflight-offline-token.json) — "
                           "refusing an unlogged dry-run posture")
    report = run_dir / "working" / "preflight" / "preflight_report.json"
    args = [cfg, "--report", report]
    if live:
        args.append("--live")
    rc = _run_script("preflight_gate.py", args)
    mode = "LIVE probe (client box)" if live else "offline (trusted test entry + logged owner token)"
    return rc == 0, ("preflight PASS [%s], report -> working/preflight/preflight_report.json" % mode
                     if rc == 0 else "preflight_gate.py FAILED (exit %d) [%s]" % (rc, mode))


def _chk_plan(run_dir):
    plan = _json(run_dir, "working/plan/plan.json")
    if not isinstance(plan, dict):
        return False, "missing working/plan/plan.json"
    if not str(plan.get("themeOfWeek", "")).strip():
        return False, "plan.json has no themeOfWeek"
    if not str(plan.get("plannerSheetId", "")).strip():
        return False, "plan.json has no plannerSheetId"
    return True, "plan.json complete"


def _chk_content_authored(run_dir):
    if not (run_dir / "working" / "content").is_dir():
        return False, "missing working/content/"
    bands = list((run_dir / "working" / "content" / "bands").glob("*.json")) \
        if (run_dir / "working" / "content" / "bands").is_dir() else []
    if not bands and not (run_dir / "working" / "content" / "content.json").is_file():
        return False, "no content authored (working/content/bands/*.json or content.json)"
    return True, "content authored"


def _chk_contract_and_bands(run_dir):
    """F11: bands + contracts PASS, and the contract set is COMPLETE for the
    plan: zero contract files can no longer pass (the QC matrix is derived
    from the actual plan and requires a contract + QC result for EVERY
    planned item)."""
    cdir = run_dir / "working" / "content"
    bands_files = sorted((cdir / "bands").glob("*.json")) if (cdir / "bands").is_dir() else []
    contract_files = sorted((cdir / "contracts").glob("*.json")) if (cdir / "contracts").is_dir() else []
    if not bands_files:
        return False, "no bands inputs at working/content/bands/*.json"
    if not contract_files:
        return False, ("AF-SM-QC-MATRIX: ZERO content contracts present — the plan requires a "
                       "contract for every planned item (an empty contract set FAILS)")
    for f in bands_files:
        rc = _run_script("prove_bands.py", [f])
        if rc != 0:
            return False, "prove_bands FAILED on %s (exit %d)" % (f.name, rc)
    for f in contract_files:
        rc = _run_script("validate_contract.py", [f])
        if rc != 0:
            return False, "validate_contract FAILED on %s (exit %d)" % (f.name, rc)
    ok, _msg, failures = _verify_qc_matrix(run_dir)
    if not ok:
        return False, "; ".join(failures[:4]) + (" (+%d more)" % (len(failures) - 4) if len(failures) > 4 else "")
    return True, "bands + contracts PASS (%d bands, %d contracts) + complete QC matrix" % (
        len(bands_files), len(contract_files))


def _chk_media_ledger(run_dir):
    """F11: media completion is not trusted from a locally-supplied flag file
    alone — the terminal-jobs summary is cross-checked against the SQLite
    ledger (the jobs table is the record the media workers actually wrote)."""
    summ = _json(run_dir, "working/media/media_ledger.json")
    if not isinstance(summ, dict):
        return False, "missing working/media/media_ledger.json"
    if summ.get("all_terminal") is not True:
        return False, "media ledger has non-terminal jobs (incomplete run)"
    if summ.get("is_carousel") and summ.get("assemble_ok") is not True:
        return False, "carousel assembly floor not met (>=2 images)"
    # F11 independence check: reconcile the summary's numbers against the
    # ledger DB when present; a summary that contradicts the DB fails closed.
    db = run_dir / "working" / "media" / "ledger.db"
    if db.is_file():
        try:
            sys.path.insert(0, str(SCRIPTS))
            import ledger  # noqa: E402
            import sqlite3  # noqa: F401  (ledger owns its connection)
            run_id = str(summ.get("run") or run_dir.name)
            db_summary = ledger.summarize(db, run_id)
            if isinstance(db_summary, dict) and db_summary.get("total"):
                if int(db_summary.get("complete") or 0) < int(db_summary.get("total") or 0) \
                        and summ.get("all_terminal") is True:
                    return False, ("AF-SM-QC-MATRIX: media_ledger.json claims all_terminal but the "
                                   "ledger DB shows %d/%d complete (a locally-supplied completion "
                                   "flag cannot contradict the ledger)" % (
                                       db_summary.get("complete"), db_summary.get("total")))
        except Exception as exc:  # noqa: BLE001 — an unreadable ledger fails CLOSED
            return False, "media ledger DB unreadable (fail-closed): %s" % exc
    return True, "media ledger terminal (images_ready=%s)" % summ.get("images_ready")


def _chk_scrub(run_dir):
    # SK2-13: this is the RUNTIME scan over generated client content, so require the
    # client-name list — an unconfigured list must fail closed (a silent pass could
    # let a client name leak into published content), unlike the build-time scan.
    rc = _run_script("scrub_gate.py", ["--require-names", run_dir / "working"])
    return rc == 0, ("scrub PASS" if rc == 0 else "scrub_gate.py FAILED (exit %d)" % rc)


def _chk_manifest(run_dir):
    rc = _run_script("build_manifest.py", ["--run-dir", run_dir])
    if rc != 0:
        return False, "build_manifest.py FAILED (exit %d)" % rc
    if not (run_dir / "delivery" / "PROCESS-CERTIFICATE.json").is_file():
        return False, "no certificate issued"
    return True, "certificate issued"


def _live_mode(run_dir):
    """F08: True ONLY for a PRODUCTION-mode run (the trusted entry's stamp),
    False for a simulated/test posture. Run CONTENT (config probes, staged
    tokens, SMIB_PREFLIGHT_OFFLINE) no longer influences the mode at all —
    leftover test configuration cannot silently disable live verification.
    Raises ConfigurationError when the trusted stamp is absent/invalid, so a
    caller can never silently default."""
    return _read_execution_mode(run_dir)[0] == EXECUTION_PRODUCTION


# ===========================================================================
# F10 — PER-DESTINATION DELIVERY PROOF
# ---------------------------------------------------------------------------
# The delivery sheet registry (working/delivery/deliveries.json) stores ONE row
# per company/cycle/content-revision/account with the delivery.json contract
# fields (remote_post_id, scheduled_at, provider_state draft|scheduled|published|
# failed|unknown, checked_at, failure_reason, published_url). Publishing success
# is claimed per destination from an INDEPENDENT readback (ghl_contracts posts
# list with status fields): draft/failed/unknown NEVER count as published, a
# scheduled post is reconciled after its due time, only failed destinations are
# retried, and an ambiguous timeout is reconciled by content/account key BEFORE
# any retry (a create success + lost response adopts the existing post id —
# never a duplicate).
# ===========================================================================
DELIVERY_STATES = ("draft", "scheduled", "published", "failed", "unknown")
PUBLISHED_STATE = "published"


def _delivery_rows(run_dir):
    rows = _json(run_dir, "working/delivery/deliveries.json")
    return rows if isinstance(rows, list) else []


def _write_delivery_rows(run_dir, rows):
    p = Path(run_dir) / "working" / "delivery" / "deliveries.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return p


def _delivery_row_key(company_id, cycle_id, content_revision, account_id):
    return "%s|%s|%s|%s" % (str(company_id), str(cycle_id), str(content_revision), str(account_id))


def _upsert_delivery_row(run_dir, company_id, cycle_id, content_revision, account_id, **fields):
    """Insert/update the delivery row for this (company, cycle, revision,
    account) key. Unknown provider states normalize to 'unknown' (never
    silently 'published')."""
    state = str(fields.get("provider_state") or "unknown").strip().lower()
    if state not in DELIVERY_STATES:
        state = "unknown"
    rec = {
        "delivery_id": fields.get("delivery_id") or ("dlv-%s" % str(abs(hash(_delivery_row_key(
            company_id, cycle_id, content_revision, account_id))))[:16]),
        "company_id": str(company_id), "cycle_id": str(cycle_id),
        "content_revision": int(content_revision), "account_id": str(account_id),
        "remote_post_id": fields.get("remote_post_id"),
        "scheduled_at": fields.get("scheduled_at"),
        "provider_state": state,
        "checked_at": fields.get("checked_at") or _utc_now_iso(),
        "failure_reason": fields.get("failure_reason"),
        "published_url": fields.get("published_url"),
    }
    rows = [r for r in _delivery_rows(run_dir)
            if not (isinstance(r, dict)
                    and _delivery_row_key(r.get("company_id"), r.get("cycle_id"),
                                          r.get("content_revision"), r.get("account_id"))
                    == _delivery_row_key(company_id, cycle_id, content_revision, account_id))]
    rows.append(rec)
    _write_delivery_rows(run_dir, rows)
    return rec


def _expected_delivery_keys(run_dir):
    """F10: the EXPECTED delivery set, derived from the plan (plan.json's
    per-account plan rows / platform list), NOT from the poster's receipts.
    Returns a list of (company_id, cycle_id, content_revision, account_id)."""
    plan = _json(run_dir, "working/plan/plan.json", {}) or {}
    company_id = str(plan.get("companyId") or plan.get("company_id") or plan.get("locationId") or "")
    cycle_id = str(plan.get("cycleId") or plan.get("cycle_id") or plan.get("weekOf") or "")
    revision = plan.get("contentRevision") or plan.get("revision") or 1
    keys, seen = [], set()
    rows = plan.get("accounts") if isinstance(plan.get("accounts"), list) else []
    for a in rows:
        if not isinstance(a, dict):
            continue
        aid = str(a.get("account_id") or a.get("id") or "").strip()
        if not aid:
            continue
        k = _delivery_row_key(company_id, cycle_id, revision, aid)
        if k not in seen:
            seen.add(k)
            keys.append((company_id, cycle_id, revision, aid))
    if not keys:
        # No per-account plan rows: the configured platform LIST defines the
        # destinations (one expected delivery per configured channel).
        for p in (plan.get("platforms") or []):
            aid = str(p).strip()
            if not aid:
                continue
            k = _delivery_row_key(company_id, cycle_id, revision, aid)
            if k not in seen:
                seen.add(k)
                keys.append((company_id, cycle_id, revision, aid))
    return keys


def _reconcile_deliveries_from_listing(run_dir, listing):
    """F10 reconcile: read back EVERY expected delivery from the independent
    listing [{post_id, status, scheduled_at, published_url}] and upsert each
    row's provider state. Ambiguous timeouts (expected but absent, or a
    scheduled post past due) stay 'unknown' — they NEVER become published and
    they MUST be reconciled before any retry creates another post."""
    plan = _json(run_dir, "working/plan/plan.json", {}) or {}
    by_content = {}
    for p in (listing or []):
        if isinstance(p, dict) and p.get("post_id"):
            by_content[str(p["post_id"])] = p
    reconciled = []
    for (company_id, cycle_id, revision, account_id) in _expected_delivery_keys(run_dir):
        existing = None
        for r in _delivery_rows(run_dir):
            if isinstance(r, dict) and _delivery_row_key(
                    r.get("company_id"), r.get("cycle_id"), r.get("content_revision"),
                    r.get("account_id")) == _delivery_row_key(company_id, cycle_id,
                                                              revision, account_id):
                existing = r
                break
        # Idempotent adoption: match an EXISTING row/post by content+account
        # key before treating this destination as uncreated (a create success
        # with a lost response must adopt the remote post, never re-create).
        pid = str((existing or {}).get("remote_post_id") or "").strip()
        post = by_content.get(pid) if pid else None
        if post is None:
            # content-key scan: a post whose recorded account/revision matches
            plan_content = str(plan.get("contentRevision") or revision)
            for cand in (listing or []):
                if not isinstance(cand, dict):
                    continue
                meta = cand.get("meta") or {}
                if (str(meta.get("account_id") or "") == str(account_id)
                        and str(meta.get("content_revision") or plan_content) == str(revision)):
                    post = cand
                    break
        if post is None:
            reconciled.append(_upsert_delivery_row(
                run_dir, company_id, cycle_id, revision, account_id,
                provider_state="unknown",
                failure_reason="reconcile: no post read back for this destination (ambiguous — "
                               "reconcile before any retry creates another post)",
                remote_post_id=(existing or {}).get("remote_post_id"),
                scheduled_at=(existing or {}).get("scheduled_at"))
                if existing else
                _upsert_delivery_row(
                    run_dir, company_id, cycle_id, revision, account_id,
                    provider_state="unknown",
                    failure_reason="reconcile: no post read back for this destination"))
            continue
        reconciled.append(_upsert_delivery_row(
            run_dir, company_id, cycle_id, revision, account_id,
            remote_post_id=post.get("post_id"),
            provider_state=str(post.get("status") or "unknown").strip().lower(),
            scheduled_at=post.get("scheduled_at") or (existing or {}).get("scheduled_at"),
            published_url=post.get("published_url"),
            failure_reason=None))
    return reconciled


def _delivery_published_set(run_dir):
    """The account_ids whose CURRENT delivery state is published (from the
    delivery rows only — never from the poster's own receipts)."""
    out = set()
    for r in _delivery_rows(run_dir):
        if isinstance(r, dict) and str(r.get("provider_state") or "").strip().lower() \
                == PUBLISHED_STATE:
            out.add(str(r.get("account_id")))
    return out


def _retryable_deliveries(run_dir):
    """F10: ONLY failed destinations are retryable. 'unknown' (an ambiguous
    timeout) must be reconciled first — it is NOT a retry candidate."""
    out = []
    for r in _delivery_rows(run_dir):
        if isinstance(r, dict) and str(r.get("provider_state") or "").strip().lower() == "failed":
            out.append(r)
    return out


# ===========================================================================
# F11 — COMPLETE + INDEPENDENT QC EVIDENCE MATRIX
# ---------------------------------------------------------------------------
# The required contract/QC matrix is DERIVED FROM THE ACTUAL PLAN
# (working/plan/plan.json): EVERY planned artifact needs a content contract
# (working/content/contracts/<artifact>.json) AND an independent QC receipt
# (working/qc/qc_receipts.json rows per the artifact_qc_receipt.json W0
# contract). Empty, missing, or unrelated sets FAIL. A receipt must carry an
# independently-assigned reviewer (qc_reviewer_id != the artifact's producer,
# the reviewer identity resolved by the ORCHESTRATOR from the run's QC
# roster — never self-asserted by the receipt) and rubric results bound to
# the EXACT artifact sha256 + revision. Any edit to an approved artifact
# (hash mismatch) INVALIDATES that approval. Receipts are plain SHA-256
# evidence — no "signed" claim is made or implied.
# ===========================================================================
QC_RECEIPTS = "working/qc/qc_receipts.json"


def _artifact_sha256(run_dir, rel):
    import hashlib
    p = Path(run_dir) / rel
    if not p.is_file():
        return None
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return None


def _planned_artifacts(run_dir):
    """The plan's artifact list: [{artifact_id, revision, path}]. Derived from
    plan.json plannedItems (canonical) / artifacts; a plan without a declared
    artifact set fails closed upstream (the matrix cannot be derived)."""
    plan = _json(run_dir, "working/plan/plan.json", {}) or {}
    items = plan.get("plannedItems") or plan.get("artifacts") or []
    out = []
    for it in (items if isinstance(items, list) else []):
        if not isinstance(it, dict):
            continue
        aid = str(it.get("artifact_id") or it.get("id") or "").strip()
        rel = str(it.get("path") or "").strip()
        if not aid or not rel:
            continue
        try:
            rev = int(it.get("revision") or 1)
        except (TypeError, ValueError):
            rev = 1
        out.append({"artifact_id": aid, "revision": rev, "path": rel})
    return out


def _qc_reviewer_roster(run_dir):
    """The QC reviewer identities the ORCHESTRATOR assigned for this run
    (working/qc/reviewer_roster.json: [{artifact_id, reviewer_id}], written by
    the orchestrator's QC assignment step — the receipt itself can never
    assert its own reviewer)."""
    roster = _json(run_dir, "working/qc/reviewer_roster.json", [])
    return roster if isinstance(roster, list) else []


def _verify_qc_matrix(run_dir):
    """F11 CORE. Returns (ok, message, failures:list[str])."""
    plan = _json(run_dir, "working/plan/plan.json")
    if not isinstance(plan, dict):
        return False, "missing working/plan/plan.json (the QC matrix cannot be derived)", []
    planned = _planned_artifacts(run_dir)
    if not planned:
        return False, ("AF-SM-QC-MATRIX: plan.json declares NO planned artifacts — an empty "
                       "contract set FAILS (nothing to certify)"), \
            ["AF-SM-QC-MATRIX: plan.json declares NO planned artifacts"]
    cdir = run_dir / "working" / "content" / "contracts"
    contract_files = {f.stem: f for f in cdir.glob("*.json")} if cdir.is_dir() else {}
    receipts = _json(run_dir, QC_RECEIPTS, [])
    receipts = receipts if isinstance(receipts, list) else []
    by_artifact = {}
    for r in receipts:
        if isinstance(r, dict) and str(r.get("artifact_id") or "").strip():
            by_artifact[str(r["artifact_id"]).strip()] = r
    roster = {str(r.get("artifact_id")): str(r.get("reviewer_id") or "").strip()
              for r in _qc_reviewer_roster(run_dir) if isinstance(r, dict)}
    failures = []
    for it in planned:
        aid, rev, rel = it["artifact_id"], it["revision"], it["path"]
        # 1. the CONTRACT for this planned item must exist and be for THIS item
        cf = contract_files.get(aid)
        if cf is None:
            failures.append("AF-SM-QC-MATRIX: no content contract for planned item %r "
                            "(expected working/content/contracts/%s.json)" % (aid, aid))
            continue
        cobj = _json(run_dir, "working/content/contracts/%s.json" % aid, {}) or {}
        c_art = str(cobj.get("artifact_id") or "").strip()
        if c_art and c_art != aid:
            failures.append("AF-SM-QC-MATRIX: contract %s.json is for %r, not the planned item %r "
                            "(unrelated contract sets are rejected)" % (aid, c_art, aid))
        # 2. an UNRELATED qc json (not keyed to any planned artifact) cannot satisfy the gate
        receipt = by_artifact.get(aid)
        if receipt is None:
            failures.append("AF-SM-QC-MATRIX: no QC receipt for planned item %r (%s)"
                            % (aid, QC_RECEIPTS))
            continue
        if receipt.get("qc_result") != "pass":
            failures.append("AF-SM-QC-MATRIX: QC receipt for %r is not a PASS" % aid)
        # 3. reviewer INDEPENDENCE, verified through the ORCHESTRATOR's roster
        #    (not a self-asserted field on the receipt)
        producer = str(receipt.get("producer_id") or plan.get("producerId") or
                       plan.get("producer_id") or "").strip()
        reviewer = str(receipt.get("qc_reviewer_id") or "").strip()
        assigned = roster.get(aid, "")
        if not reviewer:
            failures.append("AF-SM-QC-MATRIX: QC receipt for %r records no reviewer identity" % aid)
        elif assigned and reviewer != assigned:
            failures.append("AF-SM-QC-MATRIX: QC receipt for %r claims reviewer %r but the "
                            "orchestrator assigned %r (self-asserted identity rejected)"
                            % (aid, reviewer, assigned))
        elif not assigned:
            failures.append("AF-SM-QC-MATRIX: no orchestrator-assigned reviewer for %r "
                            "(working/qc/reviewer_roster.json is the assignment of record)" % aid)
        if producer and reviewer and reviewer == producer:
            failures.append("AF-SM-QC-MATRIX: %r was approved by its own producer %r "
                            "(a producer cannot approve its own work)" % (aid, producer))
        # 4. rubric results bound to the EXACT artifact sha256 + revision
        want_sha = str(receipt.get("sha256") or "").strip()
        got_sha = _artifact_sha256(run_dir, rel)
        if not want_sha:
            failures.append("AF-SM-QC-MATRIX: QC receipt for %r records no artifact sha256" % aid)
        elif got_sha is None:
            failures.append("AF-SM-QC-MATRIX: approved artifact %r (%s) is MISSING on disk" % (aid, rel))
        elif want_sha != got_sha:
            failures.append("AF-SM-QC-MATRIX: %r was EDITED after approval (receipt sha %s..%s != "
                            "current %s..%s) — that approval is INVALIDATED, re-run QC"
                            % (aid, want_sha[:12], want_sha[-8:], got_sha[:12], got_sha[-8:]))
        try:
            got_rev = int(receipt.get("revision"))
        except (TypeError, ValueError):
            got_rev = None
        if got_rev != rev:
            failures.append("AF-SM-QC-MATRIX: QC receipt for %r is against revision %r, the plan "
                            "requires %r" % (aid, receipt.get("revision"), rev))
    return (not failures), ("QC matrix complete (%d planned item(s), contracts + independent "
                            "PASS receipts on exact sha256+revision)" % len(planned)), failures


def _live_ghl_post_listing(cfg):
    """FIX-S36-60 + F09: the live GHL social post listing for the location with
    the CLIENT's own PIT (never printed), via the DOCUMENTED S2 contract
    (POST /social-media-posting/{locationId}/posts/list with number-string
    skip/limit, results wrapper, skip/offset pagination — scripts/
    ghl_contracts.py is the one shared implementation). Returns a list of GHL
    post-id strings present in the account, or None when the listing is
    unconfirmable (fail-closed upstream). A CONTRACT-shape failure is NEVER
    misreported as zero posts."""
    try:
        sys.path.insert(0, str(SCRIPTS))
        import ghl_contracts  # noqa: E402
        pit = str(cfg.get("pit") or os.environ.get("GHL_API_KEY", ""))
        loc = str(cfg.get("locationId", ""))
        if not pit or not loc:
            return None
        posts = ghl_contracts.fetch_posts(pit, loc)
        return [p["post_id"] for p in posts if p.get("post_id")]
    except Exception:  # noqa: BLE001 — unconfirmable stays fail-closed upstream
        return None


def _live_ghl_account_plan(cfg):
    """F06/F09: the live per-account plan for this location (S1 documented
    contract, IDs preserved). Returns (accounts, error_dict|None): accounts is
    [] with an error dict when the discovery fails classified; error carries
    {error_class, retry_after} so callers can distinguish authentication /
    scope / disconnected_account / rate_limited / transient / contract."""
    try:
        sys.path.insert(0, str(SCRIPTS))
        import ghl_contracts  # noqa: E402
        pit = str(cfg.get("pit") or os.environ.get("GHL_API_KEY", ""))
        loc = str(cfg.get("locationId", ""))
        accounts = ghl_contracts.fetch_accounts(pit, loc)
        return accounts, None
    except Exception as exc:  # noqa: BLE001 — classified below
        err = getattr(exc, "error_class", "transient")
        return [], {"error_class": err, "retry_after": getattr(exc, "retry_after", None)}


def _per_account_publish_results(run_dir, cfg):
    """F06: derive the per-account publish results from the P0 per-account plan
    (working/preflight/preflight_report.json -> account_plan.accounts). Each
    account gets its OWN result row {account_id, platform, health,
    publish_state, note} — two Facebook accounts stay two rows (no
    platform-level collapse). needs_reconnect/failed accounts are EXPLICIT
    skipped/failed rows (never silent, never a run-wide block); healthy
    accounts proceed. Writes working/publish/account_results.json. Returns the
    list (empty when no plan was staged — back-compat with pre-F06 runs)."""
    report = _json(run_dir, "working/preflight/preflight_report.json", {}) or {}
    acct_plan = report.get("account_plan") or {}
    rows = acct_plan.get("accounts") if isinstance(acct_plan, dict) else None
    if not isinstance(rows, list) or not rows:
        return []
    staged = _json(run_dir, "working/publish/posted_ids.json")
    staged_ids = {str(x) for x in staged} if isinstance(staged, list) else set()
    out = []
    for r in rows:
        if not isinstance(r, dict) or not r.get("account_id"):
            continue
        health = str(r.get("health") or "ready")
        if health in ("needs_reconnect", "failed", "retrying"):
            state, note = ("failed" if health != "retrying" else "skipped"), \
                ("needs attention: %s (%s)" % (health, r.get("exclusion_reason") or "reconnect the channel"))
        else:
            state = "ready"
            note = "publish proceeds on this account" if health == "ready" \
                else str(r.get("exclusion_reason") or "skipped")
        out.append({"account_id": r["account_id"], "platform": r.get("platform", ""),
                    "account_name": r.get("account_name", ""), "health": health,
                    "publish_state": state, "note": note})
    try:
        p = run_dir / "working" / "publish" / "account_results.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    except OSError:
        pass
    return out


def _live_ghl_post_listing_with_status(cfg):
    """F10: the independent post readback WITH lifecycle status fields, via the
    F09 documented S2 contract. Returns the normalized post list
    [{post_id, status, scheduled_at, published_url}, ...] or None when
    unconfirmable (fail-closed upstream)."""
    import urllib.request  # noqa: F401 — kept for the historical import contract
    pit = str(cfg.get("pit") or os.environ.get("GHL_API_KEY", ""))
    loc = str(cfg.get("locationId", ""))
    if not pit or not loc:
        return None
    try:
        sys.path.insert(0, str(SCRIPTS))
        import ghl_contracts  # noqa: E402
        return ghl_contracts.fetch_posts(pit, loc)
    except Exception:  # noqa: BLE001 — unconfirmable stays fail-closed upstream
        return None


def _chk_publish(run_dir):
    if not (run_dir / "delivery" / "PROCESS-CERTIFICATE.json").is_file():
        return False, "publisher blocked: no process certificate (AF-SM-PUBLISH-UNPROVEN)"
    results = _json(run_dir, "working/publish/publish_results.json")
    if not isinstance(results, list) or not results:
        return False, "missing working/publish/publish_results.json"
    for i, r in enumerate(results, 1):
        rc = _run_script("validate_contract.py", ["--kind", "publish_result",
                         _dump_tmp(run_dir, "publish_%d" % i, r)])
        if rc != 0:
            return False, "publish result %d not the normalized contract" % i

    cfg = _json(run_dir, "working/copy/config.json", {}) or {}
    live = _live_mode(run_dir)

    # -- §4.4 NO-DOUBLE-POST (FIX-S36-61) -------------------------------------
    # P7 BUILDS the de-dup snapshot from the local SQLite ledger itself (this run's
    # recorded posts vs every other run's, within the lookback) + the live GHL
    # listing in --live mode, rather than only running IF a hand-authored
    # working/creative/dedup.json happens to exist (the old fail-open-by-construction
    # hole). A corrupt/unreadable ledger DB fails CLOSED ('cannot be built').
    try:
        sys.path.insert(0, str(SCRIPTS))
        import ledger  # noqa: E402
    except Exception as exc:  # noqa: BLE001
        return False, "de-dup BLOCK: cannot import the ledger to build the snapshot (%s)" % exc
    db = run_dir / "working" / "media" / "ledger.db"
    location_id = str(cfg.get("locationId", ""))
    ml = _json(run_dir, "working/media/media_ledger.json", {}) or {}
    run_id = str(ml.get("run") or run_dir.name)
    if db.is_file():
        try:
            live_listing = _json(run_dir, "working/publish/live_listing.json") if not live else None
            snap = ledger.build_dedup_snapshot(db, location_id, run_id, live_listing=live_listing)
        except Exception as exc:  # noqa: BLE001 — corrupt/unreadable ledger -> fail-closed
            return False, ("de-dup BLOCK (AF-SM-DOUBLE-POST): the ledger snapshot could not be built "
                           "(fail-closed): %s" % exc)
        blocks, cleared = ledger.check_dedup_snapshot(
            snap.get("existing"), snap.get("outgoing"),
            lookback_days=snap.get("lookback_days", ledger.DEFAULT_LOOKBACK_DAYS),
            live_listing=snap.get("live_listing"), repost_token=snap.get("repost_token"))
        if blocks and not cleared:
            return False, ("de-dup BLOCK (AF-SM-DOUBLE-POST): %d collision(s) built from the ledger. "
                           "Clear with `clean`/reschedule or a logged owner re-post token." % len(blocks))
    # A creative-interjection dedup snapshot (staged file) is ALSO honored (back-compat).
    dedup = run_dir / "working" / "creative" / "dedup.json"
    if dedup.is_file():
        rc = _run_script("ledger.py", ["dedup-snapshot", "--input", dedup])
        if rc != 0:
            return False, "de-dup BLOCK (AF-SM-DOUBLE-POST): a duplicate content-fingerprint or " \
                          "occupied slot was detected. Clear with `clean`/reschedule or a logged " \
                          "owner re-post token."

    # -- F06 PER-ACCOUNT RESULTS (recorded for the owner Q&A / partial delivery) --
    _per_account_publish_results(run_dir, cfg)

    # -- F08: SIMULATED EVIDENCE CAN NEVER SATISFY A LIVE COMPLETION ----------
    # A simulated (test/dry-run) run's receipts, offline exceptions and test
    # IDs are labeled simulated=true and can NEVER move a LIVE task to
    # published/completed: the live path below consumes ONLY production-mode
    # evidence, and a production run refuses simulated receipts outright.
    try:
        sim = _run_is_simulated(run_dir)
    except ConfigurationError as exc:
        return False, str(exc)
    for i, r in enumerate(results, 1):
        if isinstance(r, dict) and r.get("simulated") is True and not sim:
            return False, ("AF-SM-EXEC-MODE: publish result %d is a SIMULATED receipt — simulated "
                           "evidence can never satisfy a live completion" % i)

    # -- F10 PER-DESTINATION DELIVERY PROOF -----------------------------------
    # One delivery row per company/cycle/content-revision/account; the
    # provider state comes from an INDEPENDENT readback, never from the
    # poster's own receipts. draft/failed/unknown NEVER count as published.
    expected_keys = _expected_delivery_keys(run_dir)
    if not expected_keys:
        return False, ("AF-SM-PUBLISH-UNVERIFIED: no expected destinations derivable from "
                       "plan.json (per-account plan rows or platforms) — the delivery matrix "
                       "cannot be proven")

    # -- POST-PUBLISH LIVE VERIFY (FIX-S36-60 + F10) ---------------------------
    # `done` is claimed ONLY from an INDEPENDENT live GHL post-listing verify
    # WITH STATUS FIELDS, reconciled into per-destination delivery rows.
    posted_ids = _json(run_dir, "working/publish/posted_ids.json")
    posted_ids = [str(x) for x in posted_ids] if isinstance(posted_ids, list) else []
    if live:
        listing = _live_ghl_post_listing_with_status(cfg)
        if listing is None:
            return False, ("AF-SM-PUBLISH-UNVERIFIED: the live GHL post listing was unconfirmable "
                           "(fail-closed); cannot claim done without an independent verify")
        _reconcile_deliveries_from_listing(run_dir, listing)
        published = _delivery_published_set(run_dir)
        expected_accounts = {k[3] for k in expected_keys}
        not_published = sorted(expected_accounts - published)
        if not_published:
            states = {str(r.get("account_id")): r.get("provider_state")
                      for r in _delivery_rows(run_dir) if isinstance(r, dict)}
            return False, ("AF-SM-PUBLISH-UNVERIFIED: %d destination(s) not PUBLISHED on the "
                           "independent readback (%s) — draft/failed/scheduled/unknown never "
                           "count as published" % (len(not_published),
                                                   ", ".join("%s=%s" % (a, states.get(a, "?"))
                                                             for a in not_published[:8])))
        return True, ("publish results normalized (%d) + %d/%d destination(s) independently "
                      "PUBLISHED (delivery rows reconciled)" % (len(results), len(published),
                                                                len(expected_accounts)))
    # Simulated/dry-run posture: the receipt set is STAMPED simulated=true and
    # verified only against staged evidence; it can never claim published.
    evidence = _json(run_dir, "working/publish/published_listing.json")
    staged_states = _json(run_dir, "working/publish/staged_provider_states.json", {}) or {}
    for (company_id, cycle_id, revision, account_id) in expected_keys:
        state = str(staged_states.get(account_id, "unknown")).strip().lower()
        _upsert_delivery_row(run_dir, company_id, cycle_id, revision, account_id,
                             provider_state=state if state in DELIVERY_STATES else "unknown")
    try:
        (run_dir / "working" / "publish" / "publish_results_simulated.json").write_text(
            json.dumps([dict(r, simulated=True) if isinstance(r, dict) else r
                        for r in (results if isinstance(results, list) else [])], indent=2),
            encoding="utf-8")
    except OSError:
        pass
    if isinstance(evidence, list) and posted_ids:
        present = {str(x) for x in evidence}
        missing = [pid for pid in posted_ids if pid not in present]
        if missing:
            return False, ("AF-SM-PUBLISH-UNVERIFIED: %d posted id(s) absent from the staged listing "
                           "evidence (%s)" % (len(missing), ", ".join(missing[:5])))
        return True, ("publish results normalized (%d, SIMULATED=true) + staged evidence verified — "
                      "a simulated run NEVER claims published" % len(results))
    return True, ("publish results normalized (%d, SIMULATED=true); offline dry-run posture — live "
                  "GHL post-listing verify runs on the client box" % len(results))


def _chk_client_copy(run_dir):
    """M3 P2-INGEST: the client's finished copy is staged; the engine never authors."""
    d = run_dir / "working" / "creative" / "client-copy"
    files = list(d.glob("*.json")) if d.is_dir() else []
    if not files:
        return False, "no client-supplied copy at working/creative/client-copy/*.json (AF-SM-CONTENT-MISSING)"
    return True, "client copy staged (%d file(s)); verbatim proven at P6" % len(files)


def _chk_fold(run_dir, rel, kind, label):
    """Shared fold checker (C4 newsletter / C5 blog): artifact must exist and pass
    validate_contract.py + prove_bands.py for its kind (bands read from config/bands.json)."""
    f = run_dir / rel
    if not f.is_file():
        return False, "missing %s" % rel
    rc = _run_script("validate_contract.py", ["--kind", kind, f])
    if rc != 0:
        return False, "%s contract FAILED (validate_contract.py exit %d)" % (label, rc)
    rc = _run_script("prove_bands.py", ["--kind", kind, f])
    if rc != 0:
        return False, "%s bands FAILED (prove_bands.py exit %d)" % (label, rc)
    return True, "%s contract + bands PASS" % label


def _chk_newsletter(run_dir):
    return _chk_fold(run_dir, "working/content/newsletter.json", "newsletter", "newsletter")


def _chk_blog(run_dir):
    return _chk_fold(run_dir, "working/content/blog.json", "blog", "blog")


def _chk_podcast(run_dir):
    """C3 podcast fold. A labeled PODCAST_DEFERRED skip ({"deferred":true}) passes
    (Fish-Audio/Podbean unconfigured is never a failure); otherwise the ffprobe/cover
    numbers are proven against the SACRED podcast bands."""
    f = run_dir / "working" / "media" / "podcast.json"
    if not f.is_file():
        return False, "missing working/media/podcast.json"
    rec = _json(run_dir, "working/media/podcast.json", {})
    if isinstance(rec, dict) and rec.get("deferred") is True:
        return True, "PODCAST_DEFERRED (Fish-Audio/Podbean unconfigured — labeled skip, not a failure)"
    rc = _run_script("prove_bands.py", ["--kind", "podcast", f])
    if rc != 0:
        return False, "podcast bands FAILED (prove_bands.py exit %d)" % rc
    return True, "podcast script/duration/bitrate/cover bands PASS"


def _chk_engage(run_dir):
    """C6 engage fold — read-only. The anomaly report artifact must exist and carry a
    period + platform-level metrics. NEVER blocks a publish (own mode / week tail)."""
    rep = _json(run_dir, "working/qc/engage_report.json")
    if not isinstance(rep, dict):
        return False, "missing working/qc/engage_report.json (AF-SM-ENGAGE-REPORT)"
    if not rep.get("period") or not isinstance(rep.get("platforms"), (list, dict)):
        return False, "engage report missing period/platforms metrics (AF-SM-ENGAGE-REPORT)"
    return True, "read-only engagement/anomaly report present (%s)" % rep.get("period")


def _chk_deferred(run_dir):
    """DEFER stub (syndicate C9). Fail CLOSED with a clear 'deferred to vX.Y.Z' message
    rather than silently no-op — mirrors defer_stub.py."""
    rc = _run_script("defer_stub.py", ["--capability", "syndicate"])
    return False, "syndicate (non-GHL add-on channels) is DEFERRED to v0.4.0 (AF-SM-DEFERRED); " \
                  "off by default so no client is blocked meanwhile. defer_stub exit %d" % rc


# ===========================================================================
# F13 — REAL WRITEBACK PROOF
# ---------------------------------------------------------------------------
# The old _chk_writeback accepted a LOCAL list of 20 (often empty) cells and
# declared "row appended" with no Sheets involvement. A nominal success
# response without a real updatedRange also passed. Now the write receipt
# MUST carry the company-bound spreadsheet_id, schema_version, a stable
# row_key, the ACTUAL Sheets updatedRange and a content hash — anything less
# fails closed. Before completion the stable row is READ BACK by its row-key
# marker column and representative values are compared. A Sheets failure
# NEVER republishes already-published posts: delivery rows (F10) are
# independent of the planner sync, and an outage exposes a separate
# planner-sync task instead of failing the publish.
# ===========================================================================
WRITEBACK_ROW_KEY_COLUMN = 1        # the marker column that carries the row_key
PLANNER_SCHEMA_VERSION = "planner-2026.09-v1"


def _row_content_hash(row):
    import hashlib
    return hashlib.sha256(json.dumps(row, ensure_ascii=False).encode("utf-8")).hexdigest()


def _verify_writeback_receipt(run_dir):
    """F13 receipt proof. Returns (ok, msg). A LOCAL row array (even a
    well-formed 20-column one) is NOT a receipt: the required company-bound
    fields must ALL be present."""
    rec = _json(run_dir, "working/plan/row_appended.json")
    if not isinstance(rec, dict):
        return False, "missing working/plan/row_appended.json"
    row = rec.get("row") or rec.get("columns")
    if not isinstance(row, list) or len(row) != 20:
        return False, "planner row is not the normalized 20-column shape (got %s)" % (
            len(row) if isinstance(row, list) else "n/a")
    sheet_id = str(rec.get("spreadsheet_id") or "").strip()
    if not sheet_id:
        return False, ("AF-SM-WRITEBACK-PROOF: receipt carries no company-bound spreadsheet_id "
                       "(a local 20-cell array is not proof of a Sheets write)")
    if not str(rec.get("schema_version") or "").strip():
        return False, "AF-SM-WRITEBACK-PROOF: receipt carries no schema_version"
    if str(rec.get("schema_version")) != PLANNER_SCHEMA_VERSION:
        return False, ("AF-SM-WRITEBACK-PROOF: receipt schema_version %r != the planner schema %r"
                       % (rec.get("schema_version"), PLANNER_SCHEMA_VERSION))
    row_key = str(rec.get("row_key") or "").strip()
    if not row_key:
        return False, "AF-SM-WRITEBACK-PROOF: receipt carries no stable row_key"
    updated_range = str(rec.get("updatedRange") or rec.get("updated_range") or "").strip()
    if not updated_range:
        return False, ("AF-SM-WRITEBACK-PROOF: receipt carries no ACTUAL updatedRange — a nominal "
                       "'appended' response without a real range is NOT success")
    if "!" not in updated_range:
        return False, ("AF-SM-WRITEBACK-PROOF: updatedRange %r is not a real Sheets A1 range "
                       "(missing sheet!'A1' form)" % updated_range[:60])
    content_hash = str(rec.get("content_hash") or "").strip()
    if not content_hash:
        return False, "AF-SM-WRITEBACK-PROOF: receipt carries no content hash"
    if content_hash != _row_content_hash(row):
        return False, ("AF-SM-WRITEBACK-PROOF: receipt content hash does not match the staged row "
                       "(the receipt and the row disagree — fail-closed)")
    # The plan's company-bound sheet (sheet identity contract) must agree.
    plan = _json(run_dir, "working/plan/plan.json", {}) or {}
    plan_sheet = str(plan.get("plannerSheetId") or "").strip()
    if plan_sheet and sheet_id != plan_sheet:
        return False, ("AF-SM-WRITEBACK-PROOF: receipt spreadsheet_id %r is not the plan's "
                       "company-bound planner sheet %r" % (sheet_id[:8] + "...", plan_sheet[:8] + "..."))
    return True, "write receipt complete (spreadsheet bound, schema, row_key, updatedRange, hash)"


def _reconcile_writeback_readback(run_dir, readback):
    """F13 idempotent reconcile: a real append whose RESPONSE was lost is
    reconciled by reading back the stable row (by row-key marker) — one row,
    never a second append. `readback` is {found: bool, row_key, values: [...]}.
    Returns (ok, msg)."""
    rec = _json(run_dir, "working/plan/row_appended.json") or {}
    row = rec.get("row") or rec.get("columns") or []
    row_key = str(rec.get("row_key") or "").strip()
    if not isinstance(readback, dict) or readback.get("found") is not True:
        return False, ("AF-SM-WRITEBACK-PROOF: the stable row %r was not found by readback — "
                       "the write is NOT complete (reconcile before any retry creates a "
                       "second row)" % row_key)
    values = readback.get("values")
    if not isinstance(values, list):
        return False, "AF-SM-WRITEBACK-PROOF: readback carries no row values"
    marker = values[WRITEBACK_ROW_KEY_COLUMN - 1] if len(values) >= WRITEBACK_ROW_KEY_COLUMN else None
    if str(marker or "").strip() != row_key:
        return False, ("AF-SM-WRITEBACK-PROOF: readback row-key marker %r != the receipt's row_key %r"
                       % (marker, row_key))
    # Representative-value check: the first three non-marker cells read back
    # must equal the staged row's (the write did not land on a different row).
    staged_repr = [str(c) for c in row[1:4]]
    remote_repr = [str(c) for c in values[1:4]]
    if staged_repr != remote_repr:
        return False, ("AF-SM-WRITEBACK-PROOF: readback values differ from the staged row "
                       "(representative cells %r != %r)" % (remote_repr, staged_repr))
    rec["reconciled"] = True
    rec["reconciled_at"] = _utc_now_iso()
    try:
        (run_dir / "working" / "plan" / "row_appended.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8")
    except OSError:
        pass
    return True, "stable row %r read back with matching values (idempotent — no second append)" % row_key


def _sheets_outage_recovery(run_dir):
    """F13 + F10 coordination: a Sheets failure NEVER republishes
    already-published posts. The publish/delivery state is independent; the
    outage exposes a SEPARATE planner-sync task instead of failing the
    publish. Returns (published_preserved, planner_sync_task: dict|None)."""
    published = _delivery_published_set(run_dir)
    if not published:
        return True, None
    rec = _json(run_dir, "working/plan/planner_sync_task.json")
    if not isinstance(rec, dict) or not rec.get("task_id"):
        rec = {"task_id": "planner-sync-%s" % str(abs(hash(run_dir.name)))[:12],
               "kind": "planner-sync", "state": "open",
               "reason": "Sheets outage: planner row not written; published posts are "
                         "independent (delivery rows unchanged) — sync the row later",
               "created_at": _utc_now_iso()}
        try:
            (run_dir / "working" / "plan").mkdir(parents=True, exist_ok=True)
            (run_dir / "working" / "plan" / "planner_sync_task.json").write_text(
                json.dumps(rec, indent=2), encoding="utf-8")
        except OSError:
            pass
    return True, rec


def _chk_writeback(run_dir):
    ok, msg = _verify_writeback_receipt(run_dir)
    if not ok:
        return False, msg
    # The stable row must be READ BACK (working/plan/row_readback.json) before
    # writeback is complete: {found: true, row_key, values: [...]}. A receipt
    # already marked reconciled (a previous reconcile pass adopted the row)
    # completes idempotently — a retried run never appends a second row.
    rec = _json(run_dir, "working/plan/row_appended.json") or {}
    readback = _json(run_dir, "working/plan/row_readback.json")
    if isinstance(readback, dict) and readback.get("found") is True:
        ok2, msg2 = _reconcile_writeback_readback(run_dir, readback)
        if not ok2:
            return False, msg2
    elif rec.get("reconciled") is not True:
        return False, ("AF-SM-WRITEBACK-PROOF: the stable row was not found by readback — the "
                       "write is NOT complete (reconcile before any retry creates a second row)")
    return True, "writeback PROVEN: receipt complete + stable row read back (row_key %s)" % (
        rec.get("row_key"))


def _deliver_slug(text):
    import re
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def _deliver_week(run_dir):
    """Deterministic ISO week token (YYYY-Www) for the labeled-deliverable folder.
    Derived from plan.json weekOf (a date) when present, else the media-ledger run
    suffix, else 'unknown-week'. Never a wall-clock read (keeps the golden stable)."""
    import datetime
    plan = _json(run_dir, "working/plan/plan.json", {}) or {}
    wk = str(plan.get("weekOf", "")).strip()
    if wk:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                d = datetime.datetime.strptime(wk, fmt).date()
                iso = d.isocalendar()
                return "%04d-W%02d" % (iso[0], iso[1])
            except ValueError:
                pass
        return _deliver_slug(wk) or "unknown-week"
    ml = _json(run_dir, "working/media/media_ledger.json", {}) or {}
    run = str(ml.get("run", ""))
    if "_" in run:
        return run.rsplit("_", 1)[-1]
    return "unknown-week"


def _chk_deliver(run_dir):
    """FIX-XC-11h — the DELIVERY phase (P-DELIVER): assemble the labeled-deliverable
    manifest from this run's PASS artifacts and shell label_deliverables.py --copy
    FAIL-CLOSED (a declared artifact source that is missing on disk BLOCKS — nothing
    unlabeled or phantom ever 'delivers'). The deterministic LOGICAL dest root (the
    ~/Downloads convention, never a physical temp path) is recorded to
    delivery/deliverables-manifest.json so build_manifest binds it onto the
    certificate. Physical copy target is $SMIB_DELIVER_DEST (tests/CI) else the
    ~/Downloads convention. This is the ONLY call site of label_deliverables.py —
    it was pinned + self-tested + advertised with ZERO callers before this fix."""
    cfg = _json(run_dir, "working/copy/config.json", {}) or {}
    brand = str(cfg.get("brandName", "") or "brand")
    brand_slug = _deliver_slug(brand) or "brand"
    week = _deliver_week(run_dir)

    artifacts = []
    # (a) producer-declared deliverables win (authoritative; missing src => fail-closed).
    declared = _json(run_dir, "working/delivery/deliverables.json")
    if isinstance(declared, list):
        for a in declared:
            if isinstance(a, dict) and a.get("src"):
                artifacts.append(a)
    else:
        # (b) derive from LOCAL media files that actually exist on disk.
        media = run_dir / "working" / "media"
        exts = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov", ".pdf"}
        if media.is_dir():
            for f in sorted(media.rglob("*")):
                if f.is_file() and f.suffix.lower() in exts:
                    artifacts.append({"platform": "asset", "artifact": f.stem,
                                      "aspect": "1x1", "ext": f.suffix.lstrip("."), "src": str(f)})

    plan = _json(run_dir, "working/plan/plan.json", {}) or {}
    theme = str(plan.get("themeOfWeek", "")).strip()
    week_plan_md = "# %s — Week %s\n\n%s\n" % (brand, week, theme or "(weekly social plan)")

    label_manifest = {"brand": brand, "week": week, "artifacts": artifacts,
                      "week_plan_md": week_plan_md}
    lm_path = run_dir / "working" / "delivery" / "label-manifest.json"
    try:
        lm_path.parent.mkdir(parents=True, exist_ok=True)
        lm_path.write_text(json.dumps(label_manifest, indent=2), encoding="utf-8")
    except OSError as exc:
        return False, "AF-SM-DELIVER-MISSING: could not stage the label manifest: %s" % exc

    default_dest = "~/Downloads/Social-Media-in-a-Box"
    physical_dest = os.environ.get("SMIB_DELIVER_DEST", default_dest)
    rc = _run_script("label_deliverables.py",
                     ["--manifest", lm_path, "--dest", physical_dest, "--copy"])
    if rc != 0:
        return False, ("AF-SM-DELIVER-MISSING: label_deliverables.py refused (exit %d) — a declared "
                       "deliverable source is missing on disk (nothing phantom is labeled)" % rc)

    # Deterministic LOGICAL dest root recorded on the certificate (the ~/Downloads
    # convention; independent of any $SMIB_DELIVER_DEST test override).
    dest_root = "%s/%s/%s" % (default_dest, brand_slug, week)
    labels = []
    for a in artifacts:
        try:
            sys.path.insert(0, str(SCRIPTS))
            import label_deliverables as _ld  # noqa: E402
            labels.append(_ld.label_name(brand, week, a.get("day"), a.get("platform", ""),
                                         a.get("artifact", ""), a.get("aspect", "1x1"), a.get("ext", "png")))
        except Exception:  # noqa: BLE001
            pass
    rec = {"dest_root": dest_root, "brand_slug": brand_slug, "week": week,
           "count": len(artifacts), "labels": labels,
           "week_plan": "SMIB_%s_%s_week-plan.md" % (brand_slug, week)}
    try:
        (run_dir / "delivery").mkdir(parents=True, exist_ok=True)
        (run_dir / "delivery" / "deliverables-manifest.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8")
    except OSError as exc:
        return False, "AF-SM-DELIVER-MISSING: could not record the deliverables manifest: %s" % exc
    return True, ("labeled deliverables written (%d artifact(s) + week-plan) -> %s"
                  % (len(artifacts), dest_root))


def _dump_tmp(run_dir, name, obj):
    d = run_dir / "working" / "checkpoints" / "_tmp"
    d.mkdir(parents=True, exist_ok=True)
    p = d / ("%s.json" % name)
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


_CHECKERS = {
    "_chk_preflight": _chk_preflight, "_chk_plan": _chk_plan,
    "_chk_content_authored": _chk_content_authored, "_chk_contract_and_bands": _chk_contract_and_bands,
    "_chk_media_ledger": _chk_media_ledger, "_chk_scrub": _chk_scrub,
    "_chk_manifest": _chk_manifest, "_chk_publish": _chk_publish, "_chk_writeback": _chk_writeback,
    "_chk_client_copy": _chk_client_copy, "_chk_newsletter": _chk_newsletter,
    "_chk_blog": _chk_blog, "_chk_podcast": _chk_podcast, "_chk_engage": _chk_engage,
    "_chk_deferred": _chk_deferred, "_chk_deliver": _chk_deliver,
}


def _run_checker(name, run_dir):
    """FIX-XC-03k: resolve and run a phase checker. An UNMAPPED checker is a DISABLED
    gate — it fails CLOSED (was a silent soft-pass at the call site, so a manifest/
    checker-name drift could quietly no-op a required phase). Enforcement, not
    description: a required gate can never be a silent pass. Mirrors 55's
    run_product_bio._run_checker."""
    fn = _CHECKERS.get(name)
    if fn is None:
        return False, ("checker %s is not mapped — fail-closed (a required gate cannot be a "
                       "silent no-op)" % name)
    return fn(run_dir)

# v0.2.0 modes: engine-driven (v0.1.0) + fold (C3-C7) + creative (M1-M4) + syndicate defer (C9).
MODES = ["week", "day", "carousel", "video", "podcast-cover", "plan", "clean",
         "podcast", "newsletter", "blog", "engage",
         "brief", "campaign", "client-copy", "reactive", "syndicate"]

# DEFER map (fail-closed, clear 'deferred to vX.Y.Z' message; baseline config never blocked).
# F4.3: persona-adapter (C10) is now IMPLEMENTED (scripts/persona_adapter.py) and no
# longer deferred — personaSource:adapter/client-choice run the adapter, not a defer stub.
_DEFERRED = {
    "narrated-video": "0.3.0", "syndicate": "0.4.0",
    "memory-adapter": "0.5.0",
}


def _run_persona_adapter(run_dir: Path) -> bool:
    """F4.3 C10 persona INPUT adapter. Runs BEFORE the phases so downstream
    generation and the certificate can consume the resolved persona.
      personaSource:config        -> baseline no-op (nothing changes).
      personaSource:adapter       -> canonical 5-layer selection (LOGGED).
      personaSource:client-choice -> the client's named persona, FINAL/never judged.
    Returns True to BLOCK the run (an explicitly-requested adapter/client-choice
    that could not resolve — never a silent no-op); False to proceed."""
    try:
        sys.path.insert(0, str(SCRIPTS))
        import persona_adapter
        rc = persona_adapter.run(run_dir)
    except Exception as exc:  # noqa: BLE001 — adapter must not crash the run for baseline users
        cfg = _json(run_dir, "working/copy/config.json", {}) if run_dir else {}
        cfg = cfg if isinstance(cfg, dict) else {}
        if str(cfg.get("personaSource", "config")).strip().lower() in ("adapter", "client-choice"):
            print("BLOCKED: personaSource=%r requested but the persona adapter errored (%s). "
                  "Fix and re-run (fail-closed; baseline personaSource:config is never affected)."
                  % (cfg.get("personaSource"), exc), file=sys.stderr)
            return True
        print("[persona-adapter] best-effort skip (%s)" % exc, file=sys.stderr)
        return False
    if rc == persona_adapter.EXIT_UNRESOLVED:
        print("BLOCKED: an explicit persona source was requested but no persona could be "
              "resolved (see message above). Fail-closed; fix config and re-run.", file=sys.stderr)
        return True
    return False


def _defer_check(mode, args, run_dir):
    """Pre-run DEFER gate. A capability deferred to a named later version fails CLOSED
    with a clear message BEFORE any phase runs — never a silent no-op. Syndicate has its
    own manifest phase (P-SYNDICATE-DEFER); the --narrated flag and the persona/memory
    adapters are gated here. Baseline config-carried behavior (personaSource:config) is
    never affected."""
    hits = []
    cfg = _json(run_dir, "working/copy/config.json", {}) if run_dir else {}
    cfg = cfg if isinstance(cfg, dict) else {}
    if getattr(args, "narrated", False) or cfg.get("narratedVideo") is True:
        hits.append(("narrated-video", "C8 narrated Reels (55-60s multi-clip + Fish-Audio voiceover)"))
    # F4.3: persona-adapter (C10) is IMPLEMENTED — personaSource:adapter no longer
    # defers here; it is handled by _run_persona_adapter() before the phases.
    if cfg.get("memoryFeed") is True:
        hits.append(("memory-adapter", "C11 Skill-31 memory-core 'Dreaming' performance feed"))
    for cap, what in hits:
        ver = _DEFERRED.get(cap, "a later version")
        print("DEFERRED [AF-SM-DEFERRED]: %s is deferred to v%s. %s. This stub fails CLOSED "
              "rather than silently no-op; baseline config-carried behavior is never blocked."
              % (cap, ver, what), file=sys.stderr)
    return bool(hits)


def _write_gates(run_dir, gates):
    out = run_dir / "working" / "checkpoints" / "gates.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(gates, indent=2), encoding="utf-8")


def plan(manifest, mode):
    phases = manifest.get("modes", {}).get(mode)
    if not phases:
        print("FATAL: unknown mode %r" % mode, file=sys.stderr)
        return EXIT_USAGE
    print("== Social Media in a Box — mode '%s' phase plan ==" % mode)
    for i, pid in enumerate(phases, 1):
        ph = _phase(manifest, pid) or {}
        pf = (ph.get("preflight") or {}).get("checker", "-")
        print("  %d. %s — %s" % (i, pid, ph.get("name", "")))
        print("       produces: %s" % ph.get("produces_artifact", "-"))
        print("       gate    : %s | codes: %s" % (pf, ", ".join(ph.get("gate_codes", []))))
    return EXIT_PASS


def run(manifest, mode, run_dir: Path):
    phases = manifest.get("modes", {}).get(mode)
    if not phases:
        print("FATAL: unknown mode %r" % mode, file=sys.stderr)
        return EXIT_USAGE
    gates = {}
    for pid in phases:
        ph = _phase(manifest, pid)
        if not ph:
            print("FATAL: phase %s missing from manifest" % pid, file=sys.stderr)
            return EXIT_USAGE
        checker = (ph.get("preflight") or {}).get("checker")
        print("=== PHASE %s — %s ===" % (pid, ph.get("name", "")))
        ok, msg = _run_checker(checker, run_dir)
        print("   [%s] %s: %s" % ("OK" if ok else "FAIL", checker, msg))
        gates[pid] = {"passed": bool(ok)}
        # Persist gates BEFORE the manifest phase so build_manifest can read P0..P5.
        if pid != "P6-MANIFEST":
            _write_gates(run_dir, gates)
        if not ok:
            _write_gates(run_dir, gates)
            _LAST_BLOCK.clear()
            _LAST_BLOCK.update({"phase_id": pid, "note": msg})
            print("BLOCKED at %s (fail-closed). No phase skips; fix and re-run." % pid, file=sys.stderr)
            return EXIT_GATE
    _write_gates(run_dir, gates)
    print("ALL REQUESTED PHASES PASSED for mode '%s'." % mode)
    cert = run_dir / "delivery" / "PROCESS-CERTIFICATE.json"
    if cert.is_file():
        try:
            sha = json.loads(cert.read_text())["certificate_sha"]
            print("CERTIFICATE: %s (sha %s)" % (cert, sha[:12]))
        except (ValueError, KeyError):
            pass
    return EXIT_PASS


def self_test():
    """Built-in gate self-test (FIX-XC-03k / FIX-XC-11h). Proves: (1) an unmapped
    checker fails CLOSED (was a silent soft-pass); (2) EVERY checker named in
    SOCIAL-MANIFEST.json is mapped in _CHECKERS (a manifest/checker-name drift can
    no longer disable a gate); (3) the P-DELIVER checker labels real artifacts and
    fail-closes on a missing declared source. No nonce/run/provider needed."""
    import tempfile
    ok = True

    def _ck(label, cond):
        nonlocal ok
        cond = bool(cond)
        ok = ok and cond
        print("  [%s] %s" % ("PASS" if cond else "MISS", label))

    good, _ = _run_checker("_chk_does_not_exist", _SKILL_DIR)
    _ck("unmapped checker -> fail-closed (not soft-pass)", good is False)

    manifest = _load_manifest()
    declared = sorted({(ph.get("preflight") or {}).get("checker")
                       for ph in manifest.get("phases", [])
                       if (ph.get("preflight") or {}).get("checker")})
    unmapped = [c for c in declared if c not in _CHECKERS]
    _ck("every manifest checker is mapped (no gate drift): %s" % (unmapped or "all mapped"),
        not unmapped)

    # P-DELIVER golden: a local media file is labeled + copied; dest root recorded.
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td) / "run"
        (rd / "working" / "media").mkdir(parents=True)
        (rd / "working" / "copy").mkdir(parents=True)
        (rd / "working" / "plan").mkdir(parents=True)
        (rd / "working" / "copy" / "config.json").write_text(
            json.dumps({"brandName": "Brand One"}), encoding="utf-8")
        (rd / "working" / "plan" / "plan.json").write_text(
            json.dumps({"weekOf": "2026-07-06", "themeOfWeek": "t"}), encoding="utf-8")
        (rd / "working" / "media" / "slide.png").write_bytes(b"\x89PNG stub")
        old = os.environ.get("SMIB_DELIVER_DEST")
        os.environ["SMIB_DELIVER_DEST"] = str(Path(td) / "dl")
        try:
            good, _ = _chk_deliver(rd)
        finally:
            if old is None:
                os.environ.pop("SMIB_DELIVER_DEST", None)
            else:
                os.environ["SMIB_DELIVER_DEST"] = old
        rec = _json(rd, "delivery/deliverables-manifest.json", {})
        _ck("_chk_deliver golden -> PASS + records dest_root",
            good is True and isinstance(rec, dict) and str(rec.get("dest_root", "")).startswith("~/"))

    # P-DELIVER fail-closed: a declared deliverable whose source is missing BLOCKS.
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td) / "run"
        (rd / "working" / "copy").mkdir(parents=True)
        (rd / "working" / "delivery").mkdir(parents=True)
        (rd / "working" / "copy" / "config.json").write_text(
            json.dumps({"brandName": "Brand One"}), encoding="utf-8")
        (rd / "working" / "delivery" / "deliverables.json").write_text(
            json.dumps([{"platform": "tiktok", "artifact": "video", "aspect": "9:16",
                         "ext": "mp4", "src": str(Path(td) / "no-such-file.mp4")}]), encoding="utf-8")
        old = os.environ.get("SMIB_DELIVER_DEST")
        os.environ["SMIB_DELIVER_DEST"] = str(Path(td) / "dl")
        try:
            good, msg = _chk_deliver(rd)
        finally:
            if old is None:
                os.environ.pop("SMIB_DELIVER_DEST", None)
            else:
                os.environ["SMIB_DELIVER_DEST"] = old
        _ck("_chk_deliver missing declared source -> FAIL (AF-SM-DELIVER-MISSING)",
            good is False and "AF-SM-DELIVER-MISSING" in msg)

    print("== run_social_media self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return EXIT_PASS if ok else 1


# ---------------------------------------------------------------------------
# Command Center board card (FAIL-SOFT). Mirrors Skill-48 (ad_director) and the
# presentations build_deck._board_patch_phase pattern via the shared mc_board
# helper: land ONE mc-route card per run and advance it. A disabled board
# (no COMMAND_CENTER_URL) is a clean no-op; ANY failure is swallowed — the board
# is a VIEW, never a gate, and can never affect this orchestrator's exit code.
# ---------------------------------------------------------------------------
def _mc_board_begin(run_dir, mode):
    try:
        sys.path.insert(0, str(SCRIPTS))
        import mc_board
        return mc_board.begin_run(
            run_dir, slug=run_dir.name,
            title="Social Media in a Box (%s) — %s" % (mode, run_dir.name),
            department="social-media", persona="Social Media in a Box",
            source="social-media")
    except Exception as exc:  # noqa: BLE001 — board hookup must NEVER break the run.
        print("[mc_board] begin best-effort skip (%s)" % exc, file=sys.stderr)
        return None


def _mc_board_done(run_dir, task_id):
    try:
        sys.path.insert(0, str(SCRIPTS))
        import mc_board
        mc_board.complete_run(run_dir, task_id, note="certified + delivered")
    except Exception as exc:  # noqa: BLE001
        print("[mc_board] done best-effort skip (%s)" % exc, file=sys.stderr)


def _mc_board_blocked(run_dir, task_id):
    """FIX-XC-06: on a gate failure, move the card to `blocked` (never `done`) with
    the failing phase + AF code as the note, so a failed run is VISIBLE on the board
    instead of stranding forever at in_progress. FAIL-SOFT — never affects exit code."""
    try:
        sys.path.insert(0, str(SCRIPTS))
        import mc_board
        info = _LAST_BLOCK or {}
        mc_board.block_run(run_dir, task_id, phase_id=info.get("phase_id", ""),
                           note=info.get("note", "a fail-closed gate blocked the run"))
    except Exception as exc:  # noqa: BLE001
        print("[mc_board] blocked best-effort skip (%s)" % exc, file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deterministic Social Media in a Box orchestrator (Skill 57).")
    ap.add_argument("--mode", choices=MODES)
    ap.add_argument("--run-dir", help="the run directory (contains working/)")
    ap.add_argument("--plan", action="store_true", help="print the mode's phase plan and exit")
    ap.add_argument("--producers", action="store_true",
                    help="run the F05 producer adapter layer BEHIND the phase gates: each "
                         "phase's producer is invoked before its gate (missing artifacts "
                         "trigger production; unchanged inputs reuse verified outputs)")
    ap.add_argument("--narrated", action="store_true",
                    help="request the narrated video lane (C8) — DEFERRED to v0.3.0 (fails closed)")
    ap.add_argument("--self-test", dest="self_test", action="store_true",
                    help="run built-in gate self-tests (unmapped-checker + manifest-mapping + P-DELIVER) and exit")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.mode:
        ap.error("--mode is required (or use --self-test)")

    manifest = _load_manifest()
    if args.plan:
        return plan(manifest, args.mode)
    if not args.run_dir:
        ap.error("--run-dir is required (or use --plan)")
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        print("FATAL: --run-dir not found: %s" % run_dir, file=sys.stderr)
        return EXIT_USAGE
    if not _nonce_ok(run_dir):
        print("FATAL: front-door nonce missing/mismatch. Run THROUGH social-media-entry.sh "
              "(the ONE sanctioned entry); do not call this orchestrator directly.", file=sys.stderr)
        return EXIT_NONCE
    if _defer_check(args.mode, args, run_dir):
        return EXIT_GATE
    # F4.3 — C10 persona INPUT adapter (before phases; fail-closed only when an
    # explicit persona source was requested and could not resolve).
    if _run_persona_adapter(run_dir):
        return EXIT_GATE
    _mc_task = _mc_board_begin(run_dir, args.mode)
    # F05: with --producers the run loop invokes each phase's producer adapter
    # behind the unchanged gates; without it, the pure deterministic walk.
    if getattr(args, "producers", False):
        rc = run_with_producers(manifest, args.mode, run_dir)
    else:
        rc = run(manifest, args.mode, run_dir)
    if rc == EXIT_PASS:
        _mc_board_done(run_dir, _mc_task)
    else:
        # A gate failure after the card was opened: mark it blocked so it never
        # strands invisibly at in_progress (FIX-XC-06). FAIL-SOFT.
        _mc_board_blocked(run_dir, _mc_task)
    return rc


if __name__ == "__main__":
    sys.exit(main())
