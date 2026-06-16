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
    company config + USER.md + role metadata. Tokens that have no source value
    are left in place (the sub-agent or runtime can fill later).
    """
    cfg = _load_company_config()

    # Pull token values from config — accept multiple key variants
    company_name = (cfg.get("companyName") or cfg.get("company_name")
                    or cfg.get("name") or "")
    company_industry = (cfg.get("companyIndustry") or cfg.get("industry")
                        or cfg.get("industryVertical") or "")
    yearly = (cfg.get("yearlyRevenueGoal") or cfg.get("yearly_revenue_goal")
              or cfg.get("revenueGoal") or cfg.get("yearlyGoal") or "")

    cascade = _compute_revenue_cascade(yearly)

    director = "Master Orchestrator" if is_ceo else f"Director of {dept_name}"

    tokens = {
        "COMPANY_NAME": company_name,
        "COMPANY_INDUSTRY": company_industry,
        "INDUSTRY_VERTICAL": company_industry,
        "ROLE_TITLE": role_name,
        "DEPARTMENT_NAME": dept_name,
        "DIRECTOR_OR_MASTER_ORCHESTRATOR": director,
        "ISO_DATE": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "GENERATION_DATE": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "ASSIGNED_PERSONA": "—",
        'CURRENTLY_ASSIGNED_PERSONA or "—"': "—",
        "full-time-permanent": "full-time-permanent",
        "on-call": "on-call",
    }
    tokens.update(cascade)

    out = content
    for key, val in tokens.items():
        if not val:
            continue
        out = out.replace("{{" + key + "}}", str(val))

    return out


def try_library_fill(role_name, dept_path, is_ceo):
    """
    Look up the library for a pre-written how-to.md, token-fill it, and return
    the filled content. Returns None if no library match (caller falls back
    to stub_how_to).
    """
    # WS-2: pass the RAW role name (not the naive slug) so the normalizer can
    # strip decorations / employment qualifiers and reach ~100% match coverage.
    dept_slug = dept_path.name.replace("-dept", "").strip().lower()

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

    # Stamp the front so reviewers can tell at a glance this came from library
    header = (f"<!-- Filled from role-library v{role_entry.get('version', '?')} on "
              f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')} -->\n")
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
    role_slug = slugify(role_name)
    role_path = Path(dept_path) / role_slug
    role_path.mkdir(parents=True, exist_ok=True)

    is_ceo = (role_metadata.get("is_ceo", False)
              or role_slug == "master-orchestrator")
    dept_name = Path(dept_path).name.replace("-dept", "").replace("-", " ").title()

    # Unique identity files
    (role_path / "IDENTITY.md").write_text(
        stub_identity(role_name, dept_name, is_ceo), encoding="utf-8")
    (role_path / "SOUL.md").write_text(
        stub_soul(role_name, dept_name, is_ceo), encoding="utf-8")
    (role_path / "MEMORY.md").write_text(
        stub_memory(role_name), encoding="utf-8")
    (role_path / "HEARTBEAT.md").write_text(
        stub_heartbeat(role_name, dept_name), encoding="utf-8")

    # how-to.md: library first, stub fallback
    filled = try_library_fill(role_name, Path(dept_path), is_ceo)
    if filled is not None:
        (role_path / "how-to.md").write_text(filled, encoding="utf-8")
        print(f"  [library-fill] {role_slug} ← templates/role-library/...")
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


def main():
    parser = argparse.ArgumentParser(
        description="Create or augment role-level workspaces inside a department.")
    parser.add_argument("--dept-path", help="Path to the department workspace")
    parser.add_argument("--roles-json", help="JSON file with list of {name, type, is_ceo}")
    parser.add_argument("--workspace-root", help="Override workspace root (default: detect)")
    parser.add_argument("--augment", action="store_true",
                        help="Augment all existing role folders in --dept-path")
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
