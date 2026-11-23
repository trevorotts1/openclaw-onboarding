"""preflight_run.py - N-01: one command that runs before the first paid job
and again before render, listing EVERY missing or unusable input at once.

Reads the run folder only. Never executes a paid job. Tool probes are named
and bounded; a probe that cannot run is a failure, never a silent pass
(fail closed, section 3J item 15). Stdlib only.

Run:  python3 -B scripts/core/run_preflight/preflight_run.py <run_dir>
Exit 0 when every input is present and usable, 4 when anything is listed.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

PREFLIGHT_CODE = "PREFLIGHT_INPUT_MISSING"
LINK_MAX_AGE_H = 23
PROMPT_FLOOR_CHARS = 5000
EXT_MEDIA = (".wav", ".mp3", ".m4a", ".flac", ".aac")
EXT_FONT = (".ttf", ".otf", ".ttc")


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh), None
    except FileNotFoundError:
        return None, "missing"
    except Exception as exc:                      # noqa: BLE001
        return None, "unreadable: %s" % str(exc)[:160]


def _fail(check, code, detail, next_action):
    return {"check": check, "code": code, "detail": detail,
            "next_action": next_action}


def _need_json(run_dir, rel, check, next_action):
    path = os.path.join(run_dir, rel)
    doc, err = _read_json(path)
    if err:
        return None, _fail(check, PREFLIGHT_CODE, "%s %s" % (rel, err), next_action)
    return doc, None


def _find(run_dir, rels, exts=None, name_has=None):
    for rel in rels:
        p = os.path.join(run_dir, rel)
        if os.path.isfile(p) and (not exts or p.lower().endswith(exts)):
            return p
    if exts and rels:
        for base in rels:
            d = os.path.join(run_dir, base)
            if not os.path.isdir(d):
                continue
            for root, _dirs, files in os.walk(d):
                for fn in files:
                    low = fn.lower()
                    if low.endswith(exts) and (not name_has or name_has in low):
                        return os.path.join(root, fn)
    return None


def _probe_ffmpeg_text_filter():
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False, "ffmpeg is not on PATH"
    try:
        out = subprocess.run([ffmpeg, "-hide_banner", "-filters"],
                             capture_output=True, text=True, timeout=25)
        text = (out.stdout or "") + (out.stderr or "")
        if "drawtext" in text or "subtitles" in text:
            return True, "ffmpeg text filter present"
        return False, "ffmpeg has no drawtext or subtitles filter on this box"
    except Exception as exc:                      # noqa: BLE001
        return False, "ffmpeg filter probe failed: %s" % str(exc)[:160]


def _letter_reader(run_dir):
    if shutil.which("tesseract"):
        return True, "tesseract reader present"
    doc, _err = _read_json(os.path.join(run_dir, "control", "letter-reader.json"))
    if isinstance(doc, dict) and doc.get("reader") in ("vision", "tesseract"):
        return True, "letter reader declared: %s" % doc.get("reader")
    return False, "no letter reader: tesseract missing and no vision reader declared"


def _compose_engine():
    for tool, name in (("hyperframes", "hyperframes"), ("remotion", "remotion")):
        if shutil.which(tool):
            return name
    return "ffmpeg-fallback"


def _parse_ts(value):
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value:
        from datetime import datetime, timezone
        txt = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(txt)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    return None


def _check_logo(run_dir):
    try:
        from .logo_check import validate_logo
    except ImportError:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "intake_preflight"))
        from logo_check import validate_logo
    rec, err = _read_json(os.path.join(run_dir, "control", "logo.json"))
    path = rec.get("path") if isinstance(rec, dict) else None
    if not path:
        cand = _find(run_dir, ["references", "assets"], exts=(".png",), name_has="logo")
        path = cand
    res = validate_logo(path)
    if not res["ok"]:
        return _fail("logo", res["code"],
                     "; ".join(res["reasons"]) or "logo unusable",
                     "supply a transparent PNG at least 512x512")
    return None


def run_preflight(run_dir, now_unix=None, balance=None, estimate=None,
                  prompts=None, links=None, probe_tools=True):
    """Return {"ok", "checked", "failures", "engine", "box", "report_path"}."""
    run_dir = os.path.abspath(os.fspath(run_dir))
    now = time.time() if now_unix is None else now_unix
    failures = []
    checked = 0

    def note(item):
        nonlocal checked
        checked += 1
        if item:
            failures.append(item)

    # 1. title record and 2. end-card record
    _d, f = _need_json(run_dir, "control/title.json", "title record",
                       "write control/title.json")
    note(f)
    _d, f = _need_json(run_dir, "control/end-card.json", "end-card record",
                       "write control/end-card.json")
    note(f)

    # 3. logo
    note(_check_logo(run_dir))

    # 4. storyboard shot list and 5. contracts
    _d, f = _need_json(run_dir, "storyboard/shot-list.json", "storyboard/shot-list.json",
                       "write the approved shot list")
    note(f)
    _d, f = _need_json(run_dir, "storyboard/contracts.json", "storyboard contracts",
                       "write storyboard/contracts.json")
    note(f)

    # 6. approval state (approve once; pre-authorized choice also passes)
    doc, f = _need_json(run_dir, "control/story-approval.json", "approval state",
                        "record the run owner's approval")
    note(f)
    if doc is not None:
        state = str(doc.get("status", "")).lower() if isinstance(doc, dict) else ""
        if state not in ("approved", "go_ahead_if_pass", "go-ahead-if-every-check-passes"):
            note(_fail("approval", "PREFLIGHT_APPROVAL_MISSING",
                       "approval status is %r" % state,
                       "record an approval or the go-ahead-if-every-check-passes choice"))

    # 7. control records: run lock and look lock
    for rel, label in (("control/run-lock.json", "run lock"),
                       ("control/look-lock.json", "look lock")):
        _d, f = _need_json(run_dir, rel, label, "write %s" % rel)
        note(f)

    # 8. lyric sheet, 9. word timings, 10. song master
    _d, f = _need_json(run_dir, "creative/lyrics.json", "lyric sheet",
                       "write creative/lyrics.json")
    note(f)
    _d, f = _need_json(run_dir, "music/word-timings.json", "word timings",
                       "write music/word-timings.json")
    note(f)
    song = _find(run_dir, ["music"], exts=EXT_MEDIA, name_has="master")
    if not song:
        note(_fail("song-master", PREFLIGHT_CODE, "no song master under music/",
                   "place the song master named by the run lock"))

    # 11. fonts
    font = _find(run_dir, ["references", "assets", "fonts"], exts=EXT_FONT)
    if not font:
        note(_fail("fonts", PREFLIGHT_CODE, "no font file under references/ or assets/",
                   "add the caption font file"))

    # 12. the ffmpeg text filter, 13. the letter reader, 14. the compose engine
    if probe_tools:
        ok, why = _probe_ffmpeg_text_filter()
        if not ok:
            note(_fail("ffmpeg-text-filter", PREFLIGHT_CODE, why,
                       "install an ffmpeg build with drawtext or subtitles"))
        ok, why = _letter_reader(run_dir)
        if not ok:
            note(_fail("letter-reader", PREFLIGHT_CODE, why,
                       "install tesseract or declare a vision reader"))
        checked += 1                               # the filter check
        checked += 1                               # the reader check
    engine = _compose_engine()

    # 15. upload links younger than 23 hours
    if links is None:
        doc, _err = _read_json(os.path.join(run_dir, "control", "upload-links.json"))
        links = doc.get("links", []) if isinstance(doc, dict) else (doc or [])
    stale = []
    for link in links or []:
        if isinstance(link, dict):
            ts = _parse_ts(link.get("uploaded_at") or link.get("created_at"))
            label = link.get("url") or link.get("name") or "a link"
        else:
            ts, label = None, str(link)
        if ts is None or (now - ts) > LINK_MAX_AGE_H * 3600:
            stale.append(label)
    if stale:
        note(_fail("upload-links", "PREFLIGHT_LINK_STALE",
                   "links older than %d hours: %s" % (LINK_MAX_AGE_H, ", ".join(stale[:8])),
                   "upload these files again before the burst"))

    # 16. KIE balance against the estimate (estimate plus one remake round)
    if balance is None or estimate is None:
        bdoc, _e = _read_json(os.path.join(run_dir, "control", "kie-balance.json"))
        edoc, _e = _read_json(os.path.join(run_dir, "control", "spend-estimate.json"))
        if balance is None and isinstance(bdoc, dict):
            balance = bdoc.get("balance")
        if estimate is None and isinstance(edoc, dict):
            estimate = edoc.get("estimate")
    if balance is None or estimate is None:
        note(_fail("kie-balance", PREFLIGHT_CODE,
                   "balance or estimate is unknown",
                   "read the balance and the Shot Router estimate"))
    else:
        need = float(estimate) * 1.5               # estimate plus one remake round
        if float(balance) < need:
            note(_fail("kie-balance", "PREFLIGHT_BALANCE_SHORT",
                       "balance %s is under %s (estimate %s plus one remake round)"
                       % (balance, need, estimate),
                       "top up or cut the estimate before the burst"))

    # 17. every prompt against the 5,000-character floor
    if prompts is None:
        doc, _err = _read_json(os.path.join(run_dir, "storyboard", "prompts.json"))
        raw = doc.get("prompts", []) if isinstance(doc, dict) else (doc or [])
        prompts = [p.get("text", "") if isinstance(p, dict) else str(p) for p in raw]
    short = [i for i, text in enumerate(prompts or []) if len(text or "") < PROMPT_FLOOR_CHARS]
    if short:
        note(_fail("prompts", "PROMPT_TOO_SHORT",
                   "%d prompt(s) under the %d-character floor: %s"
                   % (len(short), PROMPT_FLOOR_CHARS, short[:8]),
                   "extend each short prompt through the Prompt Builder"))

    # The box is recorded here (N-76); a missing probe never blocks the list.
    box = None
    try:
        from .box_probe import record_box
        box = record_box(run_dir)
    except Exception:                              # noqa: BLE001
        pass

    report = {"schema": "blackceo.run-preflight/v1", "run_dir": run_dir,
              "checked_at": now, "checked": checked, "ok": not failures,
              "failures": failures, "compose_engine": engine, "box": box}
    ctrl = os.path.join(run_dir, "control")
    try:
        os.makedirs(ctrl, exist_ok=True)
        tmp = os.path.join(ctrl, ".preflight-report.json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, os.path.join(ctrl, "preflight-report.json"))
        report["report_path"] = os.path.join(ctrl, "preflight-report.json")
    except OSError as exc:                         # noqa: BLE001
        report["report_path"] = None
        report["report_error"] = str(exc)[:200]
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description="N-01 run pre-flight: one command, every gap at once")
    ap.add_argument("run_dir")
    ap.add_argument("--no-tools", action="store_true", help="skip bounded tool probes")
    args = ap.parse_args(argv)
    report = run_preflight(args.run_dir, probe_tools=not args.no_tools)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
