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
- The AI MUST be running on a high reasoning model (DeepSeek v4 pro, GLM 5.2, MiMo V2 Pro, Gemini 3.1 Pro, GPT 5.4); Ollama Cloud preferred, OpenRouter backup, thinking=HIGH
- Research best practices uses openrouter/perplexity/sonar-pro-search

FORBIDDEN CLIENT-FACING LANGUAGE:
See the canonical machine-readable list: interview/forbidden-jargon.json
That file is the single source of truth. Do NOT define a second list here.
Quick reference (human-readable): Never say: SOPs, handoffs, tech stack,
permanent agent, sub-agent, agent, Lean Six Sigma, DMAIC.
Instead say: step-by-step instructions, what departments share, tools you
use, team member, specialist, director.
"""

import os
import sys
import json
import re
import hashlib
import argparse
import shutil
import subprocess  # v10.15.25: module-level so bare subprocess.run / subprocess.TimeoutExpired
                   # in build_from_config (SOP-populate step) resolve. Previously the only
                   # `import subprocess` statements were function-local in OTHER functions, so the
                   # bare references crashed the build with NameError: name 'subprocess' is not defined.
from datetime import datetime
from pathlib import Path

# ── SHARED DECLINE READER (Issue #2 / Bulletproofing a) ──────────────────────
# The provenance-gated decline model + the ONE normalizer live in the sibling
# canonical_decline.py so build-workforce.py, department-floor.py and
# qc-interview-completion.py can never drift again (the drift that caused the
# residual over-provision bug (decline-normalization drift)). Add this script's own dir to sys.path so
# the import resolves whether this file is run as a script OR loaded via
# importlib.util.spec_from_file_location (the CI test harnesses).
_BW_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _BW_SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _BW_SCRIPTS_DIR)
from canonical_decline import (  # noqa: E402
    norm as _decline_norm,
    analyze as _decline_analyze,
    canonical_decline_set as _shared_canonical_decline_set,
    decision_coverage as _shared_decision_coverage,
)

# ── WS-2: import the role-library instantiation helpers from the sibling
# create_role_workspaces module so the PRIMARY build INSTANTIATES the 121
# pre-written SOPs (copy + token-personalize) instead of writing empty
# `[Step 1 - to be personalized]` stubs that then get LLM-regenerated. The
# normalizer (normalize_role_variants/normalize_dept) takes naive slug match
# from ~58% to ~100% coverage. Best-effort import: if it fails for any reason
# the build degrades gracefully to the legacy stub+LLM path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# PRD 1.5: add shared-utils to path so canonical_dept_slug is importable.
_BW_SHARED_UTILS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared-utils"
)
sys.path.insert(0, os.path.normpath(_BW_SHARED_UTILS))
try:
    from canonical_slug import canonical_dept_slug as _canonical_dept_slug  # type: ignore
    _HAS_CANONICAL_SLUG = True
except ImportError:
    _HAS_CANONICAL_SLUG = False
    # Inline fallback; mirrors canonical_slug.py so the script never fails to build.
    import re as _re_cs
    def _canonical_dept_slug(raw: str) -> str:  # type: ignore
        if not raw or not isinstance(raw, str):
            return ""
        s = raw.strip().lower()
        if s.startswith("dept-"):
            s = s[5:]
        if s.endswith("-dept"):
            s = s[:-5]
        s = s.replace(" ", "-").replace("_", "-")
        s = _re_cs.sub(r"-{2,}", "-", s)
        return s.strip("-")

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

# v13.8.14 PROVER-ALIGNMENT (single source of truth): per-role folder creation
# routes through the SAME engine floor-fill-driver.py uses —
# create_role_workspaces.create_role_workspace(). This guarantees the on-disk
# folder slug is byte-identical to the role-library .md filename and the
# floor-manifest slug (the engine slugs via role_metadata['slug'] VERBATIM, with
# slugify() as the no-slug fallback). Eliminates the historic divergence where
# build-workforce's own folder-writer produced "...play-ht" / "fp-a-..." that the
# prover could not reconcile. If the engine import fails, the in-file legacy
# writer is used as a defensive fallback (logged) so a build never hard-stops.
try:
    from create_role_workspaces import (
        create_role_workspace as _crw_create_role_workspace,
    )
    _ENGINE_ROLE_WRITER_AVAILABLE = True
except Exception as _e:  # pragma: no cover - defensive
    _ENGINE_ROLE_WRITER_AVAILABLE = False
    print(f"[ROLE-WORKSPACE WARNING] create_role_workspaces.create_role_workspace "
          f"import failed ({_e}); falling back to in-file legacy folder writer",
          file=sys.stderr)

# ROOT-CAUSE FIX (2026-06-18): the disk-truth roster generator. write_department_
# roster delegates to this so ROSTER.md lists exactly the role folders that EXIST
# on disk (including custom/extra roles materialized via materialize_custom_roles
# and partial/resume builds), instead of only the suggested-roles menu.
try:
    from create_role_workspaces import (
        regenerate_department_roster as _crw_regenerate_department_roster,
        scan_department_roles_on_disk as _crw_scan_department_roles_on_disk,
    )
    _ROSTER_DISK_TRUTH_AVAILABLE = True
except Exception as _e:  # pragma: no cover - defensive
    _ROSTER_DISK_TRUTH_AVAILABLE = False
    print(f"[ROSTER WARNING] regenerate_department_roster import failed "
          f"({_e}); ROSTER.md will be derived from the menu only", file=sys.stderr)

# PRD-2.15: helper to resolve the build state file path (no tildes; mirrors detect_platform.py).
def _resolve_build_state_path():
    """Return Path to .workforce-build-state.json or None if workspace not found."""
    vps = Path("/data/.openclaw/workspace")
    if vps.is_dir():
        return vps / ".workforce-build-state.json"
    mac = Path(os.environ.get("HOME", "")).expanduser() / ".openclaw" / "workspace"
    if mac.is_dir():
        return mac / ".workforce-build-state.json"
    return None

# WS-2: build-wide tally of how roles were staffed, for the visible ratio log.
_LIBRARY_FILL_STATS = {"instantiated_from_library": 0, "llm_generated": 0}
# Set of role folder names (absolute paths) instantiated from the library, so
# write_sop_research_manifest() can SKIP them (their SOPs are already authored
# inside how-to.md - no LLM regeneration needed).
_LIBRARY_INSTANTIATED_ROLE_DIRS = set()

# PER-ARTIFACT VERSIONING (v12.27.0): build-wide accumulator of the SOURCE
# content_sha each role was instantiated FROM. Keyed "<dept>/<role-slug>". Flushed
# into .workforce-build-state.json.artifactProvenance by
# _flush_artifact_provenance_to_state() at the end of the build. This is the FAST
# PATH detect-stale-artifacts.py reads (no need to re-scan every client file); the
# per-file `workforce-provenance` HTML-comment marker is the ground-truth fallback.
_ARTIFACT_PROVENANCE = {}              # "<dept>/<slug>" -> {source_content_sha, ...}
_ARTIFACT_PROVENANCE_MANIFEST_VERSION = {"version": None}

# PRD 2.12 / W2.1: boundary gate - canonical-library dept registry.
# FAIL-CLOSED: if sop_boundary_gate cannot be imported, or if the role-library
# directory is missing/empty (GATE_ENABLED=False), the build MUST abort with a
# non-zero exit.  The #1 invariant — a box must NEVER rewrite canonical floor
# roles/SOPs — cannot be enforced without a functioning gate.  Silently defining
# stub functions that always return False is the exact failure mode W2.1 fixes:
# it makes every canonical dept look custom and opens the LLM authoring path for
# canonical work.
try:
    from sop_boundary_gate import (  # type: ignore
        is_canonical_dept as _bw_is_canonical_dept,
        CANONICAL_LIBRARY_DEPT_IDS as _BW_CANONICAL_DEPT_IDS,
        GATE_ENABLED as _BW_GATE_ENABLED,
        ROLE_LIBRARY_DIR as _BW_ROLE_LIBRARY_DIR,
        assert_gate_enabled as _bw_assert_gate_enabled,
    )
    _BW_BOUNDARY_GATE_AVAILABLE = True
except ImportError as _bw_bg_import_err:
    print(
        f"\n[SOP-BOUNDARY-GATE] FATAL: sop_boundary_gate module could not be imported.\n"
        f"  Error: {_bw_bg_import_err}\n"
        f"The role/SOP boundary gate is MANDATORY — this build cannot proceed without it.\n"
        f"The #1 invariant (never rewrite canonical floor roles/SOPs) cannot be enforced.\n"
        f"Fix: ensure sop_boundary_gate.py is present in the same scripts/ directory as\n"
        f"build-workforce.py and is free of syntax errors.\n"
        f"BUILD ABORTED.\n",
        file=sys.stderr,
    )
    sys.exit(1)

# Gate imported — now assert it is operational (role-library must exist + non-empty).
if not _BW_GATE_ENABLED:
    print(
        f"\n[SOP-BOUNDARY-GATE] FATAL: Boundary gate is DISABLED.\n"
        f"  role-library directory missing or empty at: {_BW_ROLE_LIBRARY_DIR}\n"
        f"The #1 invariant (never rewrite canonical floor roles/SOPs) cannot be enforced\n"
        f"without a populated role-library.  Every canonical floor department would be\n"
        f"misidentified as custom and its roles rewritten by the LLM authoring path.\n"
        f"Fix: restore the templates/role-library/ directory tree and re-run.\n"
        f"BUILD ABORTED.\n",
        file=sys.stderr,
    )
    sys.exit(1)

_BW_BOUNDARY_GATE_AVAILABLE = True  # gate is live


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
    parser.add_argument(
        '--regenerate-org-chart-only',
        action='store_true',
        help=(
            'Re-render ORG-CHART.md from current build-state WITHOUT a full rebuild. '
            'Used by converge (sync-extensions.sh --converge) after add-*.sh runs '
            'to keep GET /api/org-chart current. Reads .workforce-build-state.json '
            'and writes <COMPANY_DIR>/ORG-CHART.md then exits 0.'
        )
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

    # G1-FAB-ENFORCE (anti-fabrication): read config['option'] and REFUSE to load a
    # config that would fabricate client answers. A non-interactive build is allowed
    # ONLY with a genuine interview transcript OR an explicit ownerConsent self-setup/
    # fast opt-in. Without proof this exits non-zero and writes INTERVIEW_PENDING —
    # the build never reaches build_from_config() to stamp interviewComplete=true.
    _enforce_consent_or_refuse(config)

    # PRD-2.15: assert industryPack.slug is present in build state before building.
    # This enforces that the interview ran with industry customization - an interview
    # with no recorded pack is not industry-custom and must not proceed blindly.
    # Edge case: slug="unknown" is allowed with a loud warning (unclassifiable business
    # should not be un-buildable). Absent slug entirely = hard fail.
    _state_path = _resolve_build_state_path()
    if _state_path is not None and _state_path.exists():
        try:
            _state = json.loads(_state_path.read_text(encoding="utf-8"))
            _pack = _state.get("industryPack") or {}
            _slug = _pack.get("slug")
            if not _slug:
                print(
                    "[NON-INTERACTIVE ERROR] PRD-2.15: industryPack not recorded in build state.\n"
                    "  Run: 23-ai-workforce-blueprint/scripts/record-industry-pack.sh --blob-file <research-blob>\n"
                    "  Or confirm the vertical in Phase 5 before building.\n"
                    "  State file: " + str(_state_path),
                    file=sys.stderr,
                )
                sys.exit(1)
            elif _slug == "unknown":
                print(
                    "[NON-INTERACTIVE WARNING] PRD-2.15: industryPack.slug='unknown' - no industry vertical "
                    "was detected or confirmed. Building will proceed but industry customization may be generic. "
                    "Phase 5 confirmation was expected to set the slug.",
                    file=sys.stderr,
                )
        except Exception as _e:
            print(f"[NON-INTERACTIVE WARNING] PRD-2.15: could not read build state for industryPack check: {_e}", file=sys.stderr)
            # Non-fatal: the build state may not exist in legacy flows; don't block on read errors.
    else:
        print(
            "[NON-INTERACTIVE WARNING] PRD-2.15: build state not found; cannot assert industryPack.slug. "
            "Proceeding without industry-pack verification.",
            file=sys.stderr,
        )

    return config


# ============================================================
# CANONICAL DEPARTMENT FLOOR (standard: 22 mandatory + 6 universal-primary-vertical = 28)
# ============================================================
# Every Zero Human Company is built with the mandatory canonical departments
# (21 in department-naming-map.json v2.5.0) PLUS the 7 universal primary
# vertical-pack departments (one primary per pack, always added regardless of
# industry) = 28 departments minimum. The floor is computed at runtime from the
# live naming map (len(mandatory) + count of universal-primary pack depts); the
# numbers in these comments describe the live data and are never a hardcoded
# gate. The canonical floor is further expanded by keyword-matched industry
# extras (flavor/additive, never reducing). Explicit client declines (a
# mandatory dept, a universal-primary vertical, or a custom dept) are the ONLY
# way to go below the floor.
# Canonical IDs live in department-naming-map.json (the source of truth). Legacy
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


# ============================================================
# CAPABILITY 2 - SEMANTIC COMBINE / MERGE (PRD R2.3)
# ============================================================
# _canonical_present() only catches a custom dept that is the canonical id, its
# single alias, or a known VARIANT slug. It does NOT catch a custom dept that is
# the SAME function under a different, non-slug name (e.g. "Accounting" vs
# billing-finance, "Client Success" vs customer-support, "Brand & Identity
# Design" vs graphics). Without a merge step those ship as a SECOND department
# alongside the canonical one - a duplicate. This map + the detect/apply pair
# below find that semantic overlap and, ON A RECORDED OWNER CONFIRM, fold the
# custom INTO the canonical dept (custom roles/SOPs layered in, ONE department),
# never shipping a duplicate.
#
# Keyword model (deterministic, no LLM): for each canonical id, a list of
# whole-word/phrase signals. A custom dept whose normalized name OR description
# contains a signal for exactly one canonical id is a merge CANDIDATE. The
# canonical floor dept is always the survivor (the custom function is absorbed
# into it). This is the SAME outcome the advisory build-with-AI prompt strings
# asked the LLM to "recommend" - but enforced in code with an executor.
SEMANTIC_OVERLAP_KEYWORDS = {
    "billing-finance": [
        "accounting", "bookkeeping", "bookkeep", "tax", "taxes", "payroll",
        "invoicing", "accounts payable", "accounts receivable", "ledger",
    ],
    "customer-support": [
        "client success", "customer success", "client care", "client services",
        "account success", "help desk", "helpdesk", "client experience",
    ],
    "graphics": [
        "brand identity", "brand and identity", "brand design", "identity design",
        "visual identity", "branding design", "creative design", "logo design",
    ],
    "crm": [
        "marketing and crm", "crm automation", "marketing automation",
        "convert and flow", "convert & flow", "pipeline automation",
        "customer relationship management",
    ],
    "openclaw-maintenance": [
        "fleet operations", "fleet ops", "fleet rescue", "rescue operations",
        "platform maintenance", "infrastructure ops", "infra ops", "devops",
    ],
    "project-architecture-office": [
        "zhc build office", "build office", "workforce build", "delivery office",
        "program office", "pmo", "project management office",
    ],
    "legal": [
        "compliance", "regulatory", "risk and compliance", "risk & compliance",
        "contracts and compliance",
    ],
    "communications": [
        "public relations", "pr and comms", "internal comms", "corporate comms",
    ],
}

# Universal-primary vertical depts can also absorb a custom function. Keyed the
# same way; survivor is the canonical vertical id.
SEMANTIC_OVERLAP_KEYWORDS_VERTICAL = {
    "presentations": [
        "speeches", "thought leadership", "thought-leadership", "keynotes",
        "speaking", "pitch decks", "slide decks", "presentation design",
    ],
    "listings": ["mls", "property listings", "listing management"],
    "podcast": ["podcasting", "show production", "episode production"],
}


def _semantic_overlap_match(custom_id, custom_info, overlap_map):
    """
    Return the canonical id a custom dept semantically overlaps, or None.

    Deterministic keyword scan over the custom dept's normalized id + name +
    description. A custom dept matches a canonical id when it contains at least
    one of that id's signals. If signals for MORE THAN ONE canonical id match,
    return None (ambiguous - never auto-propose a merge we cannot defend; leave
    it as a standalone custom for the owner to place by hand). The match is
    advisory: it produces a PROPOSAL; only a recorded owner confirm merges it.
    """
    info = custom_info or {}
    haystack = " ".join([
        str(custom_id or ""),
        str(info.get("name", "") or ""),
        str(info.get("description", "") or ""),
        str(info.get("activities", "") or ""),
    ]).lower()
    haystack = re.sub(r"[-_]", " ", haystack)
    hits = set()
    for cid, signals in overlap_map.items():
        for sig in signals:
            s = sig.lower()
            if " " in s:
                if s in haystack:
                    hits.add(cid)
                    break
            elif re.search(r"\b" + re.escape(s) + r"\b", haystack):
                hits.add(cid)
                break
    if len(hits) == 1:
        return next(iter(hits))
    return None


def detect_semantic_overlaps(selected_departments):
    """
    CAPABILITY 2 (detect). Find custom depts that semantically overlap a canonical
    floor dept (or universal-primary vertical) under a NON-aliased, NON-variant
    name. Returns a list of proposal dicts:
        {"custom_id", "custom_name", "target_canonical", "target_kind"}
    where target_kind is "mandatory" or "vertical".

    A custom dept already recognized by _canonical_present() (id/alias/variant)
    is NOT a proposal - it is already de-duped by reconcile_canonical_floor().
    This step ONLY surfaces the semantic (non-slug) overlaps that step misses.
    """
    floor_ids = set(load_canonical_floor().keys())
    proposals = []
    for did, info in selected_departments.items():
        # Skip anything that is itself a canonical dept under id/alias/variant.
        if any(_canonical_present(cid, {did: info}) for cid in floor_ids):
            continue
        target = _semantic_overlap_match(did, info, SEMANTIC_OVERLAP_KEYWORDS)
        kind = "mandatory"
        if not target:
            target = _semantic_overlap_match(did, info, SEMANTIC_OVERLAP_KEYWORDS_VERTICAL)
            kind = "vertical"
        if target and target != did:
            proposals.append({
                "custom_id": did,
                "custom_name": (info or {}).get("name", did),
                "target_canonical": target,
                "target_kind": kind,
            })
    return proposals


def apply_semantic_merges(selected_departments, core_answers):
    """
    CAPABILITY 2 (execute). For each detected semantic overlap, look up the OWNER'S
    recorded decision in build-state canonicalReconciliation.mergeDecisions and act:

      mergeDecisions[<custom_id>] == "merge"   -> FOLD the custom INTO the canonical
          dept: append the custom dept's name + description into the canonical
          dept's mergedFrom record so its roles/SOPs are layered in, then DROP the
          standalone custom dept (no duplicate ships). The canonical dept survives.
      mergeDecisions[<custom_id>] == "keep"    -> leave both standalone (owner wants
          a distinct department). No merge.
      (absent / any other value)               -> conservative DEFAULT: keep both
          standalone and record the proposal as PENDING so the interview/Phase 5.5
          can ask. NEVER auto-merge without a recorded confirm - a silent merge
          would destroy a department the owner may have wanted.

    Idempotent: a custom already folded (absent from selected_departments) is a
    no-op. Records an auditable semanticMerges block into build-state.

    Returns the mutated selected_departments dict.
    """
    proposals = detect_semantic_overlaps(selected_departments)
    if not proposals:
        return selected_departments

    build_state = _load_build_state()
    recon = build_state.get("canonicalReconciliation", {}) or {}
    merge_decisions = recon.get("mergeDecisions", {}) or {}

    merged = []
    kept = []
    pending = []
    # Survivor canonical dept -> list of absorbed custom records (for build-time
    # role/SOP layering). Persisted under canonicalReconciliation.mergedInto.
    merged_into = {}

    for p in proposals:
        cid = p["custom_id"]
        target = p["target_canonical"]
        decision = str(merge_decisions.get(cid, "")).strip().lower()
        if decision == "merge":
            custom_info = selected_departments.get(cid, {}) or {}
            # The canonical/vertical target must end up present so the fold has a
            # home. reconcile_canonical_floor() (mandatory) and apply_vertical_packs()
            # (vertical) add it; record the absorption for build-time layering.
            merged_into.setdefault(target, []).append({
                "id": cid,
                "name": custom_info.get("name", cid),
                "description": custom_info.get("description", ""),
                "base_suggested_roles": custom_info.get("base_suggested_roles", ""),
            })
            # Annotate the survivor in-place if it is already in the set (mandatory
            # may not be added until reconcile runs after this; that is fine - the
            # mergedInto record is the durable carrier the build reads).
            if target in selected_departments:
                surv = selected_departments[target]
                mf = surv.get("mergedFrom", [])
                if cid not in mf:
                    mf.append(cid)
                surv["mergedFrom"] = mf
            # Drop the standalone custom so NO duplicate department ships.
            selected_departments.pop(cid, None)
            merged.append({"custom_id": cid, "target_canonical": target, "target_kind": p["target_kind"]})
            print(f"[MERGE] Folded custom '{cid}' INTO canonical '{target}' "
                  f"(owner confirmed). No duplicate department ships.", file=sys.stderr)
        elif decision == "keep":
            kept.append({"custom_id": cid, "target_canonical": target})
            print(f"[MERGE] Owner chose to KEEP '{cid}' standalone alongside "
                  f"'{target}'. No merge.", file=sys.stderr)
        else:
            pending.append(p)
            print(f"[MERGE] PENDING decision for custom '{cid}' (overlaps "
                  f"'{target}'). Kept standalone; Phase 5.5 must ask merge/keep.",
                  file=sys.stderr)

    # Persist an auditable record (idempotent merge into build-state).
    try:
        path = _build_state_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        state = _load_build_state()
        existing = state.get("canonicalReconciliation", {})
        if not isinstance(existing, dict):
            existing = {}
        existing["semanticMerges"] = {
            "proposals": proposals,
            "merged": merged,
            "kept": kept,
            "pending": pending,
            "evaluatedAt": datetime.now().isoformat(),
            "source": "build-workforce.py apply_semantic_merges",
        }
        # mergedInto is the build-time layering carrier: survivor -> absorbed customs.
        prior_mi = existing.get("mergedInto", {}) or {}
        for tgt, recs in merged_into.items():
            prior = prior_mi.get(tgt, [])
            for r in recs:
                if not any(x.get("id") == r["id"] for x in prior):
                    prior.append(r)
            prior_mi[tgt] = prior
        existing["mergedInto"] = prior_mi
        state["canonicalReconciliation"] = existing
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
        print(f"[MERGE] Wrote semanticMerges record ({len(merged)} merged, "
              f"{len(kept)} kept, {len(pending)} pending) to {path}", file=sys.stderr)
    except OSError as e:
        print(f"[MERGE WARNING] Could not write semanticMerges record: {e}", file=sys.stderr)

    return selected_departments


def load_canonical_floor():
    """
    Read the mandatory canonical departments from department-naming-map.json
    (22 in v2.6.0; the count is read live from the map, never hardcoded).

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

    # Fallback MUST stay in lockstep with department-floor.HARDCODED_MANDATORY
    # (22 mandatory ids) so a broken install that lost the naming map still
    # enforces the full MANDATORY floor. The 6 universal-primary verticals are NOT
    # in this list - they carry their OWN broken-install fallback in
    # _universal_primary_ids() (_HARDCODED_UNIVERSAL_PRIMARY), so the combined floor
    # still degrades to the full 22 + 6 = 28, never to 22 (and never to the older
    # stale 16). The full shipped role catalog is tracked separately in
    # templates/role-library/_index.json - do not confuse it with the 28 floor.
    canonical_ids = list(mandatory.keys()) or [
        "marketing", "sales", "billing-finance", "customer-support",
        "web-development", "app-development", "graphics", "video", "audio",
        "research", "communications", "crm", "openclaw-maintenance", "legal",
        "social-media", "paid-advertisement", "personal-assistant",
        "general-task", "project-architecture-office", "bugs", "healer",
        "quality-control",
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

    PROVENANCE-GATED DECLINE MODEL (v10.16.26+):
    A decline MUST carry an explicit, attributable owner-decision record.
    The default is NO decline — any decline without provenance is IGNORED and
    emits a loud stderr warning so it surfaces in logs and the prover output.

    Accepted forms (either is sufficient):
      1. build_state["canonicalReconciliation"]["decisions"][cid] is the OBJECT
         form {decision: "no", source: "owner-interview"|"owner-explicit",
         decidedAt: <iso>, decidedBy: <id>} — all four fields required.
      2. build_state["canonicalReconciliation"]["ownerDeclineConfirmed"] == True
         (an operator-level gate that marks the entire block as owner-confirmed)
         combined with decisions[cid] == "no" (string form also accepted when
         the block-level flag is present, for backward compatibility).
      3. build_state["declinedDepartments"] entries are IGNORED unless accompanied
         by build_state["canonicalReconciliation"]["ownerDeclineConfirmed"] == True.

    BACKWARD COMPATIBILITY: bare string "no" without ownerDeclineConfirmed AND
    bare declinedDepartments[] without ownerDeclineConfirmed are REJECTED with
    a warning. This closes the fabrication vector: any actor that drops a bare
    string into decisions[cid]='no' or declinedDepartments[] without the
    owner-confirmed gate can no longer shrink the floor silently.

    WHY: a discovered fleet floor flag revealed that a build-state-level fabricated
    canonicalReconciliation block (declinedDepartments / intentionalScope
    written ad hoc by the closeout/finisher agent) silently shrank the floor
    because this reader imposed ZERO provenance requirement. Fix: fail-safe to
    the LARGER floor when provenance is absent.

    Issue #2 fix: this now DELEGATES to the shared canonical_decline.py reader so
    the ids returned are NORMALIZED (norm(): lowercase, strip non-alphanumerics)
    in the SAME space department-floor.py uses. Callers MUST therefore compare
    with _decline_norm(cid) — a raw 'billing-finance' will NOT match the
    normalized 'billingfinance' key. The provenance rule is unchanged; only the
    id space (now normalized, single source of truth) is.
    """
    return _shared_canonical_decline_set(build_state)


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


# ============================================================
# OWNER-CONSENT GATE (G1-FAB-ENFORCE) — anti-fabrication enforcement
# ============================================================
# The non-interactive build path (load_non_interactive_config -> build_from_config)
# synthesizes a Q/A transcript from config (workforce-interview-answers.md) and
# stamps interviewComplete=true. That is ONLY legitimate when EITHER (a) a genuine
# conversational interview already produced a real transcript, OR (b) the owner
# EXPLICITLY opted into a self-setup / fast (decline-the-interview) mode. Without
# one of those, recording config as "client answers" FABRICATES results the client
# never gave. This gate enforces the SKILL.md prose ("never fabricate — client words
# only") in code: no consent proof AND no genuine transcript => REFUSE the build
# (fail-safe: blocking a build is always preferable to fabricating one).

# Header stamped onto the synthetic answers file written by build_from_config. Used
# both at the write site AND by the gate / QC to detect a fabricated transcript.
NON_INTERACTIVE_ANSWERS_HEADER = "# Workforce Interview Answers (Non-Interactive)"

# Exit code emitted when the build is refused for missing owner consent. Distinct
# from the generic exit(1) so callers / CI can branch on "interview pending".
EXIT_INTERVIEW_PENDING = 87

# Exit code emitted when the build is refused because the Phase 5.5 per-department
# decision map is INCOMPLETE (Issue #3). Distinct from EXIT_INTERVIEW_PENDING so
# callers / CI can branch on "reconciliation pending" (interview happened but not
# every canonical/custom dept has a provenanced yes/no/later decision — the
# structural under-recorded-interview scenario where an under-recorded interview silently unions the
# full floor).
EXIT_RECONCILIATION_PENDING = 88

# Decision tokens that count as an EXPLICIT owner opt-in to a self-setup / fast
# (decline-the-interview) build. Anything else is rejected.
_CONSENT_OPT_IN_DECISIONS = frozenset({
    "self-setup", "self_setup", "selfsetup",
    "fast", "fast-mode", "fast_mode", "fastmode",
    "decline-interview", "decline_interview", "skip-interview", "skip_interview",
    "opt-in", "opt_in", "optin",
})


def _validate_owner_consent(config, build_state):
    """
    Validate a session-bound ownerConsent record using the SAME provenance rule as
    the decline-path validator (_canonical_decline_set, lines ~720-733): every
    required field must be present and truthy.

    Required fields: decision, source, decidedAt, decidedBy, sessionId.
    The decision must be an explicit opt-in to self-setup / fast mode
    (_CONSENT_OPT_IN_DECISIONS). The record may live in config["ownerConsent"] or
    build_state["ownerConsent"]. config takes precedence.

    Returns (ok: bool, reason: str, consent: dict|None). Never raises.
    """
    required = ("decision", "source", "decidedAt", "decidedBy", "sessionId")
    consent = None
    if isinstance((config or {}).get("ownerConsent"), dict):
        consent = config["ownerConsent"]
    elif isinstance((build_state or {}).get("ownerConsent"), dict):
        consent = build_state["ownerConsent"]
    if not isinstance(consent, dict):
        return (False,
                "no ownerConsent record present "
                "(need {decision,source,decidedAt,decidedBy,sessionId})",
                None)
    missing = [k for k in required if not consent.get(k)]
    if missing:
        return (False,
                f"ownerConsent missing/empty fields: {', '.join(missing)}",
                consent)
    decision = str(consent.get("decision", "")).strip().lower()
    if decision not in _CONSENT_OPT_IN_DECISIONS:
        return (False,
                f"ownerConsent.decision='{decision}' is not an explicit self-setup/fast "
                f"opt-in (expected one of: {', '.join(sorted(_CONSENT_OPT_IN_DECISIONS))})",
                consent)
    return (True, "ok", consent)


def _genuine_interview_answers_file():
    """
    Return the path of a GENUINE conversational-interview transcript if one exists,
    else None.

    Genuine = >=3 real **Q:** blocks, size > 512 bytes, and NOT bearing the
    non-interactive synthetic header (so a previously-fabricated transcript does NOT
    count). Deliberately IGNORES the bare interviewComplete flag — a flag is not
    proof and the fabricating path sets it too. This closes the re-run vector where
    a prior synthetic build would otherwise be read back as a "real" interview.
    """
    home = os.path.expanduser("~")
    candidates = []
    bs = _load_build_state()
    recorded = (bs.get("interviewProgress") or {}).get("answersFilePath")
    if recorded:
        candidates.append(str(recorded))
    if COMPANY_DISCOVERY_DIR:
        candidates.append(os.path.join(COMPANY_DISCOVERY_DIR, "workforce-interview-answers.md"))
    for base in ("/data/.openclaw/workspace", os.path.join(home, ".openclaw", "workspace")):
        candidates.append(os.path.join(base, "company-discovery", "workforce-interview-answers.md"))
    for cand in candidates:
        if not os.path.isfile(cand):
            continue
        try:
            size = os.path.getsize(cand)
            text = open(cand, errors="ignore").read()
        except OSError:
            continue
        if NON_INTERACTIVE_ANSWERS_HEADER in text:
            continue  # synthetic / fabricated transcript — does NOT count as genuine
        q_count = len([ln for ln in text.splitlines() if ln.strip().startswith("**Q:**")])
        if q_count >= 3 and size > 512:
            return cand
    return None


def _refuse_interview_pending(reason, option):
    """
    Fail-safe: no consent proof AND no genuine interview => REFUSE the build.

    Writes status:INTERVIEW_PENDING to interview-handoff.md (best-effort), records
    interviewBuildStatus in build-state (additive), and exits non-zero. NEVER writes
    interviewComplete=true. This is the "no consent proof = no build" guarantee.
    """
    msg = (
        "[FABRICATION-GUARD] REFUSING build: no genuine interview transcript and no "
        f"valid owner consent.\n  Reason: {reason}\n  option={option!r}\n"
        "  A non-interactive build may proceed ONLY with (a) a real conversational "
        "interview transcript (>=3 Q/A, not the synthetic header), or (b) an explicit "
        "ownerConsent{decision,source,decidedAt,decidedBy,sessionId} opting into "
        "self-setup/fast mode. Fabricating client answers is forbidden."
    )
    print(msg, file=sys.stderr)
    print(
        "INTERVIEW_NOT_COMPLETE: build refused — AI Workforce interview not completed yet "
        "(no genuine transcript / consent).",
        file=sys.stderr,
    )

    # interview-handoff.md (best-effort; the non-zero exit is the hard guarantee).
    try:
        discovery_dir = _ensure_company_discovery_dir()
    except Exception:  # noqa: BLE001
        discovery_dir = None
    if not discovery_dir:
        try:
            discovery_dir = os.path.dirname(_build_state_path())
            os.makedirs(discovery_dir, exist_ok=True)
        except Exception:  # noqa: BLE001
            discovery_dir = None
    if discovery_dir:
        try:
            handoff_path = os.path.join(discovery_dir, "interview-handoff.md")
            with open(handoff_path, "w") as f:
                f.write("# Interview Handoff\n")
                f.write(f"## Last Updated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n")
                f.write("status: INTERVIEW_PENDING\n\n")
                f.write(f"## Option Selected: {option}\n\n")
                f.write("## Build refused (fabrication guard):\n")
                f.write(f"{reason}\n\n")
                f.write("The owner must EITHER complete the interview (>=3 real Q/A) OR "
                        "record an explicit ownerConsent self-setup/fast opt-in "
                        "({decision,source,decidedAt,decidedBy,sessionId}) before the "
                        "non-interactive build can run.\n")
            print(f"[FABRICATION-GUARD] Wrote status:INTERVIEW_PENDING -> {handoff_path}",
                  file=sys.stderr)
        except OSError as e:
            print(f"[FABRICATION-GUARD] Could not write handoff: {e}", file=sys.stderr)

    # Record build-state status (additive; NEVER sets interviewComplete).
    try:
        path = _build_state_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        state = _load_build_state()
        state["interviewBuildStatus"] = "INTERVIEW_PENDING"
        state["interviewBuildRefusedReason"] = reason
        state["interviewBuildRefusedAt"] = datetime.now().isoformat()
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
    except OSError as e:
        print(f"[FABRICATION-GUARD] Could not record interviewBuildStatus: {e}", file=sys.stderr)

    sys.exit(EXIT_INTERVIEW_PENDING)


# Broken-install UNIVERSAL-PRIMARY fallback - the 6 universal-primary vertical-pack
# department ids (one per pack flagged universal_primary=true in
# department-naming-map.json v2.6.1). SAFETY NET ONLY: consulted solely when the
# live map yields NO universal primaries (map missing / unreadable / corrupt) so a
# broken install still expects the FULL 22 + 6 = 28 floor instead of silently
# degrading to 22 and dropping every universal-primary vertical. MUST stay in
# lockstep with department-naming-map.json and
# department-floor.HARDCODED_UNIVERSAL_PRIMARY. On a healthy install the live
# derivation in _universal_primary_ids() returns the 6 real ids and this is never used.
_HARDCODED_UNIVERSAL_PRIMARY = [
    "presentations", "scheduling-dispatch", "logistics-fulfillment",
    "engineering", "account-management", "podcast",
]


def _universal_primary_ids():
    """
    Return the list of universal-primary vertical-pack department ids — one per
    pack that EXPLICITLY marks a dept universal_primary=true. Mirrors
    department-floor.universal_primary_vertical_departments and
    list-canonical-departments.get_universal_primaries so all callers agree.
    NO depts[0] fallback (v2.6.1): a pack with no flagged dept contributes none.

    BROKEN-INSTALL SAFETY NET: if the live map is unreadable and this derivation
    comes back EMPTY, the result falls back to _HARDCODED_UNIVERSAL_PRIMARY (the 6
    ids) so the expected floor stays 22 + 6 = 28, never silently 22. This mirrors
    load_canonical_floor()'s hardcoded-mandatory fallback and department-floor's
    HARDCODED_UNIVERSAL_PRIMARY. Distinct from the removed depts[0] auto-promotion:
    it triggers ONLY on a broken/missing map, never on a healthy install.
    """
    packs = _load_vertical_packs()
    ids = []
    seen = set()
    for _pack_id, pack in (packs or {}).items():
        if not isinstance(pack, dict):
            continue
        for dept in pack.get("auto_add_departments", []) or []:
            if isinstance(dept, dict) and dept.get("universal_primary"):
                did = dept.get("id")
                if did and did not in seen:
                    seen.add(did)
                    ids.append(did)
                break
    # Fail-safe to the LARGER floor: empty (map unreadable) -> hardcoded 6.
    return ids or list(_HARDCODED_UNIVERSAL_PRIMARY)


def _expected_decision_ids(departments_config):
    """
    Issue #3: the full set of department ids that MUST carry a provenanced
    yes/no/later decision before the canonical floor is unioned in:
        mandatory canonical + universal-primary verticals + client customs.
    Returns a list of raw ids (the caller normalizes for comparison).
    """
    floor = load_canonical_floor()
    mandatory = list(floor.keys())
    universals = _universal_primary_ids()
    # Customs = enabled departments_config entries that are NOT a canonical id
    # (under id/alias/variant). Customs are included here for the audit/receipt
    # picture; the coverage GATE treats a configured custom as implicit-yes (owner
    # intent) and only hard-requires recorded decisions for the auto-unioned
    # canonical/universal floor — see _enforce_decision_coverage_or_refuse.
    canonical_norm = {_decline_norm(c) for c in mandatory}
    for c in mandatory:
        canonical_norm.add(_decline_norm(CANONICAL_ID_ALIASES.get(c, c)))
        for v in CANONICAL_VARIANT_SLUGS.get(c, []):
            canonical_norm.add(_decline_norm(v))
    for u in universals:
        canonical_norm.add(_decline_norm(u))
    customs = [
        did for did, dcfg in (departments_config or {}).items()
        if (dcfg or {}).get("enabled", True) and _decline_norm(did) not in canonical_norm
    ]
    # De-dup preserving order.
    out = []
    seen = set()
    for did in mandatory + universals + customs:
        n = _decline_norm(did)
        if n not in seen:
            seen.add(n)
            out.append(did)
    return out


def _refuse_reconciliation_pending(missing_ids, rejections=None):
    """
    Issue #3 fail-closed: the Phase 5.5 decision map is INCOMPLETE (one or more
    canonical/universal/custom depts have no provenanced yes/no/later decision).
    REFUSE the build rather than silently union the full floor (the structural under-recorded-interview scenario).

    Mirrors _refuse_interview_pending: writes a RECONCILIATION_PENDING handoff,
    ledgers the coverage gap + any rejected declines into build-state (additive;
    NEVER stamps interviewComplete/buildCompletedAt), and exits with a distinct
    code so callers/CI can branch on it.
    """
    rejections = rejections or []
    missing_ids = sorted(set(missing_ids))
    msg = (
        "[DECISION-COVERAGE] REFUSING build: the per-department decision map is "
        "INCOMPLETE. Every mandatory canonical, universal-primary vertical, and "
        "custom department must carry a provenanced yes/no/later decision (recorded "
        "via scripts/record-dept-decision.sh) BEFORE the canonical floor is built. "
        "Building now would silently union the full floor against the owner's intent "
        "(the silent over-provision scenario).\n"
        f"  Missing decisions ({len(missing_ids)}): {', '.join(missing_ids)}"
    )
    if rejections:
        msg += (
            f"\n  Rejected (un-provenanced) declines ({len(rejections)}): "
            + ", ".join(f"{r.get('id')} [{r.get('reason')}]" for r in rejections)
        )
    print(msg, file=sys.stderr)
    print(
        "RECONCILIATION_NOT_COMPLETE: build refused — per-department decisions "
        "incomplete (record every dept's yes/no/later, then re-run).",
        file=sys.stderr,
    )

    # RECONCILIATION_PENDING handoff (best-effort; the non-zero exit is the guarantee).
    try:
        discovery_dir = _ensure_company_discovery_dir()
    except Exception:  # noqa: BLE001
        discovery_dir = None
    if not discovery_dir:
        try:
            discovery_dir = os.path.dirname(_build_state_path())
            os.makedirs(discovery_dir, exist_ok=True)
        except Exception:  # noqa: BLE001
            discovery_dir = None
    if discovery_dir:
        try:
            handoff_path = os.path.join(discovery_dir, "interview-handoff.md")
            with open(handoff_path, "w") as f:
                f.write("# Interview Handoff\n")
                f.write(f"## Last Updated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n")
                f.write("status: RECONCILIATION_PENDING\n\n")
                f.write("## Build refused (decision-coverage gate):\n")
                f.write(f"Missing provenanced decisions for: {', '.join(missing_ids)}\n\n")
                if rejections:
                    f.write("Rejected (un-provenanced) declines:\n")
                    for r in rejections:
                        f.write(f"- {r.get('id')} — {r.get('reason')}\n")
                    f.write("\n")
                f.write("Record each missing decision with "
                        "`scripts/record-dept-decision.sh --dept <id> --decision yes|no|later "
                        "--source owner-interview --by <ownerId> --session <sessionId>`, then "
                        "re-run the build.\n")
            print(f"[DECISION-COVERAGE] Wrote status:RECONCILIATION_PENDING -> {handoff_path}",
                  file=sys.stderr)
        except OSError as e:
            print(f"[DECISION-COVERAGE] Could not write handoff: {e}", file=sys.stderr)

    # Ledger the coverage gap + rejected declines into build-state (Bulletproofing b;
    # additive; NEVER sets interviewComplete / buildCompletedAt).
    try:
        path = _build_state_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        state = _load_build_state()
        state["reconciliationBuildStatus"] = "RECONCILIATION_PENDING"
        state["decisionCoverage"] = {
            "complete": False,
            "missing": missing_ids,
            "refusedAt": datetime.now().isoformat(),
        }
        if rejections:
            state["declineRejections"] = rejections
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
    except OSError as e:
        print(f"[DECISION-COVERAGE] Could not record decisionCoverage: {e}", file=sys.stderr)

    sys.exit(EXIT_RECONCILIATION_PENDING)


def _enforce_decision_coverage_or_refuse(config, departments_config):
    """
    Issue #3 gate. In the GENUINE-INTERVIEW path (not the ownerConsent self-setup/
    fast opt-in, which by design skips the per-dept pitch), require a provenanced
    yes/no/later decision for EVERY expected department id before the floor is
    unioned in. On any gap, REFUSE fail-closed. Fast-mode / self-setup builds are
    exempt (the owner opted out of the interview). Also ledgers rejected declines.
    """
    build_state = _load_build_state()
    # Fast-mode / self-setup: owner explicitly opted out of the per-dept interview.
    consent_ok, _reason, _consent = _validate_owner_consent(config, build_state)
    if consent_ok:
        print("[DECISION-COVERAGE] ownerConsent self-setup/fast build — per-dept "
              "decision-coverage gate SKIPPED (owner opted out of the interview).",
              file=sys.stderr)
        return
    expected = _expected_decision_ids(departments_config)
    missing, _covered = _shared_decision_coverage(build_state, expected)
    # A custom department the owner EXPLICITLY placed in departments_config is
    # itself the owner's recorded intent to build it (implicit YES) — it is never
    # silently auto-unioned like a canonical dept, so it does not need a separate
    # decision record to be "covered". The over-provision hole this gate closes is the
    # AUTO-UNIONED canonical/universal floor being under-recorded; keep the gate
    # focused there and let #8's decline filter handle a declined custom.
    _configured = {_decline_norm(d) for d in (departments_config or {})}
    missing = [m for m in missing if _decline_norm(m) not in _configured]
    rejections = _decline_analyze(build_state, quiet=True)["rejections"]
    if missing or rejections:
        _refuse_reconciliation_pending(missing, rejections=rejections)
    # Coverage complete — ledger the clean verdict (additive).
    try:
        path = _build_state_path()
        state = _load_build_state()
        state["decisionCoverage"] = {
            "complete": True,
            "missing": [],
            "checkedAt": datetime.now().isoformat(),
            "expectedCount": len(expected),
        }
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
    except OSError as e:
        print(f"[DECISION-COVERAGE] Could not record clean decisionCoverage: {e}", file=sys.stderr)
    print(f"[DECISION-COVERAGE] PASS — all {len(expected)} expected departments carry a "
          f"provenanced yes/no/later decision.", file=sys.stderr)


def _collapse_to_canonical(did):
    """Map a department id to its canonical id if it is a known alias/variant slug,
    else return it unchanged. Used so the provisioning receipt compares expected vs
    built in one canonical space (e.g. 'legal-compliance' -> 'legal')."""
    n = _decline_norm(did)
    for c in load_canonical_floor().keys():
        if _decline_norm(c) == n:
            return c
        if _decline_norm(CANONICAL_ID_ALIASES.get(c, c)) == n:
            return c
        for v in CANONICAL_VARIANT_SLUGS.get(c, []):
            if _decline_norm(v) == n:
                return c
    return did


def _write_provisioning_receipt(company_name, selected_departments, config, core_answers):
    """
    Bulletproofing (c): write provisioning-receipt.json with an EXPECTED-SET
    EQUALITY invariant so BOTH over- and under-provisioning fail a gate — not just
    the "at least the floor" checks every existing gate uses.

    EXPECTED = mandatory canonical + universal-primary verticals + keyword vertical
    extras that were actually added + accepted customs + 'later's (build-now),
    MINUS provenance-declines MINUS merged-away customs.
    BUILT    = the department set actually assembled (selected_departments).

    equalityOk is TRUE only when EXPECTED == BUILT (in one canonical space), which
    means: no declined dept was built (the residual over-provision bug), no floor dept
    was dropped, customs were honored, and merged customs did not duplicate.
    prove-zhe.py asserts this equality; prove-handover.sh gates handover on it.
    Best-effort: never raises (a receipt-write failure must not fail the build).
    """
    try:
        build_state = _load_build_state()
        view = _decline_analyze(build_state, quiet=True)
        declined = view["declined"]          # normalized
        later = view["later"]                # normalized (informational — build-now)

        mandatory = list(load_canonical_floor().keys())
        universals = _universal_primary_ids()

        # Vertical additions actually made (universal + keyword extras), already
        # declined-filtered by apply_vertical_packs.
        vpacks = build_state.get("verticalPacks", {}) or {}
        added_vertical_ids = [d.get("id") for d in (vpacks.get("addedDepartments") or [])
                              if isinstance(d, dict) and d.get("id")]

        # Merged-away customs (folded into a canonical survivor by apply_semantic_merges).
        recon = build_state.get("canonicalReconciliation", {}) or {}
        merged = recon.get("semanticMerges", {}) or {}
        merged_away = {_decline_norm(m.get("custom_id"))
                       for m in (merged.get("merged") or [])
                       if isinstance(m, dict) and m.get("custom_id")}

        departments_config = config.get("departments", {}) or {}
        canonical_norm = set()
        for c in mandatory:
            canonical_norm.add(_decline_norm(c))
            canonical_norm.add(_decline_norm(CANONICAL_ID_ALIASES.get(c, c)))
            for v in CANONICAL_VARIANT_SLUGS.get(c, []):
                canonical_norm.add(_decline_norm(v))
        for u in universals:
            canonical_norm.add(_decline_norm(u))
        accepted_customs = [
            did for did, dcfg in departments_config.items()
            if (dcfg or {}).get("enabled", True)
            and _decline_norm(did) not in canonical_norm
            and _decline_norm(did) not in declined
            and _decline_norm(did) not in merged_away
        ]

        def _cnorm(x):
            return _decline_norm(_collapse_to_canonical(x))

        expected = set()
        for x in mandatory + universals + added_vertical_ids:
            if _cnorm(x) not in declined:
                expected.add(_cnorm(x))
        for x in accepted_customs:
            expected.add(_cnorm(x))

        built = {_cnorm(d) for d in selected_departments}

        missing_from_built = sorted(expected - built)         # under-provision
        declined_but_built = sorted(built & declined)          # OVER-provision (declined-but-built)
        extra_beyond_expected = sorted(built - expected)       # unexplained extras
        equality_ok = not (missing_from_built or declined_but_built or extra_beyond_expected)

        reason = "built department set == expected set (mandatory + universal-primary + " \
                 "vertical extras + accepted customs + laters, minus declines/merges)"
        if not equality_ok:
            bits = []
            if declined_but_built:
                bits.append("OVER-PROVISION: declined depts built: " + ", ".join(declined_but_built))
            if missing_from_built:
                bits.append("UNDER-PROVISION: expected depts missing: " + ", ".join(missing_from_built))
            if extra_beyond_expected:
                bits.append("UNEXPECTED extras: " + ", ".join(extra_beyond_expected))
            reason = " | ".join(bits)

        receipt = {
            "schema": "provisioning-receipt/v1",
            "company": company_name,
            "generatedAt": datetime.now().isoformat(),
            "declined": sorted(declined),
            "later": sorted(later),
            "acceptedCustoms": sorted({_cnorm(c) for c in accepted_customs}),
            "mergedAwayCustoms": sorted(merged_away),
            "verticalAdded": sorted({_cnorm(v) for v in added_vertical_ids}),
            "expectedSet": sorted(expected),
            "builtSet": sorted(built),
            "expectedCount": len(expected),
            "builtCount": len(built),
            "missingFromBuilt": missing_from_built,
            "declinedButBuilt": declined_but_built,
            "extraBeyondExpected": extra_beyond_expected,
            "equalityOk": equality_ok,
            "reason": reason,
        }

        # Write to the ZHC company folder (canonical) AND, when resolvable, to the
        # workspace root so the receipt-backed gates (prove-zhe / prove-handover)
        # find it next to the on-disk departments dir.
        targets = []
        if COMPANY_DIR:
            targets.append(os.path.join(COMPANY_DIR, "provisioning-receipt.json"))
        try:
            _ws = os.path.join(WORKSPACE_ROOT, "provisioning-receipt.json")
            if os.path.isdir(WORKSPACE_ROOT):
                targets.append(_ws)
        except Exception:  # noqa: BLE001
            pass
        for t in targets:
            try:
                tmp = t + ".tmp"
                with open(tmp, "w") as f:
                    json.dump(receipt, f, indent=2)
                os.replace(tmp, t)
                print(f"[PROVISIONING-RECEIPT] wrote {t} (equalityOk={equality_ok})", file=sys.stderr)
            except OSError as e:
                print(f"[PROVISIONING-RECEIPT] could not write {t}: {e}", file=sys.stderr)

        # Ledger the verdict into build-state (additive).
        try:
            path = _build_state_path()
            state = _load_build_state()
            state["provisioningReceipt"] = {
                "equalityOk": equality_ok,
                "expectedCount": len(expected),
                "builtCount": len(built),
                "declinedButBuilt": declined_but_built,
                "missingFromBuilt": missing_from_built,
                "generatedAt": receipt["generatedAt"],
            }
            with open(path, "w") as f:
                json.dump(state, f, indent=2)
        except OSError as e:
            print(f"[PROVISIONING-RECEIPT] could not ledger verdict: {e}", file=sys.stderr)

        if not equality_ok:
            print(f"[PROVISIONING-RECEIPT] EQUALITY FAILED — {reason}", file=sys.stderr)
        return receipt
    except Exception as e:  # noqa: BLE001 — a receipt failure must NEVER fail the build
        print(f"[PROVISIONING-RECEIPT] WARN: receipt generation failed: {e}", file=sys.stderr)
        return None


def _enforce_consent_or_refuse(config):
    """
    G1-FAB-ENFORCE gate. Permit the non-interactive build ONLY when a genuine
    conversational interview already exists OR an explicit owner consent record is
    present. Otherwise REFUSE (write INTERVIEW_PENDING handoff, exit non-zero).

    Called at the TOP of both load_non_interactive_config() and build_from_config()
    so the build is blocked BEFORE any synthetic transcript is written or
    interviewComplete=true is stamped. Idempotent: it passes or refuses consistently.
    """
    option = str((config or {}).get("option", "")).strip()
    genuine = _genuine_interview_answers_file()
    if genuine:
        print(f"[FABRICATION-GUARD] Genuine interview transcript found ({genuine}); "
              f"build permitted (full-interview path).", file=sys.stderr)
        return
    ok, reason, consent = _validate_owner_consent(config, _load_build_state())
    if ok:
        print(f"[FABRICATION-GUARD] Owner consent verified "
              f"(decision={str(consent.get('decision')).strip().lower()}, "
              f"sessionId={consent.get('sessionId')}); self-setup/fast build permitted.",
              file=sys.stderr)
        return
    _refuse_interview_pending(reason, option)


def _resolve_role_library_index():
    """
    Resolve the repo/skill _index.json (the content-manifest source of truth) so
    the build-state provenance roll-up can copy the dept + SOP source content_shas.
    Mirrors the lookup create_role_workspaces uses (ROLE_LIBRARY_PATH override,
    then the script's own skill dir). Returns (path_or_None, data_or_{}).
    """
    candidates = []
    env_dir = os.environ.get("ROLE_LIBRARY_PATH")
    if env_dir:
        candidates.append(os.path.join(env_dir, "templates", "role-library", "_index.json"))
    here = os.path.dirname(os.path.abspath(__file__))
    skill_dir = os.path.dirname(here)
    candidates.append(os.path.join(skill_dir, "templates", "role-library", "_index.json"))
    for p in candidates:
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return p, json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
    return None, {}


def _flush_artifact_provenance_to_state():
    """
    Flush the per-role _ARTIFACT_PROVENANCE accumulator into
    .workforce-build-state.json under the new `artifactProvenance` key, alongside
    the dept + SOP source content_shas copied from the role-library manifest.

    Shape (the FAST PATH detect-stale-artifacts.py reads):
        artifactProvenance: {
          manifestVersion: "<_index.json version the build read>",
          manifestContentManifestSchema: "1.0",
          builtAt: "<iso>",
          roles: { "<dept>/<slug>": {source_content_sha, source_content_version,
                                     instantiatedAt, sourcePath} },
          depts: { "<dept>": {source_content_sha} },
          sops:  { "<dept>/<sop-slug>": {source_content_sha, source_content_version,
                                          sourcePath} },
          personas: { "<persona-slug>": {source_content_sha, source_content_version,
                                          sourcePath} },   # shared pool (not per-dept)
          personaSetSha: "sha256:<sha over the sorted persona shas>"
        }

    Idempotent + additive: merges into the existing build-state, never clobbers
    unrelated keys. Called once at the end of the build. Never raises.
    """
    if not _ARTIFACT_PROVENANCE:
        return  # nothing instantiated from the library this run
    path = _build_state_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        idx_path, idx = _resolve_role_library_index()
        manifest_version = idx.get("version")
        cm = idx.get("content_manifest") or {}
        depts_manifest = idx.get("departments") or {}
        sops_manifest = idx.get("sops") or []
        personas_manifest = idx.get("personas") or []

        # dept roll-up: only the depts that actually had a role instantiated.
        touched_depts = {k.split("/", 1)[0] for k in _ARTIFACT_PROVENANCE}
        depts_out = {}
        for did in sorted(touched_depts):
            d = depts_manifest.get(did)
            if isinstance(d, dict) and d.get("content_sha"):
                depts_out[did] = {"source_content_sha": d["content_sha"]}

        # sop roll-up: record every dept-level SOP for a touched dept.
        sops_out = {}
        for s in sops_manifest:
            if not isinstance(s, dict):
                continue
            if s.get("dept") in touched_depts:
                key = f"{s.get('dept')}/{s.get('slug')}"
                sops_out[key] = {
                    "source_content_sha": s.get("content_sha"),
                    "source_content_version": s.get("content_version"),
                    "sourcePath": s.get("path"),
                }

        # persona roll-up: personas are a SHARED pool (not per-dept-rendered like
        # roles), so a client that built any department against this library built
        # against the WHOLE persona set. Record every library persona's source
        # content_sha keyed by bare slug (detect-stale normalizes to persona/<slug>),
        # plus a library-level personaSetSha = sha over the sorted persona shas so a
        # single value captures "which persona-set version this client built against".
        personas_out = {}
        _pset_lines = []
        for p in personas_manifest:
            if not isinstance(p, dict):
                continue
            pslug = p.get("slug")
            psha = p.get("content_sha")
            if not (pslug and psha):
                continue
            personas_out[pslug] = {
                "source_content_sha": psha,
                "source_content_version": p.get("content_version"),
                "sourcePath": p.get("path"),
            }
            _pset_lines.append(f"{pslug}\t{psha}")
        persona_set_sha = None
        if _pset_lines:
            payload = "\n".join(sorted(_pset_lines)).encode("utf-8")
            persona_set_sha = "sha256:" + hashlib.sha256(payload).hexdigest()

        state = _load_build_state()
        ap = {
            "manifestVersion": manifest_version,
            "manifestContentManifestSchema": cm.get("manifest_schema"),
            "builtAt": datetime.now().isoformat(),
            "roles": dict(_ARTIFACT_PROVENANCE),
            "depts": depts_out,
            "sops": sops_out,
            "personas": personas_out,
            "personaSetSha": persona_set_sha,
        }
        state["artifactProvenance"] = ap
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
        print(f"[PROVENANCE] Wrote artifactProvenance ({len(ap['roles'])} roles, "
              f"{len(depts_out)} depts, {len(sops_out)} sops, "
              f"{len(personas_out)} personas) to {path}",
              file=sys.stderr)
    except OSError as e:
        print(f"[PROVENANCE WARNING] Could not write artifactProvenance to {path}: {e}",
              file=sys.stderr)


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


# ── v12.3.1: Interview state persistence helpers ──────────────────────────────

def _write_interview_complete_to_state(answers_path=None):
    """
    Write interviewComplete=true + interviewCompletedAt + interviewProgress.lastQuestionAt
    into .workforce-build-state.json.

    Called by build_from_config() after the answers file is successfully written
    so that EVERY check that reads build-state (verify-zhc-standard.sh,
    interview-nudge-cron.sh, resume-workforce-build.sh) sees the correct flag.
    Idempotent: if interviewComplete is already true, it only refreshes the path.

    Also records the absolute path of the answers file in
    interviewProgress.answersFilePath so verify_interview_complete() and any
    future audit script can find the populated file directly without guessing.
    """
    path = _build_state_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        state = _load_build_state()
        now = datetime.now().isoformat()
        state["interviewComplete"] = True
        state["interviewCompletedAt"] = state.get("interviewCompletedAt") or now
        # P1-3: persist the company slug into build-state so EVERY downstream reader
        # (Skill 32 run-full-install.sh, update-skills.sh, the Command Center repo
        # scripts) can resolve it. Previously COMPANY_SLUG only landed in
        # company-config.json, so state-file readers resolved empty and the CC install
        # ran with an empty slug. resolve_company_paths() (called at the top of
        # build_from_config, before this) has already populated the COMPANY_SLUG global.
        # Write the canonical key `companySlug` AND, for one transition release, the
        # legacy alias `clientSlug` with the SAME value so both reader generations work.
        if COMPANY_SLUG:
            state["companySlug"] = COMPANY_SLUG
            state["clientSlug"] = COMPANY_SLUG  # transition alias (P1-3); drop once all readers use `.companySlug // .clientSlug`
        progress = state.get("interviewProgress") or {}
        if not isinstance(progress, dict):
            progress = {}
        progress.setdefault("lastQuestionAt", now)
        progress["interviewComplete"] = True
        if answers_path:
            progress["answersFilePath"] = str(answers_path)
        state["interviewProgress"] = progress
        # Set interviewQc status to "pending" if not already evaluated
        if not isinstance(state.get("interviewQc"), dict):
            state["interviewQc"] = {"status": "pending"}
        elif state["interviewQc"].get("status") not in ("pass", "needs-review"):
            state["interviewQc"]["status"] = "pending"
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
        print(f"[INTERVIEW] Wrote interviewComplete=true to {path}", file=sys.stderr)
        if answers_path:
            print(f"[INTERVIEW] answers file path recorded: {answers_path}", file=sys.stderr)
    except OSError as e:
        print(f"[INTERVIEW WARNING] Could not write interviewComplete to {path}: {e}", file=sys.stderr)


def verify_interview_complete(answers_path=None):
    """
    v12.3.1: Determine interview completeness from the PRESENCE OF REAL ANSWERS
    in the populated file - not just a flag in build-state.

    The blank template (workforce-interview-answers.md shipped with the skill)
    contains only a header and placeholder HTML comment - no **Q:**/**A:** pairs.
    A real interview produces at least 3 **Q:**/**A:** pairs (company name,
    industry, and at least one department question).

    Checks (in order):
      1. build-state interviewComplete == true  (fast path - set by this module)
      2. answers file at answers_path (or auto-discovered) has >= 3 **Q:** blocks
         and file size > 512 bytes.
      3. A skill23-*-workforce-proposal.md file >= 4000 bytes exists (legacy path).

    Returns a dict:
      {
        "complete": bool,
        "method": str,         # "flag" | "answers_file" | "proposal_doc" | "none"
        "answers_path": str|None,
        "question_count": int,
        "file_size": int,
        "flag_set": bool,
      }
    """
    result = {
        "complete": False,
        "method": "none",
        "answers_path": None,
        "question_count": 0,
        "file_size": 0,
        "flag_set": False,
    }

    # Check 1: build-state flag
    state = _load_build_state()
    flag = bool(state.get("interviewComplete"))
    result["flag_set"] = flag
    if flag:
        # G1-FAB-ENFORCE: a bare interviewComplete flag is NOT proof of a real
        # interview (the fabricating path sets it too). Record it PROVISIONALLY;
        # do NOT mark complete until it is corroborated by >=3 real Q/A blocks
        # (Check 2 / Check 3) or a valid ownerConsent record (corroboration gate
        # at the end of this function). Never trust a bare flag.
        result["method"] = "flag"
        # Below we try to confirm the answers file exists with real content.

    # Check 2: answers file with real content
    # Candidate paths: caller-supplied > build-state recorded path > standard discovery dirs
    candidates = []
    if answers_path:
        candidates.append(str(answers_path))
    recorded = (state.get("interviewProgress") or {}).get("answersFilePath")
    if recorded:
        candidates.append(str(recorded))
    # Standard discovery directory candidates (mirrors _ensure_company_discovery_dir)
    home = os.path.expanduser("~")
    for base in (
        "/data/.openclaw/workspace",
        os.path.join(home, ".openclaw", "workspace"),
    ):
        candidates.append(os.path.join(base, "company-discovery", "workforce-interview-answers.md"))

    for cand in candidates:
        if not os.path.isfile(cand):
            continue
        try:
            size = os.path.getsize(cand)
            text = open(cand, errors="ignore").read()
        except OSError:
            continue
        # Count real Q-blocks (the template has zero; real answers have ≥ 1 per question)
        q_count = len([ln for ln in text.splitlines() if ln.strip().startswith("**Q:**")])
        if q_count >= 3 and size > 512:
            result["complete"] = True
            result["method"] = "answers_file"
            result["answers_path"] = cand
            result["question_count"] = q_count
            result["file_size"] = size
            return result
        elif q_count > 0:
            # Partial - file has SOME answers but fewer than the minimum.
            result["answers_path"] = cand
            result["question_count"] = q_count
            result["file_size"] = size
            # Don't override flag-based completion if the flag is already set.
            if not flag:
                result["complete"] = False
                result["method"] = "partial_answers"
            return result

    # Check 3: legacy proposal doc (≥ 4000 bytes)
    for pattern_base in (
        os.path.join(home, "clawd", "zero-human-company"),
        "/data/.openclaw/workspace",
        os.path.join(home, ".openclaw", "workspace"),
    ):
        import glob
        for doc in glob.glob(os.path.join(pattern_base, "**", "skill23-*-workforce-proposal.md"), recursive=True):
            try:
                if os.path.getsize(doc) >= 4000:
                    if not result["complete"]:
                        result["complete"] = True
                        result["method"] = "proposal_doc"
                        result["answers_path"] = doc
                    return result
            except OSError:
                continue

    # G1-FAB-ENFORCE corroboration gate: the flag was set but Check 2/Check 3 did
    # NOT already return complete from real evidence. A bare flag is never trusted —
    # require >=3 real Q/A blocks OR a valid ownerConsent record, else REFUSE to
    # report complete (fail-safe against fabricated completion).
    if flag and result["complete"] is not True:
        if result.get("question_count", 0) >= 3:
            result["complete"] = True
            result["method"] = "flag+answers"
        else:
            consent_ok, _creason, _consent = _validate_owner_consent({}, state)
            if consent_ok:
                result["complete"] = True
                result["method"] = "consent"
            else:
                result["complete"] = False
                result["method"] = "flag_rejected_no_evidence"
                print(
                    "[INTERVIEW] interviewComplete flag is set but NO real transcript "
                    "(>=3 Q/A) and NO valid ownerConsent record was found — refusing to "
                    "treat the interview as complete (fail-safe against fabricated "
                    f"completion). reason: {_creason}",
                    file=sys.stderr,
                )

    return result


def reconcile_canonical_floor(selected_departments, core_answers, departments_config):
    """
    Enforce the canonical floor on the client's selected departments.

    Logic (standard-unless-declined):
      final = (all canonical MINUS explicit "no" in build-state) UNION client customs
      (canonical = the 22 mandatory in department-naming-map.json v2.6.0)

    - If a canonicalReconciliation.decisions block exists in build-state, honor
      each explicit "no" (drop that canonical dept) and keep everything else.
    - If NO reconciliation block exists, include all canonical depts (standard)
      and write an auditable canonicalReconciliation.autoIncluded record.
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
        # Issue #2: `declined` is now a NORMALIZED set (shared reader). Compare in
        # the same normalized space so a decline keyed "Video"/"billing_finance"
        # (from a display name / underscore variant) is HONORED, not force-built.
        if _decline_norm(cid) in declined:
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
            "declinedVerticals": record.get("declinedVerticals", []),
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
            "Never invent a department that overlaps a canonical floor department "
            "or another vertical-pack department."
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
                    "Does it overlap or conflict with any canonical floor department or another added department? If so, recommend merge/drop.",
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
    WS-4 (CANONICAL FLOOR STANDARD): auto-add vertical-pack departments.

    Standard set (the mandatory canonical floor, 22) is already applied
    by reconcile_canonical_floor(). This sibling step adds the universal primary
    vertical departments (one per pack that flags one) PLUS keyword-matched extras:

      PHASE 1 - UNIVERSAL PRIMARIES (floor layer, fires for ALL clients):
        A vertical pack exposes a universal primary department ONLY when one of its
        depts is EXPLICITLY marked universal_primary=true in
        department-naming-map.json. There is NO depts[0] fallback (v2.6.1) - a pack
        with no flagged dept (e.g. real-estate, whose listings flag was removed)
        contributes NOTHING here. The 6 flagged primaries are added to EVERY client
        regardless of industry - giving 22+6=28 as the minimum floor (v2.6.1).
        Industry matching does NOT gate these. A universal primary the owner
        explicitly declined in Phase 5.5 (canonicalReconciliation.decisions[id]
        == "no" or declinedDepartments[]) is SKIPPED here so the opt-out is honored
        symmetrically with the mandatory floor.

      PHASE 2 - KEYWORD-MATCHED EXTRAS (flavor on top of the 28 floor):
        Detect which packs match the client's industry/business context via
        auto_add_keywords. For each matching pack, add remaining (non-universal-
        primary) departments to selected_departments. These extras are ADDITIVE
        and do NOT reduce the floor - they push the final count to 28+.

      DE-DUP: all adds are de-duped against (a) the canonical floor under any
        canonical id/alias/variant, (b) a prior universal-primary already added,
        and (c) any dept already added in THIS pass.

      Each added department inherits its base_suggested_roles file so it ships
      with real roles + SOPs (never hard-fails assert_dept_map_resolves).

      Write a McKinsey-style industry-org-design research manifest and an
      auditable verticalPacks record into build-state.

    Returns the mutated selected_departments dict.
    """
    vertical_packs = _load_vertical_packs()
    if not vertical_packs:
        return selected_departments

    # Build the canonical/alias/variant id set so a vertical dept can never
    # shadow a canonical floor department (no overlap with the standard set).
    floor = load_canonical_floor()
    canonical_block = set(floor.keys())
    canonical_block |= {CANONICAL_ID_ALIASES.get(c, c) for c in floor.keys()}
    for c in floor.keys():
        canonical_block |= set(CANONICAL_VARIANT_SLUGS.get(c, []))

    # R2.6 SYMMETRIC OPT-OUT: a universal-primary vertical the owner explicitly
    # declined in Phase 5.5 must be skipped here, exactly as a declined mandatory
    # canonical dept is skipped in reconcile_canonical_floor(). The decline is
    # recorded the same way (canonicalReconciliation.decisions[id] == "no" OR a
    # flat declinedDepartments[] entry) and read by the SAME _canonical_decline_set
    # helper, so the on-disk enforcer (department-floor.declined_set) and this
    # builder stay in lockstep. _norm-style comparison (hyphen/case-insensitive)
    # keeps a decline keyed as e.g. "scheduling_dispatch" matching "scheduling-dispatch".
    _vert_declined_raw = _canonical_decline_set(_load_build_state())
    _vert_declined = {re.sub(r"[^a-z0-9]", "", str(d).lower()) for d in _vert_declined_raw}

    def _is_vertical_declined(did):
        return re.sub(r"[^a-z0-9]", "", str(did).lower()) in _vert_declined

    added_departments = []
    skipped_duplicates = []
    declined_verticals = []
    seen_added = set()

    def _add_dept(dept, pack_id, label=""):
        """Try to add a vertical dept; return True if added, False if skipped."""
        if not isinstance(dept, dict):
            return False
        did = dept.get("id")
        if not did:
            return False
        if _is_vertical_declined(did):
            declined_verticals.append({"id": did, "reason": "owner declined (Phase 5.5)", "pack": pack_id})
            print(f"[VERTICAL] Skipping '{did}' from pack '{pack_id}'{label} - owner explicitly declined.", file=sys.stderr)
            return False
        if did in canonical_block:
            skipped_duplicates.append({"id": did, "reason": "overlaps canonical floor", "pack": pack_id})
            print(f"[VERTICAL] Skipping '{did}' from pack '{pack_id}'{label} - overlaps canonical floor.", file=sys.stderr)
            return False
        if did in selected_departments or did in seen_added:
            skipped_duplicates.append({"id": did, "reason": "already present", "pack": pack_id})
            print(f"[VERTICAL] Skipping '{did}' from pack '{pack_id}'{label} - already present.", file=sys.stderr)
            return False
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
        print(f"[VERTICAL] Added dept '{did}' (pack '{pack_id}'{label}, base roles '{base}').",
              file=sys.stderr)
        return True

    # PHASE 1 - universal primaries: one from every pack that EXPLICITLY flags a
    # dept universal_primary=true. NO depts[0] fallback (v2.6.1): a pack with no
    # flagged dept (now including real-estate, whose `listings` flag was removed)
    # contributes NOTHING to the universal floor here - its depts can only be added
    # via the Phase 2 industry keyword match. This keeps industry-specific depts
    # like `listings` off generic/coaching/consulting floors while explicitly-
    # flagged primaries (e.g. saas/`engineering`) still fire for every client.
    universal_count = 0
    for pack_id, pack in vertical_packs.items():
        if not isinstance(pack, dict):
            continue
        depts = pack.get("auto_add_departments", []) or []
        if not depts:
            continue
        primary = None
        for d in depts:
            if isinstance(d, dict) and d.get("universal_primary"):
                primary = d
                break
        if primary and _add_dept(primary, pack_id, " [universal-primary]"):
            universal_count += 1

    print(f"[VERTICAL] Universal primaries added: {universal_count} of {len(vertical_packs)} packs "
          f"({len(declined_verticals)} declined by owner); "
          f"floor = {len(floor)} mandatory + {universal_count} universal-primary "
          f"= {len(floor) + universal_count}", file=sys.stderr)

    # PHASE 2 - keyword-matched extras (flavor on top of the floor).
    matched_packs = _detect_vertical_packs(core_answers, vertical_packs)
    if not matched_packs:
        print("[VERTICAL] No vertical pack matched the client's industry signal - "
              "no extras beyond the canonical floor.", file=sys.stderr)
    else:
        for pack_id, _hits in matched_packs:
            pack = vertical_packs.get(pack_id, {})
            for dept in pack.get("auto_add_departments", []) or []:
                if not isinstance(dept, dict):
                    continue
                if dept.get("universal_primary"):
                    continue  # Already added in Phase 1.
                _add_dept(dept, pack_id, " [industry-extra]")

    manifest_path = ""
    if added_departments:
        manifest_path = _write_industry_org_design_manifest(matched_packs, added_departments, core_answers)

    _write_vertical_pack_record({
        "detectedPacks": [{"pack": pid, "matchedKeywords": kws} for pid, kws in matched_packs],
        "addedDepartments": added_departments,
        "skippedDuplicates": skipped_duplicates,
        "declinedVerticals": declined_verticals,
        "researchManifest": manifest_path,
    })

    print(f"[VERTICAL] Total vertical depts added: {len(added_departments)} "
          f"({universal_count} universal + {len(added_departments)-universal_count} industry extras), "
          f"{len(skipped_duplicates)} de-duped.", file=sys.stderr)
    return selected_departments


# ============================================================
# CAPABILITY 3 - PER-DEPT CUSTOM ROLES (PRD R2.4)
# ============================================================

def _next_role_number(dept_dir):
    """Return the next free NN- prefix for a new role folder in a dept dir."""
    nums = []
    if os.path.isdir(dept_dir):
        for entry in os.listdir(dept_dir):
            m = re.match(r"^(\d{2})-", entry)
            if m and os.path.isdir(os.path.join(dept_dir, entry)):
                nums.append(int(m.group(1)))
    return (max(nums) + 1) if nums else 1


def materialize_custom_roles(dept_id, dept_info, dept_config, interview_answers):
    """
    CAPABILITY 3 (PRD R2.4): materialize the EXTRA roles the owner asked for in
    THIS department as a build decision - not the post-build add-role.sh path.

    Source of truth (in precedence order):
      1. dept_config["customRoles"]            - per-dept list from the interview config
      2. build-state canonicalReconciliation.customRoles[<dept_id>]  - interview capture
    Each entry is either a string (role title) or a dict:
        {"title": "...", "summary": "...", "permanent": true|false}

    For each requested role NOT already present in the dept (by slug), create a
    role folder with a PENDING how-to.md that carries the SAME one-shot
    library-fill instruction the standard NO_TEMPLATE path uses (so the role is
    materialized identically - never a silent empty stub). Records the
    materialized roles into build-state canonicalReconciliation.customRolesBuilt.

    Returns the list of created role folder paths (may be empty). Idempotent: a
    role whose slug already exists is skipped.
    """
    requested = list(dept_config.get("customRoles", []) or [])
    bs = _load_build_state()
    recon = bs.get("canonicalReconciliation", {}) or {}
    if not requested:
        requested = list((recon.get("customRoles", {}) or {}).get(dept_id, []) or [])

    # CAPABILITY 2 fold-in: if a custom dept was MERGED into THIS canonical dept
    # (canonicalReconciliation.mergedInto[<dept_id>]), the absorbed function ships
    # as a role INSIDE this survivor dept - never as a separate department. Add a
    # representative role for each absorbed custom so its work is materialized here.
    for absorbed in (recon.get("mergedInto", {}) or {}).get(dept_id, []) or []:
        a_name = (absorbed.get("name") or absorbed.get("id") or "").strip()
        if not a_name:
            continue
        title = f"{a_name} Specialist"
        if not any((isinstance(r, dict) and (r.get("title") == title)) or r == title for r in requested):
            requested.append({
                "title": title,
                "summary": (absorbed.get("description")
                            or f"Owner's '{a_name}' function, folded into {dept_info['name']} (Capability 2 merge)."),
                "permanent": False,
            })

    if not requested:
        return []

    dept_dir = os.path.join(DEPARTMENTS_DIR, dept_id)
    if not os.path.isdir(dept_dir):
        print(f"[CUSTOM-ROLE WARNING] dept dir missing for '{dept_id}', cannot add custom roles.", file=sys.stderr)
        return []

    company_name = interview_answers.get("company_name", "the company")
    industry = interview_answers.get("industry", "")
    existing_slugs = set()
    for entry in os.listdir(dept_dir):
        if os.path.isdir(os.path.join(dept_dir, entry)):
            existing_slugs.add(re.sub(r"^\d{2}-", "", entry))

    created = []
    built_records = []
    for item in requested:
        if isinstance(item, dict):
            title = (item.get("title") or item.get("name") or "").strip()
            summary = (item.get("summary") or item.get("description") or "").strip()
            permanent = bool(item.get("permanent", False))
        else:
            title = str(item).strip()
            summary = ""
            permanent = False
        if not title:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        if slug in existing_slugs:
            print(f"[CUSTOM-ROLE] '{title}' already present in '{dept_id}', skipping.", file=sys.stderr)
            continue
        num = _next_role_number(dept_dir)
        folder = f"{num:02d}-{slug}"
        role_dir = os.path.join(dept_dir, folder)
        os.makedirs(role_dir, exist_ok=True)
        how_to_path = os.path.join(role_dir, "how-to.md")
        if not os.path.isfile(how_to_path):
            with open(how_to_path, "w") as f:
                f.write(f"""# {title} - how-to.md  [PENDING - OWNER-REQUESTED CUSTOM ROLE - FILL FROM LIBRARY]

**Department:** {dept_info['name']} ({dept_info.get('emoji', '')})
**Company:** {company_name}
**Industry:** {industry}
**Staffing:** {"permanent specialist" if permanent else "on-call specialist"}
**Owner request:** {summary or "(owner asked for this role during the interview; no extra detail captured)"}
**Status:** PENDING - owner-requested custom role; fill from the nearest role-library template family.

> ONE-SHOT FILL INSTRUCTION (do exactly this, do NOT write a free-form essay):
> 1. Look in `23-ai-workforce-blueprint/templates/role-library/{dept_id}/` for the
>    nearest template family (closest role title). If none, use the closest dept family.
> 2. Copy that template and TOKEN-FILL: company = `{company_name}`, role = `{title}`,
>    department = `{dept_info['name']}`, industry = `{industry}`.
> 3. Keep the template's Section-9 SOP structure intact. If the owner gave a
>    specific procedure for this role (see the dept's owner-procedures.md), fold it
>    into the relevant SOP step.
> 4. Once filled, remove this PENDING header - the role drops off PENDING-SOPS.md.

## What This Role Does

{summary or f"Owner-requested specialist in the {dept_info['name']} department. Materialized as a build decision (Capability 3)."}
""")
        existing_slugs.add(slug)
        created.append(role_dir)
        built_records.append({"dept": dept_id, "title": title, "slug": slug, "permanent": permanent})
        print(f"[CUSTOM-ROLE] Materialized owner-requested role '{title}' in '{dept_id}' ({folder}).", file=sys.stderr)

    if built_records:
        try:
            path = _build_state_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            state = _load_build_state()
            existing = state.get("canonicalReconciliation", {})
            if not isinstance(existing, dict):
                existing = {}
            prior = existing.get("customRolesBuilt", [])
            for r in built_records:
                if not any(x.get("dept") == r["dept"] and x.get("slug") == r["slug"] for x in prior):
                    prior.append(r)
            existing["customRolesBuilt"] = prior
            state["canonicalReconciliation"] = existing
            with open(path, "w") as f:
                json.dump(state, f, indent=2)
        except OSError as e:
            print(f"[CUSTOM-ROLE WARNING] Could not record customRolesBuilt: {e}", file=sys.stderr)

    return created


# ============================================================
# CAPABILITY 4 - PER-DEPT CUSTOM SOPs (PRD R2.5)
# ============================================================

def capture_custom_sops(dept_id, dept_info, dept_config, interview_answers):
    """
    CAPABILITY 4 (PRD R2.5): capture the owner-specific procedures for THIS
    department as a build decision, RESPECTING sop_boundary_gate.py:

      - CANONICAL dept (templates exist in role-library) -> the build COPIES SOPs
        from the 121-template library (LLM authoring is REFUSED for canonical
        depts). We therefore do NOT author a new SOP body; instead we write the
        owner's procedure to `<dept>/owner-procedures.md` as a SUPPLEMENTAL note
        the role docs reference (a "your procedure for this" overlay), and flag it
        so the token-personalize / converge step folds it into the copied SOPs.
      - CUSTOM dept (no library templates) -> the owner's procedure is recorded so
        populate-sops-from-manifest.py LLM-authors the SOP FROM the owner's
        procedure, not generic boilerplate.

    Source of truth (precedence): dept_config["customSops"] then build-state
    canonicalReconciliation.customSops[<dept_id>]. Each entry is a string or a
    dict {"title": "...", "procedure": "..."}.

    Writes `<dept>/owner-procedures.md` (idempotent) and records
    canonicalReconciliation.customSopsCaptured. Returns the procedures file path
    or "" if nothing was captured. NEVER bypasses the canonical boundary gate.
    """
    entries = list(dept_config.get("customSops", []) or [])
    if not entries:
        bs = _load_build_state()
        recon = bs.get("canonicalReconciliation", {}) or {}
        entries = list((recon.get("customSops", {}) or {}).get(dept_id, []) or [])
    if not entries:
        return ""

    dept_dir = os.path.join(DEPARTMENTS_DIR, dept_id)
    if not os.path.isdir(dept_dir):
        print(f"[CUSTOM-SOP WARNING] dept dir missing for '{dept_id}', cannot capture SOPs.", file=sys.stderr)
        return ""

    # Determine canonicity via the SAME boundary gate the populate step honors.
    is_canonical = False
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from sop_boundary_gate import is_canonical_dept  # type: ignore
        is_canonical = bool(is_canonical_dept(dept_id))
    except Exception as e:
        # Conservative fallback: treat a dept that resolves to a suggested-roles
        # file as canonical (copy path) so we never accidentally invite LLM
        # authoring for a library dept.
        is_canonical = dept_id in DEPT_TO_SUGGESTED_ROLES
        print(f"[CUSTOM-SOP] boundary-gate import unavailable ({e}); "
              f"falling back to DEPT_TO_SUGGESTED_ROLES membership for '{dept_id}'.", file=sys.stderr)

    company_name = interview_answers.get("company_name", "the company")
    mode = ("CANONICAL (copy from library; owner procedure is a supplemental overlay "
            "folded into copied SOPs - LLM authoring stays REFUSED)"
            if is_canonical else
            "CUSTOM (LLM-author the SOP FROM this owner procedure, not boilerplate)")

    lines = [
        f"# Owner-Specific Procedures - {dept_info['name']} ({dept_info.get('emoji', '')})",
        "",
        f"**Company:** {company_name}",
        f"**Department:** {dept_id}",
        f"**SOP handling:** {mode}",
        "",
        "> These are the OWNER'S specific procedures for this department, captured",
        "> as a build decision (Capability 4). For a canonical department these are",
        "> a supplemental overlay the copied library SOPs reference - they do NOT",
        "> replace the canonical SOP body and do NOT invite LLM re-authoring. For a",
        "> custom department they are the GROUND TRUTH the authored SOP is built from.",
        "",
    ]
    captured = []
    for i, item in enumerate(entries, 1):
        if isinstance(item, dict):
            title = (item.get("title") or f"Procedure {i}").strip()
            procedure = (item.get("procedure") or item.get("text") or "").strip()
        else:
            title = f"Procedure {i}"
            procedure = str(item).strip()
        if not procedure:
            continue
        lines.append(f"## {title}")
        lines.append("")
        lines.append(procedure)
        lines.append("")
        captured.append({"dept": dept_id, "title": title})

    if not captured:
        return ""

    proc_path = os.path.join(dept_dir, "owner-procedures.md")
    with open(proc_path, "w") as f:
        f.write("\n".join(lines))
    print(f"[CUSTOM-SOP] Captured {len(captured)} owner procedure(s) for '{dept_id}' "
          f"-> {proc_path} [{'canonical-overlay' if is_canonical else 'custom-authoring-source'}]",
          file=sys.stderr)

    try:
        path = _build_state_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        state = _load_build_state()
        existing = state.get("canonicalReconciliation", {})
        if not isinstance(existing, dict):
            existing = {}
        prior = existing.get("customSopsCaptured", [])
        for r in captured:
            entry = {**r, "isCanonical": is_canonical, "file": proc_path}
            if not any(x.get("dept") == r["dept"] and x.get("title") == r["title"] for x in prior):
                prior.append(entry)
        existing["customSopsCaptured"] = prior
        state["canonicalReconciliation"] = existing
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
    except OSError as e:
        print(f"[CUSTOM-SOP WARNING] Could not record customSopsCaptured: {e}", file=sys.stderr)

    return proc_path


# ── Issue #9: onboarding "building" progress producer ─────────────────────────
# The Command Center onboarding progress page (command-center
# src/app/onboarding/building/page.tsx, fed by GET /api/onboarding/build-status)
# renders live build progress from COMPANY_DIR/build-progress.json, but nothing
# in this repo ever produced that file — the page sat idle forever. This is the
# producer for that dead data contract (a hard dependency for the interview app).
#
# Contract (must match the page's BuildProgress interface exactly):
#   {
#     "stage": "idle|manifest|research|departments|roles|qc|assembly|complete",
#     "message": str,
#     "documents_total": int,
#     "documents_complete": int,
#     "departments": [{ "id", "name", "roles_total", "roles_complete", "status" }],
#     "eta_minutes": int,
#     "started_at"?: iso8601, "completed_at"?: iso8601, "updated_at": iso8601
#   }
# department.status is one of "pending" | "in_progress" | "complete".
# Written atomically (tmp + os.replace), same pattern as the wiringStatus and
# provisioning-receipt writes. Best-effort: NEVER raises into the build.
def write_build_progress(stage, message, departments=None, documents_total=None,
                         documents_complete=0, eta_minutes=0, started_at=None,
                         completed_at=None):
    """Emit COMPANY_DIR/build-progress.json for the onboarding 'building' page."""
    if not COMPANY_DIR:
        return
    departments = departments or []
    if documents_total is None:
        documents_total = sum(int(d.get("roles_total", 0) or 0) for d in departments)
    payload = {
        "stage": stage,
        "message": message,
        "documents_total": int(documents_total),
        "documents_complete": int(documents_complete),
        "departments": departments,
        "eta_minutes": int(eta_minutes),
        "updated_at": datetime.now().isoformat(),
    }
    if started_at:
        payload["started_at"] = started_at
    if completed_at:
        payload["completed_at"] = completed_at
    try:
        os.makedirs(COMPANY_DIR, exist_ok=True)
        target = os.path.join(COMPANY_DIR, "build-progress.json")
        tmp = target + ".tmp"
        with open(tmp, "w") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp, target)
    except Exception as _bp_e:  # noqa: BLE001 - progress is telemetry, never fatal
        print(f"[BUILD-PROGRESS WARN] could not write build-progress.json: {_bp_e}",
              file=sys.stderr)


def build_from_config(config):
    """
    Build the full workforce from a non-interactive config JSON.

    This replaces the conversational interview flow with a direct build
    from the provided configuration. All department workspaces, specialists,
    and supporting files are created without any interactive prompts.
    """
    global MASTER_FILES, COMPANY_DISCOVERY_DIR

    # BUG-FIX v11.6.0 (PRD 1.9): use the module-level MASTER_FILES already resolved
    # by get_openclaw_paths() (which honours MASTER_FILES_DIR env override) instead
    # of re-scanning ~/Downloads via find_master_files_folder(), which ignores the
    # env override and caused exit 78 on fresh builds when the scanned copy is stale.
    # Only fall back to find_master_files_folder() when the module-level resolver
    # returned nothing (e.g. CI fixture without an OpenClaw install).
    if not MASTER_FILES:
        MASTER_FILES = find_master_files_folder()
    COMPANY_DISCOVERY_DIR = os.path.join(MASTER_FILES, "company-discovery")

    company_name = config["company_name"]

    # v9.6.0: resolve the Zero Human Company folder for this client BEFORE
    # any dept workspace is created. This sets COMPANY_DIR / DEPARTMENTS_DIR
    # to ~/clawd/zero-human-company/<company-slug>/...
    resolve_company_paths(company_name)
    print(f"[ZHC] Company folder: {COMPANY_DIR}", file=sys.stderr)
    print(f"[ZHC] Departments folder: {DEPARTMENTS_DIR}", file=sys.stderr)

    # G1-FAB-ENFORCE (anti-fabrication): defense-in-depth gate. Even if
    # build_from_config() is invoked directly (bypassing load_non_interactive_config),
    # REFUSE before any synthetic transcript is written or interviewComplete=true is
    # stamped unless a genuine interview OR explicit ownerConsent self-setup/fast
    # opt-in is present. Now COMPANY_DISCOVERY_DIR is resolved so any INTERVIEW_PENDING
    # handoff lands in this client's discovery folder.
    _enforce_consent_or_refuse(config)

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
            f.write(f"{NON_INTERACTIVE_ANSWERS_HEADER}\n\n")
            f.write(f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n---\n\n")
            f.write(f"**Q:** What is the name of your business?\n**A:** {company_name}\n\n---\n\n")
            f.write(f"**Q:** What industry are you in?\n**A:** {industry}\n\n---\n\n")
            if company_description:
                f.write(f"**Q:** What does your business do?\n**A:** {company_description}\n\n---\n\n")
            if tools:
                f.write(f"**Q:** What tools do you use?\n**A:** {tools}\n\n---\n\n")
            if biggest_challenge:
                f.write(f"**Q:** What is your biggest challenge?\n**A:** {biggest_challenge}\n\n---\n\n")

        # v12.3.1: Mark the interview as complete in build-state RIGHT AFTER writing
        # the answers file - so every downstream check (verify-zhc-standard.sh,
        # interview-nudge-cron.sh, resume-workforce-build.sh) sees interviewComplete=true
        # and finds the populated answers file, never the blank template.
        _write_interview_complete_to_state(answers_path=answers_path)

    # Issue #9: emit the first build-progress.json so the onboarding "building"
    # page leaves its "Connecting to build status..." null state immediately and
    # the /api/onboarding/build-status route stops returning the idle fallback.
    _build_started_at = datetime.now().isoformat()
    write_build_progress(
        "manifest", "Writing your workforce manifest...",
        eta_minutes=8, started_at=_build_started_at,
    )

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

    # Issue #3 (decision-completeness gate): in the genuine-interview path, REFUSE
    # the build fail-closed unless EVERY mandatory canonical, universal-primary
    # vertical, and custom department carries a provenanced yes/no/later decision.
    # This makes the structural over-provision scenario (an under-recorded Phase 5.5 silently
    # unioning the full floor) impossible. Fast-mode / self-setup (ownerConsent)
    # builds are exempt by design. Runs BEFORE reconcile so no floor is unioned
    # in when decisions are incomplete.
    _enforce_decision_coverage_or_refuse(config, departments_config)

    # Issue #8 (custom-department declines): filter any CUSTOM (non-canonical) dept
    # the owner PROVENANCE-DECLINED out of selected_departments BEFORE reconcile.
    # reconcile_canonical_floor honors canonical declines but never inspected the
    # client's own custom entries, so a declined custom used to ship anyway. Uses
    # the same normalized shared decline set as every other enforcer.
    _declined_norm = _shared_canonical_decline_set(_load_build_state())
    if _declined_norm:
        for _did in [d for d in list(selected_departments) if _decline_norm(d) in _declined_norm]:
            selected_departments.pop(_did, None)
            print(f"[CUSTOM-DECLINE] Dropped provenance-declined department '{_did}' "
                  f"(owner opted out in Phase 5.5).", file=sys.stderr)

    # v10.x - Enforce the canonical department floor (standard-unless-declined).
    # Builds all canonical depts (21 in v2.5.0; minus any the client explicitly
    # declined in build-state) UNION the client's customs, then writes an auditable
    # canonicalReconciliation record. Canonical depts the client named keep their
    # real description; the rest inherit the naming-map one-liner with client
    # industry context. Idempotent.
    selected_departments = reconcile_canonical_floor(
        selected_departments, core_answers, departments_config
    )

    # WS-4: research-driven industry add-ons. After the standard floor, detect
    # the client's industry from the naming-map vertical_packs keywords and add
    # the matching industry departments - de-duped against the canonical floor and
    # each other (no overlap), each inheriting a real base roles file, and
    # grounded by a McKinsey-style industry-org-design research manifest the
    # Research dept consumes. Runs BEFORE assert_dept_map_resolves so every
    # auto-added dept is proven to resolve to an existing roles file.
    selected_departments = apply_vertical_packs(selected_departments, core_answers)

    # CAPABILITY 2 (PRD R2.3): semantic COMBINE/MERGE. After the floor + verticals
    # are present (so every survivor dept exists to absorb into), fold any custom
    # dept that semantically overlaps a canonical floor / universal-primary dept
    # under a non-slug name (e.g. Accounting->billing-finance, Client Success->
    # customer-support, Brand & Identity Design->graphics) INTO the canonical dept
    # - but ONLY when the owner recorded a "merge" decision in
    # canonicalReconciliation.mergeDecisions. Confirmed merges drop the duplicate
    # standalone custom; un-decided overlaps stay standalone + are recorded PENDING
    # for Phase 5.5 to ask. Never a silent merge.
    selected_departments = apply_semantic_merges(selected_departments, core_answers)

    print(f"[NON-INTERACTIVE] Departments: {', '.join(selected_departments.keys())}", file=sys.stderr)

    # v10.15.18: HARD-FAIL the build if ANY selected department does not resolve
    # to an existing suggested-roles file. This makes the "zero-role department"
    # variance bug impossible - no department can silently ship with 0 roles/SOPs.
    assert_dept_map_resolves(list(selected_departments.keys()))

    # Issue #9: now that the department set is final, publish the department roster
    # + a stable documents_total (sum of each dept's suggested-role count) so the
    # onboarding page can render per-department progress bars and an overall %.
    _progress_departments = []
    for _pid, _pinfo in list(selected_departments.items()):
        try:
            _roles_total = len(parse_suggested_roles(_pid))
        except Exception:  # noqa: BLE001 - counting is best-effort telemetry
            _roles_total = 0
        _progress_departments.append({
            "id": _pid,
            "name": _pinfo.get("name", _pid.replace("-", " ").title()),
            "roles_total": _roles_total,
            "roles_complete": 0,
            "status": "pending",
        })
    _prog_by_id = {d["id"]: d for d in _progress_departments}
    _docs_total = sum(d["roles_total"] for d in _progress_departments)
    _docs_done = 0
    write_build_progress(
        "departments", f"Building {len(_progress_departments)} departments...",
        departments=_progress_departments, documents_total=_docs_total,
        documents_complete=0, eta_minutes=max(1, _docs_total // 2),
        started_at=_build_started_at,
    )

    # Create department workspaces
    specialists_by_dept = {}
    for dept_id, dept_info in selected_departments.items():
        dept_config = departments_config.get(dept_id, {})

        # Issue #9: mark this department in-progress before materializing its roles.
        _pe = _prog_by_id.get(dept_id)
        if _pe:
            _pe["status"] = "in_progress"
            write_build_progress(
                "roles", f"Generating roles + how-to documents for {dept_info['name']}...",
                departments=_progress_departments,
                documents_total=max(_docs_total, _docs_done),
                documents_complete=_docs_done,
                eta_minutes=max(1, (_docs_total - _docs_done) // 2),
                started_at=_build_started_at,
            )

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

        # CAPABILITY 3 (PRD R2.4): materialize the EXTRA roles this owner asked for
        # in THIS department as a build decision (not the post-build add-role.sh
        # path). Idempotent; skips any role slug already present.
        custom_role_folders = materialize_custom_roles(dept_id, dept_info, dept_config, dept_answers)
        if custom_role_folders:
            role_folders = list(role_folders) + custom_role_folders
            print(f"[NON-INTERACTIVE] Added {len(custom_role_folders)} owner-requested custom role(s) to {dept_id}/", file=sys.stderr)

        # CAPABILITY 4 (PRD R2.5): capture this owner's department-specific
        # procedures as a build decision, respecting sop_boundary_gate.py
        # (canonical = supplemental overlay over copied SOPs; custom = LLM
        # authoring source). Never invites LLM authoring for a canonical dept.
        capture_custom_sops(dept_id, dept_info, dept_config, dept_answers)

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

        # Issue #9: this department's roles are materialized — mark it complete and
        # advance the overall documents_complete counter so the page's bars fill.
        if _pe:
            _actual = len(role_folders)
            _pe["roles_complete"] = _actual if _actual else _pe["roles_total"]
            _pe["roles_total"] = max(_pe["roles_total"], _actual)
            _pe["status"] = "complete"
            _docs_done += _pe["roles_complete"]
            write_build_progress(
                "roles", f"Completed {dept_info['name']} ({_pe['roles_complete']} roles)",
                departments=_progress_departments,
                documents_total=max(_docs_total, _docs_done),
                documents_complete=_docs_done,
                eta_minutes=max(1, (max(_docs_total, _docs_done) - _docs_done) // 2 + 2),
                started_at=_build_started_at,
            )

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
    #
    # Alongside the internal ROSTER.md, emit the OWNER-FACING companion:
    # how-to-use-this-department.md (plain-language guide to the department + its
    # specialists). The agent answers "how do I use the X department / specialist?"
    # FROM this file (universal-sops/answering-how-to-use-questions.md). Both are
    # regenerated on every build so they always match the real roster.
    for dept_id, dept_info in selected_departments.items():
        write_department_roster(dept_id, dept_info)
        write_department_how_to_use(dept_id, dept_info, company_name)
    write_universal_routing_map(selected_departments)

    # Gap-3: collect every NO_TEMPLATE role (PENDING how-to.md) into a single
    # company-root manifest so the orchestrator knows exactly what to fill - a
    # missing template is never a silent empty stub.
    write_pending_sops_manifest(selected_departments)

    # Issue #9: all department roles are on disk; the org chart, rosters, routing
    # map and persona matrix are being assembled.
    write_build_progress(
        "assembly", "Assembling org chart, rosters + persona matrix...",
        departments=_progress_departments,
        documents_total=max(_docs_total, _docs_done),
        documents_complete=_docs_done, eta_minutes=3,
        started_at=_build_started_at,
    )

    # Issue #9: the SOP research manifest + auto-population is the long pole
    # (heavy sub-agents, up to ~60 min) — surface it as the QC stage so the page
    # shows meaningful activity while every document is quality-reviewed.
    write_build_progress(
        "qc", "Quality reviewing every document...",
        departments=_progress_departments,
        documents_total=max(_docs_total, _docs_done),
        documents_complete=_docs_done, eta_minutes=5,
        started_at=_build_started_at,
    )

    # v9.6.0: write the SOP research manifest so the AI agent can fan out
    # parallel sub-agents (one per department) to write real Lean Six Sigma
    # SOPs to replace the [Step X - to be personalized] placeholders.
    # The sub-agents are spawned BY the AI agent reading this manifest,
    # not by this script directly - keeps spawn under the agent's control
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
                          f"sub-agents available) - work files were written but NO SOPs are authored "
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

    # Generate departments.json - v9.6.1 writes to BOTH the ZHC company folder
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

            # v11.3.1 FIX: agents.defaults.tools.exec is REMOVED.
            # On OpenClaw 2026.6.1+ the schema validator rejects it with
            # "agents.defaults: Invalid input" and doctor --fix auto-reverts it.
            # The effective exec policy is the TOP-LEVEL tools.exec set in
            # install.sh Step 8. Per-department generation tools are unlocked
            # via explicit tools.allow on each generation dept agent (see
            # add_agent_to_config below).
            #
            # GOAL-4 D4 (4B+4C) — NO-REFUSAL TOOL BASELINE at build origin.
            # Mirrors apply-fleet-standards.sh: agents.defaults.tools.allow=["*"]
            # so a freshly-built box is BORN with departments + sub-agents able to
            # run exec / file ops / web / MCP / Kie HTTP without ever refusing a
            # job. This is the VALID defaults-level key (allow) — NOT the poison
            # key (exec). Under RESTRICT-ONLY precedence the CEO/main per-agent
            # deny (set in add_agent_to_config) STILL wins, so the wildcard does
            # NOT re-open the CEO. Idempotent: only fills the key if absent so a
            # client customization is never clobbered.
            _defaults = config_data.setdefault("agents", {}).setdefault("defaults", {})
            _defaults_tools = _defaults.setdefault("tools", {})
            if "allow" not in _defaults_tools:
                _defaults_tools["allow"] = ["*"]
                print("[NON-INTERACTIVE] no-refusal baseline: agents.defaults.tools.allow=['*'] (GOAL-4 D4)", file=sys.stderr)

            registration_failures = []
            for dept_id, dept_info in selected_departments.items():
                try:
                    result = add_agent_to_config(config_data, dept_id, dept_info)
                    if result is False:
                        # False = guard-blocked or not added (not just already-present)
                        # Check if it was already present (idempotent) vs actually failed
                        existing_ids = [a.get("id") for a in config_data.get("agents", {}).get("list", [])]
                        if f"dept-{dept_id}" not in existing_ids:
                            registration_failures.append(f"{dept_id}:add_returned_false")
                except Exception as _reg_e:
                    print(f"[NON-INTERACTIVE ERROR] Registration failed for {dept_id}: {_reg_e}", file=sys.stderr)
                    registration_failures.append(f"{dept_id}:{_reg_e}")
            if registration_failures:
                print(f"[NON-INTERACTIVE ERROR] {len(registration_failures)} dept(s) failed registration: {registration_failures}", file=sys.stderr)
            else:
                save_openclaw_config(config_data)
                print(f"[NON-INTERACTIVE] Config updated with {len(selected_departments)} department agents", file=sys.stderr)
        except Exception as e:
            print(f"[NON-INTERACTIVE ERROR] Config update block failed: {e}", file=sys.stderr)
            # registration_failures is defined at the top of the try block, so it
            # is always in scope here; append to it directly (do NOT re-init or the
            # failures recorded in the loop above would be discarded).
            try:
                registration_failures.append(f"config_block:{e}")
            except NameError:
                registration_failures = [f"config_block:{e}"]
    else:
        print(f"[NON-INTERACTIVE ERROR] openclaw.json not found at {OPENCLAW_CONFIG} — registration FAILED (wiringStatus: blocked-no-config). Build cannot be marked complete without agent config.",
              file=sys.stderr)
        registration_failures = ["all:openclaw_json_absent"]
        # Write wiringStatus to build-state (use the canonical path resolver,
        # NOT a bare WORKSPACE global which does not exist in this module).
        try:
            _state_f = _build_state_path()
            if os.path.isfile(_state_f):
                import tempfile as _tf
                _s = json.load(open(_state_f))
                _s["wiringStatus"] = "blocked-no-config"
                _s["wiringFailureReason"] = f"openclaw.json absent at {OPENCLAW_CONFIG}"
                _tmp = _tf.mktemp(dir=os.path.dirname(_state_f), prefix=".bws.", suffix=".tmp")
                json.dump(_s, open(_tmp, "w"), indent=2)
                os.replace(_tmp, _state_f)
        except Exception as _ws_e:
            print(f"[NON-INTERACTIVE WARN] could not write wiringStatus to build-state: {_ws_e}", file=sys.stderr)

    # ── POST-BUILD WIRING ASSERTION (v14.23.1 FAIL-WIRING-NOT-MATERIALIZED) ───
    # Verify ALL expected dept-<id> entries are present in agents.list on disk.
    # The primary registration loop (add_agent_to_config above) writes to the
    # in-memory config_data then saves — but only when zero failures occurred.
    # When registration_failures is non-empty the save is skipped, leaving agents
    # on disk but NOT in openclaw.json. This assertion catches that gap and
    # also the PATH-MISMATCH case where openclaw.json was absent at build time.
    #
    # Auto-repair: if any expected agents are missing, invoke
    # 32-command-center-setup/scripts/materialize-dept-agents.sh which resolves
    # the correct build-output path (~/Downloads/openclaw-master-files/... on Mac;
    # /data/openclaw-master-files/... on VPS) and registers all departments.
    # Fail loud if still incomplete after the repair attempt.
    _expected_dept_agent_ids = {f"dept-{d}" for d in selected_departments}
    if _expected_dept_agent_ids and os.path.isfile(OPENCLAW_CONFIG):
        try:
            _cfg_chk = load_openclaw_config()
            _actual_ids_chk = {
                a.get("id") for a in _cfg_chk.get("agents", {}).get("list", [])
                if isinstance(a, dict)
            }
            _wiring_missing = _expected_dept_agent_ids - _actual_ids_chk
            if not _wiring_missing:
                print(
                    f"[WIRING-ASSERT] PASS — all {len(_expected_dept_agent_ids)} "
                    f"dept agents confirmed in agents.list",
                    file=sys.stderr,
                )
            else:
                print(
                    f"[WIRING-ASSERT] {len(_wiring_missing)} dept agent(s) missing "
                    f"from agents.list: {sorted(_wiring_missing)} — "
                    f"invoking materialize-dept-agents.sh to repair",
                    file=sys.stderr,
                )
                _mat_script = os.path.normpath(os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "..", "..", "32-command-center-setup", "scripts",
                    "materialize-dept-agents.sh",
                ))
                if os.path.isfile(_mat_script):
                    try:
                        import subprocess as _wa_sp
                        _mat_rc = _wa_sp.run(
                            ["bash", _mat_script], timeout=120
                        ).returncode
                        if _mat_rc == 0:
                            _cfg_chk2 = load_openclaw_config()
                            _actual_ids2 = {
                                a.get("id")
                                for a in _cfg_chk2.get("agents", {}).get("list", [])
                                if isinstance(a, dict)
                            }
                            _still_missing = _expected_dept_agent_ids - _actual_ids2
                            if not _still_missing:
                                print(
                                    f"[WIRING-ASSERT] PASS (after materialize repair) "
                                    f"— all {len(_expected_dept_agent_ids)} dept agents "
                                    f"now confirmed in agents.list",
                                    file=sys.stderr,
                                )
                                # Clear registration_failures so progress reaches 100%
                                registration_failures.clear()
                            else:
                                print(
                                    f"[WIRING-ASSERT] FAIL-WIRING-NOT-MATERIALIZED — "
                                    f"{len(_still_missing)} dept agent(s) still absent "
                                    f"after materialize: {sorted(_still_missing)}",
                                    file=sys.stderr,
                                )
                                if "wiring:not-materialized" not in registration_failures:
                                    registration_failures.append("wiring:not-materialized")
                        else:
                            print(
                                f"[WIRING-ASSERT] materialize-dept-agents.sh exited "
                                f"{_mat_rc} — wiring still incomplete",
                                file=sys.stderr,
                            )
                            if "wiring:materialize-failed" not in registration_failures:
                                registration_failures.append("wiring:materialize-failed")
                    except Exception as _mat_e:
                        print(
                            f"[WIRING-ASSERT] materialize-dept-agents.sh error: "
                            f"{_mat_e}",
                            file=sys.stderr,
                        )
                else:
                    print(
                        f"[WIRING-ASSERT] FAIL-WIRING-NOT-MATERIALIZED — "
                        f"materialize-dept-agents.sh not found at {_mat_script}. "
                        f"Run manually: bash 32-command-center-setup/scripts/"
                        f"materialize-dept-agents.sh",
                        file=sys.stderr,
                    )
                    if "wiring:not-materialized" not in registration_failures:
                        registration_failures.append("wiring:not-materialized")
        except Exception as _wa_e:
            print(
                f"[WIRING-ASSERT] WARN: post-build wiring check failed: {_wa_e}",
                file=sys.stderr,
            )

    # B2: Gate progress_pct and "Build complete!" on registration success
    _build_progress = 100
    _build_complete_msg = "Build complete!"
    if registration_failures:
        _build_progress = 90  # cap at 90 when registration failed
        _build_complete_msg = (
            f"Build INCOMPLETE — {len(registration_failures)} department agent(s) not registered: "
            f"{registration_failures}. Roles are on disk but not wired into openclaw.json. "
            f"Re-run after fixing config."
        )
        # Write wiringStatus:failed to build-state (canonical path resolver)
        try:
            _state_f = _build_state_path()
            if os.path.isfile(_state_f):
                import tempfile as _tf2
                _s2 = json.load(open(_state_f))
                if _s2.get("wiringStatus") not in ("blocked-no-config",):
                    _s2["wiringStatus"] = "failed"
                    _s2["wiringFailureReason"] = f"registration_failures={registration_failures}"
                    _tmp2 = _tf2.mktemp(dir=os.path.dirname(_state_f), prefix=".bws.", suffix=".tmp")
                    json.dump(_s2, open(_tmp2, "w"), indent=2)
                    os.replace(_tmp2, _state_f)
        except Exception as _ws_e2:
            print(f"[NON-INTERACTIVE WARN] could not write wiringStatus:failed to build-state: {_ws_e2}", file=sys.stderr)

    # Save handoff as completed (B2: progress capped if registration failed)
    create_handoff(
        option=config.get("option", "A"),
        departments_done=list(selected_departments.keys()),
        departments_remaining=[],
        progress_pct=_build_progress
    )

    # Generate/update persona-matrix.md for workforce visibility
    generate_persona_matrix(selected_departments, persona_categories, company_name)


    # v10.5.1: Run v2.1 post-build augmentation - adds IDENTITY.md, SOUL.md,
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

    # PER-ARTIFACT VERSIONING (v12.27.0): flush the SOURCE content_sha each role
    # was instantiated from into build-state.artifactProvenance. All
    # create_role_workspace() calls (which run _instantiate_role_from_library and
    # populate the _ARTIFACT_PROVENANCE accumulator) have completed by now, so this
    # is the authoritative roll-up detect-stale-artifacts.py reads as the fast path.
    _flush_artifact_provenance_to_state()

    # Bulletproofing (c): write the provisioning receipt with the EXPECTED-SET
    # EQUALITY invariant (over- AND under-provisioning both fail). prove-zhe.py and
    # prove-handover.sh read this receipt. Best-effort — never fails the build.
    _write_provisioning_receipt(company_name, selected_departments, config, core_answers)

    print(f"\n[NON-INTERACTIVE] {_build_complete_msg}", file=sys.stderr)
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
                print("[v10.15.8] LIBRARY GATE PASS - roleLibraryStatus=done AND sopLibraryStatus=done. "
                      "Workforce may proceed to closeout.", file=sys.stderr)
            else:
                print(f"[v10.15.8] LIBRARY GATE FAIL (rc={_gate_rc}) - role library and/or SOP library "
                      f"NOT populated. Do NOT write buildCompletedAt / closeoutStatus=pending. Re-run "
                      f"post-build-role-workspaces.py and/or populate-sops-from-manifest.py, then re-run "
                      f"verify-library-gate.sh until it exits 0. The resume cron will fire [LIBRARY-RESUME] "
                      f"until both libraries are done.", file=sys.stderr)
        except Exception as _e:
            print(f"[v10.15.8 WARN] verify-library-gate.sh invocation failed: {_e}", file=sys.stderr)
    else:
        print(f"[v10.15.8 WARN] verify-library-gate.sh not present at {_gate_script}", file=sys.stderr)

    # Issue #9: terminal build-progress emit. Only signal "complete" when the
    # structural build actually succeeded (all department agents wired —
    # _build_progress == 100). If registration failed, leave the page in a
    # non-terminal state with an honest message so it keeps polling rather than
    # falsely showing "ready" (honors the "no false done" doctrine).
    try:
        _all_done = all(d["status"] == "complete" for d in _progress_departments)
        if _build_progress >= 100 and _all_done:
            write_build_progress(
                "complete", "Your AI workforce is ready ✓",
                departments=_progress_departments,
                documents_total=max(_docs_total, _docs_done),
                documents_complete=max(_docs_total, _docs_done),
                eta_minutes=0, started_at=_build_started_at,
                completed_at=datetime.now().isoformat(),
            )
        else:
            write_build_progress(
                "qc", _build_complete_msg,
                departments=_progress_departments,
                documents_total=max(_docs_total, _docs_done),
                documents_complete=_docs_done, eta_minutes=5,
                started_at=_build_started_at,
            )
    except Exception as _bp_final_e:  # noqa: BLE001
        print(f"[BUILD-PROGRESS WARN] terminal emit failed: {_bp_final_e}", file=sys.stderr)


# ============================================================
# CONFIGURATION
# ============================================================

HOME = os.path.expanduser("~")

# PRD 1.9: resolve ALL paths through get_openclaw_paths() - the single path
# authority. This script NEVER writes outside master_files/zero-human-company/.
# Legacy ~/clawd roots may be READ for backward compat via get_legacy_company_roots()
# but nothing new is written there.
_SHARED_UTILS_BW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared-utils")
sys.path.insert(0, os.path.realpath(_SHARED_UTILS_BW))
try:
    from detect_platform import get_openclaw_paths as _get_openclaw_paths_bw
    _PATHS_BW = _get_openclaw_paths_bw()
    WORKSPACE_ROOT = str(_PATHS_BW["workspace"])
    MASTER_FILES = str(_PATHS_BW["master_files"])
    # Canonical ZHC root (PRD 1.9): master_files/zero-human-company/
    ZHC_ROOT = str(_PATHS_BW["company_root"])
except (Exception, SystemExit) as _bw_err:
    # Graceful fallback - includes CI environments without an OpenClaw install.
    # detect_platform raises SystemExit(1) when no platform is detected; catch it
    # so module-level import in CI test fixtures does not crash.
    import warnings as _bw_warnings
    _bw_warnings.warn(
        f"[build-workforce PRD-1.9] detect_platform could not resolve paths ({type(_bw_err).__name__}: {_bw_err}); "
        "falling back to legacy ~/clawd root. Run the OpenClaw installer on a real box.",
        stacklevel=1,
    )
    WORKSPACE_ROOT = str(Path.home() / "clawd")
    ZHC_ROOT = os.path.join(WORKSPACE_ROOT, "zero-human-company")
    MASTER_FILES = str(Path.home() / "Downloads" / "openclaw-master-files")

# DEPARTMENTS_DIR is resolved per-company at runtime once the company slug is known.
DEPARTMENTS_DIR = None       # Resolved by resolve_company_paths() below
COMPANY_DIR = None           # <ZHC_ROOT>/<slug>/
COMPANY_SLUG = None
LEGACY_DEPARTMENTS_DIR = os.path.join(WORKSPACE_ROOT, "departments")  # pre-v9.6.0 location (READ-ONLY)

SUBAGENTS_DIR = os.path.join(WORKSPACE_ROOT, "subagents", "templates")
OPENCLAW_CONFIG = str(Path.home() / ".openclaw" / "openclaw.json")
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

    PRD 1.9: new companies are ALWAYS written to the canonical root:
        Mac:  ~/Downloads/openclaw-master-files/zero-human-company/<slug>/
        VPS:  /data/openclaw-master-files/zero-human-company/<slug>/
    Override with MASTER_FILES_DIR env var.

    Legacy roots (~/clawd/...) are READ-ONLY for backward compat.
    Run scripts/migrate-zhc-to-master-files.sh to migrate existing companies.
    """
    global COMPANY_SLUG, COMPANY_DIR, DEPARTMENTS_DIR
    COMPANY_SLUG = slugify_company_name(company_name)

    # PRD 1.9: always write to canonical root (ZHC_ROOT is now master_files/zero-human-company/)
    canonical = os.path.join(ZHC_ROOT, COMPANY_SLUG)

    # If the company already exists in a legacy location and NOT yet in canonical,
    # emit a loud warning so the operator runs the migration. Never silently write
    # new content to the old location.
    legacy_short = os.path.join(WORKSPACE_ROOT, "zhc", COMPANY_SLUG)
    legacy_clawd = os.path.join(str(Path.home() / "clawd" / "zero-human-company"), COMPANY_SLUG)
    for _legacy in (legacy_short, legacy_clawd):
        if os.path.isdir(_legacy) and not os.path.isdir(canonical):
            print(
                f"[ZHC WARNING] Company '{COMPANY_SLUG}' found at legacy path: {_legacy}\n"
                f"[ZHC WARNING] New writes will go to canonical path: {canonical}\n"
                f"[ZHC WARNING] Run scripts/migrate-zhc-to-master-files.sh to move the existing company.",
                file=sys.stderr,
            )
            break

    COMPANY_DIR = canonical
    os.makedirs(COMPANY_DIR, exist_ok=True)
    DEPARTMENTS_DIR = os.path.join(COMPANY_DIR, "departments")
    os.makedirs(DEPARTMENTS_DIR, exist_ok=True)

    # If pre-v9.6.0 legacy departments folder exists with content, log a migration note
    if os.path.isdir(LEGACY_DEPARTMENTS_DIR) and os.listdir(LEGACY_DEPARTMENTS_DIR):
        print(f"[ZHC] Legacy ~/clawd/departments/ detected (READ-ONLY for backward compat).\n"
              f"[ZHC] New writes go to canonical path: {DEPARTMENTS_DIR}", file=sys.stderr)

    return COMPANY_DIR, DEPARTMENTS_DIR

# Files inherited from main CEO workspace
INHERITED_FILES = ["TOOLS.md", "AGENTS.md", "USER.md"]

# Files to check for existing context before asking questions.
# v12.3.4: expanded to all 6 core workspace .md files (added IDENTITY.md + SOUL.md).
CONTEXT_FILES = ["USER.md", "MEMORY.md", "AGENTS.md", "TOOLS.md", "IDENTITY.md", "SOUL.md"]

# Legacy RECOMMENDED_DEPARTMENTS suggestion / display-metadata dict (N17 binding).
# NOTE: this is NOT the canonical floor. The authoritative floor is 22 mandatory
# + 6 universal-primary = 28, derived LIVE from department-naming-map.json (see
# load_canonical_floor() + _universal_primary_ids()); the full shipped role catalog
# is tracked in templates/role-library/_index.json. This legacy dict only supplies
# display metadata (name/emoji/head/description) and MUST match the dashboard's
# `config/departments.json` exactly. v10.13.0 sync: removed Operations / Creative
# / HR / IT (none of these are produced by the AI Workforce Interview anymore;
# they were pre-v10.7.0 leftovers). Added CRM, OpenClaw Maintenance, Social
# Media, Paid Advertisement (all 4 explicit interview outputs).
#
# Per N17, this dict is a SUGGESTION list during the interview - the client
# still chooses which subset they need. But no department OUTSIDE this list
# may be invented by the script. The interview output IS the source of truth
# for which subset is enabled in the dashboard.
# PR3 (2026-06-09): head values aligned to canonical role #0 names from
# 23-ai-workforce-blueprint/suggested-roles/<dept>-suggested-roles.md.
# The agent's "name" in openclaw.json agents.list is set to dept_info["head"] by
# add_agent_to_config(), so this dict is the SINGLE SOURCE OF TRUTH for the name
# that appears in the Command Center sidebar's head-agent row.
# Changed: sales, support, graphics, research, comms, crm, social, paid-ads.
RECOMMENDED_DEPARTMENTS = {
    "ceo": {"name": "CEO", "emoji": "👔", "head": "Chief Executive Officer", "description": "Executive strategy, vision, high-level decisions"},
    "marketing": {"name": "Marketing", "emoji": "📢", "head": "Chief Marketing Officer", "description": "Getting the word out about your business - social media, ads, email, content"},
    "sales": {"name": "Sales", "emoji": "💰", "head": "Chief Sales Officer", "description": "Turning interested people into paying customers"},
    "billing": {"name": "Billing / Finance", "emoji": "💳", "head": "Chief Financial Officer", "description": "Invoices, payments, tracking your money"},
    "support": {"name": "Customer Support", "emoji": "🛟", "head": "Head of Customer Success", "description": "Helping your existing customers when they need it"},
    "webdev": {"name": "Web Development", "emoji": "🌐", "head": "Head of Web Development", "description": "Your website, landing pages, funnels"},
    "appdev": {"name": "App Development", "emoji": "🛠️", "head": "Head of App Development", "description": "Mobile apps, software applications"},
    "graphics": {"name": "Graphics", "emoji": "🖼️", "head": "Chief Design Officer", "description": "Visual content - logos, images, brand assets"},
    "video": {"name": "Video Production", "emoji": "🎬", "head": "Head of Video Production", "description": "Video production, editing, AI video"},
    "audio": {"name": "Audio Production", "emoji": "🎵", "head": "Head of Audio Production", "description": "Podcasts, voiceovers, music, audio production"},
    "research": {"name": "Research", "emoji": "🔬", "head": "Chief Research Officer", "description": "Market research, competitor analysis, data insights"},
    "comms": {"name": "Communications", "emoji": "📡", "head": "Chief Communications Officer", "description": "PR, announcements, internal and external messaging"},
    "crm": {"name": "CRM", "emoji": "📇", "head": "Director of CRM", "description": "Customer data, lead lifecycle, pipeline hygiene (GHL-focused)"},
    "openclaw": {"name": "OpenClaw Maintenance", "emoji": "🦾", "head": "Head of OpenClaw Maintenance", "description": "Sunday updates, skill bumps, system QC, internal tooling"},
    "legal": {"name": "Legal / Compliance", "emoji": "⚖️", "head": "Chief Legal Officer", "description": "Contracts, regulations, keeping you protected"},
    "social": {"name": "Social Media", "emoji": "📱", "head": "Director of Social Media", "description": "Organic channels - LinkedIn, X, Instagram, TikTok, YouTube"},
    "paid-ads": {"name": "Paid Advertisement", "emoji": "🎯", "head": "Director of Paid Advertisement", "description": "Meta / Google / YouTube / TikTok paid acquisition - ROAS, CPA, retargeting"},
}

# N17 runtime guard - if config/departments.json is reachable from the workspace,
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
            # PRD 1.5: normalise via canonical_dept_slug (not raw removeprefix)
            dashboard_ids = {_canonical_dept_slug(d["id"]) for d in dashboard if isinstance(d, dict) and "id" in d}
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
            return  # Best-effort only - never block on a parsing issue

# Model assignments per department type
# Creative/content departments use Kimi (fast, good for writing)
# Technical departments use GPT 5.4 (strong at code and systems)
# Legal/operations use MiniMax M3 via the client's own Ollama Cloud (careful,
# precise reasoning). Anthropic is NEVER pinned for a client agent (operator-only,
# cost-prohibitive); clients run on models they actually have, Ollama Cloud first.
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
    "operations": "ollama/minimax-m3:cloud",
    "legal": "ollama/minimax-m3:cloud",
    "support": "ollama/kimi-k2.6:cloud",
    "billing": "ollama/kimi-k2.6:cloud",
    "hr": "ollama/kimi-k2.6:cloud",
}


# ============================================================
# RESEARCH FALLBACK (Phase 13 audit - P1)
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
        purpose_tier: "light" | "standard" | "heavy" - controls max_tokens.

    Returns:
        The model's response text, or None if research is unavailable.

    N1 compliance: Perplexity Sonar is hosted via OpenRouter, NOT Anthropic.
    N15 alignment: this is the runtime counterpart to web-research-preflight.sh
                   - preflight populates static defaults, this fills gaps.
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
        # No key - return None so caller falls back to its built-in default.
        print(f"[research] OPENROUTER_API_KEY absent - skipping web research for: {question[:80]}",
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

def _resolve_main_agent_workspace():
    """
    Resolve the path that the main (CEO/orchestrator) agent actually reads
    bootstrap files from.

    PRD 1.11: This is now a thin shim over resolve_injected_core_files() in
    shared-utils/.  The shared helper is the single canonical implementation.
    Kept here by name for backward-compat - callers need not change.

    Returns:
        str path to the injected workspace directory.
    """
    try:
        import sys as _sys
        _su = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           '..', '..', '..', 'shared-utils')
        _su = os.path.normpath(_su)
        if _su not in _sys.path:
            _sys.path.insert(0, _su)
        from resolve_injected_core_files import resolve_main_agent_workspace as _rmaw  # type: ignore
        return str(_rmaw())
    except Exception:
        pass

    # Fallback: inline 3-step resolver (bash install early-boot mirror)
    import json as _json
    workspace = None
    if os.path.isfile(OPENCLAW_CONFIG):
        try:
            with open(OPENCLAW_CONFIG, 'r') as _f:
                _cfg = _json.load(_f)
            for _ag in _cfg.get("agents", {}).get("list", []) or []:
                if isinstance(_ag, dict) and _ag.get("id") == "main":
                    _ws = _ag.get("workspace")
                    if _ws:
                        workspace = os.path.expanduser(_ws)
                        break
            if not workspace:
                _dw = _cfg.get("agents", {}).get("defaults", {}).get("workspace")
                if _dw:
                    workspace = os.path.expanduser(_dw)
        except Exception:
            pass
    if not workspace:
        workspace = os.path.join(HOME, ".openclaw", "workspace")
    return workspace


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
            # Fallback to copy only if symlink unsupported (rare - Windows w/o admin)
            print(f"[INHERITED-FILES WARN] symlink failed for {filename}: {e}; falling back to copy",
                  file=sys.stderr)
            shutil.copy2(src, dst)

    # G5: detect CEO dept - canonical orchestrator rule is PREPENDED to its
    # MEMORY.md / SOUL.md / IDENTITY.md (NOT to AGENTS.md/TOOLS.md which are
    # shared). Idempotent: CEO_ORCHESTRATOR_IDEMPOTENCY_MARKER guards against
    # duplicate injection on re-runs.
    is_ceo_dept = dept_id in ("ceo", "master-orchestrator", "dept-ceo")

    # Create SOUL.md (generated from interview, not a template)
    soul_path = os.path.join(dept_dir, "SOUL.md")
    if not os.path.isfile(soul_path):
        soul_content = generate_soul_md(dept_id, dept_info, interview_answers)
        with open(soul_path, 'w') as f:
            f.write(soul_content)
    # G5: for CEO, prepend canonical orchestrator rule at the TOP of SOUL.md
    # (idempotent - skip if V2 marker already present; upgrade V1→V2 if only V1 present)
    if is_ceo_dept:
        with open(soul_path, 'r') as f:
            existing = f.read()
        if CEO_ORCHESTRATOR_IDEMPOTENCY_MARKER not in existing:
            # Strip any V1 block first (so V2 is the only copy at the top)
            if CEO_ORCHESTRATOR_V1_MARKER in existing:
                # Remove from the V1 marker to the first --- separator (end of V1 block)
                import re as _re
                existing = _re.sub(
                    r'<!-- CEO_ORCHESTRATOR_RULE_V1 -->.*?---\s*\n', '',
                    existing, count=1, flags=_re.DOTALL)
            with open(soul_path, 'w') as f:
                f.write(CEO_ORCHESTRATOR_RULE + existing)

    # v10.13.23 - Create IDENTITY.md for the dept head (Trevor's agent-file
    # architecture). Per the spec: every top-level agent gets its own
    # IDENTITY/SOUL/MEMORY/HEARTBEAT; the SHARED files (USER/AGENTS/TOOLS)
    # stay symlinked at the workspace root. Sub-agents (role folders inside
    # this dept) get their IDENTITY.md via post-build-role-workspaces.py.
    identity_path = os.path.join(dept_dir, "IDENTITY.md")
    if not os.path.isfile(identity_path):
        identity_content = generate_identity_md(dept_id, dept_info, interview_answers)
        with open(identity_path, 'w') as f:
            f.write(identity_content)
    # G5: for CEO, prepend canonical orchestrator rule at the TOP of IDENTITY.md
    # (idempotent - skip if V2 marker present; upgrade V1→V2 if only V1 present)
    if is_ceo_dept:
        with open(identity_path, 'r') as f:
            existing = f.read()
        if CEO_ORCHESTRATOR_IDEMPOTENCY_MARKER not in existing:
            if CEO_ORCHESTRATOR_V1_MARKER in existing:
                import re as _re
                existing = _re.sub(
                    r'<!-- CEO_ORCHESTRATOR_RULE_V1 -->.*?---\s*\n', '',
                    existing, count=1, flags=_re.DOTALL)
            with open(identity_path, 'w') as f:
                f.write(CEO_ORCHESTRATOR_RULE + existing)

    # Create MEMORY.md
    memory_path = os.path.join(dept_dir, "MEMORY.md")
    if not os.path.isfile(memory_path):
        with open(memory_path, 'w') as f:
            if is_ceo_dept:
                # G5: CEO MEMORY.md leads with the canonical orchestrator rule
                # so the rule is present even in the first file the CEO reads.
                f.write(CEO_ORCHESTRATOR_RULE)
                f.write(f"# MEMORY.md - {dept_info['name']} Department\n\n> Long-term state, decisions, and metrics for this department.\n> Updated by the department head after each work session.\n")
            else:
                f.write(f"# MEMORY.md - {dept_info['name']} Department\n\n> Long-term state, decisions, and metrics for this department.\n> Updated by the department head after each work session.\n")
    # G5: if CEO MEMORY.md already exists but lacks V2 marker, prepend it
    # (upgrade V1→V2 if only V1 is present)
    elif is_ceo_dept:
        with open(memory_path, 'r') as f:
            existing = f.read()
        if CEO_ORCHESTRATOR_IDEMPOTENCY_MARKER not in existing:
            if CEO_ORCHESTRATOR_V1_MARKER in existing:
                import re as _re
                existing = _re.sub(
                    r'<!-- CEO_ORCHESTRATOR_RULE_V1 -->.*?---\s*\n', '',
                    existing, count=1, flags=_re.DOTALL)
            with open(memory_path, 'w') as f:
                f.write(CEO_ORCHESTRATOR_RULE + existing)

    # Create HEARTBEAT.md with department-specific priorities
    heartbeat_path = os.path.join(dept_dir, "HEARTBEAT.md")
    if not os.path.isfile(heartbeat_path):
        heartbeat_content = generate_heartbeat_md(dept_id, dept_info, interview_answers)
        with open(heartbeat_path, 'w') as f:
            f.write(heartbeat_content)

    # G5-FIX (v11.3.2): Inject PRIME DIRECTIVE into the MAIN AGENT's workspace
    # SOUL.md - the file the gateway actually injects into the model context.
    #
    # The previous code only wrote the directive to DEPARTMENTS_DIR/ceo/SOUL.md
    # (the dept-ceo sub-agent workspace). The MAIN orchestrator agent reads its
    # bootstrap files from agents.list[main].workspace (or agents.defaults.workspace
    # or ~/.openclaw/workspace) - a DIFFERENT path. Proven on a client box: hand-
    # writing to workspace/SOUL.md stopped the CEO from self-executing; a build
    # re-run reverted it because the build never touched that file.
    #
    # This block ALSO scrubs the "personal assistant / handle it yourself" intro
    # from workspace/SOUL.md before prepending the directive, so there are no
    # contradictory instructions. Idempotent: CEO_ORCHESTRATOR_IDEMPOTENCY_MARKER
    # guards against duplicate injection on re-runs.
    if is_ceo_dept:
        import re as _re2
        main_ws = _resolve_main_agent_workspace()
        os.makedirs(main_ws, exist_ok=True)
        ws_soul_path = os.path.join(main_ws, "SOUL.md")
        # Read existing content (or start empty)
        if os.path.isfile(ws_soul_path):
            with open(ws_soul_path, 'r') as _f:
                ws_existing = _f.read()
        else:
            ws_existing = ""
        # Only inject if V2 marker not already present
        if CEO_ORCHESTRATOR_IDEMPOTENCY_MARKER not in ws_existing:
            # Upgrade V1 → V2 if only V1 is present
            if CEO_ORCHESTRATOR_V1_MARKER in ws_existing:
                ws_existing = _re2.sub(
                    r'<!-- CEO_ORCHESTRATOR_RULE_V1 -->.*?---\s*\n', '',
                    ws_existing, count=1, flags=_re2.DOTALL)
            # Scrub the "personal assistant / handle it yourself" template intro.
            # The SOUL.md installed by install.sh starts with this marker line -
            # it instructs the agent to "just help" and "have opinions" which
            # contradicts the route-not-execute PRIME DIRECTIVE.  Strip from the
            # beginning of the file up to and including the first --- separator.
            # (Idempotent - if no such intro is found, the sub is a no-op.)
            ws_existing = _re2.sub(
                r'^# SOUL\.md.*?^---\s*\n',
                '',
                ws_existing,
                count=1,
                flags=_re2.DOTALL | _re2.MULTILINE,
            )
            with open(ws_soul_path, 'w') as _f:
                _f.write(CEO_ORCHESTRATOR_RULE + ws_existing.lstrip())
            print(
                f"[G5-FIX] PRIME DIRECTIVE written to main-agent workspace: {ws_soul_path}",
                file=sys.stderr
            )
        else:
            print(
                f"[G5-FIX] PRIME DIRECTIVE already present in {ws_soul_path} - skipping (idempotent)",
                file=sys.stderr
            )

    return dept_dir


# ============================================================
# CEO / MASTER ORCHESTRATOR CANONICAL RULE (G5 - Trevor's "make it permanent")
# ============================================================
# This block is PREPENDED to the TOP of the CEO agent's MEMORY.md, SOUL.md,
# and IDENTITY.md by create_department_workspace() when dept_id is in the CEO
# set. NOT written to AGENTS.md or TOOLS.md (shared by all agents).
#
# Required clauses (per Opus audit + SOP-00 alignment):
#   1. Route-not-execute doctrine
#   2. Sub-agent-bypass clause (spawning a worker to do it = same violation)
#   3. Owner-explicit-permission exception
#   4. General Tasks fallback when department is unclear
#
# Idempotency: create_department_workspace() checks for the IDEMPOTENCY_MARKER
# before prepending - re-running the build never duplicates the block.

CEO_ORCHESTRATOR_IDEMPOTENCY_MARKER = "<!-- CEO_ORCHESTRATOR_RULE_V2 -->"
# V2 (PR2, 2026-06-09): Replaces V1 CANONICAL ORCHESTRATOR RULE with the PRIME DIRECTIVE
# verbatim from CANONICAL-ORCHESTRATOR-RULE.md (Trevor's sharpened + corrected version).
# Key changes:
#   - Header: PRIME DIRECTIVE (5-point numbered list) replaces the old table
#   - Bridge-leak fix: routing = POST department_slug to task board, NOT spawn sub-agent
#   - Owner-explicit-permission retained as point 3 (seek AND receive consent)
#   - General-tasks fallback retained as point 4
#   - R6 corrected: lists permitted actions only, no longer suggests sub-agent spawning
# Idempotency: files with V1 marker only will get V2 prepended on next build run.
CEO_ORCHESTRATOR_V1_MARKER = "<!-- CEO_ORCHESTRATOR_RULE_V1 -->"

CEO_ORCHESTRATOR_RULE = f"""{CEO_ORCHESTRATOR_IDEMPOTENCY_MARKER}
## ⛔ PRIME DIRECTIVE - I AM A TASK ROUTER. I ROUTE. THIS IS NOT OPTIONAL.

1. I am the master orchestrator (CEO). My one job is to ROUTE tasks. When any task or request
   reaches me, I ROUTE it to the correct DEPARTMENT - every time. I have NO permission to decide
   not to route, to refuse a task, or to choose what I will or will not do.
2. I do NOT do the work myself, and I do NOT pick the specialist or spawn/keep control of a
   sub-agent to do it. I route to the DEPARTMENT. The DEPARTMENT decides which specialist
   sub-agent and which persona are needed; the task gets a persona assigned; the task is placed
   on the Kanban board. The doing belongs to the department and its specialist - never to me.
3. Before I would EVER do a task myself, I must FIRST seek and RECEIVE explicit permission and
   consent from the owner (the human in control). Without that explicit consent, I route - always.
   (Routing is my default and is always allowed; I never need permission to route.)
4. If I cannot determine the right department, I route to the General Tasks department. I never
   self-execute because I'm unsure, and I never hold a task to "stay in control" of it.
5. What I MAY do: have conversations, manage agents, manage departments, and route tasks.
   What I may NEVER do: refuse to route, decide who executes, execute the work myself, or
   commandeer a sub-agent to keep control.

### Routing = Creating a DEPARTMENT TASK (not spawning a sub-agent directly)

The correct routing action is POST to `/api/tasks/ingest` with `department_slug: "<slug>"`.
This places the task on the department's Kanban - the DEPARTMENT assigns the specialist.

Spawning a sub-agent and instructing it to execute production work IS THE SAME VIOLATION as
executing the work yourself. If a sub-agent is spawned, it MUST read its own role files and
operate via the task board - it is not a production tool for the orchestrator.

### Binding Rules

- **R1** Never generate images, videos, audio, or written deliverables
- **R2** Never write to files, databases, or external APIs as a production action
- **R3** Never use any skill that produces a deliverable (`skills: []` enforced in config)
- **R4** Every actionable request → `POST /api/tasks/ingest` with `department_slug`
- **R5** If CC unreachable → escalate via Telegram, do NOT execute directly
- **R6** If route is unclear → use `department_slug: "general-task"`, never self-execute
- **R7** Permitted actions only: Telegram messaging, task-ingest POST, read workspace files, gateway restart

---
"""

# ============================================================
# READ-THE-SOP OPERATING PROTOCOL (canonical, embedded in every agent)
# ============================================================
# The wiring gap this closes: nothing previously told a director (or a spawned
# specialist sub-agent) to READ its role folder BEFORE working. The read-first
# rule lived only in the shared AGENTS.md + INSTRUCTIONS.md prose, so an agent
# that skipped AGENTS.md had no read-the-SOP directive in its OWN first-read
# files. DIRECTOR_OPERATING_PROTOCOL below is written verbatim into the
# director's IDENTITY.md/SOUL.md (generate_identity_md/generate_soul_md), so the
# protocol is present in the files the agent reads first - not dependent on the
# shared AGENTS.md being installed. The CEO / Master Orchestrator variant lives
# in create_role_workspaces.py (CEO_OPERATING_PROTOCOL there is the single source
# of truth, embedded by stub_identity/stub_soul via post-build-role-workspaces.py).

DIRECTOR_OPERATING_PROTOCOL = """## Operating Protocol - Read the SOP Before You Work (binding)

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
   covers the task, do NOT let the sub-agent proceed by guessing - fire the
   department SOP-Writer (INSTRUCTIONS.md Moment 3.7) to author the missing SOP
   first, or escalate.
4. **Review against the how-to before reporting.** When the sub-agent returns,
   review its output against the same how-to/SOP it was supposed to follow.
   Only then report results upward.

If the owner asks an INFORMATIONAL question about THIS department or one of its
specialists ("how do I use this department?", "what can you do for me?", "how do
I use the <specialist>?"), do NOT route it as work. Answer from this department's
own guide `how-to-use-this-department.md` (in this department folder), in plain
language, and never invent specialists or capabilities the guide does not list.
Full procedure: `universal-sops/answering-how-to-use-questions.md`.
"""


def generate_identity_md(dept_id, dept_info, interview_answers):
    """
    Generate IDENTITY.md for the dept head agent.

    Trevor's agent-file architecture (v10.13.23): every top-level agent has
    its own IDENTITY/SOUL/MEMORY/HEARTBEAT. Sub-agents inherit. SHARED files
    (USER/AGENTS/TOOLS) live at the workspace root and are symlinked.

    Kept intentionally lightweight - the agent fills in its persona name and
    voice during the first conversation with the owner.
    """
    company_name = interview_answers.get('company_name', 'the company')
    dept_name = dept_info.get('name', dept_id)
    head_title = dept_info.get('head', f"{dept_name} Lead")

    # PR2 bridge-leak fix: production depts (graphics/video/audio) get an explicit
    # KIE.ai / Fal.ai production tools note so specialists know they EXECUTE generation.
    # The CEO agent does NOT get this note (CEO IDENTITY.md goes through a separate
    # code path that prepends the PRIME DIRECTIVE and never adds this section).
    PRODUCTION_DEPT_IDS = {"graphics", "video", "audio", "video-production", "audio-production"}
    is_production_dept = dept_id in PRODUCTION_DEPT_IDS or any(
        p in dept_id for p in ("graphic", "video", "audio")
    )
    production_tools_note = ""
    if is_production_dept:
        production_tools_note = """
## Production Tools - I Execute These (the CEO does not)

As a department specialist I am authorized and expected to invoke AI generation tools directly:

- **KIE.ai** (`KIE_API_KEY`) - image generation (Nano Banana, Seedream, Flux), video generation
  (VEO 3.1 Fast, Luma Dream Machine), audio/TTS endpoints. Primary production API.
- **Fal.ai** (`FAL_API_KEY`) - alternative image/video generation endpoints (Flux Pro, SDXL).
- **OpenClaw built-in skills** - `image_generate`, `video_generate`, `tts` (when available).

The Master Orchestrator NEVER invokes these directly. When a task reaches this department,
this agent (or the specialist it delegates to) runs the generation and delivers the output.
"""

    return f"""# IDENTITY.md - {head_title}

**Department:** {dept_name}
**Company:** {company_name}
**Generated by:** build-workforce.py (Skill 23)

## Who I Am

- **Name:** (assign during first conversation - capture the persona/name the owner gives this agent)
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
{production_tools_note}
## Persona Governance

When the owner assigns me a persona, I adopt its voice and style while still
honoring the mission in SOUL.md and the values in USER.md. If a persona's
instructions conflict with company values, I surface the conflict before acting.

{DIRECTOR_OPERATING_PROTOCOL}
---

This file is unique to this agent. Sub-agents under this department inherit
from this IDENTITY but write their own role-specific IDENTITY.md.
"""


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
# canonical floor folder ids (customer-support/crm/graphics/openclaw-
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
    map can never drift from the canonical floor again.
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
    print(f"[DEPT-MAP ASSERT] OK - all {len(resolved)} departments resolve to an existing "
          f"suggested-roles file in {roles_dir}", file=sys.stderr)
    return resolved


def _clean_role_slug(name):
    """
    Defensive role-NAME -> folder-slug normalizer.

    Strips the roster decorations the canary found baked into folder slugs:
      - parentheticals like "(NEW)", "(NEW -- v1.7)", "(renamed from ...)"
      - trailing version/status tails: "-- v1.7", "NEW -- v11.23.0", "vX.Y"
      - punctuation that has no place in a slug: apostrophes, "&", "+", "/",
        em/en dashes
    so that NO spec, however decorated its `### N.` header, can bake junk like
    `21-audio-demonstration-+-fish-audio-expression-specialist-new--v1.7` or
    `11-devil's-advocate--presentations` into a folder name. This is the
    belt-and-suspenders for defect #1: even when an explicit **Slug:** is
    missing, the derived slug is clean.

    The canonical/authoritative key is the explicit **Slug:** line in the
    roster; this helper is only the fallback when that is absent.
    """
    import re as _re
    s = str(name or "")
    # Drop any parenthetical decoration entirely: "(NEW -- v1.7)", "(renamed ...)"
    s = _re.sub(r"\([^)]*\)", " ", s)
    # Normalize ampersand/plus/slash and dashes to spaces/words.
    s = s.replace("&", " and ").replace("+", " ").replace("/", " ")
    s = s.replace("—", " ").replace("–", " ")  # em/en dash
    s = s.lower()
    # Strip trailing version/status tails like "-- v1.7", "new v11.23.0".
    s = _re.sub(r"\bnew\b", " ", s)
    s = _re.sub(r"\bv\d+(?:\.\d+)*\b", " ", s)
    # Keep only [a-z0-9] runs, collapse to single dashes (drops apostrophes).
    s = _re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    s = _re.sub(r"-{2,}", "-", s)
    return s


def _legacy_naive_slug(name):
    """The EXACT pre-fix slug chain. KEPT only as a reference; no longer called
    by role_folder_basename (see _engine_slugify below). Callers that depended
    on the naive behavior should migrate to _engine_slugify for prover alignment.
    """
    s = str(name or "").lower()
    s = s.replace(' ', '-').replace('(', '').replace(')', '').replace('/', '-')
    s = s.replace('--', '-').strip('-')
    return s


def _engine_slugify(name):
    """
    PROVER-ALIGNED slug function: identical algorithm to create_role_workspaces.slugify().

    Replaces every non-alphanumeric character with a single dash and strips
    leading/trailing dashes. This is the SINGLE SOURCE OF TRUTH for the
    no-explicit-slug fallback, shared with floor-fill-driver.py via the engine.

    Why this function (not _legacy_naive_slug):
      _legacy_naive_slug keeps apostrophes, '&', '.', '()', causing folder names
      the prover cannot reconcile (e.g. "Devil's Advocate" -> devil's-advocate
      vs the manifest slug devils-advocate). _engine_slugify collapses every
      non-alnum to a single dash, which matches what create_role_workspaces and
      the role-library .md filenames produce.
    """
    s = str(name or "").lower().strip()
    out = []
    prev_dash = False
    for ch in s:
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif not prev_dash:
            out.append("-")
            prev_dash = True
    return "".join(out).strip("-")


def role_folder_basename(role):
    """
    Canonical folder basename for a role: `NN-<slug>`.

    PROVER-ALIGNED SLUG PRECEDENCE (floor-fill-driver / create_role_workspaces parity):
      1. Explicit role['slug'] from the roster **Slug:** line (authoritative).
         Used VERBATIM — never passed through _clean_role_slug — so the folder
         name is byte-identical to the role-library .md filename and the prover
         floor-manifest slug. (Previously _clean_role_slug changed '.' -> '-',
         causing 'ai-voice-specialist-11-labs-play.ht' to land on disk as
         '...-play-ht' and fail the prover.)
      2. NO explicit slug -> _engine_slugify(role['name']): collapses every
         non-alnum to a single dash, stripping apostrophes, '&', '.', etc.
         This matches what create_role_workspaces.slugify() and the engine
         produce, so the prover can always reconcile the folder.
         (Previously _legacy_naive_slug kept apostrophes and '&' verbatim,
         yielding folders like "devil's-advocate-presentations" and
         "subscription-&-recurring-..." that the prover could not reconcile.)
    Number is zero-padded to 2 digits.
    """
    explicit = (role.get('slug') or '').strip()
    if explicit:
        # Use the canonical roster slug VERBATIM — single source of truth.
        slug = explicit or _engine_slugify(role.get('name') or '')
    else:
        slug = _engine_slugify(role.get('name') or '')
    num = role.get('number', 0)
    try:
        num = int(num)
    except (TypeError, ValueError):
        num = 0
    return f"{num:02d}-{slug}"


def parse_suggested_roles(dept_id):
    """
    Read and parse the suggested-roles markdown file for a department.
    Returns a list of role dicts with keys:
      - number: int (role number, 0 = department head)
      - name: str
      - slug: str (explicit canonical slug from the roster, or '' if absent)
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
                'slug': '',  # populated below if an explicit **Slug:** line follows
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
                'slug': '',
                'description': '',
                'sops': [],
                'persona_traits': '',
                'is_qc': True,
            }

        elif current_role:
            # Parse role content
            if line.startswith('**Slug:**'):
                # Explicit canonical slug. This is the AUTHORITATIVE key for both
                # the folder name (NN-<slug>/) and the role-library lookup. When
                # present it removes all ambiguity from decorated role names.
                current_role['slug'] = line.replace('**Slug:**', '').strip()
            elif line.startswith('**What it does:**'):
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

    # TABLE-FORMAT FALLBACK (FIX 4, 2026-06-17, repo-consistency gate):
    # general-task + project-architecture-office list roles in a markdown table
    # (`| # | Slug | Title | Type | Purpose |`) instead of `### N.` headers. The
    # header parser above returns 0 roles for them, so they would build ZERO
    # specialists despite shipping full role-library templates. When no `### N.`
    # roles were parsed, fall back to the role table. Kept in lockstep with
    # create_role_workspaces.parse_roster / _parse_roster_table.
    if not roles:
        roles = _parse_suggested_roles_table(content)

    return roles


def _parse_suggested_roles_table(content):
    """Parse a `| # | Slug | Title | Type | Purpose |` role table.

    Mirrors create_role_workspaces._parse_roster_table but returns the dict shape
    parse_suggested_roles produces (number/name/slug/description/sops/
    persona_traits/is_qc). Returns [] if no recognizable table is present.
    """
    import re as _re
    roles = []
    cols = None
    for line in content.split('\n'):
        s = line.strip()
        if not s.startswith('|'):
            cols = None
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        if all(_re.fullmatch(r':?-{2,}:?', c or '-') for c in cells):
            continue
        lowered = [c.lower().strip('` ') for c in cells]
        if cols is None:
            idx = {name: i for i, name in enumerate(lowered)}
            if 'slug' in idx and 'title' in idx:
                cols = idx
            continue

        def cell(name):
            i = cols.get(name)
            return cells[i].strip().strip('`') if i is not None and i < len(cells) else ''
        slug = cell('slug')
        title = cell('title')
        if not slug and not title:
            continue
        num = cell('#')
        try:
            number = int(num)
        except ValueError:
            number = len(roles)
        rtype = cell('type').lower()
        roles.append({
            'number': number,
            'name': (title or slug).strip(),
            'slug': slug,
            'description': cell('purpose'),
            'sops': [],
            'persona_traits': '',
            'is_qc': rtype == 'qc' or 'quality control' in title.lower()
                     or 'qc ' in title.lower(),
        })
    return roles


def _instantiate_role_from_library(role_name, dept_id, interview_answers):
    """
    WS-2: PRIMARY-PATH library instantiation.

    Look up the pre-written role-library template for (role_name, dept_id) via
    the normalizer. If found, copy it and token-personalize it with this
    client's interview context ({{COMPANY_NAME}} / {{COMPANY_INDUSTRY}} /
    {{ASSIGNED_PERSONA}} / {{GENERATION_DATE}} and the rest). The returned
    string is the role's full how-to.md INCLUDING its pre-written Section 9
    SOPs - so no empty `[Step 1 ...]` stubs and no LLM regeneration are needed.

    Returns the personalized content string, or None when no template matches
    (genuinely missing role → caller keeps the legacy stub+LLM path).

    Deterministic: same template + same interview context → byte-identical
    output across clients (this is what makes every client identical).
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
    # v12.17.2: extended with director/head-of titles, persona version, and
    # ISO_DATE_YEAR so the most-frequent tokens are pre-filled even if the
    # _crw_fill_tokens backstop is unavailable.
    _gen_year = gen_date[:4]
    _dept_director = "Master Orchestrator" if dept_lib == "master-orchestrator" \
                     else f"Director of {dept_display}"
    def _head_of_bwpy(area):
        return f"Head of {area}"

    out = raw
    primary_tokens = {
        "COMPANY_NAME": company_name,
        "company_name": company_name,
        "CompanyName": company_name,
        "COMPANY_INDUSTRY": industry,
        "INDUSTRY_VERTICAL": industry,
        "INDUSTRY": industry,
        "ROLE_TITLE": role_name,
        "DEPARTMENT_NAME": dept_display,
        "GENERATION_DATE": gen_date,
        "ISO_DATE": gen_date,
        "ISO_DATE_YEAR": _gen_year,
        "YEAR": _gen_year,
        "Year": _gen_year,
        "DIRECTOR_OR_MASTER_ORCHESTRATOR": _dept_director,
        "DIRECTOR_TITLE": _dept_director,
        "SALES_DIRECTOR_TITLE": _head_of_bwpy("Sales"),
        "HEAD_OF_AUDIO_PRODUCTION_TITLE": _head_of_bwpy("Audio Production"),
        "HEAD_OF_CONTENT_TITLE": _head_of_bwpy("Content"),
        "HEAD_OF_CUSTOMER_SUCCESS_TITLE": _head_of_bwpy("Customer Success"),
        "HEAD_OF_EDUCATION_TITLE": _head_of_bwpy("Education"),
        "HEAD_OF_MARKETING_TITLE": _head_of_bwpy("Marketing"),
        "HEAD_OF_PRODUCT_TITLE": _head_of_bwpy("Product"),
        "HEAD_OF_SALES_TITLE": _head_of_bwpy("Sales"),
        "HEAD_OF_SECURITY_TITLE": _head_of_bwpy("Security"),
        "HEAD_OF_VIDEO_PRODUCTION_TITLE": _head_of_bwpy("Video Production"),
        "HEAD_OF_VIDEO_TITLE": _head_of_bwpy("Video"),
        "HEAD_OF_WEB_DEVELOPMENT_TITLE": _head_of_bwpy("Web Development"),
        "CHIEF_FINANCIAL_OFFICER_TITLE": "Chief Financial Officer",
        "CHIEF_MARKETING_OFFICER_TITLE": "Chief Marketing Officer",
        "CHIEF_LEGAL_OFFICER_TITLE": "Chief Legal Officer",
        "CHIEF_REVENUE_OFFICER_TITLE": "Chief Revenue Officer",
        "CTO_TITLE": "Chief Technology Officer",
        # ASSIGNED_PERSONA is selected per-task at dispatch by persona-selector;
        # leave a neutral placeholder so the doc reads cleanly until then.
        "ASSIGNED_PERSONA": "(selected per task by persona-selector)",
        "ASSIGNED_PERSONA_VERSION": "1",
        "CURRENTLY_ASSIGNED_PERSONA": "(selected per task by persona-selector)",
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

    # BUG 1 FIX: only stamp the instantiation marker AFTER confirming the filled
    # content is substantive (>= 3072 bytes — the same floor that verify-wiring.sh
    # and qc-completeness.sh enforce).  A prior bug allowed the marker to be placed
    # on thin stubs (e.g. 156 B), causing the library gate to pass (it trusted the
    # marker) while the wiring gate failed (it checked real size).  Returning None
    # here causes the caller to fall back to the PENDING-stub path, which is
    # correctly flagged as unfilled by every subsequent gate.
    _LIBRARY_FILL_MIN_BYTES = 3072  # matches HOW_TO_MIN_BYTES in verify-wiring.sh
    out_bytes = len(out.encode("utf-8"))
    if out_bytes < _LIBRARY_FILL_MIN_BYTES:
        print(
            f"[ROLE-LIBRARY WARNING] _instantiate_role_from_library: filled content "
            f"for '{role_name}' ({dept_id}) is {out_bytes} bytes — below "
            f"{_LIBRARY_FILL_MIN_BYTES}B floor.  Returning None so caller uses "
            f"PENDING-stub path instead of stamping thin output as 'done'.",
            file=sys.stderr,
        )
        return None

    # PER-ARTIFACT PROVENANCE (v12.27.0): stamp the resolved SOURCE content_sha +
    # content_version COPIED FROM THE MANIFEST entry (role_entry IS the
    # _index.json entry that _crw_library_lookup returned; it now carries
    # content_sha/content_version stamped by hash-content-manifest.py). This is
    # the SOURCE hash — NEVER a hash of the rendered client file — and is the
    # ground-truth fallback / tamper check that detect-stale-artifacts.py greps
    # when the build-state.artifactProvenance fast path is missing. The old marker
    # rendered `v?` (no version field existed) and carried no sha.
    _re = role_entry or {}
    _content_sha = _re.get("content_sha", "sha256:UNKNOWN")
    _content_ver = _re.get("content_version", "?")
    _slug = _re.get("slug", "?")
    _dept = _re.get("dept", dept_id)
    header = (
        f"<!-- workforce-provenance: source=role-library "
        f"role-slug={_slug} dept={_dept} content_sha={_content_sha} "
        f"content_version={_content_ver} instantiated={gen_date} "
        f"generator=build-workforce.py. Pre-written Section-9 SOPs included - "
        f"not LLM-regenerated. -->\n"
    )

    # Record the SOURCE provenance for the build-state roll-up (fast-path detection).
    # Key by "<dept>/<role-slug>" — the same key detect-stale-artifacts.py builds
    # from the manifest. source_path is the canonical library file this came from.
    try:
        _prov_key = f"{_dept}/{_slug}"
        _ARTIFACT_PROVENANCE[_prov_key] = {
            "source_content_sha": _content_sha,
            "source_content_version": _content_ver,
            "instantiatedAt": gen_date,
            "sourcePath": _re.get("path", ""),
        }
    except Exception:
        pass  # provenance accounting must never break a build

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
        # ── PROVER-ALIGNMENT (v13.8.14): route folder creation through the ENGINE ──
        # Single source of truth for the on-disk folder slug: the SAME
        # create_role_workspaces.create_role_workspace() floor-fill-driver.py uses.
        # The engine slugs via role_metadata['slug'] VERBATIM (with slugify() as the
        # no-slug fallback), so the folder name is byte-identical to the role-library
        # .md filename and the floor-manifest slug. It also writes the unique
        # IDENTITY/SOUL/MEMORY/HEARTBEAT files, the SOP/00-INDEX.md, and the shared
        # AGENTS/TOOLS/USER symlinks. build-workforce then writes its EXTRA artifacts
        # (how-to.md from the role-library, 00-START-HERE.md, governing-personas.md,
        # and SOP stubs) INTO the engine-created role_path. role_dir/folder_name are
        # derived FROM the engine result so the two paths can never drift again.
        #
        # DEFECT #1 FIX (retained): the bare slug is the explicit roster **Slug:**
        # (authoritative) or the engine-slugified role name — never the raw name.
        _role_number = role.get('number', 0)
        try:
            _role_number = int(_role_number)
        except (TypeError, ValueError):
            _role_number = 0
        _role_metadata = {
            "slug": (role.get('slug') or '').strip(),
            "number": _role_number,
            "is_ceo": (_role_number == 0 and (role.get('slug') or '').strip() == "master-orchestrator"),
            "is_qc": bool(role.get('is_qc')),
        }
        if _ENGINE_ROLE_WRITER_AVAILABLE:
            try:
                _engine_path = _crw_create_role_workspace(
                    dept_dir, role['name'], (COMPANY_DIR or WORKSPACE_ROOT),
                    role_metadata=_role_metadata)
                role_dir = str(_engine_path)
                folder_name = os.path.basename(role_dir)
            except Exception as _eng_err:  # pragma: no cover - defensive
                print(f"[ROLE-WORKSPACE WARNING] engine create_role_workspace failed "
                      f"for {role['name']} ({_eng_err}); using in-file folder writer",
                      file=sys.stderr)
                folder_name = role_folder_basename(role)
                role_dir = os.path.join(dept_dir, folder_name)
                os.makedirs(role_dir, exist_ok=True)
        else:
            # Legacy fallback (engine unavailable): in-file folder writer. Uses the
            # SAME role_folder_basename() helper so the slug stays prover-aligned.
            folder_name = role_folder_basename(role)
            role_dir = os.path.join(dept_dir, folder_name)
            os.makedirs(role_dir, exist_ok=True)
        role_slug = folder_name.split('-', 1)[1] if '-' in folder_name else folder_name

        # ── MSF Layer-2: resolve capability class for this role (v1.0.0) ────────
        # Infer the role's capability class from the MSF ruleset. This is a
        # fast in-process call (no subprocess) — graceful no-op if model_selector
        # is unavailable. Result is stamped into 00-START-HERE.md and used to
        # pick the best-available model for this specific role.
        _msf_cls_info = get_role_capability_class(role_slug, dept_id)
        _msf_class = _msf_cls_info.get("capability_class", "")
        _msf_vision = _msf_cls_info.get("vision_flag", False)

        # ── WS-2: INSTANTIATE from the pre-written role-library (the fix) ──────
        # Before writing any empty `[Step 1 ...]` SOP stub, try to copy +
        # token-personalize the role's pre-written library template (which
        # already carries its full Section-9 SOPs). If it matches, write it as
        # how-to.md, mark the folder instantiated (so the SOP-research manifest
        # skips it and no LLM regeneration runs), and SKIP the stub loop below.
        # LLM generation is reserved for genuinely missing roles only.
        # DEFECT #1b FIX: prefer the explicit canonical slug as the library key.
        # The normalizer resolves a slug or a name, but a decorated name (e.g.
        # "Offer and Price Strategist (NEW)" or "Devil's Advocate -- Presentations")
        # missed the library. The clean slug ("offer-price-strategist",
        # "devils-advocate-presentations") always hits its `.md`.
        _lib_key = (role.get('slug') or '').strip() or role['name']
        library_how_to = _instantiate_role_from_library(
            _lib_key, dept_id, interview_answers)
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
                  f"- writing PENDING how-to.md stub (collected in PENDING-SOPS.md)",
                  file=sys.stderr)
            # Gap-3: NO_TEMPLATE roles must NOT leave a silent empty stub. Write a
            # how-to.md clearly headed PENDING, carrying the EXACT one-shot
            # instruction to populate it FROM the nearest role-library template
            # family (token-fill, NOT a free-form LLM essay). It is also collected
            # into the company-root PENDING-SOPS.md manifest so the orchestrator
            # knows what to fill - never silent.
            # v13.8.14: the engine (create_role_workspace) already wrote a PENDING
            # stub how-to.md when no library matched. Overwrite it with
            # build-workforce's richer PENDING how-to (company/industry tokens +
            # the company-root PENDING-SOPS.md one-shot fill instruction). Both
            # carry the [PENDING - FILL FROM LIBRARY] marker the manifest scans for.
            how_to_path = os.path.join(role_dir, "how-to.md")
            if True:
                pending_how_to = f"""# {role['name']} - how-to.md  [PENDING - FILL FROM LIBRARY]

**Department:** {dept_info['name']} ({dept_info['emoji']})
**Company:** {company_name}
**Industry:** {industry}
**Status:** PENDING - no role-library template matched this role.

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
SOP covers the task, do not guess - escalate to the {dept_info['head']} so the
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

            # MSF: include capability_class so the agent knows its class and
            # the model selection logic is self-documenting in every role dir.
            _msf_class_line = ""
            if _msf_class:
                _vision_marker = " +VISION" if _msf_vision else ""
                _msf_class_line = (
                    f"**Capability Class:** {_msf_class}{_vision_marker}  "
                    f"*(model selection tier — see MODEL-SELECTION-FRAMEWORK.md)*\n"
                )

            content = f"""# {role['name']}

