#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""landing_bridge.py — S49-08 bridge wrapper: S49 dispatch -> Skill 71 landing.

Why this exists (rooms/S49/s49-08-entrypoint-audit.md, landing row):
Skill 71's launch-context import (scripts/launch_context.py +
scripts/write_intake.py on trevorotts1/openclaw-onboarding main)
validates the exact S49 page-request (1.0, or 1.1 carrying its
prompt_policy_id citation) and cross-checks the launch
record, the route-graph hash, and the brand hash. It is VERIFIED format
consumption, but it is NOT a bare adapter-config entry:

  * it works INSIDE a run directory: page-request.json staged at the
    run root byte-identical to the dispatch request, the launch record
    at launch.json, the route graph at the request's route_graph_ref
    (which must be run-relative: no absolute path, no ".."), and the
    brand file at the request's brand_ref;
  * it needs operator arguments the S49 page-request does not carry:
    --page-version (standard|long-form), --brand-owner, --image-cap;
  * production is the 14-stage stage_gate.py pipeline run inside that
    run directory, and the result emitter (scripts/write_page_result.py)
    writes page-result.json INSIDE the run directory, while dispatch
    expects the result at its own {result} path.

This bridge is the seam between those two shapes. Dispatch invokes it
as the landing adapter command:

  python3 landing_bridge.py --request {request} --result {result}
      --work-dir {work_dir} --bridge-config <bridge-config.json>

