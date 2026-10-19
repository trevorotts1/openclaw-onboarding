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
    # ── layer-9 observation basis (MAIN ruling, 2026-10-18, option (a)) ──
    # The native internal-API workflow object carries NO status field
    # and NO trigger contents: triggers live in a separate trigger-
    # bucket file the object points at (triggersFilePath +
    # isTriggerBucketMigrated), and draft state is a property of the
    # object's draft-only construction (the builder has no publish
    # operation). Verified firsthand against every internal surface
    # (export object, Tier-0 list/get, the internal listing) in A16
    # runs 7-8. The normalization therefore RECORDS the native
    # evidence verbatim and observes from it, so the receipt shows
    # exactly what its checks rest on:
    # - trigger_evidence: the bucket pointer fields, verbatim. The
    #   bucket file exists only because the builder created and
    #   linked a trigger for this workflow at build time.
    #   The bucket CONTENTS are NOT retrievable: `caf workflows`
    #   exposes list/get/export/create/build/patch-*/restore only
    #   (verified against the installed CLI's `workflows --help`),
    #   and internal/endpoints.py defines no trigger-bucket read
    #   path. No value is invented from the pointer.
    # - status "draft": when the object carries no explicit status,
    #   is not deleted, and stands as a builder-created object, its
    #   state is observed as draft, with status_evidence recording
    #   the native fields verbatim. A deleted object NEVER derives
    #   draft; an explicit native status always governs.
    trigger_evidence = {}
    if isinstance(obj.get("triggersFilePath"), str) \
            and obj.get("triggersFilePath"):
        trigger_evidence["triggers_file_path"] = obj["triggersFilePath"]
    if isinstance(obj.get("isTriggerBucketMigrated"), bool):
        trigger_evidence["bucket_migrated"] = \
            obj["isTriggerBucketMigrated"]
    status = obj.get("status")
    status_evidence = None
    if not isinstance(status, str):
        status = None
        if obj.get("deleted") is False and (obj.get("id")
                                            or obj.get("_id")):
            status = "draft"
            status_evidence = {}
            for native_key, out_key in (
                    ("deleted", "deleted"),
                    ("creationSource", "creation_source"),
                    ("version", "version"),
                    ("dataVersion", "data_version")):
                if native_key in obj:
                    status_evidence[out_key] = obj[native_key]
    normalized = {
        "id": (obj.get("id") or obj.get("workflowId")
               or workflow_data.get("id") or workflow_id),
        "status": status,
        "triggers": triggers,
        "steps": steps,
        "allowMultiple": _export_allow_multiple(obj, workflow_data),
    }
    if trigger_evidence:
        normalized["trigger_evidence"] = trigger_evidence
    if status_evidence is not None:
        normalized["status_evidence"] = status_evidence
    return normalized


