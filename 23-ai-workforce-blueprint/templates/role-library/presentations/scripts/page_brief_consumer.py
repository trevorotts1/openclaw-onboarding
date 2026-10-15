#!/usr/bin/env python3
"""
page_brief_consumer.py - the FIX-PLAN Item 21 seam consumer (presentations
side): page-brief.json in, install plans + receipts out.

WHAT THIS IS
-------------------------------------------------------------------------------------
Item 20 (page_brief.py) emits one versioned page-brief.json per elected page
type and pins the receipt contract in page-brief-receipt.schema.json. This
module is the consumer that contract names: given a run's emitted briefs, it

  1. produces the install plan per page through the CANONICAL installer
     entry points (ghl_external_installer.build_page_install_plan /
     build_gate_form_plan - the Skill 06 / Skill 44 surfaces the installer
     already names; no REST shape is reimplemented here), in the brief's
     publish-as-drafts posture (publish.draft_first true, may_publish
     false), and writes the combined plan to
     working/pages/brief-consumer-plan.json;
  2. executes the plan through ghl_external_installer.execute_phase:
       * mode "stub" (the harness's dry/stub mode): in-memory Skill 06 /
         Skill 44 stand-in adapters run the FULL path (form creation,
         embed delivery, page install, read-back, receipt) with no live
         GHL session. Stub receipts name their stub adapters in
         execution.adapter - they prove the contract path, never a live
         install. The live session is Item 22's staffed step.
       * mode "delegated" (the production posture): no adapter in this
         process, so the installer emits plans + pending_external_execution
         receipts, exactly as it does today; a delegated Skill 06/44
         session (Item 22) executes them later.
  3. returns the receipt per page-brief-receipt.schema.json: the installer's
     own provenance receipt, extended ONLY with brief_binding (brief id +
     version + brief-file sha256 for every page the phase answers) and urls
     (per page id; null when the installer provides none), plus, on the
     sales/checkout receipt, the checkout form/workflow blocks the schema
     defines;
  4. verifies before it believes: every installed object is re-read through
     its adapter and compared (funnel/page/form/workflow ids, location,
     draft posture, slug, installed-content hash), the checkout form's
     consent read-back is compared against the brief's all-required
     posture (owner ruling 2026-10-13), and the receipt must pass
     ghl_external_installer.validate_receipt AND
     page_brief.check_brief_binding. A failed verification DOWNGRADes the
     receipt (status remote-created, readback.ok false, the failed page
     named in its read-back entry) - a receipt that cannot be verified
     reads as not installed, never as success (the Wiring Gate).

THE SKILL 44 GATE-FORM EMBEDS (Item 21, closing register item 30)
-------------------------------------------------------------------------------------
Two forms are delivered INTO the pages by this consumer, verbatim
(form_embed_js, no SRI, per the embed contracts):

  * the CHECKOUT form (the brief's form block: Skill 44 contract, fields,
    workflow, consent) is created through the Skill 44 adapter BEFORE the
    sales/checkout install, and its embed snippet replaces the native
    SKILL44_WIDGET seam form (<form id="checkout-order-form">) in
    working/sales-checkout/html/checkout.html, so the installed checkout
    page captures through the real form. The brief's approved_checkout_url
    reuse path creates NO form and splices nothing (the brief's own rule).
  * the VSL GATE form (P-U-FORM-GATE) is created through the installer's
    gate plan; its embed snippet replaces vsl_builder's native gate form
    (<form class="zhc-vsl-gate-form">) inside the gate overlay of
    working/vsl/html/vsl.html. The seam's shipped VSL page therefore never
    carries the native capture-nothing form: the splice fails closed when
    the native form is not found, and the VSL page phase is then blocked
    rather than installed with an unwired gate.

The embed snippet is treated as OPAQUE text supplied by the form adapter's
embed_snippet() (a live session captures the real embed_code_js per
vsl-gate-form-spec.json's capture list; the stubs synthesize the documented
form_embed_js shape). The consumer never parses or rewrites it; it splices
verbatim and verifies verbatim presence on read-back.

ONE-FUNNEL RULE: the VSL page installs into the sales funnel. When a sales
install is in scope for the run but its receipt cannot be verified, the
VSL phase is BLOCKED instead of letting the installer create a second
funnel for one client.

USAGE
    python3 scripts/page_brief_consumer.py --run-dir <run_dir> [--mode stub|delegated] [--phase <id> ...]
    python3 scripts/page_brief_consumer.py --selftest

EXIT CODES (the sibling vocabulary; worst outcome wins: 3 > 4 > 5 > 1 > 0)
    0  - every consumed phase complete and verified (stub mode), or plans
         + pending receipts emitted (delegated mode), or a phase correctly
         deferred/waived by its election gate
    2  - usage error
    3  - GATE BLOCKED: an election gate failed closed
    4  - VERIFY FAILED: a receipt failed validation, binding, or a
         consumer read-back (the page is marked failed in the receipt)
    5  - BLOCKED: no usable brief, brief/run scope mismatch, missing page
         HTML, or an embed splice that failed closed
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EXIT_OK = 0
EXIT_BUILD_FAILED = 1
EXIT_USAGE = 2
EXIT_GATE_BLOCKED = 3
EXIT_VERIFY_FAILED = 4
EXIT_BLOCKED = 5

MODE_STUB = "stub"
MODE_DELEGATED = "delegated"
MODES = (MODE_STUB, MODE_DELEGATED)

PHASE_SALES = "P-U-GHL-SALES"
PHASE_GATE = "P-U-FORM-GATE"
PHASE_VSL = "P-U-GHL-VSL"
# Execution order: sales first (creates the shared funnel), gate next (its
# embed must land in vsl.html before the VSL page installs), VSL last.
PHASE_ORDER = (PHASE_SALES, PHASE_GATE, PHASE_VSL)

CONSUMER_LEDGER_REL = Path("working") / "checkpoints" / "brief_consumer.json"
CONSUMER_PLAN_REL = Path("working") / "pages" / "brief-consumer-plan.json"
CHECKOUT_HTML_REL = Path("working") / "sales-checkout" / "html" / "checkout.html"
VSL_HTML_REL = Path("working") / "vsl" / "html" / "vsl.html"

CHECKOUT_FORM_MARKER = '<form id="checkout-order-form"'
VSL_FORM_MARKER = '<form class="zhc-vsl-gate-form"'


class ConsumerError(RuntimeError):
    """A fail-closed consumer failure (message names the refusing step)."""


class SpliceError(ConsumerError):
    """The embed splice failed closed (native form not found / unverifiable)."""


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


def _read_json(p: Path) -> dict:
    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_atomic(p: Path, data: dict) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)
    return p


def _here() -> Path:
    return Path(__file__).resolve().parent


def _load_siblings() -> Dict[str, Any]:
    """Import the sibling executors this consumer delegates to (the same
    posture as page_brief._load_siblings: fail-soft at import, fail-CLOSED
    at use - a missing Item 20 module is a named blocker, never a pass)."""
    here = str(_here())
    if here not in sys.path:
        sys.path.insert(0, here)
    mods: Dict[str, Any] = {}
    for name in ("page_brief", "ghl_external_installer",
                 "checkout_form_builder", "sales_checkout_builder",
                 "vsl_builder"):
        try:
            mods[name] = __import__(name)
        except Exception:  # noqa: BLE001
            mods[name] = None
    return mods


def _require(mods: Dict[str, Any], *names: str) -> None:
    missing = [n for n in names if mods.get(n) is None]
    if missing:
        raise ConsumerError(
            f"sibling module(s) unavailable: {missing} - the consumer "
            "delegates to page_brief (Item 20) and ghl_external_installer "
            "and refuses to reimplement them")


# ---------------------------------------------------------------------------
# Stub adapters (the harness's dry/stub mode). In-memory stand-ins for the
# Skill 06 / Skill 44 surfaces, in the installer's own memory-adapter
# spirit: location-scoped, proof only, and NAMED as stubs in every receipt
# they touch (execution.adapter carries the class name).
# ---------------------------------------------------------------------------
def stub_embed_snippet(form_id: str, form_name: str) -> str:
    """STUB stand-in for the embed_code_js a live Skill 44/06 session
    captures at form creation (vsl-gate-form-spec.json embed_contract:
    capture [embed_code_js, form_link]; type form_embed_js, verbatim, NO
    SRI attributes). The consumer treats the returned snippet as opaque:
    it is spliced verbatim and verified verbatim, never parsed."""
    return (
        f'<iframe src="https://api.leadconnectorhq.com/widget/form/{form_id}" '
        f'style="width:100%;height:100%;border:none;border-radius:4px" '
        f'id="inline-{form_id}" data-form-id="{form_id}" '
        f'data-form-name="{form_name}" title="{form_name}"></iframe>\n'
        f'<script src="https://link.msgsndr.com/js/form_embed.js"></script>'
    )


def _load_gx():
    mods = _load_siblings()
    _require(mods, "ghl_external_installer")
    return mods["ghl_external_installer"]


def _load_cfb():
    mods = _load_siblings()
    _require(mods, "checkout_form_builder")
    return mods["checkout_form_builder"]


class StubSkill06PageAdapter(_load_gx().MemoryPageAdapter):
    """MemoryPageAdapter plus a per-page content snapshot: install_page
    records the sha256 of the page's source HTML at install time, so the
    consumer's read-back compares what was INSTALLED against the file on
    disk (a post-install edit is a verification failure, not a pass)."""

    def __init__(self, location_id: str, run_dir: Path):
        super().__init__(location_id)
        self.run_dir = Path(run_dir)
        self._content: Dict[str, dict] = {}

    def install_page(self, funnel_id: str, page: dict) -> str:
        pid = super().install_page(funnel_id, page)
        snap = {"sha256": "", "bytes": 0}
        src = page.get("source")
        if src:
            p = self.run_dir / str(src)
            if p.is_file():
                data = p.read_bytes()
                snap = {"sha256": hashlib.sha256(data).hexdigest(),
                        "bytes": len(data)}
        self._content[pid] = snap
        return pid

    def readback_page(self, page_id: str) -> dict:
        rb = super().readback_page(page_id)
        snap = self._content.get(page_id) or {}
        rb["content_sha256"] = snap.get("sha256", "")
        rb["content_bytes"] = snap.get("bytes", 0)
        return rb


class StubSkill44GateAdapter(_load_gx().MemoryGateAdapter):
    """MemoryGateAdapter plus the form's embed snippet and a fields
    read-back (a live Skill 44 read-back re-GETs the form; the fields it
    carries are part of what the consumer verifies)."""

    def embed_snippet(self, form_id: str) -> str:
        contract = (self.forms.get(form_id) or {}).get("contract") or {}
        name = ((contract.get("form") or {}).get("name")) or ""
        return stub_embed_snippet(form_id, name)

    def readback_form(self, form_id: str) -> dict:
        rb = super().readback_form(form_id)
        contract = (self.forms.get(form_id) or {}).get("contract") or {}
        rb["fields"] = (contract.get("form") or {}).get("fields") or []
        rb["name"] = (contract.get("form") or {}).get("name")
        return rb


class StubSkill44CheckoutAdapter(_load_cfb().MemoryLeadAdapter):
    """MemoryLeadAdapter (checkout_form_builder's Skill 44 stand-in) plus
    the embed snippet and a contract read-back: the consumer verifies the
    brief's fields and all-required consent posture against what the form
    actually carries, read back after creation."""

    def embed_snippet(self, form_id: str) -> str:
        contract = (self.forms.get(form_id) or {}).get("contract") or {}
        name = ((contract.get("form") or {}).get("name")) or ""
        return stub_embed_snippet(form_id, name)

    def readback(self, form_id: str) -> dict:
        rb = super().readback(form_id)
        contract = (self.forms.get(form_id) or {}).get("contract") or {}
        form = contract.get("form") or {}
        rb["name"] = form.get("name")
        rb["fields"] = form.get("fields") or []
        rb["consent"] = form.get("consent") or {}
        rb["workflows"] = [
            {"workflow_id": w, "form_id": rec.get("form_id"),
             "location_id": self.location_id, "draft": True}
            for w, rec in self.workflows.items()
            if rec.get("form_id") == form_id
        ]
        return rb


# ---------------------------------------------------------------------------
# Embed splices (fail-closed). The native seam forms are REPLACED by the
# verbatim Skill 44 embed; a page whose native form cannot be found is
# never silently shipped with a capture-nothing form.
# ---------------------------------------------------------------------------
def _replace_form_element(html: str, marker: str, replacement: str,
                          label: str) -> str:
    start = html.find(marker)
    if start < 0:
        raise SpliceError(
            f"{label}: native form marker {marker!r} not found - refusing "
            "to ship a page whose capture form was not replaced by the "
            "Skill 44 embed (fail-closed)")
    end = html.find("</form>", start)
    if end < 0:
        raise SpliceError(f"{label}: native form has no closing </form>")
    end += len("</form>")
    return html[:start] + replacement + html[end:]


def _embed_block(form_id: str, snippet: str, kind: str) -> str:
    return (
        f"<!-- brief_consumer (FIX-PLAN Item 21): Skill 44 {kind} form "
        f"embed delivered VERBATIM (form_embed_js, no SRI); the native "
        f"seam form was replaced at install so no capture-nothing form "
        f"ships. -->\n"
        f'<div class="zhc-skill44-embed" data-form-id="{form_id}">\n'
        f"{snippet}\n</div>"
    )


def splice_checkout_embed(html: str, snippet: str, form_id: str) -> str:
    """Replace the checkout page's SKILL44_WIDGET seam form with the
    checkout form's verbatim embed. Post-conditions are asserted, not
    assumed: snippet present verbatim, native form gone."""
    out = _replace_form_element(
        html, CHECKOUT_FORM_MARKER,
        _embed_block(form_id, snippet, "checkout"), "checkout embed")
    if snippet not in out:
        raise SpliceError("checkout embed: snippet not present verbatim "
                          "after the splice")
    if CHECKOUT_FORM_MARKER in out:
        raise SpliceError("checkout embed: native seam form still present "
                          "after the splice")
    return out


def splice_vsl_gate_embed(html: str, snippet: str, form_id: str,
                          deck_slug: str) -> str:
    """Replace vsl_builder's native gate form inside the gate overlay with
    the gate form's verbatim embed. The overlay mechanic (pause + seek
    block at the gate timestamp) stays; the capture-nothing native form
    does not ship. Post-conditions asserted: snippet verbatim, native
    form gone, overlay still present."""
    out = _replace_form_element(
        html, VSL_FORM_MARKER,
        _embed_block(form_id, snippet, "VSL gate"), "vsl gate embed")
    if snippet not in out:
        raise SpliceError("vsl gate embed: snippet not present verbatim "
                          "after the splice")
    if VSL_FORM_MARKER in out:
        raise SpliceError("vsl gate embed: native gate form still "
                          "present after the splice")
    if f'id="zhc-vsl-gate-{deck_slug}"' not in out:
        raise SpliceError("vsl gate embed: gate overlay div missing "
                          "after the splice")
    return out


# ---------------------------------------------------------------------------
# Brief loading + binding
# ---------------------------------------------------------------------------
def _phase_briefs(run_dir: Path, phase_id: str,
                  mods: Dict[str, Any]) -> Tuple[Dict[str, Tuple[Path, dict]],
                                                 List[str]]:
    """Load the CURRENT brief for every page the phase answers. Returns
    ({page: (path, brief)}, problems). A missing brief is reported, never
    invented; an invalid brief is reported with its validator errors."""
    pb = mods["page_brief"]
    briefs: Dict[str, Tuple[Path, dict]] = {}
    problems: List[str] = []
    for page in pb.PHASE_TO_PAGES[phase_id]:
        path, data = pb.latest_brief(run_dir, page)
        if path is None or data is None:
            problems.append(f"no emitted brief for page {page!r} "
                            f"(working/pages/page-brief-{page}.v<N>.json)")
            continue
        errs = pb.validate_brief(data)
        if errs:
            problems.append(f"emitted {page} brief fails validation: "
                            f"{errs[:3]}")
            continue
        briefs[page] = (path, data)
    return briefs, problems


def _binding_for(briefs: Dict[str, Tuple[Path, dict]]) -> List[dict]:
    return [
        {"page_type": page, "brief_id": brief["brief_id"],
         "version": brief["version"], "sha256": _sha256_file(path)}
        for page, (path, brief) in sorted(briefs.items())
    ]


def _scope_of(briefs: Dict[str, Tuple[Path, dict]]) -> dict:
    first = next(iter(briefs.values()))[1]
    return {k: first["scope"][k] for k in
            ("deck_slug", "run_id", "company", "location_id")}


def _check_scopes(run_dir: Path, phase_id: str,
                  briefs: Dict[str, Tuple[Path, dict]],
                  intake: dict, env: Optional[dict],
                  mods: Dict[str, Any]) -> List[str]:
    """The brief's scope binding must agree with the run the consumer was
    pointed at AND with the installer's own scope resolution. Any
    disagreement is a refusal, never a silent rebind (a brief for another
    run or location must never install here)."""
    gx = mods["ghl_external_installer"]
    errs: List[str] = []
    scopes = {page: brief["scope"] for page, (_p, brief) in briefs.items()}
    first = next(iter(scopes.values()))
    for page, sc in scopes.items():
        for key in ("deck_slug", "run_id", "company", "location_id"):
            if sc.get(key) != first.get(key):
                errs.append(f"{phase_id}: {page} brief scope.{key} "
                            f"{sc.get(key)!r} disagrees with the phase "
                            f"scope {first.get(key)!r}")
        if sc.get("run_id") != run_dir.name:
            errs.append(f"{phase_id}: {page} brief is bound to run "
                        f"{sc.get('run_id')!r}, not this run "
                        f"{run_dir.name!r} - refusing a foreign brief")
    scope, blocker = gx.resolve_scope(run_dir, intake, env=env)
    if blocker is not None:
        errs.append(f"{phase_id}: installer scope refused: "
                    f"[{blocker.get('code')}] {blocker.get('detail')}")
    elif scope is not None:
        if scope["location_id"] != first.get("location_id"):
            errs.append(
                f"{phase_id}: brief location {first.get('location_id')!r}"
                f" != the run's bound location {scope['location_id']!r} "
                "(WRONG_LOCATION - a brief must never install into a "
                "different client location)")
        if scope["deck_slug"] != first.get("deck_slug"):
            errs.append(f"{phase_id}: brief deck {first.get('deck_slug')!r}"
                        f" != run deck {scope['deck_slug']!r}")
    return errs


# ---------------------------------------------------------------------------
# The checkout form step (from the brief, never re-derived from intake)
# ---------------------------------------------------------------------------
def build_checkout_contract(brief: dict, scope: dict) -> dict:
    """The Skill 44 checkout-form contract AS THE BRIEF CARRIES IT: the
    brief's form block (fields, form name, workflow, embed contract from
    checkout_form_builder at brief time) plus the brief's consent block
    with the 2026-10-13 all-required posture. Building from the brief (not
    from intake) is the seam's point: the brief is the fixed input, and
    its consent boxes already carry required: true from the ruling - the
    base checkout_form_builder.resolve_consent_copy still returns the
    superseded D3-era required: False on this base, so resolving consent
    from intake here would silently ship the wrong posture."""
    form = brief["form"]
    consent = brief["consent"]
    boxes = []
    for box in consent.get("boxes") or []:
        boxes.append({
            "kind": box.get("kind"), "label": box.get("label"),
            "text": box.get("text"),
            "default_unchecked": True, "required": True,
            "required_source": box.get("required_source"),
        })
    return {
        "schema_version": "1.0",
        "spec": "Checkout order form -- Skill-44 FORM object contract "
                "(from the page brief, FIX-PLAN Item 21)",
        "owner_skill": "44-convert-and-flow-operator",
        "cli": "caf (PIT-authenticated)",
        "mechanism": form["mechanism"],
        "scope": scope,
        "intent": form["intent"],
        "form": {
            "name": form["form_name"],
            "start_from": "scratch",
            "fields": form["fields"],
            "form_id": None,
            "consent": {
                "element": consent.get("element"),
                "posture": consent.get("posture"),
                "ruling": consent.get("ruling"),
                "boxes": boxes,
            },
        },
        "workflow": {
            "name": form["workflow"]["name"],
            "trigger": {"type": form["workflow"]["trigger"],
                        "filter": {"form": "<this checkout form -- bound "
                                           "AFTER creation>"}},
            "workflow_id": None,
            "draft_only": True,
        },
        "embed_contract": form["embed_contract"],
    }


def verify_consent_readback(brief_consent: dict,
                            readback_consent: dict) -> List[str]:
    """The all-required consent posture, verified against the form's
    read-back (owner ruling 2026-10-13): every box the brief carries must
    come back present, required, unchecked by default, with the brief's
    exact text (the checkbox text IS the consent sentence)."""
    errs: List[str] = []
    if brief_consent.get("posture") != "all_required":
        errs.append(f"brief consent posture "
                    f"{brief_consent.get('posture')!r} != 'all_required'")
        return errs
    rb_boxes = {b.get("kind"): b for b in readback_consent.get("boxes") or []
                if isinstance(b, dict)}
    for box in brief_consent.get("boxes") or []:
        kind = box.get("kind")
        rb = rb_boxes.get(kind)
        if rb is None:
            errs.append(f"consent box {kind!r} missing from the checkout "
                        "form read-back")
            continue
        if rb.get("required") is not True:
            errs.append(f"consent box {kind!r} read back required="
                        f"{rb.get('required')!r} - the 2026-10-13 ruling "
                        "requires every box")
        if rb.get("default_unchecked") is not True:
            errs.append(f"consent box {kind!r} read back "
                        "default_unchecked != true")
        if rb.get("text") != box.get("text"):
            errs.append(f"consent box {kind!r} text differs from the "
                        "brief's consent sentence")
    return errs


def _field_keys(fields: List[dict]) -> set:
    keys = set()
    for f in fields or []:
        if isinstance(f, dict):
            keys.add(f.get("field_key") or f.get("label"))
    return keys


# ---------------------------------------------------------------------------
# Receipt extension + failure marking (the receipt return)
# ---------------------------------------------------------------------------
def _extend_receipt(path: Path, *, binding: List[dict],
                    urls: Optional[dict] = None,
                    form_block: Optional[dict] = None,
                    workflow_block: Optional[dict] = None,
                    readback_form: Optional[dict] = None,
                    readback_workflow: Optional[dict] = None) -> dict:
    """Extend an installer receipt with the seam's fields ONLY
    (brief_binding, urls, and the schema's form/workflow blocks). The
    installer's own fields are never rewritten here."""
    data = _read_json(path)
    if not data:
        return data
    data["brief_binding"] = {"briefs": binding}
    if urls is not None:
        data["urls"] = urls
    if form_block is not None:
        data["form"] = form_block
    if workflow_block is not None:
        data["workflow"] = workflow_block
    rb = data.get("readback") if isinstance(data.get("readback"), dict) \
        else None
    if rb is not None:
        if readback_form is not None:
            rb["form"] = readback_form
        if readback_workflow is not None:
            rb["workflow"] = readback_workflow
        data["readback"] = rb
    _write_json_atomic(path, data)
    return data


def _urls_from_receipt(data: dict) -> dict:
    """Per-page urls keyed by page id. Values come from the receipt's own
    read-back when the installer provides them; otherwise null - the seam
    requires the key for any page the receipt claims as installed, and a
    null is the honest record that the installer provided none."""
    remote = data.get("remote") if isinstance(data.get("remote"), dict) \
        else {}
    rb_pages = ((data.get("readback") or {}).get("pages")
                if isinstance(data.get("readback"), dict) else {}) or {}
    urls: Dict[str, dict] = {}
    for key, pid in remote.items():
        if key.endswith("_page_id") and pid:
            rb = rb_pages.get(pid) if isinstance(rb_pages, dict) else {}
            rb = rb if isinstance(rb, dict) else {}
            urls[pid] = {"preview_url": rb.get("preview_url"),
                         "public_url": rb.get("public_url")}
    return urls


def _mark_failed(paths: List[Path], failed_pids: List[str],
                 failures: List[str], mods: Dict[str, Any]) -> None:
    """A failed verification marks the receipt NOT complete and the failed
    page(s) failed in their read-back entries. The receipt keeps its
    remote ids and provenance (the objects may exist); it simply no
    longer reads as a verified install, so validate_receipt and
    page_brief.verify_receipts judge it not installed."""
    gx = mods["ghl_external_installer"]
    for path in paths:
        data = _read_json(path)
        if not data:
            continue
        if data.get("status") in gx.STATUSES_COMPLETE:
            data["status"] = gx.STATUS_REMOTE_CREATED
        rb = data.get("readback") if isinstance(data.get("readback"),
                                                dict) else {}
        rb["ok"] = False
        pages = rb.get("pages") if isinstance(rb.get("pages"), dict) \
            else None
        if pages is not None:
            for pid in failed_pids:
                entry = pages.get(pid) if isinstance(pages.get(pid), dict) \
                    else {}
                entry = dict(entry)
                entry["ok"] = False
                entry["error"] = ("consumer verification failed: "
                                  + "; ".join(failures[:3]))
                pages[pid] = entry
            rb["pages"] = pages
        data["readback"] = rb
        data["proof"] = {"verified": False, "failures": failures}
        _write_json_atomic(path, data)


# ---------------------------------------------------------------------------
# Verification read-backs (each installed object re-read and compared)
# ---------------------------------------------------------------------------
def _verify_pages(run_dir: Path, phase_id: str, data: dict, scope: dict,
                  adapter: Any, mods: Dict[str, Any]) -> Tuple[List[str],
                                                                List[str]]:
    """Re-read every installed page through the adapter and compare:
    funnel, location, DRAFT posture (publish-as-drafts), slug, and the
    installed content hash vs the source file on disk. Returns
    (failures, failed_page_ids)."""
    gx = mods["ghl_external_installer"]
    failures: List[str] = []
    failed: List[str] = []
    remote = data.get("remote") if isinstance(data.get("remote"), dict) \
        else {}
    _fname, specs = gx._page_specs(run_dir, phase_id, scope)
    spec_by_key = {s["key"]: s for s in specs}
    for key, pid in sorted(remote.items()):
        if not key.endswith("_page_id") or not pid:
            continue
        page_key = key[: -len("_page_id")]
        try:
            rb = adapter.readback_page(pid)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{phase_id}: read-back of page {pid} raised "
                            f"{exc!r}")
            failed.append(pid)
            continue
        problems = []
        if rb.get("page_id") != pid:
            problems.append(f"read-back page_id {rb.get('page_id')!r} "
                            f"!= installed {pid!r}")
        if rb.get("funnel_id") != remote.get("funnel_id"):
            problems.append(f"read-back funnel {rb.get('funnel_id')!r} "
                            f"!= receipt funnel {remote.get('funnel_id')!r}")
        if rb.get("location_id") != scope["location_id"]:
            problems.append(f"read-back location "
                            f"{rb.get('location_id')!r} != brief scope "
                            f"{scope['location_id']!r}")
        if rb.get("draft") is not True:
            problems.append("read-back page is not a DRAFT - the brief's "
                            "publish posture is drafts only "
                            "(may_publish false)")
        spec = spec_by_key.get(page_key)
        if spec is not None and rb.get("slug") != spec.get("slug"):
            problems.append(f"read-back slug {rb.get('slug')!r} != plan "
                            f"slug {spec.get('slug')!r}")
        if spec is not None and rb.get("content_sha256") is not None:
            src = run_dir / str(spec.get("source") or "")
            if rb["content_sha256"] != _sha256_file(src):
                problems.append("installed content hash != the page "
                                "source on disk (the page changed after "
                                "install, or a different page installed)")
        if problems:
            failures.extend(f"{phase_id} page {page_key} ({pid}): {p}"
                            for p in problems)
            failed.append(pid)
    return failures, failed


