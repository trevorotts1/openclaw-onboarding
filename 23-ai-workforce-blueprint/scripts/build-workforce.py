#!/usr/bin/env python3
"""
AI Workforce Blueprint - Interview Engine & Workspace Builder
Version: 2.1.0
Date: March 22, 2026

TIMEOUT OVERRIDE:
For complex businesses with many departments, the full workforce build
(interview + workspace creation + persona wiring + config updates) can take
significant time. The recommended sub-agent timeout is 1800 seconds (30 minutes).
Set this when spawning the build agent to avoid premature termination on
large builds with 8+ departments and full knowledge base content generation.

This is the core engine for Skill 23 (AI Workforce Blueprint).
It handles:
1. Option A/B/C selection (ALWAYS presented, never skipped)
2. Dynamic interview (3-7 questions per department, plain English)
3. Department workspace creation with core file inheritance
4. Specialist determination (permanent vs on-call, decided by AI silently)
5. Persona alignment using the Act As If Protocol and 5-layer check
6. ORG-CHART.md generation
7. Devil's Advocate auto-creation per department (SOUL.md + SOP.md)
8. Command Center departments.json generation
9. Flush after every question (resume capability via handoff file)
10. Config safety (backup before edits, validate JSON after)

NON-INTERACTIVE MODE:
- Pass --non-interactive to read all config from a JSON file instead of prompting
- Use --config-file to specify the JSON config path (default: workforce-config.json)
- This is required when running via AI agent that cannot handle interactive prompts

IMPORTANT:
- This script is executed BY the AI agent, not run directly by the client
- The AI reads this file to understand the interview flow and executes it conversationally
- Questions are generated dynamically based on industry and context, not from a static list
- The AI MUST be running on a high reasoning model (Opus, Sonnet, MiMo V2 Pro, Gemini 3.1 Pro, GPT 5.4)
- Research best practices uses openrouter/perplexity/sonar-pro-search

FORBIDDEN CLIENT-FACING LANGUAGE:
- Never say: SOPs, handoffs, tech stack, permanent agent, sub-agent, agent
- Instead say: step-by-step instructions, what departments share, tools you use, team member, specialist, director
"""

import os
import sys
import json
import re
import argparse
import shutil
import subprocess  # v10.15.25: module-level so bare subprocess.run / subprocess.TimeoutExpired
                   # in build_from_config (SOP-populate step) resolve. Previously the only
                   # `import subprocess` statements were function-local in OTHER functions, so the
                   # bare references crashed the build with NameError: name 'subprocess' is not defined.
from datetime import datetime
from pathlib import Path

# ── WS-2: import the role-library instantiation helpers from the sibling
# create_role_workspaces module so the PRIMARY build INSTANTIATES the 991
# pre-written SOPs (copy + token-personalize) instead of writing empty
# `[Step 1 - to be personalized]` stubs that then get LLM-regenerated. The
# normalizer (normalize_role_variants/normalize_dept) takes naive slug match
# from ~58% to ~100% coverage. Best-effort import: if it fails for any reason
# the build degrades gracefully to the legacy stub+LLM path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from create_role_workspaces import (
        library_lookup as _crw_library_lookup,
        fill_tokens as _crw_fill_tokens,
        normalize_dept as _crw_normalize_dept,
    )
    _LIBRARY_FILL_AVAILABLE = True
except Exception as _e:  # pragma: no cover - defensive
    _LIBRARY_FILL_AVAILABLE = False
    print(f"[ROLE-LIBRARY WARNING] create_role_workspaces import failed "
          f"({_e}); falling back to stub+LLM SOP path", file=sys.stderr)

# WS-2: build-wide tally of how roles were staffed, for the visible ratio log.
_LIBRARY_FILL_STATS = {"instantiated_from_library": 0, "llm_generated": 0}
# Set of role folder names (absolute paths) instantiated from the library, so
# write_sop_research_manifest() can SKIP them (their SOPs are already authored
# inside how-to.md — no LLM regeneration needed).
_LIBRARY_INSTANTIATED_ROLE_DIRS = set()


# ============================================================
# ARGUMENT PARSING
# ============================================================

def parse_args():
    """Parse command-line arguments. Supports --non-interactive for AI agent use."""
    parser = argparse.ArgumentParser(
        description="AI Workforce Blueprint - Interview Engine & Workspace Builder"
    )
    parser.add_argument(
        '--non-interactive',
        action='store_true',
        help='Read config from --config-file instead of prompting interactively'
    )
    parser.add_argument(
        '--config-file',
        default='workforce-config.json',
        help='JSON config file for non-interactive mode (default: workforce-config.json)'
    )
    return parser.parse_args()


def load_non_interactive_config(config_file):
    """
    Load workforce config from a JSON file for non-interactive mode.

    Expected JSON structure:
    {
        "company_name": "Acme Corp",
        "company_description": "We sell widgets online",
        "industry": "e-commerce",
        "tools": "Stripe, Convert and Flow, Shopify",
        "biggest_challenge": "Customer retention after first purchase",
        "departments": {
            "marketing": {
                "enabled": true,
                "activities": "Daily social media posts, weekly email campaigns",
                "kpis": "10K followers by Q3, 25% email open rate",
                "tools": "Convert and Flow, Canva, Later",
                "challenges": "No consistent posting schedule"
            },
            "sales": {
                "enabled": true,
                "activities": "Inbound lead follow-up, demo calls",
                "kpis": "Close 10 deals per month",
                "tools": "Convert and Flow, Calendly",
                "challenges": "Slow response time to inbound leads"
            }
        },
        "option": "A"
    }
    """
    if not os.path.isfile(config_file):
        print(f"[NON-INTERACTIVE ERROR] Config file not found: {config_file}", file=sys.stderr)
        print(f"[NON-INTERACTIVE ERROR] Create a workforce-config.json or use --config-file to specify path.",
              file=sys.stderr)
        sys.exit(1)

    with open(config_file, 'r') as f:
        try:
            config = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[NON-INTERACTIVE ERROR] Invalid JSON in {config_file}: {e}", file=sys.stderr)
            sys.exit(1)

    # Validate required fields
    required = ["company_name", "industry", "departments"]
    missing = [k for k in required if k not in config]
    if missing:
        print(f"[NON-INTERACTIVE ERROR] Missing required config keys: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    return config


# ============================================================
# CANONICAL DEPARTMENT FLOOR (N16 standard-unless-declined)
# ============================================================
# Every Zero Human Company is built with the 16 mandatory canonical
# departments UNLESS the client explicitly declined one. The canonical IDs
# live in department-naming-map.json (the source of truth). Legacy
# RECOMMENDED_DEPARTMENTS keys differ from canonical IDs (e.g. "billing" vs
# "billing-finance"); CANONICAL_ID_ALIASES maps canonical -> legacy so we
# inherit the rich legacy metadata without forking duplicate folders.

# canonical-id -> legacy RECOMMENDED_DEPARTMENTS key (when they differ)
CANONICAL_ID_ALIASES = {
    "billing-finance": "billing",
    "customer-support": "support",
    "web-development": "webdev",
    "app-development": "appdev",
    "communications": "comms",
    "openclaw-maintenance": "openclaw",
    "social-media": "social",
    "paid-advertisement": "paid-ads",
}

# BUG 1 FIX (variant-slug phantom duplicate): some clients store a canonical
# department under a VARIANT slug that is neither the canonical id nor its
# single CANONICAL_ID_ALIASES value (e.g. "legal-compliance" instead of
# "legal", "finance-ops" instead of "billing-finance"). Without this map the
# canonical-floor "already present?" check misses the variant and auto-adds a
# phantom DUPLICATE department. This map is used ONLY for the membership /
# "already present?" check below -- never for metadata inheritance.
# canonical-id -> list of additional equivalent slugs the client might use.
CANONICAL_VARIANT_SLUGS = {
    "legal": ["legal-compliance", "compliance"],
    "billing-finance": ["finance-ops", "finance", "billing-and-finance"],
    "graphics": ["graphics-design", "design", "graphic-design"],
    "customer-support": ["customer-service", "support-service", "cust-support"],
}


def _canonical_present(cid, selected_departments):
    """
    BUG 1 FIX: return True if a canonical dept `cid` is already represented in
    `selected_departments` under ANY of its known slugs -- the canonical id
    itself, its single CANONICAL_ID_ALIASES legacy key, OR any equivalent
    VARIANT slug in CANONICAL_VARIANT_SLUGS. Used only for the "already
    present?" membership test in reconcile_canonical_floor so a variant-slugged
    dept does not trigger a phantom canonical duplicate.
    """
    if cid in selected_departments:
        return True
    legacy_key = CANONICAL_ID_ALIASES.get(cid, cid)
    if legacy_key in selected_departments:
        return True
    for variant in CANONICAL_VARIANT_SLUGS.get(cid, []):
        if variant in selected_departments:
            return True
    return False

# Canonical IDs that have no separate alias (same key in both lists)
CANONICAL_DIRECT = [
    "marketing", "sales", "graphics", "video", "audio", "research",
    "crm", "legal",
]


def load_canonical_floor():
    """
    Read the 16 mandatory canonical departments from department-naming-map.json.

    Returns an ordered dict mapping canonical-id -> dept-info dict in the
    RECOMMENDED_DEPARTMENTS shape ({name, emoji, head, description}). Each
    canonical dept inherits its legacy metadata via CANONICAL_ID_ALIASES when
    a legacy entry exists; otherwise it is built from the naming-map one-liner.

    Falls back to a hardcoded list if the map file cannot be read so the floor
    is still enforced on a broken install.
    """
    map_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "department-naming-map.json",
    )
    mandatory = {}
    try:
        with open(map_path) as f:
            data = json.load(f)
        mandatory = data.get("mandatory", {})
    except (OSError, json.JSONDecodeError) as e:
        print(f"[CANONICAL] Could not read {map_path}: {e}. Using hardcoded floor.", file=sys.stderr)

    canonical_ids = list(mandatory.keys()) or [
        "marketing", "sales", "billing-finance", "customer-support",
        "web-development", "app-development", "graphics", "video", "audio",
        "research", "communications", "crm", "openclaw-maintenance", "legal",
        "social-media", "paid-advertisement",
    ]

    floor = {}
    for cid in canonical_ids:
        legacy_key = CANONICAL_ID_ALIASES.get(cid, cid)
        if legacy_key in RECOMMENDED_DEPARTMENTS:
            info = RECOMMENDED_DEPARTMENTS[legacy_key].copy()
        else:
            m = mandatory.get(cid, {})
            info = {
                "name": m.get("display_name", cid.replace("-", " ").title()),
                "emoji": m.get("emoji", "\U0001f4c1"),
                "head": m.get("director_title", f"Director of {cid.replace('-', ' ').title()}"),
                "description": m.get("one_liner", ""),
            }
        floor[cid] = info
    return floor


def _canonical_decline_set(build_state):
    """
    Return the set of canonical IDs the client EXPLICITLY declined.

    EXPLICIT-DECLINE MODEL (v10.15.26 / v10.16.25): the ONLY sanctioned way for a
    workforce to land below the 16 mandatory floor is a RECORDED explicit decline.
    Two equivalent recordings are honored (and kept in sync with the on-disk
    enforcer department-floor.py.declined_set()):
      1. build_state["canonicalReconciliation"]["decisions"][cid] == "no"
         (the per-dept yes/no map written at interview/reconcile time)
      2. build_state["declinedDepartments"] = [cid, ...]
         (a flat list the interview/config may set directly)
    Anything else (absent, "yes", null) means the canonical dept STAYS — there is
    no implicit/silent way to drop a mandatory department.
    """
    declined = set()
    bs = build_state or {}
    recon = bs.get("canonicalReconciliation", {})
    decisions = recon.get("decisions", {}) if isinstance(recon, dict) else {}
    if isinstance(decisions, dict):
        for cid, decision in decisions.items():
            if str(decision).strip().lower() == "no":
                declined.add(cid)
    for cid in (bs.get("declinedDepartments", []) or []):
        declined.add(str(cid).strip())
    return declined


def _build_state_path():
    """Resolve the build-state JSON path (VPS first, Mac fallback)."""
    candidates = [
        "/data/.openclaw/workspace/.workforce-build-state.json",
        os.path.join(HOME, ".openclaw", "workspace", ".workforce-build-state.json"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    # Default to the platform-appropriate path even if it does not exist yet
    if os.path.isdir("/data/.openclaw"):
        return "/data/.openclaw/workspace/.workforce-build-state.json"
    return os.path.join(HOME, ".openclaw", "workspace", ".workforce-build-state.json")


def _load_build_state():
    """Load the build-state JSON (or {} if absent/unreadable). Never raises."""
    path = _build_state_path()
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _write_canonical_reconciliation(record):
    """
    Write an auditable canonicalReconciliation block into build-state.

    Idempotent + non-destructive: merges into any existing build-state JSON,
    creating the file + parent dir if needed. The record documents exactly
    which canonical depts were auto-included (standard-unless-declined) so a
    later audit can prove no canonical dept was silently dropped.
    """
    path = _build_state_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        state = _load_build_state()
        existing = state.get("canonicalReconciliation", {})
        if not isinstance(existing, dict):
            existing = {}
        # Preserve any operator-set decisions; only refresh the audit fields.
        existing.setdefault("decisions", record.get("decisions", {}))
        existing["autoIncluded"] = record.get("autoIncluded", [])
        existing["clientCustoms"] = record.get("clientCustoms", [])
        existing["reconciledAt"] = datetime.now().isoformat()
        existing["floorSize"] = record.get("floorSize", 0)
        existing["source"] = record.get("source", "build-workforce.py")
        state["canonicalReconciliation"] = existing
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
        print(f"[CANONICAL] Wrote canonicalReconciliation to {path}", file=sys.stderr)
    except OSError as e:
        print(f"[CANONICAL WARNING] Could not write reconciliation to {path}: {e}", file=sys.stderr)


def reconcile_canonical_floor(selected_departments, core_answers, departments_config):
    """
    Enforce the canonical floor on the client's selected departments.

    Logic (standard-unless-declined):
      final = (16 canonical MINUS explicit "no" in build-state) UNION client customs

    - If a canonicalReconciliation.decisions block exists in build-state, honor
      each explicit "no" (drop that canonical dept) and keep everything else.
    - If NO reconciliation block exists, include all 16 canonical (standard) and
      write an auditable canonicalReconciliation.autoIncluded record.
    - Client-named canonical depts keep the client's real description (already in
      selected_departments); canonical depts the client did NOT name inherit the
      naming-map one-liner, contextualized with company industry/voice.
    - Client custom (non-canonical) departments are always preserved.
    - Idempotent: re-running never duplicates a folder and never overwrites a
      client-authored description with a generic one.

    Returns the reconciled selected_departments dict (mutated in place + returned).
    """
    floor = load_canonical_floor()
    build_state = _load_build_state()
    declined = _canonical_decline_set(build_state)
    had_reconciliation = isinstance(build_state.get("canonicalReconciliation"), dict) \
        and bool(build_state.get("canonicalReconciliation", {}).get("decisions"))

    industry = core_answers.get("industry", "") or ""
    company_name = core_answers.get("company_name", "") or ""

    auto_included = []
    for cid, info in floor.items():
        if cid in declined:
            print(f"[CANONICAL] Skipping '{cid}' -- client explicitly declined.", file=sys.stderr)
            continue
        if _canonical_present(cid, selected_departments):
            # BUG 1 FIX: client already has this canonical dept under its
            # canonical id, its legacy alias, OR a known variant slug
            # (e.g. legal-compliance, finance-ops, graphics-design). Keep their
            # real description untouched -- do NOT auto-add a phantom duplicate.
            continue
        # Not named by the client -> inherit the canonical one-liner,
        # contextualized with the client's industry so it is not bare boilerplate.
        dept_info = info.copy()
        base_desc = dept_info.get("description", "").strip()
        if industry:
            dept_info["description"] = f"{base_desc} (tailored for {company_name or 'this company'} in {industry})".strip()
        selected_departments[cid] = dept_info
        auto_included.append(cid)
        print(f"[CANONICAL] Auto-included canonical dept '{cid}' (standard-unless-declined).", file=sys.stderr)

    # Client customs = anything in selected_departments that is not a canonical id
    canonical_ids = set(floor.keys())
    canonical_legacy = {CANONICAL_ID_ALIASES.get(c, c) for c in canonical_ids}
    # BUG 1 FIX: variant slugs are canonical depts under a different name, not
    # client customs. Fold every known variant of every canonical id into the
    # canonical set so a variant-slugged dept is not double-counted as a custom.
    canonical_variants = set()
    for c in canonical_ids:
        for v in CANONICAL_VARIANT_SLUGS.get(c, []):
            canonical_variants.add(v)
    client_customs = [
        d for d in selected_departments
        if d not in canonical_ids
        and d not in canonical_legacy
        and d not in canonical_variants
    ]

    if not had_reconciliation:
        _write_canonical_reconciliation({
            "autoIncluded": auto_included,
            "clientCustoms": client_customs,
            "floorSize": len(canonical_ids),
            "decisions": {},
            "source": "build-workforce.py reconcile_canonical_floor (no prior reconciliation)",
        })
    else:
        # Refresh the audit fields even when honoring prior decisions.
        _write_canonical_reconciliation({
            "autoIncluded": auto_included,
            "clientCustoms": client_customs,
            "floorSize": len(canonical_ids),
            "decisions": build_state.get("canonicalReconciliation", {}).get("decisions", {}),
            "source": "build-workforce.py reconcile_canonical_floor (honoring prior decisions)",
        })

    print(f"[CANONICAL] Floor reconciled: {len(selected_departments)} departments "
          f"({len(auto_included)} auto-included, {len(client_customs)} client customs, "
          f"{len(declined)} declined).", file=sys.stderr)
    return selected_departments


def _load_vertical_packs():
    """
    Read the vertical_packs block from department-naming-map.json.

    Returns the dict {pack_id: {auto_add_keywords, auto_add_departments}} or {}
    if the map cannot be read. Same source of truth as load_canonical_floor()
    and build_dept_to_suggested_roles().
    """
    map_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "department-naming-map.json",
    )
    try:
        with open(map_path) as f:
            data = json.load(f)
        return data.get("vertical_packs", {}) or {}
    except (OSError, json.JSONDecodeError) as e:
        print(f"[VERTICAL] Could not read {map_path}: {e}. No vertical packs applied.", file=sys.stderr)
        return {}


def _detect_vertical_packs(core_answers, vertical_packs):
    """
    Match the client's industry/business context to vertical packs by keyword.

    Scans the concatenation of industry + company_description + biggest_challenge
    + tools (lowercased) for each pack's auto_add_keywords. A pack matches if ANY
    of its keywords appears as a whole word / phrase in the haystack.

    Returns an ordered list of (pack_id, matched_keywords) for every matched pack,
    preserving the naming-map declaration order so the result is deterministic
    and identical across clients with the same industry signal.
    """
    haystack = " ".join([
        str(core_answers.get("industry", "") or ""),
        str(core_answers.get("company_description", "") or ""),
        str(core_answers.get("biggest_challenge", "") or ""),
        str(core_answers.get("tools", "") or ""),
    ]).lower()
    matched = []
    for pack_id, pack in vertical_packs.items():
        if not isinstance(pack, dict):
            continue
        hits = []
        for kw in pack.get("auto_add_keywords", []) or []:
            k = str(kw).strip().lower()
            if not k:
                continue
            # Word-boundary match for single tokens; substring for multi-word
            # phrases (which are already specific enough not to false-match).
            if " " in k:
                if k in haystack:
                    hits.append(kw)
            else:
                if re.search(r"\b" + re.escape(k) + r"\b", haystack):
                    hits.append(kw)
        if hits:
            matched.append((pack_id, hits))
    return matched


def _write_vertical_pack_record(record):
    """
    Write an auditable verticalPacks block into build-state (idempotent merge).

    Documents which packs were detected, the keywords that triggered them, and
    every department added (with its base roles file + de-dup decisions) so a
    later audit can prove the industry add-ons were research-grounded and that
    no overlapping/conflicting department was introduced.
    """
    path = _build_state_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        state = _load_build_state()
        state["verticalPacks"] = {
            "detectedPacks": record.get("detectedPacks", []),
            "addedDepartments": record.get("addedDepartments", []),
            "skippedDuplicates": record.get("skippedDuplicates", []),
            "researchManifest": record.get("researchManifest", ""),
            "appliedAt": datetime.now().isoformat(),
            "source": "build-workforce.py apply_vertical_packs",
        }
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
        print(f"[VERTICAL] Wrote verticalPacks audit record to {path}", file=sys.stderr)
    except OSError as e:
        print(f"[VERTICAL WARNING] Could not write verticalPacks record to {path}: {e}", file=sys.stderr)


def _write_industry_org_design_manifest(matched_packs, added_departments, core_answers):
    """
    Write an industry-org-design research manifest the Research department's
    `industry-analysis-specialist-mckinsey-style` role consumes to GROUND the
    auto-added vertical departments in real org-design research (Porter / Mintzberg
    / McKinsey-style), not a blind static list.

    The build adds the base (canonical roles file) departments deterministically;
    this manifest is the research hook that lets the Research dept VALIDATE the
    add-on set against the client's real industry structure, propose any
    industry-specific role specializations, and flag any add-on that does not
    fit -- so the final department set is research-driven, not just keyword-driven.

    Returns the manifest path (or "" if it could not be written).
    """
    if not DEPARTMENTS_DIR:
        return ""
    manifest = {
        "schemaVersion": "1.0",
        "purpose": (
            "Industry org-design validation for the vertical-pack departments "
            "auto-added to this company. The Research dept's "
            "industry-analysis-specialist-mckinsey-style role MUST review this "
            "manifest, validate each added department against the real structure "
            "of the client's industry using consulting-grade frameworks (Porter's "
            "Five Forces, value-chain / profit-pool analysis, strategic group "
            "mapping, Mintzberg organizational configurations), and either confirm "
            "the department, recommend an industry-specific specialization of it, "
            "or flag it for removal. Cite every source with a URL + retrieval date. "
            "Never invent a department that overlaps the canonical 16 or another "
            "vertical-pack department."
        ),
        "company": {
            "name": core_answers.get("company_name", ""),
            "industry": core_answers.get("industry", ""),
            "description": core_answers.get("company_description", ""),
        },
        "researchRole": "research/industry-analysis-specialist-mckinsey-style",
        "detectedPacks": [
            {"pack": pid, "matchedKeywords": kws} for pid, kws in matched_packs
        ],
        "departmentsToValidate": [
            {
                "id": d["id"],
                "name": d["name"],
                "baseSuggestedRoles": d.get("_base_suggested_roles", ""),
                "validationQuestions": [
                    "Does this department reflect a real value-chain stage / profit pool in the client's industry?",
                    "Should any role inside it be specialized for this industry (name the role + the specialization)?",
                    "Does it overlap or conflict with any canonical-16 department or another added department? If so, recommend merge/drop.",
                ],
            }
            for d in added_departments
        ],
        "generatedAt": datetime.now().isoformat(),
    }
    manifest_path = os.path.join(DEPARTMENTS_DIR, "industry-org-design-research-manifest.json")
    try:
        os.makedirs(DEPARTMENTS_DIR, exist_ok=True)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"[VERTICAL] Wrote industry-org-design research manifest: {manifest_path}", file=sys.stderr)
        return manifest_path
    except OSError as e:
        print(f"[VERTICAL WARNING] Could not write org-design manifest: {e}", file=sys.stderr)
        return ""


