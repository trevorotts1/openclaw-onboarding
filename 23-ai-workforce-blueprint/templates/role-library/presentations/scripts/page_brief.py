#!/usr/bin/env python3
"""
page_brief.py - the FIX-PLAN Item 20 seam module (presentations side).

WHAT THIS IS
-------------------------------------------------------------------------------------
Presentations stops being the only possible page builder for the elected page
set (sales page, checkout, VSL page). At the point where a run's page inputs
are complete, this module writes a versioned page-brief.json into the run
folder carrying everything a page builder (Skill 71's pipeline, or any other
conformant builder) needs, and nothing it must guess:

  * scope binding (deck / run / company / location), resolved by
    ghl_external_installer.resolve_scope - the SAME binding the installer
    phases use, never re-derived here;
  * the election record (the builders' own gate decisions, delegated to
    sales_checkout_builder.resolve_sales_checkout_gate and
    vsl_builder.resolve_vsl_gate - never re-derived, mirroring
    ghl_external_installer.resolve_gate);
  * the page set under the one-funnel rule (Loop 2C's proven layout: sales,
    checkout and VSL as pages inside ONE funnel for one client);
  * the offer block (checkout_form_builder.resolve_offer's shape);
  * approved copy blocks (the run's own copy artifacts, embedded verbatim
    with their paths and sha256 hashes);
  * a filled client-brand block following Skill 71's brand.schema.json
    pattern (palette, fonts, logo, founder photos), with every value's
    provenance stated - engine defaults are labeled engine defaults, never
    presented as client-supplied, and missing client brand inputs carry the
    CLIENT_MUST_SUPPLY sentinel instead of an invented value;
  * GIP v2.0 doctrine references for any imagery (SOP-GIP-01 v2.0 /
    SOP-GIP-02 v2.0, per Item 25's doctrine-weave);
  * form and consent requirements, with the consent posture of the owner's
    2026-10-13 ruling: every consent box REQUIRED to proceed, unchecked by
    default, the checkbox text is the consent sentence (the 2026-09-27 D3
    optional posture is superseded and is never carried into a brief);
  * APPROVED_CHECKOUT_URL semantics exactly as checkout_form_builder
    enforces them (a supplied URL must bind to this deck/company or the
    brief is refused, fail-closed - never silently dropped);
  * the client's model selection (or their configured default) AND the
    system's recommendations with reasons, as SEPARATE fields (owner
    decision 4, 2026-10-13): the selection is read only from the profile's
    model_choices selection field (Item 17's record, written only by
    resource_profile.record_model_choice); recommendations are read only
    from the recommendations_shown log. No code path in this module copies
    a recommendation into a selection.
  * provenance: run id, emitting phase ids, source artifact paths + hashes,
    brief schema version.

EMISSION RULES
-------------------------------------------------------------------------------------
  * One brief per ELECTED page type: working/pages/page-brief-<page>.v<N>.json
  * A declined election writes NO brief; the seam ledger
    (working/checkpoints/page_briefs.json, merged, never clobbered) records
    the waiver with the client's verbatim reason.
  * An unanswered election (defer) writes NO brief and is recorded as
    deferred - never conflated with a decline.
  * A gate fail-closed (a "no" with no verbatim reason, an unrecognized
    value) writes NO brief, records the AF code, and exits 3.
  * Briefs are IMMUTABLE once written: a re-run with changed inputs writes
    the NEXT version file; an existing brief file is never edited in place
    (the writer refuses an existing target path outright).
  * The schema validator (validate_brief) runs at write time and rejects an
    incomplete brief fail-closed: nothing is written.

THE RECEIPT (consumer side is FIX-PLAN Item 21, NOT this module)
-------------------------------------------------------------------------------------
The page side returns receipts in ghl_external_installer's provenance shape
(RECEIPT_SCHEMA "1.0"), extended with a brief_binding that names the brief
the receipt answers. The contract is pinned in page-brief-receipt.schema.json
beside this module. This module's --verify-receipts mode judges receipts that
exist with ghl_external_installer.validate_receipt's own semantics (ops-ledger
provenance, readback, input freshness) PLUS the brief binding; it builds
nothing and installs nothing.

WIRING NOTE
-------------------------------------------------------------------------------------
The P-U seam mode (brief emit at design-complete, receipt verify at the
install phases) registers as manifest phases in the manifest lockstep
ceremony; that registration is sequenced after the in-flight manifest v71
declarations land, so this module ships invocable exactly the way the
builders are invoked (python3 scripts/page_brief.py --run-dir <run_dir>) and
its manifest registration is specified in the stream manifest. The legacy
builders stay as the fallback for one release (Item 20's HOW).

USAGE
    python3 scripts/page_brief.py --run-dir <run_dir> [--page sales] [--emit]
    python3 scripts/page_brief.py --run-dir <run_dir> --verify-receipts
    python3 scripts/page_brief.py --selftest

EXIT CODES
    0  - emitted / correctly nothing to emit (deferred or waived) / verify:
         every present receipt complete and brief-bound (absent = pending,
         not a failure)
    2  - usage error
    3  - GATE BLOCKED: an election gate failed closed
    4  - VALIDATION / VERIFY FAILED: a brief failed write-time validation, or
         a present receipt is invalid or not bound to the current brief
    5  - BLOCKED: scope / offer / video / approved-URL blocker (phase-scoped)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Exit codes (mirroring the sibling builders' vocabulary)
# ---------------------------------------------------------------------------
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_GATE_BLOCKED = 3
EXIT_VERIFY_FAILED = 4
EXIT_BLOCKED = 5

BRIEF_SCHEMA_NAME = "page-brief"
BRIEF_SCHEMA_VERSION = "1.0"
PAGE_TYPES = ("sales", "checkout", "vsl")

BRIEF_REL_DIR = Path("working") / "pages"
LEDGER_REL = Path("working") / "checkpoints" / "page_briefs.json"
INTAKE_REL = Path("working") / "copy" / "intake.json"
MEDIA_LEDGER_REL = Path("working") / "checkpoints" / "media_library.json"

# The page a receipt phase answers (P-U-FORM-GATE's gate form serves the VSL
# viewer gate, so its receipt binds the vsl brief; P-U-GHL-SALES installs the
# sales AND checkout pages in the one funnel, so its receipt binds both).
PHASE_TO_PAGES = {
    "P-U-GHL-SALES": ("sales", "checkout"),
    "P-U-GHL-VSL": ("vsl",),
    "P-U-FORM-GATE": ("vsl",),
}

# Emitting phase ids recorded in provenance: the copy + design phases whose
# outputs complete this page's inputs (manifest v70, verified by parse).
EMITTING_PHASES = {
    "sales": ("P-U-SALES-COPY", "P-U-DESIGN-SALES", "P-U-DESIGN-RENDER-SALES"),
    "checkout": ("P-U-CHECKOUT-COPY", "P-U-DESIGN-CHECKOUT",
                 "P-U-DESIGN-RENDER-CHECKOUT"),
    "vsl": ("P-U-VSL-RESEARCH", "P-U-VSL-COPY", "P-U-DESIGN-VSL",
            "P-U-DESIGN-RENDER-VSL"),
}

CONSENT_RULING = (
    "owner ruling 2026-10-13: every consent box is REQUIRED to proceed, on "
    "every form this system ships (supersedes the 2026-09-27 fix-orders "
    "decision D3 optional posture); boxes are unchecked by default and the "
    "checkbox text is the consent sentence"
)

GIP_DOCTRINE = (
    {"sop": "SOP-GIP-01", "version": "2.0",
     "role": "image generation doctrine for any imagery on this page "
             "(Item 25 doctrine-weave: GIP doctrine adopted inside the "
             "presentations pipeline)"},
    {"sop": "SOP-GIP-02", "version": "2.0",
     "role": "image QC doctrine for any imagery on this page"},
)

SELECTION_SOURCES = ("selected", "configured-default")
CHECKOUT_INTENTS = ("lead_capture", "payment_sandbox")

MUST_SUPPLY = "CLIENT_MUST_SUPPLY"


class BriefError(RuntimeError):
    """A fail-closed brief failure (message names the refusing gate)."""


class BriefValidationError(BriefError):
    """validate_brief rejected the brief at write time."""

    def __init__(self, errors: List[str]):
        super().__init__("brief validation failed: " + "; ".join(errors))
        self.errors = errors


# ---------------------------------------------------------------------------
# Small helpers (repo style: stdlib only, atomic writes, ISO-UTC stamps)
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_file(p: Path) -> str:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return ""


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_json(p: Path) -> dict:
    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_atomic(p: Path, data: dict) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)
    return p


def _write_new_file(p: Path, text: str) -> Path:
    """Write a brief file that MUST NOT already exist (immutability): the
    final name is claimed with os.link from a temp file, which fails rather
    than overwriting when the target is taken."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    try:
        os.link(tmp, p)
    except FileExistsError:
        raise
    except OSError:
        # Filesystem without hardlinks: fall back to an exclusive create.
        with open(p, "x", encoding="utf-8") as fh:
            fh.write(text)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    return p