def _verify_installer_and_binding(run_dir: Path, phase_id: str,
                                  env: Optional[dict],
                                  mods: Dict[str, Any]) -> Tuple[List[str],
                                                                 dict]:
    """The wiring gate itself: the installer's validate_receipt plus
    page_brief.check_brief_binding, exactly as the presentations-side
    verifier (Item 20) judges."""
    gx, pb = mods["ghl_external_installer"], mods["page_brief"]
    failures: List[str] = []
    ok, detail, data = gx.validate_receipt(run_dir, phase_id, env=env)
    if not ok:
        failures.append(detail)
    if not isinstance(data, dict) or not data:
        data = gx.load_receipt(run_dir, phase_id)
    failures.extend(pb.check_brief_binding(run_dir, phase_id, data))
    return failures, data


# ---------------------------------------------------------------------------
# The consumer plan (working/pages/brief-consumer-plan.json)
# ---------------------------------------------------------------------------
def _consumer_plan(run_dir: Path, mode: str, intake: dict,
                   env: Optional[dict], mods: Dict[str, Any],
                   phase_briefs: Dict[str, Dict[str, Tuple[Path, dict]]]
                   ) -> dict:
    """The install plan per page, produced through the installer's own
    plan builders (which name the canonical Skill 06 / Skill 44 entry
    points), plus the consumer's form/embed steps."""
    gx = mods["ghl_external_installer"]
    phases: List[dict] = []
    for phase_id in PHASE_ORDER:
        briefs = phase_briefs.get(phase_id) or {}
        if not briefs:
            continue
        scope = _scope_of(briefs)
        entry: Dict[str, Any] = {
            "phase": phase_id,
            "brief_binding": {"briefs": _binding_for(briefs)},
            "scope": scope,
            "posture": "publish as DRAFTS only (brief publish.draft_first "
                       "true, may_publish false)",
            "receipts": [str(p.relative_to(run_dir))
                         for p in gx.receipt_paths(run_dir, phase_id)],
        }
        if phase_id in (PHASE_SALES, PHASE_VSL):
            funnel_name, pages = gx._page_specs(run_dir, phase_id, scope)
            shared = None
            if phase_id == PHASE_VSL:
                shared = gx.shared_funnel_id(run_dir)
            entry["plan"] = gx.build_page_install_plan(
                phase_id=phase_id, scope=scope, pages=pages,
                funnel_name=funnel_name, shared_funnel_id=shared)
            entry["plan_file"] = ("working/sales-checkout/ghl_install_plan.json"
                                  if phase_id == PHASE_SALES
                                  else "working/vsl/ghl_install_plan.json")
        if phase_id == PHASE_SALES and "checkout" in briefs:
            cbrief = briefs["checkout"][1]
            if cbrief.get("approved_checkout_url"):
                entry["form_step"] = {
                    "action": "none - the brief carries an approved "
                              "checkout URL; no new form is created and "
                              "nothing is embedded",
                    "approved_checkout_url": cbrief["approved_checkout_url"],
                }
            else:
                entry["form_step"] = {
                    "action": "create the Skill 44 checkout form + "
                              "workflow from the brief's form block, then "
                              "splice the verbatim embed into "
                              "working/sales-checkout/html/checkout.html "
                              "replacing the SKILL44_WIDGET seam form, "
                              "BEFORE the page install so the receipt's "
                              "input hashes bind the shipped page",
                    "contract": build_checkout_contract(cbrief, scope),
                    "consent_verification": "the form read-back's "
                                            "consent boxes are compared "
                                            "to the brief's all-required "
                                            "posture (2026-10-13 ruling)",
                }
        if phase_id == PHASE_GATE and "vsl" in briefs:
            vbrief = briefs["vsl"][1]
            gate = (vbrief.get("vsl") or {}).get("gate") or {}
            entry["plan"] = gx.build_gate_form_plan(
                scope=scope, fields=gate.get("form_fields"))
            entry["plan_file"] = "working/vsl/gate_form_skill44_plan.json"
            entry["form_step"] = {
                "action": "create the gate form + workflow through the "
                          "plan, then splice the verbatim embed into "
                          "working/vsl/html/vsl.html replacing "
                          "vsl_builder's native gate form inside the "
                          "gate overlay, BEFORE the VSL page install",
                "gate_timestamp_seconds": gate.get("timestamp_seconds"),
            }
        phases.append(entry)
    plan = {
        "schema_version": "1.0",
        "consumer": "scripts/page_brief_consumer.py (FIX-PLAN Item 21 "
                    "seam consumer, presentations side)",
        "mode": mode,
        "run_id": run_dir.name,
        "phases": phases,
        "built_at": _now_iso(),
    }
    _write_json_atomic(run_dir / CONSUMER_PLAN_REL, plan)
    return plan


