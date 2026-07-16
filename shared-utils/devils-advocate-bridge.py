#!/usr/bin/env python3
"""
devils-advocate-bridge.py — U55d (master-spec id U59) thin bridge.

Captures ONE Devil's Advocate generator invocation's JSON output
(``shared-utils/devils-advocate.py``) and POSTs it to the Command Center's
``POST /api/da-challenges`` (U55c, ``trevorotts1/blackceo-command-center``).
The generator itself stays untouched — this file is the ENTIRE bridge (base
spec Option A): "the pipeline/runbook step that invokes the generator captures
its JSON stdout and POSTs it to U55c." No automatic trigger-firing hooks are
implemented or asserted to exist here — this is manual/runbook invocation
wiring only, per spec scope-honesty (a follow-on unit, not this one, wires
automatic hooks from QC events).

NON-NEGOTIABLE DESIGN RULES (mirrors 06-ghl-install-pages/tools/cc_board.py,
the repo's own established producer-bridge convention — reused byte-for-byte
for auth so this bridge rides the SAME two auth layers every other Skill 6
producer already rides):

  * AUTH PARITY with the endpoint (per spec J.0.3 — "the machine bridge
    authenticates with the ONE chosen scheme (MC_API_TOKEN or the ingest HMAC
    pattern), whichever the bridge's runtime already holds"). This bridge
    sends BOTH headers whenever their env var is set (never fewer than the
    existing producer convention, so it degrades identically to every other
    Skill 6 bridge on a partially-configured box):
      - ``Authorization: Bearer <MC_API_TOKEN>``  — global middleware layer.
      - ``x-webhook-signature: HMAC-SHA256(WEBHOOK_SECRET, rawBody)`` hex —
        per-route layer, signs the EXACT bytes sent.

  * STDLIB ONLY (urllib) — zero third-party deps.

  * CREDENTIALS FROM ENV, never hardcoded; absent MISSION_CONTROL_URL => board
    disabled (clean no-op, distinct exit code 2 — see main()).
      MISSION_CONTROL_URL   base URL of the Command Center. Absent => disabled.
      MC_API_TOKEN          long-lived bearer (middleware layer). Optional.
      WEBHOOK_SECRET        HMAC secret (per-route layer). Optional.
                             (CC_WEBHOOK_SECRET accepted as an alias, same as
                             cc_board.py.)
      DA_BRIDGE_TIMEOUT     per-request timeout seconds (default 8).

  * NEVER raises out of post_challenge() — every failure (generator error,
    board unconfigured, network error, non-2xx response) comes back as a
    result dict with ``ok``/``error`` set. The CLI (main()) is what turns
    that into an exit code; library callers get a value, never an exception.

WIRE-PAYLOAD CONTRACT (POST /api/da-challenges body — the CC-side U55c route
must accept exactly this field set; a shape change here is a paired commit on
both repos):
    {
      "trigger_type":      one of the generator's five choices (echoed, not
                            re-validated here — the generator's own argparse
                            already constrains it before this function runs),
      "department":        raw identifier straight from the context JSON's
                            "department" field (whatever slug/name/id the
                            caller already had); the CC route resolves it via
                            resolveDepartment() per spec J.3.2 U55c,
      "challenge":          str, generator's parsed challenge question,
      "specific_concern":   str,
      "assumptions":        str (the "What Would Have to Be True" bullets),
      "severity":           "low" | "medium" | "high",
      "confidence":         float 0.0-1.0,
      "raw_response":       str, the full unparsed model/template response,
      "task_id":            OPTIONAL, only present when the context JSON
                             carried one.
    }

SELF-TEST (no board required, no network):
    python3 shared-utils/devils-advocate-bridge.py --selftest
    exits 0 on success, non-zero on failure.

USAGE (manual/runbook invocation):
    python3 shared-utils/devils-advocate-bridge.py \\
        --trigger critical_task --context-json /tmp/da-context.json

    # Preview the exact wire payload without POSTing anything:
    python3 shared-utils/devils-advocate-bridge.py \\
        --trigger critical_task --context-json /tmp/da-context.json --dry-run

Exit codes: 0 = posted 2xx (or --dry-run succeeded); 2 = board not configured
(MISSION_CONTROL_URL absent — a clean, non-fatal no-op, same convention as
every other Skill 6 producer bridge); 1 = a real failure (generator error,
network error, non-2xx response).
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

_DEFAULT_TIMEOUT = 8
_HERE = Path(__file__).resolve().parent
_GENERATOR_PATH = _HERE / "devils-advocate.py"
_DA_CHALLENGES_PATH = "/api/da-challenges"

# The five trigger types the generator itself accepts (mirrored here ONLY for
# --selftest fixtures and CLI help text — the generator's own argparse is the
# single source of truth and enforcement point; this bridge never re-validates
# a trigger the generator would already reject).
KNOWN_TRIGGERS = (
    "critical_task",
    "strategic_decision",
    "consecutive_approval",
    "kpi_swing",
    "sensitive_dept",
)


def _log(msg: str) -> None:
    """Single, greppable line. Bridge failures are logged, not silent."""
    print(f"[devils-advocate-bridge] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Generator loader — the hyphenated filename (matches the repo's own
# `devils-advocate.py`) is not import-able as a normal module, so load it by
# file path exactly like tests/unit/*.test.py already do for sibling
# hyphenated shared-utils scripts.
# ---------------------------------------------------------------------------
def _load_generator():
    if not _GENERATOR_PATH.is_file():
        raise FileNotFoundError(f"generator not found at {_GENERATOR_PATH}")
    spec = importlib.util.spec_from_file_location("devils_advocate_generator", _GENERATOR_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["devils_advocate_generator"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# Config + auth — byte-for-byte convention parity with cc_board.py.
# ---------------------------------------------------------------------------
def bridge_config(env: Optional[dict] = None) -> Optional[dict]:
    """Resolve bridge config from the environment. Returns None (board
    disabled, a clean no-op) when MISSION_CONTROL_URL is not set. Never
    raises."""
    env = env if env is not None else os.environ
    base = (env.get("MISSION_CONTROL_URL") or "").strip().rstrip("/")
    if not base:
        return None
    try:
        timeout = int(env.get("DA_BRIDGE_TIMEOUT", "") or _DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        timeout = _DEFAULT_TIMEOUT
    return {
        "base_url": base,
        "token": (env.get("MC_API_TOKEN") or "").strip(),
        "secret": (env.get("WEBHOOK_SECRET") or env.get("CC_WEBHOOK_SECRET") or "").strip(),
        "timeout": timeout,
    }


def _sign(secret: str, raw_body: bytes) -> Optional[str]:
    """x-webhook-signature = HMAC-SHA256(WEBHOOK_SECRET, rawBody) hex — byte-
    for-byte parity with cc_board.py's ``_sign`` (which itself matches
    ``verifyWebhookSignature()`` in the Command Center's route handlers).
    Returns None when no secret (the endpoint also no-ops in that case)."""
    if not secret:
        return None
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def _post_json(url: str, payload: dict, cfg: dict, method: str = "POST"):
    """One signed JSON request. Returns (status_code, parsed_json_or_None).
    Raises only urllib/OS errors — callers (post_challenge) catch them."""
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if cfg["token"]:
        headers["Authorization"] = f"Bearer {cfg['token']}"
    sig = _sign(cfg["secret"], raw_body)
    if sig is not None:
        headers["x-webhook-signature"] = sig
    req = urllib.request.Request(url, data=raw_body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
            body = resp.read().decode("utf-8", "replace")
            status = resp.getcode()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace") if exc.fp else ""
        status = exc.code
    try:
        parsed = json.loads(body) if body else None
    except json.JSONDecodeError:
        parsed = None
    return status, parsed


def _ts() -> str:
    """UTC timestamp, matches cc_board.py's ``_ts()`` byte-for-byte."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# Payload construction — pure function, the entire "thin" contract.