def apply_vertical_packs(selected_departments, core_answers):
    """
    WS-4: auto-add industry vertical-pack departments to the workforce.

    Standard set (the 16 canonical floor) is already applied by
    reconcile_canonical_floor(). This sibling step adds the RESEARCH-DRIVEN
    industry add-ons:

      1. Detect which vertical packs match the client's industry/business
         context (via auto_add_keywords in department-naming-map.json).
      2. Add each matched pack's departments to selected_departments,
         DE-DUPED against (a) the canonical floor — under any canonical id,
         legacy alias, or variant slug — and (b) departments already added by
         an earlier-matched pack (so personal-pro-dev's `podcast` and
         content-creator's `podcast` never double-add), and (c) any client
         custom already present. No overlapping or conflicting department.
      3. Each added department inherits its base_suggested_roles file so it
         ships with real roles + SOPs (never hard-fails assert_dept_map_resolves).
      4. Write a McKinsey-style industry-org-design research manifest so the
         Research dept GROUNDS the add-on set in real org-design research, and
         an auditable verticalPacks record into build-state.

    Returns the mutated selected_departments dict.
    """
    vertical_packs = _load_vertical_packs()
    if not vertical_packs:
        return selected_departments

    matched_packs = _detect_vertical_packs(core_answers, vertical_packs)
    if not matched_packs:
        print("[VERTICAL] No vertical pack matched the client's industry signal — "
              "canonical floor only.", file=sys.stderr)
        return selected_departments

    # Build the canonical/alias/variant id set so a vertical dept can never
    # shadow a canonical-16 department (no overlap with the standard set).
    floor = load_canonical_floor()
    canonical_block = set(floor.keys())
    canonical_block |= {CANONICAL_ID_ALIASES.get(c, c) for c in floor.keys()}
    for c in floor.keys():
        canonical_block |= set(CANONICAL_VARIANT_SLUGS.get(c, []))

    added_departments = []
    skipped_duplicates = []
    seen_added = set()

    for pack_id, _hits in matched_packs:
        pack = vertical_packs.get(pack_id, {})
        for dept in pack.get("auto_add_departments", []) or []:
            if not isinstance(dept, dict):
                continue
            did = dept.get("id")
            if not did:
                continue
            # De-dup: against canonical floor, already-present (custom or prior
            # pack), and any dept already added in THIS pass.
            if did in canonical_block:
                skipped_duplicates.append({"id": did, "reason": f"overlaps canonical floor", "pack": pack_id})
                print(f"[VERTICAL] Skipping '{did}' from pack '{pack_id}' — overlaps canonical floor.", file=sys.stderr)
                continue
            if did in selected_departments or did in seen_added:
                skipped_duplicates.append({"id": did, "reason": "already present", "pack": pack_id})
                print(f"[VERTICAL] Skipping '{did}' from pack '{pack_id}' — already present.", file=sys.stderr)
                continue
            base = dept.get("base_suggested_roles", "")
            info = {
                "name": dept.get("name", did.replace("-", " ").title()),
                "emoji": dept.get("emoji", "\U0001f4c1"),
                "head": f"Director of {dept.get('name', did.replace('-', ' ').title())}",
                "description": dept.get("one_liner", ""),
                "vertical_pack": pack_id,
                "base_suggested_roles": base,
            }
            selected_departments[did] = info
            seen_added.add(did)
            added_departments.append({
                "id": did,
                "name": info["name"],
                "pack": pack_id,
                "_base_suggested_roles": base,
            })
            print(f"[VERTICAL] Added industry dept '{did}' (pack '{pack_id}', base roles '{base}').",
                  file=sys.stderr)

    manifest_path = ""
    if added_departments:
        manifest_path = _write_industry_org_design_manifest(matched_packs, added_departments, core_answers)

    _write_vertical_pack_record({
        "detectedPacks": [{"pack": pid, "matchedKeywords": kws} for pid, kws in matched_packs],
        "addedDepartments": added_departments,
        "skippedDuplicates": skipped_duplicates,
        "researchManifest": manifest_path,
    })

    print(f"[VERTICAL] Vertical packs applied: {len(matched_packs)} pack(s) matched, "
          f"{len(added_departments)} department(s) added, "
          f"{len(skipped_duplicates)} de-duped.", file=sys.stderr)
    return selected_departments



def build_from_config(config):
    """
    Build the full workforce from a non-interactive config JSON.

    This replaces the conversational interview flow with a direct build
    from the provided configuration. All department workspaces, specialists,
    and supporting files are created without any interactive prompts.
    """
    global MASTER_FILES, COMPANY_DISCOVERY_DIR

    # Detect environment
    MASTER_FILES = find_master_files_folder()
    COMPANY_DISCOVERY_DIR = os.path.join(MASTER_FILES, "company-discovery")

    company_name = config["company_name"]

    # v9.6.0: resolve the Zero Human Company folder for this client BEFORE
    # any dept workspace is created. This sets COMPANY_DIR / DEPARTMENTS_DIR
    # to ~/clawd/zero-human-company/<company-slug>/...
    resolve_company_paths(company_name)
    print(f"[ZHC] Company folder: {COMPANY_DIR}", file=sys.stderr)
    print(f"[ZHC] Departments folder: {DEPARTMENTS_DIR}", file=sys.stderr)

    industry = config.get("industry", "")
    company_description = config.get("company_description", "")
    tools = config.get("tools", "")
    biggest_challenge = config.get("biggest_challenge", "")

    # Build core interview answers dict (used by all department functions)
    core_answers = {
        "company_name": company_name,
        "industry": industry,
        "company_description": company_description,
        "tools": tools,
        "biggest_challenge": biggest_challenge,
    }

    print(f"[NON-INTERACTIVE] Building workforce for: {company_name}", file=sys.stderr)
    print(f"[NON-INTERACTIVE] Industry: {industry}", file=sys.stderr)

    # Save the config as the interview answers
    discovery_dir = _ensure_company_discovery_dir()
    if discovery_dir:
        answers_path = os.path.join(discovery_dir, "workforce-interview-answers.md")
        with open(answers_path, 'w') as f:
            f.write(f"# Workforce Interview Answers (Non-Interactive)\n\n")
            f.write(f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n---\n\n")
            f.write(f"**Q:** What is the name of your business?\n**A:** {company_name}\n\n---\n\n")
            f.write(f"**Q:** What industry are you in?\n**A:** {industry}\n\n---\n\n")
            if company_description:
                f.write(f"**Q:** What does your business do?\n**A:** {company_description}\n\n---\n\n")
            if tools:
                f.write(f"**Q:** What tools do you use?\n**A:** {tools}\n\n---\n\n")
            if biggest_challenge:
                f.write(f"**Q:** What is your biggest challenge?\n**A:** {biggest_challenge}\n\n---\n\n")

    # Process departments
    departments_config = config.get("departments", {})
    selected_departments = {}

    for dept_id, dept_config in departments_config.items():
        if dept_config.get("enabled", True):
            if dept_id in RECOMMENDED_DEPARTMENTS:
                selected_departments[dept_id] = RECOMMENDED_DEPARTMENTS[dept_id].copy()
            else:
                # Custom department
                selected_departments[dept_id] = {
                    "name": dept_config.get("name", dept_id.replace("-", " ").title()),
                    "emoji": dept_config.get("emoji", "\U0001f4c1"),
                    "head": dept_config.get("head", f"Chief {dept_id.replace('-', ' ').title()} Officer"),
                    "description": dept_config.get("activities", ""),
                }

    # v10.x - Enforce the canonical department floor (standard-unless-declined).
    # Builds all 16 canonical depts (minus any the client explicitly declined in
    # build-state) UNION the client's customs, then writes an auditable
    # canonicalReconciliation record. Canonical depts the client named keep their
    # real description; the rest inherit the naming-map one-liner with client
    # industry context. Idempotent.
    selected_departments = reconcile_canonical_floor(
        selected_departments, core_answers, departments_config
    )

    # WS-4: research-driven industry add-ons. After the standard floor, detect
    # the client's industry from the naming-map vertical_packs keywords and add
    # the matching industry departments — de-duped against the canonical 16 and
    # each other (no overlap), each inheriting a real base roles file, and
    # grounded by a McKinsey-style industry-org-design research manifest the
    # Research dept consumes. Runs BEFORE assert_dept_map_resolves so every
    # auto-added dept is proven to resolve to an existing roles file.
    selected_departments = apply_vertical_packs(selected_departments, core_answers)

    print(f"[NON-INTERACTIVE] Departments: {', '.join(selected_departments.keys())}", file=sys.stderr)

    # v10.15.18: HARD-FAIL the build if ANY selected department does not resolve
    # to an existing suggested-roles file. This makes the "zero-role department"
    # variance bug impossible — no department can silently ship with 0 roles/SOPs.
    assert_dept_map_resolves(list(selected_departments.keys()))

    # Create department workspaces
    specialists_by_dept = {}
    for dept_id, dept_info in selected_departments.items():
        dept_config = departments_config.get(dept_id, {})

        # Build per-department interview answers
        dept_answers = {
            **core_answers,
            "department_activities": dept_config.get("activities", dept_info["description"]),
            "department_kpis": dept_config.get("kpis", ""),
            "department_tools": dept_config.get("tools", tools),
            "department_challenges": dept_config.get("challenges", ""),
        }

        # Create workspace
        dept_dir = create_department_workspace(dept_id, dept_info, dept_answers)
        print(f"[NON-INTERACTIVE] Created workspace: {dept_dir}", file=sys.stderr)

        # Create role subfolders, 00-START-HERE.md, governing-personas.md, and SOP stubs
        role_folders = create_role_workspace(dept_id, dept_info, dept_answers)
        print(f"[NON-INTERACTIVE] Created {len(role_folders)} role folders in {dept_id}/", file=sys.stderr)

        # Log department answers
        if discovery_dir:
            with open(answers_path, 'a') as f:
                f.write(f"**Q:** Tell me about your {dept_info['name']} department.\n")
                f.write(f"**A:** Activities: {dept_config.get('activities', 'N/A')}\n")
                f.write(f"KPIs: {dept_config.get('kpis', 'N/A')}\n")
                f.write(f"Challenges: {dept_config.get('challenges', 'N/A')}\n\n---\n\n")

        # Determine specialists
        specialists, decision_ctx = determine_specialists(dept_id, dept_info, dept_answers)
        specialists_by_dept[dept_id] = specialists

    # WS-2: visible instantiated-from-library vs LLM-generated ratio. This is
    # the metric that proves the build is INSTANTIATING the pre-written library
    # (deterministic, identical across clients) rather than regenerating SOPs.
    _inst = _LIBRARY_FILL_STATS["instantiated_from_library"]
    _llm = _LIBRARY_FILL_STATS["llm_generated"]
    _tot = _inst + _llm
    _pct = (100 * _inst // _tot) if _tot else 0
    print(f"[ROLE-LIBRARY SUMMARY] Roles staffed: {_tot} | "
          f"instantiated-from-library: {_inst} ({_pct}%) | "
          f"LLM-generated (no template): {_llm} ({100 - _pct if _tot else 0}%)",
          file=sys.stderr)

    # Load persona categories and create governing personas
    persona_categories = load_persona_categories()
    for dept_id, dept_info in selected_departments.items():
        personas_md = create_governing_personas_md(dept_id, dept_info, persona_categories)
        personas_path = os.path.join(DEPARTMENTS_DIR, dept_id, "governing-personas.md")
        with open(personas_path, 'w') as f:
            f.write(personas_md)

    # Generate ORG-CHART.md (writes to the per-company ZHC folder, v9.6.0+)
    org_chart = generate_org_chart(selected_departments, specialists_by_dept)
    org_chart_path = os.path.join(COMPANY_DIR or WORKSPACE_ROOT, "ORG-CHART.md")
    with open(org_chart_path, 'w') as f:
        f.write(org_chart)
    print(f"[NON-INTERACTIVE] Created ORG-CHART.md at {org_chart_path}", file=sys.stderr)

    # Machine-readable director->specialist map (the wiring fix). Emit, per
    # department, a ROSTER.md (When-to Reference Map the director consults before
    # dispatch), then the company-wide universal-sops/00-ROUTING.md the CEO reads
    # first. These were documented but never generated until now.
    for dept_id, dept_info in selected_departments.items():
        write_department_roster(dept_id, dept_info)
    write_universal_routing_map(selected_departments)

    # Gap-3: collect every NO_TEMPLATE role (PENDING how-to.md) into a single
    # company-root manifest so the orchestrator knows exactly what to fill — a
    # missing template is never a silent empty stub.
    write_pending_sops_manifest(selected_departments)

    # v9.6.0: write the SOP research manifest so the AI agent can fan out
    # parallel sub-agents (one per department) to write real Lean Six Sigma
    # SOPs to replace the [Step X — to be personalized] placeholders.
    # The sub-agents are spawned BY the AI agent reading this manifest,
    # not by this script directly — keeps spawn under the agent's control
    # so it respects the v9.4.0 maxConcurrent / maxSpawnDepth gates and
    # the v9.5.2 timeout floors (1800s per heavy-reasoning sub-agent).
    manifest_path = write_sop_research_manifest(
        company_name=company_name,
        industry=industry,
        departments=selected_departments,
        interview_answers={dept_id: dept_config for dept_id, dept_config in config.get("departments", {}).items()},
    )
    if manifest_path:
        print(f"[NON-INTERACTIVE] SOP research manifest ready: {manifest_path}", file=sys.stderr)
        print(f"[NON-INTERACTIVE] AI agent: spawn up to 10 parallel sub-agents (heavy tier, 1800s timeout) per the manifest", file=sys.stderr)

        # v9.6.2: auto-invoke populate-sops-from-manifest.py so the SOP stubs
        # actually get filled in (instead of sitting as placeholder files).
        # Runs in the background (sub-agents are spawned in parallel internally),
        # exit code 0 = all populated, 2 = some failed, 3 = no model available.
        #
        # v10.15.4: Stream stdout/stderr live (do NOT capture_output) so the
        # operator sees progress in real time. Record the return code on
        # _BUILD_RESULT for the [BUILD-RESULT] line at the end of build.
        populate_script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "populate-sops-from-manifest.py")
        _sop_populate_rc = -1
        if os.path.isfile(populate_script):
            try:
                rc = subprocess.run(
                    ["python3", populate_script, "--manifest", manifest_path,
                     "--max-parallel", "10", "--timeout", "1800"],
                    timeout=3600 + 60,  # 60-min cap on the whole batch
                ).returncode
                _sop_populate_rc = rc
                if rc == 0:
                    print(f"[NON-INTERACTIVE] SOPs auto-populated successfully", file=sys.stderr)
                elif rc == 2:
                    print(f"[NON-INTERACTIVE] Some SOP sub-agents failed; rerun with: "
                          f"python3 {populate_script}", file=sys.stderr)
                elif rc == 3:
                    print(f"[NON-INTERACTIVE] Model selector returned owner-input-required; "
                          f"SOPs not populated. The AI agent must ask the owner which model "
                          f"to use, then rerun: python3 {populate_script}", file=sys.stderr)
                elif rc == 4:
                    # v10.15.18: inline-queue mode wrote work files but did NOT
                    # author the SOPs. This is NOT done. The library gate must
                    # stay failed and the resume cron must re-fire until the
                    # substance gate confirms real DMAIC SOPs on disk.
                    print(f"[NON-INTERACTIVE] SOP population ran in INLINE-QUEUE mode (no openclaw "
                          f"sub-agents available) — work files were written but NO SOPs are authored "
                          f"yet. sopLibraryStatus=authoring. The AI agent MUST execute each dept's "
                          f".sop-write-queue/ job, then re-run verify-library-gate.sh until it exits 0. "
                          f"Do NOT write buildCompletedAt while the SOP library is empty.", file=sys.stderr)
            except subprocess.TimeoutExpired:
                print(f"[NON-INTERACTIVE] SOP population timed out at 60 min; some SOPs may be "
                      f"partial. Rerun: python3 {populate_script}", file=sys.stderr)
                _sop_populate_rc = 124
            except Exception as e:
                print(f"[NON-INTERACTIVE] SOP population error: {e}; rerun manually with: "
                      f"python3 {populate_script}", file=sys.stderr)
                _sop_populate_rc = 1
        else:
            print(f"[NON-INTERACTIVE] populate-sops-from-manifest.py not found; "
                  f"SOPs remain as DMAIC stubs", file=sys.stderr)
            _sop_populate_rc = 127
        globals()["_BUILD_SOP_POPULATE_RC"] = _sop_populate_rc

    # v10.7.0: Write company-config.json (schema v2.0) to the ZHC folder.
    # Now includes mission, owner_values, company_kpis, dept_kpis so the
    # persona-selector Layers 1-4 have real data instead of falling back to
    # flat constants. Brand colors / mission / KPIs come from the
    # non-interactive config; departments-derived dept_kpis are aggregated.
    brand_colors = config.get("brand_colors", {}) if isinstance(config.get("brand_colors"), dict) else {}
    write_company_config_json(
        company_name,
        industry,
        brand_colors,
        full_config=config,
        selected_departments=selected_departments,
    )

    # Generate departments.json — v9.6.1 writes to BOTH the ZHC company folder
    # (canonical for Skill 32 to read) and the legacy company-discovery folder
    # (kept for backward compatibility during the v9.5 -> v9.6 transition).
    departments_json = generate_departments_json(selected_departments)
    if COMPANY_DIR:
        zhc_dept_json = os.path.join(COMPANY_DIR, "departments.json")
        with open(zhc_dept_json, 'w') as f:
            json.dump(departments_json, f, indent=2)
        print(f"[NON-INTERACTIVE] Wrote departments.json to ZHC folder: {zhc_dept_json}", file=sys.stderr)
        print(f"[NON-INTERACTIVE] EXACT department count: {len(departments_json)} (this is what the client chose)", file=sys.stderr)

    if discovery_dir:
        dept_json_path = os.path.join(discovery_dir, "departments.json")
        with open(dept_json_path, 'w') as f:
            json.dump(departments_json, f, indent=2)
        print(f"[NON-INTERACTIVE] Created legacy departments.json at {dept_json_path}", file=sys.stderr)

    # Copy departments.json to Command Center config directory (bridge path gap)
    copy_departments_to_command_center(departments_json)

    # Update openclaw.json config
    if os.path.isfile(OPENCLAW_CONFIG):
        try:
            backup_path = backup_config()
            print(f"[NON-INTERACTIVE] Config backed up to: {backup_path}", file=sys.stderr)

            config_data = load_openclaw_config()
            for dept_id, dept_info in selected_departments.items():
                add_agent_to_config(config_data, dept_id, dept_info)
            save_openclaw_config(config_data)
            print(f"[NON-INTERACTIVE] Config updated with {len(selected_departments)} department agents", file=sys.stderr)
        except Exception as e:
            print(f"[NON-INTERACTIVE WARNING] Config update failed: {e}", file=sys.stderr)
    else:
        print(f"[NON-INTERACTIVE WARNING] openclaw.json not found at {OPENCLAW_CONFIG} - skipping agent config",
              file=sys.stderr)

    # Save handoff as completed
    create_handoff(
        option=config.get("option", "A"),
        departments_done=list(selected_departments.keys()),
        departments_remaining=[],
        progress_pct=100
    )

    # Generate/update persona-matrix.md for workforce visibility
    generate_persona_matrix(selected_departments, persona_categories, company_name)


    # v10.5.1: Run v2.1 post-build augmentation — adds IDENTITY.md, SOUL.md,
    # MEMORY.md, HEARTBEAT.md, how-to.md (universal 18-section template), and
    # AGENTS/TOOLS/USER symlinks to every role folder created above. Master
    # Orchestrator (CEO) gets the CEO variant of the deferral clause. Idempotent.
    #
    # v10.15.4: Stream stdout/stderr live (no capture_output). Record return
    # code for the [BUILD-RESULT] line. On non-zero rc, chain into
    # qc-completeness.sh at the end so the operator sees the failure surface
    # AND the per-dept impact, not just a silent WARN line.
    import subprocess as _subprocess
    _post_build_rc = -1
    _script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "post-build-role-workspaces.py")
    if os.path.isfile(_script):
        try:
            _result = _subprocess.run(
                ["python3", _script, "--company-slug", COMPANY_SLUG or ""],
                timeout=300
            )
            _post_build_rc = _result.returncode
            if _result.returncode != 0:
                print(f"[v2.1 ERROR] post-build-role-workspaces.py exited {_result.returncode}", file=sys.stderr)
        except _subprocess.TimeoutExpired:
            print(f"[v2.1 ERROR] post-build-role-workspaces.py timed out after 300s", file=sys.stderr)
            _post_build_rc = 124
        except Exception as _e:
            print(f"[v2.1 ERROR] post-build augmentation failed: {_e}", file=sys.stderr)
            _post_build_rc = 1
    else:
        print(f"[v2.1 ERROR] post-build-role-workspaces.py not found at {_script}", file=sys.stderr)
        _post_build_rc = 127

    # v10.15.4: Emit a single, easy-to-grep BUILD-RESULT line summarising
    # the two post-build pipelines so silent failures are no longer possible.
    _sop_rc = globals().get("_BUILD_SOP_POPULATE_RC", -1)
    print(
        f"\n[BUILD-RESULT] post_build_role_workspaces_rc={_post_build_rc} "
        f"sop_populate_rc={_sop_rc}",
        file=sys.stderr,
    )

    print(f"\n[NON-INTERACTIVE] Build complete!", file=sys.stderr)
    print(f"[NON-INTERACTIVE] Company: {company_name}", file=sys.stderr)
    print(f"[NON-INTERACTIVE] Departments: {len(selected_departments)}", file=sys.stderr)
    print(f"[NON-INTERACTIVE] Workspace: {DEPARTMENTS_DIR}", file=sys.stderr)

    # v10.15.4: On ANY non-zero rc, invoke qc-completeness.sh so the operator
    # gets a per-dept breakdown (and a Telegram alert if != PASS). On zero rc
    # we still invoke qc-completeness.sh but in --quiet mode (PASS = no
    # Telegram, log-only). Idempotent and read-only.
    _qc_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qc-completeness.sh")
    if os.path.isfile(_qc_script):
        try:
            _qc_args = ["bash", _qc_script]
            if _post_build_rc == 0 and (_sop_rc in (0, -1)):
                _qc_args.append("--quiet")
            _subprocess.run(_qc_args, timeout=180)
        except Exception as _e:
            print(f"[v2.1 WARN] qc-completeness.sh invocation failed: {_e}", file=sys.stderr)
    else:
        print(f"[v2.1 WARN] qc-completeness.sh not present at {_qc_script}", file=sys.stderr)

    # v10.15.8: ENFORCED ROLE LIBRARY + SOP LIBRARY gate. Runs verify-library-gate.sh,
    # which measures coverage and writes roleLibraryStatus / sopLibraryStatus +
    # per-dept roleLibraryFilled / sopLibraryFilled into the build-state file. A
    # workforce is NOT complete until both are 'done'. The master orchestrator MUST
    # NOT write buildCompletedAt / closeoutStatus=pending while this gate fails (rc != 0);
    # the resume cron fires a [LIBRARY-RESUME] self-ping until it passes.
    _gate_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verify-library-gate.sh")
    if os.path.isfile(_gate_script):
        try:
            _gate_rc = _subprocess.run(["bash", _gate_script], timeout=240).returncode
            if _gate_rc == 0:
                print("[v10.15.8] LIBRARY GATE PASS — roleLibraryStatus=done AND sopLibraryStatus=done. "
                      "Workforce may proceed to closeout.", file=sys.stderr)
            else:
                print(f"[v10.15.8] LIBRARY GATE FAIL (rc={_gate_rc}) — role library and/or SOP library "
                      f"NOT populated. Do NOT write buildCompletedAt / closeoutStatus=pending. Re-run "
                      f"post-build-role-workspaces.py and/or populate-sops-from-manifest.py, then re-run "
                      f"verify-library-gate.sh until it exits 0. The resume cron will fire [LIBRARY-RESUME] "
                      f"until both libraries are done.", file=sys.stderr)
        except Exception as _e:
            print(f"[v10.15.8 WARN] verify-library-gate.sh invocation failed: {_e}", file=sys.stderr)
    else:
        print(f"[v10.15.8 WARN] verify-library-gate.sh not present at {_gate_script}", file=sys.stderr)


