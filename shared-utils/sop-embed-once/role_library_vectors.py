#!/usr/bin/env python3
"""Central vectors for the Command Center's role-library SOP rows.

The CC's importRoleLibrary() (src/lib/role-library-import.ts) writes one `sops`
row per role how-to.md, slug `role-library:<dept>/<role>`, with a random id and
NO embedding (CC #416: a per-box embed would bill the client's key). This module
builds those vectors ONCE, centrally, into the shipped asset's
`role_library_embeddings` table keyed by that exact slug; provision_sop_embeddings
maps them onto each box's local sops.id BY SLUG.

Source: every role in templates/role-library/_index.json, rendered through the
SAME fill_tokens() a box uses to write how-to.md (hash-content-manifest's
neutral render: neutral company values, frozen clock), then parsed exactly as
parseRoleHowTo() parses it. Per-client token values (company name etc.) are the
one thing a central build cannot know; everything else is the box's own text.

Box role folders are named by the build generation that wrote them, so each role
is published under every slug a box is known to use (see role_slug_aliases);
aliases are checked unique per department. Each alias gets its own vector
because parseRoleHowTo puts the role slug into task_keywords.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sqlite3
import sys
from pathlib import Path

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))
from embed_sop_library import build_sop_embed_text, _md5, _vector_to_blob  # noqa: E402

SOURCE = "role-library"  # role-library-import.ts ROLE_LIBRARY_SOURCE
DOT = r"[^\n\r\u2028\u2029]"  # JS `.`: never matches a line terminator

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS role_library_embeddings (
    slug               TEXT PRIMARY KEY,
    embedding          BLOB NOT NULL,
    embedding_model    TEXT NOT NULL,
    embedding_dims     INTEGER NOT NULL,
    embedded_at        TEXT NOT NULL,
    source_content_md5 TEXT
);
"""

_SOP_SECTION_ANCHOR = re.compile(
    r"^#{1,3}\s+(section\s*9\b|9\s*[.:)]|9\s+[-–—]\s|9\s+(sops?\b|standard\s+operating)"
    r"|sops?\b|standard\s+operating\s+procedures?\b)", re.I)


# ── parseRoleHowTo() port (role-library-import.ts) ────────────────────────────
def extract_title(markdown: str, fallback: str) -> str:
    for pat in (r"^#\s+(" + DOT + r"+)$", r"^##\s+(" + DOT + r"+)$"):
        m = re.search(pat, markdown, re.M)
        if m:
            return m.group(1).strip()
    return " ".join(w[:1].upper() + w[1:] for w in re.split(r"[-_]", fallback))


def extract_step_names(markdown: str, role: str) -> list[str]:
    lines = markdown.split("\n")
    start = next((i for i, l in enumerate(lines) if _SOP_SECTION_ANCHOR.match(l)), -1)
    headings = []
    for i, l in enumerate(lines):
        m = re.fullmatch(r"(#{2,4})\s+(" + DOT + r"+)", l)
        if m:
            headings.append((len(m.group(1)), m.group(2).strip(), i))
    if start >= 0:
        anchor = len(re.match(r"#{1,3}", lines[start]).group(0))
        steps = [(t, i) for lvl, t, i in headings if i > start and lvl > anchor]
        if not steps:
            steps = [(t, i) for _, t, i in headings if i != 0]
    else:
        steps = [(t, i) for _, t, i in headings]
    title = extract_title(markdown, role).lower()
    steps = [(t, i) for t, i in steps if t.lower() != title]
    if not steps:
        return [f"Follow {role} how-to"]
    strip = re.compile(r"^sop\s*\d+(\.\d+)?\s*[:.-]?\s*", re.I)
    return [f"{n + 1}. {strip.sub('', t, count=1)[:120]}" for n, (t, _) in enumerate(steps[:25])]


def extract_description(markdown: str) -> str:
    for raw in markdown.split("\n"):
        l = raw.strip()
        if not l or l.startswith("#") or l.startswith(">"):
            continue
        return re.sub(r"^[-*]\s+", "", l, count=1)[:280]
    return ""


def parse_role_howto(markdown: str, department: str, role: str) -> dict:
    words = [role, department, *re.split(r"[-_]", role)]
    keywords = list(dict.fromkeys(k.lower().strip() for k in words if len(k.lower().strip()) >= 3))
    return {
        "slug": f"{SOURCE}:{department}/{role}",
        "name": extract_title(markdown, role),
        "description": extract_description(markdown) or f"Role library SOP for {role} ({department}).",
        "task_keywords": ",".join(keywords),
        "steps": [{"name": n} for n in extract_step_names(markdown, role)],
    }


# ── inventory + neutral render ───────────────────────────────────────────────
def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def role_slug_aliases(entry: dict, slugify) -> set[str]:
    """Role-folder slugs box builds have used for this library role (measured on
    live boxes 2026-09-23): the index slug, its dash-collapsed form, slugify(title),
    and the collapsed form without a trailing -<dept> (e.g. devils-advocate)."""
    collapsed = re.sub(r"-+", "-", entry["slug"])
    out = {entry["slug"], collapsed, slugify(entry["title"])}
    if collapsed.endswith("-" + entry["dept"]):
        out.add(collapsed[: -len(entry["dept"]) - 1])
    return {a for a in out if a}


