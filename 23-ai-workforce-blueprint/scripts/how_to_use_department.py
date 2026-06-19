#!/usr/bin/env python3
"""
how_to_use_department.py - render a "How to Use This Department" guide.

GOAL (operator's): every department gets a plain-language guide that also
explains how to use each SPECIALIST inside it, because most clients do not
realize these departments exist or know how to put them to work. The live
agent then ANSWERS owner questions ("how do I use [department]?" / "how do I
use [specialist]?") by reading the generated how-to-use-this-department.md and
responding from it (wired in master-orchestrator-dept/SOP-00-Owner-Task-Routing.md
and universal-sops/answering-how-to-use-questions.md).

This module is the SINGLE renderer used in two places:
  1. AUTHORING TIME - generate_how_to_use_docs.py writes one generic,
     fully-tokenized how-to-use-this-department.md into every department under
     templates/role-library/<dept>/ (committed to the repo). These carry
     {{TOKENS}} so they contain NO client names.
  2. BUILD TIME - build-workforce.py imports render_how_to_use() and writes a
     personalized copy into each client's departments/<dept>/ folder, filling
     the company tokens from the live build.

The specialist list is derived from the department's REAL roles so the guide
always matches the specialists that actually exist. Source of truth, in order:
  - an explicit list of role dicts passed in (build time, from
    parse_suggested_roles), OR
  - the department's suggested-roles markdown (authoring time).

Department metadata (display name, emoji, one-liner) comes from
department-naming-map.json (mandatory + vertical packs).

No model pins, no client names in the template output (tokens only), no
em dashes in the rendered prose.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)  # 23-ai-workforce-blueprint/
NAMING_MAP = os.path.join(SKILL_DIR, "department-naming-map.json")
SUGGESTED_ROLES_DIR = os.path.join(SKILL_DIR, "suggested-roles")
ROLE_LIBRARY_DIR = os.path.join(SKILL_DIR, "templates", "role-library")
ROLE_INDEX = os.path.join(ROLE_LIBRARY_DIR, "_index.json")
TEMPLATE_PATH = os.path.join(
    SKILL_DIR, "templates", "how-to-use-this-department.template.md"
)

# Roles that are real but should NOT be surfaced to the client as
# "specialists you can ask for" in this client-facing guide. Devil's Advocate
# is an internal challenge mechanism the client never meets; SOP-Writer, the
# Healer, the Deep Research role and the Brainstorming Buddy are internal
# hygiene/support roles. The QC Specialist IS mentioned (it is part of "what to
# expect back") but is not listed as a thing the owner asks for directly.
INTERNAL_ROLE_SLUGS = {
    "devils-advocate",
    "sop-writer",
    "00-start-here",
}
INTERNAL_ROLE_NAME_HINTS = (
    "devil's advocate",
    "devils advocate",
    "sop-writer",
    "sop writer",
    "healer",
    "start here",
    # Support/hygiene roles the client does not ask for directly. They run
    # behind the scenes for the department; surfacing them as "specialists you
    # can use" would mislead the owner.
    "deep research specialist",
    "deep research role",
    "brainstorming buddy",
)


def _sanitize(text):
    """Strip characters the fleet style bans from shipped prose.

    The source role files and suggested-roles markdown contain em dashes and
    en dashes ("Deep Research Specialist - Sales", "audience - the right
    audience"). The operator's house style forbids em dashes in prose, so every
    string that flows into a generated guide is run through this. Em/en dashes
    become " - " (a spaced hyphen), non-breaking spaces become regular spaces,
    and smart quotes are normalized. Idempotent.
    """
    if not text:
        return text
    replacements = {
        "—": " - ",   # em dash
        "–": " - ",   # en dash
        "‘": "'",      # left single quote
        "’": "'",      # right single quote
        "“": '"',      # left double quote
        "”": '"',      # right double quote
        " ": " ",      # non-breaking space
        "…": "...",   # ellipsis
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    # Collapse any doubled spaces the dash replacement may have introduced.
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


# Characters the fleet style bans, mapped to their plain-ASCII replacements.
# Used by the block sanitizer (which must NOT touch newlines / indentation).
_BLOCK_REPLACEMENTS = {
    "—": " - ",
    "–": " - ",
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    " ": " ",
    "…": "...",
}

# A literal "--" used as a dash in source prose. Matches EXACTLY two hyphens not
# adjacent to a third, so it never touches markdown "---" rules or "| --- |"
# table separators (3+ hyphens are left intact).
_DOUBLE_HYPHEN_RE = re.compile(r"(?<!-)--(?!-)")


def _sanitize_block(text):
    """Character-only sanitize for a full markdown document: replaces banned
    punctuation but preserves all newlines and indentation (unlike _sanitize,
    which is for single inline strings). Markdown structure ('---' rules and
    '| --- |' separators) is preserved."""
    for bad, good in _BLOCK_REPLACEMENTS.items():
        text = text.replace(bad, good)
    text = _DOUBLE_HYPHEN_RE.sub(" - ", text)
    return text


def _load_naming_map():
    try:
        with open(NAMING_MAP) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _dept_metadata():
    """Return {dept_id -> {display_name, emoji, one_liner, director_title,
    suggested_roles_file}} from the naming map (mandatory + vertical packs).

    Both the dict-style mandatory entries and the list-style vertical-pack
    auto_add_departments entries are ingested so every canonical department
    resolves to a display name + emoji + one-liner.
    """
    data = _load_naming_map()
    meta = {}

    def _ingest_dict(node):
        if not isinstance(node, dict):
            return
        for k, v in node.items():
            if isinstance(v, dict) and v.get("display_name"):
                meta[k] = {
                    "display_name": v.get("display_name", k),
                    "emoji": v.get("emoji", ""),
                    "one_liner": v.get("one_liner", ""),
                    "director_title": v.get("director_title", ""),
                    "suggested_roles_file": v.get("suggested_roles_file", ""),
                }
            elif isinstance(v, dict):
                _ingest_dict(v)

    _ingest_dict(data.get("mandatory", {}))
    _ingest_dict(data.get("vertical_packs", {}))

    # Vertical-pack departments are a LIST under auto_add_departments.
    for pack in (data.get("vertical_packs", {}) or {}).values():
        if not isinstance(pack, dict):
            continue
        for dept in pack.get("auto_add_departments", []) or []:
            if isinstance(dept, dict) and dept.get("id"):
                meta.setdefault(
                    dept["id"],
                    {
                        "display_name": dept.get("name", dept["id"]),
                        "emoji": dept.get("emoji", ""),
                        "one_liner": dept.get("one_liner", ""),
                        "director_title": dept.get("director_title", ""),
                        "suggested_roles_file": dept.get("base_suggested_roles", ""),
                    },
                )
    return meta


# Legacy folder-slug -> naming-map-id aliases, so a role-library folder named
# differently from the canonical id (e.g. "billing" folder vs "billing-finance"
# map id, "legal-compliance" folder vs "legal" map id) still resolves metadata.
FOLDER_ALIAS_TO_MAP_ID = {
    "billing": "billing-finance",
    "legal-compliance": "legal",
}


def resolve_meta(dept_folder, meta_table=None):
    """Resolve display metadata for a role-library folder slug.

    Falls back to a humanized folder name + a generic one-liner so the guide is
    never empty even for a department the naming map does not list.
    """
    meta_table = meta_table or _dept_metadata()
    m = meta_table.get(dept_folder)
    if not m:
        alias = FOLDER_ALIAS_TO_MAP_ID.get(dept_folder)
        if alias:
            m = meta_table.get(alias)
    if not m:
        human = dept_folder.replace("-", " ").replace("_", " ").title()
        m = {
            "display_name": human,
            "emoji": "",
            "one_liner": f"Work owned by the {human} department",
            "director_title": f"Director of {human}",
            "suggested_roles_file": "",
        }
    return dict(m)


# ---------------------------------------------------------------------------
# Specialist parsing (authoring time, from suggested-roles markdown)
# ---------------------------------------------------------------------------

def _parse_suggested_roles_md(path):
    """Parse a suggested-roles markdown file into role dicts:
      {number, name, description, is_head, is_qc}
    Mirrors build-workforce.parse_suggested_roles enough for the guide.
    """
    roles = []
    try:
        with open(path) as f:
            content = f.read()
    except OSError:
        return roles

    current = None
    for line in content.split("\n"):
        if line.startswith("### ") and not line.startswith("### Quality Control"):
            if current:
                roles.append(current)
            header = line[4:].strip()
            parts = header.split(". ", 1)
            try:
                number = int(parts[0])
                name = parts[1] if len(parts) > 1 else header
            except ValueError:
                number = len(roles)
                name = header
            low = name.lower()
            current = {
                "number": number,
                "name": name.strip(),
                "description": "",
                "is_head": number == 0,
                "is_qc": "quality control" in low or "qc " in low or low.startswith("qc"),
            }
        elif line.startswith("### Quality Control Agent"):
            if current:
                roles.append(current)
            current = {
                "number": 99,
                "name": "Quality Control Agent",
                "description": "",
                "is_head": False,
                "is_qc": True,
            }
        elif current is not None and line.startswith("**What it does:**"):
            current["description"] = line.replace("**What it does:**", "").strip()
    if current:
        roles.append(current)
    return roles


def _dept_purpose_from_md(path):
    """Pull the department purpose paragraph from a suggested-roles file.

    Accepts both header conventions seen across the suggested-roles files:
    '## Department Purpose' and a '**Purpose:**' front-matter line.
    """
    try:
        with open(path) as f:
            content = f.read()
    except OSError:
        return ""
    m = re.search(r"##\s*Department Purpose\s*\n+(.+?)(?:\n##|\n---|\Z)", content, re.S)
    if m:
        return _sanitize(" ".join(m.group(1).split()).strip())
    m = re.search(r"^\*\*Purpose:\*\*\s*(.+)$", content, re.M)
    if m:
        return _sanitize(m.group(1).strip())
    return ""


# ---------------------------------------------------------------------------
# Index-based role loading (the uniform, authoritative source)
# ---------------------------------------------------------------------------

def _strip_tokens(text):
    """Remove {{TOKENS}} from a sentence pulled from a role file so the guide
    never shows raw template placeholders in a specialist description.

    Note: we deliberately do NOT try to repair a dangling 'at .' left by a
    stripped {{COMPANY_NAME}} into a real phrase. A sentence that degenerates to
    "You are the X at ." is the boilerplate framing line, and
    _who_you_are_first_sentence is built to SKIP it and use the next sentence
    (the actual job description) instead.
    """
    text = re.sub(r"\{\{[^}]*\}\}", "", text)
    # Repair fragments left by a stripped {{COMPANY_NAME}}:
    #   "for {{COMPANY_NAME}}'s X" -> "for 's X"  -> "for the company's X"
    #   "of {{COMPANY_NAME}}, the" -> "of , the"  -> "of the company, the"
    #   "at {{COMPANY_NAME}}."     -> "at ."       (left for sentence-skip)
    text = re.sub(r"(\bfor|\bof|\bat|\bwith|\binside)\s+'s\b", r"\1 the company's", text)
    text = re.sub(r"\s+'s\b", " the company's", text)
    text = re.sub(r"(\bfor|\bof|\bat|\bwith|\binside)\s+,", r"\1 the company,", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _who_you_are_first_sentence(role_md_path):
    """A clean one-line description from a role file's '### Who You Are' lead,
    token-stripped and sanitized, used as the specialist's 'what it is for' line.

    Role file leads almost always open with boilerplate framing of the form
    "You are the <Role> for <Company>." whose only content after token-stripping
    is the role name. We therefore prefer the SECOND sentence (the actual job
    description) and fall back to the first only if there is no second.
    """
    try:
        with open(role_md_path) as f:
            content = f.read()
    except OSError:
        return ""
    m = re.search(r"###\s*Who You Are\s*\n+(.+?)(?:\n###|\n##|\n---|\Z)", content, re.S)
    para = m.group(1) if m else ""
    if not para:
        m2 = re.search(
            r"Role Identity\s*\n+(?:###[^\n]*\n+)?(.+?)(?:\n###|\n##|\n---|\Z)",
            content, re.S)
        para = m2.group(1) if m2 else ""
    para = _sanitize(_strip_tokens(" ".join(para.split())))
    if not para:
        return ""

    # Split into sentences; pick the first one that actually carries content
    # (not just the "You are the X" framing) and reads as a description.
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", para) if s.strip()]
    for s in sentences:
        cleaned = re.sub(r"^You are (?:the |a |an )?", "", s).strip()
        # Skip a degenerate framing sentence left after the company token was
        # stripped, e.g. "Product Manager at ." / "Launch Manager for .".
        if re.search(r"\b(for|at|in|of|with)\s*\.?\s*$", cleaned):
            continue
        if len(cleaned.split()) < 5:
            continue
        # Capitalize the first letter so a mid-paragraph second sentence reads
        # as a proper standalone description.
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:]
        return _first_sentence(cleaned, cap=180)
    # Nothing usable.
    return ""


# Common acronyms / unit tokens the _index.json title-casing mangles. The index
# Title-Cases the slug ("sdr-..." -> "Sdr ...", "crm-..." -> "Crm ..."), so these
# read wrong in a client-facing guide. Whole-word, case-insensitive replacements.
_TITLE_ACRONYMS = {
    "Sdr": "SDR", "Crm": "CRM", "Qc": "QC", "Qa": "QA", "Seo": "SEO",
    "Cro": "CRO", "Aso": "ASO", "A11y": "A11Y", "Pwa": "PWA", "Ux": "UX",
    "Ui": "UI", "Pr": "PR", "Sms": "SMS", "Dm": "DM", "Sfx": "SFX",
    "Vsl": "VSL", "Ar": "AR", "Ai": "AI", "Mcp": "MCP", "Cfo": "CFO",
    "Cmo": "CMO", "Cto": "CTO", "Ip": "IP", "Pwa": "PWA", "Fpanda": "FP&A",
    "Op-ed": "Op-Ed", "2d": "2D", "3d": "3D", "Tiktok": "TikTok",
    "Linkedin": "LinkedIn", "Youtube": "YouTube", "Whatsapp": "WhatsApp",
    "Wordpress": "WordPress", "Bluesky": "Bluesky", "Ghl": "GHL",
}


def _humanize_role_title(title):
    """Fix the common acronyms the slug-derived index title mangles so the
    client-facing specialist name reads naturally. Whole-word only, so it never
    rewrites a substring inside a longer word."""
    def repl(m):
        return _TITLE_ACRONYMS.get(m.group(0), m.group(0))
    pattern = r"\b(" + "|".join(re.escape(k) for k in _TITLE_ACRONYMS) + r")\b"
    return re.sub(pattern, repl, title)


def _match_key(name):
    """Normalize a role name to a comparison key, so the index title
    ("SDR Sales Development Rep") and the suggested-roles header
    ("SDR (Sales Development Rep)") collapse to the SAME key. We KEEP the
    parenthetical content (just drop the brackets) so the two forms agree, then
    drop remaining punctuation, lowercase, and collapse spaces. Words are sorted
    so "Account Executive (Full-Cycle)" and "Account Executive Full Cycle" match
    regardless of order/hyphenation."""
    n = (name or "").replace("(", " ").replace(")", " ")   # keep inner words
    n = re.sub(r"[^a-z0-9 ]", " ", n.lower())               # drop punctuation
    words = re.sub(r"\s+", " ", n).strip().split()
    return " ".join(sorted(words))


def _roles_from_index(dept_folder, meta):
    """Build the role list for a department from _index.json (uniform across all
    departments), dedup by slug, classify head/QC/internal, and enrich each
    specialist's description from its role file's 'Who You Are' lead.

    Returns a list of role dicts shaped like _parse_suggested_roles_md output.
    """
    try:
        with open(ROLE_INDEX) as f:
            idx = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []

    director_titles = {(meta.get("director_title") or "").lower()}
    seen = set()
    roles = []
    for r in idx.get("roles", []):
        if r.get("dept") != dept_folder:
            continue
        slug = r.get("slug", "")
        # Skip stale "ROLE--<name>" duplicate entries in the index: these are
        # uppercase-prefixed copies of the real role slug (a known graphics-dept
        # library artifact) and would double-list every specialist.
        if slug.lower().startswith("role--") or slug.startswith("ROLE"):
            continue
        if slug in seen:
            continue
        seen.add(slug)
        title = r.get("title", slug.replace("-", " ").title())
        # Drop a leading "Role " the index sometimes prepends to a title.
        title = re.sub(r"^Role\s+", "", title)
        title = _humanize_role_title(title)
        rtype = (r.get("role_type") or "").lower()
        low = title.lower()
        is_head = (
            rtype in ("director", "leadership")
            or low.startswith("director of")
            or low.startswith("head of")
            or low.startswith("chief")
            or low in director_titles
        )
        is_qc = (
            rtype == "qc"
            or "qc specialist" in low
            or "quality control" in low
            or low.startswith("qc ")
        )
        desc = ""
        path = r.get("path", "")
        if path:
            full = os.path.join(SKILL_DIR, path)
            desc = _who_you_are_first_sentence(full)
            # Cross-contamination guard: some newer role files were authored by
            # copy-pasting another department's template and the body still
            # names the WRONG department (a real data defect in the library).
            # If the extracted description names a different department's role
            # than this one, discard it rather than mislead the owner.
            if desc and _names_other_department(desc, dept_folder, meta):
                desc = ""
        roles.append({
            "number": 0 if is_head else len(roles) + 1,
            "name": title,
            "description": desc,
            "is_head": is_head,
            "is_qc": is_qc,
        })
    return roles


# Department display names keyed by folder, for the cross-contamination guard.
def _all_dept_display_names(meta_table):
    names = {}
    for did, m in (meta_table or {}).items():
        if isinstance(m, dict) and m.get("display_name"):
            names[did] = m["display_name"].lower()
    return names


# Distinctive multi-word department topics that, if they appear near the START
# of a specialist description for a DIFFERENT department, signal a stale
# copy-pasted role body (a real data defect in the library). Single-word topics
# (e.g. "sales", "research") are intentionally excluded - they appear
# legitimately across many descriptions.
_OTHER_DEPT_TOPIC_PHRASES = {
    "account management",
    "client experience",
    "customer support",
    "paid advertisement",
    "social media",
    "legal and compliance",
    "product production",
    "launch operations",
    "scheduling and dispatch",
    "logistics and fulfillment",
    "founding member",
}


def _names_other_department(desc, dept_folder, meta):
    """True if `desc` references a department clearly different from this one.

    Catches stale copy-pasted role bodies (e.g. a Launch Operations role whose
    text says "every account management decision"). Two signals:
      1. the explicit "for the <Other> department" phrasing, and
      2. a distinctive other-department topic phrase appearing in the first
         ~120 characters (where the role's own subject is stated).
    Conservative on single words so a legitimate passing mention is not lost.
    """
    this_name = (meta.get("display_name") or dept_folder).lower()
    low = desc.lower()
    for m in re.finditer(r"for the ([a-z][a-z &/-]+?) department", low):
        other = m.group(1).strip()
        if other and other not in this_name and this_name not in other:
            return True
    head = low[:120]
    for phrase in _OTHER_DEPT_TOPIC_PHRASES:
        if phrase in head and phrase not in this_name and this_name not in phrase:
            return True
    return False


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _is_internal(role):
    slug = role.get("name", "").strip().lower().replace(" ", "-")
    if slug in INTERNAL_ROLE_SLUGS:
        return True
    name_low = role.get("name", "").lower()
    return any(h in name_low for h in INTERNAL_ROLE_NAME_HINTS)


def _client_specialists(roles):
    """Filter to the specialists a client would actually ask for: drop the head,
    drop QC and internal-only roles. Keep order (by role number)."""
    out = []
    for r in sorted(roles, key=lambda x: x.get("number", 999)):
        if r.get("is_head"):
            continue
        if r.get("is_qc"):
            continue
        if _is_internal(r):
            continue
        out.append(r)
    return out


# Connector / function words a trimmed phrase must NOT end on, or it reads as a
# cut-off fragment ("...the specialist who takes over qualified, demo'd, and.").
_DANGLING_TAIL_WORDS = {
    "a", "an", "the", "of", "for", "and", "or", "to", "with", "into", "in", "on",
    "by", "from", "as", "at", "that", "who", "which", "every", "their", "its",
    "this", "these", "those", "your", "our", "is", "are", "be", "but", "so",
}


def _first_sentence(text, cap=160):
    """A clean, COMPLETE-reading first phrase of `text`, capped at `cap` chars.

    Never cuts mid-word. When the first sentence is longer than `cap`, it trims
    to the last clause boundary (comma) that fits, else to the last whole word,
    and then drops any trailing connector/function words so the line never ends
    on a dangling fragment like "... the" or "... and". Always ends in a period.
    """
    t = (text or "").replace("\n", " ").strip()
    if not t:
        return ""
    first = t.split(". ")[0].strip()
    # Also stop at the first colon - role files often pack a long clause list
    # after a colon that reads as an internal spec, not an owner-facing summary.
    first = first.split(": ")[0].strip()
    if len(first) > cap:
        cut = first[:cap]
        # Prefer the last clause boundary (comma) within the cap; it reads as a
        # complete thought far more often than an arbitrary word boundary.
        if "," in cut and cut.rfind(",") >= cap // 2:
            cut = cut[:cut.rfind(",")]
        elif " " in cut:
            cut = cut[:cut.rstrip().rfind(" ")]
        first = cut
    first = first.rstrip(" ,;-")
    # Drop trailing connector/function words so we never end on a fragment.
    words = first.split()
    while words and re.sub(r"[^a-z]", "", words[-1].lower()) in _DANGLING_TAIL_WORDS:
        words.pop()
    first = " ".join(words).rstrip(" ,;-")
    if not first:
        return ""
    if not first.endswith((".", "!", "?")):
        first += "."
    return first


def _example_request(role):
    """A plain-language example request for this specialist, derived from its
    'what it does' description. Generic and tokenized-safe (no client names).

    The description is used as a label after a colon (NOT conjugated against a
    verb), so phrasings like "Top-of-funnel outreach." or acronyms like "CRM"
    stay grammatical and correctly cased.
    """
    desc = _first_sentence(role.get("description", ""), cap=90)
    name = role.get("name", "this specialist")
    if not desc:
        return f"\"Have the {name} take on a task in its area.\""
    return f"\"Have the {name} take this on: {desc}\""


def _humanize_one_liner(meta, purpose):
    one = (meta.get("one_liner") or "").strip()
    if one:
        return one[0].upper() + one[1:] if one else one
    fs = _first_sentence(purpose)
    return fs or f"Owns the {meta.get('display_name', 'department')} work for your business."


def render_how_to_use(dept_folder, roles=None, tokens=None, meta_table=None):
    """Render the guide markdown for one department.

    Args:
      dept_folder: role-library folder slug (e.g. "sales").
      roles: optional list of role dicts ({number,name,description,is_head,
             is_qc}). If None, parsed from the department's suggested-roles file.
      tokens: optional overrides for company tokens. When None (authoring time)
             the company fields stay as {{TOKENS}} so the committed artifact
             carries NO client names.
      meta_table: optional pre-loaded naming-map metadata table.

    Returns the rendered markdown string.
    """
    tokens = tokens or {}
    meta = resolve_meta(dept_folder, meta_table)
    meta["display_name"] = _sanitize(meta.get("display_name", dept_folder))
    meta["one_liner"] = _sanitize(meta.get("one_liner", ""))

    sr_file = meta.get("suggested_roles_file") or f"{dept_folder}-suggested-roles.md"
    sr_path = os.path.join(SUGGESTED_ROLES_DIR, sr_file)
    purpose = _dept_purpose_from_md(sr_path)

    # Role source of truth, in order:
    #   1. an explicit roles list passed in (build time, from
    #      build-workforce.parse_suggested_roles), used verbatim;
    #   2. otherwise _index.json (authoring time) - uniform across ALL 34
    #      departments, enriched per-specialist from the role file's lead, then
    #      enriched again from the suggested-roles "What it does" line when the
    #      department has a suggested-roles file in the legacy "### N." format.
    if roles is None:
        roles = _roles_from_index(dept_folder, meta)
        # Enrich from the suggested-roles "What it does" line when that file
        # genuinely belongs to THIS department (its role names match the index
        # roster). Those lines are short, plain TASK descriptions ("Top-of-funnel
        # outreach. Cold email, cold call.") and read far better in an owner guide
        # than a role file's "Who You Are" IDENTITY sentence, so when one matches
        # we PREFER it. We only trust the file when enough names match, so a
        # borrowed "base" roles file (e.g. logistics pointing at customer-support)
        # contributes nothing and never surfaces the wrong department's tasks.
        sr_roles = _parse_suggested_roles_md(sr_path)
        if sr_roles:
            sr_desc = {}
            for sr in sr_roles:
                if sr.get("description"):
                    sr_desc[_match_key(sr["name"])] = _sanitize(sr["description"])
            index_keys = {_match_key(r["name"]) for r in roles}
            overlap = sum(1 for k in sr_desc if k in index_keys)
            file_belongs = overlap >= max(2, len(index_keys) // 2)
            if file_belongs:
                for r in roles:
                    k = _match_key(r["name"])
                    if k in sr_desc:
                        r["description"] = sr_desc[k]  # prefer the clean task line
        # If the index yielded nothing (e.g. a brand-new dept not yet indexed),
        # fall back to the suggested-roles parse so the guide is never empty.
        if not roles and sr_roles:
            roles = sr_roles

    # Sanitize every role name + description that flows into the guide.
    for r in roles:
        r["name"] = _sanitize(r.get("name", ""))
        r["description"] = _sanitize(r.get("description", ""))

    head_name = _sanitize(
        meta.get("director_title") or f"Director of {meta['display_name']}"
    )
    specialists = _client_specialists(roles)

    # Specialist example used in the prose tokens (first client specialist).
    spec_example = specialists[0]["name"] if specialists else f"{meta['display_name']} specialist"
    # A short, grammatical ask for "Get the <specialist> to ___". A role
    # description is an identity/spec, not an imperative, so splicing it here
    # reads wrong. Use a clean generic ask scoped to the department instead.
    spec_request_example = f"take on a {meta['display_name'].lower()} task for you"

    # --- Section 2: when-to-use bullets, from specialist descriptions ---------
    # Cap at 6 bullets so even a 40-role department stays scannable.
    when_bullets = []
    for r in specialists[:6]:
        line = _first_sentence(r.get("description", ""), cap=110)
        if line:
            when_bullets.append(f"- {line}")
    if not when_bullets:
        when_bullets = [f"- Anything in the {meta['display_name']} area of your business."]
    when_block = "\n".join(when_bullets)

    # --- Section 4: specialist table + detail blocks --------------------------
    if specialists:
        table_rows = ["| Specialist | What it is for |", "| --- | --- |"]
        detail_blocks = []
        for r in specialists:
            what = _first_sentence(r.get("description", ""), cap=120) or f"Owns the {r['name']} work."
            table_rows.append(f"| **{r['name']}** | {what} |")
            detail_blocks.append(
                f"**{r['name']}**\n\n"
                f"- *What it is for:* {what}\n"
                f"- *Example request:* {_example_request(r)}\n"
            )
        spec_table = "\n".join(table_rows)
        spec_details = "\n".join(detail_blocks)
    else:
        spec_table = (
            "| Specialist | What it is for |\n| --- | --- |\n"
            f"| _(specialists are assigned based on your workload)_ | The "
            f"{head_name} staffs this department as work comes in. |"
        )
        spec_details = (
            f"The {head_name} staffs specialists in this department as your "
            f"workload requires. Ask the department for what you need and the "
            f"right specialist is assigned for you.\n"
        )

    # A clean noun-phrase ask for the prose examples. A role description is an
    # identity sentence, not an imperative, so splicing it after "I need ___" or
    # "handle ___" reads wrong. Use a short, grammatical department-scoped phrase
    # that reads correctly after BOTH "I need help with ___" and "handle ___" in
    # Section 3 of the template.
    plain_request = f"something from the {meta['display_name'].lower()} team"

    # --- token table ----------------------------------------------------------
    fill = {
        "DEPARTMENT_NAME": meta["display_name"],
        "DEPARTMENT_EMOJI": meta.get("emoji", ""),
        "DEPARTMENT_HEAD": head_name,
        "DEPARTMENT_SLUG": dept_folder,
        "DEPARTMENT_PLAIN_LANGUAGE_PURPOSE": purpose
        or f"The {meta['display_name']} department owns all "
           f"{meta['display_name'].lower()} work for your business.",
        "DEPARTMENT_ONE_LINER": _humanize_one_liner(meta, purpose),
        "DEPARTMENT_WHEN_TO_USE_BULLETS": when_block,
        "SPECIALIST_TABLE": spec_table,
        "SPECIALIST_DETAIL_BLOCKS": spec_details,
        "SPECIALIST_EXAMPLE": spec_example,
        "SPECIALIST_REQUEST_EXAMPLE": spec_request_example,
        "PLAIN_REQUEST_EXAMPLE": plain_request,
        "DEPARTMENT_TYPICAL_DELIVERABLES": (
            f"the finished {meta['display_name'].lower()} work you asked for"
        ),
        "DEPARTMENT_HANDOFF_NOTES": "",
        # Company tokens: left as {{TOKENS}} at authoring time (no client names);
        # filled by build-workforce.py at build time.
        "COMPANY_NAME": tokens.get("COMPANY_NAME", "{{COMPANY_NAME}}"),
        "GENERATION_DATE": tokens.get("GENERATION_DATE", "{{GENERATION_DATE}}"),
    }

    with open(TEMPLATE_PATH) as f:
        tpl = f.read()

    out = tpl
    for k, v in fill.items():
        out = out.replace("{{" + k + "}}", str(v))

    # Final safety net: no em/en dashes or smart punctuation survive into the
    # shipped guide, regardless of what slipped through upstream. The two
    # company tokens are restored afterward so authoring-time output keeps them.
    out = out.replace("{{COMPANY_NAME}}", "\x00CN\x00").replace(
        "{{GENERATION_DATE}}", "\x00GD\x00")
    out = _sanitize_block(out)
    out = out.replace("\x00CN\x00", fill["COMPANY_NAME"]).replace(
        "\x00GD\x00", fill["GENERATION_DATE"])

    # Department-specific appendix sections. These carry rules that are
    # enforced at the BUILD pipeline level (AUTO-FAIL gates) and must be
    # surfaced in the owner-facing guide so the client understands them.
    # Written using plain ASCII dashes (never em/en dashes) to satisfy the
    # fleet em-dash ban. New entries follow the same pattern.
    appendix = _DEPT_APPENDIX.get(dept_folder, "")
    if appendix:
        out = out.rstrip("\n") + "\n\n" + appendix.strip("\n") + "\n"

    return out


# Department-specific appendix blocks. Each value is appended verbatim after
# the generated guide body (after the _sanitize_block pass, so they must
# already be em-dash-free). Keep entries sorted by dept_folder key.
_DEPT_APPENDIX = {
    "presentations": """\
---

## AF-DARK-SLIDE - No Dark Slides (AUTO-FAIL)

Slides MUST use LIGHT / bright backgrounds by DEFAULT. DARK or \
black-background slides are NOT ALLOWED unless the CLIENT EXPLICITLY requests \
a dark theme via the intake flag `client_dark_theme: true`. Light is the \
default; dark is opt-in by client request only.

- DEFAULT: Light / bright background slides
- ALLOWED dark: Only when `client_dark_theme: true` is set in \
working/copy/intake.json
- AUTO-FAIL: Any dark/black/near-black default background without \
`client_dark_theme: true`

**To enable a dark theme:** during onboarding, explicitly tell the Director \
of Presentations you want dark slides. The Director will record \
`client_dark_theme: true` in your intake.json. Without this explicit request, \
all slides default to light/bright backgrounds and any dark background \
specification is an AUTO-FAIL blocked by the build pipeline.
""",
}


if __name__ == "__main__":
    # CLI: render one department to stdout (for spot-checking).
    if len(sys.argv) < 2:
        print("usage: how_to_use_department.py <dept-folder-slug>", file=sys.stderr)
        sys.exit(2)
    sys.stdout.write(render_how_to_use(sys.argv[1]))
