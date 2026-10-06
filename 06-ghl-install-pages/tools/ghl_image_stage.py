#!/usr/bin/env python3
"""ghl_image_stage.py — B4 Image Pipeline Stage for the Skill-06 builder.

WHAT THIS IS
------------
The missing builder stage that chains the existing ``ghl_media`` primitives into
a complete, end-to-end image pipeline for a single page.  Nothing in the build
flow previously called ``ghl_media``; it was a complete-but-orphaned library.
This module is the wire.

PUBLIC ENTRY POINT
------------------
``run_image_pipeline(page_spec, run_dir, *, location_id, location_pit) -> dict``

  Given one page specification dict and a run directory, this function:

  1. Derives ``copy_specs`` (one per needed image) from the persona copy in
     ``page_spec``, then calls ``ghl_media.build_prompts_json`` with explicit
     ``mode='t2i'`` (a fictional brand has no logo to seed; ``t2i`` is correct
     and ``i2i`` is NEVER emitted without ``input_urls``).
  2. Calls ``ghl_media.generate_images`` to shell the canonical ``kie_generate.py``
     (REUSED AS-IS — never forked).  Asserts ``result['ok']`` AND
     ``not result['missing']`` — missing PNGs are a hard FAIL.
  3. Calls ``ghl_media.resolve_location_pit()`` / ``resolve_location_id()`` for
     the GHL LOCATION PIT and location id (GHL credentials; the KIE key is
     separate and is the box owner's own, see step 0).  Optionally calls
     ``ghl_media.create_media_folder`` to group one run's images.
  4. For each PNG, calls ``ghl_media.upload_media(...)`` (bare Python, not
     Cloudflare-WAF-gated), then RE-FETCHES the returned CDN URL and asserts
     HTTP 200 before trusting it.  Logs each ``status=200 | <url> | OK`` line to
     ``<run_dir>/logs/asset-cdn.log``.
  5. Calls ``ghl_media.image_tag(cdn_url, alt)`` to produce the ``<img>`` snippet
     that B1/B3's customCode splice drops into the page element alongside the
     build marker.
  6. Calls ``ghl_media.build_image_manifest(records, out_path=<run_dir>/images/manifest.json)``
     which rejects any non-https URL or non-200 CDN status — the manifest is
     the hard gate wired by B2's ``render_check``.

GATE CONTRACT (consumed by B2 ``ghl_verify`` — NOT written here)
----------------------------------------------------------------
B4 PRODUCES ``images/manifest.json`` + ``<img src='<cdn_url>'>`` snippets.
B4 does NOT edit ``ghl_verify.py``.  The build fails unless, per page:

  * ``images/manifest.json`` is non-empty with at least one record whose
    ``cdn_url`` is ``https`` and ``cdn_http_status == 200``.
  * The RENDERED ``/preview/`` body (HTTP 200, checked by B2) literally
    contains ``<img src="<cdn_url>">``.

AUTH MODEL SPLIT (LOAD-BEARING)
-------------------------------
KIE.ai generation (``api.kie.ai``) and GHL media upload
(``services.leadconnectorhq.com``, Bearer LOCATION PIT) are NOT behind the
Cloudflare funnels-builder interstitial, so they run from bare Python.  Only
the in-page autosave that REFERENCES the CDN URL is Cloudflare-WAF-gated and
runs in-browser (owned by B1/``ghl_rest_canvas``).  This module makes ONLY the
bare-Python calls.

HONEST-FAIL POLICY
------------------
If ``KIE_API_KEY`` is absent (currently found only in stale ``.bak`` files),
this function writes an honest ``FAIL`` record to ``images/manifest.json`` and
raises ``ImagePipelineError`` so the build gate fails.  NO SVG placeholder, NO
``file://`` URL, NO silent skip.  The box owner must provision the KIE key
(on a client box, the client's own key, via Skill 07 ``07-kie-setup``; operator
keys are never used for client work) into the active env store before a live
run.  Any alias in the ``KIE_API_KEY`` family of ``shared-utils/secret_names.json``
satisfies the check.  Shared KIE rules:
``07-kie-setup/references/kie-common-rules.md``.

DO NOT EDIT
-----------
``ghl_builder.py`` / ``ghl_verify.py`` / ``v2_dispatcher.py`` (B2),
``ghl_rest_canvas.py`` (B1), ``ghl_method.py`` / ``ghl_vercel.py`` /
``ghl_ecosystem.py`` (B3), ``kie_generate.py`` (different skill, out of scope),
tests (B6), SOP/SKILL docs (B7), ``gates.json`` (B8),
``skill-version.txt`` (repo-locked; rolled by scripts/bump-version.sh).
CHANGELOG.md may carry a dated entry for edits to this file.
EDIT ONLY: this file and (minimally) ``ghl_media.py`` if a small helper is needed.
"""

from __future__ import annotations

import json
import logging
import math
import os
import struct
import sys
import urllib.error
import urllib.request
import zlib
from collections import Counter
from pathlib import Path
from typing import Any

# Ensure the tools/ directory is on sys.path so that a plain ``import ghl_media``
# resolves correctly whether this module is imported as part of a package or run
# as a standalone script from a different working directory.
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import ghl_media  # noqa: E402  (placed after sys.path insert)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public exception — lets callers distinguish image-pipeline failures from
# generic Python errors without importing the whole module.
# ---------------------------------------------------------------------------

class ImagePipelineError(RuntimeError):
    """Raised when the image pipeline cannot produce verified CDN-hosted images.

    ``honest_fail`` is True when the failure is a missing/invalid KIE API key
    or a structural honesty failure (missing PNG, non-200 CDN, etc.) rather
    than a transient network error.  The build gate MUST treat any
    ``ImagePipelineError`` as a hard FAIL and never paper over it.
    """

    def __init__(self, message: str, *, honest_fail: bool = True):
        super().__init__(message)
        self.honest_fail = honest_fail


# ---------------------------------------------------------------------------
# Key presence check - fail loud before any network call if the KIE key is absent
# ---------------------------------------------------------------------------