def _here() -> Path:
    return Path(__file__).resolve().parent


def _load_siblings() -> Dict[str, Any]:
    """Import the sibling executors this seam delegates to (the installer's
    own _load_builders posture: fail-soft at import, fail-CLOSED at use)."""
    here = str(_here())
    if here not in sys.path:
        sys.path.insert(0, here)
    mods: Dict[str, Any] = {}
    for name in ("sales_checkout_builder", "vsl_builder",
                 "checkout_form_builder", "ghl_external_installer"):
        try:
            mods[name] = __import__(name)
        except Exception:  # noqa: BLE001
            mods[name] = None
    return mods


def _rel(run_dir: Path, p: Path) -> str:
    try:
        return str(p.relative_to(run_dir))
    except ValueError:
        return str(p)


# ---------------------------------------------------------------------------
# Elections - delegated to the builders' own gates, never re-derived
# ---------------------------------------------------------------------------
def resolve_elections(intake: dict, mods: Dict[str, Any]) -> Dict[str, dict]:
    """One gate outcome per page type. Sales and checkout share the
    WANT_SALES_CHECKOUT gate (one election, two page types); VSL has its own
    WANT_VSL_PAGE gate. A missing builder is a fail-closed, never a pass."""
    scb, vb = mods.get("sales_checkout_builder"), mods.get("vsl_builder")
    if scb is None:
        sales_gate = {"decision": "fail_closed",
                      "detail": "sales_checkout_builder unavailable -- "
                                "fail-closed, not a pass"}
    else:
        sales_gate = scb.resolve_sales_checkout_gate(intake)
    if vb is None:
        vsl_gate = {"decision": "fail_closed",
                    "detail": "vsl_builder unavailable -- fail-closed, "
                              "not a pass"}
    else:
        vsl_gate = vb.resolve_vsl_gate(intake)
    return {"sales": sales_gate, "checkout": sales_gate, "vsl": vsl_gate}


def _election_record(page: str, gate: dict) -> dict:
    toggle = "WANT_VSL_PAGE" if page == "vsl" else "WANT_SALES_CHECKOUT"
    reason_field = ("VSL_PAGE_DECLINED_REASON" if page == "vsl"
                    else "SALES_CHECKOUT_DECLINED_REASON")
    rec = {
        "page_type": page,
        "toggle_field": toggle,
        "canonical_paths": [f"pre_presentation_capture.{toggle}", toggle],
        "want_raw": gate.get("want_raw"),
        "decision": gate.get("decision"),
        "detail": gate.get("detail"),
    }
    if gate.get("decision") == "waived":
        rec["declined_reason_field"] = reason_field
        rec["declined_reason"] = gate.get("quote")
    return rec


# ---------------------------------------------------------------------------
# Gatherers - every value comes from the run's own artifacts
# ---------------------------------------------------------------------------
COPY_CANDIDATES = {
    "sales": (
        ("builder-copy", Path("working/sales-checkout/copy/sales.md")),
        ("phase-fragment", Path("working/upsell/copy/sales.fragment.md")),
    ),
    "checkout": (
        ("builder-copy", Path("working/sales-checkout/copy/checkout.md")),
        ("phase-fragment", Path("working/upsell/copy/checkout.fragment.md")),
    ),
    "vsl": (
        ("builder-copy", Path("working/vsl/copy/vsl.md")),
        ("phase-fragment", Path("working/upsell/copy/vsl.fragment.md")),
        ("research", Path("working/upsell/vsl-research.md")),
    ),
}

DESIGN_PROMPT_CANDIDATES = (
    "working/prompts/{page}.design.txt",
    "working/design/{page}.design.txt",
    "working/upsell/prompts/{page}.design.txt",
    "prompts/{page}.design.txt",
)

RENDER_CANDIDATES = {
    "sales": (
        "working/sales-checkout/renders/sales-hero.png",
        "working/design/sales-design.png",
    ),
    "checkout": (
        "working/sales-checkout/renders/checkout-hero.png",
        "working/design/checkout-design.png",
    ),
    "vsl": (
        "working/vsl/renders/vsl-hero.png",
        "working/design/vsl-design.png",
    ),
}


def _copy_blocks(run_dir: Path, page: str) -> List[dict]:
    blocks: List[dict] = []
    for kind, rel in COPY_CANDIDATES[page]:
        p = run_dir / rel
        if p.is_file():
            text = p.read_text(encoding="utf-8", errors="replace")
            if text.strip():
                blocks.append({
                    "role": page, "kind": kind, "path": _rel(run_dir, p),
                    "sha256": _sha256_file(p), "text": text,
                })
    return blocks


def _design_block(run_dir: Path, page: str,
                  media: dict) -> dict:
    prompt = None
    for tmpl in DESIGN_PROMPT_CANDIDATES:
        p = run_dir / tmpl.format(page=page)
        if p.is_file():
            prompt = {"path": _rel(run_dir, p), "sha256": _sha256_file(p)}
            break
    renders: List[dict] = []
    for rel in RENDER_CANDIDATES[page]:
        p = run_dir / rel
        if p.is_file():
            renders.append({"path": _rel(run_dir, p),
                            "sha256": _sha256_file(p)})
    hero_url = None
    for r in renders:
        for entry in media.get("hosted", []):
            if entry.get("key") and Path(r["path"]).stem in str(entry["key"]):
                hero_url = entry.get("ghl_url")
        # The builders also record their hero in their own ledgers; the
        # media library is the seam's source of hosted URLs.
    return {
        "prompt": prompt,
        "renders": renders,
        "hero_ghl_url": hero_url,
        "imagery_doctrine": {
            "sops": list(GIP_DOCTRINE),
            "prompt_gate": "KIE rule 12 length band via the shared "
                           "prompt_gate at render time",
            "note": "Any imagery a page builder generates for this page "
                    "follows the GIP v2.0 doctrine above; renders already "
                    "produced by the run are listed with their hashes.",
        },
    }


def _media(run_dir: Path) -> dict:
    ledger = _read_json(run_dir / MEDIA_LEDGER_REL)
    hosted: List[dict] = []
    for key, entry in sorted(ledger.items()):
        if isinstance(entry, dict) and isinstance(entry.get("ghl_url"), str) \
                and entry["ghl_url"].strip():
            hosted.append({"key": key, "ghl_url": entry["ghl_url"].strip()})
    webinar = ledger.get("webinar_mp4")
    return {"hosted": hosted,
            "webinar_mp4": webinar if isinstance(webinar, dict) else None,
            "ledger_path": str(MEDIA_LEDGER_REL)}


