#!/usr/bin/env python3
"""drive_adapter.py -- Layer 3 Google Drive/Docs delivery adapter (W1.11).

WHAT THIS IS (SPEC 3.4 row 9; SPEC 10.1; PRD 3.7 / 3.13; ENGINE-MANIFEST L9):
  A stateless, direct-REST adapter over the Google Drive v3 and Docs v1 APIs.
  It authenticates with the BlackCEO-owned delivery service account exactly the
  way clawd/google-api.js does (service-account JWT, RS256, domain-wide delegation,
  sub = the impersonated user under the GOOGLE_IMPERSONATE_USER label, full Drive
  scope + the Documents scope). It calls the REST endpoints DIRECTLY -- Skill 14
  is PATTERN REFERENCE ONLY and google-api.js exposes no create/permissions/
  delete actions, so those are re-implemented here (verified live at W0.6).

  The share primitives are per-document anyone-with-link VIEW (reader) for PDFs
  and covers, PLUS per-document anyone-with-link EDIT (writer) for DELIVERABLE
  Docs -- Trevor's law (LOCKED #4) deliberately overrides the engine's view-only
  floor for the editable Docs the co-author edits and the engine then pulls back
  (confirm-then-pull).
  The delivery root is PER CLIENT (U19, superseding the earlier single operator root):
  BlackCEO provisions ONE Google Shared Drive per client inside BlackCEO's own
  Workspace, and this box points at its OWN Shared-Drive root, resolved per box from
  GOOGLE_DRIVE_ROOT_FOLDER (config key delivery.drive_root_folder is a per-box slot,
  never one shared operator root -- no client tree co-mingles with another's). The
  adapter NEVER creates a NEW Drive root nor a new service account (BlackCEO provisions
  the Shared Drive out of band; load_root_folder_id refuses an unresolved slot). The
  delivery tree lives under that per-client root, and drive-tree-provision.py owns the
  idempotent Producer/Anthology/Participant folder tree; THIS module owns:
    - create a Google Doc inside a participant folder + insert its text
    - land a cover PNG (or any media) inside a participant folder
    - per-document anyone-with-link VIEW (reader) OR EDIT (writer) share
      (revocation-preserving); EDIT is deliverable-Docs only, per Trevor's law
    - pull the CURRENT plain-text body back out of a Doc (pull_doc_text) -- the
      confirm-then-pull read-back the engine freezes and revalidates
    - revoke a share and hand back a fresh view link (revoke script path)
    - the per-anthology Drive export bundle (recursive folder manifest)
  Every external WRITE is followed by a byte-for-byte READ-BACK in the SAME job
  (write_and_verify) -> AF-AE-READBACK-MISMATCH on drift.

DOCTRINE:
  - No secret value is ever printed. Credentials are reported by LABEL + SET/
    NOT-SET only. The SA key contents, the private key, the minted token, and the
    impersonated user's address never appear in stdout/stderr.
  - Zero Anthropic identifiers; zero client PII. Google-only surface.

EXIT CODES (SPEC 3.4 row 9; house convention):
  0  success (including an idempotent no-op)
  1  unexpected error
  2  validation / guard refusal (bad arguments, malformed input)
  3  API unreachable OR credential unavailable / held (dependency)
  5  read-back mismatch (AF-AE-READBACK-MISMATCH)

USAGE (machine surface -- each subcommand prints ONE JSON object to stdout;
human notes go to stderr):
  drive_adapter.py probe [--file-id ID]
        read-only reachability probe (files.get on the root or the given id).
  drive_adapter.py create-doc --name NAME --parent-folder-id ID
        [--text-file PATH | --text STR] [--share-view | --share-edit]
        create a Google Doc in the participant folder, insert text, read it back,
        optionally share it VIEW-only (--share-view) or anyone-with-link EDIT
        (--share-edit; Trevor's law for DELIVERABLE Docs); prints
        {doc_id, doc_url, share_mode, permission_id, ...}.
  drive_adapter.py upload --name NAME --parent-folder-id ID --file PATH
        [--mime TYPE] [--share-view | --share-edit]
        land a binary (e.g. the S7 cover PNG) in the participant folder.
  drive_adapter.py pull-doc-text --doc-id ID [--out PATH]
        export the CURRENT plain-text body of a Doc (the confirm-then-pull
        read-back). Prints {byte_len, sha256, text|out}; the engine freezes these
        exact bytes and revalidates them with qc-tier1-anthology.py --mode pullback.
  drive_adapter.py share --file-id ID [--edit]
        anyone-with-link VIEW-only (default) or EDIT (--edit); reads the
        permission back; prints the link.
  drive_adapter.py revoke-share --file-id ID [--permission-id ID]
        [--unlink-from-root-id PUBLIC_ANCESTOR --to-folder-id PRIVATE_DEST]
        delete the DIRECT per-document permission(s). Under the per-client
        Shared-Drive root (floor #10; NEVER anyone-can-read, per-document sharing)
        that deletion IS the revocation. LEGACY fallback -- under an anyone-can-read
        root, inherited anyone access cannot be deleted at the file level, so true
        revocation MOVES the file out of the public root (pass --unlink-from-root-id
        + --to-folder-id). Reports remaining access.
  drive_adapter.py move --file-id ID [--add-parent-id ID] [--remove-parent-id ID]
        relocate a file/folder (the real revocation primitive under a public root).
  drive_adapter.py export-bundle --folder-id ID [--out PATH]
        recursive Drive manifest for one anthology folder (the Drive half of the
        SPEC 10.1 export bundle; anthology_state.py emits the ledger half).
  drive_adapter.py provision-book-tree --client-key K --producer-email E
        --book-title T [--co-author C] [--root-folder-id ID]
        create the per-client/producer/book folder tree + producer editor share and
        print the created folder ids. SELECTS the n8n CREDENTIAL BROKER when it is
        configured (Trevor's Google creds live ONLY in n8n; a client box holds no
        Google key -- only the broker webhook URL + a low-privilege token), else
        falls back to the LOCAL service account (the operator's OWN box).
  drive_adapter.py broker-status
        report whether the n8n Drive broker is configured (SET/NOT-SET only) and
        which actions the adapter speaks.
  drive_adapter.py broker-preflight [--json]
        in broker mode, probe the live broker's capabilities and print (exit 0) or
        HOLD (exit 3) naming any REQUIRED action the broker does not yet implement --
        so an under-provisioned broker fails at provisioning, not mid-run at S7/S8.
        In local-SA mode it is a clean pass (the local SA performs the per-Doc ops).
  drive_adapter.py --self-test        offline coherence checks (no network).

n8n CREDENTIAL BROKER (fleet delivery model): the PRIVILEGED folder-tree creation +
share ops POST to an n8n webhook that holds Trevor's Google service-account key,
which never leaves n8n. A client box holds ONLY N8N_DRIVE_WEBHOOK_URL +
N8N_DRIVE_WEBHOOK_TOKEN; a compromised client box cannot leak Google creds because
they were never there. The per-Doc broker actions (create_doc, upload_pdf,
share_doc_edit, pull_doc_text) AND the per-participant tree (create_participant_tree)
are IMPLEMENTED through the n8n route template, so the whole S0..S8 Drive path runs on
a pure client box through the broker; broker-preflight probes the broker's capabilities
and HOLDs provisioning early (by name) on any missing action.
"""
import argparse
import base64
import hashlib
import http.client
import json
import os
import socket
import sys
import time
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------
SCRIPTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPTS_DIR.parent
CONFIG_DIR = SKILL_DIR / "config"

MIME_FOLDER = "application/vnd.google-apps.folder"
MIME_DOC = "application/vnd.google-apps.document"

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
DOCS_SCOPE = "https://www.googleapis.com/auth/documents"
FULL_SCOPE = DRIVE_SCOPE + " " + DOCS_SCOPE  # one token serves Drive + Docs

GOOGLE_API_HOST = "www.googleapis.com"
DOCS_API_HOST = "docs.googleapis.com"
OAUTH_HOST = "oauth2.googleapis.com"

SA_KEY_ENV = "GOOGLE_SA_KEY_FILE"
IMPERSONATE_ENV = "GOOGLE_IMPERSONATE_USER"
ROOT_FOLDER_ENV = "GOOGLE_DRIVE_ROOT_FOLDER"

# n8n Drive CREDENTIAL BROKER (fleet delivery model). A client box holds NO Google
# key -- only the broker webhook URL (not a secret) + a low-privilege shared token
# (a secret, reported SET/NOT-SET by label only). The privileged folder-tree +
# share ops POST to n8n, which holds Trevor's Google creds that never leave n8n.
N8N_WEBHOOK_URL_ENV = "N8N_DRIVE_WEBHOOK_URL"
N8N_WEBHOOK_TOKEN_ENV = "N8N_DRIVE_WEBHOOK_TOKEN"
BROKER_TOKEN_HEADER = "X-Anthology-Broker-Token"
# Per-Doc broker actions (create a Doc + insert text, upload a PDF/cover binary, share a
# Doc VIEW/EDIT, pull a Doc's text back). These are IMPLEMENTED through the n8n route
# template (config/n8n/anthology-drive-broker.workflow.json), so a pure client box that
# holds NO Google key performs the per-Doc S7/S8 delivery ops through the broker -- not
# just the operator's own box. The high-level flows (deliver_doc / deliver_media /
# do_share / pull_doc_text) route to the broker whenever broker_configured().
BROKER_DOC_ACTIONS = ("create_doc", "upload_pdf", "share_doc_edit", "pull_doc_text")
# The per-participant runtime folder tree (Root/Producer/Anthology/Participant) that S0
# intake mints "on first sight" is brokered under this action (drive-tree-provision.py).
BROKER_PARTICIPANT_ACTION = "create_participant_tree"
# The full action set a broker must expose for a pure client box to run the engine
# end-to-end (per-book tree + S0 per-participant tree + the per-Doc S7/S8 ops). The
# broker-preflight probe HOLDs provisioning early, BY NAME, on any that are missing so
# an under-provisioned broker fails at GATE 1 rather than dead-ending mid-run at S7/S8.
BROKER_REQUIRED_ACTIONS = (
    ("create_book_tree", BROKER_PARTICIPANT_ACTION) + BROKER_DOC_ACTIONS)

EX_OK, EX_ERR, EX_VALIDATION, EX_DEP, EX_READBACK = 0, 1, 2, 3, 5

_HTTP_RETRIES = 3
_HTTP_BACKOFF = 1.5
_HTTP_TIMEOUT = 60


# ---------------------------------------------------------------------------
# Typed errors -> deterministic exit codes
# ---------------------------------------------------------------------------
class AdapterError(Exception):
    exit_code = EX_ERR


class ValidationError(AdapterError):
    exit_code = EX_VALIDATION


class DependencyError(AdapterError):
    """Credential unavailable, or the Google API could not be reached."""
    exit_code = EX_DEP


class ReadbackMismatch(AdapterError):
    """A write did not read back byte-for-byte -> AF-AE-READBACK-MISMATCH."""
    exit_code = EX_READBACK


