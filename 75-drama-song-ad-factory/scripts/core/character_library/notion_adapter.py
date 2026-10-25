#!/usr/bin/env python3
"""notion_adapter: discover the client's shared character library and offer
**new**, **existing** or **mixed** cast for this episode (S75-T14).

Notion is the shared, client-scoped identity source. This module owns remote
lookup only; ``character_library.py`` stays the local cache/compatibility layer
and is never relabelled as a Notion integration.

Security and scope:
  * No network code lives here. Every remote operation goes through an
    injected authorized connection, so credentials are retrieved and used
    inside the established connection provider and never enter this module.
  * ``connection_ref`` is an opaque handle. Traces, errors and returns carry
    that handle only; :func:`scrub` strips any token-like field defensively.
  * No token, key or secret is ever printed. Missing authorization raises
    :class:`ConnectionUnavailable` with a reconnect instruction instead.

Stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile

#: Pinned Notion REST version. The transport must send it as ``Notion-Version``.
NOTION_API_VERSION = "2022-06-28"
SCHEMA_REGISTRY = "s75-character-library-registry/v1"
SCHEMA_IDENTITY = "s75-character-identity-v1"
MODE_NEW, MODE_EXISTING, MODE_MIXED = "new", "existing", "mixed"
MODES = (MODE_NEW, MODE_EXISTING, MODE_MIXED)

#: Ops the injected connection must implement. Application operations, not
#: invented endpoint names; the transport maps them onto the pinned API.
OPS = ("search", "read_page", "query_data_source", "create_page")

MAX_PAGES = 200  # bounded pagination guard
_SECRET_HINTS = ("token", "secret", "bearer", "authorization", "api_key", "apikey")


class DiscoveryError(ValueError):
    """Plain-English reason discovery or selection stopped."""


class ConnectionUnavailable(DiscoveryError):
    """No usable authorized connection. Never a reason to ask for a key in chat."""


class AmbiguousLibrary(DiscoveryError):
    """More than one plausible library; the client makes one location choice."""

    def __init__(self, candidates):
        self.candidates = list(candidates)
        DiscoveryError.__init__(
            self, "More than one saved character library matches. Choose a "
                  "location: %s." % ", ".join(
                      "%s (%s)" % (c.get("title", "untitled"), c.get("library_page_id", "?"))
                      for c in self.candidates))


def _digest(obj):
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def scrub(obj):
    """Drop any token-like field from a structure before it is traced."""
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items()
                if not any(h in str(k).lower() for h in _SECRET_HINTS)}
    if isinstance(obj, (list, tuple)):
        return [scrub(v) for v in obj]
    return obj


def _has_secret(obj):
    """True when any key looks like a credential, at any depth."""
    if isinstance(obj, dict):
        return any(any(h in str(k).lower() for h in _SECRET_HINTS) or _has_secret(v)
                   for k, v in obj.items())
    if isinstance(obj, (list, tuple)):
        return any(_has_secret(v) for v in obj)
    return False


def _trace(steps, step, **facts):
    """Record what the adapter did. Handles and IDs only — never a token."""
    steps.append(scrub({"step": step, **facts}))
    return steps


def _check(connection):
    """Refuse to run without an authorized connection object."""
    if connection is None:
        raise ConnectionUnavailable(
            "No authorized connection is stored. Reconnect through the secure "
            "connection flow; do not paste a key into chat.")
    ref = getattr(connection, "connection_ref", "")
    if not ref:
        raise ConnectionUnavailable(
            "The stored connection has no reference. Reconnect through the "
            "secure connection flow; do not paste a key into chat.")
    if not callable(getattr(connection, "call", None)):
        raise ConnectionUnavailable(
            "The stored connection cannot make calls. Reconnect through the "
            "secure connection flow.")
    return ref


def _call(connection, op, payload):
    """One authorized call. Transport owns headers, Notion-Version and retries."""
    try:
        out = connection.call(op, payload)
    except Exception as exc:  # transport-specific; surface type only, no body
        raise ConnectionUnavailable(
            "The character library could not be reached (%s). Reconnect through "
            "the secure connection flow." % type(exc).__name__) from None
    if not isinstance(out, dict):
        raise DiscoveryError("The character library returned an unreadable reply.")
    return out


def _paginate(connection, op, payload, key):
    """Follow ``has_more``/``next_cursor`` to the end. Full catalog or failure."""
    items, cursor, pages = [], None, 0
    while True:
        body = dict(payload)
        if cursor:
            body["start_cursor"] = cursor
        reply = _call(connection, op, body)
        items.extend(reply.get(key) or [])
        pages += 1
        cursor = reply.get("next_cursor")
        if not reply.get("has_more") or not cursor:
            return items, pages
        if pages >= MAX_PAGES:
            raise DiscoveryError(
                "The character library did not finish paginating after %d pages." % MAX_PAGES)


def namespace_of(page):
    """The client namespace a shared page declares, or "" when it declares none."""
    props = page.get("properties") or {}
    for name in ("client_namespace", "Client Namespace", "Client"):
        val = props.get(name)
        if isinstance(val, dict):
            val = val.get("rich_text") or val.get("title") or val.get("select")
            if isinstance(val, list):
                val = "".join(p.get("plain_text", "") for p in val if isinstance(p, dict))
            elif isinstance(val, dict):
                val = val.get("name", "")
        if val:
            return str(val).strip()
    return str(page.get("client_namespace", "")).strip()


def _registry_for(registry, client_namespace):
    if not registry:
        return None
    if registry.get("client_namespace") != client_namespace:
        raise DiscoveryError(
            "The stored library belongs to a different client namespace.")
    return registry


def resolve_client_library(connection, client_namespace, registry=None, *,
                           parent_page_id=None, page_size=50):
    """Step 1-2: find this client's library by stored ID, else by namespace.

    A title match never selects another client's library. Returns
    ``(registry, trace)``; raises :class:`AmbiguousLibrary` when more than one
    plausible library matches so the client makes one location choice.
    """
    if not str(client_namespace or "").strip():
        raise DiscoveryError("The client identity is missing, so no library can be chosen.")
    ref = _check(connection)
    steps = _trace([], "resolve_client_library",
                   client_namespace=client_namespace, connection_ref=ref)

    stored = _registry_for(registry, client_namespace)
    if stored:
        page = _call(connection, "read_page", {"page_id": stored["library_page_id"]})
        if namespace_of(page) == client_namespace:
            _trace(steps, "resolved_by_stored_id",
                   library_page_id=stored["library_page_id"])
            return stored, steps
        _trace(steps, "stored_id_namespace_mismatch",
               library_page_id=stored["library_page_id"])

    found, pages = _paginate(connection, "search",
                             {"query": client_namespace, "page_size": page_size}, "results")
    matches = [p for p in found if namespace_of(p) == client_namespace
               and (parent_page_id is None or _parent_of(p) == parent_page_id)]
    _trace(steps, "searched_libraries", pages=pages, candidates=len(matches))
    if not matches:
        raise DiscoveryError(
            "No saved character library exists for this client yet.")
    if len(matches) > 1:
        raise AmbiguousLibrary(
            [{"title": _title_of(p), "library_page_id": p.get("id")} for p in matches])
    page = matches[0]
    resolved = {
        "schema": SCHEMA_REGISTRY,
        "client_namespace": client_namespace,
        "connection_ref": ref,
        "library_page_id": page.get("id"),
        "data_source_id": page.get("data_source_id") or page.get("database_id") or "",
        "schema_version": SCHEMA_IDENTITY,
        "integration_api_version": NOTION_API_VERSION,
        "catalog_revision": "",
        "sync_state": "IN_SYNC",
        "lookup_provenance": "authorized_search_by_namespace",
    }
    _trace(steps, "resolved_by_search", library_page_id=resolved["library_page_id"])
    return resolved, steps


def _title_of(page):
    props = page.get("properties") or {}
    for val in props.values():
        if isinstance(val, dict) and val.get("type") == "title":
            return "".join(p.get("plain_text", "") for p in val.get("title") or [])
    for name in ("title", "Name"):
        if name in props:
            return str(props[name])
    return ""


def _parent_of(page):
    parent = page.get("parent") or {}
    return parent.get("page_id") or parent.get("database_id") or ""


def create_library(connection, client_namespace, parent_page_id, *, page_size=50):
    """First use: create the library under an already authorized parent page.

    Application content creation only — never a new workspace. Returns
    ``(registry, trace)`` with IDs read back from the created page.
    """
    if not str(client_namespace or "").strip():
        raise DiscoveryError("The client identity is missing, so no library can be created.")
    if not str(parent_page_id or "").strip():
        raise DiscoveryError(
            "No authorized location is available for this client's library. "
            "Connect the shared workspace or choose a location first.")
    ref = _check(connection)
    steps = _trace([], "create_library", client_namespace=client_namespace,
                   connection_ref=ref, parent_page_id=parent_page_id)
    created = _call(connection, "create_page", {
        "parent": {"page_id": parent_page_id},
        "properties": {"title": "Character Library",
                       "client_namespace": client_namespace},
    })
    page_id = created.get("id")
    if not page_id:
        raise DiscoveryError("The library was not created; no page ID was returned.")
    readback = _call(connection, "read_page", {"page_id": page_id})
    if namespace_of(readback) != client_namespace:
        raise DiscoveryError(
            "The created library does not belong to this client namespace.")
    registry = {
        "schema": SCHEMA_REGISTRY,
        "client_namespace": client_namespace,
        "connection_ref": ref,
        "library_page_id": page_id,
        "data_source_id": readback.get("data_source_id") or readback.get("database_id") or "",
        "schema_version": SCHEMA_IDENTITY,
        "integration_api_version": NOTION_API_VERSION,
        "catalog_revision": "",
        "sync_state": "IN_SYNC",
        "lookup_provenance": "created_on_first_use",
    }
    _trace(steps, "created_and_read_back", library_page_id=page_id)
    return registry, steps


def list_character_revisions(connection, registry, *, page_size=50):
    """Step 3: the full current catalog, drafts included, fully paginated.

    Returns ``(catalog, trace)``. A missing reference image never means an
    unknown identity — it is reported as ``has_reference_image: False``.
    """
    ref = _check(connection)
    registry = _registry_for(registry, (registry or {}).get("client_namespace"))
    if registry is None:
        raise DiscoveryError("No character library has been resolved for this client yet.")
    steps = _trace([], "list_character_revisions", connection_ref=ref)
    source = registry.get("data_source_id") or registry.get("library_page_id")
    if not source:
        raise DiscoveryError("The stored library has no data source to read.")
    rows, pages = _paginate(connection, "query_data_source",
                            {"data_source_id": source, "page_size": page_size}, "results")
    chars = []
    for row in rows:
        props = row.get("properties") or {}
        chars.append({
            "character_id": props.get("character_id") or row.get("id"),
            "remote_page_id": row.get("id"),
            "name": _title_of(row),
            "role": props.get("role", ""),
            "approval_state": props.get("approval_state", "DRAFT"),
            "identity_revision": props.get("identity_revision", ""),
            "record_digest": props.get("record_digest") or _digest(props),
            "has_reference_image": bool(props.get("has_reference_image", False)),
        })
    catalog = {
        "schema": SCHEMA_IDENTITY,
        "client_namespace": registry.get("client_namespace"),
        "library_page_id": registry.get("library_page_id"),
        "schema_version": SCHEMA_IDENTITY,
        "catalog_revision": _digest(chars),
        "pages_read": pages,
        "characters": sorted(chars, key=lambda c: str(c["name"])),
    }
    _trace(steps, "catalog_read", pages=pages, characters=len(chars),
           catalog_revision=catalog["catalog_revision"])
    return catalog, steps


def offer_cast_choice(catalog, previous_mode=None, previous_ids=()):
    """Step 4: one question, three options, current catalog always shown.

    A stored answer may be reused for ``recommended`` while the catalog is
    still presented and the client can change the choice.
    """
    chars = list(catalog.get("characters") or [])
    question = ("Do you want a new character for this episode, use characters "
                "you already have, or mix both?")
    options = [
        {"mode": MODE_NEW, "label": "Create new characters"},
        {"mode": MODE_EXISTING, "label": "Use characters I already have",
         "available": [c["name"] for c in chars]},
        {"mode": MODE_MIXED, "label": "Mix saved characters with new ones",
         "available": [c["name"] for c in chars]},
    ]
    chosen = previous_mode if previous_mode in MODES else None
    offered = [o["mode"] for o in options if o["mode"] != MODE_EXISTING or chars]
    return {
        "id": "cast_choice",
        "ask": question,
        "options": options,
        "offered_modes": offered,
        "recommended": chosen or MODE_NEW,
        "previous_choice": {"mode": chosen, "character_ids": list(previous_ids)} if chosen else None,
        "catalog": chars,
        "catalog_revision": catalog.get("catalog_revision", ""),
        "sync_state": catalog.get("sync_state", "IN_SYNC"),
    }


def resolve_cast_selection(mode, catalog, *, selected_character_ids=(), new_characters=()):
    """Step 5: turn the client's choice into reused and newly authored entries."""
    if mode not in MODES:
        raise DiscoveryError("Choose new, existing or mixed.")
    by_id = {c["character_id"]: c for c in catalog.get("characters") or []}
    selected = list(selected_character_ids or [])
    new = [dict(n) for n in (new_characters or [])]
    missing = [c for c in selected if c not in by_id]
    if missing:
        raise DiscoveryError(
            "These saved characters are not in this client's library: %s." % ", ".join(missing))
    if mode == MODE_NEW and (selected or not new):
        raise DiscoveryError("A new cast needs at least one new character and no saved picks.")
    if mode == MODE_EXISTING and (not selected or new):
        raise DiscoveryError("An existing cast needs at least one saved character and no new ones.")
    if mode == MODE_MIXED and not (selected and new):
        raise DiscoveryError("A mixed cast needs at least one saved character and one new one.")
    reused = [{"character_id": by_id[c]["character_id"],
               "identity_revision": by_id[c]["identity_revision"],
               "record_digest": by_id[c]["record_digest"],
               "role": by_id[c].get("role", ""),
               "source": "existing"} for c in selected]
    created = [{"name": n.get("name", ""),
                "identity_revision": n.get("identity_revision", "draft-r1"),
                "role": n.get("role", ""),
                "source": "new"} for n in new]
    return {"selection_mode": mode, "reused": reused, "new": created,
            "catalog_revision": catalog.get("catalog_revision", "")}


