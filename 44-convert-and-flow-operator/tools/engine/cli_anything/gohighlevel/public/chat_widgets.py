"""Chat Widgets family adapter (WF31, implementation spec section 28).

Contract source: the vendor OpenAPI document
``apps/v3/chat-widget-v3.json`` in ``GoHighLevel/highlevel-api-docs``, read
2026-11-08.  This module carries no HTTP method, path or Version literal into a
request: every call goes through :class:`PublicGhlAdapter`, whose registry row
owns method, path and the per-operation ``Version: v3`` header.

Two version numbers must never be confused:

* the HTTP ``Version: v3`` header comes from the operation row only;
* the widget *configuration* version is a NUMERIC body field (the create DTO
  requires it, example ``2``).  It is validated here and travels untouched.

Write-type allowlist and read-type enum are deliberately different.  The create
and update DTOs accept only ``liveChat`` and ``emailChat``.  The broader list of
types (``waChat``, ``allInOneChat``, ``voiceAiChat``, ``facebookChat``,
``instagramChat``, ``webChat``) appears only in read/query results; seeing one
there never authorises a create.

The widget schema names its identifier ``_id``.  :func:`extract_widget_id` reads
``_id`` and nothing else; there is no universal ``id`` fallback.

No embed script URL, attribute or token is ever synthesised here.  An embed is
data captured from an authorised source and is accepted only with its exact
snippet, provenance and evidence reference.  Rendered display checks and an
actual thread/inbox/responder check are separate proofs; a visible chat bubble
is never evidence that a message reached the right inbox.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

DOC_FETCH_DATE = "2026-11-08"
DOC_URL = (
    "https://raw.githubusercontent.com/GoHighLevel/highlevel-api-docs/main/"
    "apps/v3/chat-widget-v3.json"
)
#: Header value the WF00 registry rows must carry.  Documentation only: this
#: module never adds the header; the row does.
WIDGET_HTTP_VERSION = "v3"

#: The only chat types accepted by the create/update DTOs.
CREATE_CHAT_TYPES: tuple[str, ...] = ("liveChat", "emailChat")
#: The broader enum that may appear in list/query results.  Never a write enum.
READ_CHAT_TYPES: tuple[str, ...] = (
    "liveChat",
    "waChat",
    "emailChat",
    "allInOneChat",
    "voiceAiChat",
    "facebookChat",
    "instagramChat",
    "webChat",
)

#: Operation ids this family consumes.  The rows belong to WF00
#: (``public/operations.py``); this module only names them, never dispatches.
WIDGET_OPERATIONS: dict[str, str] = {
    "list": "chat_widgets.list",
    "get": "chat_widgets.get",
    "create": "chat_widgets.create",
    "update": "chat_widgets.update",
    "patch": "chat_widgets.patch",
    "delete": "chat_widgets.delete",
    "clone": "chat_widgets.clone",
    "public_config": "chat_widgets.public_config",
}

PAGE_EMBED_SLOTS: tuple[str, ...] = ("head", "body", "headerCode", "footerCode")
EMBED_PROVENANCE: frozenset[str] = frozenset(
    {"captured_ui", "provider_documentation", "api_public_config"}
)


class WidgetError(ValueError):
    """Family refusal.  Carries a machine rule and safe names only."""

    rule = "widget_error"

    def __init__(self, rule: str | None = None, **detail: Any) -> None:
        self.rule = rule or type(self).rule
        self.detail = {k: v for k, v in detail.items() if v is not None}
        parts = [self.rule]
        for key in sorted(self.detail):
            parts.append(f"{key}={self.detail[key]}")
        super().__init__(": ".join(parts))


class WidgetTypeNotWritable(WidgetError):
    rule = "widget_type_not_writable"


class WidgetSchemaError(WidgetError):
    rule = "widget_schema_invalid"


class EmbedInstructionError(WidgetError):
    rule = "embed_instruction_invalid"


class DuplicateEmbed(WidgetError):
    rule = "duplicate_embed"


class RenderedCheckIncomplete(WidgetError):
    rule = "rendered_check_incomplete"


class ConversationEvidenceInvalid(WidgetError):
    rule = "conversation_evidence_invalid"


# ---------------------------------------------------------------------------
# create / update bodies
# ---------------------------------------------------------------------------

_PLACEHOLDER = frozenset(
    {"", "tbd", "todo", "none", "null", "changeme", "change-me", "placeholder"}
)


def _required_text(value: Any, name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text or text.lower() in _PLACEHOLDER:
        raise WidgetSchemaError("field_required", field=name)
    return text


def _numeric_config_version(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WidgetSchemaError(
            "config_version_must_be_number", kind=type(value).__name__
        )
    if value < 0:
        raise WidgetSchemaError("config_version_negative", value=value)
    return value


def _write_chat_type(value: Any) -> str:
    text = str(value) if value is not None else ""
    if text not in CREATE_CHAT_TYPES:
        if text in READ_CHAT_TYPES:
            raise WidgetTypeNotWritable(
                "read_enum_is_not_a_write_enum",
                chat_type=text,
                allowed=",".join(CREATE_CHAT_TYPES),
            )
        raise WidgetTypeNotWritable(
            "chat_type_unsupported",
            chat_type=text or "<empty>",
            allowed=",".join(CREATE_CHAT_TYPES),
        )
    return text


def build_create_body(
    *,
    location_id: str,
    name: str,
    chat_type: str,
    version: int,
    settings: Mapping[str, Any] | None = None,
    default: bool | None = None,
    deleted: bool | None = None,
) -> dict[str, Any]:
    """Build the create DTO body.

    ``version`` is the numeric widget configuration version, never the HTTP
    Version header.  ``settings`` is copied verbatim: a value inside the read
    settings schema (for example ``allInOneChatTypes``) is not promoted into the
    create ``chatType`` field.
    """

    body: dict[str, Any] = {
        "locationId": _required_text(location_id, "location_id"),
        "name": _required_text(name, "name"),
        "chatType": _write_chat_type(chat_type),
        "version": _numeric_config_version(version),
    }
    if settings is not None:
        if not isinstance(settings, Mapping):
            raise WidgetSchemaError("settings_not_mapping")
        body["settings"] = copy.deepcopy(dict(settings))
    if default is not None:
        if not isinstance(default, bool):
            raise WidgetSchemaError("default_not_boolean")
        body["default"] = default
    if deleted is not None:
        if not isinstance(deleted, bool):
            raise WidgetSchemaError("deleted_not_boolean")
        body["deleted"] = deleted
    return body


def build_update_body(
    *,
    chat_type: str | None = None,
    version: int | None = None,
    name: str | None = None,
    settings: Mapping[str, Any] | None = None,
    default: bool | None = None,
) -> dict[str, Any]:
    """Build an update/patch DTO body.  At least one field is required."""

    body: dict[str, Any] = {}
    if chat_type is not None:
        body["chatType"] = _write_chat_type(chat_type)
    if version is not None:
        body["version"] = _numeric_config_version(version)
    if name is not None:
        body["name"] = _required_text(name, "name")
    if settings is not None:
        if not isinstance(settings, Mapping):
            raise WidgetSchemaError("settings_not_mapping")
        body["settings"] = copy.deepcopy(dict(settings))
    if default is not None:
        if not isinstance(default, bool):
            raise WidgetSchemaError("default_not_boolean")
        body["default"] = default
    if not body:
        raise WidgetSchemaError("update_body_empty")
    return body


# ---------------------------------------------------------------------------
# widget schema: `_id`, never a universal `id`
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WidgetRecord:
    widget_id: str
    name: str | None
    chat_type: str | None
    config_version: int | None
    raw: Mapping[str, Any] = field(repr=False, compare=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "widget_id": self.widget_id,
            "name": self.name,
            "chat_type": self.chat_type,
            "config_version": self.config_version,
        }


def extract_widget_id(payload: Mapping[str, Any]) -> str:
    """Read ``_id`` from a widget payload.

    One documented envelope tolerance: if the object is wrapped under a single
    ``widget`` or ``data`` mapping, the wrapper is unwrapped once.  There is no
    ``id`` fallback: a payload without ``_id`` is a schema failure, because a
    universal extractor is exactly the defect this rule forbids.
    """

    if not isinstance(payload, Mapping):
        raise WidgetSchemaError("widget_payload_not_mapping")
    candidate: Any = payload
    if "_id" not in candidate:
        for wrapper in ("widget", "data"):
            inner = candidate.get(wrapper)
            if isinstance(inner, Mapping) and "_id" in inner:
                candidate = inner
                break
    value = candidate.get("_id")
    if not isinstance(value, str) or not value.strip():
        raise WidgetSchemaError(
            "widget_identifier_missing", field="_id", saw_id="id" in candidate
        )
    return value.strip()


def parse_widget(payload: Mapping[str, Any]) -> WidgetRecord:
    widget_id = extract_widget_id(payload)
    source: Mapping[str, Any] = payload
    if "_id" not in payload:
        for wrapper in ("widget", "data"):
            inner = payload.get(wrapper)
            if isinstance(inner, Mapping) and "_id" in inner:
                source = inner
                break
    config_version = source.get("version")
    if config_version is not None and (
        isinstance(config_version, bool) or not isinstance(config_version, int)
    ):
        raise WidgetSchemaError(
            "config_version_not_number", value_type=type(config_version).__name__
        )
    return WidgetRecord(
        widget_id=widget_id,
        name=source.get("name") if isinstance(source.get("name"), str) else None,
        chat_type=source.get("chatType")
        if isinstance(source.get("chatType"), str)
        else None,
        config_version=config_version,
        raw=copy.deepcopy(dict(source)),
    )


def parse_widget_list(payload: Any) -> list[WidgetRecord]:
    """Normalise a list response that has no published response schema.

    Accepted envelopes are a bare list, ``{"widgets": [...]}`` and
    ``{"data": [...]}``.  Every item must carry ``_id``.  Anything else is a
    loud schema failure, not an empty success.
    """

    items: Any
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, Mapping):
        items = payload.get("widgets", payload.get("data"))
    else:
        items = None
    if not isinstance(items, list):
        raise WidgetSchemaError("widget_list_shape_unknown")
    records: list[WidgetRecord] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise WidgetSchemaError("widget_list_item_not_mapping", index=index)
        record = parse_widget(item)
        if record.widget_id in seen:
            raise WidgetSchemaError("widget_list_duplicate_id", widget_id=record.widget_id)
        seen.add(record.widget_id)
        records.append(record)
    return records


# ---------------------------------------------------------------------------
# embed instruction: captured data only, never synthesised
# ---------------------------------------------------------------------------

_SCRIPT_OR_IFRAME = re.compile(r"<(script|iframe)\b", re.IGNORECASE)
_FORM = re.compile(r"<form\b", re.IGNORECASE)


def _nonempty_mapping(value: Any, name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise EmbedInstructionError("attributes_not_mapping", field=name)
    out: dict[str, str] = {}
    for key, item in value.items():
        key_text = str(key).strip()
        value_text = str(item).strip() if item is not None else ""
        if not key_text or not value_text:
            raise EmbedInstructionError("attribute_incomplete", field=name)
        out[key_text] = value_text
    return out


@dataclass(frozen=True)
class EmbedInstruction:
    """An embed exactly as captured from an authorised source.

    The snippet must already contain ``script_url`` and ``widget_id``; this
    object never builds either.  ``evidence_ref`` names where the capture came
    from and stays in the record so a reviewer can re-check it.
    """

    widget_id: str
    script_url: str
    snippet: str
    provenance: str
    evidence_ref: str
    attributes: Mapping[str, str] = field(default_factory=dict)
    captured_at: str | None = None

    def __post_init__(self) -> None:
        widget_id = str(self.widget_id or "").strip()
        if not widget_id or widget_id.lower() in _PLACEHOLDER:
            raise EmbedInstructionError("field_required", field="widget_id")
        script_url = str(self.script_url or "").strip()
        if not script_url or script_url.lower() in _PLACEHOLDER:
            raise EmbedInstructionError("field_required", field="script_url")
        snippet = str(self.snippet or "")
        provenance = str(self.provenance or "")
        evidence_ref = str(self.evidence_ref or "").strip()
        if not evidence_ref:
            raise EmbedInstructionError("field_required", field="evidence_ref")
        if provenance not in EMBED_PROVENANCE:
            raise EmbedInstructionError(
                "provenance_invalid", provenance=provenance or "<empty>"
            )
        parsed = urlsplit(script_url)
        if parsed.scheme != "https" or not parsed.hostname or "." not in parsed.hostname:
            raise EmbedInstructionError("script_url_not_https_host", url=script_url)
        if parsed.username or parsed.password:
            raise EmbedInstructionError("script_url_has_userinfo")
        if script_url not in snippet:
            raise EmbedInstructionError("snippet_missing_script_url")
        if widget_id not in snippet:
            raise EmbedInstructionError("snippet_missing_widget_id")
        if not _SCRIPT_OR_IFRAME.search(snippet):
            raise EmbedInstructionError("snippet_not_script_or_iframe")
        if _FORM.search(snippet):
            raise EmbedInstructionError("snippet_is_an_html_form")
        attributes = _nonempty_mapping(self.attributes, "attributes")
        object.__setattr__(self, "widget_id", widget_id)
        object.__setattr__(self, "script_url", script_url)
        object.__setattr__(self, "snippet", snippet)
        object.__setattr__(self, "attributes", attributes)
        object.__setattr__(self, "evidence_ref", evidence_ref)

    def as_dict(self) -> dict[str, Any]:
        return {
            "widget_id": self.widget_id,
            "script_url": self.script_url,
            "snippet": self.snippet,
            "provenance": self.provenance,
            "evidence_ref": self.evidence_ref,
            "attributes": dict(self.attributes),
            "captured_at": self.captured_at,
        }


def load_embed_instruction(payload: Mapping[str, Any]) -> EmbedInstruction:
    if not isinstance(payload, Mapping):
        raise EmbedInstructionError("embed_payload_not_mapping")
    missing = [
        name
        for name in ("widget_id", "script_url", "snippet", "provenance", "evidence_ref")
        if not str(payload.get(name) or "").strip()
    ]
    if missing:
        raise EmbedInstructionError("embed_field_missing", fields=",".join(missing))
    return EmbedInstruction(
        widget_id=str(payload["widget_id"]),
        script_url=str(payload["script_url"]),
        snippet=str(payload["snippet"]),
        provenance=str(payload["provenance"]),
        evidence_ref=str(payload["evidence_ref"]),
        attributes=dict(payload.get("attributes") or {}),
        captured_at=payload.get("captured_at"),
    )


# ---------------------------------------------------------------------------
# installation inventory, duplicate detection, page splice
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EmbedOccurrence:
    scope: str
    path: str
    widget_id: str | None = None
    script_url: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "path": self.path,
            "widget_id": self.widget_id,
            "script_url": self.script_url,
        }


def _iter_embed_texts(page_data: Any) -> list[tuple[str, str]]:
    """Every page location where vendor embed code can legitimately live.

    Page design lives in ``sections``; tracking/embed code lives in
    ``trackingCode`` and in custom-code elements.  Both are scanned so a
    duplicate insertion cannot hide in the other surface.
    """

    found: list[tuple[str, str]] = []
    if not isinstance(page_data, Mapping):
        return found
    tracking = page_data.get("trackingCode")
    if isinstance(tracking, Mapping):
        for slot in PAGE_EMBED_SLOTS:
            value = tracking.get(slot)
            if isinstance(value, str) and value:
                found.append((f"trackingCode.{slot}", value))

    def walk(node: Any, path: str) -> None:
        if isinstance(node, Mapping):
            custom = node.get("customCode")
            if isinstance(custom, Mapping):
                value = custom.get("value")
                if isinstance(value, Mapping):
                    raw = value.get("rawCustomCode")
                    if isinstance(raw, str) and raw:
                        found.append((path + ".customCode.value.rawCustomCode", raw))
            for key, item in node.items():
                if isinstance(item, (Mapping, list)):
                    walk(item, f"{path}.{key}")
        elif isinstance(node, list):
            for index, item in enumerate(node):
                if isinstance(item, (Mapping, list)):
                    walk(item, f"{path}[{index}]")

    walk(page_data, "pageData")
    return found


def find_widget_occurrences(
    page_data: Any,
    *,
    widget_id: str | None = None,
    script_url: str | None = None,
    global_snippets: Sequence[str] = (),
) -> list[EmbedOccurrence]:
    """Count exact matches for one widget identity across global + page scope."""

    if widget_id is None and script_url is None:
        raise WidgetError("occurrence_query_empty")
    occurrences: list[EmbedOccurrence] = []
    for index, snippet in enumerate(global_snippets):
        text = str(snippet or "")
        match_widget = bool(widget_id and widget_id in text)
        match_url = bool(script_url and script_url in text)
        if match_widget or match_url:
            occurrences.append(
                EmbedOccurrence(
                    scope="global",
                    path=f"global[{index}]",
                    widget_id=widget_id if match_widget else None,
                    script_url=script_url if match_url else None,
                )
            )
    for path, text in _iter_embed_texts(page_data):
        match_widget = bool(widget_id and widget_id in text)
        match_url = bool(script_url and script_url in text)
        if match_widget or match_url:
            occurrences.append(
                EmbedOccurrence(
                    scope="page",
                    path=path,
                    widget_id=widget_id if match_widget else None,
                    script_url=script_url if match_url else None,
                )
            )
    return occurrences


def assert_single_install(
    page_data: Any,
    instruction: EmbedInstruction,
    *,
    global_snippets: Sequence[str] = (),
) -> None:
    occurrences = find_widget_occurrences(
        page_data,
        widget_id=instruction.widget_id,
        script_url=instruction.script_url,
        global_snippets=global_snippets,
    )
    if occurrences:
        raise DuplicateEmbed(
            "widget_already_installed",
            widget_id=instruction.widget_id,
            count=len(occurrences),
            paths=",".join(item.path for item in occurrences),
        )


@dataclass(frozen=True)
class InstallPlan:
    page_data: dict[str, Any]
    rollback_page_data: dict[str, Any]
    occurrence: EmbedOccurrence
    slot: str
    snippet: str

    def as_evidence(self) -> dict[str, Any]:
        return {
            "scope": self.occurrence.scope,
            "slot": self.slot,
            "widget_id": self.occurrence.widget_id,
            "script_url": self.occurrence.script_url,
            "path": self.occurrence.path,
        }


def plan_page_install(
    page_data: Mapping[str, Any],
    instruction: EmbedInstruction,
    *,
    global_snippets: Sequence[str] = (),
    slot: str = "footerCode",
) -> InstallPlan:
    """Splice one captured embed into page-level tracking code.

    The sections/elements (page design) are copied byte-for-byte and never
    touched.  A widget already present at global or page scope is refused, so a
    second install cannot create the duplicate this rule exists to prevent.
    """

    if not isinstance(instruction, EmbedInstruction):
        raise EmbedInstructionError("embed_instruction_required")
    if slot not in PAGE_EMBED_SLOTS:
        raise WidgetError("embed_slot_invalid", slot=slot)
    if not isinstance(page_data, Mapping):
        raise WidgetError("page_data_not_mapping")
    assert_single_install(
        page_data, instruction, global_snippets=global_snippets
    )
    original = copy.deepcopy(dict(page_data))
    updated = copy.deepcopy(dict(page_data))
    tracking = updated.get("trackingCode")
    if tracking is None:
        tracking = {}
    if not isinstance(tracking, Mapping):
        raise WidgetError("tracking_code_not_mapping")
    tracking = copy.deepcopy(dict(tracking))
    existing = tracking.get(slot) or ""
    if not isinstance(existing, str):
        raise WidgetError("tracking_slot_not_string", slot=slot)
    tracking[slot] = (
        existing.rstrip("\n") + "\n" + instruction.snippet
        if existing.strip()
        else instruction.snippet
    )
    updated["trackingCode"] = tracking

    if updated.get("sections") != original.get("sections"):
        raise WidgetError("page_design_changed")
    occurrences = find_widget_occurrences(
        updated,
        widget_id=instruction.widget_id,
        script_url=instruction.script_url,
        global_snippets=global_snippets,
    )
    if len(occurrences) != 1:
        raise WidgetError("install_not_single", count=len(occurrences))
    return InstallPlan(
        page_data=updated,
        rollback_page_data=original,
        occurrence=occurrences[0],
        slot=slot,
        snippet=instruction.snippet,
    )


def plan_global_install(
    global_snippets: Sequence[str],
    instruction: EmbedInstruction,
    *,
    page_data: Any = None,
) -> tuple[list[str], InstallPlan]:
    """Append one embed to the site-wide snippet list.

    Refused when the widget already exists at either scope.  Page data is only
    read for duplicate detection and is returned unchanged in the plan.
    """

    if not isinstance(instruction, EmbedInstruction):
        raise EmbedInstructionError("embed_instruction_required")
    existing = list(global_snippets or ())
    assert_single_install(page_data, instruction, global_snippets=existing)
    updated = existing + [instruction.snippet]
    occurrences = find_widget_occurrences(
        page_data,
        widget_id=instruction.widget_id,
        script_url=instruction.script_url,
        global_snippets=updated,
    )
    if len(occurrences) != 1:
        raise WidgetError("install_not_single", count=len(occurrences))
    plan = InstallPlan(
        page_data=copy.deepcopy(dict(page_data)) if isinstance(page_data, Mapping) else {},
        rollback_page_data=copy.deepcopy(dict(page_data)) if isinstance(page_data, Mapping) else {},
        occurrence=occurrences[0],
        slot="global",
        snippet=instruction.snippet,
    )
    return updated, plan


def verify_install(
    page_data: Any,
    instruction: EmbedInstruction,
    *,
    global_snippets: Sequence[str] = (),
) -> bool:
    """Exactly one occurrence and the exact captured snippet both present."""

    occurrences = find_widget_occurrences(
        page_data,
        widget_id=instruction.widget_id,
        script_url=instruction.script_url,
        global_snippets=global_snippets,
    )
    if len(occurrences) != 1:
        return False
    corpus = list(global_snippets or ()) + [
        text for _path, text in _iter_embed_texts(page_data)
    ]
    return any(instruction.snippet in text for text in corpus)


# ---------------------------------------------------------------------------
# rendered checks: display is not delivery
# ---------------------------------------------------------------------------

RENDER_CHECKS: tuple[str, ...] = (
    "desktop_display",
    "mobile_display",
    "launcher_placement",
    "keyboard_usable",
    "touch_usable",
    "navigation_unaffected",
    "checkout_unaffected",
    "consent_unaffected",
)


@dataclass(frozen=True)
class RenderedCheckResult:
    passed: bool
    widget_id: str
    checks: Mapping[str, bool | None]
    unverified: tuple[str, ...]

    def as_evidence(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "widget_id": self.widget_id,
            "checks": dict(self.checks),
            "unverified": list(self.unverified),
        }


def evaluate_rendered_checks(
    widget_id: str, checks: Mapping[str, Any], *, evidence_ref: str
) -> RenderedCheckResult:
    """Require every named display/interference check, each with evidence.

    A missing or non-boolean check is ``unverified`` and fails.  A clean result
    proves rendering only; it never proves message delivery.
    """

    _required_text(widget_id, "widget_id")
    _required_text(evidence_ref, "evidence_ref")
    if not isinstance(checks, Mapping):
        raise RenderedCheckIncomplete("checks_not_mapping")
    values: dict[str, bool | None] = {}
    unverified: list[str] = []
    for name in RENDER_CHECKS:
        value = checks.get(name)
        if isinstance(value, bool):
            values[name] = value
            if not value:
                unverified.append(name)
        else:
            values[name] = None
            unverified.append(name)
    return RenderedCheckResult(
        passed=not unverified,
        widget_id=widget_id,
        checks=values,
        unverified=tuple(unverified),
    )


# ---------------------------------------------------------------------------
# conversation / inbox / responder verification
# ---------------------------------------------------------------------------

RESPONDER_KINDS: tuple[str, ...] = ("ai", "human", "workflow")


@dataclass(frozen=True)
class MessageEvidence:
    direction: str
    body: str
    message_id: str

    def __post_init__(self) -> None:
        if self.direction not in ("inbound", "outbound"):
            raise ConversationEvidenceInvalid(
                "message_direction_invalid", direction=self.direction
            )
        _required_text(self.message_id, "message_id")
        _required_text(self.body, "body")


@dataclass(frozen=True)
class ConversationEvidence:
    widget_id: str
    location_id: str
    thread_id: str
    inbox_id: str
    responder_kind: str
    responder_id: str
    messages: tuple[MessageEvidence, ...] = ()
    handoff_target: str | None = None
    handoff_verified: bool = False
    after_hours_verified: bool = False
    visible_bubble_observed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "messages", tuple(self.messages or ()))
        for message in self.messages:
            if not isinstance(message, MessageEvidence):
                raise ConversationEvidenceInvalid("message_evidence_invalid")
        if self.responder_kind not in RESPONDER_KINDS:
            raise ConversationEvidenceInvalid(
                "responder_kind_invalid", responder_kind=self.responder_kind
            )


@dataclass(frozen=True)
class ConversationCheckResult:
    passed: bool
    checks: Mapping[str, bool]
    failed: tuple[str, ...]

    def as_evidence(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": dict(self.checks),
            "failed": list(self.failed),
        }


def verify_conversation_delivery(
    evidence: ConversationEvidence,
    *,
    expected_widget_id: str,
    expected_location_id: str,
    expected_responder_kind: str,
    require_handoff: bool = False,
    require_after_hours: bool = False,
) -> ConversationCheckResult:
    """Prove the thread, inbox and responder separately from the bubble.

    ``visible_bubble_observed`` is recorded but is never a passing check.  A
    missing thread, inbox, responder or message direction fails even when the
    bubble was seen.
    """

    if not isinstance(evidence, ConversationEvidence):
        raise ConversationEvidenceInvalid("conversation_evidence_required")
    if expected_responder_kind not in RESPONDER_KINDS:
        raise ConversationEvidenceInvalid(
            "expected_responder_kind_invalid",
            responder_kind=expected_responder_kind,
        )
    inbound = [m for m in evidence.messages if m.direction == "inbound"]
    outbound = [m for m in evidence.messages if m.direction == "outbound"]
    checks: dict[str, bool] = {
        "widget_identity_matches": evidence.widget_id == expected_widget_id,
        "location_matches": evidence.location_id == expected_location_id,
        "thread_id_present": bool(str(evidence.thread_id or "").strip()),
        "inbox_id_present": bool(str(evidence.inbox_id or "").strip()),
        "inbound_message_present": bool(inbound),
        "outbound_reply_present": bool(outbound),
        "responder_kind_matches": evidence.responder_kind == expected_responder_kind,
        "responder_id_present": bool(str(evidence.responder_id or "").strip()),
    }
    if require_handoff:
        checks["handoff_target_present"] = bool(
            str(evidence.handoff_target or "").strip()
        )
        checks["handoff_verified"] = evidence.handoff_verified is True
    if require_after_hours:
        checks["after_hours_verified"] = evidence.after_hours_verified is True
    failed = tuple(name for name, ok in checks.items() if not ok)
    return ConversationCheckResult(passed=not failed, checks=checks, failed=failed)


@dataclass(frozen=True)
class ConversationCandidate:
    """Normalised conversation row used only to find the test thread."""

    thread_id: str
    location_id: str
    inbox_id: str
    message_bodies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _required_text(self.thread_id, "thread_id")
        _required_text(self.location_id, "location_id")
        object.__setattr__(self, "message_bodies", tuple(self.message_bodies or ()))


def select_test_conversation(
    candidates: Sequence[ConversationCandidate],
    marker_text: str,
    *,
    expected_location_id: str,
) -> ConversationCandidate:
    """Find exactly one thread containing the submitted test marker.

    Ambiguity is refused: two matching threads cannot prove which inbox received
    the message.
    """

    marker = _required_text(marker_text, "marker_text")
    location = _required_text(expected_location_id, "expected_location_id")
    matches = [
        item
        for item in candidates
        if isinstance(item, ConversationCandidate)
        and item.location_id == location
        and marker in item.message_bodies
    ]
    if len(matches) != 1:
        raise WidgetError(
            "test_conversation_not_unique",
            matches=len(matches),
            location_id=location,
        )
    return matches[0]


# ---------------------------------------------------------------------------
# adapter facade
# ---------------------------------------------------------------------------

class CapturingTransport:
    """Transport decorator that retains the last response for body parsing.

    ``PublicGhlAdapter`` returns a receipt, not the response body.  This wrapper
    adds no routing, no version and no headers; it only remembers the exact
    response the adapter already received.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.last_response: Any = None

    def request(self, **kwargs: Any) -> Any:
        response = self._inner.request(**kwargs)
        self.last_response = response
        return response


