#!/usr/bin/env python3
"""
hash-content-manifest.py — per-artifact content hash + version stamper.

Stamps a CANONICAL-SOURCE content hash, a neutral-render cross-check hash, a
content_version, and a content_hashed_at timestamp onto every artifact in the
role library, and writes them in-place into:

    23-ai-workforce-blueprint/templates/role-library/_index.json

modeled exactly on tag_role_classes.py (idempotent in-place stamper over the
SAME _index.json — ONE source of truth that the consistency gate already loads
as Repo.index). It is the LAST stamper in the library-build chain, so it sees
the final content of every file (after generate-role-library.py / tag_role_classes.py).

──────────────────────────────────────────────────────────────────────────────
WHY NAIVE HASHING FAILS (and why this hashes the CANONICAL TEMPLATE, not the
rendered client bytes)
──────────────────────────────────────────────────────────────────────────────
Every canonical role .md is a pure-TEMPLATE file. `_token-reference.md` states
"the library docs themselves contain ONLY tokens, never literal client data."
A library file like account-management/client-relationship-manager.md is full of
{{COMPANY_NAME}} / {{GENERATION_DATE}} / {{ISO_DATE}} / {{ASSIGNED_PERSONA}} /
{{DIRECTOR_TITLE}} / {{MONTHLY_TARGET}} etc. At instantiation,
create_role_workspaces.fill_tokens() / build-workforce._instantiate_role_from_library()
replace these with per-client values AND inject volatile values (datetime.now()
for ISO_DATE/GENERATION_DATE, persona "(selected per task)"). So a hash of the
RENDERED client bytes differs for EVERY client AND drifts day-to-day even with an
unchanged library → massive false positives.

The fix: hash the CANONICAL LIBRARY CONTENT, with {{TOKENS}} LEFT INTACT (tokens
ARE the canonical content). Two identical templates produce an identical
content_sha regardless of which client they will later serve — eliminating
per-client false positives by construction.

──────────────────────────────────────────────────────────────────────────────
HASHING PIPELINE (content_sha — the PRIMARY hash; detection compares THIS)
──────────────────────────────────────────────────────────────────────────────
For each canonical artifact:
  a. read the library .md text as UTF-8.
  b. STRIP the provenance HTML-comment marker line(s) — any line matching
       ^<!--\\s*(Filled from role-library|WS-2: instantiated from role-library|
                workforce-provenance).*-->\\s*$
     so re-stamping the marker can never change the artifact's OWN hash
     (self-reference removal).
  c. NORMALIZE the volatile-but-non-content header fields by replacing their
     VALUE with the sentinel "<NORMALIZED>" BEFORE hashing:
       - "**Last updated:** <value>"  (whether {{ISO_DATE}} or a baked literal date)
       - "**Version:** <value>"       (the human header version line)
     Tokens themselves ({{COMPANY_NAME}} …) are LEFT INTACT — only realized
     volatile values (and the template's own header version/date) are normalized.
  d. NEWLINE-normalize (CRLF→LF) and strip a single trailing newline so editor /
     EOL noise is not a content change.
  e. content_sha = "sha256:" + sha256(resulting bytes).

NEUTRAL-RENDER CROSS-CHECK (render_sha — belt-and-suspenders, build-time only):
forward-render the template through create_role_workspaces.fill_tokens() with a
fixed NEUTRAL_CONFIG and a FROZEN clock (monkeypatch the module datetime so
ISO_DATE/GENERATION_DATE/MONTH/QUARTER/WEEK_NUMBER resolve to NEUTRAL_DATE
sentinels), then run the SAME normalization + sha. render_sha proves the template
renders DETERMINISTICALLY (no un-mapped {{token}} survives the neutral render,
no stray clock dependency). Detection uses content_sha; render_sha is a
manifest-build-time assertion only. If fill_tokens cannot be imported (e.g. a
hermetic CI without the build module) render_sha is recorded as "sha256:UNAVAILABLE"
and the --check token-leak assertion is skipped — content_sha is unaffected.

──────────────────────────────────────────────────────────────────────────────
WHAT GETS STAMPED
──────────────────────────────────────────────────────────────────────────────
roles[]      — every entry gets content_sha, render_sha, content_version,
               content_hashed_at (added next to slug/dept/title/…).
departments{}— each dept gets a content_sha computed as sha256 over the SORTED
               list of "<member-slug>\\t<member content_sha>" lines (a dept's
               content == its exact membership + each member's content). A dept
               goes STALE if a member is added/removed/renamed OR any member's
               content_sha changes.
sops[]       — NEW top-level array, one entry per dept-level SOP file under
               templates/role-library/<dept>/sops/*.md: {slug, dept, path,
               content_sha, content_version, content_hashed_at}. Hashed with the
               SAME normalized pipeline. (Per-role Section-9 SOPs live INSIDE each
               role's how-to.md, so they are already covered by that role's
               content_sha.)
personas[]   — NEW top-level array, one entry per canonical persona file under
               templates/persona-library/*.md: {slug, path, content_sha,
               content_version, content_hashed_at}. Personas are a SHARED LIBRARY
               (not per-client-rendered like each role's how-to.md): a client's
               per-department governing-personas.md is RENDERED at build time by
               filtering this shared pool through build-workforce.dept_to_domains.
               So the canonical content that can change underneath every client is
               the persona file itself — hashed here with the SAME normalized
               pipeline ({{TOKENS}} intact). A future edit to ONE persona flags
               ONLY that persona for ONLY the clients built against the old sha.
content_manifest{} — NEW top-level self-describing header: {algo, normalize[],
               neutral_config_sha, neutral_date, generator, generated_at,
               manifest_schema} so a detector can refuse a manifest built by an
               incompatible algo.

VERSION semantics: content_version defaults to "1.0.0" and is PATCH-bumped (z+1)
automatically when the freshly-computed content_sha differs from the prior
manifest's stored content_sha for that artifact key. content_sha is the machine
truth; content_version is the human-facing label.

──────────────────────────────────────────────────────────────────────────────
USAGE
──────────────────────────────────────────────────────────────────────────────
    python3 hash-content-manifest.py                 # stamp in place
    python3 hash-content-manifest.py --dry-run        # compute, do not write
    python3 hash-content-manifest.py --summary         # print stats only
    python3 hash-content-manifest.py --check           # assert manifest is
                                                        # complete + not stale
                                                        # vs files; rc 1 on drift
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ─── PATH SETUP ───────────────────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent                       # 23-ai-workforce-blueprint/
_REPO_ROOT = _SKILL_DIR.parent                        # repo root
_LIBRARY_DIR = _SKILL_DIR / "templates" / "role-library"
_PERSONA_LIBRARY_DIR = _SKILL_DIR / "templates" / "persona-library"
_INDEX_PATH = _LIBRARY_DIR / "_index.json"

MANIFEST_SCHEMA = "1.0"
DEFAULT_CONTENT_VERSION = "1.0.0"

# Neutral render config + frozen clock sentinels (render_sha cross-check).
NEUTRAL_CONFIG = {
    "companyName": "<COMPANY>",
    "industry": "<INDUSTRY>",
    "ownerName": "<OWNER>",
    "yearlyRevenueGoal": "<YEARLY>",
    "connectedSystems": [],
}
NEUTRAL_DATE = "2000-01-01"

# Canonical token form per _token-reference.md: double-brace, UPPERCASE,
# underscore-separated, >= 2 alnum chars (e.g. {{COMPANY_NAME}}, {{ISO_DATE}},
# {{AMOUNT}}). This is the ONLY form fill_tokens is responsible for resolving.
# The render-determinism (token-leak) check uses THIS so it bites on a genuine
# un-mapped canonical token while NOT false-positiving on illustrative content
# placeholders the library legitimately contains in example reports/prose
# (single-letter math vars {{X}}/{{N}}, Title-Case merge-tag examples like
# "Hi {{First Name}}") — those are canonical CONTENT, not fill tokens.
_CANONICAL_TOKEN_RE = re.compile(
    r"\{\{[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\}\}|\{\{[A-Z][A-Z0-9]{2,}\}\}")


def _canonical_leaks(rendered):
    """Return sorted unique canonical-form {{TOKEN}}s surviving a neutral render."""
    return sorted(set(_CANONICAL_TOKEN_RE.findall(rendered)))


# ─── NORMALIZATION PIPELINE ───────────────────────────────────────────────────

# (b) Provenance HTML-comment marker(s). Self-reference removal so re-stamping the
# marker can never change the artifact's own hash. Matches the LEGACY markers
# ("Filled from role-library", "WS-2: instantiated from role-library") AND the
# new "workforce-provenance" marker this versioning system writes at instantiation.
_PROVENANCE_RE = re.compile(
    r"^<!--\s*(Filled from role-library|WS-2: instantiated from role-library|"
    r"workforce-provenance).*-->\s*$",
    re.IGNORECASE,
)

# (c) Volatile header fields — replace the VALUE with the sentinel. These are the
# template's own header version/date that drift on a re-generation without the
# canonical content changing. Tokens elsewhere are left intact.
_HEADER_LASTUPDATED_RE = re.compile(r"^(\*\*Last updated:\*\*)\s*.*$")
_HEADER_VERSION_RE = re.compile(r"^(\*\*Version:\*\*)\s*.*$")
_NORMALIZED = "<NORMALIZED>"


def normalize_canonical(text):
    """
    Apply the canonical-source normalization pipeline (steps b-d) to template
    text and return the normalized bytes ready for sha256.

      b. strip provenance marker line(s)
      c. normalize the **Last updated:** / **Version:** header VALUES to <NORMALIZED>
      d. CRLF→LF, strip one trailing newline
    """
    # (d-pre) unify newlines first so line-based regexes are EOL-agnostic.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out_lines = []
    for line in text.split("\n"):
        if _PROVENANCE_RE.match(line):
            continue  # (b) drop provenance marker
        m = _HEADER_LASTUPDATED_RE.match(line)
        if m:
            out_lines.append(f"{m.group(1)} {_NORMALIZED}")
            continue
        m = _HEADER_VERSION_RE.match(line)
        if m:
            out_lines.append(f"{m.group(1)} {_NORMALIZED}")
            continue
        out_lines.append(line)
    normalized = "\n".join(out_lines)
    # (d) strip a single trailing newline (editor/EOL noise is not a content change)
    if normalized.endswith("\n"):
        normalized = normalized[:-1]
    return normalized.encode("utf-8")


def content_sha_of_text(text):
    """content_sha = 'sha256:' + sha256(normalize_canonical(text))."""
    digest = hashlib.sha256(normalize_canonical(text)).hexdigest()
    return f"sha256:{digest}"


def content_sha_of_file(path):
    """Read a library .md as UTF-8 and return its canonical content_sha."""
    text = Path(path).read_text(encoding="utf-8")
    return content_sha_of_text(text), text


# ─── NEUTRAL-RENDER CROSS-CHECK (render_sha) ──────────────────────────────────

_FILL_TOKENS = None
_FILL_TOKENS_MOD = None
_FILL_TOKENS_ERR = None


def _load_fill_tokens():
    """
    Import create_role_workspaces.fill_tokens (and its module, for clock
    monkeypatching). Returns (fill_tokens_callable_or_None). Best-effort — a
    hermetic CI without the build module simply records render_sha as UNAVAILABLE.
    """
    global _FILL_TOKENS, _FILL_TOKENS_MOD, _FILL_TOKENS_ERR
    if _FILL_TOKENS is not None or _FILL_TOKENS_ERR is not None:
        return _FILL_TOKENS
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_crw_for_render_sha", str(_SCRIPT_DIR / "create_role_workspaces.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _FILL_TOKENS = getattr(mod, "fill_tokens", None)
        _FILL_TOKENS_MOD = mod
        if _FILL_TOKENS is None:
            _FILL_TOKENS_ERR = "fill_tokens not found in create_role_workspaces"
    except Exception as e:  # noqa: BLE001
        _FILL_TOKENS_ERR = str(e)
        _FILL_TOKENS = None
    return _FILL_TOKENS


class _FrozenDatetime:
    """A datetime stand-in whose now()/utcnow() always return NEUTRAL_DATE."""
    _FROZEN = datetime(2000, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls._FROZEN if tz is None else cls._FROZEN.astimezone(tz)

    @classmethod
    def utcnow(cls):
        return cls._FROZEN.replace(tzinfo=None)

    # Pass through everything else the module might use.
    def __getattr__(self, name):  # pragma: no cover - defensive
        return getattr(datetime, name)


def render_sha_of_text(text, role_name, dept_name, is_ceo):
    """
    Forward-render `text` through fill_tokens() with NEUTRAL_CONFIG + a FROZEN
    clock, then run the same normalization + sha. Returns 'sha256:<...>' or
    'sha256:UNAVAILABLE' if fill_tokens cannot be loaded.

    Determinism is enforced by (1) the neutral config (no per-client values) and
    (2) the frozen clock (monkeypatch the module's `datetime` so ISO_DATE /
    GENERATION_DATE / MONTH / QUARTER / WEEK_NUMBER resolve to the NEUTRAL_DATE
    sentinels). The neutral config is fed via OPENCLAW_* env so fill_tokens'
    company-config loader sees it without requiring a real workspace on disk.
    """
    ft = _load_fill_tokens()
    if ft is None:
        return "sha256:UNAVAILABLE"

    mod = _FILL_TOKENS_MOD

    # Monkeypatch the module clock + the company-config loader for a hermetic,
    # deterministic neutral render. Restore both afterward.
    orig_dt = getattr(mod, "datetime", None)
    orig_loader = getattr(mod, "_load_company_config", None)
    try:
        if orig_dt is not None:
            mod.datetime = _FrozenDatetime
        if orig_loader is not None:
            mod._load_company_config = lambda: dict(NEUTRAL_CONFIG)
        rendered = ft(text, role_name, dept_name, is_ceo, role_entry=None)
    except Exception:  # noqa: BLE001 - render failure must not abort the manifest
        return "sha256:UNAVAILABLE"
    finally:
        if orig_dt is not None:
            mod.datetime = orig_dt
        if orig_loader is not None:
            mod._load_company_config = orig_loader

    digest = hashlib.sha256(normalize_canonical(rendered)).hexdigest()
    return f"sha256:{digest}", rendered


# ─── EMBEDDED SOP LINKAGE (sop_count / sop_min) ───────────────────────────────
# C9 fix (role-library index misreported SOP linkage): roles[].sop_count and
# .sop_min were hardcoded to 0 at role-registration time
# (register-library-additions.py._derive_role_meta) and NEVER revisited, so
# the index silently claimed zero SOP linkage for every role even though most
# roles embed real "### SOP 9.x" Section-9 content in their own how-to.md
# (393/433 roles at the time of this fix). This is a raw STRUCTURAL count of a
# role's OWN canonical text for LIBRARY-INDEX reporting — deliberately NOT the
# substantive DMAIC/field-shape gate qc-completeness.sh applies to a LIVE
# INSTANTIATED client workspace (different data model: this hashes the
# dept-shared role-library template, not a client's rendered/numbered
# workspace sops/ folder). EMBEDDED_SOP_FLOOR mirrors qc-completeness.sh's
# own EMBEDDED_SOP_FLOOR constant (=1); test-library-register.sh's
# consistency fixture cross-checks the two never drift apart.
_EMBEDDED_SOP_HEADING_RE = re.compile(r"^###\s*SOP\b", re.MULTILINE)
EMBEDDED_SOP_FLOOR = 1


def count_embedded_sop_headings(text):
    """Count '### SOP ...' headings in a role's canonical .md text — the
    library-index-level embedded SOP linkage count (see module note above)."""
    return len(_EMBEDDED_SOP_HEADING_RE.findall(text))


def neutral_config_sha():
    """Stable sha of the NEUTRAL_CONFIG + NEUTRAL_DATE (for the manifest header)."""
    payload = json.dumps(
        {"config": NEUTRAL_CONFIG, "neutral_date": NEUTRAL_DATE},
        sort_keys=True, ensure_ascii=False,
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ─── VERSION BUMP ─────────────────────────────────────────────────────────────

def _bump_patch(version):
    """Patch-bump x.y.z → x.y.(z+1). Returns DEFAULT on a malformed string."""
    try:
        parts = str(version).split(".")
        if len(parts) != 3:
            return DEFAULT_CONTENT_VERSION
        major, minor, patch = (int(p) for p in parts)
        return f"{major}.{minor}.{patch + 1}"
    except (ValueError, TypeError):
        return DEFAULT_CONTENT_VERSION


def _resolve_version(prior_version, prior_sha, new_sha, override):
    """
    Resolve content_version for an artifact.

      - explicit override (from a header) always wins.
      - first-time (no prior) → DEFAULT_CONTENT_VERSION.
      - sha unchanged → keep prior version.
      - sha changed → patch-bump the prior version.
    """
    if override:
        return override
    if not prior_version:
        return DEFAULT_CONTENT_VERSION
    if prior_sha == new_sha:
        return prior_version
    return _bump_patch(prior_version)


# ─── SOP DISCOVERY ────────────────────────────────────────────────────────────

def discover_dept_sops():
    """
    Find every dept-level SOP file under templates/role-library/<dept>/sops/*.md.
    Returns a sorted list of dicts {slug, dept, path(rel-to-skill-dir), abspath}.
    Per-role Section-9 SOPs live INSIDE each role's how-to.md (covered by that
    role's content_sha), so only the dedicated dept-level sops/ dirs are scanned.
    """
    out = []
    for sops_dir in sorted(_LIBRARY_DIR.glob("*/sops")):
        if not sops_dir.is_dir():
            continue
        dept = sops_dir.parent.name
        for md in sorted(sops_dir.glob("*.md")):
            rel = md.relative_to(_SKILL_DIR).as_posix()
            out.append({
                "slug": md.stem,
                "dept": dept,
                "path": rel,
                "abspath": md,
            })
    return out


