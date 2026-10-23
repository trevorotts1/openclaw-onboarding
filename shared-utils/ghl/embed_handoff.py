"""
shared-utils/ghl/embed_handoff.py — form/survey embed handoff and
receiving-page binding for the GHL delivery stream (W6C).

One writer for this file: assignment W6C. Contract: GHL-DELIVERY-SPEC.md
"Forms/surveys (W6)" + "Delivery contract (W1)". Normative rule this file
exists to enforce:

    handoff JSON alone is not insertion.

A handoff is a versioned record of ONE native form/survey embed destined for
ONE receiving page. Producing the JSON moves nothing into a page. The only
path to "inserted" is CONSUME -> INSTALL through an installer seam whose
readback is verified (spec gap 2: set AND read back, never blind-toggle;
spec gap 3: never act on an ambiguous page identity).

Public surface:

    EmbedHandoff            immutable handoff record (native ids, embed
                            payload, link, destinations, field-state
                            readback, follow-up workflow refs)
    write_handoff / load_handoff
                            JSON round-trip, fail-closed validation
    validate_handoff        -> [error strings]; empty list means valid
    resolve_page            candidates -> PageRef or None (ambiguity -> None)
    bind_receiving_page     handoff + page + installer -> BindingReceipt
    BindingLedger           idempotent binder; a consumed handoff is never
                            installed twice
    RecordingInstaller      deterministic installer double for checks and
                            for wiring tests against a real installer

Integration seams (explicit, outstanding — see unit evidence):
    * PageInstaller.install() is the page-mutation seam. The real installer
      is supplied by the W5 page primitive writer / W7 delivery surfaces
      (and W3B iframe safeguards for framed embeds). Until then only
      RecordingInstaller runs here; nothing in this file touches a browser,
      a network, or GHL.
    * BindingLedger is in-memory. Durable checkpoints are W4
      (shared-utils/delivery/checkpoints.py); this ledger is the shape to
      persist, not the persistence.
    * Native form/survey creation and field configuration are W6A/W6B.
      This file consumes their outputs (NativeAssetRef + FieldState) and
      refuses unverified field states at the binding boundary.

Import pattern (from any script in the repo):

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from shared-utils...  # directory name has no package dot-path; load by
    # path or run this file directly. The self-check is the usage example.

Run the assert-based self-check:

    python3 -I shared-utils/ghl/embed_handoff.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol, Tuple

SCHEMA_VERSION = "ghl-embed-handoff/1"

ASSET_KINDS = ("form", "survey")
EMBED_KINDS = ("script", "html", "iframe", "link")
DESTINATION_KINDS = ("page", "url", "workflow", "none")

# Handoff lifecycle. Distinct on purpose (delivery contract: PLANNED ->
# CREATED -> CONFIGURED -> PUBLISHED -> VERIFIED are distinct states).
# CREATED = JSON produced. CONSUMED = binder picked it up. INSTALLED =
# installer confirmed placement with readback. BOUND = receiving-page
# binding recorded with verified destinations. VERIFIED = post-binding
# readback of the installed native component id.
HANDOFF_STATES = ("CREATED", "CONSUMED", "INSTALLED", "BOUND", "VERIFIED")


class HandoffError(ValueError):
    """Fail-closed rejection: a handoff or binding that cannot be trusted."""


# ---------------------------------------------------------------- records


@dataclass(frozen=True)
class NativeAssetRef:
    """A real native GHL form/survey (W6A/W6B output), by native id."""

    kind: str                      # "form" | "survey"
    location_id: str
    native_id: str                 # actual form_id / survey_id
    name: str = ""
    revision: str = ""


@dataclass(frozen=True)
class EmbedPayload:
    """The embed to install: script/html fragment/iframe src, or a link."""

    kind: str                      # one of EMBED_KINDS
    body: str                      # script src URL, html fragment, iframe src, link URL
    frame_allow: Tuple[str, ...] = ()   # framing permissions; empty = none granted
    height: Optional[int] = None
    width: Optional[int] = None
    navigation: str = "same-tab"   # "same-tab" | "new-tab" | "none"


@dataclass(frozen=True)
class Destination:
    """Submission or confirmation destination, as an explicit identity."""

    kind: str                      # "page" | "url" | "workflow" | "none"
    logical_id: str = ""           # W1 stable logical id when kind is page/workflow
    native_id: str = ""            # actual page/workflow id when known
    url: str = ""                  # actual URL when kind is url


@dataclass(frozen=True)
class FieldState:
    """Requested vs observed state for one field — never blind-toggled."""

    field_id: str
    required_requested: Optional[bool] = None
    required_observed: Optional[bool] = None
    hidden_requested: Optional[bool] = None
    hidden_observed: Optional[bool] = None

    def readback_complete(self) -> bool:
        if self.required_requested is not None and self.required_observed is None:
            return False
        if self.hidden_requested is not None and self.hidden_observed is None:
            return False
        return True


@dataclass(frozen=True)
class PageRef:
    """Identity of the receiving page. Ambiguity is rejected upstream."""

    logical_id: str                # W1 stable logical id — required
    kind: str = "funnel-page"      # "funnel-page" | "website-page"
    native_id: str = ""            # actual page id once allocated
    location_id: str = ""


@dataclass(frozen=True)
class EmbedHandoff:
    """One form/survey embed, for one receiving page. JSON is not insertion."""

    asset: NativeAssetRef
    embed: EmbedPayload
    receiving_page_logical_id: str
    submission_destination: Destination
    confirmation_destination: Destination
    link: str = ""                 # shareable link for the native asset
    placement: str = ""            # slot/position hint, e.g. "body:end"
    field_states: Tuple[FieldState, ...] = ()
    follow_up_workflow_refs: Tuple[str, ...] = ()   # record-only; never sent here
    revision: str = "1"
    handoff_id: str = ""           # filled by make_handoff (content hash)

    def state(self) -> str:
        """Lifecycle state of THIS record alone: it is only ever CREATED.

        A record cannot observe its own consumption or installation. Use
        BindingReceipt.status for post-consume states.
        """
        return "CREATED"

    def is_inserted(self) -> bool:
        """Always False for a record. Handoff JSON alone is not insertion."""
        return False


@dataclass(frozen=True)
class InstallReceipt:
    """Installer readback. Empty readback is treated as not installed."""

    confirmed: bool
    readback: str = ""             # installed native component id / placement proof
    native_component_id: str = ""
    note: str = ""


class PageInstaller(Protocol):
    """Integration seam: performs the actual page mutation and reads back."""

    def install(self, handoff: EmbedHandoff, page: PageRef) -> InstallReceipt: ...


@dataclass(frozen=True)
class BindingReceipt:
    """Outcome of consuming a handoff against one receiving page."""

    handoff_id: str
    page_logical_id: str
    status: str                    # one of HANDOFF_STATES (beyond CREATED)
    inserted: bool
    install_readback: str
    native_component_id: str
    submission_destination: Destination
    confirmation_destination: Destination
    send_policy: str = "record-only"
    live_sends: int = 0
    note: str = ""


# ------------------------------------------------------------- validation


def _require(cond: bool, errors: list, msg: str) -> None:
    if not cond:
        errors.append(msg)


def validate_handoff(h: EmbedHandoff) -> list:
    """Fail-closed validation. Empty list means the handoff is valid."""
    errors: list = []
    _require(h.asset.kind in ASSET_KINDS, errors, f"asset.kind must be one of {ASSET_KINDS}")
    _require(bool(h.asset.location_id), errors, "asset.location_id required (real native identity)")
    _require(bool(h.asset.native_id), errors, "asset.native_id required (real native id)")
    _require(h.embed.kind in EMBED_KINDS, errors, f"embed.kind must be one of {EMBED_KINDS}")
    _require(bool(h.embed.body), errors, "embed.body required")
    _require(h.embed.navigation in ("same-tab", "new-tab", "none"), errors,
             "embed.navigation must be same-tab/new-tab/none")
    if h.embed.kind == "iframe" and not h.embed.frame_allow:
        errors.append("iframe embed must declare frame_allow (framing permissions explicit)")
    _require(bool(h.receiving_page_logical_id), errors,
             "receiving_page_logical_id required (no anonymous receiving page)")
    for label, d in (("submission_destination", h.submission_destination),
                     ("confirmation_destination", h.confirmation_destination)):
        _require(d.kind in DESTINATION_KINDS, errors, f"{label}.kind must be one of {DESTINATION_KINDS}")
        if d.kind in ("page", "workflow"):
            _require(bool(d.logical_id or d.native_id), errors,
                     f"{label} of kind {d.kind} needs logical_id or native_id")
        if d.kind == "url":
            _require(bool(d.url), errors, f"{label} of kind url needs url")
    for fs in h.field_states:
        _require(bool(fs.field_id), errors, "field_states entries need field_id")
    return errors


def _canonical(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _record_dict(h: EmbedHandoff) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "asset": {"kind": h.asset.kind, "location_id": h.asset.location_id,
                  "native_id": h.asset.native_id, "name": h.asset.name,
                  "revision": h.asset.revision},
        "embed": {"kind": h.embed.kind, "body": h.embed.body,
                  "frame_allow": list(h.embed.frame_allow), "height": h.embed.height,
                  "width": h.embed.width, "navigation": h.embed.navigation},
        "receiving_page_logical_id": h.receiving_page_logical_id,
        "submission_destination": vars(h.submission_destination),
        "confirmation_destination": vars(h.confirmation_destination),
        "link": h.link,
        "placement": h.placement,
        "field_states": [vars(fs) for fs in h.field_states],
        "follow_up_workflow_refs": list(h.follow_up_workflow_refs),
        "revision": h.revision,
    }


def compute_handoff_id(h: EmbedHandoff) -> str:
    """Deterministic content id: same inputs -> same id (idempotent create)."""
    return "hnd_" + hashlib.sha256(_canonical(_record_dict(h)).encode("utf-8")).hexdigest()[:16]


def make_handoff(**kwargs) -> EmbedHandoff:
    """Build + validate + stamp a handoff. Raises HandoffError on invalid."""
    h = EmbedHandoff(**kwargs)
    errors = validate_handoff(h)
    if errors:
        raise HandoffError("; ".join(errors))
    object.__setattr__(h, "handoff_id", compute_handoff_id(h))
    return h


# ---------------------------------------------------------- json roundtrip


def write_handoff(h: EmbedHandoff, path) -> Path:
    """Write the handoff JSON. This is a file, not an insertion."""
    errors = validate_handoff(h)
    if errors:
        raise HandoffError("; ".join(errors))
    p = Path(path)
    payload = dict(_record_dict(h))
    payload["handoff_id"] = h.handoff_id or compute_handoff_id(h)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return p


def load_handoff(path) -> EmbedHandoff:
    """Load + validate a handoff JSON. Unknown schema versions are rejected."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise HandoffError(f"unsupported schema_version: {raw.get('schema_version')!r}")
    try:
        h = EmbedHandoff(
            asset=NativeAssetRef(**raw["asset"]),
            embed=EmbedPayload(
                kind=raw["embed"]["kind"], body=raw["embed"]["body"],
                frame_allow=tuple(raw["embed"].get("frame_allow", ())),
                height=raw["embed"].get("height"), width=raw["embed"].get("width"),
                navigation=raw["embed"].get("navigation", "same-tab"),
            ),
            receiving_page_logical_id=raw["receiving_page_logical_id"],
            submission_destination=Destination(**raw["submission_destination"]),
            confirmation_destination=Destination(**raw["confirmation_destination"]),
            link=raw.get("link", ""),
            placement=raw.get("placement", ""),
            field_states=tuple(FieldState(**fs) for fs in raw.get("field_states", ())),
            follow_up_workflow_refs=tuple(raw.get("follow_up_workflow_refs", ())),
            revision=raw.get("revision", "1"),
            handoff_id=raw.get("handoff_id", ""),
        )
    except (KeyError, TypeError) as exc:
        raise HandoffError(f"malformed handoff: {exc}") from exc
    errors = validate_handoff(h)
    if errors:
        raise HandoffError("; ".join(errors))
    if not h.handoff_id:
        object.__setattr__(h, "handoff_id", compute_handoff_id(h))
    return h