# ============================================================
# CONFIGURATION
# ============================================================

HOME = os.path.expanduser("~")
# VPS install detection: prefer ~/clawd if it exists, else $HOME/clawd
if os.path.isdir("~/clawd"):
    WORKSPACE_ROOT = "~/clawd"
else:
    WORKSPACE_ROOT = os.path.join(HOME, "clawd")

# Zero Human Company folder structure (v9.6.0+)
# Top-level: ~/clawd/zero-human-company/
# Per-company: ~/clawd/zero-human-company/<company-slug>/
# Departments live inside the per-company folder.
ZHC_ROOT = os.path.join(WORKSPACE_ROOT, "zero-human-company")

# DEPARTMENTS_DIR is resolved per-company at runtime once the company slug is known.
# Falls back to the pre-v9.6.0 path for legacy installs (auto-detected).
DEPARTMENTS_DIR = None       # Resolved by resolve_company_paths() below
COMPANY_DIR = None           # ~/clawd/zero-human-company/<slug>/
COMPANY_SLUG = None
LEGACY_DEPARTMENTS_DIR = os.path.join(WORKSPACE_ROOT, "departments")  # pre-v9.6.0 location

SUBAGENTS_DIR = os.path.join(WORKSPACE_ROOT, "subagents", "templates")
MASTER_FILES = None  # Detected at runtime
OPENCLAW_CONFIG = os.path.join(HOME, ".openclaw", "openclaw.json")
if os.path.isdir("~/.openclaw"):
    OPENCLAW_CONFIG = "~/.openclaw/openclaw.json"
BACKUP_DIR = os.path.join(HOME, "Downloads", "openclaw-backups")
COMPANY_DISCOVERY_DIR = None  # Set after master files detected; per-company file is now in COMPANY_DIR


def slugify_company_name(name: str) -> str:
    """Convert 'BlackCEO LLC' -> 'blackceo-llc'. Lowercase, hyphens, no special chars."""
    import re
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "unnamed-company"


def resolve_company_paths(company_name: str):
    """
    Set the global COMPANY_DIR / DEPARTMENTS_DIR / COMPANY_SLUG paths based on
    the client's company name. Creates the folders if missing.

    Discovery order at runtime (an agent looking for the workforce later):
      1. ~/clawd/zero-human-company/<slug>/         ← v9.6.0+ canonical
      2. ~/clawd/zhc/<slug>/                        ← short alias (legacy from very early v9.6 testing)
      3. ~/clawd/departments/                        ← pre-v9.6.0 (still readable for legacy installs)
    """
    global COMPANY_SLUG, COMPANY_DIR, DEPARTMENTS_DIR
    COMPANY_SLUG = slugify_company_name(company_name)

    # Canonical path
    canonical = os.path.join(ZHC_ROOT, COMPANY_SLUG)
    # Short-alias path (for installs that already have it)
    short_alias = os.path.join(WORKSPACE_ROOT, "zhc", COMPANY_SLUG)

    if os.path.isdir(short_alias) and not os.path.isdir(canonical):
        # Existing short-alias install — keep using it, don't fork
        COMPANY_DIR = short_alias
    else:
        COMPANY_DIR = canonical

    os.makedirs(COMPANY_DIR, exist_ok=True)
    DEPARTMENTS_DIR = os.path.join(COMPANY_DIR, "departments")
    os.makedirs(DEPARTMENTS_DIR, exist_ok=True)

    # If pre-v9.6.0 legacy departments folder exists with content, log a migration note
    if os.path.isdir(LEGACY_DEPARTMENTS_DIR) and os.listdir(LEGACY_DEPARTMENTS_DIR):
        print(f"[ZHC] Legacy ~/clawd/departments/ detected. Reading from it for backward compat.\n"
              f"[ZHC] New writes go to: {DEPARTMENTS_DIR}", file=sys.stderr)

    return COMPANY_DIR, DEPARTMENTS_DIR

# Files inherited from main CEO workspace
INHERITED_FILES = ["TOOLS.md", "AGENTS.md", "USER.md"]

# Files to check for existing context before asking questions
CONTEXT_FILES = ["USER.md", "MEMORY.md", "AGENTS.md", "TOOLS.md"]

# Canonical 17 departments — N17 binding. This list MUST match the dashboard's
# `config/departments.json` exactly. v10.13.0 sync: removed Operations / Creative
# / HR / IT (none of these are produced by the AI Workforce Interview anymore;
# they were pre-v10.7.0 leftovers). Added CRM, OpenClaw Maintenance, Social
# Media, Paid Advertisement (all 4 explicit interview outputs).
#
# Per N17, this dict is a SUGGESTION list during the interview — the client
# still chooses which subset they need. But no department OUTSIDE this list
# may be invented by the script. The interview output IS the source of truth
# for which subset is enabled in the dashboard.
RECOMMENDED_DEPARTMENTS = {
    "ceo": {"name": "CEO", "emoji": "👔", "head": "Chief Executive Officer", "description": "Executive strategy, vision, high-level decisions"},
    "marketing": {"name": "Marketing", "emoji": "📢", "head": "Chief Marketing Officer", "description": "Getting the word out about your business - social media, ads, email, content"},
    "sales": {"name": "Sales", "emoji": "💰", "head": "Chief Revenue Officer", "description": "Turning interested people into paying customers"},
    "billing": {"name": "Billing / Finance", "emoji": "💳", "head": "Chief Financial Officer", "description": "Invoices, payments, tracking your money"},
    "support": {"name": "Customer Support", "emoji": "🛟", "head": "Chief Support Officer", "description": "Helping your existing customers when they need it"},
    "webdev": {"name": "Web Development", "emoji": "🌐", "head": "Head of Web Development", "description": "Your website, landing pages, funnels"},
    "appdev": {"name": "App Development", "emoji": "🛠️", "head": "Head of App Development", "description": "Mobile apps, software applications"},
    "graphics": {"name": "Graphics", "emoji": "🖼️", "head": "Head of Graphics", "description": "Visual content - logos, images, brand assets"},
    "video": {"name": "Video Production", "emoji": "🎬", "head": "Head of Video Production", "description": "Video production, editing, AI video"},
    "audio": {"name": "Audio Production", "emoji": "🎵", "head": "Head of Audio Production", "description": "Podcasts, voiceovers, music, audio production"},
    "research": {"name": "Research", "emoji": "🔬", "head": "Head of Research", "description": "Market research, competitor analysis, data insights"},
    "comms": {"name": "Communications", "emoji": "📡", "head": "Head of Communications", "description": "PR, announcements, internal and external messaging"},
    "crm": {"name": "CRM", "emoji": "📇", "head": "Head of CRM", "description": "Customer data, lead lifecycle, pipeline hygiene (GHL-focused)"},
    "openclaw": {"name": "OpenClaw Maintenance", "emoji": "🦾", "head": "Head of OpenClaw Maintenance", "description": "Sunday updates, skill bumps, system QC, internal tooling"},
    "legal": {"name": "Legal / Compliance", "emoji": "⚖️", "head": "Chief Legal Officer", "description": "Contracts, regulations, keeping you protected"},
    "social": {"name": "Social Media", "emoji": "📱", "head": "Head of Social Media", "description": "Organic channels — LinkedIn, X, Instagram, TikTok, YouTube"},
    "paid-ads": {"name": "Paid Advertisement", "emoji": "🎯", "head": "Head of Paid Advertisement", "description": "Meta / Google / YouTube / TikTok paid acquisition — ROAS, CPA, retargeting"},
}

# N17 runtime guard — if config/departments.json is reachable from the workspace,
# verify our hardcoded list matches it. Drift between this dict and the dashboard
# config is the exact failure mode the Phase 13 audit catches.
def _verify_departments_against_dashboard_config() -> None:
    """Best-effort N17 drift check. Logs a warning if the keys diverge; never raises."""
    import json as _json
    candidate_paths = [
        os.path.expanduser("~/.openclaw/dashboard/config/departments.json"),
        "/data/.openclaw/dashboard/config/departments.json",
        os.path.expanduser("~/Documents/blackceo-command-center/config/departments.json"),
    ]
    for p in candidate_paths:
        if not os.path.exists(p):
            continue
        try:
            with open(p) as f:
                dashboard = _json.load(f)
            dashboard_ids = {d["id"].removeprefix("dept-") for d in dashboard if isinstance(d, dict) and "id" in d}
            script_ids = set(RECOMMENDED_DEPARTMENTS.keys())
            extra_in_script = script_ids - dashboard_ids
            missing_from_script = dashboard_ids - script_ids
            if extra_in_script or missing_from_script:
                print(f"[N17 WARN] build-workforce.py departments drift from {p}:", file=sys.stderr)
                if extra_in_script:
                    print(f"  Extra in script (not in dashboard): {sorted(extra_in_script)}", file=sys.stderr)
                if missing_from_script:
                    print(f"  Missing from script (in dashboard): {sorted(missing_from_script)}", file=sys.stderr)
            return
        except Exception:
            return  # Best-effort only — never block on a parsing issue

# Model assignments per department type
# Creative/content departments use Kimi (fast, good for writing)
# Technical departments use GPT 5.4 (strong at code and systems)
# Legal/operations use Sonnet (careful, precise reasoning)
DEFAULT_MODEL_ASSIGNMENTS = {
    "creative": "ollama/kimi-k2.6:cloud",
    "marketing": "ollama/kimi-k2.6:cloud",
    "graphics": "ollama/kimi-k2.6:cloud",
    "video": "ollama/kimi-k2.6:cloud",
    "audio": "ollama/kimi-k2.6:cloud",
    "research": "ollama/kimi-k2.6:cloud",
    "comms": "ollama/kimi-k2.6:cloud",
    "ceo": "ollama/kimi-k2.6:cloud",
    "sales": "openai-codex/gpt-5.4",
    "it": "openai-codex/gpt-5.4",
    "webdev": "openai-codex/gpt-5.4",
    "appdev": "openai-codex/gpt-5.4",
    "operations": "anthropic/claude-sonnet-4-6",
    "legal": "anthropic/claude-sonnet-4-6",
    "support": "ollama/kimi-k2.6:cloud",
    "billing": "ollama/kimi-k2.6:cloud",
    "hr": "ollama/kimi-k2.6:cloud",
}


# ============================================================
# RESEARCH FALLBACK (Phase 13 audit — P1)
# ============================================================
# When the interview encounters an unknown answer (industry-specific term,
# unfamiliar role title, missing dept-KPI baseline), the script can call
# OpenRouter's Perplexity Sonar model for a live web-grounded answer.
# Best-effort: if OPENROUTER_API_KEY is missing or the network is down, the
# function returns None and the caller falls back to its existing default
# (per N15 web-research pre-flight already lands authoritative defaults in
# preflight-research.json).

RESEARCH_MODEL = "openrouter/perplexity/sonar-pro-search"
RESEARCH_TIMEOUT_S = 12