# ─── PERSONA DISCOVERY ────────────────────────────────────────────────────────

def discover_personas():
    """
    Find every canonical persona file under templates/persona-library/*.md.
    Returns a sorted list of dicts {slug, path(rel-to-skill-dir), abspath}.

    Personas are a SHARED LIBRARY (not per-client-rendered the way each role's
    how-to.md is). A client's per-department governing-personas.md is RENDERED at
    build time by filtering this shared pool through build-workforce.dept_to_domains,
    so the canonical content that can change underneath every client is the persona
    file itself. We therefore hash each persona file with the SAME canonical-source
    pipeline as roles/SOPs and record which persona content_sha(s) each client built
    against (see build-workforce artifactProvenance.personas + detect-stale-artifacts).
    Files beginning with "_" (templates/manifest sidecars) are skipped.
    """
    out = []
    if not _PERSONA_LIBRARY_DIR.is_dir():
        return out
    for md in sorted(_PERSONA_LIBRARY_DIR.glob("*.md")):
        if md.name.startswith("_"):
            continue
        rel = md.relative_to(_SKILL_DIR).as_posix()
        out.append({
            "slug": md.stem,
            "path": rel,
            "abspath": md,
        })
    return out


# ─── MAIN STAMPING ────────────────────────────────────────────────────────────