def _parsed_body(transport: Any) -> Any:
    response = getattr(transport, "last_response", None)
    body = getattr(response, "body", None)
    if not body:
        raise WidgetSchemaError("response_body_unavailable")
    import json

    try:
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        return json.loads(body)
    except (UnicodeDecodeError, ValueError) as exc:
        raise WidgetSchemaError("response_body_not_json") from exc


class ChatWidgetsPublic:
    """Typed widget operations over one tenant-bound :class:`PublicGhlAdapter`."""

    def __init__(self, adapter: Any, transport: Any) -> None:
        self._adapter = adapter
        self._transport = transport

    def list_widgets(
        self,
        tenant: Any,
        *,
        query: Mapping[str, Any] | None = None,
    ) -> list[WidgetRecord]:
        self._adapter.call(
            operation_id=WIDGET_OPERATIONS["list"],
            tenant=tenant,
            query=dict(query or {}),
        )
        return parse_widget_list(_parsed_body(self._transport))

    def get_widget(
        self,
        tenant: Any,
        *,
        location_id: str,
        widget_id: str,
    ) -> WidgetRecord:
        self._adapter.call(
            operation_id=WIDGET_OPERATIONS["get"],
            tenant=tenant,
            path_params={"locationId": location_id, "id": widget_id},
        )
        return parse_widget(_parsed_body(self._transport))

    def create_widget(
        self,
        tenant: Any,
        *,
        location_id: str,
        name: str,
        chat_type: str,
        version: int,
        settings: Mapping[str, Any] | None = None,
        default: bool | None = None,
        deleted: bool | None = None,
        idempotency_key: str,
        approval: Any = None,
        readback: Any = None,
    ) -> tuple[str, Any]:
        body = build_create_body(
            location_id=location_id,
            name=name,
            chat_type=chat_type,
            version=version,
            settings=settings,
            default=default,
            deleted=deleted,
        )
        result = self._adapter.call(
            operation_id=WIDGET_OPERATIONS["create"],
            tenant=tenant,
            body=body,
            idempotency_key=idempotency_key,
            approval=approval,
            readback=readback,
        )
        if getattr(result.status, "value", str(result.status)) != "ok":
            return "", result
        return extract_widget_id(_parsed_body(self._transport)), result

    def update_widget(
        self,
        tenant: Any,
        *,
        location_id: str,
        widget_id: str,
        idempotency_key: str,
        chat_type: str | None = None,
        version: int | None = None,
        name: str | None = None,
        settings: Mapping[str, Any] | None = None,
        default: bool | None = None,
        approval: Any = None,
        readback: Any = None,
    ) -> Any:
        body = build_update_body(
            chat_type=chat_type,
            version=version,
            name=name,
            settings=settings,
            default=default,
        )
        return self._adapter.call(
            operation_id=WIDGET_OPERATIONS["update"],
            tenant=tenant,
            path_params={"locationId": location_id, "id": widget_id},
            body=body,
            idempotency_key=idempotency_key,
            approval=approval,
            readback=readback,
        )

    def public_config(
        self,
        tenant: Any,
        *,
        widget_id: str,
    ) -> Any:
        self._adapter.call(
            operation_id=WIDGET_OPERATIONS["public_config"],
            tenant=tenant,
            path_params={"id": widget_id},
            query={"version": "2"},
        )
        return _parsed_body(self._transport)


__all__ = [
    "CREATE_CHAT_TYPES",
    "ChatWidgetsPublic",
    "ConversationCandidate",
    "ConversationCheckResult",
    "ConversationEvidence",
    "ConversationEvidenceInvalid",
    "DOC_FETCH_DATE",
    "DOC_URL",
    "DuplicateEmbed",
    "EmbedInstruction",
    "EmbedInstructionError",
    "EmbedOccurrence",
    "InstallPlan",
    "MessageEvidence",
    "PAGE_EMBED_SLOTS",
    "READ_CHAT_TYPES",
    "RENDER_CHECKS",
    "RenderedCheckIncomplete",
    "RenderedCheckResult",
    "WIDGET_HTTP_VERSION",
    "WIDGET_OPERATIONS",
    "WidgetError",
    "WidgetRecord",
    "WidgetSchemaError",
    "WidgetTypeNotWritable",
    "assert_single_install",
    "build_create_body",
    "build_update_body",
    "evaluate_rendered_checks",
    "extract_widget_id",
    "find_widget_occurrences",
    "load_embed_instruction",
    "parse_widget",
    "parse_widget_list",
    "plan_global_install",
    "plan_page_install",
    "select_test_conversation",
    "verify_conversation_delivery",
    "verify_install",
]
