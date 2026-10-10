#!/usr/bin/env python3
"""DEL-13 run inputs: where each producer's REAL inputs live in a run.

``package_run`` hands every ``produce_delivery(run_dir, item)`` adapter the
run folder; this module is the ONE place that says where inside a run each
producer's own deliver path reads from, and how to hand its output back to
the packaging call. It READS a run -- it never writes deliverable bytes and
never imports the fixture helpers.

Run layout consumed by the twelve adapters (everything relative to
``run_dir``; the delivery folder the producers write into is
``<run>/delivery``, the same folder the stage runbook's ``$DELIVERY`` is for
a live run)::

    item                    real inputs in the run
    ----------------------  -------------------------------------------------
    01 audio_versions       music/mix.mp3, music/instrumental.mp3,
                            music/vocal-stem.mp3
    02 character_bible      character/brief.json (character fields +
                            character_reference_images)
    03 script_pdf           creative/script.json + creative/script-approval.json
    04 storyboard_pdf       storyboard/{gate,contracts,stills,approval}.json
    05 video                edit/ad.mp4 + the approved sheet + measured timing
    06 clips                edit/timeline.json + edit/ad.mp4 + the chosen
                            length (card-answers.json, else brief.json)
    07 ready_to_post_kit    the whole run + the delivery folder built so far
    08 cover_thumbnail      storyboard stills + approval + the approved title
    09 lyric_sheet          creative/script.json
    10 captions_srt         the approved sheet + music/word-timings.json
    11 character_images     character/records.json
    12 welcome_sheet        none (this page writes itself)

Measured timing is the F17 receipt the run already holds
(``music/word-timings.json``: ``{"words": [{"word", "start", "end"}],
"source": ...}`` or the full ``provide_word_timings`` envelope). Nothing here
invents a clock: no timing file, no cues, no caption file.

stdlib only, no network, no provider call, no fixture bytes.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

#: the run's delivery folder (the stage runbook's $DELIVERY).
DELIVERY_NAME = "delivery"

#: timing receipt inside the run (F17 measured word timings).
TIMING_PATH = os.path.join("music", "word-timings.json")


class RunInputError(RuntimeError):
    """The run is missing what this producer's real deliver path needs."""


def as_run(run_dir):
    """Absolute Path of the run folder; refuses a non-directory."""
    root = Path(run_dir).expanduser()
    if not root.is_dir():
        raise RunInputError("run folder missing: %s" % root)
    return root


def delivery_dir(run_dir):
    """The run's delivery folder: <run>/delivery (created by the producer)."""
    return as_run(run_dir) / DELIVERY_NAME


def load_json(run_dir, rel):
    """Parse one JSON file inside the run, or refuse by its relative path."""
    path = as_run(run_dir) / rel
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise RunInputError("run is missing %s" % rel) from None
    except (OSError, ValueError) as exc:
        raise RunInputError("cannot read %s: %s" % (rel, exc)) from None


def load_json_optional(run_dir, rel, default=None):
    """Parse one JSON file inside the run; ``default`` when it is not there."""
    try:
        return load_json(run_dir, rel)
    except RunInputError:
        return default


def approved_lines(run_dir):
    """The approved sheet's own lines, in song order (strings).

    From ``creative/script.json`` -- the file the script approval signed off,
    so the caption clock and the burned captions can only ever carry words
    the client approved.
    """
    doc = load_json(run_dir, os.path.join("creative", "script.json"))
    if not isinstance(doc, dict):
        raise RunInputError("creative/script.json is not an object")
    lines = []
    for sec in doc.get("sheet") or []:
        if isinstance(sec, dict):
            lines += [str(x) for x in sec.get("lines") or [] if str(x).strip()]
    if not lines:
        text = str(doc.get("lyrics") or "")
        lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise RunInputError("creative/script.json carries no approved lines")
    return lines


def measured_cues(run_dir):
    """The run's measured caption cues: sheet words at measured times.

    ``caption_timing.captions`` on the approved lines and the run's own
    ``music/word-timings.json``. A run with no measured timing refuses --
    the caption file and the burned captions are never invented.
    """
    timing = load_json(run_dir, TIMING_PATH)
    try:
        import caption_timing            # noqa: PLC0415 - core is on sys.path
    except Exception as exc:             # noqa: BLE001 - reported, never passed
        raise RunInputError(
            "caption_timing unavailable: %s" % exc) from None
    cues, receipt = caption_timing.captions(approved_lines(run_dir), timing)
    if not isinstance(receipt, dict) or not receipt.get("ok") or not cues:
        raise RunInputError(
            "measured caption timing unusable (%s): %s"
            % ((receipt or {}).get("reason_code") or "NO_CUES",
               (receipt or {}).get("detail") or "no cues"))
    return cues