The bridge config is a JSON object with exactly two sections:

  "skill71": {"root": "<abs path to the Skill 71 tree>",
              "python": "<optional interpreter, default sys.executable>"}
  "landing": {"run_dir": "<abs path; the Skill 71 run directory>",
              "page_version": "standard" | "long-form",
              "brand_owner": "<recorded brand owner string>",
              "image_cap": <int >= 0>,
              "launch_record": "<abs path to the launch record JSON>",
              "brand_file": "<abs path to the approved brand file>",
              "consent_statements": "<optional abs path to a JSON list
                                      of {id, text, required} objects>"}

FAIL-CLOSED DISCIPLINE: page_version, brand_owner and image_cap come
from the bridge config ONLY. The bridge never invents them (no
defaults, no derivation from the request: the launch-context importer
itself records that these skill-local decisions stay with the
operator's intake answers). A missing or invalid value aborts the
bridge with a named error BEFORE any consumer process runs and before
anything is staged. The same discipline covers the launch record and
the brand file: both are operator-supplied paths, and their bytes must
hash / cross-check against the request (brand_hash, launch identity,
route_graph_hash) or the bridge aborts.

The page-request is staged VERBATIM (the exact bytes dispatch wrote),
because launch_context's import places those same bytes at the run's
page-request.json and the receipt echo is only faithful when they are
byte-identical. The route graph bytes staged are the ones whose
SHA-256 equals the request's route_graph_hash (normally the route
graph dispatch itself wrote into the work dir); a mismatch aborts.

Staging never overwrites a run file silently: a pre-existing run file
whose bytes differ from the bytes about to be staged aborts the bridge
with a named conflict, so one launch's run directory is never quietly
re-pointed at another launch's context.

The pipeline phase invokes stage_gate.py "report" on the run
directory. The gate itself owns closing stages (an agent-driven,
multi-session production process); the bridge records the gate's
verdict and stops there. The result is then emitted by
write_page_result.py and validated with the page-result 1.0 receipt
rules (collect_launch_receipts.validate_result, imported when
importable, else the vendored page-result schema via a stdlib schema
check) BEFORE it is placed at the dispatch {result} path. An invalid
result is never placed. When the fallback runs, its use is announced
on stderr and named in the bridge summary ("receipt_validation"),
and the fallback enforces the independent-review cross-check too,
so the downgrade is visible and drops no receipt rule.

The pipeline command is substitutable through the bridge config
("landing"."pipeline_command": a non-empty argv list run with the run
directory as the working directory) so fixture consumers can stand in
for the live, agent-driven pipeline in tests. Production configs omit
it and get the stage gate report.

Stdlib only. Exit 0 = result placed; 2 = fail-closed refusal;
3 = usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# The documented exit contract: 0 = result placed, 2 = fail-closed
# refusal, 3 = usage error. EXIT_USAGE is applied by
# _BridgeArgumentParser.error below: argparse's stock usage exit is
# 2, which a caller could not distinguish from a refusal.
EXIT_OK = 0
EXIT_FAILCLOSED = 2
EXIT_USAGE = 3

ROLE = "landing"
SKILL = 71


class BridgeError(ValueError):
    """A named fail-closed refusal: the bridge ran nothing and staged
    nothing beyond what the message names."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_json_file(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BridgeError(f"{label}: cannot read {path}: {exc}")
    except ValueError as exc:
        raise BridgeError(f"{label}: {path} is not valid JSON: {exc}")


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise BridgeError(f"{label}: cannot read {path}: {exc}")


def _stage_file(run_dir: Path, rel: str, raw: bytes, label: str) -> None:
    """Write raw at run_dir/rel, refusing to silently overwrite
    different bytes (fail closed on a run/context mismatch).

    Defence in depth (independent review D1): the resolved target
    must stay strictly inside the resolved run dir. Callers validate
    their refs before staging, but any ref that escapes the run
    directory (absolute, or containing "..") is refused here by name
    as well, so no staging write can ever land outside the run
    directory."""
    base = run_dir.resolve()
    target = (base / rel).resolve()
    if base not in target.parents:
        raise BridgeError(
            f"{label}: staging path {rel!r} resolves to {target}, "
            f"outside the run directory {base}; the bridge stages "
            f"only inside the run directory and refuses this ref")
    if target.is_file():
        if target.read_bytes() == raw:
            return
        raise BridgeError(
            f"{label}: {target} already exists with different bytes; "
            f"this run directory belongs to a different context and the "
            f"bridge will not overwrite it")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)


# ---------------------------------------------------------------------------
# Bridge config: every operator value is named and validated up front.
# Nothing here has a default: an absent value is a refusal, by name.
# ---------------------------------------------------------------------------

def _require_str(section: Dict[str, Any], key: str, label: str) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BridgeError(
            f"bridge config: {label}.{key} is missing or empty; this "
            f"value is operator-supplied and the bridge never invents it")
    return value


def _require_abs_path(section: Dict[str, Any], key: str, label: str) -> Path:
    value = _require_str(section, key, label)
    p = Path(value)
    if not p.is_absolute():
        raise BridgeError(
            f"bridge config: {label}.{key} must be an absolute path, "
            f"got {value!r}")
    return p


def load_bridge_config(path: Path) -> Dict[str, Any]:
    cfg = _load_json_file(path, "bridge config")
    if not isinstance(cfg, dict):
        raise BridgeError("bridge config: the document is not a JSON object")
    skill = cfg.get("skill71")
    if not isinstance(skill, dict):
        raise BridgeError("bridge config: missing 'skill71' section")
    landing = cfg.get("landing")
    if not isinstance(landing, dict):
        raise BridgeError("bridge config: missing 'landing' section")

    root = _require_abs_path(skill, "root", "skill71")
    for rel in ("scripts/write_intake.py", "scripts/stage_gate.py",
                "scripts/write_page_result.py",
                "references/page-request.schema.json"):
        if not (root / rel).is_file():
            raise BridgeError(
                f"bridge config: skill71.root {root} does not contain "
                f"{rel}; the bridge refuses to run against a tree that "
                f"is not Skill 71")
    python = skill.get("python", sys.executable)
    if not isinstance(python, str) or not python.strip():
        raise BridgeError("bridge config: skill71.python must be a "
                          "non-empty string when present")

    run_dir = _require_abs_path(landing, "run_dir", "landing")
    page_version = landing.get("page_version")
    if page_version not in ("standard", "long-form"):
        raise BridgeError(
            "bridge config: landing.page_version is missing or invalid "
            f"(got {page_version!r}); --page-version is an operator "
            "intake decision the page-request does not carry, and the "
            "bridge never invents it: set landing.page_version to "
            "'standard' or 'long-form'")
    brand_owner = _require_str(landing, "brand_owner", "landing")
    image_cap = landing.get("image_cap")
    if isinstance(image_cap, bool) or not isinstance(image_cap, int) \
            or image_cap < 0:
        raise BridgeError(
            "bridge config: landing.image_cap is missing or invalid "
            f"(got {image_cap!r}); --image-cap is an operator intake "
            "decision the page-request does not carry, and the bridge "
            "never invents it: set landing.image_cap to an integer >= 0")
    launch_record = _require_abs_path(landing, "launch_record", "landing")
    if not launch_record.is_file():
        raise BridgeError(
            f"bridge config: landing.launch_record {launch_record} "
            "does not exist; the launch record is operator-supplied")
    brand_file_cfg = _require_abs_path(landing, "brand_file", "landing")
    if not brand_file_cfg.is_file():
        raise BridgeError(
            f"bridge config: landing.brand_file {brand_file_cfg} does "
            "not exist; the approved brand file is operator-supplied")
    consent = landing.get("consent_statements")
    consent_path: Optional[Path] = None
    if consent is not None:
        consent_path = _require_abs_path(landing, "consent_statements",
                                         "landing")
        if not consent_path.is_file():
            raise BridgeError(
                f"bridge config: landing.consent_statements "
                f"{consent_path} does not exist")
    pipeline_command = landing.get("pipeline_command")
    if pipeline_command is not None:
        if not isinstance(pipeline_command, list) or not pipeline_command \
                or not all(isinstance(x, str) and x for x in pipeline_command):
            raise BridgeError(
                "bridge config: landing.pipeline_command must be a "
                "non-empty list of command strings when present")
    return {
        "skill_root": root,
        "python": python,
        "run_dir": run_dir,
        "page_version": page_version,
        "brand_owner": brand_owner,
        "image_cap": image_cap,
        "launch_record": launch_record,
        "brand_file_cfg": brand_file_cfg,
        "consent_path": consent_path,
        "pipeline_command": pipeline_command,
    }


# ---------------------------------------------------------------------------
# Request-side cross-checks (before anything runs).
# ---------------------------------------------------------------------------

def check_request(request_path: Path) -> (Dict[str, Any], bytes):
    raw = _read_bytes(request_path, "page-request")
    req = _load_json_file(request_path, "page-request")
    if not isinstance(req, dict):
        raise BridgeError("page-request: the document is not a JSON object")
    if req.get("page_role") != ROLE:
        raise BridgeError(
            f"page-request: page_role is {req.get('page_role')!r}; this "
            f"bridge serves the landing role only")
    if req.get("assigned_skill") != SKILL:
        raise BridgeError(
            f"page-request: assigned_skill is "
            f"{req.get('assigned_skill')!r}; this bridge serves Skill "
            f"71 only")
    # Dual-accept (adoption map section 1.1, the PP-Y2 cure): the
    # bridge accepts the 1.0 shape and the 1.1 shape carrying its
    # prompt_policy_id citation, under the same pair rule the landed
    # PP-T2 switch enforces in dispatch_launch.validate_request. Any
    # other shape is refused for its actual defect, never by name
    # alone; the import re-validates the request in full downstream.
    version = req.get("schema_version")
    if version not in ("1.0", "1.1"):
        raise BridgeError(
            f"page-request: schema_version is {version!r}; Skill "
            "71's launch-context import consumes the dual-accept "
            "page-request (1.0, or 1.1 carrying prompt_policy_id), "
            "so dispatch must hand it a 1.0 or 1.1 request")
    if version == "1.1":
        pid = req.get("prompt_policy_id")
        if not isinstance(pid, str) or not pid.strip():
            raise BridgeError(
                "page-request: a 1.1 request must carry a non-empty "
                "prompt_policy_id (the 1.1 label exists to carry "
                "the field)")
    elif "prompt_policy_id" in req:
        raise BridgeError(
            "page-request: prompt_policy_id requires request "
            "schema_version 1.1 (the 1.0 schema forbids the field)")
    ref = req.get("route_graph_ref")
    if not isinstance(ref, str) or not ref.strip():
        raise BridgeError("page-request: route_graph_ref is missing")
    ref_path = Path(ref)
    if ref_path.is_absolute() or ".." in ref_path.parts:
        raise BridgeError(
            f"page-request: route_graph_ref {ref!r} is not a "
            "run-relative path; Skill 71's import refuses it and so "
            "does the bridge")
    bref = req.get("brand_ref")
    if not isinstance(bref, str) or not bref.strip():
        raise BridgeError("page-request: brand_ref is missing")
    bref_path = Path(bref)
    if bref_path.is_absolute() or ".." in bref_path.parts:
        raise BridgeError(
            f"page-request: brand_ref {bref!r} is not a "
            "run-relative path; the bridge stages the brand file "
            "inside the run directory at this ref and refuses a "
            "ref that escapes it")
    return req, raw


def resolve_graph_bytes(req: Dict[str, Any], work_dir: Path) -> bytes:
    """The route graph bytes whose SHA-256 equals the request's
    route_graph_hash: the copy dispatch wrote into the work dir first,
    then the file the request's ref names relative to the work dir."""
    want = req["route_graph_hash"]
    candidates = [work_dir / "route-graph.json",
                  work_dir / Path(req["route_graph_ref"])]
    seen = []
    for cand in candidates:
        if cand in seen:
            continue
        seen.append(cand)
        if cand.is_file():
            raw = cand.read_bytes()
            if _sha256(raw) == want:
                return raw
    raise BridgeError(
        f"route graph: no graph under the dispatch work dir "
        f"({work_dir}) hashes to the request's route_graph_hash "
        f"{want}; dispatch writes route-graph.json beside the "
        "requests, and the bridge stages only bytes that match the "
        "approved hash (stale routing is refused)")


# ---------------------------------------------------------------------------
# Result validation: S49's own receipt rules when importable, else the
# vendored page-result 1.0 schema (stdlib subset check below).
# Fallback use is announced (stderr + the bridge summary) and never
# silent, and the fallback enforces the independent-review rule too.
# ---------------------------------------------------------------------------

def _load_receipts_validator() -> (Optional[Any], Optional[str]):
    """collect_launch_receipts.validate_result from the sibling
    dispatch tree this bridge was staged with, when importable.

    Returns (validate_result, None) on success, or (None, reason)
    when the module cannot be imported. The caller announces the
    fallback whenever the reason is not None, so the downgrade is
    never silent (independent review D2)."""
    here = Path(__file__).resolve()
    candidates = []
    env = os.environ.get("S49_SCRIPTS_DIR")
    if env:
        candidates.append(Path(env))
    for parent in here.parents:
        candidates.append(parent / "49-signature-funnel" / "scripts")
    for cand in candidates:
        target = cand / "collect_launch_receipts.py"
        if target.is_file():
            try:
                spec = importlib.util.spec_from_file_location(
                    "collect_launch_receipts", target)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod.validate_result, None
            except Exception as exc:
                return None, f"{target} could not be imported ({exc})"
    return None, ("no collect_launch_receipts.py found under "
                  "S49_SCRIPTS_DIR or the sibling dispatch tree")


def _schema_violations(instance: Any, schema: Dict[str, Any],
                       path: str = "$") -> List[str]:
    """Stdlib subset of JSON Schema, mirroring the interpreter Skill
    71's launch_context carries (type incl. lists, const, enum,
    required, properties, additionalProperties false, items,
    minLength, minimum, pattern). Fallback for when S49's receipts
    module is not importable."""
    import re as _re
    problems: List[str] = []

    def type_ok(value: Any, want: str) -> bool:
        if want == "string":
            return isinstance(value, str)
        if want == "boolean":
            return isinstance(value, bool)
        if want == "null":
            return value is None
        if want == "array":
            return isinstance(value, list)
        if want == "object":
            return isinstance(value, dict)
        if want == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if want == "number":
            return isinstance(value, (int, float)) \
                and not isinstance(value, bool)
        return True

    if not isinstance(schema, dict):
        return problems
    want = schema.get("type")
    if want is not None:
        wants = want if isinstance(want, list) else [want]
        if not any(type_ok(instance, w) for w in wants):
            problems.append(f"{path}: expected type "
                            f"{' or '.join(wants)}")
            return problems
    if "const" in schema and instance != schema["const"]:
        problems.append(f"{path}: must be {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        problems.append(f"{path}: {instance!r} is not one of "
                        f"{schema['enum']}")
    if isinstance(instance, str):
        if schema.get("minLength") is not None \
                and len(instance) < schema["minLength"]:
            problems.append(f"{path}: shorter than minLength "
                            f"{schema['minLength']}")
        if schema.get("pattern") \
                and not _re.search(schema["pattern"], instance):
            problems.append(f"{path}: does not match pattern "
                            f"{schema['pattern']!r}")
    if isinstance(instance, (int, float)) \
            and not isinstance(instance, bool):
        if schema.get("minimum") is not None \
                and instance < schema["minimum"]:
            problems.append(f"{path}: below minimum {schema['minimum']}")
    if isinstance(instance, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(instance):
                problems.extend(_schema_violations(
                    item, item_schema, f"{path}[{i}]"))
    if isinstance(instance, dict):
        for key in schema.get("required", []) or []:
            if key not in instance:
                problems.append(f"{path}: missing required field {key!r}")
        props = schema.get("properties", {}) or {}
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in props:
                    problems.append(f"{path}: additional property "
                                    f"{key!r} is not allowed")
        for key, subschema in props.items():
            if key in instance and isinstance(subschema, dict):
                problems.extend(_schema_violations(
                    instance[key], subschema, f"{path}.{key}"))
    return problems


def validate_emitted_result(result_path: Path,
                            req: Dict[str, Any]) -> (Dict[str, Any], str):
    """Validate the emitted page-result with S49's receipt rules
    (exact request echo included). Raises BridgeError on any failure;
    returns (parsed result, validation mode) on success, where the
    mode names which validator actually ran and is printed in the
    bridge summary."""
    result = _load_json_file(result_path, "page-result")
    validator, unavailable = _load_receipts_validator()
    if validator is not None:
        fails = validator(result, req)
        if fails:
            raise BridgeError(
                "page-result: the emitted result failed S49 receipt "
                "validation (collect_launch_receipts.validate_result): "
                + "; ".join(fails))
        return result, "collect_launch_receipts.validate_result"
    # Fallback (independent review D2): the vendored schema plus the
    # exact echo, as before, AND the independent-review cross-check
    # collect_launch_receipts.validate_result enforces, which this
    # fallback used to drop. The downgrade itself is announced on
    # stderr here and named in the bridge summary via the returned
    # mode; it is never silent.
    print("landing bridge: WARNING: collect_launch_receipts."
          "validate_result is unavailable (" + str(unavailable) + "); "
          "validating the emitted page-result with the vendored "
          "page-result 1.0 schema fallback instead. This is a "
          "downgrade and it is announced, not silent.",
          file=sys.stderr)
    schema_path = Path(__file__).resolve().parent / "vendor" \
        / "page-result.schema.json"
    schema = _load_json_file(schema_path, "vendored page-result schema")
    problems = _schema_violations(result, schema)
    if problems:
        raise BridgeError(
            "page-result: the emitted result violates the page-result "
            "1.0 schema: " + "; ".join(problems))
    if isinstance(result, dict):
        for f in ("request_id", "input_hash", "page_id", "launch_id",
                  "revision", "tenant_id", "location_id", "test_only"):
            if result.get(f) != req.get(f):
                raise BridgeError(
                    f"page-result: does not echo its request on {f}: "
                    f"{result.get(f)!r} != {req.get(f)!r}")
        if result.get("independent_review"):
            reviewer = result.get("reviewer_session")
            if not reviewer:
                raise BridgeError(
                    "page-result: independent_review claimed with "
                    "no reviewer session (vendored-schema fallback "
                    "enforces the same rule as "
                    "collect_launch_receipts.validate_result)")
            if reviewer == result.get("author_session"):
                raise BridgeError(
                    "page-result: independent_review claimed but "
                    "reviewer == author (vendored-schema fallback "
                    "enforces the same rule as "
                    "collect_launch_receipts.validate_result)")
    return result, "vendored_schema_fallback"


# ---------------------------------------------------------------------------
# The bridge.
# ---------------------------------------------------------------------------

def _run(argv: List[str], label: str, cwd: Optional[Path] = None,
         timeout: float = 1800.0) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              cwd=str(cwd) if cwd else None,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        raise BridgeError(f"{label}: timed out after {timeout}s")
    except OSError as exc:
        raise BridgeError(f"{label}: cannot execute {argv[0]!r}: {exc}")
    if proc.returncode != 0:
        detail = (proc.stdout + proc.stderr).strip()[:800]
        raise BridgeError(
            f"{label}: exited {proc.returncode}: {detail}")
    return proc


def bridge(request_path: Path, result_path: Path, work_dir: Path,
           config_path: Path) -> Dict[str, Any]:
    cfg = load_bridge_config(config_path)
    req, request_raw = check_request(request_path)

    skill_root: Path = cfg["skill_root"]
    python: str = cfg["python"]
    run_dir: Path = cfg["run_dir"]

    # Operator-supplied context documents, cross-checked against the
    # request BEFORE anything is staged or run.
    launch_raw = _read_bytes(cfg["launch_record"], "launch record")
    launch = _load_json_file(cfg["launch_record"], "launch record")
    if not isinstance(launch, dict):
        raise BridgeError("launch record: the document is not a "
                          "JSON object")
    for field in ("tenant_id", "location_id", "launch_id", "revision",
                  "brand_ref", "brand_hash", "prompt_policy_id",
                  "route_graph_ref", "route_graph_hash"):
        if launch.get(field) != req.get(field):
            raise BridgeError(
                f"launch record: {field} is {launch.get(field)!r} but "
                f"the page-request carries {req.get(field)!r}; the "
                "bridge stages only a launch record that agrees with "
                "the request it approves")
    brand_raw = _read_bytes(cfg["brand_file_cfg"], "brand file")
    if _sha256(brand_raw) != req["brand_hash"]:
        raise BridgeError(
            f"brand file: SHA-256 of the configured brand file is "
            f"{_sha256(brand_raw)}, not the request's approved "
            f"brand_hash {req['brand_hash']}; the bridge refuses to "
            "stage a brand the approved plan did not name")
    graph_raw = resolve_graph_bytes(req, work_dir)

    # Stage the run directory (byte-identical request; verbatim docs).
    run_dir.mkdir(parents=True, exist_ok=True)
    _stage_file(run_dir, "page-request.json", request_raw, "page-request")
    _stage_file(run_dir, "launch.json", launch_raw, "launch record")
    _stage_file(run_dir, req["route_graph_ref"], graph_raw, "route graph")
    _stage_file(run_dir, req["brand_ref"], brand_raw, "brand file")

    # Phase 1: intake + launch-context import (the format consumer).
    intake_argv = [python, str(skill_root / "scripts" / "write_intake.py"),
                   str(run_dir),
                   "--page-version", cfg["page_version"],
                   "--brand-owner", cfg["brand_owner"],
                   "--brand-file", req["brand_ref"],
                   "--image-cap", str(cfg["image_cap"]),
                   "--launch-context", str(run_dir / "page-request.json"),
                   "--launch-record", str(run_dir / "launch.json"),
                   "--route-graph",
                   str(run_dir / req["route_graph_ref"])]
    if cfg["consent_path"] is not None:
        intake_argv += ["--consent-statements", str(cfg["consent_path"])]
    _run(intake_argv, "Skill 71 write_intake (launch-context import)",
         timeout=600.0)

    # Phase 2: the production pipeline's own gate verdict. The gate
    # owns closing stages; the bridge never closes a stage itself.
    if cfg["pipeline_command"] is not None:
        _run(cfg["pipeline_command"], "landing pipeline command",
             cwd=run_dir)
        pipeline = {"command": cfg["pipeline_command"], "exit": 0}
    else:
        gate = [python, str(skill_root / "scripts" / "stage_gate.py"),
                "report", str(run_dir)]
        try:
            proc = subprocess.run(gate, capture_output=True, text=True,
                                  timeout=1800.0)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BridgeError(f"Skill 71 stage_gate report: {exc}")
        pipeline = {"command": gate, "exit": proc.returncode,
                    "note": "the stage gate owns stage closing; exit 0 "
                            "means every required stage is closed, any "
                            "other exit means production is still in "
                            "progress in the run directory"}

    # Phase 3: emit the page result inside the run, validate it with
    # S49's receipt rules, then place it at the dispatch result path.
    _run([python,
          str(skill_root / "scripts" / "write_page_result.py"),
          str(run_dir)], "Skill 71 write_page_result", timeout=600.0)
    emitted = run_dir / "page-result.json"
    if not emitted.is_file():
        raise BridgeError(
            "page-result: write_page_result.py exited 0 but no "
            f"page-result.json exists in the run directory {run_dir}")
    result, validation_mode = validate_emitted_result(emitted, req)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_bytes(emitted.read_bytes())
    return {
        "role": ROLE,
        "request_id": req["request_id"],
        "run_dir": str(run_dir),
        "result_path": str(result_path),
        "result_status": result.get("status"),
        "proof_class": result.get("proof_class"),
        "receipt_validation": validation_mode,
        "pipeline": pipeline,
    }


class _BridgeArgumentParser(argparse.ArgumentParser):
    """ArgumentParser whose usage errors exit EXIT_USAGE (3).

    Stock argparse exits 2 from error(); this bridge reserves 2 for
    fail-closed refusals, so a caller distinguishing the documented
    codes would misread a usage error as a refusal. The usage text
    and error line printed are argparse's own; only the code differs.
    (--help does not pass through error() and still exits 0.)"""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def main(argv: List[str]) -> int:
    ap = _BridgeArgumentParser(
        description="Bridge one S49 landing page-request into a "
                    "Skill 71 run and return its page-result.")
    ap.add_argument("--request", required=True,
                    help="the dispatch page-request JSON ({request})")
    ap.add_argument("--result", required=True,
                    help="where dispatch expects the page-result "
                         "({result})")
    ap.add_argument("--work-dir", required=True,
                    help="the dispatch work directory ({work_dir})")
    ap.add_argument("--bridge-config", required=True,
                    help="bridge config JSON (skill71 root + landing "
                         "operator values)")
    args = ap.parse_args(argv)
    try:
        summary = bridge(Path(args.request), Path(args.result),
                         Path(args.work_dir), Path(args.bridge_config))
    except BridgeError as exc:
        print(f"FAIL: {exc}")
        return EXIT_FAILCLOSED
    print(json.dumps(summary, indent=2))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
