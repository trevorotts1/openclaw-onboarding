#!/usr/bin/env python3
"""
assert_model_sovereignty.py — AF-MODEL-SOVEREIGNTY enforcement gate (PLAN.md §7).

The single assertion this gate enforces:

  No task may dispatch (and no department/role/SOP may be considered configured)
  unless its resolved model is ALL of:
    (a) non-null AND not the `openrouter/free` literal nor any bare "free" default
    (b) present in the client's available inventory
    (c) NOT in FORBIDDEN_PREFIXES (Anthropic)
    (d) modality-appropriate (capabilities ⊇ required_modality)

  Otherwise the dispatch is BLOCKED and routed to needs_owner_input — NEVER
  silently downgraded to a free/text model.

This is the ONE place the gate logic lives. It is imported by:
  - the onboarding QC sweep (scripts/repair-model-sovereignty.sh, qc-system-integrity)
  - the Command Center runtime gate (mirrored in TypeScript as assertModelSovereignty;
    the CC build consumes the SAME capability map + cascade rules — see PLAN.md §10
    "remaining for CC repo").

Usage (library):
    from assert_model_sovereignty import assert_model_sovereignty
    verdict = assert_model_sovereignty(model_id, inventory=[...], required_modality="vision")
    if not verdict["ok"]:
        block_dispatch(verdict["reason"])

Usage (CLI, for QC sweeps over a config / a single model):
    python3 assert_model_sovereignty.py --model ollama/qwen3-vl:235b-cloud \
        --required-modality vision --config ~/.openclaw/openclaw.json
    # exit 0 = sovereign/valid ; exit 3 = BLOCKED (with JSON verdict on stdout)

    python3 assert_model_sovereignty.py --scan-config ~/.openclaw/openclaw.json
    # scans every agent model in the config; exit 3 if any offender found
"""

import argparse
import json
import os
import re
import sys

# Reuse the authoritative cascade + capability logic. Works whether imported as
# a package member or run as a loose script next to select_model.py.
# The import is OPTIONAL: the standalone Anthropic detector below (is_anthropic_model
# / text_has_anthropic_model_id) is pure-stdlib and MUST remain importable by the
# sandboxed skill scripts (e.g. Skill 52 Avatar Alchemist) that forbid heavy deps
# and may not ship select_model alongside. The full assert_model_sovereignty()
# gate still requires select_model and raises a clear error if it is absent.
try:
    from . import select_model as sm  # type: ignore
except Exception:  # noqa: BLE001
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import select_model as sm  # type: ignore
    except Exception:  # noqa: BLE001
        sm = None  # type: ignore


# ─── SK2-16 — canonical Anthropic / Claude model-id detector (one source) ─────
# The SINGLE place the "is this an Anthropic model?" test lives. Skill 52
# (Avatar Alchemist) previously carried FOUR divergent copies of this regex
# (aa_qc_cert, aa_director tier-check + bypass-scan, aa_build_check) with
# INCONSISTENT coverage — some missed the `anthropic.` dot route, some missed
# bare `opus`/`sonnet`/`haiku`, some missed a bare `anthropic` provider token.
# They now all defer to the two functions below so detection can never drift.
#
# Two inputs, two purpose-built matchers (same source of truth, no divergence):
#   • is_anthropic_model(id)          — a DISCRETE model-id string (a config
#       field, a resolved model id, a cert verifier_model). STRICT: matches
#       `anthropic` in any form (slash `anthropic/`, dot `anthropic.` /
#       `us.anthropic.`, or bare), the whole `claude` family (claude, claude-3,
#       claude-5, claude-opus/-sonnet/-haiku, future gens), AND the bare
#       Anthropic model families opus / sonnet / haiku (word-bounded).
#   • text_has_anthropic_model_id(t)  — scans FREE TEXT (a prompt .md, a
#       manifest .json) for a sneaked Anthropic model *id*. ID-SHAPED so it does
#       NOT false-positive on prose or on compliance documentation that merely
#       names the vendor or quotes the ban regex — e.g. a comment "the sole
#       Anthropic-Sonnet chain is removed per the client-path rule" or a manifest
#       line 'G-NOANTHROPIC hard-fails any /anthropic|claude/i id'. Only a real
#       id-shaped token trips it: `anthropic/<m>`, `anthropic.<m>`,
#       `openrouter/anthropic/<m>`, or `claude-<gen>` (claude-3, claude-opus-4,
#       claude-instant, future gens).
_ANTHROPIC_MODEL_ID_RE = re.compile(
    r"anthropic|claude|\b(?:opus|sonnet|haiku)\b", re.IGNORECASE
)
_ANTHROPIC_IN_TEXT_RE = re.compile(
    r"anthropic[/.][a-z0-9]|\bclaude-[a-z0-9]", re.IGNORECASE
)


def is_anthropic_model(model_id) -> bool:
    """True iff a DISCRETE model-id string references an Anthropic/Claude model.

    Fail-closed by contract: an EMPTY/None id returns False here (it is 'not an
    Anthropic id'), but an empty *resolved* model id is separately a hard failure
    at each caller's gate — callers must reject a missing id in their own right
    (they do). This function only answers the Anthropic-family question.
    """
    return bool(_ANTHROPIC_MODEL_ID_RE.search(str(model_id or "")))


