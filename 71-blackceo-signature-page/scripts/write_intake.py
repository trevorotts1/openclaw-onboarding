#!/usr/bin/env python3
"""Write <run_dir>/intake.json, the intake stage artifact stage_gate.py reads.

image_engine is "kie" (default) or "agnes". stage_gate.py accepts the Agnes route on
image-generation-qc only when intake.json says "agnes" (references/kie-generation-route.md).
copy_version ("standard", "long-form", "product-selection", "upsell", or a page type's own form such as "thank-you") is a required intake decision (fix plan
Amendment 6, Items 18/19): it selects the ONE copy guide, copy spec, and
emotional-quality extract the copy stage reads (see the copy stage's
copy_selection block in references/stage-contract.json and the selection
record in references/artifact-contracts.md). The flag stays optional at
this writer so older invocations keep working; a run whose intake.json has
no copy_version cannot pass the copy stage's structure validation.
Layout waivers (Item 13/14, S3 Request 3): --brand-fonts-waived and
--layout-references-waived, each with its own reason argument, are recorded
in intake.json as layout_waivers entries the gate's layout gate consumes;
an unrecorded absence is never a waiver.
Page kind (SPF030): --page-kind sales|opt_in records which landing-role page this
run is, the signature sales page (Standard 12 sections by default, Long-Form
allowed; buttons go to checkout) or the signature landing (opt-in) page (Long-Form
15 sections; buttons open the form). The kind decides the canonical section
sequence, the wireframe closing band and the Design Board label
(references/page-kinds.json, scripts/page_kinds.py). A production run cannot close
intake without it (gate:intake_page_kind); test runs are exempt.
Answers file (lane intake): --answers-file FILE reads the one client intake answers file
(shared-utils/client_intake, schema client-intake-answers/v1) so the same questions asked in
claude-nine, Claude Code or OpenClaw feed this writer. It fills --brand-owner (business_name),
--image-cap, --page-version AND --copy-version (one copy_profile, both selectors), --page-kind
(a page_kind answer, read before the length it constrains), --design-style and --image-engine
whenever the flag is not given, writes the run's client brand file (colors as roles, fonts, logo,
photos; see scripts/brand_colors.py record-answers) and records answers_file, answers_file_sha256
and the to_confirm list in intake.json so the delivery report can name every default. A flag on the
command line always wins over the answers file. Without --answers-file nothing changes.
Exit 0 written, 2 invalid input.

Delivery fields (Item 31, Amendment 4): the intake also records the publish
target, the automation scope, and the PRESENCE of the three delivery
credentials (booleans and variable names only; values are never read into
the record and never printed). Refusals are written, at intake:

- automation_scope "workflows" with a non-GHL publish target is refused:
  workflows live where the forms live;
- a GHL publish target without the Private Integration Token or the
  location ID present is refused, naming what to supply in this install's
  own secrets.env;
- automation scope without the Firebase refresh token requires a recorded
  choice (--firebase-choice): supply the token, record that the automation
  falls back to the browser sign-in, or drop the automation scope. The page
  job may proceed; the workflows may not pretend to exist.

The credential, page-kind and page-length refusals print two registers: a
plain summary line (REFUSED:) that an operator may relay to a client
unchanged, and a NEXT line naming the exact recovery action and the role
responsible for it. Registry names, provisioning topology and tier backstops
appear in neither.

Credential presence defaults to the process environment; the --*-present /
--*-absent flags override it (for provisioning records written before the
secrets.env exists).

Launch-context import (S71-02, profile signature_launch_landing):
--launch-context <page-request.json> imports the approved Signature
Launch context for the run. The page-request (and, when supplied, the
launch record, the route graph, and the popup consent statements) are
validated against the frozen 1.0 schemas vendored in references/ by
scripts/launch_context.py; on any violation the import is refused with
the violation named and nothing is written. On success the context's
fields are mapped into intake.json (launch_profile plus the launch
block), the validated documents are placed in the run where the S71-05
handoff reads them, and the interest popup config is emitted at
launch/popup-config.json. Without --launch-context this writer's
behavior is unchanged.

Founder photo entry forms (update plan Item 10): when the brand file the
intake records can be resolved, every founder_photos entry in it is checked
at intake against the forms scripts/validate_page.py's
founder_allowed_hashes accepts, classified by that module's own
founder_photo_entry_form so the two cannot drift. An entry in none of the
accepted forms (the run-recorded failure mode: a prose string of path plus
description plus hash) refuses intake, naming the entry and the accepted
forms, instead of surfacing at the first page validation. Entries still
carrying an unsupplied marker are not form errors; the must-supply gate
owns that state.

Supplied-asset size check (Update Plan Item 19): --supplied-assets names a
JSON file declaring the run's supplied assets (the same supplied entries
Item 3's record defines: an id, a source beginning with "supplied", and the
asset file), each with its slot: either an explicit slot_px {width, height}
(the rendered size), or a slot_ratio ("47:50") with a
slot_layout_width_px (the slot's layout width; the rendered size is the
layout size scaled by DISPLAY_DENSITY_FACTOR). --section-plan may name a
section plan JSON whose slot_aspect_ratios / slot_layout_widths fill any
ratio or width a declaration omits. Every declared asset's true pixel
dimensions are measured from the file bytes (never from prose), compared
against its slot's rendered size, and recorded in intake.json under
supplied_asset_size_checks as asset_px / slot_px / verdict (OK or
UNDERSIZED, with the shortfall). An UNDERSIZED verdict prints as a named
line here, in REPORT.md, and in the evidence of every stage that places
the asset (scripts/stage_gate.py). The check never blocks a run by itself
and never substitutes, upscales, or regenerates the asset; an asset file
that cannot be read or measured, or a declaration with no determinable
slot, is invalid input (exit 2), like any other malformed intake input.

Funnel handoff (update plan Item 32): the intake also records the signature
page's own handoff contract: the Convert and Flow form's identity (its name
AND its object id, --handoff-form-name / --handoff-form-id), the pop
behavior, and the step order (signature page, then product selection page,
then order form page). A run with no form identity records the handoff as
an explicit missing input (--handoff-missing-reason) instead: a placeholder
destination is never written as if it were a handoff. The record is what
scripts/validate_handoff.py checks the built page against and what the
funnel-completion receipt proves live at install."""
import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import copy_forms
import design_style
import launch_context
import page_role
import page_kinds

