#!/usr/bin/env python3
"""rr_intake_classify.py - classify the intake's answer to the daily self-check.

DRAFT. Not installed anywhere. Target home after build:
  onboarding repo  65-rescue-receiver/rr_intake_classify.py

It REPLACES the substring matching in 65-rescue-receiver/rr-intake-auth-check.sh
(lines 306 to 324 at onboarding v27.1.71):
    case "$_bodytext" in  *test_suppressed*) ... *missing_message*) ... *unauthorized*|*forbidden*|...
A body is matched there as loose text, so the word "unauthorized" appearing
anywhere in any 2xx answer (for example inside an error page, or inside an
echoed problem description) is reported as a stale secret, and the words
"test_suppressed" appearing anywhere are reported as a working channel.

This script parses the body as JSON and reads NAMED fields only.

CLASSES (printed as one JSON object; the exit code mirrors the shell script's)
  OK                 0   HTTP 2xx, JSON, status == "test_suppressed", ticketId is null
  RR_SECRET_STALE    3   HTTP 401 or 403; or 2xx JSON whose status/error is an auth refusal
  RR_OLD_RELAY_URL   4   HTTP 2xx JSON whose status or error is "missing_message"
  UNDETERMINED       75  anything else: no answer, 429, 3xx, 5xx, a 2xx that is not
                         JSON, or a 2xx JSON this check does not recognise

Usage:
  python3 rr_intake_classify.py --http-code 200 --body-file out.json
  python3 rr_intake_classify.py --selftest
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile

AUTH_REFUSALS = {"unauthorized", "forbidden", "invalid_credential", "not_enrolled"}
EXIT = {"OK": 0, "RR_SECRET_STALE": 3, "RR_OLD_RELAY_URL": 4, "UNDETERMINED": 75}


def classify(code: str, body_text: str) -> tuple[str, str]:
    code = (code or "").strip()
    if code in ("", "000"):
        return "UNDETERMINED", "the request did not complete; a failed connection says nothing about the credential"
    if code in ("401", "403"):
        return "RR_SECRET_STALE", "the intake refused this box's credential (HTTP %s)" % code
    if not code.startswith("2"):
        return "UNDETERMINED", "HTTP %s is not a verdict about the credential" % code
    try:
        doc = json.loads(body_text)
    except ValueError:
        return "UNDETERMINED", "HTTP %s with a body that is not JSON (an error page or a login wall)" % code
    if not isinstance(doc, dict):
        return "UNDETERMINED", "HTTP %s with JSON that is not an object" % code
    status = str(doc.get("status") or "").strip().lower()
    error = str(doc.get("error") or "").strip().lower()
    if status == "test_suppressed" and doc.get("ticketId") in (None, ""):
        return "OK", "the intake answered test_suppressed with no ticket: the channel works end to end"
    if status == "missing_message" or error == "missing_message":
        return "RR_OLD_RELAY_URL", "the answer has the retired relay's shape; the address is wrong"
    if status in AUTH_REFUSALS or error in AUTH_REFUSALS:
        return "RR_SECRET_STALE", "a 2xx answer whose status or error field reports an auth refusal"
    return "UNDETERMINED", "a 2xx JSON answer this check does not recognise (status=%r)" % status


def selftest() -> int:
    ok = True
    ok &= classify("200", '{"accepted":true,"ticketId":null,"status":"test_suppressed"}')[0] == "OK"
    ok &= classify("200", '{"accepted":true,"ticketId":"RR-1","status":"test_suppressed"}')[0] == "UNDETERMINED"
    ok &= classify("200", '<html>test_suppressed</html>')[0] == "UNDETERMINED"       # loose text is not proof
    ok &= classify("200", '{"status":"ok","problem":"user said unauthorized"}')[0] == "UNDETERMINED"
    ok &= classify("200", '{"status":"missing_message"}')[0] == "RR_OLD_RELAY_URL"
    ok &= classify("200", '{"error":"not_enrolled"}')[0] == "RR_SECRET_STALE"
    ok &= classify("403", "")[0] == "RR_SECRET_STALE"
    ok &= classify("", "")[0] == "UNDETERMINED"
    ok &= classify("302", "")[0] == "UNDETERMINED"
    ok &= classify("500", "")[0] == "UNDETERMINED"
    ok &= classify("429", "")[0] == "UNDETERMINED"
    print("selftest PASS" if ok else "selftest FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--http-code", default="")
    ap.add_argument("--body-file")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    body = ""
    if a.body_file:
        try:
            with open(a.body_file, encoding="utf-8", errors="replace") as fh:
                body = fh.read()
        except OSError:
            body = ""
    cls, detail = classify(a.http_code, body)
    print(json.dumps({"class": cls, "http": a.http_code or "none", "detail": detail}, sort_keys=True))
    return EXIT[cls]


if __name__ == "__main__":
    sys.exit(main())