def _brand_block(run_dir: Path, intake: dict, scope: dict,
                 mods: Dict[str, Any], media: dict) -> dict:
    """A filled client-brand block on Skill 71's brand.schema.json pattern.
    Palette comes from the builders' own resolve_brand; only the primary can
    be client-derived today (BRAND_PRIMARY), and the block says so - the
    remaining roles are labeled engine defaults, never client brand. Fonts
    the run does not carry are CLIENT_MUST_SUPPLY, never invented."""
    scb = mods.get("sales_checkout_builder")
    brief = intake.get("deck_brief") if isinstance(intake.get("deck_brief"),
                                                   dict) else {}
    if scb is not None:
        palette = scb.resolve_brand(run_dir, intake)
    else:
        palette = {"primary": "#212748", "secondary": "#B38456",
                   "accent": "#C49A70", "base": "#F2E6D7", "ink": "#1A1A1A"}
    client_supplied = []
    if isinstance(brief.get("BRAND_PRIMARY"), str) and \
            brief["BRAND_PRIMARY"].strip():
        client_supplied.append("primary")

    def _font(*keys: str) -> str:
        for key in keys:
            v = brief.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return MUST_SUPPLY

    logo_url = None
    founder_photos: List[str] = []
    for entry in media.get("hosted", []):
        key = str(entry.get("key") or "").lower()
        if "logo" in key and logo_url is None:
            logo_url = entry["ghl_url"]
        if "founder" in key or "headshot" in key:
            founder_photos.append(entry["ghl_url"])
    return {
        "brand_id": scope["deck_slug"],
        "source": "run intake deck_brief + the builders' brand resolution "
                  "(sales_checkout_builder.resolve_brand)",
        "palette": {k: palette[k] for k in
                    ("primary", "secondary", "accent", "base", "ink")},
        "palette_client_supplied": client_supplied,
        "palette_note": "Roles not listed in palette_client_supplied are "
                        "the engine's brand defaults, recorded as defaults "
                        "- a page builder must not present them as "
                        "client-supplied brand.",
        "fonts": {
            "display": _font("FONT_DISPLAY", "DISPLAY_FONT"),
            "body": _font("FONT_BODY", "BODY_FONT"),
            "accent": _font("FONT_ACCENT", "ACCENT_FONT"),
        },
        "logo": {"url": logo_url,
                 "source": "media_library" if logo_url else None},
        "founder_photos": founder_photos,
        "people_rule": (brief.get("PEOPLE_RULE")
                        if isinstance(brief.get("PEOPLE_RULE"), str)
                        and brief["PEOPLE_RULE"].strip() else None),
    }


def _offer_block(intake: dict, page: str,
                 mods: Dict[str, Any]) -> Tuple[Optional[dict], Optional[dict]]:
    """Returns (offer, blocker). Checkout carries checkout_form_builder's
    resolve_offer shape verbatim (its MISSING_OFFER blocker is honored);
    sales and VSL carry the same resolved offer plus the wider copy facts."""
    cfb = mods.get("checkout_form_builder")
    brief = intake.get("deck_brief") if isinstance(intake.get("deck_brief"),
                                                   dict) else {}
    if cfb is None:
        return None, {"code": "MISSING_INPUT",
                      "detail": "checkout_form_builder unavailable - "
                                "cannot resolve the offer block",
                      "action": "restore the sibling builder and re-run"}
    offer, blocker = cfb.resolve_offer(brief)
    if blocker is not None:
        return None, blocker
    offer = dict(offer)
    offer["transformation_promise"] = brief.get("TRANSFORMATION_PROMISE")
    offer["cta_action"] = brief.get("CTA_ACTION")
    offer["hook_seed"] = brief.get("HOOK_SEED")
    offer["tone"] = brief.get("TONE")
    offer["primary_objection"] = brief.get("PRIMARY_OBJECTION")
    offer["proof_assets"] = brief.get("PROOF_ASSETS")
    return offer, None


def _approved_url_block(intake: dict, scope: dict,
                        mods: Dict[str, Any]) -> Tuple[Optional[dict],
                                                        Optional[dict]]:
    """APPROVED_CHECKOUT_URL semantics, delegated to checkout_form_builder:
    absent → None; present and binding → the validated block; present but
    unbound/placeholder → the builder's blocker (fail-closed, never a
    silently dropped URL)."""
    cfb = mods.get("checkout_form_builder")
    brief = intake.get("deck_brief") if isinstance(intake.get("deck_brief"),
                                                   dict) else {}
    if cfb is None:
        return None, {"code": "MISSING_INPUT",
                      "detail": "checkout_form_builder unavailable - "
                                "cannot validate an approved checkout URL",
                      "action": "restore the sibling builder and re-run"}
    url, blocker = cfb.resolve_approved_url(
        brief, deck_slug=scope["deck_slug"], company=scope["company"])
    if blocker is not None:
        return None, blocker
    if not url:
        return None, None
    return {"url": url, "binding": "validated: absolute http(s), "
            "non-placeholder host, deck/company slug bound ("
            "checkout_form_builder.check_approved_url_binding)",
            "semantics": "when present, this URL is the checkout CTA target "
                         "for both page roles; no new checkout form is "
                         "created"}, None


def _consent_block(intake: dict, mods: Dict[str, Any]) -> dict:
    """The consent requirements under the 2026-10-13 ruling. The texts come
    from checkout_form_builder.resolve_consent_copy; the required flag is
    set by the RULING (the base builder still returns the superseded D3-era
    required: False until the consent-repair PR lands - the brief records
    the ruling posture and names that delta rather than copying the stale
    flag)."""
    cfb = mods.get("checkout_form_builder")
    brief = intake.get("deck_brief") if isinstance(intake.get("deck_brief"),
                                                   dict) else {}
    resolved = cfb.resolve_consent_copy(intake, brief) if cfb else {
        "element": "Terms & Conditions", "source": "unavailable", "boxes": []}
    boxes = []
    for box in resolved.get("boxes", []):
        boxes.append({
            "kind": box.get("kind"),
            "label": box.get("label"),
            "text": box.get("text"),
            "default_unchecked": True,
            "required": True,
            "required_source": CONSENT_RULING,
        })
    return {
        "posture": "all_required",
        "ruling": CONSENT_RULING,
        "element": resolved.get("element"),
        "copy_source": resolved.get("source"),
        "boxes": boxes,
        "note": "Benefit-first copy; the checkbox text is the consent "
                "sentence; no pre-checked box counts as consent.",
    }


def _checkout_form_block(run_dir: Path, intake: dict, scope: dict,
                         offer: dict, mods: Dict[str, Any]) -> Tuple[dict, Optional[dict]]:
    cfb = mods.get("checkout_form_builder")
    if cfb is None:
        return {}, {"code": "MISSING_INPUT",
                    "detail": "checkout_form_builder unavailable",
                    "action": "restore the sibling builder and re-run"}
    intent, blocker = cfb.resolve_intent(
        intake.get("deck_brief") if isinstance(intake.get("deck_brief"),
                                               dict) else {}, offer)
    if blocker is not None:
        return {}, blocker
    fields = cfb.build_form_schema(offer=offer, intent=intent,
                                   deck_slug=scope["deck_slug"])
    return {
        "intent": intent,
        "owner_skill": "44-convert-and-flow-operator",
        "mechanism": "SKILL44_WIDGET -> FORM",
        "form_name": f"ZHC {scope['deck_slug']} Checkout",
        "fields": fields,
        "workflow": {
            "name": f"ZHC {scope['deck_slug']} Checkout Enroll",
            "trigger": "form_submitted", "draft_only": True,
        },
        "embed_contract": {"type": "form_embed_js", "verbatim": True,
                           "sri": False},
        "live_payment": "never promised by a brief: live intent resolves "
                        "to a builder blocker by design; intents here are "
                        "lead_capture or payment_sandbox only",
    }, None


def _vsl_block(run_dir: Path, scope: dict,
               mods: Dict[str, Any]) -> Tuple[Optional[dict], Optional[dict]]:
    """The VSL video + viewer-gate block, delegated to vsl_builder's own
    resolvers (video artifact via build_webinar_video's canonical template,
    gate timestamp derived from webinar_timing.json, hosted URL from the
    media ledger). A missing/broken video is AF-VSL-NO-VIDEO, fail-closed."""
    vb = mods.get("vsl_builder")
    gx = mods.get("ghl_external_installer")
    if vb is None:
        return None, {"code": "MISSING_INPUT",
                      "detail": "vsl_builder unavailable",
                      "action": "restore the sibling builder and re-run"}
    deck_slug = scope["deck_slug"]
    try:
        video_path = vb.verify_video_dependency(run_dir, deck_slug)
    except Exception as exc:  # noqa: BLE001 - VslBuildError names the AF code
        return None, {"code": "AF-VSL-NO-VIDEO", "detail": str(exc),
                      "action": "run the webinar video phase first, then "
                                "re-run the seam"}
    video_url, video_warning = vb.resolve_video_ghl_url(run_dir, deck_slug)
    gate_ts = vb.resolve_gate_timestamp(run_dir)
    gate_fields = []
    if gx is not None:
        try:
            gate_fields = gx.gate_form_fields()
        except Exception:  # noqa: BLE001
            gate_fields = []
    block = {
        "video": {
            "artifact_path": _rel(run_dir, video_path),
            "hosted_url": video_url,
            "hosted": bool(video_url),
            "deck_slug_cross_check_warning": video_warning,
        },
        "gate": {
            "timestamp_seconds": gate_ts.get("seconds"),
            "timestamp_source": gate_ts.get("source"),
            "window_seconds": gate_ts.get("window"),
            "form_fields": gate_fields,
            "form_name": f"ZHC {deck_slug} VSL Gate",
            "workflow_name": f"ZHC {deck_slug} VSL Gate Engaged",
            "workflow_trigger": "form_submitted",
            "workflow_step": "add_contact_tag zhc_vsl_engaged",
            "draft_only": True,
        },
    }
    return block, None


