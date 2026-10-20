#!/usr/bin/env python3
"""The delivery message: pages by deliverables, the "To confirm" list, the spend.

Honest by construction: a missing deliverable prints MISSING and the headline
says INCOMPLETE. Every "to confirm" item (an answer we defaulted or suggested)
is listed with a one-line way to change it. Same content on every harness;
claude-code / claude-nine get a table, OpenClaw / plain get plain lines.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness_profile  # noqa: E402
import progress_report as pr  # noqa: E402
import render_question  # noqa: E402

COLS = (("wireframe", "desktop", "Desktop wireframe"), ("wireframe", "mobile", "Mobile wireframe"),
        ("mockup", "desktop", "Desktop mockup"), ("mockup", "mobile", "Mobile mockup"))
TO_CONFIRM_STATUSES = ("default_to_confirm", "suggested")


def has(row, kind, dev):
    return bool((row.get(kind) or {}).get(dev))


def missing(row):
    gaps = [name for kind, dev, name in COLS if not has(row, kind, dev)]
    gaps += [] if row.get("labels") else ["Labels"]
    return gaps + ([] if row.get("qc") in ("pass", "n/a") else [f"Review ({row.get('qc', 'pending')})"])


def to_confirm_items(answers, names=None):
    """Explicit to_confirm list plus every default/suggested answer, de-duplicated by id."""
    names, items, seen = names or {}, [], set()
    for t in (answers or {}).get("to_confirm") or []:
        t = t if isinstance(t, dict) else {"id": str(t)}
        items.append(t)
        seen.add(str(t.get("id")))
    for qid, rec in render_question.records(answers).items():
        if rec.get("status") in TO_CONFIRM_STATUSES and qid not in seen:
            items.append({"id": qid, "value": rec.get("value"), "reason": rec.get("reason", "")})
    for t in items:
        t.setdefault("label", names.get(str(t.get("id"))) or re.sub(r"^[a-z]\d+_", "", str(t.get("id"))).replace("_", " "))
    return items


def confirm_line(t):
    change = t.get("change") or f'Reply "change {t["label"]}: <your answer>"'
    why = f" ({t['reason']})" if t.get("reason") else ""
    return f"{t['label']}: we used {t.get('value')!s}{why}. To change: {change}"


def spend_line(ledger):
    if not ledger:
        return "No image spend was recorded."
    cap, used = ledger.get("image_cap"), ledger.get("images_used", 0)
    s = f"Images: {used}" + (f" of {cap} allowed" if cap is not None else "")
    s += f" (provider {ledger.get('provider', 'unknown')})."
    if ledger.get("test_only"):
        s += " TEST ONLY: placeholder images, nothing was charged."
    if ledger.get("blocked_by_cap"):
        s += " The cap was reached, so some image work was NOT started."
    return s


def render(rows, profile, answers=None, ledger=None, names=None):
    gaps = {pr.label_of(r): missing(r) for r in rows if missing(r)}
    head = (f"INCOMPLETE: {len(gaps)} of {len(rows)} pages are missing deliverables." if gaps
            else f"COMPLETE: all {len(rows)} pages have desktop and mobile wireframes and mockups, labeled.")
    out = [head, ""]
    if profile["progress_shape"] == "table":
        out += ["| Page | " + " | ".join(c[2] for c in COLS) + " | Labeled | Review |", "|" + "---|" * 7]
        for r in rows:
            out.append(f"| {pr.label_of(r)} | " + " | ".join(
                "yes" if has(r, k, d) else "MISSING" for k, d, _ in COLS)
                + f" | {'yes' if r.get('labels') else 'MISSING'} | {r.get('qc', 'pending')} |")
    else:
        for r in rows:
            g = missing(r)
            out.append(f"{pr.label_of(r)}: " + ("all designs delivered, desktop and mobile, labeled." if not g
                                                else "MISSING " + ", ".join(g) + "."))
    items = to_confirm_items(answers, names)
    out += ["", "To confirm" + ("" if items else ": nothing, every answer was yours.")]
    out += [f"- {confirm_line(t)}" for t in items]
    out += ["", spend_line(ledger)]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rows-file", required=True)
    ap.add_argument("--answers-file")
    ap.add_argument("--ledger-file")
    ap.add_argument("--questions-file", help="optional: client-facing names for the To confirm list")
    ap.add_argument("--harness")
    a = ap.parse_args(argv)
    load = lambda p: json.loads(Path(p).read_text(encoding="utf-8")) if p else None  # noqa: E731
    answers = load(a.answers_file)
    qs = load(a.questions_file) or []
    names = {str(q["id"]): q.get("header") or q["id"] for q in qs.get("questions", qs)}
    print(render(load(a.rows_file), harness_profile.detect(a.harness, answers), answers, load(a.ledger_file), names))


if __name__ == "__main__":
    main()
