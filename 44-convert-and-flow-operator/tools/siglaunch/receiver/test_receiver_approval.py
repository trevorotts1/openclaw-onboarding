"""U-skill44-07: receiver approval is verified, refusal paths return receipts,
and the pipeline is declared non-production for Black Friday 2026.

S44-17  approval.ref must resolve through approval_record (Command Center);
        a requester-computed plan hash alone is refused.
S44-18  required_evidence refusals return (EXIT_VALIDATION, receipt), not TypeError.
S44-19  receiver/normalizer/processor declare native GHL post-sale workflows
        as the purchase path and refuse to run as a production entry.
"""
import copy
import json
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "store"))
sys.path.insert(0, str(HERE.parent / "normalizer"))
sys.path.insert(0, str(HERE.parent / "processor"))
import receiver as rcv  # noqa: E402
from receiver import EXIT_BLOCKED, EXIT_GATE, EXIT_OK, EXIT_VALIDATION, Receiver, plan_hash  # noqa: E402
from store import Store  # noqa: E402


class FakeExecutor:
    def __init__(self):
        self.build_calls = []

    def probe(self):
        return {"token_state": "healthy", "access_tier_used": "tier0"}

    def dependencies_present(self, location_id, workflow):
        return []

    def snapshot(self, location_id, slug):
        return True

    def build(self, builder_plan):
        self.build_calls.append(copy.deepcopy(builder_plan))
        slug = next(k for k in builder_plan if k != "folder")
        return {"exit_code": 0, "workflow_id": "wf-" + slug, "errors": [], "notes": [],
                "export": {"id": "wf-" + slug, "status": "draft",
                           "triggers": [{"id": "t1", "type": "contact_tag"}],
                           "steps": [{"id": "s1"}, {"id": "s2"}], "allowMultiple": True},
                "qc_exit_code": 0, "rubric": 9.1}


def make_request(ref="appr_12345678", **overrides):
    plan = {"_meta": {"deploy_mode": "draft-only"}, "folder": "Signature Launch",
            "welcome": {"name": "Welcome", "tag": "email-engine:welcome"}}
    req = {"request_id": "gxo_0123456789ab", "request_version": 1,
           "location_id": "LOC1", "launch_id": "LN1", "requesting_room": "S50",
           "deploy_mode": "draft-only",
           "approval": {"ref": ref, "plan_hash": plan_hash(plan)},  # requester-computed
           "plan": plan,
           "workflows": [{"slug": "welcome", "expected_steps": 2, "allow_multiple": True,
                          "trigger": {"type": "contact_tag", "tag": "email-engine:welcome"}}]}
    req.update(overrides)
    return req


def never_called(*a, **k):
    raise AssertionError("verifier must not run before the refusal under test")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    for name in ("MISSION_CONTROL_URL", "MC_API_TOKEN", "COMPANY_SLUG"):
        monkeypatch.delenv(name, raising=False)
    fake = FakeExecutor()
    store = Store(str(tmp_path / "s44.db"))

    def make(verifier=None):
        return Receiver(store, fake, configured_location="LOC1", approval_verifier=verifier), fake, store
    return make


# ── S44-18: both required_evidence refusals return a receipt ─────────────
@pytest.mark.parametrize("required, code", [
    ("not-a-list", "REQUIRED_EVIDENCE_INVALID"),
    ([""], "REQUIRED_EVIDENCE_INVALID"),
    (["ghl_pack_version"], "EVIDENCE_UNPRODUCIBLE"),
])
def test_required_evidence_refusals_return_receipt(env, required, code):
    rx, fake, _ = env(never_called)
    exit_code, receipt = rx.dispatch(make_request(required_evidence=required))
    assert exit_code == EXIT_VALIDATION
    assert receipt["refused"] == code and receipt["outcome"] == "refused"
    assert receipt["request_id"] == "gxo_0123456789ab"
    assert fake.build_calls == []


