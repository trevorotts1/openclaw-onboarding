"""
shared-utils/design/composition.py — design composition for the GHL delivery
stream (W9A): Skill 71 native-component slots, HTML/CSS fragment composition,
and approved Vercel embed composition with framing/sizing/navigation checks.

One writer for this file: assignment W9A. Contract: GHL-DELIVERY-SPEC.md
"Folders/pages/design (W5, W9, W7)", "Commerce (W8)", "Forms/surveys (W6)"
and "Delivery contract (W1)". Normative rules this file exists to enforce:

    * no universal full-document import assumption — a fragment is the default
      unit; a full document is imported only where the target surface says it
      supports it, or through one explicit, recorded conversion;
    * scoped CSS and design tokens — every visible color in style rules comes
      from a brand token (var(--brand-*)); a raw color in a rule is a defect;
    * explicit native-component slots — pages carry declared slots for the
      native GHL components (form, survey, checkout/order form, order bump,
      upsell/downsell offer, confirmation, navigation). Native reality, no
      counterfeit controls: a native-only slot is never filled with HTML;
    * approved Vercel embeds only, with framing permissions, sizing and
      navigation checked before placement (parent CSS never styles a foreign
      iframe interior);
    * a composition plan is not an installation — placement counts only with
      an installer readback (set AND read back, never assume).

Public surface:

    DesignTokens            declared brand tokens (--brand-ink/surface/
                            surface-alt/accent/dark); values come from the
                            run's brand file, never invented here
    HtmlFragment            one approved HTML/CSS fragment with treatments
    ResponsiveSpec          desktop-first breakpoints (1440/768/390)
    NativeSlot              explicit native-component slot declaration
    SlotBook                slot fills with readback; PLANNED -> FILLED ->
                            VERIFIED are distinct
    EmbedSpec / EmbedApproval / VerifiedEmbed
                            approved Vercel embed; verify_embed() runs the
                            framing/sizing/navigation/approval checks
    ComposedPage / compose_page / validate_composition
    SurfaceCapabilities     what a builder surface really supports
    render_install_plan     ordered ops for the builder surface; refuses
                            unsupported ops (never silently drops)
    install_composition     plan -> installation, only via an installer with
                            readback; CompositionLedger makes it idempotent
    write_plan / load_plan  JSON round-trip, schema-version pinned

Integration seams (explicit, outstanding — see unit evidence):
    * SurfaceCapabilities + CompositionInstaller are the page-mutation seams.
      The real surface/installer comes from the W5 page primitive writer
      (shared-utils/ghl/primitives.py) and the W7 delivery surfaces. Until
      then only RecordingInstaller runs here; nothing in this file touches a
      browser, a network, or GHL.
    * Native component creation and configuration are W6A/W6B (forms,
      surveys) and W8A/W8B/W8D (checkout, bumps, upsells, products/prices).
      This file places slots and consumes their real native ids with readback;
      it never creates a native component and never fakes one.
    * ComposedPage and InstallPlan are shapes to persist; durable checkpoints
      are W4 (shared-utils/delivery/checkpoints.py).
    * W9B (role wrappers) consumes this composition layer through
      compose_page + render_install_plan.

Import pattern (from any script in the repo):

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    # shared-utils has no package dot-path; load by path or run this file
    # directly. The self-check is the usage example.

Run the assert-based self-check:

    python3 -I shared-utils/design/composition.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol, Tuple
from urllib.parse import urlparse

SCHEMA_VERSION = "ghl-design-composition/1"

# Brand design tokens (Skill 71 composition-treatments vocabulary). Values are
# supplied by the run's brand file at install time; this module only ever
# checks references and scopes.
TOKEN_NAMES = ("--brand-ink", "--brand-surface", "--brand-surface-alt",
               "--brand-accent", "--brand-dark")

# Native-component kinds a GHL page can carry (spec outcome: navigation,
# native forms/surveys, native checkout/order forms, order bumps,
# upsells/downsells, confirmation). counterfeit_forbidden: the component must
# be the real native object — an HTML imitation is a defect ("native reality,
# no counterfeit controls").
NATIVE_COMPONENT_KINDS = {
    "navigation": {"counterfeit_forbidden": True, "html_styling_around": True},
    "form": {"counterfeit_forbidden": True, "html_styling_around": True},
    "survey": {"counterfeit_forbidden": True, "html_styling_around": True},
    "checkout": {"counterfeit_forbidden": True, "html_styling_around": True},
    "order_bump": {"counterfeit_forbidden": True, "html_styling_around": True},
    "upsell_offer": {"counterfeit_forbidden": True, "html_styling_around": True},
    "downsell_offer": {"counterfeit_forbidden": True, "html_styling_around": True},
    "confirmation": {"counterfeit_forbidden": True, "html_styling_around": True},
}

# Explicit slot requirements per Skill 71 page role (the seven
# signature_launch roles). An empty tuple is an explicit "no native slot".
ROLE_SLOT_REQUIREMENTS = {
    "landing": (("form", False),),          # required only for opt_in kind
    "product_selection": (),
    "checkout": (("checkout", True), ("order_bump", False)),
    "upsell_1": (("upsell_offer", True),),
    "downsell_1": (("downsell_offer", True),),
    "upsell_2": (("upsell_offer", True),),
    "thank_you": (("confirmation", True),),
}

# Slot lifecycle: distinct on purpose (delivery contract: PLANNED ->
# CREATED -> CONFIGURED -> PUBLISHED -> VERIFIED are distinct states).
SLOT_STATES = ("PLANNED", "FILLED", "VERIFIED")

# Embed framing permissions known to the platform. An unknown feature is
# refused — never invent permissions.
FRAME_FEATURES = ("camera", "microphone", "geolocation", "fullscreen", "autoplay",
                  "clipboard-write", "clipboard-read", "encrypted-media",
                  "picture-in-picture", "display-capture", "accelerometer",
                  "gyroscope", "magnetometer", "payment", "web-share")

NAVIGATION_MODES = ("same-tab", "new-tab", "none")

# Sizing bounds for embeds (checked, explicit — never unbounded).
EMBED_MIN_HEIGHT, EMBED_MAX_HEIGHT = 120, 4096
EMBED_MIN_WIDTH, EMBED_MAX_WIDTH = 200, 3840

# Render breakpoints for responsive layout (Skill 71 renders 1440/768/390).
DEFAULT_BREAKPOINTS = (1440, 768, 390)

_COLOR_PROPERTIES = ("color", "background", "background-color", "border-color",
                     "border-top-color", "border-right-color", "border-bottom-color",
                     "border-left-color", "outline-color", "fill", "stroke",
                     "box-shadow", "text-shadow", "caret-color", "accent-color")


class CompositionError(ValueError):
    """Fail-closed rejection: a composition or plan that cannot be trusted."""


# ----------------------------------------------------------------- records


@dataclass(frozen=True)
class DesignTokens:
    """Declared brand tokens. Values come from the run's brand file."""

    values: Tuple[Tuple[str, str], ...] = ()

    def names(self) -> Tuple[str, ...]:
        return tuple(n for n, _ in self.values)

    def declared(self, name: str) -> bool:
        return name in self.names()


