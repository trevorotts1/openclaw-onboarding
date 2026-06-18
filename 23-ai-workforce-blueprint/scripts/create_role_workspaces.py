#!/usr/bin/env python3
"""
Create / augment role-level workspaces inside a department.

v10.6.1 (Wave 5b) changes:
  - Renamed from create-role-workspaces.py (hyphens are not valid in Python
    import names — Wave 4's import was broken).
  - Added augment_role_folder() and augment_all_existing_role_folders() —
    these were referenced by post-build-role-workspaces.py since Wave 4 but
    never actually written.
  - Added library template-fill: when creating a role's how-to.md, check
    templates/role-library/_index.json for a matching pre-written doc. If
    one exists, read it from templates/role-library/[dept]/[slug].md, fill
    company-specific tokens, and use that instead of the stub. Falls back
    to the stub when no library match.

Per-role workspace layout:
    [DEPT]/[role-slug]/
    ├── IDENTITY.md         (unique, with Persona Governance Override clause)
    ├── SOUL.md             (unique, with Persona Governance Override clause)
    ├── MEMORY.md           (unique, starts empty)
    ├── HEARTBEAT.md        (unique)
    ├── how-to.md           (from library if available, else stub)
    ├── AGENTS.md → workspace_root/AGENTS.md   (symlink)
    ├── TOOLS.md  → workspace_root/TOOLS.md    (symlink)
    └── USER.md   → workspace_root/USER.md     (symlink)

For master-orchestrator, SOUL.md and IDENTITY.md use the CEO variant of the
deferral clause (mission/owner override persona on conflict).
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# v10.16.4: vendored lib/ ships with the installed skill folder; resolves
# detect_platform under /data/.openclaw/skills/23-ai-workforce-blueprint/. Repo-root
# shared-utils/ retained as fallback for in-repo invocation.
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared-utils"))
sys.path.insert(0, str(Path(__file__).parent.parent / "shared-utils"))
try:
    from detect_platform import get_openclaw_paths
except ImportError:
    def get_openclaw_paths():
        raise RuntimeError("detect_platform.py not on sys.path")


# ─── MSF: Capability-Class Model-Selection Framework (v1.0.0) ─────────────────
# Best-effort import from shared-utils/model_selector.py.
# Gracefully degrades if unavailable — never crashes the workspace builder.
try:
    from model_selector import infer_class as _msf_infer_class  # type: ignore
    _MSF_AVAILABLE = True
except ImportError:
    _MSF_AVAILABLE = False
    def _msf_infer_class(slug, dept, role_type=""):  # type: ignore
        return {}


def _crw_get_capability_class(role_slug: str, dept_slug: str, role_type: str = "") -> dict:
    """Return MSF capability-class info for a role slug + dept (or {} if unavailable)."""
    if not _MSF_AVAILABLE:
        return {}
    try:
        return _msf_infer_class(role_slug, dept_slug, role_type)
    except Exception:  # noqa: BLE001
        return {}


# ─── DEFERRAL CLAUSES ─────────────────────────────────────────────────────────

STANDARD_DEFERRAL = """
## Persona Governance Override

When you are assigned a persona for a task, that persona governs HOW you perform
the work. Your beliefs, voice, decision logic, quality bar, and judgment for that
task come from the persona — not from this file.

Act AS IF you ARE the persona for the duration of the task. Use their frameworks.
Use their phrasing. Hold their standards. Make the calls they would make.

This file is your fallback identity. It governs only when no persona is assigned.
When a persona is present, this file is subordinate to it.

**Order of operations:**
1. Check for an assigned persona. If present → act AS that persona.
2. If no persona is assigned → use this file.
3. In all cases: honor the company's mission (workspace SOUL.md) and the owner's
   stated values (workspace USER.md).
"""

CEO_DEFERRAL = """
## Persona Governance — CEO Mode

As the CEO / Master Orchestrator, you do NOT fully defer to assigned personas.
You use them as INPUT, but you remain accountable to the company's mission and
the owner's values at all times — those override the persona when there is conflict.

When a persona is assigned to a CEO-level task:
1. Read the persona's frameworks, voice, and decision logic. Consider them.
2. Compare to mission (workspace SOUL.md) and owner profile (workspace USER.md).
3. Where the persona ALIGNS → embody it for the task.
4. Where the persona CONFLICTS → mission and owner WIN. Log conflict in MEMORY.md.
5. Your own identity governs when no persona is assigned.

You are the protector of the mission. Personas are tools you use, not authorities
you serve.
"""

# Read-the-SOP operating protocol embedded in EVERY specialist's own first-read
# files (IDENTITY.md + SOUL.md). The wiring gap this closes: the read-first rule
# lived only in the shared AGENTS.md + the department ROSTER; a spawned sub-agent
# that did not load AGENTS.md had no read-the-SOP directive in its own files.
SPECIALIST_OPERATING_PROTOCOL = """
## Operating Protocol — Read the SOP Before You Work (binding)

Before executing ANY task you are spawned for, in this order:
1. Read this folder's `how-to.md` — it is the entry point to your SOPs.
2. Open the matching procedure: the Section-9 SOP in `how-to.md` OR the file in
   `SOP/` indexed by `SOP/00-INDEX.md` that covers this task. Read it FIRST.
3. Execute the SOP step by step. Do not improvise around it.
4. If NO SOP covers the task, do NOT guess — escalate to your department head so
   the SOP-Writer can author one (INSTRUCTIONS.md Moment 3.7).
"""

# CEO / Master Orchestrator variant: PRIME DIRECTIVE + route via task board.
# v11.3.2 loophole-close: the old text at step 2 said "OR spawn a sub-agent
# directly" — that IS the bypass violation (CEO self-dispatching a sub-agent
# to do production work = same as self-executing). The ONLY permitted routing
# action is POST to /api/tasks/ingest with department_slug. Replaced.
CEO_OPERATING_PROTOCOL = """
## CEO ROUTING — NO LOOPHOLES (binding, no exceptions)

### PRIME DIRECTIVE
I am the master orchestrator. My one job is to ROUTE. I do NOT execute, and I
do NOT spawn sub-agents to execute on my behalf — that is the same violation as
self-executing. The ONLY permitted routing action is:

  POST /api/tasks/ingest  with  department_slug: "<slug>"

This places the task on the department's Kanban board. The DEPARTMENT assigns
the specialist. The doing belongs to the department — never to me.

### NO LOOPHOLES
- There is NO "trivial task" or "simple task" exception that lets me self-execute.
- There is NO "quick API call" or "I know how to do this" exception.
- Telling a sub-agent I spawn to do the work IS THE SAME VIOLATION as doing it
  myself. A sub-agent I spawn is not a production tool — if a sub-agent is
  spawned it must read its own role files and operate via the task board.
- If I am unsure which department → route to `department_slug: "general-task"`.
  I NEVER hold a task or self-execute because I'm unsure.
- Before I would EVER do a task myself, I must FIRST seek AND RECEIVE explicit
  permission from the owner. Without that explicit consent, I route — always.

### What I MAY do
Telegram messaging, task-ingest POST, read workspace files, gateway restart.
Nothing else. No deliverables, no file writes, no API calls as production work.

### Informational "how do I use ..." questions (answer, do NOT route)
If the owner asks an INFORMATIONAL question about the workforce rather than for
work ("how do I use the X department?", "what can X do for me?", "how do I use
the <specialist>?", "who handles <thing>?"), I answer it directly by reading the
department's own guide `departments/<dept>/how-to-use-this-department.md` and
replying from it. This is reading a workspace file and replying, which is inside
what I MAY do. It is NOT production work, so it is NOT routed and needs no
permission. I never invent specialists or capabilities not in the guide. If a
message MIXES an info question with a work request, I answer the info part AND
route the work part. Full procedure: `../universal-sops/answering-how-to-use-questions.md`.

### Operating Steps
Before dispatching ANY task, in this order:
1. From my workspace read `../universal-sops/00-ROUTING.md` (or the department
   ROSTER.md) to identify the owning department and specialist role.
2. POST to `/api/tasks/ingest` with the correct `department_slug`. Done.
3. If the task board is unreachable → escalate via Telegram. Do NOT execute.
4. Review returned deliverables against the SOP the specialist followed.
"""


# ─── STUB GENERATORS (used as fallback when library has no match) ────────────

def stub_identity(role_name, dept_name, is_ceo):
    deferral = CEO_DEFERRAL if is_ceo else STANDARD_DEFERRAL
    protocol = CEO_OPERATING_PROTOCOL if is_ceo else SPECIALIST_OPERATING_PROTOCOL
    return f"""# {role_name} — IDENTITY

**Department:** {dept_name}
**Generated:** {_now_iso()}

## Role
{role_name} in the {dept_name} department. Detailed responsibilities live in `how-to.md`.

## Tools
See symlinked `TOOLS.md` (shared across company).

## Behavior Rules
See symlinked `AGENTS.md` (shared across company).
{protocol}{deferral}
"""


def stub_soul(role_name, dept_name, is_ceo):
    deferral = CEO_DEFERRAL if is_ceo else STANDARD_DEFERRAL
    protocol = CEO_OPERATING_PROTOCOL if is_ceo else SPECIALIST_OPERATING_PROTOCOL
    return f"""# {role_name} — SOUL

## Mission
Serve the {dept_name} department by executing this role's responsibilities at a
standard high enough to deserve the trust of the human owner.

## Voice
Mirror the owner's communication style (see workspace USER.md > Behavioral
Identity Profile). Plain, direct, no jargon unless the task domain requires it.

## Values
- Output quality beats output speed
- Honor the persona when assigned; honor the mission always
- Surface uncertainty rather than guess
- Document what you learn in MEMORY.md
{protocol}{deferral}
"""


def stub_memory(role_name):
    return f"""# {role_name} — MEMORY

(Empty — fills with use.)

## Long-term facts
- (Updated as the role accumulates work)

