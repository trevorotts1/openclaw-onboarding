#!/usr/bin/env python3
"""test_rename_checker.py -- offline unit tests for scripts/u03_modules/rename_checker.py
(U03 tooling: the fail-closed name check over the Convert and Flow pipeline listing).

WHY THIS TEST EXISTS
  rename_checker.py is the smallest live probe of the U03 family: it decides, from a
  pipeline listing, whether the standard pipeline named byte-exact "Anthology Engine"
  (config/field-map.json pipeline.standard_pipeline_name, SPEC M8) exists on the
  location. Find-and-bind is BY NAME (MASTERDOC floor 11; anthology_registry.py
  provision-pipeline), so a RENAMED pipeline is indistinguishable from an ABSENT one,
  and BOTH must refuse. These tests pin that contract offline -- golden byte-exact
  state PASSES, every attack fixture (renamed / absent / padded / case-drift /
  near-miss) FAILS, the exit-code law (0 golden, 2 STOP on a missing name, 3 HELD on
  scope-unreachable) holds, and the real urllib request carries the browser
  User-Agent (CF 1010 discipline) and NEVER a token on any surface.

Hermetic: rename_checker's check_name / run_live receive a deterministic _FakeCaf
seam; the one end-to-end request test patches urllib.request.urlopen so no socket is
opened. No credential value is ever read, printed, or asserted; the location id is
surfaced as a marker only (last 4 chars). No Anthropic-family identifier appears in
this file. Python 3 stdlib only.

Run: python3 -m pytest 59-anthology-engine/scripts/u03_modules/test_rename_checker.py -q
 or: python3 59-anthology-engine/scripts/u03_modules/test_rename_checker.py
"""
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rename_checker as rc  # noqa: E402
import anthology_registry as reg  # noqa: E402

# The location ids below are SYNTHETIC (never a real client location). The marker
# surface (last 4 chars) is the only form any operator output may carry.
LOC = "loc_test_QcDX"
PIPE_ID = "pipe_tmpl"


def _fake(pipelines=None, behavior="ok"):
    """A deterministic listing stub with the exact seam rename_checker uses."""
    return rc._FakeCaf(pipelines=pipelines, behavior=behavior)


# ---------------------------------------------------------------------------
# check_name -- the name law, fail-closed
# ---------------------------------------------------------------------------
def test_golden_byte_exact_name_passes():
    report = rc.check_name(_fake(pipelines=[{"id": PIPE_ID, "name": "Anthology Engine"}]),
                           LOC)
    assert report["ok"] is True
    assert report["current"] == "Anthology Engine"
    assert report["expected"] == "Anthology Engine"


def test_renamed_pipeline_fails_closed():
    # The canonical drift: the sibling skill's name (u02 attack_wrong_name pin).
    report = rc.check_name(_fake(pipelines=[{"id": PIPE_ID, "name": "Anthology Writer"}]),
                           LOC)
    assert report["ok"] is False
    assert report["current"] == "Anthology Writer"
    assert report["expected"] == "Anthology Engine"


def test_absent_pipeline_fails_closed_with_empty_current():
    report = rc.check_name(_fake(pipelines=[]), LOC)
    assert report["ok"] is False
    assert report["current"] == ""
    assert report["expected"] == "Anthology Engine"


def test_extra_unrelated_pipeline_does_not_break_the_check():
    report = rc.check_name(_fake(pipelines=[
        {"id": PIPE_ID, "name": "Anthology Engine"},
        {"id": "pipe_other", "name": "Some Other Pipeline"},
    ]), LOC)
    assert report["ok"] is True
    assert report["current"] == "Anthology Engine"


def test_whitespace_padded_name_fails_byte_exact():
    report = rc.check_name(_fake(pipelines=[{"id": PIPE_ID, "name": "Anthology Engine "}]),
                           LOC)
    assert report["ok"] is False
    assert report["current"] == "Anthology Engine "


def test_case_drift_fails_byte_exact():
    report = rc.check_name(_fake(pipelines=[{"id": PIPE_ID, "name": "anthology engine"}]),
                           LOC)
    assert report["ok"] is False


