#!/usr/bin/env python3
# =============================================================================
# SKILL 54 — ANTHOLOGY WRITER :: SHARED PROVER PRIMITIVES
# -----------------------------------------------------------------------------
# Deterministic, stdlib-only helpers shared by the Anthology Writer provers
# (prove_aw_intake / prove_aw_fidelity / prove_aw_tone / prove_aw_chapter /
# aw_build_check). No network, no model judgement, no third-party imports.
# Runs identically on every box (operator or client).
#
# DESIGN LAW: enforcement, not description. Every measurer here works on the
# STRIPPED text of the artifact — markdown syntax, list bullets, code fences,
# and collapsed whitespace are removed before anything is counted. A model's
# SELF-REPORTED count (a "Final word count: 2600 words" line, a COMPLETION
# VERIFICATION number) is NEVER trusted; we measure the real words. A
# whitespace-padding attack (pad a short chapter with blank lines/spaces to look
# long) cannot fool a floor: whitespace collapses to nothing.
#
# EXIT CODE CONTRACT (every prover):
#   0  PASS      — every rule satisfied.
#   2  AUTOFAIL  — one or more AF-AW-* violations (fail-closed).
#   3  USAGE/IO  — missing file / unreadable / invalid input (still fail-closed).
# =============================================================================
"""Shared deterministic primitives for the Skill 54 Anthology Writer provers."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ---- exit codes (shared by every prover) ------------------------------------
EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

# ---- SACRED floors (PRD §3.5 — anthology chapter contract) ------------------
# One chapter per contributor, stripped-word band; the tone doc is the blended
# "The {First} {Last} Tone" with its own stripped-word floor (tone-core R7).
CHAPTER_WORD_MIN = 2000
CHAPTER_WORD_MAX = 3500
TONE_WORD_FLOOR = 3000            # shared-utils/tone-writing-core 08-blended-tone
TONE_INFLUENCES_REQUIRED = 4      # blended tone is built from EXACTLY 4 analyses

# The mandatory self-attestation footer every finalized long-form artifact ends
# with. Its numbers are IGNORED (we measure); only its PRESENCE is required, so a
# stripped chapter can never masquerade as complete without it.
VERIFY_BLOCK_MARKER = "COMPLETION VERIFICATION"

# The four required intake fields the anthology pipeline actually consumes
# (PRD §3.3). personal_stories is captured but may be the literal string "N/A".
INTAKE_REQUIRED = ("anthology_title", "first_name", "last_name", "chapter_premise")
INTAKE_OPTIONAL = ("personal_stories", "client_folder_name", "email", "phone",
                   "subtitle_hint", "target_reader")

# Credential-shaped intake keys are FORBIDDEN (D7): a client's provider keys are
# resolved per box from the client's own OpenClaw config — never taken through
# intake, never the operator's. Any key that looks like a secret fails closed.
_CREDENTIAL_KEY_RE = re.compile(
    r"(api[_-]?key|apikey|secret|token|bearer|password|passwd|"
    r"openrouter|anthropic|openai|access[_-]?key|private[_-]?key|"
    r"credential|auth[_-]?token)",
    re.I,
)

# ---- regexes ----------------------------------------------------------------
_MD_INLINE_RE = re.compile(r"[*_`~#>|]")                          # inline markdown punctuation
_CODEFENCE_RE = re.compile(r"^\s*```")
_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?")
_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*\S)\s*$")           # markdown ATX header
_BOLD_HEADER_RE = re.compile(r"^\s*\*\*(.+?)\*\*\s*:?\s*$")       # a bold-only header line
# Unresolved template placeholders that must never survive into a final artifact.
_PLACEHOLDER_RE = re.compile(r"\{\{[^}]+\}\}|\[\[[^\]]+\]\]|<[A-Z][A-Z0-9_]{2,}>")


# ---- IO ---------------------------------------------------------------------
def read_text(path) -> str:
    """Read a UTF-8 text artifact or fail-closed (EXIT_USAGE)."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print("USAGE/IO: cannot read %s: %s" % (path, exc), file=sys.stderr)
        sys.exit(EXIT_USAGE)


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("USAGE/IO: cannot read/parse JSON %s: %s" % (path, exc), file=sys.stderr)
        sys.exit(EXIT_USAGE)


