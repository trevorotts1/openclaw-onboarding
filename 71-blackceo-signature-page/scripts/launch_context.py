#!/usr/bin/env python3
"""Signature Launch launch-context import for Skill 71 (S71-02).

Validates a Signature Launch page-request 1.0 document (and, when supplied,
the launch record, the route graph, and the popup consent statements)
against the frozen 1.0 schemas vendored in references/ from S49's
candidate PR #2137 at commit a2bd2c5a (schema source of record), maps the
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
from pathlib import Path

PROFILE_NAME = "signature_launch_landing"
SKILL_NUMBER = 71

SCHEMA_FILES = {
    "page-request": "page-request.schema.json",
    "launch": "launch.schema.json",
    "route-graph": "route-graph.schema.json",
}

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


class LaunchContextError(Exception):
    """A named launch-context violation; the import writes nothing."""


# ---------------------------------------------------------------------------
# Minimal JSON Schema interpreter for the subset the frozen 1.0 schemas use
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
    landing = nodes.get(request["page_id"])
    if landing is None:
        raise LaunchContextError(
            f"route graph: no node carries the request's page_id "
            f"{request['page_id']!r}; the request's page is not in the "
            f"approved route graph")
    if landing["role"] != "landing":
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
    if request["page_role"] != "landing":
        raise LaunchContextError(
            f"page-request: page_role is {request['page_role']!r}; this "
            f"import is Skill 71's landing import (profile "
            f"{PROFILE_NAME}); other roles belong to their own skills")
    if request["assigned_skill"] != SKILL_NUMBER:
        raise LaunchContextError(
            f"page-request: assigned_skill is {request['assigned_skill']!r}; "
            f"this import serves Skill {SKILL_NUMBER} only")
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
    copy_mapped = request["copy_profile"] in ("standard", "long-form")
    if copy_mapped:
        updates["copy_version"] = request["copy_profile"]
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