def research_unknown_answer(question: str, context: str = "", purpose_tier: str = "light") -> str:
    """
    Best-effort web research via OpenRouter Perplexity Sonar.

    Args:
        question: the unknown answer the agent needs (e.g. "What's the typical
                  CPA for a Series-A SaaS company in healthtech?").
        context: 1-2 sentence framing the script already has.
        purpose_tier: "light" | "standard" | "heavy" — controls max_tokens.

    Returns:
        The model's response text, or None if research is unavailable.

    N1 compliance: Perplexity Sonar is hosted via OpenRouter, NOT Anthropic.
    N15 alignment: this is the runtime counterpart to web-research-preflight.sh
                   — preflight populates static defaults, this fills gaps.
    """
    import os as _os
    import json as _json

    api_key = _os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        # Try reading from secrets/.env via the existing convention
        for env_path in (
            _os.path.expanduser("~/.openclaw/secrets/.env"),
            "/data/.openclaw/secrets/.env",
        ):
            if _os.path.exists(env_path):
                try:
                    with open(env_path) as fh:
                        for line in fh:
                            if line.startswith("OPENROUTER_API_KEY="):
                                api_key = line.strip().split("=", 1)[1].strip('"\'')
                                break
                except Exception:
                    pass
                if api_key:
                    break
    if not api_key:
        # No key — return None so caller falls back to its built-in default.
        print(f"[research] OPENROUTER_API_KEY absent — skipping web research for: {question[:80]}",
              file=sys.stderr)
        return None

    max_tokens = {"light": 300, "standard": 700, "heavy": 1500}.get(purpose_tier, 300)
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=_json.dumps({
                "model": RESEARCH_MODEL.removeprefix("openrouter/"),
                "messages": [
                    {"role": "system", "content": "You are a research assistant. Cite sources when relevant. Be concise."},
                    {"role": "user", "content": (f"{context}\n\n" if context else "") + question},
                ],
                "max_tokens": max_tokens,
            }).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://openclaw.ai",
                "X-Title": "OpenClaw AI Workforce Interview",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=RESEARCH_TIMEOUT_S) as resp:
            body = _json.loads(resp.read().decode("utf-8"))
        choices = body.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            return msg.get("content", "").strip() or None
        return None
    except Exception as e:
        print(f"[research] failed for '{question[:60]}...': {type(e).__name__}: {e}",
              file=sys.stderr)
        return None


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def find_master_files_folder():
    """
    Find the master files folder in ~/Downloads/ (case-insensitive search).
    
    FALLBACK BEHAVIOR (hardened):
    - If ~/Downloads/ exists and a matching folder is found: use it (normal path)
    - If ~/Downloads/ exists but no matching folder: create ~/Downloads/openclaw-master-files/
    - If ~/Downloads/ does NOT exist (e.g., VPS, Docker, headless):
        use ~/.openclaw/workspace/data/ as the safe fallback location
    - ALWAYS print a warning to stderr when falling back so the agent knows.
    - NEVER returns None. A persistence path is always guaranteed.
    """
    downloads = os.path.join(HOME, "Downloads")
    
    # Primary search: ~/Downloads/
    if os.path.isdir(downloads):
        for name in os.listdir(downloads):
            lower = name.lower().replace(" ", "-").replace("_", "-")
            if "openclaw" in lower and ("master" in lower or "files" in lower or "documents" in lower):
                path = os.path.join(downloads, name)
                if os.path.isdir(path):
                    return path
        # ~/Downloads exists but no matching folder found - create default
        path = os.path.join(downloads, "openclaw-master-files")
        os.makedirs(path, exist_ok=True)
        return path
    
    # FALLBACK: ~/Downloads/ does not exist (VPS, Docker, headless environment)
    # Use ~/.openclaw/workspace/data/ as a safe data-side location that survives restarts
    # Use ~/.openclaw/workspace/data as fallback (or ~/clawd/ on VPS)
    workspace_root = os.environ.get("WORKSPACE_ROOT", os.path.join(HOME, ".openclaw", "workspace"))
    if not os.path.isdir(workspace_root):
        workspace_root = os.path.join(HOME, "clawd")  # Legacy fallback
    fallback = os.path.join(workspace_root, "data")
    os.makedirs(fallback, exist_ok=True)
    print(f"[PERSISTENCE WARNING] ~/Downloads/ not found. Using fallback persistence path: {fallback}",
          file=sys.stderr)
    print(f"[PERSISTENCE WARNING] Interview answers and handoff files will be saved to: {fallback}/company-discovery/",
          file=sys.stderr)
    return fallback


def backup_config():
    """Backup openclaw.json before any edits. Self-verifying."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%I%M%p")
    backup_name = f"openclaw-json-backup-{timestamp}.json"
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    shutil.copy2(OPENCLAW_CONFIG, backup_path)

    # Self-verify: check backup exists in the right place
    if not os.path.isfile(backup_path):
        raise RuntimeError(f"Backup failed: {backup_path} does not exist after copy")

    # Verify it's not in a hidden folder
    if "/." in backup_path:
        # Wrong location - re-backup to correct location
        correct_path = os.path.join(BACKUP_DIR, backup_name)
        shutil.copy2(OPENCLAW_CONFIG, correct_path)
        if os.path.isfile(correct_path):
            backup_path = correct_path

    return backup_path


def validate_json(filepath):
    """Validate that a JSON file is parseable."""
    with open(filepath, 'r') as f:
        json.load(f)
    return True


def load_openclaw_config():
    """Load openclaw.json."""
    with open(OPENCLAW_CONFIG, 'r') as f:
        return json.load(f)


def save_openclaw_config(config):
    """Save openclaw.json with validation."""
    with open(OPENCLAW_CONFIG, 'w') as f:
        json.dump(config, f, indent=2)
    validate_json(OPENCLAW_CONFIG)


def read_existing_context():
    """Read existing workspace files for context before asking questions."""
    context = {}
    for filename in CONTEXT_FILES:
        filepath = os.path.join(WORKSPACE_ROOT, filename)
        if os.path.isfile(filepath):
            with open(filepath, 'r') as f:
                context[filename] = f.read()
    return context


def read_previous_answers():
    """Read workforce-interview-answers.md if it exists (resume capability)."""
    if COMPANY_DISCOVERY_DIR:
        answers_file = os.path.join(COMPANY_DISCOVERY_DIR, "workforce-interview-answers.md")
        if os.path.isfile(answers_file):
            with open(answers_file, 'r') as f:
                return f.read()
    return None


def read_handoff():
    """Read interview-handoff.md if it exists (resume capability)."""
    if COMPANY_DISCOVERY_DIR:
        handoff_file = os.path.join(COMPANY_DISCOVERY_DIR, "interview-handoff.md")
        if os.path.isfile(handoff_file):
            with open(handoff_file, 'r') as f:
                return f.read()
    return None


def _ensure_company_discovery_dir():
    """
    Ensure COMPANY_DISCOVERY_DIR is set and the directory exists.
    If MASTER_FILES was not detected, force re-detection with fallback.
    Returns the path or None if truly impossible (should never happen after hardening).
    """
    global MASTER_FILES, COMPANY_DISCOVERY_DIR
    if not COMPANY_DISCOVERY_DIR:
        # Re-detect with fallback guarantee
        MASTER_FILES = find_master_files_folder()
        if MASTER_FILES:
            COMPANY_DISCOVERY_DIR = os.path.join(MASTER_FILES, "company-discovery")
    if not COMPANY_DISCOVERY_DIR:
        print("[PERSISTENCE ERROR] Cannot determine company-discovery path. "
              "Interview answers will NOT be saved this session.", file=sys.stderr)
        return None
    os.makedirs(COMPANY_DISCOVERY_DIR, exist_ok=True)
    return COMPANY_DISCOVERY_DIR


# ============================================================
# WORKSPACE CREATION
# ============================================================

def create_department_workspace(dept_id, dept_info, interview_answers):
    """
    Create a full department workspace with all core files.

    Creates:
    - SOUL.md (unique, generated from interview answers)
    - MEMORY.md (empty)
    - HEARTBEAT.md (department-specific priorities)
    - memory/ folder
    - TOOLS.md (inherited from main workspace)
    - AGENTS.md (inherited from main workspace)
    - USER.md (inherited from main workspace)
    - governing-personas.md (pre-qualified persona pool)
    - devils-advocate/SOUL.md (mission, tone, methodology)
    - devils-advocate/SOP.md (review process step-by-step)
    """
    dept_dir = os.path.join(DEPARTMENTS_DIR, dept_id)
    os.makedirs(dept_dir, exist_ok=True)
    os.makedirs(os.path.join(dept_dir, "memory"), exist_ok=True)
    os.makedirs(os.path.join(dept_dir, "devils-advocate"), exist_ok=True)

    # Create Devil's Advocate SOUL.md
    da_soul_path = os.path.join(dept_dir, "devils-advocate", "SOUL.md")
    if not os.path.isfile(da_soul_path):
        da_soul_content = generate_devils_advocate_soul_md(dept_id, dept_info, interview_answers)
        with open(da_soul_path, 'w') as f:
            f.write(da_soul_content)

    # Create Devil's Advocate SOP
    da_sop_path = os.path.join(dept_dir, "devils-advocate", "SOP.md")
    if not os.path.isfile(da_sop_path):
        da_sop_content = generate_devils_advocate_sop_md(dept_id, dept_info, interview_answers)
        with open(da_sop_path, 'w') as f:
            f.write(da_sop_content)

    # v9.6.1: SHARED files (AGENTS.md / TOOLS.md / USER.md) are SYMLINKED,
    # not copied. Every dept director, specialist, and sub-agent reads the
    # SAME master file at ~/clawd/. When any agent writes to its AGENTS.md,
    # TOOLS.md, or USER.md, the write lands in the universal file and ALL
    # other agents pick it up on next read.
    #
    # Reason: prior `shutil.copy2()` was creating per-dept duplicates that
    # diverged from the master over time, defeating the purpose of a shared
    # operating playbook (AGENTS.md), shared tool registry (TOOLS.md), and
    # shared owner profile (USER.md).
    for filename in INHERITED_FILES:
        src = os.path.join(WORKSPACE_ROOT, filename)
        dst = os.path.join(dept_dir, filename)
        if not os.path.isfile(src):
            continue
        # If a stale copy or wrong symlink exists, remove it before re-linking
        if os.path.lexists(dst):
            # Already a correct symlink pointing to the master? Skip.
            if os.path.islink(dst) and os.readlink(dst) == src:
                continue
            try:
                os.remove(dst)
            except OSError as e:
                print(f"[INHERITED-FILES WARN] Could not replace {dst}: {e}", file=sys.stderr)
                continue
        try:
            os.symlink(src, dst)
        except OSError as e:
            # Fallback to copy only if symlink unsupported (rare — Windows w/o admin)
            print(f"[INHERITED-FILES WARN] symlink failed for {filename}: {e}; falling back to copy",
                  file=sys.stderr)
            shutil.copy2(src, dst)

    # Create SOUL.md (generated from interview, not a template)
    soul_path = os.path.join(dept_dir, "SOUL.md")
    if not os.path.isfile(soul_path):
        soul_content = generate_soul_md(dept_id, dept_info, interview_answers)
        with open(soul_path, 'w') as f:
            f.write(soul_content)

    # v10.13.23 — Create IDENTITY.md for the dept head (Trevor's agent-file
    # architecture). Per the spec: every top-level agent gets its own
    # IDENTITY/SOUL/MEMORY/HEARTBEAT; the SHARED files (USER/AGENTS/TOOLS)
    # stay symlinked at the workspace root. Sub-agents (role folders inside
    # this dept) get their IDENTITY.md via post-build-role-workspaces.py.
    identity_path = os.path.join(dept_dir, "IDENTITY.md")
    if not os.path.isfile(identity_path):
        identity_content = generate_identity_md(dept_id, dept_info, interview_answers)
        with open(identity_path, 'w') as f:
            f.write(identity_content)

    # Create empty MEMORY.md
    memory_path = os.path.join(dept_dir, "MEMORY.md")
    if not os.path.isfile(memory_path):
        with open(memory_path, 'w') as f:
            f.write(f"# MEMORY.md - {dept_info['name']} Department\n\n> Long-term state, decisions, and metrics for this department.\n> Updated by the department head after each work session.\n")

    # Create HEARTBEAT.md with department-specific priorities
    heartbeat_path = os.path.join(dept_dir, "HEARTBEAT.md")
    if not os.path.isfile(heartbeat_path):
        heartbeat_content = generate_heartbeat_md(dept_id, dept_info, interview_answers)
        with open(heartbeat_path, 'w') as f:
            f.write(heartbeat_content)

    return dept_dir


# ============================================================
# READ-THE-SOP OPERATING PROTOCOL (canonical, embedded in every agent)
# ============================================================
# The wiring gap this closes: nothing previously told a director (or a spawned
# specialist sub-agent) to READ its role folder BEFORE working. The read-first
# rule lived only in the shared AGENTS.md + INSTRUCTIONS.md prose, so an agent
# that skipped AGENTS.md had no read-the-SOP directive in its OWN first-read
# files. These two constants are written verbatim into the director's
# IDENTITY.md/SOUL.md (generate_identity_md/generate_soul_md) AND into the
# master-orchestrator/CEO instructions, so the protocol is present in the files
# the agent reads first — not dependent on the shared AGENTS.md being installed.

DIRECTOR_OPERATING_PROTOCOL = """## Operating Protocol — Read the SOP Before You Work (binding)

Before executing ANY task, follow these steps IN ORDER. Do not skip a step.

1. **Pick the right specialist.** Consult this department's `ROSTER.md` (the
   When-to Reference Map for this department) to choose the specialist role
   whose when-to-use line matches the task. If no role matches, escalate to the
   CEO / Master Orchestrator rather than guessing.
2. **Spawn a sub-agent and have it FULLY ADOPT the role.** Spawn an OpenClaw
   sub-agent and instruct it to read the chosen role folder's files IN ORDER:
   `00-START-HERE.md` -> `IDENTITY.md` -> `SOUL.md` -> `how-to.md` (the SOPs)
   -> `governing-personas.md`. The sub-agent acts AS IF it IS that role for the
   duration of the task and executes per the how-to (its Section-9 SOPs / the
   matching `SOP/` file indexed by `SOP/00-INDEX.md`).
3. **No procedure, no guessing.** If the role folder has no SOP/how-to that
   covers the task, do NOT let the sub-agent proceed by guessing — fire the
   department SOP-Writer (INSTRUCTIONS.md Moment 3.7) to author the missing SOP
   first, or escalate.
4. **Review against the how-to before reporting.** When the sub-agent returns,
   review its output against the same how-to/SOP it was supposed to follow.
   Only then report results upward.
"""

CEO_OPERATING_PROTOCOL = """## Operating Protocol — Route, Then Read the SOP (binding)

Before executing or dispatching ANY task, follow these steps IN ORDER.

1. **Route to the right department.** Read `universal-sops/00-ROUTING.md` to map
   the task to the owning department, then that department's `ROSTER.md` to pick
   the specialist role.
2. **Delegate or spawn with full role adoption.** Hand the task to the
   department director, OR spawn a sub-agent directly and instruct it to read
   the chosen role folder IN ORDER: `00-START-HERE.md` -> `IDENTITY.md` ->
   `SOUL.md` -> `how-to.md` -> `governing-personas.md`, then execute per the
   how-to. The sub-agent acts AS IF it IS that role for the task.
