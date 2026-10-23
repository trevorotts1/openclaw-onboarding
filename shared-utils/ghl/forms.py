#!/usr/bin/env python3
"""shared-utils/ghl/forms.py — GHL native FORMS: creation, configuration, preservation
(stream W6, assignment W6A-U1).

Scope (GHL-DELIVERY-SPEC.md "Forms/surveys (W6)" + "Durable execution (W4)"):
  * Create OR reuse a real native GHL form (never a duplicate on resume).
  * Configure fields with custom-field IDs, required state, consent and validation.
  * REQUIRED/REQUIRED-FALSE state is SET to the requested true/false AND READ BACK
    and compared — never blind-toggled. A functional failure is not cosmetic:
    an unconfirmed set is an error, never a success (owner order gap 2).
  * PRESERVATION: successful forms are never deleted (PRESERVE-on-success). Only an
    object explicitly created as scratch (``FormSpec.scratch=True``) may be deleted,
    and only with an explicit confirmation flag.
  * Returns actual native IDs, embed/script and link — every identity and readback
    value comes from the platform (executor readback), never synthesized here.

Route honesty (capability_inventory.py, W2A):
  * Form create/edit ladder is CAF_CLI -> MANAGED_BROWSER
    (SURFACE_LADDERS["form"]); the managed-builder route is
    ``browser.form_build`` = 06-ghl-install-pages/tools/ghl_form_builder.py.
  * RESTRICTION ``form_field_placement_no_rest``: NO field-placement REST API exists
    for forms. Custom fields/tags are pre-created through the API layer (caf CLI,
    44-convert-and-flow-operator); field placement happens in the gated browser
    builder. This module therefore NEVER invents REST endpoints or payloads — all
    platform mutation goes through the FormExecutor seam, whose live adapter drives
    the gated builder / CLI routes above.
  * ``caf.std_ops`` is DISCOVERABLE: the operation class of each CLI command is
    confirmed at runtime (CLI help) before use; read/list never implies create/edit.
  * A disabled or missing platform capability is reported as INCOMPLETE, never done.

Integration seams (frozen interfaces, real implementations live on sibling lanes):
  * Identity persistence follows shared-utils/delivery/checkpoints.py (W4A): native
    IDs keyed by location/kind/parent/logical identity, never name alone. Pass a
    checkpoints-backed object satisfying IdentityStore.
  * The returned record is what shared-utils/ghl/embed_handoff.py (W6C) wraps in
    NativeAssetRef(kind="form", location_id=..., native_id=...); handoff JSON alone
    is not insertion (W6C owns placement/binding).
  * Custom-field provisioning follows ghl_form_builder.py zhc_ conventions
    (``zhc_<snake_slug>`` keys, GET-before-create idempotent reuse).

Runnable check:
    python3 shared-utils/ghl/forms.py
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Dict, List, Optional, Protocol, Sequence, Tuple

# --------------------------------------------------------------------------
# States (spec delivery contract: PLANNED -> CREATED -> CONFIGURED -> PUBLISHED
# -> VERIFIED are distinct; forms do not self-publish — PUBLISHED is the page's
# concern — so the form states are PLANNED/CREATED/CONFIGURED/VERIFIED).
# --------------------------------------------------------------------------

ST_PLANNED = "PLANNED"
ST_CREATED = "CREATED"
ST_CONFIGURED = "CONFIGURED"
ST_VERIFIED = "VERIFIED"

MAX_STATE_RETRIES = 2  # bounded set+readback retries before a hard failure


class FormsError(Exception):
    """Base error for this module."""


class SpecError(FormsError):
    """Invalid requested configuration (fail at plan time)."""


class AmbiguousMatchError(FormsError):
    """More than one existing form matches — never pick the first."""


class ReadbackMismatch(FormsError):
    """A set was not confirmed by readback. Blind toggling is a failure."""


class ConsumerConflictError(FormsError):
    """Shared form has consumers and modification was not authorized."""


class PreservationError(FormsError):
    """Delete refused: successful forms are preserved."""


# --------------------------------------------------------------------------
# Request model
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationRule:
    """Per-field validation requested at configuration time.

    Declarative input for the builder executor (which owns the real UI/API
    bindings). No payload is invented here.
    """

    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    options: Tuple[str, ...] = ()
    message: str = ""

    def errors(self) -> List[str]:
        out: List[str] = []
        if self.min_length is not None and self.min_length < 0:
            out.append("min_length negative")
        if (self.min_length is not None and self.max_length is not None
                and self.max_length < self.min_length):
            out.append("max_length < min_length")
        if (self.min_value is not None and self.max_value is not None
                and self.max_value < self.min_value):
            out.append("max_value < min_value")
        if any(not str(o).strip() for o in self.options):
            out.append("empty option in options")
        if len(set(self.options)) != len(self.options):
            out.append("duplicate option")
        return out


@dataclass(frozen=True)
class FieldSpec:
    """One native form field, requested state included.

    required and hidden are mutually exclusive (ghl_form_builder.py property
    panel: a field is Required OR Hidden, never both).
    """

    key: str                      # standard element name OR zhc_<snake_slug> custom key
    label: str
    source: str = "standard"      # "standard" | "custom"
    element: str = ""             # builder element for standard fields
    custom_field_id: str = ""     # native custom-field id (custom fields only)
    width_pct: int = 100
    required: bool = False
    hidden: bool = False
    placeholder: str = ""
    validation: Optional[ValidationRule] = None

    def errors(self) -> List[str]:
        out: List[str] = []
        if not self.key.strip():
            out.append("empty key")
        if not self.label.strip():
            out.append(f"{self.key}: empty label")
        if self.source not in ("standard", "custom"):
            out.append(f"{self.key}: unknown source {self.source!r}")
        if self.source == "custom":
            if not is_zhc_field_key(self.key):
                out.append(f"{self.key}: custom key must match zhc_<snake_slug>")
            if not self.custom_field_id.strip():
                out.append(f"{self.key}: custom field needs custom_field_id "
                           "(pre-created through the API layer)")
        if self.required and self.hidden:
            out.append(f"{self.key}: required+hidden mutually exclusive")
        if not (1 <= int(self.width_pct) <= 100):
            out.append(f"{self.key}: width_pct out of 1..100")
        if self.validation is not None:
            out.extend(f"{self.key}: {e}" for e in self.validation.errors())
        return out


@dataclass(frozen=True)
class ConsentSpec:
    """Consent element on the form (terms checkbox / double opt-in notice)."""

    kind: str = "terms_checkbox"   # "terms_checkbox" | "double_opt_in"
    text: str = ""
    link_url: str = ""
    required: bool = True

    def errors(self) -> List[str]:
        out: List[str] = []
        if self.kind not in ("terms_checkbox", "double_opt_in"):
            out.append(f"unknown consent kind {self.kind!r}")
        if not self.text.strip():
            out.append("consent text empty")
        return out


@dataclass(frozen=True)
class FormSpec:
    """Requested native form."""

    logical_id: str               # stable logical identity (never name alone)
    name: str                     # container name; ZHC fleet prefix enforced
    location_id: str
    fields: Tuple[FieldSpec, ...] = ()
    consent: Optional[ConsentSpec] = None
    scratch: bool = False         # True => temp object eligible for confirmed delete

    def errors(self) -> List[str]:
        out: List[str] = []
        if not self.logical_id.strip():
            out.append("empty logical_id")
        if not self.name.strip():
            out.append("empty name")
        if not self.location_id.strip():
            out.append("empty location_id")
        keys = [f.key for f in self.fields]
        if len(set(keys)) != len(keys):
            out.append("duplicate field key")
        for f in self.fields:
            out.extend(f.errors())
        if self.consent is not None:
            out.extend(self.consent.errors())
        return out


# zhc_ convention (ghl_form_builder.py, pinned): machine keys lowercase snake
def is_zhc_field_key(key: str) -> bool:
    if not key.startswith("zhc_") or key != key.lower():
        return False
    rest = key[4:]
    return bool(rest) and all(c.isalnum() or c == "_" for c in rest) and " " not in key


# --------------------------------------------------------------------------
# Readback model (what the platform returned — never synthesized)
# --------------------------------------------------------------------------


@dataclass
class FieldReadback:
    key: str
    present: bool = False
    required: Optional[bool] = None
    hidden: Optional[bool] = None
    custom_field_id: str = ""
    validation: Optional[ValidationRule] = None

    def matches(self, spec: FieldSpec) -> bool:
        return (self.present
                and self.required is spec.required
                and self.hidden is spec.hidden
                and (spec.source != "custom"
                     or self.custom_field_id == spec.custom_field_id))


@dataclass
class ConsentReadback:
    present: bool = False
    kind: str = ""
    required: Optional[bool] = None

    def matches(self, spec: ConsentSpec) -> bool:
        return self.present and self.kind == spec.kind and self.required is spec.required


@dataclass
class FormRecord:
    """Result carrier. Identities and readbacks come from the platform."""

    logical_id: str
    location_id: str
    name: str
    native_id: str = ""
    state: str = ST_PLANNED
    reused: bool = False
    preserved: bool = False
    scratch: bool = False
    fields: Dict[str, FieldReadback] = dc_field(default_factory=dict)
    consent: Optional[ConsentReadback] = None
    embed: str = ""
    script: str = ""
    link: str = ""
    operations: List[str] = dc_field(default_factory=list)
    incomplete: List[str] = dc_field(default_factory=list)

    def readback_complete(self) -> bool:
        # VERIFIED requires confirmed readback of everything actually configured;
        # a record with no confirmed piece at all is never complete.
        if not self.fields and self.consent is None:
            return False
        return (all(f.present for f in self.fields.values())
                and (self.consent is None or bool(self.consent.present)))


# --------------------------------------------------------------------------
# Integration seams
# --------------------------------------------------------------------------


class FormExecutor(Protocol):
    """Platform mutation seam. The live adapter drives the documented ladder:
    CAF CLI (Tier 0, forms module) -> gated managed browser builder
    06-ghl-install-pages/tools/ghl_form_builder.py (browser.form_build).
    REST field placement DOES NOT EXIST (restriction form_field_placement_no_rest),
    so a compliant adapter never sends one.
    """

    def list_forms(self, location_id: str) -> List[dict]: ...
    def create_form(self, spec: FormSpec) -> dict: ...
    def read_form(self, native_id: str) -> dict: ...
    def place_field(self, native_id: str, f: FieldSpec) -> dict: ...
    def set_field_state(self, native_id: str, key: str,
                        required: bool, hidden: bool) -> dict: ...
    def read_field_state(self, native_id: str, key: str) -> dict: ...
    def set_validation(self, native_id: str, key: str,
                       rule: Optional[ValidationRule]) -> dict: ...
    def read_validation(self, native_id: str, key: str) -> dict: ...
    def set_consent(self, native_id: str, c: ConsentSpec) -> dict: ...
    def read_consent(self, native_id: str) -> dict: ...
    def read_consumers(self, native_id: str) -> List[str]: ...
    def fetch_embed(self, native_id: str) -> dict: ...
    def delete_form(self, native_id: str) -> dict: ...


class IdentityStore(Protocol):
    """Durable identity persistence (checkpoints.py contract: keyed by
    location/kind/parent/logical identity — never name alone)."""

    def get(self, location_id: str, logical_id: str) -> Optional[str]: ...
    def put(self, location_id: str, logical_id: str, native_id: str) -> None: ...


class CustomFieldProvisioner(Protocol):
    """API-layer custom-field create|reuse (zhc_ idempotency: GET first, reuse an
    existing key — never create a duplicate; ghl_form_builder.py plan_dependencies
    convention)."""

    def get_by_key(self, location_id: str, key: str) -> Optional[str]: ...
    def create(self, location_id: str, key: str, label: str) -> str: ...


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------


@dataclass
class FieldPlan:
    key: str
    custom_field_id: str
    action: str  # "reuse" | "create" | "standard"


@dataclass
class FormPlan:
    spec: FormSpec
    field_plans: List[FieldPlan] = dc_field(default_factory=list)
    errors: List[str] = dc_field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def plan_form(spec: FormSpec,
              provisioner: Optional[CustomFieldProvisioner] = None) -> FormPlan:
    """Validate the request and plan custom-field dependencies create|reuse.

    Fails closed: any spec error is recorded, no platform call is made."""
    plan = FormPlan(spec=spec, errors=list(spec.errors()))
    for f in spec.fields:
        if f.source != "custom":
            plan.field_plans.append(FieldPlan(f.key, "", "standard"))
            continue
        existing = provisioner.get_by_key(spec.location_id, f.key) if provisioner else None
        if existing:
            plan.field_plans.append(FieldPlan(f.key, existing, "reuse"))
        elif provisioner is None:
            plan.errors.append(f"{f.key}: custom field provisioning seam missing "
                              "(cannot confirm create|reuse)")
        else:
            native = provisioner.create(spec.location_id, f.key, f.label)
            if not native:
                plan.errors.append(f"{f.key}: custom-field creation returned no native id")
            else:
                plan.field_plans.append(FieldPlan(f.key, native, "create"))
    return plan


# --------------------------------------------------------------------------
# Creation / reuse (read before create; reconcile; never name-alone matching)
# --------------------------------------------------------------------------


def create_or_reuse_form(exec: FormExecutor, spec: FormSpec,
                         store: Optional[IdentityStore] = None) -> FormRecord:
    """Read before create. Exact unique match reuses; ambiguity refuses.

    Matching is by stored logical identity first (location/kind/logical id),
    then by exact unique name within the location. More than one candidate is
    an AmbiguousMatchError — never the first tab/row.
    """
    errs = spec.errors()
    if errs:
        raise SpecError("; ".join(errs))
    record = FormRecord(logical_id=spec.logical_id, location_id=spec.location_id,
                        name=spec.name, scratch=spec.scratch)

    stored = store.get(spec.location_id, spec.logical_id) if store else None
    if stored:
        row = exec.read_form(stored)
        if row and row.get("native_id") == stored:
            record.native_id = stored
            record.state = ST_CREATED
            record.reused = True
            record.operations.append(f"resume:{stored}")
            return record
        record.operations.append(f"stale-identity:{stored}")

    rows = exec.list_forms(spec.location_id)  # read BEFORE create
    record.operations.append("list_forms")
    exact = [r for r in rows if r.get("name") == spec.name]
    if len(exact) > 1:
        raise AmbiguousMatchError(
            f"{len(exact)} forms named {spec.name!r} in {spec.location_id}; "
            "refusing to pick one")
    if len(exact) == 1:
        record.native_id = exact[0].get("native_id", "")
        if not record.native_id:
            raise FormsError("matched form carries no native_id")
        record.state = ST_CREATED
        record.reused = True
        record.operations.append(f"reuse:{record.native_id}")
    else:
        created = exec.create_form(spec)
        record.operations.append("create_form")
        native = created.get("native_id", "")
        if not native:
            raise FormsError("create returned no native_id")
        row = exec.read_form(native)  # reconcile before proceeding
        record.operations.append(f"read_form:{native}")
        if not row or row.get("native_id") != native:
            raise FormsError(f"create not reconciled by readback for {native}")
        record.native_id = native
        record.state = ST_CREATED
    if store is not None:
        store.put(spec.location_id, spec.logical_id, record.native_id)
    return record


# --------------------------------------------------------------------------
# Configuration — every write SET to the requested value AND READ BACK
# --------------------------------------------------------------------------


def _set_and_verify(record: FormRecord, what: str, setter, reader, verifier) -> None:
    """Set, read back, compare. Mismatch retries bounded, then ReadbackMismatch.

    Blind toggling is a failure (owner order gap 2): success is only ever
    declared on an exact readback match."""
    for attempt in range(MAX_STATE_RETRIES + 1):
        setter()
        record.operations.append(f"set:{what}:{attempt}")
        got = reader()
        record.operations.append(f"read:{what}:{attempt}")
        if verifier(got):
            return
    raise ReadbackMismatch(f"{what}: set not confirmed by readback")


def configure_fields(exec: FormExecutor, record: FormRecord,
                     specs: Sequence[FieldSpec]) -> FormRecord:
    """Place each field, then SET required/hidden to the requested true/false and
    READ BACK the state; validation rules get the same set+readback discipline."""
    if not record.native_id:
        raise FormsError("no native form to configure")
    for f in specs:
        exec.place_field(record.native_id, f)
        record.operations.append(f"place:{f.key}")

        def setter(f=f):
            exec.set_field_state(record.native_id, f.key, f.required, f.hidden)

        def reader(f=f):
            return exec.read_field_state(record.native_id, f.key)

        def verifier(got, f=f):
            rb = _field_readback(f.key, got)
            record.fields[f.key] = rb
            return rb.matches(f)

        _set_and_verify(record, f"field-state:{f.key}", setter, reader, verifier)

        if f.validation is not None:
            def vsetter(f=f):
                exec.set_validation(record.native_id, f.key, f.validation)

            def vreader(f=f):
                return exec.read_validation(record.native_id, f.key)

            def vverifier(got, f=f):
                rb = record.fields.get(f.key) or _field_readback(f.key, {})
                rb.validation = _validation_readback(got)
                record.fields[f.key] = rb
                return rb.validation == f.validation

            _set_and_verify(record, f"validation:{f.key}", vsetter, vreader, vverifier)
    record.state = ST_CONFIGURED
    return record


def configure_consent(exec: FormExecutor, record: FormRecord,
                      spec: ConsentSpec) -> FormRecord:
    """Consent element: set then read back kind and required state."""
    if not record.native_id:
        raise FormsError("no native form to configure")
    errs = spec.errors()
    if errs:
        raise SpecError("; ".join(errs))

    def setter():
        exec.set_consent(record.native_id, spec)

    def reader():
        return exec.read_consent(record.native_id)

    def verifier(got):
        rb = ConsentReadback(present=bool(got.get("present")),
                             kind=got.get("kind", ""),
                             required=got.get("required"))
        record.consent = rb
        return rb.matches(spec)

    _set_and_verify(record, "consent", setter, reader, verifier)
    record.state = ST_CONFIGURED
    return record


def _field_readback(key: str, got: dict) -> FieldReadback:
    return FieldReadback(
        key=key,
        present=bool(got.get("present")),
        required=got.get("required"),
        hidden=got.get("hidden"),
        custom_field_id=got.get("custom_field_id", ""))


def _validation_readback(got: dict) -> Optional[ValidationRule]:
    if not got.get("present"):
        return None
    return ValidationRule(
        min_length=got.get("min_length"),
        max_length=got.get("max_length"),
        pattern=got.get("pattern"),
        min_value=got.get("min_value"),
        max_value=got.get("max_value"),
        options=tuple(got.get("options", ())),
        message=got.get("message", ""))


# --------------------------------------------------------------------------
# Preservation, consumers, finalize
# --------------------------------------------------------------------------


def check_consumers(exec: FormExecutor, record: FormRecord,
                    allow_shared_edit: bool = False) -> List[str]:
    """Check consumers before modifying a shared form (spec W6)."""
    consumers = list(exec.read_consumers(record.native_id))
    record.operations.append(f"consumers:{len(consumers)}")
    if consumers and not allow_shared_edit:
        raise ConsumerConflictError(
            f"form {record.native_id} has {len(consumers)} consumer(s); "
            "shared-form modification not authorized")
    return consumers


def cleanup_scratch(exec: FormExecutor, record: FormRecord,
                    confirm: bool = False) -> bool:
    """Delete ONLY an explicitly-scratch form, ONLY with confirm=True.

    PRESERVE-on-success: a normal (non-scratch) form is never deleted here —
    cleanup intent or not — that is the PreservationError path."""
    if not record.scratch:
        raise PreservationError(
            f"form {record.native_id} is a successful asset; preserve (never delete-on-success)")
    if not confirm:
        raise PreservationError("scratch delete requires explicit confirm=True")
    exec.delete_form(record.native_id)
    record.operations.append(f"delete:{record.native_id}")
    record.preserved = False
    return True


def finalize(exec: FormExecutor, record: FormRecord) -> FormRecord:
    """Read back the native embed/script/link and mark VERIFIED only on complete
    readback. Missing platform output is INCOMPLETE, never done."""
    got = exec.fetch_embed(record.native_id)
    record.operations.append("fetch_embed")
    record.embed = got.get("embed", "")
    record.script = got.get("script", "")
    record.link = got.get("link", "")
    if not record.embed and not record.script:
        record.incomplete.append("embed/script unavailable from platform")
    if not record.link:
        record.incomplete.append("public link unavailable from platform")
    if not record.readback_complete():
        record.incomplete.append("field readback incomplete")
    if record.incomplete:
        if record.state == ST_CONFIGURED:
            pass  # stays CONFIGURED — never claims VERIFIED
    else:
        record.state = ST_VERIFIED
    record.preserved = not record.scratch
    return record


# --------------------------------------------------------------------------
# Recording executor (self-check only; the live adapter drives the real ladder)
# --------------------------------------------------------------------------


class RecordingExecutor:
    """Deterministic in-memory FormExecutor with fault injection.

    Faults: blind_set (set does not stick -> readback mismatch), ambiguous list,
    missing embed, no readback after create.
    """

    def __init__(self, blind_set: bool = False, ambiguous: bool = False,
                 missing_embed: bool = False, name: str = "ZHC Test Form") -> None:
        self.calls: List[str] = []
        self.blind_set = blind_set
        self.ambiguous = ambiguous
        self.missing_embed = missing_embed
        self.name = name
        self._next = 0
        self.forms: Dict[str, dict] = {}
        self.fields: Dict[Tuple[str, str], dict] = {}
        self.validations: Dict[Tuple[str, str], dict] = {}
        self.consents: Dict[str, dict] = {}
        self.deleted: List[str] = []
        self.consumers: List[str] = []
        self.forced_field_state: Dict[Tuple[str, str], dict] = {}

    def list_forms(self, location_id: str) -> List[dict]:
        self.calls.append("list_forms")
        if self.ambiguous:
            return [{"native_id": "form_a", "name": self.name},
                    {"native_id": "form_b", "name": self.name}]
        return [{"native_id": nid, "name": r["name"]}
                for nid, r in self.forms.items() if nid not in self.deleted]

    def create_form(self, spec: FormSpec) -> dict:
        self.calls.append("create_form")
        self._next += 1
        nid = f"form_{self._next}"
        self.forms[nid] = {"native_id": nid, "name": spec.name}
        return {"native_id": nid}

    def read_form(self, native_id: str) -> dict:
        self.calls.append(f"read_form:{native_id}")
        return dict(self.forms.get(native_id, {}))

    def place_field(self, native_id: str, f: FieldSpec) -> dict:
        self.calls.append(f"place:{f.key}")
        self.fields[(native_id, f.key)] = {
            "present": True, "required": False, "hidden": False,
            "custom_field_id": f.custom_field_id}
        return {"placed": True}

    def set_field_state(self, native_id: str, key: str,
                        required: bool, hidden: bool) -> dict:
        self.calls.append(f"set_state:{key}:{required}:{hidden}")
        if not self.blind_set:
            self.fields[(native_id, key)]["required"] = required
            self.fields[(native_id, key)]["hidden"] = hidden
        return {"accepted": True}

    def read_field_state(self, native_id: str, key: str) -> dict:
        self.calls.append(f"read_state:{key}")
        forced = self.forced_field_state.get((native_id, key))
        if forced is not None:
            return dict(forced)
        return dict(self.fields.get((native_id, key), {"present": False}))

    def set_validation(self, native_id: str, key: str,
                       rule: Optional[ValidationRule]) -> dict:
        self.calls.append(f"set_validation:{key}")
        self.validations[(native_id, key)] = {"rule": rule}
        return {"accepted": True}

    def read_validation(self, native_id: str, key: str) -> dict:
        self.calls.append(f"read_validation:{key}")
        row = self.validations.get((native_id, key))
        rule = row["rule"] if row else None
        if rule is None:
            return {"present": False}
        return {"present": True, "min_length": rule.min_length,
                "max_length": rule.max_length, "pattern": rule.pattern,
                "min_value": rule.min_value, "max_value": rule.max_value,
                "options": rule.options, "message": rule.message}

    def set_consent(self, native_id: str, c: ConsentSpec) -> dict:
        self.calls.append("set_consent")
        if not self.blind_set:
            self.consents[native_id] = {"present": True, "kind": c.kind,
                                        "required": c.required}
        return {"accepted": True}

    def read_consent(self, native_id: str) -> dict:
        self.calls.append("read_consent")
        return dict(self.consents.get(native_id, {"present": False}))

    def read_consumers(self, native_id: str) -> List[str]:
        self.calls.append("read_consumers")
        return list(self.consumers)

    def fetch_embed(self, native_id: str) -> dict:
        self.calls.append("fetch_embed")
        if self.missing_embed:
            return {"embed": "", "script": "", "link": ""}
        return {"embed": f'<div data-form="{native_id}"></div>',
                "script": f'<script src="https://x/{native_id}.js"></script>',
                "link": f"https://x/f/{native_id}"}

    def delete_form(self, native_id: str) -> dict:
        self.calls.append(f"delete:{native_id}")
        self.deleted.append(native_id)
        return {"deleted": True}


class MemoryStore:
    """IdentityStore for the self-check."""

    def __init__(self) -> None:
        self.rows: Dict[Tuple[str, str], str] = {}

    def get(self, location_id: str, logical_id: str) -> Optional[str]:
        return self.rows.get((location_id, logical_id))

    def put(self, location_id: str, logical_id: str, native_id: str) -> None:
        self.rows[(location_id, logical_id)] = native_id


class RecordingProvisioner:
    """CustomFieldProvisioner for the self-check (GET-first reuse)."""

    def __init__(self, existing: Optional[Dict[str, str]] = None) -> None:
        self.existing = dict(existing or {})
        self.created: List[str] = []

    def get_by_key(self, location_id: str, key: str) -> Optional[str]:
        return self.existing.get(key)

    def create(self, location_id: str, key: str, label: str) -> str:
        self.created.append(key)
        self.existing[key] = f"cf_{len(self.created)}"
        return self.existing[key]


# --------------------------------------------------------------------------
# Self-check
# --------------------------------------------------------------------------


def _selfcheck() -> int:
    passed = 0

    def ok(cond: bool, msg: str) -> None:
        nonlocal passed
        assert cond, msg
        passed += 1

    def spec(**over) -> FormSpec:
        base = dict(
            logical_id="form-lead-1",
            name="ZHC Lead Form",
            location_id="loc_1",
            fields=(
                FieldSpec(key="First Name", label="First Name", element="First Name",
                          required=True),
                FieldSpec(key="zhc_podcast_rating", label="Podcast Rating",
                          source="custom", custom_field_id="cf_7",
                          validation=ValidationRule(min_value=1, max_value=5)),
            ),
            consent=ConsentSpec(kind="terms_checkbox",
                                text="I agree to the terms", required=True),
        )
        base.update(over)
        return FormSpec(**base)

    # 1 — spec validation fails closed at plan time
    bad = spec(fields=(FieldSpec(key="Email", label="Email", required=True, hidden=True),))
    ok(any("mutually exclusive" in e for e in bad.errors()),
       "required+hidden rejected at plan time")
    ok(any("zhc_<snake_slug>" in e for e in
           spec(fields=(FieldSpec(key="Rating", label="R", source="custom",
                                  custom_field_id="cf_1"),)).errors()),
       "custom key without zhc_ prefix rejected")
    ok(any("custom_field_id" in e for e in
           spec(fields=(FieldSpec(key="zhc_x", label="X", source="custom"),)).errors()),
       "custom field without native custom-field id rejected")
    ok(any("width_pct" in e for e in
           spec(fields=(FieldSpec(key="A", label="A", width_pct=0),)).errors()),
       "width bounds enforced")
    ok(any("empty option" in e for e in
           spec(fields=(FieldSpec(key="B", label="B",
                                  validation=ValidationRule(options=("x", " "))),)).errors()),
       "validation rule errors surface")
    ok(spec().errors() == [], "reference spec is clean")

    # 2 — custom-field dependency plan is GET-first create|reuse
    prov = RecordingProvisioner(existing={"zhc_podcast_rating": "cf_7"})
    plan = plan_form(spec(), prov)
    ok(plan.ok, "plan clean with provisioner")
    ok(all(p.action == "reuse" or p.action == "standard" for p in plan.field_plans),
       "existing zhc key is reuse, never re-created")
    ok(prov.created == [], "reuse path creates nothing")
    prov2 = RecordingProvisioner()
    plan2 = plan_form(spec(fields=(
        FieldSpec(key="zhc_new_field", label="New", source="custom",
                  custom_field_id="cf_pending"), )), prov2)
    ok(any(p.action == "create" for p in plan2.field_plans) and prov2.created == ["zhc_new_field"],
       "missing zhc key planned create via API layer")
    noprov = plan_form(spec(), None)
    ok(not noprov.ok and any("seam missing" in e for e in noprov.errors),
       "no provisioner -> explicit error, never silent")

    # 3 — read before create; reconcile; unique-name reuse; ambiguity refuses
    ex = RecordingExecutor()
    rec = create_or_reuse_form(ex, spec())
    ok(ex.calls[0] == "list_forms", "read BEFORE create")
    ok(ex.calls.count("create_form") == 1 and rec.native_id == "form_1",
       "create returns real native id")
    ok(rec.state == ST_CREATED and not rec.reused, "new form CREATED")
    store = MemoryStore()
    ex2 = RecordingExecutor()
    rec2 = create_or_reuse_form(ex2, spec(), store)
    rec3 = create_or_reuse_form(ex2, spec(), store)
    ok(rec3.reused and rec3.native_id == rec2.native_id
       and ex2.calls.count("create_form") == 1,
       "resume reuses stored identity; never duplicates")
    ok(store.get("loc_1", "form-lead-1") == rec2.native_id, "identity persisted")
    ex3 = RecordingExecutor(ambiguous=True, name="ZHC Lead Form")
    try:
        create_or_reuse_form(ex3, spec())
        ok(False, "ambiguity must refuse")
    except AmbiguousMatchError:
        ok(True, "two same-name forms -> refuse, never the first")
    ex4 = RecordingExecutor()
    ex4.forms["form_9"] = {"native_id": "form_9", "name": "ZHC Lead Form"}
    rec4 = create_or_reuse_form(ex4, spec())
    ok(rec4.reused and rec4.native_id == "form_9" and "create_form" not in ex4.calls,
       "exact unique name match reuses without create")

    # 4 — required state SET AND READ BACK, both directions (owner order gap 2)
    ex5 = RecordingExecutor()
    r = create_or_reuse_form(ex5, spec())
    r = configure_fields(ex5, r, spec().fields)
    ok(r.fields["First Name"].required is True and r.fields["First Name"].hidden is False,
       "required=True set and read back")
    ok(r.fields["zhc_podcast_rating"].custom_field_id == "cf_7",
       "custom-field id echoed by readback")
    ok(r.fields["zhc_podcast_rating"].validation == ValidationRule(min_value=1, max_value=5),
       "validation set and read back")
    ok(r.state == ST_CONFIGURED, "configured after confirmed readback")

    ex6 = RecordingExecutor()
    r6 = create_or_reuse_form(ex6, spec())
    opt = (FieldSpec(key="City", label="City", element="City", required=False),)
    r6 = configure_fields(ex6, r6, opt)
    ok(r6.fields["City"].required is False and r6.fields["City"].hidden is False,
       "required=False SET explicitly and read back (never left default)")

    # 5 — blind toggle is a FAILURE, not a success
    ex7 = RecordingExecutor(blind_set=True)
    r7 = create_or_reuse_form(ex7, spec())
    try:
        configure_fields(ex7, r7, spec().fields)
        ok(False, "blind set must fail")
    except ReadbackMismatch:
        ok(True, "unconfirmed set raises ReadbackMismatch")
    ok(r7.state == ST_CREATED, "failed configuration never marked CONFIGURED")
    ok(ex7.calls.count("set_state:First Name:True:False") == MAX_STATE_RETRIES + 1,
       "set+readback retried boundedly before hard failure")

    # 6 — consent set+readback; blind consent fails too
    ex8 = RecordingExecutor()
    r8 = configure_consent(ex8, create_or_reuse_form(ex8, spec()), spec().consent)
    ok(r8.consent is not None and r8.consent.kind == "terms_checkbox"
       and r8.consent.required is True, "consent set and read back")
    ex9 = RecordingExecutor(blind_set=True)
    try:
        configure_consent(ex9, create_or_reuse_form(ex9, spec()), spec().consent)
        ok(False, "blind consent must fail")
    except ReadbackMismatch:
        ok(True, "unconfirmed consent raises")

    # 7 — consumer guard before touching a shared form
    ex10 = RecordingExecutor()
    r10 = create_or_reuse_form(ex10, spec())
    ex10.consumers = ["page-3", "workflow-8"]
    try:
        check_consumers(ex10, r10)
        ok(False, "shared form must refuse unauthorized modification")
    except ConsumerConflictError:
        ok(True, "consumers block modification without authorization")
    ok(check_consumers(ex10, r10, allow_shared_edit=True) == ["page-3", "workflow-8"],
       "authorized shared edit records the consumers")

    # 8 — preservation: successful forms are never deleted
    ex11 = RecordingExecutor()
    r11 = finalize(ex11, configure_consent(ex11,
                   create_or_reuse_form(ex11, spec()), spec().consent))
    try:
        cleanup_scratch(ex11, r11, confirm=True)
        ok(False, "non-scratch delete must refuse")
    except PreservationError:
        ok(True, "PRESERVE-on-success: cleanup intent cannot delete a real form")
    ok(ex11.deleted == [], "nothing deleted")
    ex12 = RecordingExecutor()
    scratch_spec = spec(scratch=True, logical_id="form-scratch-1")
    r12 = create_or_reuse_form(ex12, scratch_spec)
    try:
        cleanup_scratch(ex12, r12, confirm=False)
        ok(False, "unconfirmed scratch delete must refuse")
    except PreservationError:
        ok(True, "scratch delete needs explicit confirm")
    ok(cleanup_scratch(ex12, r12, confirm=True) and ex12.deleted == [r12.native_id],
       "confirmed scratch form deleted")

    # 9 — finalize: VERIFIED only on complete readback; missing output = incomplete
    ok(r11.state == ST_VERIFIED and r11.preserved, "complete readback -> VERIFIED + preserved")
    ok(r11.embed and r11.script and r11.link
       and f'form_1' in r11.embed + r11.script + r11.link,
       "embed/script/link carried from platform readback")
    ex13 = RecordingExecutor(missing_embed=True)
    r13 = finalize(ex13, configure_consent(ex13,
                   create_or_reuse_form(ex13, spec()), spec().consent))
    ok(r13.state == ST_CONFIGURED and r13.incomplete,
       "missing platform output -> INCOMPLETE, never done")
    ok(not r13.readback_complete() or r13.state != ST_VERIFIED,
       "VERIFIED requires complete field readback")

    # 10 — negative controls: injected defects must be caught
    ex14 = RecordingExecutor()
    r14 = create_or_reuse_form(ex14, spec())
    ex14.place_field(r14.native_id, spec().fields[0])
    ex14.forced_field_state[(r14.native_id, "First Name")] = {
        "present": True, "required": False, "hidden": True,
        "custom_field_id": ""}  # injected defect: state did not stick
    try:
        configure_fields(ex14, r14, spec().fields[:1])
        ok(False, "injected state defect must be caught")
    except ReadbackMismatch:
        ok(True, "negative control 1: mismatched readback caught")
    ex15 = RecordingExecutor()
    r15 = create_or_reuse_form(ex15, spec())
    ex15.forms[r15.native_id]["native_id"] = "form_OTHER"  # injected defect: id drift
    ex16 = RecordingExecutor()
    ex16.forms["form_x"] = {"native_id": "form_x", "name": "ZHC Lead Form"}
    ex16.forms["form_y"] = {"native_id": "form_y", "name": "ZHC Lead Form"}
    try:
        create_or_reuse_form(ex16, spec())
        ok(False, "injected duplicate defect must be caught")
    except AmbiguousMatchError:
        ok(True, "negative control 2: duplicate-name defect caught")

    print(f"OK forms self-check: {passed} assertions")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selfcheck())