# ---------------------------------------------------------------------------
def build_payload(trigger_type: str, context: dict, generated: dict) -> dict:
    """Combine the generator's parsed output with the context's department/
    task identifiers into the exact wire shape POST /api/da-challenges reads
    (see the module docstring's WIRE-PAYLOAD CONTRACT). Pure — no I/O."""
    payload = {
        "trigger_type": trigger_type,
        "department": context.get("department") or "",
        "challenge": generated.get("challenge", ""),
        "specific_concern": generated.get("specific_concern", ""),
        "assumptions": generated.get("assumptions", ""),
        "severity": generated.get("severity", "medium"),
        "confidence": generated.get("confidence", 0.5),
        "raw_response": generated.get("raw_response", ""),
    }
    task_id = context.get("task_id")
    if task_id:
        payload["task_id"] = task_id
    return payload


def _write_receipt(evidence_root: Optional[str], trigger_type: str, result: dict) -> None:
    """Best-effort / fail-soft receipt, same doctrine as cc_board.py's U27
    board-ingest-receipt: ``evidence_root=None`` is a clean no-op; any OSError
    writing it is swallowed. NEVER raises; NEVER changes post_challenge()'s
    return value."""
    if not evidence_root:
        return
    try:
        receipt_dir = os.path.join(evidence_root, "routing")
        os.makedirs(receipt_dir, exist_ok=True)
        record = {
            "attempted_at": _ts(),
            "trigger_type": trigger_type,
            "board_configured": result.get("board_configured"),
            "ok": result.get("ok"),
            "status_code": result.get("status_code"),
            "error": result.get("error"),
        }
        path = os.path.join(receipt_dir, "da-challenge-bridge-receipt.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Public API — the whole bridge in one call. Never raises.
# ---------------------------------------------------------------------------
def post_challenge(
    trigger_type: str,
    context: dict,
    *,
    env: Optional[dict] = None,
    evidence_root: Optional[str] = None,
) -> dict:
    """Generate ONE Devil's Advocate challenge and POST it to the Command
    Center. Never raises — every failure mode comes back in the result dict.

    Returns:
        {
          "ok": bool,                  # True only on a 2xx response
          "board_configured": bool,    # False => MISSION_CONTROL_URL unset
          "status_code": int | None,
          "response": dict | None,     # parsed JSON body, if any
          "error": str | None,
          "challenge": dict | None,    # the generator's raw parsed output
          "payload": dict | None,      # the exact bytes-equivalent payload sent
        }
    """
    result: dict = {
        "ok": False,
        "board_configured": False,
        "status_code": None,
        "response": None,
        "error": None,
        "challenge": None,
        "payload": None,
    }

    try:
        generator = _load_generator()
    except Exception as exc:  # noqa: BLE001 — fail-soft boundary, by design
        result["error"] = f"generator load failed: {exc}"
        _write_receipt(evidence_root, trigger_type, result)
        return result

    try:
        generated = generator.generate_challenge(trigger_type, context)
    except Exception as exc:  # noqa: BLE001 — fail-soft boundary, by design
        result["error"] = f"generator call failed: {exc}"
        _write_receipt(evidence_root, trigger_type, result)
        return result

    result["challenge"] = generated
    payload = build_payload(trigger_type, context, generated)
    result["payload"] = payload

    cfg = bridge_config(env)
    if cfg is None:
        result["error"] = "MISSION_CONTROL_URL not set -- board disabled (clean no-op)"
        _write_receipt(evidence_root, trigger_type, result)
        return result
    result["board_configured"] = True

    url = f"{cfg['base_url']}{_DA_CHALLENGES_PATH}"
    try:
        status, parsed = _post_json(url, payload, cfg)
    except (urllib.error.URLError, OSError) as exc:
        result["error"] = f"POST failed: {exc}"
        _write_receipt(evidence_root, trigger_type, result)
        return result

    result["status_code"] = status
    result["response"] = parsed
    result["ok"] = 200 <= status < 300
    if not result["ok"]:
        result["error"] = f"non-2xx response: {status}"
    _write_receipt(evidence_root, trigger_type, result)
    return result


# ---------------------------------------------------------------------------
# CLI — selftest + real/dry-run invocation.
# ---------------------------------------------------------------------------
def _selftest() -> int:
    """Unit-level self-test — no network required. Returns 0 on pass."""
    errors: list = []

    # 1. bridge_config with no URL -> None (board disabled).
    cfg = bridge_config({})
    if cfg is not None:
        errors.append("bridge_config({}) should return None when MISSION_CONTROL_URL absent")

    # 2. bridge_config with URL -> dict with expected keys.
    cfg = bridge_config({"MISSION_CONTROL_URL": "https://example.zerohumanworkforce.com/"})
    if cfg is None:
        errors.append("bridge_config should return dict when MISSION_CONTROL_URL is set")
    else:
        for k in ("base_url", "token", "secret", "timeout"):
            if k not in cfg:
                errors.append(f"bridge_config missing key: {k}")
        if cfg.get("base_url") != "https://example.zerohumanworkforce.com":
            errors.append(f"base_url should be rstripped of trailing slash, got {cfg.get('base_url')!r}")

    # 3. _sign with no secret -> None.
    if _sign("", b"hello") is not None:
        errors.append("_sign with empty secret should return None")

    # 4. _sign with secret -> hex string of correct length (SHA-256 = 64 hex chars).
    sig = _sign("mysecret", b"hello")
    if sig is None or len(sig) != 64:
        errors.append(f"_sign with secret should return 64-char hex, got {sig!r}")
    expected = hmac.new(b"mysecret", b"hello", hashlib.sha256).hexdigest()
    if sig != expected:
        errors.append("_sign output does not match hmac.new(...).hexdigest() directly")

    # 5. build_payload — full shape, including optional task_id.
    generated = {
        "challenge": "Q?", "specific_concern": "C", "assumptions": "A",
        "severity": "high", "confidence": 0.9, "raw_response": "raw",
    }
    payload = build_payload("critical_task", {"department": "marketing", "task_id": "t-1"}, generated)
    expected_payload = {
        "trigger_type": "critical_task", "department": "marketing", "challenge": "Q?",
        "specific_concern": "C", "assumptions": "A", "severity": "high",
        "confidence": 0.9, "raw_response": "raw", "task_id": "t-1",
    }
    if payload != expected_payload:
        errors.append(f"build_payload shape mismatch: {payload!r} != {expected_payload!r}")

    # 6. build_payload — task_id omitted when absent from context.
    payload_no_task = build_payload("sensitive_dept", {"department": "legal"}, generated)
    if "task_id" in payload_no_task:
        errors.append("build_payload should omit task_id when the context carries none")

    # 7. build_payload — missing department degrades to empty string, never KeyError.
    payload_no_dept = build_payload("kpi_swing", {}, generated)
    if payload_no_dept.get("department") != "":
        errors.append(f"build_payload department should default to '', got {payload_no_dept.get('department')!r}")

    # 8. post_challenge with no board configured -> clean no-op, never raises.
    try:
        result = post_challenge("critical_task", {"title": "x", "department": "marketing"}, env={})
        if result["board_configured"] is not False:
            errors.append("post_challenge board_configured should be False when MISSION_CONTROL_URL absent")
        if result["ok"] is not False:
            errors.append("post_challenge ok should be False when board is not configured")
        if not result["error"]:
            errors.append("post_challenge should set an error string when board is not configured")
        if result["challenge"] is None:
            errors.append("post_challenge should still run the generator even when the board is unconfigured")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"post_challenge raised unexpectedly with no board configured: {exc}")

    # 9. post_challenge with an unresolvable board host -> caught, never raises.
    try:
        result = post_challenge(
            "critical_task",
            {"title": "x", "department": "marketing"},
            env={"MISSION_CONTROL_URL": "http://127.0.0.1.invalid.:1", "DA_BRIDGE_TIMEOUT": "2"},
        )
        if result["ok"] is not False:
            errors.append("post_challenge ok should be False on an unreachable host")
        if not result["error"]:
            errors.append("post_challenge should set an error string on a network failure")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"post_challenge raised unexpectedly on an unreachable host: {exc}")

    if errors:
        for e in errors:
            print(f"[selftest] FAIL — {e}", file=sys.stderr)
        print(f"[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — all checks passed (no network required)")
    return 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--trigger", choices=KNOWN_TRIGGERS)
    parser.add_argument("--context-json")
    parser.add_argument("--dry-run", action="store_true", help="Build the payload; never POST it.")
    parser.add_argument("--evidence-root", default=None, help="Write a bridge receipt under <root>/routing/.")
    parser.add_argument("--selftest", action="store_true", help="Offline self-test, no network, no board required.")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    if not args.trigger or not args.context_json:
        parser.error("--trigger and --context-json are required unless --selftest")

    with open(args.context_json, encoding="utf-8") as f:
        context = json.load(f)

    if args.dry_run:
        try:
            generator = _load_generator()
            generated = generator.generate_challenge(args.trigger, context)
        except Exception as exc:  # noqa: BLE001
            _log(f"generator failed: {exc}")
            return 1
        payload = build_payload(args.trigger, context, generated)
        print(json.dumps(payload, indent=2))
        return 0

    result = post_challenge(args.trigger, context, evidence_root=args.evidence_root)
    printable = {k: v for k, v in result.items() if k != "challenge"}
    print(json.dumps(printable, indent=2))

    if not result["board_configured"]:
        _log(result["error"] or "board not configured")
        return 2
    if not result["ok"]:
        _log(result["error"] or "post failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
