#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""resolve_execution_environment.py — Claude Code / Codex environment and model
resolver for the Cinematic and Web Funnel Engine (Skill 62), build unit U3.

Implements spec section 6 ("Claude Code and Codex Execution Compatibility") and
section 16 P0 ("Environment and dependency resolve -> environment receipt,
resolved model map"):

  1. detects Claude Code, Codex, or an explicit override;
  2. loads the role -> alias model map for that environment;
  3. validates every REQUIRED role's alias resolves to an ACTUAL model
     identifier before the receipt can PASS;
  4. refuses silent substitution for Architect/Judge — there is no code path
     that automatically fills Architect/Judge from another role's model;
  5. permits a configured capability-based fallback (Mechanical Verifier /
     Documentation Writer only, never Architect/Judge) only when the operator
     passes --allow-capability-fallback explicitly, and always records that
     the fallback fired;
  6. records environment, alias, and the ACTUAL resolved model identifier for
     every role in a written receipt (environment-receipt.json when run
     through a --run-dir, or printed to stdout otherwise).

CAPABILITY ROLES (spec 6.1): architect_judge, builder, mechanical_verifier,
documentation_writer. The first three are always required; documentation_writer
is optional by default (a project role-config file may not downgrade the
required-ness of the first three — any attempt to do so is ignored and flagged
in the receipt, never silently honored).

FAIL-CLOSED BY DESIGN: this module never guesses which model is actually
running. There is no environment variable that reliably exposes "the current
model identifier" from inside a session, so the ACTUAL model for every role
must be supplied explicitly by the invoking harness/operator (a
--resolution-file, or a CWFE_MODEL_<ROLE> environment variable). Absence of an
explicit value for a required role is a hard failure, never a silent default.

BUILDER != JUDGE (directive-level hard requirement for this build): once
architect_judge and builder both resolve to an actual model identifier, if
they are the *same* identifier the receipt FAILS unless the operator passes
BOTH --acknowledge-same-model-builder-judge AND a non-empty
--same-model-reason (a bare flag flip is not accepted — this keeps the
override auditable, never silent).

stdlib only. Exit codes: 0 = PASS (receipt written/printed, status PASS),
2 = FAIL (a resolution or invariant check failed; receipt is still
written/printed with status FAIL so the failure is inspectable), 3 = usage
error (bad arguments, unreadable config file, unknown explicit --environment).
"""

from __future__ import annotations

import argparse
import copy
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_USAGE = 3

# The general P0 phase AF code already declared in CWFE-MANIFEST.json
# (phases[0].af_code). Every failure this resolver can produce surfaces under
# this umbrella code plus a granular internal `reason_code` for detail — this
# module does not invent new top-level AF codes that would need reconciling
# into the manifest's cross-cutting dedup check owned by another unit.
AF_CODE_P0_ENVIRONMENT = "AF-CWFE-P0-ENVIRONMENT"

REQUIRED_ROLES = ("architect_judge", "builder", "mechanical_verifier")
OPTIONAL_ROLES = ("documentation_writer",)
ALL_ROLES = REQUIRED_ROLES + OPTIONAL_ROLES

# Roles a capability-based fallback is ever permitted to fill automatically.
# architect_judge is deliberately absent — there is no automatic-fallback code
# path for it at all, at any flag setting (spec 6.4.4 "refuses silent
# substitution for Architect/Judge").
FALLBACK_ELIGIBLE_ROLES = ("mechanical_verifier", "documentation_writer")
FALLBACK_SOURCE_ROLE = "builder"

KNOWN_ENVIRONMENTS = ("claude-code", "codex")

# Default capability-role -> alias map per spec 6.2 / 6.3. A project
# role-config file (--role-config) may override the `alias` string per role,
# but may never downgrade `required` for a REQUIRED_ROLES entry (enforced in
# _merge_role_config below).
DEFAULT_ROLE_MAP: Dict[str, Dict[str, Dict[str, Any]]] = {
    "claude-code": {
        "architect_judge": {"alias": "Opus", "required": True},
        "builder": {"alias": "Sonnet", "required": True},
        "mechanical_verifier": {"alias": "Haiku", "required": True},
        "documentation_writer": {"alias": "Fable", "required": False},
    },
    "codex": {
        "architect_judge": {"alias": "SOL", "required": True},
        "builder": {"alias": "TERRA", "required": True},
        "mechanical_verifier": {"alias": "LUNA", "required": True},
        "documentation_writer": {"alias": "TERRA", "required": False},
    },
}

# Best-effort autodetection signal env vars. These are a *convenience* only —
# a false negative here fails closed (status UNDETECTED), it never guesses.
# Verified present in a live Claude Code CLI session on 2026-07-15 (name only,
# no values read/printed): CLAUDECODE, CLAUDE_CODE_ENTRYPOINT. Codex signal
# names are best-effort and operator-overridable via --codex-signal-env since
# this module has no live Codex session to verify against; explicit
# --environment/CWFE_ENVIRONMENT always takes precedence over autodetection.
DEFAULT_CLAUDE_SIGNAL_VARS = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID")
DEFAULT_CODEX_SIGNAL_VARS = ("CODEX_HOME", "CODEX_SANDBOX", "CODEX_SANDBOX_NETWORK_DISABLED")


class UsageError(Exception):
    """Bad arguments / unreadable config — distinct from a resolution FAIL."""


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _role_env_var(role: str) -> str:
    return f"CWFE_MODEL_{role.upper()}"


# ---------------------------------------------------------------------------
# Environment detection
# ---------------------------------------------------------------------------

def detect_environment(
    explicit_override: Optional[str],
    env: Dict[str, str],
    claude_signal_vars: Tuple[str, ...] = DEFAULT_CLAUDE_SIGNAL_VARS,
    codex_signal_vars: Tuple[str, ...] = DEFAULT_CODEX_SIGNAL_VARS,
) -> Dict[str, Any]:
    """Returns {"name": "claude-code"|"codex"|"undetected", "detected_via": str,
    "explicit_override": bool}. Raises UsageError if an explicit override names
    an unknown environment (fail-closed on operator typo, not a silent guess)."""
    if explicit_override:
        if explicit_override not in KNOWN_ENVIRONMENTS:
            raise UsageError(
                f"--environment '{explicit_override}' is not a known environment "
                f"(expected one of {KNOWN_ENVIRONMENTS})"
            )
        return {"name": explicit_override, "detected_via": "explicit --environment", "explicit_override": True}

    env_override = env.get("CWFE_ENVIRONMENT", "").strip()
    if env_override:
        if env_override not in KNOWN_ENVIRONMENTS:
            raise UsageError(
                f"CWFE_ENVIRONMENT='{env_override}' is not a known environment "
                f"(expected one of {KNOWN_ENVIRONMENTS})"
            )
        return {"name": env_override, "detected_via": "env:CWFE_ENVIRONMENT", "explicit_override": True}

    for var in claude_signal_vars:
        if env.get(var, "").strip():
            return {"name": "claude-code", "detected_via": f"autodetect:env:{var}", "explicit_override": False}

    for var in codex_signal_vars:
        if env.get(var, "").strip():
            return {"name": "codex", "detected_via": f"autodetect:env:{var}", "explicit_override": False}

    return {"name": "undetected", "detected_via": "no explicit override and no known signal env var present", "explicit_override": False}


# ---------------------------------------------------------------------------
# Role/alias map loading
# ---------------------------------------------------------------------------

def _load_role_config(path: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        raise UsageError(f"--role-config path does not exist or is not a file: {path}")
    try:
        with p.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise UsageError(f"--role-config is not valid JSON ({path}): {exc}")
    if not isinstance(data, dict):
        raise UsageError(f"--role-config must be a JSON object keyed by environment name: {path}")
    return data


def _merge_role_config(
    base: Dict[str, Dict[str, Dict[str, Any]]],
    override: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Dict[str, Dict[str, Any]]], List[str]]:
    """Merge an operator-supplied role-config over the defaults. Only the
    `alias` string may be overridden. `required` for a REQUIRED_ROLES entry can
    never be downgraded by config — any attempt is ignored and reported back
    in `notes` so it is visible, never silently honored."""
    merged = copy.deepcopy(base)
    notes: List[str] = []
    if not override:
        return merged, notes

    for env_name, roles in override.items():
        if env_name not in merged:
            notes.append(f"role-config declares unknown environment '{env_name}' — ignored")
            continue
        if not isinstance(roles, dict):
            notes.append(f"role-config entry for '{env_name}' is not an object — ignored")
            continue
        for role_name, role_cfg in roles.items():
            if role_name not in ALL_ROLES:
                notes.append(f"role-config declares unknown role '{role_name}' under '{env_name}' — ignored")
                continue
            if not isinstance(role_cfg, dict):
                notes.append(f"role-config entry for '{env_name}.{role_name}' is not an object — ignored")
                continue
            if "alias" in role_cfg and isinstance(role_cfg["alias"], str) and role_cfg["alias"].strip():
                merged[env_name][role_name]["alias"] = role_cfg["alias"].strip()
            if "required" in role_cfg:
                if role_name in REQUIRED_ROLES and role_cfg["required"] is not True:
                    notes.append(
                        f"role-config attempted to downgrade required-ness of "
                        f"'{env_name}.{role_name}' — BLOCKED, remains required"
                    )
                elif role_name in OPTIONAL_ROLES:
                    merged[env_name][role_name]["required"] = bool(role_cfg["required"])
    return merged, notes


# ---------------------------------------------------------------------------
# Actual-model resolution (never guessed — explicit sources only)
# ---------------------------------------------------------------------------

def _load_resolution_file(path: Optional[str]) -> Dict[str, str]:
    if not path:
        return {}
    p = Path(path)
    if not p.is_file():
        raise UsageError(f"--resolution-file path does not exist or is not a file: {path}")
    try:
        with p.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise UsageError(f"--resolution-file is not valid JSON ({path}): {exc}")
    if not isinstance(data, dict):
        raise UsageError(f"--resolution-file must be a JSON object keyed by role name: {path}")
    return {k: v for k, v in data.items() if isinstance(v, str) and v.strip()}


def _resolve_actual_model(role: str, resolution_file_map: Dict[str, str], env: Dict[str, str]) -> Tuple[Optional[str], str]:
    """Returns (actual_model_or_None, source_description). Priority:
    1) --resolution-file entry for this role; 2) CWFE_MODEL_<ROLE> env var;
    3) unresolved (None) — never a guessed default."""
    if role in resolution_file_map:
        return resolution_file_map[role], "resolution-file"
    var = _role_env_var(role)
    val = env.get(var, "").strip()
    if val:
        return val, f"env:{var}"
    return None, "unresolved"


# ---------------------------------------------------------------------------
# Core resolution
# ---------------------------------------------------------------------------

def resolve(
    environment_override: Optional[str] = None,
    role_config_path: Optional[str] = None,
    resolution_file_path: Optional[str] = None,
    allow_capability_fallback: bool = False,
    acknowledge_same_model_builder_judge: bool = False,
    same_model_reason: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    claude_signal_vars: Tuple[str, ...] = DEFAULT_CLAUDE_SIGNAL_VARS,
    codex_signal_vars: Tuple[str, ...] = DEFAULT_CODEX_SIGNAL_VARS,
) -> Dict[str, Any]:
    """Runs the full P0 environment/model resolution and returns the receipt
    dict (also the exact JSON body written to environment-receipt.json).
    Raises UsageError for bad inputs (argument/config problems distinct from a
    resolution failure). Never raises for a resolution FAIL — that is
    expressed in the returned receipt's "status" field so callers can inspect
    a complete, evidence-bearing record either way."""
    if env is None:
        env = dict(os.environ)

    failure_reasons: List[str] = []
    notes: List[str] = []

    environment = detect_environment(environment_override, env, claude_signal_vars, codex_signal_vars)
    if environment["name"] == "undetected":
        failure_reasons.append(
            "ENV-UNDETECTED: could not detect Claude Code or Codex and no explicit "
            "--environment/CWFE_ENVIRONMENT override was supplied"
        )

    role_config_override = _load_role_config(role_config_path)
    role_map, merge_notes = _merge_role_config(DEFAULT_ROLE_MAP, role_config_override)
    notes.extend(merge_notes)

    resolution_file_map = _load_resolution_file(resolution_file_path)

    roles_receipt: Dict[str, Any] = {}
    env_role_map = role_map.get(environment["name"], {}) if environment["name"] != "undetected" else {}

    for role in ALL_ROLES:
        role_cfg = env_role_map.get(role)
        if role_cfg is None:
            roles_receipt[role] = {
                "alias": None,
                "alias_source": None,
                "required": role in REQUIRED_ROLES,
                "actual_model": None,
                "actual_model_source": "unresolved",
                "resolved": False,
                "fallback_used": False,
                "fallback_from": None,
            }
            if role in REQUIRED_ROLES and environment["name"] != "undetected":
                failure_reasons.append(
                    f"ROLE-ALIAS-MISSING: environment '{environment['name']}' has no alias configured "
                    f"for required role '{role}'"
                )
            continue

        alias = role_cfg.get("alias")
        required = bool(role_cfg.get("required", role in REQUIRED_ROLES))
        actual_model, source = _resolve_actual_model(role, resolution_file_map, env)
        fallback_used = False
        fallback_from = None

        if actual_model is None and required:
            if role in FALLBACK_ELIGIBLE_ROLES and allow_capability_fallback:
                fb_model, fb_source = _resolve_actual_model(FALLBACK_SOURCE_ROLE, resolution_file_map, env)
                if fb_model is not None:
                    actual_model = fb_model
                    source = f"capability-fallback:{FALLBACK_SOURCE_ROLE}:{fb_source}"
                    fallback_used = True
                    fallback_from = FALLBACK_SOURCE_ROLE
                    notes.append(
                        f"CAPABILITY-FALLBACK: role '{role}' had no resolved actual model; "
                        f"operator explicitly enabled --allow-capability-fallback, so it was "
                        f"filled from role '{FALLBACK_SOURCE_ROLE}' ({fb_model})"
                    )
                else:
                    failure_reasons.append(
                        f"ROLE-MODEL-UNRESOLVED: role '{role}' unresolved and its capability-fallback "
                        f"source role '{FALLBACK_SOURCE_ROLE}' is also unresolved"
                    )
            else:
                failure_reasons.append(
                    f"ROLE-MODEL-UNRESOLVED: required role '{role}' (alias '{alias}') has no ACTUAL "
                    f"model identifier — supply --resolution-file or {_role_env_var(role)}"
                    + (
                        "; capability fallback is not available for this role"
                        if role not in FALLBACK_ELIGIBLE_ROLES
                        else "; pass --allow-capability-fallback to permit an explicit builder fallback"
                    )
                )

        roles_receipt[role] = {
            "alias": alias,
            "alias_source": "role-config" if role_config_override else "default",
            "required": required,
            "actual_model": actual_model,
            "actual_model_source": source,
            "resolved": actual_model is not None,
            "fallback_used": fallback_used,
            "fallback_from": fallback_from,
        }

    # Architect/Judge hard rule: no automatic fallback path exists for it at
    # all (see FALLBACK_ELIGIBLE_ROLES above — architect_judge is never a
    # member), independent of --allow-capability-fallback. This assertion
    # documents and proves that invariant rather than relying on omission
    # alone; it can never fire from the loop above because the role is never
    # in FALLBACK_ELIGIBLE_ROLES, which is exactly the point.
    assert roles_receipt.get("architect_judge", {}).get("fallback_used") is not True, (
        "invariant violated: architect_judge must never receive an automatic capability fallback"
    )

    # Builder != Judge, provably.
    judge_model = roles_receipt.get("architect_judge", {}).get("actual_model")
    builder_model = roles_receipt.get("builder", {}).get("actual_model")
    distinctness: Dict[str, Any] = {
        "checked": judge_model is not None and builder_model is not None,
        "distinct": None,
        "override_acknowledged": False,
        "override_reason": None,
    }
    if judge_model is not None and builder_model is not None:
        same = judge_model.strip().lower() == builder_model.strip().lower()
        distinctness["distinct"] = not same
        if same:
            reason = (same_model_reason or "").strip()
            if acknowledge_same_model_builder_judge and reason:
                distinctness["override_acknowledged"] = True
                distinctness["override_reason"] = reason
                notes.append(
                    "BUILDER-JUDGE-COLLISION-ACKNOWLEDGED: builder and architect_judge resolved to the "
                    f"same actual model ('{builder_model}'); operator explicitly acknowledged this with "
                    f"reason: {reason}"
                )
            else:
                failure_reasons.append(
                    "BUILDER-JUDGE-COLLISION: builder and architect_judge resolved to the identical "
                    f"actual model ('{builder_model}') — the builder and final judge must be provably "
                    "different models; pass both --acknowledge-same-model-builder-judge and a non-empty "
                    "--same-model-reason to override explicitly (never silent)"
                )

    status = "PASS" if not failure_reasons else "FAIL"

    receipt: Dict[str, Any] = {
        "schema": "cwfe-environment-receipt/v1",
        "generated_at": _now(),
        "phase": "P0-ENVIRONMENT",
        "environment": environment,
        "roles": roles_receipt,
        "builder_judge_distinctness": distinctness,
        "notes": notes,
        "status": status,
        "af_code": None if status == "PASS" else AF_CODE_P0_ENVIRONMENT,
        "failure_reasons": failure_reasons,
    }
    return receipt


def write_receipt(receipt: Dict[str, Any], run_dir: Path) -> Path:
    out_path = run_dir / "environment-receipt.json"
    out_path.write_text(json.dumps(receipt, indent=2, sort_keys=False), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve the Claude Code / Codex capability-role model roster for "
        "the Cinematic and Web Funnel Engine (Skill 62), fail-closed. Writes "
        "environment-receipt.json when --run-dir is given, else prints JSON to stdout."
    )
    parser.add_argument("--run-dir", default=None, help="Run directory to write environment-receipt.json into.")
    parser.add_argument("--environment", default=None, choices=list(KNOWN_ENVIRONMENTS),
                         help="Explicit environment override (else autodetect from CWFE_ENVIRONMENT / signal env vars).")
    parser.add_argument("--role-config", default=None, help="Path to a project role-config JSON overriding aliases.")
    parser.add_argument("--resolution-file", default=None,
                         help="Path to a JSON file mapping role name -> ACTUAL resolved model identifier.")
    parser.add_argument("--allow-capability-fallback", action="store_true",
                         help="Explicitly permit mechanical_verifier/documentation_writer to fall back to "
                              "the builder's resolved model when otherwise unresolved. Never applies to "
                              "architect_judge.")
    parser.add_argument("--acknowledge-same-model-builder-judge", action="store_true",
                         help="Explicitly accept that builder and architect_judge resolved to the same "
                              "actual model. Must be paired with --same-model-reason.")
    parser.add_argument("--same-model-reason", default=None,
                         help="Required, non-empty justification when acknowledging a builder/judge model collision.")
    parser.add_argument("--self-test", action="store_true", help="Run the built-in offline self-test and exit.")
    return parser


def self_test() -> int:
    """Offline, deterministic self-test requiring no external state. Mirrors the
    U2 orchestrator's --self-test convention: proves the resolver's own
    fail-closed mechanics without touching a live run directory."""
    fails = 0

    # 1) No override, no signals, no config => UNDETECTED => FAIL, no crash.
    r = resolve(env={})
    if r["status"] != "FAIL" or r["environment"]["name"] != "undetected":
        print("  [FAIL] empty environment did not fail-closed as 'undetected'", file=sys.stderr)
        fails += 1
    else:
        print("  [PASS] empty environment fails closed (undetected, status FAIL, no guess made)")

    # 2) Claude Code signal present but no actual-model env vars => FAIL with
    #    ROLE-MODEL-UNRESOLVED for every required role (alias resolves, model does not).
    r = resolve(env={"CLAUDECODE": "1"})
    if r["status"] != "FAIL" or r["environment"]["name"] != "claude-code":
        print("  [FAIL] claude-code autodetect with no model env vars did not fail-closed correctly", file=sys.stderr)
        fails += 1
    elif not all("ROLE-MODEL-UNRESOLVED" in reason for reason in r["failure_reasons"] if "architect_judge" in reason or "builder" in reason or "mechanical_verifier" in reason):
        print("  [FAIL] expected ROLE-MODEL-UNRESOLVED failure reasons were not present", file=sys.stderr)
        fails += 1
    else:
        print("  [PASS] claude-code autodetected via env signal; unresolved actual models fail closed per required role")

    # 3) Full, valid Claude Code roster with builder != judge => PASS.
    full_env = {
        "CLAUDECODE": "1",
        "CWFE_MODEL_ARCHITECT_JUDGE": "claude-opus-4-8-fixture",
        "CWFE_MODEL_BUILDER": "claude-sonnet-5-fixture",
        "CWFE_MODEL_MECHANICAL_VERIFIER": "claude-haiku-4-5-fixture",
    }
    r = resolve(env=full_env)
    if r["status"] != "PASS":
        print(f"  [FAIL] a fully-resolved distinct roster did not PASS: {r['failure_reasons']}", file=sys.stderr)
        fails += 1
    elif not r["builder_judge_distinctness"]["distinct"]:
        print("  [FAIL] builder/judge distinctness not recorded as distinct on a valid roster", file=sys.stderr)
        fails += 1
    else:
        print("  [PASS] fully-resolved distinct claude-code roster PASSes and records distinctness")

    # 4) Same model for builder and judge, no acknowledgement => FAIL, never silent PASS.
    collision_env = dict(full_env)
    collision_env["CWFE_MODEL_BUILDER"] = "claude-opus-4-8-fixture"
    r = resolve(env=collision_env)
    if r["status"] != "FAIL" or not any("BUILDER-JUDGE-COLLISION" in x for x in r["failure_reasons"]):
        print("  [FAIL] identical builder/judge models did not fail-closed with BUILDER-JUDGE-COLLISION", file=sys.stderr)
        fails += 1
    else:
        print("  [PASS] identical builder/judge actual models fail closed (no silent pass-through)")

    # 5) Same collision, but explicitly and non-silently acknowledged => PASS, recorded.
    r = resolve(env=collision_env, acknowledge_same_model_builder_judge=True, same_model_reason="fixture: single-model roster deliberately tested")
    if r["status"] != "PASS" or not r["builder_judge_distinctness"]["override_acknowledged"]:
        print("  [FAIL] explicit, reasoned acknowledgement of a builder/judge collision did not PASS/record", file=sys.stderr)
        fails += 1
    else:
        print("  [PASS] explicit reasoned acknowledgement of a builder/judge collision PASSes and is recorded, never silent")

    # 6) Architect/Judge never receives an automatic capability fallback, even
    #    with --allow-capability-fallback set and judge unresolved.
    no_judge_env = {
        "CLAUDECODE": "1",
        "CWFE_MODEL_BUILDER": "claude-sonnet-5-fixture",
        "CWFE_MODEL_MECHANICAL_VERIFIER": "claude-haiku-4-5-fixture",
    }
    r = resolve(env=no_judge_env, allow_capability_fallback=True)
    if r["roles"]["architect_judge"]["resolved"] or r["roles"]["architect_judge"]["fallback_used"]:
        print("  [FAIL] architect_judge received a value via capability fallback — silent substitution occurred", file=sys.stderr)
        fails += 1
    elif r["status"] != "FAIL":
        print("  [FAIL] unresolved architect_judge with no fallback path available did not fail-closed", file=sys.stderr)
        fails += 1
    else:
        print("  [PASS] architect_judge never receives an automatic capability fallback, at any flag setting")

    # 7) Mechanical verifier DOES receive an explicit, flagged, and recorded
    #    capability fallback from builder when the operator opts in.
    mv_fallback_env = {
        "CLAUDECODE": "1",
        "CWFE_MODEL_ARCHITECT_JUDGE": "claude-opus-4-8-fixture",
        "CWFE_MODEL_BUILDER": "claude-sonnet-5-fixture",
    }
    r = resolve(env=mv_fallback_env, allow_capability_fallback=True)
    mv = r["roles"]["mechanical_verifier"]
    if r["status"] != "PASS" or not mv["fallback_used"] or mv["fallback_from"] != "builder":
        print("  [FAIL] mechanical_verifier capability fallback did not fire/record correctly", file=sys.stderr)
        fails += 1
    else:
        print("  [PASS] mechanical_verifier capability fallback fires only when explicitly enabled, and is recorded")

    # 8) Codex mapping resolves SOL/TERRA/LUNA aliases.
    codex_env = {
        "CWFE_ENVIRONMENT": "codex",
        "CWFE_MODEL_ARCHITECT_JUDGE": "sol-fixture-model",
        "CWFE_MODEL_BUILDER": "terra-fixture-model",
        "CWFE_MODEL_MECHANICAL_VERIFIER": "luna-fixture-model",
    }
    r = resolve(env=codex_env)
    if r["status"] != "PASS" or r["roles"]["architect_judge"]["alias"] != "SOL" or r["roles"]["builder"]["alias"] != "TERRA" or r["roles"]["mechanical_verifier"]["alias"] != "LUNA":
        print("  [FAIL] codex environment did not resolve SOL/TERRA/LUNA aliases correctly", file=sys.stderr)
        fails += 1
    else:
        print("  [PASS] codex environment resolves SOL/TERRA/LUNA aliases from CWFE_ENVIRONMENT override")

    if fails:
        print(f"RESULT: FAIL — {fails} self-test check(s) failed.", file=sys.stderr)
        return EXIT_FAIL
    print("RESULT: PASS — resolve_execution_environment self-test green (8 checks).")
    return EXIT_OK


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test())

    try:
        receipt = resolve(
            environment_override=args.environment,
            role_config_path=args.role_config,
            resolution_file_path=args.resolution_file,
            allow_capability_fallback=args.allow_capability_fallback,
            acknowledge_same_model_builder_judge=args.acknowledge_same_model_builder_judge,
            same_model_reason=args.same_model_reason,
        )
    except UsageError as exc:
        print(f"USAGE ERROR: {exc}", file=sys.stderr)
        sys.exit(EXIT_USAGE)

    if args.run_dir:
        run_dir = Path(args.run_dir)
        if not run_dir.is_dir():
            print(f"USAGE ERROR: --run-dir does not exist: {run_dir}", file=sys.stderr)
            sys.exit(EXIT_USAGE)
        out_path = write_receipt(receipt, run_dir)
        print(f"environment-receipt.json written: {out_path}")
    else:
        print(json.dumps(receipt, indent=2, sort_keys=False))

    if receipt["status"] == "PASS":
        print(f"RESULT: PASS — environment='{receipt['environment']['name']}', "
              f"judge='{receipt['roles']['architect_judge']['actual_model']}', "
              f"builder='{receipt['roles']['builder']['actual_model']}' (distinct="
              f"{receipt['builder_judge_distinctness']['distinct']})")
        sys.exit(EXIT_OK)
    else:
        print(f"RESULT: FAIL [{receipt['af_code']}] — {'; '.join(receipt['failure_reasons'])}", file=sys.stderr)
        sys.exit(EXIT_FAIL)


if __name__ == "__main__":
    main()