def _model_block(profile: Optional[dict]) -> dict:
    """The model block, per owner decision 4. Selections are read ONLY from
    profile["model_choices"] rows' selection field (Item 17's record);
    recommendations ONLY from the rows' recommendations_shown log. The two
    lists are structurally distinct shapes: a selection carries
    {provider_family, model, source, recorded_at} with source in
    SELECTION_SOURCES; a recommendation carries {provider_family, model,
    reason, shown_at, response} and never a source. When the record is
    absent (the Item 17 PR unmerged on this base), selections is empty and
    record_status says so - a recommendation is never backfilled into a
    selection to fill the gap."""
    block: Dict[str, Any] = {
        "selections": [],
        "recommendations": [],
        "record_status": "profile unavailable to the seam",
        "doctrine": "the client selects their model, or their configured "
                    "default applies; recommendations are guidance with "
                    "reasons and never become a selection or a default "
                    "(owner decision 4, 2026-10-13)",
    }
    if not isinstance(profile, dict):
        return block
    rows = profile.get("model_choices")
    if not isinstance(rows, list):
        block["record_status"] = ("model_choices record not present in the "
                                  "profile (Item 17's record); selections "
                                  "empty by construction")
        slots = profile.get("model_plan")
        block["model_plan_slots"] = slots if isinstance(slots, dict) else None
        return block
    block["record_status"] = "model_choices record present (Item 17)"
    for row in rows:
        if not isinstance(row, dict):
            continue
        family = row.get("provider_family")
        selection = row.get("selection")
        if isinstance(selection, dict) and selection.get("model"):
            block["selections"].append({
                "provider_family": family,
                "model": selection.get("model"),
                "source": selection.get("source"),
                "recorded_at": selection.get("recorded_at"),
            })
        for entry in row.get("recommendations_shown") or []:
            if isinstance(entry, dict) and entry.get("model"):
                block["recommendations"].append({
                    "provider_family": family,
                    "model": entry.get("model"),
                    "reason": entry.get("reason"),
                    "shown_at": entry.get("shown_at"),
                    "response": entry.get("response"),
                })
    slots = profile.get("model_plan")
    block["model_plan_slots"] = slots if isinstance(slots, dict) else None
    return block


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def _source_artifacts(run_dir: Path, page: str,
                      copy_blocks: List[dict], design: dict) -> List[dict]:
    arts: List[dict] = []

    def _add(p: Path) -> None:
        if p.is_file():
            arts.append({"path": _rel(run_dir, p),
                         "sha256": _sha256_file(p)})

    _add(run_dir / INTAKE_REL)
    for block in copy_blocks:
        arts.append({"path": block["path"], "sha256": block["sha256"]})
    if design.get("prompt"):
        arts.append(design["prompt"])
    for r in design.get("renders", []):
        arts.append(r)
    if page == "vsl":
        _add(run_dir / MEDIA_LEDGER_REL)
        _add(run_dir / "working" / "checkpoints" / "webinar_timing.json")
    return arts


def assemble_brief(run_dir: Path, page: str, intake: dict, scope: dict,
                   gate: dict, profile: Optional[dict],
                   mods: Dict[str, Any]) -> Tuple[Optional[dict], Optional[dict]]:
    """Assemble one page's brief. Returns (brief, blocker); a blocker means
    the page's inputs are not complete and NO brief is written for it."""
    media = _media(run_dir)
    copy_blocks = _copy_blocks(run_dir, page)
    if not copy_blocks:
        return None, {"code": "MISSING_INPUT",
                      "detail": f"no copy artifact for the {page} page - "
                                "the brief emits when the page inputs are "
                                "complete, and no copy exists yet",
                      "action": "complete the copy phases, then re-run "
                                "the seam"}
    offer, blocker = _offer_block(intake, page, mods)
    if blocker is not None:
        return None, blocker
    approved, blocker = _approved_url_block(intake, scope, mods)
    if blocker is not None and page in ("sales", "checkout"):
        return None, blocker
    design = _design_block(run_dir, page, media)
    brief: Dict[str, Any] = {
        "schema": BRIEF_SCHEMA_NAME,
        "schema_version": BRIEF_SCHEMA_VERSION,
        "brief_id": f"{scope['deck_slug']}-{page}-brief",
        "page_type": page,
        "scope": {
            "deck_slug": scope["deck_slug"], "run_id": scope["run_id"],
            "company": scope["company"],
            "location_id": scope["location_id"],
            "location_bound": scope["location_bound"],
        },
        "election": _election_record(page, gate),
        "page_set": {
            "shared_funnel": True,
            "rule": "one funnel per client run: sales, checkout and VSL "
                    "are pages inside the SAME funnel (Loop 2C proven "
                    "layout); a page builder never creates a second "
                    "funnel for one client",
            "funnel_name": scope["company"],
            "pages_elected": None,  # filled by emit() with the full set
            "this_page": page,
        },
        "offer": offer,
        "copy_blocks": copy_blocks,
        "brand": _brand_block(run_dir, intake, scope, mods, media),
        "design": design,
        "media": {"hosted": media["hosted"],
                  "ledger_path": media["ledger_path"]},
        "model": _model_block(profile),
        "publish": {
            "target": "ghl",
            "location_id": scope["location_id"],
            "location_bound": scope["location_bound"],
            "draft_first": True,
            "may_publish": False,
            "authorization": "no publish authorization is recorded in the "
                             "run; pages install as DRAFTS unless an owner "
                             "approval record exists (the installer's "
                             "plan guard)",
        },
        "provenance": {
            "run_id": scope["run_id"], "deck_slug": scope["deck_slug"],
            "emitted_at": _now_iso(),
            "emitter": "scripts/page_brief.py (FIX-PLAN Item 20 seam)",
            "emitting_phases": list(EMITTING_PHASES[page]),
            "source_artifacts": _source_artifacts(run_dir, page,
                                                  copy_blocks, design),
        },
    }
    if page == "checkout":
        form_block, blocker = _checkout_form_block(run_dir, intake, scope,
                                                   offer, mods)
        if blocker is not None:
            return None, blocker
        brief["form"] = form_block
        brief["consent"] = _consent_block(intake, mods)
        brief["approved_checkout_url"] = approved
    if page == "sales":
        brief["cta"] = {
            "action": (intake.get("deck_brief") or {}).get("CTA_ACTION"),
            "href_semantics": "the CTA resolves to the approved checkout "
                              "URL when one is validated, else to the "
                              "in-funnel checkout page route; a production "
                              "CTA never resolves to #, empty, or "
                              "javascript: (checkout_form_builder."
                              "resolve_cta_href)",
        }
        brief["approved_checkout_url"] = approved
    if page == "vsl":
        vsl_block, blocker = _vsl_block(run_dir, scope, mods)
        if blocker is not None:
            return None, blocker
        brief["vsl"] = vsl_block
        brief["consent"] = {
            "posture": "gate_form_fields_required",
            "ruling": CONSENT_RULING,
            "note": "the VSL viewer-gate form's fields (email, first name, "
                    "phone) are all required by the gate contract; any "
                    "consent boxes a builder adds to this page follow the "
                    "same all-required ruling",
        }
    return brief, None


