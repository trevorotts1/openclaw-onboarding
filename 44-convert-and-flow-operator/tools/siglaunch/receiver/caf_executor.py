"""S44-02 production Executor adapter over the caf CLI.

Implements the receiver's Executor protocol (receiver.py) by driving the
Skill 44 engine through subprocesses — every call is a FRESH process, so
capability evidence never comes from cached in-process state (the
DESIGN-NOTES fresh-process rule). Parsing is grounded in the engine's
actual contracts, verified firsthand against the installed CLI's own
--help surface (raw capture: rooms/S44/work/a16-resume/
caf-cli-surface-raw-2026-10-17.txt):

- `caf doctor`: plain-text verdict lines; exit 0 for PASS *and* WARN,
  exit 1 for FAIL (contract drift). A token WARN does not distinguish
  absent from revoked at this surface — the probe reports
  "absent-or-dead" honestly and the S06 auth entry point owns the
  distinction and the remediation.
- `--json` and `--experimental` are TOP-LEVEL caf options and must
  precede the command group: `caf --json --experimental workflows
  build --from-plan <plan.json>`. They are NOT per-command flags (a
  per-command `--json` is rejected with "No such option").
- `caf --json --experimental workflows build --from-plan <plan.json>`:
  stats JSON (workflow id, errors) on the output stream; nonzero exit
  means failure. Create commands are internal-API and require
  `--experimental`.
- `caf workflows export --workflow-id <id> --out <file>`: the
  read-back. The export JSON is written to the `--out` FILE (nothing
  is read from stdout), and the command routes through the internal
  Firebase client, so it needs the Firebase refresh token. Export has
  no `--json` and no `--folder` option.
- `caf --json workflows list`: the AC20 snapshot surface — the whole
  location's workflow state (payload may be a JSON array).
- There is NO `workflows qc` verb. Per-build QC is the skill-root
  script `qc-built-workflow.sh <workflow-id> --json` (exit 0 = all
  mechanically-checkable items PASS, 1 = one or more FAIL, 2 =
  workflow not found / caf unavailable / export blocked). Its --json
  output carries a "rubric" object with weighted_floor /
  weighted_ceiling numbers. The script requires `caf` on PATH, so
  the adapter invokes it through bash with the caf directory
  prepended to PATH.

Dependency prechecks do NOT invent a CLI surface: they consult the
Phase-A provisioning ledger (the receipts Phase A wrote), which is the
input contract the two-stage handoff defines.

Fail-closed throughout: unparseable output is a failure with the raw
evidence preserved in errors, never a success.
"""
from __future__ import annotations

import json
import shlex
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


def _extract_json_value(text: str):
    """Find the first complete JSON value (object OR array) in mixed
    CLI output. `workflows list --json` may emit a bare JSON array,
    which _extract_json (dict-only) would miss."""
    if not text:
        return None
    decoder = json.JSONDecoder()
    for start, ch in enumerate(text):
        if ch not in "{[":
            continue
        try:
            obj, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, (dict, list)):
            return obj
    return None


# ── export normalization (native export -> receiver export contract) ──
# Grounded in how qc-built-workflow.sh parses the same export shape:
# step lists may live at steps/actions/nodes or workflowData.templates;
# status is a top-level string; re-entry appears as allowMultiple /
# reEntry / allow_multiple / re_entry; trigger info appears as a
# top-level triggers[] list or as trigger-shaped step nodes.

_TRIGGER_TYPE_KEYS = ("triggerType", "trigger_type", "type")
_TRIGGER_STEP_TYPES = {"tagadded", "contact_tag", "tag_added",
                       "formsubmitted", "contactcreated"}
_REENTRY_KEYS = ("allowMultiple", "reEntry", "allow_multiple", "re_entry")


def _export_steps(obj: dict, workflow_data: dict) -> list:
    for candidate in (obj.get("steps"), obj.get("actions"),
                      obj.get("nodes"), workflow_data.get("templates")):
        if isinstance(candidate, list):
            return candidate
    return []


def _step_trigger_type(step: dict) -> Optional[str]:
    for key in _TRIGGER_TYPE_KEYS:
        value = step.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _is_trigger_step(raw_type: str) -> bool:
    low = raw_type.lower()
    return "trigger" in low or low in _TRIGGER_STEP_TYPES


def _step_tag(step: dict) -> Optional[str]:
    def from_mapping(mapping):
        if not isinstance(mapping, dict):
            return None
        tag = mapping.get("tag")
        if isinstance(tag, str) and tag:
            return tag
        tags = mapping.get("tags")
        if isinstance(tags, list) and tags and isinstance(tags[0], str) \
                and tags[0]:
            return tags[0]
        return None

    return from_mapping(step) or from_mapping(step.get("attributes"))


def _canonical_trigger(step: dict, raw_type: str) -> dict:
    low = raw_type.lower()
    if "tag" in low:
        entry = {"type": "contact_tag"}
        tag = _step_tag(step)
        if tag:
            entry["tag"] = tag
        return entry
    if "form" in low:
        return {"type": "form_submitted"}
    return {"type": raw_type}


def _export_allow_multiple(obj: dict, workflow_data: dict) -> bool:
    for key in _REENTRY_KEYS:
        for source in (obj, workflow_data):
            value = source.get(key)
            if isinstance(value, bool):
                return value
    return False