# ---- stripped-text measurement ----------------------------------------------
def strip_markdown(text: str) -> str:
    """Reduce markdown/prose to bare words + newlines. Code fences dropped,
    inline markdown punctuation removed, each line trimmed. This is what every
    counter measures — never the raw bytes, so whitespace padding is inert."""
    out_lines = []
    in_fence = False
    for line in text.splitlines():
        if _CODEFENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        stripped = _MD_INLINE_RE.sub("", line)
        out_lines.append(stripped.strip())
    return "\n".join(out_lines)


def word_count(text: str) -> int:
    """Deterministic STRIPPED word count. Collapses all whitespace to single
    tokens, so blank-line / space padding cannot inflate the number. The model's
    self-reported count is irrelevant — this is the measured truth."""
    return len(_WORD_RE.findall(strip_markdown(text)))


def normalized_tokens(text: str, min_len: int = 1) -> list:
    """Lowercased alnum tokens of the STRIPPED text (for placement/coverage)."""
    return [t for t in _WORD_RE.findall(strip_markdown(text).lower()) if len(t) >= min_len]


def normalize_phrase(text: str) -> str:
    """A whitespace/case-normalized form of a short phrase for byte-exact-ish
    lock comparisons (collapses runs of whitespace, lowercases). Used so a
    locked title matches regardless of incidental spacing, but a CHANGED word
    still breaks the lock."""
    return re.sub(r"\s+", " ", strip_markdown(text).lower()).strip()


def contains_phrase(haystack: str, needle: str) -> bool:
    """True iff the normalized needle phrase occurs in the normalized haystack."""
    n = normalize_phrase(needle)
    if not n:
        return True
    return n in normalize_phrase(haystack)


def unresolved_placeholders(text: str) -> list:
    """Every unresolved template placeholder ({{..}}, [[..]], <ALLCAPS>) left in
    a finalized artifact. A non-empty list is a hard fail (AF-AW-PLACEHOLDER)."""
    return sorted(set(_PLACEHOLDER_RE.findall(text)))


# ---- section / header parsing -----------------------------------------------
def header_lines(text: str):
    """Yield (line_index, header_text) for every line that acts as a header:
    a markdown ATX header (#..######) or a bold-only line."""
    for i, line in enumerate(text.splitlines()):
        m = _HEADER_RE.match(line)
        if m:
            yield i, m.group(1)
            continue
        m = _BOLD_HEADER_RE.match(line)
        if m:
            yield i, m.group(1)


def credential_shaped_keys(obj) -> list:
    """Return the intake keys whose NAME looks like a secret (fail-closed D7)."""
    if not isinstance(obj, dict):
        return []
    return sorted(k for k in obj if _CREDENTIAL_KEY_RE.search(str(k)))


def story_phrases(intake: dict) -> list:
    """The non-'N/A' personal-story anchor phrases the chapter must place. Each
    story item may be a string or an object with a 'summary'/'anchor' field; a
    literal 'N/A' (any case) means the contributor has no personal story and the
    placement check is vacuously satisfied for that slot."""
    raw = intake.get("personal_stories")
    items = []
    if isinstance(raw, str):
        if raw.strip() and raw.strip().upper() != "N/A":
            items = [raw]
    elif isinstance(raw, list):
        items = raw
    anchors = []
    for it in items:
        if isinstance(it, dict):
            val = it.get("anchor") or it.get("summary") or it.get("text") or ""
        else:
            val = str(it)
        val = val.strip()
        if val and val.upper() != "N/A":
            anchors.append(val)
    return anchors