# ---------------------------------------------------------------------------
# Phase runners
# ---------------------------------------------------------------------------
def _record_consumer_phase(run_dir: Path, phase_id: str, record: dict,
                           mode: str) -> None:
    ledger = _read_json(run_dir / CONSUMER_LEDGER_REL)
    phases = ledger.get("phases") if isinstance(ledger.get("phases"),
                                                dict) else {}
    phases[phase_id] = record
    ledger["phases"] = phases
    ledger["mode"] = mode
    ledger["run_id"] = run_dir.name
    ledger["updated_at"] = _now_iso()
    _write_json_atomic(run_dir / CONSUMER_LEDGER_REL, ledger)


def _ops_status(run_dir: Path, phase_id: str,
                mods: Dict[str, Any]) -> str:
    ops = mods["ghl_external_installer"].load_ops(run_dir).get(phase_id) \
        or {}
    return str(ops.get("status") or "")


def _outcome_from_installer(run_dir: Path, phase_id: str, rc: int,
                            mode: str,
                            mods: Dict[str, Any]) -> Tuple[str, int]:
    """Map an execute_phase result to (outcome, exit contribution) for
    the non-verification paths. Stub-mode completions are verified by the
    caller before being called complete."""
    gx = mods["ghl_external_installer"]
    if rc == gx.EXIT_GATE_BLOCKED:
        return "fail_closed", EXIT_GATE_BLOCKED
    if rc == gx.EXIT_BLOCKED:
        return "blocked", EXIT_BLOCKED
    if rc == gx.EXIT_BUILD_FAILED:
        return "failed", EXIT_BUILD_FAILED
    if rc != gx.EXIT_OK:
        return "failed", EXIT_VERIFY_FAILED
    data = gx.load_receipt(run_dir, phase_id)
    status = data.get("status")
    if status == gx.STATUS_PENDING:
        return "pending_external_execution", EXIT_OK
    if status in gx.STATUSES_COMPLETE:
        return ("complete" if mode == MODE_STUB else "verified"), EXIT_OK
    ops = _ops_status(run_dir, phase_id, mods)
    if ops in ("deferred", "waived"):
        return ops, EXIT_OK
    return str(status or ops or "unknown"), EXIT_OK


