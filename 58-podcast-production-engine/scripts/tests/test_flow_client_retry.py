#!/usr/bin/env python3
"""Targeted smoke tests for flow_client R-04 retry (URLError / 5xx with backoff)."""

import io
import json
import os
import sys
import urllib.error
import urllib.request

# Inject the flow_client module path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "webhook"))
import flow_client


def _fake_urlopen(seq):
    """Monkeypatch urllib.request.urlopen to yield items from seq.

    Each item is either:
      - a (status, body_str) tuple   -> returns _HttpResponse(status, body)
      - urllib.error.HTTPError       -> raises it
      - urllib.error.URLError        -> raises it
    """
    class _Resp:
        def __init__(self, status, body):
            self.status = status
            self._body = body.encode("utf-8") if isinstance(body, str) else body
        def read(self):
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    it = iter(seq)
    calls = []
    def urlopen(req, timeout=None):
        calls.append(req)
        item = next(it)
        if isinstance(item, urllib.error.URLError):
            raise item
        if isinstance(item, urllib.error.HTTPError):
            raise item
        status, body = item
        return _Resp(status, body)
    urlopen.calls = calls
    return urlopen


def _mk_httperror(code, body):
    """Create an HTTPError with a BytesIO fp so urllib internals work."""
    fp = io.BytesIO(body.encode("utf-8") if isinstance(body, str) else body)
    return urllib.error.HTTPError("http://x", code, "msg", {}, fp)


def _setup_client(sleeps, secret_val="test-secret"):
    """Create a FlowClient with env set up for _http_transport."""
    os.environ["PODCAST_INTAKE_HOOK_SECRET"] = secret_val
    os.environ["PODCAST_INTAKE_ROUTE_ID"] = "route-abc"
    client = flow_client.FlowClient(
        route_id="route-abc",
        sleep=lambda s: sleeps.append(s),
        secret_env="PODCAST_INTAKE_HOOK_SECRET",
    )
    return client


def test_4xx_no_retry():
    """4xx (409) returns immediately without retry."""
    os.environ.pop(flow_client._RETRY_DELAY_ENV, None)
    sleeps = []
    client = _setup_client(sleeps)

    seq = [_mk_httperror(409, '{"code":"revision_conflict"}')]
    orig = urllib.request.urlopen
    mock = _fake_urlopen(seq)
    urllib.request.urlopen = mock
    try:
        status, body = client._http_transport({"action": "get_flow", "flowId": "f1"})
    finally:
        urllib.request.urlopen = orig

    assert status == 409, "expected 409, got %d" % status
    assert body.get("code") == "revision_conflict"
    assert len(sleeps) == 0, "4xx should not trigger sleep (retry)"
    assert len(mock.calls) == 1
    print("  [PASS] 4xx (409) returns immediately without retry")


def test_5xx_retry_then_success():
    """5xx on attempt 1 is retried, success on attempt 2."""
    os.environ.pop(flow_client._RETRY_DELAY_ENV, None)
    sleeps = []
    client = _setup_client(sleeps)

    seq = [
        _mk_httperror(503, '{"error":"down"}'),
        (200, '{"ok":true,"result":{"flow":{"flowId":"f1","revision":1}}}'),
    ]
    orig = urllib.request.urlopen
    mock = _fake_urlopen(seq)
    urllib.request.urlopen = mock
    try:
        status, body = client._http_transport({"action": "get_flow", "flowId": "f1"})
    finally:
        urllib.request.urlopen = orig

    assert status == 200, "expected 200 after retry, got %d" % status
    assert body.get("ok") is True
    assert len(sleeps) == 1, "one sleep for the retry"
    assert sleeps[0] == 2, "first backoff delay should be 2s (base 2)"
    assert len(mock.calls) == 2
    print("  [PASS] 5xx retry then success with 2s backoff")


def test_urlerror_retry_then_success():
    """URLError on attempt 1 is retried, success on attempt 2."""
    os.environ.pop(flow_client._RETRY_DELAY_ENV, None)
    sleeps = []
    client = _setup_client(sleeps)

    seq = [
        urllib.error.URLError("connection refused"),
        (200, '{"ok":true,"result":{}}'),
    ]
    orig = urllib.request.urlopen
    mock = _fake_urlopen(seq)
    urllib.request.urlopen = mock
    try:
        status, body = client._http_transport({"action": "get_flow", "flowId": "f1"})
    finally:
        urllib.request.urlopen = orig

    assert status == 200, "expected 200 after retry"
    assert len(sleeps) == 1
    assert len(mock.calls) == 2
    print("  [PASS] URLError retry then success")


