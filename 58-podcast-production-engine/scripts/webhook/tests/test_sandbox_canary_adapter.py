#!/usr/bin/env python3
"""Hermetic contract test for the sandbox canary admission gate."""

import hashlib
import hmac
import importlib.util
import json
import os
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sandbox_canary_adapter", HERE / "sandbox_canary_adapter.py")
adapter = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(adapter)


with tempfile.TemporaryDirectory(prefix="sandbox-canary-") as tmp:
    tmp = Path(tmp)
    old = dict(os.environ)
    try:
        os.environ.update({
            "PODCAST_SANDBOX_LOCATION_ID": "LOC-sandbox-canary",
            "PODCAST_SANDBOX_TEST_CONTACT_ID": "CNT-sandbox-canary",
            "PODCAST_SANDBOX_CANARY_SECRET": "hermetic-secret-only",
            "PODCAST_SANDBOX_LEDGER_DIR": str(tmp / "ledger"),
            "PODCAST_SANDBOX_DB_PATH": str(tmp / "state.db"),
        })
        body = {
            "customData": {
                "podcast_mode": "Personal Podcast Style",
                "select_your_presentation_style_personal_podcast": "Counter Intuitive",
                "podcast_survey__barry_q1": "A safe canary changes no client state.",
                "podcast_survey__barry_q6": "Careful and evidence-led.",
                "podbean_podcast_id": "sandbox-no-publish",
                "_test": True,
            },
            "contact": {"id": "CNT-sandbox-canary", "first_name": "Sandbox"},
            "location": {"id": "LOC-sandbox-canary"},
        }
        raw = json.dumps(body, separators=(",", ":")).encode()
        sig = "sha256=" + hmac.new(b"hermetic-secret-only", raw, hashlib.sha256).hexdigest()
        status, result = adapter.accept(raw, sig)
        assert status == 200 and result["status"] == "test"
        assert result["advance"] == "researching" and result["completion_refused"] is True
        duplicate_status, duplicate = adapter.accept(raw, sig)
        assert duplicate_status == 200 and duplicate["status"] == "duplicate" and duplicate["duplicate"] is True
        denied, _ = adapter.accept(raw, "sha256=" + "0" * 64)
        assert denied == 401
        print("sandbox canary adapter: ALL ASSERTIONS PASSED")
    finally:
        os.environ.clear(); os.environ.update(old)
