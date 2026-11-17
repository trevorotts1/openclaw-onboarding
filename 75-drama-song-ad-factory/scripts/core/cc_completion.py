"""cc_completion.py — the completion evidence a Skill 75 run owes the board (S75-033).

The Command Center's Skill 75 contract (read from its source, src/lib/validation.ts):

  * SKILL75_REQUIRED_APPROVAL_KINDS, lines 449-456:
    script, lyrics, character_bible, music, storyboard, final.
  * Skill75ApprovalEnvelopeSchema, lines 519-533:
    {contract: "skill75", version: 1, kind: "approval", artifact_kind,
     revision (int > 0), sha256? (64 hex), decision: approved|revised,
     approver (1-200), decided_at (1-64), thread_id? (<= 128)}.
  * Skill75ReviewEnvelopeSchema, lines 537-547:
    {contract: "skill75", version: 1, kind: "review", reviewer (1-200),
     actor (<= 200), verdict: pass|fail, scope? (<= 64), revision? (int > 0)}.
  * UpdateAdCampaignStageSchema, lines 666-692: PATCH /api/ad-campaigns/[id]
    accepts ONE `approval` and ONE `review` per move. The same envelopes may
    also be posted as task_activities metadata; the completion guard reads every
    envelope recorded against the campaign's cards (ad-campaigns.ts 269-288).

`build(run_dir)` reads the run's OWN records and returns::

    {"approvals": [six envelopes, in the required-kind order],
     "approval":  <the 'final' envelope, for the epic's move to done>,
     "review":    <the independent review envelope>}

Each approval traces to a record the run writes (paths under the run dir):

    script, lyrics   creative/script-approval.json — the ACTIVE decision events
                     (approval_events.py: record path line 45, event fields
                     lines 582-595)
    character_bible  character/approval.json — the versioned approval event
                     (character_approval.py: APPROVAL_NAME line 86, event lines
                     692-707)
    music            song-choices/pick.json (the pick: pick/label/sha256, written
                     by song_choices.record_pick lines 1605-1606) plus the song
                     approval provenance recorded in song-choices/state.json
    storyboard       storyboard/approval.json — state 'approved', per-shot
                     revisions, invalidation history (approval_runner.py 341-346,
                     357-389)
    final            delivery/delivery-receipt.json — the delivered manifest rows
                     (song_files / video_delivery / audio_versions / cover_image /
                     delivery_clips), each carrying its sha256
    review           qc/records.json — a PASS record for final-qc or delivery,
                     whose reviewer differs from the recorded maker
                     (qc/makers.json), plus the qc-schema record fields
                     (qc_gate.validate_record lines 282-325)

A source record that is missing, or that carries no approved decision, raises
CompletionEvidenceMissing(<which>) naming it: this module never emits a blank
or placeholder record.

Stdlib only. No network, no spend.
"""
from __future__ import annotations

import hashlib
import json
import os
import time

#: The required approval kinds, in the board's own order (validation.ts 449-456).
APPROVAL_KINDS = ("script", "lyrics", "character_bible", "music", "storyboard", "final")

#: Every envelope carries the typed contract marker (validation.ts 513-516).
CONTRACT = {"contract": "skill75", "version": 1}


class CompletionEvidenceMissing(Exception):
    """A completion-evidence source record is missing or not an approval.
    `which` names the record, so a refusal says exactly what to fix."""

    def __init__(self, which):
        super().__init__("completion evidence missing: %s" % (which,))
        self.which = which


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return None


def _need(record, which):
    if record is None:
        raise CompletionEvidenceMissing(which)
    return record


def _iso(at):
    """ISO-8601 UTC for an epoch-seconds value, or None when it is not one."""
    if isinstance(at, bool):
        return None
    try:
        seconds = float(at)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


def _time_text(value, which):
    """A recorded time as text: an epoch value is converted, an ISO string is
    kept. Anything else is a refusal, never a made-up timestamp."""
    iso = _iso(value)
    if iso:
        return iso
    text = str(value or "").strip()
    if 1 <= len(text) <= 64:
        return text
    raise CompletionEvidenceMissing(which)


def _text(value, which, limit):
    text = str(value or "").strip()
    if not text or len(text) > limit:
        raise CompletionEvidenceMissing(which)
    return text


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     default=str).encode("utf-8")).hexdigest()


def _sha_or_none(value):
    if isinstance(value, str) and len(value) == 64 and \
            all(c in "0123456789abcdefABCDEF" for c in value):
        return value
    return None


