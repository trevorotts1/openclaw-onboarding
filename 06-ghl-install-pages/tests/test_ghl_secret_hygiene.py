"""Secret-hygiene tests for the GHL Tier-2 auth fallback (DONE 7).

PROVES: a full mock Tier-2 run leaks NO password, NO 2FA code, NO refresh/access
token to stdout/stderr/logs or any artifact; and a repo grep of all new source
finds no secret literal and no client name/id/email.

MOCKS ONLY — no real GHL, no real Gmail, no browser, no network.

S06-08 extension (prep step 10): TestEvidenceNoSecretSweep extends the
no-secret discipline from the auth path to the whole EVIDENCE pipeline
(verify artifacts, receipts, ladder receipts, run-state, inventory export,
build ledger, ID handoff, read-back index). The Firebase Web API key stays
allowlisted by registry reference only (gates.json), never by value.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_TOOLS_DIR = _TESTS_DIR.parent / "tools"
_REPO_ROOT = _TESTS_DIR.parent.parent
for p in (str(_TOOLS_DIR), str(_TESTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ghl_auth  # noqa: E402
import ghl_auth_fallback as fb  # noqa: E402
from mocks.mock_ghl import build_driver  # noqa: E402
from mocks.mock_gmail import MockGmailClient, build_probe  # noqa: E402
from mocks.mock_secret_store import fully_provisioned_store  # noqa: E402

_NEW_SOURCE = [
    _TOOLS_DIR / "ghl_auth.py",
    _TOOLS_DIR / "ghl_auth_fallback.py",
    _TOOLS_DIR / "ghl_gmail_probe.py",
    _TOOLS_DIR / "ghl_login_browser.py",
]

# The fabricated secret-shaped values the mocks use (these are NOT real secrets).
_FAKE_PASSWORD = "FAKE-pw-not-a-real-secret"
_FAKE_CODE = "246802"
_FAKE_REFRESH = "FAKErefreshTOKENfakeREFRESHtoken0123456789"


class TestNoSecretLeak:
    def test_full_run_leaks_no_secret(self, monkeypatch, capsys, tmp_path):
        """DONE 7: a full Tier-2 run (mock GHL + mock Gmail) prints/logs NO
        password, NO code, NO token to stdout/stderr."""
        monkeypatch.setattr(fb, "backoff", lambda attempt: None)
        store = fully_provisioned_store(**{fb.AGENCY_PASSWORD_KEYS[0]: _FAKE_PASSWORD})
        gmail = MockGmailClient(profile_address="agent@example.test",
                                messages=[], live_code=_FAKE_CODE)
        probe = build_probe(gmail, "agent@example.test")
        driver = build_driver(liveness=True, locations=[],
                              refresh_token_to_emit=_FAKE_REFRESH)

        out = str(tmp_path / "seed.json")
        res = ghl_auth.run("s", out, env={}, seed_runner=lambda *a: 2,
                           store=store, probe=probe, driver=driver)
        assert res.ok and res.tier == ghl_auth.TIER2

        captured = capsys.readouterr()
        blob = captured.out + captured.err + res.reason + res.client_message
        for secret in (_FAKE_PASSWORD, _FAKE_CODE, _FAKE_REFRESH):
            assert secret not in blob, f"secret leaked into output: {secret!r}"

        # The side file the orchestrator wrote must also be secret-free.
        side = tmp_path / "ghl-auth-tier.json"
        if side.exists():
            sidetext = side.read_text()
            for secret in (_FAKE_PASSWORD, _FAKE_CODE, _FAKE_REFRESH):
                assert secret not in sidetext

    def test_result_objects_never_carry_a_secret(self, monkeypatch, tmp_path):
        """The Tier-2 result fields (reason/client_message) never carry the token,
        password, or code."""
        monkeypatch.setattr(fb, "backoff", lambda attempt: None)
        store = fully_provisioned_store(**{fb.AGENCY_PASSWORD_KEYS[0]: _FAKE_PASSWORD})
        gmail = MockGmailClient(profile_address="agent@example.test",
                                messages=[], live_code=_FAKE_CODE)
        probe = build_probe(gmail, "agent@example.test")
        driver = build_driver(liveness=True, locations=[],
                              refresh_token_to_emit=_FAKE_REFRESH)
        res = fb.run_tier2("s", "/tmp/x", store, probe, driver)
        for field_val in (res.reason, res.client_message):
            for secret in (_FAKE_PASSWORD, _FAKE_CODE, _FAKE_REFRESH):
                assert secret not in field_val


class TestRepoSourceHygiene:
    def test_no_long_token_literal_in_source(self):
        """DONE 7: no secret literal (long JWT/base64 run) in the new modules."""
        long_re = re.compile(r"['\"][A-Za-z0-9_\-]{120,}['\"]")
        for f in _NEW_SOURCE:
            txt = f.read_text(encoding="utf-8")
            assert not long_re.search(txt), f"long token-looking literal in {f.name}"

    def test_no_real_firebase_api_key_in_new_modules(self):
        """The new modules carry NO live token; they may NOT embed the real
        securetoken Firebase API key either (that lives only in seed-ghl-auth.py)."""
        for f in _NEW_SOURCE:
            txt = f.read_text(encoding="utf-8")
            assert "AIzaSy-FAKE-EXAMPLE-KEY-DO-NOT-USE-000000" not in txt

    def test_no_operator_path_in_source(self):
        """No operator machine path literal in the new modules' CODE.

        os.path.expanduser('~') is used instead of a hardcoded home, so an
        operator path must never appear.
        """
        for f in _NEW_SOURCE:
            txt = f.read_text(encoding="utf-8")
            assert "/Users/blackceomacmini" not in txt

    def test_no_client_identifiers_in_new_files(self):
        """DONE 7: run the repo's no-client-names guard scoped to the new files +
        tests (fabricated ids must not trip it)."""
        import subprocess
        guard = _REPO_ROOT / "scripts" / "qc-assert-no-client-names.sh"
        res = subprocess.run(["bash", str(guard), "--repo-root", str(_REPO_ROOT)],
                             capture_output=True, text=True, timeout=120)
        # The guard scans the whole repo; the new files must not introduce a hit.
        assert res.returncode == 0, (
            f"no-client-names guard FAILED (a new file may carry a client id):\n{res.stdout}")


class TestFirebaseApiKeySync:
    """P3-2 (final-review Point 1 fix 2): the GoHighLevel/Convert-and-Flow
    Firebase Web API key is intentionally hardcoded (NOT a secret — a public,
    server-side-restricted Google key) in THREE places with zero runtime
    cross-file dependency: 06-ghl-install-pages/tools/seed-ghl-auth.py, Skill 44
    transport.py, and Skill 44 ghl_internal_client.py.
    gates.json::firebase_api_key_registry.canonical_value is the documented
    06-side single source of record. These tests prove the three physical
    literals — and the registry itself — never silently drift apart. A Google
    key rotation applied to only one copy would otherwise surface later as a
    confusing securetoken-exchange auth failure instead of failing CI loudly
    here."""

    _KEY_RE = re.compile(r'FIREBASE_API_KEY\s*=\s*["\']([^"\']+)["\']')

    @staticmethod
    def _extract_key(path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        m = TestFirebaseApiKeySync._KEY_RE.search(text)
        assert m, f"FIREBASE_API_KEY literal not found in {path}"
        return m.group(1)

    def test_seed_ghl_auth_matches_gates_json_registry(self):
        seed_key = self._extract_key(_TOOLS_DIR / "seed-ghl-auth.py")
        gates = json.loads((_TOOLS_DIR / "gates.json").read_text(encoding="utf-8"))
        registry_key = gates["firebase_api_key_registry"]["canonical_value"]
        assert seed_key == registry_key, (
            f"seed-ghl-auth.py FIREBASE_API_KEY ({seed_key!r}) != "
            f"gates.json firebase_api_key_registry.canonical_value "
            f"({registry_key!r}) — update BOTH together on a key rotation."
        )

    def test_seed_ghl_auth_matches_skill44_transport(self):
        transport_py = (
            _REPO_ROOT / "44-convert-and-flow-operator" / "tools" / "engine"
            / "cli_anything" / "gohighlevel" / "internal" / "transport.py"
        )
        if not transport_py.exists():
            pytest.skip("Skill 44 not present in this checkout (partial-bundle box)")
        seed_key = self._extract_key(_TOOLS_DIR / "seed-ghl-auth.py")
        transport_key = self._extract_key(transport_py)
        assert seed_key == transport_key, (
            f"FIREBASE_API_KEY drifted between seed-ghl-auth.py ({seed_key!r}) "
            f"and Skill 44 transport.py ({transport_key!r}) — a Google key "
            "rotation was applied to only one copy. Update BOTH plus "
            "gates.json::firebase_api_key_registry.canonical_value."
        )

    def test_seed_ghl_auth_matches_skill44_internal_client(self):
        client_py = (
            _REPO_ROOT / "44-convert-and-flow-operator" / "tools" / "engine"
            / "cli_anything" / "gohighlevel" / "utils" / "ghl_internal_client.py"
        )
        if not client_py.exists():
            pytest.skip("Skill 44 not present in this checkout (partial-bundle box)")
        seed_key = self._extract_key(_TOOLS_DIR / "seed-ghl-auth.py")
        client_key = self._extract_key(client_py)
        assert seed_key == client_key, (
            f"FIREBASE_API_KEY drifted between seed-ghl-auth.py ({seed_key!r}) "
            f"and Skill 44 ghl_internal_client.py ({client_key!r}) — a Google "
            "key rotation was applied to only one copy. Update BOTH plus "
            "gates.json::firebase_api_key_registry.canonical_value."
        )


class TestEvidenceNoSecretSweep:
    """S06-08 (prep step 10): the no-secret sweep over the EVIDENCE pipeline.

    A full mock evidence run is seeded with fabricated secret VALUES and
    secret-SHAPED strings at every evidence sink the prep names (verify
    DOM/console captures, receipts, ladder receipts, run-state argv/carry,
    the inventory export, the build ledger, the ID handoff, and the
    read-back index written over all of them). After the run, EVERY
    produced artifact's bytes plus captured stdout/stderr are swept: zero
    fixture values and zero unredacted secret shapes may remain, and the
    redaction counts must be recorded at the sinks that scrubbed.

    The one allowlist is the Firebase Web API key, referenced ONLY through
    the gates.json registry (its value is never copied into this test):
    any AIza-shaped string found in an artifact must equal the registry
    value (classified PUBLIC by the tree) or the sweep fails.
    """

    _PIT = "pit-fixture-1a2b3c4d5e6f708192a3b4c5d6"
    _PASSWORD = "Fixture!Password#8871"
    _REFRESH = "fixture-refresh-token-0123456789abcdef"
    _JWT = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJzdWIiOiJmaXh0dXJlLXN3ZWVwIn0"
            ".fixture-signature-0123456789")
    _VALUES = (_PIT, _PASSWORD, _REFRESH, _JWT)
    _LOC = "Ab1Cd2Ef3Gh4Ij5Kl6Mn"  # fabricated location id

    def test_full_evidence_run_sweeps_clean(self, tmp_path, monkeypatch, capsys):
        import ghl_builder as gb
        import ghl_evidence as ev
        import ghl_fallback_ladder as ladder
        import ghl_id_handoff as handoff
        import ghl_inventory as inv
        import ghl_receipts as receipts
        import ghl_run_state as run_state
        import ghl_verify as verify

        LOC = self._LOC
        values = list(self._VALUES)
        base = tmp_path / "evidence-run"
        run_dir = base / "run"
        render_dir = run_dir / "render"
        render_dir.mkdir(parents=True)

        # 1) Verify artifacts: the fetcher writes DOM + console captures
        # seeded with secrets, as a real render capture could be.
        def fetcher(url, marker):
            dom_path = render_dir / "s1.dom.html"
            dom_path.write_text(
                f"<html><body>token {self._PIT} auth Bearer {self._JWT}"
                f"<p>{marker}</p></body></html>")
            console_path = render_dir / "s1.console.json"
            console_path.write_text(json.dumps(
                {"messages": [f"login used password {self._PASSWORD}"]}))
            return {"ok": True, "http": 200, "marker_in_rendered_dom": True,
                    "render_errors": [], "location_id": LOC,
                    "dom_path": str(dom_path), "png_path": "",
                    "console_path": str(console_path),
                    "dom_sha256": "", "png_sha256": "", "console_sha256": "",
                    "dom_bytes": 0, "visible_text_len": 500}

        out = verify.verify_all(
            str(run_dir),
            [{"step": "s1", "page_id": "p1",
              "preview_url": "https://x/preview", "marker": "M",
              "copy_fidelity": False}],
            live=False, fetcher=fetcher, run_id="sweep-run",
            expected_location_id=LOC, secret_values=values)
        assert out["summary"]["overall_pass"] is True
        assert out["summary"]["tenant_binding"] == "bound"

        # 2) A receipt whose caller verify/disclosures carry secrets.
        receipt_file = receipts.write_receipt(
            str(run_dir),
            receipts.make_receipt(
                "funnel", "zhc_sweep", "created", rail="rest",
                response_id="fn-1",
                verify={"ok": True, "location_id": LOC,
                        "detail": f"read back with refresh_token={self._REFRESH}"},
                disclosures=[f"token used: {self._PIT}"],
                expected_location_id=LOC, observed_location_id=LOC,
                run_id="sweep-run"),
            secret_values=values)

        # 3) A ladder receipt whose rung detail carries a secret.
        ladder_result = ladder.run_ladder(
            "survey",
            {"browser": lambda: {"ok": True, "location_id": LOC,
                                 "detail": f"browser ok; password={self._PASSWORD}"}},
            expected_location_id=LOC, secret_values=values)
        ladder_path = str(base / "ladder-receipt.json")
        ladder.write_ladder_receipt(ladder_result, ladder_path,
                                    secret_values=values)

        # 4) Run-state with secrets in argv and carry.
        state_root = base / "state"
        st = run_state.RunState.start(
            "fixture-builder", [run_state.PhaseSpec("build")],
            run_id="sweep-run", state_root=str(state_root),
            argv=["--pit", self._PIT], secret_values=values,
            trace_suppression=ev.default_trace_suppression(),
            expected_location_id=LOC)
        st.carry_set("handoff_note", f"refresh token: {self._REFRESH}")
        st.save()

        # 5) The inventory export, with a secret inside a page name.
        report = inv.enumerate_zhc_inventory(
            LOC,
            funnel_lister=lambda loc: [{"id": "f1", "name": "ZHC Sweep",
                                        "locationId": LOC}],
            page_lister=lambda f, loc: [
                {"id": "p1", "name": f"ZHC {self._PASSWORD} Page",
                 "status": "draft", "locationId": LOC}])
        inv_path = inv.write_inventory(str(base), report, secret_values=values)

        # 6) The build ledger's free-form extra sink.
        monkeypatch.setenv("GHL_LEDGER_ROOT", str(base / "ledger"))
        gb.ledger_write("sweep-run", "ZHC Sweep", "Step 1", "created",
                        extra={"note": f"pit token: {self._PIT}"},
                        secret_values=values)

        # 7) The ID handoff, then the read-back index over the run's own
        # roots binding every artifact above (NQ2: this run's roots only).
        handoff_file = handoff.write_handoff(
            str(run_dir), handoff.new_handoff(run_id="sweep-run"),
            secret_values=values)
        index = ev.build_readback_index(
            str(run_dir), run_id="sweep-run", expected_location_id=LOC,
            trace_suppression=ev.default_trace_suppression(),
            artifacts=[
                {"path": out["raw_path"], "kind": "verify_raw",
                 "observed_location_id": LOC},
                {"path": out["summary_path"], "kind": "verify_summary"},
                {"path": receipt_file, "kind": "receipt",
                 "observed_location_id": LOC},
                {"path": ladder_path, "kind": "ladder_receipt",
                 "observed_location_id": LOC},
                {"path": st.path, "kind": "run_state"},
                {"path": inv_path, "kind": "inventory"},
                {"path": handoff_file, "kind": "id_handoff"},
            ])
        index_path = ev.write_readback_index(str(run_dir), index)
        ev.verify_readback_index(json.loads(Path(index_path).read_text()))

        # Redaction counts are recorded at the sinks that scrubbed.
        raw = json.loads(Path(out["raw_path"]).read_text())
        assert raw[0]["redactions"] >= 1
        assert out["summary"]["redactions"] >= 1
        assert json.loads(Path(receipt_file).read_text())["redactions"] >= 1
        assert st.doc["redactions"] >= 1

        # THE SWEEP: every produced artifact's bytes + captured output.
        captured = capsys.readouterr()
        texts = {"<stdout>": captured.out, "<stderr>": captured.err}
        for root, _dirs, files in os.walk(base):
            for name in files:
                p = Path(root) / name
                texts[str(p)] = p.read_bytes().decode("utf-8", "replace")
        assert len(texts) > 8  # the run really produced its artifacts

        gates = json.loads(
            (_TOOLS_DIR / "gates.json").read_text(encoding="utf-8"))
        registry_value = gates["firebase_api_key_registry"]["canonical_value"]
        aiza_shape = re.compile(r"AIza[0-9A-Za-z\-_]{35}")
        firebase_hits = 0
        for where, text in texts.items():
            for m in aiza_shape.finditer(text):
                assert m.group(0) == registry_value, (
                    f"non-registry AIza-shaped value in {where}")
                firebase_hits += 1
            for value in self._VALUES:
                assert value not in text, f"fixture secret value in {where}"
            assert not re.search(
                r"Bearer\s+(?!\[REDACTED\])[A-Za-z0-9._\-]{8,}", text), where
            assert not re.search(
                r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.", text), where
            assert not re.search(r"pit-[A-Za-z0-9\-_]{8,}", text), where
        # This fixture flow embeds no Firebase key at all; the counter is
        # the allowlist mechanism itself (registry reference, never a
        # copied value) and stays ready for a producer that legitimately
        # embeds the PUBLIC key in a DOM capture.
        assert firebase_hits == 0