def audio_sources(run_dir):
    """The three audio sources item 01 re-encodes: mix, instrumental, vocal.

    Existing pipeline output only, exactly where the music stage leaves it
    (``music/``): the finished mix (``music/mix.mp3``, or the pick the client
    chose at ``music/picked-song.mp3``), the instrumental the run made and
    the vocal stem saved for every take. Missing source -> the path is
    returned as-is and the producer's own refusal names it; nothing here
    substitutes a file.
    """
    music = as_run(run_dir) / "music"
    mix = music / "mix.mp3"
    if not mix.is_file() and (music / "picked-song.mp3").is_file():
        mix = music / "picked-song.mp3"
    return {"mix": mix, "instrumental": music / "instrumental.mp3",
            "vocal": music / "vocal-stem.mp3"}


def ad_title(run_dir):
    """The ad's own title (approved script's, else the brief's)."""
    doc = load_json_optional(run_dir, os.path.join("creative", "script.json"))
    title = str((doc or {}).get("title") or "").strip()
    if title:
        return title
    brief = load_json_optional(run_dir, "brief.json")
    title = str((brief or {}).get("title") or "").strip()
    if title:
        return title
    raise RunInputError("the run carries no ad title (creative/script.json, "
                        "brief.json)")


def chosen_length_s(run_dir):
    """The chosen ad length in seconds: card answer, else the brief.

    The same source the READY-TO-POST KIT reads, so the clips item and the
    kit can never promise different lengths for one run.
    """
    answers = load_json_optional(run_dir, "card-answers.json", [])
    if isinstance(answers, dict):
        answers = answers.get("answers")
    brief = load_json_optional(run_dir, "brief.json")
    try:
        from ready_post_kit.ready_post_kit import (           # noqa: PLC0415
            answer_map, chosen_length_s as _from_card)
    except Exception as exc:              # noqa: BLE001 - reported, never passed
        raise RunInputError("ready_post_kit unavailable: %s" % exc) from None
    length = _from_card(answer_map(answers if isinstance(answers, list) else []),
                        brief)
    if not length:
        raise RunInputError("the run carries no chosen ad length "
                            "(card-answers.json / brief.json)")
    return int(length)


def _has_filter(exe, name):
    """Measured: does THIS ffmpeg build ship the filter? Never assumed."""
    if not exe:
        return False
    try:
        proc = subprocess.run([exe, "-hide_banner", "-filters"],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    text = (proc.stdout or "") + (proc.stderr or "")
    return any(token == name for token in text.split())


def ffmpeg_with(filter_name, env_var=""):
    """An ffmpeg that MEASURES carrying ``filter_name`` (fail closed).

    Order: the operator's env override, the PATH ffmpeg, then the bundled
    ``imageio_ffmpeg`` build. The real deliver path burns with this binary
    (the stage runbook tells a live run to point ``--ffmpeg`` at a build that
    has the filter); an adapter never fakes the output when none exists.
    """
    candidates = []
    if env_var:
        override = os.environ.get(env_var, "").strip()
        if override:
            candidates.append(override)
    path_ff = shutil.which("ffmpeg")
    if path_ff:
        candidates.append(path_ff)
    try:
        import imageio_ffmpeg                  # noqa: PLC0415
        candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:                          # noqa: BLE001 - optional binary
        pass
    for exe in candidates:
        if _has_filter(exe, filter_name):
            return exe
    raise RunInputError("no ffmpeg on this box carries the %r filter "
                        "(tried: %s)" % (filter_name,
                                         ", ".join(candidates) or "nothing"))


def stage(item, folder):
    """The contract's files for ``item`` as the packaging call expects them.

    One Path per canonical file, in contract order. A deliver path that did
    not actually write every file refuses here, so COMPONENT_FAILED names the
    gap instead of a silently incomplete folder.
    """
    folder = Path(folder)
    missing = [name for name in item.files if not (folder / name).exists()]
    if missing:
        raise RunInputError(
            "%s deliver path left %d of %d file(s) unwritten in %s: %s"
            % (item.key, len(missing), len(item.files), folder,
               ", ".join(missing)))
    return [folder / name for name in item.files]


__all__ = ["RunInputError", "DELIVERY_NAME", "TIMING_PATH", "as_run",
           "delivery_dir", "load_json", "load_json_optional",
           "approved_lines", "measured_cues", "audio_sources", "ad_title",
           "chosen_length_s", "ffmpeg_with", "stage"]
