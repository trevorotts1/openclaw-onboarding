#!/usr/bin/env python3
# =============================================================================
# SKILL 59 - ANTHOLOGY ENGINE :: cover_render.py   (unit W1.14)
# THE COVER RENDER ADAPTER (SPEC Section 4 S7, Section 8.1 IMAGE tier,
# Section 10.4; script inventory row 13; ENGINE-MANIFEST S7 IMAGE)
# -----------------------------------------------------------------------------
# A Layer 3 delivery adapter (SPEC 2.3): a STATELESS function with explicit
# inputs whose only "external write" (the render + download) is followed by a
# read-back verification in the SAME job (the downloaded PNG is parsed and its
# portrait geometry is proven before the adapter reports success).
#
# WHAT IT DOES (S7 render leg only): takes the image prompt produced by the
# Layer 1 cover-prompt generator (pin aw-11, the Senior Book-Cover Design
# Specialist, structured image-prompt object) and renders the book cover on the
# CLIENT's OWN Kie.ai account using model GPT-image-2 against the TEXT-TO-IMAGE
# PORTRAIT endpoint LIVE-VERIFIED at Wave 0 (W0.6.json). It submits createTask,
# waits with a bounded re-poll of recordInfo, downloads the result PNG to a
# local target path, and proves the file is a real portrait 1024x1536 PNG on
# disk. The stage runner (stage_s7_cover.py) then hands the local PNG to
# drive_adapter.py (Drive landing) and records the artifact via anthology_state
# with BOTH cover link fields; caf_delivery.py (S8) fills the media-storage
# link. This adapter therefore RENDERS + VERIFIES and NAMES both link fields;
# it never itself writes Drive or Convert and Flow.
#
# THE PORTRAIT OVERRIDE (the reason this unit exists): Skill 46's slide
# submitter DEFAULTS aspect_ratio to "16:9" (its presentation recipe). A cover
# MUST be PORTRAIT. This adapter pins aspect_ratio "2:3" (which W0.6 measured to
# yield exactly 1024x1536, height > width) and STRUCTURALLY REFUSES any
# landscape ratio, so a cover can never render 16:9. The 16:9 image-to-image
# presentation recipe is a DIFFERENT endpoint shape and is NEVER reused here.
#
# THE KIE CONTRACT (pattern of record: Skill 46 kie-slide-submitter.js +
# box-kv-poller.js; live shape of record: W0.6.json). Skills 07/46 are the
# pattern reference exactly as Skill 14 is only a pattern reference for
# drive_adapter.py (SPEC 10.1): this adapter calls the Kie REST endpoints
# DIRECTLY with the Python standard library, reusing the verified createTask /
# recordInfo / allowlist / browser-User-Agent-download facts, so the engine's
# delivery layer stays stdlib-only with no Node runtime dependency.
#   createTask : POST https://api.kie.ai/api/v1/jobs/createTask
#                model "gpt-image-2-text-to-image",
#                input {prompt, aspect_ratio "2:3", output_format "png"}
#   recordInfo : GET  https://api.kie.ai/api/v1/jobs/recordInfo?taskId=...
#                data.state in {waiting,queuing,generating,success,fail};
#                data.resultJson -> resultUrls[] (or images[].url)
#   download   : result CDN host is allowlisted; the CDN 403s the default
#                urllib UA, so a browser User-Agent is REQUIRED (W0.6).
# SINGLE-IMAGE PATH: a cover is ONE image, so deck size 1 <= callback threshold
# 5 => useCallbacks=false (Skill 46 fix 33): the box SKIPS the callback Worker
# and polls recordInfo DIRECTLY. That direct bounded poll IS the "bounded
# re-poll"; on exhaustion the adapter HOLDS (exit 3) so hold_queue.py +
# alert-dedup.py fire the durable hold and the ONE deduped founder alert. The
# large-deck callback relay is proven alive (W0.6) but is not on the cover path.
#
# CRASH-SAFE + COST-SAFE (SPEC 2.2 idempotency): a render-state sidecar written
# BEFORE the paid createTask lets a re-run RESUME an in-flight taskId instead of
# paying twice; a completed render with the PNG already on disk is an idempotent
# no-op success.
#
# EXIT CODE CONTRACT (ENGINE-MANIFEST row 13: "0 PNG landed; 3 callback lost
# after re-poll (held)", widened to the house set of SPEC 3.4 while keeping 0/3
# as the primary axis; classify_child_rc in stage_s7_cover.py maps 3 -> HELD):
#   0  PNG landed: rendered, downloaded, and PROVEN portrait on disk
#      (INCLUDING an idempotent replay no-op)
#   1  unexpected error
#   2  validation / guard refusal (misuse: missing prompt or output path, an
#      explicitly requested LANDSCAPE aspect ratio, a literal-key input)
#   3  HELD (the durable hold path, held_reason carries the cause): callback /
#      poll lost after the bounded re-poll ceiling, insufficient credits (402),
#      provider auth failure (401), provider unreachable, the Kie credential
#      NOT SET, or a result that could not be proven a portrait PNG on disk
#      (nothing landed -> hold for a retry). Never emits 5, so it can never be
#      mis-mapped to the SLOT-unresolved lane.
#
# DOCTRINE: move in silence (operator-verbose only, never client-facing);
# NOTHING Anthropic in this runtime file; Convert and Flow naming in every
# client surface; the Kie key is resolved BY LABEL from the client env stores
# (live process env first) and is NEVER printed (SET / NOT SET only) and NEVER
# hardcoded; writes run as the node user, never root. STDLIB ONLY (urllib +
# json + hashlib): zero third-party deps; the self-test makes ZERO network
# calls and spends ZERO credits.
# =============================================================================
"""cover_render.py - the Kie.ai GPT-image-2 portrait cover render adapter (S7)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------- #
# Locations
# --------------------------------------------------------------------------- #
SKILL_DIR = Path(__file__).resolve().parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"

# --------------------------------------------------------------------------- #
# Kie contract (W0.6.json live-verified; Skill 46 pattern of record)
# --------------------------------------------------------------------------- #
DEFAULT_KIE_BASE_URL = "https://api.kie.ai"
CREATE_TASK_PATH = "/api/v1/jobs/createTask"
RECORD_INFO_PATH = "/api/v1/jobs/recordInfo"

# Primary cover model (W0.6): the TEXT-TO-IMAGE portrait model, NOT the
# image-to-image presentation recipe.
COVER_MODEL = "gpt-image-2-text-to-image"

# THE OVERRIDE. Skill 46's submitter defaults aspect_ratio to "16:9"; a cover is
# portrait, so this adapter pins "2:3" (W0.6: 2:3 -> exactly 1024x1536).
SKILL46_DEFAULT_ASPECT = "16:9"          # documented ONLY to be overridden
COVER_ASPECT = "2:3"                     # portrait; the pinned cover ratio
COVER_WIDTH, COVER_HEIGHT = 1024, 1536   # W0.6 measured portrait geometry
OUTPUT_FORMAT = "png"

# --------------------------------------------------------------------------- #
# The four config-pinned NAMED cover styles (U8 / B8). ALL FOUR render on the
# SAME image model + the SAME portrait 2:3 endpoint this adapter already uses;
# the ONLY thing that differs per style is a STYLE DIRECTION appended to the
# aw-11 base cover prompt (apply_style). Exactly ONE style -- "Pure Type" -- is
# STRICTLY typography-driven: no pictorial imagery at all. The ORDER is
# authoritative and maps 1:1 to config/field-map.json cover_style_fields:
# COVER_STYLES[i].slot == sample_url_fields[str(slot)], and STYLE_NAMES (in this
# order) == choice_options (the SINGLE_OPTIONS picklist the client picks from).
# The client receives all four and picks their favourite; the producer approves
# the SET (no down-select). Never rename a style without re-stamping field-map's
# choice_options + slot mapping -- the coherence is self-tested.
# --------------------------------------------------------------------------- #
COVER_STYLES = (
    {
        "key": "signature",
        "name": "Signature",
        "slot": 1,
        "typography_only": False,
        "directive": (
            "Render the flagship, market-ready book cover: a single strong focal "
            "image or conceptual symbol executed with photographic/illustrative "
            "polish, a disciplined 2-3 colour palette, premium foil-quality finish, "
            "and a confident typographic hierarchy. This is the bestseller-shelf "
            "default -- balanced, iconic, and instantly legible at thumbnail."
        ),
    },
    {
        "key": "bold_editorial",
        "name": "Bold Editorial",
        "slot": 2,
        "typography_only": False,
        "directive": (
            "Render a bold magazine-editorial cover: an OVERSIZED, dominant "
            "sans-serif title that fills the composition, aggressive high-contrast "
            "colour blocking, a strict grid, and at most one restrained graphic "
            "accent. Punchy, contemporary, and unmistakably loud on a shelf -- "
            "typography leads, imagery is secondary and minimal."
        ),
    },
    {
        "key": "fine_art",
        "name": "Fine Art",
        "slot": 3,
        "typography_only": False,
        "directive": (
            "Render a painterly, literary fine-art cover: textured, gallery-quality "
            "artwork with a sophisticated muted palette, layered metaphorical "
            "imagery, generous contemplative negative space, and an elegant serif "
            "title set with refined tracking. Understated, timeless, and premium."
        ),
    },
    {
        "key": "pure_type",
        "name": "Pure Type",
        "slot": 4,
        "typography_only": True,
        "directive": (
            "Render a strictly TYPE-DRIVEN cover: the design is built ENTIRELY from "
            "the locked title, subtitle, and author byline as expressive editorial "
            "typography on a solid or subtly-toned colour field. Dramatic scale and "
            "weight contrast, deliberate kerning and alignment, and commanding "
            "negative space carry the whole cover."
        ),
    },
)
STYLE_NAMES = tuple(s["name"] for s in COVER_STYLES)
STYLE_KEYS = tuple(s["key"] for s in COVER_STYLES)

STYLE_BLOCK_HEADER = "=== COVER STYLE DIRECTION (render this exact cover in the named style) ==="

# The strict no-imagery constraint appended ONLY for the typography-only style so
# the render can never fall back to a photographic/illustrative composition.
TYPE_ONLY_CONSTRAINT = (
    "STRICT TYPOGRAPHY-ONLY COVER: this cover contains NO photographic, "
    "illustrative, pictorial, or figurative imagery of ANY kind -- no people, "
    "objects, scenes, subject-textures, or decorative illustration. Compose the "
    "ENTIRE cover from TYPOGRAPHY and flat colour alone. Keep it portrait 2:3 and "
    "thumbnail-legible; the locked title, subtitle, and byline are reproduced "
    "faithfully and carry the whole design."
)

STYLE_SET_CONTRACT = "anthology-engine-cover-style-set-render"

# Kie result-CDN allowlist (Skill 46 box-kv-poller KIE_RESULT_HOSTS; W0.6
# observed tempfile.aiquickdraw.com serving a live cover result).
KIE_RESULT_HOSTS = (
    "tempfile.aiquickdraw.com",
    "tempfileb.aiquickdraw.com",
    "static.aiquickdraw.com",
    "tempfile.redpandaai.co",
)

# W0.6: the Kie result CDN 403s urllib's default User-Agent; a browser UA
# succeeds. Required for the result download only, sent on every call for safety.
MOZILLA_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Conventional Kie credential labels (Skill 07: KIE_API_KEY). The resolved label
# per box may be anything (model-map IMAGE tier <CLIENT_KIE_KEY_LABEL>); the
# caller may override with --key-label. Values are NEVER printed.
DEFAULT_KEY_LABELS = ("KIE_API_KEY",)
DEFAULT_BASE_URL_LABELS = ("KIE_BASE_URL",)

# The Kie account-credit balance endpoint (W0.9) -- read-only, zero generation
# tokens; used only to classify a pre-flight (never a mandatory gate here).
CREDIT_PATH = "/api/v1/chat/credit"

# Bounded re-poll defaults (Skill 46 box-kv-poller fallback ceiling 10 min).
DEFAULT_POLL_INTERVAL_S = 5.0
DEFAULT_POLL_CEILING_S = 600.0
DEFAULT_POLL_BACKOFF_MAX_S = 30.0
DEFAULT_CREATE_TIMEOUT_S = 30.0
DEFAULT_DOWNLOAD_TIMEOUT_S = 120.0

# Exit codes (see the module header).
EX_OK, EX_ERR, EX_REFUSE, EX_HELD = 0, 1, 2, 3

# Held reason vocabulary (held_reason on the result manifest / exit 3).
HELD_CREDENTIAL_NOT_SET = "credential_not_set"
HELD_CREDIT_OUT = "credit_out"
HELD_AUTH = "auth"
HELD_PROVIDER_UNREACHABLE = "provider_unreachable"
HELD_CALLBACK_LOST = "callback_lost"
HELD_TASK_FAILED = "task_failed"
HELD_RENDER_NOT_PORTRAIT = "render_not_portrait"
HELD_DOWNLOAD_FAILED = "download_failed"

RESULT_CONTRACT = "anthology-engine-cover-render-result"


# --------------------------------------------------------------------------- #
# Small utilities (doctrine: never print a secret value)
# --------------------------------------------------------------------------- #
def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(msg: str) -> None:
    """Operator-verbose, stderr only (never a client surface)."""
    sys.stderr.write("[cover_render] %s\n" % msg)


def _env_first(names):
    """First present, non-empty env value among `names`. Returns (name, value)
    or (None, None). NEVER prints the value (doctrine: SET / NOT SET only).
    Mirrors anthology_state.py._env_first so credential resolution is uniform."""
    for n in names:
        v = os.environ.get(n, "")
        if v and v.strip():
            return n, v.strip()
    return None, None


def _parse_aspect(ar):
    """'a:b' -> (a, b) positive ints, else None."""
    m = re.match(r"^\s*(\d+)\s*:\s*(\d+)\s*$", ar or "")
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    if a <= 0 or b <= 0:
        return None
    return a, b


def _is_portrait_ratio(ar) -> bool:
    """True only for a taller-than-wide ratio (a < b). 16:9 -> False; 2:3 -> True."""
    p = _parse_aspect(ar)
    return bool(p and p[0] < p[1])


def _png_dimensions(data: bytes):
    """(width, height) parsed from a PNG's IHDR header, else None. STDLIB only:
    8-byte signature, then IHDR chunk length(4) 'IHDR' width(4) height(4)."""
    sig = b"\x89PNG\r\n\x1a\n"
    if not data or len(data) < 24 or data[:8] != sig or data[12:16] != b"IHDR":
        return None
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    if width <= 0 or height <= 0:
        return None
    return width, height


def _host_allowlisted(url: str) -> bool:
    """Result URL host must be a known Kie CDN (exact or a subdomain)."""
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    return any(host == h or host.endswith("." + h) for h in KIE_RESULT_HOSTS)


def _looks_like_literal_key(s: str) -> bool:
    """Guard: refuse a prompt/argument that carries a literal provider key shape
    (the legacy cover node's exposed-key defect this engine deletes). Requires a
    REALISTIC key shape -- a non-alphanumeric LEFT BOUNDARY plus a LENGTH FLOOR --
    so ordinary hyphenated English that is common in business/entrepreneurship
    cover art direction ('risk-taking', 'task-oriented', 'task-master',
    'desk-bound', 'dusk-lit', 'mask-like') is NOT a false positive, while every
    real leaked provider key still trips (OpenAI/OpenRouter keys carry 40+ key
    chars after the prefix, far above the 16-char floor). The prior
    'sk-[A-Za-z0-9]' matched only 'sk-' + one alnum and false-refused those words.
    Never logs the matched text."""
    if not s:
        return False
    patterns = (
        # sk- / sk-proj- / sk-or-v1- provider keys. The left-boundary lookbehind
        # rejects 'ri[sk-]taking'/'ta[sk-]oriented' (preceded by a letter); the
        # {16,} floor rejects any short hyphenated word even at a word boundary.
        r"(?<![A-Za-z0-9])sk-(?:or-v1-|proj-)?[A-Za-z0-9_-]{16,}",
        # A literal bearer token (>=16 token chars after the scheme).
        r"Bearer\s+[A-Za-z0-9._-]{16,}",
    )
    return any(re.search(p, s) for p in patterns)


# --------------------------------------------------------------------------- #
# HTTP (stdlib urllib; captures 4xx/5xx status instead of raising through)
# --------------------------------------------------------------------------- #
class _Resp:
    __slots__ = ("status", "json", "raw", "error_reason")

    def __init__(self, status=0, data=None, raw=b"", error_reason=None):
        self.status = status
        self.json = data
        self.raw = raw
        self.error_reason = error_reason


def _request(url, method="GET", headers=None, body=None, timeout=30.0, want_json=True):
    """One HTTP call. Returns _Resp. Never raises for an HTTP status; a transport
    failure (URLError / socket) yields status 0 with error_reason set. The Kie
    key rides only in the Authorization header the caller supplies; never logged."""
    data = None
    hdrs = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    hdrs.setdefault("User-Agent", MOZILLA_UA)
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None) or resp.getcode()
            parsed = None
            if want_json and raw:
                try:
                    parsed = json.loads(raw.decode("utf-8"))
                except Exception:
                    parsed = None
            return _Resp(status=status, data=parsed, raw=raw)
    except urllib.error.HTTPError as e:
        raw = b""
        try:
            raw = e.read()
        except Exception:
            pass
        parsed = None
        if want_json and raw:
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except Exception:
                parsed = None
        return _Resp(status=e.code, data=parsed, raw=raw, error_reason="http_%s" % e.code)
    except urllib.error.URLError as e:
        return _Resp(status=0, error_reason="urlerror:%s" % getattr(e, "reason", "unknown"))
    except Exception as e:  # timeout, socket, etc.
        return _Resp(status=0, error_reason="transport:%s" % type(e).__name__)


# --------------------------------------------------------------------------- #
# Field map (read-only): the cover link-field pair this adapter NAMES so the
# downstream artifact-record captures BOTH cover link fields.
# --------------------------------------------------------------------------- #
def _cover_link_fields():
    """Return {"cover_image_field": <media-storage key>, "cover_drive_field":
    <Drive key>} from config/field-map.json. Falls back to the known PRD Section
    6 keys if the map is unreadable (the map is the source of truth; this adapter
    only READS it -- provisioning creates/verifies the keys)."""
    image_field = "contact.anthology_cover_image_url"   # Convert and Flow media link (caf_delivery, S8)
    drive_field = "contact.anthology_cover_drive_url"   # Drive link (drive_adapter)
    try:
        fm = json.loads(FIELD_MAP_PATH.read_text(encoding="utf-8"))
        cover = (fm.get("deliverable_fields") or {}).get("cover") or {}
        image_field = cover.get("doc_url", image_field)  # cover doc_url == media-storage image link
        drive_field = cover.get("pdf_url", drive_field)  # cover pdf_url == Drive link
    except Exception:
        pass
    return {"cover_image_field": image_field, "cover_drive_field": drive_field}


# --------------------------------------------------------------------------- #
# Render-state sidecar (crash-safe + cost-safe resume; SPEC 2.2)
# --------------------------------------------------------------------------- #
def _state_path(out_png: Path) -> Path:
    return out_png.with_suffix(out_png.suffix + ".render-state.json")


def _read_state(out_png: Path):
    try:
        return json.loads(_state_path(out_png).read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_state(out_png: Path, state: dict) -> None:
    p = _state_path(out_png)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(p))


# --------------------------------------------------------------------------- #
# The request body (createTask). aspect_ratio is ALWAYS the portrait override.
# --------------------------------------------------------------------------- #
def build_create_body(prompt, model=COVER_MODEL, aspect=COVER_ASPECT,
                      resolution=None, callback_url=None):
    """Assemble the createTask body. resolution is OMITTED unless explicitly set
    (W0.6: default yields 1024x1536; re-measure if resolution is raised).
    callback_url is included ONLY for the large-deck callback path (never for a
    single cover)."""
    body = {
        "model": model,
        "input": {
            "prompt": prompt,
            "aspect_ratio": aspect,
            "output_format": OUTPUT_FORMAT,
        },
    }
    if resolution:
        body["input"]["resolution"] = resolution
    if callback_url:
        body["callBackUrl"] = callback_url
    return body


# --------------------------------------------------------------------------- #
# Named cover styles (U8): specialize the aw-11 BASE prompt into a per-style
# prompt. Pure + deterministic + network-free (the differentiation is ALL in the
# prompt; the model, endpoint, and portrait geometry are identical for all four).
# --------------------------------------------------------------------------- #
def _coerce_style(style):
    """Accept a style dict (from COVER_STYLES), a style key ('pure_type'), or a
    style name ('Pure Type'); return the canonical style dict. Raise ValueError on
    an unknown selector."""
    if isinstance(style, dict):
        return style
    if isinstance(style, str):
        s = style.strip().lower()
        for st in COVER_STYLES:
            if st["key"].lower() == s or st["name"].lower() == s:
                return st
    raise ValueError("unknown cover style %r (known: %s)"
                     % (style, ", ".join("%s/%s" % (st["key"], st["name"]) for st in COVER_STYLES)))


def apply_style(base_prompt, style):
    """Return the aw-11 BASE cover prompt specialized into ONE named style. Same
    image model, same portrait 2:3 geometry; only the appended STYLE DIRECTION (and,
    for the typography-only style, the strict no-imagery constraint) differs."""
    st = _coerce_style(style)
    parts = [(base_prompt or "").rstrip(), "", STYLE_BLOCK_HEADER,
             "STYLE NAME: %s" % st["name"], st["directive"]]
    if st.get("typography_only"):
        parts += ["", TYPE_ONLY_CONSTRAINT]
    return "\n".join(parts)


def _extract_result_urls(data: dict):
    """Pull image URLs out of a recordInfo 'success' payload. data.resultJson is
    a JSON string (W0.6) -> resultUrls[]; also tolerate images[].url and
    resultImageUrl (Skill 46 box-kv-poller._extractResultJsonUrls)."""
    rj = (data or {}).get("resultJson")
    if isinstance(rj, str):
        try:
            rj = json.loads(rj)
        except Exception:
            rj = None
    urls = []
    if isinstance(rj, dict):
        if isinstance(rj.get("resultUrls"), list):
            urls += [u for u in rj["resultUrls"] if isinstance(u, str)]
        if isinstance(rj.get("images"), list):
            urls += [i.get("url") for i in rj["images"] if isinstance(i, dict) and i.get("url")]
        if isinstance(rj.get("resultImageUrl"), str):
            urls.append(rj["resultImageUrl"])
    # Some shapes surface resultUrls at the top level of data.
    if isinstance((data or {}).get("resultUrls"), list):
        urls += [u for u in data["resultUrls"] if isinstance(u, str)]
    # De-dup, preserve order.
    seen, out = set(), []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


# --------------------------------------------------------------------------- #
# The render (the one paid, external step) + read-back verification
# --------------------------------------------------------------------------- #
class RenderHeld(Exception):
    """A non-fatal 'cannot complete now' -> exit 3 with a typed held_reason."""

    def __init__(self, reason, detail=""):
        super().__init__("%s: %s" % (reason, detail))
        self.reason = reason
        self.detail = detail


def _kie_headers(key):
    return {"Authorization": "Bearer %s" % key, "Content-Type": "application/json"}


def _create_task(base_url, key, body, timeout):
    r = _request(base_url + CREATE_TASK_PATH, method="POST", headers=_kie_headers(key),
                 body=body, timeout=timeout)
    if r.status == 402:
        raise RenderHeld(HELD_CREDIT_OUT, "createTask 402 insufficient credits")
    if r.status in (401, 403):
        raise RenderHeld(HELD_AUTH, "createTask %s unauthorized" % r.status)
    if r.status == 0:
        raise RenderHeld(HELD_PROVIDER_UNREACHABLE, r.error_reason or "createTask transport")
    j = r.json or {}
    task_id = (j.get("data") or {}).get("taskId")
    if r.status != 200 or (j.get("code") not in (200, None)) or not task_id:
        # A non-200 body code is a provider-side rejection; hold for retry.
        raise RenderHeld(HELD_PROVIDER_UNREACHABLE,
                         "createTask code=%s status=%s" % (j.get("code"), r.status))
    return task_id


def _poll_record_info(base_url, key, task_id, interval_s, ceiling_s, backoff_max_s):
    """Bounded re-poll of recordInfo. Returns result URLs on success; raises
    RenderHeld(callback_lost) at the ceiling and RenderHeld(task_failed) on a
    provider 'fail' state. Backoff respects Kie's 10-req/s query budget."""
    deadline = time.monotonic() + ceiling_s
    delay = interval_s
    url = base_url + RECORD_INFO_PATH + "?taskId=" + urllib.parse.quote(task_id, safe="")
    hdrs = {"Authorization": "Bearer %s" % key}
    last_state = "unknown"
    while time.monotonic() < deadline:
        time.sleep(delay)
        r = _request(url, method="GET", headers=hdrs, timeout=30.0)
        if r.status == 0:
            # Transient transport blip: back off and keep polling within ceiling.
            delay = min(delay * 2.0, backoff_max_s)
            continue
        if r.status in (401, 403):
            raise RenderHeld(HELD_AUTH, "recordInfo %s unauthorized" % r.status)
        data = (r.json or {}).get("data") or {}
        state = data.get("state", "unknown")
        last_state = state
        if state == "success":
            urls = _extract_result_urls(data)
            safe = [u for u in urls if _host_allowlisted(u)]
            if not safe:
                # 'success' with zero allowlisted URLs is not a landed render.
                raise RenderHeld(HELD_DOWNLOAD_FAILED, "success but 0 allowlisted result URLs")
            return safe
        if state == "fail":
            raise RenderHeld(HELD_TASK_FAILED,
                             "failCode=%s" % data.get("failCode"))
        # waiting | queuing | generating -> backoff and continue.
        delay = min(delay * 1.5, backoff_max_s)
    raise RenderHeld(HELD_CALLBACK_LOST,
                     "recordInfo ceiling %.0fs reached, last state=%s" % (ceiling_s, last_state))


def _download_and_verify(urls, out_png: Path, timeout):
    """Download the first allowlisted URL that yields a valid PORTRAIT PNG, write
    it to out_png, and return (source_url, width, height, sha256). Raises
    RenderHeld on download failure or a non-portrait result (nothing landed)."""
    last_reason = "no urls"
    for u in urls:
        if not _host_allowlisted(u):
            _log("result URL host not allowlisted; dropping")
            continue
        req = urllib.request.Request(u, method="GET", headers={"User-Agent": MOZILLA_UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = getattr(resp, "status", None) or resp.getcode()
                if status != 200:
                    last_reason = "http %s" % status
                    continue
                data = resp.read()
        except Exception as e:
            last_reason = "download:%s" % type(e).__name__
            continue
        dims = _png_dimensions(data)
        if not dims:
            last_reason = "not a PNG"
            continue
        width, height = dims
        if not (height > width):
            # The whole point of this unit: a cover must be portrait.
            raise RenderHeld(HELD_RENDER_NOT_PORTRAIT,
                             "rendered %dx%d is not portrait (height must exceed width)"
                             % (width, height))
        out_png.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_png.with_suffix(out_png.suffix + ".part")
        tmp.write_bytes(data)
        os.replace(str(tmp), str(out_png))
        sha = hashlib.sha256(data).hexdigest()
        return u, width, height, sha
    raise RenderHeld(HELD_DOWNLOAD_FAILED, last_reason)


# --------------------------------------------------------------------------- #
# The public entry: render()
# --------------------------------------------------------------------------- #
def render(prompt, out_png: Path, participant_key="",
           base_url=None, key_labels=DEFAULT_KEY_LABELS, model=COVER_MODEL,
           aspect=COVER_ASPECT, resolution=None, style=None,
           poll_interval_s=DEFAULT_POLL_INTERVAL_S,
           poll_ceiling_s=DEFAULT_POLL_CEILING_S,
           poll_backoff_max_s=DEFAULT_POLL_BACKOFF_MAX_S,
           create_timeout_s=DEFAULT_CREATE_TIMEOUT_S,
           download_timeout_s=DEFAULT_DOWNLOAD_TIMEOUT_S):
    """Render the cover and return (exit_code, result_manifest). Never prints a
    secret. On any 'cannot complete now' condition returns (EX_HELD, manifest
    with status 'held' + held_reason) so hold_queue.py + alert-dedup.py own the
    durable hold and the single deduped founder alert."""
    link_fields = _cover_link_fields()
    manifest = {
        "contract": RESULT_CONTRACT,
        "schema_version": 1,
        "participant_key": participant_key,
        "model": model,
        "aspect_ratio": aspect,
        "style": None,
        "target_dimensions": {"width": COVER_WIDTH, "height": COVER_HEIGHT, "portrait": True},
        "link_fields": link_fields,
        "local_png_path": str(out_png),
        "task_id": None,
        "source_url": None,
        "dimensions": None,
        "sha256": None,
        "status": None,
        "held_reason": None,
        "rendered_at": None,
    }

    # --- Guard: the portrait override is structural. A cover is NEVER landscape.
    if not _is_portrait_ratio(aspect):
        _log("REFUSE: aspect_ratio %r is not portrait (a cover must be portrait; "
             "Skill 46 default %r is overridden to %r)"
             % (aspect, SKILL46_DEFAULT_ASPECT, COVER_ASPECT))
        manifest["status"] = "refused"
        manifest["held_reason"] = "non_portrait_aspect"
        return EX_REFUSE, manifest

    # --- Guard: prompt present and free of a literal key shape.
    if not prompt or not prompt.strip():
        _log("REFUSE: empty cover prompt (expected the aw-11 structured image prompt)")
        manifest["status"] = "refused"
        manifest["held_reason"] = "empty_prompt"
        return EX_REFUSE, manifest
    if _looks_like_literal_key(prompt):
        _log("REFUSE: the cover prompt contains a literal credential shape; refused")
        manifest["status"] = "refused"
        manifest["held_reason"] = "literal_key_in_prompt"
        return EX_REFUSE, manifest

    # --- Named style (U8): specialize the base prompt. Same model + portrait
    #     geometry; ONLY the appended STYLE DIRECTION differs. Unknown -> refuse.
    style_dict = None
    if style is not None:
        try:
            style_dict = _coerce_style(style)
        except ValueError as exc:
            _log("REFUSE: %s" % exc)
            manifest["status"] = "refused"
            manifest["held_reason"] = "unknown_style"
            return EX_REFUSE, manifest
        manifest["style"] = {"key": style_dict["key"], "name": style_dict["name"],
                             "slot": style_dict.get("slot"),
                             "typography_only": bool(style_dict.get("typography_only"))}
    effective_prompt = apply_style(prompt, style_dict) if style_dict else prompt

    # --- Idempotent no-op: a completed render already on disk (SPEC 2.2).
    prior = _read_state(out_png)
    if prior and prior.get("status") == "rendered" and out_png.exists():
        dims = _png_dimensions(out_png.read_bytes())
        if dims and dims[1] > dims[0]:
            _log("idempotent no-op: cover already rendered and portrait on disk")
            manifest.update({
                "status": "rendered", "task_id": prior.get("task_id"),
                "source_url": prior.get("source_url"),
                "dimensions": {"width": dims[0], "height": dims[1], "portrait": True},
                "sha256": hashlib.sha256(out_png.read_bytes()).hexdigest(),
                "rendered_at": prior.get("rendered_at") or _utcnow(),
            })
            return EX_OK, manifest

    # --- Resolve the Kie credential BY LABEL (live process env first). SET/NOT-SET.
    key_name, key_val = _env_first(list(key_labels))
    if not key_val:
        _log("HELD: Kie credential NOT SET under labels %s (resolve by label; "
             "value never printed). Held for retry once configured." % list(key_labels))
        manifest["status"] = "held"
        manifest["held_reason"] = HELD_CREDENTIAL_NOT_SET
        return EX_HELD, manifest
    _log("Kie credential SET (label %s); rendering portrait cover %s" % (key_name, aspect))

    if base_url is None:
        _, base_url = _env_first(list(DEFAULT_BASE_URL_LABELS))
        base_url = (base_url or DEFAULT_KIE_BASE_URL).rstrip("/")
    else:
        base_url = base_url.rstrip("/")

    try:
        # Resume an in-flight task if a state sidecar already holds a taskId
        # (cost-safe: never re-submit a paid task the box already created).
        task_id = None
        if prior and prior.get("task_id") and prior.get("status") in (None, "submitted", "held"):
            task_id = prior["task_id"]
            _log("resuming in-flight task from render-state (no re-submit)")
        if not task_id:
            body = build_create_body(effective_prompt, model=model, aspect=aspect, resolution=resolution)
            _write_state(out_png, {"status": "submitting", "task_id": None,
                                   "participant_key": participant_key,
                                   "aspect_ratio": aspect, "model": model,
                                   "submitted_at": _utcnow()})
            task_id = _create_task(base_url, key_val, body, create_timeout_s)
            _write_state(out_png, {"status": "submitted", "task_id": task_id,
                                   "participant_key": participant_key,
                                   "aspect_ratio": aspect, "model": model,
                                   "submitted_at": _utcnow()})
            _log("createTask accepted; polling recordInfo (bounded re-poll)")
        manifest["task_id"] = task_id

        urls = _poll_record_info(base_url, key_val, task_id,
                                 poll_interval_s, poll_ceiling_s, poll_backoff_max_s)
        source_url, width, height, sha = _download_and_verify(urls, out_png, download_timeout_s)

        manifest.update({
            "status": "rendered",
            "source_url": source_url,
            "dimensions": {"width": width, "height": height, "portrait": True},
            "sha256": sha,
            "rendered_at": _utcnow(),
        })
        _write_state(out_png, {"status": "rendered", "task_id": task_id,
                               "participant_key": participant_key,
                               "aspect_ratio": aspect, "model": model,
                               "source_url": source_url,
                               "dimensions": {"width": width, "height": height},
                               "rendered_at": manifest["rendered_at"]})
        _log("PNG landed: %dx%d portrait at %s" % (width, height, out_png))
        return EX_OK, manifest

    except RenderHeld as h:
        _log("HELD (%s): %s" % (h.reason, h.detail))
        manifest["status"] = "held"
        manifest["held_reason"] = h.reason
        st = _read_state(out_png) or {}
        st.update({"status": "held", "held_reason": h.reason, "held_at": _utcnow(),
                   "task_id": manifest.get("task_id")})
        try:
            _write_state(out_png, st)
        except Exception:
            pass
        return EX_HELD, manifest


# --------------------------------------------------------------------------- #
# render_style_set() (U8): render the aw-11 base prompt in ALL FOUR named styles.
# A thin, ordered loop over render() -- each style renders on the SAME model +
# portrait endpoint into its OWN out path. It RENDERS ONLY; upload to media
# storage + Drive and the sample-field writes are the S7 stage runner's job.
# `render_fn` is injectable so the offline self-test drives the loop with ZERO
# network and ZERO spend.
# --------------------------------------------------------------------------- #
def _style_out_png(out_dir: Path, style) -> Path:
    return Path(out_dir) / ("cover-%s.png" % style["key"])


def render_style_set(base_prompt, out_dir, participant_key="", styles=COVER_STYLES,
                     render_fn=None, **render_kwargs):
    """Render `base_prompt` in each of the four named styles. Returns
    (overall_code, set_manifest). overall_code is EX_OK only when ALL styles
    landed; otherwise it is the FIRST non-OK style code (a held/refused style does
    not abort the others -- the whole set is attempted so one hold does not hide a
    second problem). Never prints a secret."""
    rf = render_fn or render
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    overall = EX_OK
    for style in styles:
        st = _coerce_style(style)
        out_png = _style_out_png(out_dir, st)
        code, manifest = rf(base_prompt, out_png, participant_key=participant_key,
                            style=st, **render_kwargs)
        if overall == EX_OK and code != EX_OK:
            overall = code
        entries.append({
            "key": st["key"], "name": st["name"], "slot": st.get("slot"),
            "typography_only": bool(st.get("typography_only")),
            "out_png": str(out_png), "code": code,
            "status": manifest.get("status"), "held_reason": manifest.get("held_reason"),
            "source_url": manifest.get("source_url"), "manifest": manifest,
        })
    set_manifest = {
        "contract": STYLE_SET_CONTRACT,
        "schema_version": 1,
        "participant_key": participant_key,
        "style_count": len(entries),
        "all_rendered": overall == EX_OK,
        "styles": entries,
    }
    return overall, set_manifest


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _load_prompt(args) -> str:
    """The image prompt from --prompt, or --prompt-file (raw text OR a JSON
    object carrying a 'prompt'/'image_prompt' field from the aw-11 structured
    output)."""
    if args.prompt:
        return args.prompt
    if args.prompt_file:
        raw = Path(args.prompt_file).read_text(encoding="utf-8")
        stripped = raw.strip()
        if stripped.startswith("{"):
            try:
                obj = json.loads(stripped)
                for k in ("prompt", "image_prompt", "cover_prompt", "text"):
                    v = obj.get(k)
                    if isinstance(v, str) and v.strip():
                        return v
            except Exception:
                pass
        return raw
    return ""


def cmd_plan() -> int:
    lf = _cover_link_fields()
    print("cover_render.py  (S7 cover render adapter, unit W1.14)")
    print("  model            : %s  (Kie GPT-image-2 text-to-image, W0.6)" % COVER_MODEL)
    print("  aspect_ratio     : %s  (PORTRAIT; overrides Skill 46 default %s)"
          % (COVER_ASPECT, SKILL46_DEFAULT_ASPECT))
    print("  target geometry  : %dx%d portrait" % (COVER_WIDTH, COVER_HEIGHT))
    print("  createTask       : POST %s" % (DEFAULT_KIE_BASE_URL + CREATE_TASK_PATH))
    print("  recordInfo       : GET  %s" % (DEFAULT_KIE_BASE_URL + RECORD_INFO_PATH))
    print("  path             : single image -> direct bounded recordInfo re-poll")
    print("                     (deck size 1 <= callback threshold 5; Skill 46 fix 33)")
    print("  on lost callback : HELD (exit 3) -> hold_queue.py + alert-dedup.py")
    print("  credential       : Kie key by LABEL %s (env-first; never printed)"
          % list(DEFAULT_KEY_LABELS))
    print("  result CDN hosts : %s" % ", ".join(KIE_RESULT_HOSTS))
    print("  link fields NAMED: image=%s ; drive=%s"
          % (lf["cover_image_field"], lf["cover_drive_field"]))
    print("  named styles (U8): %s" % ", ".join(
        "%s%s" % (s["name"], " [type-only]" if s.get("typography_only") else "") for s in COVER_STYLES))
    print("  exit codes       : 0 PNG landed | 2 refuse | 3 held | 1 error")
    return EX_OK


def cmd_list_styles() -> int:
    """Print the four config-pinned named styles (slot order = choice-picklist +
    sample-field order). Offline, no network."""
    print("cover_render named cover styles (U8 / B8) -- slot order is authoritative:")
    for s in COVER_STYLES:
        print("  %d. %-14s (%s)%s" % (s["slot"], s["name"], s["key"],
                                      "  [STRICTLY TYPOGRAPHY-DRIVEN]" if s.get("typography_only") else ""))
        print("       %s" % s["directive"])
    return EX_OK


def cmd_style_set(args) -> int:
    """Render the base prompt in ALL FOUR named styles into --out-dir. Writes
    cover-<key>.png per style + a set manifest to --result-out (or stdout). Live
    (spends per style); the offline path is --self-test / --list-styles."""
    prompt = _load_prompt(args)
    if not prompt.strip():
        _log("REFUSE: empty prompt for the style set")
        return EX_REFUSE
    overall, setman = render_style_set(
        prompt, Path(args.out_dir).expanduser(), participant_key=args.participant_key,
        base_url=args.base_url, key_labels=tuple(args.key_labels), model=args.model,
        aspect=args.aspect, resolution=args.resolution,
        poll_interval_s=args.poll_interval, poll_ceiling_s=args.poll_ceiling,
        create_timeout_s=args.create_timeout, download_timeout_s=args.download_timeout)
    if args.result_out:
        rp = Path(args.result_out).expanduser()
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps(setman, indent=2), encoding="utf-8")
    else:
        print(json.dumps(setman, indent=2))
    return overall


def cmd_dry_run(args) -> int:
    """Build and print the (secret-free) request body and resolve credential
    presence, WITHOUT calling Kie. Zero network, zero cost."""
    prompt = _load_prompt(args)
    if not _is_portrait_ratio(args.aspect):
        _log("REFUSE: aspect %r is not portrait" % args.aspect)
        return EX_REFUSE
    if not prompt.strip():
        _log("REFUSE: empty prompt")
        return EX_REFUSE
    body = build_create_body(prompt, model=args.model, aspect=args.aspect,
                             resolution=args.resolution)
    key_name, key_val = _env_first(list(args.key_labels))
    redacted = json.loads(json.dumps(body))
    # Never echo the full prompt back verbatim into a shared surface; show length.
    redacted["input"]["prompt"] = "<prompt: %d chars>" % len(prompt)
    print(json.dumps({
        "createTask_body": redacted,
        "kie_credential": ("SET (label %s)" % key_name) if key_val else "NOT SET",
        "portrait": True,
        "link_fields": _cover_link_fields(),
    }, indent=2))
    return EX_OK


def self_test() -> int:
    # Exit-code map.
    assert (EX_OK, EX_ERR, EX_REFUSE, EX_HELD) == (0, 1, 2, 3)

    # The portrait override is structural.
    assert _is_portrait_ratio("2:3") is True
    assert _is_portrait_ratio("16:9") is False       # the Skill 46 default is refused
    assert _is_portrait_ratio("1:1") is False
    assert _is_portrait_ratio("3:2") is False
    assert _is_portrait_ratio("bad") is False
    assert _parse_aspect("1024:1536") == (1024, 1536)

    # PNG header parser + a synthetic portrait header (no network, no file).
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = (13).to_bytes(4, "big") + b"IHDR" + (1024).to_bytes(4, "big") + (1536).to_bytes(4, "big")
    assert _png_dimensions(sig + ihdr) == (1024, 1536)
    land = sig + (13).to_bytes(4, "big") + b"IHDR" + (1536).to_bytes(4, "big") + (1024).to_bytes(4, "big")
    lw, lh = _png_dimensions(land)
    assert lw > lh                                    # would be refused as non-portrait
    assert _png_dimensions(b"not a png") is None

    # createTask body always carries the portrait override, png, and no resolution
    # unless asked; callBackUrl absent by default (single-image direct-poll path).
    b = build_create_body("a cover", aspect=COVER_ASPECT)
    assert b["model"] == COVER_MODEL
    assert b["input"]["aspect_ratio"] == "2:3"
    assert b["input"]["output_format"] == "png"
    assert "resolution" not in b["input"]
    assert "callBackUrl" not in b
    b2 = build_create_body("a cover", resolution="2K", callback_url="https://x/cb")
    assert b2["input"]["resolution"] == "2K" and b2["callBackUrl"] == "https://x/cb"

    # Result-URL extraction across the W0.6 (resultJson string) and Skill 46 shapes.
    ok_host = "https://tempfile.aiquickdraw.com/x.png"
    data_str = {"resultJson": json.dumps({"resultUrls": [ok_host]})}
    assert _extract_result_urls(data_str) == [ok_host]
    data_imgs = {"resultJson": {"images": [{"url": ok_host}]}}
    assert _extract_result_urls(data_imgs) == [ok_host]

    # Allowlist.
    assert _host_allowlisted(ok_host) is True
    assert _host_allowlisted("https://evil.example.com/x.png") is False
    assert _host_allowlisted("not a url") is False

    # Literal-key guard. A REALISTIC key shape (length floor + left boundary)
    # trips; ordinary hyphenated English that is common in entrepreneurship /
    # BlackCEO cover art direction MUST NOT (the prior 'sk-[A-Za-z0-9]' regex
    # false-refused these -> S7 prover-lane stall; this is the W1.14 QC fix).
    assert _looks_like_literal_key("draw a book cover") is False
    assert _looks_like_literal_key("a bold, risk-taking entrepreneur, portrait book cover") is False
    assert _looks_like_literal_key("a task-oriented, desk-bound task-master leader") is False
    assert _looks_like_literal_key("brisk, dusk-lit, mask-like cover, whisk of gold") is False
    assert _looks_like_literal_key("use sk-abcd1234 to auth") is False  # too short: not a real key shape
    # Realistic-length leaked keys still trip (>=16 chars after the prefix).
    assert _looks_like_literal_key("leaked sk-abcdefghijklmnop1234567890QRSTUV here") is True
    assert _looks_like_literal_key("token sk-proj-abcdefghijklmnop1234567890 leak") is True
    assert _looks_like_literal_key("or sk-or-v1-0123456789abcdef0123456789abcdef leak") is True
    assert _looks_like_literal_key("Authorization: Bearer abcdefghijklmnop1234567890") is True

    # Link fields name BOTH cover fields (media-storage + Drive).
    lf = _cover_link_fields()
    assert lf["cover_image_field"] and lf["cover_drive_field"]
    assert lf["cover_image_field"] != lf["cover_drive_field"]

    # --- U8: four config-pinned NAMED cover styles ------------------------------
    assert len(COVER_STYLES) == 4, "expected exactly 4 named cover styles"
    assert len(set(STYLE_KEYS)) == 4 and len(set(STYLE_NAMES)) == 4, "style keys/names must be distinct"
    assert tuple(s["slot"] for s in COVER_STYLES) == (1, 2, 3, 4), "slots must be 1..4 in order"
    type_only = [s for s in COVER_STYLES if s.get("typography_only")]
    assert len(type_only) == 1, "exactly one style must be strictly typography-driven"
    assert type_only[0]["name"] == "Pure Type"

    # _coerce_style accepts a dict, a key, or a name (case-insensitive); refuses junk.
    assert _coerce_style("pure_type")["name"] == "Pure Type"
    assert _coerce_style("Bold Editorial")["key"] == "bold_editorial"
    assert _coerce_style(COVER_STYLES[0]) is COVER_STYLES[0]
    try:
        _coerce_style("no_such_style")
        assert False, "unknown style must raise"
    except ValueError:
        pass

    # apply_style appends the style direction; the type-only style adds the strict
    # no-imagery constraint and every specialization differs from every other.
    base = "A portrait book cover for LEAD BOLD, byline JANE DOE."
    specialized = {s["key"]: apply_style(base, s) for s in COVER_STYLES}
    for key, text in specialized.items():
        st = _coerce_style(key)
        assert base.rstrip() in text and STYLE_BLOCK_HEADER in text
        assert st["name"] in text
    assert TYPE_ONLY_CONSTRAINT in specialized["pure_type"]
    assert "TYPOGRAPHY-ONLY" in specialized["pure_type"]
    for key in ("signature", "bold_editorial", "fine_art"):
        assert TYPE_ONLY_CONSTRAINT not in specialized[key], "%s must not carry the type-only clause" % key
    assert len(set(specialized.values())) == 4, "all four specialized prompts must differ"

    # render() with a style stamps the manifest and refuses an unknown style
    # WITHOUT any network (the credential HELD path is reached only for a valid
    # style once guards pass -- proving style resolution precedes the paid call).
    import tempfile as _tf
    _d = Path(_tf.mkdtemp(prefix="cover-style-selftest-"))
    code, man = render("draw a cover", _d / "x.png", style="totally_unknown", key_labels=("__AE_NO_KEY__",))
    assert code == EX_REFUSE and man["held_reason"] == "unknown_style"
    code, man = render("draw a cover", _d / "y.png", style="pure_type", key_labels=("__AE_NO_KEY__",))
    assert code == EX_HELD and man["held_reason"] == HELD_CREDENTIAL_NOT_SET
    assert man["style"] and man["style"]["key"] == "pure_type" and man["style"]["typography_only"] is True

    # render_style_set loops ALL FOUR via an injected stub render_fn (ZERO network,
    # ZERO spend): distinct out paths, one entry per style, and each style's
    # specialized prompt is what the render actually received.
    seen = {}

    def _stub_render(prompt, out_png, participant_key="", style=None, **kw):
        st = _coerce_style(style)
        seen[st["key"]] = apply_style(prompt, st)
        m = {"status": "rendered", "held_reason": None,
             "source_url": "https://tempfile.aiquickdraw.com/%s.png" % st["key"],
             "style": {"key": st["key"], "name": st["name"]}}
        return EX_OK, m

    overall, setman = render_style_set(base, _d / "set", participant_key="c1::a1",
                                       render_fn=_stub_render)
    assert overall == EX_OK and setman["all_rendered"] is True
    assert setman["style_count"] == 4 and len(setman["styles"]) == 4
    assert [e["slot"] for e in setman["styles"]] == [1, 2, 3, 4]
    assert len({e["out_png"] for e in setman["styles"]}) == 4
    assert seen and seen == specialized, "stub must receive each style's specialized prompt"
    # a held style does not abort the set; overall reflects the first non-OK code
    overall2, _ = render_style_set(base, _d / "set2",
                                   render_fn=lambda *a, **k: (EX_HELD, {"status": "held", "held_reason": HELD_CREDIT_OUT}))
    assert overall2 == EX_HELD

    # --- U8 coherence: field-map cover_style_fields agrees with COVER_STYLES ----
    try:
        fm = json.loads(FIELD_MAP_PATH.read_text(encoding="utf-8"))
        csf = fm.get("cover_style_fields") or {}
        assert list(csf.get("choice_options") or []) == list(STYLE_NAMES), \
            "field-map choice_options must equal STYLE_NAMES in order"
        suf = csf.get("sample_url_fields") or {}
        for s in COVER_STYLES:
            assert suf.get(str(s["slot"])), "missing sample_url_field for slot %s" % s["slot"]
        assert len(set(suf.values())) == 4, "sample_url_fields must be four distinct keys"
        assert csf.get("choice_field") and csf.get("target_cover_fields", {}).get("image") \
            and csf.get("target_cover_fields", {}).get("drive")
    except FileNotFoundError:
        pass  # committed template always ships alongside; skip only if absent

    print("cover_render self-test: OK "
          "(portrait override, PNG read-back, Kie body/parse, allowlist, link fields, "
          "4 named styles + 1 type-only, apply_style, render_style_set, field-map coherence)")
    return EX_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Render an anthology cover: Kie GPT-image-2 PORTRAIT 1024x1536 (S7).")
    ap.add_argument("--participant-key", default="", help="composite contact_id::anthology_id (logging/result keying)")
    ap.add_argument("--prompt", help="the aw-11 image prompt text")
    ap.add_argument("--prompt-file", help="path to the aw-11 prompt (raw text or a JSON object with a 'prompt' field)")
    ap.add_argument("--out", help="local target path for the rendered cover PNG")
    ap.add_argument("--out-dir", help="output directory for --style-set (writes cover-<key>.png per style)")
    ap.add_argument("--result-out", help="path to write the JSON result manifest for downstream collaborators")
    ap.add_argument("--style", help="render ONE named style (key or name): %s" % ", ".join(STYLE_KEYS))
    ap.add_argument("--style-set", action="store_true",
                    help="render ALL FOUR named styles into --out-dir (U8 cover set)")
    ap.add_argument("--list-styles", action="store_true", help="print the four named cover styles and exit")
    ap.add_argument("--aspect", default=COVER_ASPECT, help="aspect ratio (portrait only; default 2:3)")
    ap.add_argument("--model", default=COVER_MODEL, help="Kie image model (default %s)" % COVER_MODEL)
    ap.add_argument("--resolution", default=None, help="optional Kie resolution (omit for the W0.6 default 1024x1536)")
    ap.add_argument("--base-url", default=None, help="Kie base URL override (else KIE_BASE_URL label, else api.kie.ai)")
    ap.add_argument("--key-label", dest="key_labels", action="append",
                    help="env label(s) for the Kie key (default KIE_API_KEY); repeatable")
    ap.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL_S)
    ap.add_argument("--poll-ceiling", type=float, default=DEFAULT_POLL_CEILING_S,
                    help="bounded re-poll ceiling in seconds; on exhaustion -> HELD (exit 3)")
    ap.add_argument("--create-timeout", type=float, default=DEFAULT_CREATE_TIMEOUT_S)
    ap.add_argument("--download-timeout", type=float, default=DEFAULT_DOWNLOAD_TIMEOUT_S)
    ap.add_argument("--plan", action="store_true", help="print the render contract and exit")
    ap.add_argument("--dry-run", action="store_true", help="build+print the request body (no network) and exit")
    ap.add_argument("--self-test", action="store_true", help="verify the internal contract (no network) and exit")
    args = ap.parse_args(argv)
    if not args.key_labels:
        args.key_labels = list(DEFAULT_KEY_LABELS)

    try:
        if args.self_test:
            return self_test()
        if args.plan:
            return cmd_plan()
        if args.list_styles:
            return cmd_list_styles()
        if args.dry_run:
            return cmd_dry_run(args)
        if args.style_set:
            if not args.out_dir:
                ap.error("--out-dir is required with --style-set (per-style cover-<key>.png land here)")
            return cmd_style_set(args)

        if not args.out:
            ap.error("--out is required to render (the local target path for the cover PNG)")
        prompt = _load_prompt(args)

        code, manifest = render(
            prompt, Path(args.out).expanduser(), participant_key=args.participant_key,
            base_url=args.base_url, key_labels=tuple(args.key_labels), model=args.model,
            aspect=args.aspect, resolution=args.resolution, style=args.style,
            poll_interval_s=args.poll_interval, poll_ceiling_s=args.poll_ceiling,
            create_timeout_s=args.create_timeout, download_timeout_s=args.download_timeout)

        if args.result_out:
            rp = Path(args.result_out).expanduser()
            rp.parent.mkdir(parents=True, exist_ok=True)
            rp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        else:
            print(json.dumps(manifest, indent=2))
        return code
    except SystemExit:
        raise
    except BrokenPipeError:
        return EX_OK
    except Exception as exc:  # last-resort: never leak a stack to a client surface
        _log("unexpected error: %s: %s" % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
