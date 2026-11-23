#!/usr/bin/env python3
"""run_preflight.py - N-01: one command, every missing or unusable input listed
at once, before the first paid job and again before render. Stdlib only.

The rule (plan N-01): a run may not begin paid work with a hole in its inputs.
This module checks EVERY input on one pass and returns the complete list; it
never stops at the first failure, because a list of one hole costs a second
round trip and the plan exists to stop that.

Inputs checked here:
  title record, end-card record, logo, storyboard/shot-list.json, contracts,
  approval state, control/ records, lyric sheet, word timings, song master,
  fonts, the ffmpeg text filter, the letter reader, HyperFrames or the
  fallback compose engine, upload links younger than 23 hours, KIE balance
  against the estimate, and every prompt against the 5,000-character floor.

Values may be read from a run folder on disk, or supplied in a payload (so the
check can be exercised without a live run). A supplied value always wins; a
missing one is reported, never guessed.

Outcomes: ``ok`` (every input usable) or ``rejected`` with reason
``RUN_PREFLIGHT_UNUSABLE`` and the full ``missing`` and ``unusable`` lists.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys

SCHEMA = "blackceo.run-preflight/v1"
MIN_PROMPT_CHARS = 5000                 # section 2: the 5,000-character floor
LINK_MAX_AGE_S = 23 * 3600              # section 10C row 23
MIN_DISK_FREE_PCT = 10                  # section 3D.8 / 3J MAJOR 18
DEFAULT_TOOLS = ("ffmpeg", "ffprobe")
LETTER_READER_TOOLS = ("tesseract",)
COMPOSE_ENGINES = ("hyperframes", "remotion", "ffmpeg-fallback")

#: (id, candidate relative paths, kind). The first existing path satisfies the
#: input; an input is missing only when none exists.
WITHIN_RUN_INPUTS = (
    ("title-record", ("control/title.json", "creative/title.json"), "json"),
    ("end-card-record", ("control/end-card.json", "control/endcard.json",
                         "creative/end-card.json"), "json"),
    ("shot-list", ("storyboard/shot-list.json",), "json"),
    ("contracts", ("control/contracts.json", "control/contracts"), "any"),
    ("approval-state", ("control/approval.json", "control/approval-state.json"), "json"),
    ("control-records", ("control",), "dir"),
    ("lyric-sheet", ("creative/lyrics.json", "music/lyrics.json"), "json"),
    ("word-timings", ("music/word-timings.json", "creative/word-timings.json"), "json"),
    ("song-master", ("music/picked-song.mp3", "music/master.mp3",
                     "music/master.wav"), "media"),
    ("fonts", ("control/fonts.json", "assets/fonts"), "any"),
)


def _first_existing(run_dir, rels):
    for rel in rels:
        path = os.path.join(run_dir, rel)
        if os.path.exists(path):
            return rel, path
    return None, None


def _read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _row(check_id, ok, detail, unusable=False):
    return {"id": check_id, "ok": bool(ok), "unusable": bool(unusable),
            "detail": detail}


def check_within_run(run_dir, provided=None):
    """Return the rows for the inputs that live in the run folder."""
    provided = provided or {}
    rows = []
    for check_id, rels, kind in WITHIN_RUN_INPUTS:
        if check_id in provided:
            ok = bool(provided[check_id])
            rows.append(_row(check_id, ok,
                             "supplied" if ok else "supplied as unusable",
                             unusable=not ok))
            continue
        rel, path = _first_existing(run_dir, rels) if run_dir else (None, None)
        if path is None:
            rows.append(_row(check_id, False,
                             "none of %s exists" % ", ".join(rels)))
            continue
        if kind == "json":
            try:
                _read_json(path)
            except (OSError, ValueError) as exc:
                rows.append(_row(check_id, False, "%s unreadable: %s" % (rel, exc),
                                 unusable=True))
                continue
        if kind == "media" and os.path.getsize(path) <= 0:
            rows.append(_row(check_id, False, "%s is empty" % rel, unusable=True))
            continue
        rows.append(_row(check_id, True, rel))
    return rows


def check_tools(names):
    return {name: shutil.which(name) is not None for name in names}


def check_letter_reader(payload):
    """The letter reader is tesseract, found by NAME; presence only."""
    supplied = payload.get("letter_reader")
    if supplied is not None:
        return _row("letter-reader", bool(supplied),
                    "supplied" if supplied else "no reader supplied")
    found = check_tools(LETTER_READER_TOOLS)
    ok = all(found.values())
    return _row("letter-reader", ok,
                "tesseract found" if ok else "tesseract not on PATH")


def check_text_filter(payload):
    """ffmpeg's text drawing filter is a capability flag; never executed here."""
    supplied = payload.get("ffmpeg_text_filter")
    if supplied is None:
        return _row("ffmpeg-text-filter", False,
                    "not recorded; pre-flight must record the ffmpeg text filter state")
    return _row("ffmpeg-text-filter", bool(supplied),
                "present" if supplied else "ffmpeg has no text drawing filter",
                unusable=not supplied)