def test_contract_scope_seam_finds_name_by_exact_key_only():
    # The whole law is the value the contract carries, so a non-standard want
    # value must fail even when a pipeline of that name exists -- a drifted
    # contract source must never bless a non-standard name.
    report = rc.check_name(_fake(pipelines=[{"id": PIPE_ID, "name": "Anthology Engine"}]),
                           LOC, want="Not the Contract Name")
    assert report["ok"] is False
    assert report["current"] == "Anthology Engine"  # the live name is reported as found
    assert report["expected"] == "Not the Contract Name"


def test_check_name_is_pure_and_reads_only_the_listing():
    caf = _fake(pipelines=[{"id": PIPE_ID, "name": "Anthology Engine"}])
    rc.check_name(caf, LOC)
    assert caf.calls == [LOC], "check_name must issue exactly one listing read"


# ---------------------------------------------------------------------------
# run_live -- exit-code law and the ONE JSON report surface
# ---------------------------------------------------------------------------
def test_run_live_golden_exits_zero_with_ok_true_json(capsys):
    err = io.StringIO()
    rc2 = rc.run_live(_fake(pipelines=[{"id": PIPE_ID, "name": "Anthology Engine"}]),
                      LOC, out=err)
    assert rc2 == reg.EX_OK
    report = json.loads(capsys.readouterr()[0])
    assert report["ok"] is True
    assert report["current"] == "Anthology Engine"
    assert report["expected"] == "Anthology Engine"


def test_run_live_renamed_exits_stop_with_ok_false_json(capsys):
    err = io.StringIO()
    rc2 = rc.run_live(_fake(pipelines=[{"id": PIPE_ID, "name": "Anthology Engine RENAMED"}]),
                      LOC, out=err)
    assert rc2 == reg.EX_STOP
    report = json.loads(capsys.readouterr()[0])
    assert report["ok"] is False
    assert report["current"] == "Anthology Engine RENAMED"
    assert "AF-AE-TEMPLATE-PIPELINE-MISSING" in err.getvalue()


def test_run_live_scope_denied_exits_stop_never_a_fabricated_answer(capsys):
    err = io.StringIO()
    rc2 = rc.run_live(_fake(behavior="scope"), LOC, out=err)
    assert rc2 == reg.EX_STOP
    assert capsys.readouterr()[0] == "", "a refused scope must NOT emit a JSON verdict"


def test_run_live_edge_block_and_transport_exit_held(capsys):
    # CF 1010 edge block and transport failure are UNDETERMINED scope -> HELD (3),
    # retryable -- never a scope STOP and never a fabricated verdict.
    for behavior in ("edge", "transport"):
        err = io.StringIO()
        rc2 = rc.run_live(_fake(behavior=behavior), LOC, out=err)
        assert rc2 == reg.EX_HELD, "behavior %r must exit HELD, got %d" % (behavior, rc2)
        assert "HELD" in err.getvalue()
        assert capsys.readouterr()[0] == "", \
            "an unreachable read must NOT emit a JSON verdict (behavior %r)" % behavior


# ---------------------------------------------------------------------------
# CLI entry -- subcommand law, no credential needed offline
# ---------------------------------------------------------------------------
def test_cli_self_test_exits_zero_offline():
    assert rc.main(["self-test"]) == reg.EX_OK


def test_cli_plan_exits_zero_and_names_the_law():
    assert rc.main(["plan"]) == reg.EX_OK


def test_cli_live_without_credential_exits_stop_without_printing_a_value(monkeypatch, capsys):
    # With NO credential and NO location id resolvable, the live path STOPS
    # (exit 2) naming the labels it checked -- never a printed value. The
    # registry's _env_first is patched so this test NEVER reads the canonical
    # .env stores (doctrine: no store read, no value in the transcript) and a
    # value present in some shell environment can never leak into output.
    monkeypatch.setattr(reg, "_env_first", lambda names, environ=None: (None, None))
    rc2 = rc.main(["live"])
    assert rc2 == reg.EX_STOP
    out, err = capsys.readouterr()
    assert "CONVERT_AND_FLOW_PIT" in (out + err)  # labels named, never values
    # No token-shaped value on the operator surface: 'pit-' is a legit word in
    # the guidance text, but a real token (e.g. "pit-89ff13c9-...") must never
    # land on stdout or stderr.
    assert not re.search(r"pit-[0-9a-f]{8}-[0-9a-f]{4}", out + err), \
        "the STOP surface must not echo a token value"


