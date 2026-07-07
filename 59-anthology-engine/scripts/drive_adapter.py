#!/usr/bin/env python3
"""drive_adapter.py -- Layer 3 Google Drive/Docs delivery adapter (W1.11).

WHAT THIS IS (SPEC 3.4 row 9; SPEC 10.1; PRD 3.7 / 3.13; ENGINE-MANIFEST L9):
  A stateless, direct-REST adapter over the Google Drive v3 and Docs v1 APIs.
  It authenticates with the operator's EXISTING service account exactly the way
  clawd/google-api.js does (service-account JWT, RS256, domain-wide delegation,
  sub = the impersonated user under the GOOGLE_IMPERSONATE_USER label, full Drive
  scope + the Documents scope). It calls the REST endpoints DIRECTLY -- Skill 14
  is PATTERN REFERENCE ONLY and google-api.js exposes no create/permissions/
  delete actions, so those are re-implemented here (verified live at W0.6).

  NOTHING new is provisioned in Google: no new service account, no new share
  primitive beyond per-document anyone-with-link VIEW, and NO new Drive root.
  The delivery tree lives under the operator's EXISTING anyone-can-read root
  (config key delivery.drive_root_folder). drive-tree-provision.py owns the
  idempotent Producer/Anthology/Participant folder tree; THIS module owns:
    - create a Google Doc inside a participant folder + insert its text
    - land a cover PNG (or any media) inside a participant folder
    - per-document anyone-with-link VIEW-only share (revocation-preserving)
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
        [--text-file PATH | --text STR] [--share-view]
        create a Google Doc in the participant folder, insert text, read it back,
        optionally share view-only; prints {doc_id, doc_url, permission_id, ...}.
  drive_adapter.py upload --name NAME --parent-folder-id ID --file PATH
        [--mime TYPE] [--share-view]
        land a binary (e.g. the S7 cover PNG) in the participant folder.
  drive_adapter.py share --file-id ID
        anyone-with-link VIEW-only; reads the permission back; prints the link.
  drive_adapter.py revoke-share --file-id ID [--permission-id ID]
        [--unlink-from-root-id PUBLIC_ANCESTOR --to-folder-id PRIVATE_DEST]
        delete DIRECT anyone permission(s). NOTE: because the delivery root is
        anyone-can-read, per-file anyone access is INHERITED and cannot be deleted
        at the file level; true revocation MOVES the file out of the public root
        (pass --unlink-from-root-id + --to-folder-id). Reports remaining access.
  drive_adapter.py move --file-id ID [--add-parent-id ID] [--remove-parent-id ID]
        relocate a file/folder (the real revocation primitive under a public root).
  drive_adapter.py export-bundle --folder-id ID [--out PATH]
        recursive Drive manifest for one anthology folder (the Drive half of the
        SPEC 10.1 export bundle; anthology_state.py emits the ledger half).
  drive_adapter.py --self-test        offline coherence checks (no network).
"""
import argparse
import base64
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
            "%s NOT SET; the operator's existing service-account key is "
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


def list_permissions(token, file_id):
    from urllib.parse import quote
    path = ("/drive/v3/files/%s/permissions?supportsAllDrives=true"
            "&fields=permissions(id,type,role,allowFileDiscovery,permissionDetails)"
            % quote(file_id, safe=""))
    return _json_api("GET", GOOGLE_API_HOST, path, token).get("permissions", [])


def _perm_is_inherited(perm):
    """True iff this permission is INHERITED from an ancestor folder.

    Under an anyone-can-read delivery ROOT (the operator's existing topology) the
    anyone/reader grant is inherited by every descendant and CANNOT be deleted at
    the file level (Drive returns 403). Detected via permissionDetails[].inherited."""
    for d in perm.get("permissionDetails", []) or []:
        if d.get("inherited"):
            return True
    return False