def check_compose_engine(payload):
    engine = payload.get("compose_engine")
    if engine is None:
        return _row("compose-engine", False,
                    "not recorded; pre-flight must name hyperframes, remotion or ffmpeg-fallback")
    ok = engine in COMPOSE_ENGINES
    return _row("compose-engine", ok,
                engine if ok else "unknown engine %r" % (engine,), unusable=not ok)


def check_upload_links(payload, now=None):
    links = payload.get("upload_links")
    if links is None:
        return _row("upload-links", True, "no links to check")
    now = now if now is not None else _now_s()
    stale = []
    for link in links:
        age = link.get("age_s")
        if age is None and link.get("created_at") is not None:
            age = now - float(link["created_at"])
        if age is None or age >= LINK_MAX_AGE_S:
            stale.append(link.get("url") or link.get("id") or "?")
    ok = not stale
    return _row("upload-links", ok,
                "all younger than 23 hours" if ok else
                "older than 23 hours, re-upload: %s" % ", ".join(stale),
                unusable=not ok)


def check_kie_balance(payload):
    balance = payload.get("kie_balance")
    estimate = payload.get("kie_estimate")
    if balance is None or estimate is None:
        return _row("kie-balance", False,
                    "balance and estimate are both required to compare")
    ok = float(balance) >= float(estimate)
    return _row("kie-balance", ok,
                "balance %s >= estimate %s" % (balance, estimate) if ok else
                "balance %s is under the estimate %s" % (balance, estimate),
                unusable=not ok)


def check_prompts(payload):
    prompts = payload.get("prompts")
    if prompts is None:
        return _row("prompt-length", False,
                    "no prompts supplied to check against the 5,000-character floor")
    short = [i for i, text in enumerate(prompts) if len(text or "") < MIN_PROMPT_CHARS]
    ok = not short
    return _row("prompt-length", ok,
                "every prompt meets the floor" if ok else
                "below the 5,000-character floor: %s" % short, unusable=not ok)


def check_disk(path, now=None):
    try:
        usage = shutil.disk_usage(path or os.getcwd())
    except OSError as exc:
        return _row("disk", False, "disk cannot be read: %s" % exc, unusable=True)
    free_pct = 100.0 * usage.free / usage.total if usage.total else 0.0
    ok = free_pct >= MIN_DISK_FREE_PCT
    return _row("disk", ok, "%.1f%% free" % free_pct, unusable=not ok)


def _now_s():
    import time
    return time.time()


def preflight(payload=None):
    """Run every input check on one pass. ``payload`` keys:
    run_dir, provided{id:bool}, logo_path, tools[], letter_reader,
    ffmpeg_text_filter, compose_engine, upload_links[{url,age_s|created_at}],
    kie_balance, kie_estimate, prompts[], disk_path, now.
    Returns {schema, outcome, reason_code, missing[], unusable[], checks[]}.
    """
    payload = payload or {}
    run_dir = payload.get("run_dir")
    rows = []
    rows.extend(check_within_run(run_dir, payload.get("provided")))

    # Logo presence here; its PNG/alpha/size validation is F-EOC-2's job and
    # is added in this same unit.
    logo = payload.get("logo_path")
    if logo is None and run_dir:
        logo, _ = _first_existing(run_dir, ("assets/logo.png", "control/logo.png"))
    rows.append(_row("logo", bool(logo),
                     logo if logo else "no logo path recorded (assets/logo.png)",
                     unusable=False))

    tools = check_tools(payload.get("tools") or DEFAULT_TOOLS)
    missing_tools = sorted(name for name, ok in tools.items() if not ok)
    rows.append(_row("runtime-tools", not missing_tools,
                     "found" if not missing_tools else "missing: %s" % ", ".join(missing_tools)))
    rows.append(check_letter_reader(payload))
    rows.append(check_text_filter(payload))
    rows.append(check_compose_engine(payload))
    rows.append(check_upload_links(payload, payload.get("now")))
    rows.append(check_kie_balance(payload))
    rows.append(check_prompts(payload))
    rows.append(check_disk(payload.get("disk_path") or run_dir, payload.get("now")))

    wrong = [r["id"] for r in rows if not r["ok"]]
    unusable = [r["id"] for r in rows if r["unusable"]]
    out = {"schema": SCHEMA, "checks": rows,
           "missing": wrong, "unusable": unusable}
    if wrong:
        out.update(outcome="rejected", reason_code="RUN_PREFLIGHT_UNUSABLE",
                   next_action="Fix every listed input on one pass, then run "
                               "pre-flight again before any paid job.")
    else:
        out.update(outcome="ok", reason_code="RUN_PREFLIGHT_OK",
                   next_action="Inputs complete. Run again before render.")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--payload", default=None,
                    help="JSON file of supplied values (logo path, prompts, links...)")
    args = ap.parse_args(argv)
    payload = {"run_dir": args.run_dir}
    if args.payload:
        with open(args.payload, encoding="utf-8") as fh:
            payload.update(json.load(fh))
        payload["run_dir"] = args.run_dir
    result = preflight(payload)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["outcome"] == "ok" else 4


if __name__ == "__main__":
    sys.exit(main())
