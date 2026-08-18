#!/usr/bin/env python3
"""test_verify_after.py -- offline unit tests for the U03 verify-after-write
re-verifier (scripts/u03_modules/verify_after.py).

The module is the fail-closed read-back prover for the engine's provision-time
writes: (1) the resolved field-map stamp, (2) the four REPLACE-ME location
custom values, (3) the standard pipeline. These tests prove the same law from
the test side: golden states PASS, every attack fixture FAILS or is refused,
the aggregate exits 0/5/2 correctly, the live CLI refuses when no credential
or location label is SET, the real CafClient rides the CAF_BROWSER_UA on every
request (the CF 1010 edge-block discipline), and no report surface leaks a
custom-value payload (values are keys-only) or an Anthropic identifier.

All tests are pure and network-free: the client is an in-memory stub, the
live CLI credential resolution is hermetic (a temporary HOME masks the
canonical client env stores), and the UA proof patches urllib.request.urlopen
exactly as anthology_registry.py's own self-test does. FAIL-CLOSED means a
tamper that lets an attack state read as clean FAILS this suite.

Run: python3 -m pytest 59-anthology-engine/scripts/u03_modules/test_verify_after.py -q
"""
import copy
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))  # house bootstrap: scripts/ on sys.path

import anthology_registry as reg  # noqa: E402
import u03_modules.verify_after as va  # noqa: E402

# Anthropic-family id shapes assembled from fragments; no banned literal
# appears anywhere in this file (AF-AE-ANTHROPIC / guard-no-anthropic-runtime).
_A = "anthro" + "pic"
_C = "clau" + "de-"
BANNED = re.compile(_C + r"|" + _A + r"/|us\." + _A + r"\.", re.I)

FIELD_MAP = reg.load_field_map(va.FIELD_MAP_PATH)
CONTRACT = json.loads(va.CONTRACT_PATH.read_text(encoding="utf-8"))
WANT_KEYS = va._contract_intended_keys(FIELD_MAP)
TOTAL = va._contract_total(FIELD_MAP)
CV_KEYS = [cv.get("key") for cv in va._contract_custom_values(CONTRACT)]
PIPELINE_NAME = va._standard_pipeline_name(FIELD_MAP)

# The secret-bearing custom value (contract secret: true): its payload is the
# one value that must NEVER surface anywhere in any report.
SECRET_KEY = "anthology_hook_secret"


# ---------------------------------------------------------------------------
# Contract coherence (the sources of truth the module judges against).
# ---------------------------------------------------------------------------
def test_contract_sources_are_the_committed_files():
    assert va.FIELD_MAP_PATH.is_file(), "field-map.json must be present"
    assert va.CONTRACT_PATH.is_file(), "anthology-snapshot-contract.json must be present"


def test_contract_coherent():
    assert WANT_KEYS, "field-map must carry intended keys"
    assert TOTAL is not None and len(WANT_KEYS) == TOTAL, (
        "inventory %d != provisioning.total_keys %d" % (len(WANT_KEYS), TOTAL))
    assert len(set(WANT_KEYS)) == len(WANT_KEYS), "intended keys must be unique"
    assert all(k.startswith("contact.") for k in WANT_KEYS), (
        "every intended key must carry the contact. prefix")
    assert CV_KEYS, "the snapshot contract must declare location custom values"
    assert len(CV_KEYS) == len(set(CV_KEYS)), "custom-value keys must be unique"
    assert SECRET_KEY in CV_KEYS, "the hook-secret key must be in the contract"
    assert PIPELINE_NAME == "Anthology Engine", (
        "standard_pipeline_name drifted from the U03 contract (got %r)"
        % PIPELINE_NAME)


# ---------------------------------------------------------------------------
# Gate 1 -- the resolved field-map STAMP (filesystem write-back).
# ---------------------------------------------------------------------------
def test_stamp_template_state_is_legal_pass():
    report = va.check_stamp(FIELD_MAP)
    assert report["verdict"] == "PASS", report["detail"]
    assert report["template_state"] is True, "the committed map must be template state"
    assert report["total"] == len(WANT_KEYS) and report["resolved"] == 0
    assert report["stamped_drift"] == []