def _extend_phase_receipts(run_dir: Path, phase_id: str, binding: List[dict],
                           mods: Dict[str, Any], *,
                           form_block: Optional[dict] = None,
                           workflow_block: Optional[dict] = None,
                           readback_form: Optional[dict] = None,
                           readback_workflow: Optional[dict] = None
                           ) -> dict:
    """Extend every receipt file of the phase with the brief binding (and,
    for page phases, urls). Returns the primary receipt's data."""
    gx = mods["ghl_external_installer"]
    primary: dict = {}
    for path in gx.receipt_paths(run_dir, phase_id):
        if not path.is_file():
            continue
        data = _extend_receipt(
            path, binding=binding, form_block=form_block,
            workflow_block=workflow_block, readback_form=readback_form,
            readback_workflow=readback_workflow)
        if phase_id != PHASE_GATE and data:
            data = _extend_receipt(path, binding=binding,
                                   urls=_urls_from_receipt(data))
        if path == gx.receipt_paths(run_dir, phase_id)[0]:
            primary = data
    return primary


def _consume_sales(run_dir: Path, ctx: Dict[str, Any]) -> dict:
    gx = ctx["mods"]["ghl_external_installer"]
    phase_id = PHASE_SALES
    briefs = ctx["briefs_by_phase"][phase_id]
    binding = _binding_for(briefs)
    scope = _scope_of(briefs)
    rec: Dict[str, Any] = {"phase": phase_id, "mode": ctx["mode"],
                           "pages": {}, "failures": []}
    checkout_brief = briefs["checkout"][1]
    form_info: Optional[dict] = None

    if ctx["mode"] == MODE_STUB:
        if checkout_brief.get("approved_checkout_url"):
            form_info = {"reuse": (checkout_brief["approved_checkout_url"]
                                   or {}).get("url")}
        else:
            adapter = ctx["adapters"]["checkout"]
            contract = build_checkout_contract(checkout_brief, scope)
            try:
                form_id = adapter.create_form(contract)
                workflow_id = adapter.create_workflow(contract, form_id)
            except Exception as exc:  # noqa: BLE001
                rec["outcome"] = "blocked"
                rec["exit"] = EXIT_BLOCKED
                rec["failures"].append(
                    f"checkout form step failed ({exc!r}) - pages not "
                    "installed, so no page ships the unwired seam form")
                return rec
            snippet = adapter.embed_snippet(form_id)
            html_path = run_dir / CHECKOUT_HTML_REL
            try:
                html = html_path.read_text(encoding="utf-8")
                html_path.write_text(
                    splice_checkout_embed(html, snippet, form_id),
                    encoding="utf-8")
            except (OSError, SpliceError) as exc:
                rec["outcome"] = "blocked"
                rec["exit"] = EXIT_BLOCKED
                rec["failures"].append(
                    f"checkout embed splice failed closed: {exc}")
                return rec
            form_info = {"form_id": form_id, "workflow_id": workflow_id,
                         "contract": contract, "snippet": snippet}

    rc, _receipt = gx.execute_phase(
        run_dir, phase_id,
        page_adapter=ctx["adapters"].get("page")
        if ctx["mode"] == MODE_STUB else None,
        env=ctx["env"])
    rec["installer_exit"] = rc

    form_block = workflow_block = None
    rb_form = rb_workflow = None
    if form_info and form_info.get("form_id"):
        contract = form_info["contract"]
        form_block = {"name": contract["form"]["name"],
                      "form_id": form_info["form_id"]}
        workflow_block = {"name": contract["workflow"]["name"],
                          "workflow_id": form_info["workflow_id"],
                          "draft_only": True}
        try:
            rb = ctx["adapters"]["checkout"].readback(form_info["form_id"])
            rb_form = rb
            wfs = rb.get("workflows") or []
            if wfs:
                rb_workflow = wfs[0]
        except Exception:  # noqa: BLE001
            rb_form = None
    elif form_info and form_info.get("reuse"):
        form_block = {"name": None, "form_id": "reuse:approved-url"}
        workflow_block = {"name": None,
                          "workflow_id": "reuse:approved-url",
                          "draft_only": True}
    data = _extend_phase_receipts(
        run_dir, phase_id, binding, ctx["mods"], form_block=form_block,
        workflow_block=workflow_block, readback_form=rb_form,
        readback_workflow=rb_workflow)

    outcome, exit_code = _outcome_from_installer(run_dir, phase_id, rc,
                                                 ctx["mode"], ctx["mods"])
    rec["outcome"] = outcome
    rec["exit"] = exit_code
    if outcome != "complete" or ctx["mode"] != MODE_STUB:
        if isinstance(data, dict):
            rec["receipt_status"] = data.get("status")
        return rec

    # Stub-mode verification: installer + binding + per-page read-backs +
    # the checkout form step (fields, workflow, consent, embed).
    failures, data = _verify_installer_and_binding(run_dir, phase_id,
                                                   ctx["env"], ctx["mods"])
    remote = data.get("remote") if isinstance(data, dict) else {}
    page_failures, failed_pids = [], []
    if remote:
        page_failures, failed_pids = _verify_pages(
            run_dir, phase_id, data, scope, ctx["adapters"]["page"],
            ctx["mods"])
        failures.extend(page_failures)
    if form_info and form_info.get("form_id"):
        failures.extend(_verify_checkout_step(
            run_dir, checkout_brief, form_info, scope, rec,
            failed_pids, remote, ctx))
    if form_info and form_info.get("reuse"):
        html_path = run_dir / CHECKOUT_HTML_REL
        html = html_path.read_text(encoding="utf-8") \
            if html_path.is_file() else ""
        if form_info["reuse"] not in html:
            failures.append(
                "approved-URL reuse: the shipped checkout page does "
                "not route to the brief's approved checkout URL "
                f"{form_info['reuse']!r}")
            if remote.get("checkout_page_id"):
                failed_pids.append(remote["checkout_page_id"])
    if failures:
        _mark_failed(gx.receipt_paths(run_dir, phase_id), failed_pids,
                     failures, ctx["mods"])
        rec["outcome"] = "failed"
        rec["exit"] = EXIT_VERIFY_FAILED
        rec["failures"].extend(failures)
        for key, pid in sorted((remote or {}).items()):
            if key.endswith("_page_id") and pid:
                rec["pages"][key[: -len("_page_id")]] = {
                    "page_id": pid,
                    "status": "failed" if pid in failed_pids
                    else "complete"}
        return rec
    for key, pid in sorted((remote or {}).items()):
        if key.endswith("_page_id") and pid:
            rec["pages"][key[: -len("_page_id")]] = {
                "page_id": pid, "status": "complete",
                "funnel_id": remote.get("funnel_id")}
    if form_info and form_info.get("form_id"):
        rec["form"] = {"form_id": form_info["form_id"],
                       "workflow_id": form_info["workflow_id"],
                       "consent": "verified all-required (2026-10-13 "
                                  "ruling)",
                       "embed": "verified verbatim in the installed "
                                "checkout page"}
    return rec


