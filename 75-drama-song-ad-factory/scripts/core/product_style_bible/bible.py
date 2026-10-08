"""Product DNA (13.2) + Style Bible (13.3) + visual prompt compiler (15).

Compiler is the only path from bible to prompt: style bible is injected into
every visual prompt, reference asset IDs are bound by ID lookup, never by
manual copy. Image pins per planning/provider-contracts.md: sunburst default,
legacy gpt-image-2 for 3:1/1:3/9:21, no flare. Stdlib only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SCHEMA_VERSION = "1.0.0"

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

# ponytail: aspect set + caps follow provider-contracts.md; flare override needs
# an operator ruling — add an explicit allow_flare flag only then.

#: Aspects the image layer knows how to route.
ASPECTS = frozenset(("16:9", "9:16", "1:1", "5:4", "4:5",
                     "2:1", "1:2", "3:1", "1:3", "9:21"))

#: Legacy routes keep gpt-image-2, never 2.5 (provider-contracts.md R04).
LEGACY_ASPECTS = frozenset(("3:1", "1:3", "9:21"))

SUNBURST_MODEL = "gpt-image-2-5-sunburst"
LEGACY_MODEL = "gpt-image-2-legacy"  # per-mode suffix chosen by image layer

PROMPT_CAP_SUNBURST = 20000
PROMPT_CAP_LEGACY = 25000  # OWNER_CONFIRMED cap


def _load_enforcer():
    """Find shared-utils/kie_prompt_enforcer.py (repo checkout or installed skills tree)."""
    import os as _os
    import sys as _sys
    envd = _os.environ.get("OPENCLAW_SKILLS_DIR")
    dirs = [p / "shared-utils" for p in Path(__file__).resolve().parents]
    if envd:
        dirs.append(Path(envd) / "shared-utils")
    dirs += [Path.home() / ".openclaw" / "skills" / "shared-utils",
             Path("/data/.openclaw/skills/shared-utils")]
    for d in dirs:
        if (d / "kie_prompt_enforcer.py").is_file():
            _sys.path.insert(0, str(d))
            import kie_prompt_enforcer
            return kie_prompt_enforcer
    return None


_ENFORCER = _load_enforcer()


def enforce_prompt(prompt: str, model: str):
    """Route compiled KIE prompts through the shared enforcer when present.

    The numeric cap stays authoritative (band-named constants); the enforcer
    adds the check + audit trail required by rule 12. kind="verbatim": the
    style bible's compiled [STYLE]/[SHOT] prompt is a ceiling-only artifact."""
    KPE = _load_enforcer()
    if KPE is not None:
        v = KPE.check(
            model, prompt, kind="verbatim",
            fallback_max=PROMPT_CAP_LEGACY if model == LEGACY_MODEL else PROMPT_CAP_SUNBURST,
        )
        if not v.get("ok"):
            raise CompilerError("KIE_PROMPT_GUARD", "%s: %s" % (model, v.get("message", "")))
    return prompt

PRODUCT_TEXT_FIELDS = (
    "packaging_reference",
    "logo_mark",
    "color",
    "geometry",
    "label_placement",
    "cap_lid",
)

PRODUCT_KNOWN = frozenset(
    ["product_id", "schema_version", "dosage_or_quantity_text",
     "dosage_verified", "approved_texts", "prohibited_invented_text",
     "required_product_reference_images"] + list(PRODUCT_TEXT_FIELDS)
)

STYLE_TEXT_FIELDS = (
    "aesthetic",
    "rendering_style",
    "camera_language",
    "lens_tendencies",
    "lighting_doctrine",
    "contrast_architecture",
    "environment_texture",
    "grain_sharpness",
)

STYLE_LIST_MIN1 = (
    "color_palette",
    "visual_continuity_constraints",
    "banned_visual_cliches",
)

STYLE_KNOWN = frozenset(
    ["style_id", "schema_version", "aspect_ratio"]
    + list(STYLE_TEXT_FIELDS) + list(STYLE_LIST_MIN1)
)