# ── S44-17: approval verified through approval_record ────────────────────
def test_self_computed_hash_is_refused_with_default_verifier(env):
    """No injected verifier, no Command Center configured: the requester's own
    hash must never open the gate (fail closed, nothing built or stored)."""
    rx, fake, store = env()
    exit_code, receipt = rx.dispatch(make_request(ref=plan_hash({"x": 1})))
    assert exit_code in (EXIT_GATE, EXIT_BLOCKED)
    assert receipt["outcome"] == "refused" and receipt["status"] == "blocked"
    assert fake.build_calls == []
    assert store.get_request("gxo_0123456789ab") is None


def test_unresolved_ref_is_refused_before_any_engine_call(env):
    class Refused(Exception):
        code = "APPROVAL-NOT-FROM-AUTHORITY"

    def verifier(*a, **k):
        raise Refused("Command Center has no such approval record")

    rx, fake, store = env(verifier)
    exit_code, receipt = rx.dispatch(make_request(ref="owner-batch-1"))
    assert exit_code == EXIT_GATE
    assert receipt["refused"] == "APPROVAL-NOT-FROM-AUTHORITY"
    assert fake.build_calls == [] and store.get_request("gxo_0123456789ab") is None


def test_store_unreachable_is_a_named_blocker_not_approval(env):
    def verifier(*a, **k):
        raise OSError("down")

    rx, fake, _ = env(verifier)
    exit_code, receipt = rx.dispatch(make_request())
    assert exit_code == EXIT_BLOCKED and receipt["refused"] == "APPROVAL_UNAVAILABLE"
    assert fake.build_calls == []


def test_non_ok_verifier_result_is_refused(env):
    rx, fake, _ = env(lambda *a, **k: {"ok": False})
    exit_code, receipt = rx.dispatch(make_request())
    assert exit_code == EXIT_GATE and receipt["refused"] == "APPROVAL_NOT_VERIFIED"
    assert fake.build_calls == []


def test_non_object_approval_is_refused_not_crashed(env):
    rx, _, _ = env(never_called)
    exit_code, receipt = rx.dispatch(make_request(approval="approved"))
    assert exit_code == EXIT_VALIDATION and receipt["refused"] == "APPROVAL_INVALID"


def test_verified_approval_dispatches_and_receipt_names_the_authority(env):
    seen = {}

    def verifier(ref, kind, phash, scope, **k):
        seen.update(ref=ref, kind=kind, phash=phash, scope=scope)
        return {"ok": True, "authority": "command-center"}

    rx, fake, _ = env(verifier)
    req = make_request()
    exit_code, receipt = rx.dispatch(req)
    assert exit_code == EXIT_OK and len(fake.build_calls) == 1
    assert seen == {"ref": "appr_12345678", "kind": rcv.APPROVAL_KIND,
                    "phash": plan_hash(req["plan"]), "scope": list(rcv.APPROVAL_SCOPE)}
    assert receipt["approval"]["verified_by"] == "command-center"


# ── S44-17 against the real shared verifier ──
# Absent (before U-approval-02 merges): the default verifier fails closed.
# Present: it accepts only a matching Command Center record.
def test_real_approval_record_accepts_only_a_command_center_record(env, monkeypatch):
    req = make_request()
    if not rcv._APPROVAL_RECORD_PATH.is_file():
        monkeypatch.setenv("COMPANY_SLUG", "client-a")
        monkeypatch.setenv("MISSION_CONTROL_URL", "http://127.0.0.1:9")
        rx, fake, store = env()
        code, receipt = rx.dispatch(req)
        assert (code, receipt["refused"]) == (EXIT_BLOCKED, "APPROVAL_UNAVAILABLE")
        assert fake.build_calls == [] and store.get_request(req["request_id"]) is None
        return
    state = {"status": 200, "record": {
        "schema_version": "1.0", "approval_id": "appr_12345678", "kind": rcv.APPROVAL_KIND,
        "plan_hash": plan_hash(req["plan"]), "client_identity": "client-a",
        "source_message_ref": "ghl:msg-1", "scope": list(rcv.APPROVAL_SCOPE),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "revoked": False, "verification_class": "authenticated_platform_record"}}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(state["record"]).encode()
            self.send_response(state["status"])
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("MISSION_CONTROL_URL", "http://127.0.0.1:%d" % srv.server_port)
    monkeypatch.setenv("MC_API_TOKEN", "tok-test")
    monkeypatch.setenv("COMPANY_SLUG", "client-a")
    try:
        rx, fake, _ = env()
        assert rx.dispatch(req)[0] == EXIT_OK and len(fake.build_calls) == 1
        # record bound to a different plan hash -> refused
        state["record"] = dict(state["record"], plan_hash="0" * 64)
        rx2, fake2, _ = env()
        code, receipt = rx2.dispatch(make_request(request_id="gxo_0123456789ac"))
        assert code == EXIT_GATE and receipt["refused"] == "APPROVAL-HASH"
        assert len(fake2.build_calls) == 1  # the refused dispatch built nothing more
        # Command Center has no such record -> refused
        state["status"] = 404
        code, receipt = rx2.dispatch(make_request(request_id="gxo_0123456789ad"))
        assert code == EXIT_GATE and receipt["refused"] == "APPROVAL-NOT-FROM-AUTHORITY"
    finally:
        srv.shutdown()
        srv.server_close()