**Department:** {dept_info['name']} ({dept_info['emoji']})
**Company:** {company_name}
**Industry:** {industry}
**Role Type:** {role_type}
{_msf_class_line}
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

        # 3. Create SOP stub files - ONLY for roles with no library template.
        # WS-2: when the role was instantiated from the library, its full
        # Section-9 SOPs already live inside how-to.md; writing empty
        # `[Step 1 ...]` stubs here would re-introduce the LLM-regeneration bug.
        role_was_instantiated = (
            os.path.abspath(role_dir) in _LIBRARY_INSTANTIATED_ROLE_DIRS)
        for sop_filename in ([] if role_was_instantiated else role['sops']):
            # SANITIZE (fleet bugfix): SOP titles parsed from suggested-roles
            # files can contain path-unsafe chars (e.g. '(McKinsey/HBR/IBISWorld/
            # Statista)'); a raw '/' makes os.path.join nest into a non-existent
            # subdir and crashes the whole build with FileNotFoundError. Flatten.
            _safe_sop = sop_filename.replace(os.sep, '-').replace('/', '-').strip()
            sop_path = os.path.join(role_dir, _safe_sop)
            if not os.path.isfile(sop_path):
                sop_name = _safe_sop.replace('.md', '').replace('-', ' ').title()
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
# the AI agent running this build, not by this script - this script writes a
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
    # PRD 2.12: boundary gate tracking - record per-dept canonical status so
    # populate-sops-from-manifest.py and verify-library-gate.sh can assert the
    # invariant without re-computing canonicity independently.
    boundary_canonical = []   # dept_ids that are canonical (should NOT be here)
    boundary_custom = []      # dept_ids that are genuinely custom (authoring OK)

    for dept_id, dept_info in departments.items():
        dept_dir = os.path.join(DEPARTMENTS_DIR, dept_id)
        if not os.path.isdir(dept_dir):
            continue

        # PRD 2.12 - BOUNDARY GATE pre-check: if a canonical dept ends up in
        # this manifest it means _instantiate_role_from_library() failed for
        # all its roles (library lookup miss or _LIBRARY_FILL_AVAILABLE=False).
        # Log LOUDLY and SKIP - the authoring path must never run for canonical
        # depts. Token economics: pre-written templates exist precisely for this.
        if _BW_BOUNDARY_GATE_AVAILABLE and _bw_is_canonical_dept(dept_id):
            boundary_canonical.append(dept_id)
            print(
                f"[SOP-BOUNDARY-GATE] REFUSE manifest entry for canonical dept '{dept_id}'. "
                f"All roles in this dept should have been instantiated from the role-library "
                f"(via _instantiate_role_from_library) before reaching this point. "
                f"Check that _LIBRARY_FILL_AVAILABLE=True and the library lookup succeeded. "
                f"Skipping this dept - it will NOT be authored by LLM sub-agents.",
                file=sys.stderr,
            )
            continue

        # Track custom depts (genuinely eligible for authoring)
        if _BW_BOUNDARY_GATE_AVAILABLE:
            boundary_custom.append(dept_id)

        # Collect every SOP stub that needs population
        sop_files = []
        for entry in os.listdir(dept_dir):
            role_dir = os.path.join(dept_dir, entry)
            if not os.path.isdir(role_dir) or entry == "memory" or entry == "devils-advocate":
                continue
            # WS-2: skip roles instantiated from the library - their Section-9
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

    # PRD 2.12 BUILD GATE summary line - loud observability for the operator.
    if _BW_BOUNDARY_GATE_AVAILABLE:
        if boundary_canonical:
            print(
                f"[SOP-BOUNDARY-GATE] BUILD GATE WARNING: {len(boundary_canonical)} canonical dept(s) "
                f"were REFUSED from the authoring manifest: {boundary_canonical}. "
                f"These depts' SOPs must come from the role-library copy path. "
                f"Verify _LIBRARY_FILL_AVAILABLE=True and re-run build if their role files are empty.",
                file=sys.stderr,
            )
        print(
            f"[SOP-BOUNDARY-GATE] Manifest boundary gate: "
            f"canonical_refused={len(boundary_canonical)} custom_queued={len(boundary_custom)}",
            file=sys.stderr,
        )

    manifest = {
        "version": "1.0",
        "company": company_name,
        "company_slug": COMPANY_SLUG,
        "industry": industry,
        "generated_at": datetime.now().isoformat(),
        "max_parallel_sub_agents": 10,
        "departments": entries,
        "sub_agent_instructions": LEAN_SIX_SIGMA_SOP_PROMPT,
        # PRD 2.12: boundary gate field - consumed by populate-sops-from-manifest.py
        # and verify-library-gate.sh to assert no canonical dept entered authoring.
        "boundary_gate": {
            "canonical_refused": boundary_canonical,
            "custom_queued": boundary_custom,
            "gate_available": _BW_BOUNDARY_GATE_AVAILABLE,
        },
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"[SOP-MANIFEST] Wrote {manifest_path} with {len(entries)} custom dept(s) queued for authoring", file=sys.stderr)
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
  - Done criteria - MEASURABLE, not vague. e.g. 'Email scheduled, subject line A/B tested, segment confirmed'

  ## MEASURE
  - KPIs this task moves. Numbers, not adjectives.
  - How those KPIs map to the department KPIs: {DEPT_KPIS}
  - How department KPIs roll up to company KPIs.

  ## ANALYZE (when the task underperforms)
  - Root-cause checklist. Five Whys. Not symptom-chasing.
  - Common failure modes specific to this industry: research them via Perplexity.

  ## IMPROVE - Step-by-Step
  - Numbered concrete steps. Each step references a specific tool from: {DEPT_TOOLS}
  - Each step is something an AI agent can ACTUALLY do (read file X, call API Y, post to channel Z).
  - Embody the role's persona expertise. If the persona is John Maxwell for a leadership role, use Maxwell's principles verbatim where applicable.

  ## CONTROL
  - Devil's Advocate checkpoints. What the DA verifies before declaring done.
  - The DA must validate measurable criteria from DEFINE, not subjective taste.

  ## ESCALATION + RESEARCH RULE (binding - paste this section verbatim into every SOP)
  If you hit an edge case not covered above:
    - DO NOT GUESS. Guessing is forbidden for any AI employee.
    - You are either ABSOLUTELY SURE of the next step (proceed) or you are NOT SURE (research).
    - If not sure: run Perplexity research (`openrouter/perplexity/sonar-pro-search`) with a specific query, OR escalate to the {DEPT_HEAD}.
    - Document the edge case AND the research outcome in {DEPT_DIR}/memory/[YYYY-MM-DD].md.