SKILL_ROOT = Path(__file__).resolve().parents[1]

ENGINES = ("kie", "agnes")
DESIGN_STYLE_SOURCES = ("client_choice", "recommended_accepted")

# Item 19: supplied assets are measured against the slot's RENDERED size:
# the layout size scaled by this display-density factor (a 2x retina
# rendering of the slot is the smallest honest target for a placed photo).
DISPLAY_DENSITY_FACTOR = 2

HANDOFF_BEHAVIOR = "form_pop"
HANDOFF_STEP_ORDER = ("signature_page", "product_selection_page", "order_form_page")

CREDENTIALS = (
    ("pit", "ghl_pit", "GHL_PRIVATE_INTEGRATION_TOKEN"),
    ("location_id", "ghl_location", "GHL_LOCATION_ID"),
    ("firebase_refresh_token", "ghl_firebase", "GHL_FIREBASE_REFRESH_TOKEN"),
)


def refuse(summary, recovery, role):
    """A refusal in two registers (finding 24): `summary` is the plain
    blocker an operator may relay to a client unchanged; the NEXT line is
    the exact recovery action and the role responsible for it, for the
    operator. Registry names, provisioning topology and tier backstops
    belong in neither line."""
    print(f"REFUSED: {summary}")
    print(f"NEXT (operator, role: {role}): {recovery}")
    return 2