3. **No procedure, no guessing.** If no SOP/how-to covers the task, author the
   missing SOP first (or direct the owning department's SOP-Writer to) — never
   let an agent proceed by guessing.
4. **Review against the how-to before reporting.** Verify each result against
   the SOP it was supposed to follow before reporting to the owner.
"""


def generate_identity_md(dept_id, dept_info, interview_answers):
    """
    Generate IDENTITY.md for the dept head agent.

    Trevor's agent-file architecture (v10.13.23): every top-level agent has
    its own IDENTITY/SOUL/MEMORY/HEARTBEAT. Sub-agents inherit. SHARED files
    (USER/AGENTS/TOOLS) live at the workspace root and are symlinked.

    Kept intentionally lightweight — the agent fills in its persona name and
    voice during the first conversation with the owner.
    """
    company_name = interview_answers.get('company_name', 'the company')
    dept_name = dept_info.get('name', dept_id)
    head_title = dept_info.get('head', f"{dept_name} Lead")

    return f"""# IDENTITY.md — {head_title}

**Department:** {dept_name}
**Company:** {company_name}
**Generated by:** build-workforce.py (Skill 23)

## Who I Am

- **Name:** (assign during first conversation — capture the persona/name the owner gives this agent)
- **Role:** {head_title}
- **Department:** {dept_name}
- **Reports to:** Master Orchestrator (CEO Agent)

## What This Role Owns

The {dept_name} department's performance and outputs. See SOUL.md for the
department mission, KPIs, and standards. See HEARTBEAT.md for the cadence.

## Operating Discipline

- I back up the local OpenClaw config before any change.
- I follow the Teach Yourself Protocol (TYP) for substantial new knowledge.
- I investigate root cause before fixing. I never claim done without verifying.
- I use the symlinked TOOLS.md to know what tools are available.
- I use the symlinked AGENTS.md to know how to behave and who to escalate to.
- I use the symlinked USER.md to know who I work for and how they communicate.

## Persona Governance

When the owner assigns me a persona, I adopt its voice and style while still
honoring the mission in SOUL.md and the values in USER.md. If a persona's
instructions conflict with company values, I surface the conflict before acting.

{DIRECTOR_OPERATING_PROTOCOL}
---

This file is unique to this agent. Sub-agents under this department inherit
from this IDENTITY but write their own role-specific IDENTITY.md.
""".replace("{DIRECTOR_OPERATING_PROTOCOL}", DIRECTOR_OPERATING_PROTOCOL)


def generate_soul_md(dept_id, dept_info, interview_answers):
    """
    Generate a SOUL.md specific to this department based on interview answers.
    This is NOT a generic template. It reflects what the client actually said.

    interview_answers is a dict with keys like:
    - 'company_name': str
    - 'industry': str
    - 'department_activities': str (what the client said this dept does)
    - 'department_kpis': str (what success looks like)
    - 'department_tools': str (what tools this dept uses)
    - 'department_challenges': str (what's not working)
    """
    company_name = interview_answers.get('company_name', 'the company')
    industry = interview_answers.get('industry', '')
    activities = interview_answers.get('department_activities', dept_info['description'])
    kpis = interview_answers.get('department_kpis', '')
    tools = interview_answers.get('department_tools', '')
    challenges = interview_answers.get('department_challenges', '')

    soul = f"""# SOUL.md - {dept_info['head']}

You are the {dept_info['head']} for {company_name}.

## Identity
- Title: {dept_info['head']}
- Department: {dept_info['name']}
- Company: {company_name}
- Industry: {industry}

## Role
You own the {dept_info['name'].lower()} department's performance. You receive tasks, delegate to specialists, monitor results, and report to the CEO.

## What This Department Does
{activities}
"""

    if kpis:
        soul += f"""
## What Success Looks Like
{kpis}
"""

    if tools:
        soul += f"""
## Tools This Department Uses
{tools}
"""

    if challenges:
        soul += f"""
## Current Challenges to Address
{challenges}
"""

    soul += """
## Responsibilities
1. Monitor department KPIs and metrics
2. Assign tasks to specialist team members (consult ROSTER.md to pick the role)
3. Confirm a procedure exists and review outputs against it before delivery
4. Generate weekly performance summaries
5. Escalate blockers to the CEO
6. Operate under the Act As If Protocol - select the right persona for each task

## Communication Style
Direct, data-driven, results-focused. Always cite specific numbers. Never vague.

"""
    soul += DIRECTOR_OPERATING_PROTOCOL
    return soul


def generate_heartbeat_md(dept_id, dept_info, interview_answers):
    """Generate department-specific HEARTBEAT.md."""
    return f"""# HEARTBEAT.md - {dept_info['name']} Department

## Current Priorities
- Department just created. Awaiting first tasks.
- Review SOUL.md to understand role and responsibilities.
- Review governing-personas.md for available coaching personas.

## Standing Checks
- Check department KPIs weekly
- Review specialist output quality
- Report status to CEO agent

## Notes
- This department was created on {datetime.now().strftime('%B %d, %Y')}
"""


def generate_devils_advocate_soul_md(dept_id, dept_info, interview_answers):
    """
    Generate a SOUL.md for the Devil's Advocate role within a department.
    The Devil's Advocate exists to stress-test ideas, find blind spots,
    and prevent groupthink - not to block progress, but to strengthen it.
    """
    company_name = interview_answers.get('company_name', 'the company')
    industry = interview_answers.get('industry', '')
    kpis = interview_answers.get('department_kpis', '')
    challenges = interview_answers.get('department_challenges', '')

    soul = f"""# SOUL.md - Devil's Advocate ({dept_info['name']} Department)

You are the Devil's Advocate for the {dept_info['name']} department at {company_name}.

## Mission
Your job is to make every decision stronger by finding what others missed.
You do NOT exist to say no. You exist to make sure the yes is earned.

## Identity
- Role: Devil's Advocate
- Department: {dept_info['name']}
- Company: {company_name}
- Industry: {industry}

## Tone
- Respectful but relentless. Challenge the idea, never the person.
- Curious, not cynical. Ask "what would make this fail?" not "this will fail."
- Specific, not vague. Point to the exact risk, not a general unease.
- Constructive. Every critique comes with a "here's what would fix it" option.
- Brief. State the risk, the evidence, and the fix. Move on.

## Methodology
1. **Assumption Test**: List every assumption the plan depends on. Flag any that are unproven.
2. **Failure Mode Analysis**: For each step, ask "what is the most likely way this breaks?"
3. **Second-Order Effects**: What happens AFTER the intended result? What ripple does it cause?
4. **Alternative View**: If you had to argue the opposite position, what is the strongest case?
5. **Worst Case**: What does the worst realistic scenario look like? Can the business survive it?
6. **Missing Voices**: Who is affected by this decision who is NOT in the room?
"""

    if kpis:
        soul += f"""\n## Department KPIs to Protect\n{kpis}\n"""

    if challenges:
        soul += f"""\n## Known Vulnerabilities (Start Here)\nThese are already-identified weak spots. Prioritize these in reviews:\n{challenges}\n"""

    soul += """\n## Hard Rules\n- Never approve something you have not challenged.\n- Never challenge without offering a path forward.\n- Never let a deadline override a real risk.\n- If you are the only voice of dissent, that is exactly when you must speak.\n- If you cannot find a real risk, say so explicitly: "I see no significant risk here."\n- Dissent is data. Silence is not safety.\n"""

    return soul


def generate_devils_advocate_sop_md(dept_id, dept_info, interview_answers):
    """
    Generate an SOP for the Devil's Advocate review process within a department.
    This is the step-by-step operating procedure for how DA reviews work.\n    """
    company_name = interview_answers.get('company_name', 'the company')

    sop = f"""# Devil's Advocate Review SOP - {dept_info['name']} Department

## When a Review Is Triggered\n\nA Devil's Advocate review is required before any of the following:\n1. Launching a new campaign, product, or service\n2. Making a financial commitment above the department's threshold\n3. Changing a process that affects customers\n4. Approving a strategy shift or pivot\n5. Publishing content that represents the company publicly\n\nA review is optional (but encouraged) for:\n- Routine operational tasks\n- Internal communications\n- Minor adjustments to existing processes\n\n## Review Process\n\n### Step 1: Receive the Proposal\nThe department head sends the proposal to the Devil's Advocate with context:\n- What is being proposed\n- Why it is being proposed\n- What success looks like\n- What the timeline is\n\n### Step 2: Assumption Mapping\nList every assumption the proposal depends on. For each:\n- Is it stated or unstated?\n- Is it proven or unproven?\n- What happens if it is wrong?\n\nFlag any unproven assumptions as risks.\n\n### Step 3: Failure Mode Identification\nFor each major component of the proposal, answer:\n- What is the most likely way this fails?\n- How would we detect that failure early?\n- What is the recovery plan if it fails?\n\n### Step 4: Second-Order Effects\nTrace the proposal's impact one step beyond the intended result:\n- What does success cause next?\n- Who or what else is affected?\n- Are there unintended consequences?\n\n### Step 5: Alternative View\nBuild the strongest case for the opposite decision.\nThis is not to reverse the decision, but to test whether the original\nreasoning holds up against a real challenge.\n\n### Step 6: Write the Review\nFormat the review as:\n\n**Proposal**: [brief summary]\n**Verdict**: PROCEED / PROCEED WITH CONDITIONS / DO NOT PROCEED\n**Top Risks**:\n1. [risk] - [severity: high/medium/low] - [mitigation]\n2. [risk] - [severity: high/medium/low] - [mitigation]\n3. [risk] - [severity: high/medium/low] - [mitigation]\n**Assumptions Flagged**: [count] unproven\n**Missing Voices**: [who is not in the room]\n**Conditions** (if any): [what must change or be added before proceeding]\n\n### Step 7: Department Head Decision\nThe department head reads the review and makes the final call.\nThe Devil's Advocate does not have veto power. The role is advisory.\n\nIf the department head overrides a "DO NOT PROCEED" or "PROCEED WITH CONDITIONS":\n- They must document their reasoning in writing\n- The override and reasoning are logged in the department's memory file\n\n## Escalation\n\nIf the Devil's Advocate identifies a risk that could affect the entire company\n(not just this department), escalate to the CEO agent immediately.\nDo not wait for the department head's decision cycle.\n\n## Cadence\n\n- **Active Review**: Triggered by any qualifying proposal (see above)\n- **Standing Review**: Weekly scan of department operations for emerging risks\n- **Deep Dive**: Monthly review of department KPIs and strategic direction\n\n## Log Format\n\nEach review is logged in the department's memory folder:\n- File: memory/da-reviews-YYYY-MM.md\n- Entry: date, proposal summary, verdict, top risks, override (if any)\n"""

    return sop


# ============================================================
# ROLE WORKSPACE CREATION (Phase: post-department, pre-specialist)
# ============================================================

# ============================================================
# DEPT -> SUGGESTED-ROLES FILE MAP (canonical, single-source-of-truth)
# ============================================================
# v10.15.18 BUG FIX (zero-role-department): the previous hardcoded map keyed
# on LEGACY ids (support/operations/creative/hr/it) that DO NOT match the
# canonical 16-dept folder ids (customer-support/crm/graphics/openclaw-
# maintenance/...), and several of its files (operations-/creative-/hr-people-/
# it-tech-suggested-roles.md) DO NOT EXIST in the repo. For any dept that
# resolved through a missing/mismatched entry, role parsing silently warned
# and produced ZERO roles -> ZERO SOPs for that whole department. That is one
# of the documented variance drivers (whole departments at ~0).
#
# THE FIX: derive the map from department-naming-map.json (the SAME source of
# truth load_canonical_floor() uses), so the canonical ids ALWAYS resolve to a
# real file. We also keep the legacy ids as aliases (for any client whose
# departments.json still stores a legacy slug). build_dept_to_suggested_roles()
# is the canonical builder; LEGACY_DEPT_ALIASES bridges old slugs.

# Legacy slug -> the suggested-roles filename it should resolve to. These are
# ONLY for backward compatibility with old departments.json files; canonical
# ids come from the naming map. (creative/operations/hr/it intentionally map to
# the closest real file so a stale slug never yields zero roles.)
LEGACY_DEPT_ALIASES = {
    "billing": "billing-suggested-roles.md",
    "support": "customer-support-suggested-roles.md",
    "webdev": "web-development-suggested-roles.md",
    "appdev": "app-development-suggested-roles.md",
    "comms": "communications-suggested-roles.md",
    "openclaw": "openclaw-maintenance-suggested-roles.md",
    "social": "social-media-suggested-roles.md",
    "paid-ads": "paid-advertisement-suggested-roles.md",
    "ceo": "master-orchestrator-suggested-roles.md",
    "master-orchestrator": "master-orchestrator-suggested-roles.md",
}


def build_dept_to_suggested_roles():
    """
    Build the canonical dept-id -> suggested-roles filename map from
    department-naming-map.json (mandatory + vertical_packs), then layer the
    legacy aliases on top. The naming map is the SINGLE SOURCE OF TRUTH so the
    map can never drift from the canonical 16-dept floor again.
    """
    map_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "department-naming-map.json",
    )
    result = {}
    try:
        with open(map_path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[DEPT-MAP] Could not read {map_path}: {e}. Using legacy aliases only.", file=sys.stderr)
        data = {}

    def _ingest(node):
        if not isinstance(node, dict):
            return
        for k, v in node.items():
            if isinstance(v, dict) and v.get("suggested_roles_file"):
                result[k] = v["suggested_roles_file"]
            elif isinstance(v, dict):
                _ingest(v)  # nested (vertical_packs)

    _ingest(data.get("mandatory", {}))
    _ingest(data.get("vertical_packs", {}))

    # WS-4: vertical-pack departments live as a LIST under each pack's
    # `auto_add_departments` (not as a {suggested_roles_file} dict), so the
    # recursive `_ingest` above does NOT reach them. Map each vertical-pack
    # dept id to its `base_suggested_roles` file (the closest canonical roles
    # file) so an auto-added industry department ALWAYS resolves in
    # assert_dept_map_resolves() and ships with real roles + SOPs. The Research
    # dept's industry-analysis-specialist-mckinsey-style role then refines the
    # base via the industry-org-design research manifest.
    for pack in (data.get("vertical_packs", {}) or {}).values():
        if not isinstance(pack, dict):
            continue
        for dept in pack.get("auto_add_departments", []) or []:
            if isinstance(dept, dict) and dept.get("id") and dept.get("base_suggested_roles"):
                result.setdefault(dept["id"], dept["base_suggested_roles"])
    # Master orchestrator / CEO is not in the naming map's department list but
    # is always built; ensure it resolves.
    result.setdefault("master-orchestrator", "master-orchestrator-suggested-roles.md")
    result.setdefault("ceo", "master-orchestrator-suggested-roles.md")
    # Layer legacy aliases LAST so they never overwrite a canonical id.
    for legacy, fname in LEGACY_DEPT_ALIASES.items():
        result.setdefault(legacy, fname)
    return result


# Mapping from department ID to suggested-roles filename (canonical-derived)
DEPT_TO_SUGGESTED_ROLES = build_dept_to_suggested_roles()


def assert_dept_map_resolves(dept_ids):
    """
    BUILD-TIME HARD ASSERTION (v10.15.18): every dept id we are about to build
    MUST resolve to a suggested-roles file that ACTUALLY EXISTS on disk.
    Previously a missing/mismatched entry produced a silent WARNING and a
    zero-role department. Now the build HARD-FAILS so the gap is impossible to
    ship. The resume cron re-fires and the operator sees the failure.

    Raises SystemExit(78) listing every unresolved dept. Returns the resolved
    {dept_id: abspath} map on success.
    """
    # Locate the suggested-roles directory (same search order as parse_suggested_roles)
    search_paths = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "suggested-roles"),
        os.path.join(WORKSPACE_ROOT, "23-ai-workforce-blueprint", "suggested-roles"),
    ]
    if MASTER_FILES:
        search_paths.insert(0, os.path.join(MASTER_FILES, "23-ai-workforce-blueprint", "suggested-roles"))
    roles_dir = next((sp for sp in search_paths if os.path.isdir(sp)), None)
    if not roles_dir:
        raise SystemExit(
            "[DEPT-MAP ASSERT] FATAL: no suggested-roles/ directory found in any of: "
            + "; ".join(search_paths)
        )

    resolved = {}
    unresolved = []
    for did in dept_ids:
        fname = DEPT_TO_SUGGESTED_ROLES.get(did)
        if not fname:
            # last-resort pattern + fuzzy match (mirrors parse_suggested_roles)
            cand = os.path.join(roles_dir, f"{did}-suggested-roles.md")
            if os.path.isfile(cand):
                resolved[did] = cand
                continue
            fuzzy = None
            for f in os.listdir(roles_dir):
                if did.replace("-", "") in f.replace("-", "").replace("_", ""):
                    fuzzy = os.path.join(roles_dir, f)
                    break
            if fuzzy:
                resolved[did] = fuzzy
                continue
            unresolved.append(f"{did} (no map entry, no {did}-suggested-roles.md, no fuzzy match)")
            continue
        path = os.path.join(roles_dir, fname)
        if not os.path.isfile(path):
            unresolved.append(f"{did} -> {fname} (FILE MISSING)")
        else:
            resolved[did] = path

    if unresolved:
        print("[DEPT-MAP ASSERT] FATAL: the following departments do NOT resolve to an "
              "existing suggested-roles file. The build is HARD-FAILING so no department "
              "ships with ZERO roles. Fix the map / add the file, then re-run:", file=sys.stderr)
        for u in unresolved:
            print(f"  - {u}", file=sys.stderr)
        raise SystemExit(78)
    print(f"[DEPT-MAP ASSERT] OK — all {len(resolved)} departments resolve to an existing "
          f"suggested-roles file in {roles_dir}", file=sys.stderr)
    return resolved


def parse_suggested_roles(dept_id):
    """
    Read and parse the suggested-roles markdown file for a department.
    Returns a list of role dicts with keys:
      - number: int (role number, 0 = department head)
      - name: str
      - description: str ("What it does")
      - sops: list of str (SOP filenames)
      - persona_traits: str
      - is_qc: bool (True if this is the QC Agent role)
    Returns empty list if no file found.
    """
    filename = DEPT_TO_SUGGESTED_ROLES.get(dept_id)
    if not filename:
        # Fallback: try pattern-based lookup
        filename = f"{dept_id}-suggested-roles.md"

    # Search for the file in suggested-roles folder
    suggested_roles_dir = None
    search_paths = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "suggested-roles"),
        os.path.join(WORKSPACE_ROOT, "23-ai-workforce-blueprint", "suggested-roles"),
    ]
    if MASTER_FILES:
        search_paths.insert(0, os.path.join(MASTER_FILES, "23-ai-workforce-blueprint", "suggested-roles"))

    for sp in search_paths:
        if os.path.isdir(sp):
            suggested_roles_dir = sp
            break

    if not suggested_roles_dir:
        print(f"[ROLE-WORKSPACE WARNING] No suggested-roles directory found for {dept_id}", file=sys.stderr)
        return []

    filepath = os.path.join(suggested_roles_dir, filename)
    if not os.path.isfile(filepath):
        # Try exact match by scanning directory
        for f in os.listdir(suggested_roles_dir):
            if dept_id.replace("-", "") in f.replace("-", "").replace("_", ""):
                filepath = os.path.join(suggested_roles_dir, f)
                break

    if not os.path.isfile(filepath):
        print(f"[ROLE-WORKSPACE WARNING] No suggested-roles file for dept '{dept_id}' (tried {filename})",
              file=sys.stderr)
        return []

    with open(filepath, 'r') as f:
        content = f.read()

    roles = []
    current_role = None

    for line in content.split('\n'):
        # Detect role headers: ### N. Role Name
        if line.startswith('### ') and not line.startswith('### Quality Control'):
            if current_role:
                roles.append(current_role)

            header = line[4:].strip()
            is_qc = 'quality control' in header.lower() or 'qc agent' in header.lower()

            # Parse number and name
            parts = header.split('. ', 1)
            try:
                number = int(parts[0])
                name = parts[1] if len(parts) > 1 else header
            except ValueError:
                number = len(roles)
                name = header

            current_role = {
                'number': number,
                'name': name.strip(),
                'description': '',
                'sops': [],
                'persona_traits': '',
                'is_qc': is_qc,
            }

        elif line.startswith('### Quality Control Agent'):
            # QC agent section - save current role if any, start QC role
            if current_role:
                roles.append(current_role)
            current_role = {
                'number': 99,
                'name': 'Quality Control Agent',
                'description': '',
                'sops': [],
                'persona_traits': '',
                'is_qc': True,
            }

        elif current_role:
            # Parse role content
            if line.startswith('**What it does:**'):
                current_role['description'] = line.replace('**What it does:**', '').strip()
            elif line.startswith('- ') and current_role['sops'] is not None:
                # Collect SOP items under "Core SOPs to build:"
                sop = line[2:].strip()
                if sop and sop.startswith('0'):
                    current_role['sops'].append(sop)
            elif line.startswith('**Persona Trait Suggestions:**'):
                current_role['persona_traits'] = line.replace('**Persona Trait Suggestions:**', '').strip()
            elif line.startswith('**Core SOPs to build:**'):
                # SOPs follow on subsequent lines starting with '- '
                pass  # collected above

    # Don't forget the last role
    if current_role:
        roles.append(current_role)

    return roles


def _instantiate_role_from_library(role_name, dept_id, interview_answers):
    """
    WS-2: PRIMARY-PATH library instantiation.

    Look up the pre-written role-library template for (role_name, dept_id) via
    the normalizer. If found, copy it and token-personalize it with this
    client's interview context ({{COMPANY_NAME}} / {{COMPANY_INDUSTRY}} /
    {{ASSIGNED_PERSONA}} / {{GENERATION_DATE}} and the rest). The returned
    string is the role's full how-to.md INCLUDING its pre-written Section 9
    SOPs — so no empty `[Step 1 ...]` stubs and no LLM regeneration are needed.

    Returns the personalized content string, or None when no template matches
    (genuinely missing role → caller keeps the legacy stub+LLM path).

    Deterministic: same template + same interview context → byte-identical
    output across clients (this is what makes Kofi == Lyric == everyone).
    """
    if not _LIBRARY_FILL_AVAILABLE:
        return None
    try:
        doc_path, role_entry = _crw_library_lookup(role_name, dept_id)
    except Exception as e:
        print(f"[ROLE-LIBRARY WARNING] lookup failed for '{role_name}' "
              f"({dept_id}): {e}", file=sys.stderr)
        return None
    if not doc_path:
        return None

    try:
        raw = Path(doc_path).read_text(encoding="utf-8")
    except Exception as e:
        print(f"[ROLE-LIBRARY WARNING] read failed for {doc_path}: {e}",
              file=sys.stderr)
        return None

    company_name = interview_answers.get("company_name", "")
    industry = interview_answers.get("industry", "")
    try:
        dept_lib = _crw_normalize_dept(dept_id)
    except Exception:
        dept_lib = dept_id
    dept_display = dept_lib.replace("-", " ").title()
    gen_date = datetime.now().strftime("%Y-%m-%d")

    # Direct, deterministic fill of the canonical PRD tokens first so we never
    # depend on company-config.json existing on disk yet at build time.
    out = raw
    primary_tokens = {
        "COMPANY_NAME": company_name,
        "COMPANY_INDUSTRY": industry,
        "INDUSTRY_VERTICAL": industry,
        "ROLE_TITLE": role_name,
        "DEPARTMENT_NAME": dept_display,
        "GENERATION_DATE": gen_date,
        "ISO_DATE": gen_date,
        # ASSIGNED_PERSONA is selected per-task at dispatch by persona-selector;
        # leave a neutral placeholder so the doc reads cleanly until then.
        "ASSIGNED_PERSONA": "(selected per task by persona-selector)",
    }
    for key, val in primary_tokens.items():
        if val:
            out = out.replace("{{" + key + "}}", str(val))

    # Backstop: run create_role_workspaces.fill_tokens for revenue cascade /
    # director title / any remaining tokens it can source from company-config.
    if _crw_fill_tokens is not None:
        try:
            is_ceo = (dept_lib == "master-orchestrator")
            out = _crw_fill_tokens(out, role_name, dept_display, is_ceo,
                                   role_entry=role_entry)
        except Exception as e:
            print(f"[ROLE-LIBRARY WARNING] token backstop failed: {e}",
                  file=sys.stderr)

    header = (f"<!-- WS-2: instantiated from role-library "
              f"v{role_entry.get('version', '?') if role_entry else '?'} "
              f"({role_entry.get('slug', '?') if role_entry else '?'}) on "
              f"{gen_date}. Pre-written Section-9 SOPs included — not "
              f"LLM-regenerated. -->\n")
    return header + out