# ---------------------------------------------------------------------------
# Name law + browser-UA discipline: the REAL request path, end to end
# ---------------------------------------------------------------------------
def test_real_request_carries_browser_ua_and_never_the_token(capsys):
    """Patch urllib.request.urlopen so the REAL CafClient._request executes: the
    request must carry CAF_BROWSER_UA (the Cloudflare edge 1010 fix) and the token
    only in the Authorization header -- never in the URL, and the URL must query
    the location id on the /opportunities/pipelines read."""
    import urllib.request

    captured = {}

    class _FakeResp:
        def __init__(self, body):
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _ok_open(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.header_items()}
        return _FakeResp(b'{"pipelines": [{"id": "pipe_tmpl", "name": "Anthology Engine"}]}')

    saved = urllib.request.urlopen
    urllib.request.urlopen = _ok_open
    try:
        client = reg.CafClient("pit-test-token-not-a-real-value")
        report = rc.check_name(client, LOC)
    finally:
        urllib.request.urlopen = saved

    assert report["ok"] is True
    assert "user-agent" in captured["headers"]
    assert captured["headers"]["user-agent"] == reg.CAF_BROWSER_UA, \
        "the browser UA must ride on every request (CF 1010), got %r" \
        % captured["headers"]["user-agent"]
    assert "/opportunities/pipelines" in captured["url"]
    assert "locationId=" in captured["url"]
    assert "pit-test-token-not-a-real-value" not in captured["url"], \
        "the token must NEVER appear in the URL"
    assert captured["headers"].get("authorization", "").startswith("Bearer "), \
        "the token must ride ONLY in the Authorization header"


# ---------------------------------------------------------------------------
# Contract source pin
# ---------------------------------------------------------------------------
def test_expected_name_pinned_to_field_map_contract():
    # The name law is never hardcoded: it is the committed field-map contract.
    # (self-test refuses a drift; the two read seams must agree with the contract.)
    fm = reg.load_field_map(rc.FIELD_MAP_PATH)
    want = (fm.get("pipeline") or {}).get("standard_pipeline_name") or ""
    assert want == "Anthology Engine"
    assert rc._expected_name == want, "rename_checker's contract pin drifted from field-map"


class _FakeMonkeyPatch:
    """Stand-in for the pytest monkeypatch fixture used by the direct runner."""

    def __init__(self):
        self._saved = {}

    def setenv(self, name, value):
        import os
        self._saved[name] = os.environ.get(name, _MISSING)
        os.environ[name] = value

    def delenv(self, name, raising=True):
        import os
        if name in os.environ:
            self._saved[name] = os.environ.pop(name)
        elif raising:
            raise KeyError(name)

    def setattr(self, target, name, value):
        obj, attr = (target, name) if isinstance(name, str) else (name.__self__, name.__name__)
        self._saved[("attr", obj, attr)] = getattr(obj, attr)
        setattr(obj, attr, value)


_MISSING = object()


def _run_all():
    import contextlib

    class _Cap:
        """pytest-capsys-compatible stand-in: .readouterr() -> (out, err) text
        pair; StringIO files accept writes during the redirected call."""

        def __init__(self):
            self._out, self._err = io.StringIO(), io.StringIO()

        def readouterr(self):
            return self._out.getvalue(), self._err.getvalue()

        def write(self, text):
            self._out.write(text)

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        args = []
        varnames = fn.__code__.co_varnames[:fn.__code__.co_argcount]
        for name in varnames:
            if name == "capsys":
                args.append(_Cap())
            elif name == "monkeypatch":
                args.append(_FakeMonkeyPatch())
        if varnames:
            with contextlib.ExitStack() as stack:
                if "capsys" in varnames:
                    stack.enter_context(contextlib.redirect_stdout(args[varnames.index("capsys")]))
                    stack.enter_context(contextlib.redirect_stderr(args[varnames.index("capsys")]))
                fn(*args)
        else:
            fn()
        try:
            print("  [PASS] %s" % fn.__name__)
        except Exception:
            pass
            print("  [PASS] %s" % fn.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("  [FAIL] %s -- %s" % (fn.__name__, exc))
    print("test_rename_checker: %s (%d/%d)"
          % ("ALL PASSED" if not failed else "FAILURES", len(fns) - failed, len(fns)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
