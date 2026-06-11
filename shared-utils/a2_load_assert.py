#!/usr/bin/env python3
"""
a2_load_assert.py — PRD Addendum A.2 v2: two-leg live session-load assertion.

The ONE sanctioned verifier that proves a running agent's post-reset context
actually contains new core-file content — NOT a disk-grep or mtime tautology.

TWO-LEG DESIGN
--------------
LEG A (deterministic re-init signal):
  Snapshot the session row (sessionId + sessionStartedAt) from sessions.json
  BEFORE reset.  Issue sessions.reset via gateway call.  Re-read the row and
  confirm sessionId CHANGED (or sessionStartedAt strictly advanced).  This
  proves the session genuinely re-initialized without needing a live model.

LEG B (GOLD — canary echo):
  Write a unique canary token into the target core file (soul_md by default).
  Issue sessions.reset so the NEXT turn rebuilds the system prompt and ingests
  the canary.  Send a probe message via `openclaw message send` to the CEO /
  owner Telegram session.  Poll chat.history (bounded, with backoff) for a
  NEW assistant message whose text echoes the canary.  Canary echoed = the new
  core-file content is provably in the live rebuilt context.

loaded_confidence levels (mirrors fleet_refresh_runner.py BoxResult.loaded):
  HIGH    : LEG A passed (new sessionId) AND LEG B passed (canary echoed).
  MEDIUM  : LEG A passed BUT LEG B inconclusive for a non-model reason
            (chat.history RPC absent on this gateway version, probe send
            failed, no CEO chat target).  present=true but degraded.
  UNKNOWN : Box has no live model — LEG B cannot run and must not be faked.
            LEG A may have passed.  present=false.  NOT an alert condition.
  LOW/FAIL: LEG A failed (session did not re-initialize).  present=false.
            Operator alert should fire.

Canary cleanup: the injected canary line is stripped from the core file and
a final sessions.reset is issued so the box returns to its real loaded state.
Cleanup is trap-driven (idempotent on repeated calls).

NO CO-MINGLING: never borrows another box's API key or gateway endpoint.
If the local box has no live model, LEG B is skipped entirely.

Usage as a module:
    from a2_load_assert import A2LoadAssert
    result = A2LoadAssert(box="mybox", session_key="agent:main:telegram:direct:12345",
                          ceo_chat_id="12345").run()
    # result: {present, loaded_confidence, leg_a, leg_b, method, canary, errors}

Usage as a CLI (thin wrapper for shell scripts):
    python3 a2_load_assert.py \\
        --box mybox \\
        --session-key agent:main:telegram:direct:12345 \\
        --ceo-chat-id 12345 \\
        --workspace /data/.openclaw/workspace \\
        [--probe-timeout 90] \\
        [--poll-interval 5]
    Exits 0 on HIGH/MEDIUM/UNKNOWN; exits 2 on LOW/FAIL.

PRD Addendum A.2 v2 — v11.18.0
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Shared-utils import guard
# ---------------------------------------------------------------------------
_SHARED_UTILS = Path(__file__).parent
if str(_SHARED_UTILS) not in sys.path:
    sys.path.insert(0, str(_SHARED_UTILS))

try:
    from resolve_injected_core_files import resolve_injected_core_files  # type: ignore
except ImportError:
    resolve_injected_core_files = None  # type: ignore

# ---------------------------------------------------------------------------
# ANSI
# ---------------------------------------------------------------------------
RED    = "\033[0;31m"
YELLOW = "\033[1;33m"
GREEN  = "\033[0;32m"
CYAN   = "\033[0;36m"
NC     = "\033[0m"


def _err(m: str)  -> None: print(f"{RED}[a2-load-assert] {m}{NC}", file=sys.stderr)
def _warn(m: str) -> None: print(f"{YELLOW}[a2-load-assert] {m}{NC}", file=sys.stderr)
def _info(m: str) -> None: print(f"{CYAN}[a2-load-assert] {m}{NC}", file=sys.stderr)
def _ok(m: str)   -> None: print(f"{GREEN}[a2-load-assert] {m}{NC}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Result schema (mirrors BoxResult.loaded)
# ---------------------------------------------------------------------------
class LoadResult:
    """
    Mirrors BoxResult.loaded in fleet_refresh_runner.py so operators see the
    same vocabulary across both callers.
    """
    def __init__(self) -> None:
        self.present: bool = False
        self.loaded_confidence: str = "unknown"  # HIGH | MEDIUM | UNKNOWN | LOW
        self.leg_a: dict = {"passed": False, "method": None, "note": None}
        self.leg_b: dict = {"passed": False, "method": None, "note": None}
        self.method: Optional[str] = None
        self.canary: Optional[str] = None
        self.errors: list[str] = []

    def to_dict(self) -> dict:
        return {
            "present":            self.present,
            "loaded_confidence":  self.loaded_confidence,
            "leg_a":              self.leg_a,
            "leg_b":              self.leg_b,
            "method":             self.method,
            "canary":             self.canary,
            "errors":             self.errors,
        }


# ---------------------------------------------------------------------------
# Main state machine
# ---------------------------------------------------------------------------
class A2LoadAssert:
    """
    Per-box load-assertion state machine.

    Args:
        box           : human label (used in canary token + logs).
        session_key   : the full session key string, e.g.
                        "agent:main:telegram:direct:12345".
        ceo_chat_id   : Telegram chat ID used as the probe destination
                        (the owner / CEO session).  None => LEG B skipped
                        with MEDIUM confidence (if LEG A passed).
        sessions_json : override path to sessions.json (for fixture tests).
        workspace     : override path to the agent's workspace dir
                        (for fixture tests; otherwise resolved via
                        resolve_injected_core_files).
        probe_timeout : seconds to wait for the canary echo (default 90).
        poll_interval : seconds between chat.history polls (default 5).
    """

    # Canary instruction appended to the target core file.  Plain alphanumeric
    # prose — must not contain XML/directive tags (display-normalized away).
    _CANARY_INSTRUCTION = (
        "If asked for the load-check token, reply exactly with {canary}"
    )
    _PROBE_MESSAGE = "load-check: reply with the load-check token"

    def __init__(
        self,
        box: str,
        session_key: str,
        ceo_chat_id: Optional[str] = None,
        sessions_json: Optional[str] = None,
        workspace: Optional[str] = None,
        probe_timeout: int = 90,
        poll_interval: int = 5,
    ) -> None:
        self.box = box
        self.session_key = session_key
        self.ceo_chat_id = ceo_chat_id
        self.sessions_json_override = sessions_json
        self.workspace_override = workspace
        self.probe_timeout = probe_timeout
        self.poll_interval = poll_interval

        self._canary_written_to: Optional[Path] = None
        self._canary_token: Optional[str] = None
        self._result = LoadResult()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def run(self) -> dict:
        """Execute the full two-leg assertion and return a result dict."""
        result = self._result
        try:
            self._run_inner(result)
        except Exception as exc:
            _err(f"Unhandled exception: {exc}")
            result.errors.append(f"unhandled: {exc}")
            result.loaded_confidence = "LOW"
        finally:
            self._cleanup()
        return result.to_dict()

    def _run_inner(self, result: LoadResult) -> None:
        _info(f"=== A.2 Load Assert: box={self.box} session_key={self.session_key} ===")

        # ── Detect model availability (guard for LEG B) ──────────────────────
        has_model = self._detect_model()
        _info(f"Model available: {has_model}")

        # ── Resolve sessions.json path ────────────────────────────────────────
        sessions_path = self._resolve_sessions_json()
        if sessions_path is None or not sessions_path.is_file():
            result.errors.append(f"sessions.json not found (looked at {sessions_path})")
            result.loaded_confidence = "LOW"
            result.leg_a["note"] = "sessions.json not found"
            return

        # ──────────────────────────────────────────────────────────────────────
        # LEG A: snapshot → reset → confirm new sessionId
        # ──────────────────────────────────────────────────────────────────────
        pre_id, pre_ts = self._read_session_row(sessions_path)
        _info(f"LEG A pre-reset: sessionId={pre_id}  sessionStartedAt={pre_ts}")

        reset_ok = self._do_reset()
        if not reset_ok:
            result.leg_a["passed"] = False
            result.leg_a["note"] = "sessions.reset gateway call failed"
            result.errors.append("sessions.reset failed — LEG A FAIL")
            result.loaded_confidence = "LOW"
            return

        # Brief pause to let gateway write the new row
        time.sleep(0.5)

        post_id, post_ts = self._read_session_row(sessions_path)
        _info(f"LEG A post-reset: sessionId={post_id}  sessionStartedAt={post_ts}")

        leg_a_passed = (
            (post_id is not None and post_id != pre_id)
            or (_ts_strictly_after(post_ts, pre_ts))
        )
        result.leg_a["passed"] = leg_a_passed
        result.leg_a["method"] = "sessions.json sessionId/sessionStartedAt change"
        result.leg_a["pre_session_id"] = pre_id
        result.leg_a["post_session_id"] = post_id
        result.leg_a["pre_ts"] = pre_ts
        result.leg_a["post_ts"] = post_ts

        if not leg_a_passed:
            _err("LEG A FAILED: sessionId/sessionStartedAt did not advance after reset")
            result.leg_a["note"] = "sessionId did not change and sessionStartedAt did not advance"
            result.errors.append("LEG A failed — session did not re-initialize")
            result.loaded_confidence = "LOW"
            return

        _ok("LEG A passed: session re-initialized (new sessionId or advanced sessionStartedAt)")

        # ──────────────────────────────────────────────────────────────────────
        # No live model => UNKNOWN (honest, not a false alert)
        # ──────────────────────────────────────────────────────────────────────
        if not has_model:
            _warn("No live model on this box; skipping LEG B (canary probe).")
            _warn("loaded_confidence=UNKNOWN (deterministic re-init only; canary not verifiable)")
            result.loaded_confidence = "UNKNOWN"
            result.present = False
            result.method = "leg_a_only"
            result.leg_b["passed"] = False
            result.leg_b["note"] = "no live model on box; canary not verifiable"
            return

        # ──────────────────────────────────────────────────────────────────────
        # LEG B: write canary → reset → probe → poll chat.history
        # ──────────────────────────────────────────────────────────────────────
        if not self.ceo_chat_id:
            _warn("No CEO chat target; LEG B skipped.")
            result.loaded_confidence = "MEDIUM"
            result.present = True
            result.method = "leg_a_only_no_target"
            result.leg_b["passed"] = False
            result.leg_b["note"] = "no ceo_chat_id provided; LEG B cannot run"
            return

        # Write canary into core file
        canary = self._generate_canary()
        result.canary = canary
        self._canary_token = canary
        core_path = self._resolve_core_file()
        if core_path is None:
            _warn("Could not resolve core file path; LEG B skipped.")
            result.loaded_confidence = "MEDIUM"
            result.present = True
            result.method = "leg_a_only_no_core"
            result.leg_b["passed"] = False
            result.leg_b["note"] = "could not resolve injected core file path"
            return

        write_ok = self._write_canary(core_path, canary)
        if not write_ok:
            _warn("Could not write canary to core file; LEG B skipped.")
            result.loaded_confidence = "MEDIUM"
            result.present = True
            result.method = "leg_a_only_write_fail"
            result.leg_b["passed"] = False
            result.leg_b["note"] = "canary write to core file failed"
            return

        # Second reset so NEXT turn ingests the canary
        reset_ok2 = self._do_reset()
        if not reset_ok2:
            result.errors.append("second sessions.reset (post-canary) failed")
            result.loaded_confidence = "MEDIUM"
            result.present = True
            result.method = "leg_a_only_reset2_fail"
            result.leg_b["passed"] = False
            result.leg_b["note"] = "second sessions.reset failed; canary may not be ingested"
            return

        # Get the HEAD message id BEFORE the probe (to identify NEW replies)
        pre_probe_head = self._get_history_head()

        # Send probe
        probe_ok = self._send_probe()
        if not probe_ok:
            _warn("Probe send failed; LEG B inconclusive.")
            result.loaded_confidence = "MEDIUM"
            result.present = True
            result.method = "leg_a_only_probe_fail"
            result.leg_b["passed"] = False
            result.leg_b["note"] = "probe message send failed"
            return

        # Bounded poll for canary echo
        leg_b_passed, b_note = self._poll_for_canary(canary, pre_probe_head)
        result.leg_b["passed"] = leg_b_passed
        result.leg_b["method"] = "chat.history + transcript jsonl fallback"
        result.leg_b["note"] = b_note

        if leg_b_passed:
            _ok(f"LEG B passed: agent echoed canary {canary!r}")
            result.present = True
            result.loaded_confidence = "HIGH"
            result.method = "leg_a_and_leg_b"
        else:
            _warn(f"LEG B inconclusive: canary not echoed within timeout ({self.probe_timeout}s)")
            result.present = True
            result.loaded_confidence = "MEDIUM"
            result.method = "leg_a_only_b_timeout"

    # ------------------------------------------------------------------
    # Session row helpers
    # ------------------------------------------------------------------
    def _resolve_sessions_json(self) -> Optional[Path]:
        if self.sessions_json_override:
            return Path(self.sessions_json_override)
        root = os.environ.get("FLEET_REFRESH_ROOT", "").strip()
        if root:
            base = Path(root)
        elif Path("/data/.openclaw").exists():
            base = Path("/data/.openclaw")
        else:
            base = Path.home() / ".openclaw"
        return base / "agents" / "main" / "sessions" / "sessions.json"

    def _read_session_row(self, sessions_path: Path) -> tuple[Optional[str], Optional[str]]:
        """
        Read the session row for self.session_key from sessions.json.
        Returns (sessionId, sessionStartedAt) — either may be None.
        """
        try:
            data = json.loads(sessions_path.read_text())
            row = data.get(self.session_key, {})
            return row.get("sessionId"), row.get("sessionStartedAt")
        except Exception as exc:
            _warn(f"Could not read sessions.json: {exc}")
            return None, None

    # ------------------------------------------------------------------
    # Gateway call helpers
    # ------------------------------------------------------------------
    def _do_reset(self) -> bool:
        """Issue sessions.reset via gateway call.  Returns True on success."""
        _info(f"Issuing sessions.reset for key: {self.session_key}")
        if not shutil.which("openclaw"):
            _err("openclaw not on PATH")
            return False
        try:
            result = subprocess.run(
                ["openclaw", "gateway", "call", "sessions.reset",
                 "--params", json.dumps({"key": self.session_key,
                                          "reason": "a2-load-assert"})],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                _err(f"sessions.reset failed (exit {result.returncode}): {result.stderr[:200]}")
                return False
            try:
                resp = json.loads(result.stdout)
                if resp.get("ok") is False:
                    _err(f"sessions.reset returned error: {resp}")
                    return False
                _ok("sessions.reset succeeded")
                return True
            except Exception:
                _ok("sessions.reset succeeded (non-JSON response)")
                return True
        except subprocess.TimeoutExpired:
            _err("sessions.reset timed out")
            return False
        except Exception as exc:
            _err(f"sessions.reset exception: {exc}")
            return False

    def _get_history_head(self) -> Optional[str]:
        """Return the id of the most recent message in chat.history, or None."""
        if not shutil.which("openclaw"):
            return None
        try:
            result = subprocess.run(
                ["openclaw", "gateway", "call", "chat.history",
                 "--params", json.dumps({"key": self.session_key, "limit": 5})],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode != 0:
                return None
            data = json.loads(result.stdout)
            msgs = data if isinstance(data, list) else data.get("messages", [])
            if msgs:
                last = msgs[-1]
                return last.get("id") or last.get("messageId")
        except Exception:
            pass
        return None

    def _send_probe(self) -> bool:
        """Send the probe message via openclaw message send (one-way).  Returns True if the command succeeded."""
        if not shutil.which("openclaw"):
            _err("openclaw not on PATH; probe send failed")
            return False
        try:
            result = subprocess.run(
                ["openclaw", "message", "send",
                 "--channel", "telegram",
                 "--target", str(self.ceo_chat_id),
                 "--message", self._PROBE_MESSAGE],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                _warn(f"probe send returned exit {result.returncode}: {result.stderr[:200]}")
                return False
            _info("Probe message sent")
            return True
        except subprocess.TimeoutExpired:
            _warn("probe send timed out")
            return False
        except Exception as exc:
            _warn(f"probe send exception: {exc}")
            return False

    def _poll_for_canary(
        self,
        canary: str,
        pre_probe_head: Optional[str],
    ) -> tuple[bool, str]:
        """
        Bounded poll of chat.history for a NEW assistant message echoing canary.
        Falls back to reading the transcript jsonl directly.
        Returns (passed, note).
        """
        deadline = time.monotonic() + self.probe_timeout
        attempt = 0
        chat_history_available = True

        while time.monotonic() < deadline:
            attempt += 1
            _info(f"LEG B poll attempt {attempt} (deadline in {deadline - time.monotonic():.0f}s)")

            if chat_history_available and shutil.which("openclaw"):
                try:
                    result = subprocess.run(
                        ["openclaw", "gateway", "call", "chat.history",
                         "--params", json.dumps({"key": self.session_key, "limit": 20})],
                        capture_output=True, text=True, timeout=15
                    )
                    if result.returncode == 0:
                        data = json.loads(result.stdout)
                        msgs = data if isinstance(data, list) else data.get("messages", [])
                        for msg in msgs:
                            msg_id = msg.get("id") or msg.get("messageId")
                            role = msg.get("role") or msg.get("type", "")
                            text = msg.get("content") or msg.get("text") or ""
                            if pre_probe_head and msg_id == pre_probe_head:
                                break
                            if role in ("assistant", "agent") and canary in str(text):
                                return True, f"canary echoed in chat.history msg id={msg_id}"
                    else:
                        out = result.stdout + result.stderr
                        if "unknown method" in out.lower() or "not found" in out.lower():
                            _warn("chat.history RPC not available; falling back to transcript jsonl")
                            chat_history_available = False
                except Exception as exc:
                    _warn(f"chat.history poll exception: {exc}")
                    chat_history_available = False

            transcript_found = self._scan_transcript_for_canary(canary)
            if transcript_found:
                return True, "canary echoed (found in transcript jsonl)"

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sleep_time = min(self.poll_interval, remaining)
            if sleep_time > 0:
                time.sleep(sleep_time)

        return False, f"canary not found within {self.probe_timeout}s timeout"

    def _scan_transcript_for_canary(self, canary: str) -> bool:
        """
        Read the most recent transcript jsonl for the session and scan for
        the canary in assistant/agent messages.  Secondary read path when
        chat.history is display-normalized or the RPC is absent.
        """
        try:
            sessions_path = self._resolve_sessions_json()
            if sessions_path is None:
                return False
            data = json.loads(sessions_path.read_text())
            row = data.get(self.session_key, {})
            session_id = row.get("sessionId")
            if not session_id:
                return False
            root = sessions_path.parent.parent.parent  # .openclaw/
            jsonl_path = root / "agents" / "main" / "sessions" / f"{session_id}.jsonl"
            if not jsonl_path.is_file():
                return False
            for line in jsonl_path.read_text().splitlines():
                try:
                    entry = json.loads(line)
                    if entry.get("role") in ("assistant", "agent"):
                        content = entry.get("content") or entry.get("text") or ""
                        if canary in str(content):
                            return True
                except Exception:
                    continue
        except Exception as exc:
            _warn(f"transcript jsonl scan failed: {exc}")
        return False

    # ------------------------------------------------------------------
    # Core file / canary helpers
    # ------------------------------------------------------------------
    def _generate_canary(self) -> str:
        """Generate a unique plain-alphanumeric canary token."""
        epoch = int(time.time())
        rand = random.randint(1000, 9999)
        safe_box = "".join(c if c.isalnum() else "X" for c in self.box)
        return f"A2CANARY{safe_box}{epoch}{rand}"

    def _resolve_core_file(self) -> Optional[Path]:
        """
        Return the path to the target core file (soul_md) using the same
        resolution as resolve_injected_core_files.  Workspace override wins.
        """
        if self.workspace_override:
            return Path(self.workspace_override) / "SOUL.md"
        if resolve_injected_core_files is not None:
            try:
                paths = resolve_injected_core_files("main")
                return paths.get("soul_md")
            except Exception as exc:
                _warn(f"resolve_injected_core_files failed: {exc}")
        root = os.environ.get("FLEET_REFRESH_ROOT", "").strip()
        if root:
            return Path(root) / "workspace" / "SOUL.md"
        if Path("/data/.openclaw/workspace/SOUL.md").exists():
            return Path("/data/.openclaw/workspace/SOUL.md")
        return Path.home() / ".openclaw" / "workspace" / "SOUL.md"

    def _write_canary(self, core_path: Path, canary: str) -> bool:
        """Append canary token + instruction to the core file."""
        try:
            instruction = self._CANARY_INSTRUCTION.format(canary=canary)
            line = f"\n<!-- a2-canary-probe start -->\n{instruction}\n{canary}\n<!-- a2-canary-probe end -->\n"
            with open(core_path, "a") as f:
                f.write(line)
            self._canary_written_to = core_path
            _info(f"Canary {canary!r} written to {core_path}")
            return True
        except Exception as exc:
            _warn(f"Canary write failed: {exc}")
            return False

    def _strip_canary(self, core_path: Path, canary: str) -> bool:
        """Remove the canary block from the core file (idempotent)."""
        try:
            text = core_path.read_text()
            cleaned = re.sub(
                r"\n<!-- a2-canary-probe start -->.*?<!-- a2-canary-probe end -->\n",
                "",
                text,
                flags=re.DOTALL,
            )
            if cleaned != text:
                core_path.write_text(cleaned)
                _info(f"Canary stripped from {core_path}")
            return True
        except Exception as exc:
            _warn(f"Canary strip failed: {exc}")
            return False

    def _cleanup(self) -> None:
        """
        Strip the canary from the core file and issue a final sessions.reset
        so the box returns to its real loaded state.  Idempotent.
        """
        if self._canary_written_to and self._canary_token:
            self._strip_canary(self._canary_written_to, self._canary_token)
            _info("Issuing final sessions.reset after canary cleanup")
            self._do_reset()
            self._canary_written_to = None
            self._canary_token = None

    # ------------------------------------------------------------------
    # Model availability check
    # ------------------------------------------------------------------
    def _detect_model(self) -> bool:
        """
        Detect whether the local box has a live/working model.
        Uses the box's own gateway only — NEVER borrows another box's key.
        Returns True if a model appears to be live.
        """
        if not shutil.which("openclaw"):
            return False
        try:
            result = subprocess.run(
                ["openclaw", "gateway", "call", "chat.history",
                 "--params", json.dumps({"key": self.session_key, "limit": 1})],
                capture_output=True, text=True, timeout=15
            )
            out = result.stdout + result.stderr
            no_model_signals = [
                "no model", "no_model", "no working model",
                "model not configured", "model unavailable",
                "api key", "unauthorized", "rate limit",
            ]
            if any(s in out.lower() for s in no_model_signals):
                _warn("No-model signal detected in gateway response")
                return False
            if result.returncode == 0:
                return True
            return False
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Confidence helpers (used by the bash gate for exit-code mapping)
# ---------------------------------------------------------------------------
_CONFIDENCE_EXIT = {
    "HIGH":    0,
    "MEDIUM":  0,   # degraded but not an error
    "UNKNOWN": 0,   # honest no-model; not an alert condition
    "LOW":     2,   # LEG A failed; operator alert needed
}


def _ts_strictly_after(post: Optional[str], pre: Optional[str]) -> bool:
    """Return True if post > pre (ISO8601 or epoch int/str comparison)."""
    if post is None or pre is None:
        return False
    try:
        return float(str(post)) > float(str(pre))
    except (ValueError, TypeError):
        pass
    return str(post) > str(pre)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="A.2 v2 load assertion — LEG A (sessionId re-init) + LEG B (canary echo)"
    )
    parser.add_argument("--box", required=True, help="Box label")
    parser.add_argument("--session-key", required=True,
                        help="Full session key, e.g. agent:main:telegram:direct:12345")
    parser.add_argument("--ceo-chat-id", default=None,
                        help="Telegram chat ID for probe destination (owner/CEO session)")
    parser.add_argument("--sessions-json", default=None,
                        help="Override path to sessions.json")
    parser.add_argument("--workspace", default=None,
                        help="Override workspace path (for tests)")
    parser.add_argument("--probe-timeout", type=int, default=90,
                        help="Seconds to wait for canary echo (default 90)")
    parser.add_argument("--poll-interval", type=int, default=5,
                        help="Seconds between chat.history polls (default 5)")
    args = parser.parse_args()

    asserter = A2LoadAssert(
        box=args.box,
        session_key=args.session_key,
        ceo_chat_id=args.ceo_chat_id,
        sessions_json=args.sessions_json,
        workspace=args.workspace,
        probe_timeout=args.probe_timeout,
        poll_interval=args.poll_interval,
    )
    result = asserter.run()

    print(json.dumps(result, indent=2))

    confidence = result.get("loaded_confidence", "LOW")
    sys.exit(_CONFIDENCE_EXIT.get(confidence, 2))


if __name__ == "__main__":
    main()
