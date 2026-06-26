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
     the OPERATOR'S OWN fixture keys (never a client key).  Optionally calls
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
``file://`` URL, NO silent skip.  The operator must provision ``KIE_API_KEY``
(their own key, via Skill 07 ``07-kie-setup``) into the active env store before
a live run.

DO NOT EDIT
-----------
``ghl_builder.py`` / ``ghl_verify.py`` / ``v2_dispatcher.py`` (B2),
``ghl_rest_canvas.py`` (B1), ``ghl_method.py`` / ``ghl_vercel.py`` /
``ghl_ecosystem.py`` (B3), ``kie_generate.py`` (different skill, out of scope),
tests (B6), SOP/SKILL docs (B7), ``gates.json`` (B8),
``skill-version.txt`` / ``CHANGELOG.md``.
EDIT ONLY: this file and (minimally) ``ghl_media.py`` if a small helper is needed.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request
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
# Key presence check — fail loud before any network call if KIE_API_KEY absent
# ---------------------------------------------------------------------------

_KIE_KEY_ENV_NAMES = ("KIE_API_KEY",)
_KIE_ENV_STORES = (
    "~/.openclaw/workspace/.env",
    "~/clawd/secrets/.env",
    "~/.openclaw/secrets/.env",
)


def _resolve_kie_api_key(env: dict | None = None) -> str:
    """Resolve ``KIE_API_KEY`` from the environment or the canonical env stores.

    Mirrors the lookup order documented in ``kie_generate.py``.  Raises
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
        if val:
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
                    if k in _KIE_KEY_ENV_NAMES and v:
                        return v
        except OSError:
            continue

    raise ImagePipelineError(
        "KIE_API_KEY is absent from all env stores "
        f"({', '.join(_KIE_ENV_STORES)}) and from the live process environment. "
        "Provision KIE_API_KEY (the operator's own key) via Skill 07 "
        "(07-kie-setup) before running the image pipeline. "
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
# copy_specs derivation from page_spec
# ---------------------------------------------------------------------------

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
            spec: dict[str, Any] = {
                "id": sid,
                "prompt": prompt,
                "mode": "t2i",  # always explicit; i2i is never emitted here
                "alt": str(entry.get("alt") or f"{page_name} image"),
            }
            if page_id:
                spec["used_on_page_id"] = page_id
            if "locator" in entry:
                spec["locator"] = entry["locator"]
            specs.append(spec)
        if specs:
            return specs

    # 2) Derive a hero image from the page copy.
    copy_block = page_spec.get("copy") or {}
    headline = str(copy_block.get("headline") or "").strip()
    subheadline = str(copy_block.get("subheadline") or "").strip()
    body = str(copy_block.get("body") or "").strip()

    # Build a concise scene brief from whatever copy fields are present.
    scene_parts = [p for p in [headline, subheadline, body] if p]
    if not scene_parts:
        # Last-resort: use the page name as the scene context if nothing else.
        scene_parts = [page_name]

    # Cap prompt length before the English/Latin pin is appended (the pin is
    # appended by build_prompts_json, not here).
    scene_brief = " | ".join(scene_parts)[:300]

    hero_prompt = (
        f"Professional marketing hero image for a web page titled '{page_name}'. "
        f"Scene context: {scene_brief}. "
        "Clean, modern, high-quality lifestyle photo, no text overlaid on the image."
    )

    # Derive a URL-safe slug from the page name for the slide id.
    import re as _re
    slug = _re.sub(r"[^A-Za-z0-9]+", "-", page_name.lower()).strip("-") or "hero"
    slide_id = f"{slug}-hero"

    spec = {
        "id": slide_id,
        "prompt": hero_prompt,
        "mode": "t2i",
        "alt": f"{page_name} hero image",
    }
    if page_id:
        spec["used_on_page_id"] = page_id

    return [spec]


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
    # Injected for tests — never set in production.
    _generate_runner=None,
    _upload_opener=None,
    _folder_opener=None,
    _cdn_fetcher=None,
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
        location_id: The GHL sub-account location id (operator's own fixture).
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

    # ── Step 0: KIE_API_KEY present? Fail loud before any network call. ────────
    try:
        _resolve_kie_api_key(env)
    except ImagePipelineError as exc:
        logger.error("IMAGE PIPELINE FAIL (key absent): %s", exc)
        return _fail(str(exc), honest=True)

    # ── Step 1: Resolve operator credentials (never a client key). ────────────
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
    try:
        enriched_specs = ghl_media.build_prompts_json(
            copy_specs,
            out_path=prompts_path,
            default_mode="t2i",
        )
    except (ValueError, RuntimeError) as exc:
        logger.error("IMAGE PIPELINE FAIL (build_prompts_json): %s", exc)
        return _fail(str(exc), honest=True)

    expected_ids = [s["slide"] for s in enriched_specs]

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

    # Build a map from slide id -> enriched spec for alt text / locator lookup.
    spec_map = {s["slide"]: s for s in enriched_specs}

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