def test_urlerror_exhaustion_raises_flow_error():
    """All URLError attempts fail -> FlowError raised (unchanged surface)."""
    os.environ.pop(flow_client._RETRY_DELAY_ENV, None)
    sleeps = []
    client = _setup_client(sleeps)

    seq = [
        urllib.error.URLError("refused"),
        urllib.error.URLError("refused"),
        urllib.error.URLError("refused"),
    ]
    orig = urllib.request.urlopen
    urllib.request.urlopen = _fake_urlopen(seq)
    try:
        client._http_transport({"action": "get_flow", "flowId": "f1"})
    except flow_client.FlowError as exc:
        assert "gateway unreachable" in str(exc)
        assert "refused" in str(exc)
    else:
        raise AssertionError("expected FlowError on URLError exhaustion")
    finally:
        urllib.request.urlopen = orig

    assert len(sleeps) == 2, "2 sleeps (between attempts 1->2 and 2->3)"
    print("  [PASS] URLError exhaustion raises FlowError (unchanged surface)")


def test_5xx_exhaustion_returns_last_response():
    """All attempts 5xx -> return last HTTP response (not FlowError)."""
    os.environ.pop(flow_client._RETRY_DELAY_ENV, None)
    sleeps = []
    client = _setup_client(sleeps)

    seq = [
        _mk_httperror(503, '{"error":"down"}'),
        _mk_httperror(502, '{"error":"gateway"}'),
        _mk_httperror(500, '{"error":"boom"}'),
    ]
    orig = urllib.request.urlopen
    urllib.request.urlopen = _fake_urlopen(seq)
    try:
        status, body = client._http_transport({"action": "get_flow", "flowId": "f1"})
    finally:
        urllib.request.urlopen = orig

    assert status == 500, "expected 500 from last exhausted attempt"
    assert len(sleeps) == 2
    print("  [PASS] 5xx exhaustion returns last HTTP response")


def test_retry_delay_env_shrinks_sleeps():
    """PODCAST_FLOW_RETRY_DELAY=1 shrinks backoff: 1s, 2s."""
    os.environ[flow_client._RETRY_DELAY_ENV] = "1"
    sleeps = []
    client = _setup_client(sleeps)

    seq = [
        urllib.error.URLError("e1"),
        urllib.error.URLError("e2"),
        urllib.error.URLError("e3"),
    ]
    orig = urllib.request.urlopen
    urllib.request.urlopen = _fake_urlopen(seq)
    try:
        client._http_transport({"action": "get_flow", "flowId": "f1"})
    except flow_client.FlowError:
        pass
    finally:
        urllib.request.urlopen = orig

    os.environ.pop(flow_client._RETRY_DELAY_ENV, None)
    assert sleeps == [1, 2], "with base=1: delay1=1, delay2=2, got %s" % sleeps
    print("  [PASS] PODCAST_FLOW_RETRY_DELAY=1 shrinks backoff to 1s/2s")


def test_backoff_cap():
    """Backoff never exceeds CAP (8s by default)."""
    os.environ.pop(flow_client._RETRY_DELAY_ENV, None)
    assert flow_client.FlowClient._retry_delay(1) == 2
    assert flow_client.FlowClient._retry_delay(2) == 4
    assert flow_client.FlowClient._retry_delay(3) == 8
    assert flow_client.FlowClient._retry_delay(4) == 8, "capped at 8"
    assert flow_client.FlowClient._retry_delay(5) == 8, "capped at 8"
    print("  [PASS] backoff capped at 8s")


def test_retry_logged_to_stderr():
    """Each retry attempt is logged to stderr before sleep."""
    os.environ.pop(flow_client._RETRY_DELAY_ENV, None)
    sleeps = []
    client = _setup_client(sleeps)

    seq = [
        urllib.error.URLError("refused"),
        (200, '{"ok":true}'),
    ]
    orig = urllib.request.urlopen
    urllib.request.urlopen = _fake_urlopen(seq)
    saved_stderr = sys.stderr
    try:
        buf = io.StringIO()
        sys.stderr = buf
        client._http_transport({"action": "get_flow", "flowId": "f1"})
        output = buf.getvalue()
    finally:
        sys.stderr = saved_stderr
        urllib.request.urlopen = orig

    assert len(sleeps) == 1
    assert "retrying in" in output, "expected retry log in stderr, got: %r" % output
    assert "connection error" in output
    print("  [PASS] retry is logged to stderr before sleep")


if __name__ == "__main__":
    ok = True
    for name, fn in [
        ("4xx no retry", test_4xx_no_retry),
        ("5xx retry then success", test_5xx_retry_then_success),
        ("URLError retry then success", test_urlerror_retry_then_success),
        ("URLError exhaustion raises FlowError", test_urlerror_exhaustion_raises_flow_error),
        ("5xx exhaustion returns last response", test_5xx_exhaustion_returns_last_response),
        ("PODCAST_FLOW_RETRY_DELAY shrinks sleeps", test_retry_delay_env_shrinks_sleeps),
        ("backoff cap", test_backoff_cap),
        ("retry logged to stderr", test_retry_logged_to_stderr),
    ]:
        try:
            fn()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print("  [MISS] %s: %s" % (name, exc))
            ok = False
    print("== flow_client_retry test: %s ==" % ("ALL PASSED" if ok else "FAILED"))
    sys.exit(0 if ok else 1)