def _verify_checkout_step(run_dir: Path, checkout_brief: dict,
                          form_info: dict, scope: dict, rec: dict,
                          failed_pids: List[str], remote: dict,
                          ctx: Dict[str, Any]) -> List[str]:
    """Verify the checkout form step against its read-back: location,
    workflow binding, the brief's fields, the all-required consent
    posture, and the verbatim embed in the shipped checkout page. Any
    failure is charged to the checkout page."""
    failures: List[str] = []
    adapter = ctx["adapters"]["checkout"]
    form_id = form_info["form_id"]
    try:
        rb = adapter.readback(form_id)
    except Exception as exc:  # noqa: BLE001
        return [f"checkout form read-back raised {exc!r}"]
    if rb.get("location_id") != scope["location_id"]:
        failures.append(f"checkout form read-back location "
                        f"{rb.get('location_id')!r} != brief scope "
                        f"{scope['location_id']!r}")
    if form_info["workflow_id"] not in (rb.get("workflow_ids") or []):
        failures.append(f"checkout workflow {form_info['workflow_id']!r} "
                        "is not bound to the form in its read-back")
    brief_fields = _field_keys(
        (checkout_brief.get("form") or {}).get("fields") or [])
    if _field_keys(rb.get("fields") or []) != brief_fields:
        failures.append("checkout form read-back fields differ from the "
                        "brief's form fields")
    failures.extend(verify_consent_readback(
        checkout_brief.get("consent") or {}, rb.get("consent") or {}))
    html_path = run_dir / CHECKOUT_HTML_REL
    html = html_path.read_text(encoding="utf-8") \
        if html_path.is_file() else ""
    if form_info["snippet"] not in html:
        failures.append("checkout embed snippet is not present verbatim "
                        "in the shipped checkout page")
    if CHECKOUT_FORM_MARKER in html:
        failures.append("the native SKILL44_WIDGET seam form is still "
                        "in the shipped checkout page")
    if failures and remote.get("checkout_page_id"):
        failed_pids.append(remote["checkout_page_id"])
    return failures


def _consume_gate(run_dir: Path, ctx: Dict[str, Any]) -> dict:
    gx = ctx["mods"]["ghl_external_installer"]
    phase_id = PHASE_GATE
    briefs = ctx["briefs_by_phase"][phase_id]
    binding = _binding_for(briefs)
    scope = _scope_of(briefs)
    rec: Dict[str, Any] = {"phase": phase_id, "mode": ctx["mode"],
                           "pages": {}, "failures": []}
    vsl_brief = briefs["vsl"][1]
    gate = (vsl_brief.get("vsl") or {}).get("gate") or {}
    form_info: Optional[dict] = None

    if ctx["mode"] == MODE_STUB:
        plan = gx.build_gate_form_plan(scope=scope,
                                       fields=gate.get("form_fields"))
        if plan["form"]["name"] != gate.get("form_name") or \
                plan["workflow"]["name"] != gate.get("workflow_name"):
            rec["outcome"] = "blocked"
            rec["exit"] = EXIT_BLOCKED
            rec["failures"].append(
                "the installer's gate plan names "
                f"{plan['form']['name']!r}/{plan['workflow']['name']!r} "
                f"but the brief names {gate.get('form_name')!r}/"
                f"{gate.get('workflow_name')!r} - refusing to install a "
                "differently-named gate form")
            return rec
        adapter = ctx["adapters"]["gate"]
        try:
            form_id = adapter.create_form(
                {"scope": plan["scope"], "form": plan["form"]})
            workflow_id = adapter.create_workflow(
                {"scope": plan["scope"], "workflow": plan["workflow"]},
                form_id)
        except Exception as exc:  # noqa: BLE001
            rec["outcome"] = "blocked"
            rec["exit"] = EXIT_BLOCKED
            rec["failures"].append(f"gate form step failed ({exc!r})")
            return rec
        # Seed the durable ops ledger exactly where the installer's own
        # executor records created ids, so execute_phase RESUMES (read
        # back + receipts) instead of creating duplicates.
        execution_id = gx._new_execution_id()
        gx.record_ops(run_dir, phase_id, {
            "status": gx.STATUS_REMOTE_CREATED,
            "execution_id": execution_id,
            "remote": {"form_id": form_id, "workflow_id": workflow_id},
            "next_action": "brief_consumer created the gate form + "
                           "workflow from the brief; execute_phase "
                           "resumes for read-back + receipts"})
        snippet = adapter.embed_snippet(form_id)
        form_info = {"form_id": form_id, "workflow_id": workflow_id,
                     "snippet": snippet}
        ctx["gate_form"] = form_info
        html_path = run_dir / VSL_HTML_REL
        try:
            html = html_path.read_text(encoding="utf-8")
            html_path.write_text(
                splice_vsl_gate_embed(html, snippet, form_id,
                                      scope["deck_slug"]),
                encoding="utf-8")
        except (OSError, SpliceError) as exc:
            # The form + workflow are real and still receipted below; the
            # VSL PAGE phase is what must not proceed (it would ship the
            # capture-nothing native form).
            ctx["vsl_embed_error"] = str(exc)
            rec["failures"].append(
                f"vsl gate embed splice failed closed: {exc} (the VSL "
                "page phase is blocked; the gate form + workflow still "
                "install and receipt)")

    rc, _receipt = gx.execute_phase(
        run_dir, phase_id,
        gate_adapter=ctx["adapters"].get("gate")
        if ctx["mode"] == MODE_STUB else None,
        env=ctx["env"])
    rec["installer_exit"] = rc
    _extend_phase_receipts(run_dir, phase_id, binding, ctx["mods"])
    outcome, exit_code = _outcome_from_installer(run_dir, phase_id, rc,
                                                 ctx["mode"], ctx["mods"])
    rec["outcome"] = outcome
    rec["exit"] = exit_code
    if outcome != "complete" or ctx["mode"] != MODE_STUB:
        return rec

    failures, _data = _verify_installer_and_binding(
        run_dir, phase_id, ctx["env"], ctx["mods"])
    adapter = ctx["adapters"]["gate"]
    form_id = (form_info or {}).get("form_id")
    workflow_id = (form_info or {}).get("workflow_id")
    try:
        rb_form = adapter.readback_form(form_id)
        rb_wf = adapter.readback_workflow(workflow_id)
        if rb_form.get("location_id") != scope["location_id"]:
            failures.append("gate form read-back location "
                            f"{rb_form.get('location_id')!r} != brief "
                            f"scope {scope['location_id']!r}")
        if workflow_id not in (rb_form.get("workflow_ids") or []):
            failures.append("gate workflow is not bound to the gate "
                            "form in its read-back")
        brief_keys = _field_keys(gate.get("form_fields") or [])
        rb_fields = rb_form.get("fields") or []
        if _field_keys(rb_fields) != brief_keys:
            failures.append("gate form read-back fields differ from the "
                            "brief's gate fields")
        for f in rb_fields:
            if isinstance(f, dict) and f.get("required") is not True:
                failures.append(f"gate form field "
                                f"{f.get('field_key')!r} read back not "
                                "required - the gate contract requires "
                                "every field")
        if rb_wf.get("form_id") != form_id:
            failures.append("gate workflow read-back is not bound to "
                            f"the gate form {form_id!r}")
        if rb_wf.get("location_id") != scope["location_id"]:
            failures.append("gate workflow read-back location mismatch")
        if rb_wf.get("draft") is not True:
            failures.append("gate workflow read back not DRAFT - the "
                            "gate contract is draft-only")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"gate read-back raised {exc!r}")
    if failures:
        _mark_failed(gx.receipt_paths(run_dir, phase_id), [], failures,
                     ctx["mods"])
        rec["outcome"] = "failed"
        rec["exit"] = EXIT_VERIFY_FAILED
        rec["failures"].extend(failures)
        return rec
    rec["form"] = {"form_id": form_id, "workflow_id": workflow_id,
                   "embed": "spliced verbatim into the VSL page "
                            "(verified at the VSL phase)"}
    return rec