# ---------------------------------------------------------------------------
# Validation - fail-closed at write time, in the repo's own style
# ---------------------------------------------------------------------------
def _is_hex_color(v: Any) -> bool:
    return isinstance(v, str) and len(v) == 7 and v.startswith("#") and \
        all(c in "0123456789abcdef" for c in v[1:].lower())


def _is_sha256(v: Any) -> bool:
    return isinstance(v, str) and len(v) == 64 and \
        all(c in "0123456789abcdef" for c in v.lower())


def validate_brief(brief: Any) -> List[str]:
    """Return the list of validation errors (empty == valid). A brief that
    fails here is NEVER written (write_brief raises BriefValidationError)."""
    errs: List[str] = []
    if not isinstance(brief, dict):
        return ["brief is not a JSON object"]
    if brief.get("schema") != BRIEF_SCHEMA_NAME:
        errs.append(f"schema {brief.get('schema')!r} != {BRIEF_SCHEMA_NAME!r}")
    if brief.get("schema_version") != BRIEF_SCHEMA_VERSION:
        errs.append(f"schema_version {brief.get('schema_version')!r} != "
                    f"{BRIEF_SCHEMA_VERSION!r}")
    page = brief.get("page_type")
    if page not in PAGE_TYPES:
        errs.append(f"page_type {page!r} not in {PAGE_TYPES}")
        return errs
    ver = (brief.get("brief") or {}).get("version") \
        if isinstance(brief.get("brief"), dict) else brief.get("version")
    if not isinstance(ver, int) or ver < 1:
        errs.append("brief version missing or < 1")
    if not str(brief.get("brief_id") or "").strip():
        errs.append("brief_id missing")
    scope = brief.get("scope") if isinstance(brief.get("scope"), dict) else {}
    for key in ("deck_slug", "run_id", "company", "location_id"):
        if not str(scope.get(key) or "").strip():
            errs.append(f"scope.{key} missing")
    election = brief.get("election") if isinstance(brief.get("election"),
                                                   dict) else {}
    if election.get("decision") != "build":
        errs.append("election.decision is not 'build' - a brief is written "
                    "only for an elected page")
    expected_toggle = "WANT_VSL_PAGE" if page == "vsl" else \
        "WANT_SALES_CHECKOUT"
    if election.get("toggle_field") != expected_toggle:
        errs.append(f"election.toggle_field {election.get('toggle_field')!r}"
                    f" != {expected_toggle!r}")
    page_set = brief.get("page_set") if isinstance(brief.get("page_set"),
                                                   dict) else {}
    if page_set.get("shared_funnel") is not True:
        errs.append("page_set.shared_funnel is not true (one-funnel rule)")
    if page not in (page_set.get("pages_elected") or []):
        errs.append("page_set.pages_elected does not include this page")
    offer = brief.get("offer") if isinstance(brief.get("offer"), dict) else {}
    if not str(offer.get("name") or "").strip():
        errs.append("offer.name missing - a page builder must never guess "
                    "the offer")
    if page == "checkout":
        for key in ("price_display", "amount_minor", "currency",
                    "price_mode", "payment_plan"):
            if key not in offer:
                errs.append(f"offer.{key} missing on the checkout brief")
    blocks = brief.get("copy_blocks")
    if not isinstance(blocks, list) or not blocks:
        errs.append("copy_blocks missing or empty - the brief carries the "
                    "approved copy, the builder does not write its own")
    else:
        for i, b in enumerate(blocks):
            if not isinstance(b, dict) or b.get("role") != page:
                errs.append(f"copy_blocks[{i}].role is not {page!r}")
            elif not _is_sha256(b.get("sha256")):
                errs.append(f"copy_blocks[{i}].sha256 missing/invalid")
            elif not str(b.get("text") or "").strip():
                errs.append(f"copy_blocks[{i}].text empty")
    brand = brief.get("brand") if isinstance(brief.get("brand"), dict) else {}
    palette = brand.get("palette") if isinstance(brand.get("palette"),
                                                 dict) else {}
    for key in ("primary", "secondary", "accent", "base", "ink"):
        if not _is_hex_color(palette.get(key)):
            errs.append(f"brand.palette.{key} missing or not a hex color")
    if not str(brand.get("brand_id") or "").strip():
        errs.append("brand.brand_id missing")
    prov = brief.get("provenance") if isinstance(brief.get("provenance"),
                                                 dict) else {}
    arts = prov.get("source_artifacts")
    if not isinstance(arts, list) or not arts:
        errs.append("provenance.source_artifacts missing or empty")
    else:
        if not any(a.get("path") == str(INTAKE_REL) for a in arts
                   if isinstance(a, dict)):
            errs.append("provenance.source_artifacts does not include the "
                        "run intake")
        for i, a in enumerate(arts):
            if not isinstance(a, dict) or not _is_sha256(a.get("sha256")):
                errs.append(f"provenance.source_artifacts[{i}] lacks a "
                            "sha256")
    if prov.get("run_id") != scope.get("run_id"):
        errs.append("provenance.run_id does not match scope.run_id")
    model = brief.get("model") if isinstance(brief.get("model"), dict) else {}
    if not isinstance(model.get("selections"), list):
        errs.append("model.selections missing")
    else:
        for i, s in enumerate(model["selections"]):
            if not isinstance(s, dict) or not str(s.get("model") or "").strip():
                errs.append(f"model.selections[{i}].model missing")
            elif s.get("source") not in SELECTION_SOURCES:
                errs.append(f"model.selections[{i}].source "
                            f"{s.get('source')!r} not in {SELECTION_SOURCES}"
                            " - a recommendation is never a selection")
    if not isinstance(model.get("recommendations"), list):
        errs.append("model.recommendations missing")
    else:
        for i, r in enumerate(model["recommendations"]):
            if not isinstance(r, dict) or not str(r.get("model") or "").strip():
                errs.append(f"model.recommendations[{i}].model missing")
            elif "source" in r:
                errs.append(f"model.recommendations[{i}] carries a "
                            "selection 'source' field - recommendations "
                            "and selections are distinct shapes")
    publish = brief.get("publish") if isinstance(brief.get("publish"),
                                                 dict) else {}
    if publish.get("draft_first") is not True:
        errs.append("publish.draft_first is not true")
    if page == "checkout":
        form = brief.get("form") if isinstance(brief.get("form"), dict) else {}
        if form.get("intent") not in CHECKOUT_INTENTS:
            errs.append(f"form.intent {form.get('intent')!r} not in "
                        f"{CHECKOUT_INTENTS} - a brief never promises live "
                        "payment")
        consent = brief.get("consent") if isinstance(brief.get("consent"),
                                                     dict) else {}
        if consent.get("posture") != "all_required":
            errs.append("consent.posture is not 'all_required' (owner "
                        "ruling 2026-10-13)")
        boxes = consent.get("boxes")
        if not isinstance(boxes, list) or not boxes:
            errs.append("consent.boxes missing or empty on checkout brief")
        else:
            for i, b in enumerate(boxes):
                if not isinstance(b, dict) or b.get("required") is not True:
                    errs.append(f"consent.boxes[{i}].required is not true")
                elif b.get("default_unchecked") is not True:
                    errs.append(f"consent.boxes[{i}].default_unchecked is "
                                "not true")
    if page == "vsl":
        vsl = brief.get("vsl") if isinstance(brief.get("vsl"), dict) else {}
        video = vsl.get("video") if isinstance(vsl.get("video"), dict) else {}
        if not str(video.get("artifact_path") or "").strip():
            errs.append("vsl.video.artifact_path missing")
        gate = vsl.get("gate") if isinstance(vsl.get("gate"), dict) else {}
        ts = gate.get("timestamp_seconds")
        if not isinstance(ts, (int, float)) or ts <= 0:
            errs.append("vsl.gate.timestamp_seconds missing or <= 0")
        keys = [f.get("field_key") or f.get("key")
                for f in gate.get("form_fields") or []
                if isinstance(f, dict)]
        for need in ("zhc_vsl_email", "zhc_vsl_first_name", "zhc_vsl_phone"):
            if need not in keys:
                errs.append(f"vsl.gate.form_fields lacks {need}")
    return errs


