#!/usr/bin/env python3
"""shared-utils/ghl/surveys.py — native survey fields, branches, submission and
confirmation destinations for the GHL delivery stream (W6, assignment W6B).

One writer for this file: assignment W6B. Contract: GHL-DELIVERY-SPEC.md
"Forms/surveys (W6)" + "Delivery contract (W1)" + "Durable execution (W4)".

Normative rules this file exists to enforce:

    * fields / custom-field IDs, required state, consent and validation are
      configured on a REAL native survey, and every requested state is SET and
      READ BACK — never blind-toggled (spec gap 2);
    * survey branches (jump-to conditional logic + branch convergence) are
      planned fail-closed: a dangling reference or a fall-through into a sibling
      branch aborts BEFORE any platform call (ghl_survey_builder preflight P4 /
      B08 semantics);
    * submission and confirmation destinations are explicit identities and are
      read back before anything counts as configured;
    * "done" is readback-gated: PLANNED -> CREATED -> CONFIGURED -> VERIFIED are
      distinct states and VERIFIED requires an exact observed match.

GROUNDING (every route/fact below cites a file this repository ships — never
invented endpoints or payloads):

    * fallback-ladder.json surface "survey": order ["browser", "api"] —
      browser drag rail PRIMARY (06-ghl-install-pages/tools/ghl_survey_builder.py),
      canvas-free REST FALLBACK capture-gated (tools/ghl_survey_rest.py).
      There is NO public survey-build API.
    * proven READ: GET backend.leadconnectorhq.com/surveys/<id> (owner token-id)
      and GET services.leadconnectorhq.com/surveys/?locationId=…&limit=… via the
      frozen public adapter operation "surveys.list" (ghl_public_client.list_surveys);
      both documented in ghl_survey_rest.py (GHL-169 named gaps).
    * proven WRITE: ONLY the SPA's own save route as RECORDED from the builder's
      Save click (routing/survey-save-capture.json). ghl_survey_rest.require_capture
      raises CaptureRequired before any write — this module obeys the same
      anti-blind-POST invariant: it never emits a write for an assumed endpoint.
    * public survey URL is CONSTRUCTED from the id —
      https://link.msgsndr.com/widget/survey/<id> (ghl_survey_builder.survey_public_url;
      a deliverable URL comes with a fetch-200 receipt, never from DOM scraping).
    * field key policy F2 (ghl_survey_builder._resolve_field_key / plan_survey_dependencies):
      "verbatim" engine keys must pre-exist byte-for-byte (create is REFUSED);
      "zhc" agent keys are idempotent zhc_<snake_slug>; GET existing keys first,
      REUSE matches, create only the missing zhc_ remainder (F1 grocery-shopping rule).
    * survey form data shape (ghl_survey_rest.verify_roundtrip): formData.slides
      (slideName + slideData elements) + form.conditionalLogic — the semantic
      round-trip diff compares slide count/names/element counts and the
      conditionalLogic count; any diff fails the build.

Integration seams (explicit, outstanding — recorded in unit evidence):

    * SurveyExecutor is the platform-write seam (managed browser via the W3
      harness adapters, or the capture-gated REST lane). Nothing in this file
      touches a browser, a network, or GHL: only RecordingExecutor runs here.
    * Custom-field pre-creation is Skill 44 / W6A territory; this module plans
      the dependency actions (reuse/create/REFUSED/verify_required) and refuses
      to bind an unconfirmed verbatim key.
    * Embed/installation of the survey on a receiving page is W6C
      (shared-utils/ghl/embed_handoff.py). as_embed_contract() emits exactly the
      asset/link/field-state/destination records that handoff consumes
      (NativeAssetRef + FieldState shapes match embed_handoff field-for-field).
    * Durable checkpoints are W4 (shared-utils/delivery/checkpoints.py).

Import pattern (from any script in the repo):

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    # directory name has no package dot-path; load by path or run this file
    # directly. The self-check is the usage example.

Run the assert-based self-check (offline — no network, no browser):

    python3 -I shared-utils/ghl/surveys.py
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

SCHEMA_VERSION = "ghl-surveys/1"

# --- route facts (cited above; NEVER guessed at call time) -------------------
SURVEYS_LIST_OPERATION_ID = "surveys.list"           # ghl_public_client SURVEYS_LIST
SURVEY_BACKEND_ORIGIN = "https://backend.leadconnectorhq.com"   # GET <id>, proven
SURVEY_WIDGET_HOST = "https://link.msgsndr.com"                 # public URL host
SURVEY_SURFACE_LADDER = ("browser", "api")           # fallback-ladder.json "survey"
PUBLIC_SURVEY_BUILD_API = False                      # none exists (fallback-ladder)

# --- field key policy (F2 contract) -----------------------------------------
KEY_POLICIES = ("verbatim", "zhc")
DEFAULT_KEY_POLICY = "zhc"
ZHC_KEY_PREFIX = "zhc_"

# --- lifecycle states (W1 delivery contract: distinct on purpose) ------------
SURVEY_STATES = ("PLANNED", "CREATED", "CONFIGURED", "VERIFIED", "INCOMPLETE")

ASSET_KIND = "survey"
EMBED_KINDS = ("script", "html", "iframe", "link")
DESTINATION_KINDS = ("page", "url", "workflow", "none")
SLIDE_KINDS = ("welcome", "question", "capture")


class SurveyError(ValueError):
    """Fail-closed rejection: a spec, plan or readback that cannot be trusted."""


class CapabilityIncomplete(RuntimeError):
    """A required platform operation is disabled/missing for this executor.

    Raised (and recorded on the receipt) whenever configuration would need a
    capability that is NOT verified — reported as INCOMPLETE, never as done."""


# ----------------------------------------------------------------- records

@dataclass(frozen=True)
class FieldSpec:
    """One survey question field.

    required/hidden are REQUESTED states; observed states arrive only through
    FieldState readback. ``consent=True`` marks a marketing-consent checkbox
    (plain T&C copy — never A2P/10DLC language, per ghl_survey_builder Phase J).
    """

    key: str                       # binding key -> {{contact.<key>}}
    label: str
    kind: str = "single_line"      # single_line | multi_line | email | phone |
                                   # radio | dropdown | checkbox | date | consent
    key_policy: str = DEFAULT_KEY_POLICY
    custom_field_id: str = ""      # native custom-field id when already bound
    options: Tuple[str, ...] = ()
    validation: str = ""           # "" | "email" | "phone" | "required_only"
    consent: bool = False
    required: Optional[bool] = None
    hidden: Optional[bool] = None


@dataclass(frozen=True)
class FieldState:
    """Requested vs observed state for one field — never blind-toggled.

    Field-for-field compatible with embed_handoff.FieldState (W6C consumes it).
    """

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

    def matches(self) -> bool:
        """True only when every requested state was observed as requested."""
        if not self.readback_complete():
            return False
        if self.required_requested is not None and self.required_observed != self.required_requested:
            return False
        if self.hidden_requested is not None and self.hidden_observed != self.hidden_requested:
            return False
        return True


@dataclass(frozen=True)
class BranchRule:
    """One jump-to conditional rule: if <if_field> == <if_value> -> <then_slide>.

    owner_slide hosts the rule on a slide OTHER than the if_field slide (branch
    exit -> converge jump); empty means the forward-router default. kind
    distinguishes task-supplied routers from derived convergence jumps.
    """

    if_field: str
    if_value: str
    then_slide: str
    owner_slide: str = ""
    kind: str = "router"           # "router" | "converge"


@dataclass(frozen=True)
class SlideSpec:
    """One survey slide. fields hold field keys/labels (refs resolved in plan)."""

    name: str
    fields: Tuple[str, ...] = ()
    kind: str = "question"


@dataclass(frozen=True)
class Destination:
    """Submission or confirmation destination, as an explicit identity.

    Compatible with embed_handoff.Destination.
    """

    kind: str                      # "page" | "url" | "workflow" | "none"
    logical_id: str = ""           # W1 stable logical id when kind is page/workflow
    native_id: str = ""            # actual page/workflow id when known
    url: str = ""                  # actual URL when kind is url


@dataclass(frozen=True)
class DestinationReceipt:
    """Requested vs observed destination — readback-gated."""

    role: str                      # "submission" | "confirmation"
    requested: Destination
    observed: Optional[Destination]

    def matches(self) -> bool:
        if self.observed is None:
            return False
        return (self.requested.kind == self.observed.kind
                and self.requested.logical_id == self.observed.logical_id
                and self.requested.native_id == self.observed.native_id
                and self.requested.url == self.observed.url)


@dataclass(frozen=True)
class NativeAssetRef:
    """A real native GHL survey, by native id. Compatible with embed_handoff."""

    kind: str = ASSET_KIND
    location_id: str = ""
    native_id: str = ""
    name: str = ""
    revision: str = ""


@dataclass(frozen=True)
class SurveySpec:
    """The complete requested configuration for one native survey."""

    name: str
    location_id: str
    fields: Tuple[FieldSpec, ...] = ()
    slides: Tuple[SlideSpec, ...] = ()       # empty = default one-field-per-slide
    branches: Tuple[BranchRule, ...] = ()
    converge_slide: str = ""
    submission_destination: Destination = Destination("none")
    confirmation_destination: Destination = Destination("none")
    follow_up_workflow_refs: Tuple[str, ...] = ()   # record-only; never sent here
    folder_name: str = ""
    revision: str = "1"


@dataclass(frozen=True)
class SurveyArtifact:
    """What W6B hands downstream: real native ids, link/embed, readbacks."""

    asset: NativeAssetRef
    link: str = ""                     # constructed public URL (id-derived)
    embed_kind: str = "link"           # one of EMBED_KINDS
    embed_body: str = ""               # snippet/src when the platform returns one
    field_states: Tuple[FieldState, ...] = ()
    branch_rules: Tuple[BranchRule, ...] = ()
    submission_destination: DestinationReceipt = field(
        default_factory=lambda: DestinationReceipt("submission", Destination("none"), None))
    confirmation_destination: DestinationReceipt = field(
        default_factory=lambda: DestinationReceipt("confirmation", Destination("none"), None))
    follow_up_workflow_refs: Tuple[str, ...] = ()
    live_sends: int = 0                # always 0 here — record-only binding
    state: str = "PLANNED"
    notes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ConfigureReceipt:
    """Outcome of configure_survey. ``ok`` is readback-gated, never assumed."""

    status: str                    # one of SURVEY_STATES
    artifact: SurveyArtifact
    field_states: Tuple[FieldState, ...] = ()
    branch_readback_count: Optional[int] = None
    roundtrip: Tuple[str, ...] = ()    # semantic diff lines; empty = clean
    consumers: Tuple[str, ...] = ()
    incomplete: Tuple[str, ...] = ()   # capability gaps, named

    @property
    def ok(self) -> bool:
        return self.status == "VERIFIED"


# --------------------------------------------------------------- planning

def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(text).strip().lower()).strip("_")
    return s


def resolve_field_key(f: FieldSpec) -> Tuple[str, str]:
    """(field_key, key_policy) per the F2 contract (ghl_survey_builder._resolve_field_key).

    verbatim: byte-for-byte, never slugged/prefixed, MUST pre-exist (create REFUSED).
    zhc:      idempotent zhc_<snake_slug> from explicit key or label; never
              double-prefixes.
    """
    policy = f.key_policy.lower()
    if policy not in KEY_POLICIES:
        policy = DEFAULT_KEY_POLICY
    explicit = (f.key or "").strip()
    if policy == "verbatim":
        return explicit, "verbatim"
    slug = _slug(explicit or f.label) or "field"
    if not slug.startswith(ZHC_KEY_PREFIX):
        slug = ZHC_KEY_PREFIX + slug
    return slug, "zhc"


def plan_field_dependencies(
    fields: Sequence[FieldSpec],
    existing_field_keys: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """F1 grocery-shopping rule (mirror of ghl_survey_builder.plan_survey_dependencies):
    GET existing custom fields -> REUSE matching key -> CREATE only the missing
    zhc_ remainder -> read back. Action per field:

        reuse            key exists on the location
        create           missing zhc key (Skill 44 creates it out-of-band)
        REFUSED          missing verbatim key AFTER a GET (hard block)
        verify_required  verbatim key with no GET yet (live path must GET first)

    ``existing_field_keys is None`` means NO live GET has happened — binding is
    then refused for verbatim keys (never drag an unconfirmed field).
    """
    live_get_done = existing_field_keys is not None
    # GHL fieldKey rows are often "contact.zhc_foo" — accept the tail token too
    # (same tolerance as ghl_survey_builder._caf_list_field_keys).
    existing = set()
    for k in (existing_field_keys or []):
        k = str(k).strip().lower()
        if k:
            existing.add(k)
            if "." in k:
                existing.add(k.rsplit(".", 1)[-1])
    specs: List[Dict[str, Any]] = []
    missing_verbatim: List[Dict[str, Any]] = []
    for f in fields:
        key, policy = resolve_field_key(f)
        exists = bool(key) and key.lower() in existing
        if policy == "verbatim":
            if not key:
                action = "REFUSED"
                missing_verbatim.append({"label": f.label,
                                         "reason": "key_policy=verbatim but no key supplied"})
            elif not live_get_done:
                action = "verify_required"
            elif exists:
                action = "reuse"
            else:
                action = "REFUSED"
                missing_verbatim.append({"label": f.label, "key": key,
                                         "reason": "verbatim key not present on location"})
        else:
            action = "reuse" if exists else "create"
        specs.append({
            "field_key": key,
            "label": f.label,
            "data_type": f.kind,
            "options": list(f.options),
            "merge_token": f"{{{{contact.{key}}}}}" if key else "",
            "key_policy": policy,
            "action": action,
        })
    return {
        "schema_version": "1.0",
        "custom_fields": specs,
        "blocked": bool(missing_verbatim),
        "missing_verbatim_keys": missing_verbatim,
        "idempotency": {
            "live_get_done": live_get_done,
            "live_get_required": not live_get_done,
            "rule": "GET existing custom fields; REUSE any matching key; only CREATE "
                    "the missing zhc_ remainder. verbatim keys are never created — "
                    "they MUST pre-exist. Never duplicate.",
        },
    }


def plan_slides(spec: SurveySpec) -> Tuple[SlideSpec, ...]:
    """Default layout when spec.slides is empty: welcome + one question slide per
    field (F-order) + capture slide — the layout ghl_survey_builder._plan_slides
    builds for a task without task['slides']. A supplied layout is kept as-is."""
    if spec.slides:
        return tuple(spec.slides)
    out: List[SlideSpec] = [SlideSpec(name="Welcome", kind="welcome")]
    for f in spec.fields:
        out.append(SlideSpec(name=f.label, fields=(f.key or f.label,), kind="question"))
    out.append(SlideSpec(name="Your details", kind="capture"))
    return tuple(out)


def derive_convergence_rules(spec: SurveySpec,
                             slides: Sequence[SlideSpec]) -> Tuple[BranchRule, ...]:
    """Area-5.1 branch-convergence primitive (ghl_survey_builder._derive_convergence_rules):
    for each forward router rule, derive one jump owned by that branch's exit
    slide that lands on converge_slide, so the respondent never falls into a
    sibling branch's required fields. Returns () without converge_slide or when
    the topology is degenerate (dangling refs are reported by validate_topology).
    """
    if not spec.converge_slide:
        return ()
    idx = _slide_resolver(slides)
    converge = idx(spec.converge_slide)
    if converge is None:
        return ()
    c_i = converge[0]
    entries: List[Tuple[int, BranchRule]] = []
    for r in spec.branches:
        if r.owner_slide or r.kind == "converge":
            continue
        t = idx(r.then_slide)
        if t is not None and t[0] < c_i:
            entries.append((t[0], r))
    if not entries:
        return ()
    entry_is = sorted({i for i, _ in entries})
    derived: List[BranchRule] = []
    for b_i, r in entries:
        later = [i for i in entry_is if i > b_i]
        boundary = min(later) if later else c_i
        exit_i = min(boundary - 1, c_i - 1)
        if exit_i < b_i:
            exit_i = b_i
        derived.append(BranchRule(if_field=r.if_field, if_value=r.if_value,
                                  then_slide=spec.converge_slide,
                                  owner_slide=slides[exit_i].name, kind="converge"))
    return tuple(derived)


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _slide_resolver(slides: Sequence[SlideSpec]):
    """name -> (index, slide) by normalized name; also accepts 'P<n>'/'Slide n'/index."""
    by_name: Dict[str, Tuple[int, SlideSpec]] = {}
    for i, s in enumerate(slides):
        by_name.setdefault(_norm(s.name), (i, s))
        by_name.setdefault(f"p{i + 1}", (i, s))
        by_name.setdefault(f"slide {i + 1}", (i, s))
        by_name.setdefault(str(i + 1), (i, s))

    def resolve(ref: Any) -> Optional[Tuple[int, SlideSpec]]:
        return by_name.get(_norm(ref))
    return resolve


def validate_topology(spec: SurveySpec,
                      slides: Sequence[SlideSpec]) -> List[str]:
    """Fail-closed structural validation (ghl_survey_builder._validate_topology
    rules + B08 fall-through). Returns [] when sound; every string is a HARD
    STOP reason — no platform call may happen while this list is non-empty."""
    errors: List[str] = []
    field_keys = {_norm(f.key or f.label) for f in spec.fields}
    q_slides = [s for s in slides if s.kind == "question"]

    # (1) unknown field references in slide layouts
    for s in q_slides:
        for ref in s.fields:
            if _norm(ref) not in field_keys:
                errors.append(f"slide {s.name!r} references unknown field {ref!r}")

    # (2)/(3) custom layout placement coverage
    if spec.slides:
        placed: Dict[str, int] = {}
        for s in q_slides:
            for ref in s.fields:
                placed[_norm(ref)] = placed.get(_norm(ref), 0) + 1
        for ref, cnt in placed.items():
            if cnt > 1:
                errors.append(f"field {ref!r} is placed on {cnt} slides (must be exactly one)")
        for f in spec.fields:
            if _norm(f.key or f.label) not in placed:
                errors.append(f"survey field {f.label!r} is not placed on any slide (orphan)")

    # (4) branching references
    resolve = _slide_resolver(slides)
    all_rules = list(spec.branches)
    for r in all_rules:
        if _norm(r.if_field) not in field_keys and _norm(r.if_field) not in \
                {_norm(f.label) for f in spec.fields}:
            errors.append(f"branch rule references unknown if_field {r.if_field!r}")
        if resolve(r.then_slide) is None:
            errors.append(f"branch rule has dangling then_slide {r.then_slide!r}")
        if r.owner_slide and resolve(r.owner_slide) is None:
            errors.append(f"branch rule has dangling owner_slide {r.owner_slide!r}")
    if spec.converge_slide and resolve(spec.converge_slide) is None:
        errors.append(f"converge_slide {spec.converge_slide!r} does not resolve to a survey slide")

    # (5) branch fall-through (B08): a forward router landing on a slide
    # immediately followed by another branch entry, with no convergence jump,
    # strands the respondent before Submit — HARD STOP even without converge_slide.
    fwd = [r for r in all_rules if not r.owner_slide and r.kind == "router"]
    sib: Dict[int, str] = {}
    for r in fwd:
        t = resolve(r.then_slide)
        if t is not None:
            sib.setdefault(t[0], r.then_slide)
    if not spec.converge_slide:
        for i in sorted(sib):
            nxt = sib.get(i + 1)
            if nxt is not None:
                errors.append(
                    f"B08: branch slide {sib[i]!r} falls through into sibling branch "
                    f"{nxt!r} (no slide between them, no convergence jump) — respondent "
                    "cannot submit; set converge_slide or add a jump")
    # ponytail: with converge_slide declared, convergence-coverage accounting
    # (each branch exit reaches the converge slide via a derived jump) lives in
    # derive_convergence_rules, which covers every forward router when the
    # converge ref resolves (a dangling one is an error above). Add an explicit
    # reachability matrix here if tasks start supplying hand-written owner_slide
    # jumps instead of derived ones.
    return errors


def validate_spec(spec: SurveySpec) -> List[str]:
    """Whole-spec fail-closed validation. Empty list means the spec is sound."""
    errors: List[str] = []
    if not spec.name.strip():
        errors.append("spec.name required")
    if not spec.location_id.strip():
        errors.append("spec.location_id required (real native identity)")
    for f in spec.fields:
        if not (f.key or f.label).strip():
            errors.append("every field needs a key or label")
        if f.key_policy not in KEY_POLICIES:
            errors.append(f"field {f.label!r}: key_policy must be one of {KEY_POLICIES}")
        if f.kind in ("radio", "dropdown", "checkbox") and not f.options:
            errors.append(f"field {f.label!r}: choice field needs options")
        if f.consent and f.kind not in ("consent", "checkbox"):
            errors.append(f"field {f.label!r}: consent flag needs consent/checkbox kind")
    for role, d in (("submission_destination", spec.submission_destination),
                    ("confirmation_destination", spec.confirmation_destination)):
        if d.kind not in DESTINATION_KINDS:
            errors.append(f"{role}.kind must be one of {DESTINATION_KINDS}")
        if d.kind in ("page", "workflow") and not (d.logical_id or d.native_id):
            errors.append(f"{role} of kind {d.kind} needs logical_id or native_id")
        if d.kind == "url" and not d.url:
            errors.append(f"{role} of kind url needs url")
    if spec.submission_destination.kind == "workflow" and not spec.follow_up_workflow_refs:
        errors.append("workflow submission destination requires follow_up_workflow_refs")
    slides = plan_slides(spec)
    errors.extend(validate_topology(spec, slides))
    return errors


# ------------------------------------------------------------- executor seam

class SurveyExecutor(Protocol):
    """Platform-write seam. Real implementations: W3 managed-browser harness
    adapters (survey builder drag rail) or the capture-gated REST lane. Every
    method returns OBSERVED state — this module never trusts its own writes."""

    def create_or_find(self, spec: SurveySpec) -> NativeAssetRef: ...
    def read_asset(self, ref: NativeAssetRef) -> Dict[str, Any]: ...
    def set_field_state(self, ref: NativeAssetRef, key: str,
                        required: Optional[bool], hidden: Optional[bool]) -> None: ...
    def read_field_state(self, ref: NativeAssetRef, key: str) -> Dict[str, Optional[bool]]: ...
    def apply_branches(self, ref: NativeAssetRef, rules: Sequence[BranchRule]) -> None: ...
    def read_branches(self, ref: NativeAssetRef) -> List[Dict[str, str]]: ...
    def set_destinations(self, ref: NativeAssetRef, submission: Destination,
                         confirmation: Destination) -> None: ...
    def read_destinations(self, ref: NativeAssetRef) -> Dict[str, Optional[Destination]]: ...
    def list_consumers(self, ref: NativeAssetRef) -> List[str]: ...
    def embed_payload(self, ref: NativeAssetRef) -> Tuple[str, str]:
        """(embed_kind, embed_body); ("link", "") when the platform gives only a link."""


@dataclass
class RecordingExecutor:
    """Deterministic executor double: records calls, serves canned readbacks.

    Used by the self-check and as the wiring shape for a real adapter. With
    ``capabilities`` narrowed it doubles as a capability-gap probe."""
    name: str = "recording"
    native_id: str = "srv_test0001"
    existing_keys: Tuple[str, ...] = ()
    consumers: Tuple[str, ...] = ()
    capabilities: Tuple[str, ...] = (
        "create_or_find", "read_asset", "set_field_state", "read_field_state",
        "apply_branches", "read_branches", "set_destinations", "read_destinations",
        "list_consumers", "embed_payload")
    observed_required: Dict[str, bool] = field(default_factory=dict)
    observed_hidden: Dict[str, bool] = field(default_factory=dict)
    observed_branches: List[Dict[str, str]] = field(default_factory=list)
    observed_destinations: Dict[str, Optional[Destination]] = field(default_factory=dict)
    # Injected drift for negative controls (readback != request):
    drift_required: Dict[str, bool] = field(default_factory=dict)
    drift_branch_drop: bool = False
    calls: List[str] = field(default_factory=list)

    def _need(self, op: str) -> None:
        if op not in self.capabilities:
            raise CapabilityIncomplete(f"{self.name}: operation {op!r} not available")
        self.calls.append(op)

    def create_or_find(self, spec: SurveySpec) -> NativeAssetRef:
        self._need("create_or_find")
        return NativeAssetRef(kind=ASSET_KIND, location_id=spec.location_id,
                              native_id=self.native_id, name=spec.name,
                              revision=spec.revision)

    def read_asset(self, ref: NativeAssetRef) -> Dict[str, Any]:
        self._need("read_asset")
        slides = [{"slideName": s.name,
                   "slideData": [{"k": k} for k in s.fields]} for s in plan_slides(_SPECS[ref.native_id])]
        return {"formData": {"slides": slides,
                             "form": {"conditionalLogic": list(self.observed_branches)}}}

    def set_field_state(self, ref: NativeAssetRef, key: str,
                        required: Optional[bool], hidden: Optional[bool]) -> None:
        self._need("set_field_state")
        if required is not None:
            self.observed_required[key] = self.drift_required.get(key, required)
        if hidden is not None:
            self.observed_hidden[key] = hidden

    def read_field_state(self, ref: NativeAssetRef, key: str) -> Dict[str, Optional[bool]]:
        self._need("read_field_state")
        return {"required": self.observed_required.get(key),
                "hidden": self.observed_hidden.get(key)}

    def apply_branches(self, ref: NativeAssetRef, rules: Sequence[BranchRule]) -> None:
        self._need("apply_branches")
        out = [{"if_field": r.if_field, "if_value": r.if_value,
                "then_slide": r.then_slide, "owner_slide": r.owner_slide}
               for r in rules]
        self.observed_branches = out[:-1] if self.drift_branch_drop and out else out

    def read_branches(self, ref: NativeAssetRef) -> List[Dict[str, str]]:
        self._need("read_branches")
        return list(self.observed_branches)

    def set_destinations(self, ref: NativeAssetRef, submission: Destination,
                         confirmation: Destination) -> None:
        self._need("set_destinations")
        self.observed_destinations["submission"] = submission
        self.observed_destinations["confirmation"] = confirmation

    def read_destinations(self, ref: NativeAssetRef) -> Dict[str, Optional[Destination]]:
        self._need("read_destinations")
        return {"submission": self.observed_destinations.get("submission"),
                "confirmation": self.observed_destinations.get("confirmation")}

    def list_consumers(self, ref: NativeAssetRef) -> List[str]:
        self._need("list_consumers")
        return list(self.consumers)

    def embed_payload(self, ref: NativeAssetRef) -> Tuple[str, str]:
        self._need("embed_payload")
        return ("link", "")


# RecordingExecutor.read_asset needs the spec per native id — a tiny side table
# populated by configure_survey; kept module-local to preserve the frozen dataclasses.
_SPECS: Dict[str, SurveySpec] = {}


# -------------------------------------------------------------- orchestration

def survey_public_url(survey_id: str) -> str:
    """Public URL CONSTRUCTED from the id (ghl_survey_builder.survey_public_url).
    Never scraped from a DOM link. Consumers must prove it with a fetch-200
    receipt before treating it as a deliverable."""
    if not survey_id or not str(survey_id).strip():
        raise SurveyError("survey_id required")
    return f"{SURVEY_WIDGET_HOST}/widget/survey/{str(survey_id).strip()}"


def verify_roundtrip(expected: Dict[str, Any], got: Dict[str, Any]) -> List[str]:
    """Semantic round-trip diff (ghl_survey_rest.verify_roundtrip contract):
    slide COUNT, slideName sequence, per-slide element count, conditionalLogic
    count. Server-stamped fields ignored. Non-empty list = the build FAILS."""
    diffs: List[str] = []

    def slides_of(p: Dict[str, Any]) -> List[dict]:
        fd = p.get("formData", p) if isinstance(p, dict) else {}
        sl = fd.get("slides") if isinstance(fd, dict) else None
        return sl if isinstance(sl, list) else []

    def logic_of(p: Dict[str, Any]) -> List[dict]:
        fd = p.get("formData", p) if isinstance(p, dict) else {}
        form = fd.get("form") if isinstance(fd, dict) else None
        cl = form.get("conditionalLogic") if isinstance(form, dict) else None
        return cl if isinstance(cl, list) else []

    es, gs = slides_of(expected), slides_of(got)
    if len(es) != len(gs):
        diffs.append(f"slide count {len(es)} != {len(gs)}")
    else:
        for i, (a, b) in enumerate(zip(es, gs)):
            an = a.get("slideName") or a.get("name") or ""
            bn = b.get("slideName") or b.get("name") or ""
            if an != bn:
                diffs.append(f"slide[{i}] name {an!r} != {bn!r}")
            al = len(a.get("slideData", []) if isinstance(a.get("slideData"), list) else [])
            bl = len(b.get("slideData", []) if isinstance(b.get("slideData"), list) else [])
            if al != bl:
                diffs.append(f"slide[{i}] element count {al} != {bl}")
    if len(logic_of(expected)) != len(logic_of(got)):
        diffs.append(f"conditionalLogic count {len(logic_of(expected))} != {len(logic_of(got))}")
    return diffs


def check_consumers(ref: NativeAssetRef, executor: SurveyExecutor) -> Tuple[str, ...]:
    """Spec rule: check consumers before modifying a shared survey. A survey with
    live consumers may be reconfigured only with explicit approval
    (``allow_shared_modify`` on configure_survey) — and even then nothing is
    deleted or unbound here."""
    return tuple(executor.list_consumers(ref))


def configure_survey(
    spec: SurveySpec,
    executor: SurveyExecutor,
    *,
    existing_field_keys: Optional[Sequence[str]] = None,
    allow_shared_modify: bool = False,
) -> ConfigureReceipt:
    """The W6B pipeline: validate -> plan fields -> read-before-create -> set AND
    read back fields -> branches -> destinations -> semantic round-trip.

    Fail-closed: any validation error raises SurveyError before any platform
    call; any readback mismatch yields status INCOMPLETE (never VERIFIED);
    a missing executor capability is named in ``incomplete`` and the status is
    INCOMPLETE — a disabled operation is never reported as done.
    """
    errors = validate_spec(spec)
    if errors:
        raise SurveyError("; ".join(errors))

    dep = plan_field_dependencies(spec.fields, existing_field_keys)
    if dep["blocked"]:
        raise SurveyError("field dependency plan blocked: "
                          + "; ".join(str(m) for m in dep["missing_verbatim_keys"]))

    incomplete: List[str] = []
    notes: List[str] = []

    def guarded(op: str, fn):
        try:
            return fn()
        except CapabilityIncomplete as exc:
            incomplete.append(str(exc))
            return None

    # Read-before-create: executor.create_or_find must find-or-create, never
    # duplicate (W4 durable execution). Consumers checked before any modify.
    ref = guarded("create_or_find", lambda: executor.create_or_find(spec))
    if ref is None:
        return ConfigureReceipt(status="INCOMPLETE",
                                artifact=SurveyArtifact(asset=NativeAssetRef(location_id=spec.location_id),
                                                        state="INCOMPLETE",
                                                        notes=tuple(incomplete)),
                                incomplete=tuple(incomplete))
    _SPECS[ref.native_id] = spec

    consumers = guarded("list_consumers", lambda: check_consumers(ref, executor))
    consumers = consumers or ()
    if consumers and not allow_shared_modify:
        raise SurveyError(
            f"survey {ref.native_id!r} has {len(consumers)} consumer(s) "
            f"({', '.join(consumers[:3])}); shared modify refused — pass "
            "allow_shared_modify=True with explicit approval")

    # Fields: SET and READ BACK — never blind-toggle (spec gap 2).
    field_states: List[FieldState] = []
    for f in spec.fields:
        key, _policy = resolve_field_key(f)
        guarded("set_field_state", lambda f=f, key=key: executor.set_field_state(
            ref, key, f.required, f.hidden))
        obs = guarded("read_field_state", lambda key=key: executor.read_field_state(ref, key))
        fs = FieldState(field_id=key,
                        required_requested=f.required,
                        required_observed=(obs or {}).get("required") if obs is not None else None,
                        hidden_requested=f.hidden,
                        hidden_observed=(obs or {}).get("hidden") if obs is not None else None)
        field_states.append(fs)
        if not fs.matches():
            notes.append(f"field {key!r}: requested state not observed "
                         f"(required {fs.required_requested}->{fs.required_observed}, "
                         f"hidden {fs.hidden_requested}->{fs.hidden_observed})")

    # Branches: explicit + derived convergence jumps, then read back.
    slides = plan_slides(spec)
    derived = derive_convergence_rules(spec, slides)
    rules = tuple(spec.branches) + derived
    if rules:
        guarded("apply_branches", lambda: executor.apply_branches(ref, rules))
    observed_rules = guarded("read_branches", lambda: executor.read_branches(ref))
    branch_count_ok = (observed_rules is None) or (len(observed_rules) == len(rules))
    if observed_rules is not None and not branch_count_ok:
        notes.append(f"branch readback count {len(observed_rules)} != planned {len(rules)}")

    # Destinations: set + read back (submission AND confirmation).
    guarded("set_destinations", lambda: executor.set_destinations(
        ref, spec.submission_destination, spec.confirmation_destination))
    obs_dest = guarded("read_destinations", lambda: executor.read_destinations(ref)) or {}
    sub_rec = DestinationReceipt("submission", spec.submission_destination,
                                 obs_dest.get("submission") if obs_dest else None)
    conf_rec = DestinationReceipt("confirmation", spec.confirmation_destination,
                                  obs_dest.get("confirmation") if obs_dest else None)
    for rec in (sub_rec, conf_rec):
        if rec.requested.kind != "none" and not rec.matches():
            notes.append(f"{rec.role} destination readback mismatch")

    # Semantic round-trip against the platform's own read of the survey.
    expected = {"formData": {
        "slides": [{"slideName": s.name, "slideData": [{"k": k} for k in s.fields]}
                   for s in slides],
        "form": {"conditionalLogic": [{"i": i} for i in range(len(rules))]}}}
    readback = guarded("read_asset", lambda: executor.read_asset(ref))
    roundtrip: Tuple[str, ...] = ()
    if readback is not None:
        got_logic = readback.get("formData", {}).get("form", {}).get("conditionalLogic", [])
        normalized_got = {"formData": {
            "slides": readback.get("formData", {}).get("slides", []),
            "form": {"conditionalLogic": [{"i": i} for i in range(len(got_logic))]}}}
        roundtrip = tuple(verify_roundtrip(expected, normalized_got))

    embed_kind, embed_body = ("link", "")
    emb = guarded("embed_payload", lambda: executor.embed_payload(ref))
    if emb is not None:
        embed_kind, embed_body = emb
    link = survey_public_url(ref.native_id)

    # Status: VERIFIED only on exact readback everywhere; missing capability ->
    # INCOMPLETE (never done); drift -> INCOMPLETE with named reasons.
    if incomplete:
        status = "INCOMPLETE"
    elif (not notes and branch_count_ok and not roundtrip
          and all(fs.matches() for fs in field_states)
          and (sub_rec.matches() or spec.submission_destination.kind == "none")
          and (conf_rec.matches() or spec.confirmation_destination.kind == "none")):
        status = "VERIFIED"
    elif ref.native_id and not notes and roundtrip == () and not field_states:
        status = "CREATED"
    else:
        status = "INCOMPLETE"

    artifact = SurveyArtifact(
        asset=ref,
        link=link,
        embed_kind=embed_kind,
        embed_body=embed_body,
        field_states=tuple(field_states),
        branch_rules=rules,
        submission_destination=sub_rec,
        confirmation_destination=conf_rec,
        follow_up_workflow_refs=tuple(spec.follow_up_workflow_refs),
        live_sends=0,
        state=status,
        notes=tuple(notes))
    return ConfigureReceipt(
        status=status,
        artifact=artifact,
        field_states=tuple(field_states),
        branch_readback_count=(len(observed_rules) if observed_rules is not None else None),
        roundtrip=roundtrip,
        consumers=consumers,
        incomplete=tuple(incomplete))


def as_embed_contract(artifact: SurveyArtifact) -> Dict[str, Any]:
    """The W6B output record W6C's embed_handoff consumes: asset + embed + link +
    field states + submission/confirmation destinations + record-only workflow
    refs. Field names match embed_handoff's NativeAssetRef / FieldState /
    Destination shapes exactly. JSON is not insertion (W6C rule) — this only
    hands the verified asset side across the seam."""
    return {
        "schema_version": SCHEMA_VERSION,
        "asset": {"kind": artifact.asset.kind, "location_id": artifact.asset.location_id,
                  "native_id": artifact.asset.native_id, "name": artifact.asset.name,
                  "revision": artifact.asset.revision},
        "embed": {"kind": artifact.embed_kind, "body": artifact.embed_body or artifact.link},
        "link": artifact.link,
        "field_states": [
            {"field_id": fs.field_id,
             "required_requested": fs.required_requested,
             "required_observed": fs.required_observed,
             "hidden_requested": fs.hidden_requested,
             "hidden_observed": fs.hidden_observed}
            for fs in artifact.field_states],
        "submission_destination": {
            "kind": artifact.submission_destination.observed.kind
            if artifact.submission_destination.observed else "none",
            "logical_id": artifact.submission_destination.requested.logical_id,
            "native_id": artifact.submission_destination.requested.native_id,
            "url": artifact.submission_destination.requested.url},
        "confirmation_destination": {
            "kind": artifact.confirmation_destination.observed.kind
            if artifact.confirmation_destination.observed else "none",
            "logical_id": artifact.confirmation_destination.requested.logical_id,
            "native_id": artifact.confirmation_destination.requested.native_id,
            "url": artifact.confirmation_destination.requested.url},
        "follow_up_workflow_refs": list(artifact.follow_up_workflow_refs),
        "live_sends": artifact.live_sends,
    }


# --------------------------------------------------------------- self-check

def _demo_spec() -> SurveySpec:
    return SurveySpec(
        name="Intake Survey",
        location_id="LOC1",
        fields=(
            FieldSpec(key="zhc_goal", label="Goal", kind="radio",
                      options=("A", "B"), required=True),
            FieldSpec(key="zhc_email", label="Email", kind="email",
                      validation="email", required=True),
            FieldSpec(key="zhc_tandc", label="T & C", kind="consent",
                      consent=True, required=True),
        ),
        branches=(
            BranchRule(if_field="zhc_goal", if_value="A", then_slide="Slide 2"),
            BranchRule(if_field="zhc_goal", if_value="B", then_slide="Slide 3"),
        ),
        converge_slide="Slide 4",
        submission_destination=Destination("workflow", logical_id="wf_followup"),
        confirmation_destination=Destination("url", url="https://example.com/thanks"),
        follow_up_workflow_refs=("wf_followup",),
    )


def _selfcheck() -> int:
    checks = 0
    failures: List[str] = []

    def ok(cond: bool, msg: str) -> None:
        nonlocal checks
        checks += 1
        if not cond:
            failures.append(msg)

    # --- field key policy (F2) ---
    k, p = resolve_field_key(FieldSpec(key="podcast_survey__additional_info", label="X",
                                       key_policy="verbatim"))
    ok(k == "podcast_survey__additional_info" and p == "verbatim",
       "verbatim key must be byte-for-byte")
    k2, _ = resolve_field_key(FieldSpec(key="My Label", label="My Label"))
    ok(k2 == "zhc_my_label", f"zhc slug wrong: {k2}")
    k3, _ = resolve_field_key(FieldSpec(key="zhc_already", label="x"))
    ok(k3 == "zhc_already", "zhc must never double-prefix")

    # --- dependency plan: reuse / create / REFUSED / verify_required ---
    dep = plan_field_dependencies(
        (FieldSpec(key="zhc_a", label="A"),
         FieldSpec(key="zhc_b", label="B"),
         FieldSpec(key="eng_key", label="E", key_policy="verbatim")), None)
    acts = [c["action"] for c in dep["custom_fields"]]
    ok(acts == ["create", "create", "verify_required"], f"actions wrong: {acts}")
    dep2 = plan_field_dependencies(
        (FieldSpec(key="zhc_a", label="A"),
         FieldSpec(key="eng_key", label="E", key_policy="verbatim")), ["contact.zhc_a"])
    acts2 = [c["action"] for c in dep2["custom_fields"]]
    ok(acts2 == ["reuse", "REFUSED"], f"post-GET actions wrong: {acts2}")
    ok(dep2["blocked"], "missing verbatim key must block")

    # --- topology: dangling refs + B08 fall-through are hard stops ---
    bad = SurveySpec(name="B", location_id="L",
                     fields=(FieldSpec(key="zhc_a", label="A"),
                             FieldSpec(key="zhc_b", label="B")),
                     slides=(SlideSpec("Welcome", kind="welcome"),
                             SlideSpec("Q1", fields=("zhc_a",)),
                             SlideSpec("Q2", fields=("zhc_b",))),
                     branches=(BranchRule("zhc_a", "x", "Nope"),))
    errs = validate_topology(bad, plan_slides(bad))
    ok(any("dangling then_slide" in e for e in errs), f"missing dangling ref error: {errs}")
    fallthrough = SurveySpec(
        name="F", location_id="L",
        fields=(FieldSpec(key="zhc_a", label="A"),),
        branches=(BranchRule("zhc_a", "x", "Slide 2"),
                  BranchRule("zhc_a", "y", "Slide 3")))
    errs_ft = validate_topology(fallthrough, plan_slides(fallthrough))
    ok(any("B08" in e for e in errs_ft), f"B08 fall-through not caught: {errs_ft}")

    # --- convergence derivation covers branch exits ---
    spec = _demo_spec()
    slides = plan_slides(spec)
    derived = derive_convergence_rules(spec, slides)
    ok(len(derived) == 2 and all(r.kind == "converge" for r in derived),
       f"convergence jumps wrong: {derived}")
    ok(validate_topology(spec, slides) == [],
       f"demo spec must be sound: {validate_topology(spec, slides)}")

    # --- configure: happy path readback-gated to VERIFIED ---
    ex = RecordingExecutor(existing_keys=tuple(
        resolve_field_key(f)[0] for f in spec.fields))
    rec = configure_survey(spec, ex, existing_field_keys=list(ex.existing_keys))
    ok(rec.status == "VERIFIED", f"happy path must VERIFIED, got {rec.status}: {rec.artifact.notes}")
    ok(rec.ok and rec.artifact.live_sends == 0, "record-only binding must keep live_sends at 0")
    ok(len(rec.field_states) == 3 and all(fs.matches() for fs in rec.field_states),
       "field states must be set AND read back")
    ok(rec.branch_readback_count == 4,  # 2 routers + 2 derived convergence jumps
       f"branch readback count wrong: {rec.branch_readback_count}")
    ok(rec.roundtrip == (), f"roundtrip must be clean: {rec.roundtrip}")
    ok(rec.artifact.link == f"{SURVEY_WIDGET_HOST}/widget/survey/{ex.native_id}",
       "link must be constructed from the id")
    ok(rec.artifact.submission_destination.matches()
       and rec.artifact.confirmation_destination.matches(),
       "destinations must be read back and match")

    # --- negative control 1: required state drift (set != read back) ---
    ex_drift = RecordingExecutor(native_id="srv_drift1",
                                 drift_required={"zhc_email": False})
    rec_d = configure_survey(spec, ex_drift,
                             existing_field_keys=[resolve_field_key(f)[0] for f in spec.fields])
    ok(rec_d.status == "INCOMPLETE" and not rec_d.ok,
       "required-state drift must never read as done")
    ok(any("zhc_email" in n for n in rec_d.artifact.notes),
       "drift must be named in notes")

    # --- negative control 2: dropped branch on readback ---
    ex_drop = RecordingExecutor(native_id="srv_drift2", drift_branch_drop=True)
    rec_b = configure_survey(spec, ex_drop,
                             existing_field_keys=[resolve_field_key(f)[0] for f in spec.fields])
    ok(rec_b.status == "INCOMPLETE"
       and any("branch readback count" in n for n in rec_b.artifact.notes),
       "dropped branch must fail closed")

    # --- negative control 3: capability gap -> INCOMPLETE, named, never done ---
    ex_gap = RecordingExecutor(native_id="srv_gap",
                               capabilities=("create_or_find", "read_asset"))
    rec_g = configure_survey(spec, ex_gap,
                             existing_field_keys=[resolve_field_key(f)[0] for f in spec.fields])
    ok(rec_g.status == "INCOMPLETE" and not rec_g.ok and rec_g.incomplete,
       "capability gap must report incomplete")
    ok(any("not available" in s for s in rec_g.incomplete),
       "capability gap must name the missing operation")

    # --- shared-survey consumer gate ---
    ex_shared = RecordingExecutor(native_id="srv_shared", consumers=("page/home",))
    try:
        configure_survey(spec, ex_shared,
                         existing_field_keys=[resolve_field_key(f)[0] for f in spec.fields])
        ok(False, "shared survey with consumers must refuse modify without approval")
    except SurveyError:
        ok(True, "")
    rec_shared = configure_survey(spec, ex_shared,
                                  existing_field_keys=[resolve_field_key(f)[0] for f in spec.fields],
                                  allow_shared_modify=True)
    ok(rec_shared.consumers == ("page/home",), "consumer audit must be recorded")

    # --- anti-blind-POST / route honesty invariants ---
    ok(SURVEY_SURFACE_LADDER == ("browser", "api") and not PUBLIC_SURVEY_BUILD_API,
       "surface ladder must stay browser->api with no public build API")
    ok(SURVEYS_LIST_OPERATION_ID == "surveys.list", "public adapter operation id drift")

    # --- W6C seam: contract record carries verified states, record-only refs ---
    contract = as_embed_contract(rec.artifact)
    ok(contract["asset"]["native_id"] == ex.native_id
       and contract["live_sends"] == 0
       and contract["follow_up_workflow_refs"] == ["wf_followup"]
       and all("required_observed" in fs for fs in contract["field_states"]),
       "embed contract shape wrong")

    # --- fail-closed: invalid spec raises before any executor call ---
    ex_clean = RecordingExecutor(native_id="srv_clean")
    try:
        configure_survey(SurveySpec(name="", location_id=""), ex_clean)
        ok(False, "invalid spec must raise")
    except SurveyError:
        ok(True, "")
    ok(ex_clean.calls == [], "no platform call may happen on an invalid spec")

    if failures:
        for f_msg in failures:
            print(f"  FAIL: {f_msg}")
        print(f"\nself-check FAIL — {len(failures)}/{checks} checks failed")
        return 1
    print(f"self-check OK ({checks} assertions)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in ("--selftest",):
        print("usage: surveys.py [--selftest]   (default: run the self-check)")
        return 2
    return _selfcheck()


if __name__ == "__main__":
    sys.exit(main())