def _consume_vsl(run_dir: Path, ctx: Dict[str, Any]) -> dict:
    gx = ctx["mods"]["ghl_external_installer"]
    phase_id = PHASE_VSL
    briefs = ctx["briefs_by_phase"][phase_id]
    binding = _binding_for(briefs)
    scope = _scope_of(briefs)
    rec: Dict[str, Any] = {"phase": phase_id, "mode": ctx["mode"],
                           "pages": {}, "failures": []}

    if ctx.get("vsl_embed_error"):
        rec["outcome"] = "blocked"
        rec["exit"] = EXIT_BLOCKED
        rec["failures"].append(
            "the gate embed did not land in the VSL page "
            f"({ctx['vsl_embed_error']}) - the page is not installed "
            "with a capture-nothing gate form")
        return rec
    if ctx["mode"] == MODE_STUB and ctx.get("sales_in_scope"):
        if gx.shared_funnel_id(run_dir) is None:
            rec["outcome"] = "blocked"
            rec["exit"] = EXIT_BLOCKED
            rec["failures"].append(
                "a sales install is in scope for this run but its "
                "receipt does not verify - refusing to let the VSL "
                "install create a second funnel for one client "
                "(one-funnel rule)")
            return rec

    rc, _receipt = gx.execute_phase(
        run_dir, phase_id,
        page_adapter=ctx["adapters"].get("page")
        if ctx["mode"] == MODE_STUB else None,
        env=ctx["env"])
    rec["installer_exit"] = rc
    data = _extend_phase_receipts(run_dir, phase_id, binding, ctx["mods"])
    outcome, exit_code = _outcome_from_installer(run_dir, phase_id, rc,
                                                 ctx["mode"], ctx["mods"])
    rec["outcome"] = outcome
    rec["exit"] = exit_code
    if outcome != "complete" or ctx["mode"] != MODE_STUB:
        if isinstance(data, dict):
            rec["receipt_status"] = data.get("status")
        return rec

    failures, data = _verify_installer_and_binding(run_dir, phase_id,
                                                   ctx["env"], ctx["mods"])
    remote = data.get("remote") if isinstance(data, dict) else {}
    page_failures, failed_pids = [], []
    if remote:
        page_failures, failed_pids = _verify_pages(
            run_dir, phase_id, data, scope, ctx["adapters"]["page"],
            ctx["mods"])
        failures.extend(page_failures)
    # The shipped VSL page must carry the gate embed, never the native
    # capture-nothing form.
    html_path = run_dir / VSL_HTML_REL
    html = html_path.read_text(encoding="utf-8") \
        if html_path.is_file() else ""
    embed_failures = []
    if VSL_FORM_MARKER in html:
        embed_failures.append("vsl_builder's native gate form is still "
                              "in the shipped VSL page (capture-nothing)")
    snippet = (ctx.get("gate_form") or {}).get("snippet")
    if snippet is not None:
        if snippet not in html:
            embed_failures.append("the gate form embed is not present "
                                  "verbatim in the shipped VSL page")
    elif "zhc-skill44-embed" not in html:
        embed_failures.append("no Skill 44 gate embed marker in the "
                              "shipped VSL page")
    if embed_failures:
        failures.extend(embed_failures)
        if remote.get("vsl_page_id"):
            failed_pids.append(remote["vsl_page_id"])
    if failures:
        _mark_failed(gx.receipt_paths(run_dir, phase_id), failed_pids,
                     failures, ctx["mods"])
        rec["outcome"] = "failed"
        rec["exit"] = EXIT_VERIFY_FAILED
        rec["failures"].extend(failures)
        for key, pid in sorted((remote or {}).items()):
            if key.endswith("_page_id") and pid:
                rec["pages"][key[: -len("_page_id")]] = {
                    "page_id": pid,
                    "status": "failed" if pid in failed_pids
                    else "complete"}
        return rec
    for key, pid in sorted((remote or {}).items()):
        if key.endswith("_page_id") and pid:
            rec["pages"][key[: -len("_page_id")]] = {
                "page_id": pid, "status": "complete",
                "funnel_id": remote.get("funnel_id")}
    return rec


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
_RUNNERS = {PHASE_SALES: _consume_sales, PHASE_GATE: _consume_gate,
            PHASE_VSL: _consume_vsl}

_EXIT_PRIORITY = {EXIT_GATE_BLOCKED: 4, EXIT_VERIFY_FAILED: 3,
                  EXIT_BLOCKED: 2, EXIT_BUILD_FAILED: 1, EXIT_OK: 0}