@dataclass(frozen=True)
class HtmlFragment:
    """One approved HTML/CSS fragment with its composition treatments."""

    fragment_id: str
    html: str
    css: str = ""
    treatments: Tuple[str, ...] = ()   # data-treatment ids (composition-treatments)
    source_revision: str = ""          # approved content revision


@dataclass(frozen=True)
class ResponsiveSpec:
    """Desktop-first layout with intentional mobile reflow, never shrink-only."""

    desktop: int = 1440
    breakpoints: Tuple[int, ...] = DEFAULT_BREAKPOINTS


@dataclass(frozen=True)
class NativeSlot:
    """Explicit native-component slot in the composed page."""

    slot_id: str
    kind: str                      # one of NATIVE_COMPONENT_KINDS
    required: bool = True
    role: str = ""                 # owning Skill 71 page role, when role-bound
    anchor: str = ""               # placement hint, e.g. "body:end"


@dataclass(frozen=True)
class SlotFill:
    """A slot fill with readback. Requested state is never blind-assumed."""

    slot_id: str
    native_component_id: str
    readback: str = ""             # observed native component id / placement proof

    def readback_matches(self) -> bool:
        return bool(self.readback) and self.readback == self.native_component_id


@dataclass(frozen=True)
class EmbedApproval:
    """Owner approval of one Vercel deployment for page embedding."""

    approved_by: str
    deployment_url: str            # the approved deployment (host must match)
    revision: str = ""             # approved content revision/deploy id
    approved_domains: Tuple[str, ...] = ()   # extra approved custom domains


@dataclass(frozen=True)
class EmbedSpec:
    """A Vercel embed candidate. Unchecked specs never reach a page."""

    embed_id: str
    url: str
    kind: str = "iframe"           # "iframe" | "link" | "html" | "script"
    body: str = ""                 # anchor/html/script body for non-iframe kinds
    frame_allow: Tuple[str, ...] = ()   # framing permissions; empty = none granted
    sandbox: str = ""              # explicit sandbox policy for iframes
    width: Optional[int] = None
    height: Optional[int] = None
    max_width: Optional[int] = None
    aspect_ratio: Optional[float] = None   # e.g. 1.777 for 16:9 responsive
    navigation: str = "same-tab"   # same-tab | new-tab | none
    approval: Optional[EmbedApproval] = None


@dataclass(frozen=True)
class VerifiedEmbed:
    """An embed whose framing/sizing/navigation/approval checks all passed."""

    spec: EmbedSpec
    checks: Tuple[str, ...]        # names of the checks that passed


@dataclass(frozen=True)
class ComposedPage:
    """One page's design composition: fragments, embeds, slots, tokens."""

    page_logical_id: str           # W1 stable logical id — required
    scope_id: str                  # CSS scope token for this page
    fragments: Tuple[HtmlFragment, ...] = ()
    embeds: Tuple[VerifiedEmbed, ...] = ()    # verified only
    slots: Tuple[NativeSlot, ...] = ()
    tokens: DesignTokens = DesignTokens()
    responsive: ResponsiveSpec = ResponsiveSpec()
    document_policy: str = "fragment-only"    # or "strip-to-fragment"
    role: str = ""
    composition_id: str = ""       # filled by compose_page (content hash)


# ------------------------------------------------------------------ helpers


def _require(cond: bool, errors: list, msg: str) -> None:
    if not cond:
        errors.append(msg)


def looks_like_full_document(html: str) -> bool:
    """A full document is not a fragment; import support is never assumed."""
    return bool(re.search(r"<!doctype\s+html|<html[\s>]|<head[\s>]|<body[\s>]",
                          html, re.I))


def strip_to_fragment(html: str) -> str:
    """Explicit conversion: keep the body interior only.

    Refuses documents whose body cannot be located — conversion is recorded,
    never guessed.
    """
    m = re.search(r"<body[^>]*>(.*)</body>", html, re.I | re.S)
    if not m:
        raise CompositionError("full document has no locatable <body>; "
                               "cannot convert to fragment")
    return m.group(1).strip()


# --------------------------------------------------------------- css checks

_HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_COLOR_FN_RE = re.compile(r"\b(?:rgb|rgba|hsl|hsla)\s*\(", re.I)
_NAMED_RE = re.compile(
    r"(?<![-\w])(?:black|white|red|green|blue|gray|grey|orange|yellow|purple|"
    r"pink|brown|silver|gold|teal|navy|maroon|olive|lime|aqua|cyan|magenta|"
    r"violet|beige|ivory|coral|salmon|tan|snow|azure|khaki|crimson|indigo|"
    r"plum|orchid|turquoise)(?![-\w])", re.I)
_DECL_RE = re.compile(r"([a-zA-Z][-a-zA-Z0-9]*)\s*:\s*([^;{}]+)")
_VAR_RE = re.compile(r"var\(\s*(--[\w-]+)\s*\)")
_URL_RE = re.compile(r"url\([^)]*\)")

_ALLOWED_COLOR_WORDS = ("transparent", "currentcolor", "inherit", "initial",
                        "unset", "none")


def _strip_noise(value: str) -> str:
    """Remove var() references and url() payloads before color scanning."""
    v = _VAR_RE.sub(" ", value)
    v = _URL_RE.sub(" ", v)
    return v