# ---------------------------------------------------------------------------
# Writing - versioned, immutable, ledger-recorded
# ---------------------------------------------------------------------------
def brief_rel_path(page: str, version: int) -> Path:
    return BRIEF_REL_DIR / f"page-brief-{page}.v{version}.json"


def existing_brief_versions(run_dir: Path, page: str) -> List[int]:
    out: List[int] = []
    d = run_dir / BRIEF_REL_DIR
    if d.is_dir():
        for p in d.glob(f"page-brief-{page}.v*.json"):
            try:
                out.append(int(p.name.split(".v")[-1].split(".")[0]))
            except ValueError:
                continue
    return sorted(out)


def latest_brief(run_dir: Path, page: str) -> Tuple[Optional[Path], Optional[dict]]:
    versions = existing_brief_versions(run_dir, page)
    if not versions:
        return None, None
    p = run_dir / brief_rel_path(page, versions[-1])
    return p, _read_json(p)


def write_brief(run_dir: Path, brief: dict) -> Path:
    """Validate, then write the NEXT version file. Never edits an existing
    brief: the version is max(existing)+1 and the target is claimed
    no-clobber. Raises BriefValidationError before anything is written."""
    page = brief["page_type"]
    versions = existing_brief_versions(run_dir, page)
    version = (versions[-1] + 1) if versions else 1
    brief["version"] = version
    brief["supersedes"] = (str(brief_rel_path(page, versions[-1]))
                           if versions else None)
    errors = validate_brief(brief)
    if errors:
        raise BriefValidationError(errors)
    target = run_dir / brief_rel_path(page, version)
    _write_new_file(target, json.dumps(brief, indent=2))
    return target


def _record_ledger(run_dir: Path, page: str, event: dict) -> None:
    ledger = _read_json(run_dir / LEDGER_REL)
    pages = ledger.setdefault("pages", {})
    entry = pages.setdefault(page, {"events": []})
    entry["events"].append(event)
    entry["last"] = event
    ledger["updated_at"] = _now_iso()
    _write_json_atomic(run_dir / LEDGER_REL, ledger)


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------
def emit(run_dir: Path, pages: Optional[List[str]] = None,
         profile: Optional[dict] = None,
         env: Optional[dict] = None) -> Tuple[int, dict]:
    """Emit briefs for the elected pages of one run. Returns (exit_code,
    results) where results maps page -> outcome record. The run record (the
    seam ledger) says why for every page that got no brief."""
    pages = pages or list(PAGE_TYPES)
    mods = _load_siblings()
    gx = mods.get("ghl_external_installer")
    intake = _read_json(run_dir / INTAKE_REL)
    results: Dict[str, dict] = {}
    if not intake:
        for page in pages:
            rec = {"page": page, "outcome": "blocked",
                   "blocker": {"code": "MISSING_INPUT",
                               "detail": "working/copy/intake.json "
                                         "missing or unreadable",
                               "action": "complete intake, then re-run"}}
            _record_ledger(run_dir, page, {**rec, "checked_at": _now_iso()})
            results[page] = rec
        return EXIT_BLOCKED, results
    if gx is None:
        for page in pages:
            rec = {"page": page, "outcome": "fail_closed",
                   "detail": "ghl_external_installer unavailable - "
                             "fail-closed, not a pass"}
            _record_ledger(run_dir, page, {**rec, "checked_at": _now_iso()})
            results[page] = rec
        return EXIT_GATE_BLOCKED, results
    scope, blocker = gx.resolve_scope(run_dir, intake, env=env)
    if blocker is not None or scope is None:
        for page in pages:
            rec = {"page": page, "outcome": "blocked", "blocker": blocker}
            _record_ledger(run_dir, page, {**rec, "checked_at": _now_iso()})
            results[page] = rec
        return EXIT_BLOCKED, results
    gates = resolve_elections(intake, mods)
    elected = [p for p in PAGE_TYPES
               if gates[p].get("decision") == "build"]
    exit_code = EXIT_OK
    for page in pages:
        gate = gates[page]
        decision = gate.get("decision")
        election = _election_record(page, gate)
        if decision in ("defer", "waived"):
            rec = {"page": page, "outcome": decision,
                   "election": election,
                   "note": "no brief written - " +
                           ("the election was never answered"
                            if decision == "defer" else
                            "the client declined with a verbatim reason")}
            _record_ledger(run_dir, page, {**rec, "checked_at": _now_iso()})
            results[page] = rec
            continue
        if decision == "fail_closed":
            rec = {"page": page, "outcome": "fail_closed",
                   "election": election}
            _record_ledger(run_dir, page, {**rec, "checked_at": _now_iso()})
            results[page] = rec
            exit_code = EXIT_GATE_BLOCKED
            continue
        brief, blocker = assemble_brief(run_dir, page, intake, scope, gate,
                                        profile, mods)
        if blocker is not None or brief is None:
            rec = {"page": page, "outcome": "blocked", "blocker": blocker,
                   "election": election}
            _record_ledger(run_dir, page, {**rec, "checked_at": _now_iso()})
            results[page] = rec
            if exit_code == EXIT_OK:
                exit_code = EXIT_BLOCKED
            continue
        brief["page_set"]["pages_elected"] = elected
        try:
            path = write_brief(run_dir, brief)
        except BriefValidationError as exc:
            rec = {"page": page, "outcome": "validation_failed",
                   "errors": exc.errors, "election": election}
            _record_ledger(run_dir, page, {**rec, "checked_at": _now_iso()})
            results[page] = rec
            exit_code = EXIT_VERIFY_FAILED
            continue
        rec = {"page": page, "outcome": "emitted",
               "brief": _rel(run_dir, path),
               "version": brief["version"],
               "sha256": _sha256_file(path),
               "election": election}
        _record_ledger(run_dir, page, {**rec, "checked_at": _now_iso()})
        results[page] = rec
    return exit_code, results


# ---------------------------------------------------------------------------
# Receipt verification (judging only - the consumer is Item 21)
# ---------------------------------------------------------------------------
def check_brief_binding(run_dir: Path, phase_id: str,
                        receipt: dict) -> List[str]:
    """The seam extension to validate_receipt: the receipt must name, in
    brief_binding.briefs, the CURRENT emitted brief for each page the phase
    answers, with the brief file's exact sha256. A receipt answering a
    superseded brief is stale, exactly like stale input hashes."""
    errs: List[str] = []
    binding = receipt.get("brief_binding")
    if not isinstance(binding, dict) or not isinstance(binding.get("briefs"),
                                                       list):
        return [f"{phase_id}: receipt carries no brief_binding - it does "
                "not prove which brief it answers"]
    bound = {b.get("page_type"): b for b in binding["briefs"]
             if isinstance(b, dict)}
    for page in PHASE_TO_PAGES[phase_id]:
        path, current = latest_brief(run_dir, page)
        if path is None or current is None:
            errs.append(f"{phase_id}: no emitted brief for page {page!r} "
                        "to bind against")
            continue
        entry = bound.get(page)
        if entry is None:
            errs.append(f"{phase_id}: brief_binding lacks the {page} brief")
            continue
        if entry.get("brief_id") != current.get("brief_id"):
            errs.append(f"{phase_id}: brief_binding {page} brief_id "
                        f"{entry.get('brief_id')!r} != emitted "
                        f"{current.get('brief_id')!r}")
        if entry.get("version") != current.get("version"):
            errs.append(f"{phase_id}: brief_binding {page} version "
                        f"{entry.get('version')!r} != current "
                        f"{current.get('version')!r} (superseded brief)")
        if entry.get("sha256") != _sha256_file(path):
            errs.append(f"{phase_id}: brief_binding {page} sha256 does not "
                        "match the emitted brief file")
    return errs


