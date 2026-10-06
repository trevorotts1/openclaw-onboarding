#!/usr/bin/env python3
"""Isolated, signed ingress for the Podcast System Sandbox canary.

This adapter deliberately accepts only the one designated test contact at the
configured sandbox location.  It unwraps the Convert and Flow survey envelope,
uses the normal deterministic intake handler, then records a local Step 2
research-handoff receipt.  It has no provider clients and never calls Fish,
Podbean, Convert and Flow, enrollment, notifications, or a model.

It is not a production endpoint.  The process must be started with all of the
PODCAST_SANDBOX_* variables below and a separate PODCAST_SANDBOX_CANARY_SECRET.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import intake_handler  # noqa: E402

STATE = ROOT / "podcast_state.py"
ROUTE_ID = "podcast-intake-sandbox-canary"
ROUTE_PATH = "/podcast-intake-sandbox-canary"
DEFAULT_BASE = Path.home() / ".openclaw" / "state" / "podcast-engine" / "sandbox-canary" / "intake-ledger"
DEFAULT_DB = Path.home() / ".openclaw" / "state" / "podcast-engine" / "sandbox-canary" / "state.db"


class CanaryError(RuntimeError):
    pass


def _required(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise CanaryError("missing required sandbox configuration: %s" % name)
    return value


def config() -> dict[str, str]:
    return {
        "expected_location_id": _required("PODCAST_SANDBOX_LOCATION_ID"),
        "test_contact_id": _required("PODCAST_SANDBOX_TEST_CONTACT_ID"),
        "secret": _required("PODCAST_SANDBOX_CANARY_SECRET"),
        "base": os.environ.get("PODCAST_SANDBOX_LEDGER_DIR", str(DEFAULT_BASE)),
        "db": os.environ.get("PODCAST_SANDBOX_DB_PATH", str(DEFAULT_DB)),
        "route_id": ROUTE_ID,
        "mode": "no-flow",
    }


def _safe(value: dict[str, Any]) -> dict[str, Any]:
    """Return response evidence without submission content, PII, or secrets."""
    keep = ("status", "job", "decision", "state", "test", "bridge", "job_id",
            "duplicate", "delivery_count", "receipt", "advance", "completion_refused")
    return {k: value[k] for k in keep if k in value}


def _run_state(cfg: dict[str, str], *args: str) -> dict[str, Any]:
    env = dict(os.environ)
    env["PODCAST_DB_PATH"] = cfg["db"]
    # Board mirroring is enabled only when the launch environment deliberately
    # supplies the local CC URL and its credentials.
    proc = subprocess.run(
        [sys.executable, str(STATE), "--json", *args], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=20,
        check=False,
    )
    data: dict[str, Any] = {}
    if proc.stdout.strip():
        try:
            data = json.loads(proc.stdout.strip().splitlines()[-1])
        except json.JSONDecodeError:
            pass
    if proc.returncode:
        raise CanaryError("sandbox state writer rejected the requested safe transition")
    return data


def _progress_safe_research_handoff(cfg: dict[str, str], job_id: str) -> dict[str, Any]:
    """Record one non-provider worker handoff and enter researching.

    This is intentionally the furthest automated canary progression.  There is
    no content generation, audio, publishing, link-back, enrollment, or
    notification action on this route.
    """
    evidence_dir = Path(cfg["base"]).parent / "receipts"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(evidence_dir, 0o700)
    except OSError:
        pass
    evidence = evidence_dir / (hashlib.sha256(job_id.encode("utf-8")).hexdigest() + ".step-2.json")
    evidence.write_text(json.dumps({
        "kind": "sandbox_canary_research_handoff",
        "external_effects": [],
        "provider_calls": 0,
    }, sort_keys=True), encoding="utf-8")
    try:
        os.chmod(evidence, 0o600)
    except OSError:
        pass
    action = "sandbox-canary-research-handoff"
    key = "sandbox-canary:%s:2" % job_id
    _run_state(cfg, "receipt", "begin", "--job-id", job_id, "--step", "2",
               "--action", action, "--idempotency-key", key)
    _run_state(cfg, "receipt", "complete", "--job-id", job_id, "--step", "2",
               "--action", action, "--idempotency-key", key, "--result-file", str(evidence))
    _run_state(cfg, "advance", "--job-id", job_id, "--to", "researching")

    # This explicit refusal probes the permanent test terminal rule.  The
    # request is expected to fail before any completion side effect is possible.
    env = dict(os.environ); env["PODCAST_DB_PATH"] = cfg["db"]
    refused = subprocess.run([sys.executable, str(STATE), "--json", "advance",
                              "--job-id", job_id, "--to", "complete"], text=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             env=env, timeout=20, check=False)
    if refused.returncode == 0:
        raise CanaryError("test job completion guard unexpectedly allowed completion")
    return {"receipt": "research_handoff_recorded", "advance": "researching",
            "completion_refused": True}


def accept(raw: bytes, signature: str | None) -> tuple[int, dict[str, Any]]:
    cfg = config()
    expected = "sha256=" + hmac.new(cfg["secret"].encode("utf-8"), raw, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        return 401, {"status": "unauthorized"}
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return 400, {"status": "invalid_json"}
    if not isinstance(body, dict):
        return 400, {"status": "invalid_body"}
    try:
        # intake_handler bridges through a subprocess which resolves this same
        # environment variable.  Set it before intake so the ledger and SQLite
        # roster are inseparable from the sandbox database.
        os.environ["PODCAST_DB_PATH"] = cfg["db"]
        verdict = intake_handler.handle(body, {
            "expected_location_id": cfg["expected_location_id"],
            "test_contact_id": cfg["test_contact_id"],
            "route_id": cfg["route_id"],
            "base": cfg["base"],
            "mode": "no-flow",
        })
    except Exception:
        return 500, {"status": "intake_error"}
    if verdict.get("status") == "duplicate":
        return 200, _safe({**verdict, "duplicate": True})
    if verdict.get("status") != "test" or not verdict.get("job_id"):
        return 409, _safe(verdict)
    try:
        progression = _progress_safe_research_handoff(cfg, str(verdict["job_id"]))
    except CanaryError:
        return 500, {"status": "safe_worker_error"}
    return 200, _safe({**verdict, **progression})


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path != ROUTE_PATH:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > 262144:
            self.send_error(413)
            return
        status, payload = accept(self.rfile.read(length), self.headers.get("X-Podcast-Intake-Signature"))
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, _fmt: str, *_args: object) -> None:
        return  # Avoid request paths/content becoming long-lived process logs.


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Signed Podcast System Sandbox canary ingress.")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=4021)
    args = parser.parse_args(argv)
    try:
        config()
    except CanaryError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    if not args.serve:
        print("configuration valid")
        return 0
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