def text_has_anthropic_model_id(text) -> bool:
    """True iff FREE TEXT contains an id-shaped Anthropic/Claude model reference.

    Used by content bypass-scans over prompts/manifests. Deliberately narrower
    than is_anthropic_model so prose that names the vendor while DOCUMENTING its
    removal is not flagged as a violation.
    """
    return bool(_ANTHROPIC_IN_TEXT_RE.search(str(text or "")))


def assert_model_sovereignty(
    model_id,
    inventory=None,
    required_modality="text",
    openclaw_json_path=None,
):
    """Return {ok: bool, reason: str, code: str, model_id, tier, required_modality}.

    `code` is one of: OK, NULL_MODEL, FREE_DEFAULT, FORBIDDEN, NOT_IN_INVENTORY,
    MODALITY_MISMATCH.
    """
    if sm is None:
        raise RuntimeError(
            "assert_model_sovereignty requires select_model.py (cascade/capability "
            "logic) alongside this module; it was not importable."
        )
    rm = required_modality or "text"

    def verdict(ok, code, reason):
        return {
            "ok": ok,
            "code": code,
            "reason": reason,
            "model_id": model_id,
            "tier": sm.tier_of_model(model_id) if model_id else 0,
            "required_modality": rm,
        }

    # (a) non-null + not a free/bare default
    if not model_id or not str(model_id).strip():
        return verdict(False, "NULL_MODEL",
                       "Resolved model is null/empty — dispatch BLOCKED, routed to owner.")
    mid = str(model_id).strip()
    if mid.lower() in sm.FREE_SENTINELS:
        return verdict(False, "FREE_DEFAULT",
                       f"Resolved model is the free sentinel '{mid}' — never a valid "
                       f"resolution (PLAN.md §7). Dispatch BLOCKED.")

    # (c) not forbidden (Anthropic)
    if sm._is_forbidden(mid):
        return verdict(False, "FORBIDDEN",
                       f"Resolved model '{mid}' is forbidden (Anthropic). BLOCKED.")

    # (b) present in inventory
    if inventory is None:
        cfg = sm._load_openclaw_config(openclaw_json_path)
        inventory = sm._list_available_models(cfg)
    inv_ids = []
    for m in inventory or []:
        if isinstance(m, str):
            inv_ids.append(m)
        elif isinstance(m, dict) and m.get("id"):
            inv_ids.append(m["id"])
    if inv_ids and mid not in inv_ids:
        return verdict(False, "NOT_IN_INVENTORY",
                       f"Resolved model '{mid}' is not in the client's available "
                       f"inventory. BLOCKED (PLAN.md §7b).")

    # (d) modality-appropriate (HARD)
    if not sm.model_has_modality(mid, rm):
        return verdict(False, "MODALITY_MISMATCH",
                       f"Resolved model '{mid}' lacks required modality '{rm}'. "
                       f"A {rm} task must run on a {rm}-capable model. BLOCKED.")

    return verdict(True, "OK", f"'{mid}' is sovereign (tier {sm.tier_of_model(mid)}, "
                               f"modality '{rm}' satisfied).")


def scan_config(openclaw_json_path=None):
    """Scan every agent model in a config for sovereignty offenders.

    Returns (offenders: list, scanned: list). An offender is any agent whose
    primary model fails the gate at the baseline `text` modality. (Per-task
    modality checks happen at dispatch; this is the build/QC-time floor that
    catches null / free-default / forbidden / not-in-inventory.)
    """
    if sm is None:
        raise RuntimeError(
            "scan_config requires select_model.py alongside this module; it was "
            "not importable."
        )
    cfg = sm._load_openclaw_config(openclaw_json_path)
    inventory = sm._list_available_models(cfg)
    offenders = []
    scanned = []

    def _primary(model_field):
        if isinstance(model_field, str):
            return model_field
        if isinstance(model_field, dict):
            return model_field.get("primary") or model_field.get("model")
        return None

    agents = cfg.get("agents", {})
    entries = []
    defaults = agents.get("defaults", {})
    if defaults.get("model"):
        entries.append(("agents.defaults", defaults.get("model")))
    for a in agents.get("list", []):
        if isinstance(a, dict):
            entries.append((a.get("id", "?"), a.get("model")))

    for agent_id, model_field in entries:
        primary = _primary(model_field)
        scanned.append({"agent": agent_id, "model": primary})
        v = assert_model_sovereignty(primary, inventory=inventory, required_modality="text")
        if not v["ok"]:
            offenders.append({"agent": agent_id, **v})

    return offenders, scanned


def main():
    p = argparse.ArgumentParser(description="AF-MODEL-SOVEREIGNTY enforcement gate.")
    p.add_argument("--model", default=None, help="A single resolved model id to validate")
    p.add_argument("--required-modality", default="text")
    p.add_argument("--config", default=None, help="Path to openclaw.json (inventory source)")
    p.add_argument("--scan-config", default=None,
                   help="Scan every agent model in this config for offenders")
    args = p.parse_args()

    if args.scan_config:
        offenders, scanned = scan_config(args.scan_config)
        print(json.dumps({
            "scanned": len(scanned),
            "offenders": offenders,
            "clean": not offenders,
        }, indent=2))
        sys.exit(0 if not offenders else 3)

    if args.model is not None:
        v = assert_model_sovereignty(
            args.model,
            required_modality=args.required_modality,
            openclaw_json_path=args.config,
        )
        print(json.dumps(v, indent=2))
        sys.exit(0 if v["ok"] else 3)

    p.error("provide either --model or --scan-config")


if __name__ == "__main__":
    main()