# ---- client-exact band overrides (fleet law: an exact ask WINS over a default) --
# "Client gets EXACTLY what they ask for — never floor/cap/change it." A default
# band (chapter 2,000-3,500; tone floor 3,000) is the fallback; a client-stated
# EXACT word target is honored verbatim. But — enforcement, not description — an
# exact target is honored ONLY through an AUDITED channel: a logged override
# object that is recorded, approved, reasoned, and provably TIED to the locked
# brief. An override applied without that log is a silent floor-swap and fails
# CLOSED (AF-AW-OVERRIDE-UNLOGGED). Mirrors the Skill-57 override shape.
def _slugify(data) -> str:
    """Slugify a str or an intake dict. Accepts both types and returns a clean
    lowercased dash-separated slug. A dict is treated as an intake record:
    the slug is built from anthology_title + first_name + last_name."""
    if isinstance(data, dict):
        base = "%s %s %s" % (data.get("anthology_title", "anthology"),
                             data.get("first_name", ""), data.get("last_name", ""))
    else:
        base = str(data or "anthology")
    slug = re.sub(r"[^a-z0-9]+", "-", base.strip().lower()).strip("-")
    return slug or "anthology"


def brief_identity(brief) -> set:
    """The set of acceptable brief_ref values a logged override may cite to tie
    itself to the LOCKED brief (intake.json). An override whose brief_ref is not
    in this set is UNLOGGED — not provably tied to THIS contributor's brief."""
    if not isinstance(brief, dict):
        return set()
    title = str(brief.get("anthology_title", "")).strip().lower()
    slug = _slugify("%s %s %s" % (brief.get("anthology_title", "anthology"),
                                  brief.get("first_name", ""), brief.get("last_name", "")))
    return {r for r in (title, slug) if r}


def resolve_band_override(override, brief, keys):
    """Resolve a client-exact band override from a LOGGED overrides channel.

    Returns (status, reason, applied):
      "none"     — no override supplied; use the DEFAULT band.
      "unlogged" — an override was supplied but is NOT provably logged and tied to
                   the locked brief -> the caller fails CLOSED (an exact ask is
                   honored only when it is recorded, approved, reasoned, and cites
                   this brief; an unlogged override is a silent floor-swap).
      "applied"  — the override is logged + tied; `applied` holds the requested
                   numeric keys to use INSTEAD of the defaults.

    keys: the numeric override keys to extract (e.g. ("chapter_word_min",
    "chapter_word_max") or ("tone_word_floor",))."""
    if override is None:
        return "none", "no client band override supplied (default band)", {}
    if not isinstance(override, dict) or not override:
        return "unlogged", "override channel present but not a non-empty object", {}
    for field in ("source", "approved_by", "reason", "brief_ref"):
        if not str(override.get(field, "")).strip():
            return ("unlogged", "override is missing a logged %r — an applied override MUST be "
                    "recorded, approved, reasoned, and cite the locked brief" % field, {})
    refs = brief_identity(brief)
    if not refs:
        return "unlogged", "no locked brief supplied to tie the override to", {}
    if str(override.get("brief_ref", "")).strip().lower() not in refs:
        return ("unlogged", "override brief_ref %r does not match the locked brief (%s) — "
                "not provably tied" % (override.get("brief_ref"), ", ".join(sorted(refs))), {})
    applied = {}
    for k in keys:
        if k in override and override.get(k) is not None:
            try:
                applied[k] = int(override[k])
            except (TypeError, ValueError):
                return "unlogged", "override %r is not an integer" % k, {}
    if not applied:
        # The override IS logged and tied, it simply does not target THIS band
        # (e.g. a chapter-band override reaching the tone prover). That is not an
        # unlogged swap — this prover just uses its DEFAULT floor.
        return ("none", "logged override does not target this band (%s) — default applies"
                % ", ".join(keys), {})
    return ("applied", "client-exact override applied from the logged channel "
            "(source=%r, approved_by=%r)" % (override.get("source"), override.get("approved_by")),
            applied)


