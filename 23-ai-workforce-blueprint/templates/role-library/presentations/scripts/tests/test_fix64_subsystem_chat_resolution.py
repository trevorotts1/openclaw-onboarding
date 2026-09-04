"""FIX 64 (one notification transport) -- subsystem chat-id resolution tests.

The proof this file pins:
  1. resolve_subsystem_chat() (report.py, the dispatch3 choke point) maps
     "watchdog"/"supervisor"/"capacity" to OWNER_CHAT_ID, and keeps the label
     verbatim when OWNER_CHAT_ID is unset (never a fabricated id).
  2. resolve_chat_id_for_transport() (presentation-notify.py, the transport
     boundary) maps a label to the numeric operator id from the tiered env
     keys, prefixes the message with the label, and returns "" (exit-4
     undeliverable, queued for --sweep-undeliverable) when nothing resolves.
  3. is_numeric_chat_id() discriminates: signed/supergroup numerics are real
     targets, subsystem labels never are.
  4. dispatch3 passes a real numeric chat_id through UNCHANGED.
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent


def _load_notify_module():
    """presentation-notify.py is a hyphenated top-level script (no package),
    loaded by path -- the same way a bare python3 run imports it."""
    spec = importlib.util.spec_from_file_location(
        "presentation_notify_f64", str(SCRIPTS / "presentation-notify.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


from presentation_job.report import (  # noqa: E402
    CheckResult,
    KNOWN_SUBSYSTEM_IDS,
    dispatch3,
    is_numeric_chat_id as report_is_numeric,
    resolve_subsystem_chat,
)


# --------------------------------------------------------------------------
# 1. dispatch3 choke point (report.py)
# --------------------------------------------------------------------------

class TestResolveSubsystemChat:
    @pytest.mark.parametrize("label", ["watchdog", "supervisor", "capacity"])
    def test_label_resolves_to_owner_chat_id(self, monkeypatch, label):
        monkeypatch.setenv("OWNER_CHAT_ID", "8505558285")
        assert resolve_subsystem_chat(label) == "8505558285"

    @pytest.mark.parametrize("label", ["watchdog", "supervisor", "capacity"])
    def test_label_kept_verbatim_when_owner_unset(self, monkeypatch, label):
        monkeypatch.delenv("OWNER_CHAT_ID", raising=False)
        assert resolve_subsystem_chat(label) == label

    def test_real_chat_id_never_touched(self, monkeypatch):
        monkeypatch.setenv("OWNER_CHAT_ID", "1111111111")
        assert resolve_subsystem_chat("8505558285") == "8505558285"
        assert resolve_subsystem_chat("-1001234567890") == "-1001234567890"

    def test_known_subsystem_ids_are_exactly_the_three(self):
        assert KNOWN_SUBSYSTEM_IDS == ("watchdog", "supervisor", "capacity")

    def test_dispatch3_numeric_chat_id_passes_through(self, tmp_path, monkeypatch):
        stub = tmp_path / "stub-notify.py"
        stub.write_text(
            "import json,sys\n"
            "doc = json.load(sys.stdin)\n"
            "Path = None\n"
            "open(sys.argv[1], 'w').write(json.dumps(doc))\n",
            encoding="utf-8")
        out = tmp_path / "payload.json"
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD",
                           f"{sys.executable} {stub} {out}")
        res = dispatch3("8505558285", "stall", "numeric passthrough probe")
        assert res is CheckResult.PASS
        doc = json.loads(out.read_text())
        assert doc["chat_id"] == "8505558285"


# --------------------------------------------------------------------------
# 2. transport boundary (presentation-notify.py)
# --------------------------------------------------------------------------

class TestTransportBoundary:
    def test_label_resolves_via_owner_chat_id_env(self, monkeypatch):
        T = _load_notify_module()
        monkeypatch.setenv("OWNER_CHAT_ID", "8505558285")
        target, prefix = T.resolve_chat_id_for_transport("watchdog")
        assert target == "8505558285"
        assert prefix == "[watchdog] "

    def test_label_resolves_via_presentation_tier_key(self, monkeypatch):
        T = _load_notify_module()
        for key in ("OWNER_CHAT_ID", "OPENCLAW_OWNER_CHAT_ID"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("PRESENTATION_OWNER_CHAT_ID", "424242")
        target, prefix = T.resolve_chat_id_for_transport("supervisor")
        assert target == "424242"
        assert prefix == "[supervisor] "

    def test_unresolvable_label_is_undeliverable_not_a_target(self, monkeypatch):
        T = _load_notify_module()
        for key in T.OWNER_CHAT_ID_ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
        target, prefix = T.resolve_chat_id_for_transport(
            "watchdog", env={}, config_path="/nonexistent/openclaw.json")
        assert target == ""
        assert prefix == ""

    def test_non_numeric_operator_value_never_becomes_a_target(self, monkeypatch):
        T = _load_notify_module()
        # OWNER_CHAT_ID holds a LABEL (the exact historical misconfiguration):
        # the transport must not hand a non-numeric string to the gateway.
        monkeypatch.setenv("OWNER_CHAT_ID", "watchdog")
        target, prefix = T.resolve_chat_id_for_transport("capacity")
        assert target == ""
        assert prefix == ""

    def test_exit4_when_no_target_anywhere(self, monkeypatch, tmp_path):
        """The transport runs standalone (dispatch3 bypassed) with a label and
        NO resolvable id: exit 4 (undeliverable, queued for the sweep), never
        a fabricated id, never a silent drop."""
        for key in ("OWNER_CHAT_ID", "OPENCLAW_OWNER_CHAT_ID",
                    "PRESENTATION_OWNER_CHAT_ID", "OWNER_TELEGRAM_CHAT_ID",
                    "TELEGRAM_CHAT_ID"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))  # no openclaw.json fallback
        import subprocess
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "presentation-notify.py")],
            input=json.dumps({"chat_id": "watchdog", "kind": "stall",
                              "message": "hermetic undeliverable probe"}),
            text=True, capture_output=True, timeout=60,
            env={**os.environ, "HOME": str(tmp_path)})
        assert r.returncode == 4
        assert "queued for --sweep-undeliverable" in r.stderr


# --------------------------------------------------------------------------
# 3. numeric discrimination
# --------------------------------------------------------------------------

class TestNumericDiscrimination:
    @pytest.mark.parametrize("good", ["8505558285", "-1001234567890",
                                      "-850555", "0"])
    def test_numeric_ids_are_targets(self, monkeypatch, good):
        T = _load_notify_module()
        assert T.is_numeric_chat_id(good) is True
        assert report_is_numeric(good) is True

    @pytest.mark.parametrize("bad", ["watchdog", "supervisor", "capacity",
                                     "", "12abc", "  ", "chat:watchdog"])
    def test_labels_and_garbage_are_never_targets(self, monkeypatch, bad):
        T = _load_notify_module()
        assert T.is_numeric_chat_id(bad) is False
        assert report_is_numeric(bad) is False


# --------------------------------------------------------------------------
# 4. the retired shim keeps working by delegation only
# --------------------------------------------------------------------------

class TestRetiredShim:
    REPO = SCRIPTS.parents[3]  # .../23-ai-workforce-blueprint

    def test_shim_is_marked_retired(self):
        shim = self.REPO / "tools" / "presentation-notify.sh"
        assert shim.is_file()
        head = shim.read_text(encoding="utf-8")[:400]
        assert "RETIRED" in head

    def test_shim_delegates_stdin_payload_to_canonical_transport(
            self, tmp_path, monkeypatch):
        shim = self.REPO / "tools" / "presentation-notify.sh"
        payload = tmp_path / "shim-payload.json"
        monkeypatch.setenv("OWNER_CHAT_ID", "8505558285")
        monkeypatch.setenv("PRESENTATION_NOTIFY_DRY_RUN", "1")
        # the shim resolves the canonical transport relative to ITS OWN dir;
        # from the repo layout that is the department scripts dir.
        import subprocess
        r = subprocess.run(["bash", str(shim)],
                           input=json.dumps({"chat_id": "watchdog",
                                             "kind": "stall",
                                             "message": "shim test"}),
                           text=True, capture_output=True, timeout=60,
                           env={**os.environ})
        # Delivery outcome depends on this box's live gateway and is NOT the
        # shim's contract -- the shim's contract is DELEGATION: it exits with
        # the canonical transport's own code (0 sent; 2 unconfigured; 4
        # undeliverable; 5 gateway rejected/timed out). Any of those proves
        # the payload reached the canonical transport and the shim made no
        # delivery decision of its own. The one hard rule: stderr never names
        # api.telegram.org -- the shim never touches a token or the raw API.
        assert r.returncode in (0, 2, 4, 5)
        assert "api.telegram.org" not in (r.stderr or "")
