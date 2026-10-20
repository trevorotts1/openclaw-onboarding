#!/usr/bin/env python3
"""Signature Launch launch-context import for Skill 71 (S71-02).

Validates a Signature Launch page-request document (1.0, or 1.1
carrying its prompt_policy_id citation) (and, when supplied, the launch
record, the route graph, and the popup consent statements) against the
schemas vendored in references/: the frozen 1.0 shapes from S49's
candidate PR #2137 at commit a2bd2c5a (schema source of record),
extended to dual-accept form by the PP-Y2 adoption build (adoption map
section 1.1) with the Q12 prompt-policy citation field and the pair
rule the landed PP-T2 switch enforces (a 1.1 request must carry a
non-empty prompt_policy_id, a 1.0 request must not carry the field).
The import maps the
approved launch context into the run's intake, and prepares the run
artifacts the profile emits at intake:

  page-request.json          the validated request, verbatim (run root;
                             the S71-05 handoff reads it there)
  launch.json                the validated launch record, verbatim, when
                             supplied (the handoff reads journey_mode here)
  <route_graph_ref>          the validated route graph, verbatim, when
                             supplied (the handoff resolves it by this ref)
  launch/popup-config.json   the branded interest popup's config in the
                             S71-07 component's config shape, consent
                             statements carried verbatim, never invented
  launch/design-tokens.css   the design tokens component's tokens_to_css()
                             output for the run's brand, when the shared
                             component is present in the tree

Validation is fail-closed: the first violation raises LaunchContextError
naming the violation, and the caller writes nothing. The schemas are the
authority: this module interprets the vendored schema documents (the
JSON Schema subset they use) rather than a hand transcription, so the
checks cannot drift from the frozen contracts.

Profile: signature_launch_landing (packet doc 07 section 3). Skill 71's
import accepts only a landing request assigned to Skill 71.
"""
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import copy_forms  # noqa: E402  the one registry of copy forms

PROFILE_NAME = "signature_launch_landing"
SKILL_NUMBER = 71

# Fix 3 shared image service: the four image stages for every page role
# are produced by this skill. A page-request carries this marker only
# when it enters through scripts/shared_page_service.py; the two
# landing-only refusals below lift for those requests and no others.
SHARED_SERVICE_MARKER = "shared_image_service"
SHARED_SERVICE_ID = "71-blackceo-signature-page"
SHARED_SERVICE_SKILLS = (71, 78, 79, 80, 81, 82)
# page-request copy_profile -> the copy_version (references/copy-specs/<v>-v6.json) the
# image stages check section counts against. An unmapped profile records none.
COPY_PROFILE_VERSION = {"standard": "standard", "long-form": "long-form",
                        "signature-upsell-eight-section": "upsell"}

SCHEMA_FILES = {
    "page-request": "page-request.schema.json",
    "launch": "launch.schema.json",
    "route-graph": "route-graph.schema.json",
}

# The prompt-policy registry of record (Q13): the citation vocabulary
# for a 1.1 request's prompt_policy_id. It lives in the shared domain
# folder beside this skill's tree, the same cross-tree reach
# emit_design_tokens makes for the design tokens component.
PROMPT_POLICY_REGISTRY_REF = (
    "shared-utils/signature_launch/domain/prompt-policy-registry.json")

# The interest popup component's contract (shared component interest-popup
# 1.0.0, owner S71, built by S71-07): the fixed field set, its native
# field map (the identity map: the native form uses exactly these field
# names), the default id prefix, and the event a verified capture emits.
POPUP_COMPONENT = "interest-popup"
POPUP_COMPONENT_VERSION = "1.0.0"
POPUP_ID_PREFIX = "sl-interest"
POPUP_FIELDS = ("first_name", "last_name", "email", "phone")
POPUP_EVENT = "sl:interest-capture"

