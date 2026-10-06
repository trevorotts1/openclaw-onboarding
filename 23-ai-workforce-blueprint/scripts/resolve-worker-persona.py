#!/usr/bin/env python3
"""resolve-worker-persona.py — RR-034 worker-start persona resolver (thin bridge).

Calls ONLY existing Skill 22/23 services — mechanical gate, catalog listing,
company-config default/governance resolution, content-task rule — and emits a
JSON envelope the FLEET worker-persona module consumes. No new scoring, no new
funnel, no network of its own.

Deliberately takes NO incident-text input (isolation by construction): incident
prose is untrusted data and must never reach persona selection.

Usage:
    python3 resolve-worker-persona.py --task "restart the gateway container" \
        --department rescue --format json
    python3 resolve-worker-persona.py --task "..." --company-config path.json \
        --catalog path.json --search-available 0 --budget-ms 5000
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_SHARED = _REPO / "shared-utils"
sys.path.insert(0, str(_HERE))

GOVERNANCE_FALLBACK = "covey-7-habits"
DEFAULT_FALLBACK = "blackceo-house-voice"
RESOLVER_VERSION = 1


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mech_gate():
    try:
        return _load("mechanical_gate", _SHARED / "mechanical-gate.py")
    except Exception:
        return None


def _selector():
    try:
        return _load("persona_selector_v2", _HERE / "persona-selector-v2.py")
    except Exception:
        return None


def _blend():
    try:
        return _load("persona_blend", _HERE / "persona_blend.py")
    except Exception:
        return None


def _catalog_sha(catalog_path):
    try:
        raw = Path(catalog_path).read_bytes()
        return hashlib.sha256(raw).hexdigest()[:16]
    except Exception:
        return None


def _policy_hash(cfg):
    if not isinstance(cfg, dict):
        return None
    subset = {
        "default_persona_id": str(cfg.get("default_persona_id") or ""),
        "governance_persona_id": str(cfg.get("governance_persona_id") or ""),
    }
    if not subset["default_persona_id"] and not subset["governance_persona_id"]:
        return None
    return hashlib.sha256(json.dumps(subset).encode()).hexdigest()[:32]


def _scope_key(company, box, ticket):
    return hashlib.sha256("|".join([company or "", box or "", ticket or ""]).encode()).hexdigest()[:16]


def resolve_worker_persona(task_text, *, company_config=None, catalog_path=None,
                           department="rescue", mode_hint=None, task_category=None,
                           allow_blend=True, search_available=True,
                           budget_ms=5000, scope=None):
    """Resolve worker persona context. Pure stdlib, hermetic.

    company_config: dict or Path to company-config.json (None => missing).
    catalog_path: Path to persona-categories.json (for provenance sha).
    scope: {company, box, ticket} — echoed + hashed, never used for lookup.
    """
    t0 = time.monotonic()
    scope = scope or {}
    task = str(task_text or "")

    # 1. mechanical gate (single source; inline mirror if file absent).
    gate = _mech_gate()
    if gate:
        mechanical = bool(gate.is_mechanical(task))
    else:
        tl = task.lower()
        mechanical = ("check disk" in tl or "check memory" in tl or
                      any(__import__("re").search(r"\b" + w + r"\b", tl)
                          for w in ("restart", "reboot", "ping", "ls", "chmod", "chown")))
    task_mode = "mechanical" if mechanical else str(mode_hint or "leadership")

    # 2. company config (mandatory policy source).
    cfg = None
    if isinstance(company_config, dict):
        cfg = company_config
    elif company_config:
        try:
            cfg = json.loads(Path(company_config).read_text(encoding="utf-8"))
        except Exception:
            cfg = None
    ph = _policy_hash(cfg) if cfg else None
    # A dict that carries neither key is not policy.
    policy_status = "ok" if ph else "missing_mandatory"

    cat_sha = _catalog_sha(catalog_path) if catalog_path else None

    def finish(sel_extra):
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        out = {
            "resolver_version": RESOLVER_VERSION,
            "task_mode": task_mode,
            "mechanical": mechanical,
            "policy_status": policy_status,
            "policy_hash": ph,
            "allow_unsafe_effects": ph is not None,
            "safe_diagnosis_only": ph is None,
            "budget_ms": int(budget_ms),
            "budget_exceeded": elapsed_ms > int(budget_ms),
            "elapsed_ms": elapsed_ms,
            "scope": {"company": scope.get("company", ""), "box": scope.get("box", ""),
                      "ticket": scope.get("ticket", "")},
            "scope_key": _scope_key(scope.get("company", ""), scope.get("box", ""), scope.get("ticket", "")),
            "catalog_sha": cat_sha,
            **sel_extra,
        }
        return out

    # 3. mechanical => governance pointer only, blend NEVER applicable.
    if mechanical:
        gov = GOVERNANCE_FALLBACK
        gov_src = "governance_default"
        if isinstance(cfg, dict) and str(cfg.get("governance_persona_id") or "").strip():
            gov, gov_src = str(cfg["governance_persona_id"]).strip(), "company_config"
        return finish({
            "persona_id": None, "no_persona_required": True,
            "governance_persona_id": gov, "governance_source": gov_src,
            "source": "mechanical-gate", "fallback": None,
            "blend_applicable": False, "blend_reason": "mechanical_no_blend",
            "task_category": task_category,
        })

    # 4. optional search unavailable => LABELED cached fallback.
    if not search_available:
        pid = DEFAULT_FALLBACK
        src = "default_persona"
        if isinstance(cfg, dict) and str(cfg.get("default_persona_id") or "").strip():
            pid, src = str(cfg["default_persona_id"]).strip(), "company_config"
        return finish({
            "persona_id": pid, "persona_version": 1,
            "source": "cached-fallback", "fallback": "labeled",
            "fallback_source": src,
            "provenance": {"source": "cached-fallback",
                           "reason": "remote_search_unavailable:search_available_false",
                           "catalog_sha": cat_sha, "pinned": True},
            "governance_persona_id": (str(cfg.get("governance_persona_id")).strip()
                                      if isinstance(cfg, dict) and str(cfg.get("governance_persona_id") or "").strip()
                                      else GOVERNANCE_FALLBACK),
            "blend_applicable": False, "blend_reason": "search_unavailable_no_blend",
            "task_category": task_category,
        })

    # 5. live selection through existing services (catalog listing + client-
    # sovereign default/governance resolution). Full funnel scoring needs a DB
    # + embeddings; the worker bridge resolves the governing/default ids and
    # reports provenance — the FLEET side records the receipt.
    sel = _selector()
    try:
        if sel is None:
            raise RuntimeError("selector_unavailable")
        # Build a minimal paths dict from explicit files (hermetic).
        import tempfile
        tmp = Path(tempfile.gettempdir()) / "rr034-resolve"
        paths = {
            "user_md": tmp / "USER.md",
            "persona_categories": Path(catalog_path) if catalog_path else (tmp / "no-cats.json"),
            "coaching_personas": tmp / "coaching",
            "company_config": Path(company_config) if company_config and not isinstance(company_config, dict) else (tmp / "no-cfg.json"),
            "skills": tmp / "skills",
        }
        if isinstance(company_config, dict):
            # spill dict to temp so the selector's own loader resolves it
            spill = tmp / "spill-company-config.json"
            tmp.mkdir(parents=True, exist_ok=True)
            spill.write_text(json.dumps(company_config), encoding="utf-8")
            paths["company_config"] = spill
            sel._COMPANY_CONFIG_CACHE = {"path": None, "data": None, "warned": True}
        available = sel.list_available_personas(paths)
        dpid, dsrc = sel._resolve_default_persona_id(paths, available)
        gpid, gsrc = sel._resolve_governance_persona_id(paths)
    except Exception as e:
        pid = DEFAULT_FALLBACK
        if isinstance(cfg, dict) and str(cfg.get("default_persona_id") or "").strip():
            pid = str(cfg["default_persona_id"]).strip()
        return finish({
            "persona_id": pid, "persona_version": 1,
            "source": "cached-fallback", "fallback": "labeled",
            "provenance": {"source": "cached-fallback",
                           "reason": "remote_search_unavailable:" + str(e)[:80],
                           "catalog_sha": cat_sha, "pinned": True},
            "governance_persona_id": GOVERNANCE_FALLBACK,
            "blend_applicable": False, "blend_reason": "search_unavailable_no_blend",
            "task_category": task_category,
        })

    # 6. blend ONLY where applicable: non-mechanical + content-task signal.
    blend_applicable, blend_reason = False, "not_content_task"
    if allow_blend:
        bl = _blend()
        try:
            if bl and bl.is_content_task(task):
                blend_applicable, blend_reason = True, "content_task"
        except Exception:
            pass

    return finish({
        "persona_id": dpid, "persona_version": 1,
        "source": "selector:" + str(dsrc),
        "fallback": None,
        "provenance": {"source": "skill22/23-selection", "catalog_sha": cat_sha, "pinned": False},
        "governance_persona_id": gpid, "governance_source": gsrc,
        "blend_applicable": blend_applicable, "blend_reason": blend_reason,
        "task_category": task_category,
    })


def main(argv=None):
    ap = argparse.ArgumentParser(description="RR-034 worker-start persona resolver")
    ap.add_argument("--task", required=True)
    ap.add_argument("--department", default="rescue")
    ap.add_argument("--mode", default=None)
    ap.add_argument("--task-category", default=None)
    ap.add_argument("--company-config", default=None)
    ap.add_argument("--catalog", default=None)
    ap.add_argument("--search-available", default="1")
    ap.add_argument("--allow-blend", default="1")
    ap.add_argument("--budget-ms", type=int, default=5000)
    ap.add_argument("--company", default="")
    ap.add_argument("--box", default="")
    ap.add_argument("--ticket", default="")
    ap.add_argument("--format", default="json", choices=["json"])
    a = ap.parse_args(argv)
    cfg = a.company_config if a.company_config else None
    out = resolve_worker_persona(
        a.task, company_config=cfg, catalog_path=a.catalog,
        department=a.department, mode_hint=a.mode, task_category=a.task_category,
        allow_blend=a.search_available and a.allow_blend not in ("0", "false", "no"),
        search_available=a.search_available not in ("0", "false", "no"),
        budget_ms=a.budget_ms,
        scope={"company": a.company, "box": a.box, "ticket": a.ticket},
    )
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