class CompilerError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def validate_product(d):
    """Error list (empty = valid). Unverified dosage text always fails."""
    if not isinstance(d, dict):
        return ["NOT_A_RECORD"]
    errs = []
    for k in sorted(d):
        if k not in PRODUCT_KNOWN:
            errs.append("UNKNOWN_FIELD:%s" % k)
    for k in ["product_id"] + list(PRODUCT_TEXT_FIELDS):
        if k not in d:
            errs.append("MISSING:%s" % k)
    for k in ("prohibited_invented_text",
              "required_product_reference_images"):
        if k not in d:
            errs.append("MISSING:%s" % k)
    if errs:
        return errs
    if d.get("schema_version") != SCHEMA_VERSION:
        errs.append("BAD_SCHEMA_VERSION:%r" % (d.get("schema_version"),))
    pid = d["product_id"]
    if not isinstance(pid, str) or not ID_RE.match(pid):
        errs.append("BAD_PRODUCT_ID:%r" % (pid,))
    for k in PRODUCT_TEXT_FIELDS:
        v = d[k]
        if not isinstance(v, str) or not v.strip():
            errs.append("BAD_TEXT:%s" % k)
    for k in ("prohibited_invented_text",
              "required_product_reference_images"):
        v = d[k]
        if not isinstance(v, list) or not v or \
                any(not isinstance(i, str) or not i.strip() for i in v):
            errs.append("BAD_LIST:%s" % k)
    texts = d.get("approved_texts", [])
    if not isinstance(texts, list) or \
            any(not isinstance(t, str) for t in texts):
        errs.append("BAD_LIST:approved_texts")
    dose = d.get("dosage_or_quantity_text", "")
    if dose and not isinstance(dose, str):
        errs.append("BAD_TEXT:dosage_or_quantity_text")
    # 13.2: dosage/quantity text only when supplied AND verified.
    if isinstance(dose, str) and dose.strip() \
            and d.get("dosage_verified") is not True:
        errs.append("DOSAGE_UNVERIFIED:dosage text without verified source")
    if isinstance(dose, str) and dose.strip() \
            and d.get("dosage_verified") is True and dose not in texts:
        errs.append("DOSAGE_NOT_ALLOWLISTED:verified dose must be approved")
    overlap = set(texts) & set(d.get("prohibited_invented_text", []))
    if overlap:
        errs.append("ALLOWLIST_CONTAINS_PROHIBITED:%s" % sorted(overlap))
    return errs


def check_text(candidate, product):
    """Reject invented/prohibited text in a candidate string."""
    errs = []
    low = candidate.lower() if isinstance(candidate, str) else ""
    for p in product.get("prohibited_invented_text", []):
        if p.lower() in low:
            errs.append("INVENTED_PRODUCT_TEXT:%s" % p)
    dose = product.get("dosage_or_quantity_text", "")
    if isinstance(dose, str) and dose.strip() \
            and product.get("dosage_verified") is not True \
            and dose.lower() in low:
        errs.append("UNVERIFIED_DOSAGE_IN_TEXT")
    return errs


def validate_style(d):
    """Error list (empty = valid). Unknown aspect fails closed."""
    if not isinstance(d, dict):
        return ["NOT_A_RECORD"]
    errs = []
    for k in sorted(d):
        if k not in STYLE_KNOWN:
            errs.append("UNKNOWN_FIELD:%s" % k)
    for k in ["style_id"] + list(STYLE_TEXT_FIELDS):
        if k not in d:
            errs.append("MISSING:%s" % k)
    for k in STYLE_LIST_MIN1:
        if k not in d:
            errs.append("MISSING:%s" % k)
    if "aspect_ratio" not in d:
        errs.append("MISSING:aspect_ratio")
    if errs:
        return errs
    if d.get("schema_version") != SCHEMA_VERSION:
        errs.append("BAD_SCHEMA_VERSION:%r" % (d.get("schema_version"),))
    sid = d["style_id"]
    if not isinstance(sid, str) or not ID_RE.match(sid):
        errs.append("BAD_STYLE_ID:%r" % (sid,))
    for k in STYLE_TEXT_FIELDS:
        v = d[k]
        if not isinstance(v, str) or not v.strip():
            errs.append("BAD_TEXT:%s" % k)
    for k in STYLE_LIST_MIN1:
        v = d[k]
        if not isinstance(v, list) or not v or \
                any(not isinstance(i, str) or not i.strip() for i in v):
            errs.append("BAD_LIST:%s" % k)
    if d["aspect_ratio"] not in ASPECTS:
        errs.append("UNKNOWN_ASPECT:%r" % (d["aspect_ratio"],))
    return errs


def route_model(aspect_ratio):
    """Legacy 3:1/1:3/9:21 stay gpt-image-2; everything else sunburst."""
    if aspect_ratio in LEGACY_ASPECTS:
        return LEGACY_MODEL
    return SUNBURST_MODEL