# The design components' recorded identities (S71-07 component record):
# produced pages under the profile include design.css and the tokens
# component's CSS output for the run's brand.
DESIGN_CSS_REF = "shared-utils/signature_launch/design/design.css"
DESIGN_CSS_SHA256 = "68f6084ba8e86cb32622bbf799b49b16a518c4c348481dcbe2f992200cda2cce"
TOKENS_COMPONENT_REF = "shared-utils/signature_launch/design/tokens/tokens.py"
TOKENS_COMPONENT_VERSION = "1.0.0"

# Page-result next-role vocabulary for a landing page (packet doc 07
# section 5): after a verified interest submission the launch advances to
# product selection, to checkout, or (free-entry journeys) to the
# terminal thank-you page recorded as free_entry.
NEXT_ROLES = ("product_selection", "checkout", "free_entry")

IDENTITY_FIELDS = ("tenant_id", "location_id", "launch_id", "revision")


def _page_role():
    """scripts/page_role.py: the copy versions a copy_profile may map to (landing forms and
    each page type's own form)."""
    spec = importlib.util.spec_from_file_location(
        "page_role", Path(__file__).resolve().parent / "page_role.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LaunchContextError(Exception):
    """A named launch-context violation; the import writes nothing."""


# ---------------------------------------------------------------------------
# Minimal JSON Schema interpreter for the subset the vendored schemas use
# (type incl. type lists, const, enum, required, properties,
# additionalProperties: false, items, minItems, minLength, minimum,
# pattern, allOf with if/then). Returns a list of named violations.
# ---------------------------------------------------------------------------

def _type_name(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, (int, float)):
        return "number"
    return type(value).__name__


def _is_integer(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and value.is_integer()


def _type_ok(value, want):
    if want == "string":
        return isinstance(value, str)
    if want == "boolean":
        return isinstance(value, bool)
    if want == "null":
        return value is None
    if want == "array":
        return isinstance(value, list)
    if want == "object":
        return isinstance(value, dict)
    if want == "integer":
        return _is_integer(value)
    if want == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True


def validate(instance, schema, path="$", label="document"):
    """Collect violations of `schema` by `instance`; [] means valid."""
    problems = []
    if not isinstance(schema, dict):
        return problems
    for clause in schema.get("allOf", []) or []:
        if isinstance(clause, dict) and "if" in clause and "then" in clause:
            if not validate(instance, clause["if"], path, label):
                problems.extend(validate(instance, clause["then"], path, label))
        else:
            problems.extend(validate(instance, clause, path, label))
    want = schema.get("type")
    if want is not None:
        wants = want if isinstance(want, list) else [want]
        if not any(_type_ok(instance, w) for w in wants):
            problems.append(
                f"{label}: {path}: expected type {' or '.join(wants)}, "
                f"got {_type_name(instance)}")
            return problems
    if "const" in schema and instance != schema["const"]:
        problems.append(
            f"{label}: {path}: must be {schema['const']!r}, got {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        problems.append(
            f"{label}: {path}: {instance!r} is not one of {schema['enum']}")
    if isinstance(instance, str):
        if schema.get("minLength") is not None and len(instance) < schema["minLength"]:
            problems.append(
                f"{label}: {path}: string shorter than minLength "
                f"{schema['minLength']}")
        if schema.get("pattern") and not re.search(schema["pattern"], instance):
            problems.append(
                f"{label}: {path}: {instance!r} does not match pattern "
                f"{schema['pattern']!r}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if schema.get("minimum") is not None and instance < schema["minimum"]:
            problems.append(
                f"{label}: {path}: {instance} is below minimum "
                f"{schema['minimum']}")
    if isinstance(instance, list):
        if schema.get("minItems") is not None and len(instance) < schema["minItems"]:
            problems.append(
                f"{label}: {path}: has {len(instance)} item(s), fewer than "
                f"minItems {schema['minItems']}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(instance):
                problems.extend(validate(item, item_schema, f"{path}[{i}]", label))
    if isinstance(instance, dict):
        for key in schema.get("required", []) or []:
            if key not in instance:
                problems.append(f"{label}: {path}: missing required field {key!r}")
        props = schema.get("properties", {}) or {}
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in props:
                    problems.append(
                        f"{label}: {path}: additional property {key!r} is not "
                        f"allowed by the schema")
        for key, subschema in props.items():
            if key in instance and isinstance(subschema, dict):
                problems.extend(validate(instance[key], subschema,
                                         f"{path}.{key}", label))
    return problems


def _load_schema(skill_root, kind):
    path = Path(skill_root) / "references" / SCHEMA_FILES[kind]
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LaunchContextError(
            f"frozen {kind} schema unreadable at {path}: {exc}; the import "
            f"validates against the vendored schema and cannot proceed "
            f"without it")


def _registry_policy_ids(skill_root):
    """The active policy ids minted by the prompt-policy registry of
    record (Q13). Fail-closed, with the same discipline as
    _load_schema: a 1.1 citation can only be checked against a
    registry that can be read, so an unreadable or malformed registry
    refuses the import rather than letting the citation pass
    unverified."""
    path = Path(skill_root).parent / PROMPT_POLICY_REGISTRY_REF
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
        return {entry["policy_id"] for entry in registry["entries"]
                if isinstance(entry, dict)
                and entry.get("entry_status") == "active"
                and isinstance(entry.get("policy_id"), str)}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise LaunchContextError(
            f"prompt-policy registry of record unreadable at {path}: "
            f"{exc}; a 1.1 request's prompt_policy_id is a citation "
            f"minted by that registry only, and the import cannot "
            f"verify the citation without it")


def _load_document(path, label):
    p = Path(path)
    try:
        raw = p.read_bytes()
    except OSError as exc:
        raise LaunchContextError(f"{label}: cannot read {p}: {exc}")
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise LaunchContextError(f"{label}: {p} is not valid JSON: {exc}")
    if not isinstance(doc, dict):
        raise LaunchContextError(f"{label}: {p} is not a JSON object")
    return doc, raw


def sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def _resolve_existing(skill_root, run_dir, ref):
    """First existing file among ref as given, skill-root-relative, and
    run-dir-relative; None when the ref resolves to no file."""
    for candidate in (Path(ref), Path(skill_root) / ref, Path(run_dir) / ref):
        if candidate.is_file():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Consent statements (the popup component's config shape). No frozen 1.0
# schema carries consent statements (the launch schema has no
# communication/consent group), so they arrive as an import input in the
# component's own shape: a JSON list of {id, text, required} objects.
# They are carried verbatim; the import never invents statement text.
# ---------------------------------------------------------------------------

def load_consent_statements(path):
    p = Path(path)
    try:
        raw = p.read_bytes()
    except OSError as exc:
        raise LaunchContextError(f"consent statements: cannot read {p}: {exc}")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise LaunchContextError(f"consent statements: {p} is not valid JSON: {exc}")
    if not isinstance(data, list):
        raise LaunchContextError(
            "consent statements: the document must be a JSON list of "
            "{id, text, required} objects (the interest popup component's "
            "config shape)")
    seen = set()
    for i, entry in enumerate(data):
        where = f"consent statements[{i}]"
        if not isinstance(entry, dict):
            raise LaunchContextError(f"{where}: not an object")
        extra = sorted(set(entry) - {"id", "text", "required"})
        if extra:
            raise LaunchContextError(
                f"{where}: additional field(s) {extra}; the component's "
                f"statement shape is exactly id, text, required")
        for key in ("id", "text"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise LaunchContextError(f"{where}: {key!r} must be a non-empty string")
        if not isinstance(entry.get("required"), bool):
            raise LaunchContextError(f"{where}: 'required' must be a boolean")
        if entry["id"] in seen:
            raise LaunchContextError(
                f"{where}: duplicate consent statement id {entry['id']!r}")
        seen.add(entry["id"])
    return data


# ---------------------------------------------------------------------------
# Routing: the approved next role, derived by the same rule the S71-05
# handoff applies at report time (the landing node's interest_submitted
# edge; free_entry only for a free_entry journey ending at thank_you).
# ---------------------------------------------------------------------------

def derive_next_role(request, graph, launch):
    """Return (next_role, next_page_id, basis). Refuses a graph whose
    landing routing contradicts the approved vocabulary or journey."""
    nodes = {n["page_id"]: n for n in graph["nodes"]}
    shared = (request.get(SHARED_SERVICE_MARKER) == SHARED_SERVICE_ID)
    landing = nodes.get(request["page_id"])
    if landing is None:
        raise LaunchContextError(
            f"route graph: no node carries the request's page_id "
            f"{request['page_id']!r}; the request's page is not in the "
            f"approved route graph")
    if shared and landing["role"] != request["page_role"]:
        raise LaunchContextError(
            f"route graph: the request's page {request['page_id']!r} has "
            f"role {landing['role']!r} in the graph, not the request's "
            f"{request['page_role']!r}")
    if landing["role"] != "landing":
        if shared:
            # Fix 3 shared image service: a non-landing page has no
            # intake-time next role; its page result reads the route
            # graph at report time (scripts/page_result.py).
            return None, None, (
                "non-landing shared-service page: no intake-time next "
                "role; the report-time page-result emitter reads the "
                "route graph")
        raise LaunchContextError(
            f"route graph: the request's page {request['page_id']!r} has "
            f"role {landing['role']!r} in the graph, not 'landing'")
    edges = [e for e in graph["edges"]
             if e["from"] == request["page_id"] and e["event"] == "interest_submitted"]
    if not edges:
        raise LaunchContextError(
            f"route graph: no interest_submitted edge leaves the landing "
            f"node {request['page_id']!r}; the approved next role cannot "
            f"be derived")
    edge = edges[0]
    target = nodes.get(edge["to"])
    if target is None:
        raise LaunchContextError(
            f"route graph: interest_submitted edge targets unknown page "
            f"{edge['to']!r}")
    role = target["role"]
    if role in ("product_selection", "checkout"):
        return role, edge["to"], "route graph interest_submitted edge"
    if role == "thank_you":
        if launch is None:
            return None, edge["to"], (
                "landing advances to the terminal thank_you node; "
                "free_entry requires the launch record's journey_mode, "
                "which was not supplied")
        if launch["journey_mode"] == "free_entry":
            return "free_entry", edge["to"], (
                "route graph interest_submitted edge to the terminal "
                "thank_you node under a free_entry journey")
        raise LaunchContextError(
            f"route graph: interest_submitted sends the landing page to "
            f"thank_you node {edge['to']!r}, but the launch journey_mode "
            f"is {launch['journey_mode']!r}; free_entry routing requires "
            f"a free_entry journey")
    raise LaunchContextError(
        f"route graph: interest_submitted sends the landing page to "
        f"{edge['to']!r} with role {role!r}; a landing page may advance "
        f"only to product_selection, checkout, or an approved free-entry "
        f"thank_you (packet doc 07 section 5)")


# ---------------------------------------------------------------------------
# Design assets: the tokens component's CSS for the run's brand, when the
# shared component is in the tree. The resolver never invents values:
# brand values that are absent resolve to None and are named, exactly as
# the component records them. Pre-assembly trees (the component lands
# with the S71 candidate) record the component's absence instead of a
# substitute output.
# ---------------------------------------------------------------------------

def tokens_component_path(skill_root):
    return Path(skill_root).parent / TOKENS_COMPONENT_REF


def emit_design_tokens(skill_root, brand_file):
    """Return (css_text_or_None, record). Never raises for a missing
    component; raises LaunchContextError when the component is present
    but the brand cannot be resolved through it."""
    record = {"component": f"design-tokens@{TOKENS_COMPONENT_VERSION}",
              "component_ref": TOKENS_COMPONENT_REF}
    comp = tokens_component_path(skill_root)
    if not comp.is_file():
        record.update({"status": "component_not_in_tree", "path": None,
                       "missing_tokens": None})
        return None, record
    if brand_file is None or not Path(brand_file).is_file():
        raise LaunchContextError(
            f"design tokens: the tokens component is present at {comp} "
            f"but the run's brand file {brand_file} cannot be read; the "
            f"profile cannot emit the tokens CSS without the approved brand")
    try:
        brand = json.loads(Path(brand_file).read_text(encoding="utf-8"))
    except ValueError as exc:
        raise LaunchContextError(
            f"design tokens: brand file {brand_file} is not valid JSON: {exc}")
    try:
        spec = importlib.util.spec_from_file_location("signature_launch_tokens", comp)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        resolution = mod.resolve_tokens(brand)
        css = mod.tokens_to_css(resolution)
    except Exception as exc:
        raise LaunchContextError(
            f"design tokens: the tokens component at {comp} failed on the "
            f"run's brand: {exc}")
    record.update({"status": "emitted", "path": "launch/design-tokens.css",
                   "missing_tokens": list(resolution.get("missing") or []),
                   "brand_id": resolution.get("brand_id"),
                   "token_version": resolution.get("token_version")})
    return css, record


# ---------------------------------------------------------------------------
# The import itself.
# ---------------------------------------------------------------------------

def prepare_import(skill_root, run_dir, request_path, launch_path=None,
                   graph_path=None, consent_path=None, brand_file=None):
    """Validate everything, in memory, before anything is written.

    Returns (intake_updates, artifacts): intake_updates carries the
    top-level intake fields the profile sets (image_engine / copy_version
    / test_run overrides plus launch_profile and the launch block);
    artifacts maps run-relative paths to the exact bytes to write.
    Raises LaunchContextError naming the first violation.
    """
    skill_root = Path(skill_root)
    run_dir = Path(run_dir)

    request, request_raw = _load_document(request_path, "page-request")
    problems = validate(request, _load_schema(skill_root, "page-request"),
                        label="page-request")
    if problems:
        raise LaunchContextError("; ".join(problems))
    shared = (request.get(SHARED_SERVICE_MARKER) == SHARED_SERVICE_ID)
    if request["page_role"] != "landing" and not shared:
        raise LaunchContextError(
            f"page-request: page_role is {request['page_role']!r}; this "
            f"import is Skill 71's landing import (profile "
            f"{PROFILE_NAME}); other roles belong to their own skills")
    if request["assigned_skill"] != SKILL_NUMBER:
        if not (shared
                and request["assigned_skill"] in SHARED_SERVICE_SKILLS):
            raise LaunchContextError(
                f"page-request: assigned_skill is "
                f"{request['assigned_skill']!r}; this import serves "
                f"Skill {SKILL_NUMBER} only")
    # The prompt-policy pair rule (adoption map section 1.1; the same
    # rule the landed PP-T2 switch enforces in
    # dispatch_launch.validate_request): the 1.1 label exists to carry
    # the citation field. The vendored schema's allOf already refuses
    # a 1.1 request without the field; the schema subset cannot
    # express the 1.0 side, so it is checked here, beside the role and
    # skill checks. A carried citation must name a policy the registry
    # of record minted (Q12: the name is minted by the common registry
    # only; the citation names the governing policy and records no
    # selection).
    if request["schema_version"] == "1.0" and "prompt_policy_id" in request:
        raise LaunchContextError(
            "page-request: prompt_policy_id requires request "
            "schema_version 1.1 (the 1.0 schema forbids the field)")
    if "prompt_policy_id" in request:
        policy_id = request["prompt_policy_id"]
        if policy_id not in _registry_policy_ids(skill_root):
            raise LaunchContextError(
                f"page-request: prompt_policy_id {policy_id!r} is not "
                f"an active policy id in the prompt-policy registry "
                f"of record ({PROMPT_POLICY_REGISTRY_REF}); the "
                f"citation must name a policy the registry minted")
    ref = request["route_graph_ref"]
    if Path(ref).is_absolute() or ".." in Path(ref).parts:
        raise LaunchContextError(
            f"page-request: route_graph_ref {ref!r} is not a run-relative "
            f"path; the route graph is placed inside the run directory")

    launch = None
    launch_raw = None
    if launch_path is not None:
        launch, launch_raw = _load_document(launch_path, "launch record")
        problems = validate(launch, _load_schema(skill_root, "launch"),
                            label="launch record")
        if problems:
            raise LaunchContextError("; ".join(problems))
        for field in IDENTITY_FIELDS + ("brand_ref", "brand_hash",
                                        "route_graph_ref", "route_graph_hash"):
            if launch[field] != request[field]:
                raise LaunchContextError(
                    f"launch record: {field} is {launch[field]!r} but the "
                    f"page-request carries {request[field]!r}; the launch "
                    f"context must agree with the request it approves")
        if launch.get("prompt_policy_id") != request.get("prompt_policy_id"):
            raise LaunchContextError(
                f"launch record: prompt_policy_id is "
                f"{launch.get('prompt_policy_id')!r} but the "
                f"page-request carries "
                f"{request.get('prompt_policy_id')!r}; the launch "
                f"context must agree with the request it approves")
        if launch["status"] not in ("approved", "building"):
            raise LaunchContextError(
                f"launch record: status is {launch['status']!r}; a page "
                f"build import requires an approved launch (status "
                f"'approved' or 'building')")
        if launch["test_only"] != request["test_only"]:
            raise LaunchContextError(
                f"launch record: test_only is {launch['test_only']} but "
                f"the page-request carries {request['test_only']}; the "
                f"context must agree on whether the run is a test")

    graph = None
    graph_raw = None
    next_role = next_page_id = None
    next_basis = "route graph not supplied; next role not derived"
    if graph_path is not None:
        graph, graph_raw = _load_document(graph_path, "route graph")
        problems = validate(graph, _load_schema(skill_root, "route-graph"),
                            label="route graph")
        if problems:
            raise LaunchContextError("; ".join(problems))
        actual = sha256_bytes(graph_raw)
        if actual != request["route_graph_hash"]:
            raise LaunchContextError(
                f"route graph: SHA-256 of the supplied graph is {actual} "
                f"but the page-request records route_graph_hash "
                f"{request['route_graph_hash']}; stale routing is refused")
        for field in IDENTITY_FIELDS:
            if graph[field] != request[field]:
                raise LaunchContextError(
                    f"route graph: {field} is {graph[field]!r} but the "
                    f"page-request carries {request[field]!r}")
        next_role, next_page_id, next_basis = derive_next_role(request, graph, launch)

    consent = []
    consent_supplied = False
    if consent_path is not None:
        consent = load_consent_statements(consent_path)
        consent_supplied = True

    # Brand cross-check: when brand_ref resolves to a file, its bytes must
    # hash to the approved brand_hash, and it must be the brand file the
    # run gates against.
    brand_hash_check = "not_a_file_ref"
    brand_resolved = _resolve_existing(skill_root, run_dir, request["brand_ref"])
    if brand_resolved is not None:
        actual = sha256_bytes(brand_resolved.read_bytes())
        if actual != request["brand_hash"]:
            raise LaunchContextError(
                f"page-request: brand_ref {request['brand_ref']!r} resolves "
                f"to {brand_resolved}, whose SHA-256 is {actual}, not the "
                f"approved brand_hash {request['brand_hash']}")
        brand_hash_check = "matched"
        if brand_file:
            run_brand = _resolve_existing(skill_root, run_dir, brand_file)
            if run_brand is not None and run_brand.resolve() != brand_resolved.resolve():
                raise LaunchContextError(
                    f"page-request: brand_ref resolves to {brand_resolved} "
                    f"but the intake brand file is {run_brand}; the run "
                    f"must gate against the approved brand")

    # Field mapping into the run's intake (packet doc 07 section 5,
    # doc 02 section 2). The launch context fills the fields it carries;
    # skill-local decisions it does not carry (page_version, image_cap,
    # brand_owner) stay with the operator's intake answers.
    updates = {}
    if launch is not None:
        provider = launch["image_provider"]
        if provider == "other_explicit":
            raise LaunchContextError(
                "launch record: image_provider is 'other_explicit'; this "
                "skill's intake records image_engine 'kie' or 'agnes' "
                "only, so an explicitly named other provider must be "
                "resolved before intake, not silently defaulted")
        updates["image_engine"] = provider
    copy_version = COPY_PROFILE_VERSION.get(request["copy_profile"])
    if copy_version is None and request["copy_profile"] in copy_forms.FORMS:
        copy_version = request["copy_profile"]  # a copy_profile that names a registered form is that form
    copy_mapped = copy_version is not None
    if copy_mapped:
        updates["copy_version"] = copy_version
    # a shared-service page of another role is built from that role's own form: the request's
    # copy_profile names the landing page's copy, which this page does not carry
    role_form = copy_forms.form_for_role(request["page_role"]) if shared else None
    if role_form:
        copy_mapped = True
        updates["copy_version"] = role_form
    if request["test_only"]:
        updates["test_run"] = True

    design_brand = None
    if brand_file:
        design_brand = _resolve_existing(skill_root, run_dir, brand_file)
    if design_brand is None:
        design_brand = brand_resolved
    css, tokens_record = emit_design_tokens(skill_root, design_brand)

    launch_block = {
        "schema_version": request["schema_version"],
        "prompt_policy_id": request.get("prompt_policy_id"),
        "request_id": request["request_id"],
        "input_hash": request["input_hash"],
        "tenant_id": request["tenant_id"],
        "location_id": request["location_id"],
        "launch_id": request["launch_id"],
        "revision": request["revision"],
        "page_id": request["page_id"],
        "page_role": request["page_role"],
        "assigned_skill": request["assigned_skill"],
        "approval_ref": request["approval_ref"],
        "brand_ref": request["brand_ref"],
        "brand_hash": request["brand_hash"],
        "brand_hash_check": brand_hash_check,
        "route_graph_ref": request["route_graph_ref"],
        "route_graph_hash": request["route_graph_hash"],
        "route_graph_placed": graph is not None,
        "offer_refs": list(request["offer_refs"]),
        "copy_profile": request["copy_profile"],
        "copy_profile_mapped": copy_mapped,
        "allowed_write_target": request["allowed_write_target"],
        "test_only": request["test_only"],
        "journey_mode": launch["journey_mode"] if launch else None,
        "image_provider": launch["image_provider"] if launch else None,
        "plan_approval_ref": launch["plan_approval_ref"] if launch else None,
        "next_role": next_role,
        "next_page_id": next_page_id,
        "next_role_basis": next_basis,
        "page_request_ref": "page-request.json",
        "launch_record_ref": "launch.json" if launch is not None else None,
        "popup_config_ref": "launch/popup-config.json",
        "consent_source": "launch_context_import" if consent_supplied else None,
        "design_assets": {
            "design_css": {"component_file": DESIGN_CSS_REF,
                           "sha256": DESIGN_CSS_SHA256},
            "design_tokens_css": tokens_record,
        },
    }
    updates["launch_profile"] = PROFILE_NAME
    updates["launch"] = launch_block

    popup_config = {
        "component": POPUP_COMPONENT,
        "component_version": POPUP_COMPONENT_VERSION,
        "id_prefix": POPUP_ID_PREFIX,
        "fields": list(POPUP_FIELDS),
        "native_field_map": {f: f for f in POPUP_FIELDS},
        "consent_statements": consent,
        "consent_source": "launch_context_import" if consent_supplied else None,
        "events": [POPUP_EVENT],
    }

    artifacts = {
        "page-request.json": request_raw,
        "launch/popup-config.json": (
            json.dumps(popup_config, indent=2) + "\n").encode("utf-8"),
    }
    if launch_raw is not None:
        artifacts["launch.json"] = launch_raw
    if graph_raw is not None:
        artifacts[request["route_graph_ref"]] = graph_raw
    if css is not None:
        artifacts["launch/design-tokens.css"] = css.encode("utf-8")
    return updates, artifacts


def write_artifacts(run_dir, artifacts):
    """Write the prepared artifacts under the run directory. Called only
    after intake.json itself is written, with every byte already
    validated and prepared in memory."""
    run_dir = Path(run_dir)
    for rel, raw in artifacts.items():
        target = run_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
