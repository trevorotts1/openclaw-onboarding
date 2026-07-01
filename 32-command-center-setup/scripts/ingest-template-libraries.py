#!/usr/bin/env python3
"""Skill 32 — Funnel + Automation TEMPLATE LIBRARY ingester (idempotent, LEXICAL).

WHY: the 38 funnel templates (06-ghl-install-pages/funnel-templates/) and the 28 automation
templates (44-convert-and-flow-operator/automation-templates/) live in a THIRD island that the
Command Center never searched — department-head agents search SOPs via mission-control.db (lexical)
and personas via the Gemini semantic index, but the templates were reachable only by invoking the
matcher CLI with the right env. This makes them discoverable in the SAME lexical store the agents
already query, with NO embedding re-index (the matchers are lexical; do not re-embed the persona
corpus — shared-corpus re-embedding bloat lesson).

WHAT: creates/ensures a `templates` table in mission-control.db and upserts every funnel +
automation template as a lexical row carrying name + aliases + task_keywords, so the agents'
existing keyword/SOP search surfaces them. Idempotent (INSERT OR REPLACE on a stable id).

Usage:
    python3 ingest-template-libraries.py [--db <mission-control.db>] [--skills-root <dir>]

Defaults resolve the platform mission-control.db and the installed skills root. Safe to re-run;
run from Event 7 of universal-sops/adding-capability-after-build.md whenever a library changes.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone

def _resolve_default_db() -> str:
    """PRD 1.3: resolve mission-control.db via the single shared resolver (Mac
    ~/projects/command-center first, then VPS /data/projects/command-center) so a
    no-arg run finds the DB on a Mac too — the old VPS-only literal broke Mac.
    Falls back to add-department.sh's candidate list, then the legacy VPS literal."""
    here = os.path.dirname(os.path.abspath(__file__))
    shared = os.path.normpath(os.path.join(here, "..", "..", "shared-utils"))
    if shared not in sys.path:
        sys.path.insert(0, shared)
    try:
        from resolve_db import find_dashboard_db, is_db_found  # type: ignore
        p = find_dashboard_db()
        if is_db_found(p):
            return str(p)
    except ImportError:
        pass
    home = os.path.expanduser("~")
    for c in (
        os.path.join(home, "projects", "command-center", "mission-control.db"),
        os.path.join(home, "projects", "mission-control", "mission-control.db"),
        "/opt/mission-control/mission-control.db",
        "/app/mission-control.db",
        "/data/projects/command-center/mission-control.db",
    ):
        if os.path.isfile(c):
            return c
    return "/data/projects/command-center/mission-control.db"


_DEFAULT_DB = _resolve_default_db()


def _resolve_skills_root(explicit: str | None) -> str:
    if explicit:
        return os.path.abspath(explicit)
    # this script lives at <skills>/32-command-center-setup/scripts/ -> skills root is ../../..
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", ".."))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _keywords(*parts) -> str:
    bag = " ".join(str(p) for p in parts if p)
    toks = sorted({t for t in re.findall(r"[a-z0-9][a-z0-9-]+", bag.lower()) if len(t) > 2})
    return " ".join(toks)


def _iter_templates(root: str, kind: str):
    """Yield (id, group, name, aliases, summary, keywords, ref) for each template .json."""
    if not os.path.isdir(root):
        return
    for group in sorted(os.listdir(root)):
        gdir = os.path.join(root, group)
        if not os.path.isdir(gdir) or group.startswith("_"):
            continue
        for fn in sorted(os.listdir(gdir)):
            if not fn.endswith(".json") or fn.startswith("_"):
                continue
            path = os.path.join(gdir, fn)
            try:
                doc = json.load(open(path, encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(doc, dict):
                continue
            tid = doc.get("id") or fn[:-5]
            name = doc.get("name", "")
            aliases = doc.get("aliases", []) or []
            summary = doc.get("summary") or doc.get("purpose") or ""
            whenuse = doc.get("whenToUse") or ""
            if isinstance(whenuse, dict):
                whenuse = " ".join(str(v) for v in whenuse.values())
            rel = os.path.relpath(path, os.path.dirname(os.path.dirname(root)))
            kw = _keywords(name, " ".join(map(str, aliases)), summary, whenuse, group, kind)
            yield {
                "id": f"{kind}:{group}/{tid}",
                "kind": kind,
                "group": group,
                "template_id": tid,
                "name": name,
                "aliases": json.dumps(aliases),
                "summary": _norm(summary)[:1000],
                "task_keywords": kw,
                "ref": rel,
            }


def ensure_table(db: sqlite3.Connection) -> None:
    db.executescript("""
        CREATE TABLE IF NOT EXISTS templates (
          id            TEXT PRIMARY KEY,
          kind          TEXT NOT NULL,         -- 'funnel' | 'automation'
          "group"       TEXT,
          template_id   TEXT NOT NULL,
          name          TEXT,
          aliases       TEXT,                  -- JSON array
          summary       TEXT,
          task_keywords TEXT,                  -- lexical search bag (space-joined tokens)
          ref           TEXT,                  -- repo-relative path
          updated_at    TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_templates_kind ON templates(kind);
        CREATE INDEX IF NOT EXISTS idx_templates_keywords ON templates(task_keywords);
    """)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("MISSION_CONTROL_DB", _DEFAULT_DB))
    ap.add_argument("--skills-root", default=None)
    ap.add_argument("--dry-run", action="store_true", help="print what would be ingested; no DB write")
    a = ap.parse_args(argv)

    skills = _resolve_skills_root(a.skills_root)
    funnel_root = os.path.join(skills, "06-ghl-install-pages", "funnel-templates")
    auto_root = os.path.join(skills, "44-convert-and-flow-operator", "automation-templates")

    rows = list(_iter_templates(funnel_root, "funnel")) + list(_iter_templates(auto_root, "automation"))
    n_funnel = sum(1 for r in rows if r["kind"] == "funnel")
    n_auto = sum(1 for r in rows if r["kind"] == "automation")
    print(f"discovered {len(rows)} templates ({n_funnel} funnel, {n_auto} automation)")

    if a.dry_run:
        for r in rows[:5]:
            print(f"  {r['id']:<55} kw='{r['task_keywords'][:60]}...'")
        print("  (dry-run — no DB write)")
        return 0

    if not os.path.isfile(a.db):
        print(f"ERROR: mission-control.db not found at {a.db} "
              f"(pass --db or run on a Command-Center box)", file=sys.stderr)
        return 2

    db = sqlite3.connect(a.db)
    ensure_table(db)
    now = datetime.now(timezone.utc).isoformat()
    for r in rows:
        db.execute(
            'INSERT OR REPLACE INTO templates '
            '(id, kind, "group", template_id, name, aliases, summary, task_keywords, ref, updated_at) '
            'VALUES (?,?,?,?,?,?,?,?,?,?)',
            (r["id"], r["kind"], r["group"], r["template_id"], r["name"], r["aliases"],
             r["summary"], r["task_keywords"], r["ref"], now))
    db.commit()
    total = db.execute("SELECT COUNT(*) FROM templates").fetchone()[0]
    db.close()
    print(f"ingested {len(rows)} templates into {a.db} (templates table now has {total} rows). "
          f"LEXICAL only — no embedding re-index.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
