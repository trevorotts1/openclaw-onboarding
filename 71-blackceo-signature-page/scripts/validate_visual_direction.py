#!/usr/bin/env python3
"""validate_visual_direction.py <run_dir>

Order A2 (BLACKCEO-SKILL-71-ENFORCEMENT-FIX-ORDER.md) enforcement:
- No creative direction at intake means SECRET_SAUCE_ONLY. An agent may
  never self-select an external style ("no direction supplied" never means
  "choice delegated to the agent").
- An external style in the visual bible must be the exact style ID the
  owner named at intake.
- Every page token must sit within the brand file's color_tolerance
  (per RGB channel) of a brand palette color or logo-only color.
- Every font must be one of the brand file's fonts and never a banned font —
  UNLESS the brand file's font_policy says when_brand_fonts_missing =
  "derive-document" and the brand fonts are still MUST_SUPPLY placeholders:
  then fonts go from BLOCKED to DERIVE-AND-DOCUMENT (the bible must carry
  fonts_source "derived", a non-empty font_rationale, and a font_reviewer;
  banned fonts still FAIL).
- The brand file must not still carry TREVOR_MUST_SUPPLY /
  CLIENT_MUST_SUPPLY placeholders — EXCEPT fonts.* when font_policy
  authorizes derive-document (each other missing key still printed).

Reads <run_dir>/intake.json and <run_dir>/visual-mockup/page-visual-bible.json.
The brand file comes from intake.json's brand_file field.

Exit codes: 0 pass, 1 fail (each reason on its own line), 2 unreadable input.
"""
import json
import os
import re
import sys

MUST_SUPPLY = ("TREVOR_MUST_SUPPLY", "CLIENT_MUST_SUPPLY")
SECRET_SAUCE_ONLY = "SECRET_SAUCE_ONLY"
HEX_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def die2(msg):
    print("ERROR: %s" % msg, file=sys.stderr)
    sys.exit(2)


def load_json(path, what):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        die2("%s not found: %s" % (what, path))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        die2("%s unreadable: %s: %s" % (what, path, e))


