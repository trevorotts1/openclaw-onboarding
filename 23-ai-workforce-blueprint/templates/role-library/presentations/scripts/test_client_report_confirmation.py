"""U046 — test_client_report_confirmation.py"""
import importlib.util, json, os, sys, tempfile
from pathlib import Path
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
spec = importlib.util.spec_from_file_location("rsd", os.path.join(_HERE, "run_signature_deck.py"))
rsd = importlib.util.module_from_spec(spec)
try: spec.loader.exec_module(rsd)
except SystemExit: pass

@pytest.mark.parametrize("rec, expected", [
    ({"sent": True, "gateway_msg_id": "abc"}, True),
    ({"sent": True, "gateway_msg_id": ""}, False),
    ({"sent": False, "gateway_msg_id": "abc"}, False),
    ({"sent": False, "gateway_msg_id": "", "undeliverable": "no owner target configured"}, True),
    ({}, False),
])
def test_report_confirmed(rec, expected):
    assert rsd._report_confirmed(rec) == expected

def test_any_truthy_undeliverable():
    assert rsd._report_confirmed({"sent": False, "gateway_msg_id": "", "undeliverable": "anything at all"}) is True

@pytest.mark.parametrize("env_val, expected", [
    (None, False), ("", False), ("0", False), ("true", False),
    ("yes", False), ("1 ", False), ("1", True),
])
def test_report_confirm_enforced(env_val, expected):
    key = "PRESENTATION_REPORT_CONFIRM_ENFORCE"
    if env_val is None: os.environ.pop(key, None)
    else: os.environ[key] = env_val
    try: assert rsd._report_confirm_enforced() == expected
    finally: os.environ.pop(key, None)

_PHASES = [{"id": "P4-COPY", "order": 4, "produces_artifact": "copy.json"}, {"id": "P9-DELIVER", "order": 9}]
_DEF_ATT = {"P4-COPY"}

def _wr(rd, recs):
    p = rsd._client_reports_path(rd); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(recs))

def _gate(rd, enf, att=_DEF_ATT):
    if enf: os.environ["PRESENTATION_REPORT_CONFIRM_ENFORCE"] = "1"
    else: os.environ.pop("PRESENTATION_REPORT_CONFIRM_ENFORCE", None)
    orig = getattr(rsd, "_attested_phase_ids", None)
    rsd._attested_phase_ids = lambda _rd, _a=att: set(_a)
    try: return rsd._check_prior_phase_reports(rd, _PHASES, "P9-DELIVER")
    finally:
        if orig is not None: rsd._attested_phase_ids = orig
        os.environ.pop("PRESENTATION_REPORT_CONFIRM_ENFORCE", None)

def _r(pid, kind, sent=True, gid="mid-1", und=""):
    return {"phase_id": pid, "kind": kind, "gateway_msg_id": gid, "sent": sent, "text": "t", "ts": "x", "undeliverable": und}

def test_warn_unconfirmed(capsys):
    rd = Path(tempfile.mkdtemp())
    _wr(rd, [_r("P4-COPY", "start", sent=False, gid=""), _r("P4-COPY", "done", sent=False, gid="")])
    out = _gate(rd, False); c = capsys.readouterr()
    assert out == "" and "WARN-REPORT-UNCONFIRMED" in c.err and "P4-COPY:start" in c.err and "P4-COPY:done" in c.err

def test_enforce_unconfirmed_blocks():
    rd = Path(tempfile.mkdtemp())
    _wr(rd, [_r("P4-COPY", "start", sent=False, gid=""), _r("P4-COPY", "done", sent=False, gid="")])
    out = _gate(rd, True)
    assert out != "" and out.startswith("AF-PHASE-REPORT-MISSING:")

def test_missing_blocks_warn():
    rd = Path(tempfile.mkdtemp()); _wr(rd, [])
    assert _gate(rd, False) != "" and "AF-PHASE-REPORT-MISSING" in _gate(rd, False)

def test_missing_blocks_enforce():
    rd = Path(tempfile.mkdtemp()); _wr(rd, [])
    assert _gate(rd, True) != "" and "AF-PHASE-REPORT-MISSING" in _gate(rd, True)

def test_p0_exemption_warn():
    rd = Path(tempfile.mkdtemp()); _wr(rd, [])
    ph = [{"id": "P-0.5-RESEARCH", "order": -0.5}, {"id": "P9-DELIVER", "order": 9}]
    rsd._attested_phase_ids = lambda _rd: {"P-0.5-RESEARCH"}
    try: assert rsd._check_prior_phase_reports(rd, ph, "P9-DELIVER") == ""
    finally: pass

def test_p0_exemption_enforce():
    rd = Path(tempfile.mkdtemp()); _wr(rd, [])
    os.environ["PRESENTATION_REPORT_CONFIRM_ENFORCE"] = "1"
    ph = [{"id": "P-0.5-RESEARCH", "order": -0.5}, {"id": "P9-DELIVER", "order": 9}]
    rsd._attested_phase_ids = lambda _rd: {"P-0.5-RESEARCH"}
    try: assert rsd._check_prior_phase_reports(rd, ph, "P9-DELIVER") == ""
    finally: os.environ.pop("PRESENTATION_REPORT_CONFIRM_ENFORCE", None)

def test_emit_undeliverable_no_target(monkeypatch):
    rd = Path(tempfile.mkdtemp())
    monkeypatch.setattr(rsd, "_send_owner_message", lambda _: ("", False))
    monkeypatch.setattr(rsd, "_resolve_owner_route", lambda: (None, None))
    rsd.emit_client_report(rd, "P4-COPY", "start")
    recs = rsd._load_client_reports(rd)
    assert len(recs) == 1 and recs[0]["undeliverable"] == "no owner target configured" and recs[0]["sent"] is False

def test_emit_undeliverable_send_failed(monkeypatch):
    rd = Path(tempfile.mkdtemp())
    monkeypatch.setattr(rsd, "_send_owner_message", lambda _: ("", False))
    monkeypatch.setattr(rsd, "_resolve_owner_route", lambda: ("telegram", "some-id"))
    rsd.emit_client_report(rd, "P4-COPY", "start")
    recs = rsd._load_client_reports(rd)
    assert len(recs) == 1 and recs[0]["undeliverable"] == "gateway send did not confirm" and recs[0]["sent"] is False