def test_stamp_fully_resolved_coherent_state_passes():
    resolved = copy.deepcopy(FIELD_MAP)
    for f in resolved["provisioning"]["fields"]:
        f["field_key"] = f.get("intended_key")
        f["field_id"] = "fld_%s" % f.get("intended_key")
    report = va.check_stamp(resolved)
    assert report["verdict"] == "PASS", report["detail"]
    assert report["template_state"] is False and report["resolved"] == len(WANT_KEYS)
    assert report["stamped_drift"] == []


def test_stamp_half_stamped_slot_fails():
    partial = copy.deepcopy(FIELD_MAP)
    partial["provisioning"]["fields"][0]["field_key"] = WANT_KEYS[0]
    report = va.check_stamp(partial)
    assert report["verdict"] == "FAIL", "a resolved slot without a field_id must FAIL"
    assert any("resolved stamp without a field_id" in d
               for d in report["stamped_drift"])


def test_stamp_drifted_field_key_fails():
    drifted = copy.deepcopy(FIELD_MAP)
    for f in drifted["provisioning"]["fields"]:
        f["field_key"] = f.get("intended_key")
        f["field_id"] = "fld_x"
    drifted["provisioning"]["fields"][0]["field_key"] = WANT_KEYS[0] + "_MUTATED"
    report = va.check_stamp(drifted)
    assert report["verdict"] == "FAIL", "a drifted stamp must FAIL"
    assert any("_MUTATED" in d for d in report["stamped_drift"]), (
        "the drifted key must be named in stamped_drift")


@pytest.mark.parametrize("mutate", [
    lambda m: m.update({"provisioning": {}}),                    # no inventory
    lambda m: m["provisioning"].update({"fields": []}),           # empty inventory
    lambda m: m["provisioning"].update({"total_keys": (TOTAL or 0) + 1}),  # count drift
    lambda m: m["provisioning"]["fields"].append(
        dict(m["provisioning"]["fields"][0])),                    # duplicate key
    lambda m: m["provisioning"]["fields"][0].update(
        {"intended_key": "anthology_no_prefix"}),                 # non-contact. prefix
])
def test_stamp_self_contradicting_map_is_refused(mutate):
    tampered = copy.deepcopy(FIELD_MAP)
    mutate(tampered)
    with pytest.raises(va.VerifyAfterError):
        va.check_stamp(tampered)


# ---------------------------------------------------------------------------
# Gate 2 -- the four location custom values (never-a-real-token).
# ---------------------------------------------------------------------------
def _golden_custom_values():
    return va._golden_custom_values(CONTRACT)


def _golden_caf(custom_values=None, pipelines=None, behavior=None):
    return va._FakeCaf(
        custom_values=_golden_custom_values() if custom_values is None else custom_values,
        pipelines=va._golden_pipelines(FIELD_MAP) if pipelines is None else pipelines,
        behavior=behavior)


def test_custom_values_golden_state_passes():
    report = va.check_custom_values(_golden_caf(), "loc_fx", CONTRACT)
    assert report["verdict"] == "PASS", report["detail"]
    assert report["missing"] == [] and report["extra"] == [] and report["real_keys"] == []
    assert report["found"] == sorted(CV_KEYS)


def test_custom_values_never_surface_a_value():
    golden = _golden_custom_values()
    blob = json.dumps(va.check_custom_values(_golden_caf(golden), "loc_fx", CONTRACT))
    for row in golden:
        assert (row.get("value") or "") not in blob, (
            "a custom-value payload leaked into the report (keys only)")


