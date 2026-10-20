#!/usr/bin/env python3
"""Per-page build status. Claude Code / claude-nine: one table. OpenClaw / plain:
one short message per FINISHED page (never a wall of text, never a repeat).

A row: {page_key, label?, role?, state: queued|working|done|failed|blocked,
wireframe:{desktop,mobile}, mockup:{desktop,mobile}, labels, qc: pass|fail|pending|n/a, note?}.
Labels come from Skill 71's deliverable_labels when present (one place names a page).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness_profile  # noqa: E402

FINISHED = ("done", "failed", "blocked")
_LABELS = Path(__file__).resolve().parents[3] / "71-blackceo-signature-page" / "scripts"


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
    ap.add_argument("--rows-file", required=True, help="JSON list of rows")
    ap.add_argument("--harness")
    ap.add_argument("--announced", default="", help="comma-separated keys already announced")
    a = ap.parse_args(argv)
    rows = json.loads(Path(a.rows_file).read_text(encoding="utf-8"))
    print(json.dumps(render(rows, harness_profile.detect(a.harness),
                            [k for k in a.announced.split(",") if k]), indent=2))


if __name__ == "__main__":
    main()