def scan_css_colors(css: str, tokens: DesignTokens) -> list:
    """Every visible color in a style RULE must be a brand token reference.

    Custom-property definitions (--*) carry the brand-file values themselves
    and are exempt; ordinary properties are not. Raw hex, color functions or
    named colors in a rule are defects (composition-treatments token rule).
    """
    errors: list = []
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    for prop, value in _DECL_RE.findall(css):
        if prop.startswith("--"):
            continue
        if prop not in _COLOR_PROPERTIES:
            continue
        probe = _strip_noise(value)
        for what, rx in (("hex", _HEX_RE), ("color function", _COLOR_FN_RE),
                         ("named color", _NAMED_RE)):
            if rx.search(probe):
                errors.append(f"raw {what} in '{prop}' rule; use a brand token "
                              f"(var(--brand-*)): {value.strip()!r}")
        for name in _VAR_RE.findall(value):
            if not tokens.declared(name):
                errors.append(f"undeclared design token {name} in '{prop}'")
    return errors


def check_scope(css: str, scope_id: str) -> list:
    """Styles are scoped to the page; global and foreign-interior selectors fail.

    Parent CSS cannot style protected/foreign iframe interiors: a selector
    reaching inside an <iframe> is refused.
    """
    errors: list = []
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    css = re.sub(r"@media[^{]*\{", "{", css)   # flatten media preludes
    scope_token = f"scope-{scope_id}"
    for m in re.finditer(r"([^{}]+)\{[^{}]*\}", css):
        selector = m.group(1).strip()
        if not selector or selector.startswith("@"):
            continue
        for sel in (s.strip() for s in selector.split(",")):
            if not sel:
                continue
            if re.search(r"(^|[\s>+~])(html|body|:root|\*)(?![\w-])", sel):
                errors.append(f"global selector escapes page scope: {sel!r}")
            if re.search(r"iframe[\s>+~]", sel, re.I):
                errors.append(f"selector styles inside a foreign iframe "
                              f"interior: {sel!r}")
            if scope_token not in sel:
                errors.append(f"selector not scoped to {scope_token}: {sel!r}")
    return errors


def check_responsive(css: str, spec: ResponsiveSpec) -> list:
    """Desktop-first with intentional reflow: every non-desktop breakpoint
    needs an explicit media rule. Shrink-only pages are defects."""
    errors: list = []
    preludes = [p for p in re.findall(r"@media([^{]+)", css)]
    blob = " ".join(preludes)
    for bp in spec.breakpoints:
        if bp == spec.desktop:
            continue
        if not re.search(rf"\b{bp}\s*px", blob):
            errors.append(f"no explicit reflow rule for breakpoint {bp}px "
                          "(intentional mobile reflow, never shrink-only)")
    return errors


# -------------------------------------------------------------- embed checks


def check_embed(e: EmbedSpec) -> list:
    """Framing, sizing, navigation and approval — all checked, fail-closed."""
    errors: list = []
    u = urlparse(e.url)
    _require(u.scheme == "https", errors, "embed url must be https")
    _require(bool(u.netloc), errors, "embed url needs a host")
    host = (u.netloc or "").lower().split(":")[0]

    _require(e.kind in ("iframe", "link", "html", "script"), errors,
             "embed.kind must be iframe/link/html/script")
    _require(e.navigation in NAVIGATION_MODES, errors,
             f"embed.navigation must be one of {NAVIGATION_MODES}")

    # approval: an approved Vercel deployment only
    if e.approval is None:
        errors.append("embed has no approval; only approved Vercel embeds compose")
    else:
        _require(bool(e.approval.approved_by), errors, "approval.approved_by required")
        _require(bool(e.approval.revision), errors,
                 "approval.revision required (approved content pinned)")
        app_host = (urlparse(e.approval.deployment_url).netloc or "").lower().split(":")[0]
        approved_domains = tuple(d.lower() for d in e.approval.approved_domains)
        host_approved = (host == app_host) or (host in approved_domains)
        _require(host_approved, errors,
                 f"embed host {host!r} is not the approved deployment "
                 f"{app_host!r} or an approved domain")
        _require(host.endswith(".vercel.app") or host in approved_domains, errors,
                 f"embed host {host!r} is not a Vercel deployment or approved domain")

    # framing permissions: explicit, known features only
    if e.kind == "iframe":
        _require(bool(e.frame_allow), errors,
                 "iframe embed must declare frame_allow (framing permissions explicit)")
        for feat in e.frame_allow:
            name = feat.split("(", 1)[0].strip()
            _require(name in FRAME_FEATURES, errors,
                     f"unknown framing permission {name!r}; never invent permissions")
        _require(bool(e.sandbox), errors, "iframe embed must declare an explicit sandbox")

    # sizing: bounded and explicit; responsive needs a width and height strategy
    responsive = e.max_width is not None or e.aspect_ratio is not None
    if responsive:
        _require(e.max_width is not None and e.max_width > 0, errors,
                 "responsive embed needs an explicit max_width")
        _require(e.height is not None or e.aspect_ratio is not None, errors,
                 "responsive embed needs a height or aspect_ratio strategy")
    else:
        _require(e.width is not None and e.width > 0, errors,
                 "fixed embed needs an explicit width")
        _require(e.height is not None and e.height > 0, errors,
                 "fixed embed needs an explicit height")
    if e.height is not None:
        _require(EMBED_MIN_HEIGHT <= e.height <= EMBED_MAX_HEIGHT, errors,
                 f"height {e.height} outside [{EMBED_MIN_HEIGHT}, {EMBED_MAX_HEIGHT}]")
    if e.width is not None:
        _require(EMBED_MIN_WIDTH <= e.width <= EMBED_MAX_WIDTH, errors,
                 f"width {e.width} outside [{EMBED_MIN_WIDTH}, {EMBED_MAX_WIDTH}]")
    if e.aspect_ratio is not None:
        _require(e.aspect_ratio > 0, errors, "aspect_ratio must be positive")

    # navigation: never smuggle top-level navigation; new-tab carries noopener
    if e.navigation == "none":
        _require('target="_blank"' not in e.body and "<a " not in e.body.lower(),
                 errors, "navigation=none but body carries a navigable link")
    if e.navigation == "new-tab" and 'target="_blank"' in e.body:
        _require("noopener" in e.body, errors,
                 'new-tab embed must carry rel="noopener"')
    if re.search(r'target\s*=\s*"_?(top|parent)"', e.body, re.I):
        errors.append("embed body navigates the top-level window; refused")
    return errors


def verify_embed(e: EmbedSpec) -> VerifiedEmbed:
    """Checked embeds only. Raises CompositionError naming every failure."""
    errors = check_embed(e)
    if errors:
        raise CompositionError("embed " + e.embed_id + " refused: " + "; ".join(errors))
    checks = ("approval", "host", "framing", "sizing", "navigation")
    return VerifiedEmbed(spec=e, checks=checks)