def role_records(role_library: Path) -> tuple[list[dict], int]:
    """One parsed record per (department, alias). Returns (records, render_fallbacks)."""
    scripts = role_library.parent.parent / "scripts"
    crw = _load(scripts / "create_role_workspaces.py", "_rlv_crw")
    hcm = _load(scripts / "hash-content-manifest.py", "_rlv_hcm")
    index = json.loads((role_library / "_index.json").read_text(encoding="utf-8"))

    owners: dict[tuple[str, str], set[str]] = {}
    for e in index["roles"]:
        for a in role_slug_aliases(e, crw.slugify):
            owners.setdefault((e["dept"], a), set()).add(e["slug"])
    clash = {k: v for k, v in owners.items() if len(v) > 1}
    if clash:
        raise SystemExit(f"FATAL: role alias maps to two roles: {sorted(clash)[:3]}")

    records, fallbacks = [], 0
    for e in index["roles"]:
        raw = (role_library.parent.parent / e["path"]).read_text(encoding="utf-8")
        dept_name = e["dept"].replace("-", " ").title()
        is_ceo = e["slug"] == "master-orchestrator"
        res = hcm.render_sha_of_text(raw, e["title"], dept_name, is_ceo)
        if isinstance(res, tuple):
            text = res[1]
        else:  # neutral render unavailable: tokens left intact
            text, fallbacks = raw, fallbacks + 1
        for alias in sorted(role_slug_aliases(e, crw.slugify)):
            records.append(parse_role_howto(text, e["dept"], alias))
    return records, fallbacks


# ── embed (HASH-SKIP, same contract as embed_sop_library.embed_delta) ─────────
def embed_roles(conn: sqlite3.Connection, records: list[dict], embed_fn=None, dry_run=False) -> dict:
    conn.executescript(SCHEMA_SQL)
    stats = {"embedded": 0, "skipped_unchanged": 0, "errors": 0}
    real = None
    if embed_fn is None and not dry_run:
        from embedding_engine import GEMINI_OUTPUT_DIM, get_embedder, get_embedding, _assert_vector_dim
        real = get_embedder(provider_hint="gemini")
    for rec in records:
        text = build_sop_embed_text(rec)
        md5 = _md5(text)
        row = conn.execute("SELECT source_content_md5 FROM role_library_embeddings WHERE slug=?",
                           (rec["slug"],)).fetchone()
        if row is not None and row[0] == md5:
            stats["skipped_unchanged"] += 1
            continue
        if dry_run:
            stats["embedded"] += 1
            continue
        try:
            if embed_fn is not None:
                from embedding_engine import GEMINI_MODEL
                vec, model = embed_fn(text), GEMINI_MODEL
                blob, dim = _vector_to_blob(vec), len(vec)
            else:
                provider, _client, model = real
                vec = get_embedding(real, text)
                _assert_vector_dim(vec, GEMINI_OUTPUT_DIM, provider, model)
                blob, dim = vec.astype("float32").tobytes(), int(vec.shape[0])
            conn.execute(
                """INSERT INTO role_library_embeddings
                       (slug, embedding, embedding_model, embedding_dims, embedded_at, source_content_md5)
                   VALUES (?, ?, ?, ?, datetime('now'), ?)
                   ON CONFLICT(slug) DO UPDATE SET embedding=excluded.embedding,
                       embedding_model=excluded.embedding_model, embedding_dims=excluded.embedding_dims,
                       embedded_at=excluded.embedded_at, source_content_md5=excluded.source_content_md5""",
                (rec["slug"], blob, model, dim, md5))
            stats["embedded"] += 1
        except Exception as exc:  # noqa: BLE001 - surfaced in stats
            stats["errors"] += 1
            print(f"  [role-library-vectors] ERROR slug={rec['slug']}: {exc}", file=sys.stderr)
    # Drop aliases no longer produced (a renamed/retired role), so the asset never ships stale slugs.
    live = {r["slug"] for r in records}
    stale = [s for (s,) in conn.execute("SELECT slug FROM role_library_embeddings") if s not in live]
    if not dry_run:
        conn.executemany("DELETE FROM role_library_embeddings WHERE slug=?", [(s,) for s in stale])
    stats["removed_stale"] = len(stale)
    conn.commit()
    return stats


def verify(conn: sqlite3.Connection, model: str, dim: int) -> tuple[bool, str]:
    conn.executescript(SCHEMA_SQL)
    rows = conn.execute("SELECT slug, embedding_model, embedding_dims, length(embedding) "
                        "FROM role_library_embeddings").fetchall()
    bad = [r for r in rows if r[1] != model or r[2] != dim or r[3] != dim * 4]
    if bad:
        return False, f"{len(bad)} bad role-library row(s), e.g. {bad[:3]}"
    return True, f"all {len(rows)} role-library row(s) verified {model}/{dim}"