def _load_index(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_index(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def stamp_manifest(data, do_render=True):
    """
    Compute + stamp content_sha/render_sha/content_version/content_hashed_at onto
    roles[], dept content_shas into departments{}, the sops[] array, and the
    content_manifest{} header. Mutates `data` in place. Returns a stats dict.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    stats = {
        "roles_hashed": 0, "roles_missing": [], "roles_bumped": 0,
        "sops_hashed": 0, "depts_hashed": 0, "personas_hashed": 0,
        "render_unavailable": 0, "token_leaks": [],
        "roles_below_sop_floor": 0,
    }

    # ── roles[] ───────────────────────────────────────────────────────────────
    sha_by_slug = {}  # "<dept>/<slug>" -> content_sha (for dept rollup)
    for role in data.get("roles", []):
        slug = role.get("slug", "")
        dept = role.get("dept", "")
        rel = role.get("path", "")
        abspath = _SKILL_DIR / rel
        key = f"{dept}/{slug}"
        if not abspath.is_file():
            stats["roles_missing"].append(rel)
            # Leave any prior hash in place; record an explicit MISSING marker so
            # the gate can flag it rather than silently producing a stale sha.
            role["content_sha"] = role.get("content_sha", "sha256:MISSING")
            continue
        new_sha, text = content_sha_of_file(abspath)
        prior_sha = role.get("content_sha")
        prior_ver = role.get("content_version")
        override = role.get("content_version_override")
        new_ver = _resolve_version(prior_ver, prior_sha, new_sha, override)
        if prior_sha and prior_sha != new_sha and not override:
            stats["roles_bumped"] += 1

        is_ceo = (dept == "master-orchestrator")
        role_title = role.get("title", slug)
        dept_display = dept.replace("-", " ").title()
        if do_render:
            r = render_sha_of_text(text, role_title, dept_display, is_ceo)
            if isinstance(r, tuple):
                rsha, rendered = r
                leaks = _canonical_leaks(rendered)
                if leaks:
                    stats["token_leaks"].append((key, leaks[:8]))
            else:
                rsha = r
                if rsha == "sha256:UNAVAILABLE":
                    stats["render_unavailable"] += 1
        else:
            rsha = role.get("render_sha", "sha256:UNAVAILABLE")

        role["content_sha"] = new_sha
        role["render_sha"] = rsha
        role["content_version"] = new_ver
        role["content_hashed_at"] = now_iso
        # C9 fix: refresh SOP linkage from the SAME text already read for the
        # content hash, for EVERY role (new or existing) on every stamp pass —
        # this self-heals the historical hardcoded-0 ghost values and keeps
        # sop_count/sop_min from drifting silently as role content changes.
        role["sop_count"] = count_embedded_sop_headings(text)
        role["sop_min"] = EMBEDDED_SOP_FLOOR
        if role["sop_count"] < role["sop_min"]:
            stats["roles_below_sop_floor"] += 1
        sha_by_slug[key] = new_sha
        sha_by_slug.setdefault(slug, new_sha)  # bare-slug alias for dept rollup
        stats["roles_hashed"] += 1

    # ── departments{} content_sha ──────────────────────────────────────────────
    depts = data.get("departments", {})
    if isinstance(depts, dict):
        for dept_id, dept_obj in depts.items():
            if not isinstance(dept_obj, dict):
                continue
            members = sorted(dept_obj.get("roles", []) or [])
            lines = []
            for m in members:
                msha = sha_by_slug.get(f"{dept_id}/{m}") or sha_by_slug.get(m) or "sha256:MISSING"
                lines.append(f"{m}\t{msha}")
            payload = "\n".join(lines).encode("utf-8")
            dept_obj["content_sha"] = "sha256:" + hashlib.sha256(payload).hexdigest()
            dept_obj["content_hashed_at"] = now_iso
            stats["depts_hashed"] += 1

    # ── sops[] (NEW top-level array) ────────────────────────────────────────────
    prior_sops = {s.get("path"): s for s in data.get("sops", []) if isinstance(s, dict)}
    sops_out = []
    for sop in discover_dept_sops():
        new_sha, _text = content_sha_of_file(sop["abspath"])
        prev = prior_sops.get(sop["path"], {})
        prior_sha = prev.get("content_sha")
        prior_ver = prev.get("content_version")
        new_ver = _resolve_version(prior_ver, prior_sha, new_sha, prev.get("content_version_override"))
        if prior_sha and prior_sha != new_sha:
            stats["roles_bumped"] += 1
        sops_out.append({
            "slug": sop["slug"],
            "dept": sop["dept"],
            "path": sop["path"],
            "content_sha": new_sha,
            "content_version": new_ver,
            "content_hashed_at": now_iso,
        })
        stats["sops_hashed"] += 1
    data["sops"] = sops_out

    # ── personas[] (NEW top-level array) ────────────────────────────────────────
    # The canonical persona library is a SHARED pool, hashed with the SAME normalized
    # canonical pipeline as roles/SOPs ({{TOKENS}} left intact). Each persona file
    # gets {slug, path, content_sha, content_version, content_hashed_at}. A persona
    # entry's content_sha changes only when that persona .md's canonical content
    # changes — so a future edit to ONE persona flags ONLY that persona for ONLY the
    # clients that built against the old sha (no per-client/day false positives).
    prior_personas = {p.get("path"): p for p in data.get("personas", []) if isinstance(p, dict)}
    personas_out = []
    for persona in discover_personas():
        new_sha, _text = content_sha_of_file(persona["abspath"])
        prev = prior_personas.get(persona["path"], {})
        prior_sha = prev.get("content_sha")
        prior_ver = prev.get("content_version")
        new_ver = _resolve_version(prior_ver, prior_sha, new_sha, prev.get("content_version_override"))
        if prior_sha and prior_sha != new_sha:
            stats["roles_bumped"] += 1
        personas_out.append({
            "slug": persona["slug"],
            "path": persona["path"],
            "content_sha": new_sha,
            "content_version": new_ver,
            "content_hashed_at": now_iso,
        })
        stats["personas_hashed"] += 1
    data["personas"] = personas_out

    # ── content_manifest{} self-describing header ──────────────────────────────
    data["content_manifest"] = {
        "algo": "sha256",
        "normalize": [
            "strip-provenance-marker",
            "normalize-header-version-and-date",
            "lf-newlines",
            "strip-trailing-nl",
        ],
        "neutral_config_sha": neutral_config_sha(),
        "neutral_date": NEUTRAL_DATE,
        "generator": "hash-content-manifest.py",
        "generated_at": now_iso,
        "manifest_schema": MANIFEST_SCHEMA,
    }
    return stats


# ─── --check MODE ─────────────────────────────────────────────────────────────

def check_manifest(data, do_render=True):
    """
    Assert the manifest is COMPLETE and NOT STALE vs the live library files:
      (a) every roles[]/sops[] entry HAS content_sha + content_version
      (b) each stored content_sha EQUALS a freshly recomputed one (not stale)
      (c) the content_manifest header is present + uses the expected algo/schema
      (d) render_sha recomputes with no surviving un-mapped {{token}} (when the
          render module is available)
    Returns (ok: bool, problems: list[str]).
    """
    problems = []

    cm = data.get("content_manifest")
    if not isinstance(cm, dict):
        problems.append("content_manifest header MISSING (run hash-content-manifest.py)")
    else:
        if cm.get("algo") != "sha256":
            problems.append(f"content_manifest.algo is {cm.get('algo')!r}, expected 'sha256'")
        if cm.get("manifest_schema") != MANIFEST_SCHEMA:
            problems.append(
                f"content_manifest.manifest_schema is {cm.get('manifest_schema')!r}, "
                f"expected {MANIFEST_SCHEMA!r}")

    # roles
    for role in data.get("roles", []):
        slug = role.get("slug", "?")
        dept = role.get("dept", "?")
        key = f"{dept}/{slug}"
        rel = role.get("path", "")
        if not role.get("content_sha"):
            problems.append(f"role {key}: MISSING content_sha")
            continue
        if not role.get("content_version"):
            problems.append(f"role {key}: MISSING content_version")
        abspath = _SKILL_DIR / rel
        if not abspath.is_file():
            problems.append(f"role {key}: file not found ({rel})")
            continue
        fresh, text = content_sha_of_file(abspath)
        if fresh != role["content_sha"]:
            problems.append(
                f"role {key}: STALE content_sha (stored {role['content_sha'][:18]}…, "
                f"file {fresh[:18]}…) — re-run hash-content-manifest.py")
        if do_render:
            r = render_sha_of_text(
                text, role.get("title", slug), dept.replace("-", " ").title(),
                dept == "master-orchestrator")
            if isinstance(r, tuple):
                _rsha, rendered = r
                leaks = _canonical_leaks(rendered)
                if leaks:
                    problems.append(
                        f"role {key}: TOKEN LEAK — un-mapped canonical token(s) survive "
                        f"the neutral render: {leaks[:6]}")

    # sops
    for sop in data.get("sops", []):
        key = f"{sop.get('dept','?')}/{sop.get('slug','?')}"
        rel = sop.get("path", "")
        if not sop.get("content_sha"):
            problems.append(f"sop {key}: MISSING content_sha")
            continue
        if not sop.get("content_version"):
            problems.append(f"sop {key}: MISSING content_version")
        abspath = _SKILL_DIR / rel
        if not abspath.is_file():
            problems.append(f"sop {key}: file not found ({rel})")
            continue
        fresh, _ = content_sha_of_file(abspath)
        if fresh != sop["content_sha"]:
            problems.append(
                f"sop {key}: STALE content_sha — re-run hash-content-manifest.py")

    # Coverage: every dept-level sops/ file on disk must be in the manifest.
    manifest_sop_paths = {s.get("path") for s in data.get("sops", [])}
    for sop in discover_dept_sops():
        if sop["path"] not in manifest_sop_paths:
            problems.append(f"sop {sop['dept']}/{sop['slug']}: present on disk but ABSENT from manifest sops[]")

    # personas (canonical persona library — shared pool)
    for persona in data.get("personas", []):
        key = persona.get("slug", "?")
        rel = persona.get("path", "")
        if not persona.get("content_sha"):
            problems.append(f"persona {key}: MISSING content_sha")
            continue
        if not persona.get("content_version"):
            problems.append(f"persona {key}: MISSING content_version")
        abspath = _SKILL_DIR / rel
        if not abspath.is_file():
            problems.append(f"persona {key}: file not found ({rel})")
            continue
        fresh, _ = content_sha_of_file(abspath)
        if fresh != persona["content_sha"]:
            problems.append(
                f"persona {key}: STALE content_sha — re-run hash-content-manifest.py")

    # Coverage: every persona-library file on disk must be in the manifest.
    manifest_persona_paths = {p.get("path") for p in data.get("personas", [])}
    for persona in discover_personas():
        if persona["path"] not in manifest_persona_paths:
            problems.append(f"persona {persona['slug']}: present on disk but ABSENT from manifest personas[]")

    return (len(problems) == 0), problems


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Stamp per-artifact content_sha + version into _index.json "
                    "(canonical-source hash; no per-client false positives).")
    parser.add_argument("--index", default=str(_INDEX_PATH),
                        help=f"Path to _index.json (default: {_INDEX_PATH})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute hashes but do not write the index.")
    parser.add_argument("--summary", action="store_true",
                        help="Print stats without modifying anything.")
    parser.add_argument("--check", action="store_true",
                        help="Assert the manifest is complete + not stale vs the "
                             "live files; exit 1 on any drift (CI / gate mode).")
    parser.add_argument("--no-render", action="store_true",
                        help="Skip the render_sha neutral-render cross-check "
                             "(faster; content_sha is unaffected).")
    args = parser.parse_args(argv)

    index_path = Path(args.index)
    if not index_path.is_file():
        print(f"ERROR: _index.json not found at {index_path}", file=sys.stderr)
        return 2

    data = _load_index(index_path)
    do_render = not args.no_render

    # ── --check: validate, do not write ────────────────────────────────────────
    if args.check:
        ok, problems = check_manifest(data, do_render=do_render)
        n_roles = len(data.get("roles", []))
        n_sops = len(data.get("sops", []))
        n_personas = len(data.get("personas", []))
        if ok:
            print(f"✓ content-manifest CHECK PASS — {n_roles} roles + {n_sops} sops "
                  f"+ {n_personas} personas all carry content_sha/content_version; "
                  f"every stored sha matches the live file; no token leaks.")
            return 0
        print(f"✗ content-manifest CHECK FAIL — {len(problems)} problem(s):", file=sys.stderr)
        for p in problems[:60]:
            print(f"    - {p}", file=sys.stderr)
        if len(problems) > 60:
            print(f"    … and {len(problems) - 60} more", file=sys.stderr)
        return 1

    # ── stamp (compute) ─────────────────────────────────────────────────────────
    stats = stamp_manifest(data, do_render=do_render)

    print(f"content-manifest stamped over {index_path}")
    print(f"  roles hashed:        {stats['roles_hashed']}")
    print(f"  dept content_shas:   {stats['depts_hashed']}")
    print(f"  dept-level sops:     {stats['sops_hashed']}")
    print(f"  personas hashed:     {stats['personas_hashed']}")
    print(f"  content_versions bumped (sha changed): {stats['roles_bumped']}")
    print(f"  roles below embedded-SOP floor ({EMBEDDED_SOP_FLOOR}): {stats['roles_below_sop_floor']}")
    if stats["roles_missing"]:
        print(f"  WARNING: {len(stats['roles_missing'])} role path(s) not found on disk:")
        for m in stats["roles_missing"][:10]:
            print(f"      - {m}")
    if do_render and stats["render_unavailable"]:
        print(f"  NOTE: render_sha UNAVAILABLE for {stats['render_unavailable']} role(s) "
              f"(fill_tokens not importable — content_sha unaffected).")
    if stats["token_leaks"]:
        print(f"  WARNING: {len(stats['token_leaks'])} role(s) leak un-mapped token(s) "
              f"under the neutral render:")
        for key, leaks in stats["token_leaks"][:10]:
            print(f"      - {key}: {leaks}")

    if args.summary or args.dry_run:
        print("\n  [DRY RUN] Index NOT written." if args.dry_run else "\n  [SUMMARY] Index NOT written.")
        return 0

    _save_index(index_path, data)
    print(f"\n  Written: {index_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
