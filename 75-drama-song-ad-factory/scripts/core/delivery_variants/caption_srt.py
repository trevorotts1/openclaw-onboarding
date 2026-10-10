"""DEL-10: the delivery folder ships the caption file (.srt).

The client cleans captions up in an editor, so a run exports ONE .srt into
its own delivery folder at the end of the run, named by the package map
(``10 - Captions.srt``; slot ``FILE_NUMBER`` is the one constant to move).

The words and the clock are the pipeline's, never re-authored here: cues
arrive from the measured caption timing (``caption_timing.captions(sheet,
timing)`` -> ``protected_names.build_captions``) and the SRT text is built
by ``final_assembler.captions_burn.build_srt`` — the same builder the
caption burn uses — so the exported file and the burned captions cannot
drift apart. The text is parsed back before it is written: a file that
lands is valid SRT by construction.

Fail closed (F18): no measured cues -> refusal receipt, no file, no
invented clock. Stdlib only: no network, no ffmpeg, no transcription
import (the one transcription step stays in audio_c3/lyric_timing.py).

Run: python3 scripts/core/delivery_variants/test_caption_srt_del10.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

_CORE = Path(__file__).resolve().parents[1]
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

TOOL_NAME = "caption_srt"
TOOL_VERSION = "1.0.0"
CHECK_NAME = "caption_srt"

#: Package map slot for the caption file: one constant, renumber here.
FILE_NUMBER = 10
FILE_LABEL = "Captions"
FILE_EXT = ".srt"

PASS = "PASS"
FAIL = "FAIL"

#: Refusal codes (fail-closed, never a silent pass).
BAD_INPUT = "SRT_BAD_INPUT"
NO_CUES = "SRT_NO_MEASURED_CUES"
BAD_CUES = "SRT_CUES_INVALID"
NO_SOURCE = "SRT_BURN_SOURCE_UNAVAILABLE"
WRITE_FAILED = "SRT_WRITE_FAILED"

_TIMESTAMP_RE = re.compile(
    r"^(\d{2,}):([0-5]\d):([0-5]\d),(\d{3}) --> "
    r"(\d{2,}):([0-5]\d):([0-5]\d),(\d{3})$")


def srt_file_name(number=FILE_NUMBER):
    """The numbered name the client sees: ``10 - Captions.srt``."""
    n = int(number)
    if n < 0 or n > 99:
        raise ValueError("%s: file number must be 0-99, got %r"
                         % (BAD_INPUT, number))
    label = re.sub(r"[^\w\- ]+", "", FILE_LABEL).strip() or "Captions"
    return "%02d - %s%s" % (n, label, FILE_EXT)


def _refuse(reason_code, detail, **extra):
    """A refusal receipt: no file written, no clock invented."""
    out = {"ok": False, "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
           "check": CHECK_NAME, "file": None, "path": None, "cue_count": 0,
           "sha256": None, "timing": "unavailable",
           "reason_code": reason_code, "detail": detail}
    out.update(extra)
    return out


def _seconds(h, m, s, ms):
    return (int(h) * 3600 + int(m) * 60 + int(s)) + int(ms) / 1000.0


def parse_srt(text):
    """Parse SRT text back to cues. Raises ValueError on any structure break.

    Independent of the writer: sequential 1..N indexes, one timestamp line
    per cue in ``HH:MM:SS,mmm --> HH:MM:SS,mmm`` form, start <= end, a
    non-empty text body, cues in time order. Returns
    [{"index", "start", "end", "text"}].
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty caption file")
    blocks = re.split(r"(?:\r?\n){2,}", text.strip("\r\n"))
    cues = []
    prev_start = None
    for i, block in enumerate(blocks, 1):
        lines = block.split("\n")
        if len(lines) < 3:
            raise ValueError("cue %d: needs an index, a timing line and text"
                             % i)
        if lines[0].strip() != str(i):
            raise ValueError("cue %d: index line is %r, expected %d"
                             % (i, lines[0], i))
        m = _TIMESTAMP_RE.match(lines[1].strip())
        if not m:
            raise ValueError("cue %d: bad timing line %r" % (i, lines[1]))
        start = _seconds(*m.groups()[:4])
        end = _seconds(*m.groups()[4:])
        if end < start:
            raise ValueError("cue %d: ends before it starts" % i)
        if prev_start is not None and start < prev_start:
            raise ValueError("cue %d: cues are not in time order" % i)
        body = "\n".join(lines[2:])
        if not body.strip():
            raise ValueError("cue %d: no text" % i)
        cues.append({"index": i, "start": start, "end": end, "text": body})
        prev_start = start
    return cues


