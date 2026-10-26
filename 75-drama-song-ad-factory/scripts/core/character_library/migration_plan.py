#!/usr/bin/env python3
"""S75-T17: a reversible plan for migrating the character library's local IDs.

The local store (:mod:`character_library.character_library`) keys a saved
character by a *slug*, which is derived from the name the client typed. Three
things follow, and all three are read from the store itself, never assumed:

  * a SAVE record lives at ``<client>/character-library/<slug>/character.json``
    with ``schema: blackceo.character-library/v1`` plus its reference images;
  * a LIST record is the numbered offer the client was shown -- the position of
    a name in ``saved_character_question()`` -- so "2" means a different person
    as soon as one character is added;
  * a REUSE record is an intake-session answer to ``saved_character`` holding
    the option label (``Use Maya Lee``), the number shown, and the raw reply.

None of those is a stable identity. A stored ``slug`` is trusted by nobody
here: a record is migrated only when its identity is proved from its own
content and its own files -- the folder name, the slug field, the name the
slug claims to come from, the character.json bytes and the SHA-256 of every
reference image. A record that fails any of those checks is BLOCKED, and a plan
with a blocked record or an unresolved reuse reference applies nothing.

What apply writes is additive and deterministic: one identity file per record
and two maps under ``<client>/character-library/.identity-migration/``. The
saved records and every reuse session are left byte-for-byte alone, so the
migration is undone by deleting that one directory. Old IDs (``slug:``,
``name:``, ``use:``) are mapped once; a second apply recomputes the same
content-derived IDs, finds them already mapped, and writes nothing.

Dry run is the default. ``apply`` and ``reverse`` both require ``confirm=True``.

Stdlib only. No network, no credentials, no client data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile

try:                                        # imported as a package by pytest
    from . import character_library as _store
except ImportError:                         # run as a plain script (python3 -I)
    _here = os.path.dirname(os.path.abspath(__file__))
    if _here not in sys.path:
        sys.path.insert(0, _here)
    import character_library as _store

__all__ = [
    "MigrationError", "PlanRefused", "ConfirmationRequired", "StalePlan",
    "MigrationBlocked", "discover", "build_plan", "plan_digest", "apply",
    "reverse", "verify", "resolve", "new_identity", "content_digest",
    "PLAN_SCHEMA", "IDENTITY_SCHEMA", "ID_MAP_SCHEMA", "REFERENCES_SCHEMA",
    "HISTORY_SCHEMA",
    "LEGACY_RECORD_SCHEMA", "SESSION_SCHEMA", "MIGRATION_DIRNAME", "STATUSES",
]

PLAN_SCHEMA = "s75.character-library-migration/v1"
IDENTITY_SCHEMA = "s75.character-identity-map/v1"
ID_MAP_SCHEMA = "s75.character-id-map/v1"
REFERENCES_SCHEMA = "s75.character-migration-references/v1"
HISTORY_SCHEMA = "s75.character-migration-history/v1"
LEGACY_RECORD_SCHEMA = "blackceo.character-library/v1"
SESSION_SCHEMA = "blackceo.intake-session/v1"

#: One hidden directory, outside every saved record, so removal is the undo.
MIGRATION_DIRNAME = ".identity-migration"

#: Record statuses. Only MAPPED records get an identity file.
STATUSES = ("MAPPED", "BLOCKED")

#: Content fields that describe the person. Bookkeeping never enters the digest,
#: mirroring identity.py's own exclusion rule.
_CONTENT_FIELDS = ("name", "description", "voice_notes", "background", "ethnicity")

#: Every reuse question id the local card can raise for a saved character.
_REUSE_QUESTION_IDS = ("saved_character", "character")

_MAX_SESSION_FILES = 500          # bounded scan of a runs root
_MAX_SESSION_DEPTH = 4
_USE_PREFIX = "Use "

class MigrationError(ValueError):
    """Plain-English reason planning, applying or reversing stopped."""

class PlanRefused(MigrationError):
    """The plan itself is malformed or names a client folder it cannot read."""

class ConfirmationRequired(MigrationError):
    """An apply or a reverse ran without ``confirm=True``. Nothing was written."""

class StalePlan(MigrationError):
    """The local records changed after the plan was made. Nothing was written."""

class MigrationBlocked(MigrationError):
    """A record or reference could not be proved. Nothing was written."""

# --- plain values and hashing --------------------------------------------

def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")

def _digest(value):
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()

def _file_digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()

def _read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, ValueError):
        return None
    return loaded if type(loaded) is dict else None

def _atomic_json(path, value):
    folder = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".migration-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise

def _text(value):
    return value if type(value) is str else ""

def _rel(path, start):
    return os.path.relpath(os.path.abspath(path), os.path.abspath(start))

# --- content and identity provenance -------------------------------------

def content_digest(content, reference_digests):
    """Digest of what the record *is*: its content fields and its image bytes.

    The slug, the folder name and the JSON key order are deliberately absent, so
    a renamed folder or a reformatted file cannot pretend the person changed.
    """
    body = {"fields": {key: _text((content or {}).get(key))
                       for key in _CONTENT_FIELDS},
            "reference_digests": [str(d) for d in sorted(reference_digests or [])]}
    return _digest(body)

def new_identity(content_digest_value, slug):
    """The stable new ID: content-derived, with the old slug as the tie-break.

    Two distinct saved records with identical content are still two identities
    with their own history, so the slug is part of the derivation. The value is
    deterministic: the same record yields the same ID on every run.
    """
    if type(content_digest_value) is not str or not content_digest_value.startswith("sha256:"):
        raise MigrationError("A content digest is required to mint an identity.")
    slug = _text(slug).strip()
    if not slug:
        raise MigrationError("A saved record needs a slug to mint an identity.")
    raw = ("s75.character-identity/v1|" + content_digest_value + "|" + slug).encode("utf-8")
    return "ch-" + hashlib.sha256(raw).hexdigest()[:24]

def _read_save(root, folder_name, client_dir):
    """One actual save record, proved from its own bytes. Never trusts the slug."""
    folder = os.path.join(root, folder_name)
    path = os.path.join(folder, "character.json")
    record = _read_json(path)
    if record is None:
        return {"status": "BLOCKED", "old_slug": folder_name,
                "record_path": _rel(path, client_dir),
                "reason_code": "UNREADABLE_RECORD",
                "reason": "character.json is missing, unreadable or not an object."}
    if record.get("schema") != LEGACY_RECORD_SCHEMA:
        return {"status": "BLOCKED", "old_slug": folder_name,
                "record_path": _rel(path, client_dir),
                "reason_code": "UNKNOWN_RECORD_SCHEMA",
                "reason": "The record does not declare %s." % LEGACY_RECORD_SCHEMA}

    content = {key: _text(record.get(key)) for key in _CONTENT_FIELDS}
    stored_slug = _text(record.get("slug")).strip()
    try:
        derived_slug = _store.slugify(content["name"])
    except _store.LibraryError:
        derived_slug = ""
    if not content["name"] or not derived_slug:
        return {"status": "BLOCKED", "old_slug": folder_name,
                "record_path": _rel(path, client_dir),
                "reason_code": "NO_PROVABLE_NAME",
                "reason": "The record has no name a slug can be derived from."}
    if stored_slug != derived_slug or folder_name != derived_slug:
        return {"status": "BLOCKED", "old_slug": folder_name,
                "record_path": _rel(path, client_dir),
                "reason_code": "IDENTITY_CONFLICT",
                "reason": ("The folder %r, the stored slug %r and the name %r do "
                           "not agree, so the record's identity is not proved."
                           % (folder_name, stored_slug, content["name"]))}

    listed = record.get("reference_images")
    if type(listed) is not list or not listed:
        return {"status": "BLOCKED", "old_slug": folder_name,
                "record_path": _rel(path, client_dir),
                "reason_code": "NO_REFERENCE_IMAGES",
                "reason": "The record lists no reference image to prove it with."}
    references = []
    for entry in listed:
        rel = _text(entry)
        target = os.path.join(folder, rel)
        if not rel or not os.path.isfile(target):
            return {"status": "BLOCKED", "old_slug": folder_name,
                    "record_path": _rel(path, client_dir),
                    "reason_code": "MISSING_REFERENCE_IMAGE",
                    "reason": "A listed reference image is absent: %r." % (rel,)}
        references.append({"path": rel, "digest": _file_digest(target),
                           "bytes": os.path.getsize(target)})

    cd = content_digest(content, [r["digest"] for r in references])
    identity = {
        "schema": IDENTITY_SCHEMA,
        "new_id": new_identity(cd, folder_name),
        "status": "MAPPED",
        "old_slug": folder_name,
        "legacy_ids": ["slug:" + folder_name, "name:" + content["name"]],
        "content": content,
        "content_digest": cd,
        "identity_evidence": {
            "record_schema": record["schema"],
            "record_path": _rel(path, client_dir),
            "character_json_digest": _file_digest(path),
            "slug_stored": stored_slug,
            "slug_derived_from_name": derived_slug,
            "folder_matches_slug": True,
            "reference_images": references,
            "proved_by": ("schema + folder/slug/name agreement + character.json "
                          "digest + every reference image digest"),
        },
    }
    return identity

def _session_paths(runs_root, run_dirs):
    """Every actual intake session under the given run dirs / runs root."""
    found = []
    for run_dir in run_dirs or ():
        for name in ("intake-session.json", os.path.join("control", "intake-session.json")):
            candidate = os.path.join(str(run_dir), name)
            if os.path.isfile(candidate):
                found.append(os.path.abspath(candidate))
                break
    root = str(runs_root or "")
    if root and os.path.isdir(root):
        base_depth = root.rstrip(os.sep).count(os.sep)
        for current, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            if current.count(os.sep) - base_depth >= _MAX_SESSION_DEPTH:
                dirs[:] = []
            if "intake-session.json" in files:
                found.append(os.path.abspath(os.path.join(current, "intake-session.json")))
            if len(found) >= _MAX_SESSION_FILES:
                break
    return sorted(set(found))

def _read_session(path, by_name):
    """Reuse records from one session. Names, not bare numbers, identify a person."""
    session = _read_json(path)
    if session is None or session.get("schema") != SESSION_SCHEMA:
        return None, None
    references, records = [], session.get("answer_records")
    records = records if type(records) is dict else {}
    for question_id in sorted(records):
        record = records[question_id]
        if type(record) is not dict or question_id not in _REUSE_QUESTION_IDS:
            continue
        option = record.get("option") if type(record.get("option")) is dict else {}
        label = _text(option.get("label"))
        parsed = record.get("parsed") if type(record.get("parsed")) is dict else {}
        parsed_text = _text(parsed.get("text"))
        name = ""
        for candidate in (label, parsed_text):
            if candidate.startswith(_USE_PREFIX):
                name = candidate[len(_USE_PREFIX):].strip()
                break
        if not name:
            continue                        # "Create a new character": no saved target
        expected = by_name.get(name)
        entry = {
            "source": _rel(path, os.path.dirname(os.path.dirname(path))),
            "session_path": os.path.abspath(path),
            "session_digest": _file_digest(path),
            "question_id": question_id,
            "raw_answer": _text(record.get("raw_answer")),
            "option_number": option.get("number_shown"),
            "option_label": label or parsed_text,
            "old_id": "use:" + (label or parsed_text),
            "old_slug": expected["old_slug"] if expected else "",
            "new_id": expected["new_id"] if expected else "",
            "status": "RESOLVED" if expected else "UNRESOLVED",
            "reason_code": "" if expected else "REFERENCED_CHARACTER_NOT_FOUND",
        }
        if not expected:
            entry["reason"] = (
                "The session picked %r, but no saved record in this client's "
                "library proves that identity today." % (name,))
        references.append(entry)
    history = {
        "session_path": os.path.abspath(path),
        "session_digest": _file_digest(path),
        "events": len(session.get("events") or []),
        "answer_records": len(records),
        "active_question_ids": len(session.get("active_question_ids") or []),
    }
    return references, history

def discover(client_dir, *, runs_root="", run_dirs=()):
    """Read the ACTUAL local save, list and reuse records for one client.

    Returns a plain dict: records (each with provenance or a BLOCKED reason),
    the numbered list offer the client actually saw, reuse references, and the
    history digests of every session read. Read-only.
    """
    client = os.path.abspath(os.path.expanduser(str(client_dir)))
    root = os.path.join(client, _store.LIBRARY_DIRNAME)
    records = []
    if os.path.isdir(root):
        for name in sorted(os.listdir(root)):
            if name.startswith(".") or not os.path.isdir(os.path.join(root, name)):
                continue
            records.append(_read_save(root, name, client))

    by_name = {}
    for record in records:
        if record.get("status") != "MAPPED":
            continue
        name = record["content"]["name"]
        by_name.setdefault(name, record)     # first by slug order; collisions noted below

    collisions = sorted(name for name in by_name
                        if sum(1 for r in records
                               if r.get("status") == "MAPPED"
                               and r["content"]["name"] == name) > 1)

    # The list record is the offer the card actually renders, position included.
    list_record = {"source": "character_library.saved_character_question",
                   "offered": [], "catalog_names": []}
    try:
        question = _store.saved_character_question(client)
        catalog = _store.list_characters(client)
    except (_store.LibraryError, OSError):
        question, catalog = None, []
    list_record["catalog_names"] = [c.get("name", "") for c in catalog]
    if question:
        for position, (label, detail) in enumerate(question.get("options") or [], 1):
            list_record["offered"].append({"position": position,
                                           "label": _text(label),
                                           "detail": _text(detail)})

    reuse, history = [], []
    for path in _session_paths(runs_root, run_dirs):
        found, stats = _read_session(path, by_name)
        if found:
            reuse.extend(found)
        if stats:
            history.append(stats)

    return {"client_dir": client, "store_root": root,
            "records": records, "list_record": list_record,
            "reuse": reuse, "history": history,
            "ambiguous_names": collisions}

def build_plan(client_dir, *, runs_root="", run_dirs=()):
    """The full reversible plan. Dry run by default: this only reads."""
    inventory = discover(client_dir, runs_root=runs_root, run_dirs=run_dirs)
    mapped = [r for r in inventory["records"] if r.get("status") == "MAPPED"]
    blocked = [r for r in inventory["records"] if r.get("status") != "MAPPED"]

    legacy, legacy_problems = {}, []
    for record in mapped:
        for old_id in record["legacy_ids"]:
            if old_id.startswith("name:") and record["content"]["name"] in inventory["ambiguous_names"]:
                legacy_problems.append({"old_id": old_id, "new_id": record["new_id"],
                                        "reason_code": "AMBIGUOUS_OLD_ID"})
                continue
            prior = legacy.get(old_id)
            if prior is not None and prior != record["new_id"]:
                legacy_problems.append({"old_id": old_id, "new_id": record["new_id"],
                                        "reason_code": "OLD_ID_CLAIMED_TWICE"})
                continue
            legacy[old_id] = record["new_id"]
    for reference in inventory["reuse"]:
        if reference["status"] == "RESOLVED":
            prior = legacy.get(reference["old_id"])
            if prior is None:
                legacy[reference["old_id"]] = reference["new_id"]

    plan = {
        "schema": PLAN_SCHEMA,
        "dry_run": True,
        "client_dir": inventory["client_dir"],
        "inputs": {"runs_root": str(runs_root or ""),
                   "run_dirs": sorted(str(d) for d in (run_dirs or ()))},
        "store_root": inventory["store_root"],
        "migration_dir": os.path.join(inventory["store_root"], MIGRATION_DIRNAME),
        "records": inventory["records"],
        "legacy_ids": dict(sorted(legacy.items())),
        "legacy_id_problems": legacy_problems,
        "ambiguous_names": inventory["ambiguous_names"],
        "list_record": inventory["list_record"],
        "reuse": inventory["reuse"],
        "history": inventory["history"],
        "counts": {
            "records": len(inventory["records"]),
            "mapped": len(mapped),
            "blocked": len(blocked),
            "reuse_resolved": sum(1 for r in inventory["reuse"] if r["status"] == "RESOLVED"),
            "reuse_unresolved": sum(1 for r in inventory["reuse"] if r["status"] != "RESOLVED"),
            "legacy_ids": len(legacy),
        },
    }
    plan["plan_digest"] = plan_digest(plan)
    return plan

def plan_digest(plan):
    """Digest of everything an apply depends on, so a stale plan is refused."""
    body = {key: plan.get(key) for key in
            ("client_dir", "store_root", "records", "legacy_ids",
             "legacy_id_problems", "reuse", "history", "list_record")}
    return _digest(body)

def _identity_body(record, client_dir):
    body = dict(record)
    body["record_path"] = _rel(os.path.join(client_dir, _store.LIBRARY_DIRNAME,
                                            record["old_slug"]), client_dir)
    return body

def _id_map_document(plan):
    records = {}
    for record in plan["records"]:
        if record.get("status") != "MAPPED":
            continue
        records[record["new_id"]] = {
            "new_id": record["new_id"],
            "old_slug": record["old_slug"],
            "legacy_ids": list(record["legacy_ids"]),
            "content_digest": record["content_digest"],
            "identity_file": "identities/%s.json" % record["new_id"],
            "record_path": _rel(os.path.join(plan["store_root"], record["old_slug"]),
                                plan["client_dir"]),
        }
    return {
        "schema": ID_MAP_SCHEMA,
        "records": dict(sorted(records.items())),
        "legacy_ids": dict(sorted(plan["legacy_ids"].items())),
        "counts": {"records": len(records), "legacy_ids": len(plan["legacy_ids"])},
    }

def _references_document(plan):
    return {
        "schema": REFERENCES_SCHEMA,
        "references": [{key: reference.get(key) for key in
                        ("source", "session_path", "session_digest", "question_id",
                         "raw_answer", "option_number", "option_label", "old_id",
                         "old_slug", "new_id", "status", "reason_code")}
                       for reference in plan["reuse"]],
    }

def _history_document(plan):
    """The sessions whose history the migration must not disturb."""
    return {
        "schema": HISTORY_SCHEMA,
        "sessions": [{key: entry.get(key) for key in
                      ("session_path", "session_digest", "events",
                       "answer_records", "active_question_ids")}
                     for entry in plan["history"]],
    }

def _blocked_reasons(plan):
    reasons = []
    if plan["counts"]["blocked"]:
        reasons.append("BLOCKED_RECORDS")
    if plan["counts"]["reuse_unresolved"]:
        reasons.append("UNRESOLVED_REUSE_REFERENCES")
    if plan["legacy_id_problems"]:
        reasons.append("OLD_ID_CONFLICT")
    return reasons

def apply(plan, *, confirm=False):
    """Write the migration. Dry run unless ``confirm=True`` is passed.

    Nothing is written when the plan was not confirmed, when the local records
    changed since the plan was made, or when any record or reference could not
    be proved. A second apply of the same state is a no-op: every ID is already
    mapped and no file is rewritten.
    """
    if type(plan) is not dict or plan.get("schema") != PLAN_SCHEMA:
        raise PlanRefused("Apply needs a plan made by build_plan().")
    if confirm is not True:
        raise ConfirmationRequired(
            "This is a dry run. Nothing was written. Re-run with confirm=True "
            "to apply the plan.")
    inputs = plan.get("inputs") or {}
    fresh = build_plan(plan["client_dir"],
                       runs_root=inputs.get("runs_root", ""),
                       run_dirs=inputs.get("run_dirs") or ())
    if plan_digest(fresh) != plan.get("plan_digest"):
        raise StalePlan(
            "The local records changed after this plan was made, so nothing "
            "was written. Make a new plan and show it before applying.")
    reasons = _blocked_reasons(plan)
    if reasons:
        raise MigrationBlocked(
            "Refusing to migrate while local evidence is incomplete (%s). "
            "Nothing was written; fix the named records and plan again."
            % ", ".join(reasons))

    migration_dir = plan["migration_dir"]
    id_map_path = os.path.join(migration_dir, "id-map.json")
    history_path = os.path.join(migration_dir, "history.json")
    references_path = os.path.join(migration_dir, "references.json")
    wanted = _id_map_document(plan)
    wanted_history = _history_document(plan)
    wanted_references = _references_document(plan)
    if (_read_json(id_map_path) == wanted
            and _read_json(history_path) == wanted_history
            and _read_json(references_path) == wanted_references):
        return {"status": "NOOP", "applied": False, "mapped_new": [],
                "written": [], "plan_digest": plan["plan_digest"],
                "message": "Every old ID is already mapped; nothing was written."}

    written = []
    for record in plan["records"]:
        if record.get("status") != "MAPPED":
            continue
        path = os.path.join(migration_dir, "identities", record["new_id"] + ".json")
        body = _identity_body(record, plan["client_dir"])
        if _read_json(path) != body:
            _atomic_json(path, body)
            written.append(path)
    if _read_json(references_path) != wanted_references:
        _atomic_json(references_path, wanted_references)
        written.append(references_path)
    if _read_json(history_path) != wanted_history:
        _atomic_json(history_path, wanted_history)
        written.append(history_path)
    _atomic_json(id_map_path, wanted)       # last: the map is the commit point
    written.append(id_map_path)
    return {"status": "APPLIED", "applied": True,
            "mapped_new": sorted(wanted["records"]),
            "written": written, "plan_digest": plan["plan_digest"],
            "message": "Mapped %d saved record(s) and %d old ID(s)."
                       % (len(wanted["records"]), len(wanted["legacy_ids"]))}

def reverse(client_dir, *, confirm=False):
    """Undo the migration by removing the one directory it created.

    Saved records and reuse sessions are never written by apply, so removing
    the migration directory restores the tree byte for byte.
    """
    if confirm is not True:
        raise ConfirmationRequired(
            "Reversing the migration removes %s. Re-run with confirm=True."
            % MIGRATION_DIRNAME)
    client = os.path.abspath(os.path.expanduser(str(client_dir)))
    migration_dir = os.path.join(client, _store.LIBRARY_DIRNAME, MIGRATION_DIRNAME)
    if not os.path.isdir(migration_dir):
        return {"status": "NOTHING_TO_REVERSE", "removed": []}
    removed = sorted(os.path.join(current, name)
                     for current, _dirs, files in os.walk(migration_dir)
                     for name in files)
    shutil.rmtree(migration_dir)
    return {"status": "REVERSED", "removed": removed}

def resolve(document, old_id):
    """Resolve one old ID from an applied id-map, or None."""
    if type(document) is not dict:
        return None
    return (document.get("legacy_ids") or {}).get(str(old_id))

def verify(client_dir):
    """Prove an applied migration still resolves: IDs, records and references.

    Every mapped record's identity file must still match the record's content
    digest, and every reuse reference must resolve to one of those records and
    to an unchanged session file.
    """
    client = os.path.abspath(os.path.expanduser(str(client_dir)))
    migration_dir = os.path.join(client, _store.LIBRARY_DIRNAME, MIGRATION_DIRNAME)
    id_map = _read_json(os.path.join(migration_dir, "id-map.json"))
    references = _read_json(os.path.join(migration_dir, "references.json"))
    history = _read_json(os.path.join(migration_dir, "history.json"))
    if id_map is None or references is None:
        raise MigrationError("No applied migration was found to verify.")
    problems, checked = [], []
    inventory = discover(client)
    by_slug = {r["old_slug"]: r for r in inventory["records"]
               if r.get("status") == "MAPPED"}
    for new_id, entry in sorted((id_map.get("records") or {}).items()):
        record = by_slug.get(entry.get("old_slug"))
        identity = _read_json(os.path.join(migration_dir, entry.get("identity_file", "")))
        target = os.path.join(client, entry.get("record_path", ""))
        if record is None or not os.path.isdir(target):
            problems.append({"new_id": new_id, "reason_code": "RECORD_MISSING"})
        elif identity is None or identity.get("content_digest") != record["content_digest"]:
            problems.append({"new_id": new_id, "reason_code": "IDENTITY_DRIFTED"})
        else:
            checked.append(new_id)
    resolved = 0
    for reference in references.get("references") or []:
        old_id = reference.get("old_id")
        new_id = resolve(id_map, old_id)
        if not new_id or new_id not in (id_map.get("records") or {}):
            problems.append({"old_id": old_id, "reason_code": "REFERENCE_UNRESOLVED"})
            continue
        if reference.get("session_path") and os.path.isfile(reference["session_path"]):
            if _file_digest(reference["session_path"]) != reference.get("session_digest"):
                problems.append({"old_id": old_id,
                                 "reason_code": "SESSION_HISTORY_CHANGED"})
                continue
        resolved += 1
    retained = 0
    for entry in (history or {}).get("sessions") or []:
        path = entry.get("session_path")
        if not path:
            continue
        if not os.path.isfile(path):
            problems.append({"session_path": path, "reason_code": "HISTORY_MISSING"})
            continue
        if _file_digest(path) != entry.get("session_digest"):
            problems.append({"session_path": path, "reason_code": "HISTORY_CHANGED"})
            continue
        retained += 1
    return {"ok": not problems, "records_checked": len(checked),
            "references_resolved": resolved, "history_retained": retained,
            "problems": problems}

# --- CLI -----------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Plan, apply, verify or reverse the character-library "
                    "identity migration. Dry run unless --apply or --reverse.")
    ap.add_argument("--client-dir", required=True,
                    help="The client's own data folder.")
    ap.add_argument("--runs-root", default="",
                    help="Folder to scan for actual intake sessions (reuse records).")
    ap.add_argument("--run-dir", action="append", default=[],
                    help="One run folder holding a control/intake-session.json.")
    ap.add_argument("--apply", action="store_true", help="Apply the plan.")
    ap.add_argument("--reverse", action="store_true", help="Undo the migration.")
    ap.add_argument("--verify", action="store_true", help="Check an applied migration.")
    ap.add_argument("--confirm", action="store_true",
                    help="Required with --apply or --reverse.")
    args = ap.parse_args(argv)
    try:
        if args.reverse:
            print(json.dumps(reverse(args.client_dir, confirm=args.confirm), indent=2))
            return 0
        if args.verify:
            print(json.dumps(verify(args.client_dir), indent=2))
            return 0
        plan = build_plan(args.client_dir, runs_root=args.runs_root,
                          run_dirs=args.run_dir)
        if args.apply:
            print(json.dumps(apply(plan, confirm=args.confirm), indent=2))
            return 0
        plan["dry_run"] = True
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    except ConfirmationRequired as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except (MigrationError, _store.LibraryError) as exc:
        print(str(exc), file=sys.stderr)
        return 4

if __name__ == "__main__":
    sys.exit(main())
