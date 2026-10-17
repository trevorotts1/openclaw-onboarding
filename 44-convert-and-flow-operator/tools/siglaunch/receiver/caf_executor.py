"""S44-02 production Executor adapter over the caf CLI.

Implements the receiver's Executor protocol (receiver.py) by driving the
Skill 44 engine through subprocesses — every call is a FRESH process, so
capability evidence never comes from cached in-process state (the
DESIGN-NOTES fresh-process rule). Parsing is grounded in the engine's
actual contracts, read firsthand:

- `caf doctor`: plain-text verdict lines; exit 0 for PASS *and* WARN,
  exit 1 for FAIL (contract drift). A token WARN does not distinguish
  absent from revoked at this surface — the probe reports
  "absent-or-dead" honestly and the S06 auth entry point owns the
  distinction and the remediation.
- `caf workflows build <plan.json>`: stats JSON (workflow id, errors)
  on the output stream; nonzero exit means failure.
- `caf workflows export --json --workflow-id <id>`: the read-back.
- `caf workflows qc --json <id>`: rubric + exit code.

Dependency prechecks do NOT invent a CLI surface: they consult the
Phase-A provisioning ledger (the receipts Phase A wrote), which is the
input contract the two-stage handoff defines.

Fail-closed throughout: unparseable output is a failure with the raw
evidence preserved in errors, never a success.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

Runner = Callable[[list[str], int], tuple[int, str, str]]


def _subprocess_runner(argv: list[str], timeout: int) -> tuple[int, str, str]:
    proc = subprocess.run(argv, capture_output=True, text=True,
                          timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


def _extract_json(text: str) -> Optional[dict]:
    """Find the first complete JSON object in mixed CLI output."""
    start = text.find("{")
    while start != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(text[start:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        start = text.find("{", start + 1)
    return None


class CafExecutor:
    def __init__(self, caf_path: str = "caf",
                 runner: Runner = _subprocess_runner,
                 provisioning_ledger: Optional[str] = None,
                 snapshot_dir: Optional[str] = None,
                 timeout: int = 300):
        self.caf_path = caf_path
        self.runner = runner
        self.provisioning_ledger = provisioning_ledger
        self.snapshot_dir = snapshot_dir or tempfile.mkdtemp(
            prefix="s44-snapshots-")
        self.timeout = timeout

    # ── capability probe: fresh `caf doctor` process ─────────────────────
    def probe(self) -> dict:
        code, out, err = self.runner([self.caf_path, "doctor"], 120)
        text = (out + "\n" + err)
        if code == 1 or "FAIL doctor" in text:
            return {"token_state": "degraded",
                    "access_tier_used": "tier0-caf",
                    "doctor": text.strip()[:400]}
        if "Firebase token absent or dead" in text:
            return {"token_state": "absent-or-dead",
                    "access_tier_used": "tier0-caf",
                    "doctor": text.strip()[:400]}
        if "WARN doctor" in text:
            return {"token_state": "absent",
                    "access_tier_used": "tier0-caf",
                    "doctor": text.strip()[:400]}
        if "PASS doctor" in text:
            return {"token_state": "healthy",
                    "access_tier_used": "tier0-caf",
                    "doctor": text.strip()[:400]}
        return {"token_state": "degraded",
                "access_tier_used": "tier0-caf",
                "doctor": "unrecognized doctor output: " + text.strip()[:300]}

    # ── Phase-A dependency precheck against the provisioning ledger ──────
    def dependencies_present(self, location_id: str,
                             workflow: dict) -> list[str]:
        requires = workflow.get("requires") or {}
        if not requires:
            return []
        if not self.provisioning_ledger:
            return ["provisioning ledger not configured: dependencies "
                    "cannot be verified, refusing to assume"]
        try:
            ledger = json.loads(
                Path(self.provisioning_ledger).read_text())
        except Exception as e:  # unreadable ledger = unverifiable = missing
            return [f"provisioning ledger unreadable: {e}"]
        provisioned = ledger.get(location_id, {})
        missing = []
        for kind in ("tags", "fields", "products"):
            have = set(provisioned.get(kind, []))
            for want in requires.get(kind, []):
                if want not in have:
                    missing.append(f"{kind[:-1]}:{want}")
        return missing

    # ── AC20 snapshot-or-abort: export current folder state first ────────
    def snapshot(self, location_id: str, workflow_slug: str) -> bool:
        Path(self.snapshot_dir).mkdir(parents=True, exist_ok=True)
        target = Path(self.snapshot_dir) / (
            f"{location_id}-{workflow_slug}-{int(time.time())}.json")
        code, out, err = self.runner(
            [self.caf_path, "workflows", "export", "--json",
             "--folder", "Signature Launch"], 120)
        state = _extract_json(out) or _extract_json(err)
        if code != 0 or state is None:
            return False
        target.write_text(json.dumps(state))
        return target.exists()

    # ── build one workflow, then read it back and QC it ──────────────────
    def build(self, builder_plan: dict) -> dict:
        result = {"exit_code": 1, "workflow_id": None, "errors": [],
                  "notes": [], "export": None, "qc_exit_code": None,
                  "rubric": None}
        with tempfile.NamedTemporaryFile(
                "w", suffix=".json", delete=False) as fh:
            json.dump(builder_plan, fh)
            plan_path = fh.name
        code, out, err = self.runner(
            [self.caf_path, "workflows", "build", plan_path], self.timeout)
        stats = _extract_json(err) or _extract_json(out)
        result["exit_code"] = code
        if stats is None:
            result["errors"].append(
                "build output unparseable; raw tail: "
                + (err or out).strip()[-300:])
            return result
        result["errors"] = list(stats.get("errors", []))
        result["notes"] = list(stats.get("notes", []))
        workflow_id = (stats.get("workflow_id")
                       or stats.get("id")
                       or (stats.get("created") or [{}])[0].get("id"))
        result["workflow_id"] = workflow_id
        if code != 0 or not workflow_id:
            return result
        # read-back: the export is the receipt's evidence
        ecode, eout, eerr = self.runner(
            [self.caf_path, "workflows", "export", "--json",
             "--workflow-id", workflow_id], 120)
        export = _extract_json(eout) or _extract_json(eerr)
        if ecode != 0 or export is None:
            result["errors"].append("post-build export read-back failed")
            return result
        result["export"] = export
        # QC gate (read-only)
        qcode, qout, qerr = self.runner(
            [self.caf_path, "workflows", "qc", "--json", workflow_id],
            120)
        qc = _extract_json(qout) or _extract_json(qerr) or {}
        result["qc_exit_code"] = qcode
        result["rubric"] = qc.get("rubric", qc.get("score"))
        return result