# ------------------------------------------------------ receiving-page bind


def resolve_page(candidates) -> Optional[PageRef]:
    """Exactly one candidate wins. Zero or several -> None (spec gap 3)."""
    uniq = []
    seen = set()
    for c in candidates:
        key = (c.logical_id, c.native_id, c.kind)
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    if len(uniq) != 1:
        return None
    return uniq[0]


def bind_receiving_page(handoff: EmbedHandoff, page: PageRef,
                        installer: PageInstaller, ledger: Optional["BindingLedger"] = None,
                        post_bind_readback: str = "") -> BindingReceipt:
    """Consume a handoff and install it into the receiving page.

    The only function that can move a handoff past CREATED. Refuses:
      * invalid handoff or unverified field-state readback (never blind-toggle)
      * page without a logical id, or page not matching the handoff target
      * no installer, or an installer whose readback is unconfirmed/empty
      * a second install of the same handoff (when a ledger is passed)
    Never sends client communications: follow-up workflow refs are carried
    record-only and this module performs no sends (live_sends stays 0).
    """
    errors = validate_handoff(handoff)
    if errors:
        raise HandoffError("; ".join(errors))
    for fs in handoff.field_states:
        if not fs.readback_complete():
            raise HandoffError(f"field {fs.field_id}: requested state not read back; "
                               "set AND observe before binding")
    if not page.logical_id:
        raise HandoffError("receiving page has no logical_id; ambiguous identity rejected")
    if page.logical_id != handoff.receiving_page_logical_id:
        raise HandoffError("receiving page does not match handoff target")
    if installer is None:
        raise HandoffError("no installer; handoff JSON alone is not insertion")

    if ledger is not None:
        prior = ledger.get(handoff.handoff_id, page.logical_id)
        if prior is not None:
            return prior

    receipt = installer.install(handoff, page)
    if not receipt.confirmed:
        return BindingReceipt(
            handoff_id=handoff.handoff_id, page_logical_id=page.logical_id,
            status="CONSUMED", inserted=False, install_readback="",
            native_component_id="",
            submission_destination=handoff.submission_destination,
            confirmation_destination=handoff.confirmation_destination,
            note="installer did not confirm; not inserted",
        )
    if not receipt.readback:
        return BindingReceipt(
            handoff_id=handoff.handoff_id, page_logical_id=page.logical_id,
            status="CONSUMED", inserted=False, install_readback="",
            native_component_id="",
            submission_destination=handoff.submission_destination,
            confirmation_destination=handoff.confirmation_destination,
            note="empty install readback; treated as not inserted (read back, never assume)",
        )

    status = "BOUND"
    component_id = receipt.native_component_id
    if post_bind_readback:
        if component_id and post_bind_readback == component_id:
            status = "VERIFIED"
        else:
            status = "INSTALLED"
    elif component_id:
        status = "INSTALLED"

    out = BindingReceipt(
        handoff_id=handoff.handoff_id, page_logical_id=page.logical_id,
        status=status, inserted=True, install_readback=receipt.readback,
        native_component_id=component_id,
        submission_destination=handoff.submission_destination,
        confirmation_destination=handoff.confirmation_destination,
        note="follow-up workflow refs carried record-only; live_sends=0",
    )
    if ledger is not None:
        ledger.record(handoff.handoff_id, page.logical_id, out)
    return out


