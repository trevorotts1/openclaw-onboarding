"""beat_sheet.line_match: line-match verdicts and buried events (N-66).

Plan 3F.2. Every lyric line gets a verdict against its on-screen row:

  * **MATCH** -- the picture shows what the words say;
  * **WEAK** -- related but indirect;
  * **MISMATCH** -- unrelated or contradicting.

Any MISMATCH blocks the story gate (``MISMATCH``, 3J MAJOR item 10). A line
with no verdict is refused (``LINE_MATCH_MISSING``, item 11). WEAK lines are
listed for the run owner and capped at one in five lines; past the cap is
``WEAK_CAP_EXCEEDED``, MEDIUM, shown and never blocking (3J.2). A story event
that falls under a lip-sync piece is refused (``EVENT_UNDER_LIP_WINDOW``,
item 9: lip-sync pieces are placed first and nothing sits under them).

Stdlib only; data in, verdicts out; no model call, no write.
"""
from __future__ import annotations

from ._util import finding, num, rows
from .beat_sheet import LINE_MATCH_VERDICTS


def _verdict(row):
    value = row.get("line_match")
    if isinstance(value, str):
        value = value.strip().upper()
        if value in LINE_MATCH_VERDICTS:
            return value
    return None


def match_defects(script):
    """A verdict on every line; MISMATCH blocks; WEAK is capped and listed."""
    out = []
    script_rows = rows(script)
    weak = []
    for index, row in enumerate(script_rows):
        verdict = _verdict(row)
        if verdict is None:
            out.append(finding("LINE_MATCH_MISSING", "/rows/%d/line_match" % index,
                               "every lyric line gets MATCH, WEAK or MISMATCH"))
        elif verdict == "MISMATCH":
            out.append(finding("MISMATCH", "/rows/%d/line_match" % index,
                               "the picture is unrelated to the words; MISMATCH blocks",
                               line_id=row.get("line_id")))
        elif verdict == "WEAK":
            weak.append(row.get("line_id") or index)
    total = len(script_rows)
    if total and len(weak) > total / 5.0:
        out.append(finding("WEAK_CAP_EXCEEDED", "/rows",
                           "%d WEAK lines of %d; the cap is one in five, listed for "
                           "the run owner" % (len(weak), total),
                           weak=tuple(weak)))
    return out


def _lip_windows(script):
    spans = []
    for row in rows(script):
        if row.get("lip_sync") is True or str(row.get("lip_sync")).strip().lower() \
                in ("yes", "true", "lip-sync", "lipsync"):
            start, end = num(row.get("start_s")), num(row.get("end_s"))
            if start is not None and end is not None and end > start:
                spans.append((row.get("line_id"), start, end))
    return spans


def buried_event_defects(script):
    """No story event sits under a lip-sync piece (3F.2, N-54)."""
    out = []
    spans = _lip_windows(script)
    for index, row in enumerate(rows(script)):
        event = row.get("event")
        if not isinstance(event, dict) or not event.get("kind"):
            continue
        start, end = num(row.get("start_s")), num(row.get("end_s"))
        if start is None or end is None:
            continue
        mid = (start + end) / 2.0
        for line_id, lip_start, lip_end in spans:
            if line_id == row.get("line_id"):
                continue
            if lip_start <= mid < lip_end:
                out.append(finding("EVENT_UNDER_LIP_WINDOW", "/rows/%d/event" % index,
                                   "the event %r sits under the lip-sync piece on %r"
                                   % (event.get("kind"), line_id),
                                   event_kind=event.get("kind")))
                break
    return out


def check_line_match(script):
    """Result envelope for the line-match checks (N-66)."""
    defects = match_defects(script) + buried_event_defects(script)
    return {"ok": not any(d.get("level") == "MAJOR" for d in defects),
            "defects": defects}


def _selfcheck():
    cues = {"eyes": "steady", "brows": "set", "mouth": "firm",
            "smile": "no", "teeth": "no", "tears": "none"}

    def row(i, verdict, **extra):
        base = {"row_id": "r%d" % i, "line_id": "l%d" % i, "beat_number": 1,
                "start_s": 4.0 * (i - 1), "end_s": 4.0 * i, "line_match": verdict,
                "lip_sync": False, "facial_cues": cues}
        base.update(extra)
        return base

    good = {"rows": [row(1, "MATCH"), row(2, "WEAK"), row(3, "MATCH"),
                     row(4, "MATCH"), row(5, "MATCH"), row(6, "MATCH")]}
    assert check_line_match(good)["ok"], check_line_match(good)["defects"]
    bad = {"rows": [row(1, "MISMATCH")]}
    assert [d["code"] for d in check_line_match(bad)["defects"]] == ["MISMATCH"]
    missing = {"rows": [row(1, None)]}
    assert [d["code"] for d in check_line_match(missing)["defects"]] \
        == ["LINE_MATCH_MISSING"]
    weak = {"rows": [row(1, "WEAK"), row(2, "WEAK")]}
    assert check_line_match(weak)["ok"]  # WEAK never blocks
    assert any(d["code"] == "WEAK_CAP_EXCEEDED"
               for d in check_line_match(weak)["defects"])
    buried = {"rows": [
        {"row_id": "r1", "line_id": "l1", "beat_number": 1, "start_s": 0.0,
         "end_s": 8.0, "lip_sync": True, "line_match": "MATCH"},
        {"row_id": "r2", "line_id": "l2", "beat_number": 1, "start_s": 2.0,
         "end_s": 4.0, "lip_sync": False, "line_match": "MATCH",
         "event": {"kind": "letter"}}]}
    assert any(d["code"] == "EVENT_UNDER_LIP_WINDOW"
               for d in check_line_match(buried)["defects"])


if __name__ == "__main__":
    _selfcheck()
    print("beat_sheet.line_match selfcheck: OK")