def consume(run_dir: Path, *, mode: str = MODE_STUB,
            env: Optional[dict] = None,
            phases: Optional[List[str]] = None,
            adapters: Optional[Dict[str, Any]] = None
            ) -> Tuple[int, Dict[str, dict]]:
    """Consume a run's emitted page briefs: plan, execute (stub or
    delegated), return brief-bound receipts, verify. Returns (exit_code,
    {phase_id: outcome record})."""
    run_dir = Path(run_dir).resolve()
    if mode not in MODES:
        raise ConsumerError(f"mode {mode!r} not in {MODES}")
    mods = _load_siblings()
    _require(mods, "page_brief", "ghl_external_installer",
             "checkout_form_builder")
    gx, pb = mods["ghl_external_installer"], mods["page_brief"]
    intake = _read_json(run_dir / gx.INTAKE_REL)
    wanted = [p for p in PHASE_ORDER if phases is None or p in phases]

    results: Dict[str, dict] = {}
    briefs_by_phase: Dict[str, Dict[str, Tuple[Path, dict]]] = {}
    runnable: List[str] = []
    for phase_id in wanted:
        briefs, problems = _phase_briefs(run_dir, phase_id, mods)
        pages_needed = len(pb.PHASE_TO_PAGES[phase_id])
        if len(briefs) == pages_needed and not problems:
            scope_errs = _check_scopes(run_dir, phase_id, briefs, intake,
                                       env, mods)
            if scope_errs:
                rec = {"phase": phase_id, "mode": mode, "pages": {},
                       "outcome": "blocked", "exit": EXIT_BLOCKED,
                       "failures": scope_errs}
            else:
                briefs_by_phase[phase_id] = briefs
                runnable.append(phase_id)
                continue
        elif not briefs and len(problems) == pages_needed and \
                all(p.startswith("no emitted brief") for p in problems):
            rec = {"phase": phase_id, "mode": mode, "pages": {},
                   "outcome": "no_brief", "exit": EXIT_OK,
                   "failures": [],
                   "detail": "no emitted briefs for this phase's pages "
                             "- nothing to consume (not a failure)"}
        else:
            rec = {"phase": phase_id, "mode": mode, "pages": {},
                   "outcome": "blocked", "exit": EXIT_BLOCKED,
                   "failures": problems}
        results[phase_id] = rec
        _record_consumer_phase(run_dir, phase_id, rec, mode)

    if not runnable:
        worst = EXIT_OK
        for rec in results.values():
            if _EXIT_PRIORITY[rec["exit"]] > _EXIT_PRIORITY[worst]:
                worst = rec["exit"]
        if all(rec["outcome"] == "no_brief" for rec in results.values()):
            worst = EXIT_BLOCKED
            print("brief_consumer: no emitted briefs for any phase - "
                  "nothing to consume (run page_brief.py --emit first)",
                  file=sys.stderr)
        return worst, results

    # Stub adapters bind the run's own scope location (never another
    # client's): the installer's resolved scope for THIS run.
    run_scope, _blk = gx.resolve_scope(run_dir, intake, env=env)
    location = (run_scope or {}).get("location_id") or "unbound-test"
    if mode == MODE_STUB:
        ad: Dict[str, Any] = dict(adapters or {})
        ad.setdefault("page", StubSkill06PageAdapter(location, run_dir))
        ad.setdefault("gate", StubSkill44GateAdapter(location))
        ad.setdefault("checkout", StubSkill44CheckoutAdapter(location))
    else:
        ad = {}
    ctx: Dict[str, Any] = {
        "mods": mods, "mode": mode, "env": env,
        "briefs_by_phase": briefs_by_phase, "adapters": ad,
        "sales_in_scope": PHASE_SALES in briefs_by_phase or
        (run_dir / gx.RECEIPT_REL[PHASE_SALES]).is_file(),
    }
    _consumer_plan(run_dir, mode, intake, env, mods, briefs_by_phase)
    for phase_id in PHASE_ORDER:
        if phase_id not in runnable:
            continue
        rec = _RUNNERS[phase_id](run_dir, ctx)
        results[phase_id] = rec
        _record_consumer_phase(run_dir, phase_id, rec, mode)

    worst = EXIT_OK
    for rec in results.values():
        code = rec.get("exit", EXIT_OK)
        if _EXIT_PRIORITY[code] > _EXIT_PRIORITY[worst]:
            worst = code
    return worst, results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Consume a run's page-brief.json files (FIX-PLAN "
                    "Item 21): produce the install plan per page through "
                    "ghl_external_installer's canonical Skill 06/44 "
                    "entry points, execute it (stub or delegated), "
                    "deliver the Skill 44 form embeds, and return "
                    "brief-bound, read-back-verified receipts.")
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("--mode", choices=list(MODES), default=MODE_STUB,
                    help="stub: full path against in-memory Skill 06/44 "
                         "stand-ins (no live GHL session); delegated: "
                         "plans + pending receipts for the Item 22 "
                         "staffed session")
    ap.add_argument("--phase", action="append", choices=list(PHASE_ORDER),
                    default=None, help="restrict to one phase (repeatable)")
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
    try:
        code, results = consume(run_dir, mode=args.mode,
                                phases=args.phase)
    except ConsumerError as exc:
        print(f"brief_consumer: BLOCKED: {exc}", file=sys.stderr)
        return EXIT_BLOCKED
    for phase_id in PHASE_ORDER:
        rec = results.get(phase_id)
        if rec is None:
            continue
        line = f"{phase_id}: {rec['outcome']}"
        if rec.get("failures"):
            line += f" - {rec['failures'][:2]}"
        print(line)
    return code


# ---------------------------------------------------------------------------
# Offline deterministic self-test (fixture briefs in, stub install,
# receipts out, binding verified; tamper / failed read-back / superseded
# cases). No network, no kie.ai spend, no GHL call.
# ---------------------------------------------------------------------------
def _fixture_run(base: Path) -> Path:
    """A run folder in B30's fixture shape (intake + copy + media ledger
    + timing + video), with briefs emitted by page_brief itself and page
    HTML built by the REAL builders' own HTML functions - so the fixture
    carries the exact SKILL44_WIDGET seam form and native VSL gate form
    the shipped builders produce."""
    mods = _load_siblings()
    pb, scb, vb = mods["page_brief"], mods["sales_checkout_builder"], \
        mods["vsl_builder"]
    run = base / "run-acme"
    for rel in ("working/copy", "working/sales-checkout/copy",
                "working/sales-checkout/html", "working/vsl/copy",
                "working/vsl/html", "working/upsell/copy",
                "working/checkpoints", "working/delivery"):
        (run / rel).mkdir(parents=True, exist_ok=True)
    intake = {
        "deck_slug": "acme-brief",
        "company": "Acme Co",
        "GHL_LOCATION_ID": "loc-test-1",
        "pre_presentation_capture": {"WANT_SALES_CHECKOUT": "yes",
                                     "WANT_VSL_PAGE": "yes"},
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
    (run / "working" / "copy" / "intake.json").write_text(
        json.dumps(intake, indent=2), encoding="utf-8")
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
                "ghl_url": "https://storage.googleapis.com/msgsndr/"
                           "loc-test-1/acme.mp4",
                "deck_slug": "acme-brief"},
            "logo_main": {
                "ghl_url": "https://assets.cdn.filesafe.space/"
                           "loc-test-1/logo.png"},
        }), encoding="utf-8")
    (run / "working/checkpoints/webinar_timing.json").write_text(
        json.dumps({"total_audio_sec": 1200.0, "timing": [
            {"slide": 1, "audio_start": 0.0},
            {"slide": 5, "audio_start": 300.0},
            {"slide": 9, "audio_start": 700.0}]}), encoding="utf-8")
    (run / "working" / "delivery" / "acme-brief-WEBINAR.mp4").write_bytes(
        b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp42"
        b"\x00\x00\x00\x08free")
    code, _res = pb.emit(run, profile=None, env={})
    if code != pb.EXIT_OK:
        raise RuntimeError(f"fixture brief emission failed: {_res}")
    brand = scb.resolve_brand(run, intake)
    brief = intake["deck_brief"]
    client, slug = intake["company"], intake["deck_slug"]
    sales_fields = scb._content_fields_for_page("sales", brief, client)
    checkout_fields = scb._content_fields_for_page("checkout", brief,
                                                   client)
    sales_html = scb.build_page_html(
        page_role="sales", brand=brand, client_name=client,
        fields=dict(sales_fields, proof=brief["PROOF_ASSETS"]),
        hero_image_src=None, marker=f"ZHC-SC-{slug}", deck_slug=slug)
    checkout_html = scb.build_page_html(
        page_role="checkout", brand=brand, client_name=client,
        fields=dict(checkout_fields,
                    order_line="Momentum Method - $997",
                    reassurance="Secure checkout."),
        hero_image_src=None, marker=f"ZHC-SC-{slug}", deck_slug=slug)
    (run / CHECKOUT_HTML_REL).parent.mkdir(parents=True, exist_ok=True)
    (run / "working/sales-checkout/html/sales.html").write_text(
        sales_html, encoding="utf-8")
    (run / CHECKOUT_HTML_REL).write_text(checkout_html, encoding="utf-8")
    vsl_html = vb.build_vsl_html(
        brand=brand, client_name=client,
        fields=vb._vsl_content_fields(brief, client), hero_image_src=None,
        video_src="https://storage.googleapis.com/msgsndr/loc-test-1/"
                  "acme.mp4",
        video_hosted=True, gate_seconds=300.0, deck_slug=slug,
        marker=f"ZHC-VSL-{slug}")
    (run / VSL_HTML_REL).write_text(vsl_html, encoding="utf-8")
    return run


def _sanitize_env() -> Dict[str, Optional[str]]:
    """shared_funnel_id reads the process env (the installer's own
    default); keep the self-test deterministic on any box."""
    import os
    saved = {}
    for key in ("GOHIGHLEVEL_LOCATION_ID", "GHL_LOCATION_ID"):
        saved[key] = os.environ.pop(key, None)
    return saved


def _restore_env(saved: Dict[str, Optional[str]]) -> None:
    import os
    for key, val in saved.items():
        if val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = val


