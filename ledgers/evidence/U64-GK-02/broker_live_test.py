#!/usr/bin/env python3
"""
U64/GK-02 live proof script for the 51-node Anthology Drive Broker.
Reads ANTHOLOGY_DRIVE_BROKER_TOKEN from env (never printed), hits the
canary webhook path, and exercises all 6 documented actions plus an
idempotency re-read to prove Drive read-back.
Prints ONLY response bodies/status codes -- never the token.
"""
import json
import os
import sys
import base64
import urllib.request
import urllib.error

BASE = "https://main.blackceoautomations.com/webhook/anthology-drive-u64-canary"
TOKEN = os.environ.get("ANTHOLOGY_DRIVE_BROKER_TOKEN", "")
if not TOKEN:
    print("FATAL: ANTHOLOGY_DRIVE_BROKER_TOKEN not present in shell env (not printing value regardless)")
    sys.exit(2)

def call(action, body, label):
    payload = dict(body)
    payload["action"] = action
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-anthology-broker-token": TOKEN,
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
sys.exit(0 if (all_2xx and not any_501) else 1)