def verify_receipts(run_dir: Path,
                    env: Optional[dict] = None) -> Tuple[int, dict]:
    """Judge the seam receipts that exist. Absent receipt = pending (not a
    failure, the installer's own posture). A present receipt must pass
    ghl_external_installer.validate_receipt AND the brief binding."""
    mods = _load_siblings()
    gx = mods.get("ghl_external_installer")
    results: Dict[str, dict] = {}
    if gx is None:
        return EXIT_VERIFY_FAILED, {"error": "ghl_external_installer "
                                             "unavailable"}
    exit_code = EXIT_OK
    for phase_id in PHASE_TO_PAGES:
        paths = gx.receipt_paths(run_dir, phase_id)
        if not paths[0].is_file():
            results[phase_id] = {"status": "pending",
                                 "detail": "no receipt - pending external "
                                           "execution, not a failure"}
            continue
        complete, detail, data = gx.validate_receipt(run_dir, phase_id,
                                                     env=env)
        binding_errs = check_brief_binding(run_dir, phase_id, data) \
            if isinstance(data, dict) else ["receipt unreadable"]
        ok = bool(complete) and not binding_errs
        results[phase_id] = {
            "status": "complete" if ok else "invalid",
            "installer_detail": detail,
            "binding_errors": binding_errs,
        }
        if not ok:
            exit_code = EXIT_VERIFY_FAILED
    return exit_code, results


# ---------------------------------------------------------------------------
# Profile loading for the CLI (fail-soft, like the driver's importers)
# ---------------------------------------------------------------------------
def _load_profile(config_dir: Optional[str],
                  profile_json: Optional[str]) -> Optional[dict]:
    if profile_json:
        return _read_json(Path(profile_json)) or None
    here = str(_here())
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        from presentation_job import resource_profile as rp  # noqa: E402
        return rp.load_profile(Path(config_dir) if config_dir else None)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Emit versioned page-brief.json files for a run's "
                    "elected pages (FIX-PLAN Item 20 seam), or verify the "
                    "receipts the page side returned.")
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("--page", action="append", choices=list(PAGE_TYPES),
                    default=None, help="restrict to one page type "
                                       "(repeatable)")
    ap.add_argument("--emit", action="store_true",
                    help="emit briefs (the default action)")
    ap.add_argument("--verify-receipts", action="store_true",
                    help="verify seam receipts against the emitted briefs")
    ap.add_argument("--config-dir", default=None,
                    help="resource profile config dir (model records)")
    ap.add_argument("--profile-json", default=None,
                    help="read the resource profile from this JSON file "
                         "instead of the profile store")
    ap.add_argument("--selftest", action="store_true",
                    help="offline deterministic self-test")
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    ap = _build_parser()
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not args.run_dir:
        ap.error("--run-dir is required (or --selftest)")
    run_dir = Path(args.run_dir).resolve()
    if args.verify_receipts:
        code, results = verify_receipts(run_dir)
        for phase_id, rec in results.items():
            print(f"{phase_id}: {rec.get('status')} "
                  f"{rec.get('installer_detail', '')} "
                  f"{rec.get('binding_errors', '')}")
        return code
    profile = _load_profile(args.config_dir, args.profile_json)
    code, results = emit(run_dir, pages=args.page, profile=profile)
    for page, rec in results.items():
        if rec["outcome"] == "emitted":
            print(f"{page}: EMITTED {rec['brief']} (v{rec['version']})")
        elif rec["outcome"] in ("defer", "waived"):
            print(f"{page}: {rec['outcome'].upper()} - no brief written "
                  f"({rec['election'].get('detail', '')})")
        elif rec["outcome"] == "blocked":
            blk = rec.get("blocker") or {}
            print(f"{page}: BLOCKED [{blk.get('code')}]: {blk.get('detail')}",
                  file=sys.stderr)
        elif rec["outcome"] == "validation_failed":
            print(f"{page}: VALIDATION FAILED: {rec['errors']}",
                  file=sys.stderr)
        else:
            print(f"{page}: {rec['outcome'].upper()}: "
                  f"{rec.get('detail', '')}", file=sys.stderr)
    return code


# ---------------------------------------------------------------------------
# Offline deterministic self-test
# ---------------------------------------------------------------------------
def _fixture_run(base: Path, *, sales: str = "yes", vsl: str = "yes",
                 sales_reason: str = "", vsl_reason: str = "") -> Path:
    run = base / "run-acme"
    (run / "working" / "copy").mkdir(parents=True)
    (run / "working" / "sales-checkout" / "copy").mkdir(parents=True)
    (run / "working" / "sales-checkout" / "renders").mkdir(parents=True)
    (run / "working" / "vsl" / "copy").mkdir(parents=True)
    (run / "working" / "vsl" / "renders").mkdir(parents=True)
    (run / "working" / "upsell" / "copy").mkdir(parents=True)
    (run / "working" / "checkpoints").mkdir(parents=True)
    (run / "working" / "delivery").mkdir(parents=True)
    pre: Dict[str, Any] = {}
    if sales:
        pre["WANT_SALES_CHECKOUT"] = sales
    if sales_reason:
        pre["SALES_CHECKOUT_DECLINED_REASON"] = sales_reason
    if vsl:
        pre["WANT_VSL_PAGE"] = vsl
    if vsl_reason:
        pre["VSL_PAGE_DECLINED_REASON"] = vsl_reason
    intake = {
        "deck_slug": "acme-brief",
        "company": "Acme Co",
        "GHL_LOCATION_ID": "loc-test-1",
        "pre_presentation_capture": pre,
        "deck_brief": {
            "OFFER_NAME": "Momentum Method",
            "FINAL_PRICE": "$997",
            "TRANSFORMATION_PROMISE": "Go from stuck to shipped in 30 days.",
            "AUDIENCE": "overwhelmed solo founders",
            "CTA_ACTION": "Enroll Now",
            "HOOK_SEED": "You don't need more time. You need momentum.",
            "PRIMARY_OBJECTION": "I don't have time for another program.",
            "PROOF_ASSETS": "312 founders shipped their first launch.",
            "TONE": "warm, direct",
            "BRAND_PRIMARY": "#1a2b6d",
        },
    }
    (run / INTAKE_REL).write_text(json.dumps(intake, indent=2),
                                  encoding="utf-8")
    (run / "working/sales-checkout/copy/sales.md").write_text(
        "# Sales copy\nMomentum Method for overwhelmed solo founders.\n",
        encoding="utf-8")
    (run / "working/sales-checkout/copy/checkout.md").write_text(
        "# Checkout copy\nComplete your order: Momentum Method, $997.\n",
        encoding="utf-8")
    (run / "working/vsl/copy/vsl.md").write_text(
        "# VSL copy\nWatch the Momentum Method training.\n",
        encoding="utf-8")
    (run / "working/upsell/copy/sales.fragment.md").write_text(
        "Sales fragment copy.\n", encoding="utf-8")
    (run / "working/checkpoints/media_library.json").write_text(
        json.dumps({
            "webinar_mp4": {
                "ghl_url": "https://storage.googleapis.com/msgsndr/loc-test-1/acme.mp4",
                "deck_slug": "acme-brief"},
            "logo_main": {
                "ghl_url": "https://assets.cdn.filesafe.space/loc-test-1/logo.png"},
        }), encoding="utf-8")
    (run / "working/checkpoints/webinar_timing.json").write_text(
        json.dumps({"total_audio_sec": 1200.0, "timing": [
            {"slide": 1, "audio_start": 0.0},
            {"slide": 5, "audio_start": 300.0},
            {"slide": 9, "audio_start": 700.0}]}), encoding="utf-8")
    video = run / "working" / "delivery" / "acme-brief-WEBINAR.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp42"
                      b"\x00\x00\x00\x08free")
    return run


FIXTURE_PROFILE = {
    "model_choices": [
        {"provider_family": "openrouter",
         "selection": {"model": "client-picked-model", "source": "selected",
                       "recorded_at": "2026-10-14T00:00:00Z"},
         "recommendations_shown": [
             {"model": "other-model", "reason": "shown as an alternative",
              "shown_at": "2026-10-14T00:00:00Z", "response": "declined"}]},
        {"provider_family": "ollama-cloud",
         "selection": None,
         "recommendations_shown": [
             {"model": "rec-only-model",
              "reason": "no provider cap; the machine is the only limit",
              "shown_at": "2026-10-14T00:00:00Z", "response": "offered"}]},
        {"provider_family": "deepseek-direct",
         "selection": {"model": "configured-model",
                       "source": "configured-default",
                       "recorded_at": "2026-10-14T00:00:00Z"},
         "recommendations_shown": []},
    ]
}