# ---- AF code recovery guidance ----------------------------------------------
AF_CODE_GUIDANCE = {
    "AF-AW-INTAKE-MISSING": {
        "file": "{run_dir}/working/intake.json",
        "field": "Required fields: anthology_title, first_name, last_name, chapter_premise",
        "expected_shape": '{"anthology_title":"My Book","first_name":"John","last_name":"Doe","chapter_premise":"...","personal_stories":"N/A"}',
        "fix_hint": "Ensure all four required fields are present and non-empty in working/intake.json. "
                    "Whitespace-only values count as missing. Use the intake template at "
                    "54-anthology-writer/intake/aw-intake-template.md for the correct shape.",
    },
    "AF-AW-INTAKE-CREDENTIAL": {
        "file": "{run_dir}/working/intake.json",
        "field": "Forbidden credential-shaped keys (api_key, token, secret, password, etc.)",
        "expected_shape": "No keys matching api_key|apikey|secret|token|bearer|password|openrouter|anthropic|openai|access_key|private_key|credential|auth_token (case-insensitive)",
        "fix_hint": "Remove any credential-shaped keys from working/intake.json. Client provider keys "
                    "are resolved per box from the client's own OpenClaw config, never through intake. "
                    "The key name itself is the violation -- rename it (e.g. 'api_key' -> 'client_reference').",
    },
    "AF-AW-CHAP-LEN": {
        "file": "{run_dir}/working/chapter.md",
        "field": "Stripped word count",
        "expected_shape": "2,000-3,500 stripped words (default band; client-exact override wins)",
        "fix_hint": "If the measured word count is below the minimum, expand the chapter with "
                    "substantive prose (not padding -- whitespace is stripped before counting). "
                    "If above the maximum, trim the longest sections. "
                    "The COMPLETION VERIFICATION block must also be present.",
    },
    "AF-AW-VERIFY-BLOCK": {
        "file": "{run_dir}/working/chapter.md",
        "field": "COMPLETION VERIFICATION block",
        "expected_shape": "A markdown section containing the literal text 'COMPLETION VERIFICATION'",
        "fix_hint": "Add a 'COMPLETION VERIFICATION' section at the end of working/chapter.md. "
                    "This is the mandatory self-attestation footer every finalized chapter must carry. "
                    "Its numbers are ignored (we measure); only its presence is required.",
    },
    "AF-AW-PLACEHOLDER": {
        "file": "{run_dir}/working/chapter.md (or outline.md)",
        "field": "Unresolved template placeholders",
        "expected_shape": "No {{..}}, [[..]], or <ALLCAPS> patterns anywhere in the artifact",
        "fix_hint": "Search the artifact for {{..}}, [[..]], or <ALLCAPS> patterns and replace each "
                    "with the actual content. These are template markers that must not survive into the "
                    "finalized artifact. Common culprits: {{anthology_title}}, <CLIENT_NAME>.",
    },
    "AF-AW-TITLE-LOCK": {
        "file": "{run_dir}/working/chapter.md (or outline.md) + working/title.json",
        "field": "Locked title / subtitle",
        "expected_shape": "The title and subtitle from title.json must appear byte-exact (whitespace/case normalized) in the artifact body",
        "fix_hint": "Ensure the locked title and subtitle from working/title.json appear in the "
                    "chapter/outline body exactly as written (whitespace and case normalized). "
                    "A changed subtitle in the body will trip this. Check for spelling/case differences.",
    },
    "AF-AW-STORIES": {
        "file": "{run_dir}/working/chapter.md (or outline.md) + working/intake.json",
        "field": "Personal story anchors",
        "expected_shape": "Every non-'N/A' personal_stories anchor phrase from intake.json must appear (whitespace/case normalized) in the artifact",
        "fix_hint": "Ensure every non-'N/A' personal story anchor phrase from working/intake.json "
                    "appears in the chapter/outline text. Check that the story phrasings match "
                    "exactly (whitespace and case are normalized, but words must match).",
    },
    "AF-AW-TONE-4": {
        "file": "{run_dir}/working/tone-doc.md",
        "field": "Tone influence analyses (indices 1-4)",
        "expected_shape": "Exactly 4 distinct influence analysis headers carrying indices {1,2,3,4}",
        "fix_hint": "The blended tone doc must reference exactly 4 influence analyses with header lines "
                    "like '## Influence 1 -- ...', '**Tone Style 2:**', or 'Influence #3'. "
                    "Ensure all four indices (1,2,3,4) appear in section headers. "
                    "Fewer than 4 means a thinned tone; a self-report of '4 influences' is never trusted.",
    },
    "AF-AW-TONE-FLOOR": {
        "file": "{run_dir}/working/tone-doc.md",
        "field": "Stripped word count",
        "expected_shape": "At least 3,000 stripped words (default floor; client-exact override wins)",
        "fix_hint": "Expand the blended tone document to meet the 3,000-word floor. "
                    "Whitespace padding is inert (stripped before counting). "
                    "Add substantive analysis prose to each of the four influence sections.",
    },
    "AF-AW-ANTHROPIC": {
        "file": "{run_dir}/working/RUN-LEDGER.json",
        "field": "Resolved model ids (must NOT contain 'anthropic' or 'claude') + operator credential env vars",
        "expected_shape": "All resolved model ids must be NON-Anthropic; no OPERATOR_ANTHROPIC_API_KEY/OPERATOR_API_KEY/ANTHROPIC_ADMIN_KEY in env",
        "fix_hint": "Replace any Anthropic model id (containing 'anthropic' or 'claude') in RUN-LEDGER.json "
                    "with the client's strongest NON-Anthropic model. Remove any operator credential "
                    "environment variables (OPERATOR_ANTHROPIC_API_KEY, etc.) from the run environment. "
                    "Client runs use the client's OWN keys only.",
    },
    "AF-AW-REWRITE-BUDGET": {
        "file": "{run_dir}/working/RUN-LEDGER.json",
        "field": "rewrite_count",
        "expected_shape": "rewrite_count <= 2 (bounded rework loop)",
        "fix_hint": "The rewrite_count in RUN-LEDGER.json exceeds the maximum of 2. "
                    "Too many rewrites were performed on this chapter. Consider starting a fresh run "
                    "rather than reworking the existing artifacts further.",
    },
    "AF-AW-PROVENANCE-MISSING": {
        "file": "{run_dir}/working/RUN-LEDGER.json",
        "field": "stages array (must record resolved model ids)",
        "expected_shape": "RUN-LEDGER.json must have a non-empty 'stages' array with 'model'/'model_id'/'resolved_model' fields in each stage",
        "fix_hint": "RUN-LEDGER.json must record the model provenance the chapter was authored on. "
                    "Ensure each stage entry carries a model id (field name: 'model', 'model_id', or "
                    "'resolved_model'). An empty/absent stages array means the no-Anthropic gate cannot "
                    "be proven -- populate it with the NON-Anthropic model ids used during authoring.",
    },
    "AF-AW-PROMPT-DRIFT": {
        "file": "{skill_dir}/assets/prompts/*.md and ANTHOLOGY-MANIFEST.json",
        "field": "Prompt asset sha256 must match the manifest source_prompt_pins",
        "expected_shape": "Every assets/prompts/*.md sha256 == its recorded pin in ANTHOLOGY-MANIFEST.json; no unpinned prompt files",
        "fix_hint": "The baked authoring prompt assets have drifted from their pinned hashes. "
                    "Either restore the original prompt files from the shipped skill, or update the "
                    "source_prompt_pins in ANTHOLOGY-MANIFEST.json to match the new sha256 values. "
                    "NOTE: prompt drift means the IP has changed -- verify the change is intentional "
                    "before updating the pins.",
    },
    "AF-AW-AVATAR-MISSING": {
        "file": "{run_dir}/working/avatar.md",
        "field": "Avatar dossier presence and content",
        "expected_shape": "A non-empty markdown file containing the Skill 52 avatar-alchemist handoff dossier",
        "fix_hint": "working/avatar.md is absent, empty, or whitespace-only. The Skill 52 avatar "
                    "handoff must produce a real avatar dossier before downstream authoring can begin. "
                    "Run the Skill 52 avatar-alchemist delegation (prompts 01-03) against this "
                    "contributor's intake data to generate the dossier.",
    },
    "AF-AW-AVATAR-HANDOFF-DRIFT": {
        "file": "{skill_dir}/../52-avatar-alchemist/prompts/*",
        "field": "Skill 52 avatar prompt sha256 must match the manifest avatar_handoff pins",
        "expected_shape": "Every referenced Skill 52 prompt at its pinned path with sha256 == the manifest avatar_handoff pin",
        "fix_hint": "A referenced Skill 52 avatar prompt is missing, tampered, or version-drifted. "
                    "Ensure Skill 52 (52-avatar-alchemist) is installed and its prompts match the pinned "
                    "hashes in ANTHOLOGY-MANIFEST.json -> avatar_handoff.stages. "
                    "The avatar IP is single-sourced in Skill 52 and referenced by path only.",
    },
    "AF-AW-AVATAR-COPIED": {
        "file": "{skill_dir}/ (this skill's tree)",
        "field": "No Skill 52 avatar prompt file may be copied into this skill's tree",
        "expected_shape": "No files matching Skill 52 avatar stage directory names (01-avatar-questions-1-30, etc.) or byte-identical copies",
        "fix_hint": "A Skill 52 avatar prompt file was copied into this skill's tree. "
                    "Delete the copied file(s). The avatar IP stays single-sourced in Skill 52 "
                    "and is referenced BY PATH, never copied. The delegation resolves at runtime.",
    },
    "AF-AW-OVERRIDE-UNLOGGED": {
        "file": "{run_dir}/working/overrides.json",
        "field": "Override must be logged (source, approved_by, reason, brief_ref) and tied to the locked brief",
        "expected_shape": '{"source":"client-exact-request","approved_by":"operator","reason":"...","brief_ref":"<anthology-title-slug>","chapter_word_min":2000,"chapter_word_max":3600}',
        "fix_hint": "The band override in working/overrides.json is not properly logged and tied. "
                    "Every override must carry: source, approved_by, reason, and brief_ref. "
                    "The brief_ref must match the anthology title slug from the locked intake brief. "
                    "An unlogged override is a silent floor-swap and is rejected fail-closed.",
    },
    "AF-AW-STAGE-SKIPPED": {
        "file": "{run_dir}/working/ (various artifacts)",
        "field": "Required QC'd working copies must be present for the current phase",
        "expected_shape": "All required working artifacts for the active phase must be present and non-empty",
        "fix_hint": "One or more required working artifacts are missing for the current phase. "
                    "Each phase has prerequisites (e.g., P6-CHAPTER-QC needs chapter.md, outline.md, "
                    "title.json, intake.json, RUN-LEDGER.json). Run through the phases in order and "
                    "ensure each authoring step produces its artifact before advancing.",
    },
    "AF-AW-BLURB-MISSING": {
        "file": "{run_dir}/working/blurb.md",
        "field": "Blurb content (must be finalized prose: non-empty, no placeholders, >= 20 words)",
        "expected_shape": "A finished back-cover blurb of at least 20 words, with no unresolved placeholders",
        "fix_hint": "working/blurb.md is either missing, empty, too short (<20 words), or carries "
                    "unresolved placeholders. Write a finished back-cover blurb (at least 20 words of "
                    "substantive prose) and save it to working/blurb.md before P7-DELIVER.",
    },
    "AF-AW-DELIVER-MISMATCH": {
        "file": "{run_dir}/delivery/ (vs working/ source)",
        "field": "Delivery artifact bytes must match the QC'd working copy byte-for-byte",
        "expected_shape": "Every delivery/* file sha256 == its working/* source sha256",
        "fix_hint": "A delivery artifact disagrees byte-for-byte with its QC'd working copy -- this is "
                    "a swap-after-QC or planted deliverable. Delete the mismatched file from delivery/ "
                    "and re-run P7-DELIVER to reassemble from the QC'd working sources.",
    },
    "AF-AW-PROCESS-INTEGRITY": {
        "file": "N/A (process-level)",
        "field": "All P0-P6 phases must have passed before a certificate can be issued",
        "expected_shape": "All 8 phases (P0-INTAKE through P6-CHAPTER-QC, plus P0A-AVATAR) must be verified",
        "fix_hint": "A full P0-P6 pass is required before a process certificate can be issued. "
                    "Re-run from the failing phase to complete all phases. "
                    "A partial (--upto) run never certifies.",
    },
    "AF-AW-HASH-PIN": {
        "file": "{skill_dir}/ENGINE-PIN.sha256",
        "field": "Enforcement set sha256 (orchestrator + provers + _aw_common.py)",
        "expected_shape": "The computed sha256 of the enforcement files must match the pinned value in ENGINE-PIN.sha256",
        "fix_hint": "The enforcement-set hash does not match the pinned head in ENGINE-PIN.sha256. "
                    "Either the enforcement files (run_anthology.py, the provers, _aw_common.py) have "
                    "been modified, or the pin file is stale. Verify the changes are intentional, then "
                    "update ENGINE-PIN.sha256 with the new computed hash.",
    },
    "AF-AW-ENTRY-BYPASS": {
        "file": "{run_dir}/ (run directory .py files)",
        "field": "No hand-rolled external uploader/notifier scripts in the run directory",
        "expected_shape": "No .py files in the run directory containing Drive/Slack/Gmail/n8n/Airtable API calls (outside the canonical enforcement set)",
        "fix_hint": "Delete any hand-rolled .py scripts in the run directory that call external services "
                    "(Google Drive, Slack, Gmail/SMTP, n8n webhooks, Airtable). The Anthology Writer is "
                    "LOCAL-ONLY; delivery is a labeled bundle in ~/Downloads. No external uploader/notifier "
                    "is permitted -- the client's own OpenClaw gateway handles any channel push.",
    },
    "AF-AW-UNRESOLVED-MODELMAP": {
        "file": "{run_dir}/model-map.json",
        "field": "Resolved provider model ids (no <CLIENT_*> placeholders, no Anthropic ids)",
        "expected_shape": '{"<tier>":"<provider>/<model-id>"} with all placeholders resolved to actual provider model ids',
        "fix_hint": "The run-dir model-map.json still carries <CLIENT_*> placeholders or a banned "
                    "Anthropic id. Run the fleet installer (preflight.sh --run-dir) on a configured "
                    "box to resolve the tier map to the client's own NON-Anthropic providers. "
                    "Each <CLIENT_XX> placeholder must be replaced with a real provider model id.",
    },
    "AF-AW-TONE-CORE-SYNC": {
        "file": "{skill_dir}/prompts/ (tone-style prompt directories)",
        "field": "Tone-style prompt cores must be in sync with shared-utils/tone-writing-core",
        "expected_shape": "Every prompts/0*-tone-style-*/system.md and methodology.md sha256 must match the canonical tone-writing-core source",
        "fix_hint": "A tone-style prompt core has drifted from the canonical tone-writing-core in "
                    "shared-utils/. Run verify_tone_core_sync.py to identify the drifted files, then "
                    "restore them from the shared-utils source or update the sync pins.",
    },
    "AF-AW-ENTRY-SANITY": {
        "file": "{run_dir}/working/intake.json",
        "field": "Intake must be a valid JSON object with a non-empty anthology_title",
        "expected_shape": '{"anthology_title":"...","first_name":"...","last_name":"...","chapter_premise":"..."}',
        "fix_hint": "working/intake.json is missing, not valid JSON, or has an empty anthology_title. "
                    "Ensure the intake file is a well-formed JSON object with at least a non-empty "
                    "anthology_title. Use the intake template at 54-anthology-writer/intake/aw-intake-template.md.",
    },
    "AW_DEPS_MISSING": {
        "file": "System dependency",
        "field": "python3 must be available on the PATH",
        "expected_shape": "python3 resolves to an executable on the PATH",
        "fix_hint": "Install Python 3 on this system. The Anthology Writer orchestrator and all provers "
                    "require Python 3 (stdlib only, no third-party packages). On macOS: brew install python3. "
                    "On Debian/Ubuntu: apt install python3.",
    },
}


