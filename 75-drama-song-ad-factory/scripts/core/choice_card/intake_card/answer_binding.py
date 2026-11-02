"""Exact saved-answer binding for the MUSIC STYLE question (C05/F8 seed).

Derived only from the intake session's persisted answer record:

* the immutable question snapshot that was actually rendered,
* its definition digest and full rendered-question digest,
* the exact raw client reply,
* the offered option identity and the number shown at answer time,
* the recorded source reference.

The style is resolved from the label shown at answer time against the frozen
snapshot, then to the one canonical catalog id. The current menu is never read
to reinterpret an old numeric reply; old 1/2/3 answers therefore keep the
original three meanings.

F8 trusted ingress is NOT implemented or claimed. This module binds the
provenance that was persisted; it does not create it. A record carrying an
explicit synthetic-test marker is returned as ``test_only`` and can never be
reported as a human production fact.

stdlib only. No network, no provider call, no spend, no file writes.
"""
from __future__ import annotations

import json
from pathlib import Path

SCHEMA = "blackceo.intake-answer-binding/v1"
QUESTION_ID = "music"
SOURCE_PRODUCTION = "client"
INGRESS_AUTHORITY = "UNRESOLVED_F8"

_SYNTHETIC_ORIGINS = frozenset({
    "synthetic_test", "synthetic-test", "test_only", "test-only", "test",
    "synthetic_test_only", "synthetic-test-only",
})
_SYNTHETIC_KINDS = frozenset({
    "synthetic_test", "synthetic-test", "test_only", "test-only",
})
_SYNTHETIC_REF_PREFIXES = ("test:", "test-only:", "synthetic:")