def export_captions_srt(delivery_dir, cues, number=FILE_NUMBER):
    """Write the delivery folder's numbered .srt from MEASURED cues.

    ``cues`` is what the pipeline already produced (``{"text", "start",
    "end"}`` windows from ``caption_timing.captions``). Returns a receipt:
    ``ok``/``file``/``path``/``cue_count``/``sha256``/``timing`` plus a
    ``reason_code`` on refusal. Fail closed: empty or unusable cues write
    nothing (``timing`` stays ``"unavailable"``), a bad delivery folder is
    reported, never worked around.
    """
    if not isinstance(delivery_dir, (str, os.PathLike)) \
            or not str(delivery_dir).strip():
        return _refuse(BAD_INPUT, "delivery_dir required")
    if not isinstance(cues, (list, tuple)):
        return _refuse(BAD_INPUT, "cues must be a list of measured windows")
    if not cues:
        return _refuse(NO_CUES,
                       "no measured cues; the caption file is not invented")
    try:
        import importlib
        burn = importlib.import_module("final_assembler.captions_burn")
    except Exception as exc:  # noqa: BLE001 - reported, never a pass
        return _refuse(NO_SOURCE, "captions_burn unavailable: %s" % exc)
    try:
        text = burn.build_srt(cues)
    except ValueError as exc:
        detail = str(exc)
        code = NO_CUES if "no cue" in detail else BAD_CUES
        return _refuse(code, detail)
    try:
        parsed = parse_srt(text)
    except ValueError as exc:  # a file that cannot parse is never written
        return _refuse(BAD_CUES, "built text is not valid SRT: %s" % exc)
    name = srt_file_name(number)
    path = os.path.join(str(delivery_dir), name)
    try:
        os.makedirs(str(delivery_dir), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    except OSError as exc:
        return _refuse(WRITE_FAILED, str(exc))
    return {"ok": True, "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
            "check": CHECK_NAME, "file": name, "path": path,
            "cue_count": len(parsed),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "timing": "measured", "reason_code": None, "detail": None}


def check_captions_srt(delivery_dir, number=FILE_NUMBER):
    """QC gate: (PASS|FAIL, detail). Missing or unparseable = FAIL."""
    name = srt_file_name(number)
    path = os.path.join(str(delivery_dir or ""), name)
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return (FAIL, "delivery missing caption file %s" % name)
    try:
        cues = parse_srt(text)
    except ValueError as exc:
        return (FAIL, "%s is not valid SRT: %s" % (name, exc))
    return (PASS, "%s carries %d valid cues" % (name, len(cues)))


def _cli(argv=None):
    """CLI: ``export <delivery_dir> <cues.json>`` | ``check <delivery_dir>``."""
    args = sys.argv[1:] if argv is None else list(argv)
    if len(args) == 2 and args[0] == "check":
        verdict, detail = check_captions_srt(args[1])
        print(json.dumps({"check": CHECK_NAME, "verdict": verdict,
                          "detail": detail}))
        return 0 if verdict == PASS else 5
    if len(args) == 3 and args[0] == "export":
        try:
            cues = json.loads(Path(args[2]).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(json.dumps({"outcome": "error", "reason_code": BAD_INPUT,
                              "detail": str(exc)}))
            return 1
        receipt = export_captions_srt(args[1], cues)
        print(json.dumps(receipt, sort_keys=True))
        return 0 if receipt.get("ok") else 5
    print(json.dumps({"outcome": "error", "reason_code": BAD_INPUT,
                      "detail": "usage: caption_srt.py export "
                                "<delivery_dir> <cues.json> | "
                                "check <delivery_dir>"}))
    return 1



def produce_delivery(run_dir, item):
    """DEL-13 packaging adapter: the REAL DEL-10 deliver path (the .srt).

    Builds the cues exactly as the pipeline does -- the run's approved sheet
    timed by the run's own measured word timings
    (``music/word-timings.json`` via ``caption_timing.captions``) -- and
    hands them to ``export_captions_srt``. No measured timing is a refusal
    (RunInputError), never an invented clock and never fixture SRT text:
    ``contract.produce_item`` is test-only and no deliver path imports it.
    Signature: produce_delivery(run_dir, item) -> list[Path].
    """
    from delivery_package import run_inputs as RI
    out = RI.delivery_dir(run_dir)
    cues = RI.measured_cues(run_dir)
    receipt = export_captions_srt(str(out), cues)
    if not (isinstance(receipt, dict) and receipt.get("ok")):
        raise RI.RunInputError("caption export refused (%s): %s"
                               % ((receipt or {}).get("reason_code") or "?",
                                  (receipt or {}).get("detail") or "?"))
    return RI.stage(item, out)


if __name__ == "__main__":
    raise SystemExit(_cli())
