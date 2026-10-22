#!/usr/bin/env python3
"""ghl_recipe_objects.py — P5 object-recipe contract + SCOPED object identity
for funnels, folders, websites, steps and pages (Skill 06 v3.0, C6).

WHY THIS EXISTS
---------------
Master plan v3.0 §10.1 requires six DISTINCT object identities where the tree
previously had one loose notion of "a funnel". The load-bearing distinction is
the one that silently corrupts a build: **a funnel folder is not a website
folder**, and a funnel is not a website even though both are created through
`POST /funnels/funnel/create` with a `type` field and both are read through
`/funnels/funnel/list`. Treating them as one kind makes a second run adopt the
wrong container and then write a page into it.

This module owns the deterministic, mechanical parts of the §10.2 recipe
contract that can be decided WITHOUT a live write:

  * the kind table — parent rules, platform `type`, the captured read route,
    the captured UI baseline and its HONEST status, the readback contract;
  * scoped identity — `(kind, native_id, location_id, parent_id)`, never a
    label (B09);
  * reconciliation — one pure decision function over already-enumerated rows
    that answers reuse / create / refuse, and that refuses to retry over an
    uncertain prior attempt (B07/B17);
  * readback gating — a create is not done until the native id AND the saved
    state are read back (C6);
  * publication gating — a recipe never flips `pageType` to published;
  * the `llm_calls_during_recipe == 0` guard (B18).

WHAT THIS MODULE IS *NOT*
-------------------------
No network, no browser, no credential resolution, no GHL I/O of any kind. It
is the same isolation discipline as `ghl_object_router.py`: every live read and
every live write is a caller-injected callable. It does not re-implement the
create/autosave/read primitives — those stay in `ghl_rest_canvas.py` (routes +
payload shapes) and `ghl_funnels_read.py` (public inventory reads), both used
here as READ-ONLY references. `ghl_object_router.execute_write` remains the
only receipted write driver; `assert_admissible` exists because that driver
treats a RAISED idempotency probe as "not found" and would otherwise CREATE
over a refusal (see the patch note on `assert_admissible`).

CAPTURE STATUS — the honest part
--------------------------------
Every UI baseline below is transcribed from the LOCKED capture docs
(`SELECTORS-LIVE-funnel.md`, `SELECTORS-LIVE-page.md`, `selectors-live.json`)
with the confidence value and the doc's own caveat preserved:

  * funnel / website folders: the LIST route is captured live (HTTP 200,
    `?locationId=&type=funnel`), and the `Create folder` button anchor is
    captured at confidence 9 in BOTH lists. The create DIALOG's interior
    (its name field, its confirm button) was NEVER captured, and no folder
    create RESPONSE shape was captured. So folder identity is proven on the
    READ side only, and folder creation is RUNTIME_CAPTURE at click time.
    Nothing is invented to fill that gap.
  * funnels / websites: modal + list anchors locked (9-9.5).
  * steps / pages: New-step dialog anchors locked (9-9.5); the website
    variant of the same dialog is `Add new page` (9.5).
  * native split-test VARIANT: NOT captured at the entity/traffic level at
    all — see `ghl_split_variant.py`, which is DISABLED by construction.

LIVE STATUS: OFFLINE_PROVEN. Nothing here has been exercised against a real
location; there is no approved sandbox, and this module never writes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ── Object kinds (distinct, never conflated) ─────────────────────────────────

KIND_FUNNEL_FOLDER = "funnel_folder"
KIND_WEBSITE_FOLDER = "website_folder"
KIND_FUNNEL = "funnel"
KIND_WEBSITE = "website"
KIND_STEP = "step"
KIND_PAGE = "page"
KIND_VARIANT = "variant"

ALL_KINDS: Tuple[str, ...] = (
    KIND_FUNNEL_FOLDER,
    KIND_WEBSITE_FOLDER,
    KIND_FUNNEL,
    KIND_WEBSITE,
    KIND_STEP,
    KIND_PAGE,
    KIND_VARIANT,
)

# Folder kinds are the pair that MUST NOT be merged: identical row shape,
# identical button label, different `type` scope on the list call.
FOLDER_KINDS: Tuple[str, ...] = (KIND_FUNNEL_FOLDER, KIND_WEBSITE_FOLDER)

# ── Reconciliation outcomes ──────────────────────────────────────────────────

REUSE = "reuse"
CREATE = "create"
REFUSE_AMBIGUOUS = "refuse_ambiguous"
REFUSE_COLLISION = "refuse_collision"
REFUSE_CONTRADICTION = "refuse_contradiction"
REFUSE_WRONG_SCOPE = "refuse_wrong_scope"
REFUSE_UNPROVEN_READ = "refuse_unproven_read"

REFUSALS: Tuple[str, ...] = (
    REFUSE_AMBIGUOUS,
    REFUSE_COLLISION,
    REFUSE_CONTRADICTION,
    REFUSE_WRONG_SCOPE,
    REFUSE_UNPROVEN_READ,
)

# ── UI-baseline status vocabulary (capture honesty, not a confidence score) ──

BASELINE_LOCKED = "LOCKED"                  # anchors captured live, named below
BASELINE_RUNTIME_CAPTURE = "RUNTIME_CAPTURE"  # anchor locked, interior not
BASELINE_PENDING = "PENDING_LIVE_SELECTOR_CAPTURE"  # nothing usable captured


# ── Kind schema ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ObjectKindSchema:
    """One object kind's declared contract (§10.2): what may be its parent,
    how its native id is spelled, which captured read proves it, what the
    readback must contain, and how good the UI capture actually is."""

    kind: str
    platform_type: str            # the platform `type` value this kind lives in
    parent_kinds: Tuple[str, ...]  # "" entry = may hang at the location root
    parent_field: Optional[str]    # row field carrying the parent id
    fallback_parent_fields: Tuple[str, ...]
    id_fields: Tuple[str, ...]
    list_route: str
    ui_baseline: str
    ui_baseline_status: str
    readback: str


_KINDS: Dict[str, ObjectKindSchema] = {
    KIND_FUNNEL_FOLDER: ObjectKindSchema(
        kind=KIND_FUNNEL_FOLDER,
        platform_type="funnel",
        parent_kinds=("",),
        parent_field=None,
        fallback_parent_fields=(),
        id_fields=("id", "_id"),
        list_route=(
            "GET /funnels/funnel/folder/list?locationId=&type=funnel "
            "(LIVE 200, SELECTORS-LIVE-funnel.md §A); entities via "
            "GET /funnels/funnel/folder/entities?locationId=&type=funnel"
        ),
        ui_baseline=(
            "list toolbar getByRole('button', { name: 'Create folder' }) conf 9; "
            "create dialog interior + create response shape NOT captured"
        ),
        ui_baseline_status=BASELINE_RUNTIME_CAPTURE,
        readback="re-list folder/list?type=funnel; id + locationId present",
    ),
    KIND_WEBSITE_FOLDER: ObjectKindSchema(
        kind=KIND_WEBSITE_FOLDER,
        platform_type="website",
        parent_kinds=("",),
        parent_field=None,
        fallback_parent_fields=(),
        id_fields=("id", "_id"),
        list_route=(
            "GET /funnels/funnel/folder/list?locationId=&type=website "
            "(same route family, DIFFERENT type scope; the websites list "
            "carries the same 'Create folder' anchor, SELECTORS-LIVE-page.md §B)"
        ),
        ui_baseline=(
            "websites list getByRole('button', { name: 'Create folder' }) conf 9; "
            "create dialog interior + create response shape NOT captured"
        ),
        ui_baseline_status=BASELINE_RUNTIME_CAPTURE,
        readback="re-list folder/list?type=website; id + locationId present",
    ),
    KIND_FUNNEL: ObjectKindSchema(
        kind=KIND_FUNNEL,
        platform_type="funnel",
        parent_kinds=("", KIND_FUNNEL_FOLDER),
        parent_field="parentId",
        fallback_parent_fields=(),
        id_fields=("id", "_id"),
        list_route=(
            "GET /funnels/funnel/list?locationId=&type=funnel "
            "(LIVE 200) / public GET /funnels/funnel/list via ghl_funnels_read"
        ),
        ui_baseline=(
            "New-funnel modal: 'From blank' 9, getByPlaceholder('e.g. Sales funnel') "
            "9.5, 'Create' 9.5; NOTE live non-determinism — the click sometimes "
            "fires create directly and skips the modal (branch on what appears)"
        ),
        ui_baseline_status=BASELINE_LOCKED,
        readback="GET /funnels/funnel/fetch/<id> (200) + locationId match",
    ),
    KIND_WEBSITE: ObjectKindSchema(
        kind=KIND_WEBSITE,
        platform_type="website",
        parent_kinds=("", KIND_WEBSITE_FOLDER),
        parent_field="parentId",
        fallback_parent_fields=(),
        id_fields=("id", "_id"),
        list_route=(
            "GET /funnels/funnel/list?locationId=&type=website "
            "(websites are funnels of type website, SELECTORS-LIVE-page.md)"
        ),
        ui_baseline=(
            "New-website modal: 'From blank' 9, getByPlaceholder('e.g. Sales "
            "website') 9.5, 'Create' 9.5"
        ),
        ui_baseline_status=BASELINE_LOCKED,
        readback="GET /funnels/funnel/fetch/<id> + type=='website' + locationId match",
    ),
    KIND_STEP: ObjectKindSchema(
        kind=KIND_STEP,
        platform_type="funnel",
        parent_kinds=(KIND_FUNNEL, KIND_WEBSITE),
        parent_field="funnelId",
        fallback_parent_fields=(),
        id_fields=("id", "_id", "stepId"),
        list_route=(
            "GET /funnels/funnel/fetch/<funnelId> (steps[]); page rows via "
            "GET /funnels/page/list?funnelId=&locationId= carry stepId"
        ),
        ui_baseline=(
            "New-step dialog: getByPlaceholder('Name for page') 9.5, "
            "getByPlaceholder('Path') 9, 'Create funnel step' 9.5"
        ),
        ui_baseline_status=BASELINE_LOCKED,
        readback="funnel fetch carries the step id; page list carries stepId",
    ),
    KIND_PAGE: ObjectKindSchema(
        kind=KIND_PAGE,
        platform_type="funnel",
        parent_kinds=(KIND_STEP, KIND_FUNNEL, KIND_WEBSITE),
        parent_field="stepId",
        fallback_parent_fields=("funnelId",),
        id_fields=("id", "_id"),
        list_route=(
            "GET /funnels/page/list?funnelId=&locationId= (LIVE 200) / public "
            "GET /funnels/page via ghl_funnels_read"
        ),
        ui_baseline=(
            "shared New-step dialog (same anchors as step); websites use "
            "'Add new page' 9.5"
        ),
        ui_baseline_status=BASELINE_LOCKED,
        readback=(
            "GET /funnels/page/<pageId> (200) + numeric pageVersion + funnelId "
            "match; created id from create-step response via "
            "ghl_rest_canvas.created_page_id"
        ),
    ),
    KIND_VARIANT: ObjectKindSchema(
        kind=KIND_VARIANT,
        platform_type="funnel",
        parent_kinds=(KIND_STEP,),
        parent_field="stepId",
        fallback_parent_fields=(),
        id_fields=("id", "_id"),
        list_route="NONE CAPTURED (see tools/ghl_split_variant.py)",
        ui_baseline=(
            "step overview 'Create variation' conf 8.5 (carried forward, not "
            "re-verified); entity relation + traffic semantics NOT captured"
        ),
        ui_baseline_status=BASELINE_PENDING,
        readback="UNKNOWN until live capture; capability is DISABLED",
    ),
}


def schema_for(kind: str) -> ObjectKindSchema:
    """Return the declared schema for one kind. An unknown kind RAISES — a
    recipe never runs against an undeclared object type."""
    entry = _KINDS.get(str(kind or "").strip())
    if entry is None:
        raise KeyError(
            f"unknown recipe object kind {kind!r}; declared kinds are "
            f"{list(ALL_KINDS)}"
        )
    return entry


def kind_table() -> Dict[str, Dict[str, Any]]:
    """The kind table as plain data (report/JSON friendly, no dataclass)."""
    out: Dict[str, Dict[str, Any]] = {}
    for kind in ALL_KINDS:
        s = _KINDS[kind]
        out[kind] = {
            "kind": s.kind,
            "platform_type": s.platform_type,
            "parent_kinds": list(s.parent_kinds),
            "parent_field": s.parent_field,
            "fallback_parent_fields": list(s.fallback_parent_fields),
            "id_fields": list(s.id_fields),
            "list_route": s.list_route,
            "ui_baseline": s.ui_baseline,
            "ui_baseline_status": s.ui_baseline_status,
            "readback": s.readback,
        }
    return out


# ── Scoped identity (B09: identity, never a label) ───────────────────────────

class IdentityError(ValueError):
    """A scoped identity is malformed or the parent kind is not permitted."""


@dataclass(frozen=True)
class ObjectIdentity:
    """A GHL object named by SCOPE, not by label.

    ``parent_id`` "" means "the location root". Two objects with the same name
    and different ``parent_id`` are DIFFERENT objects; two objects with the
    same ``native_id`` and different ``kind`` are a contradiction, not a match.
    """

    kind: str
    native_id: str
    location_id: str
    parent_id: str = ""

    def key(self) -> Tuple[str, str, str, str]:
        return (self.kind, self.native_id, self.location_id, self.parent_id)

    def as_dict(self) -> Dict[str, str]:
        return {
            "kind": self.kind,
            "native_id": self.native_id,
            "location_id": self.location_id,
            "parent_id": self.parent_id,
        }


def build_identity(kind: str, native_id: Any, location_id: Any,
                   parent_id: Any = "", *,
                   parent_kind: Optional[str] = None) -> ObjectIdentity:
    """Build a validated scoped identity.

    Refuses (``IdentityError``) when the kind is undeclared, either id is
    blank, a non-root kind has no parent, or ``parent_kind`` is not one the
    kind may hang under — the last check is the "wrong parent" refusal at
    identity-construction time, before any read or write.
    """
    schema = schema_for(kind)
    nid = _req(native_id, "native_id")
    loc = _req(location_id, "location_id")
    pid = str(parent_id or "").strip()
    if pid == "" and "" not in schema.parent_kinds:
        raise IdentityError(
            f"{kind} requires a parent ({schema.parent_kinds}); a root-level "
            "identity for this kind would silently become a different object"
        )
    if pid != "" and parent_kind is not None:
        pk = str(parent_kind or "").strip()
        if pk not in schema.parent_kinds:
            raise IdentityError(
                f"{kind} may not hang under a {pk!r} parent; allowed parents "
                f"are {schema.parent_kinds} (a funnel folder is not a website "
                "folder, and a website is not a funnel)"
            )
    return ObjectIdentity(kind=schema.kind, native_id=nid,
                          location_id=loc, parent_id=pid)


def _req(value: Any, name: str) -> str:
    text = str(value if value is not None else "").strip()
    if not text:
        raise IdentityError(f"{name} is required (got {value!r})")
    return text


# ── Row scoping + reconciliation ─────────────────────────────────────────────

@dataclass
class ReconcileResult:
    """The single decision a recipe makes before it may create anything."""

    action: str
    reason: str = ""
    identity: Optional[ObjectIdentity] = None
    row: Optional[Dict[str, Any]] = None
    candidates: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.action in (REUSE, CREATE)

    @property
    def refused(self) -> bool:
        return self.action in REFUSALS


def _row_scope(kind: str, row: Dict[str, Any]) -> Dict[str, Any]:
    """Project one inventory row onto the fields reconciliation compares.

    Tolerant on id aliasing (``_id`` -> ``id``), exactly like
    ``ghl_funnels_read.normalize_funnel_row``; it invents no field. A row whose
    ``type`` disagrees with the kind's platform type is kept but flagged
    ``kind_ok=False`` so a website row can never satisfy a funnel request.
    """
    schema = schema_for(kind)
    if not isinstance(row, dict):
        raise TypeError(f"inventory rows must be dicts (got {type(row).__name__})")
    native_id = ""
    for f in schema.id_fields:
        if row.get(f):
            native_id = str(row[f]).strip()
            break
    location_id = str(
        row.get("locationId") or row.get("location_id") or ""
    ).strip()
    parent_id = ""
    if schema.parent_field:
        parent_id = str(row.get(schema.parent_field) or "").strip()
    if not parent_id:
        for f in schema.fallback_parent_fields:
            if row.get(f):
                parent_id = str(row[f]).strip()
                break
    declared_type = str(row.get("type") or "").strip().lower()
    kind_ok = (declared_type == "" or declared_type == schema.platform_type)
    return {
        "row": row,
        "native_id": native_id,
        "location_id": location_id,
        "parent_id": parent_id,
        "name": str(row.get("name") or ""),
        "kind_ok": kind_ok,
        "declared_type": declared_type,
    }


def _ident(kind: str, p: Dict[str, Any]) -> Optional[ObjectIdentity]:
    if not p["native_id"] or not p["location_id"]:
        return None
    return ObjectIdentity(kind=kind, native_id=p["native_id"],
                          location_id=p["location_id"],
                          parent_id=p["parent_id"])


def _scope_text(p: Dict[str, Any]) -> str:
    return (f"id={p['native_id'] or '<none>'} location={p['location_id'] or '<none>'} "
            f"parent={p['parent_id'] or '<root>'} type={p['declared_type'] or '<absent>'}")


def reconcile(
    rows: Iterable[Dict[str, Any]],
    *,
    kind: str,
    location_id: Any,
    parent_id: Any = "",
    name: Optional[str] = None,
    native_id: Optional[str] = None,
    read_complete: bool = True,
) -> ReconcileResult:
    """Decide reuse / create / refuse for ONE object, from enumerated rows.

    Precedence (strongest evidence first):
      1. ``native_id`` match in the requested scope  -> REUSE.
      2. ``native_id`` match in a DIFFERENT scope, or with a different kind
         -> REFUSE_WRONG_SCOPE. A recorded id is never re-adopted after it
         moves parents or changes kind.
      3. ``name`` match inside the requested scope, unique -> REUSE.
      4. ``name`` match inside scope, 2+  -> REFUSE_AMBIGUOUS.
      5. ``native_id`` given, id absent, name taken in scope by a different id
         -> REFUSE_CONTRADICTION (uncertain prior attempt: reconcile by hand
         before any retry, §10.2).
      6. ``name`` match only OUTSIDE scope (other parent / other location)
         -> REFUSE_COLLISION. This is B09: the label collides elsewhere, so the
         object is a different object and is neither adopted nor overwritten.
      7. nothing -> CREATE.

    ``read_complete=False`` refuses up front: a partial or failed inventory can
    never prove absence, so it can never license a create (B07).
    """
    schema = schema_for(kind)
    loc = _req(location_id, "location_id")
    pid = str(parent_id or "").strip()
    if pid == "" and "" not in schema.parent_kinds:
        return ReconcileResult(
            REFUSE_WRONG_SCOPE,
            reason=f"{kind} requires a parent; a root scope would be a "
                   f"different object (allowed: {schema.parent_kinds})",
        )
    if not read_complete:
        return ReconcileResult(
            REFUSE_UNPROVEN_READ,
            reason="the inventory read is not proven complete; absence cannot "
                   "be established, so no create is admissible",
        )
    nid = str(native_id or "").strip()
    want_name = str(name or "").strip()
    if not nid and not want_name:
        return ReconcileResult(
            REFUSE_CONTRADICTION,
            reason="no identity supplied: reconciliation needs a recorded "
                   "native id or a name (a recipe never creates blind)",
        )

    parsed = [_row_scope(kind, r) for r in (rows or [])]

    # 1/2 — the recorded native id is the strongest evidence there is.
    if nid:
        id_rows = [p for p in parsed if p["native_id"] == nid]
        if id_rows:
            in_scope = [
                p for p in id_rows
                if p["kind_ok"] and p["location_id"] == loc and p["parent_id"] == pid
            ]
            if in_scope:
                return ReconcileResult(
                    REUSE,
                    reason=f"native id {nid} matched in the requested scope",
                    identity=_ident(kind, in_scope[0]),
                    row=in_scope[0]["row"],
                    candidates=[nid],
                )
            return ReconcileResult(
                REFUSE_WRONG_SCOPE,
                reason=(
                    f"recorded {kind} id {nid} exists in a different scope "
                    f"({_scope_text(id_rows[0])}) than the requested "
                    f"location={loc} parent={pid or '<root>'}; refusing to "
                    "adopt it"
                ),
                candidates=[p["native_id"] for p in id_rows],
            )

    # 3-7 — scoped name match, and the elsewhere-collision refusal.
    if want_name:
        target = want_name.casefold()
        name_rows = [
            p for p in parsed
            if p["kind_ok"] and p["name"].strip().casefold() == target
        ]
        in_scope = [
            p for p in name_rows
            if p["location_id"] == loc and p["parent_id"] == pid
        ]
        if nid and in_scope:
            return ReconcileResult(
                REFUSE_CONTRADICTION,
                reason=(
                    f"recorded {kind} id {nid} is absent, but its name {want_name!r} "
                    f"is already taken in the same scope by "
                    f"{[p['native_id'] for p in in_scope]}; the prior attempt is "
                    "uncertain — reconcile the real object before any retry"
                ),
                candidates=[p["native_id"] for p in in_scope],
            )
        if len(in_scope) == 1:
            return ReconcileResult(
                REUSE,
                reason=f"unique {kind} named {want_name!r} in the requested scope",
                identity=_ident(kind, in_scope[0]),
                row=in_scope[0]["row"],
                candidates=[in_scope[0]["native_id"]],
            )
        if len(in_scope) > 1:
            return ReconcileResult(
                REFUSE_AMBIGUOUS,
                reason=(
                    f"{len(in_scope)} {kind}s named {want_name!r} share the "
                    "requested scope; refusing to guess which one is the target"
                ),
                candidates=[p["native_id"] for p in in_scope],
            )
        if name_rows:
            return ReconcileResult(
                REFUSE_COLLISION,
                reason=(
                    f"{kind} name {want_name!r} already exists OUTSIDE the "
                    f"requested scope ({_scope_text(name_rows[0])}); the label "
                    "collides elsewhere, so this is a different object and is "
                    "neither adopted nor overwritten (B09)"
                ),
                candidates=[p["native_id"] for p in name_rows],
            )

    return ReconcileResult(
        CREATE,
        reason=(
            f"no {kind} matches id={nid or '<none>'} name={want_name or '<none>'} "
            f"in location={loc} parent={pid or '<root>'}"
        ),
    )


class RecipeRefusal(RuntimeError):
    """A reconciliation refusal reached a step that must not proceed."""


def assert_admissible(result: ReconcileResult) -> ReconcileResult:
    """Stop before any write unless the decision is REUSE or CREATE.

    PROPOSED PATCH (not applied — `ghl_object_router.py` is outside this
    lane's ownership): `execute_write` wraps its idempotency probe in a bare
    ``except Exception`` and treats a RAISE as "not found", which would let a
    refusal fall through to a create. Until that is fixed, callers must run
    ``assert_admissible`` BEFORE ``execute_write``, and must not hand it a
    probe that can raise for a refusal.
    """
    if result.ok:
        return result
    raise RecipeRefusal(
        f"recipe refused before write: {result.action} — {result.reason}"
    )


# ── Readback gating (C6: native IDs + saved state on every create) ───────────

class ReadbackIncomplete(AssertionError):
    """A create did not prove its native identity or its saved state."""


def extract_native_id(kind: str, payload: Dict[str, Any]) -> str:
    """Pull the native id out of a create response, kind by kind.

    Only shapes that were actually captured are handled. The step/page case
    reuses ``ghl_rest_canvas.created_page_id`` (the live-captured
    ``page._ref._path.segments`` walk) rather than re-deriving it. Anything
    else raises instead of guessing a key.
    """
    schema = schema_for(kind)
    if not isinstance(payload, dict):
        raise ReadbackIncomplete(f"{kind} create response is not a dict")
    if kind in (KIND_STEP, KIND_PAGE) and isinstance(payload.get("page"), dict):
        import ghl_rest_canvas  # read-only reuse; no edit, no call
        try:
            return ghl_rest_canvas.created_page_id(payload)
        except (KeyError, TypeError) as exc:
            raise ReadbackIncomplete(
                f"{kind} create response 'page' carries no captured id shape: {exc}"
            ) from exc
    for f in schema.id_fields:
        value = payload.get(f)
        if value:
            return str(value).strip()
    raise ReadbackIncomplete(
        f"{kind} create response carries none of the captured id fields "
        f"{schema.id_fields}; the native id was not proven, so the create is "
        "not a success"
    )


def assert_readback(
    kind: str,
    create_response: Dict[str, Any],
    readback: Dict[str, Any],
    *,
    location_id: str,
    parent_id: str = "",
    saved_state_keys: Sequence[str] = (),
) -> str:
    """Prove a create landed: native id from the response, then the SAME id
    and the requested scope from an independent read, plus the saved-state
    keys the kind declares. Returns the proven native id.

    The read is the authority: a response id that the read cannot find is a
    failed create, never a pending one.
    """
    native_id = extract_native_id(kind, create_response)
    if not isinstance(readback, dict) or not readback:
        raise ReadbackIncomplete(
            f"{kind} {native_id}: no readback was supplied; a create without "
            "an authoritative read is unproven"
        )
    seen = str(readback.get("id") or readback.get("_id") or "").strip()
    if seen != native_id:
        raise ReadbackIncomplete(
            f"{kind}: create returned id {native_id!r} but the readback "
            f"reports {seen or '<none>'!r}; identity is unproven"
        )
    got_loc = str(
        readback.get("locationId") or readback.get("location_id") or ""
    ).strip()
    if got_loc != str(location_id).strip():
        raise ReadbackIncomplete(
            f"{kind} {native_id}: readback location {got_loc or '<none>'!r} "
            f"!= requested {location_id!r}"
        )
    schema = schema_for(kind)
    if schema.parent_field:
        got_parent = str(readback.get(schema.parent_field) or "").strip()
        for f in schema.fallback_parent_fields:
            if not got_parent:
                got_parent = str(readback.get(f) or "").strip()
        if got_parent != str(parent_id or "").strip():
            raise ReadbackIncomplete(
                f"{kind} {native_id}: readback parent "
                f"{got_parent or '<root>'!r} != requested "
                f"{parent_id or '<root>'!r} (wrong-parent landing)"
            )
    missing = [k for k in saved_state_keys if k not in readback]
    if missing:
        raise ReadbackIncomplete(
            f"{kind} {native_id}: readback is missing saved-state key(s) "
            f"{missing}; the save is not proven"
        )
    return native_id


# ── Publication gating (a recipe never publishes) ────────────────────────────

class PublicationRefused(AssertionError):
    """A recipe payload would publish or move live traffic."""


def assert_no_publication(payload: Dict[str, Any]) -> None:
    """Refuse any autosave/create payload that would publish.

    ``ghl_rest_canvas.autosave_body`` keeps a page UNPUBLISHED via
    ``pageType: "draft"`` (the live pointer never moves). This gate makes that
    a checked invariant instead of a default a caller can quietly override.
    """
    if not isinstance(payload, dict):
        raise PublicationRefused("payload must be a dict")
    page_type = str(payload.get("pageType") or "").strip().lower()
    if page_type and page_type != "draft":
        raise PublicationRefused(
            f"recipe payload sets pageType={page_type!r}; only 'draft' is "
            "permitted (publication is a separate, explicitly authorized step)"
        )
    if payload.get("publish") is True:
        raise PublicationRefused(
            "recipe payload sets publish=True; publication is never inferred "
            "from a build authorization"
        )
    for key in ("traffic", "control_traffic", "split"):
        if key in payload:
            raise PublicationRefused(
                f"recipe payload carries {key!r}; traffic/split changes belong "
                "to the disabled variant capability, never to a create recipe"
            )


# ── B18: llm_calls_during_recipe == 0 ───────────────────────────────────────

class RecipeLlmCallViolation(RuntimeError):
    """A general-purpose LLM call happened inside a click/fill/wait loop."""


class LlmCallGuard:
    """Bracket a known script's action loop; assert it made zero LLM calls.

    AI may plan, start, diagnose and repair a recipe OUTSIDE the loop (§10.2).
    Inside it, every call is a violation: it is non-deterministic, it bills per
    action, and it turns a replayable recipe into a prompt.
    """

    def __init__(self, recipe_id: str = "") -> None:
        self.recipe_id = str(recipe_id or "")
        self.calls: List[Dict[str, str]] = []

    def record(self, where: str, detail: str = "") -> None:
        self.calls.append({"where": str(where or ""), "detail": str(detail or "")})

    @property
    def count(self) -> int:
        return len(self.calls)

    def assert_zero(self) -> int:
        if self.calls:
            first = self.calls[0]
            raise RecipeLlmCallViolation(
                f"llm_calls_during_recipe={self.count} for recipe "
                f"{self.recipe_id or '<unnamed>'} (first at {first['where']!r}); "
                "known scripts perform zero LLM calls inside click/fill/wait "
                "loops (B18)"
            )
        return 0


# ── Recipe contract (§10.2 declaration) ─────────────────────────────────────

RECIPE_SEQUENCE: Tuple[str, ...] = (
    "validate_request",
    "admission",
    "browser_lease",
    "authenticate_and_verify_location",
    "reconcile",
    "execute",
    "readback",
    "verify",
    "receipt",
    "release",
)

EXECUTION_MODES: Tuple[str, ...] = ("rest_in_browser", "browser", "disabled")


class ContractError(ValueError):
    """A recipe contract is incomplete or internally inconsistent."""


@dataclass
class RecipeContract:
    """The declaration every P5 recipe must carry before it may run."""

    recipe_version: str
    object_kind: str
    execution_mode: str
    location_id: str
    parent_id: str
    parent_kind: str
    input_schema: Dict[str, str]
    idempotency_key: str
    auth_rail: str
    browser_lease_required: bool
    scoped_approval: str
    readback_contract: str
    expected_ui_baseline: str = ""
    expected_ui_baseline_status: str = ""

    def validate(self) -> "RecipeContract":
        schema = schema_for(self.object_kind)
        if not str(self.recipe_version or "").strip():
            raise ContractError("recipe_version is required")
        if self.execution_mode not in EXECUTION_MODES:
            raise ContractError(
                f"execution_mode {self.execution_mode!r} is not one of "
                f"{list(EXECUTION_MODES)}"
            )
        _req(self.location_id, "location_id")
        _req(self.idempotency_key, "idempotency_key")
        _req(self.auth_rail, "auth_rail")
        _req(self.scoped_approval, "scoped_approval")
        if str(self.scoped_approval).strip().upper() == "UNSET":
            raise ContractError(
                "scoped_approval is UNSET; a recipe may not run without an "
                "approval scoped to its account/location/parent (§10.2)"
            )
        _req(self.readback_contract, "readback_contract")
        pid = str(self.parent_id or "").strip()
        if pid == "" and "" not in schema.parent_kinds:
            raise ContractError(
                f"{self.object_kind} needs a parent_id (allowed: "
                f"{schema.parent_kinds})"
            )
        if pid != "" and self.parent_kind not in schema.parent_kinds:
            raise ContractError(
                f"{self.object_kind} may not hang under "
                f"{self.parent_kind!r}; allowed parents are "
                f"{schema.parent_kinds}"
            )
        if self.execution_mode == "disabled":
            raise ContractError(
                f"{self.object_kind} recipe is DISABLED ("
                f"{self.expected_ui_baseline_status or 'capability off'}); it "
                "cannot be validated as a runnable contract"
            )
        if (self.expected_ui_baseline_status
                == BASELINE_PENDING):
            raise ContractError(
                f"{self.object_kind} recipe names PENDING_LIVE_SELECTOR_CAPTURE; "
                "a pending capture is never a production recipe (§10.3)"
            )
        if self.idempotency_key.strip() == "name":
            raise ContractError(
                "idempotency_key may not be a bare name; use the scoped "
                "identity (kind+native_id+location+parent) per B09"
            )
        return self

    def validate_input(self, values: Dict[str, Any]) -> Dict[str, Any]:
        """Check a recipe's input against the declared schema. Extra keys are
        refused, not ignored: an unexpected input is an unreviewed input.

        ``native_id`` is the ONE allowed-optional key: it carries a previously
        recorded native id into reconciliation so a resume can prove the prior
        object instead of creating a second one (B07/B17). It is optional
        because a first run has no id to pass.
        """
        if not isinstance(values, dict):
            raise ContractError("recipe input must be a dict")
        missing = [k for k in self.input_schema if k not in values]
        if missing:
            raise ContractError(f"recipe input is missing required key(s) {missing}")
        allowed = set(self.input_schema) | {"native_id"}
        extra = [k for k in values if k not in allowed]
        if extra:
            raise ContractError(f"recipe input carries undeclared key(s) {extra}")
        return dict(values)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "recipe_version": self.recipe_version,
            "object_kind": self.object_kind,
            "execution_mode": self.execution_mode,
            "location_id": self.location_id,
            "parent_id": self.parent_id,
            "parent_kind": self.parent_kind,
            "input_schema": dict(self.input_schema),
            "idempotency_key": self.idempotency_key,
            "auth_rail": self.auth_rail,
            "browser_lease_required": self.browser_lease_required,
            "scoped_approval": self.scoped_approval,
            "readback_contract": self.readback_contract,
            "expected_ui_baseline": self.expected_ui_baseline,
            "expected_ui_baseline_status": self.expected_ui_baseline_status,
        }


def recipe_contract_for(kind: str, *, location_id: str, parent_id: str = "",
                        parent_kind: str = "", recipe_version: str = "v3.0",
                        execution_mode: str = "rest_in_browser",
                        auth_rail: str = "firebase_token_id",
                        scoped_approval: str = "") -> RecipeContract:
    """Build the DECLARED contract for one kind from the kind table.

    Defaults are deliberately conservative: the browser-lease requirement is
    true for every kind (all of these routes run inside a seeded eval), the UI
    baseline is the captured one for the kind, and a kind whose capture is
    still pending gets ``execution_mode="disabled"`` so it cannot validate.
    """
    schema = schema_for(kind)
    mode = execution_mode
    if schema.ui_baseline_status == BASELINE_PENDING:
        mode = "disabled"
    return RecipeContract(
        recipe_version=recipe_version,
        object_kind=kind,
        execution_mode=mode,
        location_id=location_id,
        parent_id=parent_id,
        parent_kind=parent_kind,
        input_schema={"name": "str", "slug": "str"},
        idempotency_key="scoped_identity(kind,native_id,location,parent)",
        auth_rail=auth_rail,
        browser_lease_required=True,
        scoped_approval=scoped_approval or "UNSET",
        readback_contract=schema.readback,
        expected_ui_baseline=schema.ui_baseline,
        expected_ui_baseline_status=schema.ui_baseline_status,
    )


# ── Self-test (pure; no network, no browser) ─────────────────────────────────

def _selftest() -> int:
    import sys

    errors: List[str] = []
    loc = "loc-selftest"

    funnel_folder = {"id": "ff1", "name": "ZHC A", "locationId": loc,
                     "type": "funnel"}
    website_folder = {"id": "wf1", "name": "ZHC A", "locationId": loc,
                      "type": "website"}

    r = reconcile([funnel_folder, website_folder], kind=KIND_FUNNEL_FOLDER,
                  location_id=loc, name="ZHC A")
    if r.action != REUSE or r.identity.native_id != "ff1":
        errors.append(f"funnel folder should reuse ff1, got {r.action} "
                      f"{r.identity and r.identity.native_id}")

    r = reconcile([funnel_folder], kind=KIND_WEBSITE_FOLDER, location_id=loc,
                  name="ZHC A")
    if r.action != CREATE:
        errors.append("a funnel folder must never satisfy a website folder "
                      f"request, got {r.action}")

    r = reconcile([{"id": "f9", "name": "ZHC A", "locationId": loc,
                    "parentId": "other-parent"}],
                  kind=KIND_FUNNEL, location_id=loc, parent_id="folder-1",
                  name="ZHC A")
    if r.action != REFUSE_COLLISION:
        errors.append(f"elsewhere collision must refuse, got {r.action}")

    r = reconcile([{"id": "f1", "name": "ZHC A", "locationId": loc,
                    "parentId": "p1"}],
                  kind=KIND_FUNNEL, location_id=loc, parent_id="p1",
                  native_id="f1")
    if r.action != REUSE:
        errors.append(f"second run must reuse, got {r.action}")

    r = reconcile([], kind=KIND_FUNNEL, location_id=loc, name="ZHC New",
                  read_complete=False)
    if r.action != REFUSE_UNPROVEN_READ:
        errors.append(f"unproven read must refuse, got {r.action}")

    guard = LlmCallGuard("selftest")
    if guard.assert_zero() != 0:
        errors.append("empty guard must report zero")
    guard.record("click", "x")
    try:
        guard.assert_zero()
        errors.append("a recorded call must raise")
    except RecipeLlmCallViolation:
        pass

    try:
        assert_no_publication({"pageType": "published"})
        errors.append("published payload must raise")
    except PublicationRefused:
        pass

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — ghl_recipe_objects identity + reconcile + gates "
          "(no network)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="offline selftest")
    ap.add_argument("--kinds", action="store_true", help="print the kind table")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.kinds:
        import json
        print(json.dumps(kind_table(), indent=2))
        return 0
    ap.print_help()
    return 2


__all__ = [
    "KIND_FUNNEL_FOLDER", "KIND_WEBSITE_FOLDER", "KIND_FUNNEL", "KIND_WEBSITE",
    "KIND_STEP", "KIND_PAGE", "KIND_VARIANT", "ALL_KINDS", "FOLDER_KINDS",
    "REUSE", "CREATE", "REFUSALS",
    "BASELINE_LOCKED", "BASELINE_RUNTIME_CAPTURE", "BASELINE_PENDING",
    "ObjectKindSchema", "schema_for", "kind_table",
    "ObjectIdentity", "build_identity", "IdentityError",
    "ReconcileResult", "reconcile", "RecipeRefusal", "assert_admissible",
    "ReadbackIncomplete", "extract_native_id", "assert_readback",
    "PublicationRefused", "assert_no_publication",
    "RecipeLlmCallViolation", "LlmCallGuard",
    "RECIPE_SEQUENCE", "EXECUTION_MODES", "RecipeContract", "ContractError",
    "recipe_contract_for",
]


if __name__ == "__main__":
    import sys
    sys.exit(main())
