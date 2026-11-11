#!/usr/bin/env python3
"""Per-page build status. Claude Code / claude-nine: one table. OpenClaw / plain:
one short message per FINISHED page (never a wall of text, never a repeat).

Rows are never hand-authored: they are derived from package-manifest.json after the Skill 83 package
check passes, and a rows file carries the manifest's sha256 (load_bound_rows refuses anything else).
A row: {page_key, label?, role?, state: queued|working|done|failed|blocked,
wireframe:{desktop,mobile}, mockup:{desktop,mobile}, labels, qc: pass|fail|pending|n/a, note?}.
Labels come from Skill 71's deliverable_labels when present (one place names a page).
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness_profile  # noqa: E402

FINISHED = ("done", "failed", "blocked")
SCHEMA = "bfl-rows/1"


def _sibling(names, rel=""):
    """A sibling skill under either layout (onboarding `NN-name/`, 999 `.claude/skills/name/`), found by
    walking up; none found gives the onboarding spelling."""
    for base in Path(__file__).resolve().parents:
        for b in (base, base / ".claude" / "skills", base / "skills"):
            for name in names:
                if (b / name / "SKILL.md").is_file():
                    return b / name / rel
    return Path(__file__).resolve().parents[3] / names[0] / rel


_LAUNCHER = _sibling(("83-black-friday-launcher", "black-friday-launcher"))


class RowsRefused(Exception):
    """The rows are not generated from a checked manifest."""


def sha_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def derive_rows(manifest_path, root=None):
    """Rows from package-manifest.json, only after the package check passes (else RowsRefused)."""
    mp = Path(manifest_path)
    sys.path.insert(0, str(_LAUNCHER))
    try:
        from launcher_core import checks, page_designs as pd
    finally:
        sys.path.pop(0)
    try:
        # client_rows: a practice package (test_only true) fails here, so no client row is ever made from one
        fails = checks.check_package(mp, Path(root) if root else mp.parent, client_rows=True)
        manifest = json.loads(mp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RowsRefused(f"cannot read the package manifest ({exc})")
    if fails:
        raise RowsRefused(f"the package check failed ({len(fails)} violation(s)): {fails[0]}")
    rows = []
    for piece in manifest.get("pieces") or []:
        arts = [(pd.classify(str(a.get("path") or ""), a.get("kind")), Path(str(a.get("path") or "")).name)
                for a in piece.get("artifacts") or []]
        arts = [(k, n) for k, n in arts if k]
        kinds = {k for k, _ in arts}
        side = lambda kind, dev: any(f"{kind}_{dev}_{x}" in kinds for x in ("section", "pdf"))  # noqa: E731
        row = {"page_key": pd.page_key(piece), "role": piece.get("role_instance") or piece.get("role"),
               "state": "done",
               "wireframe": {d: side("wireframe", d) for d in ("desktop", "mobile")},
               "mockup": {d: side("mockup", d) for d in ("desktop", "mobile")},
               "labels": bool(arts) and all(n.lower().startswith(pd.label_slug(piece) + "_") for _, n in arts)}
        row["qc"] = "pass" if row["labels"] and all(v for kind in ("wireframe", "mockup") for v in row[kind].values()) else "pending"
        rows.append(row)
    return rows


def emit_rows(manifest_path, out, root=None):
    """Write the only rows file the reports accept: rows plus the manifest's sha256."""
    doc = {"schema": SCHEMA, "manifest_sha256": sha_of(manifest_path), "rows": derive_rows(manifest_path, root)}
    Path(out).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def load_bound_rows(rows_file, manifest_path, root=None):
    """The rows, or RowsRefused: hand-authored, not bound to this manifest's sha256, or not what it yields."""
    try:
        doc = json.loads(Path(rows_file).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RowsRefused(f"cannot read the rows file ({exc})")
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA or not isinstance(doc.get("rows"), list):
        raise RowsRefused("the rows file was not generated from a package manifest (hand-authored rows are refused)")
    try:
        bound = doc.get("manifest_sha256") == sha_of(manifest_path)
    except OSError as exc:
        raise RowsRefused(f"cannot read the package manifest ({exc})")
    if not bound:
        raise RowsRefused("the rows file is not bound to this package-manifest.json (sha256 mismatch)")
    if doc["rows"] != derive_rows(manifest_path, root):
        raise RowsRefused("the rows differ from what the checked manifest yields")
    return doc["rows"]
_LABELS = _sibling(("71-blackceo-signature-page", "blackceo-signature-page"), "scripts")


def label_of(row):
    if row.get("label"):
        return str(row["label"])
    role = row.get("role") or row.get("page_key")
    sys.path.insert(0, str(_LABELS))
    try:
        import deliverable_labels
        return deliverable_labels.page_type(role)
    except ImportError:
        return str(role or "page").replace("_", " ").title()
    finally:
        sys.path.pop(0)


def pair(row, kind):
    d = row.get(kind) or {}
    return bool(d.get("desktop")), bool(d.get("mobile"))


def cell(row, kind):
    d, m = pair(row, kind)
    return f"D {'yes' if d else 'no'} / M {'yes' if m else 'no'}"


def table(rows):
    out = ["| Page | Status | Wireframes | Mockups | Labeled | Review |", "|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {label_of(r)} | {r.get('state', 'queued')} | {cell(r, 'wireframe')} | "
                   f"{cell(r, 'mockup')} | {'yes' if r.get('labels') else 'no'} | {r.get('qc', 'pending')} |")
    done = sum(1 for r in rows if r.get("state") == "done")
    out.append(f"\n{done} of {len(rows)} pages finished.")
    return "\n".join(out)


def _both(row, kind):
    d, m = pair(row, kind)
    return "desktop and mobile" if d and m else "desktop only" if d else "mobile only" if m else "none yet"


def page_message(row, done_count, total):
    name, state = label_of(row), row.get("state")
    if state == "done":
        msg = (f"{name} is finished. Wireframes: {_both(row, 'wireframe')}. "
               f"Mockups: {_both(row, 'mockup')}. Labeled: {'yes' if row.get('labels') else 'no'}. "
               f"Review: {row.get('qc', 'pending')}.")
    else:
        msg = f"{name} is {state}." + (f" {row['note']}" if row.get("note") else "")
    return f"{msg} {done_count} of {total} pages finished."


def messages(rows, announced=()):
    """-> (new messages, announced keys). Pass the keys back next time: no page is announced twice."""
    seen, out = list(announced), []
    done = sum(1 for r in rows if r.get("state") == "done")
    for r in rows:
        k = str(r.get("page_key"))
        if r.get("state") in FINISHED and k not in seen:
            out.append(page_message(r, done, len(rows)))
            seen.append(k)
    return out, seen


def render(rows, profile, announced=()):
    if profile["progress_shape"] == "table":
        return {"shape": "table", "text": table(rows)}
    msgs, seen = messages(rows, announced)
    return {"shape": "messages", "messages": msgs, "announced": seen}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", required=True, help="package-manifest.json the rows are bound to")
    ap.add_argument("--root", help="package root (default: the manifest's folder)")
    ap.add_argument("--rows-file", help="rows generated by --emit-rows")
    ap.add_argument("--emit-rows", metavar="OUT", help="write rows.json from the manifest (package check must pass)")
    ap.add_argument("--harness")
    ap.add_argument("--announced", default="", help="comma-separated keys already announced")
    a = ap.parse_args(argv)
    try:
        if a.emit_rows:
            return emit_rows(a.manifest, a.emit_rows, a.root)
        rows = load_bound_rows(a.rows_file, a.manifest, a.root) if a.rows_file else sys.exit("--rows-file or --emit-rows is required")
    except RowsRefused as exc:
        sys.exit(f"REFUSED: {exc}")
    print(json.dumps(render(rows, harness_profile.detect(a.harness),
                            [k for k in a.announced.split(",") if k]), indent=2))


if __name__ == "__main__":
    main()
