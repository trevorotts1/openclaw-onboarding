"""MOCK-only unit tests — scrub_turn_telemetry (V2 evidence hygiene, R7 P3).

These tests are MOCK-ONLY. No network, no browser, no real client data — the
"telemetry" is synthetic and uses the literal leak token (``redacted-client``)
that the V2 capture exposed, plus generic verbs. The assertions cover:

  * the leaked ``<client>__<verb>`` MCP tool-name prefix is neutralised to
    ``mcp__redacted__<verb>`` in both VALUES and dict KEYS,
  * the tool VERB after ``__`` is preserved (telemetry stays useful),
  * structural JSON scrub round-trips to valid JSON,
  * ``is_clean`` / ``--check`` detect any residual leak (fail-loud),
  * a non-JSON file with a .json extension is scrubbed as text (never fail-open).

No real client identity is asserted as legitimate — the token is treated purely
as a string to redact.
"""
from __future__ import annotations

import json
import os
import sys

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest

import scrub_turn_telemetry as scrub


# The exact shapes observed in the V2 capture (logs/agent-turn-3.out.json).
LEAKED_NAMES = [
    "redacted-client__messages_send",
    "redacted-client__conversations_list",
    "redacted-client__events_poll",
    "redacted-client__permissions_respond",
]


class TestScrubText:
    def test_neutralises_namespace_keeps_verb(self):
        out, n = scrub.scrub_text("calling redacted-client__messages_send now")
        assert "redacted-client__" not in out
        assert "mcp__redacted__messages_send" in out   # verb preserved
        assert n == 1

    def test_counts_all_occurrences(self):
        text = " ".join(LEAKED_NAMES)
        out, n = scrub.scrub_text(text)
        assert n == len(LEAKED_NAMES)
        assert scrub.is_clean(out)

    def test_does_not_touch_unrelated_text(self):
        text = "the agent built a funnel and saved a draft"
        out, n = scrub.scrub_text(text)
        assert out == text
        assert n == 0

    def test_does_not_clip_larger_identifier(self):
        # A token that merely CONTAINS the leak word as a substring of a larger
        # word (no '__' boundary) is left alone.
        text = "notredacted-clientfoo"  # no '__' -> not a namespaced tool name
        out, n = scrub.scrub_text(text)
        assert n == 0
        assert out == text


class TestScrubObj:
    def test_scrubs_values_and_keys(self):
        obj = {
            "tools_used": LEAKED_NAMES,
            "timing": {"redacted-client__messages_send": 12, "other": 3},
            "note": "fired redacted-client__events_poll",
        }
        out, n = scrub.scrub_obj(obj)
        flat = json.dumps(out)
        assert "redacted-client__" not in flat
        # Key was scrubbed (namespace neutralised, verb kept).
        assert "mcp__redacted__messages_send" in out["timing"]
        assert out["timing"]["mcp__redacted__messages_send"] == 12
        assert n >= len(LEAKED_NAMES) + 2   # list + key + note

    def test_numbers_and_none_untouched(self):
        obj = {"a": 1, "b": None, "c": True, "d": [1, 2.5]}
        out, n = scrub.scrub_obj(obj)
        assert out == obj
        assert n == 0


class TestScrubFile:
    def test_json_file_roundtrips_clean(self, tmp_path):
        src = tmp_path / "agent-turn-3.out.json"
        src.write_text(json.dumps({"tools_used": LEAKED_NAMES}), encoding="utf-8")
        rec = scrub.scrub_file(str(src))
        assert rec["format"] == "json"
        assert rec["replacements"] == len(LEAKED_NAMES)
        cleaned = src.read_text(encoding="utf-8")
        assert scrub.is_clean(cleaned)
        # Still valid JSON after scrub.
        json.loads(cleaned)

    def test_out_dir_writes_copy_leaves_source(self, tmp_path):
        src = tmp_path / "turn.json"
        src.write_text(json.dumps({"x": "redacted-client__messages_send"}), encoding="utf-8")
        outdir = tmp_path / "clean"
        outdir.mkdir()
        rec = scrub.scrub_file(str(src), str(outdir / "turn.json"))
        assert scrub.is_clean((outdir / "turn.json").read_text(encoding="utf-8"))

    def test_invalid_json_extension_scrubbed_as_text_not_fail_open(self, tmp_path):
        # A .json file that is actually NOT valid JSON must still be scrubbed
        # (fail-CLOSED) — never written back with the leak intact.
        src = tmp_path / "broken.json"
        src.write_text("{not valid json redacted-client__events_poll", encoding="utf-8")
        rec = scrub.scrub_file(str(src))
        assert rec["format"] == "text"
        assert rec["replacements"] == 1
        assert scrub.is_clean(src.read_text(encoding="utf-8"))


class TestIsCleanAndCheck:
    def test_is_clean_detects_leak(self):
        assert scrub.is_clean("all good here") is True
        assert scrub.is_clean("oops redacted-client__messages_send") is False

    def test_check_mode_exit_codes(self, tmp_path):
        dirty = tmp_path / "d.json"
        dirty.write_text(json.dumps({"x": "redacted-client__events_poll"}), encoding="utf-8")
        clean = tmp_path / "c.json"
        clean.write_text(json.dumps({"x": "ok"}), encoding="utf-8")
        # --check on a dirty file returns non-zero (fail-loud).
        assert scrub.main(["--check", str(dirty)]) == 1
        # --check on a clean file returns zero.
        assert scrub.main(["--check", str(clean)]) == 0

    def test_extra_token_redacted(self):
        out, n = scrub.scrub_text("acme-corp__messages_send", tokens=("redacted-client", "acme-corp"))
        assert n == 1
        assert "acme-corp__" not in out
