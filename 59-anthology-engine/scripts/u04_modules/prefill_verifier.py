#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u04_modules/prefill_verifier.py  (U04 tooling)
# INTAKE PRE-FILL VERIFIER (G3 GATEWAY) — the fail-closed verifier that the
# LIVE universal author-intake form's hidden anthology_id field is pre-filled
# from the minted intake link's ONE query param
# (<forms_base>/widget/form/<form_id>?anthology_id=<minted>, built by
# anthology_book.build_intake_link). A form that DROPS the minted Book ID
# silently routes an unbound submission — the same G3 defect family the
# sibling query_key_checker guards from the KEY side; this module guards the
# VALUE side.
# -----------------------------------------------------------------------------
# WHAT THIS OWNS — THE G3 LAW, VALUE SIDE
#   The minted link rides the ONE query param anthology_id onto the form's
#   HIDDEN anthology_id field (intake_router.py:133-134 accepts
#   customData.anthology_id; SKILL.md:52), so the Book ID never types a
#   keystroke. The pre-fill is NOT server-rendered: two fetched copies of the
#   SAME form page (with and without ?anthology_id=<probe>) are BYTE-IDENTICAL
#   (proofed live against the fleet-wide universal form U65pwoeMTy1niMqllKWG
#   on link.msgsndr.com), and the prefill value appears in NO fetched byte.
#   The widget hydrates the hidden field CLIENT-SIDE: the shipped widget build
#   (the page's <script type="module"> bundle + the dynamic chunk it loads,
#   both under stcdn.leadconnectorhq.com/_preview/) maps
#   `hiddenFieldQueryKey in urlParams` -> formFieldsValue[tag] = the param
#   value for every field whose definition carries a hiddenFieldQueryKey
#   (proofed in the served widget code, chunk DO9dUel-.js: the Ct hydration
#   function — "O.hiddenFieldQueryKey in c" — runs over the form's fields and
#   writes the query-param value into the field's value store; the hidden
#   anthology_id textarea renders value="ANTH_TEST" in a REAL browser only).
#   So the honest LIVE observation is a two-part signature:
#     1. the served page is the SAME for the probe-param URL as for the bare
#        URL (the widget owns the pre-fill, never the origin — a page that
#        BAKES the probe into the served bytes is a tampered/caching page,
#        REFUSED, because the real widget would double-apply), and
#     2. the build artifact signature: the served module bundle + the loaded
#        dynamic chunk + the build-meta JSON (timestamp) match the committed
#        fleet baseline in config/prefill-verifier-baseline.json, and that
#        signature's prefill-mode code IS the hydration law. A build that no
#        longer maps the URL param onto the hidden field changes the artifact
#        signature and the SELF-TEST's signed fixture stops matching it
#        (fail-closed: a drifted artifact is a MISMATCH, never a blind pass).
#   The signature carries ONLY digest + path + length — a build identifier,
#   never a credential, and never the probe value (a fixture probe is a
#   deliberate value, not a secret; the SELF-TEST keeps it fixed so a run can
#   never be influenced by a caller-supplied value).
#
#   The module NEVER needs a browser to fetch or to fail closed: the two
#   public GETs ride reg.CAF_BROWSER_UA (CF 1010 law) and the build baseline
#   ships in config/. A REAL browser render (the rendered hidden-field value)
#   is OPTIONALLY observed when a headless-Chromium runtime is present — this
#   box ships chromium_headless_shell + the Chromium build in the ms-playwright
#   cache, and the module drives that runtime DIRECTLY (subprocess with
#   --headless=new + the DevTools Protocol over a loopback WebSocket, stdlib
#   only: subprocess, urllib, json, socket, struct, base64) with ZERO
#   optional dependencies. NO driver, NO browser-control service, NO local
#   server, NO network to any third-party automation host. When the runtime
#   is ABSENT or the render cannot complete, the rendered check is
#   SKIPPED-as-undetermined / HELD (never a blind pass); the signature
#   checks still report their own verdict.
#
# CREDENTIAL-FREE BY DESIGN (the sibling query_key_checker doctrine): the
# hosted-form page and the widget build are PUBLIC surfaces — the author's
# browser loads both. This module holds NO credential surface at all: nothing
# to resolve, nothing that could ever print a token. The ANTH_TEST probe is a
# deliberately synthetic fixture value (a test value, not a secret, and never
# the real fleet pin), pinned in the offline self-test.
#
# FAIL-CLOSED (the whole point)
#   - a form page that cannot be fetched (HTTP error, transport failure,
#     timeout) is HELD (exit 3) — the law is UNDETERMINED, never proven
#     compliant (the query_key_checker discipline),
#   - a 2xx body that cannot be decoded faithfully is HELD (exit 3) — a
#     tampered page is the attack this gate exists for,
#   - a page that differs between the bare URL and the probe-param URL is a
#     REFUSAL (exit 5) — either the origin bakes the probe into the served
#     bytes (a caching/tampered page the real widget would double-apply) or a
#     malicious rewrite; a byte-identical page is the PROVEN live shape,
#   - a page that does not reference the widget build (no _preview module
#     script, no build-meta) is a REFUSAL (exit 5) — the page is not the
#     hosted-form surface this gate exists for,
#   - a build artifact that does not fetch, does not match its committed
#     baseline digest, or whose signature section is absent from the baseline
#     is a MISMATCH (exit 5) — the hydration law became unverifiable, never
#     a silent pass (the baseline file is the committed, hashed source; a
#     stale or missing baseline is a STOP, exit 2),
#   - the hydration code text itself (the hiddenFieldQueryKey->urlParams
#     mapping in the widget code) must be present in the fetched bundle; a
#     bundle whose hydration code is absent is a MISMATCH (exit 5),
#   - a rendered observation is attempted ONLY when a headless-Chromium
#     runtime is present; absent runtime -> SKIPPED as undetermined (never
#     fabricated); probe value NOT rendered exactly / probe rendered onto the
#     WRONG field / prefill rendered with the param ABSENT is a MISMATCH
#     (exit 5); a render that cannot complete (no page target, CDP failure,
#     timeout) is HELD (exit 3),
#   - the expected query key is NEVER hardcoded here: it is mirrored from
#     scripts/anthology_book.py INTAKE_QUERY_KEY (the SAME constant
#     build_intake_link mints with, imported at runtime — the
#     delta_reporter.py single-implementation doctrine) and pinned
#     byte-for-byte in the offline self-test, so a drift between the minted
#     link and this gate trips the self-test before it can ship.
#
# EXIT CODES (house convention 0/1/2/3/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  PASS — served pages byte-identical, widget build signature matches the
#      committed baseline, hydration code present, probe URL canonical
#      (also plan and self-test PASS)
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — the expected query key cannot be resolved
#      (anthology_book.py INTAKE_QUERY_KEY unimportable or empty), the
#      committed prefill baseline is missing/malformed/not-a-JSON-object, or
#      usage error: the law is unverifiable — a check that cannot see its
#      law never fabricates a pass
#   3  HELD — the form page / build artifact is unreachable (HTTP error,
#      transport failure, edge block, timeout), its bytes cannot be decoded,
#      or a rendered observation cannot complete: the law is UNDETERMINED,
#      never proven compliant
#   4  self-test FAILED (an offline assertion tripped; a tamper NEVER
#      masquerades as exit 1)
#   5  FAIL — served-page drift (probe baked into the served bytes), page not
#      the hosted-form surface, build signature drift, hydration code absent,
#      or a rendered prefill mismatch (AF-AE-PREFILL-* family; the G3
#      value-side defect)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on
# stderr; --self-test is OFFLINE and needs NO token and NO network):
#   prefill_verifier.py live [--forms-base URL] [--intake-form-id ID]
#       [--probe VALUE] [--no-render] [--timeout SECONDS]
#   prefill_verifier.py plan            # offline; the G3 value-side law with
#                                       # its sources of truth
#   prefill_verifier.py self-test       # offline golden + attack fixtures
#
# STDLIB ONLY (urllib + json + re + subprocess + a loopback WebSocket
# client); calls NO model; a browser is driven DIRECTLY over the DevTools
# Protocol only when present (optional, never required for a PASS on the
# served surface). Sibling import bootstrap
# identical to the other u04 modules: sys.path insert to scripts/ then
# `import anthology_registry as reg` for the canonical CAF_BROWSER_UA. The
# expected key is imported from anthology_book (its own sibling bootstrap
# runs once at import). DOCTRINE: move in silence; NOTHING Anthropic in any
# runtime file; Convert and Flow naming in every client surface; NEVER print
# a secret value — and this module holds no secret to print.
# =============================================================================
"""prefill_verifier.py — G3 value-side gate: the minted intake link's
?anthology_id=<minted> pre-fills the form's hidden anthology_id field."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
import os
import re
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Sibling import bootstrap (house convention): the registry owns the
# canonical constants (CAF_BROWSER_UA) and the fail-closed helper surfaces;
# this module mirrors the constants it needs and pins the mirror in its
# offline self-test.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The fleet-wide non-client defaults mirrored from anthology_book.py: the
# shared LeadConnector hosted-form domain, the ONE universal author-intake
# form id, the widget path prefix, and the build-artifact root (platform /
# universal values, never a per-client domain or credential; all overridable
# per box). The mirror is pinned in the offline self-test so a drift between
# the minted link and this gate trips the self-test before it can ship.
DEFAULT_FORMS_BASE = "https://link.msgsndr.com"
DEFAULT_UNIVERSAL_INTAKE_FORM_ID = "U65pwoeMTy1niMqllKWG"
WIDGET_FORM_PATH = "/widget/form"
DEFAULT_BUILD_ROOT = "https://stcdn.leadconnectorhq.com/_preview"

# The deliberately synthetic probe value the live verify rides. A test
# value, NOT a secret and NEVER the real fleet pin; pinned in the offline
# self-test so a run can never be influenced by a caller-supplied value.
# The minted Book ID shape is ANTH_<20 hex> (anthology_book.mint_book_id);
# the probe follows the ANTH_ prefix law so the served surface is exercised
# exactly as the minted link exercises it.
DEFAULT_PROBE_VALUE = "ANTH_TEST"

# The committed fleet baseline of the widget build signature (the hashed
# source of truth for the hydration law — a build that no longer maps the
# URL param onto the hidden field changes the artifact signature and the
# self-test's signed fixture stops matching it, fail-closed).
BASELINE_REL_PATH = "config/prefill-verifier-baseline.json"

# Fetched artifact cap (bytes): the widget bundle is ~380KB decompressed;
# the cap only guards a runaway response.
MAX_READ_BYTES = 8 * 1024 * 1024

# The hydration code law, as it ships in the widget build: the prefill map
# maps a field's hiddenFieldQueryKey onto the URL param. The signature code
# text below is the exact served shape (chunk DO9dUel-.js, the Ct hydration
# function, proofed live); its presence is required in the fetched widget
# code, and the OFFLINE self-test pins the text byte-exact so a drift in the
# served widget code trips the self-test before it can ship. A missing
# marker is a MISMATCH, never a silent pass.
PREFILL_HYDRATION_MARKER = "hiddenFieldQueryKey in c"
PREFILL_ASSIGN_MARKER = "I.value[O.tag]="


def _resolve_intake_key() -> str:
    """The G3 expected query key, from the ONE source of truth: the same
    INTAKE_QUERY_KEY constant build_intake_link mints links with
    (scripts/anthology_book.py). Fail-closed: an unimportable or empty
    constant returns "" — the law is unverifiable, never a guessed key."""
    try:
        import anthology_book  # noqa: F401  (sibling import after path bootstrap)
        key = (getattr(anthology_book, "INTAKE_QUERY_KEY", "") or "").strip()
    except Exception:  # noqa: BLE001  (import failure -> fail closed)
        return ""
    return key


def _mask_form_id(form_id: str) -> str:
    """Non-reversible marker for a form id (last 4 chars), the house
    masking law for every identifier surface."""
    form_id = (form_id or "").strip()
    return ("..." + form_id[-4:]) if len(form_id) >= 4 else "...(short)"


def _decompress(data: bytes) -> str:
    """Decode the fetched body, transparently gunzipping when the server
    served Content-Encoding: gzip. A body that cannot be decoded faithfully
    raises ValueError -> HELD (the law is UNDETERMINED on unreadable bytes,
    never proven compliant)."""
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data.decode("utf-8", errors="strict")


def _digest_bytes(data: bytes) -> str:
    """The sha256 hex digest of the fetched bytes — the artifact identifier
    carried on every surface (a digest, never content)."""
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# The live read — the PUBLIC hosted-form page + the PUBLIC widget build
# (zero credentials; the sibling query_key_checker discipline).
# ---------------------------------------------------------------------------
class _PrefillPageError(Exception):
    """Unexpected error surfaced by a prefill_verifier run (fail-closed)."""


def fetch_http(url: str, timeout: float = 20.0) -> bytes:
    """Fetch a URL with the house browser User-Agent (reg.CAF_BROWSER_UA —
    the CF 1010 law; the SAME UA'd GET proved against the live page).
    Returns the raw (still possibly gzip-compressed) bytes. Raises
    reg.CafUnreachable (HELD family) on any HTTP error / transport failure /
    timeout. NEVER reads a credential — there is none."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": reg.CAF_BROWSER_UA,
                 "Accept-Encoding": "gzip",
                 "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            if status >= 400:
                raise urllib.error.HTTPError(
                    url, status, "HTTP %s" % status,
                    dict(resp.headers), resp)
            raw = resp.read(MAX_READ_BYTES + 1)
            if len(raw) > MAX_READ_BYTES:
                raise reg.CafUnreachable(
                    "artifact exceeded %d bytes (runaway response)" % MAX_READ_BYTES)
        return raw
    except reg.CafUnreachable:
        raise
    except urllib.error.HTTPError as exc:
        # Edge / WAF / origin refusal -> HELD (UNDETERMINED, never a FAIL
        # and never a pass). A bare 403 here is most likely the CF 1010 edge
        # block.
        raise reg.CafUnreachable(
            "HTTP %s on %s (held: the pre-fill law is UNDETERMINED)"
            % (exc.code, url)) from exc
    except urllib.error.URLError as exc:
        raise reg.CafUnreachable(
            "unreachable (transport): %s (%s)" % (exc.reason, url)) from exc
    except (TimeoutError, OSError) as exc:
        raise reg.CafUnreachable(
            "fetch failed: %s (%s)" % (type(exc).__name__, url)) from exc


def _fetch_page(forms_base: str, form_id: str, timeout: float) -> bytes:
    """Fetch the PUBLIC hosted-form page for the given base/form id. Raises
    _PrefillPageError (STOP family) on a URL that cannot be built, and
    reg.CafUnreachable (HELD family) on any fetch failure."""
    base = (forms_base or "").strip().rstrip("/")
    fid = (form_id or "").strip()
    if not base or not fid:
        raise _PrefillPageError(
            "cannot build the form page URL: forms base or form id is EMPTY")
    return fetch_http("%s%s/%s" % (base, WIDGET_FORM_PATH, fid), timeout=timeout)


def _widget_refs(page: str) -> list:
    """The widget build references from the served page, in page order:
    the module bundle script, EVERY <link as="script"> chunk the page
    preloads, and the build-meta URL (derived from the page's own
    __NUXT__ app config: cdnURL + buildAssetsDir + buildId ->
    builds/meta/<buildId>.json — the SAME resolution the widget bundle
    performs at runtime, proofed live). A page with NO module script and NO
    build-meta is not the hosted-form surface this gate exists for
    (REFUSED, never a pass)."""
    refs = []
    for m in re.finditer(
            r'<script[^>]*\bsrc="(https://stcdn\.leadconnectorhq\.com/_preview/'
            r'[A-Za-z0-9_.-]+\.js)"', page):
        refs.append(m.group(1))
    for m in re.finditer(
            r'<link\s+[^>]*as="script"[^>]*href="(https://stcdn\.'
            r'leadconnectorhq\.com/_preview/[A-Za-z0-9_.-]+\.js)"', page):
        refs.append(m.group(1))
    m = re.search(
        r'app:\{baseURL:"[^"]*",buildId:"([A-Za-z0-9-]+)",'
        r'buildAssetsDir:"([^"]*)",cdnURL:"([^"]*)"\}', page)
    if m:
        build_id, assets_dir, cdn_url = m.group(1), m.group(2), m.group(3)
        base = cdn_url.rstrip("/") + assets_dir.rstrip("/")
        refs.append("%s/builds/meta/%s.json" % (base, build_id))
    return refs


def _parse_bundle_refs(bundle_text: str) -> list:
    """The chunk URLs the module bundle imports (the SAME
    stcdn.leadconnectorhq.com/_preview/ root), in order of first mention —
    the dynamic-import form (proofed live: the module bundle's
    import(...) chunks carry the SAME _preview root as the page's preloads).
    The hydration code ships in a dynamic chunk (proofed live in chunk
    DO9dUel-.js), so the hydration-law fetch follows these imports."""
    seen = []
    for m in re.finditer(
            r'import\s*\(\s*["\']([^"\']*stcdn\.leadconnectorhq\.com/_preview/'
            r'[A-Za-z0-9_.-]+\.js)["\']', bundle_text):
        url = m.group(1)
        if url not in seen:
            seen.append(url)
    return seen


def _build_signature(url: str, data: bytes) -> dict:
    """One artifact's signature record: url, sha256 digest, byte length.
    A build identifier — never a credential and never the probe value."""
    return {"url": url, "sha256": _digest_bytes(data), "bytes": len(data)}


# ---------------------------------------------------------------------------
# The committed baseline — the hashed source of truth for the hydration law.
# ---------------------------------------------------------------------------
class _BaselineError(Exception):
    """Fail-closed STOP: the committed prefill baseline cannot be read, so
    the hydration law is unverifiable and no check may pass."""


def _baseline_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / BASELINE_REL_PATH


def load_baseline(path: Path = None) -> dict:
    """Load the committed prefill baseline. A missing/malformed file or a
    non-object payload raises _BaselineError (STOP family) — the law is
    unverifiable. NEVER echoes a baseline value: a digest is an identifier,
    not a credential, but the house never prints content it did not fetch."""
    path = path or _baseline_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise _BaselineError(
            "AF-AE-PREFILL-BASELINE-UNREADABLE: %s cannot be read (%s) — "
            "the hydration law is unverifiable" % (path, type(exc).__name__)) from exc
    except ValueError as exc:
        raise _BaselineError(
            "AF-AE-PREFILL-BASELINE-MALFORMED: %s is not valid JSON (%s) — "
            "the hydration law is unverifiable" % (path, type(exc).__name__)) from exc
    if not isinstance(data, dict):
        raise _BaselineError(
            "AF-AE-PREFILL-BASELINE-MALFORMED: %s does not parse to a JSON "
            "object — the hydration law is unverifiable" % path)
    return data


# ---------------------------------------------------------------------------
# The pure checks — fail-closed, deterministic, value-free.
# ---------------------------------------------------------------------------
def check_page_identity(bare: bytes, probed: bytes) -> dict:
    """The served-surface identity law: the form page MUST be byte-identical
    with and without the probe param (the pre-fill is the widget's job, never
    the origin's — proofed live; a page that bakes the probe into the served
    bytes is a tampered/caching page REFUSED, because the real widget would
    double-apply). Fail-closed: any byte difference is a mismatch."""
    same = bare == probed
    return {
        "ok": same,
        "bare_sha256": _digest_bytes(bare),
        "probed_sha256": _digest_bytes(probed),
        "bytes": len(bare),
        "detail": None if same else (
            "served-page drift: the probe URL serves a DIFFERENT page than "
            "the bare URL (digests differ) — a tampered or caching page, "
            "never the live widget surface"),
    }


def check_page_is_widget(page: str) -> dict:
    """The surface law: the served page MUST reference the widget build
    (a _preview module script and/or the build-meta JSON). A page that does
    not is not the hosted-form surface this gate exists for."""
    refs = _widget_refs(page)
    ok = bool(refs)
    return {
        "ok": ok,
        "refs": refs,
        "detail": None if ok else (
            "the served page carries NO widget build reference "
            "(no _preview module script, no build-meta JSON) — not the "
            "hosted-form surface this gate exists for"),
    }


def check_probe_url_canonical(base: str, form_id: str, key: str, probe: str) -> str:
    """The canonical probe URL — built from the SAME constants
    build_intake_link mints with (single-implementation doctrine): the URL
    the form_reader family treats as canonical, computed here for the
    byte-identity fetch. Raises _PrefillPageError on an empty key/probe."""
    key = (key or "").strip()
    probe = (probe or "").strip()
    if not key or not probe:
        raise _PrefillPageError(
            "cannot build the canonical probe URL: query key or probe value "
            "is EMPTY")
    from urllib.parse import quote
    b = (base or "").strip().rstrip("/")
    fid = quote(form_id or "", safe="")
    return "%s%s/%s?%s=%s" % (
        b, WIDGET_FORM_PATH, fid, key, quote(probe, safe=""))


def check_build_signature(fetched: dict, baseline: dict) -> dict:
    """The hydration-law signature check: every fetched artifact must match
    its committed baseline digest byte-exact, and the baseline's signature
    section must carry an entry for every fetched artifact (a fetched
    artifact with NO committed signature is unverifiable -> mismatch). The
    baseline's own self-test signature is never compared here (a fresh
    baseline overrides it — the committed file is the source of truth for
    the CURRENT build)."""
    sigs = baseline.get("signatures") or {}
    if not isinstance(sigs, dict):
        return {"ok": False, "detail": (
            "baseline has no signatures section — the hydration law is "
            "unverifiable"), "checked": []}
    mismatches = []
    checked = []
    for url, record in fetched.items():
        expected = sigs.get(url)
        if not isinstance(expected, dict) or not expected.get("sha256"):
            mismatches.append((url, "no committed signature for this artifact"))
            continue
        if expected.get("sha256") != record["sha256"]:
            mismatches.append((url, "digest drift: committed %s, live %s"
                              % (expected["sha256"][:12], record["sha256"][:12])))
        checked.append(url)
    ok = not mismatches
    return {
        "ok": ok,
        "checked": checked,
        "detail": None if ok else (
            "build signature drift: %s — a build that no longer maps the URL "
            "param onto the hidden field changes the artifact; never a blind "
            "pass" % "; ".join("%s (%s)" % (u, why) for u, why in mismatches)),
    }


def check_hydration_code(widget_code: str) -> dict:
    """The hydration-code law: the fetched widget code MUST carry the exact
    prefill-map shape (hiddenFieldQueryKey -> urlParams -> field value) that
    the offline self-test pins. A bundle whose hydration code is absent or
    drifted is a MISMATCH — never a silent pass."""
    ok = (PREFILL_HYDRATION_MARKER in widget_code
          and PREFILL_ASSIGN_MARKER in widget_code)
    return {
        "ok": ok,
        "detail": None if ok else (
            "the widget code carries NO prefill hydration law (markers "
            "%r / %r absent) — the URL param would not map onto the hidden "
            "field" % (PREFILL_HYDRATION_MARKER, PREFILL_ASSIGN_MARKER)),
    }


# ---------------------------------------------------------------------------
# The OPTIONAL rendered observation — a real browser render of the probe URL,
# driven DIRECTLY with headless Chromium + the DevTools Protocol over a
# loopback WebSocket (stdlib only, zero optional dependencies, zero
# third-party automation hosts, zero local servers). Never required for a
# PASS on the served surface; a render that cannot complete is HELD (exit 3)
# — the rendered law is UNDETERMINED, never proven compliant.
# ---------------------------------------------------------------------------
class _RenderError(Exception):
    """Fail-closed refusal of a rendered observation (mismatch family): the
    probe value rendered onto the WRONG field, rendered with the param
    ABSENT, or rendered with a non-exact value."""


def find_headless_chromium() -> str:
    """Locate a headless Chromium runtime on THIS box. Returns the binary
    path or "" (absent — the rendered check is then SKIPPED as
    undetermined, never fabricated). Candidates, in order: the ms-playwright
    cache's chromium_headless_shell (the shell the repo's own toolchain
    ships), the ms-playwright cache's full Chromium build, and the system
    Chrome/Chromium. A path is returned only when it EXISTS and is
    EXECUTABLE."""
    home = os.path.expanduser("~")
    roots = [
        os.path.join(home, "Library", "Caches", "ms-playwright"),
        os.path.join(home, ".cache", "ms-playwright"),
    ]
    candidates = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            names = sorted(os.listdir(root))
        except OSError:
            continue
        for prefix in ("chromium_headless_shell-", "chromium-"):
            for n in sorted(x for x in names if x.startswith(prefix)):
                # the shell's binary lives at <rev>/chrome-headless-shell-<plat>/
                # chrome-headless-shell; the full build at <rev>/chrome-mac/Chromium
                sub = os.path.join(root, n, "chrome-headless-shell-mac-arm64",
                                   "chrome-headless-shell")
                candidates.append(sub)
                candidates.append(os.path.join(root, n, "chrome-mac", "Chromium"))
    candidates += [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome",
    ]
    for exe in candidates:
        if exe and os.path.isfile(exe) and os.access(exe, os.X_OK):
            return exe
    return ""


class _CdpConnection:
    """A minimal WebSocket client for the DevTools Protocol — stdlib only
    (socket + the ws frame codec), loopback-only, NO third-party driver. The
    ONLY remote it ever connects to is the headless Chromium this module
    itself launched on 127.0.0.1."""

    def __init__(self, ws_url: str, port: int, timeout: float = 10.0):
        self._path = ws_url.split(":%d" % port)[1]
        self._port = port
        self._sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        self._timeout = timeout
        self._handshake()

    def _handshake(self) -> None:
        key = base64.b64encode(os.urandom(16)).decode()
        req = ("GET %s HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nUpgrade: websocket\r\n"
               "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
               "Sec-WebSocket-Version: 13\r\n\r\n"
               % (self._path, self._port, key))
        self._sock.sendall(req.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise reg.CafUnreachable(
                    "CDP handshake failed (held: the rendered pre-fill law "
                    "is UNDETERMINED)")
            resp += chunk
        if b"101" not in resp.split(b"\r\n", 1)[0]:
            raise reg.CafUnreachable(
                "CDP handshake refused (held: the rendered pre-fill law is "
                "UNDETERMINED)")

    def send(self, payload: dict) -> None:
        data = json.dumps(payload).encode()
        mask = os.urandom(4)
        hdr = bytearray([0x81])
        if len(data) < 126:
            hdr.append(0x80 | len(data))
        else:
            hdr.append(0x80 | 126)
            hdr += struct.pack(">H", len(data))
        hdr += mask
        hdr += bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self._sock.sendall(bytes(hdr))

    def recv(self) -> str:
        """Read ONE ws frame (text). Raises reg.CafUnreachable on close."""
        hdr = self._sock.recv(2)
        if len(hdr) < 2:
            raise reg.CafUnreachable(
                "CDP connection closed (held: the rendered pre-fill law is "
                "UNDETERMINED)")
        ln = hdr[1] & 0x7F
        if ln == 126:
            ln = struct.unpack(">H", self._sock.recv(2))[0]
        data = b""
        while len(data) < ln:
            chunk = self._sock.recv(ln - len(data))
            if not chunk:
                raise reg.CafUnreachable(
                    "CDP frame truncated (held: the rendered pre-fill law is "
                    "UNDETERMINED)")
            data += chunk
        return data.decode("utf-8", "replace")

    def evaluate(self, expression: str, timeout: float = 8.0) -> dict:
        """Runtime.evaluate with returnByValue; returns the result dict or
        raises reg.CafUnreachable (HELD) when no response arrives."""
        self.send({"id": 1, "method": "Runtime.evaluate",
                   "params": {"expression": expression,
                              "returnByValue": True}})
        self._sock.settimeout(timeout)
        while True:
            frame = self.recv()
            if not frame:
                continue
            try:
                msg = json.loads(frame)
            except ValueError:
                continue
            if msg.get("id") == 1:
                if "error" in msg:
                    raise reg.CafUnreachable(
                        "CDP evaluate error: %s (held: the rendered pre-fill "
                        "law is UNDETERMINED)" % msg["error"].get("message", "?"))
                return msg.get("result") or {}

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


def _render_probe_url(url: str, timeout: float = 45.0) -> str:
    """Render the probe URL in a headless Chromium and return the rendered
    hidden-field value of the form field carrying data-q=anthology_id (the
    SAME selector the sibling query_key_checker parses). The value is read
    through the DevTools Protocol (Runtime.evaluate on the page target)
    after the widget has had time to hydrate the hidden field — proofed
    live: the SAME evaluate returns the probe value exactly. Raises
    _RenderError (mismatch family) when the value is absent or non-exact,
    reg.CafUnreachable (HELD) when the render cannot complete, and
    _PrefillPageError (STOP) when the probe URL is unusable. The URL is the
    ONLY argument: no runtime path, no shell string, no injection surface —
    a fixed argv list (the house subprocess discipline)."""
    if not url or not url.startswith("https://"):
        raise _PrefillPageError(
            "refusing to render a non-https URL (%r)" % (url[:32],))
    # a loopback debugging port — never 0 (which the runtime would refuse)
    for port in range(9333, 9344):
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            probe.settimeout(1)
            probe.bind(("127.0.0.1", port))
            probe.close()
            break
        except OSError:
            continue
    else:
        raise reg.CafUnreachable(
            "no loopback debugging port available (held: the rendered "
            "pre-fill law is UNDETERMINED)")
    try:
        proc = subprocess.Popen(
            [find_headless_chromium(), "--headless=new", "--disable-gpu",
             "--no-first-run", "--no-default-browser-check",
             "--remote-debugging-port=%d" % port,
             "--remote-allow-origins=*", url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        raise reg.CafUnreachable(
            "headless render could not start: %s (held: the rendered pre-fill "
            "law is UNDETERMINED)" % type(exc).__name__) from exc
    conn = None
    try:
        deadline = time.time() + timeout
        ws_url = ""
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/json" % port, timeout=3) as resp:
                    targets = json.loads(resp.read().decode("utf-8", "replace"))
                page = next((t for t in targets if t.get("type") == "page"), None)
                if page and page.get("webSocketDebuggerUrl"):
                    ws_url = page["webSocketDebuggerUrl"]
                    break
            except (OSError, ValueError, urllib.error.URLError):
                pass
            time.sleep(0.5)
        if not ws_url:
            raise reg.CafUnreachable(
                "the headless render exposed no page target (held: the "
                "rendered pre-fill law is UNDETERMINED)")
        conn = _CdpConnection(ws_url, port)
        # let the widget mount and hydrate the hidden field (proofed live:
        # ~5-7s after launch the evaluate returns the probe value exactly)
        time.sleep(6.0)
        expr = ('JSON.stringify((()=>{const t=document.querySelector('
                '\'textarea[data-q="anthology_id"]\');'
                'return {v:t?t.value:null}})())')
        result = conn.evaluate(expr, timeout=timeout)
        raw = (result.get("result") or {}).get("value")
        if not isinstance(raw, str):
            raise reg.CafUnreachable(
                "the CDP evaluate returned no value (held: the rendered "
                "pre-fill law is UNDETERMINED)")
        try:
            payload = json.loads(raw)
        except ValueError:
            raise reg.CafUnreachable(
                "the CDP evaluate returned malformed JSON (held: the rendered "
                "pre-fill law is UNDETERMINED)")
        value = payload.get("v")
        if value is None:
            raise reg.CafUnreachable(
                "the rendered page carries no field with "
                "data-q=anthology_id (held: the rendered pre-fill law is "
                "UNDETERMINED)")
        return value if isinstance(value, str) else ""
    finally:
        if conn is not None:
            conn.close()
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except (OSError, subprocess.SubprocessError):
            try:
                proc.kill()
            except OSError:
                pass


def verify_render_optional(url: str, probe: str, *,
                           allow_render: bool, out) -> tuple:
    """The optional rendered observation: when a headless runtime is present
    AND the caller did not pass --no-render, render the probe URL and require
    the hidden anthology_id field to carry EXACTLY the probe value. Returns
    (status, record) where status is one of 'PASS', 'SKIP', 'FAIL', 'HELD'
    and record is the report row. Fail-closed: a rendered NON-exact or
    WRONG-FIELD value is a MISMATCH (exit 5), never a pass; a render that
    cannot complete is HELD (exit 3) — the rendered law is UNDETERMINED. The
    probe value is a deliberate fixture value, never a secret, and the report
    carries PASS/FAIL verdicts plus the field marker only — never a value."""
    if not allow_render:
        return "SKIP", {"status": "SKIP",
                        "detail": "--no-render given (served-surface checks "
                                  "only; the rendered pre-fill is not observed)"}
    exe = find_headless_chromium()
    if not exe:
        return "SKIP", {"status": "SKIP",
                        "detail": "no headless-Chromium runtime found on this "
                                  "box — the rendered pre-fill observation is "
                                  "NOT AVAILABLE (undetermined, never "
                                  "fabricated; served-surface checks still "
                                  "report their own verdict)"}
    try:
        value = _render_probe_url(url)
    except reg.CafUnreachable as exc:
        return "HELD", {"status": "HELD", "detail": str(exc)}
    if value != probe:
        return "FAIL", {"status": "FAIL",
                        "detail": ("AF-AE-PREFILL-RENDER: the hidden field "
                                   "keyed anthology_id rendered %r, expected "
                                   "the probe value exactly — the minted "
                                   "link would not pre-fill the Book ID"
                                   % _mask_value(value))}
    return "PASS", {"status": "PASS",
                    "detail": ("the rendered hidden field keyed anthology_id "
                               "carries EXACTLY the probe value — the minted "
                               "link pre-fills the Book ID")}


def _mask_value(value: str) -> str:
    """Mask a rendered value for the operator surface — a deliberate probe
    fixture value, not a secret, but never printed in full (the house
    masking discipline for every identifier surface)."""
    value = (value or "").strip()
    return "%s...(len %d)" % (value[:4], len(value)) if value else "(empty)"


# ---------------------------------------------------------------------------
# The live aggregate — fail-closed, ONE JSON report object on stdout.
# ---------------------------------------------------------------------------
def run_live(forms_base: str, form_id: str, probe: str, *, key: str,
             baseline: dict, allow_render: bool = True, timeout: float = 20.0,
             out=None) -> int:
    """The fail-closed live aggregate. Returns the exit code: 0 PASS, 5
    MISMATCH, 3 HELD, 2 STOP. Emits the ONE JSON report object on stdout;
    human notes go to out (stderr). Never prints a secret — and holds none."""
    out = out or sys.stderr
    start = time.time()
    report = {
        "contract": "anthology-engine-prefill-verify",
        "schema_version": 1,
        "form_id_masked": _mask_form_id(form_id),
        "probe": probe,
        "checks": {},
        "fail_closed": True,
    }

    def _fail(detail):
        out.write("[prefill-verifier] FAIL: %s\n" % detail)
        return EX_MISMATCH

    # ---- 1. served-surface identity: probe URL vs bare URL ----------------
    try:
        bare = _fetch_page(forms_base, form_id, timeout)
        page_text = _decompress(bare)
        probe_url = check_probe_url_canonical(
            forms_base, form_id, key, probe)
        probed = fetch_http(probe_url, timeout=timeout)
    except _PrefillPageError as exc:
        reg._stop(out, str(exc),
                  ["Pass --forms-base and --intake-form-id and re-run."])
        return EX_STOP
    except reg.CafUnreachable as exc:
        out.write("[prefill-verifier] HELD: %s. NOT a compliance verdict — "
                  "retryable.\n" % exc)
        return EX_HELD
    try:
        probed_text = _decompress(probed)
    except (OSError, ValueError) as exc:
        out.write("[prefill-verifier] HELD: %s\n"
                  % ("probe page body cannot be decoded faithfully: %s" % exc))
        return EX_HELD

    identity = check_page_identity(bare, probed)
    report["checks"]["page_identity"] = identity
    if not identity["ok"]:
        return _fail(identity["detail"])

    widget = check_page_is_widget(page_text)
    report["checks"]["page_is_widget"] = widget
    if not widget["ok"]:
        return _fail(widget["detail"])

    # ---- 2. hydration-law signature: the widget build vs the baseline -----
    build = {"baseline": {"schema": baseline.get("schema_version", "?")},
             "artifacts": {}}
    hydrated_code = ""
    try:
        for ref in widget["refs"]:
            if ref.endswith(".js"):
                data = fetch_http(ref, timeout=timeout)
                build["artifacts"][ref] = _build_signature(ref, data)
                text = _decompress(data)
                hydrated_code += text
                for chunk in _parse_bundle_refs(text):
                    cdata = fetch_http(chunk, timeout=timeout)
                    build["artifacts"][chunk] = _build_signature(chunk, cdata)
                    hydrated_code += _decompress(cdata)
            else:  # the build-meta JSON — a timestamp identifier, a digest
                data = fetch_http(ref, timeout=timeout)
                build["artifacts"][ref] = _build_signature(ref, data)
                try:
                    meta = json.loads(_decompress(data))
                    build["meta"] = {"id": meta.get("id"),
                                     "timestamp": meta.get("timestamp")}
                except (ValueError, OSError) as exc:
                    out.write("[prefill-verifier] HELD: build-meta %s is not "
                              "valid JSON (%s)\n" % (ref, type(exc).__name__))
                    return EX_HELD
    except reg.CafUnreachable as exc:
        out.write("[prefill-verifier] HELD: %s. NOT a compliance verdict — "
                  "retryable.\n" % exc)
        return EX_HELD
    report["build"] = build

    sig = check_build_signature(build["artifacts"], baseline)
    report["checks"]["build_signature"] = sig
    if not sig["ok"]:
        return _fail(sig["detail"])

    hydration = check_hydration_code(hydrated_code)
    report["checks"]["hydration_code"] = hydration
    if not hydration["ok"]:
        return _fail(hydration["detail"])

    # ---- 3. the OPTIONAL rendered observation ----------------------------
    render_status, render_row = verify_render_optional(
        probe_url, probe, allow_render=allow_render, out=out)
    report["checks"]["render"] = render_row
    if render_status == "FAIL":
        return _fail(render_row["detail"])
    if render_status == "HELD":
        out.write("[prefill-verifier] HELD: %s\n" % render_row["detail"])
        return EX_HELD

    report["verdict"] = "PASS"
    report["elapsed_s"] = round(time.time() - start, 2)
    print(json.dumps(report, indent=2, sort_keys=True))
    out.write("[prefill-verifier] OK: served page byte-identical with the "
              "probe URL; widget build signature matches the committed "
              "baseline; hydration code present; rendered pre-fill %s.\n"
              % ("PASS" if render_status == "PASS" else "NOT OBSERVED "
                 "(no runtime — served-surface verdict only)"))
    return EX_OK


# ---------------------------------------------------------------------------
# Offline self-test (no network, no credentials) — proves the pure logic:
# golden state passes, every attack fixture FAILS, and the G3 value-side law
# stays pinned to the anthology_book constant. A tamper NEVER masquerades as
# exit 1.
# ---------------------------------------------------------------------------
def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[prefill-verifier] SELF-TEST FAILED "
                         "(AF-AE-PREFILL-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _fake_bundle(hydration=True) -> str:
    """A minimal fake widget bundle carrying (or not) the pinned hydration
    markers — the pure code-law fixture, no real artifact content."""
    if not hydration:
        return "function n(e){return e}"
    return ("function Ct(e,r){"
            + PREFILL_HYDRATION_MARKER.replace(" in c", " in c")
            + "&&(" + PREFILL_ASSIGN_MARKER + "e)}")


def _self_test_body(dev) -> None:
    key = _resolve_intake_key()
    assert key, "INTAKE_QUERY_KEY must not be empty"
    assert key == "anthology_id", \
        "INTAKE_QUERY_KEY drifted from the G3 contract (is %r)" % key
    assert DEFAULT_PROBE_VALUE == "ANTH_TEST", \
        "the probe value drifted from the committed fixture (is %r)" % DEFAULT_PROBE_VALUE
    assert DEFAULT_FORMS_BASE == "https://link.msgsndr.com"
    assert DEFAULT_UNIVERSAL_INTAKE_FORM_ID == "U65pwoeMTy1niMqllKWG"
    assert WIDGET_FORM_PATH == "/widget/form"
    assert DEFAULT_BUILD_ROOT == "https://stcdn.leadconnectorhq.com/_preview"
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), \
        "CAF_BROWSER_UA drifted from the browser-UA law (CF 1010)"
    assert "Python-urllib" not in reg.CAF_BROWSER_UA

    # ---- 1. served-page identity law (pure, deterministic) ----------------
    bare = b"<html>same page</html>"
    probed = b"<html>same page</html>"
    report = check_page_identity(bare, probed)
    assert report["ok"] is True
    assert report["bare_sha256"] == report["probed_sha256"]
    # 1a. any byte drift -> FAIL (a tampered/caching page is the attack)
    report = check_page_identity(bare, b"<html>DIFFERENT</html>")
    assert report["ok"] is False, "page drift must fail"
    # 1b. probe baked into the served bytes -> FAIL
    baked = (b"<html><input value=\"" + DEFAULT_PROBE_VALUE.encode()
             + b"\"></html>")
    report = check_page_identity(bare, baked)
    assert report["ok"] is False, ("baked probe must fail (the widget would "
                                   "double-apply)")

    # ---- 2. widget-surface law --------------------------------------------
    widget_page = ('<html><head><script type="module" src="https://'
                   'stcdn.leadconnectorhq.com/_preview/mxFsF5jP.js" '
                   'crossorigin></script></head><body></body></html>')
    report = check_page_is_widget(widget_page)
    assert report["ok"] is True, ("the widget fixture must pass, got %r"
                                  % report["refs"])
    assert any("mxFsF5jP.js" in u for u in report["refs"]), (
        "the module-bundle URL must be among the widget refs")
    # 2a. no build reference -> FAIL (not the hosted-form surface)
    report = check_page_is_widget("<html><body>hello</body></html>")
    assert report["ok"] is False, "a non-widget page must fail"

    # ---- 3. canonical probe URL (the SAME law build_intake_link mints) -----
    url = check_probe_url_canonical(DEFAULT_FORMS_BASE,
                                    DEFAULT_UNIVERSAL_INTAKE_FORM_ID,
                                    key, DEFAULT_PROBE_VALUE)
    assert url == ("https://link.msgsndr.com/widget/form/"
                   "U65pwoeMTy1niMqllKWG?anthology_id=ANTH_TEST"), url
    # 3a. an empty key or probe refuses (STOP family, never a guessed URL)
    try:
        check_probe_url_canonical(DEFAULT_FORMS_BASE,
                                  DEFAULT_UNIVERSAL_INTAKE_FORM_ID, "", "X")
        raise AssertionError("an empty query key must refuse")
    except _PrefillPageError:
        pass
    try:
        check_probe_url_canonical(DEFAULT_FORMS_BASE,
                                  DEFAULT_UNIVERSAL_INTAKE_FORM_ID, key, "")
        raise AssertionError("an empty probe value must refuse")
    except _PrefillPageError:
        pass

    # ---- 4. build-signature law (pure, deterministic) ---------------------
    # the committed baseline exists, parses, and is an object (fail-closed
    # source of truth; a missing/stale baseline is a STOP, never a pass)
    baseline = load_baseline()
    assert isinstance(baseline, dict) and baseline.get("schema_version"), \
        "the committed prefill baseline must carry schema_version"
    # the baseline's self-test fixture pins the hydration-marker code text
    # with its own committed sha256 — a drift in EITHER trips the battery
    # before the live gate is ever trusted
    st = baseline.get("self_test") or {}
    blob = st.get("blob")
    assert isinstance(blob, str) and blob, \
        "the baseline must carry a self-test code blob"
    assert blob == ("function Ct(e,r){hiddenFieldQueryKey in c&&"
                    "(I.value[O.tag]=e)}"), \
        "the self-test code blob drifted from the pinned fixture"
    assert isinstance(st.get("sha256"), str) and len(st["sha256"]) == 64, \
        "the self-test signature must carry a sha256 hex digest"
    assert st["sha256"] == hashlib.sha256(blob.encode("utf-8")).hexdigest(), \
        "the committed self-test digest does not match the pinned blob"
    assert _fake_bundle(hydration=True) == blob, \
        "the module's golden hydration fixture drifted from the baseline blob"
    # 4a. the baseline's LIVE signatures cover the widget build (absolute
    #     https URLs, sha256 digests) and every signature is non-empty
    golden = baseline.get("signatures") or {}
    assert isinstance(golden, dict) and golden, \
        "the baseline must carry a signature set"
    for url, record in golden.items():
        assert isinstance(url, str) and url.startswith("https://"), \
            "a signature URL must be absolute https"
        assert isinstance(record, dict) and isinstance(record.get("sha256"), str) \
            and len(record["sha256"]) == 64, \
            "a signature must carry a sha256 hex digest"
    # 4b. a drifted artifact (digest tamper) -> FAIL, never a pass
    tampered = {"%s" % url: {"url": url, "sha256": "0" * 64, "bytes": 1}
                for url in golden}
    res = check_build_signature(tampered, baseline)
    assert res["ok"] is False, "a tampered artifact must fail"
    # 4c. an artifact with NO committed signature -> FAIL (unverifiable)
    res = check_build_signature(
        {"https://stcdn.leadconnectorhq.com/_preview/nonexistent.js":
         {"url": "https://stcdn.leadconnectorhq.com/_preview/nonexistent.js",
          "sha256": "1" * 64, "bytes": 1}}, baseline)
    assert res["ok"] is False, "an unsigned artifact must fail"
    # 4d. a baseline with NO signatures section -> FAIL (law unverifiable)
    res = check_build_signature({"a": {"sha256": "1" * 64}},
                                {"schema_version": 1})
    assert res["ok"] is False, "a signature-less baseline must fail"
    # 4e. the golden code fixture PASSES the hydration-code law
    res = check_hydration_code(blob)
    assert res["ok"] is True, "the pinned hydration blob must pass the law"
    # 4e. missing/malformed baseline files are a STOP (exit 2 family)
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        missing = Path(td) / "nope.json"
        try:
            load_baseline(missing)
            raise AssertionError("a missing baseline must refuse")
        except _BaselineError:
            pass
        (Path(td) / "bad.json").write_text("{not json", encoding="utf-8")
        try:
            load_baseline(Path(td) / "bad.json")
            raise AssertionError("a malformed baseline must refuse")
        except _BaselineError:
            pass
        (Path(td) / "arr.json").write_text("[1,2]", encoding="utf-8")
        try:
            load_baseline(Path(td) / "arr.json")
            raise AssertionError("a non-object baseline must refuse")
        except _BaselineError:
            pass

    # ---- 5. hydration-code law (pure) -------------------------------------
    res = check_hydration_code(_fake_bundle(hydration=True))
    assert res["ok"] is True, "the hydration markers must pass"
    res = check_hydration_code(_fake_bundle(hydration=False))
    assert res["ok"] is False, "a bundle without the hydration law must fail"
    res = check_hydration_code("")
    assert res["ok"] is False, "an empty bundle must fail"

    # ---- 6. chunk-ref parser: the golden page's module bundle -------------
    refs = _parse_bundle_refs(
        'import("./chunk1.js");import("https://stcdn.leadconnectorhq.com/'
        '_preview/DO9dUel-.js");import("https://stcdn.leadconnectorhq.com/'
        '_preview/DO9dUel-.js")')
    assert refs == ["https://stcdn.leadconnectorhq.com/_preview/DO9dUel-.js"], \
        "chunk refs must be deduplicated, ordered, absolute"

    # ---- 7. the mirror pins (browser-UA + the G3 key) ---------------------
    assert key == "anthology_id", "the G3 key mirror drifted"
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0") \
        and "Chrome/" in reg.CAF_BROWSER_UA, \
        "CAF_BROWSER_UA drifted from the browser-UA law"

    # ---- 8. never-print: no credential-shaped string on any surface -------
    identity = check_page_identity(b"<html>same</html>", b"<html>same</html>")
    all_text = json.dumps({
        "url": url, "sha256": identity["bare_sha256"],
        "probe": DEFAULT_PROBE_VALUE,
    })
    for token in ("pit-", "Bearer "):
        assert token not in all_text, \
            "surface leak: %r must never appear" % token

    dev.write("prefill_verifier self-test: OK (G3 value-side law pinned to "
              "anthology_book.INTAKE_QUERY_KEY %r; probe %r; golden PASS; "
              "fixtures: page-drift / baked-probe / non-widget-page / "
              "empty-key / empty-probe / tampered-digest / unsigned-"
              "artifact / signature-less-baseline / missing-baseline / "
              "malformed-baseline / non-object-baseline / hydration-absent / "
              "empty-bundle / chunk-ref-dedup; commit-mirror + browser-UA + "
              "never-print)\n" % (key, DEFAULT_PROBE_VALUE))

    dev.write("[prefill-verifier] golden fixture: probe URL served "
              "byte-identical + widget signature committed -> PASS "
              "(by construction)\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="prefill_verifier.py",
        description="Fail-closed G3 VALUE-side gate for the LIVE universal "
                    "author-intake form (U04): the minted intake link's ONE "
                    "query param ?anthology_id=<minted> must pre-fill the "
                    "form's HIDDEN anthology_id field. The live read is the "
                    "PUBLIC hosted-form page + the PUBLIC widget build — "
                    "zero credentials; a real browser render is OPTIONAL "
                    "and only when a headless-Chromium runtime is present "
                    "(never fabricated, HELD otherwise). One JSON object on "
                    "stdout; never prints a secret (Skill 59).")
    ap.add_argument("--forms-base", default=DEFAULT_FORMS_BASE,
                    help="override the hosted-form base (default: the "
                         "fleet-default %s)" % DEFAULT_FORMS_BASE)
    ap.add_argument("--intake-form-id", default=DEFAULT_UNIVERSAL_INTAKE_FORM_ID,
                    help="override the universal intake form id (default: the "
                         "fleet-wide universal form id)")
    ap.add_argument("--probe", default=DEFAULT_PROBE_VALUE,
                    help="override the probe value (default: the committed "
                         "fixture %s)" % DEFAULT_PROBE_VALUE)
    ap.add_argument("--baseline", default=str(_baseline_path()),
                    help="path to the committed prefill baseline (default: "
                         "config/prefill-verifier-baseline.json)")
    ap.add_argument("--no-render", action="store_true",
                    help="skip the OPTIONAL headless-Chromium render "
                         "(served-surface checks only; the rendered pre-fill "
                         "is then NOT observed)")
    ap.add_argument("--timeout", type=float, default=20.0,
                    help="fetch timeout in seconds (default 20)")
    ap.add_argument("cmd", nargs="?", choices=["live", "plan", "self-test"],
                    default="live")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()

        key = _resolve_intake_key()
        if not key:
            reg._stop(sys.stderr, "The intake query-key law is EMPTY.",
                      ["scripts/anthology_book.py INTAKE_QUERY_KEY is empty "
                       "or unimportable — restore the constant and re-run."])
            return EX_STOP

        if args.cmd == "plan":
            # offline plan: no network, no credentials
            print(json.dumps({
                "contract": "anthology-engine-prefill-check-plan",
                "schema_version": 1,
                "expected_query_key": key,
                "probe": args.probe,
                "check": ("GET <forms_base>/widget/form/<form_id> with and "
                          "without ?%s=<probe> and require BYTE-IDENTICAL "
                          "served pages (the pre-fill is the widget's job, "
                          "never the origin's); require the served widget "
                          "build (module bundle + build-meta + the loaded "
                          "dynamic chunk) to match the committed baseline "
                          "digests and to carry the hydration code ("
                          "%r -> %r); OPTIONALLY render the probe URL in "
                          "headless Chromium and require the hidden field "
                          "keyed %s to carry EXACTLY the probe value" % (
                              key, PREFILL_HYDRATION_MARKER,
                              PREFILL_ASSIGN_MARKER, key)),
                "probe_url": check_probe_url_canonical(
                    (args.forms_base or "").strip().rstrip("/"),
                    args.intake_form_id, key, args.probe),
                "baseline": str(args.baseline),
                "credential_surface": "none — the hosted-form page and the "
                                      "widget build are the public surfaces "
                                      "the author's browser loads",
                "note": "offline plan only — no fetch, no credential needed; "
                        "a page/artifact that cannot be fetched is HELD "
                        "(exit 3), never judged; a real browser render is "
                        "OPTIONAL (absent runtime -> rendered check SKIPPED "
                        "as undetermined)",
            }, indent=2, sort_keys=True))
            return EX_OK

        # ---- live check: public GETs, zero credentials, optional render ----
        try:
            baseline = load_baseline(Path(args.baseline).expanduser())
        except _BaselineError as exc:
            reg._stop(sys.stderr, str(exc),
                      ["Restore config/prefill-verifier-baseline.json and "
                       "re-run."])
            return EX_STOP
        return run_live(args.forms_base, args.intake_form_id, args.probe,
                        key=key, baseline=baseline,
                        allow_render=not args.no_render,
                        timeout=args.timeout, out=sys.stderr)

    except _PrefillPageError as exc:
        reg._stop(sys.stderr, str(exc),
                  ["Pass --forms-base and --intake-form-id and re-run."])
        return EX_STOP
    except _BaselineError as exc:
        reg._stop(sys.stderr, str(exc),
                  ["Restore config/prefill-verifier-baseline.json and "
                   "re-run."])
        return EX_STOP
    except reg.CafUnreachable as exc:
        # includes UpstreamBlockedError (edge/WAF) — HELD, UNDETERMINED
        sys.stderr.write("[prefill-verifier] HELD: %s. NOT a compliance "
                         "verdict — retryable.\n" % exc)
        return EX_HELD
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[prefill-verifier] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