## Decisions
- (Logged at the time they're made)

## What I've learned about the owner / customers
- (Captured from feedback over time)
"""


def stub_heartbeat(role_name, dept_name):
    return f"""# {role_name} — HEARTBEAT

Cadence: every 30 minutes (default).
Owner: this role
Dept: {dept_name}

## Scheduled tasks
(Empty — populated by the role's daily/weekly routines in how-to.md.)

## On startup
1. Read `how-to.md` for full procedure
2. Read inherited `AGENTS.md`, `TOOLS.md`, `USER.md` (via symlinks)
3. Check for assigned persona (if any)
4. Read your latest entries in `MEMORY.md`
"""


def stub_how_to(role_name, dept_name, is_ceo):
    """Placeholder used when the library has no matching doc.

    Gap-3: NOT a silent empty stub. Headed PENDING with the EXACT one-shot
    token-fill instruction (fill FROM the nearest library template family, NOT a
    free-form essay). The 'how-to.md (stub)' marker is what PENDING-SOPS.md scans
    for so the orchestrator gets a manifest of everything still to fill.
    """
    deferral = CEO_DEFERRAL if is_ceo else STANDARD_DEFERRAL
    return f"""# {role_name} — how-to.md (stub)  [PENDING — FILL FROM LIBRARY]

**Department:** {dept_name}
**Status:** PENDING — no pre-written library doc matched this role.
**Generated:** {_now_iso()}

> ONE-SHOT FILL INSTRUCTION (do exactly this, do NOT write a free-form essay):
> 1. Find the nearest template family in
>    `23-ai-workforce-blueprint/templates/role-library/` for the
>    `{dept_name}` department (closest role title). If this department has no
>    library docs, use the closest department's family.
> 2. Copy that template and TOKEN-FILL only the placeholders (role =
>    `{role_name}`, department = `{dept_name}`, plus the company/industry tokens).
> 3. Keep the template's Section-9 SOP structure intact. Reserve free-form
>    generation with `templates/universal-how-to-template.md` ONLY if there is
>    genuinely no comparable library template.
> 4. Once filled, remove this PENDING header so this role drops off PENDING-SOPS.md.

## 1. Role Identity

### Who You Are
{role_name} in {dept_name}.

### What This Role Is NOT
(Pending fill — see the one-shot instruction above.)

## 2. Persona Governance Override
{deferral}

## 3-19. Pending fill — read the one-shot instruction at the top of this file.
"""


# ─── LIBRARY TEMPLATE-FILL (Wave 5b) ──────────────────────────────────────────

def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _resolve_skill_dir():
    """Return absolute path to 23-ai-workforce-blueprint inside the install.

    SOP-pull RC-3 (Fix 9): ROLE_LIBRARY_PATH env var lets an operator point the
    role-library importer at a custom ZHC departments tree OR a non-default skill
    install dir when the default path yields an empty templates/role-library/.
    Resolution order:
        1. $ROLE_LIBRARY_PATH — operator/env override (must contain
           templates/role-library/_index.json; warning printed if not)
        2. $OPENCLAW_WORKSPACE_PATH / skills / 23-ai-workforce-blueprint — legacy
           workspace-root override
        3. Standard detect_platform paths["skills"] / "23-ai-workforce-blueprint"
        4. Fallback: __file__ parent.parent (in-repo / dev execution)

    On live VPS the canonical ZHC departments tree lives at
    /data/clawd/zero-human-company/<slug>/departments; operators who keep their
    role templates there should set ROLE_LIBRARY_PATH to that departments tree and
    maintain a templates/role-library/_index.json inside it.
    """
    import os
    rl_path_env = os.environ.get("ROLE_LIBRARY_PATH", "").strip()
    if rl_path_env:
        p = Path(rl_path_env)
        # Validate it contains the index so a misconfigured var gets a clear warning
        index_candidate = p / "templates" / "role-library" / "_index.json"
        if not index_candidate.exists():
            print(
                f"  [ROLE_LIBRARY_PATH] WARN: $ROLE_LIBRARY_PATH={rl_path_env} "
                f"but templates/role-library/_index.json not found there. "
                f"Falling back to install-dir skill templates.",
                file=sys.stderr,
            )
        else:
            return p

    ws_path_env = os.environ.get("OPENCLAW_WORKSPACE_PATH", "").strip()
    if ws_path_env:
        candidate = Path(ws_path_env) / "skills" / "23-ai-workforce-blueprint"
        if (candidate / "templates" / "role-library" / "_index.json").exists():
            return candidate

    try:
        paths = get_openclaw_paths()
        return paths["skills"] / "23-ai-workforce-blueprint"
    except Exception:
        # Fallback: assume this file is at skills/23-ai-workforce-blueprint/scripts/
        return Path(__file__).resolve().parent.parent


# ─── ROLE-NAME NORMALIZER (WS-2: 58% naive match → ~100% normalized) ──────────
#
# WS-1 archaeology proved that naive `slugify(role_name)` exact-matches only
# 124/214 (58%) of suggested-roles against the role-library slugs, because the
# two name-spaces drifted: the library slugs encode `&`→drop-or-`and`, `/`→space,
# em-dash variants, and the suggested-roles names carry decorations
# (`**`, `⭐`, `FLAGSHIP ROLE`) plus employment-type qualifiers
# (`(full-time-permanent or on-call)`). A single deterministic normalizer that
# generates MULTIPLE candidate keys per name and matches against keys derived
# from BOTH the library `title` and `slug` reaches 215/215 (100%) on both repos
# with zero collisions. This is the function that makes the build INSTANTIATE
# the 991 pre-written SOPs instead of LLM-regenerating them from empty stubs.

# Department-name aliases: suggested-roles dept id / workspace dept folder name
# → role-library `dept` value in _index.json. Identity for the 16 canonical
# depts; aliases cover historical/workspace-folder spellings.
_LIBRARY_DEPT_ALIASES = {
    "legal": "legal-compliance",
    "legal-compliance": "legal-compliance",
    "billing-finance": "billing",
    "billing": "billing",
    "video-production": "video",
    "video": "video",
    "audio-production": "audio",
    "audio": "audio",
}

# Employment / availability qualifier tokens — describe schedule, not the role.
# Dropped wherever they appear so `Reddit Specialist (full-time-permanent or
# on-call)` normalizes to the same key as the library's `reddit-specialist`.
_EMPLOYMENT_TOKENS = {
    "full", "time", "permanent", "part", "on", "call", "temporary",
    "contract", "seasonal", "unless", "audience", "justifies", "depending",
    "or",
}


def normalize_dept(dept_slug):
    """Map a workspace/suggested-roles dept id to the role-library dept value."""
    key = str(dept_slug or "").replace("-dept", "").replace("dept-", "").strip().lower()
    return _LIBRARY_DEPT_ALIASES.get(key, key)


def _strip_role_decorations(s):
    s = s.replace("**", "").replace("⭐", "").replace("★", "").replace("🌟", "")
    s = re.sub(r"(?i)\bflagship\s+role\b", " ", s)
    s = re.sub(r"(?i)\bflagship\b", " ", s)
    return s


def _clean_role_key(s, amp):
    """amp in {'and','drop'} — the library is internally inconsistent about `&`,
    so we generate both and match if either hits."""
    s = s.replace("—", "-").replace("–", "-")
    s = s.replace("&", " and ") if amp == "and" else s.replace("&", " ")
    s = s.replace("/", " ").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    toks = [t for t in s.split() if t not in _EMPLOYMENT_TOKENS]
    return " ".join(toks)


def normalize_role_variants(name):
    """
    Return the set of candidate normalized keys for a role name. Generated for
    BOTH suggested-role names AND library titles/slugs so they meet in the
    middle. Two parenthetical strategies (drop-from-`(` vs keep-paren-words) ×
    two `&` strategies (`and` vs drop) = up to 4 keys.
    """
    out = set()
    base = _strip_role_decorations(str(name or "")).strip()
    a = base.split("(", 1)[0] if "(" in base else base        # drop from first '('
    b = base.replace("(", " ").replace(")", " ")              # keep paren words
    for raw in (a, b):
        for amp in ("and", "drop"):
            v = _clean_role_key(raw, amp)
            if v:
                out.add(v)
    return out


# Cache: skill_dir -> {dept: {normalized_key: role_entry}}
_LIBRARY_INDEX_CACHE = {}


def _build_library_index(skill_dir):
    """Read _index.json and build {dept: {normalized_key: role_entry}}."""
    skill_dir = Path(skill_dir)
    cache_key = str(skill_dir)
    if cache_key in _LIBRARY_INDEX_CACHE:
        return _LIBRARY_INDEX_CACHE[cache_key]

    index_path = skill_dir / "templates" / "role-library" / "_index.json"
    by_dept = {}
    if not index_path.exists():
        _LIBRARY_INDEX_CACHE[cache_key] = by_dept
        return by_dept
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [WS-2] WARN: could not parse _index.json: {e}", file=sys.stderr)
        _LIBRARY_INDEX_CACHE[cache_key] = by_dept
        return by_dept

    for role_entry in index.get("roles", []):
        dept = role_entry.get("dept", "").lower()
        if not dept:
            continue
        title = role_entry.get("title", "")
        slug = role_entry.get("slug", "")
        keys = set()
        # title may be a token placeholder ({{ROLE_TITLE}}) — fall back to slug
        if title and "{{" not in title:
            keys |= normalize_role_variants(title)
        keys |= normalize_role_variants(slug.replace("-", " "))
        d = by_dept.setdefault(dept, {})
        for k in keys:
            d.setdefault(k, role_entry)  # first writer wins (stable, no clobber)

    _LIBRARY_INDEX_CACHE[cache_key] = by_dept
    return by_dept


def library_lookup(role_slug, dept_slug):
    """
    Return (library_doc_path, role_entry_dict) or (None, None) if no match.

    WS-2: matches via the normalizer (variant keys) against keys derived from
    BOTH the library title and slug, so the 42% of roles that the old naive
    exact-slug match dropped now resolve. `role_slug` may be a raw role NAME or
    a slug — both normalize to the same candidate keys.
    """
    skill_dir = _resolve_skill_dir()
    by_dept = _build_library_index(skill_dir)
    dept_key = normalize_dept(dept_slug)
    dept_map = by_dept.get(dept_key, {})
    if not dept_map:
        return None, None

    role_entry = None
    for cand in normalize_role_variants(str(role_slug).replace("-", " ")):
        if cand in dept_map:
            role_entry = dept_map[cand]
            break
    if role_entry is None:
        return None, None

    doc_rel = role_entry.get("path", "")
    doc_abs = skill_dir / doc_rel
    if doc_abs.exists():
        return doc_abs, role_entry
    # Fallback: built from convention
    fallback = (skill_dir / "templates" / "role-library"
                / role_entry["dept"] / f"{role_entry['slug']}.md")
    if fallback.exists():
        return fallback, role_entry
    return None, role_entry


def _load_company_config():
    """Read company-config.json from the workspace, or {} if missing."""
    try:
        paths = get_openclaw_paths()
        cfg_path = paths.get("company_config")
        if cfg_path and Path(cfg_path).exists():
            return json.loads(Path(cfg_path).read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _load_user_md_excerpt():
    """Pull a short owner-profile excerpt from workspace USER.md for tokens."""
    try:
        paths = get_openclaw_paths()
        user_md = paths.get("user_md")
        if user_md and Path(user_md).exists():
            text = Path(user_md).read_text(encoding="utf-8")
            return text[:2000]
    except Exception:
        pass
    return ""


def _compute_revenue_cascade(yearly):
    """Return monthly/weekly/daily/quarterly given yearly. Empty dict if no yearly."""
    try:
        y = float(str(yearly).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return {}
    return {
        "YEARLY_GOAL": f"${y:,.0f}",
        "QUARTERLY_TARGET": f"${y/4:,.0f}",
        "MONTHLY_TARGET": f"${y/12:,.0f}",
        "WEEKLY_TARGET": f"${y/52:,.0f}",
        "DAILY_TARGET": f"${y/250:,.0f}",  # 250 working days
    }


def fill_tokens(content, role_name, dept_name, is_ceo, role_entry=None):
    """
    Replace {{TOKEN}} placeholders in `content` with values derived from the
    company config + USER.md + role metadata.

    v12.17.2 FIX (token-map): extended from ~8 tokens to cover every distinct
    {{TOKEN}} found across all 439 role-library files.  Two categories:
      - Config/interview-sourced: pull from company-config.json when available.
      - Neutral literal defaults: sensible static strings for all domain-specific
        tokens (platform names, KPI thresholds, titles) so that ZERO {{...}}
        patterns survive a build.  This eliminates the TOKEN_LEAK_RE trigger in
        qc-completeness.sh's embedded_sop_count gate, which was causing 371+
        roles to score 0 on the SOP-floor metric even though their how-to.md
        files contained fully-authored Section-9 SOP blocks.
    """
    cfg = _load_company_config()
    _now = datetime.now(timezone.utc)
    _iso_date = _now.strftime("%Y-%m-%d")
    _iso_year = _now.strftime("%Y")

    # Pull token values from config — accept multiple key variants
    company_name = (cfg.get("companyName") or cfg.get("company_name")
                    or cfg.get("name") or "")
    company_slug = (cfg.get("slug") or cfg.get("companySlug")
                    or cfg.get("company_slug") or "")
    company_industry = (cfg.get("companyIndustry") or cfg.get("industry")
                        or cfg.get("industryVertical") or "")
    company_mission = (cfg.get("mission") or cfg.get("companyMission")
                       or cfg.get("mission_one_line") or "")
    company_tz = (cfg.get("timezone") or cfg.get("companyTimezone") or "America/Chicago")
    primary_color = ""
    if isinstance(cfg.get("brand"), dict):
        primary_color = cfg["brand"].get("primary", "")
    primary_color = primary_color or "#1f2937"

    # Owner fields — try USER.md first, fall back to config
    owner_name = (cfg.get("ownerName") or cfg.get("owner_name")
                  or cfg.get("ownerFirstName") or "")
    owner_voice = (cfg.get("ownerVoiceSample") or cfg.get("owner_voice_sample") or "")
    owner_comms = (cfg.get("ownerCommunicationStyle") or cfg.get("owner_communication_style")
                   or "direct, no jargon")

    # Detect CRM from connected_systems list (GoHighLevel is the default fleet CRM)
    _connected = cfg.get("connectedSystems") or cfg.get("connected_systems") or []
    _crm = "GoHighLevel"
    if "hubspot" in str(_connected).lower():
        _crm = "HubSpot"
    elif "salesforce" in str(_connected).lower():
        _crm = "Salesforce"

    yearly = (cfg.get("yearlyRevenueGoal") or cfg.get("yearly_revenue_goal")
              or cfg.get("revenueGoal") or cfg.get("yearlyGoal") or "")

    cascade = _compute_revenue_cascade(yearly)

    # Director / head-of title helpers
    director = "Master Orchestrator" if is_ceo else f"Director of {dept_name}"
    _dept_norm = dept_name.strip()

    def _head_of(area):
        return f"Head of {area}"

    # Role slug derived from role_name
    _role_slug = re.sub(r"[^a-z0-9]+", "-", role_name.lower()).strip("-")

    # ── PRIMARY tokens (config + derived) ──────────────────────────────────────
    tokens = {
        # Core identity
        "COMPANY_NAME": company_name,
        "company_name": company_name,
        "CompanyName": company_name,
        "COMPANY_INDUSTRY": company_industry,
        "INDUSTRY_VERTICAL": company_industry,
        "INDUSTRY": company_industry,
        "industry": company_industry,
        "COMPANY_SLUG": company_slug,
        "COMPANY_MISSION_ONE_LINE": company_mission,
        "COMPANY_TIMEZONE": company_tz,
        "PRIMARY_COLOR": primary_color,
        "BUSINESS_NAME": company_name,
        # Role / dept
        "ROLE_TITLE": role_name,
        "role_slug": _role_slug,
        "DEPARTMENT_NAME": dept_name,
        "DEPT_DIR": _dept_norm.lower().replace(" ", "-"),
        # Director titles
        "DIRECTOR_OR_MASTER_ORCHESTRATOR": director,
        "DIRECTOR_TITLE": director,
        "SALES_DIRECTOR_TITLE": _head_of("Sales"),
        "CHIEF_FINANCIAL_OFFICER_TITLE": "Chief Financial Officer",
        "CHIEF_MARKETING_OFFICER_TITLE": "Chief Marketing Officer",
        "CHIEF_LEGAL_OFFICER_TITLE": "Chief Legal Officer",
        "CHIEF_REVENUE_OFFICER_TITLE": "Chief Revenue Officer",
        "CTO_TITLE": "Chief Technology Officer",
        "DEPT_HEAD_PERSONA_OR_ROLE": director,
        # Head-of titles (per _token-reference.md)
        "HEAD_OF_AUDIO_PRODUCTION_TITLE": _head_of("Audio Production"),
        "HEAD_OF_CONTENT_TITLE": _head_of("Content"),
        "HEAD_OF_CUSTOMER_SUCCESS_TITLE": _head_of("Customer Success"),
        "HEAD_OF_EDUCATION_TITLE": _head_of("Education"),
        "HEAD_OF_MARKETING_TITLE": _head_of("Marketing"),
        "HEAD_OF_PRODUCT_TITLE": _head_of("Product"),
        "HEAD_OF_SALES_TITLE": _head_of("Sales"),
        "HEAD_OF_SECURITY_TITLE": _head_of("Security"),
        "HEAD_OF_VIDEO_PRODUCTION_TITLE": _head_of("Video Production"),
        "HEAD_OF_VIDEO_TITLE": _head_of("Video"),
        "HEAD_OF_WEB_DEVELOPMENT_TITLE": _head_of("Web Development"),
        # Owner
        "OWNER_NAME": owner_name,
        "OWNER_FIRST_NAME": owner_name,
        "FIRST_NAME": owner_name,
        "FirstName": owner_name,
        "OWNER_VOICE_SAMPLE": owner_voice,
        "OWNER_COMMUNICATION_STYLE": owner_comms,
        # Dates
        "ISO_DATE": _iso_date,
        "GENERATION_DATE": _iso_date,
        "ISO_DATE_YEAR": _iso_year,
        "YEAR": _iso_year,
        "Year": _iso_year,
        "DATE": _iso_date,
        # Persona (filled at task dispatch; placeholder keeps doc readable)
        "ASSIGNED_PERSONA": "(selected per task by persona-selector)",
        "ASSIGNED_PERSONA_VERSION": "1",
        "CURRENTLY_ASSIGNED_PERSONA": "(selected per task by persona-selector)",
        # CRM
        "CRM_PLATFORM_NAME": _crm,
        "CRM_TOOL": _crm,
        # Revenue cascade (from _compute_revenue_cascade)
        **cascade,
    }

    # ── NEUTRAL DEFAULTS for all domain-specific tokens ─────────────────────────
    # These cover every remaining {{TOKEN}} in the 439 role-library files.
    # Values are sensible operational defaults; overridden by post-build config
    # sync when the company provides real values.
    _defaults = {
        # Platform / tool names
        "AD_PLATFORM_NAME": "Google Ads",
        "SOCIAL_PLATFORM_NAME": "Instagram",
        "EMAIL_PLATFORM": "GoHighLevel",
        "EMAIL_PLATFORM_NAME": "GoHighLevel",
        "EMAIL_TOOL": "GoHighLevel",
        "SENDING_DOMAIN": "mail." + (company_slug or "company") + ".com",
        "PRIMARY_MAILBOX_PROVIDERS": "Gmail, Outlook, Yahoo",
        "YEARLY_EMAIL_VOLUME": "120,000 emails/year",
        "PROJECT_MANAGEMENT_TOOL": "Notion",
        "TASK_TOOL": "Notion",
        "TASK_TOOL_NAME": "Notion",
        "TASK_PLATFORM": "Notion",
        "PM_TOOL": "Notion",
        "CALENDAR_TOOL": "Google Calendar",
        "SCHEDULING_TOOL": "Calendly",
        "SCHEDULING_TOOL_NAME": "Calendly",
        "VIDEO_CONFERENCING_TOOL": "Google Meet",
        "VIDEO_CONF_TOOL": "Google Meet",
        "COMMUNICATION_PLATFORM": "Slack",
        "COMMUNICATION_CHANNEL": "Slack",
        "MESSAGING_PLATFORM": "Slack",
        "TEAM_COMMS_CHANNEL": "Slack",
        "DOCS_TOOL": "Notion",
        "DOCS_PLATFORM": "Notion",
        "DOC_PLATFORM": "Notion",
        "DOC_LIBRARY_PLATFORM": "Notion",
        "DAM_PLATFORM": "Google Drive",
        "ASSET_MANAGEMENT": "Google Drive",
        "RESEARCH_KNOWLEDGE_BASE": "Notion",
        "RESEARCH_INTAKE_SYSTEM": "Notion",
        "SOURCE_CONTROL_PLATFORM": "GitHub",
        "CI_CD_TOOL": "GitHub Actions",
        "CI_PLATFORM_NAME": "GitHub Actions",
        "CODE_SANDBOX_ENV": "GitHub Codespaces",
        "CONTAINER_ORCHESTRATION": "Docker Compose",
        "CONTAINER_REGISTRY": "GitHub Container Registry",
        "MONITORING_TOOL_NAME": "Grafana",
        "APM_TOOL": "Grafana",
        "ERROR_TRACKER": "Sentry",
        "INCIDENT_MANAGEMENT_TOOL": "PagerDuty",
        "INCIDENT_TOOL": "PagerDuty",
        "SECRETS_MANAGEMENT_TOOL": "1Password",
        "SECURITY_SCANNING_TOOL": "Snyk",
        "SECURITY_TOOL": "Snyk",
        "SECURITY_PLUGIN": "Wordfence",
        "TEST_FRAMEWORK": "pytest",
        "E2E_TEST_FRAMEWORK": "Playwright",
        "PERFORMANCE_TEST_TOOL": "k6",
        "TEST_MANAGEMENT_TOOL": "Notion",
        "CONVERSATION_INTEL_TOOL": "Gong",
        "SALES_ENGAGEMENT_TOOL": "GoHighLevel",
        "SALES_INTELLIGENCE_TOOL": "Apollo",
        "INTERACTIVE_DEMO_TOOL": "Loom",
        "PROPOSAL_TOOL": "PandaDoc",
        "FORECASTING_TOOL": "Notion",
        "LEDGER_PLATFORM": "QuickBooks Online",
        "BILLING_SYSTEM": "Stripe",
        "PAYMENT_GATEWAY": "Stripe",
        "PAYMENT_GATEWAY_DASHBOARD": "Stripe Dashboard",
        "TAX_TOOL": "QuickBooks Online",
        "COMPENSATION_TOOL": "Gusto",
        "SURVEY_TOOL": "Typeform",
        "LMS_PLATFORM": "Skool",
        "MEMBERSHIP_PLATFORM": "Skool",
        "MEMBER_PORTAL_PLATFORM": "Skool",
        "COMMUNITY_PLATFORM": "Skool",
        "PODCAST_HOST_PLATFORM": "Buzzsprout",
        "VSL_HOSTING_PLATFORM": "Wistia",
        "VIDEO_REVIEW_PLATFORM": "Frame.io",
        "THUMBNAIL_TESTING_TOOL": "TubeBuddy",
        "THUMBNAIL_TOOL": "Canva",
        "SCREEN_RECORDER": "Loom",
        "VIDEO_EDITING_SOFTWARE": "CapCut",
        "AUDIO_TOOL": "Audacity",
        "MOTION_GRAPHICS_TOOL": "After Effects",
        "COLOR_GRADING_TOOL": "DaVinci Resolve",
        "AI_CLIP_TOOL": "OpusClip",
        "SCRIPT_ANALYSIS_TOOL": "Claude",
        "ANALYTICS_PLATFORM": "Google Analytics 4",
        "PRODUCT_ANALYTICS_TOOL": "PostHog",
        "REPORT_DELIVERY_CHANNEL": "Slack",
        "REPORTING_TOOL_NAME": "Looker Studio",
        "TECH_RADAR_TOOL": "ThoughtWorks Tech Radar",
        "QC_CHECKLIST_TOOL": "Notion",
        "COMPETITOR_INTELLIGENCE_SOURCE": "SparkToro",
        "CMS_PLATFORM": "WordPress",
        "HOSTING_PROVIDER": "Vercel",
        "CDN_PROVIDER": "Cloudflare",
        "STAGING_ENV": "staging." + (company_slug or "company") + ".com",
        "BACKUP_TOOL": "Backblaze B2",
        "TRAVEL_BOOKING_TOOL": "Google Flights / Airbnb",
        "HANDOFF_FORM_LINK": "https://forms.gle/placeholder",
        "LANDING_PAGE_BUILDER": "Framer",
        "TESTIMONIAL_TOOL_NAME": "Testimonial.to",
        "REVIEW_PLATFORM_NAME": "Google Reviews",
        "REPO_MARKETING_SITE": "github.com/" + (company_slug or "company") + "/marketing-site",
        "REPO_CUSTOMER_DASHBOARD": "github.com/" + (company_slug or "company") + "/customer-dashboard",
        "REPO_ADMIN_PANEL": "github.com/" + (company_slug or "company") + "/admin",
        "FULFILLMENT_TRACKER_PLATFORM": "ShipStation",
        "VENDOR_PORTAL": "vendor-portal." + (company_slug or "company") + ".com",
        # GHL specifics
        "GHL_LOCATION_ID": "(set in openclaw.json → ghl.locationId)",
        "GHL_TOKEN": "(set in openclaw.json → ghl.apiKey)",
        # KPI / metric defaults (realistic operational numbers)
        "ROLE_REV_PERCENT": "5",
        "BLENDED_ROAS_TARGET": "3.0",
        "MER_TARGET": "3.0",
        "TARGET_CPA": "$50",
        "TARGET_CPC": "$2.00",
        "TARGET_CPE": "$0.10",
        "AD_SPEND_CAP": "$5,000/month",
        "SEARCH_TERM_SPEND_THRESHOLD": "$50",
        "LOW_QS_SPEND_THRESHOLD": "$20",
        "BUDGET_CHANGE_APPROVAL_THRESHOLD": "$500",
        "OWNER_APPROVAL_THRESHOLD": "$1,000",
        "OWNER_APPROVAL_COST_THRESHOLD": "$1,000",
        "DISCOUNT_THRESHOLD": "20%",
        "MAX_DISCOUNT_PERCENT": "20",
        "CREDIT_THRESHOLD": "$200",
        "OWNER_RENEWAL_THRESHOLD": "$5,000",
        "APPROVAL_THRESHOLD": "$500",
        "TECH_APPROVAL_THRESHOLD": "$500",
        "ESCALATION_THRESHOLD": "$2,000",
        "ESCALATION_ARR_THRESHOLD": "$10,000",
        "ESCALATION_DISPUTE_THRESHOLD": "$500",
        "ESCALATION_RESOLVE_HOURS": "24",
        "ESCALATION_RESOLVE_HOURS_DEFAULT": "24",
        "AT_RISK_THRESHOLD": "60",
        "CRITICAL_THRESHOLD": "90",
        "SYSTEMIC_RISK_THRESHOLD": "3",
        "THRESHOLD": "80%",
        "DA_THRESHOLD": "40",
        "TIER_1_ARR_THRESHOLD": "$5,000",
        "HIGH_VALUE_ORDER_THRESHOLD": "$500",
        "HIGH_VALUE_NOTIFICATION_THRESHOLD": "$1,000",
        "HIGH_REVENUE_SKU_THRESHOLD": "$200",
        "PO_DIRECTOR_REVIEW_THRESHOLD": "$2,500",
        "EMERGENCY_PO_THRESHOLD": "$1,000",
        "WRITE_OFF_QC_THRESHOLD": "$100",
        "DEAD_STOCK_WRITEOFF_THRESHOLD": "180",
        "BUNDLE_SIZE_THRESHOLD": "10",
        "RECOVERY_GESTURE_MAX": "$50",
        "SD_SPOT_BUDGET": "$500",
        # Operational metrics
        "SHOW_RATE_TARGET": "85%",
        "SHOW_UP_RATE_TARGET": "85%",
        "NO_SHOW_RATE_TARGET": "15%",
        "NO_SHOW_RECOVERY_TARGET": "50%",
        "CONFIRMATION_RATE_TARGET": "90%",
        "CANCELLATION_RECOVERY_TARGET": "40%",
        "SAME_DAY_CANCEL_TARGET": "5%",
        "SAME_DAY_CANCEL_HOURS": "24",
        "RESCHEDULE_WINDOW_DAYS": "7",
        "BOOKING_UTILIZATION_TARGET": "80%",
        "POST_SESSION_REBOOK_TARGET": "60%",
        "SEVEN_DAY_REBOOK_TARGET": "40%",
        "REBOOKING_CONVERSION_TARGET": "50%",
        "SAME_CONVERSATION_REBOOK_TARGET": "25%",
        "BOOKING_CYCLE_TIME_MINUTES": "10",
        "APPOINTMENTS_PER_STAFF_PER_DAY": "8",
        "TRAVEL_BUFFER_MINUTES": "15",
        "DISPATCH_TO_ARRIVAL_MINUTES": "45",
        "ON_TIME_ARRIVAL_TARGET": "90%",
        "ON_TIME_ESCALATION_THRESHOLD": "30",
        "ON_TIME_RECOVERY_TARGET": "95%",
        "DEVIATION_RESOLUTION_MINUTES": "60",
        "STAFF_NONRESPONSE_TARGET": "5%",
        "SCHEDULE_CHANGE_RATE_TARGET": "10%",
        "MAX_REROUTES_PER_DAY": "3",
        "COMMUNICATION_RESPONSE_TARGET": "4 hours",
        # Sales / revenue
        "AVG_DEAL_SIZE": "$2,500",
        "MONTHLY_LEAD_TARGET": "50",
        "WEEKLY_INQUIRY_TARGET": "15",
        "MONTHLY_OPP_TARGET": "20",
        "MONTHLY_NEW_CUSTOMER_TARGET": "10",
        "MONTHLY_EXPANSION_TARGET": "$5,000",
        "MONTHLY_RETENTION_TARGET": "95%",
        "CONVERSION_RATE_TARGET": "25%",
        "FOLLOWUP_OPEN_RATE_TARGET": "40%",
        "FOLLOWUP_REPLY_TARGET": "10%",
        "MAX_TOUCH_GAP_DAYS": "3",
        "TARGET_AUDIENCE": "solopreneurs and small business owners",
        "TARGET_JOB_FUNCTION": "Founder / CEO",
        "LEAD_SOURCE": "organic + paid social",
        "AVG_SESSION_VALUE": "$500",
        "ONBOARDING_OPEN_RATE_TARGET": "60%",
        "ONBOARDING_WINDOW_DAYS": "7",
        "DAY7_CONVERSION_TARGET": "30%",
        "FIRST_SESSION_RETENTION_TARGET": "80%",
        "RETENTION_WINDOW_DAYS": "30",
        "WAITLIST_MAX_DAYS": "14",
        "WAITLIST_ESCALATION_COUNT": "10",
        "WAITLIST_ESCALATION_THRESHOLD": "20",
        "WAITLIST_CONVERSION_TARGET": "40%",
        "VSL_CONVERSION_TARGET": "5%",
        "TESTIMONIAL_COLLECTION_TARGET": "10/month",
        "REFERRAL_TARGET": "5/month",
        "CASE_STUDY_TARGET": "1/quarter",
        "RECOMMENDATION_ADOPTION_TARGET": "70%",
        # Customer success / support
        "HEALTH_SCORE_TARGET": "80",
        "CHURN_RATE": "5%",
        "NRR_TARGET": "110%",
        "GRR_TARGET": "95%",
        "ARR": "(set at build)",
        "MRR": "(set at build)",
        "CONTRACTED_ARR": "(set at build)",
        "ARR_EXAMPLE": "$120,000",
        "ARPU": "$200",
        "FOUNDING_MEMBER_ARR": "$36,000",
        "FOUNDING_RETENTION_TARGET": "90%",
        "FOUNDING_NPS_TARGET": "50",
        "EXPANSION_CALC": "NRR - GRR",
        "TOTAL_MEMBERS": "(set at build)",
        "MEMBER_TIER": "Standard",
        "MEMBERSHIP_SUPPORT_TICKETS": "50/month",
        "ENROLLMENT_YEAR": _iso_year,
        "CUSTOMER_SERVICE_CONTACT_COST": "$15",
        "CS_HANDOFF_PROCESS": "warm handoff via CRM note + Slack message",
        "CS_PLATFORM_NAME": "GoHighLevel",
        "SDR_TEAM": "Sales team",
        "MARKETING_TEAM": "Marketing team",
        "CUSTOMER_SUCCESS_TEAM": "Customer Success team",
        "CUSTOMER_SUPPORT_TEAM": "Customer Support team",
        "COMPETITIVE_INTEL_TEAM": "Research team",
        "COMPETITOR_LIST": "(add top 3 competitors post-build)",
        "REFERENCE_CUSTOMER": "(add a reference customer post-build)",
        "PRODUCT_FEEDBACK_PROCESS": "collect in Notion → weekly review",
        # Video / content
        "MONTHLY_WATCH_HOURS": "10,000",
        "VIDEOS_PER_MONTH": "8",
        "IMPRESSIONS_TARGET": "100,000/month",
        "REVENUE_PER_VIEW": "$0.004",
        "TARGET_PRODUCTION_HOURS": "40/month",
        "YT_AD_REVENUE": "$400/month",
        "SPONSORSHIP_REVENUE": "$2,000/month",
        "COURSE_ATTRIBUTION": "YouTube → course landing page",
        "VSL_SALES": "$10,000/month",
        "TOTAL_VIDEO_REVENUE": "(set at build)",
        "YOUTUBE_CTR_BENCHMARK": "5%",
        "MONTHLY_PODCAST_DOWNLOAD_TARGET": "5,000",
        "MONTHLY_PODCAST_LEAD_TARGET": "25",
        "EPISODE_TITLE": "(set per episode)",
        "MONTHLY_PRODUCTION_TARGET": "4 episodes/month",
        # Research / intel
        "INDUSTRY_STATISTIC": "(source an industry statistic post-build)",
        "MARKET_SIZE": "(research market size post-build)",
        "GROWTH_RATE": "(research industry growth rate post-build)",
        "INDUSTRY_BENCHMARK_CTR": "2%",
        "EMAIL_CTR_BENCHMARK": "3%",
        "REVENUE": "(set at build)",
        "REVENUE_CASCADE": "see cascade KPIs above",
        "GROWTH": "(set at build)",
        "CUSTOMERS": "(set at build)",
        # Engineering / dev
        "TEST_COVERAGE_TARGET": "80%",
        "DEPLOY_FREQUENCY_TARGET": "daily",
        "QUARTERLY_FEATURE_TARGET": "4",
        "RELEASE_VERSION": "1.0.0",
        "VERSION": "1.0.0",
        "DEPENDENCY_NAME": "(dependency name)",
        "THIRD_PARTY_VENDOR": "(vendor name)",
        "ENGINEER_NAME": "(engineer name)",
        "ENGINEER_NAME_2": "(engineer name 2)",
        "ENGINEER_RAMP_DAYS": "30",
        "TICKET_ID": "(ticket ID)",
        "CVE_ID": "(CVE ID)",
        "FEATURE": "(feature name)",
        "DEBT_ITEM": "(tech debt item)",
        "ESTIMATED_IMPACT": "(estimated impact)",
        "DEADLINE": "(set per task)",
        "STAGING_ENV_URL": "staging." + (company_slug or "company") + ".com",
        "environment_name": "production",
        "db_name": "app_db",
        "FUNDING_AMOUNT": "(set per funding round)",
        "MARKET_SIZE_EXAMPLE": "(set post-research)",
        # Listings / real estate
        "ACTIVE_LISTINGS_TARGET": "10",
        "WEEKLY_LISTINGS_TARGET": "2",
        "KEY_LOCATION": "(primary market location)",
        "AVAILABILITY_DATE": "(set per listing)",
        "CITY_NAME": "(city name)",
        "STATE_NAME": "(state name)",
        "TTL_SLA_HOURS": "48",
        "DA_THRESHOLD": "40",
        # Logistics / fulfillment
        "OTIF_TARGET": "95%",
        "OTIF_FLOOR": "90%",
        "OTIF_DAILY_FLOOR": "88%",
        "CARRIER_OTIF_FLOOR": "92%",
        "COST_PER_ORDER_TARGET": "$8",
        "COST_PER_RETURN_TARGET": "$5",
        "RETURN_RATE_TARGET": "5%",
        "MAX_CUSTOMER_WAIT_DAYS": "5",
        "RETURN_WINDOW_DAYS": "30",
        "RETURNS_PROCESSING_SLA_HOURS": "48",
        "MAX_RETURN_RATE": "10%",
        "ORDER_PROCESSING_HOURS": "24",
        "DELIVERY_SATISFACTION_TARGET": "90%",
        "TRACKING_STALL_HOURS": "48",
        "CARRIER_TRACE_SLA_HOURS": "24",
        "CARRIER_CLAIM_FOLLOWUP_DAYS": "7",
        "RETURN_RATE_SPIKE_THRESHOLD": "15%",
        "VENDOR_FILL_RATE_TARGET": "98%",
        "INVENTORY_ACCURACY_TARGET": "99%",
        "INVENTORY_TURNOVER_TARGET": "12x/year",
        "INVENTORY_RECOVERY_RATE_TARGET": "80%",
        "SLOW_MOVING_THRESHOLD": "90",
        "STOCKOUT_WARNING_DAYS": "7",
        "MIN_DAYS_OF_SUPPLY": "14",
        "MAX_DAYS_OF_SUPPLY": "60",
        "B_MIN_DAYS": "7",
        "B_MAX_DAYS": "30",
        "B_ITEM_STOCKOUT_TARGET": "2%",
        "MAX_SHRINKAGE_THRESHOLD": "1%",
        "DEAD_STOCK_WRITEOFF_THRESHOLD": "180",
        "HIGH_REVENUE_SKU_THRESHOLD": "$200",
        "MIN_LIQUIDATION_RECOVERY": "30%",
        "EXCEPTION_RATE_TARGET": "2%",
        "VENDOR_PORTAL_URL": "vendor-portal." + (company_slug or "company") + ".com",
        "FORECAST_ACCURACY_PERCENT": "85%",
        "MAX_DISCOUNT_PERCENT": "20",
        "CONTRACT_REVIEW_PROCESS": "legal review required for contracts > $5,000",
        "LEGAL_COMPLIANCE_CONTACT": "legal@" + (company_slug or "company") + ".com",
        "LEGAL_REVIEW_SLA": "5 business days",
        "ANNUAL_TARGET": "(set at build — yearly revenue target)",
        "MONTHLY": "(computed from yearly / 12)",
        "WEEKLY": "(computed from yearly / 52)",
        "DAILY": "(computed from yearly / 250)",
        "MONTH": _now.strftime("%B"),
        "Month": _now.strftime("%B"),
        "QUARTER": f"Q{(_now.month - 1) // 3 + 1}",
        "WEEK_NUMBER": _now.strftime("%V"),
        "NUMBER": "1",
        "TOTAL": "(computed)",
        "AMOUNT": "(set per task)",
        "VALUE": "(set per task)",
        "RELATIONSHIP_NAME": "(set per task)",
        "SOP_NAME": "(SOP name)",
        "TOKEN": "(token value)",
        "TOKEN_NAME": "(token name)",
        "TOKENS": "(token values)",
        "NAME": "(name)",
        "GUEST_NAME": "(guest name)",
        "MEMBER_NAME": "(member name)",
        "CLIENT_NAME": "(client name)",
        "CLIENT_FIRST_NAME": "(client first name)",
        "CLIENT_METHOD": "(client's preferred contact method)",
        "FIRST_NAME": owner_name or "(first name)",
        "FirstName": owner_name or "(first name)",
        "first_name": "(first name)",
        "ACCOUNT_NAME_TOKEN": "(account name)",
        "SERVICE": "(service name)",
        "SERVICE_TYPE": "(service type)",
        "SERVICE_PRICE": "(service price)",
        "PRICE_POINT": "(price point)",
        "PRODUCT_NAME": "(product name)",
        "PRODUCT_SLUG": re.sub(r"[^a-z0-9]+", "-", (company_name or "product").lower()).strip("-"),
        "DEPT_HEAD_PERSONA_OR_ROLE": director,
        "DESCRIPTION": "(description)",
        "COMPETITOR_LIST_PLACEHOLDER": "(list top competitors post-build)",
        # Scheduling / personal assistant
        "APPOINTMENT_TIME": "(set per appointment)",
        "APPOINTMENT_TIME_TOKEN_NAME": "appointment_time",
        "BOOKING_LINK": "https://calendly.com/" + (company_slug or "company"),
        "HIGH_VALUE_APPOINTMENT_TYPES": "strategy call, discovery call",
        "ANNIVERSARY_GIFT_BUDGET": "$100",
        "HOLIDAY_PREP_DEADLINE": "December 1",
        "MEMBER_PORTAL_URL": "members." + (company_slug or "company") + ".com",
        # Phone / SMS
        "PHONE_PLATFORM_NAME": "GoHighLevel",
        "PHONE_TOOL_NAME": "GoHighLevel",
        "SMS_PLATFORM_NAME": "GoHighLevel",
        "SMS_TOOL_NAME": "GoHighLevel",
        # QC
        "QC_APPROVAL_RATE_TARGET": "95%",
        "CRITICAL_DEFECT_RATE_TARGET": "0.1%",
        "GREEN_PCT": "90",
        "RED_PCT": "10",
        # Misc date offsets (relative descriptions — not computed, kept readable)
        "DATE_1": "(date 1)",
        "DATE_2": "(date 2)",
        "DATE_3": "(date 3)",
        "DATE_PLUS_3_DAYS": "(3 days from task date)",
        "DATE_PLUS_5_DAYS": "(5 days from task date)",
        "DATE_PLUS_7_DAYS": "(7 days from task date)",
        "DATE_PLUS_14_DAYS": "(14 days from task date)",
        # Misc lowercase template vars (e.g. used in GHL workflow templates)
        "campaign_name": "(campaign name)",
        "campaign_source": "(campaign source)",
        "department_budget_code": "(department budget code)",
        "expiry_date": "(expiry date)",
        "optional_keyword": "(optional keyword)",
        "rate": "(rate)",
        "requester_name": "(requester name)",
        "variant_identifier": "(variant identifier)",
        "environment_name": "production",
        "REVENUE_PER_VIEW": "$0.004",
        # founding-member-concierge / membership
        "FOUNDING_MEMBER_ARR": "$36,000",
        "TOTAL_MEMBERS": "(set at build)",
        "ENROLLMENT_YEAR": _iso_year,
        "WEEKEND_AVAILABILITY": "by appointment only",
        # Real-estate / listings extra
        "WEEKLY_REVENUE_LIFT": "$500",
        "WEEKLY_SHOW_RATE_REVENUE_LIFT": "$250",
        # Web / membership site
        "REPO_MARKETING_SITE": "github.com/" + (company_slug or "company") + "/marketing-site",
        "REPO_CUSTOMER_DASHBOARD": "github.com/" + (company_slug or "company") + "/customer-dashboard",
        "REPO_ADMIN_PANEL": "github.com/" + (company_slug or "company") + "/admin",
        "PAYMENT_GATEWAY_DASHBOARD": "dashboard.stripe.com",
        "MEMBERSHIP_SUPPORT_TICKETS": "50/month",
        "QUARTERLY_FEATURE_TARGET": "4",
        "COMMUNITY_PLATFORM": "Skool",
        "CMS_PLATFORM": "WordPress",
        "HOSTING_PROVIDER": "Vercel",
        "CDN_PROVIDER": "Cloudflare",
        "ANALYTICS_PLATFORM": "Google Analytics 4",
        # Remaining tokens not yet covered above
        "CASCADE_DELAY_THRESHOLD": "30",
        "CLOUD_PLATFORM": "AWS",
        "CLOUD_PROVIDER": "AWS",
        "CRM_UPDATE_LAG_MINUTES": "15",
        "HOURLY_REVENUE_AT_RISK": "$100",
        "MAX_UTILIZATION_PERCENT": "90",
        "MIN_UTILIZATION_PERCENT": "50",
        "SAME_DAY_COMPLETION_TARGET": "90%",
        "TARGET_CYCLE_DAYS": "30",
        "WEEKLY_BOOKINGS": "(set at build)",
        "EMAIL_PREVIEW_TOOL": "Litmus",
    }

    # ── MERGE: config-sourced take precedence over defaults ──────────────────────
    # Build final map: _defaults first, then primary tokens override them.
    final_tokens = {**_defaults, **tokens}

    # Revenue cascade fallback: if yearly was not set, insert readable placeholders
    # so the cascade tokens never survive as {{...}} in built output.
    _cascade_fallbacks = {
        "YEARLY_GOAL": "(set yearlyRevenueGoal in config)",
        "QUARTERLY_TARGET": "(set yearlyRevenueGoal in config)",
        "MONTHLY_TARGET": "(set yearlyRevenueGoal in config)",
        "WEEKLY_TARGET": "(set yearlyRevenueGoal in config)",
        "DAILY_TARGET": "(set yearlyRevenueGoal in config)",
    }
    for k, v in _cascade_fallbacks.items():
        if not final_tokens.get(k):
            final_tokens[k] = v

    out = content
    for key, val in final_tokens.items():
        if val is None:
            continue
        out = out.replace("{{" + key + "}}", str(val))

    return out


def try_library_fill(role_name, dept_path, is_ceo, lib_key=None):
    """
    Look up the library for a pre-written how-to.md, token-fill it, and return
    the filled content. Returns None if no library match (caller falls back
    to stub_how_to).

    lib_key: optional explicit library lookup key (the canonical role slug). When
    provided it is tried FIRST so a decorated display name can never defeat the
    lookup; falls back to role_name if the explicit key misses.
    """
    # WS-2: pass the RAW role name (not the naive slug) so the normalizer can
    # strip decorations / employment qualifiers and reach ~100% match coverage.
    dept_slug = dept_path.name.replace("-dept", "").strip().lower()

    doc_path, role_entry = (None, None)
    if lib_key:
        doc_path, role_entry = library_lookup(lib_key, dept_slug)
    if not doc_path:
        doc_path, role_entry = library_lookup(role_name, dept_slug)
    if not doc_path:
        return None

    try:
        raw = doc_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  [Wave 5b] WARN: failed reading {doc_path}: {e}", file=sys.stderr)
        return None

    dept_name = dept_path.name.replace("-dept", "").replace("-", " ").title()
    filled = fill_tokens(raw, role_name, dept_name, is_ceo, role_entry=role_entry)

    # BUG 1 FIX: only stamp the "Filled from role-library" marker AFTER confirming
    # that the filled content is substantive (>= 3072 bytes — same floor that
    # verify-wiring.sh and qc-completeness.sh enforce).  A stub that received the
    # marker was passing the library gate while failing the wiring gate because the
    # gate trusted the marker rather than checking real content size.  If the filled
    # string is below the floor, return None so the caller falls back to the
    # PENDING-stub path (which is correctly flagged as unfilled) instead of
    # rubber-stamping thin output as "done".
    LIBRARY_FILL_MIN_BYTES = 3072  # matches HOW_TO_MIN_BYTES in verify-wiring.sh
    if len(filled.encode("utf-8")) < LIBRARY_FILL_MIN_BYTES:
        print(
            f"  [Wave 5b] WARN: library fill for '{role_name}' ({dept_path.name}) "
            f"produced {len(filled.encode('utf-8'))} bytes — below {LIBRARY_FILL_MIN_BYTES}B "
            f"floor; treating as NO MATCH so stub path is used instead.",
            file=sys.stderr,
        )
        return None

    # Stamp the front so reviewers can tell at a glance this came from library.
    # Marker is written ONLY when content size >= floor (enforced above).
    #
    # PER-ARTIFACT PROVENANCE (v12.27.0): emit the resolved SOURCE content_sha +
    # content_version COPIED FROM THE MANIFEST entry for this role (role_entry IS
    # the _index.json entry that library_lookup returned, which now carries
    # content_sha/content_version stamped by hash-content-manifest.py). This is
    # the SOURCE hash — NEVER a hash of the rendered client file — so
    # detect-stale-artifacts.py can compare it against the live manifest and tell
    # whether THIS client's copy of this role is CURRENT or STALE. The old marker
    # rendered `v?` (no version field existed) and carried no sha.
    _gen_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    _content_sha = (role_entry or {}).get('content_sha', 'sha256:UNKNOWN')
    _content_ver = (role_entry or {}).get('content_version', '?')
    _slug = (role_entry or {}).get('slug', '?')
    _dept = (role_entry or {}).get('dept', dept_slug)
    header = (
        f"<!-- workforce-provenance: source=role-library "
        f"role-slug={_slug} dept={_dept} content_sha={_content_sha} "
        f"content_version={_content_ver} instantiated={_gen_date} "
        f"generator=create_role_workspaces.py -->\n"
    )
    return header + filled


# ─── PATH / NAMING HELPERS ────────────────────────────────────────────────────

def slugify(name):
    s = name.lower().strip()
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


# ─── CORE: CREATE A SINGLE ROLE WORKSPACE ─────────────────────────────────────

def create_role_workspace(dept_path, role_name, workspace_root, role_metadata=None):
    """
    Create a single role-level workspace inside dept_path. Uses library
    template-fill for how-to.md when a matching doc exists; falls back to
    stub otherwise.
    """
    role_metadata = role_metadata or {}

    # DEFECT #4 FIX: dept-scoped instantiation must produce numbered folders
    # `NN-<clean-slug>/` that AGREE with build-workforce.py and the role-library.
    # Precedence for the bare slug:
    #   1. explicit role_metadata["slug"] (canonical roster slug — authoritative)
    #   2. slugify(role_name) (legacy fallback for callers that pass only a name)
    # When a role number is supplied, the folder is zero-padded `NN-<slug>`; the
    # CEO/master-orchestrator keeps its un-numbered well-known folder name.
    explicit_slug = (role_metadata.get("slug") or "").strip()
    base_slug = explicit_slug or slugify(role_name)
    is_ceo = (role_metadata.get("is_ceo", False)
              or base_slug == "master-orchestrator"
              or slugify(role_name) == "master-orchestrator")

    role_number = role_metadata.get("number", role_metadata.get("role_number"))
    if is_ceo:
        # CEO lives at a stable, un-numbered folder (resolved by name elsewhere).
        role_slug = base_slug
        folder_name = base_slug
    elif role_number is not None and str(role_number).strip() != "":
        try:
            _num = int(role_number)
            folder_name = f"{_num:02d}-{base_slug}"
        except (TypeError, ValueError):
            folder_name = base_slug
        role_slug = base_slug
    else:
        # No number supplied: keep legacy un-numbered behavior (backward-safe).
        role_slug = base_slug
        folder_name = base_slug

    role_path = Path(dept_path) / folder_name
    role_path.mkdir(parents=True, exist_ok=True)
    dept_name = Path(dept_path).name.replace("-dept", "").replace("-", " ").title()

    # ── MSF: stamp capability_class into role_metadata (Layer-2, v1.0.0) ──────
    # Resolve the capability class for this role if not already in metadata.
    # This enriches role_metadata so downstream consumers (fill_tokens, etc.)
    # can surface the class without re-computing.
    if "capability_class" not in role_metadata:
        dept_slug = Path(dept_path).name.replace("-dept", "").strip().lower()
        _rtype = role_metadata.get("role_type", "")
        _cls_info = _crw_get_capability_class(role_slug, dept_slug, _rtype)
        if _cls_info:
            role_metadata = dict(role_metadata)  # don't mutate caller's dict
            role_metadata["capability_class"] = _cls_info.get("capability_class", "")
            role_metadata["vision_flag"] = _cls_info.get("vision_flag", False)
            role_metadata["msf_purpose_tier"] = _cls_info.get("purpose_tier", "")

    # Unique identity files
    (role_path / "IDENTITY.md").write_text(
        stub_identity(role_name, dept_name, is_ceo), encoding="utf-8")
    (role_path / "SOUL.md").write_text(
        stub_soul(role_name, dept_name, is_ceo), encoding="utf-8")
    (role_path / "MEMORY.md").write_text(
        stub_memory(role_name), encoding="utf-8")
    (role_path / "HEARTBEAT.md").write_text(
        stub_heartbeat(role_name, dept_name), encoding="utf-8")

    # how-to.md: library first, stub fallback. Feed the explicit canonical slug
    # as the lookup key so a decorated display name can never defeat the fill.
    filled = try_library_fill(role_name, Path(dept_path), is_ceo,
                              lib_key=(explicit_slug or None))
    if filled is not None:
        (role_path / "how-to.md").write_text(filled, encoding="utf-8")
        print(f"  [library-fill] {folder_name} ← templates/role-library/...")
    else:
        (role_path / "how-to.md").write_text(
            stub_how_to(role_name, dept_name, is_ceo), encoding="utf-8")

    # v10.9.0 P1-E: SOP/ subfolder per role (N19 requirement)
    # Per-role SOP folder holds the how-to docs the role uses on the job.
    # Some roles get one giant document; some get multiple. how-to.md (root)
    # is the canonical INDEX into SOP/. This is where the role looks for
    # instructions on individual tasks.
    sop_dir = role_path / "SOP"
    sop_dir.mkdir(exist_ok=True)
    sop_index = sop_dir / "00-INDEX.md"
    if not sop_index.exists():
        sop_index.write_text(
            f"""# {role_name} — SOP Index

This folder contains the standard operating procedures the {role_name} uses
to perform their job. The role's `how-to.md` (one level up) is the entry
point and references this folder.

## How this folder works

- **00-INDEX.md** (this file) — table of contents for the SOPs in this folder.
- **NN-<topic>.md** — individual SOPs, numbered in execution order where order matters.
  Examples:
    01-daily-startup.md
    02-task-intake.md
    03-quality-check.md
    99-escalation-protocol.md
- **_assets/** (optional) — supporting files referenced by SOPs (templates, screenshots, prompts).

## Conventions

- Each SOP is one focused procedure. Don't bury 5 procedures in one doc.
- Each SOP starts with: Purpose, Inputs, Steps, Outputs, Escalation.
- SOPs are READ-FIRST: the role MUST read the relevant SOP before executing
  a task it covers. No improvising.
- When a persona is assigned for a task (see workspace-level `governing-personas.md`),
  the persona governs HOW the role executes the SOP — but the SOP's WHAT remains
  the canonical procedure.

## Populating this folder

Initially this folder may contain only this index. SOPs are added incrementally:
- By the role itself as it accumulates work (the role writes its own SOPs)
- By the `populate-sops-from-manifest.py` script when a role-library manifest exists for this department
- By the Master Orchestrator dispatching a "write SOP" task during onboarding for high-priority procedures

When a new SOP is added, append a line to the table below.

## Current SOPs

| # | File | Purpose |
|---|------|---------|
| 00 | 00-INDEX.md | This index |

(Add new SOPs as rows above as they're authored.)
""",
            encoding="utf-8",
        )

    # Symlinks for shared files
    for shared in ["AGENTS.md", "TOOLS.md", "USER.md"]:
        link_path = role_path / shared
        target = Path(workspace_root) / shared
        try:
            if link_path.exists() or link_path.is_symlink():
                link_path.unlink()
            link_path.symlink_to(target)
        except OSError as e:
            print(f"  WARN: could not symlink {shared} in {role_path}: {e}",
                  file=sys.stderr)
            link_path.write_text(
                f"# {shared} — see workspace root\n\n"
                f"Symlink to {target} failed. Re-run create_role_workspaces.py "
                f"with appropriate permissions.\n")

    return role_path


# ─── AUGMENT EXISTING ROLE FOLDERS (Wave 5b: previously missing!) ────────────

V21_REQUIRED = ["IDENTITY.md", "SOUL.md", "MEMORY.md", "HEARTBEAT.md", "how-to.md"]
V21_SYMLINKS = ["AGENTS.md", "TOOLS.md", "USER.md"]


def augment_role_folder(role_path, workspace_root, role_metadata=None):
    """
    Add v2.1 files to an existing role folder if missing. Idempotent.
    Returns {"written": [filenames], "symlinked": [filenames]}.
    """
    role_path = Path(role_path)
    workspace_root = Path(workspace_root)
    role_metadata = role_metadata or {}

    if not role_path.is_dir():
        return {"written": [], "symlinked": [], "error": f"not a directory: {role_path}"}

    role_slug = role_path.name
    # Strip leading numeric prefix like "00-" or "12-"
    name_for_display = re.sub(r"^\d+-", "", role_slug)
    role_name = role_metadata.get("name") or name_for_display.replace("-", " ").title()
    is_ceo = (role_metadata.get("is_ceo", False)
              or role_slug == "master-orchestrator")
    dept_path = role_path.parent
    dept_name = dept_path.name.replace("-dept", "").replace("-", " ").title()

    written = []
    for filename in V21_REQUIRED:
        fpath = role_path / filename
        if fpath.exists():
            continue
        if filename == "IDENTITY.md":
            fpath.write_text(stub_identity(role_name, dept_name, is_ceo), encoding="utf-8")
        elif filename == "SOUL.md":
            fpath.write_text(stub_soul(role_name, dept_name, is_ceo), encoding="utf-8")
        elif filename == "MEMORY.md":
            fpath.write_text(stub_memory(role_name), encoding="utf-8")
        elif filename == "HEARTBEAT.md":
            fpath.write_text(stub_heartbeat(role_name, dept_name), encoding="utf-8")
        elif filename == "how-to.md":
            filled = try_library_fill(role_name, dept_path, is_ceo)
            if filled is not None:
                fpath.write_text(filled, encoding="utf-8")
                print(f"  [library-fill] {role_slug} ← templates/role-library/...")
            else:
                fpath.write_text(stub_how_to(role_name, dept_name, is_ceo), encoding="utf-8")
        written.append(filename)

    # v10.9.0 P1-E: ensure SOP/ folder exists in augmented roles too
    sop_dir = role_path / "SOP"
    if not sop_dir.exists():
        sop_dir.mkdir(parents=True, exist_ok=True)
        sop_index = sop_dir / "00-INDEX.md"
        if not sop_index.exists():
            sop_index.write_text(
                f"# {role_name} — SOP Index\n\n"
                f"Operating procedures for {role_name} in {dept_name}.\n"
                f"Files: NN-<topic>.md (numbered in execution order where order matters).\n"
                f"This index is auto-created by create_role_workspaces.py augment path.\n",
                encoding="utf-8",
            )
            written.append("SOP/00-INDEX.md")

    symlinked = []
    for shared in V21_SYMLINKS:
        link_path = role_path / shared
        if link_path.exists() or link_path.is_symlink():
            continue
        target = workspace_root / shared
        try:
            link_path.symlink_to(target)
            symlinked.append(shared)
        except OSError as e:
            print(f"  WARN: could not symlink {shared}: {e}", file=sys.stderr)

    return {"written": written, "symlinked": symlinked}


def augment_all_existing_role_folders(dept_path, workspace_root, dry_run=False):
    """
    Walk every subfolder of dept_path. For each subfolder that looks like a role
    folder (not a known special name), augment it.
    Returns a list of {"role": slug, "written": [...], "symlinked": [...]}.
    """
    dept_path = Path(dept_path)
    workspace_root = Path(workspace_root)
    SKIP_NAMES = {"memory", "devils-advocate", "_archive", "_index",
                  "_compliance_audit", "_pending_rewrite", "_stage1_drafts"}

    results = []
    for entry in sorted(dept_path.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name in SKIP_NAMES or entry.name.startswith("."):
            continue

        if dry_run:
            results.append({"role": entry.name, "written": [], "symlinked": [], "dry_run": True})
            print(f"    [DRY-RUN] would augment {entry.name}")
            continue

        result = augment_role_folder(entry, workspace_root)
        result["role"] = entry.name
        results.append(result)
        if result["written"] or result["symlinked"]:
            extras = []
            if result["written"]:
                extras.append(f"+files: {','.join(result['written'])}")
            if result["symlinked"]:
                extras.append(f"+links: {','.join(result['symlinked'])}")
            print(f"    {entry.name}: {' | '.join(extras)}")

    # ROOT-CAUSE FIX: after (re)materializing/augmenting a department's role
    # folders, ALWAYS refresh its ROSTER.md from the folders now on disk. This is
    # the path post-build-role-workspaces.py (and the resume/fleet pass) take, so
    # a partial or resume materialization can never leave a stale roster behind.
    regenerate_department_roster(dept_path, dry_run=dry_run)
    return results


# ─── governing-personas.md per dept (v10.8.0 P0-3 fix) ────────────────────────

def write_governing_personas_md(dept_path, dept_id, dept_name=None):
    """
    Write a department's governing-personas.md reference guide. This file is
    the persona-matching protocol's required per-department artifact (Hop 9
    of the integration trace).

    The persona-selector reads `persona-categories.json` at runtime and
    decides which persona to apply per task. This file is a HUMAN reference
    listing the top pre-qualified personas for this department — it does
    NOT statically assign a persona. The selector still chooses dynamically.

    Idempotent: overwrites the file each time the workspace is rebuilt so
    edits to persona-categories.json propagate.
    """
    dept_path = Path(dept_path)
    if not dept_path.exists():
        return None

    if dept_name is None:
        dept_name = dept_path.name.replace("-dept", "").replace("-", " ").title()

    # Read persona-categories.json via detect_platform (P0-5 path resolver)
    persona_list_text = "_(persona-categories.json not found at install time — "\
                         "this file will repopulate after Skill 22 builds the catalog)_"
    try:
        paths = get_openclaw_paths()
        pc_path = paths.get("persona_categories")
        if pc_path and Path(pc_path).exists():
            data = json.loads(Path(pc_path).read_text(encoding="utf-8"))
            # Schema is dict {persona_id: {author, book, domain, perspective, custom}}
            # OR list [{id, ...}]
            entries = []
            if isinstance(data, dict):
                for pid, meta in data.items():
                    if not isinstance(meta, dict):
                        continue
                    entries.append({"id": pid, **meta})
            elif isinstance(data, list):
                for m in data:
                    if isinstance(m, dict):
                        entries.append(m)
            # Pick personas whose domain tag plausibly matches this dept.
            # We use a simple keyword family map below — selector still does
            # the real LLM-evaluated pick per task.
            dept_lower = dept_id.lower().replace("-dept", "").replace("dept-", "")
            # Valid domain keys (from persona-categories.json domainTags):
            #   marketing, sales, leadership, finance, operations, communication,
            #   copywriting, mindset, productivity-systems, coaching,
            #   strategy-innovation, personal-development
            # FIX 2 (2026-06-17): added 12 canonical departments that were missing,
            # causing them to fall back to first-5 personas instead of domain-matched ones.
            DEPT_DOMAIN_HINTS = {
                "marketing":      ["marketing", "copywriting", "strategy-innovation"],
                "sales":          ["sales", "communication", "copywriting"],
                "billing":        ["finance", "operations"],
                "billing-finance": ["finance", "operations"],
                "customer-support": ["communication", "coaching"],
                "crm":            ["sales", "communication"],
                "social-media":   ["marketing", "communication", "copywriting"],
                "paid-advertisement": ["marketing", "copywriting", "strategy-innovation"],
                "research":       ["strategy-innovation", "productivity-systems"],
                "communications": ["communication", "leadership"],
                "legal":          ["leadership", "strategy-innovation"],
                "legal-compliance": ["leadership", "strategy-innovation"],
                "openclaw-maintenance": ["productivity-systems", "operations"],
                "web-development":  ["productivity-systems"],
                "app-development":  ["productivity-systems"],
                "graphics":         ["copywriting", "strategy-innovation"],
                "video":            ["copywriting", "strategy-innovation"],
                "video-production": ["copywriting", "strategy-innovation"],
                "audio":            ["copywriting", "communication"],
                "audio-production": ["copywriting", "communication"],
                # --- FIX 2 additions (2026-06-17) ---
                "presentations":    ["copywriting", "marketing", "communication"],
                "bugs":             ["productivity-systems", "strategy-innovation", "operations"],
                "healer":           ["coaching", "personal-development", "mindset"],
                "personal-assistant": ["operations", "leadership", "productivity-systems"],
                "engineering":      ["productivity-systems", "strategy-innovation", "operations"],
                "listings":         ["marketing", "sales", "copywriting"],
                "logistics-fulfillment": ["operations", "productivity-systems"],
                "podcast":          ["copywriting", "communication", "marketing"],
                "scheduling-dispatch": ["operations", "productivity-systems", "leadership"],
                "general-task":     ["operations", "productivity-systems", "leadership"],
                "project-architecture-office": ["strategy-innovation", "leadership", "operations"],
                "project-management": ["leadership", "strategy-innovation", "productivity-systems"],
                # --- FIX 3 additions (2026-06-17, repo-consistency gate) ---
                # These canonical FLOOR dept ids were missing, so they fell back
                # to the first-5-personas default in write_governing_personas_md.
                # Enforced by scripts/qc-assert-repo-consistency.py.
                "crm":              ["sales", "communication", "operations"],
                "quality-control":  ["productivity-systems", "operations", "strategy-innovation"],
                "account-management": ["communication", "coaching", "strategy-innovation"],
            }
            hints = DEPT_DOMAIN_HINTS.get(dept_lower, [])
            ranked = []
            for e in entries:
                domain = (e.get("domain") or "").lower()
                if any(h in domain for h in hints):
                    ranked.append(e)
            # If nothing matched, just show the first 5 in the catalog
            if not ranked:
                ranked = entries[:5]
            else:
                ranked = ranked[:5]

            if ranked:
                rows = []
                for e in ranked:
                    pid = e.get("id", "?")
                    author = e.get("author", "")
                    book = e.get("book", "")
                    domain = e.get("domain", "")
                    rows.append(f"| `{pid}` | {author} | {book} | {domain} |")
                persona_list_text = (
                    "| Persona ID | Author | Source | Domain |\n"
                    "|------------|--------|--------|--------|\n"
                    + "\n".join(rows)
                )
    except Exception as e:
        persona_list_text = f"_(error reading persona-categories.json: {e})_"

    content = f"""# governing-personas.md — {dept_name}

**Generated:** {_now_iso()}
**Department:** {dept_name} (`{dept_id}`)

## What this file is

A REFERENCE GUIDE — not a static assignment. The persona-selector picks the
governing persona per task at runtime using the 5-layer scoring matrix
(mission / owner_values / company_kpis / dept_kpis / task_fit).

This file lists personas that have been **pre-qualified** for this department's
work based on their domain alignment. The selector treats this list as a
recommendation pool, but it can still pick from outside the pool when the
task context warrants it.

## Pre-qualified personas

{persona_list_text}

## How selection works

For every task assigned to this department:

1. The director (or dispatching agent) calls `persona-selector-v2.py --task "..." --department {dept_id}`
2. The selector pre-qualifies personas using Layers 1+2 (company mission +
   owner values fit)
3. It scores remaining candidates on Layers 3-5 (company KPIs / dept KPIs /
   task fit via semantic similarity)
4. The top-scoring persona is selected and the assignment is logged to
   `persona-selection-log.md` + `persona_assignment` DB
5. The role-based agent adopts that persona for the duration of the task
6. On task completion, `record-task-completion` runs the adherence verifier
   and writes back to `persona_assignment.verification_json`

## Anti-staleness

If the same persona is selected ≥5 times in a row for the same (department,
task_category) without a switch, `persona_assignment.needs_review` flips to 1.
Surface that on the dashboard and review whether the stickiness is genuine.

## Updating this file

This file is regenerated every time `create_role_workspaces.py` is run
against the department. Edit `persona-categories.json` (or run Skill 22 to
add more personas) and re-run the workspace builder.
"""
    out_path = dept_path / "governing-personas.md"
    out_path.write_text(content, encoding="utf-8")
    print(f"  ✓ wrote {out_path.relative_to(dept_path.parent) if dept_path.parent.exists() else out_path}")
    return out_path


# ─── BUILD ALL ROLES FOR A DEPT (used by build-workforce.py) ──────────────────

def build_all_roles_for_dept(dept_path, dept_id, roles, workspace_root):
    """
    Create all role workspaces for a department. Each role gets library
    template-fill on its how-to.md when a matching library doc exists.

    v10.8.0 P0-3: also writes governing-personas.md per department (Hop 9
    of the integration trace).
    """
    created = []
    for role in roles:
        role_path = create_role_workspace(
            dept_path, role["name"], workspace_root, role_metadata=role)
        created.append(role_path)
        try:
            rel = role_path.relative_to(Path(workspace_root).parent.parent)
        except ValueError:
            rel = role_path
        print(f"  ✓ Created role workspace: {rel}")

    # Write the per-dept governing-personas.md reference guide (P0-3)
    write_governing_personas_md(dept_path, dept_id)

    return created


# ─── CLI ──────────────────────────────────────────────────────────────────────

def refresh_all_governing_personas_md(workspace_root: Path) -> int:
    """
    v6.6.0 — --refresh-personas-only: walk every dept folder under workspace_root
    and re-write governing-personas.md from the current persona-categories.json.

    Cheap, idempotent, no LLM calls. Called by orchestrator.py Phase 6b after
    a new persona is appended to persona-categories.json so the command-center
    dashboard picks it up without a full workspace rebuild.

    Returns the number of dept folders refreshed.
    """
    refreshed = 0
    # Dept folders are direct children of workspace_root that look like depts
    # (contain a governing-personas.md OR have role sub-folders).
    for child in sorted(workspace_root.iterdir()):
        if not child.is_dir():
            continue
        # Heuristic: dept folders contain role sub-folders or an existing
        # governing-personas.md. Skip obvious non-dept dirs.
        skip_names = {"node_modules", ".git", "scripts", "templates", "shared-utils",
                      "lib", "agent-prompts", "personas", "books", "text", "logs",
                      "backups", "credentials", "secrets", "media"}
        if child.name.startswith(".") or child.name in skip_names:
            continue
        governing_md = child / "governing-personas.md"
        # Only refresh if the file already exists (don't create for non-dept dirs)
        if not governing_md.exists():
            # Check if it has role sub-folders
            has_roles = any(
                (sub / "IDENTITY.md").exists() or (sub / "how-to.md").exists()
                for sub in child.iterdir()
                if sub.is_dir()
            )
            if not has_roles:
                continue
        dept_id = child.name
        try:
            out = write_governing_personas_md(child, dept_id)
            if out:
                refreshed += 1
        except Exception as e:
            print(f"  Warning: could not refresh governing-personas.md for {dept_id}: {e}",
                  file=sys.stderr)
    return refreshed


# ─── DEPT-SCOPED INSTANTIATION (defect #4: a COMPLETE department) ─────────────

_ROSTER_DECORATION_RE = re.compile(r"\([^)]*\)")


def _roster_clean_name(name):
    """Strip parenthetical decorations from a roster `### N. <name>` header so a
    name like 'Capacity and Reliability Engineer (NEW)' reads cleanly. The
    explicit **Slug:** line is the authoritative key; this only tidies display."""
    s = _ROSTER_DECORATION_RE.sub("", str(name or "")).strip()
    return re.sub(r"\s{2,}", " ", s)


def parse_roster(roster_path):
    """
    Parse a suggested-roles markdown roster into a list of role dicts:
        {"number": int, "name": str, "slug": str, "role_type": str}

    Reads the `### N. Name` headers and the per-role `**Slug:**` / `**Role
    type:**` lines. The explicit **Slug:** is the canonical key for both folder
    naming (`NN-<slug>/`) and role-library lookup. Roles without an explicit
    slug fall back to a decoration-stripped slugify of the name.
    """
    roster_path = Path(roster_path)
    text = roster_path.read_text(encoding="utf-8")
    roles = []
    cur = None
    for line in text.split("\n"):
        if line.startswith("### "):
            if cur is not None:
                roles.append(cur)
            header = line[4:].strip()
            parts = header.split(". ", 1)
            try:
                number = int(parts[0])
                name = parts[1] if len(parts) > 1 else header
            except ValueError:
                number = len(roles)
                name = header
            cur = {
                "number": number,
                "name": _roster_clean_name(name),
                "slug": "",
                "role_type": "specialist",
            }
        elif cur is not None:
            if line.startswith("**Slug:**"):
                cur["slug"] = line.replace("**Slug:**", "").strip()
            elif line.startswith("**Role type:**"):
                cur["role_type"] = line.replace("**Role type:**", "").strip().lower()
    if cur is not None:
        roles.append(cur)
    # TABLE-FORMAT FALLBACK (FIX 4, 2026-06-17, repo-consistency gate):
    # Two rosters (general-task, project-architecture-office) list their roles as
    # a markdown table `| # | Slug | Title | Type | Purpose |` instead of
    # `### N. Name` headers. The header parser above returns 0 roles for them, so
    # the dept would silently materialize ZERO specialists despite having full
    # role-library templates. When NO `### N.` roles were parsed, fall back to
    # parsing the role table. Kept in lockstep with build-workforce.parse_suggested_roles.
    if not roles:
        roles = _parse_roster_table(text)
    # Backfill any missing slug from the cleaned name.
    for r in roles:
        if not r["slug"]:
            r["slug"] = slugify(r["name"])
    return roles


def _parse_roster_table(text):
    """Parse a `| # | Slug | Title | Type | Purpose |` role table into role dicts.

    Recognizes the header row (a `|`-delimited row whose normalized cells contain
    both a 'slug' column and a 'title' column), then reads each subsequent data
    row, mapping the slug/title/type columns by position. Skips the `---|---`
    separator row. Returns [] if no recognizable table is present.
    """
    rows = []
    cols = None  # {col_name: index}
    for line in text.split("\n"):
        s = line.strip()
        if not s.startswith("|"):
            cols = None  # a non-table line ends the current table
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        # separator row: all cells are dashes/colons
        if all(re.fullmatch(r":?-{2,}:?", c or "-") for c in cells):
            continue
        lowered = [c.lower().strip("` ") for c in cells]
        if cols is None:
            # Try to interpret this as the header row.
            idx = {name: i for i, name in enumerate(lowered)}
            if "slug" in idx and "title" in idx:
                cols = idx
            continue
        # Data row.
        def cell(name):
            i = cols.get(name)
            return cells[i].strip().strip("`") if i is not None and i < len(cells) else ""
        slug = cell("slug")
        title = cell("title")
        if not slug and not title:
            continue
        num = cell("#")
        try:
            number = int(num)
        except ValueError:
            number = len(rows)
        rows.append({
            "number": number,
            "name": title or slug,
            "slug": slug,
            "role_type": (cell("type") or "specialist").lower(),
        })
    return rows


# ─── DISK-TRUTH DEPARTMENT ROSTER (ROSTER.md) ─────────────────────────────────
# ROOT-CAUSE FIX (2026-06-18): every materialization path writes role folders
# into a department but, before this, NONE of them (re)generated the department's
# ROSTER.md — the When-to Reference Map the director agent actually reads. The
# director reads ROSTER.md, NOT the folders, so it under-reported its roles
# (e.g. "1 role" when 24 NN-<slug>/ folders existed). build-workforce.py wrote
# ROSTER.md only in the full build loop, and even then derived rows from the
# *menu* (parse_suggested_roles), so custom/extra/partial materializations drifted.
#
# These helpers (re)generate ROSTER.md from the ACTUAL on-disk role folders, so
# the roster ALWAYS matches what was materialized. Idempotent — safe to call on
# every materialization path (full build, --from-roster, augment, resume, fleet).

# Folder names that are NOT roles and must be excluded from the roster.
_ROSTER_SKIP_FOLDERS = {
    "memory", "_archive", "_index", "_compliance_audit", "_pending_rewrite",
    "_stage1_drafts", "sops", "scripts", "roles", "_drafts", "artifacts",
    "templates", "assets",
}
# Match a folder/heading title in the per-role IDENTITY.md stub:
#   "# <Role Name> — IDENTITY"   (em-dash or hyphen variants)
_IDENTITY_TITLE_RE = re.compile(r"^#\s+(.*?)\s*[—–-]\s*IDENTITY\s*$")
_REPORTS_TO_RE = re.compile(r"^\*\*Reports to:\*\*\s*(.+?)\s*$", re.IGNORECASE)
_ROLE_TYPE_RE = re.compile(r"^\*\*Role type:\*\*\s*(.+?)\s*$", re.IGNORECASE)
_ROLE_TYPE_ALT_RE = re.compile(r"^\*\*Role Type:\*\*\s*(.+?)\s*$", re.IGNORECASE)
_NN_PREFIX_RE = re.compile(r"^(\d+)-(.*)$")


def _first_md_heading(text):
    """Return the first level-1 markdown heading text, or '' if none."""
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return ""


def _read_role_from_folder(role_path):
    """Read one materialized role folder and return its roster fields from disk.

    The authoritative title/reports-to/type live in the role's own files (written
    by create_role_workspace / the role-library how-to). Resolution order, most to
    least authoritative:
      1. 00-START-HERE.md  -> '# <Role Name>' + '**Role Type:**'
      2. how-to.md         -> '# <Role Name>' + '**Reports to:**' + '**Role type:**'
      3. IDENTITY.md       -> '# <Role Name> — IDENTITY'
      4. folder slug (decoration-stripped, title-cased)
    The leading NN- of the folder name is the role number. A '00-' role is the
    department head.

    Returns {"number", "name", "slug", "role_type", "reports_to", "is_head"} or
    None when role_path is not a usable role folder.
    """
    role_path = Path(role_path)
    if not role_path.is_dir():
        return None
    folder = role_path.name

    number = 999
    slug = folder
    m = _NN_PREFIX_RE.match(folder)
    if m:
        try:
            number = int(m.group(1))
        except ValueError:
            number = 999
        slug = m.group(2)

    name = ""
    reports_to = ""
    role_type = ""

    def _scan(fname):
        nonlocal name, reports_to, role_type
        fpath = role_path / fname
        if not fpath.is_file():
            return
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        if not name:
            if fname == "IDENTITY.md":
                # Try the "<Name> — IDENTITY" stub form first, then a plain heading.
                for line in text.split("\n"):
                    mt = _IDENTITY_TITLE_RE.match(line.strip())
                    if mt:
                        name = mt.group(1).strip()
                        break
                if not name:
                    name = _first_md_heading(text)
            else:
                name = _first_md_heading(text)
        for line in text.split("\n"):
            s = line.strip()
            if not reports_to:
                rm = _REPORTS_TO_RE.match(s)
                if rm:
                    reports_to = rm.group(1).strip()
            if not role_type:
                tm = _ROLE_TYPE_RE.match(s) or _ROLE_TYPE_ALT_RE.match(s)
                if tm:
                    role_type = tm.group(1).strip()

    # 00-START-HERE.md and how-to.md carry the richest, most current metadata.
    for fname in ("00-START-HERE.md", "how-to.md", "IDENTITY.md"):
        _scan(fname)

    if not name:
        name = _roster_clean_name(slug.replace("-", " ").title())

    is_head = (number == 0) or slug == "master-orchestrator"
    return {
        "number": number,
        "name": _roster_clean_name(name),
        "slug": slug,
        "role_type": (role_type or "").lower(),
        "reports_to": reports_to,
        "is_head": is_head,
    }


def scan_department_roles_on_disk(dept_path):
    """Return the materialized role folders for a department, read FROM DISK.

    Supports BOTH layouts: the flat `NN-<slug>/` folders directly under the dept
    dir (what create_role_workspace writes), AND a nested `roles/<slug>/` layout
    if a department uses one. Excludes dept-level meta folders (sops/, scripts/,
    memory/, dot-folders, etc.). Sorted by role number then slug so the head (00)
    leads. Returns a list of role dicts (see _read_role_from_folder).
    """
    dept_path = Path(dept_path)
    if not dept_path.is_dir():
        return []
    roles = []

    def _consider(entry):
        if not entry.is_dir():
            return
        nm = entry.name
        if nm.startswith(".") or nm.lower() in _ROSTER_SKIP_FOLDERS:
            return
        # A role folder has at least one of the canonical role files.
        if not any((entry / f).exists()
                   for f in ("00-START-HERE.md", "IDENTITY.md", "how-to.md")):
            return
        role = _read_role_from_folder(entry)
        if role:
            roles.append(role)

    # Flat NN-<slug>/ layout (canonical).
    for entry in sorted(dept_path.iterdir()):
        _consider(entry)
    # Nested roles/<slug>/ layout (defensive; some trees use it).
    nested = dept_path / "roles"
    if nested.is_dir():
        for entry in sorted(nested.iterdir()):
            _consider(entry)

    roles.sort(key=lambda r: (r.get("number", 999), r.get("slug", "")))
    return roles


def _roster_when_to_use(role):
    """One-line when-to-use cell for a disk-derived role (kept scannable)."""
    return f"Tasks owned by the {role['name']}."


def regenerate_department_roster(dept_path, dept_name=None, dept_head=None,
                                 dept_emoji="", dry_run=False):
    """(Re)generate <dept_path>/ROSTER.md FROM the on-disk role folders.

    This is the idempotent disk-truth companion to
    build-workforce.write_department_roster: instead of deriving rows from the
    suggested-roles menu, it lists exactly the role folders that EXIST in the
    department right now, so the roster can never under-report materialized roles.

    Output matches build-workforce.write_department_roster's format (same header,
    same `| Role | Role folder | Type | When to use |` table, same dispatch
    footer) so the director's OPERATING PROTOCOL reads it identically regardless
    of which path generated it.

    Returns the Path written (or that would be written under dry_run), or None if
    dept_path is not a directory.
    """
    dept_path = Path(dept_path)
    if not dept_path.is_dir():
        return None

    roles = scan_department_roles_on_disk(dept_path)

    if dept_name is None:
        dept_name = dept_path.name.replace("-dept", "").replace("-", " ").title()
    # Department head: prefer an explicit arg, else the 00- head role's name,
    # else any role's stated reports-to, else the dept name.
    if not dept_head:
        head_role = next((r for r in roles if r.get("is_head")), None)
        if head_role:
            dept_head = head_role["name"]
        else:
            dept_head = next((r["reports_to"] for r in roles if r.get("reports_to")),
                             dept_name)

    lines = [
        f"# ROSTER - {dept_name} ({dept_emoji})".rstrip(),
        "",
        f"**Department head:** {dept_head}",
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
            rtype = ("QC" if "qc" in role.get("role_type", "")
                     or role["slug"].endswith("qc-specialist")
                     or role["slug"].startswith("qc-")
                     else ("Head" if role.get("is_head") else "Specialist"))
            lines.append(
                f"| {role['name']} | `{role['slug']}/` | {rtype} | "
                f"{_roster_when_to_use(role)} |"
            )
    else:
        lines.append("| _(no role folders found on disk - investigate "
                     "materialization)_ |  |  |  |")

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
        f"*Generated from the on-disk role folders by create_role_workspaces."
        f"regenerate_department_roster (Skill 23) on "
        f"{datetime.now().strftime('%B %d, %Y at %I:%M %p')}. Lists "
        f"{len(roles)} role folder(s).*",
        "",
    ]

    roster_path = dept_path / "ROSTER.md"
    if not dry_run:
        roster_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[ROSTER] {'(dry-run) ' if dry_run else ''}"
          f"{roster_path} ({len(roles)} roles from disk)")
    return roster_path


def _resolve_dept_library_dir(dept_slug):
    """Return the role-library dir for a dept (Path) or None."""
    skill_dir = _resolve_skill_dir()
    dept_key = normalize_dept(dept_slug)
    cand = skill_dir / "templates" / "role-library" / dept_key
    return cand if cand.is_dir() else None


# Dept-level meta files copied (token-filled) into the workspace department root.
_DEPT_LEVEL_FILES = ["IDENTITY.md", "SOUL.md", "TOOLS.md",
                     "how-to-use-this-department.md"]


def scaffold_department(dept_path, dept_slug, dry_run=False):
    """
    ADDITIVE department-level scaffolding (defect #4). Writes, only if missing
    (never clobbers), the department-level IDENTITY/SOUL/TOOLS/
    how-to-use-this-department from the role-library (token-filled), plus a
    `sops/` folder populated from the library's dept `sops/`. Returns a dict of
    what was written. Writes ONLY under dept_path — never touches siblings.
    """
    dept_path = Path(dept_path)
    written = {"files": [], "sops": 0}
    lib_dir = _resolve_dept_library_dir(dept_slug)
    dept_name = dept_path.name.replace("-dept", "").replace("-", " ").title()

    dept_path.mkdir(parents=True, exist_ok=True)

    # Dept-level meta files (token-filled from the library when present).
    for fname in _DEPT_LEVEL_FILES:
        target = dept_path / fname
        if target.exists():
            continue
        src = (lib_dir / fname) if lib_dir else None
        if src and src.exists():
            raw = src.read_text(encoding="utf-8")
            content = fill_tokens(raw, dept_name, dept_name, False, role_entry=None)
        else:
            content = (f"# {dept_name} — {fname[:-3]}\n\n"
                       f"Department-level {fname[:-3]} for {dept_name}. "
                       f"(No role-library template was available at scaffold time.)\n")
        if not dry_run:
            target.write_text(content, encoding="utf-8")
        written["files"].append(fname)

    # sops/ folder — copy the library dept SOP docs (additive, missing-only).
    sops_target = dept_path / "sops"
    if not dry_run:
        sops_target.mkdir(exist_ok=True)
    if lib_dir and (lib_dir / "sops").is_dir():
        for sop in sorted((lib_dir / "sops").glob("*.md")):
            dest = sops_target / sop.name
            if dest.exists():
                continue
            if not dry_run:
                dest.write_text(sop.read_text(encoding="utf-8"), encoding="utf-8")
            written["sops"] += 1

    # scripts/ folder — copy any dept-level executable scripts (additive,
    # missing-only; never clobbers existing files). This deploys role-owned
    # no-AI generators (e.g. presentations/scripts/build_teleprompter.py,
    # build_deck.py, etc.) into the client workspace so the role SOPs can run
    # them with the relative path 'presentations/scripts/build_teleprompter.py'.
    # Only .py and .sh files are copied; we skip __pycache__ and .pyc.
    scripts_target = dept_path / "scripts"
    if lib_dir and (lib_dir / "scripts").is_dir():
        if not dry_run:
            scripts_target.mkdir(exist_ok=True)
        scripts_copied = 0
        for src_file in sorted((lib_dir / "scripts").iterdir()):
            if src_file.name.startswith("__") or src_file.suffix == ".pyc":
                continue
            if src_file.is_dir():
                continue  # skip nested dirs (e.g. __pycache__)
            if src_file.suffix not in (".py", ".sh", ".json"):
                continue
            dest_file = scripts_target / src_file.name
            if dest_file.exists():
                continue
            if not dry_run:
                import shutil as _shutil
                _shutil.copy2(src_file, dest_file)
            scripts_copied += 1
        if scripts_copied:
            written.setdefault("scripts", 0)
            written["scripts"] = scripts_copied

    return written


def instantiate_department(dept_path, dept_slug, roles, workspace_root,
                           dry_run=False):
    """
    Instantiate a COMPLETE department into dept_path (defect #4). ADDITIVE:
    only writes under dept_path; never overwrites sibling departments.

    For every role: `NN-<clean-slug>/` folder + library-filled how-to.md
    (real content) + IDENTITY/SOUL/MEMORY/HEARTBEAT + SOP/ index. PLUS the
    department-level IDENTITY/SOUL/TOOLS/how-to-use-this-department + sops/.

    Returns a summary dict.
    """
    dept_path = Path(dept_path)
    workspace_root = Path(workspace_root)
    summary = {"dept": dept_path.name, "roles_created": [], "dept_files": [],
               "sops_copied": 0, "scripts_copied": 0}

    if dry_run:
        print(f"[instantiate] DRY-RUN dept={dept_path.name} ({len(roles)} roles)")
    # Department-level scaffolding first.
    scaffolded = scaffold_department(dept_path, dept_slug, dry_run=dry_run)
    summary["dept_files"] = scaffolded["files"]
    summary["sops_copied"] = scaffolded["sops"]
    summary["scripts_copied"] = scaffolded.get("scripts", 0)

    for role in roles:
        if dry_run:
            print(f"  [DRY-RUN] would create "
                  f"{int(role.get('number', 0)):02d}-{role['slug']}/")
            summary["roles_created"].append(f"{int(role.get('number',0)):02d}-{role['slug']}")
            continue
        role_path = create_role_workspace(
            dept_path, role["name"], workspace_root, role_metadata=role)
        summary["roles_created"].append(role_path.name)

    # ROOT-CAUSE FIX: (re)generate ROSTER.md from the role folders we just
    # materialized, so the director's When-to Reference Map always matches the
    # actual roles on disk. Idempotent; runs on every --from-roster instantiation.
    roster_path = regenerate_department_roster(dept_path, dept_slug, dry_run=dry_run)
    if roster_path is not None:
        summary["roster_regenerated"] = str(roster_path)
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Create or augment role-level workspaces inside a department.")
    parser.add_argument("--dept-path", help="Path to the department workspace")
    parser.add_argument("--roles-json", help="JSON file with list of {name, type, is_ceo}")
    parser.add_argument("--workspace-root", help="Override workspace root (default: detect)")
    parser.add_argument("--augment", action="store_true",
                        help="Augment all existing role folders in --dept-path")
    # Dept-scoped, additive instantiation (defect #4). Produces a COMPLETE
    # department: all roster roles as NN-<slug>/ with library-filled how-to.md,
    # plus dept-level IDENTITY/SOUL/TOOLS/how-to-use-this-department + sops/.
    parser.add_argument("--from-roster",
                        help="Instantiate a complete department from a "
                             "suggested-roles roster .md into --dept-path "
                             "(additive; never overwrites siblings).")
    parser.add_argument("--dept-slug",
                        help="Department slug for --from-roster library lookup "
                             "(default: derived from --dept-path name).")
    parser.add_argument("--dry-run", action="store_true")
    # v6.6.0: --refresh-personas-only
    # Called by orchestrator.py Phase 6b after a new persona is added.
    # Re-writes governing-personas.md for all dept folders — cheap + idempotent.
    # Does NOT require --dept-path (operates on the full workspace).
    parser.add_argument(
        "--refresh-personas-only", action="store_true",
        help=(
            "Re-write governing-personas.md for every dept folder under "
            "--workspace-root (or auto-detected workspace root). "
            "No LLM calls, no role creation — idempotent refresh only. "
            "Called automatically by orchestrator.py Phase 6b after a new persona "
            "is added to persona-categories.json."
        ),
    )
    args = parser.parse_args()

    if args.workspace_root:
        workspace_root = Path(args.workspace_root)
    else:
        try:
            paths = get_openclaw_paths()
            workspace_root = Path(paths["workspace"])
        except Exception as e:
            print(f"ERROR: could not detect workspace root: {e}", file=sys.stderr)
            print("Pass --workspace-root explicitly.", file=sys.stderr)
            return 1

    # ── --refresh-personas-only: re-write governing-personas.md everywhere ──
    if args.refresh_personas_only:
        print(f"[create_role_workspaces] --refresh-personas-only: scanning {workspace_root}")
        n = refresh_all_governing_personas_md(workspace_root)
        print(f"[create_role_workspaces] Refreshed governing-personas.md in {n} dept folder(s).")
        return 0

    if not args.dept_path:
        parser.error("--dept-path is required (unless --refresh-personas-only is used)")
    dept_path = Path(args.dept_path)

    # ── --from-roster: complete, additive dept-scoped instantiation ──────────
    if args.from_roster:
        roster_path = Path(args.from_roster)
        if not roster_path.is_file():
            print(f"ERROR: roster not found: {roster_path}", file=sys.stderr)
            return 1
        dept_slug = args.dept_slug or dept_path.name.replace("-dept", "").strip().lower()
        roles = parse_roster(roster_path)
        if not roles:
            print(f"ERROR: no roles parsed from {roster_path}", file=sys.stderr)
            return 1
        summary = instantiate_department(dept_path, dept_slug, roles,
                                         workspace_root, dry_run=args.dry_run)
        print(f"\n[instantiate] dept={summary['dept']} "
              f"roles={len(summary['roles_created'])} "
              f"dept_files={len(summary['dept_files'])} "
              f"sops_copied={summary['sops_copied']}")
        # FIX 1 (2026-06-17): generate governing-personas.md for every
        # instantiated department — the --from-roster path skipped this step,
        # so incrementally-added departments (presentations, bugs, healer, etc.)
        # never received it. Idempotent; never overwrites IDENTITY/SOUL/MEMORY.
        if not args.dry_run:
            write_governing_personas_md(dept_path, dept_slug)
        return 0

    if args.augment:
        results = augment_all_existing_role_folders(dept_path, workspace_root,
                                                     dry_run=args.dry_run)
        print(f"\nAugmented {len(results)} role folders in {dept_path.name}")
        return 0

    if not args.roles_json:
        parser.error("--roles-json is required unless --augment or --refresh-personas-only is used")
    with open(args.roles_json, encoding="utf-8") as f:
        roles = json.load(f)

    created = build_all_roles_for_dept(dept_path, dept_path.name, roles, workspace_root)
    print(f"\nCreated {len(created)} role workspaces in {dept_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
