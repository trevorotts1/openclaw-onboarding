#!/usr/bin/env python3
"""S75-081: one song validator, one style rule. Zero network, zero spend.

Proves ``music_director.validate_payload``:
  1. the caller's environment passes through, so Skill 74's answer is the one
     used: a stand-in adapter that reports the Suno style as CEILING_ONLY at
     500 lets a 500-character style PASS;
  2. the control: with Skill 74 switched off, that same 500-character style is
     refused (the old behaviour this fix removes);
  3. a validator file that is not installed comes back as ``"missing": True``,
     never as a bare exit 2.

Run: python3 -B scripts/core/music_director/test_validate_payload_s75_081.py
Exit 0 = all pass, 1 = failures.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)

# Judge the SOURCE on disk, never a stale __pycache__.
_CACHE = os.path.join(CORE, "__pycache__")
if os.path.isdir(_CACHE):
    for _n in os.listdir(_CACHE):
        if _n.endswith(".pyc"):
            try:
                os.remove(os.path.join(_CACHE, _n))
            except OSError:
                pass

import music_director as MD          # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


_WORDS = ("warm 90s R&B, half-time drop, spoken opener, live drums, wide "
          "chorus, resolved ending. ")
STYLE_500 = (_WORDS * (500 // len(_WORDS) + 1))[:500]


def envelope(style):
    """One current createTask generate envelope (the shape the song path sends)."""
    return {"endpoint": "https://api.kie.ai/api/v1/jobs/createTask",
            "model": "ai-music-api/generate",
            "input": {"custom_mode": True, "instrumental": False, "model": "V6",
                      "style": style, "title": "One Song",
                      "lyrics": "[Verse] One closed door.",
                      "negative_tags": "", "duration": 30}}


def fake_adapter(td):
    """A stand-in Skill 74 answering `prompt-budget` with a CEILING_ONLY 500."""
    path = Path(td) / "kie_live_adapter.py"
    path.write_text(
        "import json, sys\n"
        "answer = {'data': {'status': 'CEILING_ONLY', 'max': 500,\n"
        "                   'limit_source': 'stand-in live schema',\n"
        "                   'schema_version': 'stand-in-1', 'verbatim': False,\n"
        "                   'provider': 'kie'}}\n"
        "sys.stdout.write(json.dumps(\n"
        "    answer if sys.argv[1:2] == ['prompt-budget'] else {}))\n",
        encoding="utf-8")
    return str(path)


class adapter_env:
    """Set KIE_LIVE_ADAPTER_PATH for one case, then put the old value back."""

    def __init__(self, value):
        self.value = value
        self.saved = os.environ.get("KIE_LIVE_ADAPTER_PATH")
        self.had = "KIE_LIVE_ADAPTER_PATH" in os.environ

    def __enter__(self):
        os.environ["KIE_LIVE_ADAPTER_PATH"] = self.value
        return self

    def __exit__(self, *exc):
        if self.had:
            os.environ["KIE_LIVE_ADAPTER_PATH"] = self.saved
        else:
            os.environ.pop("KIE_LIVE_ADAPTER_PATH", None)
        return False


def test_ceiling_only_style_passes():
    with tempfile.TemporaryDirectory(prefix="s75-081-") as td:
        with adapter_env(fake_adapter(td)):
            res = MD.validate_payload(envelope(STYLE_500))
    check("a ceiling-only Skill 74 answer lets a 500-character style pass",
          res["ok"] is True and res["rc"] == 0, json.dumps(res)[:400])


def test_without_skill_74_the_style_is_refused():
    with adapter_env(""):          # the bridge's own off switch; no network
        res = MD.validate_payload(envelope(STYLE_500))
    check("with Skill 74 off the same style is refused (the control)",
          res["ok"] is False and res["rc"] != 0, json.dumps(res)[:400])


def test_missing_validator_is_reported():
    original = MD.workcopy_paths
    with tempfile.TemporaryDirectory(prefix="s75-081-missing-") as td:
        missing = os.path.join(td, "scripts", "validate_audio_request.py")
        try:
            MD.workcopy_paths = lambda: {"root": td, "models": "",
                                         "validator": missing}
            with adapter_env(""):
                res = MD.validate_payload(envelope(STYLE_500))
        finally:
            MD.workcopy_paths = original
    check("a missing validator file is reported as missing, not exit 2",
          res.get("missing") is True and res["ok"] is False
          and res.get("rc") is None, json.dumps(res)[:400])


def main():
    test_ceiling_only_style_passes()
    test_without_skill_74_the_style_is_refused()
    test_missing_validator_is_reported()
    print()
    if FAILS:
        print("FAILED: %d" % len(FAILS))
        for f in FAILS:
            print("  - %s" % f)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