def af_guidance_for(code: str) -> dict:
    """Return the AF_CODE_GUIDANCE entry for `code`, or a minimal fallback."""
    g = AF_CODE_GUIDANCE.get(code)
    if g is not None:
        return g
    return {
        "file": "unknown",
        "field": "unknown",
        "expected_shape": "unknown",
        "fix_hint": "See the violation message for details. Search the code for this AF code "
                    "to find the relevant gate logic in the prover scripts.",
    }


def print_af_guidance(code: str, file=None, *, measured: str = None, required: str = None,
                      run_dir: str = None, skill_dir: str = None):
    """Print actionable recovery guidance for an AF code to `file` (default stderr).
    Resolves {run_dir} and {skill_dir} placeholders in file paths and hints."""
    g = af_guidance_for(code)
    out = file if file is not None else sys.stderr
    # Resolve template variables in file/hint paths
    resolved_file = g["file"]
    resolved_hint = g["fix_hint"]
    if run_dir:
        resolved_file = resolved_file.replace("{run_dir}", run_dir)
        resolved_hint = resolved_hint.replace("{run_dir}", run_dir)
    if skill_dir:
        resolved_file = resolved_file.replace("{skill_dir}", skill_dir)
        resolved_hint = resolved_hint.replace("{skill_dir}", skill_dir)

    print("    ── RECOVERY GUIDANCE ──", file=out)
    print("    AF code     : %s" % code, file=out)
    if measured is not None:
        print("    Measured    : %s" % measured, file=out)
    if required is not None:
        print("    Required    : %s" % required, file=out)
    print("    File        : %s" % resolved_file, file=out)
    print("    Field       : %s" % g["field"], file=out)
    print("    Expected    : %s" % g["expected_shape"], file=out)
    print("    FIX         : %s" % resolved_hint, file=out)
    print("    ─────────────────────────", file=out)


