#!/usr/bin/env python3
"""storyboard_grid: DEL-04 contract -- the approved storyboard as a grid PDF.

Proves the deliverable a client actually reads: every approved scene picture on
a grid, each captioned with the lyric line and what happens, in song order;
built only from the run's storyboard approval records; nothing under 12 pt;
no model/tool name, dollar amount or income promise anywhere in the text; one
clear numbered file in the run's delivery folder.

Run: python3 scripts/core/storyboard_grid/test_storyboard_grid.py
(stdlib only, no network, no spend)
"""
import json
import os
import re
import struct
import sys
import tempfile
import zlib

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import pdf_kit.pdf_kit as PDF                    # noqa: E402
import storyboard_director.approval_package as AP  # noqa: E402
from storyboard_grid import storyboard_grid as SG   # noqa: E402

FAILS = []

#: Generic fixture material only -- no client name ever enters the repository.
TITLE = "Morning Light Sample"


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        "" if cond else " (%s)" % (detail,)))
    if not cond:
        FAILS.append(name)


def png_bytes(width, height, pixel, colour=6):
    """A non-interlaced 8-bit PNG (colour 6 = RGBA, 2 = RGB)."""
    rows = b""
    for _ in range(height):
        rows += b"\x00" + bytes(pixel) * width
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, colour, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def make_run(order=(0, 1, 2), stills=True, approve=True,
             meaning_extra=""):
    """A run whose storyboard approval record exists (or does not).

    ``order`` is the order the shots are stored in, deliberately independent of
    song order, so the grid can be proven to sort by the song.
    """
    run = tempfile.mkdtemp(prefix="sgrid-")
    sb = os.path.join(run, "storyboard")
    os.makedirs(os.path.join(sb, "stills"), exist_ok=True)
    lines = ("Light spills across the kitchen floor",
             "She sets the jar down by the window",
             "The morning is hers to keep")
    places = ("kitchen", "window", "porch")
    actions = ("crosses the room and opens the curtains",
               "sets the jar down and smiles",
               "steps outside into the sun")
    meanings = ("the day begins with one small ritual",
                "the offer is right there, ready",
                "she is ready to start")
    shots, contracts, still_map = [], {}, {}
    for i, slot in enumerate(order):
        sid = "s%d" % (slot + 1)
        shots.append({"shot_id": sid, "song_start": slot * 4.0,
                      "song_end": slot * 4.0 + 4.0, "story_stage": "setup",
                      "location_id": places[slot],
                      "status": "storyboard_approved"})
        contracts[sid] = {
            "lyric_text": lines[slot],
            "viewer_understanding": meanings[slot] + meaning_extra,
            "character_action": actions[slot],
            "visible_emotion": "warm, unhurried",
        }
        if stills:
            rel = os.path.join("storyboard", "stills", sid + ".png")
            with open(os.path.join(run, rel), "wb") as fh:
                fh.write(png_bytes(32, 18, (60 + slot * 40, 120, 180, 255)))
            still_map[sid] = rel
    def dump(rel, obj):
        path = os.path.join(run, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
    dump(os.path.join("storyboard", "contracts.json"), contracts)
    dump(os.path.join("storyboard", "stills.json"), still_map)
    dump(os.path.join("storyboard", "shot-list.json"), {"shots": shots})
    dump(os.path.join("creative", "script.json"), {"title": TITLE})
    if approve:
        dump(os.path.join("storyboard", "gate.json"),
             {"shots": shots, "review": {"outcome": "pass"}})
        dump(os.path.join("storyboard", "approval.json"),
             {"state": "approved", "choice": "yes"})
    return run


def test_refuses_without_approval_record():
    run = make_run(approve=False)
    try:
        SG.load(run)
        check("no approval record refuses", False)
    except SG.GridError as exc:
        check("no approval record refuses",
              exc.code == "STORYBOARD_NOT_APPROVED", exc)
    assert not FAILS, FAILS


def test_refuses_an_incomplete_approval():
    run = make_run()
    os.remove(os.path.join(run, "storyboard", "stills", "s2.png"))
    try:
        SG.load(run)
        check("a missing still refuses with the approval gate's code", False)
    except AP.ApprovalError as exc:
        check("a missing still refuses with the approval gate's code",
              exc.code == AP.STILL_MISSING and "s2" in str(exc), exc)
    run = make_run()
    path = os.path.join(run, "storyboard", "contracts.json")
    contracts = json.load(open(path, encoding="utf-8"))
    del contracts["s1"]["character_action"]
    json.dump(contracts, open(path, "w", encoding="utf-8"))
    try:
        SG.load(run)
        check("an incomplete card refuses", False)
    except AP.ApprovalError as exc:
        check("an incomplete card refuses", exc.code == AP.CARD_INCOMPLETE, exc)
    assert not FAILS, FAILS


def test_captions_follow_the_song_not_the_file():
    run = make_run(order=(2, 0, 1))          # stored out of song order
    package = SG.load(run)
    check("title comes from the approved script", package["title"] == TITLE,
          package["title"])
    rows = SG.captions(package["items"])
    check("one caption per approved shot", len(rows) == 3, len(rows))
    check("shot numbers run 1..n in song order",
          [r["n"] for r in rows] == [1, 2, 3], [r["n"] for r in rows])
    headings = [r["heading"] for r in rows]
    check("headings carry the shot number and its timecode",
          all(h.startswith("SHOT %d" % n) and re.search(r"\d:\d\d-\d:\d\d", h)
              for n, h in enumerate(headings, 1)), headings)
    check("every caption carries the lyric line",
          all(r["lyric"].startswith('"') and r["lyric"].endswith('"')
              for r in rows), [r["lyric"] for r in rows])
    check("every caption says what happens",
          all(r["what"].startswith("What happens: ") and len(r["what"]) > 30
              for r in rows), [r["what"] for r in rows])
    check("every caption names the face",
          all(r["face"].startswith("Face: ") for r in rows), [r["face"] for r in rows])
    check("the first line really is the first line sung",
          "Light spills across the kitchen floor" in rows[0]["lyric"],
          rows[0]["lyric"])
    assert not FAILS, FAILS


def test_deliver_writes_one_numbered_pdf():
    run = make_run(order=(1, 2, 0))
    folder = tempfile.mkdtemp(prefix="sgrid-del-")
    path = SG.deliver(run, folder)
    check("named deliverable lands in the run's delivery folder",
          path == os.path.join(folder, SG.DELIVERY_NAME), path)
    check("numbered file name", os.path.basename(path) == "04-storyboard.pdf",
          path)
    blob = open(path, "rb").read()
    check("is a PDF", blob.startswith(b"%PDF-1.4"), blob[:8])
    text = PDF.extract_text(blob)
    check("heading on the first page", "STORYBOARD" in text, text[:200])
    check("the document subtitle is present", SG.SUBTITLE in text)
    check("shot headings present",
          all("SHOT %d" % n in text for n in (1, 2, 3)), text)
    check("lyric lines present",
          all(lyric in text for lyric in
              ("Light spills across the kitchen floor",
               "She sets the jar down by the window",
               "The morning is hers to keep")), text)
    check("what happens present on every caption",
          text.count("What happens: ") == 3, text.count("What happens: "))
    check("page number printed", "Page 1" in text, text[-120:])
    check("scene pictures embedded",
          blob.count(b"/Subtype /Image") == 3,
          blob.count(b"/Subtype /Image"))
    sizes = [float(s) for s in re.findall(rb"/F\d+ ([\d.]+) Tf", blob)]
    check("font sizes were actually drawn", len(sizes) >= 8, len(sizes))
    check("nothing under the 12 pt floor", sizes and min(sizes) >= PDF.MIN_PT,
          min(sizes) if sizes else None)
    pages = blob.count(b"/Type /Page ")
    check("page tree reports that many pages",
          ("/Count %d" % pages).encode() in blob, pages)
    assert not FAILS, FAILS


def test_grid_spans_pages_without_overflowing():
    run = make_run(order=(0, 1, 2))
    package = SG.load(run)
    rows = SG.captions(package["items"])
    # Same three shots drawn twice over: 6 cells must still fit the margins.
    path = SG.write_pdf(rows + [dict(r, n=r["n"] + 3, heading=r["heading"])
                                for r in rows],
                        os.path.join(tempfile.mkdtemp(prefix="sgrid-pg-"),
                                     "grid.pdf"), TITLE)
    blob = open(path, "rb").read()
    text = PDF.extract_text(blob)
    check("a second page was opened when the first filled",
          text.count("SHOT 1") == 2 and "Page 2" in text,
          (text.count("SHOT 1"), "Page 2" in text))
    check("every cell still drawn", text.count("What happens: ") == 6,
          text.count("What happens: "))
    sizes = [float(s) for s in re.findall(rb"/F\d+ ([\d.]+) Tf", blob)]
    check("second page still honours the floor", min(sizes) >= PDF.MIN_PT,
          min(sizes))
    assert not FAILS, FAILS


def test_client_facing_text_rules():
    clean = SG.forbidden_text(
        "Morning Light Sample. She sets the cookie tray by the window.")
    check("ordinary copy is clean", clean == [], clean)
    for sample, code in (
            ("Made with Claude", "TOOL_OR_MODEL_NAME"),
            ("runs on the KIE queue", "TOOL_OR_MODEL_NAME"),
            ("rendered by Runway ML", "INCOME_PROMISE"),
            ("a Llama 3 checkpoint", "INCOME_PROMISE"),
            ("guaranteed income for anyone", "INCOME_PROMISE"),
            ("passive income stream", "INCOME_PROMISE"),
            ("only $49 today", "DOLLAR_AMOUNT"),
            ("save 20 dollars", "DOLLAR_AMOUNT")):
        hits = SG.forbidden_text(sample)
        check("%r is refused" % sample,
              any(h.startswith(code) for h in hits), hits)
    # A word containing a banned token as a substring, or an ordinary word a
    # product also uses, must survive -- the guard blocks delivery otherwise.
    for phrase in ("she bakes a cookie", "the baker did smile",
                   "she walks down the runway", "a llama in the field"):
        hits = SG.forbidden_text(phrase)
        check("%r is clean" % phrase, hits == [], hits)
    # The refusal happens before a byte is written, not after.
    run = make_run()
    path = os.path.join(run, "storyboard", "contracts.json")
    contracts = json.load(open(path, encoding="utf-8"))
    contracts["s1"]["viewer_understanding"] = "the offer costs only $49"
    json.dump(contracts, open(path, "w", encoding="utf-8"))
    try:
        SG.deliver(run, tempfile.mkdtemp(prefix="sgrid-ban-"))
        check("a dollar amount refuses the whole document", False)
    except SG.GridError as exc:
        check("a dollar amount refuses the whole document",
              exc.code == "CLIENT_TEXT_FORBIDDEN" and "DOLLAR" in str(exc), exc)
    assert not FAILS, FAILS


def test_empty_storyboard_refuses():
    try:
        SG.write_pdf([], os.path.join(tempfile.mkdtemp(prefix="sgrid-e-"),
                                      "x.pdf"), TITLE)
        check("no shots refuses", False)
    except SG.GridError as exc:
        check("no shots refuses", exc.code == "STORYBOARD_EMPTY", exc)
    assert not FAILS, FAILS


if __name__ == "__main__":
    for run in (test_refuses_without_approval_record,
                test_refuses_an_incomplete_approval,
                test_captions_follow_the_song_not_the_file,
                test_deliver_writes_one_numbered_pdf,
                test_grid_spans_pages_without_overflowing,
                test_client_facing_text_rules,
                test_empty_storyboard_refuses):
        run()
    print("FAIL (%d): %s" % (len(FAILS), ", ".join(FAILS)) if FAILS
          else "ALL PASS")
    sys.exit(1 if FAILS else 0)