class BindingError(ValueError):
    """A refused binding: missing provenance, changed bytes, or unknown style."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _session():
    try:
        from . import intake_session as session
    except ImportError:
        import intake_session as session
    return session


def _catalog():
    from music_styles import catalog
    return catalog


def _targets():
    from music_styles import style_targets
    return style_targets


def _digest(value):
    # ONE digest implementation: the session that wrote the records.
    return _session()._digest(value)


def _is_synthetic(record):
    origin = str(record.get("origin") or "").strip().lower()
    kind = str(record.get("provenance_kind") or "").strip().lower()
    ref = str(record.get("source_ref") or "").strip().lower()
    return (origin in _SYNTHETIC_ORIGINS or kind in _SYNTHETIC_KINDS
            or any(ref.startswith(p) for p in _SYNTHETIC_REF_PREFIXES))


def _style_id_for_label(label, catalog):
    """Exact label -> one catalog id. Never position, never fuzzy inference."""
    if not isinstance(label, str) or not label.strip():
        raise BindingError("BINDING_STYLE_UNKNOWN", "no shown style label")
    exact = [sid for sid in catalog.STYLE_IDS
             if catalog.CATALOG[sid]["label"] == label]
    if not exact:
        folded = label.strip().casefold()
        exact = [sid for sid in catalog.STYLE_IDS
                 if catalog.CATALOG[sid]["label"].strip().casefold() == folded]
    if len(exact) != 1:
        raise BindingError(
            "BINDING_STYLE_UNKNOWN",
            "%r matches %d catalog styles: %r" % (label, len(exact), exact))
    return exact[0]


def bind_saved_answer(record, *, allow_synthetic=False):
    """Bind one persisted ``answer_records['music']`` row.

    ``allow_synthetic=False`` refuses an explicitly marked test record rather
    than letting it flow as a production answer. ``True`` returns it with
    ``production_fact`` False and ``test_only`` True.
    """
    if not isinstance(record, dict):
        raise BindingError("BINDING_RECORD_REQUIRED",
                           "an answer record object is required")
    question_id = record.get("question_id")
    if question_id != QUESTION_ID:
        raise BindingError("BINDING_QUESTION_MISMATCH",
                           "record question_id is %r, expected %r"
                           % (question_id, QUESTION_ID))
    if record.get("accepted") is not True:
        raise BindingError("BINDING_NOT_ACCEPTED",
                           "only an accepted client answer can be bound")

    definition = record.get("question")
    rendered = record.get("rendered_question")
    raw = record.get("raw_answer")
    parsed = record.get("parsed")
    option = record.get("option")
    if not isinstance(definition, dict) or not isinstance(rendered, str):
        raise BindingError("BINDING_QUESTION_SNAPSHOT_MISSING",
                           "the immutable question snapshot and its text are required")
    if not isinstance(raw, str) or not isinstance(parsed, dict) or not isinstance(option, dict):
        raise BindingError("BINDING_ANSWER_FIELDS_MISSING",
                           "raw_answer, parsed and option are required")

    if _digest(definition) != record.get("definition_digest"):
        raise BindingError("BINDING_DEFINITION_DIGEST_MISMATCH",
                           "the question snapshot no longer matches its digest")
    if _digest({"id": question_id, "definition": definition,
                "message": rendered}) != record.get("question_digest"):
        raise BindingError("BINDING_QUESTION_DIGEST_MISMATCH",
                           "the rendered question no longer matches its digest")
    if parsed.get("id") != question_id:
        raise BindingError("BINDING_QUESTION_ID_MISMATCH",
                           "stored answer or option names a different question")

    source = record.get("source")
    source_ref = record.get("source_ref")
    if not isinstance(source_ref, str) or not source_ref.strip():
        raise BindingError("BINDING_SOURCE_REF_REQUIRED",
                           "the exact client reply needs a source reference")
    synthetic = _is_synthetic(record)
    if synthetic and not allow_synthetic:
        raise BindingError(
            "BINDING_SYNTHETIC_NOT_ALLOWED",
            "this is a marked synthetic test; pass allow_synthetic=True and "
            "carry test_only downstream, never a human production fact")
    if source != SOURCE_PRODUCTION and not synthetic:
        raise BindingError("BINDING_PROVENANCE_REFUSED",
                           "source %r is not an accepted client or marked test"
                           % (source,))

    # The raw reply, the parsed answer and the option identity must agree.
    session = _session()
    verified = session._parse(raw, definition)
    if not verified or verified.get("error"):
        raise BindingError("BINDING_INVALID_OPTION",
                           "the saved raw reply is not an offered option")
    verified["id"] = question_id
    if session._dump(verified) != session._dump(parsed):
        raise BindingError("BINDING_RAW_ANSWER_MISMATCH",
                           "the saved parsed answer differs from the raw reply")
    if session._dump(session._option(definition, verified)) != session._dump(option):
        raise BindingError("BINDING_OPTION_MISMATCH",
                           "the saved option identity differs from the raw reply")

    number = option.get("number_shown")
    options = definition.get("options")
    if type(number) is not int or not isinstance(options, list) or not 1 <= number <= len(options):
        raise BindingError("BINDING_OPTION_MISMATCH",
                           "the shown option number is outside the frozen menu")
    snapshot = options[number - 1]
    if not isinstance(snapshot, (list, tuple)) or len(snapshot) < 1 or snapshot[0] != option.get("label"):
        raise BindingError("BINDING_OPTION_MISMATCH",
                           "the frozen menu row does not carry the shown label")

    catalog = _catalog()
    style_id = _style_id_for_label(snapshot[0], catalog)
    target = _targets().target(style_id)
    synthetic = bool(synthetic)
    return {
        "schema": SCHEMA,
        "question_id": question_id,
        "raw_answer": raw,
        "source": source,
        "source_ref": source_ref,
        "origin": "synthetic_test_only" if synthetic else "client_recorded",
        "production_fact": not synthetic,
        "test_only": synthetic,
        "ingress_authority": INGRESS_AUTHORITY,
        "question_digest": record["question_digest"],
        "definition_digest": record["definition_digest"],
        "rendered_question": rendered,
        "number_shown": number,
        "snapshot_option": {
            "number": number,
            "label": snapshot[0],
            "description": snapshot[1] if len(snapshot) > 1 else None,
        },
        "style_id": style_id,
        "style_label": catalog.CATALOG[style_id]["label"],
        "catalog_revision": catalog.CATALOG_REVISION,
        "recipe_revision": catalog.CATALOG[style_id]["recipe_revision"],
        "target": target,
    }


def bind_run(run_dir, *, question_id=QUESTION_ID, allow_synthetic=False):
    """Bind the music answer persisted in ``<run>/control/intake-session.json``.

    A caller-supplied style id is not accepted anywhere: the only style source
    is the session's own frozen answer record.
    """
    path = Path(run_dir) / "control" / "intake-session.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BindingError("BINDING_SESSION_UNREADABLE",
                           "cannot read %s: %s" % (path, exc))
    session = _session()
    if not isinstance(state, dict) or state.get("schema") != session.SCHEMA:
        raise BindingError("BINDING_SESSION_UNREADABLE",
                           "unrecognised intake session schema at %s" % path)
    records = state.get("answer_records")
    record = records.get(question_id) if isinstance(records, dict) else None
    if record is None:
        raise BindingError("BINDING_ANSWER_MISSING",
                           "no saved %r answer in %s" % (question_id, path))
    bound = bind_saved_answer(record, allow_synthetic=allow_synthetic)
    bound["session_path"] = str(path)
    bound["session_done"] = bool(state.get("done"))
    bound["recap_confirmed"] = isinstance(state.get("confirmation"), dict)
    return bound


def request_handoff(binding):
    """The exact fields a request producer may consume from a binding.

    It carries the style id plus the frozen answer identity, so a hand-built
    request cannot swap the style or invent an answer.
    """
    if not isinstance(binding, dict) or binding.get("schema") != SCHEMA:
        raise BindingError("BINDING_REQUIRED",
                           "a bound saved answer is required")
    target = binding.get("target") or {}
    return {
        "style_id": binding["style_id"],
        "style_label": binding["style_label"],
        "catalog_revision": binding["catalog_revision"],
        "recipe_revision": binding["recipe_revision"],
        "provider_compiler": target.get("provider_compiler"),
        "record_source": target.get("record_source"),
        "template_kind": target.get("template_kind"),
        "question_id": binding["question_id"],
        "question_digest": binding["question_digest"],
        "raw_answer": binding["raw_answer"],
        "source": binding["source"],
        "source_ref": binding["source_ref"],
        "origin": binding["origin"],
        "production_fact": binding["production_fact"],
        "test_only": binding["test_only"],
        "ingress_authority": binding["ingress_authority"],
    }


def assert_style_matches(style_id, binding):
    """Refuse a request whose style differs from the saved answer."""
    if not isinstance(binding, dict) or binding.get("schema") != SCHEMA:
        raise BindingError("BINDING_REQUIRED",
                           "an assert against a request needs a bound answer")
    if style_id != binding.get("style_id"):
        raise BindingError(
            "BINDING_STYLE_MISMATCH",
            "request style %r differs from the saved answer %r"
            % (style_id, binding.get("style_id")))
    return True