def _envelope(kind, revision, sha256, approver, decided_at, thread_id=None):
    if isinstance(revision, bool) or not isinstance(revision, int) or revision <= 0:
        raise CompletionEvidenceMissing("%s revision (a positive integer)" % kind)
    envelope = dict(CONTRACT, kind="approval", artifact_kind=kind, revision=revision,
                    decision="approved", approver=approver, decided_at=decided_at)
    if sha256:
        envelope["sha256"] = sha256
    if thread_id:
        envelope["thread_id"] = str(thread_id)[:128]
    return envelope


def _requester(run_dir):
    """The run's recorded requester identity: the conversation the work was
    presented to and answered from (the canonical origin record, else the card
    receipt's send target). Never a guessed name."""
    origin = _read_json(os.path.join(run_dir, "control", "origin.json"))
    if isinstance(origin, dict):
        channel = str(origin.get("channel") or "").strip()
        conversation = str(origin.get("conversation_id")
                           or origin.get("chat_id") or "").strip()
        if channel and conversation:
            return "%s:%s" % (channel, conversation)
        if conversation:
            return conversation
    receipt = _read_json(os.path.join(run_dir, "control", "card-receipt.json"))
    if isinstance(receipt, dict) and str(receipt.get("target") or "").strip():
        return str(receipt["target"]).strip()
    raise CompletionEvidenceMissing(
        "requester identity (control/origin.json or control/card-receipt.json)")


def _script_approval(run_dir, kind):
    """Script and lyrics: the ACTIVE approved decision event for the artifact."""
    record = _need(_read_json(os.path.join(run_dir, "creative", "script-approval.json")),
                   "%s approval record (creative/script-approval.json)" % kind)
    events = [event for event in (record.get("approvals") or [])
              if isinstance(event, dict) and event.get("kind") == kind
              and event.get("state") == "active"
              and str(event.get("decision") or "").lower() == "approved"]
    if not events:
        raise CompletionEvidenceMissing(
            "%s approval (no active approved decision in creative/script-approval.json)"
            % kind)
    event = events[-1]
    return _envelope(kind, event.get("revision"), _sha_or_none(event.get("sha256")),
                     _text(event.get("approved_by"), "%s approver" % kind, 200),
                     _time_text(event.get("timestamp"), "%s decided_at" % kind),
                     event.get("thread_id"))


def _character_approval(run_dir):
    """The character bible: its versioned approval event. The sha256 is the hash
    of the approved asset manifest the event binds (image and class hashes)."""
    record = _need(_read_json(os.path.join(run_dir, "character", "approval.json")),
                   "character bible approval record (character/approval.json)")
    if str(record.get("status") or "").lower() != "approved":
        raise CompletionEvidenceMissing(
            "character_bible approval (record status %r)" % (record.get("status"),))
    manifest = {"image_hashes": record.get("image_hashes") or {},
                "class_hashes": record.get("class_hashes") or {}}
    origin = record.get("origin") if isinstance(record.get("origin"), dict) else {}
    return _envelope("character_bible", record.get("bible_revision"), _digest(manifest),
                     _text(record.get("approved_by"), "character_bible approver", 200),
                     _time_text(record.get("at"), "character_bible decided_at"),
                     origin.get("thread_id"))


def _music_approval(run_dir):
    """The music: the recorded pick, bound to the picked file's own sha256, with
    the identity and time the run recorded for the song approval."""
    pick = _need(_read_json(os.path.join(run_dir, "song-choices", "pick.json")),
                 "music pick record (song-choices/pick.json)")
    if not isinstance(pick, dict):
        raise CompletionEvidenceMissing("music pick record (song-choices/pick.json)")
    state = _need(_read_json(os.path.join(run_dir, "song-choices", "state.json")),
                  "song approval record (song-choices/state.json)")
    state = state if isinstance(state, dict) else {}
    provenance = state.get("provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    approver = _text(provenance.get("who") or state.get("target"),
                     "music approver (song-choices/state.json provenance)", 200)
    # ponytail: the run records the pick file and its hash, but no pick time of
    # its own; the song-approval provenance time is the recorded client decision
    # time. Add `at` to record_pick's pick.json when that writer is next owned.
    decided_at = _time_text(provenance.get("at"), "music decided_at")
    return _envelope("music", 1, _sha_or_none(pick.get("sha256")), approver, decided_at)