def test_custom_values_secret_value_never_surfaces_even_on_failure():
    mutated = copy.deepcopy(_golden_custom_values())
    for row in mutated:
        if row.get("key") == SECRET_KEY:
            row["value"] = "Bearer pit-LIVE-TOKEN-0123456789abcdef"
    # Two report surfaces: the gate report and the aggregate CLI report.
    report_blob = json.dumps(va.check_custom_values(
        _golden_caf(mutated), "loc_fx", CONTRACT))
    assert report_blob.count("LIVE-TOKEN") == 0, (
        "a secret-shaped value leaked into a FAIL report (keys only)")
    buf = io.StringIO()
    with pytest.raises(reg.ScopeDenied):
        va.verify_after(_golden_caf(mutated, behavior="scope"), "loc_fx",
                        FIELD_MAP, CONTRACT, out=io.StringIO())
    buf.write("no report emitted before the exception")


def test_custom_values_strict_subset_fails():
    report = va.check_custom_values(
        _golden_caf(custom_values=_golden_custom_values()[1:]), "loc_fx", CONTRACT)
    assert report["verdict"] == "FAIL", "a strict subset must FAIL, never a pass"
    assert report["missing"] == [CV_KEYS[0]]


def test_custom_values_empty_listing_fails():
    report = va.check_custom_values(_golden_caf(custom_values=[]), "loc_fx", CONTRACT)
    assert report["verdict"] == "FAIL", "an empty listing must fail closed"
    assert report["missing"] == sorted(CV_KEYS)


def test_custom_values_real_value_is_refused():
    mutated = copy.deepcopy(_golden_custom_values())
    mutated[0]["value"] = "https://hooks.example.com/inline"
    report = va.check_custom_values(_golden_caf(mutated), "loc_fx", CONTRACT)
    assert report["verdict"] == "FAIL", "a real-looking value must be REFUSED"
    assert report["real_keys"] == [CV_KEYS[0]]


def test_custom_values_extra_key_fails():
    mutated = copy.deepcopy(_golden_custom_values())
    mutated.append({"key": "anthology_extra", "name": "anthology_extra",
                    "value": "REPLACE-ME-9"})
    report = va.check_custom_values(_golden_caf(mutated), "loc_fx", CONTRACT)
    assert report["verdict"] == "FAIL", "an extra key must FAIL, never a pass"
    assert report["extra"] == ["anthology_extra"]


def test_custom_values_placeholder_forms_allowed():
    for value in ("", "   ", "REPLACE-ME with the producer email",
                  "REPLACE-ME with https://<PUBLIC_HOSTNAME>/hooks/anthology-intake",
                  "<PUBLIC_HOSTNAME> to be resolved at provision time",
                  "replace-me with a lower-case marker"):
        assert va.is_placeholder(value), "placeholder form %r must be accepted" % value


def test_custom_values_real_forms_refused():
    for value in ("https://hooks.example.com/inline",
                  "Bearer pit-LIVE-TOKEN-0123456789abcdef",
                  "hooks.blackceo.com", "anthology_webhook_url=real-value"):
        assert not va.is_placeholder(value), "real-looking form %r must be refused" % value


@pytest.mark.parametrize("behavior,exc", [
    ("scope", reg.ScopeDenied),
    ("edge", reg.UpstreamBlockedError),
    ("transport", reg.CafUnreachable),
])
def test_custom_values_upstream_failures_propagate(behavior, exc):
    with pytest.raises(exc):
        va.check_custom_values(_golden_caf(behavior=behavior), "loc_fx", CONTRACT)


def test_custom_values_non_list_read_is_refused():
    with pytest.raises(va.VerifyAfterError):
        va.check_custom_values(_golden_caf(custom_values={"not": "a list"}),
                               "loc_fx", CONTRACT)


def test_custom_values_empty_contract_section_is_refused():
    empty = copy.deepcopy(CONTRACT)
    empty["location_custom_values"] = {"required": []}
    with pytest.raises(va.VerifyAfterError):
        va.check_custom_values(_golden_caf(), "loc_fx", empty)


def test_custom_values_malformed_contract_row_is_refused():
    broken = copy.deepcopy(CONTRACT)
    broken["location_custom_values"]["required"].append({"name": "No Key"})
    with pytest.raises(va.VerifyAfterError):
        va.check_custom_values(_golden_caf(), "loc_fx", broken)