Hard constraints:
  - NEVER reference Anthropic models. Use the selector chain heavy tier when invoking models.
  - Plain English. No corporate jargon.
  - Tools referenced must be from {DEPT_TOOLS}. If a useful tool is missing from that list, recommend it under a 'Suggested tool additions' section at the bottom - don't pretend it's available.
  - Cite Perplexity research findings inline when a step is derived from research. e.g. 'Per industry benchmark (Perplexity 2026-05-13): companies in {INDUSTRY} typically...'

For each role folder in this department, you'll find:
  - 00-START-HERE.md (DO NOT rewrite - already contains role context)
  - governing-personas.md (DO NOT rewrite - already lists persona traits)
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
                # fleet-standard default. Never the deprecated moonshot/kimi-k2.5 -
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
    # Map department IDs to relevant domain tags.
    # Valid domain keys (from persona-categories.json domainTags):
    #   marketing, sales, leadership, finance, operations, communication,
    #   copywriting, mindset, productivity-systems, coaching,
    #   strategy-innovation, personal-development
    # FIX 2 (2026-06-17): added 12 canonical departments that were missing,
    # causing all of them to fall back to the generic ["leadership"] pool.
    # FIX 3 (2026-06-17, repo-consistency gate): selected_departments keys on the
    # CANONICAL dept ids (billing-finance, customer-support, web-development,
    # app-development, communications, openclaw-maintenance, social-media,
    # paid-advertisement, crm, quality-control, account-management) — NOT the
    # legacy short ids (billing/support/webdev/comms/...). Those canonical ids were
    # missing here, so 11 floor depts silently fell back to ['leadership']. Every
    # FLOOR dept id is now a key (legacy ids kept as aliases for old configs).
    # This map is enforced by scripts/qc-assert-repo-consistency.py.
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
        # --- FIX 2 additions (2026-06-17) ---
        "presentations": ["copywriting", "marketing", "communication"],
        "bugs": ["productivity-systems", "strategy-innovation", "operations"],
        "healer": ["coaching", "personal-development", "mindset"],
        "personal-assistant": ["operations", "leadership", "productivity-systems"],
        "engineering": ["software-craft", "productivity-systems", "strategy-innovation", "operations"],
        "listings": ["marketing", "sales", "copywriting"],
        "logistics-fulfillment": ["operations", "productivity-systems"],
        "podcast": ["copywriting", "communication", "marketing"],
        "scheduling-dispatch": ["operations", "productivity-systems", "leadership"],
        "general-task": ["operations", "productivity-systems", "leadership"],
        "project-architecture-office": ["strategy-innovation", "leadership", "operations"],
        "project-management": ["leadership", "strategy-innovation", "productivity-systems"],
        # --- FIX 3 additions (2026-06-17): CANONICAL floor dept ids ---
        "billing-finance": ["finance", "operations"],
        "customer-support": ["communication", "coaching"],
        "web-development": ["strategy-innovation", "marketing", "productivity-systems"],
        "app-development": ["strategy-innovation", "productivity-systems"],
        "communications": ["communication", "leadership", "marketing"],
        "openclaw-maintenance": ["productivity-systems", "strategy-innovation", "operations"],
        "social-media": ["marketing", "communication", "copywriting"],
        "paid-advertisement": ["marketing", "copywriting", "strategy-innovation"],
        "crm": ["sales", "communication", "operations"],
        "quality-control": ["productivity-systems", "operations", "strategy-innovation"],
        "account-management": ["communication", "coaching", "strategy-innovation"],
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
# work - the director->specialist dispatch lived only in runtime LLM reasoning.
# These generators emit, at build time:
#   - <dept>/ROSTER.md            (one row per role folder + a when-to-use line;
#                                  the director's OPERATING PROTOCOL references it)
#   - universal-sops/00-ROUTING.md (company-wide task-type -> department map)
# They are derived from the SAME parse_suggested_roles() the folder builder uses,
# so the roster role slugs always match the on-disk NN-role-slug/ folders.