def _selftest() -> int:
    import tempfile

    mods = _load_siblings()
    try:
        _require(mods, "page_brief", "ghl_external_installer",
                 "checkout_form_builder", "sales_checkout_builder",
                 "vsl_builder")
    except ConsumerError as exc:
        print(f"page_brief_consumer selftest -> FAIL ({exc})")
        return 1
    pb, gx = mods["page_brief"], mods["ghl_external_installer"]
    fails: List[str] = []
    saved = _sanitize_env()
    try:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)

            # 0) Splice discipline: no native form -> fail closed.
            for fn, args in (
                    (splice_checkout_embed, ("<div>no form</div>", "S",
                                             "form_mem_0001")),
                    (splice_vsl_gate_embed, ("<div>no form</div>", "S",
                                             "form_mem_0001", "acme"))):
                try:
                    fn(*args)
                    fails.append(f"{fn.__name__} ACCEPTED html with no "
                                 "native form to replace")
                except SpliceError:
                    pass

            # 1) End-to-end stub run: fixture briefs in, plan executed
            #    against the stub installer, receipts out, binding
            #    verified by Item 20's own verifier.
            run = _fixture_run(base / "a")
            code, results = consume(run, mode=MODE_STUB, env={})
            if code != EXIT_OK:
                fails.append(f"e2e stub consume exit {code} != 0: "
                             f"{results}")
            for phase_id in PHASE_ORDER:
                rec = results.get(phase_id) or {}
                if rec.get("outcome") != "complete":
                    fails.append(f"e2e: {phase_id} outcome "
                                 f"{rec.get('outcome')} != complete: "
                                 f"{rec.get('failures')}")
            vcode, vres = pb.verify_receipts(run, env={})
            if vcode != pb.EXIT_OK:
                fails.append(f"e2e: page_brief.verify_receipts exit "
                             f"{vcode}: {vres}")
            for phase_id in PHASE_ORDER:
                if vres.get(phase_id, {}).get("status") != "complete":
                    fails.append(f"e2e: verifier judges {phase_id} "
                                 f"{vres.get(phase_id)}")
            sales_rec = gx.load_receipt(run, PHASE_SALES)
            remote = sales_rec.get("remote") or {}
            form = sales_rec.get("form") or {}
            if not str(form.get("form_id") or "").startswith("form_mem_"):
                fails.append(f"e2e: sales receipt carries no stub "
                             f"checkout form id: {form}")
            urls = sales_rec.get("urls") or {}
            if set(urls) != {remote.get("sales_page_id"),
                             remote.get("checkout_page_id")}:
                fails.append(f"e2e: sales receipt urls wrong: {urls}")
            rb_form = (sales_rec.get("readback") or {}).get("form") or {}
            boxes = (rb_form.get("consent") or {}).get("boxes") or []
            if not boxes or not all(b.get("required") is True
                                    for b in boxes):
                fails.append("e2e: checkout consent read-back in the "
                             "receipt is not all-required")
            vsl_rec = gx.load_receipt(run, PHASE_VSL)
            if (vsl_rec.get("remote") or {}).get("funnel_id") != \
                    remote.get("funnel_id"):
                fails.append("e2e: VSL did not reuse the sales funnel "
                             "(one-funnel rule)")
            checkout_html = (run / CHECKOUT_HTML_REL).read_text(
                encoding="utf-8")
            snippet = stub_embed_snippet(form["form_id"],
                                         form.get("name") or
                                         "ZHC acme-brief Checkout")
            if snippet not in checkout_html:
                fails.append("e2e: checkout embed not in the shipped "
                             "checkout page")
            if CHECKOUT_FORM_MARKER in checkout_html:
                fails.append("e2e: native seam form still in the "
                             "shipped checkout page")
            vsl_html = (run / VSL_HTML_REL).read_text(encoding="utf-8")
            if VSL_FORM_MARKER in vsl_html:
                fails.append("e2e: native gate form still in the "
                             "shipped VSL page")
            if "zhc-skill44-embed" not in vsl_html or \
                    'id="zhc-vsl-gate-acme-brief"' not in vsl_html:
                fails.append("e2e: gate embed / overlay missing from "
                             "the shipped VSL page")
            for p in gx.receipt_paths(run, PHASE_GATE):
                gate_rec = _read_json(p)
                if not (gate_rec.get("brief_binding") or {}).get("briefs"):
                    fails.append(f"e2e: gate receipt {p.name} carries "
                                 "no brief_binding")

            # 2) A tampered brief hash fails the binding.
            run2 = _fixture_run(base / "b")
            code, _r = consume(run2, mode=MODE_STUB, env={})
            if code != EXIT_OK:
                fails.append(f"tamper setup: consume exit {code}")
            vsl_path, _vsl = pb.latest_brief(run2, "vsl")
            vsl_path.write_text(vsl_path.read_text(encoding="utf-8")
                                + "\n", encoding="utf-8")
            errs = pb.check_brief_binding(
                run2, PHASE_VSL, gx.load_receipt(run2, PHASE_VSL))
            if not errs:
                fails.append("tamper: binding check ACCEPTED a brief "
                             "whose file hash changed after install")
            vcode, vres = pb.verify_receipts(run2, env={})
            if vcode == pb.EXIT_OK:
                fails.append("tamper: verify_receipts judged a tampered "
                             f"binding complete: {vres}")

            # 3) A failed read-back marks the page failed.
            class _DraftLyingPageAdapter(StubSkill06PageAdapter):
                def __init__(self, *a, **kw):
                    super().__init__(*a, **kw)
                    self._checkout_pid = None

                def install_page(self, funnel_id, page):
                    pid = super().install_page(funnel_id, page)
                    if page.get("key") == "checkout":
                        self._checkout_pid = pid
                    return pid

                def readback_page(self, page_id):
                    rb = super().readback_page(page_id)
                    if page_id == self._checkout_pid:
                        rb["draft"] = False
                    return rb

            run3 = _fixture_run(base / "c")
            code, results3 = consume(
                run3, mode=MODE_STUB, env={},
                adapters={"page": _DraftLyingPageAdapter("loc-test-1",
                                                         run3)})
            if code != EXIT_VERIFY_FAILED:
                fails.append(f"readback: consume exit {code} != 4: "
                             f"{results3}")
            if results3[PHASE_SALES].get("outcome") != "failed":
                fails.append(f"readback: sales outcome "
                             f"{results3[PHASE_SALES].get('outcome')} "
                             "!= failed")
            rec3 = gx.load_receipt(run3, PHASE_SALES)
            if rec3.get("status") in gx.STATUSES_COMPLETE:
                fails.append("readback: failed page's receipt still "
                             "reads complete")
            rb3 = rec3.get("readback") or {}
            co_pid = (rec3.get("remote") or {}).get("checkout_page_id")
            if rb3.get("ok") is not False or \
                    (rb3.get("pages") or {}).get(co_pid, {}).get("ok") \
                    is not False:
                fails.append("readback: checkout page not marked failed "
                             f"in the receipt read-back: {rb3}")
            if results3[PHASE_VSL].get("outcome") != "blocked":
                fails.append("readback: VSL phase must block on the "
                             "unverifiable sales funnel (one-funnel "
                             f"rule), got "
                             f"{results3[PHASE_VSL].get('outcome')}")
            vcode, _vres = pb.verify_receipts(run3, env={})
            if vcode == pb.EXIT_OK:
                fails.append("readback: verifier judged the failed "
                             "install complete")

            # 4) A superseded brief's receipt judges stale.
            run4 = _fixture_run(base / "d")
            code, _r = consume(run4, mode=MODE_STUB, env={})
            if code != EXIT_OK:
                fails.append(f"supersede setup: consume exit {code}")
            (run4 / "working/sales-checkout/copy/sales.md").write_text(
                "# Sales copy v2\nChanged copy.\n", encoding="utf-8")
            code, _r = pb.emit(run4, profile=None, env={})
            if code != pb.EXIT_OK:
                fails.append(f"supersede setup: re-emit exit {code}")
            vcode, vres = pb.verify_receipts(run4, env={})
            if vcode != pb.EXIT_VERIFY_FAILED:
                fails.append(f"supersede: verify exit {vcode} != 4")
            binding_errs = vres.get(PHASE_SALES, {}).get(
                "binding_errors") or []
            if not any("version" in e for e in binding_errs):
                fails.append(f"supersede: binding errors do not name "
                             f"the stale version: {binding_errs}")

            # 5) Delegated mode: plans + pending receipts, binding
            #    carried, pages untouched (no splice without a session).
            run5 = _fixture_run(base / "e")
            code, results5 = consume(run5, mode=MODE_DELEGATED, env={})
            if code != EXIT_OK:
                fails.append(f"delegated: consume exit {code}: "
                             f"{results5}")
            for phase_id in PHASE_ORDER:
                rec = results5.get(phase_id) or {}
                if rec.get("outcome") != "pending_external_execution":
                    fails.append(f"delegated: {phase_id} outcome "
                                 f"{rec.get('outcome')} != pending")
                data = gx.load_receipt(run5, phase_id)
                if data.get("status") != gx.STATUS_PENDING:
                    fails.append(f"delegated: {phase_id} receipt not "
                                 f"pending: {data.get('status')}")
                if pb.check_brief_binding(run5, phase_id, data):
                    fails.append(f"delegated: {phase_id} pending receipt "
                                 "fails the brief binding")
            if CHECKOUT_FORM_MARKER not in (run5 / CHECKOUT_HTML_REL) \
                    .read_text(encoding="utf-8"):
                fails.append("delegated: checkout page was modified "
                             "without a session (splice belongs to "
                             "execution)")
            if not (run5 / CONSUMER_PLAN_REL).is_file() or \
                    not (run5 / "working/sales-checkout/"
                         "ghl_install_plan.json").is_file() or \
                    not (run5 / "working/vsl/"
                         "gate_form_skill44_plan.json").is_file():
                fails.append("delegated: plan artifacts missing")
    finally:
        _restore_env(saved)

    if fails:
        print("page_brief_consumer selftest -> FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("page_brief_consumer selftest -> PASS (splice fail-closed; "
          "end-to-end stub run: briefs in, plans via the installer's "
          "canonical builders, stub execution, brief-bound receipts, "
          "Item 20 verifier judges all three phases complete, one "
          "funnel shared, checkout embed + all-required consent "
          "read-back in the receipt, VSL gate embed shipped with the "
          "native form removed; tampered brief hash fails the binding; "
          "failed read-back marks the checkout page failed and blocks "
          "the VSL phase on the one-funnel rule; superseded brief "
          "judges stale; delegated mode emits plans + pending "
          "brief-bound receipts and touches no page)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
