#!/usr/bin/env python3
"""Build the canonical SOP library release asset (sops-library-v3.jsonl.gz).

The V2 library (release v10.13.29, 2,618 records) was curated in Notion and
exported once; no generator for it exists in this repo or the VPS repo. So this
builder never regenerates those records: it copies every V2 line VERBATIM (same
slug => same `sops.id` on every box => a pure upsert, never a duplicate) and
APPENDS one record per department SOP file under
23-ai-workforce-blueprint/templates/role-library/<dept>/sops/*.md -- the 145
files `_index.json sops[]` lists, none of which were ever in the asset.

Build once, centrally; boxes only download + upsert (ingest-sop-library.py) and
download vectors (sop-embed-once). Zero per-box parsing, zero client-key cost.

Usage:
  build_sop_library.py --base V2.jsonl.gz --base-sha256 SHA \
      --role-library DIR --out sops-library-v3.jsonl.gz
Prints a JSON summary (counts, new slugs, sha256) on stdout.
"""
import argparse
import gzip
import hashlib
import io
import json
import re
import sys
from pathlib import Path

REPO_BLOB = ("https://github.com/trevorotts1/openclaw-onboarding/blob/main/"
             "23-ai-workforce-blueprint/templates/role-library/")
MAX_STEPS = 30
MAX_CHECKLIST = 12


def _norm(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def dept_sop_slug(dept, stem):
    return f"{dept}-{_norm(stem)}"


def truncation_id(slug):
    """sop_embeddings asset id rule (embed_sop_library.sop_id_from_slug)."""
    return "sop_" + slug.replace("-", "_")[:60]


def _field(md, label):
    m = re.search(r"^\*\*" + label + r":?\*\*:?\s*(.+)$", md, re.M)
    return m.group(1).strip() if m else None


def _source_role(md):
    src = _field(md, "Source")
    if src:
        m = re.match(r"`?[\w-]+/([\w-]+)\.md", src)
        if m:
            return m.group(1)
    owner = _field(md, "Owner Role") or _field(md, "Owner")
    if owner:
        return _norm(re.split(r"[(\"“]", owner)[0]) or None
    return None


def _description(md, fallback):
    for raw in md.splitlines():
        line = raw.strip()
        if not line or line[0] in "#>|*-" or line[:1].isdigit():
            continue
        return line[:280]
    return fallback


def _steps(md, title):
    steps, cur = [], None
    for raw in md.splitlines():
        h = re.match(r"^#{2,3}\s+(.+?)\s*$", raw)
        if h:
            text = h.group(1).strip()
            if text.lower() == title.lower():
                continue
            cur = {"step_number": len(steps) + 1, "name": text[:160], "checklist": []}
            steps.append(cur)
            continue
        item = re.match(r"^\s*(?:[-*]|\d+[.)])\s+(.+)$", raw)
        if cur is not None and item and len(cur["checklist"]) < MAX_CHECKLIST:
            cur["checklist"].append(item.group(1).strip()[:240])
    steps = steps[:MAX_STEPS]
    if not steps:
        steps = [{"step_number": 1, "name": f"Follow {title}", "checklist": []}]
    return steps


def build_record(dept, path, role_library):
    md = path.read_text(encoding="utf-8")
    h1 = re.search(r"^#\s+(.+?)\s*$", md, re.M)
    title = h1.group(1).strip() if h1 else path.stem
    dept_title = dept.replace("-", " ").title()
    slug = dept_sop_slug(dept, path.stem)
    words = [dept, *_norm(path.stem).split("-"), *_norm(title).split("-")]
    keywords = list(dict.fromkeys(w for w in words if len(w) >= 3))[:20]
    rel = path.relative_to(role_library).as_posix()
    return {
        "slug": slug,
        "name": f"{dept_title}: {title}"[:200],
        "description": _description(md, f"{title} ({dept_title} department SOP)."),
        "version": 1,
        "department": dept,
        "cadence": None,
        "source_role": _source_role(md),
        "confidence": None,
        "confidence_tier": None,
        "estimated_minutes": None,
        "time_of_day": None,
        "source_file_url": REPO_BLOB + rel,
        "task_keywords": ",".join(keywords),
        "success_criteria": (_field(md, "Outputs") or "")[:280],
        "steps": _steps(md, title),
        "prerequisites": None,
        "persona_hints": [],
        "template_vars_used": [],
        "dependencies_upstream": [],
        "dependencies_downstream": [],
        "layer_version": "v1",
    }


def dept_sop_files(role_library):
    """Exactly the files _index.json sops[] lists (the library's own inventory)."""
    index = json.loads((role_library / "_index.json").read_text(encoding="utf-8"))
    out = []
    for entry in index["sops"]:
        p = role_library / Path(entry["path"]).relative_to("templates/role-library")
        if not p.is_file():
            raise SystemExit(f"FATAL: _index.json lists a missing SOP file: {entry['path']}")
        out.append((entry["dept"], p))
    return sorted(out, key=lambda t: t[1].as_posix())


def build(base_gz, base_sha, role_library, out_path):
    raw = Path(base_gz).read_bytes()
    got = hashlib.sha256(raw).hexdigest()
    if got != base_sha:
        raise SystemExit(f"FATAL: base asset sha256 {got} != pinned {base_sha}")
    base_lines = [l for l in gzip.decompress(raw).decode("utf-8").splitlines() if l.strip()]
    base_slugs = [json.loads(l)["slug"] for l in base_lines]

    new = [build_record(d, p, role_library) for d, p in dept_sop_files(role_library)]
    new_slugs = [r["slug"] for r in new]
    if len(set(new_slugs)) != len(new_slugs):
        raise SystemExit("FATAL: duplicate slug among department SOPs")
    clash = set(new_slugs) & set(base_slugs)
    if clash:
        raise SystemExit(f"FATAL: department SOP slug collides with a V2 slug: {sorted(clash)[:5]}")
    base_tids = {truncation_id(s) for s in base_slugs}
    new_tids = [truncation_id(s) for s in new_slugs]
    if len(set(new_tids)) != len(new_tids) or base_tids & set(new_tids):
        raise SystemExit("FATAL: a department SOP slug collides under the 60-char embeddings id rule")

    body = "\n".join(base_lines + [json.dumps(r, ensure_ascii=False, sort_keys=True) for r in new]) + "\n"
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0) as gz:  # deterministic bytes
        gz.write(body.encode("utf-8"))
    Path(out_path).write_bytes(buf.getvalue())
    return {
        "base_records": len(base_lines),
        "new_records": len(new),
        "jsonl_record_count": len(base_lines) + len(new),
        "distinct_slug_count": len(set(base_slugs) | set(new_slugs)),
        "gz_size_bytes": len(buf.getvalue()),
        "sha256": hashlib.sha256(buf.getvalue()).hexdigest(),
        "new_slugs": new_slugs,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True, help="V2 sops-library-v2.jsonl.gz")
    ap.add_argument("--base-sha256", required=True, help="pinned sha256 of --base")
    ap.add_argument("--role-library", required=True, type=Path)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    print(json.dumps(build(a.base, a.base_sha256, a.role_library, a.out), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
