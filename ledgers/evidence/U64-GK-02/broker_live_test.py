#!/usr/bin/env python3
"""
U64/GK-02 live proof script for the 51-node Anthology Drive Broker.
Reads ANTHOLOGY_DRIVE_BROKER_TOKEN from env (never printed), hits the
canary webhook path, and exercises all 6 documented actions plus an
idempotency re-read to prove Drive read-back.
Prints ONLY response bodies/status codes -- never the token.

`--self-check` runs the same request builder and response handling against a
local stub server: no token, no network, no Drive writes. CI runs that mode,
because the live mode needs a production token and mutates a live Drive tree.
"""
import json
import os
import sys
import base64
import threading
import http.server
import urllib.request
import urllib.error

BASE = "https://main.blackceoautomations.com/webhook/anthology-drive-u64-canary"
TOKEN_ENV = "ANTHOLOGY_DRIVE_BROKER_TOKEN"

def call(action, body, label, base=None, token=None):
    base = base or BASE
    token = os.environ.get(TOKEN_ENV, "") if token is None else token
    payload = dict(body)
    payload["action"] = action
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        base,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-anthology-broker-token": token,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            code = resp.getcode()
            out = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        code = e.code
        try:
            out = json.loads(e.read().decode("utf-8"))
        except Exception:
            out = {"raw_error": str(e)}
    print(f"\n=== {label} (action={action}) -> HTTP {code} ===")
    print(json.dumps(out, indent=2))
    return code, out

def self_check():
    """Hermetic: the request shape, the token header, and 2xx/401 handling the live run depends on."""
    seen = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n) or b"{}")
            seen["action"] = payload.get("action")
            seen["token"] = self.headers.get("x-anthology-broker-token")
            if payload.get("action") == "denied":
                status, out = 401, {"ok": False, "error": "self-check denial"}
            else:
                status, out = 200, {"ok": True, "action": payload.get("action")}
            raw = json.dumps(out).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d/webhook/anthology-drive-u64-canary" % srv.server_address[1]
    try:
        code, out = call("capabilities", {}, "self-check-200", base=base, token="self-check-token")
        assert code == 200 and out.get("ok") is True and out.get("action") == "capabilities", (code, out)
        assert seen["action"] == "capabilities", seen
        assert seen["token"] == "self-check-token", "token must travel on x-anthology-broker-token"
        code, out = call("denied", {}, "self-check-401", base=base, token="self-check-token")
        assert code == 401 and out.get("ok") is False, (code, out)
    finally:
        srv.shutdown()
    print("broker_live_test --self-check: PASS (request shape, token header, 2xx and 401 handling)")
    return 0