def create_role_workspace(dept_id, dept_info, interview_answers):
    """
    Create role subfolders inside a department workspace.

    For each role in the suggested-roles file:
    1. Create a subfolder named after the role (slugified)
    2. Create 00-START-HERE.md with role description
    3. Create governing-personas.md with persona trait suggestions
    4. Create SOP stub files listed in the suggested-roles file

    Args:
        dept_id: Department identifier (e.g., 'marketing')
        dept_info: Department info dict (name, emoji, head, description)
        interview_answers: Interview answers dict (company_name, industry,
                          department_activities, department_kpis, etc.)

    Returns:
        List of created role folder paths
    """
    dept_dir = os.path.join(DEPARTMENTS_DIR, dept_id)
    if not os.path.isdir(dept_dir):
        print(f"[ROLE-WORKSPACE WARNING] Department directory does not exist: {dept_dir}", file=sys.stderr)
        return []

    # Parse the suggested-roles file
    roles = parse_suggested_roles(dept_id)
    if not roles:
        print(f"[ROLE-WORKSPACE] No roles found for {dept_id}, skipping role workspace creation."
              f" If roles are expected, check suggested-roles/{DEPT_TO_SUGGESTED_ROLES.get(dept_id, 'unknown')}",
              file=sys.stderr)
        return []

    company_name = interview_answers.get('company_name', 'the company')
    industry = interview_answers.get('industry', '')
    department_tools = interview_answers.get('department_tools', '')
    department_kpis = interview_answers.get('department_kpis', '')
    department_challenges = interview_answers.get('department_challenges', '')

    created_folders = []

    for role in roles:
        # Build slug folder name: '00-chief-marketing-officer' or '02-social-media-manager'
        role_slug = role['name'].lower()
        role_slug = role_slug.replace(' ', '-').replace('(', '').replace(')', '').replace('/', '-')
        role_slug = role_slug.replace('--', '-').strip('-')
        folder_name = f"{role['number']:02d}-{role_slug}"
        role_dir = os.path.join(dept_dir, folder_name)
        os.makedirs(role_dir, exist_ok=True)

        # ── WS-2: INSTANTIATE from the pre-written role-library (the fix) ──────
        # Before writing any empty `[Step 1 ...]` SOP stub, try to copy +
        # token-personalize the role's pre-written library template (which
        # already carries its full Section-9 SOPs). If it matches, write it as
        # how-to.md, mark the folder instantiated (so the SOP-research manifest
        # skips it and no LLM regeneration runs), and SKIP the stub loop below.
        # LLM generation is reserved for genuinely missing roles only.
        library_how_to = _instantiate_role_from_library(
            role['name'], dept_id, interview_answers)
        if library_how_to is not None:
            how_to_path = os.path.join(role_dir, "how-to.md")
            with open(how_to_path, 'w') as f:
                f.write(library_how_to)
            _LIBRARY_INSTANTIATED_ROLE_DIRS.add(os.path.abspath(role_dir))
            _LIBRARY_FILL_STATS["instantiated_from_library"] += 1
            print(f"[ROLE-LIBRARY] INSTANTIATED {folder_name} ({dept_id}) "
                  f"← role-library (SOPs included, no LLM regen)", file=sys.stderr)
        else:
            _LIBRARY_FILL_STATS["llm_generated"] += 1
            print(f"[ROLE-LIBRARY] NO TEMPLATE for {folder_name} ({dept_id}) "
                  f"— writing PENDING how-to.md stub (collected in PENDING-SOPS.md)",
                  file=sys.stderr)
            # Gap-3: NO_TEMPLATE roles must NOT leave a silent empty stub. Write a
            # how-to.md clearly headed PENDING, carrying the EXACT one-shot
            # instruction to populate it FROM the nearest role-library template
            # family (token-fill, NOT a free-form LLM essay). It is also collected
            # into the company-root PENDING-SOPS.md manifest so the orchestrator
            # knows what to fill — never silent.
            how_to_path = os.path.join(role_dir, "how-to.md")
            if not os.path.isfile(how_to_path):
                pending_how_to = f"""# {role['name']} — how-to.md  [PENDING — FILL FROM LIBRARY]

**Department:** {dept_info['name']} ({dept_info['emoji']})
**Company:** {company_name}
**Industry:** {industry}
**Status:** PENDING — no role-library template matched this role.

> ONE-SHOT FILL INSTRUCTION (do exactly this, do NOT write a free-form essay):
> 1. Look in `23-ai-workforce-blueprint/templates/role-library/{dept_id}/` for the
>    nearest template family (same department, closest role title). If this
>    department has no library docs, use the closest department's family.
> 2. Copy that template and TOKEN-FILL only the placeholders:
>    company = `{company_name}`, role = `{role['name']}`, department =
>    `{dept_info['name']}`, industry = `{industry}`.
> 3. Keep the template's Section-9 SOP structure intact. Reserve free-form
>    generation ONLY if there is genuinely no comparable template.
> 4. Once filled, remove this PENDING header and this role drops off PENDING-SOPS.md.

## What This Role Does
{role['description'] if role['description'] else '(see 00-START-HERE.md)'}

## SOPs (read-first)
The numbered `0N-*.md` files in this folder are step-by-step instruction sets.
Read the matching SOP BEFORE executing a task it covers. No improvising. If no
SOP covers the task, do not guess — escalate to the {dept_info['head']} so the
SOP-Writer can author one (INSTRUCTIONS.md Moment 3.7).
"""
                with open(how_to_path, 'w') as f:
                    f.write(pending_how_to)

        # 1. Create 00-START-HERE.md
        start_here_path = os.path.join(role_dir, "00-START-HERE.md")
        if not os.path.isfile(start_here_path):
            role_type = "QC Agent" if role['is_qc'] else "Specialist"
            if role['number'] == 0:
                role_type = "Department Head"

            content = f"""# {role['name']}

**Department:** {dept_info['name']} ({dept_info['emoji']})
**Company:** {company_name}
**Industry:** {industry}
**Role Type:** {role_type}

## What This Role Does
{role['description']}

## Department Context
"""
            if department_tools:
                content += f"**Department Tools:** {department_tools}\n"
            if department_kpis:
                content += f"**Department KPIs:** {department_kpis}\n"
            if department_challenges:
                content += f"**Current Challenges:** {department_challenges}\n"

            content += f"\n## SOPs (Standard Operating Procedures)\n"
            if role['sops']:
                content += "Each file below is a step-by-step instruction set. Follow them in order.\n\n"
                for sop in role['sops']:
                    content += f"- {sop}\n"
            else:
                content += "No SOPs defined yet. The department head will assign SOPs as tasks come in.\n"

            content += f"\n## Persona Trait Suggestions\n"
            if role['persona_traits']:
                content += f"{role['persona_traits']}\n"
            else:
                content += "No specific traits defined. Use the department's governing-personas.md as a reference.\n"

            content += f"\n---\n\n*Created: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}*\n"

            with open(start_here_path, 'w') as f:
                f.write(content)

        # 2. Create governing-personas.md for this role
        personas_path = os.path.join(role_dir, "governing-personas.md")
        if not os.path.isfile(personas_path):
            personas_content = f"""# Governing Personas - {role['name']}

**Department:** {dept_info['name']}
**Role:** {role['name']}
**Company:** {company_name}

## Persona Alignment
This role's persona selection is guided by the trait suggestions below.
At runtime, the AI selects the best persona PER TASK using 5-layer alignment.
The instruction is: 'Act as if you are [persona] executing this task.'

## Trait Suggestions for This Role
{role['persona_traits'] if role['persona_traits'] else 'Use department-level governing-personas.md as the primary reference.'}

## Department-Level Personas
See the parent department's `governing-personas.md` for the full pre-qualified persona pool.
This file adds role-specific filtering on top of the department pool.

---

*Created: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}*\n"""
            with open(personas_path, 'w') as f:
                f.write(personas_content)

        # 3. Create SOP stub files — ONLY for roles with no library template.
        # WS-2: when the role was instantiated from the library, its full
        # Section-9 SOPs already live inside how-to.md; writing empty
        # `[Step 1 ...]` stubs here would re-introduce the LLM-regeneration bug.
        role_was_instantiated = (
            os.path.abspath(role_dir) in _LIBRARY_INSTANTIATED_ROLE_DIRS)
        for sop_filename in ([] if role_was_instantiated else role['sops']):
            sop_path = os.path.join(role_dir, sop_filename)
            if not os.path.isfile(sop_path):
                sop_name = sop_filename.replace('.md', '').replace('-', ' ').title()
                sop_content = f"""# {sop_name}

**Role:** {role['name']}
**Department:** {dept_info['name']}
**Company:** {company_name}
**Industry:** {industry}
**Version:** 1.0 | {datetime.now().strftime('%B %d, %Y')}

## Purpose
This SOP provides step-by-step instructions for: {sop_name.lower()}.

## Who This Is For
The {role['name']} in the {dept_info['name']} department.

## Prerequisites
- Access to department tools: {department_tools if department_tools else 'See department TOOLS.md'}
- Understanding of department KPIs: {department_kpis if department_kpis else 'See department SOUL.md'}

## Step-by-Step Instructions

> **TODO:** This SOP needs to be populated with industry-specific best practices.
> The AI agent should research best practices using Perplexity and personalize
> these steps using the client's interview answers (tools, KPIs, challenges).
>
> **Interview context:**
> - Industry: {industry}
> - Department challenges: {department_challenges if department_challenges else 'Not specified'}
> - Department tools: {department_tools if department_tools else 'Not specified'}
> - Department KPIs: {department_kpis if department_kpis else 'Not specified'}

1. [Step 1 - to be personalized based on research]
2. [Step 2 - to be personalized based on research]
3. [Step 3 - to be personalized based on research]

## What to Do If Something Goes Wrong
- Check department SOUL.md for escalation procedures
- Report to the department head
- Log the issue in the department memory/ folder

## Escalation
If this task cannot be completed at the specialist level, escalate to the {dept_info['head']}.

---

*Created: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}*
*Status: STUB - Needs research + personalization*
"""
                with open(sop_path, 'w') as f:
                    f.write(sop_content)

        created_folders.append(role_dir)
        print(f"[ROLE-WORKSPACE] Created role: {folder_name} in {dept_id}/", file=sys.stderr)

    print(f"[ROLE-WORKSPACE] {len(created_folders)} roles created for {dept_id}", file=sys.stderr)
    return created_folders


# ============================================================
# LEAN SIX SIGMA SOP POPULATION (v9.6.0)
# ============================================================
# After all department + role workspaces are created, this phase replaces the
# `[Step 1 - to be personalized]` placeholders with REAL SOP content. It uses:
#   - Perplexity research for industry best practices (--purpose-tier heavy)
#   - The dept's SOUL.md (mission, values, KPIs from the interview)
#   - The role's persona blueprint (from Skill 22 if installed)
#   - Lean Six Sigma DMAIC structure (Define, Measure, Analyze, Improve, Control)
#
# Spawns 5-10 parallel sub-agents (one per department, capped at maxConcurrent=10
# per the v9.4.0 sub-agent config). The actual sub-agent spawn is performed by
# the AI agent running this build, not by this script — this script writes a
# manifest the agent reads and executes.

SOP_RESEARCH_MANIFEST_NAME = "sop-research-manifest.json"


def write_sop_research_manifest(company_name, industry, departments, interview_answers):
    """
    Write a manifest the AI agent reads to spawn parallel research + SOP-writing
    sub-agents. One sub-agent per department.

    Each manifest entry contains everything a sub-agent needs to write the real
    SOPs for one department: the role list, the SOP filenames, the dept's
    interview context, KPIs, persona traits, the company mission.

    Sub-agent prompt is also embedded so all sub-agents follow the same
    Lean Six Sigma DMAIC template and the "no guessing" rule.
    """
    if not COMPANY_DIR:
        print("[SOP-MANIFEST] COMPANY_DIR not resolved; skipping", file=sys.stderr)
        return None

    manifest_path = os.path.join(COMPANY_DIR, SOP_RESEARCH_MANIFEST_NAME)
    entries = []

    for dept_id, dept_info in departments.items():
        dept_dir = os.path.join(DEPARTMENTS_DIR, dept_id)
        if not os.path.isdir(dept_dir):
            continue

        # Collect every SOP stub that needs population
        sop_files = []
        for entry in os.listdir(dept_dir):
            role_dir = os.path.join(dept_dir, entry)
            if not os.path.isdir(role_dir) or entry == "memory" or entry == "devils-advocate":
                continue
            # WS-2: skip roles instantiated from the library — their Section-9
            # SOPs already live in how-to.md, so they must NOT be queued for
            # LLM regeneration. (They also have no `0N-...md` stub files, but
            # this guard makes the intent explicit and robust to re-runs.)
            if os.path.abspath(role_dir) in _LIBRARY_INSTANTIATED_ROLE_DIRS:
                continue
            for fname in os.listdir(role_dir):
                if fname.startswith(("01-", "02-", "03-", "04-", "05-", "06-", "07-", "08-", "09-")) and fname.endswith(".md"):
                    sop_files.append({
                        "role_folder": entry,
                        "sop_file": fname,
                        "role_dir": role_dir,
                    })

        dept_answers = interview_answers.get(dept_id, {}) if isinstance(interview_answers.get(dept_id), dict) else {}
        entry = {
            "dept_id": dept_id,
            "dept_name": dept_info.get("name", dept_id),
            "dept_head": dept_info.get("head", ""),
            "dept_dir": dept_dir,
            "company_name": company_name,
            "industry": industry,
            "department_activities": dept_answers.get("department_activities", ""),
            "department_kpis": dept_answers.get("department_kpis", ""),
            "department_tools": dept_answers.get("department_tools", ""),
            "department_challenges": dept_answers.get("department_challenges", ""),
            "sop_files": sop_files,
            "sub_agent_purpose_tier": "heavy",
            "sub_agent_timeout_seconds": 1800,
        }
        entries.append(entry)

    manifest = {
        "version": "1.0",
        "company": company_name,
        "company_slug": COMPANY_SLUG,
        "industry": industry,
        "generated_at": datetime.now().isoformat(),
        "max_parallel_sub_agents": 10,
        "departments": entries,
        "sub_agent_instructions": LEAN_SIX_SIGMA_SOP_PROMPT,
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"[SOP-MANIFEST] Wrote {manifest_path} with {len(entries)} departments queued for parallel SOP writing", file=sys.stderr)
    return manifest_path


# The sub-agent prompt template. The AI agent reads this from the manifest and
# uses it verbatim when spawning each per-department SOP-writing sub-agent.
LEAN_SIX_SIGMA_SOP_PROMPT = """
You are writing real, AI-facing SOPs for the {DEPT_NAME} department of {COMPANY_NAME} (industry: {INDUSTRY}).

You have ONE department's worth of SOP stub files to populate. Each stub currently has placeholder steps like '[Step 1 - to be personalized based on research]'. Your job is to REPLACE those placeholders with real, executable steps the AI agent will follow.

Use the Lean Six Sigma DMAIC structure for every SOP. Every SOP file must contain these sections:

  ## DEFINE
  - What this task is in one sentence
  - Required inputs (data, files, credentials, prior outputs)
  - Required outputs (the artifact this task produces)
  - Done criteria — MEASURABLE, not vague. e.g. 'Email scheduled, subject line A/B tested, segment confirmed'

  ## MEASURE
  - KPIs this task moves. Numbers, not adjectives.
  - How those KPIs map to the department KPIs: {DEPT_KPIS}
  - How department KPIs roll up to company KPIs.

  ## ANALYZE (when the task underperforms)
  - Root-cause checklist. Five Whys. Not symptom-chasing.
  - Common failure modes specific to this industry: research them via Perplexity.

  ## IMPROVE — Step-by-Step
  - Numbered concrete steps. Each step references a specific tool from: {DEPT_TOOLS}
  - Each step is something an AI agent can ACTUALLY do (read file X, call API Y, post to channel Z).
  - Embody the role's persona expertise. If the persona is John Maxwell for a leadership role, use Maxwell's principles verbatim where applicable.

  ## CONTROL
  - Devil's Advocate checkpoints. What the DA verifies before declaring done.
  - The DA must validate measurable criteria from DEFINE, not subjective taste.

  ## ESCALATION + RESEARCH RULE (binding — paste this section verbatim into every SOP)
  If you hit an edge case not covered above:
    - DO NOT GUESS. Guessing is forbidden for any AI employee.
    - You are either ABSOLUTELY SURE of the next step (proceed) or you are NOT SURE (research).
    - If not sure: run Perplexity research (`openrouter/perplexity/sonar-pro-search`) with a specific query, OR escalate to the {DEPT_HEAD}.
    - Document the edge case AND the research outcome in {DEPT_DIR}/memory/[YYYY-MM-DD].md.

Hard constraints:
  - NEVER reference Anthropic models. Use the selector chain heavy tier when invoking models.
  - Plain English. No corporate jargon.
  - Tools referenced must be from {DEPT_TOOLS}. If a useful tool is missing from that list, recommend it under a 'Suggested tool additions' section at the bottom — don't pretend it's available.
  - Cite Perplexity research findings inline when a step is derived from research. e.g. 'Per industry benchmark (Perplexity 2026-05-13): companies in {INDUSTRY} typically...'

For each role folder in this department, you'll find:
  - 00-START-HERE.md (DO NOT rewrite — already contains role context)
  - governing-personas.md (DO NOT rewrite — already lists persona traits)
  - 01-, 02-, 03-, etc. SOP files (THESE are what you populate)
  - tools.md, good-examples.md, bad-examples.md (write these if missing)

When you write an SOP, keep the file's existing top metadata (Role, Department, Company, Industry, Version, Date). Replace ONLY the body sections (Purpose, Who This Is For, Prerequisites, Step-by-Step, What to Do If Something Goes Wrong, Escalation) with the DMAIC-structured content above.

Output: rewrite each SOP file in place. Report back with a list of files written, line count per file, and any edge cases you flagged for owner attention.
"""


# ============================================================
# SPECIALIST DETERMINATION (Silent - no client questions)
# ============================================================

def determine_specialists(dept_id, dept_info, interview_answers):
    activities = interview_answers.get('department_activities', '')
    activities_lower = activities.lower()
    PERMANENT_SIGNALS = [
        'daily', 'weekly', 'every day', 'every week', 'regular',
        'recurring', 'ongoing', 'continuous', 'always', 'consistently',
        'schedule', 'routine', 'maintain', 'manage', 'track', 'monitor',
        'relationship', 'client', 'customer', 'follow up', 'follow-up',
        'campaign', 'pipeline', 'inbox', 'respond', 'report',
    ]
    ONCALL_SIGNALS = [
        'occasionally', 'sometimes', 'once', 'one-time', 'one time',
        'quarterly', 'annually', 'yearly', 'as needed', 'when needed',
        'project-based', 'project based', 'single', 'audit', 'review',
    ]
    permanent_score = sum(1 for signal in PERMANENT_SIGNALS if signal in activities_lower)
    oncall_score = sum(1 for signal in ONCALL_SIGNALS if signal in activities_lower)

    specialists = []
    suggested_roles_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'suggested-roles',
        f'{dept_id}-suggested-roles.md'
    )
    if os.path.isfile(suggested_roles_path):
        with open(suggested_roles_path, 'r') as f:
            content = f.read()
        import re
        role_blocks = re.split(r'###\s+\d+\.\s+', content)
        for block in role_blocks[1:]:
            lines = block.strip().split('\n')
            if not lines:
                continue
            role_name = lines[0].strip()
            role_slug = role_name.lower().replace(' ', '-').replace('/', '-')
            role_type = 'permanent' if permanent_score >= oncall_score else 'on-call'
            block_lower = block.lower()
            if any(s in block_lower for s in ['daily', 'weekly', 'ongoing', 'manages', 'monitors']):
                role_type = 'permanent'
            elif any(s in block_lower for s in ['occasionally', 'one-time', 'as needed', 'quarterly']):
                role_type = 'on-call'
            specialists.append({
                'id': role_slug,
                'name': role_name,
                'type': role_type,
                # Route specialists through the SAME model selector the department
                # director uses (resolves to kimi-k2.6+/deepseek), floored at the
                # fleet-standard default. Never the deprecated moonshot/kimi-k2.5 —
                # that hardcode caused fleet-wide "Unknown model" on routed dept-agent
                # calls (directors were already fixed; specialists were missed).
                'model': _resolve_director_model(dept_id) or 'ollama/kimi-k2.6:cloud',
                'reason': f'From suggested roles for {dept_id}, type={role_type} based on activity signals'
            })
    else:
        print(f"[WARNING] No suggested-roles file for {dept_id} at {suggested_roles_path}", file=sys.stderr)

    decision_context = {
        'department': dept_id,
        'permanent_signals_found': permanent_score,
        'oncall_signals_found': oncall_score,
        'activities_text': activities,
        'specialists_count': len(specialists),
        'suggested_roles_file': suggested_roles_path if os.path.isfile(suggested_roles_path) else 'NOT FOUND',
    }
    return specialists, decision_context