# ----------------------------------------------------------- composed page


def slot_requirements(role: str, page_kind: str = "") -> tuple:
    """Explicit slot requirements for a page role (landing opt_in needs the
    registration form; landing sales routes to checkout instead)."""
    if role not in ROLE_SLOT_REQUIREMENTS:
        raise CompositionError(f"unknown page role {role!r}")
    reqs = []
    for kind, required in ROLE_SLOT_REQUIREMENTS[role]:
        if role == "landing" and kind == "form" and page_kind == "opt_in":
            required = True
        reqs.append((kind, required))
    return tuple(reqs)


def _scope_selector(scope_id: str) -> str:
    return f"scope-{scope_id}"


def validate_composition(page: ComposedPage) -> list:
    """Fail-closed validation of a composed page. Empty list means valid."""
    errors: list = []
    _require(bool(page.page_logical_id), errors,
             "page_logical_id required (no anonymous page)")
    _require(bool(page.scope_id), errors, "scope_id required (scoped CSS)")
    _require(page.document_policy in ("fragment-only", "strip-to-fragment"), errors,
             "document_policy must be fragment-only or strip-to-fragment")
    if page.role:
        _require(page.role in ROLE_SLOT_REQUIREMENTS, errors,
                 f"unknown page role {page.role!r}")

    seen_frag = set()
    for f in page.fragments:
        _require(bool(f.fragment_id), errors, "fragment_id required")
        _require(f.fragment_id not in seen_frag, errors,
                 f"duplicate fragment_id {f.fragment_id!r}")
        seen_frag.add(f.fragment_id)
        _require(bool(f.html.strip()), errors,
                 f"fragment {f.fragment_id} has no html")
        if looks_like_full_document(f.html):
            if page.document_policy == "fragment-only":
                errors.append(f"fragment {f.fragment_id} is a full document; "
                              "full-document import is not assumed "
                              "(set document_policy to strip-to-fragment or "
                              "target a surface with document import)")
        errors.extend(scan_css_colors(f.css, page.tokens))
        errors.extend(check_scope(f.css, page.scope_id))

    if page.fragments:
        errors.extend(check_responsive(
            " ".join(f.css for f in page.fragments), page.responsive))

    seen_slots = set()
    slot_kinds = {}
    for s in page.slots:
        _require(bool(s.slot_id), errors, "slot_id required")
        _require(s.slot_id not in seen_slots, errors,
                 f"duplicate slot_id {s.slot_id!r}")
        seen_slots.add(s.slot_id)
        _require(s.kind in NATIVE_COMPONENT_KINDS, errors,
                 f"slot {s.slot_id}: unknown native-component kind {s.kind!r}")
        slot_kinds[s.slot_id] = s.kind

    for v in page.embeds:
        errors.extend([f"embed {v.spec.embed_id}: {e}"
                       for e in check_embed(v.spec)])

    # role-bound explicit slots: every required kind present exactly once
    if page.role:
        for kind, required in slot_requirements(page.role):
            count = sum(1 for k in slot_kinds.values() if k == kind)
            if required and count != 1:
                errors.append(f"role {page.role} requires exactly one {kind} "
                              f"slot; found {count}")
    return errors


def compose_page(*, page_logical_id: str, scope_id: str,
                 fragments=(), embeds=(), slots=(), tokens=DesignTokens(),
                 responsive=ResponsiveSpec(), document_policy: str = "fragment-only",
                 role: str = "", page_kind: str = "") -> ComposedPage:
    """Build + validate + stamp a composition. Raises CompositionError."""
    page = ComposedPage(
        page_logical_id=page_logical_id, scope_id=scope_id,
        fragments=tuple(fragments), embeds=tuple(embeds), slots=tuple(slots),
        tokens=tokens, responsive=responsive, document_policy=document_policy,
        role=role)
    errors = validate_composition(page)
    if errors:
        raise CompositionError("; ".join(errors))
    cid = compute_composition_id(page)
    return ComposedPage(
        page_logical_id=page.page_logical_id, scope_id=page.scope_id,
        fragments=page.fragments, embeds=page.embeds, slots=page.slots,
        tokens=page.tokens, responsive=page.responsive,
        document_policy=page.document_policy, role=page.role,
        composition_id=cid)


def _composition_dict(page: ComposedPage) -> dict:
    return {
        "page_logical_id": page.page_logical_id,
        "scope_id": page.scope_id,
        "fragments": [{"fragment_id": f.fragment_id, "html": f.html,
                       "css": f.css, "treatments": list(f.treatments),
                       "source_revision": f.source_revision}
                      for f in page.fragments],
        "embeds": [{"embed_id": v.spec.embed_id, "url": v.spec.url,
                    "kind": v.spec.kind, "checks": list(v.checks)}
                   for v in page.embeds],
        "slots": [{"slot_id": s.slot_id, "kind": s.kind, "required": s.required,
                   "role": s.role, "anchor": s.anchor} for s in page.slots],
        "tokens": {"values": [list(v) for v in page.tokens.values]},
        "responsive": {"desktop": page.responsive.desktop,
                       "breakpoints": list(page.responsive.breakpoints)},
        "document_policy": page.document_policy,
        "role": page.role,
    }


def compute_composition_id(page: ComposedPage) -> str:
    """Deterministic content id: same inputs -> same id (idempotent compose)."""
    canon = json.dumps(_composition_dict(page), sort_keys=True,
                       separators=(",", ":"), ensure_ascii=False)
    return "cmp_" + hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------- slot book


class SlotBook:
    """Slot fills with readback. PLANNED -> FILLED -> VERIFIED are distinct."""

    def __init__(self) -> None:
        self._fills: dict = {}

    def fill(self, slot: NativeSlot, native_component_id: str,
             readback: str = "") -> str:
        """Record a fill. Returns the slot state.

        FILLED needs a real native id; VERIFIED needs readback that matches it
        (set AND read back — never blind-assume placement).
        """
        if slot.kind in NATIVE_COMPONENT_KINDS and not native_component_id:
            raise CompositionError(f"slot {slot.slot_id}: empty native id refused")
        if not native_component_id:
            raise CompositionError(f"slot {slot.slot_id}: native_component_id required")
        fill = SlotFill(slot_id=slot.slot_id, native_component_id=native_component_id,
                        readback=readback)
        self._fills[slot.slot_id] = fill
        return "VERIFIED" if fill.readback_matches() else "FILLED"

    def state(self, slot: NativeSlot) -> str:
        fill = self._fills.get(slot.slot_id)
        if fill is None:
            return "PLANNED"
        return "VERIFIED" if fill.readback_matches() else "FILLED"

    def verify(self, page: ComposedPage) -> list:
        """Required slots must be VERIFIED; optional unfilled slots are fine."""
        errors: list = []
        for s in page.slots:
            st = self.state(s)
            if s.required and st != "VERIFIED":
                errors.append(f"slot {s.slot_id} ({s.kind}) is {st}, not VERIFIED")
        return errors