class CafExecutor:
    # Evidence fields this adapter can actually fill (GU-018). The
    # receiver intersects this with its own producible set, so the
    # carrier declares exactly what exists. Fields absent here — the QC
    # checklist instance/complete/WF-item detail, ghl_pack_version, the
    # conversational trigger set — have no surface in this adapter and
    # are declared unproducible, never filled with a placeholder.
    EVIDENCE_FIELDS = frozenset({
        "build_stats", "readback", "qc.exit_code", "qc.rubric",
    })

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
        # Only the exit code and the rubric floor are captured. The
        # checklist instance path / completion flag / WF item count the
        # stage-14 contract asks for are NOT produced here; the receiver
        # declares them unproducible (GU-018) rather than inventing them.
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
        # qc.wf_items (automation-handoff.md:196-204: "the WF item
        # count carried VERBATIM, e.g. 22/22"). The QC script emits
        # `items` — one entry per WF item with a mechanical status —
        # so the count IS producible from this surface: PASSed items
        # over the number of items the script actually ran. An
        # N/A / REQUIRES_HUMAN_REVIEW item is not a PASS and is not
        # counted as one; it still counts in the denominator, so the
        # fraction can never overstate what was proven.
        items = qc.get("items")
        if isinstance(items, dict) and items:
            passed = sum(
                1 for entry in items.values()
                if isinstance(entry, dict)
                and entry.get("status") == "PASS")
            result["wf_items"] = f"{passed}/{len(items)}"

    # ── build one workflow, then read it back and QC it ──────────────────
    # ── per-operation QC fields this adapter CAN and CANNOT produce ──────
    # Contract: automation-handoff.md:196-204 / artifact-contracts.md:656-667
    # name qc.script, qc.exit_code, qc.checklist_instance,
    # qc.checklist_complete and qc.wf_items.
    #   qc.script / qc.exit_code  — produced (the script+its exit code).
    #   qc.wf_items               — produced from the script's `items`
    #                               object as PASSed/total (see _run_qc).
    #   qc.checklist_instance     — NOT producible HERE. qc-built-workflow.sh
    #                               emits per-item statuses + the rubric to
    #                               stdout and appends build-events.jsonl; it
    #                               creates no checklist instance file. The
    #                               contract's instance is a run artifact
    #                               (filed under automation-wiring/), and a
    #                               receiver adapter has no run_dir to write
    #                               it into. It stays None, named in notes.
    #   qc.checklist_complete     — NOT producible HERE. Mechanical PASS
    #                               (overall_mechanical) is not checklist
    #                               completion: the REQUIRES_HUMAN_REVIEW
    #                               items are graded by the Step-9 QC agent,
    #                               outside the executor contract. None.
    def build(self, builder_plan: dict) -> dict:
        result = {"exit_code": 1, "workflow_id": None, "errors": [],
                  "notes": [], "export": None, "export_raw": None,
                  "qc_exit_code": None, "rubric": None, "wf_items": None,
                  "stats": None}
        with tempfile.NamedTemporaryFile(
                "w", suffix=".json", delete=False) as fh:
            json.dump(builder_plan, fh)
            plan_path = fh.name
        code, out, err = self.runner(
            [self.caf_path, "--json", "--experimental", "workflows",
             "build", "--from-plan", plan_path], self.timeout)
        stats = _extract_json(out) or _extract_json(err)
        result["exit_code"] = code
        # Record the FULL build stats on every run (MAIN layer-9
        # ruling): run 8's stats were discarded by the pre-fix
        # executor, leaving its triggers_created count unpreserved —
        # an evidence gap that stays named on that receipt. No future
        # run loses them.
        result["stats"] = stats
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
        if not workflow_id:
            # The engine CLI's REAL stats contract (utils/
            # workflow_builder.py build_from_plan -> stats dict,
            # emitted by gohighlevel_cli._emit_build_result): the
            # ONLY carrier of created workflow IDs on success is
            # stats["workflow_ids"], a {slug: id} map. There is no
            # top-level "workflow_id"/"id"/"created" key in a real
            # build result. Layer-8 defect, A16 run 7 (2026-10-18):
            # the native build SUCCEEDED but this extraction read
            # only the legacy keys above, returned None with empty
            # errors, and export/QC/judge never ran. Fixed under
            # MAIN's layer-8 ruling, option (a); regression-pinned
            # by test_stats_shape_regression.py, which feeds the
            # REAL stats shape through build(). Extraction prefers
            # the value for a slug in this build's own plan (plan
            # keys other than "folder"); a single-entry map is
            # unambiguous and is taken as-is; a multi-entry map
            # with no plan slug match extracts NOTHING (fail-closed:
            # never guess which workflow a receipt belongs to).
            ids_map = stats.get("workflow_ids")
            if isinstance(ids_map, dict) and ids_map:
                plan_slugs = [k for k in builder_plan if k != "folder"]
                for slug in plan_slugs:
                    candidate = ids_map.get(slug)
                    if isinstance(candidate, str) and candidate:
                        workflow_id = candidate
                        break
                if not workflow_id and len(ids_map) == 1:
                    only = next(iter(ids_map.values()))
                    if isinstance(only, str) and only:
                        workflow_id = only
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