# ============================================================
# PERSONA ALIGNMENT (Act As If Protocol)
# ============================================================

def load_persona_categories():
    """Load persona-categories.json for tag-based filtering."""
    # Check multiple possible locations
    paths = [
        os.path.join(HOME, "Downloads", "openclaw-master-files", "coaching-personas", "persona-categories.json"),
    ]
    if MASTER_FILES:
        paths.insert(0, os.path.join(MASTER_FILES, "coaching-personas", "persona-categories.json"))

    for path in paths:
        if os.path.isfile(path):
            with open(path, 'r') as f:
                return json.load(f)
    return None


def get_personas_for_category(categories_data, domain_tag):
    """Get all personas tagged with a specific domain."""
    if not categories_data or "personas" not in categories_data:
        return []
    matches = []
    for persona_id, data in categories_data["personas"].items():
        if domain_tag in data.get("domain", []):
            matches.append({
                "id": persona_id,
                "author": data.get("author", ""),
                "book": data.get("book", ""),
                "domain": data.get("domain", []),
                "perspective": data.get("perspective", []),
            })
    return matches


def create_governing_personas_md(dept_id, dept_info, categories_data):
    """
    Create governing-personas.md for a department.
    Lists the pre-qualified persona pool (passed Layers 1-2 at setup).
    Layers 3-5 run fresh per task at runtime.
    """
    # Map department IDs to relevant domain tags
    dept_to_domains = {
        "marketing": ["marketing", "copywriting", "communication"],
        "sales": ["sales", "communication", "strategy-innovation"],
        "billing": ["finance", "operations"],
        "support": ["communication", "coaching"],
        "operations": ["operations", "productivity-systems", "leadership"],
        "creative": ["copywriting", "marketing", "communication"],
        "hr": ["leadership", "coaching", "communication"],
        "legal": ["communication", "strategy-innovation"],
        "it": ["productivity-systems", "strategy-innovation", "operations"],
        "webdev": ["strategy-innovation", "marketing", "productivity-systems"],
        "appdev": ["strategy-innovation", "productivity-systems"],
        "graphics": ["marketing", "communication"],
        "video": ["marketing", "communication"],
        "audio": ["marketing", "communication"],
        "research": ["strategy-innovation", "operations"],
        "comms": ["communication", "leadership", "marketing"],
        "ceo": ["leadership", "strategy-innovation", "coaching", "mindset"],
    }

    domains = dept_to_domains.get(dept_id, ["leadership"])
    all_matches = []
    seen = set()

    if categories_data:
        for domain in domains:
            for persona in get_personas_for_category(categories_data, domain):
                if persona["id"] not in seen:
                    all_matches.append(persona)
                    seen.add(persona["id"])

    content = f"# Governing Personas - {dept_info['name']} Department\n\n"
    content += "These personas have been pre-qualified for this department (passed company mission and owner alignment).\n"
    content += "At runtime, the AI selects the best persona PER TASK using 5-layer alignment.\n"
    content += "The instruction is: 'Act as if you are [persona] executing this task.'\n\n"

    if all_matches:
        content += "## Available Personas\n\n"
        for p in all_matches:
            domains_str = ", ".join(p["domain"])
            perspective_str = ", ".join(p["perspective"]) if p["perspective"] else "general"
            content += f"- **{p['author']}** ({p['book']}) - domains: {domains_str} | perspective: {perspective_str}\n"
    else:
        content += "## No Personas Available\n\n"
        content += "Install Skill 22 (Book-to-Persona Coaching Leadership System) to add coaching personas.\n"
        content += "Then re-run this skill in Option C (audit mode) to wire personas in.\n"

    return content


# ============================================================
# ORG CHART GENERATION
# ============================================================

def generate_org_chart(departments, specialists_by_dept):
    """Generate ORG-CHART.md showing the full company structure."""
    content = "# Company Org Chart\n\n"
    content += f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n"
    content += "## CEO / Master Orchestrator (main agent)\n\n"

    for dept_id, dept_info in departments.items():
        content += f"### {dept_info['emoji']} {dept_info['name']} - {dept_info['head']}\n"
        specialists = specialists_by_dept.get(dept_id, [])
        if specialists:
            for spec in specialists:
                type_label = "full-time" if spec.get("type") == "permanent" else "on-call"
                content += f"  - {spec['name']} ({type_label})\n"
        else:
            content += "  - (specialists to be determined based on workload)\n"
        content += "\n"

    return content


# ============================================================
# MACHINE-READABLE DIRECTOR -> SPECIALIST MAP (ROSTER + ROUTING)
# ============================================================
# The wiring gap this closes: determine_specialists() output previously flowed
# ONLY to the org chart, and the per-department When-to Reference Map +
# universal-sops/00-ROUTING.md were documented (INSTALL.md/ai-workforce-blueprint-
# full.md) but NEVER generated by the build. A director therefore had no
# build-emitted, machine-readable list of which specialist owns which kind of
# work — the director->specialist dispatch lived only in runtime LLM reasoning.
# These generators emit, at build time:
#   - <dept>/ROSTER.md            (one row per role folder + a when-to-use line;
#                                  the director's OPERATING PROTOCOL references it)
#   - universal-sops/00-ROUTING.md (company-wide task-type -> department map)
# They are derived from the SAME parse_suggested_roles() the folder builder uses,
# so the roster role slugs always match the on-disk NN-role-slug/ folders.


def _role_folder_slug(role):
    """Reproduce the NN-role-slug/ folder name create_role_workspace() writes."""
    role_slug = role['name'].lower()
    role_slug = role_slug.replace(' ', '-').replace('(', '').replace(')', '').replace('/', '-')
    role_slug = role_slug.replace('--', '-').strip('-')
    return f"{role.get('number', 0):02d}-{role_slug}"


def _when_to_use_line(role):
    """One-line when-to-use trigger for a role, derived from its description.

    Falls back to the role name so the cell is never empty. Kept to a single
    line (first sentence / first 160 chars) so ROSTER.md stays scannable.
    """
    desc = (role.get('description') or '').strip()
    if not desc:
        return f"Tasks owned by the {role['name']}."
    # First sentence, capped, single line.
    first = desc.replace('\n', ' ').split('. ')[0].strip()
    if len(first) > 160:
        first = first[:157].rstrip() + '...'
    if not first.endswith('.'):
        first += '.'
    return first


def write_department_roster(dept_id, dept_info):
    """Write <dept>/ROSTER.md — the machine-readable When-to Reference Map the
    director consults (per its OPERATING PROTOCOL) before dispatching a task.

    Lists every specialist role folder in this department with a one-line
    when-to-use and the exact read-in-order path the spawned sub-agent follows.
    Returns the absolute path written, or None if the dept folder is missing.
    """
    if not DEPARTMENTS_DIR:
        return None
    dept_dir = os.path.join(DEPARTMENTS_DIR, dept_id)
    if not os.path.isdir(dept_dir):
        print(f"[ROSTER] dept dir missing for {dept_id}; skipping", file=sys.stderr)
        return None

    roles = parse_suggested_roles(dept_id)
    lines = [
        f"# ROSTER — {dept_info['name']} ({dept_info.get('emoji', '')})",
        "",
        f"**Department head:** {dept_info.get('head', dept_id)}",
        "**This is the When-to Reference Map for this department.** Before you "
        "dispatch ANY task, find the row whose *When to use* matches the task, "
        "then spawn a sub-agent and have it read that role folder IN ORDER: "
        "`00-START-HERE.md` -> `IDENTITY.md` -> `SOUL.md` -> `how-to.md` -> "
        "`governing-personas.md`, then execute per the how-to. If no row matches, "
        "escalate to the CEO — do not guess.",
        "",
        "| Role | Role folder | Type | When to use |",
        "| --- | --- | --- | --- |",
    ]
    if roles:
        for role in roles:
            folder = _role_folder_slug(role)
            rtype = "QC" if role.get('is_qc') else ("Head" if role.get('number') == 0 else "Specialist")
            lines.append(
                f"| {role['name']} | `{folder}/` | {rtype} | {_when_to_use_line(role)} |"
            )
    else:
        lines.append("| _(no roles resolved — investigate dept->menu mapping)_ |  |  |  |")

    lines += [
        "",
        "## How the director dispatches",
        "1. Match the task to a row above (When to use).",
        "2. Spawn a sub-agent; instruct it to read that role folder in order and "
        "act AS IF it IS that role.",
        "3. If the role's `how-to.md` / `SOP/` does not cover the task, fire the "
        "department SOP-Writer (INSTRUCTIONS.md Moment 3.7) before proceeding — "
        "never guess.",
        "4. Review the sub-agent's output against the same how-to before reporting.",
        "",
        f"*Generated by build-workforce.py (Skill 23) on "
        f"{datetime.now().strftime('%B %d, %Y at %I:%M %p')}.*",
        "",
    ]
    roster_path = os.path.join(dept_dir, "ROSTER.md")
    with open(roster_path, 'w') as f:
        f.write("\n".join(lines))
    print(f"[ROSTER] Wrote {roster_path} ({len(roles)} roles)", file=sys.stderr)
    return roster_path


def write_universal_routing_map(departments):
    """Write universal-sops/00-ROUTING.md — the company-wide master routing file
    that maps a task to its owning department, then points at that department's
    ROSTER.md for role-level selection.

    Documented in INSTALL.md (5-BUILD-D) + ai-workforce-blueprint-full.md as the
    canonical routing file but never previously generated by the build. The CEO /
    Master Orchestrator's OPERATING PROTOCOL reads this file first.
    """
    if not COMPANY_DIR:
        print("[ROUTING] COMPANY_DIR not resolved; skipping 00-ROUTING.md", file=sys.stderr)
        return None
    universal_dir = os.path.join(COMPANY_DIR, "universal-sops")
    os.makedirs(universal_dir, exist_ok=True)

    lines = [
        "# 00-ROUTING.md — Master Task Routing",
        "",
        "The CEO / Master Orchestrator reads this FIRST for every task: find the "
        "department whose *Handles* matches the task, open that department's "
        "`departments/<dept>/ROSTER.md` to pick the specialist role, then spawn a "
        "sub-agent that reads the role folder in order and executes per its "
        "`how-to.md`. If no department matches, ask the owner — do not guess.",
        "",
        "| Department | Folder | Director | Handles |",
        "| --- | --- | --- | --- |",
    ]
    for dept_id, dept_info in departments.items():
        if dept_id in ("ceo", "master-orchestrator", "dept-ceo"):
            continue
        handles = (dept_info.get('description') or dept_info.get('name', dept_id)).replace('\n', ' ').strip()
        if len(handles) > 160:
            handles = handles[:157].rstrip() + '...'
        lines.append(
            f"| {dept_info.get('emoji', '')} {dept_info['name']} | "
            f"`departments/{dept_id}/` | {dept_info.get('head', '')} | {handles} |"
        )
    lines += [
        "",
        "## Read-the-SOP rule (binding)",
        "Routing is not the work. After routing, the owning director (or the CEO) "
        "MUST follow the read-the-SOP Operating Protocol: pick the role from the "
        "department ROSTER.md, spawn a sub-agent that reads "
        "`00-START-HERE.md -> IDENTITY.md -> SOUL.md -> how-to.md -> "
        "governing-personas.md`, execute per the how-to, and review the result "
        "against the how-to before reporting. No SOP for the task? Author it first "
        "(SOP-Writer, INSTRUCTIONS.md Moment 3.7) — never guess.",
        "",
        f"*Generated by build-workforce.py (Skill 23) on "
        f"{datetime.now().strftime('%B %d, %Y at %I:%M %p')}.*",
        "",
    ]
    routing_path = os.path.join(universal_dir, "00-ROUTING.md")
    with open(routing_path, 'w') as f:
        f.write("\n".join(lines))
    print(f"[ROUTING] Wrote {routing_path} ({len(departments)} departments)", file=sys.stderr)
    return routing_path


def write_pending_sops_manifest(departments):
    """Write PENDING-SOPS.md at the company root — the human/orchestrator-readable
    manifest of every role whose how-to.md is a PENDING stub (no library template
    matched), so the orchestrator knows exactly what still needs filling.

    Closes the 'silent empty stub' gap: a NO_TEMPLATE role is no longer a quiet
    placeholder — it is headed PENDING in its own how-to.md AND collected here.
    Scans the on-disk role folders for how-to.md files that carry the PENDING
    marker (written by create_role_workspace / create_role_workspaces.stub_how_to).
    """
    if not COMPANY_DIR or not DEPARTMENTS_DIR:
        return None
    pending = []  # (dept_id, role_folder, how_to_path)
    if os.path.isdir(DEPARTMENTS_DIR):
        for dept_id in sorted(departments.keys()):
            dept_dir = os.path.join(DEPARTMENTS_DIR, dept_id)
            if not os.path.isdir(dept_dir):
                continue
            for entry in sorted(os.listdir(dept_dir)):
                role_dir = os.path.join(dept_dir, entry)
                if not os.path.isdir(role_dir) or entry in ("memory", "devils-advocate"):
                    continue
                how_to = os.path.join(role_dir, "how-to.md")
                if not os.path.isfile(how_to):
                    continue
                try:
                    head = open(how_to).read(600)
                except OSError:
                    continue
                if "PENDING — FILL FROM LIBRARY" in head or "how-to.md (stub)" in head:
                    pending.append((dept_id, entry, how_to))

    lines = [
        "# PENDING-SOPS.md — Role how-to.md files awaiting library fill",
        "",
        f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}",
        "",
    ]
    if not pending:
        lines += [
            "All role `how-to.md` files were instantiated from the role-library "
            "(token-fill). Nothing pending. ✅",
            "",
        ]
    else:
        lines += [
            f"**{len(pending)} role(s) have a PENDING how-to.md** — no role-library "
            "template matched, so each carries a PENDING header with a one-shot "
            "fill instruction. Populate each FROM the nearest library template "
            "family (token-fill style, NOT a free-form LLM essay). Do NOT mark the "
            "workforce complete until this list is empty.",
            "",
            "| Department | Role folder | how-to.md |",
            "| --- | --- | --- |",
        ]
        for dept_id, role_folder, how_to in pending:
            lines.append(f"| {dept_id} | `{role_folder}/` | `{how_to}` |")
        lines += [
            "",
            "## How to fill each (one-shot, token-fill)",
            "For each row: open the role's `how-to.md`, read its PENDING header for "
            "the exact instruction, find the nearest matching template family in "
            "`23-ai-workforce-blueprint/templates/role-library/<dept>/`, copy it, "
            "and token-fill the company/role/industry placeholders. Reserve "
            "free-form generation only for roles with NO comparable template.",
            "",
        ]
    manifest_path = os.path.join(COMPANY_DIR, "PENDING-SOPS.md")
    with open(manifest_path, 'w') as f:
        f.write("\n".join(lines))
    print(f"[PENDING-SOPS] Wrote {manifest_path} ({len(pending)} pending)", file=sys.stderr)
    return manifest_path


# ============================================================
# COMMAND CENTER CONFIG GENERATION
# ============================================================

def write_company_config_json(company_name, industry, brand_colors=None,
                              full_config=None, selected_departments=None):
    """
    v10.7.0: Write company-config.json to the per-company ZHC folder.

    Schema v2.0 includes the data the persona scoring engine reads at
    runtime (mission, owner_values, company_kpis, dept_kpis). The earlier
    v1.0 schema only carried name/industry/brand and the persona-selector
    Layer 3 always fell back to a flat constant.

    Args:
        company_name:     str — company display name.
        industry:         str — industry vertical (e.g., "personal-development").
        brand_colors:     dict — optional {primary, accent, text} hex values.
        full_config:      dict — the non-interactive config (or harvested
                                  interview answers) from which mission, owner
                                  values, and company KPIs are pulled.
        selected_departments: dict — departments dict (dept_id -> info) used
                                  to derive dept_kpis aggregate.
    """
    if not COMPANY_DIR:
        print("[COMPANY-CONFIG] COMPANY_DIR not resolved; skipping", file=sys.stderr)
        return None

    brand_colors = brand_colors or {}
    full_config = full_config or {}
    selected_departments = selected_departments or {}

    mission = (
        full_config.get("mission")
        or full_config.get("company_mission")
        or full_config.get("company_description")
        or ""
    )

    owner_values = full_config.get("owner_values") or []
    if isinstance(owner_values, str):
        owner_values = [v.strip() for v in owner_values.split(",") if v.strip()]

    company_kpis = full_config.get("company_kpis") or []
    if isinstance(company_kpis, str):
        company_kpis = [k.strip() for k in company_kpis.split(",") if k.strip()]

    departments_cfg = full_config.get("departments", {}) or {}
    dept_kpis = {}
    for dept_id, dept_info in selected_departments.items():
        raw_kpis = ""
        if isinstance(departments_cfg.get(dept_id), dict):
            raw_kpis = departments_cfg[dept_id].get("kpis", "") or ""
        if not raw_kpis and isinstance(dept_info, dict):
            raw_kpis = dept_info.get("kpis", "") or ""
        if isinstance(raw_kpis, list):
            dept_kpis[dept_id] = raw_kpis
        elif isinstance(raw_kpis, str) and raw_kpis:
            dept_kpis[dept_id] = [k.strip() for k in raw_kpis.split(",") if k.strip()]
        else:
            dept_kpis[dept_id] = []

    cfg = {
        "name":     company_name,
        "slug":     COMPANY_SLUG,
        "industry": industry,
        "mission":  mission,
        "owner_values": owner_values,
        "company_kpis": company_kpis,
        "dept_kpis":    dept_kpis,
        "connected_systems": full_config.get("connected_systems", []),
        "brand": {
            "primary": brand_colors.get("primary", "#1f2937"),
            "accent":  brand_colors.get("accent",  "#3b82f6"),
            "text":    brand_colors.get("text",    "#f8fafc"),
        },
        "created":  datetime.now().isoformat(),
        "schema_version": "2.0",
    }
    path = os.path.join(COMPANY_DIR, "company-config.json")
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"[COMPANY-CONFIG] Wrote {path} (schema v2.0)", file=sys.stderr)
    missing = [k for k in ("mission", "owner_values", "company_kpis") if not cfg[k]]
    if missing:
        print(f"[COMPANY-CONFIG] WARN: empty fields {missing} — persona scoring "
              f"Layers 1-3 will fall back. Re-run interview or pass via config.",
              file=sys.stderr)
    return path