# ---------------------------------------------------------------------------
# Auth -- service-account JWT (RS256, domain-wide delegation), per google-api.js
# ---------------------------------------------------------------------------
def _b64u(raw):
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _load_sa():
    """Load the service-account key file named by GOOGLE_SA_KEY_FILE.

    The key material is held in memory only and NEVER printed."""
    path = os.environ.get(SA_KEY_ENV)
    if not path:
        raise DependencyError(
            "%s NOT SET; the BlackCEO-owned delivery service-account key is "
            "required (no value is created here)." % SA_KEY_ENV)
    p = Path(path)
    if not p.is_file():
        raise DependencyError(
            "%s points at a file that does not exist or is unreadable "
            "(reported by label only)." % SA_KEY_ENV)
    try:
        sa = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - surface class, never contents
        raise DependencyError(
            "%s could not be parsed as JSON (%s)." % (SA_KEY_ENV, type(exc).__name__))
    if not sa.get("client_email") or not sa.get("private_key"):
        raise DependencyError(
            "%s is missing client_email/private_key fields." % SA_KEY_ENV)
    return sa


def _rsa_sign_sha256(signing_input, private_key_pem):
    """RS256 sign `signing_input` (bytes) with the PEM private key.

    Primary path: the `cryptography` library (present wherever the Google client
    libraries are). Fallback: the openssl CLI, feeding the key through a 0600
    temp file that is unlinked immediately. The key never lands in argv or logs.
    Returns the raw signature bytes."""
    # -- primary: cryptography --------------------------------------------
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        key = serialization.load_pem_private_key(
            private_key_pem.encode("utf-8"), password=None)
        return key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    except ImportError:
        pass
    # -- fallback: openssl CLI via a short-lived 0600 temp file -----------
    import subprocess
    import tempfile
    tmp = tempfile.NamedTemporaryFile(  # POSIX default mode is 0600
        mode="w", suffix=".pem", delete=False)
    try:
        os.chmod(tmp.name, 0o600)
        tmp.write(private_key_pem)
        tmp.close()
        proc = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", tmp.name, "-binary"],
            input=signing_input, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise DependencyError(
                "RS256 signing failed: neither the cryptography library nor the "
                "openssl CLI could sign the JWT.")
        return proc.stdout
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


# process-lifetime token cache keyed by scope string
_TOKEN_CACHE = {}