def image_pixel_dimensions(path):
    """An image file's true pixel dimensions, read from its bytes (PNG,
    JPEG, GIF, or WebP headers; standard library only), or None when the
    bytes carry no readable header. Never trusts a recorded dimension."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
        width, height = struct.unpack(">II", data[16:24])
        return (width, height)
    if len(data) >= 10 and data[:6] in (b"GIF87a", b"GIF89a"):
        width, height = struct.unpack("<HH", data[6:10])
        return (width, height)
    if len(data) >= 30 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        kind = data[12:16]
        if kind == b"VP8X" and len(data) >= 30:
            width = int.from_bytes(data[24:27], "little") + 1
            height = int.from_bytes(data[27:30], "little") + 1
            return (width, height)
        if kind == b"VP8L" and len(data) >= 25:
            bits = int.from_bytes(data[21:25], "little")
            return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        if kind == b"VP8 " and len(data) >= 30:
            width = struct.unpack("<H", data[26:28])[0] & 0x3FFF
            height = struct.unpack("<H", data[28:30])[0] & 0x3FFF
            return (width, height)
        return None
    if len(data) >= 4 and data[:2] == b"\xff\xd8":
        # JPEG: walk segments to a start-of-frame marker.
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            length = struct.unpack(">H", data[i + 2:i + 4])[0]
            if length < 2:
                return None
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                          0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                height, width = struct.unpack(">HH", data[i + 5:i + 9])
                return (width, height)
            i += 2 + length
        return None
    return None


def parse_aspect_ratio(text):
    """Parse a slot aspect ratio ("47:50" or "47x50") to (w, h), or None."""
    if not isinstance(text, str):
        return None
    parts = text.strip().lower().replace("x", ":").split(":")
    if len(parts) != 2:
        return None
    try:
        width, height = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None
    return (width, height)


def slot_rendered_px(decl, plan_entry):
    """The slot's rendered pixel size {width, height} for one supplied
    asset declaration, or None when no slot can be determined. An explicit
    slot_px is already the rendered size; otherwise the size is the layout
    width (the declaration's, else the section plan's) at the slot ratio,
    scaled by DISPLAY_DENSITY_FACTOR."""
    slot_px = decl.get("slot_px")
    if isinstance(slot_px, dict):
        try:
            width, height = int(slot_px["width"]), int(slot_px["height"])
        except (KeyError, TypeError, ValueError):
            return None
        if width > 0 and height > 0:
            return {"width": width, "height": height}
        return None
    ratio = parse_aspect_ratio(decl.get("slot_ratio") or decl.get("aspect_ratio")
                               or decl.get("ratio"))
    if ratio is None and plan_entry is not None:
        ratio = parse_aspect_ratio((plan_entry.get("slot_aspect_ratios") or {}).get(
            decl.get("id") or decl.get("image_id")))
    layout_width = decl.get("slot_layout_width_px") or decl.get("layout_width_px")
    if layout_width is None and plan_entry is not None:
        widths = plan_entry.get("slot_layout_widths") or {}
        layout_width = widths.get(decl.get("id") or decl.get("image_id"))
        if layout_width is None:
            layout_width = plan_entry.get("layout_width_px") or plan_entry.get("content_width_px")
    if ratio is None or layout_width is None:
        return None
    try:
        layout_width = int(layout_width)
    except (TypeError, ValueError):
        return None
    if layout_width <= 0:
        return None
    width = layout_width * DISPLAY_DENSITY_FACTOR
    height = round(width * ratio[1] / ratio[0])
    return {"width": width, "height": height}


def section_plan_index(plan_path):
    """Index a section plan JSON by image id: {id: section entry}. The
    plan is a list of section objects carrying image_slot_ids and
    slot_aspect_ratios (and, where recorded, slot_layout_widths)."""
    if plan_path is None:
        return {}
    try:
        plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if isinstance(plan, dict):
        plan = plan.get("sections") or []
    index = {}
    if isinstance(plan, list):
        for section in plan:
            if not isinstance(section, dict):
                continue
            for image_id in section.get("image_slot_ids") or []:
                index[str(image_id)] = section
            for image_id in (section.get("slot_aspect_ratios") or {}):
                index.setdefault(str(image_id), section)
    return index


def supplied_size_check_records(declarations, base_dir, plan_index=None):
    """Item 19: measure every declared supplied asset against its slot.

    declarations: list of dicts naming id, source (must begin with
    "supplied", the Item 3 supplied-entry rule), file, and the slot (see
    slot_rendered_px). Returns (records, problems): one record per asset
    with asset_px / slot_px / verdict (and shortfall_px when UNDERSIZED);
    problems names any declaration that cannot be honestly measured."""
    records, problems = [], []
    plan_index = plan_index or {}
    for decl in declarations:
        if not isinstance(decl, dict):
            problems.append(f"supplied-asset declaration {decl!r} is not an object")
            continue
        image_id = decl.get("id") or decl.get("image_id")
        source = decl.get("source")
        rel = decl.get("file") or decl.get("path")
        who = image_id or rel or "unnamed asset"
        if not image_id:
            problems.append(f"supplied-asset declaration for {who} names no image id")
            continue
        if not (isinstance(source, str) and source.strip().lower().startswith("supplied")):
            problems.append(f"supplied-asset declaration for {image_id} carries source "
                            f"{source!r}; the size check runs over supplied entries "
                            "(a source beginning with \"supplied\", Item 3)")
            continue
        if not rel:
            problems.append(f"supplied-asset declaration for {image_id} names no asset file")
            continue
        asset_path = Path(rel)
        if not asset_path.is_absolute():
            asset_path = Path(base_dir) / asset_path
        dims = image_pixel_dimensions(asset_path)
        if dims is None:
            problems.append(f"supplied asset {image_id}: cannot measure the true pixel "
                            f"dimensions of {rel} from its bytes (missing, unreadable, "
                            "or an unrecognized image format); the size check records "
                            "measured bytes only, never intake prose")
            continue
        slot_px = slot_rendered_px(decl, plan_index.get(str(image_id)))
        if slot_px is None:
            problems.append(f"supplied asset {image_id}: no slot size can be determined "
                            "(declare slot_px, or slot_ratio with slot_layout_width_px, "
                            "or name a section plan carrying the slot's ratio and width)")
            continue
        asset_px = {"width": dims[0], "height": dims[1]}
        record = {"id": str(image_id), "source": source, "file": str(rel),
                  "asset_px": asset_px, "slot_px": slot_px,
                  "display_density_factor": DISPLAY_DENSITY_FACTOR}
        if dims[0] >= slot_px["width"] and dims[1] >= slot_px["height"]:
            record["verdict"] = "OK"
        else:
            record["verdict"] = "UNDERSIZED"
            record["shortfall_px"] = {
                "width": max(0, slot_px["width"] - dims[0]),
                "height": max(0, slot_px["height"] - dims[1])}
        records.append(record)
    return records, problems


def supplied_size_line(record):
    """The named one-line flag for one size-check record (printed at
    intake, in REPORT.md, and in placing stages' evidence)."""
    asset, slot = record["asset_px"], record["slot_px"]
    line = (f"SUPPLIED ASSET SIZE {record['id']} ({record.get('source')}): "
            f"asset {asset['width']}x{asset['height']} px, "
            f"slot {slot['width']}x{slot['height']} px: {record['verdict']}")
    if record["verdict"] == "UNDERSIZED":
        short = record["shortfall_px"]
        line += (f" (shortfall {short['width']}x{short['height']} px; "
                 "flagged, never substituted, upscaled, or regenerated)")
    return line


def credential_presence(a):
    out = {}
    for key, dest, default_var in CREDENTIALS:
        var = getattr(a, f"{dest}_var") or default_var
        override = getattr(a, f"{dest}_present")
        present = (var in os.environ and bool(os.environ[var])) if override is None else override
        out[key] = {"variable": var, "present": bool(present)}
    return out


SKILL_ROOT = Path(__file__).resolve().parent.parent


def resolve_brand_file(brand_file, run_dir):
    """Resolve the brand file the intake records: run-dir relative first
    (the resolution stage_gate.brand_path_for applies when it reads the
    intake back), then as given, then skill-root relative. Returns None when
    no candidate exists (nothing to check yet; invocations naming a
    not-yet-authored brand file keep working exactly as before)."""
    named = Path(brand_file)
    candidates = [named] if named.is_absolute() else [
        run_dir / named, named, SKILL_ROOT / named]
    for cand in candidates:
        if cand.is_file():
            return cand
    return None


def founder_photo_form_problems(brand_path, run_dir):
    """Update plan Item 10: the founder_photos form check described in the
    module docstring. Returns refusal lines (empty when every entry is in an
    accepted form, carries an unsupplied marker, or the brand file cannot be
    read; an unreadable brand file is the must-supply gate's report, not
    this check's)."""
    try:
        data = json.loads(brand_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    photos = data.get("founder_photos")
    if photos is None:
        return []
    if isinstance(photos, str):
        photos = [photos]
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import validate_page
    except Exception as exc:  # the classifier must come from the validator itself
        return [f"could not import validate_page to check founder_photos forms: {exc}"]
    bases = (brand_path.parent, run_dir, SKILL_ROOT, Path.cwd())

    def path_exists(text):
        p = Path(text)
        if p.is_absolute():
            return p.exists()
        return any((base / p).exists() for base in bases)

    forms = ", ".join(validate_page.FOUNDER_PHOTO_FORMS)
    problems = []
    for entry in photos:
        if validate_page.founder_photo_entry_form(entry, path_exists=path_exists) is None:
            problems.append(
                f"brand founder_photos entry {str(entry).strip()!r} is not in a "
                f"form the page validator accepts; each entry must be one of: "
                f"{forms}. A prose entry (path plus description plus hash) "
                f"fails every page validation; record the bare hash, a "
                f"'sha256:' value, or the photo's file path instead.")
    return problems


def read_answers(path):
    """The answers file as (doc, defaults for this writer's flags). Refuses a file of another schema.

    Page kind is read before length (finding 17): the kind decides which
    lengths are allowed, so a client's recorded kind is imported and the
    length is checked against it instead of colliding at the copy stage.
    copy_profile fills BOTH copy selectors - page_version and copy_version -
    because the copy stage reads copy_version, and a run that records only
    page_version cannot close copy."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"--answers-file {path} is not readable JSON ({exc})")
    if not isinstance(doc, dict) or doc.get("schema") != "client-intake-answers/v1":
        raise ValueError(f"--answers-file {path} is not a client-intake-answers/v1 file")

    def entry(key):
        e = (doc.get("answers") or {}).get(key)
        return e if isinstance(e, dict) else {}

    def value(key):
        e = entry(key)
        return e.get("value") if e.get("status") != "unknown" else None

    defaults = {}
    if value("business_name"):
        defaults["brand_owner"] = value("business_name")
    if isinstance(value("image_cap"), int):
        defaults["image_cap"] = value("image_cap")
    kind = value("page_kind")
    if kind is not None:
        normalized = page_kinds.normalize(kind)
        if normalized not in page_kinds.kind_ids():
            raise ValueError(
                f"--answers-file {path} records page_kind {kind!r}, which is not "
                f"one of {', '.join(page_kinds.kind_ids())}; record the client's "
                "answer as sales or opt_in and rerun")
        defaults["page_kind"] = normalized
    profile = value("copy_profile")
    if profile in ("standard", "long_form"):
        form = "standard" if profile == "standard" else "long-form"
        defaults["page_version"] = form
        defaults["copy_version"] = form
    if value("design_style") in design_style.STYLE_IDS:
        defaults["design_style"] = value("design_style")
    provider = value("image_provider")
    if provider in ENGINES:
        defaults["image_engine"] = provider
    return doc, defaults


def main(argv=None):
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--answers-file", type=Path, default=None)
    pre_args, _ = pre.parse_known_args(argv)
    answers_doc, from_answers = None, {}
    if pre_args.answers_file is not None:
        try:
            answers_doc, from_answers = read_answers(pre_args.answers_file)
        except ValueError as exc:
            print(f"REFUSED: {exc}")
            return 2
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("run_dir", type=Path)
    p.add_argument("--answers-file", type=Path, default=None,
                   help="the client intake answers file (client-intake-answers/v1); fills the flags it can")
    p.add_argument("--page-version", choices=list(copy_forms.FORMS), default=from_answers.get("page_version"),
                   help="standard or long-form for a landing page; a page type's own form "
                        "(thank-you) for that page, which also records its page_role")
    p.add_argument("--brand-owner", required="brand_owner" not in from_answers, default=from_answers.get("brand_owner"))
    p.add_argument("--brand-file", default="brand/client-brand.json" if answers_doc is not None else "assets/brand/blackceo-brand.json")
    p.add_argument("--creative-direction", default=None)
    p.add_argument("--image-cap", type=int, required="image_cap" not in from_answers, default=from_answers.get("image_cap"))
    p.add_argument("--image-engine", choices=ENGINES, default=from_answers.get("image_engine", "kie"))
    p.add_argument("--design-style", choices=design_style.STYLE_IDS, default=from_answers.get("design_style"),
                   help="the client's page design style: A Block, B Circle or C Hybrid "
                        "(references/design-styles.md); ask with `design_style.py question`")
    p.add_argument("--design-style-source", choices=DESIGN_STYLE_SOURCES, default=None,
                   help="how the style was chosen (default client_choice when --design-style is given)")
    p.add_argument("--copy-version", choices=list(copy_forms.FORMS), default=from_answers.get("copy_version"),
                   help="the run's copy selection (required intake decision, "
                        "Amendment 6 Items 18/19); selects the copy guide, spec, "
                        "and emotional-quality extract for the copy stage")
    p.add_argument("--page-kind", choices=page_kinds.kind_ids(), default=from_answers.get("page_kind"),
                   help="the landing-role page this run builds: sales (signature sales "
                        "page) or opt_in (signature landing opt-in page); decides the "
                        "canonical section sequence, wireframe closing band and Design "
                        "Board label (references/page-kinds.json)")
    p.add_argument("--test-run", action="store_true")
    p.add_argument("--supplied-assets", type=Path, default=None,
                   help="Item 19: JSON file declaring the run's supplied assets "
                        "(a list, or an object with an \"assets\" list); each entry "
                        "names id, source (beginning with \"supplied\"), file, and "
                        "its slot (slot_px, or slot_ratio + slot_layout_width_px). "
                        "Every asset is measured from its bytes and the verdict "
                        "recorded in intake.json; UNDERSIZED never blocks intake")
    p.add_argument("--section-plan", type=Path, default=None,
                   help="Item 19: section plan JSON whose slot_aspect_ratios / "
                        "slot_layout_widths fill slot data a supplied-asset "
                        "declaration omits")
    p.add_argument("--brand-fonts-waived", action="store_true",
                   help="record a waiver for the layout gate's brand-fonts check "
                        "(requires --brand-fonts-waiver-reason)")
    p.add_argument("--brand-fonts-waiver-reason", default=None)
    p.add_argument("--layout-references-waived", action="store_true",
                   help="record a waiver for the layout gate's reference-existence "
                        "check (requires --layout-references-waiver-reason)")
    p.add_argument("--layout-references-waiver-reason", default=None)
    # Launch-context import (S71-02).
    p.add_argument("--launch-context", type=Path, default=None,
                   help="Signature Launch page-request 1.0 document; validates "
                        "it against the frozen schemas in references/ and "
                        "imports the approved launch context, activating the "
                        "signature_launch_landing profile")
    p.add_argument("--launch-record", type=Path, default=None,
                   help="the launch record (launch.json 1.0) the request "
                        "belongs to; requires --launch-context")
    p.add_argument("--route-graph", type=Path, default=None,
                   help="the approved route graph (route-graph 1.0); its "
                        "SHA-256 must equal the request's route_graph_hash; "
                        "requires --launch-context")
    p.add_argument("--consent-statements", type=Path, default=None,
                   help="the approved popup consent statements as a JSON "
                        "list of {id, text, required} objects (the interest "
                        "popup component's config shape), carried verbatim "
                        "into launch/popup-config.json; requires "
                        "--launch-context")
    # Update plan Item 32: the funnel handoff record.
    p.add_argument("--handoff-form-name", default=None,
                   help="the Convert and Flow form the primary CTA pops: its "
                        "name (recorded with --handoff-form-id as the form's "
                        "identity in intake.json's funnel_handoff)")
    p.add_argument("--handoff-form-id", default=None,
                   help="the named form's object id (its identity is a name "
                        "AND an object id; one without the other is refused)")
    p.add_argument("--handoff-missing-reason", default=None,
                   help="record the handoff form identity as an explicit "
                        "missing input with this reason, instead of a form "
                        "identity; never combined with the form flags")
    # Item 31 delivery fields (Amendment 4).
    p.add_argument("--publish-target", choices=["ghl", "vercel-embed", "vercel"])
    p.add_argument("--automation-scope", choices=["none", "workflows"], default="none")
    p.add_argument("--firebase-choice", choices=["supply", "backstop", "drop"])
    for _key, dest, _var in CREDENTIALS:
        flag = dest.replace("_", "-")
        p.add_argument(f"--{flag}-var")
        g = p.add_mutually_exclusive_group()
        g.add_argument(f"--{flag}-present", dest=f"{dest}_present",
                       action="store_const", const=True, default=None)
        g.add_argument(f"--{flag}-absent", dest=f"{dest}_present",
                       action="store_const", const=False, default=None)
    a = p.parse_args(argv)
    if a.image_cap < 0 or not a.run_dir.is_dir():
        print("FAIL: run_dir must exist and image_cap must be >= 0")
        return 2
    # One copy selection, two selectors (finding 17): whichever selector is
    # given fills the other, so no run records a page_version with a null
    # copy_version for the copy stage to trip on.
    if a.page_version is None and a.copy_version is not None:
        a.page_version = a.copy_version
    if a.copy_version is None and a.page_version is not None:
        a.copy_version = a.page_version
    if a.page_version is None:
        return refuse(
            "the page length for this run was not recorded.",
            "rerun with --page-version standard|long-form (or --copy-version), "
            "or supply an answers file whose copy_profile answer records the "
            "client's choice.",
            "intake")
    forms = page_role.role_specs()
    if (forms.get(a.page_version) or forms.get(a.copy_version)) and a.copy_version not in (None, a.page_version):
        print(f"REFUSED: --page-version \"{a.page_version}\" and --copy-version \"{a.copy_version}\" "
              "disagree; a page type's own form is both its page_version and its copy_version, and a "
              "page type is never forced into another page type's canonical sections.")
        return 2

    # Launch-context import (S71-02): validate everything in memory before
    # anything is written; a refusal here leaves the run untouched.
    launch_prepared = None
    if a.launch_context is None:
        for flag, value in (("--launch-record", a.launch_record),
                            ("--route-graph", a.route_graph),
                            ("--consent-statements", a.consent_statements)):
            if value is not None:
                print(f"REFUSED: {flag} is a launch-context import input and "
                      f"requires --launch-context (the page-request it "
                      f"belongs to).")
                return 2
    else:
        try:
            launch_prepared = launch_context.prepare_import(
                SKILL_ROOT, a.run_dir, a.launch_context,
                launch_path=a.launch_record, graph_path=a.route_graph,
                consent_path=a.consent_statements, brand_file=a.brand_file)
        except launch_context.LaunchContextError as exc:
            print(f"REFUSED: launch context import: {exc}")
            return 2
        mapped_copy = launch_prepared[0].get("copy_version")
        if (a.copy_version is not None and mapped_copy is not None
                and a.copy_version != mapped_copy):
            print(f"REFUSED: --copy-version \"{a.copy_version}\" conflicts "
                  f"with the launch context's approved copy_profile "
                  f"\"{mapped_copy}\"; the approved launch context governs, "
                  f"so drop the conflicting flag.")
            return 2

    if a.page_kind:
        effective_copy = a.copy_version or (
            launch_prepared[0].get("copy_version") if launch_prepared else None) or a.page_version
        try:
            page_kinds.check(a.page_kind, effective_copy)
        except page_kinds.KindError as exc:
            return refuse(
                "the page length recorded for this run does not fit the kind of "
                "page being built, so intake stopped before writing anything.",
                f"{exc}. Rerun with --copy-version long-form for an opt-in page "
                "(standard or long-form for a sales page), or correct --page-kind "
                "to the page the client chose.",
                "intake")

    brand_path = resolve_brand_file(a.brand_file, a.run_dir)
    if brand_path is not None:
        problems = founder_photo_form_problems(brand_path, a.run_dir)
        if problems:
            for line in problems:
                print(f"REFUSED: {line}")
            return 2

    intake = {"page_version": a.page_version, "brand_owner": a.brand_owner, "brand_file": a.brand_file,
              "creative_direction": a.creative_direction, "image_cap": a.image_cap,
              "image_engine": a.image_engine, "test_run": a.test_run,
              "copy_version": a.copy_version}
    # a page type's own form records its role, so every stage (section count, wireframe prompt,
    # design board, gate) reads one declaration instead of guessing a landing page
    own_form = page_role.role_specs().get(a.copy_version or a.page_version)
    if own_form:
        intake["page_role"] = own_form["page_role"]
        intake["copy_version"] = own_form["copy_version"]  # a page type's page_version is its copy_version
    page_type = (own_form or {}).get("page_role") or (
        (launch_prepared[0].get("launch") or {}).get("page_role") if launch_prepared else None)
    if page_type and page_type != page_role.LANDING_ROLE:
        pass  # SPF030: only a landing-role page is a sales or an opt-in page; every other page type has no kind
    elif a.page_kind:
        intake["page_kind"] = a.page_kind
    else:
        print("NOTE page_kind: none recorded. Rerun with --page-kind sales|opt_in; a "
              "production run cannot close intake without it (test runs are exempt).")
        print("NEXT (operator, role: intake): ask the client which page this is (the "
              "signature sales page or the signature landing opt-in page) and rerun "
              "with --page-kind sales|opt_in, or record it as a page_kind answer in "
              "the answers file.")
    if a.design_style:
        intake["design_style"] = a.design_style
        intake["design_style_source"] = a.design_style_source or "client_choice"
    elif a.design_style_source:
        print("REFUSED: --design-style-source needs --design-style.")
        return 2
    else:
        print("NOTE design_style: none recorded. Ask the client with "
              "`python3 scripts/design_style.py question` and rerun with --design-style A|B|C; "
              "a production run cannot close intake without it (test runs are exempt).")

    waivers = []
    for flag, reason, gate_name in (
            (a.brand_fonts_waived, a.brand_fonts_waiver_reason, "brand-fonts"),
            (a.layout_references_waived, a.layout_references_waiver_reason, "layout-references")):
        if flag and not (reason and reason.strip()):
            print(f"REFUSED: the {gate_name} waiver requires its recorded reason "
                  f"argument; a waiver without a reason is not a waiver.")
            return 2
        if flag:
            waivers.append({"gate": gate_name, "reason": reason.strip()})
    if waivers:
        intake["layout_waivers"] = waivers

    if a.publish_target is not None:
        credentials = credential_presence(a)
        if a.automation_scope == "workflows" and a.publish_target != "ghl":
            print(f"REFUSED: automation_scope \"workflows\" requires publish_target "
                  f"\"ghl\" (workflows live where the forms live); got publish_target "
                  f"\"{a.publish_target}\". Drop the automation scope or target GHL.")
            return 2
        if a.publish_target == "ghl":
            missing = [credentials[k]["variable"] for k in ("pit", "location_id")
                       if not credentials[k]["present"]]
            if missing:
                return refuse(
                    "this page cannot be published to Convert and Flow yet: the "
                    "account access it needs is not set up for this install.",
                    "add the missing values to this install's own secrets.env and "
                    f"rerun intake: {', '.join(missing)}",
                    "account access")
        automation_scope = a.automation_scope
        extra = {}
        if automation_scope == "workflows" and not credentials["firebase_refresh_token"]["present"]:
            var = credentials["firebase_refresh_token"]["variable"]
            if a.firebase_choice is None:
                return refuse(
                    "the automation part of this job cannot be prepared yet: the "
                    "workflow sign-in it needs is not set up for this install. The "
                    "page itself can still be built.",
                    "rerun with one recorded choice: --firebase-choice supply (set "
                    "up the workflow sign-in, then rerun), --firebase-choice "
                    "backstop (record that the automation falls back to the "
                    "browser sign-in), or --firebase-choice drop (build the page "
                    "with no automation). The page job may proceed; the workflows "
                    "may not pretend to exist.",
                    "account access")
            if a.firebase_choice == "supply":
                return refuse(
                    "the automation part of this job still cannot be prepared: the "
                    "workflow sign-in is not present for this install.",
                    f"add {var} to this install's own secrets.env and rerun intake.",
                    "account access")
            if a.firebase_choice == "backstop":
                extra["firebase_backstop_declared"] = True
            elif a.firebase_choice == "drop":
                automation_scope = "none"
                extra["automation_scope_dropped"] = "workflows (Firebase token not supplied)"
        intake["publish_target"] = a.publish_target
        intake["automation_scope"] = automation_scope
        intake["credentials"] = credentials
        intake.update(extra)

    size_lines = []
    if a.supplied_assets is not None:
        try:
            declared = json.loads(a.supplied_assets.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"REFUSED: --supplied-assets {a.supplied_assets} is not readable "
                  f"JSON ({exc}); the Item 19 size check needs the declarations file.")
            return 2
        if isinstance(declared, dict):
            declared = declared.get("assets") or declared.get("supplied_assets") or []
        if not isinstance(declared, list):
            print("REFUSED: --supplied-assets must carry a list of supplied-asset "
                  "declarations (or an object with an \"assets\" list).")
            return 2
        records, problems = supplied_size_check_records(
            declared, a.run_dir, section_plan_index(a.section_plan))
        if problems:
            for problem in problems:
                print(f"REFUSED: {problem}")
            return 2
        intake["supplied_asset_size_checks"] = records
        size_lines = [supplied_size_line(r) for r in records]

    name_given = a.handoff_form_name is not None
    id_given = a.handoff_form_id is not None
    missing_given = a.handoff_missing_reason is not None
    if missing_given and (name_given or id_given):
        print("REFUSED: the funnel handoff takes either the form identity "
              "(--handoff-form-name and --handoff-form-id) or the explicit "
              "missing input (--handoff-missing-reason), never both.")
        return 2
    if name_given != id_given:
        got = "name" if name_given else "object id"
        print(f"REFUSED: the funnel handoff form identity is a name AND an "
              f"object id; only the {got} was given. Supply both, or record "
              f"the explicit missing input with --handoff-missing-reason.")
        return 2
    if name_given:
        if not a.handoff_form_name.strip() or not a.handoff_form_id.strip():
            print("REFUSED: the funnel handoff form name and object id must "
                  "both be non-empty; a blank identity is a placeholder, "
                  "not a handoff.")
            return 2
        intake["funnel_handoff"] = {
            "form": {"name": a.handoff_form_name.strip(),
                     "form_id": a.handoff_form_id.strip()},
            "behavior": HANDOFF_BEHAVIOR,
            "step_order": list(HANDOFF_STEP_ORDER)}
    elif missing_given:
        if not a.handoff_missing_reason.strip():
            print("REFUSED: --handoff-missing-reason requires the reason "
                  "text; a missing input without its reason is not recorded.")
            return 2
        intake["funnel_handoff"] = {
            "status": "missing_input",
            "missing": "form_identity",
            "reason": a.handoff_missing_reason.strip(),
            "behavior": HANDOFF_BEHAVIOR,
            "step_order": list(HANDOFF_STEP_ORDER)}

    if launch_prepared is not None:
        updates, _prepared_artifacts = launch_prepared
        intake.update(updates)

    if answers_doc is not None:
        intake["answers_file"] = str(a.answers_file)
        intake["answers_file_sha256"] = hashlib.sha256(a.answers_file.read_bytes()).hexdigest()
        intake["to_confirm"] = [{"id": t.get("id"), "value": t.get("value"), "reason": t.get("reason")}
                                for t in answers_doc.get("to_confirm") or []]
        if from_answers.get("design_style") and a.design_style == from_answers["design_style"] and not a.design_style_source:
            entry = (answers_doc.get("answers") or {}).get("design_style") or {}
            # the gate accepts only these two values; the true status stays in design_style_status and to_confirm
            intake["design_style_source"] = "client_choice" if entry.get("status") == "provided" else "recommended_accepted"
            intake["design_style_status"] = entry.get("status")

    (a.run_dir / "intake.json").write_text(json.dumps(intake, indent=2) + "\n", encoding="utf-8")
    if answers_doc is not None:
        import brand_colors
        try:
            brand_path = brand_colors.record_from_answers(a.run_dir, a.answers_file)
            print(f"wrote {brand_path} from the answers file (palette_status="
                  f"{(brand_colors._json(brand_path) or {}).get('palette_status')})")
        except ValueError as exc:
            print(f"NOTE brand colors: {exc}. No wireframe, mockup or image stage may start until the client "
                  f"gives colors or the safe default is applied (python3 scripts/brand_colors.py check).")
        for t in intake["to_confirm"]:
            print(f"TO CONFIRM {t['id']}: {t['reason']}")
    for line in size_lines:
        print(line)
    print(f"wrote {a.run_dir / 'intake.json'} (image_engine={intake['image_engine']})")
    if launch_prepared is not None:
        _updates, artifacts = launch_prepared
        launch_context.write_artifacts(a.run_dir, artifacts)
        print(f"launch profile {launch_context.PROFILE_NAME} imported: "
              f"{', '.join(sorted(artifacts))} written under {a.run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