# ------------------------------------------------------------ install plan


@dataclass(frozen=True)
class SurfaceCapabilities:
    """What a builder surface really supports — read/list is not create/edit."""

    surface_id: str
    supports_custom_html: bool = False
    supports_custom_css: bool = False
    supports_iframe_embed: bool = False
    supports_full_document: bool = False
    supports_native_kinds: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanOp:
    """One ordered surface operation."""

    op_id: str
    op_kind: str                   # "fragment" | "embed" | "native-slot" | "document"
    target_id: str
    surface_kind: str              # "custom-code" | "embed-block" | "native-component"
    detail: dict = field(default_factory=dict)


@dataclass(frozen=True)
class InstallPlan:
    """Ordered ops for one page. A plan is not an installation."""

    plan_id: str
    page_logical_id: str
    composition_id: str
    ops: Tuple[PlanOp, ...]
    document_policy: str = "fragment-only"

    def state(self) -> str:
        return "PLANNED"


def render_install_plan(page: ComposedPage, caps: SurfaceCapabilities) -> InstallPlan:
    """Turn a composition into ordered surface ops — or refuse.

    Every fragment, embed and slot becomes exactly one op; an unsupported op
    raises naming the platform restriction. Nothing is silently dropped.
    """
    errors = validate_composition(page)
    if errors:
        raise CompositionError("; ".join(errors))
    ops: list = []
    n = 0

    def op(op_kind: str, target_id: str, surface_kind: str, detail: dict) -> None:
        nonlocal n
        n += 1
        ops.append(PlanOp(op_id=f"op_{n:03d}", op_kind=op_kind,
                          target_id=target_id, surface_kind=surface_kind,
                          detail=detail))

    for f in page.fragments:
        if looks_like_full_document(f.html):
            if page.document_policy == "strip-to-fragment":
                body = strip_to_fragment(f.html)
                op("document", f.fragment_id, "custom-code",
                   {"converted": "strip-to-fragment", "html": body,
                    "css": f.css, "scope": _scope_selector(page.scope_id)})
                continue
            raise CompositionError(
                f"surface {caps.surface_id} cannot import full documents and "
                f"fragment {f.fragment_id} is a full document")
        if not caps.supports_custom_html:
            raise CompositionError(
                f"surface {caps.surface_id} does not support custom HTML; "
                f"fragment {f.fragment_id} cannot be installed")
        if f.css and not caps.supports_custom_css:
            raise CompositionError(
                f"surface {caps.surface_id} does not support custom CSS; "
                f"fragment {f.fragment_id} cannot be installed")
        op("fragment", f.fragment_id, "custom-code",
           {"html": f.html, "css": f.css, "treatments": list(f.treatments),
            "scope": _scope_selector(page.scope_id)})

    for v in page.embeds:
        if not caps.supports_iframe_embed and v.spec.kind == "iframe":
            raise CompositionError(
                f"surface {caps.surface_id} does not support iframe embeds; "
                f"embed {v.spec.embed_id} cannot be installed")
        op("embed", v.spec.embed_id, "embed-block",
           {"url": v.spec.url, "kind": v.spec.kind,
            "frame_allow": list(v.spec.frame_allow), "sandbox": v.spec.sandbox,
            "width": v.spec.width, "height": v.spec.height,
            "max_width": v.spec.max_width, "aspect_ratio": v.spec.aspect_ratio,
            "navigation": v.spec.navigation, "checks": list(v.checks)})

    for s in page.slots:
        if s.kind not in caps.supports_native_kinds:
            raise CompositionError(
                f"surface {caps.surface_id} does not support native {s.kind}; "
                f"slot {s.slot_id} cannot be installed (capability incomplete)")
        op("native-slot", s.slot_id, "native-component",
           {"kind": s.kind, "required": s.required, "anchor": s.anchor})

    expected = len(page.fragments) + len(page.embeds) + len(page.slots)
    if len(ops) != expected:
        raise CompositionError(
            f"plan has {len(ops)} ops for {expected} composition items; "
            "silent drops are refused")
    canon = json.dumps({"page": page.composition_id,
                        "ops": [(o.op_kind, o.target_id, o.surface_kind)
                                for o in ops]},
                       sort_keys=True, separators=(",", ":"))
    plan_id = "pln_" + hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]
    return InstallPlan(plan_id=plan_id, page_logical_id=page.page_logical_id,
                       composition_id=page.composition_id, ops=tuple(ops),
                       document_policy=page.document_policy)


# ------------------------------------------------------------ install seam


@dataclass(frozen=True)
class OpReceipt:
    """Per-op installer readback. Empty readback is not installed."""

    op_id: str
    confirmed: bool
    readback: str = ""


@dataclass(frozen=True)
class InstallReceipt:
    """Outcome of installing one plan. A plan is not an installation."""

    plan_id: str
    page_logical_id: str
    status: str                    # "PLANNED" | "INSTALLED"
    installed: bool
    op_receipts: Tuple[OpReceipt, ...] = ()
    note: str = ""


class CompositionInstaller(Protocol):
    """Integration seam: performs the page mutation and reads back each op."""

    def install_plan(self, plan: InstallPlan, page_logical_id: str) -> Tuple[OpReceipt, ...]: ...


class RecordingInstaller:
    """Deterministic installer double for checks and wiring tests."""

    def __init__(self, confirmed: bool = True, readback: str = "comp_1",
                 blank_ops: tuple = ()) -> None:
        self.confirmed = confirmed
        self.readback = readback
        self.blank_ops = blank_ops
        self.calls: list = []

    def install_plan(self, plan: InstallPlan, page_logical_id: str) -> Tuple[OpReceipt, ...]:
        self.calls.append((plan.plan_id, page_logical_id))
        out = []
        for o in plan.ops:
            rb = "" if o.op_id in self.blank_ops else self.readback
            out.append(OpReceipt(op_id=o.op_id, confirmed=self.confirmed, readback=rb))
        return tuple(out)