def _normalize_export(obj: dict, workflow_id: str) -> dict:
    """Translate a native caf export into the receiver's export
    contract: {"id", "status", "triggers", "steps", "allowMultiple"}.
    Never fabricates a trigger that is not in the export."""
    workflow_data = obj.get("workflowData")
    if not isinstance(workflow_data, dict):
        workflow_data = {}
    steps = _export_steps(obj, workflow_data)
    triggers = []
    top = obj.get("triggers")
    if isinstance(top, list):
        for entry in top:
            if isinstance(entry, dict) and entry.get("type"):
                normalized = {"type": entry["type"]}
                if entry.get("tag"):
                    normalized["tag"] = entry["tag"]
                triggers.append(normalized)
    for step in steps:
        if not isinstance(step, dict):
            continue
        raw_type = _step_trigger_type(step)
        if raw_type and _is_trigger_step(raw_type):
            triggers.append(_canonical_trigger(step, raw_type))
    status = obj.get("status")
    return {
        "id": (obj.get("id") or obj.get("workflowId")
               or workflow_data.get("id") or workflow_id),
        "status": status if isinstance(status, str) else None,
        "triggers": triggers,
        "steps": steps,
        "allowMultiple": _export_allow_multiple(obj, workflow_data),
    }


class CafExecutor:
    def __init__(self, caf_path: str = "caf",
                 runner: Runner = _subprocess_runner,
                 provisioning_ledger: Optional[str] = None,
                 snapshot_dir: Optional[str] = None,
                 timeout: int = 300,
                 qc_script: Optional[str] = None):
        self.caf_path = caf_path
        self.runner = runner
        self.provisioning_ledger = provisioning_ledger
        self.snapshot_dir = snapshot_dir or tempfile.mkdtemp(
            prefix="s44-snapshots-")
        self.timeout = timeout
        self.qc_script = qc_script

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

    # ── AC20 snapshot-or-abort: capture current location state first ─────
    def snapshot(self, location_id: str, workflow_slug: str) -> bool:
        Path(self.snapshot_dir).mkdir(parents=True, exist_ok=True)
        target = Path(self.snapshot_dir) / (
            f"{location_id}-{workflow_slug}-{int(time.time())}.json")
        code, out, err = self.runner(
            [self.caf_path, "--json", "workflows", "list"], 120)
        state = _extract_json_value(out)
        if state is None:
            state = _extract_json_value(err)
        if code != 0 or state is None:
            return False
        target.write_text(json.dumps(state))
        return target.exists()

    # ── per-build QC: skill-root qc-built-workflow.sh (no `qc` verb) ─────
    def _qc_script_path(self) -> Path:
        if self.qc_script:
            return Path(self.qc_script)
        try:
            skill_root = Path(self.caf_path).resolve().parents[2]
        except (IndexError, RuntimeError):
            return Path("qc-built-workflow.sh")
        return skill_root / "qc-built-workflow.sh"

    def _run_qc(self, workflow_id: str, result: dict) -> None:
        qc_path = self._qc_script_path()
        if not qc_path.exists():
            # Honest recording, never a fabricated pass: the receiver
            # sees qc_exit_code None and judges accordingly.
            result["notes"].append(
                "qc surface unavailable: qc-built-workflow.sh not "
                f"found at {qc_path}")
            return
        caf_dir = str(Path(self.caf_path).resolve().parent)
        # The QC script requires `caf` on PATH (command -v caf) and
        # shells out to it; prepend this executor's caf directory.
        command = (
            f"export PATH={shlex.quote(caf_dir)}:$PATH; "
            f"exec bash {shlex.quote(str(qc_path))} "
            f"{shlex.quote(str(workflow_id))} --json")
        qcode, qout, qerr = self.runner(["bash", "-c", command], 120)
        result["qc_exit_code"] = qcode
        qc = _extract_json(qout) or _extract_json(qerr) or {}
        rubric = qc.get("rubric")
        if isinstance(rubric, dict):
            floor = rubric.get("weighted_floor")
            if isinstance(floor, (int, float)) \
                    and not isinstance(floor, bool):
                result["rubric"] = floor

    # ── build one workflow, then read it back and QC it ──────────────────
    def build(self, builder_plan: dict) -> dict:
        result = {"exit_code": 1, "workflow_id": None, "errors": [],
                  "notes": [], "export": None, "export_raw": None,
                  "qc_exit_code": None, "rubric": None}
        with tempfile.NamedTemporaryFile(
                "w", suffix=".json", delete=False) as fh:
            json.dump(builder_plan, fh)
            plan_path = fh.name
        code, out, err = self.runner(
            [self.caf_path, "--json", "--experimental", "workflows",
             "build", "--from-plan", plan_path], self.timeout)
        stats = _extract_json(out) or _extract_json(err)
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
        # read-back: export writes the evidence JSON to the --out file
        with tempfile.NamedTemporaryFile(
                "w", suffix=".json", delete=False) as efh:
            export_path = efh.name
        ecode, _eout, _eerr = self.runner(
            [self.caf_path, "workflows", "export",
             "--workflow-id", workflow_id, "--out", export_path], 120)
        raw_export = None
        if ecode == 0:
            try:
                parsed = json.loads(Path(export_path).read_text())
                if isinstance(parsed, dict):
                    raw_export = parsed
            except (OSError, ValueError):
                raw_export = None
        if ecode != 0 or raw_export is None:
            result["errors"].append("post-build export read-back failed")
            return result
        result["export_raw"] = raw_export
        result["export"] = _normalize_export(raw_export, workflow_id)
        # QC gate (read-only): skill-root script, exit code + rubric
        self._run_qc(workflow_id, result)
        return result