def assert_compiled(prompt):
    """Downstream guard: prompt came from the compiler, not manual copy."""
    return isinstance(prompt, str) and "[compiled:style=" in prompt \
        and "[STYLE]" in prompt and "[/STYLE]" in prompt


def compile_visual_prompt(style, characters, product, shot):
    """Inject style bible + bind reference asset IDs. Raises CompilerError."""
    serrs = validate_style(style)
    if serrs:
        raise CompilerError("STYLE_INVALID", "; ".join(serrs))
    perrs = validate_product(product)
    if perrs:
        raise CompilerError("PRODUCT_INVALID", "; ".join(perrs))
    if not isinstance(shot, dict):
        raise CompilerError("SHOT_INVALID", "shot must be a dict")
    shot_id = shot.get("shot_id", "")
    base = shot.get("base_prompt", "")
    cids = shot.get("character_ids", [])
    if not isinstance(shot_id, str) or not shot_id.strip():
        raise CompilerError("SHOT_INVALID", "shot_id required")
    if not isinstance(base, str) or not base.strip():
        raise CompilerError("SHOT_INVALID", "base_prompt required")
    if not isinstance(cids, list):
        raise CompilerError("SHOT_INVALID", "character_ids must be a list")
    scanned = " ".join((base, style["rendering_style"],
                        style["lighting_doctrine"]))
    if "flare" in scanned.lower():
        raise CompilerError("FLARE_PROHIBITED",
                            "flare needs an operator ruling")
    by_id = {}
    for c in characters if isinstance(characters, list) else []:
        if isinstance(c, dict) and isinstance(c.get("character_id"), str):
            by_id[c["character_id"]] = c
    assets = []
    for cid in cids:
        rec = by_id.get(cid)
        if rec is None:
            raise CompilerError("UNKNOWN_CHARACTER", cid)
        refs = rec.get("approved_reference_asset_ids", [])
        if not refs:
            raise CompilerError("NO_REFERENCE_ASSET", cid)
        for a in refs:
            if a not in assets:
                assets.append(a)
    for a in product["required_product_reference_images"]:
        if a not in assets:
            assets.append(a)
    terrs = check_text(base, product)
    if terrs:
        raise CompilerError("INVENTED_PRODUCT_TEXT", "; ".join(terrs))
    model = route_model(style["aspect_ratio"])
    cap = PROMPT_CAP_LEGACY if model == LEGACY_MODEL \
        else PROMPT_CAP_SUNBURST
    allow = product.get("approved_texts", [])
    lines = ["[compiled:style=%s model=%s aspect=%s]"
             % (style["style_id"], model, style["aspect_ratio"]),
             "[STYLE]"]
    for k in list(STYLE_TEXT_FIELDS) + ["aspect_ratio"]:
        lines.append("%s: %s" % (k, style[k]))
    for k in STYLE_LIST_MIN1:
        lines.append("%s: %s" % (k, " | ".join(style[k])))
    lines.append("[/STYLE]")
    lines.append("[CHARACTER_REFS] %s [/CHARACTER_REFS]" % ", ".join(
        "%s=%s" % (cid, "+".join(by_id[cid]["approved_reference_asset_ids"]))
        for cid in cids))
    lines.append("[PRODUCT_REFS] %s [/PRODUCT_REFS]" %
                 ", ".join(product["required_product_reference_images"]))
    lines.append("[TEXT_ALLOWLIST] %s [/TEXT_ALLOWLIST]" %
                 ("; ".join(allow) if allow else "(none)"))
    lines.append("[SHOT:%s] %s [/SHOT]" % (shot_id, base.strip()))
    # Part F F12: every compiled clip prompt asks for motion — the failed
    # 2026-10-08 runs produced near-still clips because the prompt never
    # said the subject moves. Exact one-line wording, builder style.
    lines.append("[MOTION] The subject moves naturally through the frame; "
                 "limbs, head and camera stay in gentle continuous motion. "
                 "[/MOTION]")
    prompt = "\n".join(lines)
    if len(prompt) > cap:
        raise CompilerError("OVER_CAP", "%d > %d for %s"
                            % (len(prompt), cap, model))
    enforce_prompt(prompt, model)
    return {"prompt": prompt, "model": model,
            "aspect_ratio": style["aspect_ratio"], "asset_ids": assets,
            "prompt_chars": len(prompt)}


def dumps_record(d):
    return json.dumps({k: d[k] for k in sorted(d)}, sort_keys=True,
                      ensure_ascii=True)
