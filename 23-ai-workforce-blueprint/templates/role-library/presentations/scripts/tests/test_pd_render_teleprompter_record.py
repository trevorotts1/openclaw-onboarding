"""PD-210 — the teleprompter publish record tells the truth.

Pinned here (PASS5-GATES.md, PD-210 acceptance):

  A1  a stubbed opener returning 302 → the record carries `verify_redirected: true`;
      with TELEPROMPTER_VERIFY_STRICT forced True → status `verify_failed`.
  A2  a record whose `local_sha256` is missing or differs from the HTML on disk →
      the bundle gate fails naming the mismatch.
  A3  the no-credentials path → `public_url` is null (and the intended address is
      still recorded as `intended_url`).

No network call is made: the redirect is a stubbed opener and the R2 upload is
stubbed. Credentials are process env values in the test, never real secrets, and
the no-credentials case stubs `_load_secret` so no secrets file is read.
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.error
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import build_deck  # noqa: E402

HTML = b"<!DOCTYPE html><html><body>teleprompter</body></html>"


def _bundle(tmp_path: Path):
    """A bundle with the teleprompter HTML and a deliverables ledger."""
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "presenter-teleprompter.html").write_bytes(HTML)
    ledger = tmp_path / "deliverables.json"
    ledger.write_text(json.dumps([{"key": "teleprompter_html", "status": "built"}]))
    run_dir = tmp_path / "run"
    return bundle, run_dir, ledger


def _stub_redirect_opener(monkeypatch, location="https://login.example.com/access"):
    """Stub urllib's opener so `_http_status` runs its real no-follow path and
    returns a 302 with a Location, exactly as an Access login redirect would."""
    class _Opener:
        def open(self, req, timeout=None):
            url = getattr(req, "full_url", str(req))
            raise urllib.error.HTTPError(url, 302, "Found", {"Location": location}, None)

    monkeypatch.setattr(build_deck.urllib.request, "build_opener", lambda *h: _Opener())


def _present_creds(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ZHW_APPS_API_TOKEN", "test-token")
    monkeypatch.setenv("CLOUDFLARE_ZHW_ACCOUNT_ID", "test-account")
    monkeypatch.setattr(build_deck, "_r2_put_object", lambda *a, **k: None)


def test_redirect_recorded_and_published_when_not_strict(monkeypatch, tmp_path):
    bundle, run_dir, ledger = _bundle(tmp_path)
    _present_creds(monkeypatch)
    _stub_redirect_opener(monkeypatch)
    monkeypatch.setattr(build_deck, "TELEPROMPTER_VERIFY_STRICT", False)

    rec = build_deck.publish_teleprompter(bundle, "deck", run_dir, "mac", ledger)

    assert rec["verify_redirected"] is True
    assert rec["redirect_host"] == "login.example.com"
    assert rec["verified_http_status"] == 302
    assert rec["status"] == "published"


def test_redirect_is_a_verify_failure_when_strict(monkeypatch, tmp_path):
    bundle, run_dir, ledger = _bundle(tmp_path)
    _present_creds(monkeypatch)
    _stub_redirect_opener(monkeypatch)
    monkeypatch.setattr(build_deck, "TELEPROMPTER_VERIFY_STRICT", True)

    with pytest.raises(RuntimeError):
        build_deck.publish_teleprompter(bundle, "deck", run_dir, "mac", ledger)

    rec = json.loads((bundle / "teleprompter_publish.json").read_text())
    assert rec["verify_redirected"] is True
    assert rec["status"] == "verify_failed"


def test_gate_rejects_a_record_for_a_different_file(monkeypatch, tmp_path):
    bundle, _run, _ledger = _bundle(tmp_path)
    monkeypatch.setattr(build_deck, "_teleprompter_credentials_present", lambda: True)
    good = {
        "status": "published",
        "public_url": "https://teleprompter.zerohumanworkforce.com/c/d/teleprompter.html",
        "local_sha256": hashlib.sha256(HTML).hexdigest(),
        "verified_http_status": 200,
    }

    # Control: the matching record passes.
    (bundle / "teleprompter_publish.json").write_text(json.dumps(good))
    assert build_deck._check_teleprompter_published(bundle) == ("", False)

    # The file is swapped after the record was written: the gate must catch it.
    good["local_sha256"] = "0" * 64
    (bundle / "teleprompter_publish.json").write_text(json.dumps(good))
    reason, warn_only = build_deck._check_teleprompter_published(bundle)
    assert reason == "publish record does not match the teleprompter file"
    assert warn_only is False


def test_no_credentials_record_carries_no_public_url(monkeypatch, tmp_path):
    bundle, run_dir, ledger = _bundle(tmp_path)
    # Stub the secret reader so this test never touches a real secrets store.
    monkeypatch.setattr(build_deck, "_load_secret", lambda name: "")

    rec = build_deck.publish_teleprompter(bundle, "deck", run_dir, "mac", ledger)

    assert rec["status"] == "warned_no_credentials"
    assert rec["public_url"] is None
    assert rec["intended_url"].endswith("/teleprompter.html")
    assert rec["local_sha256"] == hashlib.sha256(HTML).hexdigest()