def mint_token(scope=FULL_SCOPE):
    """Mint (and cache) an OAuth access token for `scope` via the SA JWT grant.

    Mirrors clawd/google-api.js getToken(): RS256-signed assertion with
    iss=client_email, sub=GOOGLE_IMPERSONATE_USER, aud=oauth2 token endpoint,
    exchanged at oauth2.googleapis.com/token for a bearer token."""
    now = int(time.time())
    cached = _TOKEN_CACHE.get(scope)
    if cached and cached[1] - 60 > now:
        return cached[0]

    sub = os.environ.get(IMPERSONATE_ENV)
    if not sub:
        raise DependencyError(
            "%s NOT SET; the impersonated Workspace user is required "
            "(value referenced by label only, never printed)." % IMPERSONATE_ENV)
    sa = _load_sa()

    header = _b64u(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")))
    payload = _b64u(json.dumps({
        "iss": sa["client_email"],
        "sub": sub,
        "aud": "https://%s/token" % OAUTH_HOST,
        "iat": now,
        "exp": now + 3600,
        "scope": scope,
    }, separators=(",", ":")))
    signing_input = ("%s.%s" % (header, payload)).encode("ascii")
    signature = _b64u(_rsa_sign_sha256(signing_input, sa["private_key"]))
    assertion = "%s.%s.%s" % (header, payload, signature)

    body = ("grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer"
            "&assertion=" + assertion)
    status, data = _https(
        "POST", OAUTH_HOST, "/token",
        {"Content-Type": "application/x-www-form-urlencoded"}, body.encode("ascii"))
    if status != 200:
        raise DependencyError(
            "token endpoint returned HTTP %s (check that domain-wide delegation "
            "authorizes the Drive + Documents scopes; no secret shown)." % status)
    try:
        tok = json.loads(data)["access_token"]
    except Exception:
        raise DependencyError("token endpoint response had no access_token.")
    _TOKEN_CACHE[scope] = (tok, now + 3600)
    return tok


# ---------------------------------------------------------------------------
# Low-level HTTPS with a bounded transient retry
# ---------------------------------------------------------------------------
def _https(method, host, path, headers, body=None):
    """One HTTPS round-trip with a small retry on transient failures.

    Returns (status:int, raw:bytes). Raises DependencyError only if every retry
    fails at the socket level (the endpoint is genuinely unreachable)."""
    last = None
    for attempt in range(_HTTP_RETRIES):
        try:
            conn = http.client.HTTPSConnection(host, timeout=_HTTP_TIMEOUT)
            try:
                conn.request(method, path, body=body, headers=headers)
                resp = conn.getresponse()
                raw = resp.read()
                status = resp.status
            finally:
                conn.close()
        except (socket.gaierror, socket.timeout, ConnectionError, OSError) as exc:
            last = exc
            time.sleep(_HTTP_BACKOFF ** attempt)
            continue
        # retry only genuinely transient upstream states
        if status in (429, 500, 502, 503, 504) and attempt < _HTTP_RETRIES - 1:
            time.sleep(_HTTP_BACKOFF ** attempt)
            last = None
            continue
        return status, raw
    raise DependencyError(
        "Google API host %s unreachable after %d attempts (%s)."
        % (host, _HTTP_RETRIES, type(last).__name__ if last else "transient"))


def _json_api(method, host, path, token, body=None, expect=(200,)):
    """JSON REST call. Returns the parsed body on an expected status; otherwise
    raises the right typed error so the exit code is deterministic."""
    headers = {"Authorization": "Bearer %s" % token, "Content-Type": "application/json"}
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    status, raw = _https(method, host, path, headers, payload)
    if status in expect:
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except Exception:
            return {}
    _raise_for_status(status, method, path, raw)


def _raise_for_status(status, method, path, raw):
    detail = ""
    try:
        j = json.loads(raw)
        detail = j.get("error", {}).get("message", "") if isinstance(j, dict) else ""
    except Exception:
        detail = ""
    # scrub anything that could echo an identifier we do not want in logs
    short = detail[:180]
    if status in (401, 403):
        raise DependencyError(
            "auth/permission failure (HTTP %s) on %s -- check the service "
            "account's delegation and the folder ACL. %s" % (status, method, short))
    if status == 404:
        raise DependencyError("resource not found (HTTP 404) on %s %s. %s"
                              % (method, path.split("?")[0], short))
    if status in (429, 500, 502, 503, 504):
        raise DependencyError("Google API transient/overload HTTP %s. %s" % (status, short))
    raise AdapterError("unexpected Google API response HTTP %s on %s. %s"
                       % (status, method, short))


def _q(value):
    """Escape a value for a Drive `q=` name clause (single-quote -> \\')."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


# ---------------------------------------------------------------------------
# Drive / Docs operations (direct REST -- shapes verified live at W0.6)
# ---------------------------------------------------------------------------
_FILE_FIELDS = "id,name,mimeType,parents,trashed,capabilities,webViewLink,webContentLink"


def files_get(token, file_id, fields=_FILE_FIELDS):
    """GET a file's metadata. Raises DependencyError(404) if it does not exist."""
    from urllib.parse import quote
    path = ("/drive/v3/files/%s?supportsAllDrives=true&fields=%s"
            % (quote(file_id, safe=""), quote(fields, safe="(),")))
    return _json_api("GET", GOOGLE_API_HOST, path, token)


def find_child_folder(token, parent_id, name):
    """Return the earliest-created non-trashed child FOLDER named `name`, or None.

    Idempotency anchor for drive-tree-provision.py: Drive permits duplicate
    names, so we pick deterministically by createdTime and never spawn a twin."""
    from urllib.parse import quote
    query = ("'%s' in parents and name = '%s' and mimeType = '%s' and trashed = false"
             % (_q(parent_id), _q(name), MIME_FOLDER))
    path = ("/drive/v3/files?q=%s&orderBy=createdTime&pageSize=100"
            "&fields=files(id,name,mimeType,createdTime)"
            "&supportsAllDrives=true&includeItemsFromAllDrives=true"
            % quote(query, safe=""))
    data = _json_api("GET", GOOGLE_API_HOST, path, token)
    files = data.get("files", [])
    return files[0] if files else None


def create_folder(token, name, parent_id):
    path = "/drive/v3/files?supportsAllDrives=true&fields=id,name,mimeType,webViewLink"
    body = {"name": name, "mimeType": MIME_FOLDER, "parents": [parent_id]}
    return _json_api("POST", GOOGLE_API_HOST, path, token, body)


def get_or_create_folder(token, parent_id, name):
    """Idempotent get-or-create of a child folder. Returns (folder_dict, created).

    NEVER used for the root: the root must pre-exist and is only ever files_get."""
    if not name or not str(name).strip():
        raise ValidationError("a folder name is required (empty name refused).")
    existing = find_child_folder(token, parent_id, name)
    if existing:
        return existing, False
    return create_folder(token, name, parent_id), True


def create_doc(token, name, parent_id):
    """Create an empty Google Doc inside `parent_id`. Returns the file dict."""
    path = "/drive/v3/files?supportsAllDrives=true&fields=id,name,mimeType,webViewLink"
    body = {"name": name, "mimeType": MIME_DOC, "parents": [parent_id]}
    return _json_api("POST", GOOGLE_API_HOST, path, token, body)


def docs_insert_text(token, doc_id, text):
    """Insert `text` at the top of a Google Doc (index 1) via Docs batchUpdate."""
    from urllib.parse import quote
    path = "/v1/documents/%s:batchUpdate" % quote(doc_id, safe="")
    body = {"requests": [{"insertText": {"location": {"index": 1}, "text": text}}]}
    return _json_api("POST", DOCS_API_HOST, path, token, body)


def docs_read_text(token, doc_id):
    """Return the full plain text of a Google Doc body (for read-back)."""
    from urllib.parse import quote
    path = "/v1/documents/%s" % quote(doc_id, safe="")
    doc = _json_api("GET", DOCS_API_HOST, path, token)
    out = []
    for el in doc.get("body", {}).get("content", []):
        para = el.get("paragraph")
        if not para:
            continue
        for pe in para.get("elements", []):
            run = pe.get("textRun")
            if run and "content" in run:
                out.append(run["content"])
    return "".join(out)


def upload_media(token, name, parent_id, local_path, mime=None):
    """Multipart-upload a binary file (e.g. the S7 cover PNG) into a folder."""
    p = Path(local_path)
    if not p.is_file():
        raise ValidationError("upload source not found: %s" % local_path)
    data = p.read_bytes()
    if mime is None:
        mime = _guess_mime(p.name)
    boundary = "anthology-%s" % uuid.uuid4().hex
    metadata = {"name": name, "parents": [parent_id]}
    pre = ("--%s\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n%s\r\n"
           "--%s\r\nContent-Type: %s\r\n\r\n"
           % (boundary, json.dumps(metadata), boundary, mime)).encode("utf-8")
    post = ("\r\n--%s--" % boundary).encode("utf-8")
    payload = pre + data + post
    headers = {
        "Authorization": "Bearer %s" % token,
        "Content-Type": "multipart/related; boundary=%s" % boundary,
    }
    path = ("/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true"
            "&fields=id,name,mimeType,webViewLink,webContentLink")
    status, raw = _https("POST", GOOGLE_API_HOST, path, headers, payload)
    if status != 200:
        _raise_for_status(status, "POST", path, raw)
    return json.loads(raw)


def _guess_mime(filename):
    lower = filename.lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith(".webp"):
        return "image/webp"
    return "application/octet-stream"


def share_view_only(token, file_id):
    """Grant anyone-with-link VIEW (reader, link-only). Returns the permission."""
    from urllib.parse import quote
    path = ("/drive/v3/files/%s/permissions?supportsAllDrives=true"
            "&fields=id,type,role,allowFileDiscovery" % quote(file_id, safe=""))
    body = {"role": "reader", "type": "anyone", "allowFileDiscovery": False}
    return _json_api("POST", GOOGLE_API_HOST, path, token, body)


def share_edit(token, file_id):
    """Grant anyone-with-link EDIT (writer, link-only). Returns the permission.

    Trevor's law (LOCKED #4): a DELIVERABLE Google Doc is shared anyone-with-link
    EDIT so the co-author edits their own Doc in place and the engine pulls the
    edits back (confirm-then-pull). This deliberately overrides the engine's
    view-only floor for deliverable Docs ONLY. It changes only the share ROLE on
    the document; it does NOT change WHOSE Google account, service account, or
    Drive root owns the file. The identical body shape as share_view_only, but
    role=writer."""
    from urllib.parse import quote
    path = ("/drive/v3/files/%s/permissions?supportsAllDrives=true"
            "&fields=id,type,role,allowFileDiscovery" % quote(file_id, safe=""))
    body = {"role": "writer", "type": "anyone", "allowFileDiscovery": False}
    return _json_api("POST", GOOGLE_API_HOST, path, token, body)


def share_user_role(token, file_id, email, role="writer", notify=False):
    """Grant a NAMED USER (emailAddress) a `role` on a file/folder.

    role='writer' = editor, role='reader' = viewer. Used by the LOCAL-SA fallback
    of provision_book_tree to make the producer an EDITOR on the book folder
    (Trevor's access model). The n8n broker performs the identical named-user share
    server-side, so the client box never needs the Google key. Returns the
    permission dict; the producer's address is passed to Google but never printed."""
    from urllib.parse import quote
    path = ("/drive/v3/files/%s/permissions?supportsAllDrives=true"
            "&sendNotificationEmail=%s&fields=id,type,role"
            % (quote(file_id, safe=""), "true" if notify else "false"))
    body = {"role": role, "type": "user", "emailAddress": email}
    return _json_api("POST", GOOGLE_API_HOST, path, token, body)


def list_permissions(token, file_id):
    from urllib.parse import quote
    path = ("/drive/v3/files/%s/permissions?supportsAllDrives=true"
            "&fields=permissions(id,type,role,allowFileDiscovery,permissionDetails)"
            % quote(file_id, safe=""))
    return _json_api("GET", GOOGLE_API_HOST, path, token).get("permissions", [])


def _perm_is_inherited(perm):
    """True iff this permission is INHERITED from an ancestor folder.

    Under the per-client Shared-Drive root (floor #10) the root is NOT anyone-can-read
    and sharing is per-document, so nothing is inherited. This classifier is the
    LEGACY safeguard for an anyone-can-read root topology, where an inherited
    anyone/reader grant CANNOT be deleted at the file level (Drive returns 403).
    Detected via permissionDetails[].inherited."""
    for d in perm.get("permissionDetails", []) or []:
        if d.get("inherited"):
            return True
    return False


def move_file(token, file_id, add_parent=None, remove_parent=None):
    """Relocate a file/folder: add and/or remove a parent (files.update).

    Under the per-client Shared-Drive root (floor #10) revocation is deleting the
    direct per-document grant, so this move is not needed. It is the LEGACY-fallback
    primitive: the ONLY way to truly revoke INHERITED public access under an
    anyone-can-read root is to move the item OUT of the public subtree into a private
    folder. Returns the updated file dict (id, parents)."""
    from urllib.parse import quote
    params = ["supportsAllDrives=true", "fields=id,name,parents"]
    if add_parent:
        params.append("addParents=%s" % quote(add_parent, safe=""))
    if remove_parent:
        params.append("removeParents=%s" % quote(remove_parent, safe=""))
    path = "/drive/v3/files/%s?%s" % (quote(file_id, safe=""), "&".join(params))
    return _json_api("PATCH", GOOGLE_API_HOST, path, token, body={})


def delete_permission(token, file_id, permission_id):
    from urllib.parse import quote
    path = ("/drive/v3/files/%s/permissions/%s?supportsAllDrives=true"
            % (quote(file_id, safe=""), quote(permission_id, safe="")))
    _json_api("DELETE", GOOGLE_API_HOST, path, token, expect=(200, 204))


def delete_file(token, file_id):
    """Trash-free delete (used only for self-cleaning smoke runs)."""
    from urllib.parse import quote
    path = "/drive/v3/files/%s?supportsAllDrives=true" % quote(file_id, safe="")
    _json_api("DELETE", GOOGLE_API_HOST, path, token, expect=(200, 204))


def list_children(token, folder_id):
    """List every non-trashed direct child of a folder (paged)."""
    from urllib.parse import quote
    out = []
    page_token = None
    while True:
        query = "'%s' in parents and trashed = false" % _q(folder_id)
        path = ("/drive/v3/files?q=%s&pageSize=1000&orderBy=folder,name"
                "&fields=nextPageToken,files(id,name,mimeType,webViewLink,createdTime,size,md5Checksum)"
                "&supportsAllDrives=true&includeItemsFromAllDrives=true"
                % quote(query, safe=""))
        if page_token:
            path += "&pageToken=%s" % quote(page_token, safe="")
        data = _json_api("GET", GOOGLE_API_HOST, path, token)
        out.extend(data.get("files", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            return out


# ---------------------------------------------------------------------------
# Read-back guard -- AF-AE-READBACK-MISMATCH (ENGINE-MANIFEST py_symbol)
# ---------------------------------------------------------------------------
def write_and_verify(write_fn, verify_fn, what):
    """Run a write, then verify it read back correctly IN THE SAME JOB.

    `write_fn()` performs the mutation and returns its result; `verify_fn(result)`
    re-reads the live state and returns True iff it matches byte-for-byte. On a
    mismatch this raises ReadbackMismatch -> exit 5 (AF-AE-READBACK-MISMATCH)."""
    result = write_fn()
    if not verify_fn(result):
        raise ReadbackMismatch("read-back mismatch after %s" % what)
    return result


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------
def _is_unresolved_slot(value):
    """True if a config value is still an unresolved provisioning slot rather than a
    real id (e.g. "<LABEL:GOOGLE_DRIVE_ROOT_FOLDER>", "<CLIENT_...>"). Such a value is
    the committed per-box TEMPLATE placeholder and must NEVER be used as a live root --
    a box that never resolved it must fail loudly, not deliver into a bogus id."""
    if not value:
        return True
    v = str(value).strip()
    return v.startswith("<") or "LABEL:" in v


def load_root_folder_id(explicit=None):
    """Resolve the PER-CLIENT delivery root id: explicit arg > env > engine config.

    The root is the per-client BlackCEO-hosted Shared Drive supplied per box via
    GOOGLE_DRIVE_ROOT_FOLDER. Never invents a root: it is only ever verified
    (files_get), never created. An unresolved template slot in engine config is
    IGNORED (a box that never set the env fails loudly rather than delivering into a
    placeholder)."""
    if explicit:
        return explicit
    env = os.environ.get(ROOT_FOLDER_ENV)
    if env:
        return env
    for name in ("engine-config.json", "engine-config.template.json"):
        cfg = CONFIG_DIR / name
        if cfg.is_file():
            try:
                data = json.loads(cfg.read_text(encoding="utf-8"))
                root = data.get("delivery", {}).get("drive_root_folder")
                if root and not _is_unresolved_slot(root):
                    return root
            except Exception:
                continue
    raise ValidationError(
        "no delivery root id resolvable (pass --root-folder-id, or set the per-client "
        "%s to this box's BlackCEO-hosted Shared-Drive root; the committed template "
        "slot is never used as a live root)." % ROOT_FOLDER_ENV)


def _credential_status():
    """SET / NOT-SET report for the operator surface -- never a value."""
    return {
        SA_KEY_ENV: "SET" if os.environ.get(SA_KEY_ENV) else "NOT SET",
        IMPERSONATE_ENV: "SET" if os.environ.get(IMPERSONATE_ENV) else "NOT SET",
    }


# ---------------------------------------------------------------------------
# n8n DRIVE CREDENTIAL BROKER (fleet delivery model).
#
# Trevor's Google service-account key lives ONLY inside n8n (his n8n VPS). A client
# box holds NO Google key -- only the broker webhook URL + a low-privilege shared
# token. The PRIVILEGED folder-tree creation + share are POSTed to the n8n webhook
# (action create_book_tree); n8n uses Trevor's creds (which never leave n8n) to
# create the per-client/producer/book tree under BlackCEO's Anthology root, set the
# shares, and return the created folder ids. A compromised client box cannot leak
# Google creds because they were never there.
#
# SELECTION: if the broker is configured (URL + token both resolve), the privileged
# ops route through it; else they fall back to the local SA. The ONLY box that
# legitimately holds the SA key is the operator's OWN box (never a client box).
# ---------------------------------------------------------------------------
def _broker_webhook_url():
    """Resolve the n8n Drive-broker webhook URL (NOT a secret): env first, then
    engine config delivery.drive_broker.webhook_url. Returns the URL or None; an
    unresolved template slot is ignored so a box that never set it stays SA-mode."""
    url = os.environ.get(N8N_WEBHOOK_URL_ENV)
    if url and not _is_unresolved_slot(url):
        return url
    for name in ("engine-config.json", "engine-config.template.json"):
        cfg = CONFIG_DIR / name
        if cfg.is_file():
            try:
                data = json.loads(cfg.read_text(encoding="utf-8"))
                broker = (data.get("delivery", {}) or {}).get("drive_broker", {}) or {}
                u = broker.get("webhook_url")
                if u and not _is_unresolved_slot(u):
                    return u
            except Exception:
                continue
    return None


def _broker_token():
    """Resolve the low-privilege broker webhook token from N8N_DRIVE_WEBHOOK_TOKEN.
    SECRET: held in memory only, NEVER printed (reported SET/NOT-SET by label)."""
    tok = os.environ.get(N8N_WEBHOOK_TOKEN_ENV)
    return tok if tok and not _is_unresolved_slot(tok) else None


def broker_configured():
    """True iff BOTH the broker webhook URL AND its token resolve on this box.

    When True, the privileged folder-tree + share ops route through the n8n
    credential broker (Trevor's Google creds live ONLY in n8n) instead of the local
    SA. When False, the box falls back to the local SA (the operator's own box)."""
    return bool(_broker_webhook_url() and _broker_token())


def _broker_credential_status():
    """SET / NOT-SET report for the broker levers -- never a value."""
    return {
        N8N_WEBHOOK_URL_ENV: "SET" if _broker_webhook_url() else "NOT SET",
        N8N_WEBHOOK_TOKEN_ENV: "SET" if _broker_token() else "NOT SET",
    }


def _broker_request(action, payload):
    """Low-level POST of one action to the n8n Drive broker; return (status, parsed).

    This does NOT raise on an application-level failure (401/404/501/{ok:false}) so a
    caller that must CLASSIFY the response -- the capabilities / probe preflight -- can
    read the status and body without a try/except. It raises only for transport / config
    problems: the URL or token is unresolved, the URL is not https (the token must never
    travel in cleartext), the host is unreachable, or the body is not JSON. The
    low-privilege webhook token authenticates the call in a header and is NEVER printed.
    n8n commonly wraps a single response item in a one-element list, unwrapped here."""
    from urllib.parse import urlsplit
    url = _broker_webhook_url()
    token = _broker_token()
    if not url:
        raise DependencyError(
            "%s NOT SET; the n8n Drive-broker webhook URL is required." % N8N_WEBHOOK_URL_ENV)
    if not token:
        raise DependencyError(
            "%s NOT SET; the n8n Drive-broker webhook token is required "
            "(value referenced by label only, never printed)." % N8N_WEBHOOK_TOKEN_ENV)
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc:
        raise ValidationError(
            "%s must be an https:// URL (the broker token must never travel in "
            "cleartext)." % N8N_WEBHOOK_URL_ENV)
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    body = dict(payload)
    body["action"] = action
    headers = {"Content-Type": "application/json", BROKER_TOKEN_HEADER: token}
    status, raw = _https("POST", parts.netloc, path, headers,
                         json.dumps(body).encode("utf-8"))
    try:
        parsed = json.loads(raw) if raw else {}
    except Exception:
        parsed = None
    if isinstance(parsed, list):
        parsed = parsed[0] if parsed else {}
    if not isinstance(parsed, dict):
        raise DependencyError("n8n Drive broker returned a non-JSON body.")
    return status, parsed


def _broker_post(action, payload):
    """POST one action to the n8n Drive credential broker; return the parsed JSON dict
    on success, else raise the right typed error (so callers get a deterministic exit
    code). Wraps _broker_request with the fail-loud status/ok classification."""
    status, parsed = _broker_request(action, payload)
    detail = str(parsed.get("error") or parsed.get("message") or "")[:180]
    if status in (401, 403):
        raise DependencyError(
            "n8n Drive broker rejected the webhook token (HTTP %s); check %s. %s"
            % (status, N8N_WEBHOOK_TOKEN_ENV, detail))
    if status == 404:
        raise DependencyError(
            "n8n Drive broker webhook not found (HTTP 404); check %s and that the "
            "workflow is active. %s" % (N8N_WEBHOOK_URL_ENV, detail))
    if status == 501 or parsed.get("error") == "not_implemented":
        raise DependencyError(
            "n8n Drive broker action %r is not implemented on the deployed workflow "
            "(HTTP %s); import/activate the current "
            "config/n8n/anthology-drive-broker.workflow.json. %s"
            % (action, status, detail))
    if status not in (200, 201):
        raise DependencyError("n8n Drive broker returned HTTP %s. %s" % (status, detail))
    if parsed.get("ok") is False:
        raise DependencyError(
            "n8n Drive broker reported failure for action %r: %s"
            % (action, detail or parsed.get("error")))
    return parsed


def broker_create_book_tree(client_key, producer_email, book_title, co_author=None):
    """Route the PRIVILEGED per-book folder-tree creation + shares to the n8n
    credential broker (action create_book_tree).

    Trevor's Google service-account key NEVER lands on this box: n8n holds it,
    creates the per-client/producer/book folder tree under BlackCEO's Anthology
    root, sets the shares (producer = editor on the book folder; PDFs view;
    co-author per-Doc EDIT handled at doc time), and returns the created folder ids.
    Returns a normalized dict:
      {ok, via, root_folder_id, client_folder_id, producer_folder_id,
       book_folder_id, ...}."""
    if not client_key or not str(client_key).strip():
        raise ValidationError("client_key is required for create_book_tree.")
    if not producer_email or not str(producer_email).strip():
        raise ValidationError("producer_email is required for create_book_tree.")
    if not book_title or not str(book_title).strip():
        raise ValidationError("book_title is required for create_book_tree.")
    payload = {
        "client_key": str(client_key).strip(),
        "producer_email": str(producer_email).strip(),
        "book_title": str(book_title).strip(),
    }
    if co_author:
        payload["co_author"] = str(co_author).strip()
    result = _broker_post("create_book_tree", payload)
    for key in ("book_folder_id", "producer_folder_id"):
        if not result.get(key):
            raise DependencyError(
                "n8n Drive broker create_book_tree response is missing %r "
                "(the broker must return the created folder ids)." % key)
    result.setdefault("ok", True)
    result.setdefault("action", "create_book_tree")
    # drive_adapter is authoritative on WHICH path served this call, regardless of any
    # informational marker the workflow returned -> stamp the broker path unconditionally.
    result["via"] = "n8n_broker"
    return result


# ---------------------------------------------------------------------------
# Per-Doc broker actions (create_doc, upload_pdf, share_doc_edit, pull_doc_text) and
# the per-participant tree (create_participant_tree). These route the S0..S8 Drive ops
# through the n8n webhook so a pure client box -- which holds NO Google key -- performs
# them WITHOUT ever touching the Google service account. The broker (n8n) does the
# privileged Google write server-side and returns ids/links; every response is
# normalized to the SAME shape the local-SA flow returns so the stage runners consume
# either path identically. The engine SELECTS these whenever broker_configured().
# ---------------------------------------------------------------------------
def _norm_share_mode(share_mode):
    if share_mode in (None, ""):
        return None
    if share_mode in ("view", "edit"):
        return share_mode
    raise ValidationError(
        "unknown share mode %r (expected 'view', 'edit', or none)" % share_mode)


def broker_create_doc(name, parent_folder_id, text=None, share_mode=None):
    """Broker create_doc: create a Google Doc in `parent_folder_id`, insert `text`,
    optionally share it, and return the SAME dict deliver_doc()'s local-SA path returns.
    n8n performs the create + insert + read-back + share with Trevor's Google creds (which
    never leave n8n) and returns the doc id + link + permission id."""
    if not name or not str(name).strip():
        raise ValidationError("create_doc: a Doc name is required.")
    if not parent_folder_id or not str(parent_folder_id).strip():
        raise ValidationError("create_doc: a parent folder id is required.")
    mode = _norm_share_mode(share_mode)
    payload = {"parent_folder_id": str(parent_folder_id).strip(),
               "name": str(name).strip(), "text": text or ""}
    if mode:
        payload["share_mode"] = mode
    r = _broker_post("create_doc", payload)
    doc_id = r.get("doc_id")
    if not doc_id:
        raise DependencyError(
            "n8n Drive broker create_doc response is missing 'doc_id' (the broker must "
            "return the created Doc id).")
    applied = r.get("share_mode") if "share_mode" in r else mode
    return {
        "ok": True, "action": "create-doc", "via": "n8n_broker", "doc_id": doc_id,
        "name": r.get("name", name), "doc_url": r.get("doc_url") or r.get("webViewLink"),
        "share_mode": applied,
        "view_shared": applied == "view", "edit_shared": applied == "edit",
        "permission_id": r.get("permission_id"), "verified": True,
    }


def broker_upload_media(name, parent_folder_id, local_path, mime=None, share_mode=None):
    """Broker upload_pdf: land a binary (the S7 cover PNG, or a rendered PDF) in
    `parent_folder_id` via the broker. The bytes are base64-encoded on this box and the
    broker uploads them into the folder with Trevor's Google creds. Returns the SAME dict
    deliver_media()'s local-SA path returns (the action key stays 'upload_pdf' -- the
    broker's binary-landing action -- while any media type is supported)."""
    if not parent_folder_id or not str(parent_folder_id).strip():
        raise ValidationError("upload_pdf: a parent folder id is required.")
    p = Path(local_path)
    if not p.is_file():
        raise ValidationError("upload source not found: %s" % local_path)
    if mime is None:
        mime = _guess_mime(p.name)
    mode = _norm_share_mode(share_mode)
    content_b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    payload = {"parent_folder_id": str(parent_folder_id).strip(),
               "name": str(name).strip() if name else p.name,
               "content_b64": content_b64, "mime": mime}
    if mode:
        payload["share_mode"] = mode
    r = _broker_post("upload_pdf", payload)
    file_id = r.get("file_id")
    if not file_id:
        raise DependencyError(
            "n8n Drive broker upload_pdf response is missing 'file_id' (the broker must "
            "return the uploaded file id).")
    applied = r.get("share_mode") if "share_mode" in r else mode
    return {
        "ok": True, "action": "upload", "via": "n8n_broker", "file_id": file_id,
        "name": r.get("name", name), "drive_url": r.get("drive_url") or r.get("webViewLink"),
        "download_url": r.get("download_url") or r.get("webContentLink"),
        "share_mode": applied,
        "view_shared": applied == "view", "edit_shared": applied == "edit",
        "permission_id": r.get("permission_id"), "verified": True,
    }


def broker_share(file_id, share_mode):
    """Broker share_doc_edit: grant anyone-with-link VIEW or EDIT on `file_id` through the
    broker. Returns the SAME dict do_share()'s local-SA path returns."""
    if not file_id or not str(file_id).strip():
        raise ValidationError("share_doc_edit: a file id is required.")
    mode = _norm_share_mode(share_mode)
    if not mode:
        raise ValidationError("share_doc_edit: a share mode ('view' or 'edit') is required.")
    r = _broker_post("share_doc_edit", {"file_id": str(file_id).strip(), "share_mode": mode})
    applied = r.get("share_mode") if "share_mode" in r else mode
    return {
        "ok": True, "action": "share", "via": "n8n_broker", "file_id": file_id,
        "share_mode": applied, "permission_id": r.get("permission_id"),
        "view_url": r.get("view_url") or r.get("webViewLink"), "verified": True,
    }


def broker_pull_doc_text(doc_id):
    """Broker pull_doc_text: return the CURRENT plain-text body of a Google Doc (the
    confirm-then-pull read-back) through the broker. Returns the text string; the caller
    (do_pull_doc_text) freezes the exact bytes + sha256 client-side, so the read-back
    contract is preserved regardless of which path served it."""
    if not doc_id or not str(doc_id).strip():
        raise ValidationError("pull_doc_text: a doc id is required.")
    r = _broker_post("pull_doc_text", {"doc_id": str(doc_id).strip()})
    if "text" not in r:
        raise DependencyError(
            "n8n Drive broker pull_doc_text response is missing 'text' (the broker must "
            "return the Doc body verbatim).")
    return r["text"] or ""


def broker_provision_participant_tree(producer, anthology=None, participant=None):
    """Broker create_participant_tree: idempotent get-or-create of
    Root/Producer[/Anthology[/Participant]] through the broker (the S0 'on first sight'
    runtime tree). Returns the SAME dict drive-tree-provision.provision() returns so the
    S0 caller caches folder ids onto the ledger rows identically in either mode."""
    if not producer or not str(producer).strip():
        raise ValidationError("create_participant_tree: --producer is required.")
    if participant and not anthology:
        raise ValidationError(
            "create_participant_tree: --participant requires --anthology (tree is top-down).")
    payload = {"producer": str(producer).strip()}
    if anthology:
        payload["anthology"] = str(anthology).strip()
    if participant:
        payload["participant"] = str(participant).strip()
    r = _broker_post("create_participant_tree", payload)
    prod_id = r.get("producer_folder_id")
    if not prod_id:
        raise DependencyError(
            "n8n Drive broker create_participant_tree response is missing "
            "'producer_folder_id' (the broker must return the created folder ids).")
    result = {
        "ok": True, "action": "provision", "via": "n8n_broker",
        "root": {"id": r.get("root_folder_id"), "name": r.get("root_folder_name"),
                 "existing": True, "created": False},
        "producer": {"id": prod_id, "name": producer,
                     "created": bool(r.get("producer_created"))},
    }
    deepest = prod_id
    if anthology:
        anth_id = r.get("anthology_folder_id")
        if not anth_id:
            raise DependencyError(
                "n8n Drive broker create_participant_tree omitted 'anthology_folder_id'.")
        result["anthology"] = {"id": anth_id, "name": anthology,
                               "created": bool(r.get("anthology_created"))}
        deepest = anth_id
        if participant:
            part_id = r.get("participant_folder_id")
            if not part_id:
                raise DependencyError(
                    "n8n Drive broker create_participant_tree omitted "
                    "'participant_folder_id'.")
            result["participant"] = {"id": part_id, "name": participant,
                                     "created": bool(r.get("participant_created"))}
            result["participant_folder_id"] = part_id
            deepest = part_id
    result["deepest_folder_id"] = deepest
    return result


def broker_capabilities():
    """Ask the broker which actions it implements (action `capabilities`). Returns the
    implemented-action list, or None if the deployed workflow predates the capabilities
    probe (an old create_book_tree-only broker) -- in which case the caller falls back to
    a per-action probe. Never raises on an application-level status; transport/config
    problems still raise via _broker_request."""
    status, parsed = _broker_request("capabilities", {})
    if status in (200, 201) and isinstance(parsed.get("implemented_actions"), list):
        return [str(a) for a in parsed["implemented_actions"]]
    return None


def broker_preflight():
    """SHORT E9 fix -- probe the broker for the REQUIRED per-Doc/tree action set and
    report exactly which (if any) are MISSING, so provisioning HOLDs early by name
    instead of dead-ending mid-run at S7/S8 on a client box whose broker is not the
    current version.

    In local-SA mode this is a clean pass (the local SA performs every op). In broker
    mode it asks `capabilities`; if the broker predates that probe it falls back to a
    side-effect-free `probe:true` request per action. Returns a machine dict:
      {ok, mode, broker_configured, capabilities, required_actions, missing_actions, ...}."""
    if not broker_configured():
        return {"ok": True, "mode": "local_sa", "broker_configured": False,
                "required_actions": list(BROKER_REQUIRED_ACTIONS), "missing_actions": [],
                "note": "no n8n Drive broker on this box; the local service account "
                        "performs the per-Doc/tree ops (operator's own box)."}
    required = list(BROKER_REQUIRED_ACTIONS)
    try:
        status, parsed = _broker_request("capabilities", {})
    except (DependencyError, ValidationError) as exc:
        return {"ok": False, "mode": "n8n_broker", "broker_configured": True,
                "required_actions": required, "missing_actions": required,
                "error": "%s: %s" % (type(exc).__name__, exc),
                "broker": _broker_credential_status()}
    if status in (401, 403):
        return {"ok": False, "mode": "n8n_broker", "broker_configured": True,
                "auth_failed": True, "required_actions": required,
                "missing_actions": required,
                "detail": "the broker rejected the webhook token (check %s)."
                          % N8N_WEBHOOK_TOKEN_ENV,
                "broker": _broker_credential_status()}
    caps = None
    if status in (200, 201) and isinstance(parsed.get("implemented_actions"), list):
        caps = [str(a) for a in parsed["implemented_actions"]]
    if caps is not None:
        missing = [a for a in required if a not in caps]
    else:
        # Old broker (no capabilities action): probe each action side-effect-free.
        missing = []
        for a in required:
            try:
                st, pj = _broker_request(a, {"probe": True})
            except (DependencyError, ValidationError):
                missing.append(a)
                continue
            implemented = (
                st in (200, 201)
                and pj.get("ok") is not False
                and pj.get("implemented") is not False
                and pj.get("error") not in ("not_implemented", "unknown_action"))
            if not implemented:
                missing.append(a)
    return {"ok": not missing, "mode": "n8n_broker", "broker_configured": True,
            "capabilities": caps, "required_actions": required,
            "missing_actions": missing, "broker": _broker_credential_status()}


def provision_book_tree(client_key, producer_email, book_title, co_author=None,
                        root_folder_id=None):
    """Create the per-client/producer/book Drive folder tree + set the producer
    editor share, returning the created folder ids.

    SELECTION: if the n8n broker is configured (URL + token), the privileged
    creation + share are POSTed to n8n (Trevor's Google creds live ONLY in n8n).
    Otherwise this falls back to the LOCAL service account -- the ONLY box that
    legitimately holds the SA key is the operator's OWN box.

    Returns a dict with via ('n8n_broker' | 'local_sa') and the folder ids."""
    if broker_configured():
        return broker_create_book_tree(client_key, producer_email, book_title,
                                       co_author=co_author)
    # -- local-SA fallback (operator's own box) --
    if not client_key or not str(client_key).strip():
        raise ValidationError("client_key is required.")
    if not producer_email or not str(producer_email).strip():
        raise ValidationError("producer_email is required.")
    if not book_title or not str(book_title).strip():
        raise ValidationError("book_title is required.")
    root_id = load_root_folder_id(root_folder_id)
    token = mint_token()
    client_folder, _ = get_or_create_folder(token, root_id, str(client_key).strip())
    producer_folder, _ = get_or_create_folder(token, client_folder["id"],
                                              str(producer_email).strip())
    book_folder, _ = get_or_create_folder(token, producer_folder["id"],
                                          str(book_title).strip())
    # producer = editor on the book folder (Trevor's access model)
    share_user_role(token, book_folder["id"], str(producer_email).strip(),
                    role="writer", notify=False)
    return {
        "ok": True, "action": "create_book_tree", "via": "local_sa",
        "root_folder_id": root_id,
        "client_folder_id": client_folder["id"],
        "producer_folder_id": producer_folder["id"],
        "book_folder_id": book_folder["id"],
        "producer_editor_shared": True,
        "credentials": _credential_status(),
    }


# ---------------------------------------------------------------------------
# High-level flows used by the CLI subcommands
# ---------------------------------------------------------------------------
def deliver_doc(name, parent_folder_id, text=None, share_mode=None):
    """Create a Doc in the participant folder, insert text (read back), optionally
    share it (read back). `share_mode` is 'view', 'edit', or None:
    a DELIVERABLE Doc uses 'edit' (Trevor's law) so the co-author edits in place
    and the engine pulls it back. Returns a machine-readable result dict.

    SELECTION: on a client box the n8n broker performs this with Trevor's Google creds
    (which never leave n8n); the operator's own box falls back to the local SA."""
    if broker_configured():
        return broker_create_doc(name, parent_folder_id, text=text, share_mode=share_mode)
    token = mint_token()
    doc = create_doc(token, name, parent_folder_id)
    doc_id = doc["id"]

    if text is not None and text != "":
        write_and_verify(
            lambda: docs_insert_text(token, doc_id, text),
            lambda _r: docs_read_text(token, doc_id).rstrip("\n") == text.rstrip("\n"),
            "Docs insertText")

    permission_id, mode_applied = _apply_share(token, doc_id, share_mode)

    meta = files_get(token, doc_id, fields="id,name,webViewLink")
    return {
        "ok": True, "action": "create-doc", "doc_id": doc_id,
        "name": meta.get("name", name), "doc_url": meta.get("webViewLink"),
        "share_mode": mode_applied,
        "view_shared": mode_applied == "view",
        "edit_shared": mode_applied == "edit",
        "permission_id": permission_id,
        "verified": True,
    }


def deliver_media(name, parent_folder_id, local_path, mime=None, share_mode=None):
    """Land a binary (S7 cover PNG) in the participant folder, read back, optionally
    share it. `share_mode` is 'view', 'edit', or None. Cover images stay 'view'
    (an image is not a deliverable Doc: nothing is pulled back from it and the
    co-author only picks a favorite). Returns a machine-readable result dict.

    SELECTION: on a client box the n8n broker lands the bytes (base64-relayed) with
    Trevor's Google creds; the operator's own box falls back to the local SA."""
    if broker_configured():
        return broker_upload_media(name, parent_folder_id, local_path, mime=mime,
                                   share_mode=share_mode)
    token = mint_token()
    up = upload_media(token, name, parent_folder_id, local_path, mime)
    file_id = up["id"]
    # read-back: the file exists under the intended parent
    write_and_verify(
        lambda: up,
        lambda _r: _verify_parent(token, file_id, parent_folder_id),
        "media upload parent check")

    permission_id, mode_applied = _apply_share(token, file_id, share_mode)

    meta = files_get(token, file_id, fields="id,name,webViewLink,webContentLink")
    return {
        "ok": True, "action": "upload", "file_id": file_id,
        "name": meta.get("name", name), "drive_url": meta.get("webViewLink"),
        "download_url": meta.get("webContentLink"),
        "share_mode": mode_applied,
        "view_shared": mode_applied == "view",
        "edit_shared": mode_applied == "edit",
        "permission_id": permission_id,
        "verified": True,
    }


def _verify_anyone_reader(token, file_id, created_perm):
    """True iff the file now carries an anyone/reader/link-only permission."""
    for perm in list_permissions(token, file_id):
        if perm.get("type") == "anyone" and perm.get("role") == "reader" \
                and perm.get("allowFileDiscovery") in (False, None):
            return True
    return False


def _verify_anyone_writer(token, file_id, created_perm):
    """True iff the file now carries an anyone/writer/link-only permission."""
    for perm in list_permissions(token, file_id):
        if perm.get("type") == "anyone" and perm.get("role") == "writer" \
                and perm.get("allowFileDiscovery") in (False, None):
            return True
    return False


def _apply_share(token, file_id, share_mode):
    """Apply an anyone-with-link share of `share_mode`, byte-checked read-back.

      'view'   -> reader (the engine's original floor; PDFs and cover images).
      'edit'   -> writer (anyone-with-link EDIT; Trevor's law for DELIVERABLE
                  Docs so the co-author edits their own Doc and the engine pulls
                  it back).
      None/''  -> no share.

    Returns (permission_id, mode_applied). An unknown mode is refused (exit 2)."""
    if not share_mode:
        return None, None
    if share_mode == "view":
        perm = write_and_verify(
            lambda: share_view_only(token, file_id),
            lambda r: _verify_anyone_reader(token, file_id, r),
            "anyone-with-link view share")
        return perm.get("id"), "view"
    if share_mode == "edit":
        perm = write_and_verify(
            lambda: share_edit(token, file_id),
            lambda r: _verify_anyone_writer(token, file_id, r),
            "anyone-with-link edit share")
        return perm.get("id"), "edit"
    raise ValidationError(
        "unknown share mode %r (expected 'view', 'edit', or none)" % share_mode)


def _verify_parent(token, file_id, parent_id):
    meta = files_get(token, file_id, fields="id,parents,trashed")
    return (not meta.get("trashed", False)) and parent_id in (meta.get("parents") or [])


def do_share(file_id, share_mode="view"):
    # On a client box the broker performs the share; the operator's box uses the local SA.
    if broker_configured():
        return broker_share(file_id, share_mode)
    token = mint_token()
    permission_id, mode_applied = _apply_share(token, file_id, share_mode)
    meta = files_get(token, file_id, fields="id,name,webViewLink")
    return {
        "ok": True, "action": "share", "file_id": file_id,
        "share_mode": mode_applied,
        "permission_id": permission_id, "view_url": meta.get("webViewLink"),
        "verified": True,
    }


def pull_doc_text(doc_id):
    """Return the CURRENT plain-text body of a Google Doc.

    This is the confirm-then-pull read-back: the moment a co-author confirms,
    the engine calls this to lift whatever they typed into their shared editable
    Doc, verbatim, and freezes it as the new stage artifact. Wraps docs_read_text
    over a freshly minted token; byte-exactness is proven in self_test with the
    Docs API mocked. WHOSE account is impersonated is unchanged (mint_token).

    SELECTION: on a client box the broker returns the Doc body; the operator's own box
    reads it via the local SA. Either way do_pull_doc_text freezes the exact bytes."""
    if broker_configured():
        return broker_pull_doc_text(doc_id)
    token = mint_token()
    return docs_read_text(token, doc_id)


def do_pull_doc_text(doc_id, out=None):
    """CLI flow for pull_doc_text: pull the Doc body and report it byte-exactly.

    The result carries a sha256 + byte length so the stage runner can FREEZE the
    exact bytes it then revalidates with qc-tier1-anthology.py --mode pullback
    (word band, title-lock presence, story anchors -- advisory, never blocking)."""
    text = pull_doc_text(doc_id)
    raw = text.encode("utf-8")
    result = {
        "ok": True, "action": "pull-doc-text", "doc_id": doc_id,
        "byte_len": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
        "verified": True,
    }
    if out:
        Path(out).write_text(text, encoding="utf-8")
        result["out"] = str(out)
    else:
        result["text"] = text
    return result


def do_revoke_share(file_id, permission_id=None, unlink_from_root_id=None,
                    to_folder_id=None):
    """Revoke public access to a file.

    Two mechanisms:
      1. DIRECT permissions (grants made ON the file itself) are deleted -- under the
         per-client Shared-Drive root (floor #10; NOT anyone-can-read, per-document
         sharing) this deletion IS the revocation.
      2. LEGACY fallback for an anyone-can-read root: INHERITED anyone access CANNOT
         be deleted at the file level (Drive returns 403). The ONLY true revocation
         is to MOVE the file OUT of the public subtree: pass --unlink-from-root-id
         (the public ancestor to drop) and --to-folder-id (a private destination).
    The result reports honestly whether any anyone access REMAINS."""
    token = mint_token()
    removed = []
    skipped_inherited = []

    perms = list_permissions(token, file_id)
    targets = [p for p in perms if (p.get("id") == permission_id)] if permission_id \
        else [p for p in perms if p.get("type") == "anyone"]
    for perm in targets:
        if _perm_is_inherited(perm):
            skipped_inherited.append(perm.get("id"))
            continue
        delete_permission(token, file_id, perm["id"])
        removed.append(perm.get("id"))

    moved_to = None
    if unlink_from_root_id and to_folder_id:
        upd = move_file(token, file_id, add_parent=to_folder_id,
                        remove_parent=unlink_from_root_id)
        moved_to = to_folder_id
        # re-read after the move; inherited public access should now be gone
        perms = list_permissions(token, file_id)

    # honest read-back: does ANY anyone access still resolve?
    anyone_remaining = [p for p in perms if p.get("type") == "anyone"]
    inherited_remaining = [p.get("id") for p in anyone_remaining if _perm_is_inherited(p)]
    direct_remaining = [p.get("id") for p in anyone_remaining if not _perm_is_inherited(p)]

    # a DIRECT grant we tried to remove must be gone (that is what we control)
    if direct_remaining and (permission_id or not unlink_from_root_id):
        raise ReadbackMismatch("a direct anyone-with-link permission survived revocation")

    meta = files_get(token, file_id, fields="id,name,webViewLink")
    result = {
        "ok": True, "action": "revoke-share", "file_id": file_id,
        "removed_permission_ids": removed,
        "moved_to_folder_id": moved_to,
        "anyone_access": bool(anyone_remaining),
        "current_view_url": meta.get("webViewLink"), "verified": True,
    }
    if skipped_inherited or inherited_remaining:
        result["inherited_anyone_note"] = (
            "anyone access here is INHERITED from the anyone-can-read delivery "
            "root and cannot be deleted at the file level; move the file/subtree "
            "out of the public root (--unlink-from-root-id + --to-folder-id) to "
            "truly revoke.")
        result["inherited_permission_ids"] = skipped_inherited or inherited_remaining
    return result


def do_move(file_id, add_parent=None, remove_parent=None):
    token = mint_token()
    upd = move_file(token, file_id, add_parent=add_parent, remove_parent=remove_parent)
    parents = upd.get("parents") or []
    if add_parent and add_parent not in parents:
        raise ReadbackMismatch("addParents did not take effect")
    if remove_parent and remove_parent in parents:
        raise ReadbackMismatch("removeParents did not take effect")
    return {"ok": True, "action": "move", "file_id": file_id, "parents": parents,
            "verified": True}


def do_export_bundle(folder_id, out=None):
    """Recursively enumerate one anthology folder into a manifest (the Drive half
    of the SPEC 10.1 export bundle). No file contents, no secrets -- ids, names,
    mimeTypes, and view links only."""
    token = mint_token()
    root_meta = files_get(token, folder_id, fields="id,name,mimeType,webViewLink")
    if root_meta.get("mimeType") != MIME_FOLDER:
        raise ValidationError("export-bundle target is not a folder: %s" % folder_id)

    files = []
    stack = [(folder_id, "")]
    seen = set()
    while stack:
        fid, prefix = stack.pop()
        if fid in seen:
            continue
        seen.add(fid)
        for child in list_children(token, fid):
            rel = (prefix + "/" + child["name"]) if prefix else child["name"]
            entry = {
                "id": child["id"], "name": child["name"], "path": rel,
                "mimeType": child.get("mimeType"),
                "webViewLink": child.get("webViewLink"),
                "createdTime": child.get("createdTime"),
                "size": child.get("size"), "md5Checksum": child.get("md5Checksum"),
            }
            files.append(entry)
            if child.get("mimeType") == MIME_FOLDER:
                stack.append((child["id"], rel))

    bundle = {
        "ok": True, "action": "export-bundle",
        "root": {"id": root_meta["id"], "name": root_meta.get("name"),
                 "webViewLink": root_meta.get("webViewLink")},
        "file_count": len(files), "files": files,
    }
    if out:
        Path(out).write_text(json.dumps(bundle, indent=2, ensure_ascii=False),
                             encoding="utf-8")
        return {"ok": True, "action": "export-bundle", "folder_id": folder_id,
                "out": str(out), "file_count": len(files)}
    return bundle


def do_probe(file_id=None):
    """Read-only reachability probe: mint a token and files.get the target (the
    delivery root by default). Zero residue. Proves auth + Drive reachability."""
    token = mint_token()
    target = file_id or load_root_folder_id()
    meta = files_get(token, target, fields="id,name,mimeType,capabilities,shared")
    caps = meta.get("capabilities", {}) or {}
    return {
        "ok": True, "action": "probe", "id": meta.get("id"),
        "name": meta.get("name"), "mimeType": meta.get("mimeType"),
        "is_folder": meta.get("mimeType") == MIME_FOLDER,
        "can_add_children": caps.get("canAddChildren"),
        "can_share": caps.get("canShare"),
        "credentials": _credential_status(),
    }


# ---------------------------------------------------------------------------
# Offline self-test (no network) -- proves the pure logic + wiring contract
# ---------------------------------------------------------------------------
def self_test():
    # exit-code contract
    assert (EX_OK, EX_ERR, EX_VALIDATION, EX_DEP, EX_READBACK) == (0, 1, 2, 3, 5)
    assert ValidationError.exit_code == 2
    assert DependencyError.exit_code == 3
    assert ReadbackMismatch.exit_code == 5
    # base64url is unpadded and url-safe
    assert _b64u(b"\xfb\xff\xfe") == "-__-"
    assert "=" not in _b64u(json.dumps({"alg": "RS256"}))
    # q-escaping neutralizes injection into a Drive name clause
    assert _q("O'Brien") == "O\\'Brien"
    assert _q("a\\b") == "a\\\\b"
    # mime guesser
    assert _guess_mime("cover.PNG") == "image/png"
    assert _guess_mime("x.jpeg") == "image/jpeg"
    assert _guess_mime("m.pdf") == "application/pdf"
    assert _guess_mime("blob.bin") == "application/octet-stream"
    # inherited-permission classifier (the LEGACY anyone-can-read root topology)
    assert _perm_is_inherited({"permissionDetails": [{"inherited": True}]}) is True
    assert _perm_is_inherited({"permissionDetails": [{"inherited": False}]}) is False
    assert _perm_is_inherited({"type": "anyone"}) is False
    # write_and_verify passes on match, raises on drift
    box = {"n": 0}
    r = write_and_verify(lambda: box.__setitem__("n", 7) or "w",
                         lambda _r: box["n"] == 7, "unit")
    assert r == "w"
    raised = False
    try:
        write_and_verify(lambda: "w", lambda _r: False, "unit")
    except ReadbackMismatch:
        raised = True
    assert raised, "write_and_verify must raise on a read-back mismatch"
    # get_or_create refuses an empty folder name (no network reached)
    empty_refused = False
    try:
        get_or_create_folder("tok", "parent", "   ")
    except ValidationError:
        empty_refused = True
    assert empty_refused
    # unresolved-slot classifier
    assert _is_unresolved_slot("<LABEL:GOOGLE_DRIVE_ROOT_FOLDER>") is True
    assert _is_unresolved_slot("<CLIENT_DRIVE_ROOT>") is True
    assert _is_unresolved_slot("") is True
    assert _is_unresolved_slot("0AKp8Qw3Rt5Yu8Io2Pk4Lz1Vt6Bn0Cy7") is False
    # config root resolution: explicit wins; the PER-CLIENT env value is returned as-is
    assert load_root_folder_id("EXPLICIT_ID") == "EXPLICIT_ID"
    _saved_root = os.environ.get(ROOT_FOLDER_ENV)
    os.environ[ROOT_FOLDER_ENV] = "0ACLIENT_PER_BOX_SHARED_DRIVE_ID"
    try:
        assert load_root_folder_id() == "0ACLIENT_PER_BOX_SHARED_DRIVE_ID", \
            "the per-client GOOGLE_DRIVE_ROOT_FOLDER value must be returned verbatim"
    finally:
        if _saved_root is None:
            os.environ.pop(ROOT_FOLDER_ENV, None)
        else:
            os.environ[ROOT_FOLDER_ENV] = _saved_root
    # the committed template pins NO single operator root: it carries a per-box slot
    # resolved from GOOGLE_DRIVE_ROOT_FOLDER, and an unresolved slot is refused so a
    # box that never set the env fails loudly instead of delivering into a placeholder.
    tmpl = CONFIG_DIR / "engine-config.template.json"
    if tmpl.is_file():
        cfg = json.loads(tmpl.read_text(encoding="utf-8"))
        root_cfg = cfg["delivery"]["drive_root_folder"]
        assert _is_unresolved_slot(root_cfg), \
            "template delivery root must be a per-box slot (no hard-pinned operator root)"
        # With no arg and no env, the slot is IGNORED -> loud ValidationError, never
        # a bogus placeholder root. (Live engine-config.json overrides the template.)
        if not (CONFIG_DIR / "engine-config.json").is_file():
            _saved_root2 = os.environ.get(ROOT_FOLDER_ENV)
            os.environ.pop(ROOT_FOLDER_ENV, None)
            try:
                slot_refused = False
                try:
                    load_root_folder_id()
                except ValidationError:
                    slot_refused = True
                assert slot_refused, "an unresolved template slot must not resolve as a root"
            finally:
                if _saved_root2 is not None:
                    os.environ[ROOT_FOLDER_ENV] = _saved_root2

    # -- U7: editable-Doc EDIT share + pull_doc_text read-back (Docs API MOCKED) --
    # anyone/writer classifier: only an anyone+writer+link-only perm satisfies EDIT.
    _saved = {k: globals().get(k) for k in
              ("list_permissions", "_json_api", "mint_token",
               "share_view_only", "share_edit",
               "_verify_anyone_reader", "_verify_anyone_writer", "broker_configured")}
    try:
        # This block exercises the LOCAL-SA path deterministically, independent of any
        # ambient N8N_DRIVE_* env on the test box.
        globals()["broker_configured"] = lambda: False
        globals()["list_permissions"] = lambda *_a, **_k: [
            {"type": "anyone", "role": "writer", "allowFileDiscovery": False}]
        assert _verify_anyone_writer("t", "f", None) is True
        assert _verify_anyone_reader("t", "f", None) is False
        globals()["list_permissions"] = lambda *_a, **_k: [
            {"type": "anyone", "role": "reader", "allowFileDiscovery": False}]
        assert _verify_anyone_writer("t", "f", None) is False
        assert _verify_anyone_reader("t", "f", None) is True

        # share_edit posts an anyone/writer body (captured; no network).
        captured = {}

        def _cap(method, host, path, token, body=None, expect=(200,)):
            captured["body"] = body
            return {"id": "perm-w", "type": "anyone", "role": "writer",
                    "allowFileDiscovery": False}
        globals()["_json_api"] = _cap
        perm = share_edit("tok", "docid")
        assert captured["body"] == {"role": "writer", "type": "anyone",
                                    "allowFileDiscovery": False}, captured
        assert perm["role"] == "writer"

        # _apply_share dispatches view/edit and refuses an unknown mode (exit 2).
        globals()["share_view_only"] = lambda *_a, **_k: {"id": "pv"}
        globals()["share_edit"] = lambda *_a, **_k: {"id": "pe"}
        globals()["_verify_anyone_reader"] = lambda *_a, **_k: True
        globals()["_verify_anyone_writer"] = lambda *_a, **_k: True
        assert _apply_share("t", "f", None) == (None, None)
        assert _apply_share("t", "f", "view") == ("pv", "view")
        assert _apply_share("t", "f", "edit") == ("pe", "edit")
        bad_mode = False
        try:
            _apply_share("t", "f", "sideways")
        except ValidationError:
            bad_mode = True
        assert bad_mode, "an unknown share mode must be refused (ValidationError -> exit 2)"

        # pull_doc_text read-back is BYTE-EXACT with the Docs API MOCKED (acceptance).
        doc_fixture = {"body": {"content": [
            {"paragraph": {"elements": [
                {"textRun": {"content": "The Weight of the Keys\n"}},
                {"textRun": {"content": "My client's own edited line."}}]}},
            {"paragraph": {"elements": [
                {"textRun": {"content": "\nA second paragraph, verbatim.\n"}}]}},
            {"sectionBreak": {}},  # a non-paragraph element is ignored
        ]}}
        expected_body = ("The Weight of the Keys\nMy client's own edited line."
                         "\nA second paragraph, verbatim.\n")
        globals()["_json_api"] = lambda *_a, **_k: doc_fixture
        globals()["mint_token"] = lambda scope=FULL_SCOPE: "FAKE_TOKEN"
        assert docs_read_text("FAKE_TOKEN", "DOCID") == expected_body, \
            "docs_read_text must return the Doc body byte-for-byte"
        res = do_pull_doc_text("DOCID")
        assert res["text"] == expected_body, repr(res.get("text"))
        assert res["byte_len"] == len(expected_body.encode("utf-8"))
        assert res["sha256"] == hashlib.sha256(expected_body.encode("utf-8")).hexdigest()
        # --out writes the exact bytes and omits the inline text.
        import tempfile as _tf
        with _tf.NamedTemporaryFile("w", suffix=".txt", delete=False) as _fh:
            _outp = _fh.name
        try:
            res2 = do_pull_doc_text("DOCID", out=_outp)
            assert "text" not in res2 and res2["out"] == _outp
            assert Path(_outp).read_text(encoding="utf-8") == expected_body
        finally:
            os.unlink(_outp)
    finally:
        for k, v in _saved.items():
            if v is not None:
                globals()[k] = v

    # -- n8n Drive credential broker (HTTP MOCKED; no network) --
    _bsaved = {k: globals().get(k) for k in ("_broker_post", "_broker_request", "mint_token")}
    _benv = {k: os.environ.get(k) for k in (N8N_WEBHOOK_URL_ENV, N8N_WEBHOOK_TOKEN_ENV)}
    try:
        for k in (N8N_WEBHOOK_URL_ENV, N8N_WEBHOOK_TOKEN_ENV):
            os.environ.pop(k, None)
        # the URL alone must NOT enable the broker (both levers required).
        os.environ[N8N_WEBHOOK_URL_ENV] = "https://main.example/webhook/anthology-drive"
        assert broker_configured() is False, "URL alone must not enable the broker"
        os.environ[N8N_WEBHOOK_TOKEN_ENV] = "unit-broker-token"
        assert broker_configured() is True, "URL + token must enable the broker"
        assert _broker_credential_status()[N8N_WEBHOOK_TOKEN_ENV] == "SET"
        assert _broker_credential_status()[N8N_WEBHOOK_TOKEN_ENV] != "unit-broker-token"

        # broker_create_book_tree POSTs action=create_book_tree with the right
        # payload and maps the returned folder ids (the create_book_tree contract).
        captured = {}

        def _fake_post(action, payload):
            captured["action"] = action
            captured["payload"] = dict(payload)
            return {"ok": True, "root_folder_id": "ROOT", "client_folder_id": "CID",
                    "producer_folder_id": "PID", "book_folder_id": "BID"}
        globals()["_broker_post"] = _fake_post
        res = broker_create_book_tree("clientA", "producer@x.example",
                                      "The Weight of the Keys", co_author="co@x.example")
        assert captured["action"] == "create_book_tree", captured
        assert captured["payload"] == {"client_key": "clientA",
                                       "producer_email": "producer@x.example",
                                       "book_title": "The Weight of the Keys",
                                       "co_author": "co@x.example"}, captured
        assert res["book_folder_id"] == "BID" and res["producer_folder_id"] == "PID"
        assert res["via"] == "n8n_broker"

        # provision_book_tree SELECTS the broker when configured (no SA touched).
        globals()["mint_token"] = lambda scope=FULL_SCOPE: (_ for _ in ()).throw(
            AssertionError("mint_token (local SA) must NOT be called in broker mode"))
        sel = provision_book_tree("clientA", "producer@x.example", "Bk")
        assert sel["book_folder_id"] == "BID" and sel.get("via") == "n8n_broker"

        # a broker response missing folder ids fails loudly (never a silent no-op).
        globals()["_broker_post"] = lambda a, p: {"ok": True}
        missing_ids = False
        try:
            broker_create_book_tree("c", "p@x.example", "b")
        except DependencyError:
            missing_ids = True
        assert missing_ids, "a broker response without folder ids must raise"

        # per-Doc broker actions are IMPLEMENTED (routed, normalized, not faked).
        # create_doc: POSTs the right action+payload and returns deliver_doc's shape.
        globals()["_broker_post"] = lambda a, p: (
            captured.update({"action": a, "payload": dict(p)})
            or {"ok": True, "doc_id": "DOC1", "doc_url": "https://docs/DOC1",
                "share_mode": "edit", "permission_id": "PW"})
        d = broker_create_doc("client-DOC", "PARENT", text="body", share_mode="edit")
        assert captured["action"] == "create_doc"
        assert captured["payload"] == {"parent_folder_id": "PARENT",
                                       "name": "client-DOC", "text": "body",
                                       "share_mode": "edit"}, captured
        assert d["doc_id"] == "DOC1" and d["doc_url"] == "https://docs/DOC1"
        assert d["via"] == "n8n_broker" and d["edit_shared"] is True and d["verified"] is True
        # share_doc_edit
        globals()["_broker_post"] = lambda a, p: (
            captured.update({"action": a, "payload": dict(p)})
            or {"ok": True, "share_mode": "view", "permission_id": "PV",
                "view_url": "https://drive/F1"})
        s = broker_share("F1", "view")
        assert captured["action"] == "share_doc_edit" and s["view_url"] == "https://drive/F1"
        assert s["share_mode"] == "view" and s["via"] == "n8n_broker"
        # pull_doc_text returns the Doc body verbatim (the caller freezes bytes).
        globals()["_broker_post"] = lambda a, p: (
            captured.update({"action": a, "payload": dict(p)})
            or {"ok": True, "text": "Verbatim body.\n"})
        assert broker_pull_doc_text("DOCX") == "Verbatim body.\n"
        assert captured["action"] == "pull_doc_text" and captured["payload"] == {"doc_id": "DOCX"}
        # a per-Doc response missing its id/text fails loudly (never a silent no-op).
        globals()["_broker_post"] = lambda a, p: {"ok": True}
        for fn in (lambda: broker_create_doc("n", "p"),
                   lambda: broker_pull_doc_text("d")):
            raised = False
            try:
                fn()
            except DependencyError:
                raised = True
            assert raised, "a per-Doc broker response missing its id/text must raise"
        # deliver_doc SELECTS the broker when configured (the local SA is never minted).
        globals()["_broker_post"] = lambda a, p: {
            "ok": True, "doc_id": "DOC2", "doc_url": "u", "share_mode": p.get("share_mode")}
        dd = deliver_doc("nm", "par", text="t", share_mode="edit")
        assert dd["doc_id"] == "DOC2" and dd["via"] == "n8n_broker"

        # broker-preflight: a capabilities list that covers every REQUIRED action passes;
        # a short one HOLDs and names EXACTLY the missing actions.
        globals()["_broker_request"] = lambda a, p: (
            200, {"ok": True, "implemented_actions": list(BROKER_REQUIRED_ACTIONS)})
        pf = broker_preflight()
        assert pf["ok"] is True and pf["missing_actions"] == [], pf
        globals()["_broker_request"] = lambda a, p: (
            200, {"ok": True, "implemented_actions": ["create_book_tree"]})
        pf2 = broker_preflight()
        assert pf2["ok"] is False, pf2
        assert set(pf2["missing_actions"]) == set(BROKER_DOC_ACTIONS) | {BROKER_PARTICIPANT_ACTION}, pf2
        # an old broker with NO capabilities action -> per-action probe fallback: a 501
        # not_implemented marks that action missing.
        def _probe_req(a, p):
            if a == "capabilities":
                return 501, {"ok": False, "error": "unknown_action"}
            if a in BROKER_DOC_ACTIONS or a == BROKER_PARTICIPANT_ACTION:
                return 501, {"ok": False, "error": "not_implemented"}
            return 200, {"ok": True, "implemented": True}
        globals()["_broker_request"] = _probe_req
        pf3 = broker_preflight()
        assert pf3["ok"] is False and "create_book_tree" not in pf3["missing_actions"], pf3
        assert set(pf3["missing_actions"]) == set(BROKER_DOC_ACTIONS) | {BROKER_PARTICIPANT_ACTION}, pf3

        # _broker_post refuses a non-https URL (token must never travel cleartext).
        # Restore the REAL _broker_post + _broker_request so the https guard runs.
        globals()["_broker_post"] = _bsaved["_broker_post"]
        globals()["_broker_request"] = _bsaved["_broker_request"]
        os.environ[N8N_WEBHOOK_URL_ENV] = "http://insecure.example/webhook/x"
        cleartext_refused = False
        try:
            _broker_post("create_book_tree", {})
        except ValidationError:
            cleartext_refused = True
        assert cleartext_refused, "the broker must refuse a non-https webhook URL"
    finally:
        for k, v in _bsaved.items():
            if v is not None:
                globals()[k] = v
        for k, v in _benv.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    print("drive_adapter self-test: OK (auth assembly, escaping, read-back guard, "
          "per-client root resolution + slot refusal, exit-code contract, EDIT share, "
          "pull_doc_text byte-exact, n8n broker select + payload + https-only, "
          "per-Doc broker create_doc/share/pull + deliver_doc select, "
          "broker-preflight capability/probe HOLD-by-name)")
    return EX_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _out(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")


def build_parser():
    p = argparse.ArgumentParser(
        prog="drive_adapter.py",
        description="Direct Google Drive/Docs delivery adapter (W1.11).")
    p.add_argument("--self-test", action="store_true",
                   help="run offline coherence checks and exit")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("probe", help="read-only reachability probe (files.get)")
    sp.add_argument("--file-id", help="target id (default: the delivery root)")

    cd = sub.add_parser("create-doc", help="create a Google Doc in a folder")
    cd.add_argument("--name", required=True)
    cd.add_argument("--parent-folder-id", required=True)
    g = cd.add_mutually_exclusive_group()
    g.add_argument("--text", help="inline body text to insert")
    g.add_argument("--text-file", help="path to a UTF-8 file whose content is inserted")
    sgd = cd.add_mutually_exclusive_group()
    sgd.add_argument("--share-view", action="store_true",
                     help="also grant anyone-with-link VIEW-only (reader)")
    sgd.add_argument("--share-edit", action="store_true",
                     help="grant anyone-with-link EDIT (writer); Trevor's law for DELIVERABLE Docs")

    up = sub.add_parser("upload", help="land a binary (e.g. the cover PNG) in a folder")
    up.add_argument("--name", required=True)
    up.add_argument("--parent-folder-id", required=True)
    up.add_argument("--file", required=True, help="local path to the binary")
    up.add_argument("--mime", help="MIME type (guessed from the name if omitted)")
    sgu = up.add_mutually_exclusive_group()
    sgu.add_argument("--share-view", action="store_true",
                     help="also grant anyone-with-link VIEW-only (reader)")
    sgu.add_argument("--share-edit", action="store_true",
                     help="grant anyone-with-link EDIT (writer)")

    pd = sub.add_parser("pull-doc-text",
                        help="export the CURRENT plain-text body of a Doc (confirm-then-pull read-back)")
    pd.add_argument("--doc-id", required=True)
    pd.add_argument("--out", help="write the pulled text to this path (else returned inline)")

    sh = sub.add_parser("share", help="anyone-with-link VIEW (default) or EDIT (--edit) share")
    sh.add_argument("--file-id", required=True)
    sh.add_argument("--edit", action="store_true",
                    help="grant anyone-with-link EDIT (writer) instead of VIEW")

    rv = sub.add_parser("revoke-share", help="remove the anyone-with-link permission(s)")
    rv.add_argument("--file-id", required=True)
    rv.add_argument("--permission-id", help="a specific permission id (else all anyone perms)")
    rv.add_argument("--unlink-from-root-id",
                    help="public ancestor to drop (true revocation under a public root)")
    rv.add_argument("--to-folder-id",
                    help="private destination the file is moved into when unlinking")

    mv = sub.add_parser("move", help="add/remove a parent (relocate a file or folder)")
    mv.add_argument("--file-id", required=True)
    mv.add_argument("--add-parent-id")
    mv.add_argument("--remove-parent-id")

    eb = sub.add_parser("export-bundle", help="recursive Drive manifest for one folder")
    eb.add_argument("--folder-id", required=True)
    eb.add_argument("--out", help="write the manifest JSON to this path")

    pbt = sub.add_parser(
        "provision-book-tree",
        help="create the client/producer/book folder tree + producer editor share "
             "(n8n broker if configured, else local SA)")
    pbt.add_argument("--client-key", required=True)
    pbt.add_argument("--producer-email", required=True)
    pbt.add_argument("--book-title", required=True)
    pbt.add_argument("--co-author", help="optional co-author (per-Doc EDIT handled at doc time)")
    pbt.add_argument("--root-folder-id", help="override the local-SA root (ignored in broker mode)")

    sub.add_parser(
        "broker-status",
        help="report whether the n8n Drive broker is configured (SET/NOT-SET only)")

    bp = sub.add_parser(
        "broker-preflight",
        help="probe the broker's capabilities; HOLD (exit 3) naming any REQUIRED "
             "per-Doc/tree action it does not yet implement (local-SA mode: clean pass)")
    bp.add_argument("--json", action="store_true", help="(default) JSON output")

    return p


def dispatch(args):
    if args.self_test:
        return self_test()
    cmd = args.cmd
    if cmd == "probe":
        _out(do_probe(args.file_id))
        return EX_OK
    if cmd == "create-doc":
        text = args.text
        if args.text_file:
            tf = Path(args.text_file)
            if not tf.is_file():
                raise ValidationError("--text-file not found: %s" % args.text_file)
            text = tf.read_text(encoding="utf-8")
        mode = "edit" if args.share_edit else ("view" if args.share_view else None)
        _out(deliver_doc(args.name, args.parent_folder_id, text=text, share_mode=mode))
        return EX_OK
    if cmd == "upload":
        mode = "edit" if args.share_edit else ("view" if args.share_view else None)
        _out(deliver_media(args.name, args.parent_folder_id, args.file,
                           mime=args.mime, share_mode=mode))
        return EX_OK
    if cmd == "pull-doc-text":
        _out(do_pull_doc_text(args.doc_id, args.out))
        return EX_OK
    if cmd == "share":
        _out(do_share(args.file_id, share_mode="edit" if args.edit else "view"))
        return EX_OK
    if cmd == "revoke-share":
        _out(do_revoke_share(args.file_id, args.permission_id,
                             unlink_from_root_id=args.unlink_from_root_id,
                             to_folder_id=args.to_folder_id))
        return EX_OK
    if cmd == "move":
        if not (args.add_parent_id or args.remove_parent_id):
            raise ValidationError("move requires --add-parent-id and/or --remove-parent-id")
        _out(do_move(args.file_id, args.add_parent_id, args.remove_parent_id))
        return EX_OK
    if cmd == "export-bundle":
        _out(do_export_bundle(args.folder_id, args.out))
        return EX_OK
    if cmd == "provision-book-tree":
        _out(provision_book_tree(args.client_key, args.producer_email, args.book_title,
                                 co_author=args.co_author, root_folder_id=args.root_folder_id))
        return EX_OK
    if cmd == "broker-status":
        _out({"ok": True, "action": "broker-status",
              "broker_configured": broker_configured(),
              "broker": _broker_credential_status(),
              "implemented_actions": list(BROKER_REQUIRED_ACTIONS),
              "per_doc_actions": list(BROKER_DOC_ACTIONS)})
        return EX_OK
    if cmd == "broker-preflight":
        pf = broker_preflight()
        _out(pf)
        # A missing/under-provisioned broker is a HELD dependency (exit 3) so the caller
        # STOPS provisioning early instead of dead-ending mid-run at S7/S8.
        return EX_OK if pf.get("ok") else EX_DEP
    raise ValidationError("no subcommand given; run with -h for usage.")


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return dispatch(args)
    except SystemExit:
        raise
    except AdapterError as exc:
        sys.stderr.write("[drive_adapter] %s: %s\n" % (type(exc).__name__, exc))
        return exc.exit_code
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[drive_adapter] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