def _role_folder_slug(role):
    """Reproduce the NN-role-slug/ folder name create_role_workspace() writes.

    Delegates to the single canonical helper so the org-chart / routing docs use
    the SAME clean, decoration-stripped, explicit-slug-aware name as the folder
    builder. (Previously this duplicated a naive slug that baked in decorations.)
    """
    return role_folder_basename(role)


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
    """Write <dept>/ROSTER.md - the machine-readable When-to Reference Map the
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

    # ROOT-CAUSE FIX (2026-06-18): prefer the disk-truth roster. write_department_
    # roster runs AFTER create_role_workspace + materialize_custom_roles, so the
    # role folders already exist on disk. Listing them (not just the menu) means
    # ROSTER.md reflects custom/extra roles and partial builds, and the SAME helper
    # backs every other materialization path — so the roster can never under-report
    # the roles an agent actually has. Falls back to the menu-derived body below
    # only if the helper is unavailable or no folders exist yet.
    if _ROSTER_DISK_TRUTH_AVAILABLE:
        try:
            _disk_roles = _crw_scan_department_roles_on_disk(dept_dir)
        except Exception:
            _disk_roles = None
        if _disk_roles:
            try:
                return _crw_regenerate_department_roster(
                    dept_dir,
                    dept_name=dept_info.get("name"),
                    dept_head=dept_info.get("head", dept_info.get("name", dept_id)),
                    dept_emoji=dept_info.get("emoji", ""),
                )
            except Exception as _e:  # pragma: no cover - never block the build
                print(f"[ROSTER] disk-truth generator failed for {dept_id} "
                      f"({_e}); falling back to menu-derived roster", file=sys.stderr)

    roles = parse_suggested_roles(dept_id)
    lines = [
        f"# ROSTER - {dept_info['name']} ({dept_info.get('emoji', '')})",
        "",
        f"**Department head:** {dept_info.get('head', dept_id)}",
        "**This is the When-to Reference Map for this department.** Before you "
        "dispatch ANY task, find the row whose *When to use* matches the task, "
        "then spawn a sub-agent and have it read that role folder IN ORDER: "
        "`00-START-HERE.md` -> `IDENTITY.md` -> `SOUL.md` -> `how-to.md` -> "
        "`governing-personas.md`, then execute per the how-to. If no row matches, "
        "escalate to the CEO - do not guess.",
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
        lines.append("| _(no roles resolved - investigate dept->menu mapping)_ |  |  |  |")

    lines += [
        "",
        "## How the director dispatches",
        "1. Match the task to a row above (When to use).",
        "2. Spawn a sub-agent; instruct it to read that role folder in order and "
        "act AS IF it IS that role.",
        "3. If the role's `how-to.md` / `SOP/` does not cover the task, fire the "
        "department SOP-Writer (INSTRUCTIONS.md Moment 3.7) before proceeding - "
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


def write_department_how_to_use(dept_id, dept_info, company_name=""):
    """Write <dept>/how-to-use-this-department.md - the OWNER-FACING plain-language
    guide to the department and the specialists inside it.

    This is the companion to ROSTER.md: ROSTER.md is the director's internal
    dispatch map; this guide is what the owner reads (and what the agent answers
    FROM) when they ask "how do I use the X department?" or "how do I use the
    <specialist>?". The specialist list is derived from this department's REAL
    roster (parse_suggested_roles), so the guide always matches what exists.

    Uses the shared renderer in how_to_use_department.render_how_to_use, the same
    module that generates the committed (tokenized) templates under
    templates/role-library/<dept>/. Company tokens are filled here at build time.
    Degrades gracefully: if the renderer is unavailable, the build is not blocked.
    """
    if not DEPARTMENTS_DIR:
        return None
    dept_dir = os.path.join(DEPARTMENTS_DIR, dept_id)
    if not os.path.isdir(dept_dir):
        print(f"[HOW-TO-USE] dept dir missing for {dept_id}; skipping", file=sys.stderr)
        return None

    try:
        _scripts_dir = os.path.dirname(os.path.abspath(__file__))
        if _scripts_dir not in sys.path:
            sys.path.insert(0, _scripts_dir)
        import how_to_use_department as _htu
    except Exception as e:  # noqa: BLE001 - never block the build on the guide
        print(f"[HOW-TO-USE] renderer unavailable ({e}); skipping {dept_id}", file=sys.stderr)
        return None

    # Pass the REAL parsed roster so the guide lists this department's own
    # specialists (the renderer shapes parse_suggested_roles output for us).
    roles = parse_suggested_roles(dept_id)
    explicit_roles = None
    if roles:
        explicit_roles = [
            {
                "number": r.get("number", 50),
                "name": r.get("name", ""),
                "description": r.get("description", ""),
                "is_head": r.get("number", 50) == 0,
                "is_qc": bool(r.get("is_qc")),
            }
            for r in roles
        ]

    tokens = {
        "COMPANY_NAME": company_name or "your business",
        "GENERATION_DATE": datetime.now().strftime("%B %d, %Y"),
    }
    try:
        md = _htu.render_how_to_use(dept_id, roles=explicit_roles, tokens=tokens)
    except Exception as e:  # noqa: BLE001
        print(f"[HOW-TO-USE] render failed for {dept_id} ({e}); skipping", file=sys.stderr)
        return None

    out_path = os.path.join(dept_dir, "how-to-use-this-department.md")
    with open(out_path, 'w') as f:
        f.write(md)
    print(f"[HOW-TO-USE] Wrote {out_path}", file=sys.stderr)
    return out_path


def write_universal_routing_map(departments):
    """Write universal-sops/00-ROUTING.md - the company-wide master routing file
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
        "# 00-ROUTING.md - Master Task Routing",
        "",
        "The CEO / Master Orchestrator reads this FIRST for every task: find the "
        "department whose *Handles* matches the task, open that department's "
        "`departments/<dept>/ROSTER.md` to pick the specialist role, then spawn a "
        "sub-agent that reads the role folder in order and executes per its "
        "`how-to.md`. If no department matches, ask the owner - do not guess.",
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
        "(SOP-Writer, INSTRUCTIONS.md Moment 3.7) - never guess.",
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
    """Write PENDING-SOPS.md at the company root - the human/orchestrator-readable
    manifest of every role whose how-to.md is a PENDING stub (no library template
    matched), so the orchestrator knows exactly what still needs filling.

    Closes the 'silent empty stub' gap: a NO_TEMPLATE role is no longer a quiet
    placeholder - it is headed PENDING in its own how-to.md AND collected here.
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
                if "PENDING - FILL FROM LIBRARY" in head or "how-to.md (stub)" in head:
                    pending.append((dept_id, entry, how_to))

    lines = [
        "# PENDING-SOPS.md - Role how-to.md files awaiting library fill",
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
            f"**{len(pending)} role(s) have a PENDING how-to.md** - no role-library "
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
        company_name:     str - company display name.
        industry:         str - industry vertical (e.g., "personal-development").
        brand_colors:     dict - optional {primary, accent, text} hex values.
        full_config:      dict - the non-interactive config (or harvested
                                  interview answers) from which mission, owner
                                  values, and company KPIs are pulled.
        selected_departments: dict - departments dict (dept_id -> info) used
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
        print(f"[COMPANY-CONFIG] WARN: empty fields {missing} - persona scoring "
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
    as a board column - it does NOT overlap the worker departments (it is not
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
        # Guard: never double-emit a CEO/master-orchestrator worker column -
        # the CEO is already the prepended top column.
        if dept_id in ("ceo", "master-orchestrator", "dept-ceo"):
            continue
        # RC-3: emit explicit bare canonical slug so CC canonical-map + migration
        # 046 can key on slug without stripping the "dept-" prefix at runtime.
        # dept_id is always a bare canonical slug (marketing, sales, billing-finance,
        # etc.) - never a dept-X compound.  The "id" field keeps the dept- prefix
        # for legacy CC compatibility; "slug" is the authoritative bare form.
        # PRD 1.5: run dept_id through canonical_dept_slug so the slug field is
        # always the authoritative bare form (lowercase, hyphenated, no dept- prefix)
        # even if an older build wrote a non-canonical key into `departments`.
        canonical = _canonical_dept_slug(dept_id) or dept_id
        entries.append({
            "id": f"dept-{canonical}",
            "slug": canonical,
            "emoji": dept_info["emoji"],
            "name": dept_info["name"],
            "headTitle": dept_info["head"],
            "workspacePath": f"departments/{canonical}",
        })
    return entries


def copy_departments_to_command_center(departments_json):
    """
    Copy departments.json to the Command Center config directory.
    The build-workforce script writes to company-discovery/ but the CC
    reads from its own config/ directory. This function bridges the gap.
    """
    # Common CC install locations to try (in order of preference).
    # P2-6: the REAL install dir is ~/projects/command-center (Mac; see Skill 32
    # run-full-install.sh DASHBOARD_DIR) and /data/projects/command-center (VPS).
    # The legacy blackceo-command-center paths below never existed on real boxes,
    # so this copy always no-op'd. Put the real dirs FIRST; keep the legacy paths
    # after for any hand-placed checkout.
    cc_search_paths = [
        os.path.join(HOME, "projects", "command-center", "config"),         # real Mac install (DASHBOARD_DIR)
        os.path.join("/data", "projects", "command-center", "config"),      # real VPS install
        # legacy / hand-placed checkouts (kept after the real paths)
        os.path.join(HOME, "clawd", "projects", "blackceo-command-center", "config"),
        os.path.join(HOME, "projects", "blackceo-command-center", "config"),
        os.path.join(HOME, "clawd", "blackceo-command-center", "config"),
        os.path.join(HOME, "Downloads", "blackceo-command-center", "config"),
    ]

    # Also check for a symlink or env var pointing to CC. The explicit override
    # stays FIRST (highest precedence), ahead of the real + legacy paths above.
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
        # P2-6: not finding an on-disk CC config/ dir is NORMAL, not a warning. The
        # PRIMARY path that populates the Command Center board is Skill 32's DB seeding
        # (run-full-install.sh phases 6b/6c: seed-workspaces.py +
        # sync-departments-from-build-state.py), which reads the client's build-state
        # directly — NOT this optional file-copy mirror. Downgraded from WARNING so a
        # box seeding the board correctly via Skill 32 never emits a false alarm.
        print("[CC-SYNC] No on-disk Command Center config/ directory present — this is "
              "expected. The board is populated by Skill 32 DB seeding "
              "(seed-workspaces.py + sync-departments-from-build-state.py), not this "
              "file copy. departments.json remains available at the company-discovery "
              "path; set BLACKCEO_COMMAND_CENTER_ROOT to also mirror it into a CC checkout.",
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

    # Build department-to-persona mapping.
    # Valid domain keys (from persona-categories.json domainTags):
    #   marketing, sales, leadership, finance, operations, communication,
    #   copywriting, mindset, productivity-systems, coaching,
    #   strategy-innovation, personal-development
    # FIX 2 (2026-06-17): added 12 canonical departments that were missing,
    # causing all of them to fall back to the generic ["leadership"] pool.
    # FIX 3 (2026-06-17, repo-consistency gate): added the canonical FLOOR dept
    # ids (billing-finance/customer-support/web-development/app-development/
    # communications/openclaw-maintenance/social-media/paid-advertisement/crm/
    # quality-control/account-management) — selected_departments keys on these,
    # not the legacy short ids, so they were silently mapping to ['leadership'].
    # Kept in lockstep with create_governing_personas_md and enforced by
    # scripts/qc-assert-repo-consistency.py.
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
        # --- FIX 2 additions (2026-06-17) ---
        "presentations": ["copywriting", "marketing", "communication"],
        "bugs": ["productivity-systems", "strategy-innovation", "operations"],
        "healer": ["coaching", "personal-development", "mindset"],
        "personal-assistant": ["operations", "leadership", "productivity-systems"],
        "engineering": ["software-craft", "productivity-systems", "strategy-innovation", "operations"],
        "listings": ["marketing", "sales", "copywriting"],
        "logistics-fulfillment": ["operations", "productivity-systems"],
        "podcast": ["copywriting", "communication", "marketing"],
        "scheduling-dispatch": ["operations", "productivity-systems", "leadership"],
        "general-task": ["operations", "productivity-systems", "leadership"],
        "project-architecture-office": ["strategy-innovation", "leadership", "operations"],
        "project-management": ["leadership", "strategy-innovation", "productivity-systems"],
        # --- FIX 3 additions (2026-06-17): CANONICAL floor dept ids ---
        "billing-finance": ["finance", "operations"],
        "customer-support": ["communication", "coaching"],
        "web-development": ["strategy-innovation", "marketing", "productivity-systems"],
        "app-development": ["strategy-innovation", "productivity-systems"],
        "communications": ["communication", "leadership", "marketing"],
        "openclaw-maintenance": ["productivity-systems", "strategy-innovation", "operations"],
        "social-media": ["marketing", "communication", "copywriting"],
        "paid-advertisement": ["marketing", "copywriting", "strategy-innovation"],
        "crm": ["sales", "communication", "operations"],
        "quality-control": ["productivity-systems", "operations", "strategy-innovation"],
        "account-management": ["communication", "coaching", "strategy-innovation"],
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
    #
    # N31 FIX (v11.1.0): model MUST be an object {primary, fallbacks:[...]},
    # NEVER a bare string. Bare strings bypass all fallback chains - if Ollama
    # Cloud is over-capacity the agent dies silently. See AGENTS.md N31.
    #
    # MSF (v12.x): the dept-head model now comes from the capability-class layer.
    # resolve_dept_agent_model() (a) honors any Layer-0 explicit pin on a seed
    # entry, (b) infers the dept's DOMINANT capability class and resolves a
    # concrete model from the box's AVAILABLE models via resolve_role_model(),
    # and (c) falls straight through to the legacy _resolve_dept_default_model()
    # cascade when model_selector is unavailable / no class model resolves.
    # GENERATION roles never pull a dept HEAD off an LLM (the head is a router),
    # and the per-role GENERATION gate inside resolve_role_model keeps individual
    # generation roles off LLMs.
    _seed_entry = next(
        (a for a in agents_list if isinstance(a, dict) and a.get("id") == agent_id),
        None,
    )
    _primary, _dept_default = resolve_dept_agent_model(dept_id, existing_entry=_seed_entry)
    # FIX B (model-tiering / no self-grading FM-1/FM-2): quality-control must run
    # on a DIFFERENT model than the presentations producer. If the selector resolves
    # both to the same primary, override quality-control to the designated
    # independent heavy-vision model.
    if dept_id == "quality-control":
        try:
            _producer_primary = resolve_dept_agent_model("presentations")[0]
            if _primary == _producer_primary:
                _primary = "ollama/qwen3-vl:235b-cloud"
        except Exception:  # noqa: BLE001
            pass  # never break the build if the selector is unreachable
    # Record the dept default so the CC seeding step can write the
    # agent_settings (role_id IS NULL, setting_type='model') row (PLAN.md §3.2).
    _record_dept_default(dept_id, _dept_default, _primary)
    model = {
        "primary": _primary,
        "fallbacks": [
            "openrouter/moonshotai/kimi-k2.6",
            "ollama/deepseek-v4-pro:cloud",
            "openrouter/deepseek/deepseek-v4-pro",
        ],
    }
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

    # CEO / Master Orchestrator agent - pure router, NEVER executes production work.
    # Setting skills:[] blocks ALL installed OpenClaw skills for this agent so it
    # cannot invoke image_generate, tts, video_generate, file-write production
    # tools, coding-agent, or any other skill-backed production capability.
    # Other department agents (graphics, video, audio, etc.) inherit the
    # unrestricted default (no skills key → agents.defaults.skills or platform
    # default). See docs.openclaw.ai/tools/skills-config for the skills override
    # spec: agent-level skills REPLACES defaults, so [] = zero skills allowed.
    #
    # v11.3.1: Generation departments (graphics, video, audio) get an explicit
    # tools.allow so generation tools survive any parent-deny inheritance.
    # Verified tool names from a live client box (2026.6.1):
    #   image_generate, video_generate, music_generate (confirmed in tools.deny
    #   on main agent). tts, exec, read, write, edit, web_fetch, web_search
    #   confirmed in docs.openclaw.ai/gateway/security.
    # Fix #9 (presentation-dept hardening): presentations is a generation-class
    # dept too — its deterministic build_deck.py renderer, Fish-Audio render, PDF
    # export, and teleprompter build all need exec/read/write/edit/web_fetch/
    # web_search. Without the explicit allow, a parent deny on `main` shadowed
    # those tools and the dept agent stalled headless with "no permission." Grant
    # presentations the SAME protective set so a per-agent allow re-grants them.
    GENERATION_DEPT_IDS = {"graphics", "video", "audio", "presentations"}
    GENERATION_TOOLS_ALLOW = [
        "image_generate",
        "video_generate",
        "music_generate",
        "tts",
        "exec",
        "read",
        "write",
        "edit",
        "web_fetch",
        "web_search",
    ]

    # ── CEO / MASTER-ORCHESTRATOR TOOL-GATE (GOAL-5, Item 1) ──────────────────
    # The CEO is a pure ROUTER. skills:[] alone does NOT gate the OpenClaw
    # built-in tools (exec/write/edit/browser/image), which is how the CEO could
    # still self-execute production work. We deny EVERY production tool here,
    # using the REAL built-in tool names from docs.openclaw.ai/gateway/security
    # (read, write, edit, apply_patch, exec, process, browser, canvas, web_fetch,
    # web_search, image, cron, gateway, nodes, sessions_*), and deny ALL GHL MCP
    # tools by provider. We keep only the tools the CEO needs to ROUTE and
    # converse: read (workspace files), web_fetch/web_search (read-only lookups),
    # the messaging channels, and sessions_send/list/history (to coordinate, not
    # to spawn production workers).
    #
    # Tool-policy precedence is RESTRICT-ONLY (docs.openclaw.ai/tools/
    # multi-agent-sandbox-tools): a deny here cannot be un-denied in-session, so
    # the owner-consent carve-out is a PROFILE/ENTRY SWAP, not an in-session
    # allow (see grant-ceo-consent.sh + the runtime hook).
    #
    # `exec` is the crux: it is BOTH the production-execution tool AND (today)
    # the path the CEO uses to `curl POST /api/tasks/ingest`. Until the dedicated
    # `route_task` MCP tool ships fleet-wide we keep `exec` in ALLOW so routing
    # still works — but verify-routing.sh G7 emits a FAIL-WARN for that interim
    # state so a box is never falsely marked clean. When the route-task MCP tool
    # is present, move `exec` from CEO_TOOL_ALLOW into CEO_TOOL_DENY.
    CEO_TOOL_DENY = [
        "write",
        "edit",
        "apply_patch",
        "browser",
        "canvas",
        "image",
        "process",
        # Belt-and-suspenders MCP deny by name-glob, in case a gateway version
        # does not honor tools.byProvider. Denies always win and are restrict-only.
        "ghl-community-mcp__*",
        "ghl-mcp__*",
    ]
    CEO_TOOL_ALLOW = [
        "read",
        "web_fetch",
        "web_search",
        # Messaging: "message" is the channel-agnostic send tool seen in live
        # configs; the per-channel names are also valid (docs/gateway/security).
        "message",
        "telegram",
        "slack",
        "discord",
        "sessions_send",
        "sessions_list",
        "sessions_history",
        # mc-route__route_task = the SHIPPED signed routing tool (scripts/mc-route.sh);
        # the CEO routes by CALLING it (structured tool call, no shell) — that presence
        # is what clears verify-routing.sh G7. exec is RETAINED (per G1's decision in
        # hooks/lib-ceo-tool-gate.sh), NOT removed: it stays ONLY as the exec channel for
        # the two anchored helpers (route-presentation.sh + mc-route.sh); the intent-gate
        # default-denies every other exec. KEEP IN SYNC with hooks/lib-ceo-tool-gate.sh.
        "mc-route__route_task",
        "exec",
    ]
    # GHL MCP is registered under BOTH ids on live boxes: ghl-community-mcp AND
    # the legacy alias ghl-mcp. Deny ALL tools from both, by provider. The glob
    # entries in CEO_TOOL_DENY ("<server>__*") are a belt-and-suspenders fallback
    # for any version where byProvider is not honored — harmless if it is.
    CEO_MCP_DENY = {
        "ghl-community-mcp": {"deny": ["*"]},
        "ghl-mcp": {"deny": ["*"]},
    }

    is_ceo_agent = dept_id in ("ceo", "master-orchestrator", "dept-ceo")
    is_generation_dept = dept_id in GENERATION_DEPT_IDS
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
    if is_ceo_agent:
        # Enforce orchestrator-only posture: no production skills.
        # The CEO routes via messaging + task-ingest API calls only.
        agent_entry["skills"] = []
        # GOAL-5 Item 1: hard tool-gate so skills:[] is not the ONLY brake.
        # Deny every production tool by real built-in name + deny all GHL MCP
        # tools by provider; allow only routing/conversation tools.
        agent_entry["tools"] = {
            "deny": list(CEO_TOOL_DENY),
            "allow": list(CEO_TOOL_ALLOW),
            "byProvider": dict(CEO_MCP_DENY),
        }
        # v16.1.3 FIX — cross-agent routing tools (sessions.visibility +
        # agentToAgent) live on ROOT `tools`, NEVER on the per-agent tools block.
        # The per-agent AgentEntry.tools schema is additionalProperties:false and
        # REJECTS sessions/agentToAgent (allowed keys: allow/alsoAllow/byProvider/
        # codeMode/deny/elevated/exec/fs/loopDetection/message/profile/sandbox/
        # toolsBySender) — writing them per-agent fails `openclaw config validate`,
        # so the reload is skipped and the cron engine goes down on a
        # router-default box. Root `tools` DOES accept them:
        # tools.sessions.visibility=all so the routing agent sees ALL agent
        # sessions (gateway default "tree" — spawned-children only — silently
        # blocks cross-agent department handoffs); tools.agentToAgent so the
        # router can message peer agents directly. Idempotent: setdefault only
        # seeds missing keys, never clobbers a client customization.
        _root_tools = config.setdefault("tools", {})
        if not isinstance(_root_tools, dict):
            _root_tools = {}
            config["tools"] = _root_tools
        _root_sessions = _root_tools.setdefault("sessions", {})
        if not isinstance(_root_sessions, dict):
            _root_sessions = {}
            _root_tools["sessions"] = _root_sessions
        if _root_sessions.get("visibility") != "all":
            _root_sessions["visibility"] = "all"
        _root_a2a = _root_tools.setdefault("agentToAgent", {})
        if not isinstance(_root_a2a, dict):
            _root_a2a = {}
            _root_tools["agentToAgent"] = _root_a2a
        _root_a2a.setdefault("enabled", True)
        _root_a2a.setdefault("allow", ["*"])
    if is_generation_dept:
        # Explicit tools.allow so generation tools survive any parent-deny
        # inheritance. The dept agent runs under its own tool policy but a
        # parent deny on main (e.g. image_generate denied) would otherwise
        # shadow these tools when the dept agent is invoked as a sub-agent.
        agent_entry["tools"] = {"allow": GENERATION_TOOLS_ALLOW}

    # FIX A.3 (model-tiering): force a HIGH reasoning budget for the deck producer
    # AND its independent QC grader. thinkingDefault is the schema-valid per-agent
    # key (values off|minimal|low|medium|high|xhigh|adaptive|max). Heavy tier means
    # nothing if thinking is off.
    if dept_id in ("presentations", "quality-control"):
        agent_entry["thinkingDefault"] = "high"

    agents_list.append(agent_entry)
    config["agents"]["list"] = agents_list
    # Layer-1: persist the dept-default artifact for CC seeding (idempotent —
    # rewrites the full accumulated set each call; PLAN.md §3.2).
    try:
        flush_dept_defaults_artifact()
    except Exception:  # noqa: BLE001  (never fail the build on artifact write)
        pass
    return True


def _select_model_script_path():
    """Locate shared-utils/select_model.py across known install layouts."""
    candidates = [
        os.path.join(HOME, "Downloads", "openclaw-master-files", "shared-utils", "select_model.py"),
        str(Path.home() / "Downloads" / "openclaw-master-files" / "shared-utils" / "select_model.py"),
        os.path.join(HOME, ".openclaw", "skills", "shared-utils", "select_model.py"),
        # repo-local (CI / dev) — this script lives at 23-ai-workforce-blueprint/scripts/
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared-utils", "select_model.py"),
    ]
    for sel in candidates:
        if os.path.isfile(sel):
            return sel
    return None


def _resolve_dept_default_model(dept_id):
    """Layer-1 build-time dept default (PLAN.md §3.2).

    Calls select_model.py in --mode dept-default, which looks up the department's
    suitability (tier + baseline MODALITY) and resolves a concrete, modality-correct
    model from the client inventory via the authoritative cascade
    (Ollama Cloud -> OpenRouter open-source -> free). NEVER returns the free
    sentinel and NEVER returns a model-less result silently. Returns the full
    selector dict, or None if the selector is unreachable at install time.
    """
    import subprocess
    from canonical_slug import canonical_dept_slug as _cds  # type: ignore  # noqa
    try:
        canon = _cds(dept_id)
    except Exception:  # noqa: BLE001
        canon = dept_id
    sel = _select_model_script_path()
    if not sel:
        return None
    try:
        r = subprocess.run(
            ["python3", sel, "--mode", "dept-default",
             "--department", canon, "--format", "json"],
            capture_output=True, text=True, timeout=15,
        )
        if r.stdout.strip():
            data = json.loads(r.stdout)
            mid = (data.get("model_id") or "").lower()
            # Defense in depth: never accept a forbidden or free-default model.
            if mid and "anthropic/" not in mid and "claude-" not in mid and mid not in (
                "openrouter/free", "free"
            ):
                return data
    except Exception:  # noqa: BLE001
        pass
    return None


def _resolve_director_model(dept_id):
    """Dept-default model id for the director agent (modality-aware, Layer-1).

    Backwards-compatible shim: still returns a bare model-id string (so all
    existing callers keep working), but now resolves via the modality-aware
    suitability map (a graphics dept gets a vision model, a CEO gets heavy text)
    instead of always forcing --purpose-tier heavy.
    """
    data = _resolve_dept_default_model(dept_id)
    if data and data.get("model_id"):
        return data["model_id"]
    return None


# ── Layer-2: Per-role capability-class model resolution (MSF v1.0.0) ──────────
# The Capability-Class Model-Selection Framework adds a ROLE-LEVEL layer above
# the existing department-tier system. Each role's model is resolved by its
# capability class (HEAVY-REASONING / WRITING / JUDGMENT / MECHANICAL /
# CONVERSATIONAL / GENERATION) rather than inheriting the dept default blindly.
#
# Backward-compatible: if model_selector.py is unreachable, the caller falls
# through to the existing dept-default path — never crashes the build.

_MSF_SELECTOR_CACHE: dict = {}  # slug+dept -> capability info (avoids re-import per role)
_MSF_AVAILABLE: bool | None = None  # lazy init


def _ensure_msf_available() -> bool:
    """Import model_selector once; cache availability."""
    global _MSF_AVAILABLE
    if _MSF_AVAILABLE is not None:
        return _MSF_AVAILABLE
    try:
        # shared-utils is already on sys.path (inserted at script top)
        from model_selector import infer_class as _ic  # type: ignore  # noqa: F401
        _MSF_AVAILABLE = True
    except ImportError:
        _MSF_AVAILABLE = False
    return _MSF_AVAILABLE


def get_role_capability_class(role_slug: str, dept_id: str, role_type: str = "") -> dict:
    """
    Return capability-class info for a role slug + dept.

    Returns dict with at minimum:
      capability_class, vision_flag, purpose_tier, required_modality,
      generation_pipeline, inference_layer
    Returns {} if model_selector.py is unavailable (caller uses dept default).
    """
    cache_key = f"{role_slug}|{dept_id}"
    if cache_key in _MSF_SELECTOR_CACHE:
        return _MSF_SELECTOR_CACHE[cache_key]
    if not _ensure_msf_available():
        return {}
    try:
        from model_selector import infer_class  # type: ignore
        result = infer_class(role_slug, dept_id, role_type)
    except Exception as exc:  # noqa: BLE001
        print(f"[MSF WARN] infer_class failed for '{role_slug}' ({dept_id}): {exc}",
              file=sys.stderr)
        result = {}
    _MSF_SELECTOR_CACHE[cache_key] = result
    return result


def resolve_role_model(
    role_slug: str,
    dept_id: str,
    role_type: str = "",
    explicit_override: str | None = None,
    class_info: dict | None = None,
) -> dict:
    """
    Full per-role model resolution (Layer-2 of MSF). THE resolver — both the
    per-role and dept-head assignment paths route through this function.

    Resolution priority (highest wins):
      0. explicit_override (from openclaw.json agents.list[].model if already set)
      1. Capability-class resolution via model_selector.py
      2. Dept-default fallback (existing _resolve_dept_default_model)

    `class_info` lets a caller INJECT a pre-computed capability-class dict (e.g.
    the dept's DOMINANT class) instead of inferring from the slug — this is how
    the dept-head path makes the roster's true demand drive the model. When
    omitted, the class is inferred from the slug as before.

    Requirement (b) — GENERATION never gets an LLM and vice-versa — is enforced
    here: a GENERATION class returns ONLY the fixed pipeline (no LLM cascade),
    and a non-GENERATION class never returns a generation pipeline.

    Returns dict with model_id (str | None), capability_class, vision_flag,
    purpose_tier, needs_owner_input, prompt_to_owner, source.
    """
    # Layer 0 — explicit override wins without touching the cascade
    if explicit_override:
        return {
            "model_id": explicit_override,
            "capability_class": None,
            "vision_flag": False,
            "purpose_tier": None,
            "needs_owner_input": False,
            "prompt_to_owner": "",
            "source": "explicit_override",
        }

    cls_info = class_info if class_info else get_role_capability_class(role_slug, dept_id, role_type)

    # GENERATION class: fixed pipeline, no LLM
    if cls_info.get("capability_class") == "GENERATION":
        pipeline = cls_info.get("generation_pipeline") or "kie-ai/gpt-image-2-image-to-image"
        return {
            "model_id": pipeline,
            "capability_class": "GENERATION",
            "vision_flag": False,
            "purpose_tier": None,
            "needs_owner_input": False,
            "prompt_to_owner": "",
            "source": "msf_generation_pipeline",
        }

    # Layer 1 — call select_model.py via subprocess using the class-derived tier
    if cls_info.get("purpose_tier"):
        sel = _select_model_script_path()
        if sel:
            # select_model.py --mode task drives its chain off --difficulty
            # (hard/medium/simple), NOT --purpose-tier. Map the class tier to the
            # matching difficulty so a HEAVY class actually resolves the HEAVY
            # chain (deepseek-pro/kimi) instead of defaulting to medium/mid. This
            # is what makes the capability class genuinely DRIVE model strength.
            _tier_to_difficulty = {"heavy": "hard", "mid": "medium", "fast": "simple"}
            _difficulty = _tier_to_difficulty.get(cls_info["purpose_tier"], "medium")
            try:
                r = subprocess.run(
                    [
                        sys.executable, sel,
                        "--mode", "task",
                        "--purpose-tier", cls_info["purpose_tier"],
                        "--difficulty", _difficulty,
                        "--required-modality", cls_info.get("required_modality", "text"),
                        "--format", "json",
                    ],
                    capture_output=True, text=True, timeout=15,
                )
                if r.stdout.strip():
                    data = json.loads(r.stdout)
                    mid = (data.get("model_id") or "").lower()
                    if mid and "anthropic/" not in mid and "claude-" not in mid:
                        return {
                            "model_id": data["model_id"],
                            "capability_class": cls_info.get("capability_class"),
                            "vision_flag": cls_info.get("vision_flag", False),
                            "purpose_tier": cls_info.get("purpose_tier"),
                            "needs_owner_input": data.get("needs_owner_input", False),
                            "prompt_to_owner": data.get("prompt_to_owner", ""),
                            "source": "msf_class_cascade",
                        }
            except Exception as exc:  # noqa: BLE001
                print(f"[MSF WARN] select_model subprocess failed for role "
                      f"'{role_slug}': {exc}", file=sys.stderr)

    # Layer 2 — dept default fallback (existing path; always worked before MSF)
    dept_data = _resolve_dept_default_model(dept_id)
    if dept_data and dept_data.get("model_id"):
        return {
            "model_id": dept_data["model_id"],
            "capability_class": cls_info.get("capability_class"),
            "vision_flag": cls_info.get("vision_flag", False),
            "purpose_tier": dept_data.get("tier"),
            "needs_owner_input": dept_data.get("needs_owner_input", False),
            "prompt_to_owner": dept_data.get("prompt_to_owner", ""),
            "source": "msf_dept_fallback",
        }

    # Terminal fallback — safe known good
    return {
        "model_id": "ollama/kimi-k2.6:cloud",
        "capability_class": cls_info.get("capability_class"),
        "vision_flag": cls_info.get("vision_flag", False),
        "purpose_tier": cls_info.get("purpose_tier"),
        "needs_owner_input": False,
        "prompt_to_owner": "",
        "source": "msf_terminal_fallback",
    }


# ── MSF: dept-dominant capability class (drives the dept-head agent model) ────
# The dept-level agent (`dept-<id>`) is written ONCE per department and must be
# provisioned for the MOST-DEMANDING role it owns (it is the head/router that
# fields the hardest work and delegates the rest). So instead of the old static
# dept-tier lookup, we infer the capability class of EVERY role in the dept's
# roster and take the max by demand order, OR-ing the vision flag. That tier +
# modality then drives the SAME class-aware resolver (resolve_role_model) that
# per-role assignment uses — making the capability-class framework the real,
# live driver of the model written into openclaw.json.
#
# Demand order (highest first). GENERATION is intentionally NOT here: a dept
# whose roster is purely generation roles still needs an LLM-backed HEAD to
# route/QC, so generation roles never pull the dept head off an LLM. The
# per-role GENERATION gate (handled inside resolve_role_model / model_selector)
# is what keeps individual generation roles off an LLM.
_MSF_CLASS_DEMAND_ORDER = [
    "HEAVY-REASONING",
    "JUDGMENT",
    "WRITING",
    "CONVERSATIONAL",
    "MECHANICAL",
]


def _dept_dominant_class(dept_id: str) -> dict:
    """Infer the dept's dominant (most-demanding) capability class from its roster.

    Returns a dict shaped like infer_class() output:
      { capability_class, vision_flag, purpose_tier, required_modality, ... }
    or {} when model_selector is unavailable OR the roster is empty (caller then
    falls through to the legacy dept cascade — fully backward-compatible).
    """
    if not _ensure_msf_available():
        return {}
    try:
        roles = parse_suggested_roles(dept_id)
    except Exception:  # noqa: BLE001
        roles = []
    if not roles:
        return {}

    best_class = None
    best_rank = len(_MSF_CLASS_DEMAND_ORDER)  # higher index = lower demand
    any_vision = False
    best_info = {}
    for role in roles:
        try:
            name = (role.get("name") or "").lower()
        except AttributeError:
            continue
        slug = name.replace(" ", "-").replace("(", "").replace(")", "")
        slug = slug.replace("/", "-").replace("--", "-").strip("-")
        info = get_role_capability_class(slug, dept_id)
        cls = info.get("capability_class")
        if info.get("vision_flag"):
            any_vision = True
        if cls in _MSF_CLASS_DEMAND_ORDER:
            rank = _MSF_CLASS_DEMAND_ORDER.index(cls)
            if rank < best_rank:
                best_rank = rank
                best_class = cls
                best_info = info

    if best_class is None:
        return {}

    # Re-derive tier/modality for the winning class, OR-ing in any vision need
    # from across the roster (a graphics dept head should be vision-capable even
    # if its single most-demanding role happened to be text-only).
    purpose_tier = best_info.get("purpose_tier")
    required_modality = "vision" if any_vision else best_info.get("required_modality", "text")
    if required_modality == "vision" and not purpose_tier:
        purpose_tier = "heavy"  # safety: vision needs a real tier
    return {
        "capability_class": best_class,
        "vision_flag": any_vision,
        "purpose_tier": purpose_tier,
        "required_modality": required_modality,
        "generation_pipeline": None,
        "inference_layer": "dept_dominant",
    }


def resolve_dept_agent_model(dept_id, existing_entry=None):
    """Class-aware dept-head model resolution (MSF live driver).

    This is the REAL caller that wires the capability-class framework into the
    agent model written to openclaw.json. Resolution priority:

      0. Layer-0 explicit override — an existing `dept-<id>` entry that already
         carries an explicit model.primary string (a client/Layer-0 pin) wins
         outright and is never overwritten.
      1. Capability-class cascade — infer the dept's dominant class, then run
         resolve_role_model() with that tier/modality so the model comes from
         the class layer against the box's AVAILABLE models.
      2. Legacy dept-default cascade — if model_selector is unavailable, the
         roster is empty, or the class layer resolves nothing, fall straight
         through to _resolve_dept_default_model() (unchanged pre-MSF behavior).

    Returns (primary_model_id: str, selector_data: dict|None) where selector_data
    is the artifact-shaped dict for _record_dept_default (or None on override).
    """
    # Layer 0 — honor an explicit pin already on the entry (never clobber it).
    if isinstance(existing_entry, dict):
        existing_model = existing_entry.get("model")
        explicit = None
        if isinstance(existing_model, dict):
            explicit = existing_model.get("primary")
        elif isinstance(existing_model, str):
            explicit = existing_model
        if explicit:
            mid = explicit.strip().lower()
            # Refuse to honor a forbidden pin; fall through to resolution instead.
            if mid and "anthropic/" not in mid and "claude-" not in mid and mid not in (
                "openrouter/free", "free"
            ):
                return explicit, None

    # Layer 1 — capability-class cascade. The dept's DOMINANT capability class
    # (computed from its whole roster) supplies the purpose_tier + required
    # modality that drive resolution. We resolve via resolve_role_model() — the
    # SAME live resolver used for per-role assignment — and explicitly seed it
    # with the dominant class so it never re-classifies the dept head off the
    # roster's true demand (a dept HEAD is the most-demanding role it owns).
    dom = _dept_dominant_class(dept_id)
    if dom.get("purpose_tier"):
        try:
            resolved = _resolve_model_for_class(dom, dept_id)
            mid = (resolved or {}).get("model_id")
            if mid:
                low = mid.lower()
                if "anthropic/" not in low and "claude-" not in low and low not in (
                    "openrouter/free", "free"
                ):
                    selector_data = {
                        "model_id": mid,
                        "tier": dom.get("purpose_tier"),
                        "required_modality": dom.get("required_modality"),
                        "capability_class": dom.get("capability_class"),
                        "vision_flag": dom.get("vision_flag"),
                        "source": resolved.get("source"),
                    }
                    return mid, selector_data
        except Exception as exc:  # noqa: BLE001
            print(f"[MSF WARN] dept-head class resolution failed for "
                  f"'{dept_id}': {exc}", file=sys.stderr)

    # Layer 2 — legacy dept-default cascade (unchanged, never crashes a build).
    _dept_default = _resolve_dept_default_model(dept_id)
    _primary = (_dept_default or {}).get("model_id") or "ollama/kimi-k2.6:cloud"
    return _primary, _dept_default


def _resolve_model_for_class(cls_info: dict, dept_id: str) -> dict:
    """Resolve a concrete model from a capability-class info dict.

    Thin bridge that makes the dominant-class tier/modality the REAL driver of
    the resolved model: it injects the class dict into resolve_role_model() (THE
    resolver), so the dept-head path and the per-role path share one code path.
    resolve_role_model enforces requirement (b): GENERATION → fixed pipeline (no
    LLM); non-GENERATION → text/vision LLM via select_model.py's cascade.
    """
    return resolve_role_model(
        role_slug=f"{dept_id}-department-head",
        dept_id=dept_id,
        class_info=cls_info,
    )


# ── Layer-1 dept-default artifact (PLAN.md §3.2 / §6 reconciliation) ──
# build-workforce.py writes openclaw.json (agent model objects) at install time;
# it does NOT own the Command Center sqlite agent_settings table. So it emits a
# dept-default artifact that the CC seeding/closeout step consumes to write the
# agent_settings (role_id IS NULL, setting_type='model') dept-default rows. This
# is the bridge that makes "every department always has a real, modality-correct
# dept-default before any task dispatches" true on both sides.
_DEPT_DEFAULTS_ACCUM = {}


def _record_dept_default(dept_id, selector_data, resolved_primary):
    selector_data = selector_data or {}
    _DEPT_DEFAULTS_ACCUM[dept_id] = {
        "department": dept_id,
        "model_id": resolved_primary,
        "tier": selector_data.get("tier"),
        "required_modality": selector_data.get("required_modality"),
        "suitability_tier": selector_data.get("suitability_tier"),
        "needs_owner_input": bool(selector_data.get("needs_owner_input")),
        "setting_type": "model",
        "role_id": None,
        "source": "build-workforce-layer1",
    }


def flush_dept_defaults_artifact():
    """Write the accumulated dept defaults to a JSON artifact for CC seeding.

    Idempotent; safe to call multiple times. Returns the artifact path or None.
    """
    if not _DEPT_DEFAULTS_ACCUM:
        return None
    target_dir = DEPARTMENTS_DIR or os.path.join(
        MASTER_FILES if "MASTER_FILES" in globals() else os.path.join(HOME, "Downloads", "openclaw-master-files")
    )
    try:
        os.makedirs(target_dir, exist_ok=True)
    except OSError:
        return None
    artifact = os.path.join(target_dir, "dept-default-models.json")
    payload = {
        "_doc": "Layer-1 dept defaults emitted by build-workforce.py. The CC "
                "seeding/closeout step writes each as an agent_settings row "
                "(role_id IS NULL, setting_type='model'). PLAN.md §3.2.",
        "generated_by": "build-workforce.py",
        "defaults": list(_DEPT_DEFAULTS_ACCUM.values()),
    }
    try:
        with open(artifact, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"[LAYER-1] Wrote dept-default artifact: {artifact} "
              f"({len(_DEPT_DEFAULTS_ACCUM)} departments)", file=sys.stderr)
        return artifact
    except OSError as e:  # noqa: BLE001
        print(f"[LAYER-1 WARN] Could not write dept-default artifact: {e}", file=sys.stderr)
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
    - Check existing files before asking (v12.3.4: all 6 core files via context-ingest.py)
    - Confirm known info: "We already know X. Still correct?"
    - Offer research: "Not sure? I can research best practices for your industry."
    - Flush after every answered question
    - Update handoff file after every answer
    - Progress indicators at milestones
    - Use Perplexity sonar-pro-search for best practices research

    CONTEXT INGESTION (v12.3.4):
    Step 2.5 runs scripts/context-ingest.py BEFORE Phase 1 to assemble a
    KNOWN-CONTEXT map from all 6 core workspace files (USER, MEMORY, AGENTS,
    TOOLS, IDENTITY, SOUL), pre-interview-research.md, software-stack-capabilities.md,
    prior workforce-interview-answers.md, and provided-context-manifest.md.
    The map classifies each interview theme: known/partial/unknown → confirm/deepen/ask-fresh.
    KNOWN-CONTEXT is shown to the client and confirmed; it is NEVER silently recorded
    as a client answer. Only log_answer() after a live client confirmation turn may write
    to workforce-interview-answers.md (NO-FABRICATION invariant).
    """
    global MASTER_FILES, COMPANY_DISCOVERY_DIR

    # Step 1: Detect environment (guaranteed non-None after hardening)
    MASTER_FILES = find_master_files_folder()
    COMPANY_DISCOVERY_DIR = os.path.join(MASTER_FILES, "company-discovery")
    print(f"[PERSISTENCE] Master files folder: {MASTER_FILES}", file=sys.stderr)
    print(f"[PERSISTENCE] Interview answers will be saved to: {COMPANY_DISCOVERY_DIR}/", file=sys.stderr)

    # Step 2: Read existing context (now spans all 6 core .md files: USER, MEMORY,
    # AGENTS, TOOLS, IDENTITY, SOUL - see CONTEXT_FILES constant, expanded v12.3.4)
    existing_context = read_existing_context()
    previous_answers = read_previous_answers()
    handoff = read_handoff()

    # Step 2.5: Context Ingestion Pre-Pass (v12.3.4)
    # Run context-ingest.py to produce [slug]/interview-context-map.json and a
    # human digest. Load the map before Phase 1 and use it to:
    #   - KNOWN → confirm with client, never auto-record
    #   - PARTIAL → deepen (sharper follow-up using context as lead-in)
    #   - UNKNOWN → ask fresh
    # If the map is absent (new box, empty workspace), every theme is unknown and
    # the interview runs exactly as it does today - purely additive.
    # The AI agent should invoke: python3 scripts/context-ingest.py [--json] [--human]
    # and load the resulting interview-context-map.json into its working context.
    # See INSTRUCTIONS.md "Phase 0.5 - Context Ingestion" + "Context Ingestion +
    # Pull-Forward Rule (Binding)" for the full routing and KNOWN-CONTEXT vs
    # RECORDED-ANSWER definitions.

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
    #   - context-ingest.py (NEW v12.3.4) at Step 2.5 to classify themes known/partial/unknown
    #   - log_answer() after every question - THE ONLY writer to workforce-interview-answers.md
    #   - create_handoff() after every answer
    #   - create_department_workspace() for each department
    #   - determine_specialists() for specialist decisions
    #   - create_governing_personas_md() for persona wiring
    #   - generate_org_chart() at the end
    #   - generate_departments_json() for the Command Center
    #   - add_agent_to_config() for each department head
    #   - backup_config() before ANY config edits
    #   - save_openclaw_config() with validation after edits


def regenerate_org_chart_only():
    """§1.3: Re-render ORG-CHART.md from current .workforce-build-state.json.
    Called by converge (sync-extensions.sh --converge) after any add-*.sh run.
    Reads build-state, extracts dept/role data, regenerates ORG-CHART.md.
    Exits 0 on success, 1 on error."""
    import json as _json
    import os as _os
    from pathlib import Path as _Path

    state_path = _build_state_path()
    if not _os.path.isfile(state_path):
        print(f"[--regenerate-org-chart-only] FATAL: build-state not found at {state_path}", file=sys.stderr)
        sys.exit(1)

    try:
        state = _json.load(open(state_path))
    except (_json.JSONDecodeError, OSError) as e:
        print(f"[--regenerate-org-chart-only] FATAL: cannot read {state_path}: {e}", file=sys.stderr)
        sys.exit(1)

    # Build simple dept/specialist maps from build-state
    depts_raw = state.get("departments", {})
    if isinstance(depts_raw, list):
        depts_list = depts_raw
    else:
        depts_list = [
            {"slug": k, "name": v.get("name") or " ".join(w.capitalize() for w in k.split("-")),
             "emoji": v.get("emoji", ""), "rolesPlanned": v.get("rolesPlanned", 0)}
            for k, v in depts_raw.items()
        ]

    selected_departments = {
        d.get("slug", str(i)): {
            "name": d.get("name", d.get("slug", "")),
            "emoji": d.get("emoji", ""),
            "head": d.get("head", f"{d.get('name', d.get('slug', ''))} Lead"),
        }
        for i, d in enumerate(depts_list)
    }
    specialists_by_dept = {slug: [] for slug in selected_departments}

    org_chart = generate_org_chart(selected_departments, specialists_by_dept)

    # Determine COMPANY_DIR: same logic as build-workforce.py main path
    company_dir = state.get("companyDir") or COMPANY_DIR or WORKSPACE_ROOT
    if not company_dir or not _os.path.isdir(company_dir):
        # Fallback to workspace root
        ws_cands = ["/data/.openclaw/workspace", _os.path.join(HOME, ".openclaw", "workspace")]
        company_dir = next((c for c in ws_cands if _os.path.isdir(c)), WORKSPACE_ROOT)

    org_chart_path = _os.path.join(company_dir, "ORG-CHART.md")
    try:
        with open(org_chart_path, "w") as f:
            f.write(org_chart)
        print(f"[--regenerate-org-chart-only] ORG-CHART.md written to {org_chart_path}", file=sys.stderr)
    except OSError as e:
        print(f"[--regenerate-org-chart-only] FATAL: cannot write {org_chart_path}: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"org_chart_path={org_chart_path}")
    sys.exit(0)


if __name__ == "__main__":
    args = parse_args()
    if getattr(args, 'regenerate_org_chart_only', False):
        regenerate_org_chart_only()
    elif args.non_interactive:
        config = load_non_interactive_config(args.config_file)
        build_from_config(config)
    else:
        main()