# ── S44-19: native GHL declared, no production entry ─────────────────────
MODULES = [HERE / "receiver.py",
           HERE.parent / "normalizer" / "normalizer.py",
           HERE.parent / "processor" / "processor.py"]


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.stem)
def test_module_declares_native_ghl_and_refuses_production_entry(path):
    import importlib
    mod = importlib.import_module(path.stem)
    assert mod.BLACK_FRIDAY_2026_PURCHASE_PATH == "native-ghl-post-sale-workflows"
    assert mod.PRODUCTION_ENTRY_ENABLED is False
    assert mod.main([]) == mod.EXIT_NOT_PRODUCTION != 0
    proc = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 6
    assert "native-ghl-post-sale-workflows" in proc.stderr and proc.stdout == ""


# ── S44-19: python -m siglaunch run, one purchase end to end (fake executor) ──
TOOLS = HERE.parents[1]  # tools/, so `-m siglaunch` resolves


def _run(tmp_path, *extra):
    ev, cat, db = tmp_path / "ev.json", tmp_path / "cat.json", tmp_path / "s.sqlite"
    ev.write_text(json.dumps({
        "tenant_id": "T1", "location_id": "LOC1", "launch_id": "LN1", "provider": "ghl",
        "provider_event_id": "evt-1", "native_event_kind": "order_paid",
        "native_order_ref": "ord-1", "native_transaction_ref": "txn-1",
        "occurred_at": "2026-10-15T20:00:00Z", "received_at": "2026-10-15T20:00:05Z",
        "payment_status": "succeeded", "evidence_ref": "readback/ord-1", "test_only": True,
        "contact_ref": "contact-1",
        "line_items": [{"native_line_ref": "li-m", "native_product_ref": "prod-main",
                        "offer_id": "off-main", "currency": "USD", "amount_minor": 49700,
                        "entitlement_ids": ["ent-main"]}]}))
    cat.write_text(json.dumps({"tenant_id": "T1", "location_id": "LOC1", "launch_id": "LN1",
                               "bindings": {"prod-main": "main"}, "purchase_tag": "verified-purchase"}))
    proc = subprocess.run([sys.executable, "-m", "siglaunch", "run", "--event", str(ev),
                           "--catalog", str(cat), "--db", str(db), *extra],
                          cwd=TOOLS, capture_output=True, text=True, timeout=120)
    return proc, db


def test_run_fake_processes_one_purchase_then_is_idempotent(tmp_path):
    proc, db = _run(tmp_path, "--executor", "fake")
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["ingest"] == "accepted" and out["active_entitlements"] == ["ent-main"]
    assert [e for e in out["fake_effects"] if e["effect"] == "tag"] == [
        {"effect": "tag", "contact_ref": "contact-1", "tag": "verified-purchase"}]
    proc2, _ = _run(tmp_path, "--executor", "fake")
    out2 = json.loads(proc2.stdout)
    assert proc2.returncode == 0 and out2["ingest"] == "duplicate" and out2["fake_effects"] == []


@pytest.mark.parametrize("extra", [("--executor", "live"), ()])
def test_run_refuses_anything_but_fake_executor(tmp_path, extra):
    proc, db = _run(tmp_path, *extra)
    assert proc.returncode == 6 and "native-ghl-post-sale-workflows" in proc.stderr
    assert not db.exists()