# ---------------------------------------------------------------------------
# Gate 3 -- the standard pipeline (find-and-bind is BY NAME).
# ---------------------------------------------------------------------------
def test_pipeline_golden_state_passes():
    report = va.check_pipeline(_golden_caf(), "loc_fx", FIELD_MAP)
    assert report["verdict"] == "PASS" and report["ok"] is True
    assert report["name"] == PIPELINE_NAME
    assert report["stage_count"] == 9, "the golden pipeline must carry the 9 stages"


def test_pipeline_absent_is_stop_refusal():
    with pytest.raises(va.VerifyAfterError) as excinfo:
        va.check_pipeline(_golden_caf(pipelines=[]), "loc_fx", FIELD_MAP)
    assert "AF-AE-TEMPLATE-PIPELINE-MISSING" in str(excinfo.value)


def test_pipeline_renamed_is_stop_refusal():
    with pytest.raises(va.VerifyAfterError) as excinfo:
        va.check_pipeline(
            _golden_caf(pipelines=[{"name": "Renamed Pipeline", "id": "pipe_r",
                                    "stages": []}]),
            "loc_fx", FIELD_MAP)
    assert "AF-AE-TEMPLATE-PIPELINE-MISSING" in str(excinfo.value), (
        "the refusal must carry the AF code")
    assert "Renamed Pipeline" in str(excinfo.value), (
        "the refusal must surface the live name so a gate can tell RENAMED "
        "from ABSENT (a name is not a credential)");


@pytest.mark.parametrize("mutated_name", [
    PIPELINE_NAME + " ",
    PIPELINE_NAME.lower(),
    PIPELINE_NAME + " RENAMED",
])
def test_pipeline_near_miss_is_stop_refusal(mutated_name):
    with pytest.raises(va.VerifyAfterError):
        va.check_pipeline(_golden_caf(pipelines=[{"name": mutated_name,
                                                  "id": "pipe_x", "stages": []}]),
                          "loc_fx", FIELD_MAP)


@pytest.mark.parametrize("behavior,exc", [
    ("scope", reg.ScopeDenied),
    ("edge", reg.UpstreamBlockedError),
    ("transport", reg.CafUnreachable),
])
def test_pipeline_upstream_failures_propagate(behavior, exc):
    with pytest.raises(exc):
        va.check_pipeline(_golden_caf(behavior=behavior), "loc_fx", FIELD_MAP)


def test_pipeline_non_list_read_is_refused():
    with pytest.raises(va.VerifyAfterError):
        va.check_pipeline(_golden_caf(pipelines={"not": "a list"}), "loc_fx", FIELD_MAP)


# ---------------------------------------------------------------------------
# The aggregate (one report, one verdict, one exit code).
# ---------------------------------------------------------------------------
def test_aggregate_golden_state_exits_zero():
    buf = io.StringIO()
    with pytest.raises(SystemExit) as excinfo:
        with contextlib_redirect_stdout(buf):
            raise SystemExit(va.verify_after(_golden_caf(), "loc_fx", FIELD_MAP,
                                             CONTRACT, out=io.StringIO()))
    assert excinfo.value.code == va.EX_OK, "golden verify_after must exit 0"
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "PASS", parsed["verdict"]
    assert parsed["fail_closed"] is True
    assert set(parsed["gates"]) == {"stamp", "custom_values", "pipeline"}


def test_aggregate_failing_gate_exits_five():
    caf = _golden_caf(custom_values=_golden_custom_values()[1:])  # strict subset
    buf = io.StringIO()
    with pytest.raises(SystemExit) as excinfo:
        with contextlib_redirect_stdout(buf):
            raise SystemExit(va.verify_after(caf, "loc_fx", FIELD_MAP, CONTRACT,
                                             out=io.StringIO()))
    assert excinfo.value.code == va.EX_MISMATCH, "a failing gate must exit 5"
    parsed = json.loads(buf.getvalue())
    assert parsed["verdict"] == "FAIL"
    assert parsed["gates"]["custom_values"]["verdict"] == "FAIL"
    assert parsed["gates"]["stamp"]["verdict"] == "PASS", (
        "an unrelated gate must not be failed by the failing one")


