#!/usr/bin/env python3
"""script_pdf tests: DEL-03, the approved script as a printed PDF.

Covers the approval binding, the fail-closed content rules, the layout floor,
the delivery-folder files (numbered name, receipt hash, README block) and the
QC check. No network, no provider, no spend, no absolute operator path.
Run: python3 script_pdf/test_script_pdf.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import script_approval as SA                        # noqa: E402
from delivery_docs import pdf_writer as PW           # noqa: E402
from delivery_variants.manifests import sha256_file  # noqa: E402
from script_pdf import script_pdf as SP              # noqa: E402

TITLE = "She Found Power in the Climb"
STORY = [
    ["Ordinary world", ["She carried the boxes herself.",
                        "The stairs never got easier."]],
    ["The climb", ["One seed of truth made her strong."]],
]
SHEET = [
    {"tag": "Intro", "delivery": "spoken",
     "lines": ["One closed door."]},
    {"tag": "Hook 1", "delivery": "sung",
     "lines": ["I am not sma-a-all", "I ne-ever wa-a-as"]},
    {"tag": "Outro", "delivery": "spoken",
     "lines": ["She Found Power in the Climb. Get the book. Link below."]},
]
LYRICS = "\n".join(line for sec in SHEET for line in sec["lines"])


def _run(tmp, story=None, sheet=None, lyrics=None, approval=None):
    """A run folder holding creative/script.json (+ record) and a delivery dir."""
    run = os.path.join(tmp, "run")
    delivery = os.path.join(tmp, "delivery")
    os.makedirs(os.path.join(run, "creative"), exist_ok=True)
    payload = {"title": TITLE,
               "story": [list(a) for a in (story if story is not None else STORY)],
               "sheet": sheet if sheet is not None else SHEET,
               "lyrics": LYRICS if lyrics is None else lyrics}
    with open(os.path.join(run, "creative", "script.json"), "w",
              encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    rec = approval if approval is not None else {
        "required": True, "status": "approved",
        "lyrics_sha": SA.lyrics_sha(payload["lyrics"]), "sent": True}
    if rec is not None:
        with open(os.path.join(run, "creative", "script-approval.json"), "w",
                  encoding="utf-8") as handle:
            json.dump(rec, handle, indent=2, sort_keys=True)
    os.makedirs(delivery, exist_ok=True)
    return run, delivery


# --- approval binding ----------------------------------------------------

def test_refuses_when_the_script_was_not_approved():
    with tempfile.TemporaryDirectory() as tmp:
        for rec in (None,
                    {"required": True, "status": "pending",
                     "lyrics_sha": SA.lyrics_sha(LYRICS)},
                    {"required": False, "status": "approved",
                     "lyrics_sha": SA.lyrics_sha(LYRICS)},
                    {"status": "approved", "lyrics_sha": SA.lyrics_sha(LYRICS)}):
            run, delivery = _run(tmp, approval=rec)
            record = os.path.join(run, "creative", "script-approval.json")
            if rec is None and os.path.isfile(record):
                os.remove(record)
            got = SP.render(run, delivery)
            assert got["ok"] is False, got
            assert got["reason_code"] == SP.REASON_NOT_APPROVED, got
            assert os.listdir(delivery) == [], os.listdir(delivery)


def test_refuses_a_stale_revision():
    with tempfile.TemporaryDirectory() as tmp:
        rec = {"required": True, "status": "approved",
               "lyrics_sha": SA.lyrics_sha("some other lyric sheet entirely"),
               "sent": True}
        run, delivery = _run(tmp, approval=rec)
        got = SP.render(run, delivery)
        assert got["ok"] is False, got
        assert got["reason_code"] == SP.REASON_STALE, got
        assert not os.listdir(delivery), "a refused render must write nothing"


def test_refuses_when_the_script_document_is_missing():
    with tempfile.TemporaryDirectory() as tmp:
        run, delivery = _run(tmp)
        os.remove(os.path.join(run, "creative", "script.json"))
        got = SP.render(run, delivery)
        assert got["ok"] is False and got["reason_code"] == SP.REASON_NO_SOURCE, got
        run, delivery = _run(tmp, sheet=[])
        got = SP.render(run, delivery)
        assert got["ok"] is False and got["reason_code"] == SP.REASON_NO_SOURCE, got


# --- content rules -------------------------------------------------------

def test_price_copy_never_prints():
    for line in ("Only $47 today", "yours for 47 USD", "the fee is £1,200",
                 "save €50 this week", "just 9.99 dollars", "only 350 EUR",
                 "Enter your card and pay $20"):
        hit = SP.copy_violation(line)
        assert hit is not None, line
        assert hit[0] == SP.REASON_PRICE, hit
    # A price that never appears as a figure is not a figure.
    assert SP.copy_violation("She climbed anyway and it cost her dear.") is None


def test_income_promises_never_print():
    for line in ("make money fast", "a guaranteed income for life",
                 "get rich this year", "six figures in a year",
                 "achieve financial freedom", "passive income for everyone",
                 "Earn up to five figures a month", "a residual income stream",
                 "$5,000 per month", "earn $200 a day"):
        hit = SP.copy_violation(line)
        assert hit is not None, line
        assert hit[0] in (SP.REASON_INCOME, SP.REASON_PRICE), hit
    assert SP.copy_violation("She climbed and it was hard. "
                             "Money saved for rent was not enough.") is None


def test_tool_and_model_names_never_print():
    for line in ("Rendered with ffmpeg", "we ran the python builder",
                 "built by suno", "checked by claude", "a seedance model",
                 "the kie credits", "run it through whisper"):
        hit = SP.copy_violation(line)
        assert hit is not None, line
        assert hit[0] == SP.REASON_TOOL, hit


def test_section_labels_are_not_song_copy():
    # Structure is exempt: a bracketed tag and the two section headings are
    # allowed to sit next to words the rules would otherwise refuse.
    for label in ("THE STORY", "THE SONG LYRICS", "the song title",
                  "Approved for Production", "[Hook 1]", "[Verse]"):
        assert SP.copy_violation(label) is None, label
    # ...but the rule still bites on the copy that follows one.
    assert SP.copy_violation("THE STORY\nEarn up to 10k a month") is not None


# --- layout and delivery -------------------------------------------------

def test_render_writes_a_numbered_binded_pdf():
    with tempfile.TemporaryDirectory() as tmp:
        run, delivery = _run(tmp)
        got = SP.render(run, delivery)
        assert got["ok"] is True, got
        assert got["name"] == "03 - SCRIPT.pdf", got["name"]
        assert got["file"] == os.path.join(delivery, "03 - SCRIPT.pdf")
        assert got["pages"] >= 1 and got["sha256"]

        data = open(got["file"], "rb").read()
        assert data.startswith(b"%PDF-") and b"%%EOF" in data[-4096:]
        sizes = [float(s) for s in re.findall(rb"/F\d\s+([0-9.]+)\s+Tf", data)]
        assert sizes, "no type was drawn"
        assert min(sizes) >= PW.MIN_PT, min(sizes)
        # the approved copy is on the page, verbatim
        assert b"I am not sma-a-all" in data, "lyric missing from the PDF"
        assert b"She Found Power in the Climb" in data
        assert b"THE SONG LYRICS" in data and b"THE STORY" in data
        assert TITLE.encode("ascii", "replace") in data

        receipt = json.load(open(os.path.join(delivery, "delivery-receipt.json"),
                                 encoding="utf-8"))
        entry = receipt["script_pdf"]
        assert entry["file"] == "03 - SCRIPT.pdf"
        assert entry["sha256"] == sha256_file(got["file"]) == got["sha256"]
        assert entry["pages"] == got["pages"]
        assert entry["lyrics_sha"] == SA.lyrics_sha(LYRICS)

        readme = open(os.path.join(delivery, "README.md"), encoding="utf-8").read()
        assert SP.PDF_NAME in readme and SP.README_BEGIN in readme
        verdict, detail = SP.check_delivery(delivery)
        assert verdict == SP.PASS, detail


def test_readme_and_receipt_merge_without_clobbering():
    with tempfile.TemporaryDirectory() as tmp:
        run, delivery = _run(tmp)
        with open(os.path.join(delivery, "README.md"), "w",
                  encoding="utf-8") as handle:
            handle.write("# Delivery\n\nThe master video is `01 - MASTER.mp4`.\n")
        with open(os.path.join(delivery, "delivery-receipt.json"), "w",
                  encoding="utf-8") as handle:
            json.dump({"song_files": [{"file": "ad.mp3"}],
                       "campaign_id": "run-1"}, handle)
        got = SP.render(run, delivery)
        assert got["ok"], got
        receipt = json.load(open(os.path.join(delivery, "delivery-receipt.json"),
                                 encoding="utf-8"))
        assert receipt["song_files"] and receipt["campaign_id"] == "run-1"
        assert "script_pdf" in receipt
        readme = open(os.path.join(delivery, "README.md"), encoding="utf-8").read()
        assert "01 - MASTER.mp4" in readme, "existing README content was lost"
        # a second render replaces its own block, not the rest of the file
        again = SP.render(run, delivery)
        assert again["ok"], again
        readme = open(os.path.join(delivery, "README.md"), encoding="utf-8").read()
        assert readme.count(SP.README_BEGIN) == 1
        assert "01 - MASTER.mp4" in readme


def test_long_script_lands_on_several_pages_inside_the_floor():
    with tempfile.TemporaryDirectory() as tmp:
        story = [["Act %d" % act,
                  ["Line %d of the story, told plainly." % n for n in range(4)]]
                 for act in range(6)]
        sheet = [{"tag": "Verse %d" % i,
                  "lines": ["Sing this line for the %d time, held on the beat." % j
                            for j in range(14)]} for i in range(8)]
        lyrics = "\n".join(line for sec in sheet for line in sec["lines"])
        run, delivery = _run(tmp, story=story, sheet=sheet, lyrics=lyrics)
        got = SP.render(run, delivery)
        assert got["ok"], got
        assert got["pages"] >= 3, got["pages"]
        verdict, detail = SP.check_pdf(got["file"])
        assert verdict == SP.PASS, detail


def test_malformed_script_document_refuses_without_raising():
    shapes = [
        {"title": "x", "story": "not a list", "sheet": SHEET},
        {"title": "x", "story": [["Act", "not a list of lines"]], "sheet": SHEET},
        {"title": "x", "story": [["Act"]], "sheet": SHEET},          # not a pair
        {"title": "x", "story": [], "sheet": ["not an object"]},
        {"title": "x", "story": [], "sheet": [{"tag": "V", "lines": "one line"}]},
        {"title": {"not": "a string"}, "story": [], "sheet": SHEET},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        run, delivery = _run(tmp)
        for payload in shapes:
            with open(os.path.join(run, "creative", "script.json"), "w",
                      encoding="utf-8") as handle:
                json.dump(payload, handle)
            got = SP.render(run, delivery)
            assert got["ok"] is False, (payload, got)
            assert got["reason_code"] == SP.REASON_NO_SOURCE, (payload, got)
        assert os.listdir(delivery) == [], os.listdir(delivery)


def test_check_fails_closed_on_missing_and_on_small_type():
    with tempfile.TemporaryDirectory() as tmp:
        missing = os.path.join(tmp, "nope", SP.PDF_NAME)
        verdict, detail = SP.check_delivery(os.path.join(tmp, "nope"))
        assert verdict == SP.FAIL, detail
        assert "missing" in detail or "unreadable" in detail, detail

        verdict, detail = SP.check_pdf(missing)
        assert verdict == SP.FAIL, detail

        # a receipt that does not bind the file must fail the gate
        run, delivery = _run(tmp)
        assert SP.render(run, delivery)["ok"]
        receipt = json.load(open(os.path.join(delivery, "delivery-receipt.json"),
                                 encoding="utf-8"))
        receipt["script_pdf"]["sha256"] = "0" * 64
        with open(os.path.join(delivery, "delivery-receipt.json"), "w",
                  encoding="utf-8") as handle:
            json.dump(receipt, handle)
        verdict, detail = SP.check_delivery(delivery)
        assert verdict == SP.FAIL and "hash" in detail, detail

        # a PDF that set 10 pt type must fail the floor
        bad = os.path.join(delivery, "bad.pdf")
        raw = open(os.path.join(delivery, SP.PDF_NAME), "rb").read()
        assert b" 13 Tf " in raw
        with open(bad, "wb") as handle:
            handle.write(raw.replace(b" 13 Tf ", b" 10 Tf "))
        verdict, detail = SP.check_pdf(bad)
        assert verdict == SP.FAIL and "below" in detail, detail


def test_refusal_writes_nothing_into_the_folder():
    with tempfile.TemporaryDirectory() as tmp:
        run, delivery = _run(tmp, approval={
            "required": True, "status": "pending",
            "lyrics_sha": SA.lyrics_sha(LYRICS), "sent": True})
        got = SP.render(run, delivery)
        assert got["ok"] is False
        assert os.listdir(delivery) == [], os.listdir(delivery)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(exc))
    print("ALL PASS" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)