def expand_hex(hexstr):
    h = hexstr[1:]
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def walk_strings(node, path=""):
    """Yield (json_path, string) for every string value; lists included."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk_strings(v, "%s.%s" % (path, k) if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk_strings(v, "%s[%d]" % (path, i))
    elif isinstance(node, str):
        yield path, node


def resolve_brand_file(intake, run_dir, skill_root):
    raw = intake.get("brand_file")
    if not isinstance(raw, str) or not raw.strip():
        die2("intake.json has no brand_file value; cannot locate the run's brand file")
    candidates = [raw] if os.path.isabs(raw) else [
        os.path.join(run_dir, raw),
        os.path.join(skill_root, raw),
    ]
    for cand in candidates:
        if os.path.isfile(cand):
            return cand
    die2("brand file not found (tried: %s)" % ", ".join(candidates))


def main():
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        sys.exit(0 if len(sys.argv) == 2 else 2)
    run_dir = sys.argv[1]
    if not os.path.isdir(run_dir):
        die2("run_dir is not a directory: %s" % run_dir)
    skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    intake = load_json(os.path.join(run_dir, "intake.json"), "intake.json")
    bible = load_json(
        os.path.join(run_dir, "visual-mockup", "page-visual-bible.json"),
        "visual-mockup/page-visual-bible.json")

    reasons = []

    # Brand file: FAIL if any value is still a MUST_SUPPLY placeholder —
    # EXCEPT fonts, which the brand file's font_policy may authorize as
    # derive-document (agent derives the best display/body/accent for the job,
    # documents the rationale in the bible, reviewer approves; never blocked).
    brand_path = resolve_brand_file(intake, run_dir, skill_root)
    brand = load_json(brand_path, "brand file (%s)" % brand_path)
    policy = brand.get("font_policy") or {}
    fonts_derivable = (
        isinstance(policy, dict)
        and policy.get("when_brand_fonts_missing") == "derive-document"
    )
    for path, value in walk_strings(brand):
        if value in MUST_SUPPLY:
            if fonts_derivable and path.startswith("fonts."):
                continue
            reasons.append(
                "FAIL: brand file %s still has %s = %s — this key is not supplied yet"
                % (brand_path, path, value))

    palette = {}
    for section in ("palette", "logo_only_colors"):
        for name, value in walk_strings(brand.get(section, {})):
            if HEX_RE.match(value):
                palette[name] = expand_hex(value)
    try:
        tolerance = int(brand.get("color_tolerance", 0))
    except (TypeError, ValueError):
        tolerance = 0
    brand_fonts = {v for _, v in walk_strings(brand.get("fonts", {}))}
    banned_fonts = set(brand.get("banned_fonts", []))
    # FAIL: no intake direction => SECRET_SAUCE_ONLY mandatory.
    selection_mode = bible.get("selection_mode")
    creative_direction = intake.get("creative_direction")
    no_direction = creative_direction is None or (
        isinstance(creative_direction, str) and not creative_direction.strip())
    if no_direction and selection_mode != SECRET_SAUCE_ONLY:
        reasons.append(
            "FAIL: intake.creative_direction is not supplied, so selection_mode must be "
            "%s, but the bible says %r — no direction supplied never means the agent "
            "may choose a style" % (SECRET_SAUCE_ONLY, selection_mode))

    # FAIL: external style must be the exact style ID the owner named.
    if selection_mode not in (None, SECRET_SAUCE_ONLY):
        style_id = str(bible.get("style_id") or selection_mode).strip()
        named = (creative_direction or "").strip().casefold()
        style_fold = style_id.casefold()
        if not named or (style_fold not in named and named not in style_fold):
            reasons.append(
                "FAIL: bible selection_mode is an external style (%r, style_id %r) but "
                "intake.creative_direction (%r) does not name that exact style ID"
                % (selection_mode, style_id, creative_direction))

    # FAIL: page tokens must be within color_tolerance of a brand color.
    for path, value in walk_strings(bible.get("page_tokens", {})):
        if not HEX_RE.match(value):
            continue
        rgb = expand_hex(value)
        best_name = None
        best_diff = None
        for name, prgb in palette.items():
            diff = max(abs(a - b) for a, b in zip(rgb, prgb))
            if best_diff is None or diff < best_diff:
                best_name, best_diff = name, diff
        if best_diff is None or best_diff > tolerance:
            nearest = ("nearest brand color %s (diff %d)" % (best_name, best_diff)
                       if best_name else "no palette colors found in brand file")
            reasons.append(
                "FAIL: page token %s at bible.page_tokens.%s is off-palette (%s; "
                "tolerance %d per channel)" % (value, path, nearest, tolerance))

    # Fonts: when the brand file's fonts are MUST_SUPPLY placeholders under a
    # derive-document font_policy, the bible must be DERIVED AND DOCUMENTED:
    # fonts_source == "derived", a non-empty font_rationale, and every bible
    # font must name a real family (never a MUST_SUPPLY placeholder). A banned
    # font always FAILS, derived or not.
    fonts_missing = bool(fonts_derivable) and any(
        value in MUST_SUPPLY for _, value in walk_strings(brand.get("fonts", {})))
    if fonts_missing:
        font_source = str(bible.get("fonts_source") or "").strip()
        if font_source != "derived":
            reasons.append(
                "FAIL: brand file fonts are TREVOR_MUST_SUPPLY/CLIENT_MUST_SUPPLY and "
                "font_policy authorizes derive-document, so the bible must set "
                "fonts_source = \"derived\" (got %r) — derive the best fonts for the job "
                "and document them" % (font_source or None))
        rationale = str(bible.get("font_rationale") or "").strip()
        if not rationale:
            reasons.append(
                "FAIL: bible font_rationale is empty — the derived font choice must "
                "carry a written rationale (why each display/body/accent face fits "
                "this page's copy and audience)")
        if str(policy.get("requires_reviewer", True)).lower() in ("true", "1", "yes"):
            reviewer = str(bible.get("font_reviewer") or "").strip()
            if not reviewer:
                reasons.append(
                    "FAIL: font_policy.requires_reviewer is true but the bible has no "
                    "font_reviewer — the independent reviewer who approved the derived "
                    "fonts must be named in the bible")
    for path, value in walk_strings(bible.get("fonts", {})):
        problems = []
        if value in MUST_SUPPLY:
            problems.append("is still a %s placeholder" % value)
        else:
            if not fonts_missing and value not in brand_fonts:
                # With derived fonts the brand list holds no real names, so the
                # membership check does not apply; only banned-font law does.
                problems.append("not one of the brand file's fonts")
            if value in banned_fonts:
                problems.append("in banned_fonts")
        if problems:
            reasons.append("FAIL: font %r at bible.fonts.%s: %s"
                           % (value, path, "; ".join(problems)))

    if reasons:
        print("\n".join(reasons))
        sys.exit(1)
    print("PASS: visual direction checks passed (selection_mode %r)"
          % (selection_mode or SECRET_SAUCE_ONLY))
    sys.exit(0)


if __name__ == "__main__":
    main()