class CompositionLedger:
    """Idempotent in-memory installer state (durable checkpoints: W4)."""

    def __init__(self) -> None:
        self._done: dict = {}
        self.installs = 0

    def get(self, plan_id: str, page_logical_id: str) -> Optional[InstallReceipt]:
        return self._done.get((plan_id, page_logical_id))

    def record(self, plan_id: str, page_logical_id: str,
               receipt: InstallReceipt) -> None:
        self._done[(plan_id, page_logical_id)] = receipt
        self.installs += 1


def install_composition(plan: InstallPlan, installer: CompositionInstaller,
                        ledger: Optional[CompositionLedger] = None) -> InstallReceipt:
    """Install a plan through a confirming installer with readback.

    The only function that can move a plan past PLANNED. Refuses: no
    installer; any op unconfirmed or without readback (read back, never
    assume). Re-installing the same plan returns the prior receipt.
    """
    if installer is None:
        raise CompositionError("no installer; a composition plan is not an installation")
    if ledger is not None:
        prior = ledger.get(plan.plan_id, plan.page_logical_id)
        if prior is not None:
            return prior
    receipts = installer.install_plan(plan, plan.page_logical_id)
    by_id = {r.op_id: r for r in receipts}
    problems = []
    for o in plan.ops:
        r = by_id.get(o.op_id)
        if r is None:
            problems.append(f"op {o.op_id} has no receipt")
        elif not r.confirmed:
            problems.append(f"op {o.op_id} unconfirmed")
        elif not r.readback:
            problems.append(f"op {o.op_id} empty readback")
    if problems:
        out = InstallReceipt(
            plan_id=plan.plan_id, page_logical_id=plan.page_logical_id,
            status="PLANNED", installed=False, op_receipts=tuple(receipts),
            note="; ".join(problems) + " (read back, never assume)")
    else:
        out = InstallReceipt(
            plan_id=plan.plan_id, page_logical_id=plan.page_logical_id,
            status="INSTALLED", installed=True, op_receipts=tuple(receipts),
            note="all ops confirmed with readback")
    if ledger is not None and out.installed:
        ledger.record(plan.plan_id, plan.page_logical_id, out)
    return out


# ---------------------------------------------------------- json roundtrip


def write_plan(plan: InstallPlan, path) -> Path:
    """Write the plan JSON. This is a file, not an installation."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "plan_id": plan.plan_id,
        "page_logical_id": plan.page_logical_id,
        "composition_id": plan.composition_id,
        "document_policy": plan.document_policy,
        "ops": [{"op_id": o.op_id, "op_kind": o.op_kind,
                 "target_id": o.target_id, "surface_kind": o.surface_kind,
                 "detail": o.detail} for o in plan.ops],
    }
    p = Path(path)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                 encoding="utf-8")
    return p


def load_plan(path) -> InstallPlan:
    """Load a plan JSON. Unknown schema versions are rejected."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise CompositionError(f"unsupported schema_version: "
                               f"{raw.get('schema_version')!r}")
    try:
        ops = tuple(PlanOp(op_id=o["op_id"], op_kind=o["op_kind"],
                           target_id=o["target_id"],
                           surface_kind=o["surface_kind"],
                           detail=o.get("detail", {}))
                    for o in raw["ops"])
        return InstallPlan(plan_id=raw["plan_id"],
                           page_logical_id=raw["page_logical_id"],
                           composition_id=raw["composition_id"],
                           ops=ops,
                           document_policy=raw.get("document_policy",
                                                   "fragment-only"))
    except (KeyError, TypeError) as exc:
        raise CompositionError(f"malformed plan: {exc}") from exc


# ------------------------------------------------------------- self-check


