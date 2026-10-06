#!/usr/bin/env python3
"""render_documents.py - Podcast Production Engine, Step 12 (DOCUMENTS).

Two deliverables per episode:
  1. Episode Package - rich and fully rendered, with NO font below 12 point.
  2. Speech Script  - clean text only.

Destination is detected in priority order: Google first, then Notion, then
plain text as the last resort. Detection is by tooling and credential PRESENCE
only; this script reports SET or NOT SET and never prints a secret value.

This renderer is deterministic and pure standard library. It calls NO model and
NO MCP tool. It renders the two artifacts to disk and emits a machine-readable
destination action plan.

DELIVERY IS A TWO-TIER CHAIN, performed by this renderer:

  Tier 1  Google Drive, through the client's own Skill 14 Google Workspace
          credentials. Each rendered document is uploaded as a Google Doc, the
          sharing the plan describes is applied, every executed intent is stamped
          performed:true with its file id and link, and the links are recorded
          under plan["links"] so Steps 16 and 17 reference real documents.
  Tier 2  The client's OWN Notion workspace, tried when Skill 14 is not configured
          on this box or the Drive call delivered nothing. Nearly every client box
          already has Notion connected. One "Podcast Episodes" parent page per
          client, then one page per episode, created idempotently: re-running
          Step 12 for the same episode replaces that page's blocks and never
          duplicates it. The Notion API cannot upload a file, so the published
          audio from Step 15 is LINKED, never uploaded.
  Tier 3  Today's intent-only record plus ONE log line naming both prerequisites.

Drive speaks the Drive REST API directly with the client's own service account and
NEVER invokes the gws binary, which self-wipes its credential store when it runs
headless. Notion follows the repo's existing convention (37-zhc-closeout and the
Skill 38 client-doc standard), including the client-ownership rule: the page lives
in the CLIENT's Notion under the CLIENT's token, and the agency token and agency
parent page are refused. No tier can fail the episode or change this script's exit
code. --no-deliver forces the intent-only path.

Google sharing rule (Google destination only): anyone with the link can edit,
expressed as Drive permission role=writer, type=anyone. Notion has no identical
concept; its plan carries a share-to-web note instead.

Doctrine honored: silence (operator and agent output only, never a client
message), secrecy (labels and SET or NOT SET only, never a value), no content
model call anywhere in this file, zero em dash characters, and no triple
backtick fences in any produced output.

Subcommands:
  render        --manifest <json> --out-dir <dir> [--force-destination X]
                [--speech-script-file <f>] [--no-deliver]
  detect        [--json]
  check         --package <html.file>         (font-floor 12pt self-check)
  check-script  --script <txt.file>           (clean-text sanity guard)

Exit codes: 0 ok; 2 bad arguments or input; 3 render or validation failure.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

FONT_FLOOR_PT = 12
TITLE_FONT_PT = 26
SECTION_FONT_PT = 18
BODY_FONT_PT = 14
META_FONT_PT = 12  # smallest element used; equals the floor, never below it


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def slugify(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text[:80] or "podcast"


# ---------------------------------------------------------------------------
# Destination detection (presence only; never a value)
# ---------------------------------------------------------------------------

def _env_set(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def detect_destination() -> dict:
    """Return a detection report and the chosen destination.

    Google wins when the gws CLI is present OR a Google Workspace signal is set.
    Notion wins when a Notion token AND a parent page are both set.
    Otherwise plain text (local) is the last resort. Values are never read;
    only presence (SET or NOT SET) is reported.
    """
    gws_on_path = shutil.which("gws") is not None
    google_env = [n for n in (
        "GOOGLE_WORKSPACE_ENABLED", "GWS_ACCOUNT",
        "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_WORKSPACE_TOKEN",
    ) if _env_set(n)]
    google_ok = gws_on_path or bool(google_env)

    notion_token = next((n for n in ("NOTION_API_KEY", "NOTION_TOKEN") if _env_set(n)), None)
    notion_parent = next((n for n in ("NOTION_PARENT_PAGE_ID", "NOTION_PODCAST_PARENT") if _env_set(n)), None)
    notion_ok = bool(notion_token) and bool(notion_parent)

    if google_ok:
        chosen = "google"
    elif notion_ok:
        chosen = "notion"
    else:
        chosen = "local"

    return {
        "chosen": chosen,
        "google": {
            "available": google_ok,
            "gws_cli": "SET" if gws_on_path else "NOT SET",
            "env_signals": {n: "SET" for n in google_env} or {"GOOGLE_WORKSPACE": "NOT SET"},
        },
        "notion": {
            "available": notion_ok,
            "token": ("SET (%s)" % notion_token) if notion_token else "NOT SET",
            "parent_page": ("SET (%s)" % notion_parent) if notion_parent else "NOT SET",
        },
        "local": {"available": True, "note": "plain-text last resort is always available"},
    }


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------

def load_manifest(path: str, speech_file: str | None) -> dict:
    p = Path(path)
    if not p.is_file():
        raise ValueError("manifest not found: %s" % path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("manifest is not valid JSON: %s" % exc) from exc
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")

    if not str(data.get("title", "")).strip():
        raise ValueError("manifest.title is required")

    # Resolve the speech script from a file override, an inline field, or a
    # path field. The Speech Script must exist; it is a required deliverable.
    script = ""
    if speech_file:
        sf = Path(speech_file)
        if not sf.is_file():
            raise ValueError("speech script file not found: %s" % speech_file)
        script = sf.read_text(encoding="utf-8")
    elif isinstance(data.get("speech_script"), str) and data["speech_script"].strip():
        script = data["speech_script"]
    elif str(data.get("speech_script_file", "")).strip():
        sf = Path(data["speech_script_file"])
        if not sf.is_file():
            raise ValueError("manifest.speech_script_file not found: %s" % data["speech_script_file"])
        script = sf.read_text(encoding="utf-8")
    else:
        raise ValueError("no speech script supplied (speech_script, speech_script_file, or --speech-script-file)")

    data["_speech_script_text"] = script.strip("\n")
    return data


# ---------------------------------------------------------------------------
# Episode Package HTML renderer (font floor 12pt, enforced by construction)
# ---------------------------------------------------------------------------

def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _multiline(value: str) -> str:
    return "<br>".join(_esc(line) for line in str(value).split("\n"))


def render_package_html(m: dict) -> str:
    title = _esc(m.get("title"))
    client = m.get("client", "")
    style = m.get("style", "")
    mode = m.get("mode", "")
    guest = m.get("guest_first_name", "")
    thesis = m.get("thesis", "")
    description = m.get("description", "")
    runtime = m.get("runtime_minutes")
    word_count = m.get("word_count")
    research = m.get("research") or {}
    cover_path = m.get("cover_path", "")
    podbean_url = m.get("podbean_url", "")

    meta_bits = []
    if style:
        meta_bits.append("Style: %s" % _esc(style))
    if mode:
        meta_bits.append("Mode: %s" % _esc(mode))
    if guest:
        meta_bits.append("Guest: %s" % _esc(guest))
    if runtime is not None:
        meta_bits.append("Runtime: %s minutes" % _esc(runtime))
    if word_count is not None:
        meta_bits.append("Spoken words: %s" % _esc(word_count))
    meta_line = " &middot; ".join(meta_bits)

    def section(heading: str, inner: str) -> str:
        if not inner:
            return ""
        return "  <section>\n    <h2>%s</h2>\n%s\n  </section>\n" % (_esc(heading), inner)

    def list_block(items: list) -> str:
        rows = "".join("      <li>%s</li>\n" % _multiline(i) for i in items if str(i).strip())
        return "    <ul>\n%s    </ul>" % rows if rows else ""

    body_parts: list[str] = []
    if thesis:
        body_parts.append(section("Thesis", "    <p>%s</p>" % _multiline(thesis)))
    if description:
        body_parts.append(section("Show notes", "    <p>%s</p>" % _multiline(description)))

    takeaways = research.get("key_takeaways") or []
    if takeaways:
        body_parts.append(section("Key takeaways", list_block(takeaways)))

    statements = research.get("power_statements") or []
    if statements:
        quotes = "".join(
            "    <blockquote>%s</blockquote>\n" % _multiline(s) for s in statements if str(s).strip()
        )
        body_parts.append(section("Power statements", quotes.rstrip("\n")))

    studies = research.get("case_studies") or []
    if studies:
        rows = []
        for s in studies:
            if isinstance(s, dict):
                st = _esc(s.get("title", "Case study"))
                sm = _multiline(s.get("summary", ""))
                src = s.get("source", "")
                src_html = ""
                if src:
                    if str(src).startswith("http"):
                        src_html = '<div class="src">Source: <a href="%s">%s</a></div>' % (_esc(src), _esc(src))
                    else:
                        src_html = '<div class="src">Source: %s</div>' % _esc(src)
                rows.append("    <div class=\"study\">\n      <h3>%s</h3>\n      <p>%s</p>\n      %s\n    </div>" % (st, sm, src_html))
            else:
                rows.append("    <div class=\"study\"><p>%s</p></div>" % _multiline(s))
        body_parts.append(section("Case studies", "\n".join(rows)))

    findings = research.get("findings") or []
    if findings:
        body_parts.append(section("Supporting findings", list_block(findings)))

    sources = research.get("sources") or []
    if sources:
        rows = ""
        for s in sources:
            if str(s).startswith("http"):
                rows += '      <li><a href="%s">%s</a></li>\n' % (_esc(s), _esc(s))
            else:
                rows += "      <li>%s</li>\n" % _esc(s)
        body_parts.append(section("Sources", "    <ol>\n%s    </ol>" % rows))

    links_rows = ""
    if podbean_url:
        links_rows += '      <li>Episode: <a href="%s">%s</a></li>\n' % (_esc(podbean_url), _esc(podbean_url))
    if cover_path:
        links_rows += "      <li>Cover art file: %s</li>\n" % _esc(cover_path)
    if links_rows:
        body_parts.append(section("Assets", "    <ul>\n%s    </ul>" % links_rows))

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subtitle = _esc(client) if client else ""

    # Every font-size below is expressed in points and is at or above the 12pt
    # floor. The check subcommand re-verifies this on the produced file.
    css = "\n".join([
        "    :root { color-scheme: light dark; }",
        "    body { font-family: Georgia, 'Times New Roman', serif; font-size: %dpt; line-height: 1.55;" % BODY_FONT_PT,
        "      max-width: 46rem; margin: 2rem auto; padding: 0 1.25rem; color: #1a1a1a; background: #ffffff; }",
        "    h1 { font-size: %dpt; line-height: 1.2; margin: 0 0 0.25rem; }" % TITLE_FONT_PT,
        "    h2 { font-size: %dpt; margin: 1.6rem 0 0.5rem; border-bottom: 1px solid #ddd; padding-bottom: 0.2rem; }" % SECTION_FONT_PT,
        "    h3 { font-size: %dpt; margin: 1rem 0 0.3rem; }" % BODY_FONT_PT,
        "    p, li, blockquote { font-size: %dpt; }" % BODY_FONT_PT,
        "    .meta, .src, footer { font-size: %dpt; color: #555; }" % META_FONT_PT,
        "    blockquote { border-left: 3px solid #888; margin: 0.6rem 0; padding: 0.2rem 0 0.2rem 1rem; font-style: italic; }",
        "    .study { margin: 0.8rem 0 1.1rem; }",
        "    a { color: #0b5cad; }",
        "    footer { margin-top: 2.4rem; border-top: 1px solid #ddd; padding-top: 0.6rem; }",
        "    @media (prefers-color-scheme: dark) {",
        "      body { color: #ececec; background: #14161a; }",
        "      h2 { border-bottom-color: #333; } .meta, .src, footer { color: #b3b3b3; }",
        "      footer { border-top-color: #333; } a { color: #6db3ff; }",
        "    }",
    ])

    head = "\n".join([
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8">',
        '  <meta name="viewport" content="width=device-width, initial-scale=1">',
        "  <title>%s - Episode Package</title>" % title,
        "  <style>",
        css,
        "  </style>",
        "</head>",
        "<body>",
    ])

    header = "  <header>\n    <h1>%s</h1>\n" % title
    if subtitle:
        header += '    <div class="meta">%s</div>\n' % subtitle
    if meta_line:
        header += '    <div class="meta">%s</div>\n' % meta_line
    header += "  </header>\n"

    footer = (
        "  <footer>Episode Package rendered %s. The Speech Script is delivered as a "
        "separate clean-text file. Font floor: %dpt.</footer>\n" % (_esc(generated), FONT_FLOOR_PT)
    )

    return head + "\n" + header + "\n" + "".join(bp for bp in body_parts if bp) + "\n" + footer + "</body>\n</html>\n"


# ---------------------------------------------------------------------------
# Destination action plan
# ---------------------------------------------------------------------------

def build_plan(m: dict, detection: dict, destination: str, forced: bool,
               package_path: Path, speech_path: Path) -> dict:
    title = str(m.get("title"))
    ready = True
    actions: list[dict] = []
    sharing: dict = {}

    if destination == "google":
        ready = detection["google"]["available"]
        pkg_name = "%s - Episode Package" % title
        spk_name = "%s - Speech Script" % title
        actions = [
            {"action": "drive.upload_convert", "source": str(package_path),
             "mime_import": "text/html",
             "mime_target": "application/vnd.google-apps.document",
             "name": pkg_name, "capture": "package_doc_id",
             "cli_hint": "gws drive files upload (LIVE-VERIFY exact flags against the client gws CLI)"},
            {"action": "drive.upload_convert", "source": str(speech_path),
             "mime_import": "text/plain",
             "mime_target": "application/vnd.google-apps.document",
             "name": spk_name, "capture": "speech_doc_id",
             "cli_hint": "gws drive files upload (LIVE-VERIFY exact flags against the client gws CLI)"},
            {"action": "drive.set_permission", "target_ref": "package_doc_id",
             "role": "writer", "type": "anyone",
             "meaning": "anyone with the link can edit"},
            {"action": "drive.set_permission", "target_ref": "speech_doc_id",
             "role": "writer", "type": "anyone",
             "meaning": "anyone with the link can edit"},
            {"action": "capture_link", "from": "package_doc_id", "into": "links.package_doc"},
            {"action": "capture_link", "from": "speech_doc_id", "into": "links.speech_doc"},
        ]
        sharing = {"scope": "anyone", "role": "writer",
                   "human": "anyone with the link can edit"}

    elif destination == "notion":
        ready = detection["notion"]["available"]
        actions = [
            {"action": "notion.create_page", "parent": "NOTION_PARENT_PAGE_ID",
             "title": "%s - Episode Package" % title,
             "content_source": str(package_path), "capture": "package_page_url",
             "note": "render the package sections as Notion blocks via REST, never MCP"},
            {"action": "notion.create_page", "parent": "NOTION_PARENT_PAGE_ID",
             "title": "%s - Speech Script" % title,
             "content_source": str(speech_path), "capture": "speech_page_url",
             "note": "clean text only"},
            {"action": "capture_link", "from": "package_page_url", "into": "links.package_doc"},
            {"action": "capture_link", "from": "speech_page_url", "into": "links.speech_doc"},
        ]
        sharing = {"scope": "notion-share-to-web",
                   "note": "the anyone-with-the-link-can-edit rule is Google-specific; "
                           "for Notion, share per the client's Notion policy"}

    else:  # local
        actions = [{"action": "none",
                    "note": "plain-text last resort; the HTML package and the TXT speech "
                            "script on disk are the deliverables"}]
        sharing = {"scope": "local", "note": "no external sharing"}

    return {
        "step": 12,
        "destination": destination,
        "forced": forced,
        "ready": ready,
        "detection": detection,
        "artifacts": {
            "episode_package_html": str(package_path),
            "speech_script_txt": str(speech_path),
        },
        "font_floor_pt": FONT_FLOOR_PT,
        "data_plane": "agent-own-turn REST or gws; sub-agents get no MCP",
        "actions": actions,
        "sharing": sharing,
    }


# ---------------------------------------------------------------------------
# Drive delivery (performed here, with the client's OWN Skill 14 credentials)
# ---------------------------------------------------------------------------
# Step 12 used to emit drive.upload_convert and drive.set_permission as ACTION
# INTENTS that nothing ever executed, so a fully provisioned client box still
# logged Drive delivery as not provisioned. The intents stay (they remain the
# machine-readable record of what Step 12 owes the episode), but when the box
# actually holds Google Workspace credentials this module now PERFORMS them and
# stamps each intent performed:true with the resulting file id and link.
#
# CREDENTIALS. Resolution follows Skill 14 (14-google-workspace-integration) and
# invents no new names. Skill 14 documents the service-account plus domain-wide
# delegation path as the one that succeeds for Drive upload: point
# GOOGLE_APPLICATION_CREDENTIALS (or Skill 14 Section 3 Option B's
# GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE) at the gcp-service-account.json, and
# name the impersonated Workspace user in GCP_IMPERSONATE_USER. Skill 14's
# documented default key location is used as the last resort. The destination
# folder is optional and comes from PODCAST_DRIVE_ROOT_FOLDER_ID; with no folder
# the documents land in the impersonated user's own My Drive root.
#
# gws SAFETY. This module speaks the Drive REST API directly and NEVER invokes
# the gws binary, not even to test for credentials. A bare gws call in a headless
# shell cannot unlock its keyring and gws's own failure mode then rewrites the
# default credential store to credential_source "none", wiping every account on
# the box. Step 12 runs headless by definition, so shelling out to gws is
# forbidden here. Presence is decided from env names and a readable key file.
#
# SCOPE. The full Drive scope is the only one that works for this grant; the
# narrow drive.file and drive.readonly scopes are rejected by domain-wide
# delegation with unauthorized_client.
#
# FAIL SOFT. No credential, no key file, an unreachable API, or a Drive error
# never fails the episode. The renderer records what happened and returns the
# same exit code it would have returned with delivery switched off.
#
# SECRECY. Credentials are reported by LABEL and SET or NOT SET only. The key
# file contents, the private key, the minted token, and the impersonated user's
# address are never printed.

# Skill 14 credential contract. Every name below is Skill 14's own.
SA_KEY_ENVS = ("GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE")
SA_DEFAULT_PATH = "~/clawd/secrets/gcp-service-account.json"
IMPERSONATE_ENVS = ("GCP_IMPERSONATE_USER", "GWS_ACCOUNT")

# Podcast-owned, optional: the Drive folder the episode documents land in.
DRIVE_ROOT_FOLDER_ENV = "PODCAST_DRIVE_ROOT_FOLDER_ID"

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
GOOGLE_API_HOST = "www.googleapis.com"
OAUTH_HOST = "oauth2.googleapis.com"
MIME_GOOGLE_DOC = "application/vnd.google-apps.document"

SKIP_LINE = ("drive delivery skipped: Skill 14 Google Workspace credentials not "
             "configured on this box (see 14-google-workspace-integration/INSTALL.md)")

_HTTP_TIMEOUT = 60
_HTTP_RETRIES = 3
_HTTP_BACKOFF = 1.5


class DriveDeliveryError(Exception):
    """A Drive delivery failure. Recorded on the plan; never fails the episode."""


def _first_set_env(names: tuple) -> str | None:
    return next((n for n in names if _env_set(n)), None)


def resolve_drive_credentials() -> dict:
    """Resolve the client's Skill 14 Drive credentials, by label only.

    Returns a report dict carrying `resolved`. Resolution needs BOTH a readable
    service-account key file (client_email plus private_key) AND an impersonation
    subject. Anything less is NOT configured and Step 12 stays intent-only.
    """
    key_env = _first_set_env(SA_KEY_ENVS)
    if key_env:
        key_path = Path(os.path.expanduser(os.environ[key_env].strip()))
        key_source = key_env
    else:
        key_path = Path(os.path.expanduser(SA_DEFAULT_PATH))
        key_source = "Skill 14 default path"

    subject_env = _first_set_env(IMPERSONATE_ENVS)
    folder_env = DRIVE_ROOT_FOLDER_ENV if _env_set(DRIVE_ROOT_FOLDER_ENV) else None

    report = {
        "resolved": False,
        "reason": "",
        "service_account_key": "NOT SET",
        "impersonated_user": "NOT SET",
        "root_folder": "NOT SET",
        "scope": DRIVE_SCOPE,
        "transport": "drive REST v3 (the gws binary is never invoked)",
    }
    if folder_env:
        report["root_folder"] = "SET (%s)" % folder_env

    if not key_path.is_file():
        report["reason"] = ("no readable service-account key file (%s)" % key_source)
        return report
    try:
        sa = json.loads(key_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - surface the class, never the contents
        report["reason"] = ("service-account key file is not valid JSON (%s)"
                            % type(exc).__name__)
        return report
    if not isinstance(sa, dict) or not sa.get("client_email") or not sa.get("private_key"):
        report["reason"] = "service-account key file is missing client_email or private_key"
        return report
    report["service_account_key"] = "SET (%s)" % key_source

    if not subject_env:
        report["reason"] = ("no impersonated Workspace user (%s)"
                            % " or ".join(IMPERSONATE_ENVS))
        return report
    report["impersonated_user"] = "SET (%s)" % subject_env

    report["resolved"] = True
    report["_sa"] = sa
    report["_subject"] = os.environ[subject_env].strip()
    report["_root_folder_id"] = os.environ[DRIVE_ROOT_FOLDER_ENV].strip() if folder_env else None
    return report


def public_credential_report(creds: dict) -> dict:
    """The credential report with every private field stripped, safe to serialize."""
    return {k: v for k, v in creds.items() if not k.startswith("_")}


def _b64u(raw: object) -> str:
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _rsa_sign_sha256(signing_input: bytes, private_key_pem: str) -> bytes:
    """RS256-sign the JWT input. Prefers the cryptography library, else openssl.

    The private key never lands in argv; the openssl fallback writes it to a
    0600 temp file that is unlinked immediately.
    """
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        key = serialization.load_pem_private_key(
            private_key_pem.encode("utf-8"), password=None)
        return key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    except ImportError:
        pass
    import subprocess
    import tempfile
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False)
    try:
        os.chmod(tmp.name, 0o600)
        tmp.write(private_key_pem)
        tmp.close()
        proc = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", tmp.name, "-binary"],
            input=signing_input, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise DriveDeliveryError(
                "RS256 signing failed: neither the cryptography library nor the "
                "openssl CLI could sign the assertion")
        return proc.stdout
    except FileNotFoundError:
        raise DriveDeliveryError(
            "RS256 signing failed: neither the cryptography library nor the "
            "openssl CLI is available")
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _https(method: str, host: str, path: str, headers: dict, body=None):
    """One HTTPS round trip with a bounded retry on genuinely transient states."""
    import http.client
    import socket
    import time
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
        if status in (429, 500, 502, 503, 504) and attempt < _HTTP_RETRIES - 1:
            time.sleep(_HTTP_BACKOFF ** attempt)
            last = None
            continue
        return status, raw
    raise DriveDeliveryError(
        "Google API host %s unreachable after %d attempts (%s)"
        % (host, _HTTP_RETRIES, type(last).__name__ if last else "transient"))


def _api_error_detail(raw: bytes) -> str:
    try:
        parsed = json.loads(raw)
    except Exception:
        return ""
    if not isinstance(parsed, dict):
        return ""
    err = parsed.get("error")
    if isinstance(err, dict):
        reasons = [str(d.get("reason", "")) for d in err.get("errors", [])
                   if isinstance(d, dict)]
        message = str(err.get("message", ""))
        joined = " ".join([r for r in reasons if r] + ([message] if message else ""))
        return joined[:180]
    return ""


class DriveTransport:
    """Direct Drive v3 REST over the Skill 14 service account and DWD subject.

    The gws binary is never invoked. Tokens are minted in process, cached for the
    process lifetime, and never printed.
    """

    def __init__(self, creds: dict) -> None:
        self._sa = creds["_sa"]
        self._subject = creds["_subject"]
        self._token = None
        self._token_expiry = 0

    def _access_token(self) -> str:
        import time
        now = int(time.time())
        if self._token and self._token_expiry - 60 > now:
            return self._token
        header = _b64u(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")))
        payload = _b64u(json.dumps({
            "iss": self._sa["client_email"],
            "sub": self._subject,
            "aud": "https://%s/token" % OAUTH_HOST,
            "iat": now,
            "exp": now + 3600,
            "scope": DRIVE_SCOPE,
        }, separators=(",", ":")))
        signing_input = ("%s.%s" % (header, payload)).encode("ascii")
        signature = _b64u(_rsa_sign_sha256(signing_input, self._sa["private_key"]))
        assertion = "%s.%s.%s" % (header, payload, signature)
        body = ("grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer"
                "&assertion=" + assertion).encode("ascii")
        status, raw = _https(
            "POST", OAUTH_HOST, "/token",
            {"Content-Type": "application/x-www-form-urlencoded"}, body)
        if status != 200:
            raise DriveDeliveryError(
                "token endpoint returned HTTP %s; confirm domain-wide delegation "
                "authorizes the full Drive scope (no secret shown)" % status)
        try:
            token = json.loads(raw)["access_token"]
        except Exception:
            raise DriveDeliveryError("token endpoint response carried no access_token")
        self._token = token
        self._token_expiry = now + 3600
        return token

    def upload_convert(self, source: str, name: str, mime_import: str,
                       mime_target: str, parent_folder_id: str | None = None) -> dict:
        """Multipart-upload one rendered file, converting it to a Google Doc.

        Drive performs the conversion when the metadata mimeType is a Google type
        and the media part carries the source type. Returns {id, link}.
        """
        import uuid
        src = Path(source)
        if not src.is_file():
            raise DriveDeliveryError("upload source not found: %s" % source)
        data = src.read_bytes()
        metadata: dict = {"name": name}
        if mime_target:
            metadata["mimeType"] = mime_target
        if parent_folder_id:
            metadata["parents"] = [parent_folder_id]
        boundary = "podcast-step12-%s" % uuid.uuid4().hex
        pre = ("--%s\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n%s\r\n"
               "--%s\r\nContent-Type: %s\r\n\r\n"
               % (boundary, json.dumps(metadata), boundary, mime_import)).encode("utf-8")
        post = ("\r\n--%s--" % boundary).encode("utf-8")
        headers = {
            "Authorization": "Bearer %s" % self._access_token(),
            "Content-Type": "multipart/related; boundary=%s" % boundary,
        }
        path = ("/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true"
                "&fields=id,name,mimeType,webViewLink")
        status, raw = _https("POST", GOOGLE_API_HOST, path, headers, pre + data + post)
        if status not in (200, 201):
            raise DriveDeliveryError(
                "Drive upload returned HTTP %s. %s" % (status, _api_error_detail(raw)))
        try:
            parsed = json.loads(raw)
        except Exception:
            raise DriveDeliveryError("Drive upload response was not JSON")
        file_id = parsed.get("id")
        if not file_id:
            raise DriveDeliveryError("Drive upload response carried no file id")
        return {"id": file_id,
                "link": parsed.get("webViewLink")
                or "https://docs.google.com/document/d/%s/edit" % file_id}

    def set_permission(self, file_id: str, role: str, type_: str) -> dict:
        """Grant the link-only permission the intent describes.

        An anyone-with-link grant inherited from the parent folder cannot be set
        again at the file level; Drive answers 403 cannotModifyInheritedPermission
        and the document already carries the access, so that answer is reported as
        inherited rather than treated as a failure.
        """
        from urllib.parse import quote
        path = ("/drive/v3/files/%s/permissions?supportsAllDrives=true"
                "&fields=id,type,role" % quote(str(file_id), safe=""))
        headers = {"Authorization": "Bearer %s" % self._access_token(),
                   "Content-Type": "application/json"}
        body = json.dumps({"role": role, "type": type_,
                           "allowFileDiscovery": False}).encode("utf-8")
        status, raw = _https("POST", GOOGLE_API_HOST, path, headers, body)
        if status in (200, 201):
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {}
            return {"permission_id": parsed.get("id"), "inherited": False}
        detail = _api_error_detail(raw)
        if status == 403 and "cannotModifyInheritedPermission" in detail:
            return {"permission_id": None, "inherited": True}
        raise DriveDeliveryError(
            "Drive permission returned HTTP %s. %s" % (status, detail))


def _make_transport(creds: dict) -> DriveTransport:
    """Transport factory. Tests replace this to exercise delivery without a network."""
    return DriveTransport(creds)


def perform_drive_delivery(plan: dict, creds: dict) -> dict:
    """Execute the plan's Drive intents in place. Never raises.

    Each executed intent is stamped performed:true and carries the id and link it
    produced. The captured links are written to plan["links"] so Steps 16 and 17
    (GHL completion) reference real documents instead of a promise. This function
    writes NO engine state: podcast_state.py remains the sole writer, and the
    documents plan file on disk is Step 12's own record of what it delivered.
    """
    delivery: dict = {
        "channel": "google_drive",
        "attempted": True,
        "performed": False,
        "status": "error",
        "credentials": public_credential_report(creds),
        "documents": {},
        "errors": [],
    }
    links: dict = plan.setdefault("links", {})
    captured: dict = {}
    root_folder_id = creds.get("_root_folder_id")

    try:
        transport = _make_transport(creds)
    except Exception as exc:  # noqa: BLE001
        delivery["errors"].append("transport unavailable: %s" % _safe_error(exc))
        return delivery

    for action in plan.get("actions", []):
        kind = action.get("action")
        try:
            if kind == "drive.upload_convert":
                result = transport.upload_convert(
                    source=action["source"],
                    name=action["name"],
                    mime_import=action.get("mime_import", "text/plain"),
                    mime_target=action.get("mime_target", MIME_GOOGLE_DOC),
                    parent_folder_id=root_folder_id,
                )
                capture = action.get("capture")
                if capture:
                    captured[capture] = result
                action["performed"] = True
                action["file_id"] = result["id"]
                action["link"] = result["link"]

            elif kind == "drive.set_permission":
                ref = action.get("target_ref")
                target = captured.get(ref)
                if not target:
                    raise DriveDeliveryError(
                        "permission target %s was never captured" % ref)
                result = transport.set_permission(
                    file_id=target["id"],
                    role=action.get("role", "writer"),
                    type_=action.get("type", "anyone"),
                )
                action["performed"] = True
                action["file_id"] = target["id"]
                action["permission_id"] = result.get("permission_id")
                action["inherited_permission"] = bool(result.get("inherited"))

            elif kind == "capture_link":
                ref = action.get("from")
                target = captured.get(ref)
                if not target:
                    raise DriveDeliveryError("link source %s was never captured" % ref)
                key = str(action.get("into", "")).split(".")[-1]
                if key:
                    links[key] = target["link"]
                    delivery["documents"][key] = {"file_id": target["id"],
                                                  "link": target["link"]}
                action["performed"] = True

        except Exception as exc:  # noqa: BLE001 - one intent failing never fails the episode
            action["performed"] = False
            action["error"] = _safe_error(exc)
            delivery["errors"].append("%s: %s" % (kind, _safe_error(exc)))

    delivery["performed"] = bool(delivery["documents"])
    if delivery["errors"]:
        delivery["status"] = "partial" if delivery["performed"] else "error"
    elif delivery["performed"]:
        delivery["status"] = "performed"
    else:
        # Credentials resolved but the plan carried no Drive intent to execute.
        delivery["status"] = "skipped"
        delivery["reason"] = "the plan carries no Google Drive action to perform"
    return delivery


def _safe_error(exc: Exception) -> str:
    """One-line error text with no secret and no newline."""
    text = str(exc) or type(exc).__name__
    return " ".join(text.split())[:200]


def record_drive_skip(plan: dict, creds: dict) -> dict:
    """Record the intent-only outcome when Skill 14 credentials are not configured."""
    return {
        "channel": "google_drive",
        "attempted": False,
        "performed": False,
        "status": "skipped",
        "reason": creds.get("reason", "credentials not configured"),
        "credentials": public_credential_report(creds),
        "documents": {},
        "errors": [],
    }


# ---------------------------------------------------------------------------
# Notion delivery (Tier 2, the client's OWN Notion workspace)
# ---------------------------------------------------------------------------
# Nearly every client box already has Notion connected, so Notion is the fallback
# when Google Workspace is not configured on this box or the Drive call fails.
# The convention here is the repo's existing one, not a new one:
#   37-zhc-closeout/scripts/ensure-notion-parent-page.sh  token + parent + guards
#   37-zhc-closeout/scripts/create-notion-closeout.sh     API version, block shapes,
#                                                         idempotent child lookup
#   38-conversational-ai-system/references/notion-client-doc-standard.md
#                                                         the client-doc standard
#
# CLIENT OWNERSHIP (binding). The page must live in the CLIENT's Notion, under the
# CLIENT's own token. Skill 37 refuses when the token equals ZHC_AGENCY_NOTION_TOKEN
# or the parent equals ZHC_AGENCY_NOTION_PARENT_PAGE_ID; this module refuses on the
# same two guards, and an explicit parent page is required because ownership is
# never inferred from a workspace-wide search.
#
# NO FILE UPLOAD. The Notion API cannot upload a file. The published audio from
# Step 15 is LINKED, never uploaded, and the rendered HTML and text artifacts stay
# on disk as the durable base.
#
# IDEMPOTENT. One "Podcast Episodes" parent page per client, created once, then one
# child page per episode keyed by the episode title. Re-running Step 12 for the same
# episode REPLACES that page's blocks; it never creates a second page.

# Skill 37 / Skill 38 Notion contract. NOTION_API_TOKEN is the repo's name; the two
# that Step 12 already documented are kept so an existing box does not regress.
NOTION_TOKEN_ENVS = ("NOTION_API_TOKEN", "NOTION_API_KEY", "NOTION_TOKEN")
NOTION_PARENT_ENVS = ("NOTION_PODCAST_PARENT", "NOTION_PARENT_PAGE_ID",
                      "NOTION_WORKSPACE_ROOT_ID")
NOTION_AGENCY_TOKEN_ENV = "ZHC_AGENCY_NOTION_TOKEN"
NOTION_AGENCY_PARENT_ENV = "ZHC_AGENCY_NOTION_PARENT_PAGE_ID"
NOTION_VERSION_ENV = "NOTION_API_VERSION"
NOTION_DEFAULT_VERSION = "2022-06-28"
NOTION_HOST = "api.notion.com"

# The one parent page every episode page hangs under, created once per client.
NOTION_EPISODES_PAGE_TITLE = "Podcast Episodes"

# Notion API limits: 100 children per request, 2000 characters per rich-text run.
# Skill 37 chunks at 1900; the same margin is kept here.
NOTION_MAX_BLOCKS_PER_REQUEST = 100
NOTION_MAX_RICH_TEXT = 1900

BOTH_TIERS_SKIP_LINE = (
    "document delivery skipped: neither Google Workspace (Skill 14, see "
    "14-google-workspace-integration/INSTALL.md) nor Notion (NOTION_API_TOKEN plus "
    "an explicit client-owned parent page, see 37-zhc-closeout) is configured on "
    "this box; the rendered files on disk are the deliverables")


class NotionDeliveryError(Exception):
    """A Notion delivery failure. Recorded on the plan; never fails the episode."""


def resolve_notion_credentials() -> dict:
    """Resolve the client's own Notion credentials, by label only.

    Needs a token AND an explicit parent page. Ownership is never inferred from a
    workspace-wide search, and the agency token and agency parent are refused.
    """
    token_env = _first_set_env(NOTION_TOKEN_ENVS)
    parent_env = _first_set_env(NOTION_PARENT_ENVS)

    report = {
        "resolved": False,
        "reason": "",
        "token": "NOT SET",
        "parent_page": "NOT SET",
        "api_version": os.environ.get(NOTION_VERSION_ENV, "").strip() or NOTION_DEFAULT_VERSION,
        "ownership": "client-owned parent required; agency token and agency parent refused",
    }

    if not token_env:
        report["reason"] = "no Notion token (%s)" % " or ".join(NOTION_TOKEN_ENVS)
        return report
    token = os.environ[token_env].strip()
    report["token"] = "SET (%s)" % token_env

    agency_token = os.environ.get(NOTION_AGENCY_TOKEN_ENV, "").strip()
    if agency_token and token == agency_token:
        report["token"] = "REFUSED (agency token)"
        report["reason"] = ("the configured token is the agency token; a client "
                            "document is never published with an agency credential")
        return report

    if not parent_env:
        report["reason"] = ("no explicit client-owned parent page (%s)"
                            % " or ".join(NOTION_PARENT_ENVS))
        return report
    parent = os.environ[parent_env].strip()
    report["parent_page"] = "SET (%s)" % parent_env

    agency_parent = os.environ.get(NOTION_AGENCY_PARENT_ENV, "").strip()
    if agency_parent and parent.replace("-", "") == agency_parent.replace("-", ""):
        report["parent_page"] = "REFUSED (agency parent)"
        report["reason"] = ("the configured parent page is the agency parent; a "
                            "client document never lands in agency space")
        return report

    report["resolved"] = True
    report["_token"] = token
    report["_parent_page_id"] = parent
    return report


# ---------------------------------------------------------------------------
# Markdown to Notion blocks
# ---------------------------------------------------------------------------

_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")


def _rich_text_runs(text: str) -> list:
    """Split text into Notion rich-text runs, turning markdown links into links.

    Every run is capped at the rich-text character limit, so a very long paragraph
    is carried as several runs inside ONE block rather than being truncated.
    """
    runs: list = []

    def _plain(segment: str) -> None:
        for start in range(0, len(segment), NOTION_MAX_RICH_TEXT):
            piece = segment[start:start + NOTION_MAX_RICH_TEXT]
            if piece:
                runs.append({"type": "text", "text": {"content": piece}})

    cursor = 0
    for match in _MD_LINK_RE.finditer(text):
        _plain(text[cursor:match.start()])
        label = match.group(1)[:NOTION_MAX_RICH_TEXT]
        runs.append({"type": "text",
                     "text": {"content": label, "link": {"url": match.group(2)}}})
        cursor = match.end()
    _plain(text[cursor:])
    return runs or [{"type": "text", "text": {"content": ""}}]


def _block(kind: str, text: str) -> dict:
    return {"object": "block", "type": kind, kind: {"rich_text": _rich_text_runs(text)}}


def markdown_to_notion_blocks(markdown: str) -> list:
    """Convert the subset of markdown this engine emits into Notion blocks.

    Headings (# to ###), bulleted list items, links inside any line, and everything
    else as paragraphs. Blank lines separate blocks and produce none of their own.
    The engine never emits code fences, so none are handled.
    """
    blocks: list = []
    for raw in (markdown or "").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("### "):
            blocks.append(_block("heading_3", stripped[4:].strip()))
        elif stripped.startswith("## "):
            blocks.append(_block("heading_2", stripped[3:].strip()))
        elif stripped.startswith("# "):
            blocks.append(_block("heading_1", stripped[2:].strip()))
        elif stripped.startswith(("- ", "* ", "+ ")):
            blocks.append(_block("bulleted_list_item", stripped[2:].strip()))
        else:
            blocks.append(_block("paragraph", stripped))
    return blocks


def _md_escape(value: object) -> str:
    """Flatten a value to one markdown-safe line."""
    return " ".join(str(value).split())


def render_package_markdown(m: dict) -> str:
    """The Episode Package as markdown, from the SAME manifest the HTML uses.

    Notion blocks are built from this rather than by parsing the rendered HTML, so
    the structure stays exact and the two renderings never drift apart in meaning.
    """
    research = m.get("research") or {}
    lines: list = []

    def section(title: str, items: list, bullet: bool = True) -> None:
        rows = [i for i in (items or []) if str(i).strip()]
        if not rows:
            return
        lines.append("")
        lines.append("## %s" % title)
        for row in rows:
            lines.append(("- %s" if bullet else "%s") % _md_escape(row))

    lines.append("## Episode properties")
    props = [
        ("Title", m.get("title")),
        ("Date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        ("Style", m.get("style")),
        ("Mode", m.get("mode")),
        ("Runtime (minutes)", m.get("runtime_minutes")),
        ("Spoken words", m.get("word_count")),
        ("Guest", m.get("guest_first_name")),
    ]
    for label, value in props:
        if str(value or "").strip():
            lines.append("- %s: %s" % (label, _md_escape(value)))
    # The Notion API cannot upload a file, so the published audio is LINKED.
    audio = str(m.get("podbean_url") or "").strip()
    if audio:
        lines.append("- Published audio: [%s](%s)" % (_md_escape(m.get("title")), audio))

    if str(m.get("thesis") or "").strip():
        lines.append("")
        lines.append("## Thesis")
        lines.append(_md_escape(m.get("thesis")))

    if str(m.get("description") or "").strip():
        lines.append("")
        lines.append("## Show notes")
        for para in str(m["description"]).split("\n"):
            if para.strip():
                lines.append(_md_escape(para))

    section("Key takeaways", research.get("key_takeaways"))
    section("Power statements", research.get("power_statements"))

    studies = [c for c in (research.get("case_studies") or []) if isinstance(c, dict)]
    if studies:
        lines.append("")
        lines.append("## Case studies")
        for case in studies:
            lines.append("### %s" % _md_escape(case.get("title", "Case study")))
            if str(case.get("summary") or "").strip():
                lines.append(_md_escape(case["summary"]))
            source = str(case.get("source") or "").strip()
            if source:
                lines.append("- Source: %s" % _md_escape(source))

    section("Supporting findings", research.get("findings"))
    section("Sources", research.get("sources"))

    lines.append("")
    lines.append("## Speech Script")
    for para in str(m.get("_speech_script_text", "")).split("\n"):
        if para.strip():
            lines.append(_md_escape(para))

    return "\n".join(lines).strip() + "\n"


# ---------------------------------------------------------------------------
# Notion transport
# ---------------------------------------------------------------------------

class NotionTransport:
    """Direct Notion REST with the client's own integration token.

    Shapes and the API version follow 37-zhc-closeout/scripts/create-notion-closeout.sh.
    """

    def __init__(self, creds: dict) -> None:
        self._token = creds["_token"]
        self._version = creds.get("api_version") or NOTION_DEFAULT_VERSION

    def _headers(self) -> dict:
        return {
            "Authorization": "Bearer %s" % self._token,
            "Notion-Version": self._version,
            "Content-Type": "application/json",
        }

    def _call(self, method: str, path: str, body=None, expect=(200,)) -> dict:
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        status, raw = _https(method, NOTION_HOST, path, self._headers(), payload)
        if status in expect:
            if not raw:
                return {}
            try:
                return json.loads(raw)
            except Exception:
                return {}
        raise NotionDeliveryError(
            "Notion %s returned HTTP %s. %s"
            % (path.split("?")[0], status, _notion_error_detail(raw)))

    def find_child_page(self, parent_id: str, title: str) -> str | None:
        """Id of the direct child page with this exact title, else None.

        Paginated. Uses the block-children listing, which is authoritative for
        DIRECT children, so a workspace-wide search can never match a foreign page.
        """
        from urllib.parse import quote
        cursor = None
        while True:
            path = ("/v1/blocks/%s/children?page_size=100"
                    % quote(str(parent_id), safe=""))
            if cursor:
                path += "&start_cursor=%s" % quote(str(cursor), safe="")
            data = self._call("GET", path)
            for row in data.get("results", []) or []:
                if not isinstance(row, dict) or row.get("type") != "child_page":
                    continue
                if (row.get("child_page") or {}).get("title") == title:
                    return row.get("id")
            if not data.get("has_more") or not data.get("next_cursor"):
                return None
            cursor = data["next_cursor"]

    def create_page(self, parent_id: str, title: str, blocks: list) -> dict:
        """Create a child page. Only the first request's worth of blocks is inline."""
        body = {
            "parent": {"page_id": parent_id},
            "properties": {"title": {"title": [{"type": "text",
                                                "text": {"content": title}}]}},
            "children": blocks[:NOTION_MAX_BLOCKS_PER_REQUEST],
        }
        data = self._call("POST", "/v1/pages", body, expect=(200, 201))
        page_id = data.get("id")
        if not page_id:
            raise NotionDeliveryError("Notion page create returned no page id")
        if len(blocks) > NOTION_MAX_BLOCKS_PER_REQUEST:
            self.append_blocks(page_id, blocks[NOTION_MAX_BLOCKS_PER_REQUEST:])
        return {"id": page_id,
                "url": data.get("url") or _notion_page_url(page_id)}

    def append_blocks(self, page_id: str, blocks: list) -> None:
        """Append blocks, chunked at the API's 100-children-per-request limit."""
        from urllib.parse import quote
        path = "/v1/blocks/%s/children" % quote(str(page_id), safe="")
        for start in range(0, len(blocks), NOTION_MAX_BLOCKS_PER_REQUEST):
            chunk = blocks[start:start + NOTION_MAX_BLOCKS_PER_REQUEST]
            self._call("PATCH", path, {"children": chunk})

    def clear_children(self, page_id: str) -> None:
        """Delete every direct child block so an update replaces, never duplicates."""
        from urllib.parse import quote
        while True:
            data = self._call(
                "GET", "/v1/blocks/%s/children?page_size=100" % quote(str(page_id), safe=""))
            rows = [r.get("id") for r in (data.get("results") or [])
                    if isinstance(r, dict) and r.get("id")]
            for block_id in rows:
                self._call("DELETE", "/v1/blocks/%s" % quote(str(block_id), safe=""))
            if not rows or not data.get("has_more"):
                return

    def update_page(self, page_id: str, blocks: list) -> dict:
        """Replace an existing episode page's content in place."""
        self.clear_children(page_id)
        self.append_blocks(page_id, blocks)
        return {"id": page_id, "url": _notion_page_url(page_id)}


def _notion_page_url(page_id: str) -> str:
    return "https://www.notion.so/%s" % str(page_id).replace("-", "")


def _notion_error_detail(raw: bytes) -> str:
    try:
        parsed = json.loads(raw)
    except Exception:
        return ""
    if not isinstance(parsed, dict):
        return ""
    parts = [str(parsed.get("code", "")), str(parsed.get("message", ""))]
    return " ".join(p for p in parts if p)[:180]


def _make_notion_transport(creds: dict) -> NotionTransport:
    """Transport factory. Tests replace this to exercise delivery without a network."""
    return NotionTransport(creds)


def perform_notion_delivery(plan: dict, creds: dict, manifest: dict) -> dict:
    """Deliver the episode documents into the client's own Notion. Never raises.

    One "Podcast Episodes" parent page per client, created idempotently, then one
    child page per episode keyed by the episode title. Re-running Step 12 for the
    same episode replaces that page's blocks instead of creating a second page.
    """
    record: dict = {
        "channel": "notion",
        "attempted": True,
        "performed": False,
        "status": "error",
        "credentials": public_credential_report(creds),
        "documents": {},
        "errors": [],
        "note": ("the Notion API cannot upload a file; the published audio is "
                 "linked and the rendered files on disk remain the durable base"),
    }
    title = str(manifest.get("title") or "").strip() or "Podcast episode"

    try:
        transport = _make_notion_transport(creds)
    except Exception as exc:  # noqa: BLE001
        record["errors"].append("transport unavailable: %s" % _safe_error(exc))
        return record

    try:
        blocks = markdown_to_notion_blocks(render_package_markdown(manifest))

        episodes_id = transport.find_child_page(
            creds["_parent_page_id"], NOTION_EPISODES_PAGE_TITLE)
        if not episodes_id:
            created = transport.create_page(
                creds["_parent_page_id"], NOTION_EPISODES_PAGE_TITLE,
                [_block("paragraph",
                        "Every produced episode lands here as its own page.")])
            episodes_id = created["id"]
            record["episodes_page_created"] = True
        else:
            record["episodes_page_created"] = False
        record["episodes_page_id"] = episodes_id

        existing = transport.find_child_page(episodes_id, title)
        if existing:
            result = transport.update_page(existing, blocks)
            record["action"] = "updated"
        else:
            result = transport.create_page(episodes_id, title, blocks)
            record["action"] = "created"

        record["documents"]["episode_page"] = {"page_id": result["id"],
                                               "url": result["url"],
                                               "blocks": len(blocks)}
        record["performed"] = True
        record["status"] = "performed"

        # When the plan's primary destination was Notion it already carries
        # notion.create_page intents. Stamp them exactly like the Drive ones so the
        # episode record reads the same whichever tier delivered.
        for action in plan.get("actions", []):
            kind = action.get("action")
            if kind == "notion.create_page":
                action["performed"] = True
                action["channel"] = "notion"
                action["page_id"] = result["id"]
                action["url"] = result["url"]
            elif kind == "capture_link" and str(action.get("into", "")).startswith("links."):
                key = str(action["into"]).split(".")[-1]
                plan.setdefault("links", {})[key] = result["url"]
                action["performed"] = True
                action["channel"] = "notion"
    except Exception as exc:  # noqa: BLE001 - never fails the episode
        record["errors"].append(_safe_error(exc))
        record["status"] = "partial" if record["documents"] else "error"
    return record


def record_notion_skip(creds: dict) -> dict:
    """Record the not-configured outcome for the Notion tier."""
    return {
        "channel": "notion",
        "attempted": False,
        "performed": False,
        "status": "skipped",
        "reason": creds.get("reason", "credentials not configured"),
        "credentials": public_credential_report(creds),
        "documents": {},
        "errors": [],
    }


# ---------------------------------------------------------------------------
# The delivery chain: Google Drive, then Notion, then intent-only
# ---------------------------------------------------------------------------

# The tier order, stated once so it cannot drift between the code and the docs.
DRIVE_TIER_ORDER = ("google_drive", "notion")

def deliver_documents(plan: dict, manifest: dict, allow_delivery: bool = True) -> dict:
    """Run the two-tier delivery chain and summarize it on the plan.

    Tier 1 is Google Drive through the client's Skill 14 credentials. Tier 2 is the
    client's own Notion, tried when Drive is not configured on this box or its call
    delivered nothing. Tier 3 is today's intent-only record with ONE log line naming
    both prerequisites. No tier can fail the episode or change the exit code.
    """
    summary: dict = {
        "channel": None,
        "performed": False,
        "status": "skipped",
        "documents": {},
        "errors": [],
        "tiers": {},
        "log": [],
    }
    plan["delivery"] = summary

    if not allow_delivery:
        summary["status"] = "disabled"
        summary["reason"] = "--no-deliver requested; the plan is intent-only"
        return summary

    # ---- Tier 1: Google Drive -------------------------------------------
    has_drive_intent = any(a.get("action", "").startswith("drive.")
                           for a in plan.get("actions", []))
    drive_creds = resolve_drive_credentials()
    if drive_creds["resolved"] and has_drive_intent:
        drive = perform_drive_delivery(plan, drive_creds)
    else:
        drive = record_drive_skip(plan, drive_creds)
        if drive_creds["resolved"] and not has_drive_intent:
            drive["reason"] = "the plan carries no Google Drive action to perform"
    summary["tiers"]["google_drive"] = drive
    summary["errors"].extend(drive.get("errors", []))

    # Drive counts as delivered when it landed at least one document. A permission
    # that failed after a successful upload is partial, not a reason to fall back:
    # the documents are already in the client's Drive.
    if drive.get("performed"):
        summary["channel"] = "google_drive"
        summary["performed"] = True
        summary["status"] = drive["status"]
        summary["documents"] = drive["documents"]
        summary["log"].append(
            "drive delivery %s: %d document(s) uploaded and shared"
            % (drive["status"], len(drive["documents"])))
        return summary

    if drive["status"] == "skipped":
        summary["log"].append(SKIP_LINE)
    else:
        summary["log"].append(
            "drive delivery failed; falling back to Notion. %s"
            % "; ".join(drive.get("errors", [])[:2]))

    # ---- Tier 2: Notion --------------------------------------------------
    notion_creds = resolve_notion_credentials()
    if notion_creds["resolved"]:
        notion = perform_notion_delivery(plan, notion_creds, manifest)
    else:
        notion = record_notion_skip(notion_creds)
    summary["tiers"]["notion"] = notion
    summary["errors"].extend(notion.get("errors", []))

    if notion.get("performed"):
        summary["channel"] = "notion"
        summary["performed"] = True
        summary["status"] = notion["status"]
        summary["documents"] = notion["documents"]
        page = notion["documents"].get("episode_page", {})
        plan.setdefault("links", {})["episode_page"] = page.get("url")
        summary["log"].append(
            "notion delivery performed: episode page %s" % notion.get("action", "written"))
        return summary

    # ---- Tier 3: intent only --------------------------------------------
    if drive["status"] == "skipped" and notion["status"] == "skipped":
        summary["status"] = "skipped"
        summary["log"] = [BOTH_TIERS_SKIP_LINE]
    else:
        summary["status"] = "error"
        if notion["status"] == "skipped":
            summary["log"].append(
                "notion fallback unavailable: %s" % notion.get("reason", "not configured"))
        else:
            summary["log"].append(
                "notion delivery failed: %s" % "; ".join(notion.get("errors", [])[:2]))
    return summary


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

_FONT_RE = re.compile(r"font-size\s*:\s*([0-9]*\.?[0-9]+)\s*(pt|px|em|rem|%)", re.IGNORECASE)


def check_font_floor(html_path: str) -> tuple[bool, list[str]]:
    p = Path(html_path)
    if not p.is_file():
        return False, ["package file not found: %s" % html_path]
    text = p.read_text(encoding="utf-8")
    problems: list[str] = []
    found = 0
    for value, unit in _FONT_RE.findall(text):
        found += 1
        v = float(value)
        unit = unit.lower()
        if unit == "pt":
            pt = v
        elif unit == "px":
            pt = v * 0.75  # 96px per inch, 72pt per inch
        else:
            problems.append("font-size %s%s uses a relative unit; use pt so the "
                            "12pt floor is verifiable" % (value, unit))
            continue
        if pt < FONT_FLOOR_PT:
            problems.append("font-size %s%s is below the %dpt floor" % (value, unit, FONT_FLOOR_PT))
    if found == 0:
        problems.append("no font-size declaration found; cannot prove the 12pt floor")
    return (len(problems) == 0), problems


def check_script_clean(txt_path: str) -> tuple[bool, list[str], list[str]]:
    p = Path(txt_path)
    if not p.is_file():
        return False, ["speech script file not found: %s" % txt_path], []
    text = p.read_text(encoding="utf-8")
    hard: list[str] = []
    warn: list[str] = []
    if not text.strip():
        hard.append("speech script is empty")
    if "\u2014" in text:
        hard.append("em dash character present (forbidden everywhere)")
    if "`" * 3 in text:
        hard.append("triple backtick fence present (forbidden in produced output)")
    if re.search(r"</?[a-zA-Z][^>]*>", text):
        hard.append("HTML tag present; the Speech Script must be clean text only")
    for i, line in enumerate(text.splitlines(), 1):
        if re.match(r"\s*#{1,6}\s", line):
            warn.append("line %d looks like a markdown heading" % i)
        elif re.match(r"\s*([*_]{1,2}\S|[-*+]\s|\d+\.\s)", line):
            warn.append("line %d looks like a markdown list or emphasis marker" % i)
    return (len(hard) == 0), hard, warn


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_render(args: argparse.Namespace) -> int:
    try:
        m = load_manifest(args.manifest, args.speech_script_file)
    except ValueError as exc:
        eprint("ERROR: %s" % exc)
        return 2

    detection = detect_destination()
    if args.force_destination:
        destination = args.force_destination
        forced = True
    else:
        destination = detection["chosen"]
        forced = False

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = "%s-%s" % (slugify(m.get("client", "")), slugify(m.get("title", "")))
    slug = slug.strip("-") or "podcast-episode"

    package_path = (out_dir / ("%s-episode-package.html" % slug)).resolve()
    speech_path = (out_dir / ("%s-speech-script.txt" % slug)).resolve()
    plan_path = (out_dir / ("%s-documents-plan.json" % slug)).resolve()

    # Render + persist the two deliverables.
    package_html = render_package_html(m)
    package_path.write_text(package_html, encoding="utf-8")
    speech_path.write_text((m["_speech_script_text"] + "\n"), encoding="utf-8")

    # Self-verify before declaring success (fail-closed).
    font_ok, font_problems = check_font_floor(str(package_path))
    if not font_ok:
        eprint("ERROR: rendered package failed the %dpt font-floor check:" % FONT_FLOOR_PT)
        for pb in font_problems:
            eprint("  - %s" % pb)
        return 3
    script_ok, script_hard, script_warn = check_script_clean(str(speech_path))
    for w in script_warn:
        eprint("[render_documents][WARN] %s" % w)
    if not script_ok:
        eprint("ERROR: Speech Script failed the clean-text check:")
        for hp in script_hard:
            eprint("  - %s" % hp)
        return 3

    plan = build_plan(m, detection, destination, forced, package_path, speech_path)

    # Step 12 owns the delivery it plans. The chain is Google Drive through the
    # client's Skill 14 credentials, then the client's own Notion, then today's
    # intent-only record. No tier can fail the episode or change the exit code.
    delivery = deliver_documents(plan, m, allow_delivery=not args.no_deliver)
    for line in delivery.get("log", []):
        prefix = "[render_documents]" if delivery["performed"] else "[render_documents][WARN]"
        eprint("%s %s" % (prefix, line))
    for err in delivery.get("errors", []):
        eprint("[render_documents][WARN]   %s" % err)

    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    if forced and not plan["ready"]:
        eprint("[render_documents][WARN] destination forced to '%s' but its credentials "
               "are NOT SET; the agent must resolve them before executing the plan." % destination)

    print(json.dumps(plan, indent=2))
    return 0


def cmd_detect(args: argparse.Namespace) -> int:
    detection = detect_destination()
    creds = resolve_drive_credentials()
    notion_creds = resolve_notion_credentials()
    detection["drive_delivery"] = public_credential_report(creds)
    detection["notion_delivery"] = public_credential_report(notion_creds)
    if args.json:
        print(json.dumps(detection, indent=2))
    else:
        print("Chosen destination: %s" % detection["chosen"])
        print("  google: available=%s gws_cli=%s"
              % (detection["google"]["available"], detection["google"]["gws_cli"]))
        print("  tier 1 drive delivery: resolved=%s key=%s user=%s folder=%s"
              % (creds["resolved"], creds["service_account_key"],
                 creds["impersonated_user"], creds["root_folder"]))
        print("  tier 2 notion delivery: resolved=%s token=%s parent=%s"
              % (notion_creds["resolved"], notion_creds["token"],
                 notion_creds["parent_page"]))
        print("  notion: available=%s token=%s parent_page=%s"
              % (detection["notion"]["available"], detection["notion"]["token"],
                 detection["notion"]["parent_page"]))
        print("  local:  always available (plain-text last resort)")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    ok, problems = check_font_floor(args.package)
    if ok:
        print("PASS: every font-size in %s is at or above the %dpt floor" % (args.package, FONT_FLOOR_PT))
        return 0
    eprint("FAIL: font-floor check on %s" % args.package)
    for pb in problems:
        eprint("  - %s" % pb)
    return 3


def cmd_check_script(args: argparse.Namespace) -> int:
    ok, hard, warn = check_script_clean(args.script)
    for w in warn:
        eprint("[WARN] %s" % w)
    if ok:
        print("PASS: %s is clean text" % args.script)
        return 0
    eprint("FAIL: clean-text check on %s" % args.script)
    for hp in hard:
        eprint("  - %s" % hp)
    return 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="render_documents.py",
        description="Podcast Production Engine Step 12 document renderer and destination planner.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_render = sub.add_parser("render", help="render the Episode Package and Speech Script and emit a destination plan")
    p_render.add_argument("--manifest", required=True, help="path to the episode manifest JSON")
    p_render.add_argument("--out-dir", required=True, help="output directory for the artifacts")
    p_render.add_argument("--force-destination", choices=["google", "notion", "local"],
                          help="override destination detection")
    p_render.add_argument("--speech-script-file", help="path to the clean speech script text file")
    p_render.add_argument("--no-deliver", action="store_true",
                          help="render and plan only; never perform the Google Drive "
                               "delivery even when Skill 14 credentials are configured")
    p_render.set_defaults(func=cmd_render)

    p_detect = sub.add_parser("detect", help="report destination detection only")
    p_detect.add_argument("--json", action="store_true", help="emit JSON")
    p_detect.set_defaults(func=cmd_detect)

    p_check = sub.add_parser("check", help="verify the 12pt font floor on a package HTML file")
    p_check.add_argument("--package", required=True, help="path to the episode package HTML")
    p_check.set_defaults(func=cmd_check)

    p_cs = sub.add_parser("check-script", help="verify a speech script is clean text")
    p_cs.add_argument("--script", required=True, help="path to the speech script text file")
    p_cs.set_defaults(func=cmd_check_script)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
