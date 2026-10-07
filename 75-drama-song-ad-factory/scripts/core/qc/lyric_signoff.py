#!/usr/bin/env python3
"""lyric_signoff.py: human lyric sign-off gate, Plan 9.3 (V2 addition). stdlib only.

Version 1's W4-07 generated a song with no recorded lyric approval at all.
From version 2 the song stage carries a sign-off record that a human made,
binds to the exact lyrics being sung, and predates song generation.

Rules (fail-closed):
- no record, or a record without the required fields -> never PASS
- approver must be a human with an identity (a model cannot approve
  lyrics it just wrote; 17.6 independence, 9.3 "human lyric sign-off")
- the record carries a digest of the approved lyric lines; a digest that
  does not match the lyrics now heading to Suno is stale -> FAIL (the
  approval never covered these words)
- status must be a recorded decision: "approved" or "declined". Plan 4.0
  makes the sign-off step optional for the client, so a recorded decline
  still unblocks generation; what W4-07 did -- recording nothing -- never
  does.
- when the caller knows when generation started, an approval stamped after
  it is rejected (sign-off is "before song generation")

ponytail: plan 4.0 (optional sign-off) vs plan 9.3 (recorded approval) are
reconciled as "a recorded human decision is mandatory, the outcome is the
client's". Tighten to approved-only the moment the owner says the client
must approve.
"""
from __future__ import annotations

import hashlib
import json

PASS = "PASS"
FAIL = "FAIL"
UNAVAILABLE = "UNAVAILABLE"

STATUSES = ("approved", "declined")


class SignoffError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def lyrics_digest(lines):
    """Stable digest of the approved lyric lines (order preserving)."""
    if not isinstance(lines, list):
        raise SignoffError("BAD_LYRICS", "lyric lines must be a list")
    canon = json.dumps(lines, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _fail(failures, code, detail):
    failures.append({"code": code, "detail": detail, "verdict": FAIL})


def check_signoff(signoff, expected_digest=None, song_started_at=None,
                  maker=None):
    """Validate the sign-off record. Returns verdict/code/failures."""
    failures = []
    if not isinstance(signoff, dict):
        _fail(failures, "LYRIC_SIGNOFF_MISSING",
              "no lyric sign-off recorded before song generation")
        return {"verdict": FAIL, "code": "LYRIC_SIGNOFF_MISSING",
                "failures": failures, "status": None}

    approver = signoff.get("approver")
    identity = approver.get("identity") if isinstance(approver, dict) else None
    if not isinstance(identity, str) or not identity.strip():
        _fail(failures, "LYRIC_SIGNOFF_SCHEMA",
              "approver.identity must record who signed off")
    kind = approver.get("kind") if isinstance(approver, dict) else None
    if kind != "human":
        _fail(failures, "LYRIC_SIGNOFF_NOT_HUMAN",
              "approver.kind must be 'human', got %r" % (kind,))

    approved_at = signoff.get("approved_at")
    if not isinstance(approved_at, str) or not approved_at.strip():
        _fail(failures, "LYRIC_SIGNOFF_SCHEMA",
              "approved_at must record when the human decided")

    status = signoff.get("status")
    if status not in STATUSES:
        _fail(failures, "LYRIC_SIGNOFF_STATUS",
              "status must be one of %s, got %r" % (list(STATUSES), status))

    digest = signoff.get("lyrics_digest")
    if not isinstance(digest, str) or not digest.strip():
        _fail(failures, "LYRIC_SIGNOFF_NO_DIGEST",
              "lyrics_digest must bind the approval to the approved words")
    elif expected_digest is not None and digest != expected_digest:
        _fail(failures, "LYRIC_SIGNOFF_STALE",
              "signed lyrics differ from the lyrics now queued for the song")

    if maker is not None and isinstance(identity, str) and identity == maker:
        _fail(failures, "LYRIC_SIGNOFF_NOT_INDEPENDENT",
              "sign-off by the maker of the lyrics is not review evidence")

    if song_started_at and isinstance(approved_at, str) and approved_at.strip():
        if approved_at > song_started_at:
            _fail(failures, "LYRIC_SIGNOFF_AFTER_SONG",
                  "sign-off %r is after song generation start %r"
                  % (approved_at, song_started_at))

    if not failures:
        return {"verdict": PASS, "code": None, "failures": [],
                "status": status}
    verdict = UNAVAILABLE if all(f["verdict"] == UNAVAILABLE
                                 for f in failures) else FAIL
    return {"verdict": verdict, "code": failures[0]["code"],
            "failures": failures, "status": status}


def song_generation_allowed(result):
    """True only for a PASS sign-off: generation stays blocked otherwise."""
    return isinstance(result, dict) and result.get("verdict") == PASS