def live():
    TOKEN = os.environ.get(TOKEN_ENV, "")
    if not TOKEN:
        print("FATAL: ANTHOLOGY_DRIVE_BROKER_TOKEN not present in shell env (not printing value regardless)")
        return 2

    results = {}

    # 0) capabilities probe (read-only, no side effects)
    code, out = call("capabilities", {}, "0-capabilities")
    results["capabilities"] = (code, out)

    # 1) create_book_tree (first run -- creates scratch tree under Anthology root)
    code, out = call("create_book_tree", {
        "client_key": "U64-LIVE-TEST",
        "producer_email": "management@blackceo.com",
        "book_title": "U64 Canary Book",
    }, "1a-create_book_tree (create)")
    results["book_tree_1"] = (code, out)
    book_folder_id = out.get("book_folder_id")
    client_folder_id = out.get("client_folder_id")
    producer_folder_id = out.get("producer_folder_id")

    # 1b) re-run identical create_book_tree -- proves idempotent Drive READ-BACK
    # (List nodes must find the SAME folders, not create duplicates)
    code, out = call("create_book_tree", {
        "client_key": "U64-LIVE-TEST",
        "producer_email": "management@blackceo.com",
        "book_title": "U64 Canary Book",
    }, "1b-create_book_tree (idempotent re-read)")
    results["book_tree_2"] = (code, out)
    results["book_tree_idempotent"] = (
        out.get("book_folder_id") == book_folder_id
        and out.get("client_folder_id") == client_folder_id
        and out.get("producer_folder_id") == producer_folder_id
    )

    # 2) create_participant_tree (first + idempotent re-read)
    code, out = call("create_participant_tree", {
        "producer": "U64-LIVE-TEST-Producer",
        "anthology": "U64-LIVE-TEST-Anthology",
        "participant": "U64-LIVE-TEST-Participant",
    }, "2a-create_participant_tree (create)")
    results["participant_tree_1"] = (code, out)
    participant_folder_id = out.get("participant_folder_id")

    code, out = call("create_participant_tree", {
        "producer": "U64-LIVE-TEST-Producer",
        "anthology": "U64-LIVE-TEST-Anthology",
        "participant": "U64-LIVE-TEST-Participant",
    }, "2b-create_participant_tree (idempotent re-read)")
    results["participant_tree_2"] = (code, out)
    results["participant_tree_idempotent"] = out.get("participant_folder_id") == participant_folder_id

    # 3) create_doc (inside the scratch book folder)
    doc_text = "U64 live test content -- proof-of-life for GK-02 broker deploy."
    code, out = call("create_doc", {
        "parent_folder_id": book_folder_id,
        "name": "U64 Canary Doc",
        "text": doc_text,
        "share_mode": "view",
    }, "3-create_doc")
    results["create_doc"] = (code, out)
    doc_id = out.get("doc_id")

    # 4) upload_pdf (small text payload, base64) inside the scratch book folder
    content_b64 = base64.b64encode(b"U64 canary upload test content.").decode("ascii")
    code, out = call("upload_pdf", {
        "parent_folder_id": book_folder_id,
        "name": "u64-canary-upload.txt",
        "content_b64": content_b64,
        "mime": "text/plain",
        "share_mode": "view",
    }, "4-upload_pdf")
    results["upload_pdf"] = (code, out)

    # 5) share_doc_edit on the doc created in step 3
    code, out = call("share_doc_edit", {
        "file_id": doc_id,
        "share_mode": "edit",
    }, "5-share_doc_edit")
    results["share_doc_edit"] = (code, out)

    # 6) pull_doc_text -- reads the doc content BACK from Google Drive
    code, out = call("pull_doc_text", {
        "doc_id": doc_id,
    }, "6-pull_doc_text")
    results["pull_doc_text"] = (code, out)
    pulled_text = out.get("text", "")
    results["pull_doc_text_matches"] = doc_text.strip() in pulled_text

    print("\n\n================ SUMMARY ================")
    for k in ["capabilities", "book_tree_1", "book_tree_2", "participant_tree_1",
              "participant_tree_2", "create_doc", "upload_pdf", "share_doc_edit", "pull_doc_text"]:
        code, out = results[k]
        ok = out.get("ok")
        print(f"{k}: HTTP {code}, ok={ok}")
    print(f"book_tree_idempotent (read-back match): {results['book_tree_idempotent']}")
    print(f"participant_tree_idempotent (read-back match): {results['participant_tree_idempotent']}")
    print(f"pull_doc_text_matches (content read back matches what was written): {results['pull_doc_text_matches']}")
    print(f"book_folder_id: {book_folder_id}")
    print(f"client_folder_id: {client_folder_id}")
    print(f"producer_folder_id: {producer_folder_id}")
    print(f"participant_folder_id: {participant_folder_id}")
    print(f"doc_id: {doc_id}")

    all_2xx = all(200 <= results[k][0] < 300 for k in [
        "capabilities", "book_tree_1", "book_tree_2", "participant_tree_1",
        "participant_tree_2", "create_doc", "upload_pdf", "share_doc_edit", "pull_doc_text"])
    any_501 = any(results[k][0] == 501 for k in results if isinstance(results[k], tuple))
    print(f"\nALL_2XX: {all_2xx}")
    print(f"ANY_501: {any_501}")
    return 0 if (all_2xx and not any_501) else 1

if __name__ == "__main__":
    if "--self-check" in sys.argv:
        sys.exit(self_check())
    sys.exit(live())