def _load_secret_helper():
    """Import shared-utils/secret_helper.py (the ONE secret-name canon reader).

    shared-utils is not a package, so probe the repo sibling and the well-known
    fleet install locations (Mac ``~/.openclaw/skills`` and VPS
    ``/data/.openclaw/skills``).  Returns the module, or None when unreadable."""
    if "secret_helper" in sys.modules:
        return sys.modules["secret_helper"]
    import importlib.util
    for base in (
        os.path.join(_TOOLS_DIR, "..", "..", "shared-utils"),
        os.path.expanduser("~/.openclaw/skills/shared-utils"),
        "/data/.openclaw/skills/shared-utils",
    ):
        path = os.path.normpath(os.path.join(base, "secret_helper.py"))
        if not os.path.isfile(path):
            continue
        try:
            spec = importlib.util.spec_from_file_location("secret_helper", path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules["secret_helper"] = mod
            spec.loader.exec_module(mod)
            return mod
        except Exception:  # noqa: BLE001
            sys.modules.pop("secret_helper", None)
    return None


def _kie_key_names() -> tuple[str, ...]:
    """Every accepted name for the KIE key: the ``KIE_API_KEY`` family of
    ``shared-utils/secret_names.json`` (aliases live THERE, never restated here).

    ponytail: if the canon cannot be loaded this fails open to the canonical name
    only; add aliases to secret_names.json, not here."""
    helper = _load_secret_helper()
    return tuple(helper.alias_list("KIE_API_KEY")) if helper else ("KIE_API_KEY",)


def _kie_value_ok(value: str) -> bool:
    """True when ``value`` is non-empty and not placeholder-shaped."""
    if not value:
        return False
    helper = _load_secret_helper()
    return not helper.is_placeholder(value) if helper else True


_KIE_KEY_ENV_NAMES = _kie_key_names()
_KIE_ENV_STORES = (
    "~/.openclaw/workspace/.env",
    "~/clawd/secrets/.env",
    "~/.openclaw/secrets/.env",
)


def _resolve_kie_api_key(env: dict | None = None) -> str:
    """Resolve the KIE key from the environment or the canonical env stores.

    Accepts every alias in the ``KIE_API_KEY`` family of the shared secret-name
    canon (``shared-utils/secret_names.json``) and skips placeholder-shaped
    values.  On a client box this is the CLIENT'S OWN key.  Mirrors the store
    order documented in ``kie_generate.py``.  Raises
    ``ImagePipelineError`` (``honest_fail=True``) if the key is absent so the
    build gate fails with an honest FAIL rather than a silent skip.

    This function DOES NOT fall back to ``.bak`` files.  If the key only exists
    in a stale backup, it is treated as absent — the operator must provision it
    into the active env store via Skill 07 before a live run.
    """
    env = env if env is not None else os.environ

    # 1) Live process environment.
    for name in _KIE_KEY_ENV_NAMES:
        val = str(env.get(name, "")).strip().strip("'\"")
        if _kie_value_ok(val):
            return val

    # 2) Canonical env-store files (same paths kie_generate.py reads).
    for store_path in _KIE_ENV_STORES:
        expanded = os.path.expanduser(store_path)
        if not os.path.isfile(expanded):
            continue
        try:
            with open(expanded, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k in _KIE_KEY_ENV_NAMES and _kie_value_ok(v):
                        return v
        except OSError:
            continue

    raise ImagePipelineError(
        "The KIE key is absent from all env stores "
        f"({', '.join(_KIE_ENV_STORES)}) and from the live process environment "
        f"(names checked: {', '.join(_KIE_KEY_ENV_NAMES)}). "
        "Provision KIE_API_KEY (the box owner's own key; on a client box, the "
        "client's) via Skill 07 (07-kie-setup) before running the image pipeline. "
        "NO placeholder image will be substituted — this is a hard FAIL.",
        honest_fail=True,
    )


# ---------------------------------------------------------------------------
# CDN re-fetch helper
# ---------------------------------------------------------------------------

def _refetch_cdn_url(cdn_url: str, *, timeout: int = 30) -> int:
    """HEAD-then-GET the CDN URL and return the HTTP status code.

    Asserts the URL is ``https`` before fetching (a non-https URL is refused
    rather than silently accepted).  Returns the HTTP status; does NOT raise on
    non-200 (the caller decides whether to fail)."""
    if not cdn_url.lower().startswith("https://"):
        raise ImagePipelineError(
            f"CDN URL is not https: {cdn_url!r} — refusing to accept a non-https "
            "media URL.  The GHL media upload must return a public "
            "storage.googleapis.com/msgsndr/... URL.",
            honest_fail=True,
        )
    try:
        req = urllib.request.Request(
            cdn_url,
            method="GET",
            headers={"User-Agent": "ghl-image-stage-verify/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode()
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception as exc:  # noqa: BLE001
        raise ImagePipelineError(
            f"CDN re-fetch failed for {cdn_url!r}: {exc}",
            honest_fail=False,
        ) from exc


# ---------------------------------------------------------------------------
# Log helper
# ---------------------------------------------------------------------------

def _append_cdn_log(log_path: str, status: int, cdn_url: str, label: str) -> None:
    """Append one ``status=NNN | <url> | <label>`` line to ``logs/asset-cdn.log``."""
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(f"status={status} | {cdn_url} | {label}\n")


# ---------------------------------------------------------------------------
# FIX-IMG-01 — deterministic PNG sanity (blank / garbled / off-size detection)
# ---------------------------------------------------------------------------
#
# Image QC used to be existence + provenance ONLY (PNG magic, CDN 200, taskId), so
# a BLANK, solid-color, or truncated raster passed every gate and shipped. This
# deterministic stage inspects the actual bytes of each generated PNG BEFORE it is
# uploaded: it parses the IHDR dimensions, enforces a resolution-scaled size floor
# (a solid-color 2K PNG compresses FAR below a real photo), and rejects near-zero
# color entropy (a blank frame). A failing slot is regenerated up to 2 times, then
# hard-FAILs with the slot id. No network, no model — purely mechanical.

# resolution-class → (minimum longest-edge px, minimum file bytes).
_PNG_RES_FLOORS: dict[str, tuple[int, int]] = {
    "2K":    (1400, 150_000),
    "1080P": (900,  90_000),
    "720P":  (600,  45_000),
}
_PNG_RES_DEFAULT = "2K"
# Minimum Shannon entropy (bits/byte) of the DECOMPRESSED scanline stream. A real
# photo is > 4 bits/byte; a solid / near-blank frame is ~0. 0.5 only trips on the
# genuinely blank, never on a real (even flat-graphic) image.
_PNG_ENTROPY_MIN_BITS = 0.5


def _png_ihdr_dims(png_path: str) -> tuple[int, int]:
    """Return ``(width, height)`` parsed from the PNG IHDR chunk.

    Raises ``ValueError`` if the file is not a PNG with a well-formed IHDR (the
    first chunk after the 8-byte signature)."""
    with open(png_path, "rb") as fh:
        head = fh.read(26)
    if head[:8] != ghl_media.PNG_MAGIC or head[12:16] != b"IHDR":
        raise ValueError(f"{png_path!r}: not a PNG with a valid IHDR chunk")
    width, height = struct.unpack(">II", head[16:24])
    return int(width), int(height)


def _png_decompressed_entropy(png_path: str) -> float:
    """Shannon entropy (bits/byte) of the concatenated, zlib-decompressed IDAT
    stream. A blank / solid-color frame decompresses to a near-constant byte
    stream (entropy ~0); a real image is high-entropy. Returns 0.0 when no IDAT
    is present (also a fail signal)."""
    idat = bytearray()
    with open(png_path, "rb") as fh:
        if fh.read(8) != ghl_media.PNG_MAGIC:
            return 0.0
        while True:
            length_bytes = fh.read(4)
            if len(length_bytes) < 4:
                break
            (length,) = struct.unpack(">I", length_bytes)
            ctype = fh.read(4)
            payload = fh.read(length)
            fh.read(4)  # CRC
            if ctype == b"IDAT":
                idat += payload
            elif ctype == b"IEND":
                break
    if not idat:
        return 0.0
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error:
        raw = bytes(idat)  # fall back to compressed-stream entropy
    if not raw:
        return 0.0
    counts = Counter(raw)
    n = len(raw)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _png_sanity(png_path: str, resolution_class: str = _PNG_RES_DEFAULT) -> tuple[bool, str]:
    """Deterministic content sanity for one generated PNG.

    Returns ``(ok, reason)``. ``ok`` is True only when the file is a real PNG that
    (a) meets the resolution-scaled BYTE floor, (b) has IHDR dimensions whose
    longest edge meets the class floor, and (c) has decompressed-IDAT entropy above
    ``_PNG_ENTROPY_MIN_BITS``. Any failure returns a specific human reason. NEVER
    raises — a parse error is reported as a sanity failure so the caller can retry."""
    floors = _PNG_RES_FLOORS.get((resolution_class or _PNG_RES_DEFAULT).upper(),
                                 _PNG_RES_FLOORS[_PNG_RES_DEFAULT])
    min_long_edge, min_bytes = floors
    try:
        if not ghl_media.verify_png(png_path):
            return False, "not a valid PNG (magic-byte check failed)"
        size = os.path.getsize(png_path)
        if size < min_bytes:
            return False, (
                f"file size {size}B below the {resolution_class} floor of "
                f"{min_bytes}B (a solid-color / blank frame compresses this small)"
            )
        width, height = _png_ihdr_dims(png_path)
        if width <= 0 or height <= 0:
            return False, f"non-positive IHDR dimensions {width}x{height}"
        if max(width, height) < min_long_edge:
            return False, (
                f"IHDR {width}x{height}: longest edge {max(width, height)}px is "
                f"below the {resolution_class} floor of {min_long_edge}px"
            )
        entropy = _png_decompressed_entropy(png_path)
        if entropy < _PNG_ENTROPY_MIN_BITS:
            return False, (
                f"decompressed entropy {entropy:.3f} bits/byte below "
                f"{_PNG_ENTROPY_MIN_BITS} — image is blank / near-solid-color"
            )
    except (OSError, ValueError, struct.error) as exc:
        return False, f"sanity inspection error: {exc}"
    return True, "ok"


# ---------------------------------------------------------------------------
# FIX-XC-04f — 8-block, brand-graded image prompt derivation (client brand)
# ---------------------------------------------------------------------------
#
# Skill 6 used to fabricate a ~200-char generic hero prompt (copy truncated at
# 300 chars, ONE image per page). A prompt that thin cannot carry the on-brand,
# art-directed look a real page image needs, and Skill 6's own paid path had no
# floor to catch it. This builder emits ONE spec per major page SECTION, each a
# full 8-block prompt (order from 49 MASTERDOC §4) whose block 4 is a client-brand
# Grade Block templated from the intake brand colors — so the prompt clears the
# 1,500-char PROMPT_CHAR_FLOOR and looks like the client's brand, not a stock stub.

# Copy context is now capped at 2,000 chars (was 300) so section copy can actually
# inform the scene.
_COPY_CONTEXT_CAP = 2000


def _brand_colors(page_spec: dict) -> list[str]:
    """Resolve the client's brand colors from the page/intake spec.

    Accepts a ``brand_colors`` list, or a ``brand`` dict carrying ``colors`` /
    ``palette`` / ``primary_color`` + ``secondary_color`` / ``accent_color``.
    Returns a de-duplicated, order-preserving list of colour strings (hex or
    named); ``[]`` when the spec carries no brand colour (the Grade Block then
    falls back to a neutral, still-graded direction)."""
    out: list[str] = []
    seen: set[str] = set()

    def _add(v: Any) -> None:
        s = str(v).strip()
        key = s.lower()
        if s and key not in seen:
            seen.add(key)
            out.append(s)

    raw = page_spec.get("brand_colors")
    brand = page_spec.get("brand")
    if isinstance(raw, (list, tuple)):
        for c in raw:
            _add(c)
    if isinstance(brand, dict):
        for coll_key in ("colors", "palette", "brand_colors"):
            coll = brand.get(coll_key)
            if isinstance(coll, (list, tuple)):
                for c in coll:
                    _add(c)
        for scalar_key in ("primary_color", "secondary_color", "accent_color"):
            if brand.get(scalar_key):
                _add(brand[scalar_key])
    return out


def _brand_grade_block(brand_colors: list[str]) -> str:
    """Return the block-4 client-brand Grade Block (a full paragraph of grading
    direction) anchored to the client's brand colors. Templated so the palette is
    named verbatim; falls back to a neutral-but-graded direction when no brand
    colour is supplied."""
    if brand_colors:
        palette = ", ".join(brand_colors)
        anchor = (
            f"The palette is anchored to this brand's colors ({palette}), pushed to "
            "their richest, most luminous expression so the frame is unmistakably "
            "on-brand."
        )
    else:
        anchor = (
            "The palette is a confident, cohesive brand grade with punchy "
            "complementary relationships, pushed to its richest, most luminous "
            "expression."
        )
    return (
        "Grade this image as a high-fashion editorial cover and treat this grading "
        "direction as the single most important instruction in the prompt. Color is "
        "vibrant and boldly saturated: push global saturation well above natural so "
        "every hue reads jewel-rich and electric, never muddy, never washed out. Use "
        "a distinct cinematic grade with deep, inky shadows against luminous, glowing "
        "highlights and high, confident contrast. " + anchor + " Every human subject "
        "is lit and graded with melanin-true intelligence: deep skin tones rendered "
        "rich, dimensional, and radiant, warm undertones preserved, never ashy, never "
        "grey, never flattened. This is not natural documentary color; this is "
        "signature brand color: vivid, graded, and unforgettable, composed like a "
        "single standalone piece of art a scrolling thumb stops for."
    )


# ---------------------------------------------------------------------------
# FIX-XC-02c — DIU style-card resolution (Skill 45 design-intelligence-library)
#
# When a ``page_spec`` carries an OPTIONAL ``style_card_id`` (e.g. "FN-003"), the
# image pipeline resolves that card via DIU Workflow B (Skill 45 MASTER-SOP §7):
# look the id up in the library ``INDEX.md``, open the registered card file, and
# lift its LONG-tier prompt text.  That text is embedded VERBATIM as the
# Brand-Style portion of block 8 in every derived section prompt so a registered
# funnel / landing / website style governs the page's imagery.  Unset ==> exact
# current behavior (purely additive).
#
# Resolution is FAIL-LOUD: an id that is set but cannot be resolved (no library,
# not registered in INDEX, missing card file, or no LONG tier) raises
# ``ImagePipelineError`` rather than silently dropping the operator's requested
# brand style — a dropped style card would ship off-brand art (honest-fail).
# ---------------------------------------------------------------------------

_DIU_LIBRARY_ENV = "DIU_LIBRARY_DIR"

# Candidate ``library/`` locations, tried in order; the first with an INDEX.md
# wins.  Repo layout: tools/ -> 06-ghl-install-pages/ -> repo root -> 45-.../library.
_DIU_LIBRARY_RELCANDIDATES = (
    os.path.join("..", "..", "45-design-intelligence-library", "library"),
)
_DIU_LIBRARY_HOMECANDIDATES = (
    "~/.openclaw/skills/45-design-intelligence-library/library",
    "~/.openclaw/onboarding/45-design-intelligence-library/library",
)


def _diu_library_dir() -> Path | None:
    """Resolve Skill 45's ``library/`` dir, or None when the library is absent.

    Honors the ``DIU_LIBRARY_DIR`` env override (must itself contain INDEX.md),
    then the sibling-skill repo path, then the materialized ``~/.openclaw`` paths.
    """
    override = os.environ.get(_DIU_LIBRARY_ENV, "").strip()
    if override:
        p = Path(os.path.expanduser(override))
        return p if (p / "INDEX.md").is_file() else None
    for rel in _DIU_LIBRARY_RELCANDIDATES:
        p = Path(os.path.join(_TOOLS_DIR, rel))
        if (p / "INDEX.md").is_file():
            return p.resolve()
    for home_rel in _DIU_LIBRARY_HOMECANDIDATES:
        p = Path(os.path.expanduser(home_rel))
        if (p / "INDEX.md").is_file():
            return p
    return None


def _diu_index_lookup(index_path: Path, card_id: str) -> str | None:
    """Return the File-Path cell for ``card_id`` from a markdown INDEX.md, else None.

    Scans every table row; a row matches when any cell equals ``card_id`` exactly
    (case-insensitive).  The card file path is the row's last non-empty cell — the
    INDEX contract puts File Path last in every category table."""
    target = card_id.strip().lower()
    if not target:
        return None
    for line in index_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not any(c.lower() == target for c in cells):
            continue
        for cell in reversed(cells):
            if cell and cell not in ("-",):
                # strip a markdown link wrapper [text](path) -> path
                if cell.startswith("[") and "](" in cell and cell.endswith(")"):
                    cell = cell.split("](", 1)[1][:-1].strip()
                return cell
        return None
    return None


def _diu_resolve_card_path(lib: Path, rel: str) -> Path | None:
    """Resolve a card File-Path cell to an on-disk file under the library.

    The INDEX documents paths as "relative from design-library/"; the on-disk
    root is ``library/``.  We try the path as-is under ``library/``, under its
    parent, and with a leading ``design-library/`` or ``library/`` prefix stripped."""
    rel = rel.strip().lstrip("/")
    rel_stripped = rel
    for pref in ("design-library/", "library/"):
        if rel_stripped.startswith(pref):
            rel_stripped = rel_stripped[len(pref):]
            break
    for base, r in ((lib, rel_stripped), (lib, rel), (lib.parent, rel)):
        p = base / r
        if p.is_file():
            return p
    return None


def _diu_extract_long_tier(card_text: str) -> str | None:
    """Lift the LONG-tier prompt text from a style-card markdown body.

    Finds the ``### LONG`` heading, collects lines until the next markdown
    heading, and returns the first fenced code block's inner text when present
    (the STYLE-CARD-TEMPLATE fences each tier), else the raw section text."""
    lines = card_text.splitlines()
    start = None
    for idx, ln in enumerate(lines):
        if ln.lstrip().startswith("### LONG"):
            start = idx + 1
            break
    if start is None:
        return None
    section: list[str] = []
    for ln in lines[start:]:
        s = ln.lstrip()
        if s.startswith("### ") or s.startswith("## "):
            break
        section.append(ln)
    body = "\n".join(section)
    if "```" in body:
        parts = body.split("```")
        if len(parts) >= 3 and parts[1].strip():
            return parts[1].strip()
    stripped = body.strip()
    return stripped or None


def _resolve_style_card_block(style_card_id: str) -> str:
    """Resolve ``style_card_id`` to its LONG-tier prompt text (DIU Workflow B).

    Returns the LONG-tier text on success.  Raises ``ImagePipelineError`` when the
    id is set but cannot be resolved — a requested brand style is NEVER silently
    dropped.  Never called with a blank id (the caller guards that)."""
    cid = str(style_card_id or "").strip()
    if not cid:
        return ""
    lib = _diu_library_dir()
    if lib is None:
        raise ImagePipelineError(
            f"style_card_id={cid!r} was requested but the Skill 45 design library "
            f"could not be located (set {_DIU_LIBRARY_ENV} or install "
            "45-design-intelligence-library). Refusing to ship off-brand imagery by "
            "silently dropping the requested style card."
        )
    rel = _diu_index_lookup(lib / "INDEX.md", cid)
    if not rel:
        raise ImagePipelineError(
            f"style_card_id={cid!r} is not registered in the design library "
            f"INDEX.md ({lib / 'INDEX.md'}). Register the card (DIU Workflow A) "
            "before referencing it from a page spec."
        )
    card_path = _diu_resolve_card_path(lib, rel)
    if card_path is None:
        raise ImagePipelineError(
            f"style_card_id={cid!r} resolves to card path {rel!r} in INDEX.md, but "
            f"no such file exists under the design library at {lib}."
        )
    long_tier = _diu_extract_long_tier(card_path.read_text(encoding="utf-8"))
    if not long_tier:
        raise ImagePipelineError(
            f"style_card_id={cid!r} card {card_path.name} carries no LONG-tier prompt "
            "text (a '### LONG' section). A funnel/website style card must ship a LONG "
            "tier to feed the Brand-Style block."
        )
    return long_tier


def _build_section_prompt(
    page_name: str,
    section: dict,
    brand_colors: list[str],
    style_card_text: str = "",
) -> tuple[str, bool]:
    """Build one 8-block image prompt for a page section.

    Returns ``(prompt, text_bearing)``. The 8-block order follows 49 MASTERDOC §4:
    1 Subject & Wardrobe · 2 Composition & Shot · 3 Typography (text-bearing only)
    · 4 Signature/Brand Grade Block · 5 Lighting · 6 Quality & Render · 7 Facial
    Intelligence · 8 Brand-Style + Negative Block. The Grade Block is templated from
    the client brand colors. The prompt is written to clear PROMPT_CHAR_FLOOR.

    FIX-XC-02c: when ``style_card_text`` is supplied (a resolved DIU LONG-tier
    style card), it is embedded VERBATIM as the Brand-Style portion of block 8,
    ahead of the always-on negative directives; empty ==> the default block 8."""
    heading = str(section.get("heading") or section.get("title") or "").strip()
    body = str(section.get("copy") or section.get("body") or section.get("text") or "").strip()
    role = str(section.get("role") or section.get("type") or "content").strip() or "content"
    text_bearing = bool(section.get("text_bearing"))

    copy_context = " ".join(p for p in (heading, body) if p)[:_COPY_CONTEXT_CAP]
    if not copy_context:
        copy_context = f"the {role} section of the page titled '{page_name}'"

    subject = (
        f"Block 1 — Subject and Wardrobe: A premium, art-directed marketing image "
        f"for the {role} section of a web page titled '{page_name}'. The scene "
        f"visually expresses this section's message: {copy_context}. Feature a "
        "credible, aspirational real-world subject (people, product, or environment) "
        "styled with modern, tasteful wardrobe and props that fit the brand's "
        "premium positioning."
    )
    composition = (
        "Block 2 — Composition and Shot: Editorial composition with intentional "
        "negative space for overlaid web copy, a clear focal hierarchy, and a "
        "confident rule-of-thirds or centered hero framing. Shot on a full-frame "
        "camera look, shallow-to-medium depth of field, crisp foreground subject "
        "against a softly separated background."
    )
    if text_bearing:
        typography = (
            "Block 3 — Typography: Any lettering that appears must be spelled "
            "correctly, letter-for-letter, in clean modern sans-serif, integrated as "
            "designed graphic type (not a caption bar)."
        )
    else:
        typography = (
            "Block 3 — Typography: This is a photographic, no-text section; render no "
            "lettering, words, captions, or watermarks anywhere in the frame."
        )
    grade = "Block 4 — Grade Block: " + _brand_grade_block(brand_colors)
    lighting = (
        "Block 5 — Lighting: Dramatic, directional editorial lighting with a soft key, "
        "gentle rim separation, and controlled falloff; luminous highlights and rich "
        "shadow detail that make the subject feel dimensional and premium."
    )
    quality = (
        "Block 6 — Quality and Render: Ultra-high-detail, photorealistic, sharp "
        "focus on the subject, clean micro-contrast, no artifacts, no plastic skin, "
        "no oversmoothing; magazine-cover finish suitable for a full-bleed hero at 2K."
    )
    facial = (
        "Block 7 — Facial Intelligence: If any face is present, render it natural, "
        "symmetrical, and emotionally engaged, with authentic expression, realistic "
        "eyes and skin texture, and melanin-true tones; never uncanny, never distorted."
    )
    _negative_directives = (
        "Keep the whole frame consistent with a premium, trustworthy brand. Do not "
        "include: distorted anatomy, extra or missing fingers, warped faces, garbled "
        "or misspelled text, logos of other brands, low-resolution blur, heavy noise, "
        "watermark stamps, or stock-photo cheesiness."
    )
    if style_card_text.strip():
        # FIX-XC-02c: a resolved DIU LONG-tier style card leads block 8's Brand-Style
        # direction; the always-on negative directives still close the block.
        negative = (
            "Block 8 — Brand-Style and Negative Block: " + style_card_text.strip()
            + " " + _negative_directives
        )
    else:
        negative = "Block 8 — Brand-Style and Negative Block: " + _negative_directives

    prompt = "\n\n".join([
        subject, composition, typography, grade, lighting, quality, facial, negative,
    ])
    return prompt, text_bearing


# ---------------------------------------------------------------------------
# copy_specs derivation from page_spec
# ---------------------------------------------------------------------------

# Real, section-specific art-direction blocks that bring a derived prompt into the KIE rule 12 band (95 to 100 percent
# of the image model's maxLength). Each block states a distinct decision for THIS section (setting, subject, lens,
# light, color, copy-safe space and so on) and is filled from the section's own role, page, copy and palette; they are
# added in order, only as many as the band needs, by the rewrite loop below.
_DEPTH_BLOCKS = (
    "Environment and setting: place the subject inside a believable, specific location that suits the {role} section of '{page}', with real architectural or natural detail receding in layers: a near foreground element that frames the shot, a mid-ground where the subject lives, and a far background that is softly separated. Describe the place through its materials, its age, and the way daily use has left small marks, so it reads as lived-in and credible rather than a generic studio. Keep every element consistent with the message \"{context}\" so the scene explains the section at a glance.",
    "Subject direction: give the main subject one clear action or posture that expresses the section's meaning, with confident, relaxed body language and an engaged, unforced expression. Hands are visible and natural, doing something purposeful, never clasped stiffly or hidden. Wardrobe is polished and modern in the palette {palette}, with fabric texture visible at close range. If a product or object is the hero, show it in use, at a believable scale, with clean edges and honest material finish.",
    "Lens and camera: shoot as if on a full-frame camera with a 50 to 85 millimeter lens at a moderately wide aperture, giving a gentle falloff that isolates the subject without turning the background into mush. Keep the horizon level, place the eye line on the upper third, and avoid wide-angle distortion on faces. The viewpoint sits at or slightly below eye level to give the subject quiet authority, and the framing leaves breathing room on the side where web copy will overlay.",
    "Key light: a large soft source from the front-left at roughly forty-five degrees sculpts the face and shoulders with gentle shadow transitions, while a subtle rim light on the opposite edge separates the subject from the background. Highlights stay luminous without clipping, skin shows true dimensional tone, and shadows hold detail instead of crushing to flat black. The light direction is the same on every object in the frame so the scene feels physically coherent.",
    "Color use: build the frame around the brand palette {palette}, using the primary color for the largest calm area, the secondary color for supporting surfaces, and the accent only for a small number of deliberate focal touches that pull the eye to the subject. Neutral tones fill the gaps. Keep saturation rich and confident but never neon, keep skin tones faithful, and keep color temperature consistent across the whole image so it blends cleanly into a web page that uses the same palette.",
    "Materials and texture: render surfaces with tactile truth: brushed metal with fine directional grain, matte paper with a visible tooth, wood with open pores, glass with clean reflections, fabric with a readable weave. Each material responds to the key light in its own way, producing believable highlights and soft contact shadows where objects touch. Avoid plastic smoothness, avoid repeated texture patterns, and avoid any surface that looks painted on.",
    "Depth and layering: separate the image into clear planes using value contrast, atmospheric softness, and scale. The subject carries the strongest local contrast and the sharpest edges, the mid-ground carries moderate contrast, and the background is quieter and slightly lower in contrast. Leading lines in the setting guide the eye toward the subject. Overlap objects so that the scene feels three dimensional, and keep any small bright object away from the borders where it would pull the eye out of the frame.",
    "Copy-safe space: reserve a calm, low-detail region, about one third of the frame, on the side opposite the subject's gaze, with even tone and no busy texture so overlaid headline and button text stay perfectly legible at desktop and mobile sizes. The subject and the key props sit entirely inside the safe zone for a center crop, so a tighter mobile crop never cuts a face, a hand, or the main object.",
    "Emotional tone: the image should make a visitor feel the promise of the {role} section within two seconds: calm confidence, momentum, and trust, with warmth in the light and clarity in the composition. Avoid exaggerated, theatrical, or salesy poses. The mood is credible and premium, closer to a quality editorial feature than to an advertisement, and every detail from posture to prop supports that single feeling.",
    "Background storytelling: let secondary details quietly support the message \"{context}\": a notebook with a plan on a desk, a window showing the morning, a tidy work surface, a visible sign of progress. Each detail is specific, plausible, and small enough not to compete with the subject. Nothing in the background carries readable text unless the typography block calls for it, and nothing repeats like a pattern.",
    "Finish and polish: the final image looks like a professionally retouched magazine photograph: clean micro-contrast, natural skin texture with no over-smoothing, crisp edges on the hero, and subtle, consistent film-like grain only if it helps cohesion. Dust, lens artifacts, stray hairs, and distracting reflections are cleaned up. Output at 2K resolution with enough sharpness that a full-bleed hero holds up on a large display.",
    "Page cohesion: this image belongs to one page with several images, so keep the same lighting logic, the same palette weighting, the same level of realism, and the same camera language as its siblings. Vary the subject, the angle, and the setting between images so the set feels designed rather than repeated, while the viewer still senses one brand behind every frame.",
    "Representation and care: when people appear, show a natural range of ages and backgrounds that fits the brand's audience, with authentic expressions and dignified portrayal; render every skin tone with rich, dimensional accuracy, never ashy, never over-lightened. Faces are symmetrical enough to look natural, eyes have realistic catchlights, teeth and hands are anatomically correct, and no person appears in a way that could embarrass the client.",
    "Brand integrity: use only the supplied brand colors and the supplied reference material; do not invent a logo, a slogan, a badge, or a mock-up of another company's mark. If a logo reference is supplied it is preserved exactly and placed small and clean; if none is supplied, no logo appears at all. Every visible object stays generic enough to avoid trademark conflicts while still feeling specific and real.",
    "Typography handling: if lettering is required it is limited to the exact approved words, rendered letter for letter in a clean modern sans-serif with generous spacing, strong contrast against its background, and a clear size hierarchy between headline and supporting line; no extra words, no gibberish glyphs, and no decorative fonts that reduce legibility. If no lettering is required, every surface in the frame is free of readable characters.",
    "Quality control read: a reviewer who sees only the image should be able to name the section's message, identify the single hero, find the calm copy-safe zone, recognize the brand palette, and see no anatomical, textual, or physical errors. Anything that distracts from those five reads is removed or simplified before the image is considered finished.",
    "Rendering exclusions: no watermark, no stock-photo cheesiness, no cartoonish illustration unless the style card calls for it, no heavy vignette, no lens flare, no HDR halos, no oversaturated skies, no duplicated limbs or objects, no melted details at the edges of the frame, and no text artifacts anywhere. The result is clean, believable, and ready to place on a live page without further editing.",

    "Time and atmosphere: fix one specific moment of the day for the whole frame, for example soft mid-morning light with clean air, and let the sky, the shadow length, and the color of the air all agree with it. Add only a hint of atmospheric haze in the far distance to sell depth. Nothing in the frame contradicts the chosen hour, and the light in any window, lamp, or screen matches its surroundings.",
    "Props and scale: choose three to five props that belong to the {role} section and the story of \"{context}\", and give each a believable size relative to the subject and the room. Props are placed with intention, one anchoring the foreground, one near the subject's hands, and one in the distance, never lined up in a row and never cluttering the copy-safe zone. Worn edges and honest wear make them feel owned.",
    "Gaze and attention: if a person is present the gaze either meets the viewer with calm warmth or travels toward the copy-safe zone to guide the eye there; it never stares past the edge of the frame at nothing. The nearest sharp point in the image is the face or the hero object, the second read is the accent color touch, and the third is the supporting prop, so attention moves through the frame in a clean, intentional order.",
    "Composition options: favor a rule-of-thirds layout with the subject on a strong vertical third and the copy-safe zone on the other two thirds, or a centered hero framing with symmetrical negative space when the section is a bold statement. Avoid tangents where an edge touches a head or a hand, avoid dead center placement on a wide frame, and keep diagonals gentle so the image feels stable and trustworthy.",
    "Reflections and surfaces: where glass, polished stone, or a screen appears, reflect the real environment in a muted, believable way, never a perfect mirror and never a blinding glare. Screens show soft, non-readable interface shapes unless exact words are approved. Water or glossy floors carry a soft, partial reflection that adds depth without distracting from the subject.",
    "Accessibility and contrast: the luminance difference between the subject and its background is strong enough that the image still reads in grayscale, and the copy-safe zone has enough tonal separation from any text color the page will use. Important information is never carried by color alone, and no flicker-prone, high-frequency pattern appears anywhere in the frame.",
    "Seasonal and cultural neutrality: keep the scene free of holidays, current events, regional symbols, or fashion trends that would date the page within a year or confuse a global audience. The setting, clothing, and props are timeless, modern, and respectful, so the page can stay live for a long time without refreshing the imagery.",
    "Safe margins and crops: keep every key element at least ten percent inside the edges so wide, square, and tall crops all preserve the story. The most important detail sits within the central sixty percent of the frame. Any element that touches the border is soft and unimportant, so a crop that trims it loses nothing the page needs.",
    "Edge treatment and noise: edges of the hero are crisp and clean, with no halo, no fringing, and no ragged cutout look. Background edges soften naturally through depth of field. Digital noise is minimal and even, shadows are clean, and no banding appears in smooth gradients such as walls, skies, or soft backdrops.",
    "Final composite check: before the image is considered complete, confirm one clear hero, one calm copy-safe region, one coherent light direction, one consistent palette, correct anatomy, readable approved words only, a believable setting, and a finish that matches the other images on the page. Resolve any conflict between these checks in favor of clarity and credibility.",

    "Motion and stillness: although the image is a still, imply a calm moment just before or after an action, such as a hand about to turn a page or a person settling into a chair, so the frame feels alive without any blur. No motion smear appears on the hero, and any soft movement in the background, such as curtains or leaves, is subtle and consistent with a single light breeze.",
    "Human presence rules: show at most two people unless the section's message needs a group, keep them clearly in different planes, and avoid identical poses. Group scenes show natural spacing and varied heights, with the key person nearest the lens and the strongest light. No one looks at the camera in a posed, catalog manner unless the section calls for a direct welcome.",
    "Surface cleanliness: tables, floors, and walls are tidy but not sterile, with a few honest signs of use. There are no stray cables, no crooked frames, no visible price tags, and no accidental brand marks on devices or clothing. Anything that would force a retouch on a real photo shoot is absent from the frame from the start.",
    "Light quality details: shadows have soft, believable edges that grow softer the farther they fall from the object, highlights on skin carry a subtle sheen without turning oily, and the transition from light to shadow on rounded forms is smooth. Catchlights appear in the eyes at the same position as the key light, and any practical lamp in the scene adds a small warm pool that does not fight the key.",
    "Palette harmony: pick one dominant hue family, one supporting family, and one accent family from {palette}, and make sure that no unrelated color enters the frame through props, clothing, or background elements. Where a third-party color is unavoidable, such as a plant or a sky, it is muted and sits in the background. The overall impression is a deliberate, designed color story.",
    "Resolution and detail budget: spend detail where the eye lands, namely the face, the hands, and the hero object, and keep the rest simpler so the image is rich without being busy. Fine detail is crisp at full resolution, textures stay believable when scaled down, and no region contains so much tiny detail that it shimmers or turns into noise on a phone screen.",
    "Narrative in one frame: the picture answers three questions without words: who is this for, what is happening, and why does it matter to the visitor reading the {role} section of '{page}'. The answers come from the subject, the setting, and the light, and they agree with \"{context}\" so the image and the copy reinforce each other instead of competing.",

    "Foreground framing: include one soft, out-of-focus foreground element at a corner, such as a plant leaf, a shoulder, or the edge of a table, to frame the subject and add depth. It occupies a small area, stays outside the copy-safe zone, and carries no bright color that would steal attention from the hero.",
    "Clarity of the hero silhouette: the outline of the main subject reads cleanly against its background through value or color contrast, never blending into a similar tone behind it. Hair, fabric, and object edges are defined naturally, with soft but intentional transitions, so the shape is recognizable even as a small thumbnail on a social card.",
    "Responsible realism: render everything at photographic realism level, with correct perspective, correct proportions, correct shadows, and correct reflections. Where the style card or the brand asks for a more graphic treatment it is applied to the whole frame consistently, never to part of it, and never at the cost of anatomical accuracy or readable approved text.",
    "Section-specific emphasis: for a hero section, lead with scale and confidence and a generous open copy-safe field; for a benefits section, show clear, simple evidence of the outcome in use; for a proof section, show credible, human moments with calm light; for a closing section, show resolution, warmth, and an inviting open space that suggests the next step without any arrow or button.",
    "Delivery notes: the file is a single, flat raster at 2K with no layers, no transparency requirement, no baked border, and no baked mock-up frame. The aspect ratio requested by the page is respected exactly. The image is complete on its own, and the page's own text, buttons, and overlays are added later by the page builder.",
)


def _deepen_to_band(prompt: str, *, page_name: str, role: str, context: str, palette: str) -> str:
    """Rewrite loop (rule 12): while the prompt is outside the band, add the next section-specific blocks, using the
    verdict's exact add count, up to 3 tries; then escalate (``ImagePipelineError``). Reserves room for the pin that
    ``build_prompts_json`` appends after this."""
    ctx = {"page": page_name, "role": role or "content", "context": context, "palette": palette}
    queue = [b.format(**ctx) for b in _DEPTH_BLOCKS]
    reserve = len(ghl_media.ENGLISH_LATIN_PIN) + 2

    def rewriter(text, verdict):
        mx = verdict["max"]
        goal = (verdict["target_min"] + mx - reserve) // 2
        out = text.rstrip()
        while queue and len(out) + len(queue[0]) + 2 <= goal:
            out += "\n\n" + queue.pop(0)
        return out

    try:
        fitted, _ = ghl_media.KPE.rewrite_to_band(ghl_media.IMAGE_MODEL_DEFAULT, prompt, rewriter)
    except ghl_media.KPE.PromptBudgetError as exc:
        raise ImagePipelineError(f"section prompt for '{page_name}' could not be brought into the KIE rule 12 length band: {exc}") from exc
    return fitted


def _derive_copy_specs(page_spec: dict) -> list[dict]:
    """Derive the image ``copy_specs`` list from one page specification.

    ``page_spec`` is the per-page dict the build plan carries.  It may contain:

    * ``images``: an explicit list of image spec dicts (id, prompt, alt,
      used_on_page_id, locator) — used as-is if present.
    * ``copy``: a dict with ``headline``, ``subheadline``, ``body`` etc. keys
      used to derive a hero image prompt when no explicit ``images`` list is
      given.
    * ``page_id``: the GoHighLevel page id (for ``used_on_page_id``).
    * ``name``: the page name / title (used in the derived prompt and id).
    * ``style_card_id``: OPTIONAL (FIX-XC-02c). When set, the DIU style card's
      LONG tier is resolved (fail-loud) and embedded as block 8's Brand-Style
      direction in every prompt; unset ==> exact current behavior.

    Per-image (explicit) and per-section entries may carry an OPTIONAL
    ``aspect_ratio`` / ``resolution`` (FIX-IMG-03); when present these are carried
    onto the spec so ``build_prompts_json`` -> ``kie_generate.py`` renders that
    ratio (e.g. a 3:4 portrait) instead of the hardcoded 16:9 default.

    Every derived spec uses ``mode='t2i'`` explicitly (a fictional brand has no
    logo; ``i2i`` is NEVER emitted here).  No ``i2i`` spec is ever emitted
    without ``input_urls``; since we never pass ``input_urls`` here, we never
    emit ``i2i`` specs.

    Raises ``ImagePipelineError`` if no usable copy specs can be derived (the
    page spec carries neither an explicit ``images`` list nor enough copy to
    build a meaningful prompt).
    """
    page_id = str(page_spec.get("page_id") or page_spec.get("id") or "").strip()
    page_name = str(page_spec.get("name") or page_spec.get("title") or "page").strip()

    # FIX-XC-02c: resolve an OPTIONAL DIU style card ONCE, up front, so a
    # set-but-unresolvable id fails loud regardless of which branch below runs.
    style_card_id = str(page_spec.get("style_card_id") or "").strip()
    style_card_text = _resolve_style_card_block(style_card_id) if style_card_id else ""

    def _carry_ratio(dst: dict, src: dict) -> None:
        """FIX-IMG-03: copy an optional aspect_ratio / resolution from src->dst."""
        for _rk in ("aspect_ratio", "resolution"):
            if src.get(_rk) is not None:
                _rv = str(src.get(_rk)).strip()
                if _rv:
                    dst[_rk] = _rv

    # 1) Explicit images list — use directly (add explicit mode='t2i').
    explicit = page_spec.get("images")
    if isinstance(explicit, list) and explicit:
        specs: list[dict] = []
        for entry in explicit:
            if not isinstance(entry, dict):
                continue
            sid = str(entry.get("id") or "").strip()
            prompt = str(entry.get("prompt") or "").strip()
            if not sid or not prompt:
                continue
            # FIX-XC-02c: an operator-supplied style card also governs pre-authored
            # explicit prompts — append its Brand-Style direction as an extra block.
            if style_card_text.strip():
                prompt = (
                    prompt + "\n\nBlock 8 — Brand-Style (style card "
                    + style_card_id + "): " + style_card_text.strip()
                )
            spec: dict[str, Any] = {
                "id": sid,
                "prompt": prompt,
                "mode": "t2i",  # always explicit; i2i is never emitted here
                "alt": str(entry.get("alt") or f"{page_name} image"),
                "text_bearing": bool(entry.get("text_bearing")),
            }
            if page_id:
                spec["used_on_page_id"] = page_id
            if "locator" in entry:
                spec["locator"] = entry["locator"]
            _carry_ratio(spec, entry)
            specs.append(spec)
        if specs:
            return specs

    # 2) FIX-XC-04f: derive ONE 8-block, brand-graded spec per major page SECTION
    #    (not a single ~200-char generic hero). Brand colors template the block-4
    #    Grade Block; each prompt clears PROMPT_CHAR_FLOOR at generation time.
    import re as _re
    brand_colors = _brand_colors(page_spec)

    def _slug(text: str, fallback: str) -> str:
        return _re.sub(r"[^A-Za-z0-9]+", "-", str(text).lower()).strip("-") or fallback

    page_slug = _slug(page_name, "page")

    sections = page_spec.get("sections")
    section_list: list[dict] = []
    if isinstance(sections, list):
        section_list = [s for s in sections if isinstance(s, dict)]

    if not section_list:
        # No explicit sections: synthesize a single hero section from page copy so
        # the page still gets one full 8-block prompt (never the old thin stub).
        copy_block = page_spec.get("copy") or {}
        section_list = [{
            "role": "hero",
            "heading": str(copy_block.get("headline") or page_name).strip(),
            "copy": " ".join(
                p for p in (
                    str(copy_block.get("subheadline") or "").strip(),
                    str(copy_block.get("body") or "").strip(),
                ) if p
            ),
        }]

    specs = []
    used_ids: set[str] = set()
    for idx, section in enumerate(section_list):
        role = str(section.get("role") or section.get("type") or "").strip()
        base = _slug(section.get("id") or role or f"section-{idx + 1}", f"section-{idx + 1}")
        slide_id = f"{page_slug}-{base}"
        # Guarantee unique ids across sections (build_prompts_json rejects dupes).
        candidate = slide_id
        n = 2
        while candidate in used_ids:
            candidate = f"{slide_id}-{n}"
            n += 1
        slide_id = candidate
        used_ids.add(slide_id)

        prompt, text_bearing = _build_section_prompt(
            page_name, section, brand_colors, style_card_text=style_card_text
        )
        prompt = _deepen_to_band(
            prompt, page_name=page_name, role=role,
            context=" ".join(p for p in (str(section.get("heading") or section.get("title") or "").strip(),
                                         str(section.get("copy") or section.get("body") or section.get("text") or "").strip())
                             if p)[:_COPY_CONTEXT_CAP] or f"the {role or 'content'} section of {page_name}",
            palette=", ".join(brand_colors) if brand_colors else "the approved brand palette",
        )
        alt = str(section.get("alt") or section.get("heading") or section.get("title")
                  or f"{page_name} {role or 'section'} image").strip()

        spec = {
            "id": slide_id,
            "prompt": prompt,
            "mode": "t2i",
            "alt": alt,
            "text_bearing": text_bearing,
        }
        if page_id:
            spec["used_on_page_id"] = page_id
        if isinstance(section.get("locator"), dict):
            spec["locator"] = section["locator"]
        _carry_ratio(spec, section)
        specs.append(spec)

    return specs


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_image_pipeline(
    page_spec: dict,
    run_dir: str,
    *,
    location_id: str | None = None,
    location_pit: str | None = None,
    env: dict | None = None,
    resolution_class: str = _PNG_RES_DEFAULT,
    # Injected for tests — never set in production.
    _generate_runner=None,
    _upload_opener=None,
    _folder_opener=None,
    _cdn_fetcher=None,
    _sanity_checker=None,
) -> dict:
    """Run the complete image pipeline for one page and return a result dict.

    This is the ONLY public entry point callers use.  It chains:

      build_prompts_json → generate_images → [create_media_folder] →
      upload_media (per PNG) → CDN re-fetch → image_tag → build_image_manifest

    Args:
        page_spec: The per-page build specification dict (see ``_derive_copy_specs``
            for the expected shape).
        run_dir: The build run directory.  ``images/`` and ``logs/`` subdirectories
            are created under it.
        location_id: The GHL sub-account location id.
            When ``None``, resolved from the env via ``ghl_media.resolve_location_id``.
        location_pit: The GHL LOCATION Private Integration Token (Bearer).
            When ``None``, resolved from the env via ``ghl_media.resolve_location_pit``.
        env: Optional env dict override (default: ``os.environ``).  Used by tests
            to inject credentials without touching the real environment.

    Returns a dict::

        {
            "ok": bool,                 # True iff all images verified at CDN HTTP 200
            "page_id": str,             # from page_spec
            "manifest_path": str,       # absolute path to images/manifest.json
            "manifest": [...],          # the validated manifest records (or [])
            "img_tags": [...],          # list of <img src="..."> strings (one per image)
            "images_dir": str,          # <run_dir>/images/
            "cdn_log": str,             # <run_dir>/logs/asset-cdn.log
            "error": str | None,        # human-readable failure reason (None on success)
            "honest_fail": bool,        # True when the failure is a data-integrity failure
        }

    NEVER returns a synthetic/stub ``cdn_url``.  On any failure (missing key,
    PNG not generated, CDN non-200, etc.) the return dict has ``ok=False`` plus
    an honest ``error`` string, and ``images/manifest.json`` is written with the
    failure reason so the B2 gate sees it and fails the build.

    Raises:
        TypeError: if ``page_spec`` is not a dict or ``run_dir`` is not a str.
    """
    if not isinstance(page_spec, dict):
        raise TypeError(f"page_spec must be a dict (got {type(page_spec).__name__})")
    if not isinstance(run_dir, str) or not run_dir.strip():
        raise TypeError("run_dir must be a non-empty string")

    env = env if env is not None else os.environ
    run_dir = os.path.abspath(run_dir)
    images_dir = os.path.join(run_dir, "images")
    logs_dir = os.path.join(run_dir, "logs")
    manifest_path = os.path.join(images_dir, "manifest.json")
    cdn_log_path = os.path.join(logs_dir, "asset-cdn.log")
    prompts_path = os.path.join(images_dir, "prompts.json")

    page_id = str(page_spec.get("page_id") or page_spec.get("id") or "").strip()

    # ── Failure helper — write an honest-fail manifest so the B2 gate sees it ──
    def _fail(reason: str, *, honest: bool = True) -> dict:
        Path(images_dir).mkdir(parents=True, exist_ok=True)
        fail_record = {
            "ok": False,
            "error": reason,
            "honest_fail": honest,
            "page_id": page_id,
        }
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump([fail_record], fh, indent=2)
        return {
            "ok": False,
            "page_id": page_id,
            "manifest_path": manifest_path,
            "manifest": [],
            "img_tags": [],
            "images_dir": images_dir,
            "cdn_log": cdn_log_path,
            "error": reason,
            "honest_fail": honest,
        }

    # ── Step 0: KIE key present (any shared-canon alias)? Fail loud before any network call. ──
    try:
        _resolve_kie_api_key(env)
    except ImagePipelineError as exc:
        logger.error("IMAGE PIPELINE FAIL (key absent): %s", exc)
        return _fail(str(exc), honest=True)

    # ── Step 1: Resolve the GHL LOCATION PIT + location id. ───────────────────
    try:
        _location_id = location_id or ghl_media.resolve_location_id(env)
        _location_pit = location_pit or ghl_media.resolve_location_pit(env)
    except RuntimeError as exc:
        logger.error("IMAGE PIPELINE FAIL (credentials): %s", exc)
        return _fail(str(exc), honest=True)

    # ── Step 2: Derive copy_specs from the page spec. ─────────────────────────
    try:
        copy_specs = _derive_copy_specs(page_spec)
    except ImagePipelineError as exc:
        logger.error("IMAGE PIPELINE FAIL (copy_specs): %s", exc)
        return _fail(str(exc), honest=True)

    # ── Step 3: Build prompts.json (always explicit mode='t2i'). ──────────────
    # Specs from _derive_copy_specs always carry mode='t2i'; build_prompts_json
    # receives them with default_mode='t2i' as a belt-and-suspenders guard so
    # a hypothetical spec that omits mode also lands on 't2i' and never on 'i2i'.
    # FIX-XC-04f (d): enforce_floor=True — a prompt below PROMPT_CHAR_FLOOR raises
    # here, so a weak prompt can never reach the paid Kie subprocess below.
    try:
        enriched_specs = ghl_media.build_prompts_json(
            copy_specs,
            out_path=prompts_path,
            default_mode="t2i",
            enforce_floor=True,
        )
    except (ValueError, RuntimeError) as exc:
        logger.error("IMAGE PIPELINE FAIL (build_prompts_json): %s", exc)
        return _fail(str(exc), honest=True)

    expected_ids = [s["slide"] for s in enriched_specs]
    # Map slide id -> enriched spec (prompt/mode/alt/locator) — needed both by the
    # sanity-regen stage (to rebuild a single-slot prompts.json) and the upload loop.
    spec_map = {s["slide"]: s for s in enriched_specs}

    # ── Step 4: Generate images (shells kie_generate.py, verifies PNG bytes). ──
    # Retry up to 3 attempts with 30-second backoff to handle transient KIE latency.
    # NEVER returns a stub — any genuine failure after all retries is an honest FAIL.
    _KIE_MAX_ATTEMPTS = 3
    _KIE_BACKOFF_S = 30
    gen_result: dict | None = None
    gen_exc: Exception | None = None
    for _attempt in range(1, _KIE_MAX_ATTEMPTS + 1):
        try:
            gen_result = ghl_media.generate_images(
                prompts_path,
                images_dir,
                expected_ids=expected_ids,
                runner=_generate_runner,  # None in production (real subprocess)
            )
            if gen_result["ok"]:
                break  # success — exit retry loop
            if _attempt < _KIE_MAX_ATTEMPTS:
                logger.warning(
                    "IMAGE PIPELINE attempt %d/%d incomplete (missing=%s); retrying in %ds",
                    _attempt, _KIE_MAX_ATTEMPTS,
                    gen_result.get("missing"), _KIE_BACKOFF_S,
                )
                import time as _time
                _time.sleep(_KIE_BACKOFF_S)
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            gen_exc = exc
            logger.error("IMAGE PIPELINE attempt %d/%d exception: %s", _attempt, _KIE_MAX_ATTEMPTS, exc)
            if _attempt < _KIE_MAX_ATTEMPTS:
                import time as _time
                _time.sleep(_KIE_BACKOFF_S)
    if gen_exc is not None and gen_result is None:
        return _fail(str(gen_exc), honest=True)

    if gen_result is None or not gen_result["ok"] or gen_result["missing"]:
        missing_str = ", ".join(gen_result["missing"]) if gen_result and gen_result["missing"] else "unknown"
        reason = (
            f"KIE image generation failed after {_KIE_MAX_ATTEMPTS} attempts "
            f"(exit={gen_result['exit_code'] if gen_result else 'N/A'}); "
            f"missing PNGs: {missing_str}"
        )
        logger.error("IMAGE PIPELINE FAIL (generate_images result): %s", reason)
        return _fail(reason, honest=True)

    # FIX-IMG-08: record the prompt-count-scaled subprocess cap into run evidence.
    _append_cdn_log(
        cdn_log_path,
        0,
        f"kie-subprocess-timeout={gen_result.get('subprocess_timeout')}s",
        f"prompts={len(expected_ids)}",
    )

    # ── Step 4.5: FIX-IMG-01 deterministic PNG sanity + bounded regeneration. ──
    # Existence + provenance are NOT enough — a blank / garbled / off-size raster
    # passes PNG-magic + CDN-200 + taskId. Inspect each PNG's bytes; regenerate a
    # failing SLOT up to 2 times; then hard FAIL with the slot id (never upload a
    # bad image, never silently skip).
    _sanity = _sanity_checker or (lambda p: _png_sanity(p, resolution_class))

    def _regenerate_slot(slide_id: str) -> dict:
        """Re-run generation for ONE slide into images_dir; returns the
        generate_images result for that single slot."""
        enriched = spec_map.get(slide_id, {})
        file_entry: dict[str, Any] = {
            "slide": slide_id,
            "prompt": str(enriched.get("prompt") or ""),
            "mode": str(enriched.get("mode") or "t2i"),
        }
        if file_entry["mode"] == "i2i" and enriched.get("input_urls"):
            file_entry["input_urls"] = list(enriched["input_urls"])
        single_path = os.path.join(images_dir, f"__regen_{slide_id}.json")
        with open(single_path, "w", encoding="utf-8") as fh:
            json.dump([file_entry], fh)
        try:
            return ghl_media.generate_images(
                single_path, images_dir,
                expected_ids=[slide_id], runner=_generate_runner,
            )
        finally:
            try:
                os.remove(single_path)
            except OSError:
                pass

    _SANITY_MAX_REGEN = 2
    for img_entry in gen_result["images"]:
        slide_id = img_entry["id"]
        png_path = img_entry["file"]
        ok_sane, reason = _sanity(png_path)
        regens = 0
        while not ok_sane and regens < _SANITY_MAX_REGEN:
            regens += 1
            logger.warning(
                "IMAGE SANITY FAIL slot %r (%s) — regenerating %d/%d",
                slide_id, reason, regens, _SANITY_MAX_REGEN,
            )
            _append_cdn_log(cdn_log_path, 0, f"sanity-regen-{regens} | {slide_id}", reason)
            regen_result = _regenerate_slot(slide_id)
            if not regen_result.get("ok"):
                reason = (
                    f"regeneration attempt {regens} failed to produce a PNG "
                    f"(missing={regen_result.get('missing')})"
                )
                continue
            png_path = os.path.join(images_dir, f"{slide_id}.png")
            ok_sane, reason = _sanity(png_path)
        if not ok_sane:
            fail_reason = (
                f"image sanity FAIL for slot {slide_id!r} after {regens} "
                f"regeneration(s): {reason}"
            )
            logger.error("IMAGE PIPELINE FAIL (sanity): %s", fail_reason)
            return _fail(fail_reason, honest=True)

    # ── Step 5: (Optional) create a per-run media folder. ─────────────────────
    folder_id: str | None = None
    page_name = str(page_spec.get("name") or page_spec.get("title") or "skill6-run").strip()
    import re as _re
    run_folder_name = _re.sub(r"[^A-Za-z0-9._-]+", "-", page_name.strip()).strip("-") or "skill6-run"
    try:
        folder_result = ghl_media.create_media_folder(
            name=run_folder_name,
            location_id=_location_id,
            pit=_location_pit,
            opener=_folder_opener,  # None in production (real HTTP)
        )
        folder_id = folder_result["folderId"]
        logger.info("Created media folder %r (id=%s)", run_folder_name, folder_id)
    except RuntimeError as exc:
        # Non-fatal: fall back to name-prefix (images still land in root).
        logger.warning(
            "create_media_folder failed (%s) — uploading to media root with name prefix",
            exc,
        )
        folder_id = None

    name_prefix = ghl_media.media_folder_name_prefix(run_folder_name) if folder_id is None else ""

    # ── Step 6: Upload each PNG, re-fetch CDN URL, build manifest records. ─────
    manifest_records: list[dict] = []
    img_tags: list[str] = []

    # spec_map (slide id -> enriched spec) was built right after build_prompts_json.
    for img_entry in gen_result["images"]:
        slide_id = img_entry["id"]
        png_path = img_entry["file"]
        enriched = spec_map.get(slide_id, {})
        alt_text = str(enriched.get("alt") or slide_id)
        media_name = f"{name_prefix}{slide_id}.png"

        # 6a: Upload (bare Python, services.* — not WAF-gated).
        try:
            upload_result = ghl_media.upload_media(
                png_path=png_path,
                location_id=_location_id,
                name=media_name,
                pit=_location_pit,
                parent_id=folder_id,
                opener=_upload_opener,  # None in production
            )
        except (ValueError, RuntimeError) as exc:
            reason = f"upload_media failed for {slide_id!r}: {exc}"
            logger.error("IMAGE PIPELINE FAIL (%s)", reason)
            return _fail(reason, honest=True)

        cdn_url: str = upload_result["url"]
        file_id: str = upload_result["fileId"]

        # 6b: Re-fetch CDN URL — assert HTTP 200 before trusting it.
        if _cdn_fetcher is not None:
            # Test injection: callable(cdn_url) -> int
            cdn_status = int(_cdn_fetcher(cdn_url))
        else:
            cdn_status = _refetch_cdn_url(cdn_url)

        log_label = "OK" if cdn_status == 200 else f"FAIL-{cdn_status}"
        _append_cdn_log(cdn_log_path, cdn_status, cdn_url, log_label)

        if cdn_status != 200:
            reason = (
                f"CDN re-fetch returned HTTP {cdn_status} for {cdn_url!r} "
                f"(slide {slide_id!r}) — refusing to record a non-live CDN URL"
            )
            logger.error("IMAGE PIPELINE FAIL: %s", reason)
            return _fail(reason, honest=True)

        # 6c: Build the <img> tag for the B1/B3 customCode splice.
        tag = ghl_media.image_tag(cdn_url, alt_text)
        img_tags.append(tag)

        # 6d: Accumulate manifest record.
        manifest_records.append({
            "id": slide_id,
            "prompt": str(enriched.get("prompt") or ""),
            "file": png_path,
            "cdn_url": cdn_url,
            "cdn_http_status": cdn_status,
            "used_on_page_id": str(enriched.get("used_on_page_id") or page_id),
            "file_id": file_id,
        })

    # Guard: at least one image must have been processed.
    if not manifest_records:
        reason = (
            "Image pipeline produced zero manifest records — no images were "
            "generated, uploaded, or verified.  Check KIE_API_KEY and the "
            "prompts.json for this page."
        )
        logger.error("IMAGE PIPELINE FAIL: %s", reason)
        return _fail(reason, honest=True)

    # ── Step 7: Write manifest.json (validates https + 200 per record). ────────
    try:
        validated = ghl_media.build_image_manifest(manifest_records, out_path=manifest_path)
    except ValueError as exc:
        reason = f"build_image_manifest rejected a record: {exc}"
        logger.error("IMAGE PIPELINE FAIL (manifest): %s", reason)
        return _fail(reason, honest=True)

    logger.info(
        "Image pipeline complete: %d image(s) verified and manifested for page %r",
        len(validated),
        page_id,
    )

    return {
        "ok": True,
        "page_id": page_id,
        "manifest_path": manifest_path,
        "manifest": validated,
        "img_tags": img_tags,
        "images_dir": images_dir,
        "cdn_log": cdn_log_path,
        "error": None,
        "honest_fail": False,
    }


__all__ = [
    "ImagePipelineError",
    "run_image_pipeline",
]