class BindingLedger:
    """Idempotent in-memory binder state (durable checkpoints: W4)."""

    def __init__(self) -> None:
        self._bound: dict = {}
        self.installs = 0

    def get(self, handoff_id: str, page_logical_id: str) -> Optional[BindingReceipt]:
        return self._bound.get((handoff_id, page_logical_id))

    def record(self, handoff_id: str, page_logical_id: str, receipt: BindingReceipt) -> None:
        self._bound[(handoff_id, page_logical_id)] = receipt
        self.installs += 1


class RecordingInstaller:
    """Deterministic installer double: records calls, returns given readback."""

    def __init__(self, confirmed: bool = True, readback: str = "comp_1",
                 native_component_id: str = "comp_1") -> None:
        self.confirmed = confirmed
        self.readback = readback
        self.native_component_id = native_component_id
        self.calls: list = []

    def install(self, handoff: EmbedHandoff, page: PageRef) -> InstallReceipt:
        self.calls.append((handoff.handoff_id, page.logical_id))
        return InstallReceipt(confirmed=self.confirmed, readback=self.readback,
                              native_component_id=self.native_component_id)


# ------------------------------------------------------------- self-check


def _selfcheck() -> int:
    import tempfile

    passed = 0

    def ok(cond: bool, msg: str) -> None:
        nonlocal passed
        assert cond, msg
        passed += 1

    def sample(validate: bool = True, **over) -> EmbedHandoff:
        base = dict(
            asset=NativeAssetRef(kind="form", location_id="loc_1", native_id="form_9"),
            embed=EmbedPayload(kind="script", body='<script src="https://x/embed.js"></script>'),
            receiving_page_logical_id="page-12",
            submission_destination=Destination(kind="page", logical_id="page-13"),
            confirmation_destination=Destination(kind="url", url="https://x/thanks"),
            link="https://x/f/form_9",
            placement="body:end",
        )
        base.update(over)
        return make_handoff(**base) if validate else EmbedHandoff(**base)

    h = sample()
    ok(h.state() == "CREATED", "a record is only ever CREATED")
    ok(h.is_inserted() is False, "handoff JSON alone is not insertion")
    ok(h.handoff_id.startswith("hnd_") and len(h.handoff_id) == 20, "content-stamped id")
    ok(sample().handoff_id == h.handoff_id, "handoff_id deterministic across creates")

    # 1 — json round-trip
    with tempfile.TemporaryDirectory() as tmp:
        p = write_handoff(h, Path(tmp) / "h.json")
        h2 = load_handoff(p)
        ok(h2.handoff_id == h.handoff_id and h2.embed.body == h.embed.body,
           "write/load round-trip preserves identity and payload")
        ok(h2.is_inserted() is False, "loaded record still not inserted")

    # 2 — fail-closed validation
    bad = sample(validate=False, embed=EmbedPayload(kind="flash", body="x"))
    ok(validate_handoff(bad), "invalid embed kind rejected")
    try:
        make_handoff(asset=NativeAssetRef(kind="form", location_id="", native_id=""),
                     embed=EmbedPayload(kind="link", body="u"),
                     receiving_page_logical_id="",
                     submission_destination=Destination(kind="none"),
                     confirmation_destination=Destination(kind="none"))
        ok(False, "empty identities must raise")
    except HandoffError:
        ok(True, "empty identities rejected at make")
    ifr = sample(validate=False, embed=EmbedPayload(kind="iframe", body="https://x/f"))
    ok(any("frame_allow" in e for e in validate_handoff(ifr)),
   "iframe without declared framing permissions rejected")
    wf_dest = sample(submission_destination=Destination(kind="workflow", logical_id="wf_2"))
    ok(validate_handoff(wf_dest) == [], "workflow destination with logical_id valid")

    # 3 — receiving-page identity (spec gap 3)
    ok(resolve_page([PageRef("page-12"), PageRef("page-99")]) is None,
       "two candidates -> None, never the first")
    ok(resolve_page([]) is None, "zero candidates -> None")
    one = resolve_page([PageRef("page-12")])
    ok(one is not None and one.logical_id == "page-12", "exactly one candidate resolves")

    # 4 — binding requires a confirming installer with readback
    inst = RecordingInstaller()
    ledger = BindingLedger()
    r = bind_receiving_page(h, PageRef("page-12"), inst, ledger)
    ok(r.inserted and r.status == "INSTALLED", "confirmed install with readback -> inserted")
    ok(r.install_readback == "comp_1" and r.native_component_id == "comp_1",
       "receipt carries real readback and native component id")
    ok(r.live_sends == 0 and r.send_policy == "record-only",
       "follow-up workflow refs are record-only; zero live sends")

    # idempotent re-bind: installer called exactly once
    r2 = bind_receiving_page(h, PageRef("page-12"), inst, ledger)
    ok(r2 == r and len(inst.calls) == 1 and ledger.installs == 1,
       "second bind returns prior receipt; never installs twice")

    noconf = RecordingInstaller(confirmed=False)
    r3 = bind_receiving_page(sample(), PageRef("page-12"), noconf)
    ok(not r3.inserted and r3.status == "CONSUMED", "unconfirmed install -> not inserted")
    blank = RecordingInstaller(readback="", native_component_id="")
    r4 = bind_receiving_page(sample(), PageRef("page-12"), blank)
    ok(not r4.inserted and r4.status == "CONSUMED",
       "empty readback -> not inserted (read back, never assume)")

    try:
        bind_receiving_page(h, PageRef("page-12"), None)  # type: ignore[arg-type]
        ok(False, "no installer must raise")
    except HandoffError:
        ok(True, "no installer -> refused; handoff JSON alone is not insertion")
    try:
        bind_receiving_page(h, PageRef("page-99"), RecordingInstaller())
        ok(False, "mismatched page must raise")
    except HandoffError:
        ok(True, "page not matching handoff target refused")
    try:
        bind_receiving_page(h, PageRef(""), RecordingInstaller())
        ok(False, "page without logical id must raise")
    except HandoffError:
        ok(True, "ambiguous/anonymous receiving page refused")

    # 5 — field-state readback (spec gap 2): requested but never observed -> refuse
    unverified = sample(field_states=(FieldState(field_id="f1", required_requested=True),))
    try:
        bind_receiving_page(unverified, PageRef("page-12"), RecordingInstaller())
        ok(False, "unverified field state must raise")
    except HandoffError:
        ok(True, "requested field state without readback refused at bind")
    verified = sample(field_states=(FieldState(field_id="f1", required_requested=True,
                                               required_observed=True),))
    r5 = bind_receiving_page(verified, PageRef("page-12"), RecordingInstaller())
    ok(r5.inserted, "field state set AND read back -> bindable")

    # 6 — post-bind readback upgrades state only on exact match
    r6 = bind_receiving_page(sample(), PageRef("page-12"), RecordingInstaller(),
                             post_bind_readback="comp_1")
    ok(r6.status == "VERIFIED", "matching post-bind readback -> VERIFIED")
    r7 = bind_receiving_page(sample(), PageRef("page-12"), RecordingInstaller(),
                             post_bind_readback="comp_other")
    ok(r7.status == "INSTALLED" and r7.inserted,
       "mismatching post-bind readback stays INSTALLED, never VERIFIED")

    # 7 — schema pinning
    import os
    with tempfile.TemporaryDirectory() as tmp:
        p = write_handoff(h, Path(tmp) / "h.json")
        raw = json.loads(p.read_text(encoding="utf-8"))
        raw["schema_version"] = "ghl-embed-handoff/999"
        p.write_text(json.dumps(raw), encoding="utf-8")
        try:
            load_handoff(p)
            ok(False, "unknown schema version must raise")
        except HandoffError:
            ok(True, "unknown schema_version rejected")
        ok(os.path.getsize(p) > 0, "handoff JSON artifact written")

    print(f"OK {passed} PASS")
    return 0


if __name__ == "__main__":
    sys.exit(_selfcheck())