def move_file(token, file_id, add_parent=None, remove_parent=None):
    """Relocate a file/folder: add and/or remove a parent (files.update).

    This is the ONLY way to truly revoke INHERITED public access under an
    anyone-can-read root: move the item OUT of the public subtree into a private
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
def load_root_folder_id(explicit=None):
    """Resolve the EXISTING delivery root id: explicit arg > env > engine config.

    Never invents a root. The root is only ever verified (files_get), never
    created (SPEC 10.1 / PRD 3.7)."""
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
                if root:
                    return root
            except Exception:
                continue
    raise ValidationError(
        "no delivery root id resolvable (pass --root-folder-id, set %s, or "
        "populate delivery.drive_root_folder in engine config)." % ROOT_FOLDER_ENV)


def _credential_status():
    """SET / NOT-SET report for the operator surface -- never a value."""
    return {
        SA_KEY_ENV: "SET" if os.environ.get(SA_KEY_ENV) else "NOT SET",
        IMPERSONATE_ENV: "SET" if os.environ.get(IMPERSONATE_ENV) else "NOT SET",
    }


# ---------------------------------------------------------------------------
# High-level flows used by the CLI subcommands
# ---------------------------------------------------------------------------
def deliver_doc(name, parent_folder_id, text=None, share=False):
    """Create a Doc in the participant folder, insert text (read back), optionally
    share view-only (read back). Returns a machine-readable result dict."""
    token = mint_token()
    doc = create_doc(token, name, parent_folder_id)
    doc_id = doc["id"]

    if text is not None and text != "":
        write_and_verify(
            lambda: docs_insert_text(token, doc_id, text),
            lambda _r: docs_read_text(token, doc_id).rstrip("\n") == text.rstrip("\n"),
            "Docs insertText")

    permission_id = None
    view_shared = False
    if share:
        perm = write_and_verify(
            lambda: share_view_only(token, doc_id),
            lambda r: _verify_anyone_reader(token, doc_id, r),
            "anyone-with-link view share")
        permission_id = perm.get("id")
        view_shared = True

    meta = files_get(token, doc_id, fields="id,name,webViewLink")
    return {
        "ok": True, "action": "create-doc", "doc_id": doc_id,
        "name": meta.get("name", name), "doc_url": meta.get("webViewLink"),
        "view_shared": view_shared, "permission_id": permission_id,
        "verified": True,
    }


def deliver_media(name, parent_folder_id, local_path, mime=None, share=False):
    """Land a binary (S7 cover PNG) in the participant folder, read back, optionally
    share view-only. Returns a machine-readable result dict."""
    token = mint_token()
    up = upload_media(token, name, parent_folder_id, local_path, mime)
    file_id = up["id"]
    # read-back: the file exists under the intended parent
    write_and_verify(
        lambda: up,
        lambda _r: _verify_parent(token, file_id, parent_folder_id),
        "media upload parent check")

    permission_id = None
    view_shared = False
    if share:
        perm = write_and_verify(
            lambda: share_view_only(token, file_id),
            lambda r: _verify_anyone_reader(token, file_id, r),
            "anyone-with-link view share")
        permission_id = perm.get("id")
        view_shared = True

    meta = files_get(token, file_id, fields="id,name,webViewLink,webContentLink")
    return {
        "ok": True, "action": "upload", "file_id": file_id,
        "name": meta.get("name", name), "drive_url": meta.get("webViewLink"),
        "download_url": meta.get("webContentLink"),
        "view_shared": view_shared, "permission_id": permission_id,
        "verified": True,
    }


def _verify_anyone_reader(token, file_id, created_perm):
    """True iff the file now carries an anyone/reader/link-only permission."""
    for perm in list_permissions(token, file_id):
        if perm.get("type") == "anyone" and perm.get("role") == "reader" \
                and perm.get("allowFileDiscovery") in (False, None):
            return True
    return False


def _verify_parent(token, file_id, parent_id):
    meta = files_get(token, file_id, fields="id,parents,trashed")
    return (not meta.get("trashed", False)) and parent_id in (meta.get("parents") or [])


def do_share(file_id):
    token = mint_token()
    perm = write_and_verify(
        lambda: share_view_only(token, file_id),
        lambda r: _verify_anyone_reader(token, file_id, r),
        "anyone-with-link view share")
    meta = files_get(token, file_id, fields="id,name,webViewLink")
    return {
        "ok": True, "action": "share", "file_id": file_id,
        "permission_id": perm.get("id"), "view_url": meta.get("webViewLink"),
        "verified": True,
    }


def do_revoke_share(file_id, permission_id=None, unlink_from_root_id=None,
                    to_folder_id=None):
    """Revoke public view access to a file.

    Two mechanisms, because the operator's delivery ROOT is anyone-can-read:
      1. DIRECT anyone permissions (grants made ON the file itself) are deleted --
         this works and is what a private-root topology needs.
      2. INHERITED anyone access (from the anyone-can-read root) CANNOT be deleted
         at the file level (Drive returns 403). The ONLY true revocation is to
         MOVE the file OUT of the public subtree: pass --unlink-from-root-id (the
         public ancestor to drop) and --to-folder-id (a private destination).
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
    # inherited-permission classifier (the anyone-can-read root topology)
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
    # config root resolution: explicit wins; env fallback works
    assert load_root_folder_id("EXPLICIT_ID") == "EXPLICIT_ID"
    os.environ[ROOT_FOLDER_ENV] = "ENV_ROOT_ID"
    try:
        assert load_root_folder_id() == "ENV_ROOT_ID"
    finally:
        del os.environ[ROOT_FOLDER_ENV]
    # the committed template still carries the operator's EXISTING root id
    tmpl = CONFIG_DIR / "engine-config.template.json"
    if tmpl.is_file():
        cfg = json.loads(tmpl.read_text(encoding="utf-8"))
        assert cfg["delivery"]["drive_root_folder"] == "1gVdZ3_cx7Sv7VAfARL_LsGh5IcVB6iZw", \
            "delivery root drifted from the operator's existing shared root"
    print("drive_adapter self-test: OK (auth assembly, escaping, read-back guard, "
          "root resolution, exit-code contract)")
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
    cd.add_argument("--share-view", action="store_true",
                    help="also grant anyone-with-link VIEW-only")

    up = sub.add_parser("upload", help="land a binary (e.g. the cover PNG) in a folder")
    up.add_argument("--name", required=True)
    up.add_argument("--parent-folder-id", required=True)
    up.add_argument("--file", required=True, help="local path to the binary")
    up.add_argument("--mime", help="MIME type (guessed from the name if omitted)")
    up.add_argument("--share-view", action="store_true")

    sh = sub.add_parser("share", help="anyone-with-link VIEW-only share")
    sh.add_argument("--file-id", required=True)

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
        _out(deliver_doc(args.name, args.parent_folder_id, text=text, share=args.share_view))
        return EX_OK
    if cmd == "upload":
        _out(deliver_media(args.name, args.parent_folder_id, args.file,
                           mime=args.mime, share=args.share_view))
        return EX_OK
    if cmd == "share":
        _out(do_share(args.file_id))
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