def _selftest() -> int:
    import tempfile

    fails: List[str] = []

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        # 1) Emission for each elected page type from fixture phase outputs.
        run = _fixture_run(base / "a")
        code, results = emit(run, profile=FIXTURE_PROFILE, env={})
        if code != EXIT_OK:
            fails.append(f"emit(elected) exit {code} != 0: {results}")
        briefs: Dict[str, dict] = {}
        for page in PAGE_TYPES:
            path, data = latest_brief(run, page)
            if path is None or data is None:
                fails.append(f"emit(elected): no brief for {page}")
                continue
            briefs[page] = data
            errs = validate_brief(data)
            if errs:
                fails.append(f"emitted {page} brief fails validation: {errs}")
            if data["provenance"]["run_id"] != run.name:
                fails.append(f"{page} brief provenance run_id wrong")
        co = briefs.get("checkout", {})
        if co.get("offer", {}).get("amount_minor") != 99700:
            fails.append(f"checkout offer amount wrong: {co.get('offer')}")
        boxes = (co.get("consent") or {}).get("boxes") or []
        if not boxes or not all(b.get("required") is True for b in boxes):
            fails.append("checkout consent boxes are not all required "
                         "(owner ruling 2026-10-13)")
        vsl_b = briefs.get("vsl", {})
        gate = (vsl_b.get("vsl") or {}).get("gate") or {}
        if gate.get("timestamp_seconds") != 300.0:
            fails.append(f"vsl gate timestamp wrong: {gate}")
        video = (vsl_b.get("vsl") or {}).get("video") or {}
        if not video.get("hosted"):
            fails.append(f"vsl video not recorded hosted: {video}")

        # 2) Model fields: selection and recommendation stay distinct.
        model = briefs.get("sales", {}).get("model") or {}
        sel = {(s.get("provider_family"), s.get("model"), s.get("source"))
               for s in model.get("selections", [])}
        if ("openrouter", "client-picked-model", "selected") not in sel:
            fails.append(f"selected model missing from selections: {sel}")
        if ("deepseek-direct", "configured-model",
                "configured-default") not in sel:
            fails.append(f"configured default missing/distinct: {sel}")
        if any(m == "rec-only-model" for _f, m, _s in sel):
            fails.append("a recommendation was written into selections")
        recs = {r.get("model") for r in model.get("recommendations", [])}
        if "rec-only-model" not in recs:
            fails.append(f"recommendation missing from guidance: {recs}")

        # 3) Immutability / versioning: change a copy input, re-emit; v1
        #    bytes are untouched and a v2 exists.
        v1_path, _ = latest_brief(run, "sales")
        v1_bytes = v1_path.read_bytes() if v1_path else b""
        (run / "working/sales-checkout/copy/sales.md").write_text(
            "# Sales copy v2\nChanged copy for the second emission.\n",
            encoding="utf-8")
        code, _r = emit(run, profile=FIXTURE_PROFILE, env={})
        versions = existing_brief_versions(run, "sales")
        if versions != [1, 2]:
            fails.append(f"versioning wrong: {versions}")
        if v1_path and v1_path.read_bytes() != v1_bytes:
            fails.append("v1 brief was edited in place (immutability break)")
        # A direct no-clobber attempt on an existing target must refuse.
        try:
            _write_new_file(run / brief_rel_path("sales", 1), "{}")
            fails.append("_write_new_file overwrote an existing brief")
        except FileExistsError:
            pass

        # 4) Declined elections emit none, and the run record says why.
        run2 = _fixture_run(base / "b", sales="no", vsl="no",
                            sales_reason="We already have a checkout page.",
                            vsl_reason="We don't have a video yet.")
        code, results2 = emit(run2, profile=FIXTURE_PROFILE, env={})
        if code != EXIT_OK:
            fails.append(f"emit(declined) exit {code} != 0")
        for page in PAGE_TYPES:
            if existing_brief_versions(run2, page):
                fails.append(f"declined {page} election emitted a brief")
            if results2[page]["outcome"] != "waived":
                fails.append(f"declined {page} outcome "
                             f"{results2[page]['outcome']} != waived")
        ledger = _read_json(run2 / LEDGER_REL)
        quote = ((ledger.get("pages") or {}).get("sales", {})
                 .get("last", {}).get("election", {})
                 .get("declined_reason"))
        if quote != "We already have a checkout page.":
            fails.append(f"ledger waiver quote wrong: {quote!r}")

        # 5) Defer (never answered) emits none and is NOT a decline.
        run3 = _fixture_run(base / "c", sales="", vsl="")
        code, results3 = emit(run3, profile=FIXTURE_PROFILE, env={})
        if code != EXIT_OK or results3["vsl"]["outcome"] != "defer":
            fails.append(f"defer outcome wrong: {code} {results3}")

        # 6) Gate fail-closed: a "no" with no verbatim reason.
        run4 = _fixture_run(base / "d", vsl="no")
        code, results4 = emit(run4, profile=FIXTURE_PROFILE, env={})
        if code != EXIT_GATE_BLOCKED or \
                results4["vsl"]["outcome"] != "fail_closed":
            fails.append(f"fail-closed outcome wrong: {code} {results4}")
        if existing_brief_versions(run4, "vsl"):
            fails.append("fail-closed vsl election emitted a brief")

        # 7) Validator rejects incomplete briefs (fail-closed at write).
        good = briefs.get("sales", {})
        bad = json.loads(json.dumps(good))
        bad["offer"]["name"] = ""
        if not validate_brief(bad):
            fails.append("validator ACCEPTED a brief with no offer name")
        bad2 = json.loads(json.dumps(good))
        bad2["model"]["selections"].append(
            {"provider_family": "x", "model": "rec-only-model",
             "source": "recommended", "recorded_at": None})
        if not validate_brief(bad2):
            fails.append("validator ACCEPTED source='recommended' as a "
                         "selection")
        bad3 = json.loads(json.dumps(briefs.get("checkout", {})))
        bad3["consent"]["boxes"][0]["required"] = False
        if not validate_brief(bad3):
            fails.append("validator ACCEPTED an optional consent box")
        bad4 = json.loads(json.dumps(good))
        bad4["copy_blocks"] = []
        if not validate_brief(bad4):
            fails.append("validator ACCEPTED a brief with no copy blocks")
        run5 = _fixture_run(base / "e")
        bad5 = json.loads(json.dumps(good))
        bad5.pop("provenance", None)
        try:
            write_brief(run5, bad5)
            fails.append("write_brief WROTE an invalid brief")
        except BriefValidationError:
            pass
        if existing_brief_versions(run5, "sales"):
            fails.append("an invalid brief file exists after refusal")

        # 8) Receipt binding: missing binding errs; matching binding is
        #    clean; a stale sha errs.
        errs = check_brief_binding(run, "P-U-GHL-SALES", {})
        if not errs:
            fails.append("binding check ACCEPTED a receipt with no "
                         "brief_binding")
        binding_briefs = []
        for page in ("sales", "checkout"):
            pth, cur = latest_brief(run, page)
            binding_briefs.append({
                "page_type": page, "brief_id": cur["brief_id"],
                "version": cur["version"], "sha256": _sha256_file(pth)})
        errs = check_brief_binding(
            run, "P-U-GHL-SALES", {"brief_binding": {"briefs": binding_briefs}})
        if errs:
            fails.append(f"binding check REJECTED a matching binding: {errs}")
        binding_briefs[0]["sha256"] = "0" * 64
        errs = check_brief_binding(
            run, "P-U-GHL-SALES", {"brief_binding": {"briefs": binding_briefs}})
        if not errs:
            fails.append("binding check ACCEPTED a stale brief sha")

        # 9) Verify mode with no receipts: pending, exit 0.
        code, vres = verify_receipts(run, env={})
        if code != EXIT_OK or vres["P-U-GHL-SALES"]["status"] != "pending":
            fails.append(f"verify(no receipts) wrong: {code} {vres}")

    if fails:
        print("page_brief selftest -> FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("page_brief selftest -> PASS (emission per elected page type; "
          "checkout offer + all-required consent; vsl video + derived gate; "
          "model selection vs recommendation distinct; versioning with "
          "byte-identical v1; declined emits none with the waiver in the "
          "run record; defer is not a decline; gate fail-closed exits 3; "
          "validator rejects incomplete briefs at write time; receipt "
          "binding match/stale/missing; verify pending posture)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
