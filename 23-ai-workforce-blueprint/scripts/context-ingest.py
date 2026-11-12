#!/usr/bin/env python3
"""
context-ingest.py — Skill 23 v12.3.4: Interview Context Ingestion Pre-Pass.

Assembles a CONTEXT DIGEST from all available client sources before the AI
Workforce Blueprint interview begins. For each interview theme (Phase 1-6 topics
+ branding question ids), emits a per-theme record so the interviewing agent can
decide how to open the question.

EVERY THEME IS UNKNOWN. A keyword hit in a source is a HINT for the interviewer's
background only: never shown to the owner as a fact, never a reason to skip a
question. Facts come from structured fields ALONE, through known_facts()
(company-config.json and answers the gate already accepted), and even those are
only ever offered to the owner to confirm.

Outputs:
  - [slug]/interview-context-map.json   (machine: per-theme status/hint)
  - [workspace]/company-discovery/interview-known.json   ({knownKey:{value,source}})
  - human digest printed to stdout (--human) or full JSON (--json)

Sources ingested (in priority order):
  1. [WORKSPACE_ROOT]/IDENTITY.md
  2. [WORKSPACE_ROOT]/MEMORY.md
  3. [WORKSPACE_ROOT]/AGENTS.md
  4. [WORKSPACE_ROOT]/TOOLS.md
  5. [WORKSPACE_ROOT]/USER.md
  6. [WORKSPACE_ROOT]/SOUL.md
  7. [ZHC]/[slug]/pre-interview-research.md  (Phase 0 findings)
  8. [ZHC]/[slug]/software-stack-capabilities.md  (Phase 3.5)
  9. [MASTER_FILES]/company-discovery/workforce-interview-answers.md  (prior run)
 10. [ZHC]/[slug]/provided-context-manifest.md  (raw links from Phase 0 asset drop)

That list is read for HINTS only. AGENTS.md and TOOLS.md (NEVER_A_FACT_SOURCE) are
skipped even for hints: they describe the agent fleet and its scripts, not the
owner's business, and they mention "client", "who" and "$" constantly.

NO-FABRICATION: this script reads and reports; it NEVER writes answers.
It NEVER opens workforce-interview-answers.md for writing. The answer record
(workforce-interview-answers.md) is written EXCLUSIVELY by log_answer() in
build-workforce.py after a live client turn. Two files, two purposes:
this context map informs WHICH/HOW to ask; the answers file records ONLY
client-stated answers. This invariant is enforced by qc-interview-completion.py
check #5 (unconfirmed-context-as-answer → exit 3 HARD FAIL).

v12.3.4 / PRD-2.16
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


# ── Path resolution ───────────────────────────────────────────────────────────

def _resolve_openclaw_root() -> Path:
    """Resolve OpenClaw root: VPS=/data/.openclaw, Mac=$HOME/.openclaw."""
    vps = Path("/data/.openclaw")
    if vps.is_dir():
        return vps
    mac = Path(os.environ.get("HOME", "~")).expanduser() / ".openclaw"
    if mac.is_dir():
        return mac
    return mac


def _resolve_workspace_root(openclaw_root: Path) -> Path:
    return openclaw_root / "workspace"


def _resolve_master_files(workspace_root: Path) -> Path:
    """
    Locate master files folder. Mirrors find_master_files_folder() in
    build-workforce.py: tries env var first, then canonical paths.
    """
    env_override = os.environ.get("MASTER_FILES_DIR")
    if env_override:
        return Path(env_override)
    # VPS canonical
    vps_path = Path("/data/openclaw-master-files")
    if vps_path.is_dir():
        return vps_path
    # Mac canonical
    mac_path = Path(os.environ.get("HOME", "~")).expanduser() / "Downloads" / "openclaw-master-files"
    if mac_path.is_dir():
        return mac_path
    # Fallback: workspace parent
    return workspace_root.parent / "openclaw-master-files"


def _resolve_zhc_root(master_files: Path) -> Path:
    return master_files / "zero-human-company"


# ── Interview themes registry ─────────────────────────────────────────────────

# Per-theme config: id, phase, description, and hint-keywords to search for in context.
# These map to the Phase 1-6 THEMES and branding-questions.json ids in INSTRUCTIONS.md.
INTERVIEW_THEMES = [
    # Phase 1 — Identity & Behavior
    {"id": "hard_conversations",     "phase": 1, "label": "Conflict / hard conversation style",
     "keywords": ["conflict", "confrontation", "hard conversation", "difficult"]},
    {"id": "failure_response",       "phase": 1, "label": "Failure / mistake response",
     "keywords": ["failure", "mistake", "wrong", "setback", "failed"]},
    {"id": "money_decisions",        "phase": 1, "label": "Money decision criteria",
     "keywords": ["invest", "budget", "money", "financial", "spend", "revenue"]},
    {"id": "voice_style",            "phase": 1, "label": "Voice & communication style",
     "keywords": ["voice", "tone", "style", "describe", "barbecue", "plain English"]},
    {"id": "anti_mentors",           "phase": 1, "label": "Mentor / anti-mentor influences",
     "keywords": ["mentor", "influence", "inspired", "reject", "disagree"]},

    # Phase 2 — Mission, Purpose, Vision, Revenue
    {"id": "vision_5yr",             "phase": 2, "label": "5-year vision",
     "keywords": ["5 year", "five year", "vision", "future", "long term", "goal"]},
    {"id": "winning_12mo",           "phase": 2, "label": "What 'winning' looks like in 12 months",
     "keywords": ["12 month", "one year", "winning", "success", "milestone"]},
    {"id": "secret_ambition",        "phase": 2, "label": "Secret ambition",
     "keywords": ["ambition", "dream", "secret", "aspire", "become"]},
    {"id": "world_know_you",         "phase": 2, "label": "What world should know about you",
     "keywords": ["know about me", "personal brand", "known for"]},
    {"id": "world_know_company",     "phase": 2, "label": "What world should know about company",
     "keywords": ["know about", "company reputation", "brand"]},
    {"id": "revenue_goals",          "phase": 2, "label": "Revenue goals (safe + stretch)",
     "keywords": ["revenue", "income", "monthly", "annual", "MRR", "ARR", "goal", "$"]},

    # Phase 3 — Brand, Customers, Fears, Frustrations
    {"id": "ideal_customer",         "phase": 3, "label": "Ideal customer (who + why)",
     "keywords": ["customer", "client", "serve", "audience", "niche", "who"]},
    {"id": "unique_differentiator",  "phase": 3, "label": "Why customers choose you",
     "keywords": ["different", "unique", "why me", "competitor", "differentiator"]},
    {"id": "customer_feeling",       "phase": 3, "label": "Feeling customers leave with",
     "keywords": ["customer feel", "client feel", "experience", "transformation"]},
    {"id": "brand_evokes",           "phase": 3, "label": "Brand feeling evoked",
     "keywords": ["brand feel", "brand evoke", "brand convey"]},
    {"id": "brand_descriptors",      "phase": 3, "label": "Words customers use to describe brand",
     "keywords": ["describe", "words", "brand descriptor", "testimonial"]},
    {"id": "brand_voice",            "phase": 3, "label": "Brand voice",
     "keywords": ["voice", "tone", "brand voice", "language", "speak"]},
    {"id": "brand_primary_color",    "phase": 3, "label": "Primary brand color",
     "keywords": ["color", "colour", "hex", "brand color", "#"]},
    {"id": "brand_logo",             "phase": 3, "label": "Logo / visual identity",
     "keywords": ["logo", "visual", "design", "icon", "mark"]},
    {"id": "biggest_fear",           "phase": 3, "label": "Biggest fear about scaling",
     "keywords": ["fear", "afraid", "worry", "concern", "scaling", "grow"]},
    {"id": "biggest_frustration",    "phase": 3, "label": "Biggest frustration right now",
     "keywords": ["frustrate", "frustration", "annoying", "problem", "challenge"]},
    {"id": "real_weaknesses",        "phase": 3, "label": "Real weaknesses",
     "keywords": ["weakness", "weak", "struggle", "bad at", "not good at"]},

    # Phase 4 — Offer, Delivery, Operations
    {"id": "core_offer",             "phase": 4, "label": "Core offer / product",
     "keywords": ["offer", "product", "service", "program", "package", "sell"]},
    {"id": "delivery_model",         "phase": 4, "label": "How delivery works",
     "keywords": ["delivery", "fulfill", "deliver", "provide", "execute"]},
    {"id": "tools_stack",            "phase": 4, "label": "Tools & software stack",
     "keywords": ["tool", "software", "platform", "GoHighLevel", "Stripe", "Zapier",
                  "CRM", "tech stack", "use"]},
    {"id": "team_size",              "phase": 4, "label": "Current team size",
     "keywords": ["team", "staff", "employee", "headcount", "people", "alone", "solo"]},
    {"id": "bottleneck",             "phase": 4, "label": "Biggest operational bottleneck",
     "keywords": ["bottleneck", "slowdown", "bottleneck", "behind", "stuck", "manual"]},

    # Phase 5 — Departments & Priorities
    {"id": "priority_departments",   "phase": 5, "label": "Department priorities",
     "keywords": ["department", "priority", "focus", "most important", "first"]},
    {"id": "content_channels",       "phase": 5, "label": "Content / social channels",
     "keywords": ["Instagram", "LinkedIn", "TikTok", "YouTube", "Twitter", "X",
                  "social", "channel", "post", "content"]},
    {"id": "sales_process",          "phase": 5, "label": "Sales / lead process",
     "keywords": ["sales", "lead", "funnel", "close", "prospect", "pipeline"]},
    {"id": "support_process",        "phase": 5, "label": "Customer support process",
     "keywords": ["support", "help", "customer service", "question", "complaint"]},

    # Phase 6 — Persona / Voice
    {"id": "agent_name",             "phase": 6, "label": "Agent / AI team name",
     "keywords": ["agent name", "AI name", "assistant name", "call me", "named"]},
    {"id": "communication_style",    "phase": 6, "label": "Preferred communication style",
     "keywords": ["communication style", "formal", "casual", "friendly", "direct"]},
]


# Files that describe the box and its tooling, not the owner's business. They may
# never establish a fact, and they do not even produce a hint: they mention
# "client", "who" and "$" on every page.
NEVER_A_FACT_SOURCE = ("AGENTS.md", "TOOLS.md")

HINT_RULE = (
    "for the interviewer's background only; never shown to the owner as a fact "
    "and never a reason to skip a question"
)

# Structured company settings that may become known facts, with the key the
# question registry looks up in interview-known.json.
COMPANY_CONFIG_KEYS = (
    ("companyName", "company_name"),
    ("industry", "industry"),
    ("commandCenterName", "command_center_name"),
)
KNOWN_SOURCE_COMPANY_SETTINGS = "company-settings"
KNOWN_SOURCE_INTERVIEW_ANSWER = "interview-answer"


# ── Source reader ─────────────────────────────────────────────────────────────

def read_source(path: Path, label: str) -> dict:
    """
    Read a source file. Returns {label, path, content, present}.
    Never raises — absent files return present=False, content=None.
    """
    if path.exists() and path.is_file():
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            return {"label": label, "path": str(path), "content": content, "present": True}
        except Exception as exc:
            return {"label": label, "path": str(path), "content": None, "present": False,
                    "error": str(exc)}
    return {"label": label, "path": str(path), "content": None, "present": False}


def load_all_sources(
    workspace_root: Path,
    zhc_root: Path,
    master_files: Path,
    company_slug: str | None,
) -> list:
    """
    Load all 10 ingestion sources. Returns list of source dicts.
    Missing sources are included with present=False (pure superset: on empty box,
    all themes will be UNKNOWN and the interview runs exactly as it does today).
    """
    sources = []

    # 1-6: Core workspace .md files
    for fname in ("IDENTITY.md", "MEMORY.md", "AGENTS.md", "TOOLS.md", "USER.md", "SOUL.md"):
        sources.append(read_source(workspace_root / fname, fname))

    # 7-8: Company-slug-specific files
    company_dir = zhc_root / company_slug if company_slug else None
    if company_dir:
        sources.append(read_source(company_dir / "pre-interview-research.md",
                                   "pre-interview-research.md"))
        sources.append(read_source(company_dir / "software-stack-capabilities.md",
                                   "software-stack-capabilities.md"))
        sources.append(read_source(company_dir / "provided-context-manifest.md",
                                   "provided-context-manifest.md"))
    else:
        for fname in ("pre-interview-research.md", "software-stack-capabilities.md",
                      "provided-context-manifest.md"):
            sources.append({"label": fname, "path": None, "content": None, "present": False,
                             "note": "company slug not yet known"})

    # 9: Prior workforce-interview-answers.md
    company_discovery = master_files / "company-discovery"
    sources.append(read_source(company_discovery / "workforce-interview-answers.md",
                                "workforce-interview-answers.md (prior run)"))

    return sources


# ── Theme classifier ──────────────────────────────────────────────────────────

def _find_keyword_snippet(content: str, keywords: list, max_snippet: int = 200) -> str | None:
    """
    Case-insensitive search for any keyword in content. Returns up to max_snippet
    chars of surrounding context on first hit, or None.
    """
    if not content:
        return None
    content_lower = content.lower()
    for kw in keywords:
        idx = content_lower.find(kw.lower())
        if idx >= 0:
            start = max(0, idx - 60)
            end = min(len(content), idx + max_snippet)
            snippet = content[start:end].strip()
            # Truncate at a sentence boundary if possible
            for sep in ("\n", ". ", "! ", "? "):
                last = snippet.rfind(sep)
                if last > 80:
                    snippet = snippet[:last].strip()
                    break
            return snippet
    return None


def classify_theme(theme: dict, sources: list) -> dict:
    """
    Classify a single interview theme against all available sources.
    Returns a record: {theme_id, phase, label, status, hint, confidence,
                       suggested_action}.

    status is ALWAYS "unknown" and suggested_action is ALWAYS "ask-fresh": a keyword
    hit is not knowledge. A hit lands in "hint" ({source, snippet}) for the
    interviewer's background only. It is never shown to the owner as a fact and
    never a reason to skip a question. NEVER_A_FACT_SOURCE files are skipped.
    """
    keywords = theme["keywords"]
    hint = None

    for src in sources:
        if not src.get("present") or not src.get("content"):
            continue
        if src["label"] in NEVER_A_FACT_SOURCE:
            continue
        snippet = _find_keyword_snippet(src["content"], keywords)
        if snippet:
            hint = {"source": src["label"], "snippet": snippet}
            break

    return {
        "theme_id": theme["id"],
        "phase": theme["phase"],
        "label": theme["label"],
        "status": "unknown",
        "hint": hint,
        # The pre-v2.1 keys stay, empty, so an existing reader of the map cannot break.
        "source": None,
        "snippet": None,
        "all_sources": [],
        "confidence": "low",
        "suggested_action": "ask-fresh",
    }


def classify_all_themes(sources: list) -> list:
    return [classify_theme(t, sources) for t in INTERVIEW_THEMES]


# ── Known facts (structured fields only) ──────────────────────────────────────

def _read_json_optional(path: Path):
    """Read a JSON object. Absent or unreadable returns an empty dict — never raises."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _company_config_path(workspace_root: Path, build_state: dict):
    """company-config.json in the company root (build state), then the workspace root."""
    candidates = []
    root = build_state.get("companyRoot") if isinstance(build_state, dict) else None
    if isinstance(root, str) and root.strip():
        candidates.append(Path(root).expanduser() / "company-config.json")
    candidates.append(workspace_root / "company-config.json")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _write_known(path: Path, facts: dict) -> None:
    """Write interview-known.json atomically, mode 0600, temp file beside it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(facts, indent=2, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def known_facts(
    workspace_root: Path,
    build_state: dict | None = None,
    state_dir: Path | None = None,
    write: bool = True,
) -> dict:
    """
    Facts from STRUCTURED fields only — never from a keyword hit.

      * company-config.json: companyName / industry / commandCenterName
      * answers the gate already accepted (interview-gate-state.json)

    Returns {knownKey: {value, source}} in the shape of the interface contract
    (section 2.1) and, when write is true, merges them into
    [workspace]/company-discovery/interview-known.json without dropping keys another
    writer put there. These values are OFFERS: the gate shows them as knownValue and
    nothing is recorded until the owner submits it.
    """
    state_dir = Path(state_dir) if state_dir else workspace_root / "company-discovery"
    facts = {}

    gate_state = _read_json_optional(state_dir / "interview-gate-state.json")
    answers = gate_state.get("answers") if isinstance(gate_state.get("answers"), dict) else {}
    for qid, entry in answers.items():
        value = entry.get("value") if isinstance(entry, dict) else None
        if isinstance(value, str) and value.strip():
            facts[qid] = {"value": value.strip(), "source": KNOWN_SOURCE_INTERVIEW_ANSWER}

    config_path = _company_config_path(workspace_root, build_state or {})
    if config_path:
        config = _read_json_optional(config_path)
        for config_key, known_key in COMPANY_CONFIG_KEYS:
            value = config.get(config_key)
            if isinstance(value, str) and value.strip():
                facts[known_key] = {"value": value.strip(),
                                    "source": KNOWN_SOURCE_COMPANY_SETTINGS}

    if write and facts:
        path = state_dir / "interview-known.json"
        merged = _read_json_optional(path)
        merged.update(facts)
        _write_known(path, merged)
    return facts


# ── Output writers ────────────────────────────────────────────────────────────

def build_map(themes_classified: list, sources: list, company_slug: str | None) -> dict:
    """Assemble the full interview-context-map.json object."""
    sources_present = [s["label"] for s in sources if s.get("present")]
    known = [t for t in themes_classified if t["status"] == "known"]
    partial = [t for t in themes_classified if t["status"] == "partial"]
    unknown = [t for t in themes_classified if t["status"] == "unknown"]

    return {
        "version": "v12.3.4",
        "generatedAt": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "companySlug": company_slug,
        "sourcesPresentCount": len(sources_present),
        "sourcesPresent": sources_present,
        "summary": {
            "themesKnown": len(known),
            "themesPartial": len(partial),
            "themesUnknown": len(unknown),
            "totalThemes": len(themes_classified),
        },
        "noFabricationNote": (
            "No theme is ever known or partial from a keyword hit. A hint is for the "
            "interviewer's background only; it is never shown to the owner as a fact and "
            "never a reason to skip a question. Facts come from structured fields alone "
            "(interview-known.json), and even those are only offered for the owner to confirm: "
            "log_answer() in build-workforce.py is the ONLY writer to "
            "workforce-interview-answers.md."
        ),
        "hintRule": HINT_RULE,
        "themes": themes_classified,
    }


def write_map(map_obj: dict, output_path: Path) -> None:
    """Write interview-context-map.json atomically. NEVER touches answers file."""
    # Guard: refuse to write to workforce-interview-answers.md — belt-and-suspenders.
    if "workforce-interview-answers" in str(output_path):
        print("[FATAL] context-ingest.py attempted to write to answers file — aborting.",
              file=sys.stderr)
        sys.exit(1)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(output_path) + f".tmp.{os.getpid()}")
    try:
        tmp.write_text(json.dumps(map_obj, indent=2), encoding="utf-8")
        tmp.replace(output_path)
        print(f"[context-ingest] Context map written: {output_path}", file=sys.stderr)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        print(f"[context-ingest] WARNING: could not write context map: {exc}", file=sys.stderr)


def print_human_digest(map_obj: dict) -> None:
    """Print a concise human digest the AI agent reads at interview start."""
    s = map_obj["summary"]
    print("=" * 60)
    print("CONTEXT INGESTION DIGEST  (v12.3.4 — read before Phase 1)")
    print("=" * 60)
    print(f"Sources present : {map_obj['sourcesPresentCount']}  "
          f"({', '.join(map_obj['sourcesPresent'][:5])}{'...' if len(map_obj['sourcesPresent']) > 5 else ''})")
    hinted = [t for t in map_obj["themes"] if t.get("hint")]
    print(f"Themes to ask   : {s['totalThemes']}  (every one, fresh)")
    print(f"Themes with hint: {len(hinted)}  (background only — ask the question anyway)")
    print()
    print("NO-FABRICATION RULE: no theme is known from a keyword hit.")
    print("A hint is " + map_obj.get("hintRule", HINT_RULE) + ".")
    print()

    if hinted:
        print("--- HINTS (background only, ask the question anyway) ---")
        for t in hinted[:10]:
            hint = t["hint"]
            snippet_preview = (hint.get("snippet") or "")[:80].replace("\n", " ")
            print(f"  [{t['phase']}] {t['label']}")
            print(f"       Mentions in {hint.get('source')}  | {snippet_preview}...")
        if len(hinted) > 10:
            print(f"  ... and {len(hinted) - 10} more.")
        print()

    print("=" * 60)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Skill 23 context ingestion pre-pass. Reads all client context sources "
            "and produces interview-context-map.json: every theme is unknown, and a "
            "keyword hit is only a hint for the interviewer. Facts come from structured "
            "fields alone. NEVER writes answers."
        )
    )
    parser.add_argument(
        "--slug",
        help="Company slug (e.g. blackceo-llc). Auto-detected from build state if absent.",
        default=None,
    )
    parser.add_argument(
        "--workspace",
        help="Path to OpenClaw workspace root. Defaults to auto-detected.",
        default=None,
    )
    parser.add_argument(
        "--master-files",
        help="Path to openclaw-master-files folder. Defaults to auto-detected.",
        default=None,
    )
    parser.add_argument(
        "--output",
        help=(
            "Where to write interview-context-map.json. "
            "Defaults to [ZHC]/[slug]/interview-context-map.json."
        ),
        default=None,
    )
    parser.add_argument(
        "--format",
        choices=["json", "human"],
        default="human",
        help="Output format for stdout (default: human digest).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=("Classify and print but write nothing: no interview-context-map.json and "
              "no interview-known.json."),
    )
    args = parser.parse_args()

    # Resolve paths
    openclaw_root = _resolve_openclaw_root()
    workspace_root = Path(args.workspace) if args.workspace else _resolve_workspace_root(openclaw_root)
    master_files = Path(args.master_files) if args.master_files else _resolve_master_files(workspace_root)
    zhc_root = _resolve_zhc_root(master_files)

    # Build state: company slug for the pre-interview folder, companyRoot for company-config.json
    build_state = _read_json_optional(workspace_root / ".workforce-build-state.json")
    company_slug = args.slug
    if not company_slug:
        company_slug = build_state.get("companySlug") or build_state.get("companyName")
        if isinstance(company_slug, str) and company_slug.strip():
            company_slug = company_slug.strip()
            if "/" not in company_slug:
                # Slugify: lowercase, hyphens
                company_slug = re.sub(r"[^a-z0-9]+", "-", company_slug.lower()).strip("-")
        else:
            company_slug = None

    print(f"[context-ingest] workspace_root={workspace_root}", file=sys.stderr)
    print(f"[context-ingest] master_files={master_files}", file=sys.stderr)
    print(f"[context-ingest] company_slug={company_slug!r}", file=sys.stderr)

    # Structured facts only: company settings and answers the gate already accepted.
    facts = known_facts(workspace_root, build_state, write=not args.dry_run)
    print(f"[context-ingest] Known facts: {len(facts)}", file=sys.stderr)

    # Load all sources
    sources = load_all_sources(workspace_root, zhc_root, master_files, company_slug)
    present_count = sum(1 for s in sources if s.get("present"))
    print(f"[context-ingest] Sources present: {present_count}/{len(sources)}", file=sys.stderr)

    # Classify themes
    themes_classified = classify_all_themes(sources)

    # Build output map
    map_obj = build_map(themes_classified, sources, company_slug)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    elif company_slug and zhc_root.is_dir():
        output_path = zhc_root / company_slug / "interview-context-map.json"
    else:
        output_path = workspace_root / "interview-context-map.json"

    # Write map (unless dry-run)
    if not args.dry_run:
        write_map(map_obj, output_path)

    # Output to stdout
    if args.format == "json":
        print(json.dumps(map_obj, indent=2))
    else:
        print_human_digest(map_obj)


if __name__ == "__main__":
    main()