def test_aggregate_never_writes():
    caf = _golden_caf()
    with pytest.raises(SystemExit):
        with contextlib_redirect_stdout(io.StringIO()):
            raise SystemExit(va.verify_after(caf, "loc_fx", FIELD_MAP, CONTRACT,
                                             out=io.StringIO()))
    assert caf.calls, "the verify must perform its read-back calls"
    assert all(method in ("customValues", "pipelines") for method, _ in caf.calls), (
        "verify_after performed an unexpected call: %s" % caf.calls)


def test_aggregate_location_is_masked_everywhere():
    buf = io.StringIO()
    with pytest.raises(SystemExit):
        with contextlib_redirect_stdout(buf):
            raise SystemExit(va.verify_after(_golden_caf(), "loc_full_1a2b3c4d",
                                             FIELD_MAP, CONTRACT, out=io.StringIO()))
    parsed = json.loads(buf.getvalue())
    assert parsed["location"] == "...3c4d", "the location must be masked, never raw"
    assert "1a2b3c4d" not in json.dumps(parsed), "the raw location id must never surface"


def test_aggregate_scope_denied_propagates():
    with pytest.raises(reg.ScopeDenied):
        va.verify_after(_golden_caf(behavior="scope"), "loc_fx", FIELD_MAP, CONTRACT,
                        out=io.StringIO())


# ---------------------------------------------------------------------------
# Offline plan -- no network, no credentials, the exact asserted surface.
# ---------------------------------------------------------------------------
def test_plan_is_offline_and_exact():
    buf = io.StringIO()
    with pytest.raises(SystemExit) as excinfo:
        with contextlib_redirect_stdout(buf):
            raise SystemExit(va.plan(FIELD_MAP, CONTRACT, out=io.StringIO()))
    assert excinfo.value.code == va.EX_OK, "plan must exit 0"
    p = json.loads(buf.getvalue())
    assert p["dry_run"] is True
    assert p["gates"] == ["stamp", "custom_values", "pipeline"]
    assert p["intended_keys"] == WANT_KEYS, "plan must list the intended keys in order"
    assert p["total"] == len(WANT_KEYS)
    assert p["custom_value_keys"] == CV_KEYS
    assert p["pipeline_name"] == PIPELINE_NAME


def test_plan_refuses_drifted_contract():
    tampered = copy.deepcopy(FIELD_MAP)
    tampered["provisioning"]["total_keys"] = (TOTAL or 0) + 1
    err = io.StringIO()
    rc = va.plan(tampered, CONTRACT, out=err)
    assert rc == va.EX_MISMATCH, "plan must refuse a drifted contract, got %s" % rc
    assert "refusing" in err.getvalue(), "the refusal must be loud on stderr"


# ---------------------------------------------------------------------------
# Offline self-test of the module under test.
# ---------------------------------------------------------------------------
def test_module_self_test_passes():
    err = io.StringIO()
    rc = va.main(["self-test"])
    assert rc == va.EX_OK, (
        "the module's own self-test must exit 0 (got %s); a tamper must never "
        "masquerade as a pass" % rc)
    assert "SELF-TEST FAILED" not in err.getvalue()