def build_snapshot_and_manifest(registry, catalog, selection, *, sync_state="IN_SYNC",
                                source="REMOTE"):
    """Step 6: the two artifacts the full cast gate actually consumes."""
    cast = selection["reused"] + selection["new"]
    snapshot = {
        "schema": "s75-character-identity-library-snapshot/v1",
        "client_namespace": registry.get("client_namespace"),
        "library_page_id": registry.get("library_page_id"),
        "data_source_id": registry.get("data_source_id", ""),
        "catalog_revision": catalog.get("catalog_revision", ""),
        "selection_mode": selection["selection_mode"],
        "source": source,
        "sync_state": sync_state,
        "characters": [{"character_id": c.get("character_id", ""),
                        "identity_revision": c["identity_revision"],
                        "record_digest": c.get("record_digest", ""),
                        "approval_state": c.get("approval_state", "DRAFT")}
                       for c in cast],
    }
    snapshot["snapshot_id"] = _digest(snapshot)[:23].replace("sha256:", "snap-")
    manifest = {
        "schema": "s75-episode-cast-manifest/v1",
        "client_namespace": registry.get("client_namespace"),
        "selection_mode": selection["selection_mode"],
        "snapshot_digest": _digest(snapshot),
        "cast": [{"character_id": c.get("character_id") or c.get("name"),
                  "identity_revision": c["identity_revision"],
                  "role": c.get("role", ""),
                  "origin": c["source"]} for c in cast],
        "complete": bool(cast) and all(c["identity_revision"] for c in cast),
    }
    return snapshot, manifest


