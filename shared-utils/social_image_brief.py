#!/usr/bin/env python3
"""
social_image_brief.py — F29 unified image brief schema + post-generation
visual QC validation.

The finding (TODO F29): Skill 35 has detailed pre-generation checks; Skill 57's
visual architect prompt is generic and names Midjourney v6 while the pipeline
uses other provider paths. One image brief schema must carry brand palette,
logo rules, audience, composition, copy, approved assets, safe areas and
destination dimensions; routing goes by CAPABILITY (e.g. reliable text
rendering), never a stale model name; and the DELIVERED asset is validated
(dimensions, crops, legibility/OCR, spelling, brand consistency) before
scheduling, with preview + original URLs recorded, bounded regeneration
cost/retries, failed assets isolated and alternatives exposed for approval.

Schema lives in shared-utils/social_prompt_policy.json
(image_brief_schema). This module:

  1. validate_brief(brief) — required-field gate BEFORE prompt compilation
     (missing required field fails the brief before any prompt is compiled).
  2. validate_delivered_asset(asset) — post-generation visual QC: dimensions
     vs destination_dimensions, crop/safe-area, legibility/OCR match vs the
     approved copy (spelling lock), brand consistency (palette hexes present,
     logo not redrawn), preview/original URL recording and revision match.
  3. isolate_and_retry(assets) — one failed asset never discards successful
     copy or other account assets; regeneration is bounded (max_retries,
     max_cost) and exposes alternatives for approval.

Deterministic fixture-driven checks (no live model calls, no real OCR) —
the actual vision reviewer sees the asset per F37's strict rules; this module
validates the STRUCTURED inputs/receipts around it.

STDLIB ONLY.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

# Required fields (mirrors social_prompt_policy.json image_brief_schema.required)
REQUIRED_FIELDS = ("brand_palette", "logo_rules", "audience", "composition",
                   "copy", "approved_assets", "safe_areas",
                   "destination_dimensions")

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
RATIO_RE = re.compile(r"^\d{1,2}:\d{1,2}$")
PIXELS_RE = re.compile(r"^(\d{2,5})x(\d{2,5})$")


def _fail(code: str, detail: str) -> dict:
    return {"code": code, "detail": detail}


# ─── 1. Brief validation (BEFORE prompt compilation / spend) ────────────────

def validate_brief(brief: dict) -> dict:
    """Validate ONE unified image brief against the schema. Returns
    {valid, problems[]} — problems carry AF-BRIEF-* codes. Missing required
    fields fail the brief BEFORE any prompt is compiled or any provider is
    charged."""
    problems: list = []
    if not isinstance(brief, dict):
        return {"valid": False, "problems": [{"code": "AF-BRIEF-SCHEMA",
                 "detail": "brief is not an object"}]}
    for field in REQUIRED_FIELDS:
        if field not in brief or brief[field] in (None, "", [], {}):
            problems.append({
                "code": "AF-BRIEF-SCHEMA",
                "detail": f"required brief field '{field}' missing/empty — the "
                          "unified image brief schema requires brand_palette, "
                          "logo_rules, audience, composition, copy, "
                          "approved_assets, safe_areas, destination_dimensions."})

    # brand_palette: verified hex values only (never ad-hoc colors)
    pal = brief.get("brand_palette")
    if isinstance(pal, dict) and pal:
        for slot, hexv in pal.items():
            if not (isinstance(hexv, str) and HEX_RE.match(hexv)):
                problems.append({
                    "code": "AF-BRIEF-PALETTE",
                    "detail": f"brand_palette slot {slot!r} value {hexv!r} is not "
                              "a verified #RRGGBB hex from the approved brand profile."})

    # logo_rules: references carry role-correct instructions (F32 rule)
    rules = brief.get("logo_rules")
    if isinstance(rules, dict):
        for ref in rules.get("references") or []:
            if isinstance(ref, dict) and not ref.get("role"):
                problems.append({
                    "code": "AF-BRIEF-LOGO-REF-ROLE",
                    "detail": f"logo reference {ref.get('name')!r} has no role "
                              "(identity|product|layout|style) — per-reference "
                              "role instructions are mandatory."})

    # copy: on_image_text present (may be empty string = explicitly no text)
    copy = brief.get("copy")
    if isinstance(copy, dict):
        if "on_image_text" not in copy:
            problems.append({
                "code": "AF-BRIEF-COPY",
                "detail": "copy.on_image_text missing — state the exact approved "
                          "on-image copy, or an empty string meaning explicitly "
                          "NO text in this image."})
        if copy.get("on_image_text") and not copy.get("spelling_lock"):
            problems.append({
                "code": "AF-BRIEF-SPELLING-LOCK",
                "detail": "copy.on_image_text present but spelling_lock is not "
                          "true — the exact-spelling rule is mandatory."})

    # destination_dimensions: platform + ratio + pixels
    dest = brief.get("destination_dimensions")
    if isinstance(dest, dict) and dest:
        if not RATIO_RE.match(str(dest.get("ratio", ""))):
            problems.append({
                "code": "AF-BRIEF-DIMENSIONS",
                "detail": f"destination_dimensions.ratio {dest.get('ratio')!r} is "
                          "not an NN:NN ratio."})
        if not PIXELS_RE.match(str(dest.get("pixels", ""))):
            problems.append({
                "code": "AF-BRIEF-DIMENSIONS",
                "detail": f"destination_dimensions.pixels {dest.get('pixels')!r} "
                          "is not WxH pixels."})

    # safe_areas present with a keep-in spec
    safe = brief.get("safe_areas")
    if isinstance(safe, dict) and safe and not safe.get("keep_in"):
        problems.append({
            "code": "AF-BRIEF-SAFE-AREAS",
            "detail": "safe_areas.keep_in missing (e.g. 'central 80% of the "
                      "frame' or per-platform px margins)."})

    return {"valid": not problems, "problems": problems}


# ─── 2. Post-generation validation (delivered asset) ─────────────────────────

def validate_delivered_asset(asset: dict) -> dict:
    """Validate a DELIVERED asset against its brief before scheduling.

    asset fields:
      brief: the unified brief this asset was generated from
      delivered_dimensions: {width, height} or 'WxH'
      delivered_ratio: 'W:H' (optional; computed from dimensions if absent)
      ocr_text: str — legibility/OCR result from the actual vision reviewer
        (the reviewer sees the real asset; this validates the receipt)
      palette_seen: [hex] — brand palette sampled from the delivered image
      logo_reproduced: bool — the actual vision reviewer's mark-fidelity verdict
      crop_respects_safe_areas: bool — reviewer's crop/safe-area verdict
      preview_url, original_url: recorded URLs
      revision: str — the approved revision id this asset must match
      approved_revision: str — the revision the preview references

    Deterministic checks:
      AF-VQC-DIMENSIONS  delivered pixel dimensions == destination_dimensions
      AF-VQC-CROP        crop violates the declared safe areas
      AF-VQC-OCR         delivered text != approved copy exactly (spelling lock)
      AF-VQC-BRAND       palette drifted / mark not reproduced faithfully
      AF-VQC-REVISION    preview does not reference the approved revision
      AF-VQC-URLS        preview/original URLs missing (receipt incomplete)
    """
    problems: list = []
    brief = asset.get("brief") or {}
    dest = brief.get("destination_dimensions") or {}

    # dimensions
    got = asset.get("delivered_dimensions")
    want = str(dest.get("pixels", ""))
    if got is None or not want:
        problems.append({"code": "AF-VQC-DIMENSIONS",
                         "detail": "delivered dimensions or destination spec missing"})
    else:
        got_str = got if isinstance(got, str) else \
            f"{got.get('width')}x{got.get('height')}"
        if _norm_pixels(got) != _norm_pixels(want):
            problems.append({
                "code": "AF-VQC-DIMENSIONS",
                "detail": f"delivered {got} != destination {want} — wrong-size "
                          "assets never schedule."})

    # crop / safe areas (the actual reviewer's receipt)
    if asset.get("crop_respects_safe_areas") is False:
        problems.append({
            "code": "AF-VQC-CROP",
            "detail": "delivered crop violates the declared safe areas — "
                      "invalid crop fails visual QC before scheduling."})

    # legibility/OCR vs approved copy (spelling lock)
    want_text = (brief.get("copy") or {}).get("on_image_text") or ""
    got_text = (asset.get("ocr_text") or "").strip()
    if want_text:
        if got_text != want_text.strip():
            problems.append({
                "code": "AF-VQC-OCR",
                "detail": f"delivered text {got_text!r} != approved copy "
                          f"{want_text!r} — misspelled or missing on-image text "
                          "fails visual QC."})
    elif got_text:
        problems.append({
            "code": "AF-VQC-OCR",
            "detail": "approved copy is EMPTY (no text allowed) but the delivered "
                      "image contains letterforms — fails visual QC."})

    # brand consistency
    pal = [v for v in (brief.get("brand_palette") or {}).values()
           if isinstance(v, str)]
    seen = [h.lower() for h in (asset.get("palette_seen") or [])]
    if pal and seen:
        normalized_want = {h.lower() for h in pal}
        normalized_seen = {h.lower() for h in seen}
        if not (normalized_want & normalized_seen_compat(seen)):
            problems.append({
                "code": "AF-VQC-BRAND",
                "detail": "delivered image shows none of the approved brand "
                          "palette — wrong-brand art fails visual QC."})
    if asset.get("logo_reproduced") is False:
        problems.append({
            "code": "AF-VQC-BRAND",
            "detail": "vision reviewer reports the logo/mark was not reproduced "
                      "faithfully — fails visual QC."})

    # revision + URL receipts
    rev = asset.get("revision")
    approved = asset.get("approved_revision")
    if rev and approved and rev != approved:
        problems.append({
            "code": "AF-VQC-REVISION",
            "detail": f"preview references revision {approved!r} but the asset "
                      f"is {rev!r} — preview and publish inputs must reference "
                      "the approved revision."})
    if not asset.get("preview_url") or not asset.get("original_url"):
        problems.append({
            "code": "AF-VQC-RECEIPT",
            "detail": "preview_url and original_url must both be recorded with "
                      "the delivered asset."})

    return {"valid": not problems, "problems": problems}


def _norm_pixels(v) -> str:
    if isinstance(v, dict):
        return f"{v.get('width')}x{v.get('height')}".lower()
    return str(v).lower().replace("×", "x")


def normalized_seen_compat(seen: list) -> set:
    return {h.lower() for h in seen if isinstance(h, str)}


# ─── 3. Isolation + bounded regeneration ─────────────────────────────────────

def isolate_and_retry(results: dict, *, max_retries: int = 2,
                      max_cost_per_retry: float = 0.12) -> dict:
    """One failing asset NEVER discards successful copy or other account
    assets. Returns per-asset dispositions: healthy assets are APPROVED and
    continue; failed assets are isolated with bounded regeneration cost and
    retries, and alternatives are exposed for approval (never silent drops).

    results: {asset_id: {valid, problems}} — the per-asset validation receipts.
    """
    out = {"healthy": {}, "failed": {}, "bounded": True,
           "policy": {"max_retries": max_retries,
                      "max_cost_per_retry_usd": max_cost_per_retry}}
    for asset_id, receipt in (results or {}).items():
        if receipt.get("valid"):
            out["healthy"][asset_id] = receipt
        else:
            out["failed"][asset_id] = {
                "receipt": receipt,
                "isolated": True,
                "regeneration": {
                    "attempts_remaining": max_retries,
                    "max_cost_per_retry_usd": max_cost_per_retry,
                    "expose_alternatives_for_approval": True,
                },
                "blocks_others": False,
            }
    return out


def route_by_capability(model_id: str, needs_text: bool,
                        capability_lookup=None) -> dict:
    """Route by CAPABILITY (reliable text rendering), never a stale model name.
    Uses model-capabilities.json via select_model.capabilities_for_model when no
    explicit lookup is given. GPT Image 2 / Agnes eligible through verified
    adapters; a text-bearing asset never routes to a non-text model."""
    caps = list(capability_lookup(model_id)) if capability_lookup else []
    if not caps:
        try:
            import select_model  # shared-utils sibling
            caps = select_model.capabilities_for_model(model_id)
        except Exception:
            caps = []
    text_capable = needs_text is False or "image_generation" in caps and \
        ("text_rendering" in caps or model_id.lower().find("gpt-image") >= 0 or
         model_id.lower().find("ideogram") >= 0 or model_id.lower().find("agnes") >= 0)
    if needs_text and not text_capable:
        return {"routed": False, "reason": (
            f"model '{model_id}' does not declare reliable text rendering — "
            "route text-bearing assets to a text-capable model by capability "
            "(Ideogram V3 DESIGN, GPT Image 2 via Kie, or Agnes).")}
    return {"routed": True, "model_id": model_id, "capabilities": caps}


if __name__ == "__main__":  # pragma: no cover
    import argparse as _ap
    import json as _json
    ap = _ap.ArgumentParser(description="F29 image brief + delivered-asset validator")
    ap.add_argument("--brief-file")
    ap.add_argument("--asset-file")
    a = ap.parse_args()
    if a.brief_file:
        brief = _json.load(open(a.brief_file, encoding="utf-8"))
        print(_json.dumps(validate_brief(brief), indent=2))
    if a.asset_file:
        asset = _json.load(open(a.asset_file, encoding="utf-8"))
        print(_json.dumps(validate_delivered_asset(asset), indent=2))