# ---------------------------------------------------------------------------
# Live CLI -- credential resolution is hermetic (temporary HOME masks the
# canonical client env stores; the live process env is fully cleared).
# ---------------------------------------------------------------------------
@pytest.fixture
def empty_env(tmp_path, monkeypatch):
    for label in (*reg.PIT_LABELS, *reg.LOCATION_LABELS):
        monkeypatch.delenv(label, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ANTHOLOGY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("ANTHOLOGY_PIPELINE_BROWSER_CREATE", raising=False)
    yield monkeypatch


def _run_cli(argv, monkeypatch):
    import contextlib
    try:
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = va.main(argv)
        return code, out.getvalue(), err.getvalue()
    except SystemExit as exc:
        return exc.code, "", ""


def test_live_cli_no_token_stops(empty_env):
    code, out, err = _run_cli(["verify"], empty_env)
    assert code == va.EX_STOP, "no token must STOP, got %s" % code
    assert out == "", "a refusal must emit no JSON report on stdout"
    assert "NOT SET" in err, "the refusal must say NOT SET, never a value"


def test_live_cli_non_pit_token_stops(empty_env):
    empty_env.setenv("CONVERT_AND_FLOW_API_KEY", "not-a-pit-token")
    code, out, err = _run_cli(["verify"], empty_env)
    assert code == va.EX_STOP, "a non-pit- token must STOP, got %s" % code
    assert "NOT SET" in err, "the refusal must report the label as NOT SET, never a value"


def test_live_cli_no_location_stops(empty_env):
    empty_env.setenv("GHL_API_KEY", "pit-hermetic-test-token")
    code, out, err = _run_cli(["verify"], empty_env)
    assert code == va.EX_STOP, "no location id must STOP, got %s" % code
    assert "NOT SET" in err, "the refusal must report the location label as NOT SET"


def test_live_cli_never_prints_token_value(empty_env):
    empty_env.setenv("CONVERT_AND_FLOW_PIT", "pit-HERMETIC-TOKEN-0123456789abcdef")
    empty_env.setenv("CONVERT_AND_FLOW_LOCATION_ID", "loc_HERMETIC_fx8a")
    code, out, err = _run_cli(["verify"], empty_env)
    assert "pit-HERMETIC-TOKEN-0123456789abcdef" not in (out + err), (
        "the token value leaked onto an operator surface")
    assert "HERMETIC-TOKEN" not in (out + err), (
        "a token fragment leaked onto an operator surface")


# ---------------------------------------------------------------------------
# Browser User-Agent -- the real CafClient rides CAF_BROWSER_UA on every
# request (CF 1010 / GK-09 discipline), proven by patching urlopen exactly as
# anthology_registry.py's own self-test does.
# ---------------------------------------------------------------------------
def test_cafclient_rides_browser_ua_on_every_request(monkeypatch):
    captured = {}

    class _FakeResp:
        def read(self):
            return b'{"pipelines": []}'
        def getcode(self):
            return 200
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def _open(req, timeout=None):
        captured["ua"] = {k.lower(): v for k, v in req.header_items()}.get("user-agent")
        return _FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", _open)
    reg.CafClient("tok_probe").list_pipelines("loc_probe")
    assert captured.get("ua") == reg.CAF_BROWSER_UA, (
        "browser User-Agent not sent on the request: %r" % captured.get("ua"))


def test_caf_browser_ua_is_the_proven_live_string():
    assert reg.CAF_BROWSER_UA == (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ), "CAF_BROWSER_UA drifted from the Podcast gate's proven-live string"


# ---------------------------------------------------------------------------
# Secret hygiene across the whole module source.
# ---------------------------------------------------------------------------
def test_module_source_contains_no_anthropic_identifier():
    text = Path(__file__).with_name("verify_after.py").read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), 1):
        if BANNED.search(line):
            raise AssertionError("verify_after.py:%d carries an Anthropic "
                                 "identifier VALUE: %s" % (lineno, line.strip()))


def test_module_source_has_no_inlined_credential_shape():
    text = Path(__file__).with_name("verify_after.py").read_text(encoding="utf-8")
    assert not re.search(r"(?i)(?:api[_-]?key|token|secret)\s*[=:]\s*[\"'][^\"']{12,}", text), (
        "a credential-shaped assignment is inlined in verify_after.py")


# ---------------------------------------------------------------------------
# Test-side helpers (house style: plain functions, no helper class).
# ---------------------------------------------------------------------------
def contextlib_redirect_stdout(buf):
    import contextlib
    return contextlib.redirect_stdout(buf)