# ---- intake loading ----------------------------------------------------------
def load_intake(run_dir: Path) -> dict:
    """Load intake.json from a run dir's working/ subdirectory. Returns an empty
    dict on any failure — callers handle the missing case downstream."""
    ipath = run_dir / "working" / "intake.json"
    if not ipath.is_file():
        return {}
    try:
        return json.loads(ipath.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# ---- result plumbing --------------------------------------------------------
class Result:
    """Accumulates AF-AW-* violations; decides the exit code fail-closed."""

    def __init__(self, prover: str):
        self.prover = prover
        self.violations = []   # list of (code, message)
        self.notes = []

    def fail(self, code: str, message: str):
        self.violations.append((code, message))

    def note(self, message: str):
        self.notes.append(message)

    @property
    def passed(self) -> bool:
        return not self.violations

    def emit(self, as_json: bool, run_dir: str = None, skill_dir: str = None,
             measured: str = None, required: str = None) -> int:
        if as_json:
            out = {
                "prover": self.prover,
                "passed": self.passed,
                "violations": [{"code": c, "message": m} for c, m in self.violations],
                "notes": self.notes,
            }
            # In JSON mode, still include guidance for each violation inline
            guidance = []
            for c, _m in self.violations:
                g = af_guidance_for(c)
                entry = dict(g, code=c)
                if run_dir:
                    for k in ("file", "fix_hint"):
                        if k in entry:
                            entry[k] = entry[k].replace("{run_dir}", run_dir)
                if skill_dir:
                    for k in ("file", "fix_hint"):
                        if k in entry:
                            entry[k] = entry[k].replace("{skill_dir}", skill_dir)
                guidance.append(entry)
            if guidance:
                out["guidance"] = guidance
            if measured is not None:
                out["measured"] = measured
            if required is not None:
                out["required"] = required
            print(json.dumps(out, indent=2))
        else:
            if self.passed:
                print("PASS [%s]: all rules satisfied." % self.prover)
                for n in self.notes:
                    print("  - %s" % n)
            else:
                print("AUTOFAIL [%s]: %d violation(s)" % (self.prover, len(self.violations)),
                      file=sys.stderr)
                for c, m in self.violations:
                    print("  [%s] %s" % (c, m), file=sys.stderr)
                    print_af_guidance(c, file=sys.stderr, measured=measured, required=required,
                                     run_dir=run_dir, skill_dir=skill_dir)
        return EXIT_PASS if self.passed else EXIT_AUTOFAIL


def selftest_report(name: str, checks) -> int:
    """checks: list of (label, ok_bool). Returns 0 iff all ok."""
    ok = True
    for label, good in checks:
        print("  [%s] %s" % ("OK" if good else "XX", label))
        ok = ok and good
    print("== %s self-test: %s ==" % (name, "ALL ASSERTIONS [PASS]" if ok else "[FAIL]"))
    return 0 if ok else 1