def _storyboard_approval(run_dir):
    """The storyboard: its approved state, bound to the per-shot revisions the
    client saw. The run keeps no integer revision counter for the package, so
    the approval round is one plus the recorded invalidation rounds."""
    record = _need(_read_json(os.path.join(run_dir, "storyboard", "approval.json")),
                   "storyboard approval record (storyboard/approval.json)")
    if str(record.get("state") or "").lower() != "approved":
        raise CompletionEvidenceMissing(
            "storyboard approval (record state %r)" % (record.get("state"),))
    shots = record.get("shots") if isinstance(record.get("shots"), dict) else {}
    manifest = {shot: (row or {}).get("revision") for shot, row in shots.items()
                if isinstance(row, dict) and row.get("revision")}
    if not manifest:
        raise CompletionEvidenceMissing("storyboard approved shots (storyboard/approval.json)")
    invalidations = record.get("invalidations")
    revision = 1 + (len(invalidations) if isinstance(invalidations, list) else 0)
    # The record keeps the client's reply and the time, not an approver name: the
    # client is the run's recorded requester, on the conversation it was sent to.
    return _envelope("storyboard", revision, _digest(manifest), _requester(run_dir),
                     _time_text(record.get("at"), "storyboard decided_at"))


def _review(run_dir):
    """The independent review: a PASS final-qc (or delivery) record whose
    reviewer identity differs from the recorded maker of that check."""
    records = _need(_read_json(os.path.join(run_dir, "qc", "records.json")),
                    "final quality-control records (qc/records.json)")
    if not isinstance(records, list):
        raise CompletionEvidenceMissing("final quality-control records (qc/records.json)")
    makers = _read_json(os.path.join(run_dir, "qc", "makers.json"))
    makers = makers if isinstance(makers, dict) else {}
    passed = [row for row in records
              if isinstance(row, dict)
              and str(row.get("verdict") or "").upper() == "PASS"
              and str(row.get("stage") or "") in ("final-qc", "delivery")]
    if not passed:
        raise CompletionEvidenceMissing(
            "independent final quality-control PASS record (qc/records.json)")
    record = passed[-1]
    reviewer = record.get("reviewer") if isinstance(record.get("reviewer"), dict) else {}
    check_id = str(record.get("check_id") or "").strip()
    actor = _text(makers.get(check_id), "final quality-control maker (qc/makers.json)", 200)
    identity = _text(reviewer.get("identity"), "final quality-control reviewer", 200)
    if identity.strip().lower() == actor.strip().lower():
        raise CompletionEvidenceMissing(
            "independent final quality-control reviewer (reviewer equals the maker)")
    envelope = dict(CONTRACT, kind="review", reviewer=identity, actor=actor,
                    verdict="pass")
    if check_id:
        envelope["scope"] = check_id[:64]
    return envelope


def _final_approval(run_dir, reviewer):
    """The final production: the delivered package, bound to the digest of the
    manifest rows the delivery receipt lists, approved by the independent
    reviewer who passed the final gate."""
    path = os.path.join(run_dir, "delivery", "delivery-receipt.json")
    receipt = _need(_read_json(path), "delivery receipt (delivery/delivery-receipt.json)")
    if not isinstance(receipt, dict):
        raise CompletionEvidenceMissing("delivery receipt (delivery/delivery-receipt.json)")
    rows = {key: receipt[key] for key in ("song_files", "video_delivery",
                                          "audio_versions", "cover_image",
                                          "delivery_clips")
            if receipt.get(key)}
    if not rows:
        raise CompletionEvidenceMissing("delivery receipt rows (delivery/delivery-receipt.json)")
    try:
        written = os.path.getmtime(path)
    except OSError:
        raise CompletionEvidenceMissing("delivery receipt time (delivery/delivery-receipt.json)")
    # ponytail: the receipt records no revision counter and no delivery time of
    # its own; revision 1 is the delivered state (its identity rides the digest
    # of the listed rows) and the file's write time is the delivery time. Stamp
    # `delivered_at`/`revision` in the delivery writer when it is next owned.
    return _envelope("final", 1, _digest(rows), reviewer, _time_text(written, "final decided_at"))


def build(run_dir):
    """The run's completion evidence, or CompletionEvidenceMissing(<which>)."""
    run_dir = os.path.abspath(run_dir)
    review = _review(run_dir)
    approvals = {
        "script": _script_approval(run_dir, "script"),
        "lyrics": _script_approval(run_dir, "lyrics"),
        "character_bible": _character_approval(run_dir),
        "music": _music_approval(run_dir),
        "storyboard": _storyboard_approval(run_dir),
        "final": _final_approval(run_dir, review["reviewer"]),
    }
    return {"approvals": [approvals[kind] for kind in APPROVAL_KINDS],
            "approval": approvals["final"],
            "review": review}