def generate_departments_json(departments):
    """
    Generate departments.json for the BlackCEO Command Center.
    Schema: [{ "id": str, "emoji": str, "name": str, "headTitle": str,
               "workspacePath": str, "slug"?: str }]
    IDs use "dept-" prefix to match Command Center expectations.

    WS-4: the FIRST entry is always the CEO department so the Command Center
    renders it at the TOP of the Kanban / department rail. The CEO is the
    Master Orchestrator (the main agent above the worker departments) surfaced
    as a board column — it does NOT overlap the worker departments (it is not
    one of the keys in `departments`, which carries only the worker depts).

    The CEO entry is emitted with id `dept-ceo` AND slug `ceo` so it matches
    every Command Center CEO-first guarantee:
      - migrations.ts autoSeedFromDepartmentsJson: isCeo when slug/id is
        'ceo'/'dept-ceo' -> seeds sort_order 0.
      - migration 046 pin_ceo_department_first: keys on lower(slug)='ceo' (or
        name) -> re-pins sort_order 0 (the sync script strips the 'dept-'
        prefix, so an explicit slug 'ceo' is what migration 046 catches).
      - AgentsSidebar hoist: id ('ceo'/'dept-ceo') or name match -> front of rail.
    """
    entries = []
    # CEO column first (top of the Kanban). Master Orchestrator surfaced as a board column.
    ceo_meta = RECOMMENDED_DEPARTMENTS.get("ceo", {
        "name": "CEO", "emoji": "\U0001f454", "head": "Chief Executive Officer",
    })
    entries.append({
        "id": "dept-ceo",
        "slug": "ceo",
        "emoji": ceo_meta.get("emoji", "\U0001f454"),
        "name": ceo_meta.get("name", "CEO"),
        "headTitle": ceo_meta.get("head", "Chief Executive Officer"),
        "workspacePath": "departments/master-orchestrator",
        "isCeo": True,
    })
    for dept_id, dept_info in departments.items():
        # Guard: never double-emit a CEO/master-orchestrator worker column —
        # the CEO is already the prepended top column.
        if dept_id in ("ceo", "master-orchestrator", "dept-ceo"):
            continue
        entries.append({
            "id": f"dept-{dept_id}",
            "emoji": dept_info["emoji"],
            "name": dept_info["name"],
            "headTitle": dept_info["head"],
            "workspacePath": f"departments/{dept_id}",
        })
    return entries


def copy_departments_to_command_center(departments_json):
    """
    Copy departments.json to the Command Center config directory.
    The build-workforce script writes to company-discovery/ but the CC
    reads from its own config/ directory. This function bridges the gap.
    """
    # Common CC install locations to try (in order of preference)
    cc_search_paths = [
        os.path.join(HOME, "clawd", "projects", "blackceo-command-center", "config"),
        os.path.join(HOME, "projects", "blackceo-command-center", "config"),
        os.path.join(HOME, "clawd", "blackceo-command-center", "config"),
        os.path.join(HOME, "Downloads", "blackceo-command-center", "config"),
    ]

    # Also check for a symlink or env var pointing to CC
    cc_root = os.environ.get("BLACKCEO_COMMAND_CENTER_ROOT", "")
    if cc_root:
        cc_search_paths.insert(0, os.path.join(cc_root, "config"))

    copied_to = []
    for cc_config_dir in cc_search_paths:
        if os.path.isdir(cc_config_dir):
            dest_path = os.path.join(cc_config_dir, "departments.json")
            try:
                with open(dest_path, 'w') as f:
                    json.dump(departments_json, f, indent=2)
                copied_to.append(dest_path)
                print(f"[CC-SYNC] Copied departments.json to: {dest_path}", file=sys.stderr)
            except Exception as e:
                print(f"[CC-SYNC WARNING] Failed to copy to {dest_path}: {e}", file=sys.stderr)

    if not copied_to:
        print("[CC-SYNC WARNING] No Command Center config directory found. "
              "Set BLACKCEO_COMMAND_CENTER_ROOT or ensure CC is installed.", file=sys.stderr)
        print("[CC-SYNC] departments.json is still available at the company-discovery path.",
              file=sys.stderr)

    return copied_to


def generate_persona_matrix(departments, persona_categories, company_name):
    """
    Generate persona-matrix.md - a mapping of departments to their pre-qualified personas.
    This creates visibility into which personas are available for which departments,
    supporting the 5-layer matching protocol (Layers 1-2 pre-qualified pool).

    The matrix is regenerated whenever the workforce is built or updated.
    If persona-matrix.md exists, this function updates it; otherwise creates it.
    """
    matrix_path = os.path.join(DEPARTMENTS_DIR, "persona-matrix.md")

    # Build department-to-persona mapping
    dept_to_domains = {
        "marketing": ["marketing", "copywriting", "communication"],
        "sales": ["sales", "communication", "strategy-innovation"],
        "billing": ["finance", "operations"],
        "support": ["communication", "coaching"],
        "operations": ["operations", "productivity-systems", "leadership"],
        "creative": ["copywriting", "marketing", "communication"],
        "hr": ["leadership", "coaching", "communication"],
        "legal": ["communication", "strategy-innovation"],
        "it": ["productivity-systems", "strategy-innovation", "operations"],
        "webdev": ["strategy-innovation", "marketing", "productivity-systems"],
        "appdev": ["strategy-innovation", "productivity-systems"],
        "graphics": ["marketing", "communication"],
        "video": ["marketing", "communication"],
        "audio": ["marketing", "communication"],
        "research": ["strategy-innovation", "operations"],
        "comms": ["communication", "leadership", "marketing"],
        "ceo": ["leadership", "strategy-innovation", "coaching", "mindset"],
    }

    content = f"""# Persona Matrix - {company_name}
## Department-to-Persona Mapping for 5-Layer Matching

**Generated:** {datetime.now().strftime('%B %d, %Y at %I:%M %p')}
**Version:** 1.0

---

## Overview

This matrix maps each department to its pre-qualified persona pool (Layers 1-2 of the 5-layer matching protocol).
Personas listed here have passed company mission and owner alignment checks.

**How to use:**
1. For each task, query the personas listed for that department
2. Apply Layers 3-5 (company goals, department goals, task fit) to select the best match
3. Log selection in persona-selection-log.md

---

## Department Mappings

"""

    for dept_id, dept_info in departments.items():
        domains = dept_to_domains.get(dept_id, ["leadership"])
        matched_personas = []

        if persona_categories and "personas" in persona_categories:
            seen = set()
            for domain in domains:
                for persona_id, data in persona_categories["personas"].items():
                    if domain in data.get("domain", []) and persona_id not in seen:
                        matched_personas.append({
                            "id": persona_id,
                            "author": data.get("author", ""),
                            "book": data.get("book", ""),
                            "domains": data.get("domain", []),
                            "perspective": data.get("perspective", []),
                        })
                        seen.add(persona_id)

        content += f"### {dept_info['emoji']} {dept_info['name']} ({dept_id})\n\n"
        content += f"**Head:** {dept_info['head']}\n"
        content += f"**Domain Tags:** {', '.join(domains)}\n\n"

        if matched_personas:
            content += "**Pre-Qualified Personas:**\n\n"
            for p in matched_personas[:10]:  # Limit to top 10 per department
                perspective = ', '.join(p['perspective']) if p['perspective'] else 'general'
                content += f"- **{p['author']}** ({p['book']}) - {perspective}\n"
            if len(matched_personas) > 10:
                content += f"- *...and {len(matched_personas) - 10} more*\n"
        else:
            content += "**Pre-Qualified Personas:** None yet. Run Skill 22 (Book-to-Persona) to add personas.\n"

        content += "\n---\n\n"

    # Add usage instructions
    content += """## Using This Matrix

### Step 1: Pre-Qualification (Layers 1-2)
Personas in this matrix have already been validated against:
- Company mission alignment
- Owner values and style alignment

### Step 2: Per-Task Matching (Layers 3-5)
For each task, score candidates on:
- Layer 3: Company goals/KPIs alignment
- Layer 4: Department goals/KPIs alignment
- Layer 5: Task-specific fit

### Step 3: Selection and Logging
After selecting a persona, log it:
```
[date] [task-id] "candidates" "selected" "layer-3-reason" "layer-4-reason" "layer-5-reason"
```

---

## Updating This Matrix

This matrix is auto-generated by build-workforce.py whenever the workforce is built.
To regenerate after adding new personas (via Skill 22):
1. Re-run build-workforce.py, or
2. Manually run: `python3 build-workforce.py --non-interactive --config-file workforce-config.json`

---

*This is a living document. Update it whenever personas or departments change.*
"""

    try:
        with open(matrix_path, 'w') as f:
            f.write(content)
        print(f"[PERSONA-MATRIX] Updated: {matrix_path}", file=sys.stderr)
    except Exception as e:
        print(f"[PERSONA-MATRIX WARNING] Could not write matrix: {e}", file=sys.stderr)

    return matrix_path


# ============================================================
# AGENTS.LIST MANAGEMENT
# ============================================================

def _agent_dir_for(agent_id):
    """
    BUG 2 FIX: derive the per-agent agentDir from the agent's UNIQUE id.

    The strict OpenClaw 2026.5.22 schema (config/agent-dirs.js) requires every
    agent in agents.list[] to resolve to a UNIQUE agentDir; sharing one causes
    a `Duplicate agentDir detected` validation failure (and a gateway crash on
    restart). The gateway's own default is <stateDir>/agents/<id>/agent, so we
    mirror that here, anchored to this agent's unique id. Each dept agent gets
    its OWN directory -- never a shared one.
    """
    # Platform-aware state dir: VPS uses /data/.openclaw, Mac uses ~/.openclaw.
    # Mirrors the gateway's own default of <stateDir>/agents/<id>/agent.
    state_root = "/data/.openclaw" if os.path.isdir("/data/.openclaw") else os.path.join(HOME, ".openclaw")
    return os.path.join(state_root, "agents", agent_id, "agent")


def add_agent_to_config(config, dept_id, dept_info):
    """
    Add a department head agent to openclaw.json agents.list.

    v10.x BUG FIXES:
      - BUG 2 (duplicate agentDir + shared identity): each dept agent now gets
        its OWN agentDir derived from its UNIQUE agent id, and its OWN identity
        name straight from dept_info (per-department, never a shared
        "Billing/Finance"). A guard refuses to write two agents sharing one
        agentDir.
      - BUG 4 (invalid subagents keys): the strict 2026.5.22 schema
        (AgentEntrySchema.subagents) accepts ONLY `allowAgents` and `model`.
        The old block wrote thinking / maxChildrenPerAgent / maxConcurrent /
        maxSpawnDepth / timeoutSeconds (all rejected) plus top-level
        bootstrapMaxChars / bootstrapTotalMaxChars (also rejected). Writing
        them made `config validate` / `health` / restart FAIL. We now write
        only schema-valid keys.
    """
    config.setdefault("agents", {})
    if not isinstance(config["agents"].get("list"), list):
        config["agents"]["list"] = []
    agents_list = config["agents"]["list"]
    agent_id = f"dept-{dept_id}"

    # Check if already exists (idempotent)
    existing_ids = {a.get("id") for a in agents_list if isinstance(a, dict)}
    if agent_id in existing_ids:
        return False  # Already exists, skip

    # v9.6.1: Use the canonical model selector chain instead of the stale
    # DEFAULT_MODEL_ASSIGNMENTS dict (which still references moonshot/kimi-k2.5).
    # The selector picks Ollama Kimi 2.6+ first, with fallbacks.
    # If select_model.py is unreachable at install time, fall back to a
    # safe default that Anthropic-strips and matches v9.5.x policy.
    model = _resolve_director_model(dept_id) or "ollama/kimi-k2.6:cloud"
    workspace = os.path.join(DEPARTMENTS_DIR, dept_id)
    agent_dir = _agent_dir_for(agent_id)

    # BUG 2 FIX: guard against a duplicate agentDir. If any EXISTING agent
    # already resolves to this agent_dir under a different id, refuse to write
    # (this is exactly what `Duplicate agentDir detected` would reject).
    for a in agents_list:
        if not isinstance(a, dict):
            continue
        existing_dir = a.get("agentDir")
        if existing_dir and os.path.abspath(existing_dir) == os.path.abspath(agent_dir):
            owner_id = a.get("id")
            print(f"[CONFIG GUARD] Refusing to add '{agent_id}': agentDir "
                  f"'{agent_dir}' already owned by '{owner_id}'. Skipping.",
                  file=sys.stderr)
            return False

    # BUG 4 FIX: schema-valid subagents block ONLY. The strict 2026.5.22
    # AgentEntrySchema permits exactly { allowAgents, model } under subagents.
    canonical_subagents = {
        "allowAgents": ["*"],
        "model": {
            "fallbacks": [
                "ollama/kimi-k2.6:cloud",
                "openrouter/moonshot/kimi-k2.6",
                "ollama/deepseek-v4-pro:cloud",
                "openrouter/deepseek/deepseek-v4-pro",
            ]
        },
    }

    agent_entry = {
        "id": agent_id,
        # BUG 2 FIX: per-department identity name, never a shared one.
        "name": dept_info["head"],
        "workspace": workspace,
        # BUG 2 FIX: unique per-agent agentDir derived from the unique id.
        "agentDir": agent_dir,
        "model": model,
        "subagents": canonical_subagents,
    }

    agents_list.append(agent_entry)
    config["agents"]["list"] = agents_list
    return True


def _resolve_director_model(dept_id):
    """Call shared-utils/select_model.py --purpose-tier heavy for the dept director."""
    import subprocess
    selector_candidates = [
        os.path.join(HOME, "Downloads", "openclaw-master-files", "shared-utils", "select_model.py"),
        "~/Downloads/openclaw-master-files/shared-utils/select_model.py",
    ]
    for sel in selector_candidates:
        if os.path.isfile(sel):
            try:
                r = subprocess.run(
                    ["python3", sel, "--skill", f"dept-{dept_id}",
                     "--purpose-tier", "heavy", "--format", "id"],
                    capture_output=True, text=True, timeout=10,
                )
                model_id = r.stdout.strip()
                if model_id and "anthropic/" not in model_id.lower() and "claude-" not in model_id.lower():
                    return model_id
            except Exception:
                pass
    return None


# ============================================================
# HANDOFF FILE MANAGEMENT
# ============================================================

def create_handoff(option, departments_done, departments_remaining, progress_pct):
    """Create or update the interview handoff file for resume capability."""
    discovery_dir = _ensure_company_discovery_dir()
    if not discovery_dir:
        print("[PERSISTENCE ERROR] create_handoff() - handoff file NOT saved.", file=sys.stderr)
        return
    handoff_path = os.path.join(discovery_dir, "interview-handoff.md")
    content = f"""# Interview Handoff
## Last Updated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}

## Option Selected: {option}
## Progress: {progress_pct}%

## Departments Completed:
{chr(10).join(f'- {d}' for d in departments_done) if departments_done else '- (none yet)'}

## Departments Remaining:
{chr(10).join(f'- {d}' for d in departments_remaining) if departments_remaining else '- (all done)'}
"""
    with open(handoff_path, 'w') as f:
        f.write(content)
    print(f"[PERSISTENCE] Handoff saved to: {handoff_path}", file=sys.stderr)


def log_fallback(question, client_response, fallback_type):
    """
    Log when a client hesitates or doesn't know an answer.
    This data improves the interview for future clients.

    fallback_type: 'offered_research' | 'presented_options' | 'skipped' | 'client_stopped'
    """
    discovery_dir = _ensure_company_discovery_dir()
    if not discovery_dir:
        print("[PERSISTENCE ERROR] log_fallback() - analytics NOT saved.", file=sys.stderr)
        return
    analytics_dir = os.path.join(discovery_dir, "interview-analytics")
    os.makedirs(analytics_dir, exist_ok=True)
    log_path = os.path.join(analytics_dir, "fallback-log.json")

    entry = {
        "timestamp": datetime.now().isoformat(),
        "question": question,
        "client_response": client_response,
        "fallback_type": fallback_type,
    }

    # Load existing log or create new
    entries = []
    if os.path.isfile(log_path):
        with open(log_path, 'r') as f:
            try:
                entries = json.load(f)
            except json.JSONDecodeError:
                entries = []

    entries.append(entry)

    with open(log_path, 'w') as f:
        json.dump(entries, f, indent=2)


def log_answer(question, answer):
    """Append a Q&A to workforce-interview-answers.md."""
    discovery_dir = _ensure_company_discovery_dir()
    if not discovery_dir:
        print("[PERSISTENCE ERROR] log_answer() - answer NOT saved. Progress may be lost if session ends.",
              file=sys.stderr)
        return
    answers_path = os.path.join(discovery_dir, "workforce-interview-answers.md")

    # Create file with header if it doesn't exist
    if not os.path.isfile(answers_path):
        with open(answers_path, 'w') as f:
            f.write(f"# Workforce Interview Answers\n\nStarted: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n---\n\n")

    # Append the Q&A
    with open(answers_path, 'a') as f:
        f.write(f"**Q:** {question}\n")
        f.write(f"**A:** {answer}\n")
        f.write(f"**Logged:** {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n---\n\n")
    print(f"[PERSISTENCE] Answer logged to: {answers_path}", file=sys.stderr)


# ============================================================
# MAIN EXECUTION FLOW
# ============================================================

def main():
    """
    Main execution flow. This is called BY the AI agent, not directly by the client.
    The AI reads this file and executes the flow conversationally.

    FLOW:
    1. Detect environment (master files folder, existing context)
    2. ALWAYS present Option A/B/C (never skip)
    3. If Option A: run dynamic interview
    4. If Option B: read existing files, propose structure, get approval
    5. If Option C: scan existing structure, find gaps, fill them
    6. Create department workspaces with full core files
    7. Determine specialists (permanent vs on-call) silently
    8. Run persona alignment (Act As If Protocol, 5-layer check)
    9. Generate ORG-CHART.md
    10. Generate Command Center departments.json
    11. Create Devil's Advocate per department
    12. Update openclaw.json (backup first, validate after)
    13. Report completion with summary

    INTERVIEW RULES:
    - Dynamic questions (3-7 per department)
    - Plain English only, no jargon
    - Check existing files before asking
    - Confirm known info: "We already know X. Still correct?"
    - Offer research: "Not sure? I can research best practices for your industry."
    - Flush after every answered question
    - Update handoff file after every answer
    - Progress indicators at milestones
    - Use Perplexity sonar-pro-search for best practices research
    """
    global MASTER_FILES, COMPANY_DISCOVERY_DIR

    # Step 1: Detect environment (guaranteed non-None after hardening)
    MASTER_FILES = find_master_files_folder()
    COMPANY_DISCOVERY_DIR = os.path.join(MASTER_FILES, "company-discovery")
    print(f"[PERSISTENCE] Master files folder: {MASTER_FILES}", file=sys.stderr)
    print(f"[PERSISTENCE] Interview answers will be saved to: {COMPANY_DISCOVERY_DIR}/", file=sys.stderr)

    # Step 2: Read existing context
    existing_context = read_existing_context()
    previous_answers = read_previous_answers()
    handoff = read_handoff()

    # Step 3: Check for Skill 22 (Book-to-Persona)
    persona_categories = load_persona_categories()
    personas_available = persona_categories is not None

    # Step 4: Present options (MANDATORY - NEVER SKIP)
    # The AI agent presents these conversationally, not as code output
    print("""
    ==============================================
    AI WORKFORCE BLUEPRINT - COMPANY SETUP
    ==============================================

    Welcome! I'm going to help you set up your AI company.

    You have three options:

    Option A - Full Interview (Recommended)
    I'll ask you about your business and build everything
    based on your answers. Most personalized results.

    Option B - Quick Setup
    I'll use what I already know about you plus industry
    best practices. You review and adjust. Fastest path.

    Option C - Audit / Resume
    If you already have a workforce set up, or if we
    got interrupted last time, I'll pick up where we left off.

    Which option would you like?
    """)

    # The AI agent handles the response conversationally from here.
    # The functions above provide the building blocks.
    # The AI uses:
    #   - log_answer() after every question
    #   - create_handoff() after every answer
    #   - create_department_workspace() for each department
    #   - determine_specialists() for specialist decisions
    #   - create_governing_personas_md() for persona wiring
    #   - generate_org_chart() at the end
    #   - generate_departments_json() for the Command Center
    #   - add_agent_to_config() for each department head
    #   - backup_config() before ANY config edits
    #   - save_openclaw_config() with validation after edits


if __name__ == "__main__":
    args = parse_args()
    if args.non_interactive:
        config = load_non_interactive_config(args.config_file)
        build_from_config(config)
    else:
        main()