def load_registry(path):
    """Read the persisted client mapping, or None. Holds a handle, never a token."""
    try:
        with open(os.path.expanduser(str(path)), encoding="utf-8") as f:
            reg = json.load(f)
    except (OSError, ValueError):
        return None
    return scrub(reg) if isinstance(reg, dict) else None


def save_registry(path, registry):
    """Atomic persist of the client mapping. Refuses anything token-shaped."""
    if _has_secret(registry):
        raise DiscoveryError("Refusing to store a credential in the library registry.")
    clean = scrub(registry)
    path = os.path.expanduser(str(path))
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".registry-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(clean, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return clean


def discover(connection, client_namespace, registry=None, *,
             parent_page_id=None, previous_mode=None, previous_ids=()):
    """One launch, steps 1-5. Returns everything the launch needs to ask.

    ``library_ready`` False means first use: the caller confirms the authorized
    location before :func:`create_library` runs. Nothing is created here.
    """
    ref = _check(connection)
    if not str(client_namespace or "").strip():
        raise DiscoveryError("The client identity is missing, so no library can be chosen.")
    steps = []
    try:
        reg, more = resolve_client_library(connection, client_namespace, registry,
                                           parent_page_id=parent_page_id)
        steps += more
    except AmbiguousLibrary as exc:
        _trace(steps, "ambiguous_library_held", candidates=exc.candidates)
        return {"status": "AMBIGUOUS_LOCATION", "candidates": exc.candidates,
                "trace": steps, "connection_ref": ref}
    except ConnectionUnavailable:
        raise
    except DiscoveryError as exc:
        _trace(steps, "library_missing", reason=str(exc))
        return {"status": "FIRST_USE", "library_ready": False,
                "parent_page_id": parent_page_id, "trace": steps,
                "connection_ref": ref, "next_step": "create_library"}
    catalog, more = list_character_revisions(connection, reg)
    steps += more
    choice = offer_cast_choice(catalog, previous_mode, previous_ids)
    return {"status": "READY", "library_ready": True, "registry": reg,
            "catalog": catalog, "choice": choice, "trace": steps,
            "connection_ref": ref}