def _selfcheck() -> int:
    import tempfile

    passed = 0

    def ok(cond: bool, msg: str) -> None:
        nonlocal passed
        assert cond, msg
        passed += 1

    tokens = DesignTokens(values=tuple((n, "brand") for n in TOKEN_NAMES))
    scope = "pg1"
    good_css = (
        ".scope-pg1 .hero { background: var(--brand-surface); "
        "color: var(--brand-ink); } "
        "@media (max-width: 768px) { .scope-pg1 .hero { padding: 2rem; } } "
        "@media (max-width: 390px) { .scope-pg1 .hero { padding: 1rem; } }"
    )
    frag = HtmlFragment(fragment_id="f1", html="<section class='hero'>Hi</section>",
                        css=good_css, treatments=("split",), source_revision="r1")

    # 1 — full-document detection and explicit conversion only
    ok(looks_like_full_document("<!DOCTYPE html><html><body>x</body></html>"),
       "doctype document detected")
    ok(not looks_like_full_document("<section class='hero'>x</section>"),
       "fragment is not a document")
    ok(strip_to_fragment("<html><body><p>in</p></body></html>") == "<p>in</p>",
       "explicit strip-to-fragment keeps body interior")
    try:
        strip_to_fragment("<html><head></head></html>")
        ok(False, "document without body must refuse conversion")
    except CompositionError:
        ok(True, "conversion refuses documents with no locatable body")

    # 2 — token discipline: raw colors in rules are defects
    hex_css = ".scope-pg1 .hero { background: #ff0000; }"
    errs = scan_css_colors(hex_css, tokens)
    ok(any("hex" in e for e in errs), "raw hex color in rule caught")
    named = ".scope-pg1 .hero { color: gold; }"
    ok(any("named color" in e for e in scan_css_colors(named, tokens)),
       "named color in rule caught")
    fn = ".scope-pg1 .hero { background: rgb(1,2,3); }"
    ok(any("color function" in e for e in scan_css_colors(fn, tokens)),
       "color function in rule caught")
    ok(scan_css_colors(good_css, tokens) == [], "token-referenced colors pass")
    ok(scan_css_colors(".scope-pg1 .hero { color: transparent; }", tokens) == [],
       "transparent passes")
    ok(scan_css_colors("--brand-ink: #0b0b0c;", tokens) == [],
       "brand-file token values exempt from the rule scan")
    undeclared = ".scope-pg1 .hero { color: var(--brand-nope); }"
    ok(any("undeclared design token" in e for e in scan_css_colors(undeclared, tokens)),
       "undeclared token reference caught")

    # 3 — scope discipline
    ok(check_scope(good_css, scope) == [], "scoped css passes")
    ok(any("global selector" in e for e in
           check_scope("body { margin: 0; }", scope)),
       "global body selector caught")
    ok(any("foreign iframe" in e for e in
           check_scope(".scope-pg1 iframe .inner { color: red; }", scope)),
       "parent css styling inside a foreign iframe caught")
    ok(any("not scoped" in e for e in
           check_scope(".other .x { color: red; }", scope)),
       "unscoped selector caught")

    # 4 — responsive: intentional reflow per breakpoint
    ok(check_responsive(good_css, ResponsiveSpec()) == [],
       "both reflow breakpoints covered")
    lazy = ".scope-pg1 .hero { width: 100%; }"
    errs = check_responsive(lazy, ResponsiveSpec())
    ok(any("768" in e for e in errs) and any("390" in e for e in errs),
       "shrink-only page caught at each missing breakpoint")

    # 5 — embed checks: approval, framing, sizing, navigation
    app = EmbedApproval(approved_by="owner", deployment_url="https://ok.vercel.app",
                        revision="rev1", approved_domains=("go.client.com",))
    base = dict(embed_id="e1", url="https://ok.vercel.app/page",
                kind="iframe", frame_allow=("fullscreen",), sandbox="allow-scripts",
                height=600, width=800, navigation="same-tab", approval=app)
    ok(check_embed(EmbedSpec(**base)) == [], "approved embed passes all checks")
    ok(check_embed(EmbedSpec(**dict(base, approval=None))),
       "unapproved embed refused")
    ok(any("revision" in e for e in
           check_embed(EmbedSpec(**dict(base, approval=EmbedApproval(
               approved_by="owner", deployment_url="https://ok.vercel.app"))))),
       "approval without pinned revision refused")
    ok(any("not the approved deployment" in e for e in
           check_embed(EmbedSpec(**dict(base, url="https://evil.vercel.app/p")))),
       "host outside the approved deployment refused")
    ok(check_embed(EmbedSpec(**dict(base, url="https://go.client.com/p"))) == [],
       "approved custom domain passes")
    ok(any("https" in e for e in
           check_embed(EmbedSpec(**dict(base, url="http://ok.vercel.app/p")))),
       "non-https embed refused")
    ok(any("frame_allow" in e for e in
           check_embed(EmbedSpec(**dict(base, frame_allow=())))),
       "iframe without framing permissions refused")
    ok(any("sandbox" in e for e in
           check_embed(EmbedSpec(**dict(base, sandbox="")))),
       "iframe without explicit sandbox refused")
    ok(any("unknown framing permission" in e for e in
           check_embed(EmbedSpec(**dict(base, frame_allow=("telepathy",))))),
       "invented framing permission refused")
    ok(any("explicit height" in e for e in
           check_embed(EmbedSpec(**dict(base, width=None, height=None)))),
       "fixed embed without sizing refused")
    ok(any("outside" in e for e in
           check_embed(EmbedSpec(**dict(base, height=99999)))),
       "out-of-bounds embed height refused")
    ok(check_embed(EmbedSpec(**dict(base, width=None, max_width=900,
                                    aspect_ratio=1.777, height=None))) == [],
       "responsive embed with width+height strategy passes")
    ok(any("height or aspect_ratio" in e for e in
           check_embed(EmbedSpec(**dict(base, width=None, height=None,
                                        max_width=900)))),
       "responsive embed without height strategy refused")
    ok(any("noopener" in e for e in
           check_embed(EmbedSpec(**dict(base, navigation="new-tab",
                                        body='<a target="_blank" href="https://ok.vercel.app">x</a>')))),
       "new-tab link without noopener refused")
    ok(any("top-level window" in e for e in
           check_embed(EmbedSpec(**dict(base, body='<a target="_top" href="https://x">x</a>')))),
       "top-level navigation smuggle refused")
    ok(verify_embed(EmbedSpec(**base)).checks ==
       ("approval", "host", "framing", "sizing", "navigation"),
       "verify_embed records the checks that passed")
    try:
        verify_embed(EmbedSpec(**dict(base, approval=None)))
        ok(False, "verify_embed must refuse an unchecked embed")
    except CompositionError:
        ok(True, "verify_embed refuses embeds that fail checks")

    # 6 — explicit native-component slots; native reality, no counterfeits
    ok(set(NATIVE_COMPONENT_KINDS) ==
       {"navigation", "form", "survey", "checkout", "order_bump",
        "upsell_offer", "downsell_offer", "confirmation"},
       "native-component registry complete for the delivery outcome")
    ok(set(ROLE_SLOT_REQUIREMENTS) ==
       {"landing", "product_selection", "checkout", "upsell_1", "downsell_1",
        "upsell_2", "thank_you"}, "all seven signature_launch roles explicit")
    reqs = slot_requirements("landing", page_kind="opt_in")
    ok(("form", True) in reqs, "landing opt_in requires the registration form")
    reqs = slot_requirements("landing", page_kind="sales")
    ok(("form", False) in reqs, "landing sales routes to checkout instead")
    try:
        slot_requirements("nope")
        ok(False, "unknown role must refuse")
    except CompositionError:
        ok(True, "unknown page role refused")

    slot = NativeSlot(slot_id="s-form", kind="form", required=True,
                      role="landing", anchor="body:end")
    page = compose_page(page_logical_id="page-12", scope_id=scope,
                        fragments=[frag], slots=[slot], tokens=tokens,
                        role="landing", page_kind="opt_in")
    ok(page.composition_id.startswith("cmp_") and len(page.composition_id) == 20,
       "composition content-stamped")
    ok(compose_page(page_logical_id="page-12", scope_id=scope,
                    fragments=[frag], slots=[slot], tokens=tokens,
                    role="landing", page_kind="opt_in").composition_id ==
       page.composition_id, "composition id deterministic across composes")

    bad_kind = NativeSlot(slot_id="s-x", kind="buy_button", required=True)
    p2 = ComposedPage(page_logical_id="page-12", scope_id=scope,
                      fragments=(frag,), slots=(bad_kind,))
    ok(any("unknown native-component kind" in e for e in validate_composition(p2)),
       "unknown slot kind caught")
    checkout_slot = NativeSlot(slot_id="s-co", kind="checkout", required=True)
    p3 = ComposedPage(page_logical_id="page-12", scope_id=scope,
                      fragments=(frag,), slots=(checkout_slot,), tokens=tokens,
                      role="checkout")
    ok(validate_composition(p3) == [],
       "checkout role with the optional bump slot absent is valid")
    p4 = ComposedPage(page_logical_id="page-12", scope_id=scope,
                      fragments=(frag,), slots=(), role="checkout")
    ok(any("requires exactly one checkout" in e for e in validate_composition(p4)),
       "role missing its required native slot caught")

    # slot lifecycle: set AND read back
    book = SlotBook()
    ok(book.state(slot) == "PLANNED", "unfilled slot is PLANNED")
    ok(book.fill(slot, "form_9") == "FILLED", "fill without readback stays FILLED")
    ok(book.verify(page) != [], "unverified required slot blocks verification")
    ok(book.fill(slot, "form_9", readback="form_9") == "VERIFIED",
       "readback matching the native id verifies")
    ok(book.verify(page) == [], "all required slots VERIFIED")
    try:
        book.fill(slot, "")
        ok(False, "empty native id must refuse")
    except CompositionError:
        ok(True, "empty native id refused (no counterfeit placeholder)")
    opt_slot = NativeSlot(slot_id="s-bump", kind="order_bump", required=False)
    ok(book.verify(ComposedPage(page_logical_id="p", scope_id=scope,
                                slots=(opt_slot,))) == [],
       "optional unfilled slot tolerated")

    # 7 — full-document refusal + explicit conversion policy
    doc_frag = HtmlFragment(fragment_id="fd",
                            html="<!DOCTYPE html><html><body><p>x</p></body></html>",
                            css=good_css)
    p5 = ComposedPage(page_logical_id="page-12", scope_id=scope,
                      fragments=(doc_frag,))
    ok(any("full document" in e for e in validate_composition(p5)),
       "full document refused under fragment-only policy")
    p6 = ComposedPage(page_logical_id="page-12", scope_id=scope,
                      fragments=(doc_frag,), tokens=tokens,
                      document_policy="strip-to-fragment")
    ok(validate_composition(p6) == [], "explicit conversion policy admits document")

    # 8 — install plan: surface restrictions named, nothing dropped
    caps = SurfaceCapabilities(surface_id="ghl-custom-code",
                               supports_custom_html=True, supports_custom_css=True,
                               supports_iframe_embed=True,
                               supports_native_kinds=tuple(NATIVE_COMPONENT_KINDS))
    vembed = verify_embed(EmbedSpec(**base))
    full = compose_page(page_logical_id="page-12", scope_id=scope,
                        fragments=[frag], embeds=[vembed], slots=[slot],
                        tokens=tokens, role="landing", page_kind="opt_in")
    plan = render_install_plan(full, caps)
    ok(len(plan.ops) == 3, "one op per fragment, embed and slot — nothing dropped")
    ok(plan.state() == "PLANNED", "a plan is not an installation")
    ok({o.op_kind for o in plan.ops} == {"fragment", "embed", "native-slot"},
       "op kinds cover every composition item")
    bare = SurfaceCapabilities(surface_id="text-only")
    try:
        render_install_plan(full, bare)
        ok(False, "surface without custom html must refuse")
    except CompositionError as exc:
        ok("does not support custom HTML" in str(exc),
           "platform restriction named, not silently dropped")
    noframe = SurfaceCapabilities(surface_id="html-no-frames",
                                  supports_custom_html=True, supports_custom_css=True,
                                  supports_native_kinds=tuple(NATIVE_COMPONENT_KINDS))
    try:
        render_install_plan(full, noframe)
        ok(False, "surface without iframe support must refuse")
    except CompositionError as exc:
        ok("does not support iframe embeds" in str(exc),
           "iframe restriction named")
    nonative = SurfaceCapabilities(surface_id="no-native",
                                   supports_custom_html=True, supports_custom_css=True,
                                   supports_iframe_embed=True)
    try:
        render_install_plan(full, nonative)
        ok(False, "surface without native form support must refuse")
    except CompositionError as exc:
        ok("capability incomplete" in str(exc),
           "missing native capability reported as incomplete")
    plan6 = render_install_plan(p6, caps)
    ok(len(plan6.ops) == 1 and plan6.ops[0].op_kind == "document"
       and plan6.ops[0].detail["converted"] == "strip-to-fragment",
       "document conversion recorded explicitly in the plan")

    # 9 — install seam: readback required; idempotent
    try:
        install_composition(plan, None)  # type: ignore[arg-type]
        ok(False, "no installer must refuse")
    except CompositionError:
        ok(True, "no installer -> refused; a plan is not an installation")
    ledger = CompositionLedger()
    r = install_composition(plan, RecordingInstaller(), ledger)
    ok(r.installed and r.status == "INSTALLED", "confirmed ops with readback install")
    ok(all(op.readback == "comp_1" for op in r.op_receipts),
       "receipts carry real readbacks")
    r2 = install_composition(plan, RecordingInstaller(), ledger)
    ok(r2 == r and ledger.installs == 1,
       "second install returns the prior receipt; never installs twice")
    blank = RecordingInstaller(blank_ops=("op_002",))
    r3 = install_composition(plan, blank)
    ok(not r3.installed and r3.status == "PLANNED",
       "empty readback -> not installed (read back, never assume)")
    ok("op_002" in r3.note, "failure note names the failing op")
    r4 = install_composition(plan, RecordingInstaller(confirmed=False))
    ok(not r4.installed and r4.status == "PLANNED", "unconfirmed install -> not installed")

    # 10 — schema pinning + artifact
    with tempfile.TemporaryDirectory() as tmp:
        p = write_plan(plan, Path(tmp) / "plan.json")
        plan2 = load_plan(p)
        ok(plan2.plan_id == plan.plan_id and len(plan2.ops) == len(plan.ops),
           "write/load round-trip preserves plan identity")
        raw = json.loads(p.read_text(encoding="utf-8"))
        raw["schema_version"] = "ghl-design-composition/999"
        p.write_text(json.dumps(raw), encoding="utf-8")
        try:
            load_plan(p)
            ok(False, "unknown schema version must raise")
        except CompositionError:
            ok(True, "unknown schema_version rejected")
        ok(p.stat().st_size > 0, "plan JSON artifact written")

    print(f"OK {passed} PASS kinds={len(NATIVE_COMPONENT_KINDS)} "
          f"roles={len(ROLE_SLOT_REQUIREMENTS)}")
    return 0


if __name__ == "__main__":
    sys.exit(_selfcheck())
