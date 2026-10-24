"""Read-only admission for governed Skill 75 production.

Dependency diagnostics and unaccepted creative drafts need no permission from
this module. Production does: an intake confirmation, the existing stage graph
and current artifact decisions must agree. A free-standing authorization or
four-pick JSON receipt is not an authority path.

This checks the supported application protocol, not the identity of a person
with unrestricted filesystem/code access. Such a writer can forge histories or
change the checks; no filesystem/credential security boundary is claimed here.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import shutil
import tempfile
from urllib.parse import quote, urlsplit


def validate_upload_url(value):
    """Parse an HTTPS upload URL locally; this never opens a connection."""
    if not isinstance(value, str) or not value or any(c.isspace() or ord(c) < 32 for c in value):
        return False
    try:
        parsed = urlsplit(value)
        return bool(parsed.scheme == "https" and parsed.netloc and parsed.hostname
                    and parsed.username is None and parsed.password is None
                    and (parsed.port is None or parsed.port > 0))
    except ValueError:
        return False


def _read(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def _result(ok, code, detail, **context):
    return dict(ok=ok, reason_code=code, detail=detail,
                next_action=("Claim the admitted stage through its supported runner."
                             if ok else "Preserve the run and resume its governed intake/stage or artifact approval."),
                **context)


def _graph():
    # Reuse the published, validated graph. Never maintain a second stage list.
    from batch_mode.batch import STAGES
    from intake_preflight import factory
    problems = factory.validate_registry()
    order = tuple(stage for stage, _ in STAGES)
    if problems or order != tuple(factory.CANONICAL_STAGES):
        raise ValueError("the canonical stage registry cannot be validated")
    return order, factory.STAGE_REGISTRY


def _snapshot(run_dir, run_id=None):
    """No Store constructor or sidecar writes in the source run.

    A live WAL must not be ignored: it may contain a newly parked/waiting
    stage. Read a stable private copy when one exists; never recover the
    source store. TemporaryDirectory follows the caller's configured TMPDIR.
    """
    db = Path(run_dir) / "control" / "state.sqlite3"
    if not db.is_file():
        raise ValueError("the canonical control/state.sqlite3 is missing")
    def read(path, *, immutable):
        uri = "file:" + quote(str(path.resolve())) + "?mode=ro" + ("&immutable=1" if immutable else "")
        with closing(sqlite3.connect(uri, uri=True)) as con:
            con.execute("PRAGMA query_only=ON")
            rows = con.execute("SELECT run_id, stage, state FROM stages").fetchall()
            ids = {row[0] for row in rows}
            if len(ids) != 1 or not next(iter(ids), None):
                raise ValueError("the stage store does not identify one unambiguous run")
            held_id = next(iter(ids))
            if run_id is not None and str(run_id) != held_id:
                raise ValueError("the requested run id differs from the stage store")
            events = con.execute("SELECT stage, kind, detail, at FROM events WHERE run_id=? ORDER BY at, rowid",
                                 (held_id,)).fetchall()
            lock = con.execute("SELECT model FROM video_model_lock WHERE run_id=?", (held_id,)).fetchone()
        if not lock or not lock[0]:
            raise ValueError("the run has no recorded video-model lock")
        return held_id, {s: state for _, s, state in rows}, events, lock[0]
    paths = [Path(str(db) + suffix) for suffix in ("", "-wal", "-shm")]
    def stamp():
        return [(p.stat().st_ino, p.stat().st_size, p.stat().st_mtime_ns) if p.exists() else None for p in paths]
    before = stamp()
    wal = paths[1]
    if not wal.exists() or wal.stat().st_size == 0:
        result = read(db, immutable=True)
    else:
        with tempfile.TemporaryDirectory(prefix="s75-production-read-") as tmp:
            for path in paths:
                if path.exists():
                    shutil.copyfile(path, Path(tmp) / path.name)
            if stamp() != before:
                raise ValueError("the stage store changed during admission; recheck the current run")
            result = read(Path(tmp) / db.name, immutable=False)
    if stamp() != before:
        raise ValueError("the stage store changed during admission; recheck the current run")
    return result


def _preferences(rows):
    out = {}
    for qid in ("script", "song", "storyboard"):
        row = rows.get(qid)
        if not isinstance(row, dict) or type(row.get("n")) is not int or row["n"] not in (1, 2):
            raise ValueError("the saved %s approval preference is unknown" % qid)
        out[qid] = row["n"] == 1
    return out


def _session_authority(run_dir, state, run_id, live_model):
    from choice_card.intake_card import intake_card as card
    from choice_card.intake_card import intake_session
    from script_approval import card_answers
    status = intake_session.completion_status(run_dir)
    if not status.get("valid") or not status.get("done"):
        return _result(False, status.get("reason_code") or "INTAKE_NOT_CONFIRMED",
                       status.get("detail") or "The exact intake has no valid explicit client recap confirmation.")
    if state.get("run_id") != run_id:
        return _result(False, "PRODUCTION_RUN_ID_MISMATCH", "Intake and stage store identify different runs.")
    provider = state["answer_records"]["model"]["provider_identity"]
    expected_model = provider.get("lock") or provider["kie_model"]
    binding = state.get("model_lock") or {}
    # completion_status preserves its immutable read-only legacy projection.
    # The live WAL snapshot is authoritative for the *current* DB lock; it
    # must still equal the exact provider identity the client confirmed.
    if (live_model != expected_model or live_model != binding.get("model") or
            binding.get("provider_identity") != provider):
        return _result(False, "PRODUCTION_VIDEO_MODEL_LOCK_MISMATCH",
                       "The live video-model lock differs from the exact confirmed intake provider choice.")
    required = state["required_question_ids"]
    # completion_status also supports small renderer tests. Production must
    # contain the real card inventory; a caller-supplied one-question card must
    # never authorize an ad. Revisions keep their own exact saved definitions.
    expected = {q["id"] for q in card.QUESTIONS}
    if "episode_length" in required:
        expected.discard("length")
        expected.add("episode_length")
    if state.get("purpose_flow"):
        expected.add("purpose")
    if not expected.issubset(required):
        return _result(False, "PRODUCTION_INTAKE_INCOMPLETE", "The confirmed session omits required production question identities.")
    saved = card_answers.load(str(run_dir))
    if saved.get("state") != card_answers.OK:
        return _result(False, "PRODUCTION_ANSWER_HANDOFF_MISMATCH", "The saved production answers are unreadable.")
    rows = saved["by_id"]
    for qid in required:
        parsed = state["answer_records"][qid]["parsed"]
        actual = rows.get(qid)
        if not isinstance(actual, dict) or any(actual.get(k) != v for k, v in parsed.items()):
            return _result(False, "PRODUCTION_ANSWER_HANDOFF_MISMATCH",
                           "The saved %s answer differs from its authoritative raw client reply." % qid)
    return _result(True, "PRODUCTION_INTAKE_CONFIRMED", "Exact client answers and recap confirmation are preserved.",
                   authority="intake-session", preferences=_preferences(rows),
                   confirmation_digest=state["confirmation"]["question_digest"])


def _script_proof(run_dir, run_id, *, required=True):
    """Validate the existing whole-package decision, never a supplied override."""
    from script_approval import approval_events as events
    from script_approval import script_approval as approval
    from script_approval import stage as script_stage
    doc = script_stage._doc(str(run_dir))
    if doc is None:
        return _result(False, "PRODUCTION_SCRIPT_MISSING", "The actual whole script/lyrics artifact is missing.")
    title, story, sheet, lyrics, _ = doc
    hashes = {"script": approval.script_sha(title, story, sheet), "lyrics": approval.lyrics_sha(lyrics)}
    if not required:
        return _result(True, "PRODUCTION_SCRIPT_NOT_REQUESTED", "The client explicitly declined the script approval gate.",
                       approved_script=dict(script_sha256=hashes["script"], lyrics_sha256=hashes["lyrics"], path=str(Path(run_dir) / "creative" / "script.json"), required=False))
    status, rec = events.load_record(str(run_dir))
    if status != "ok" or not isinstance(rec, dict) or events.is_unknown_record(rec):
        return _result(False, "PRODUCTION_SCRIPT_APPROVAL_MISSING", "The whole script and lyrics have no readable artifact approval.")
    old_refusal = approval.check_script_approval(rec, lyrics)
    if old_refusal:
        return _result(False, old_refusal["reason_code"], old_refusal["detail"])
    bound_run = rec.get("run_id") or (rec.get("run") or {}).get("run_id")
    if bound_run and str(bound_run) != run_id:
        return _result(False, "PRODUCTION_APPROVAL_SCOPE_MISMATCH", "The script approval belongs to another run.")
    # Legacy aggregate status/hash alone does not establish a client decision.
    # Existing revision-aware decisions remain valid, including local channels
    # that did not provide a message id or an identity to their old writer.
    preference_hashes = set()
    intake_path = Path(run_dir) / "control" / "intake-session.json"
    if intake_path.exists():
        intake = _read(intake_path)
        row = (intake.get("answer_records") or {}).get("script") or {}
        candidates = [row.get("raw_answer"), (row.get("parsed") or {}).get("text")]
        for candidate in candidates:
            if events.is_preference_reply(candidate):
                preference_hashes.add(hashlib.sha256(str(candidate).strip().lower().encode("utf-8")).hexdigest())
    for kind, sha in hashes.items():
        art = (rec.get("artifacts") or {}).get(kind) or {}
        ev = events.active_approval(rec, kind, sha)
        origin = (rec.get("conversation") or {}).get("conversation_id")
        if (not ev or art.get("sha256") != sha or ev.get("revision") != art.get("revision") or
                ev.get("decision") != "approved" or not ev.get("decision_id") or
                not ev.get("event_id") or not ev.get("timestamp") or not ev.get("reply_text_sha") or
                (ev.get("run_id") and str(ev["run_id"]) != run_id) or
                (rec.get("maker") and ev.get("approved_by") and
                 str(rec["maker"]).strip().lower() == str(ev["approved_by"]).strip().lower()) or
                (origin and ev.get("conversation_id") != origin) or
                not any(kind in ask.get("kinds", []) and
                        (ask.get("revisions") or {}).get(kind) == art.get("revision")
                        for ask in rec.get("asks") or [])):
            return _result(False, "PRODUCTION_SCRIPT_APPROVAL_UNVERIFIED",
                           "The %s decision is not bound to this presented current artifact and run." % kind)
        if ev.get("reply_text_sha") in preference_hashes or events.is_preference_reply(ev.get("reply_text")):
            return _result(False, "ARTIFACT_REPLY_IS_PREFERENCE", "A saved intake option or viewing preference is not approval of this script and lyrics.")
        presented = next((a for a in rec.get("asks") or [] if
                          kind in a.get("kinds", []) and
                          (a.get("revisions") or {}).get(kind) == art.get("revision") and
                          a.get("ask_id") == ev.get("presentation_ask_id")), None)
        modern = False
        if (ev.get("source") == "client" and ev.get("source_ref") and presented and
                isinstance(ev.get("reply_text"), str) and ev["reply_text"].strip()):
            proof = approval.reply_provenance(run_dir, rec, {
                "source": ev["source"], "source_ref": ev["source_ref"],
                "presentation_ask_id": ev["presentation_ask_id"], "run_id": ev.get("run_id"),
                "reply_text_sha": ev.get("reply_text_sha")}, ev["reply_text"])
            modern = proof["ok"]
        legacy = (not ev.get("source") and not ev.get("source_ref") and bool(ev.get("approved_by")) and
                  ev.get("run_id") == run_id and bool(origin) and ev.get("conversation_id") == origin and
                  ev.get("requesting_conversation_id") == origin and rec.get("sent") is True and
                  any(a.get("message_id") and a["message_id"] == ev.get("reply_to_message_id") and
                      kind in a.get("kinds", []) and (a.get("revisions") or {}).get(kind) == art.get("revision")
                      for a in rec.get("asks") or []))
        if not modern and not legacy:
            return _result(False, "ARTIFACT_REPLY_PROVENANCE_UNVERIFIED",
                           "The current artifact decision has no verifiable new client reply and presented-revision binding; preserve it for source verification.")
    return _result(True, "PRODUCTION_SCRIPT_APPROVED", "The whole script and lyrics have current revision-bound decisions.",
                   approved_script=dict(script_sha256=hashes["script"], lyrics_sha256=hashes["lyrics"], path=str(Path(run_dir) / "creative" / "script.json"), required=True))


def _completed(stage, states, events):
    if states.get(stage) != "COMPLETE":
        return False
    changes = [row for row in events if row[0] == stage and row[1] in ("transition", "stale", "claim")]
    return bool(changes and changes[-1][1] == "transition" and "->COMPLETE" in changes[-1][2].split(" ", 1)[0])


def _legacy_authority(run_dir, run_id, states, events):
    """Keep the supported revision-event legacy path, never infer old raw facts.

    Legacy card rows without raw reply history are preserved. They can resume
    paid production only with independently recorded, current whole-package
    decisions and a completed governed script stage; no guessed migration or
    numeric remapping is performed here. Diagnostics/drafts remain available.
    """
    from choice_card.intake_card import intake_card as card
    from script_approval import card_answers
    saved = card_answers.load(str(run_dir))
    rows = saved.get("by_id") or {}
    expected = {q["id"] for q in card.QUESTIONS}
    if "episode_length" in rows:
        expected.discard("length")
        expected.add("episode_length")
    if saved.get("state") != card_answers.OK or not expected.issubset(rows):
        return _result(False, "PRODUCTION_INTAKE_AUTHORITY_MISSING",
                       "No authoritative intake history or verifiable legacy production handoff exists; a four-pick receipt is insufficient.")
    if not _completed("script-lyrics", states, events):
        return _result(False, "PRODUCTION_LEGACY_AUTHORITY_UNVERIFIED",
                       "Existing legacy answers are preserved, but no completed governed script stage proves their production handoff.")
    proof = _script_proof(run_dir, run_id)
    if not proof["ok"]:
        return _result(False, "PRODUCTION_LEGACY_AUTHORITY_UNVERIFIED", proof["detail"])
    return _result(True, "PRODUCTION_LEGACY_AUTHORITY_VERIFIED",
                   "Existing stable answer identities, governed stage history and current whole-package approval are verified; no old raw facts were reconstructed.",
                   authority="legacy-artifact-decisions", preferences=_preferences(rows))


def inspect_intake(run_dir, *, run_id=None):
    """Initial planning admission; never approves an unseen script/storyboard.

    Read-only, without paid calls, bootstrap, migration or preference writes.
    """
    context = {"run_dir": str(Path(run_dir).resolve()) if run_dir else None, "run_id": run_id}
    if not run_dir:
        return _result(False, "PRODUCTION_RUN_REQUIRED", "Name the existing governed run directory.", **context)
    try:
        root = Path(run_dir).resolve()
        held_id, states, events, live_model = _snapshot(root, run_id)
        context.update(run_id=held_id, video_model_lock=live_model)
        path = root / "control" / "intake-session.json"
        authority = (_session_authority(root, _read(path), held_id, live_model) if path.exists()
                     else _legacy_authority(root, held_id, states, events))
        return dict(authority, **context)
    except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError, sqlite3.Error) as exc:
        return _result(False, "PRODUCTION_STATE_UNVERIFIED", str(exc), **context)


def _ancestors(stage, registry):
    seen, visiting = set(), set()
    def visit(node):
        if node in visiting:
            raise ValueError("the stage dependency graph contains a cycle")
        visiting.add(node)
        for parent in registry[node]["prerequisites"]:
            if parent not in seen:
                visit(parent)
                seen.add(parent)
        visiting.remove(node)
    visit(stage)
    return seen


def needs_media_dependencies(stage):
    """The validated graph's initial planning prefix has no media generation.

    Unknown stages fail closed; this is not an authorization decision.
    """
    if stage is None:
        return False
    order, registry = _graph()
    if stage not in order:
        raise ValueError("unknown canonical production stage")
    return stage == "music" or "music" in _ancestors(stage, registry)


def _storyboard_proof(run_dir, *, required, events):
    from storyboard_director import approval_runner as runner
    from storyboard_director import approval_package as package
    from storyboard_director import storyboard_director as director
    state = _read(Path(run_dir) / "storyboard" / "approval.json")
    if not runner.gate_open(str(run_dir)) or not state.get("shots"):
        return _result(False, "PRODUCTION_STORYBOARD_APPROVAL_UNVERIFIED",
                       "The current storyboard has no artifact-bound whole-package approval.")
    if required and (state.get("choice") != "yes" or
            not any(stage == "video-generation" and kind == "transition" and
                    "->WAITING_APPROVAL" in str(detail).split(" ", 1)[0]
                    for stage, kind, detail, _ in events)):
        return _result(False, "PRODUCTION_STORYBOARD_APPROVAL_UNVERIFIED",
                       "The elected storyboard approval has no matching governed presentation/wait history.")
    shots, contracts, stills = runner._load(str(run_dir))
    if not shots or {s["shot_id"] for s in shots} != set(state["shots"]):
        return _result(False, "PRODUCTION_STORYBOARD_APPROVAL_UNVERIFIED", "The approved and current storyboard shot identities differ.")
    gate = _read(Path(run_dir) / "storyboard" / "gate.json")
    approved_shots = [dict(s, status="storyboard_approved") for s in shots]
    if gate.get("shots") != approved_shots:
        return _result(False, "PRODUCTION_STORYBOARD_SCOPE_MISMATCH",
                       "The video gate differs from the current approved shot plan.")
    review = director.adversarial_review(approved_shots, contracts)
    verdict = director.video_spend_allowed(approved_shots, review)
    if not verdict["allowed"] or not director.video_spend_allowed(approved_shots, gate.get("review"))["allowed"]:
        return _result(False, "PRODUCTION_STORYBOARD_REVIEW_UNVERIFIED",
                       "The current approved plan has not passed its existing adversarial review gate.")
    revisions = {s["shot_id"]: package.shot_revision(s, contracts.get(s["shot_id"]), stills.get(s["shot_id"]))
                 for s in shots}
    return _result(True, "PRODUCTION_STORYBOARD_APPROVED", "Existing storyboard approval matches the current shot contracts and still bytes.",
                   approved_storyboard={"shot_ids": list(revisions), "revisions": revisions,
                       "gate_path": str(Path(run_dir) / "storyboard" / "gate.json"),
                       "shot_list_path": str(Path(run_dir) / "storyboard" / "shot-list.json"),
                       "contracts_path": str(Path(run_dir) / "storyboard" / "contracts.json"),
                       "stills_path": str(Path(run_dir) / "storyboard" / "stills.json")})


def _offline_proof(value):
    if isinstance(value, dict):
        if value.get("execution_mode") == "offline" or value.get("production_admitted") is False:
            return True
        return any(_offline_proof(v) for v in value.values())
    if isinstance(value, list):
        return any(_offline_proof(v) for v in value)
    return False


def admit_production(run_dir, stage, *, run_id=None):
    """Admit exactly one current stage via the repository's validated graph.

    A successful receipt is a projection, not a reusable authorization token;
    dispatch must recheck at its boundary. Never accepts a supplied JSON auth,
    approval override, draft outcome or offline dispatch receipt as authority.
    """
    intake = inspect_intake(run_dir, run_id=run_id)
    context = dict(run_dir=intake.get("run_dir"), run_id=intake.get("run_id"), stage=stage,
                   current_state=None, authority=intake.get("authority"))
    if not intake["ok"]:
        return dict(intake, stage=stage, current_state=None)
    try:
        root = Path(run_dir).resolve()
        order, registry = _graph()
        if stage not in order:
            return _result(False, "PRODUCTION_STAGE_UNKNOWN", "Name a canonical production stage; a provider label is not stage authority.", **context)
        held_id, states, events, live_model = _snapshot(root, intake["run_id"])
        if live_model != intake["video_model_lock"]:
            return _result(False, "PRODUCTION_VIDEO_MODEL_LOCK_MISMATCH",
                           "The live video-model lock changed while production admission was being checked.", **context)
        context["current_state"] = states.get(stage)
        if any(s not in states for s in order):
            return _result(False, "PRODUCTION_STAGE_HANDOFF_MISSING", "Canonical stage rows are missing; dispatch cannot bootstrap them.", **context)
        if states.get(stage) not in ("NOT_STARTED", "READY", "RUNNING", "FAILED_RETRYABLE", "STALE"):
            return _result(False, "PRODUCTION_STAGE_NOT_RUNNABLE", "The requested stage is %s." % states.get(stage), **context)
        predecessors = _ancestors(stage, registry)
        for predecessor in order:
            if predecessor not in predecessors:
                continue
            if not _completed(predecessor, states, events):
                return _result(False, "PRODUCTION_PREDECESSOR_INCOMPLETE",
                               "Required predecessor %s lacks a completed governed transition." % predecessor,
                               predecessor=predecessor, **context)
            for rel in registry[predecessor].get("required_artifacts", []):
                path = (root / rel).resolve()
                if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size == 0:
                    return _result(False, "PRODUCTION_PREDECESSOR_EVIDENCE_MISSING",
                                   "Required predecessor %s has no current %s artifact." % (predecessor, rel),
                                   predecessor=predecessor, **context)
                if path.suffix == ".json" and _offline_proof(_read(path)):
                    return _result(False, "PRODUCTION_PREDECESSOR_OFFLINE_ONLY",
                                   "Required predecessor %s carries an explicitly offline/non-admitted receipt." % predecessor,
                                   predecessor=predecessor, **context)
        proofs = {}
        prefs = intake["preferences"]
        if stage == "music" or "music" in predecessors:
            proof = _script_proof(root, held_id, required=prefs["script"])
            if not proof["ok"]:
                return dict(proof, **context)
            proofs["approved_script"] = proof["approved_script"]
        if "music" in predecessors:
            from intake_preflight import factory
            from song_choices import song_choices as songs
            if prefs["song"]:
                state = songs._state(str(root))
                if not state or state.get("required") is not True:
                    return _result(False, "PRODUCTION_SONG_PREFERENCE_MISMATCH", "The client elected song choice, but its artifact gate is missing or disabled.", **context)
            # Reuse the decision-aware gate used by music completion and next.
            hold = factory._song_hold(str(root))
            if hold:
                return _result(False, hold["reason_code"], hold.get("detail") or hold.get("next_action") or "Song choice is still pending.", **context)
        if stage == "video-generation" or "video-generation" in predecessors:
            proof = _storyboard_proof(root, required=prefs["storyboard"], events=events)
            if not proof["ok"]:
                return dict(proof, **context)
            proofs["approved_storyboard"] = proof["approved_storyboard"]
        return _result(True, "PRODUCTION_STAGE_ADMITTED", "Confirmed intake, required predecessors and current artifact gates agree.",
                       **context, **proofs)
    except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError, sqlite3.Error) as exc:
        return _result(False, "PRODUCTION_PROCESS_UNVERIFIED", str(exc), **context)
