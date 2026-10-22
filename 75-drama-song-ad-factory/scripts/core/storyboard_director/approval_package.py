"""approval_package.py: the storyboard approval message shows BOTH the written
shot card and that shot's still image (Trevor, 2026-10-09). Stdlib only.

Order: storyboard cards -> one still per shot (cheap) -> THIS approval ->
only then video (the expensive part). ``build`` refuses a shot with no card
fact or no still file; ``approve`` is the only thing that stamps
``storyboard_approved`` (the 14.1 gate kie_dispatch already enforces);
``revise_shot`` redoes one shot's still and re-sends that shot only.

Every shot card carries the repair spec's per-shot facts (Skill 75 section
5.1 item 8): the relevant line, the action, the emotional purpose, the
timing and the character. Large plans are presented as NUMBERED contact
sheets and NUMBERED card pages (ordered part numbers) so a channel limit
never swallows a shot; a small plan is still one message plus one still per
shot in order.

Selective revision (5.1 item 8): ``shot_dependencies`` / ``descendants`` /
``affected_by_revision`` model which shots derive from which (contract
``change_from_prior`` and ``continuity_constraints`` references), so revising
a named shot invalidates only that shot and its descendants while every
unaffected shot keeps its approval. ``shot_revision`` binds an approval to
the contract + still bytes; ``artifact_records`` emits the SHARED artifact
schema (core/contracts/artifact-schema.json) records for the storyboard
artifacts. Named contract consumers of that shared schema: S75-W05
(story_coverage measurement records) and S75-W03 (channel_send / intake_card
typed envelope + delivery outbox) — this module adds no private schema.

Method runs (SPEC C4, METHOD-INTEGRATION F8) add three opt-in arguments, all
defaulting to today's behaviour:
    ``method=True``        the card also carries Story beat / Music / State,
                           and ``scene_match.check_cards`` requires them.
    ``lock_token`` + ``breakthrough_s``
                           the Transformation Lock: the package is refused
                           when a present-time shot after the breakthrough
                           still shows the before-state.
    ``platform_row``       paid/social runs: the card's safe_zone boxes are
                           checked against that platform row's margins.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import scene_match.scene_match as SM   # noqa: E402

STILL_MISSING = "STORYBOARD_STILL_MISSING"
CARD_INCOMPLETE = SM.CARD_INCOMPLETE
FOOTER = "Reply GO to approve, or 'shot 2: change ...' to fix one shot."
#: Numbered contact sheets / card pages kick in for large plans: more than
#: this many shots, or a message past PAGE_LIMIT characters (the channel cap
#: margin the sender also uses). A small plan stays one message, unchanged.
SHEET_MAX = 6
PAGE_MAX_CARDS = 6
PAGE_LIMIT = 4000
# Method card lines (SPEC C4): shown only when the contract carries them, so
# a package built from today's contracts renders byte for byte as before.
_CARD_LINES = (("story_beat", "Story beat"),
               ("music_cue", "Music"),
               ("state", "State"))


class ApprovalError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _clock(s):
    m, sec = divmod(int(round(s)), 60)
    return "%d:%02d" % (m, sec)


def _characters(shot, contract):
    """The character(s) this shot carries: 14.2 character_ids first, then a
    contract-level fallback. Empty string only when the plan never said."""
    ids = (shot or {}).get("character_ids")
    if isinstance(ids, (list, tuple)):
        ids = ", ".join(str(x) for x in ids if str(x).strip())
    ids = str(ids or "").strip()
    if ids:
        return ids
    c = contract if isinstance(contract, dict) else {}
    for key in ("character", "character_id", "characters"):
        v = c.get(key)
        if isinstance(v, (list, tuple)):
            v = ", ".join(str(x) for x in v if str(x).strip())
        v = str(v or "").strip()
        if v:
            return v
    return ""


def _entry(n, shot, contract, still):
    c = SM.shot_card(shot, contract)
    e = {"n": n, "shot_id": shot["shot_id"],
         "time": "%s-%s" % (_clock(shot["song_start"]), _clock(shot["song_end"])),
         "line": c["line"], "meaning": c["meaning"],
         "where_action": c["where_action"], "face_emotion": c["face_emotion"],
         "still": still}
    # 5.1 item 8 per-shot facts: line, action, emotional purpose, timing,
    # character. Old keys above stay exactly as they were (extend, never
    # remove); these are the presentation additions.
    contract = contract if isinstance(contract, dict) else {}
    e["timing"] = e["time"]
    e["action"] = str(contract.get("character_action") or "").strip()
    e["emotional_purpose"] = c["face_emotion"] \
        or str(contract.get("visible_emotion") or "").strip()
    e["character"] = _characters(shot, contract)
    for key, _ in _CARD_LINES:
        if c.get(key):
            e[key] = c[key]
    return e


def _text(e):
    head = "".join("\n%s: %s" % (label, e[key]) for key, label in _CARD_LINES if e.get(key))
    return ("Shot %d - Timing: %s%s\nLine: \"%s\"\nEmotional purpose: %s\n"
            "Action: %s\nCharacter: %s\n"
            "Viewer must understand: %s\n"
            "Place and action: %s\nFace: %s\nPicture: %s"
            % (e["n"], e["time"], head, e["line"], e["emotional_purpose"],
               e["action"], e["character"], e["meaning"], e["where_action"],
               e["face_emotion"], e["still"]))


def contact_sheets(items, per_sheet=SHEET_MAX):
    """Numbered contact sheets: stills grouped in shot order, each sheet
    numbered k/m with its shot range (5.3: numbered contact sheet for a large
    storyboard). A small plan is one sheet numbered 1/1."""
    groups = [items[i:i + per_sheet] for i in range(0, len(items), per_sheet)] \
        if items else [[]]
    sheets = []
    for k, g in enumerate(groups, 1):
        sheets.append({"n": k, "of": len(groups),
                       "shots": [e["shot_id"] for e in g],
                       "first": g[0]["n"] if g else 0,
                       "last": g[-1]["n"] if g else 0,
                       "caption": "Contact sheet %d/%d - shots %d-%d"
                                  % (k, len(groups),
                                     g[0]["n"] if g else 0, g[-1]["n"] if g else 0),
                       "images": [(e["n"], e["still"]) for e in g]})
    return sheets


def card_pages(items, footer=FOOTER, limit=PAGE_LIMIT, per_page=PAGE_MAX_CARDS):
    """Numbered card pages (ordered part numbers, 5.3): the shot cards split
    at card boundaries under ``limit`` characters and ``per_page`` cards. The
    last page carries the reply footer; earlier pages name the next part."""
    pages, cur = [], []

    def flush():
        if not cur:
            return
        pages.append({"shots": [e["shot_id"] for e in cur],
                      "first": cur[0]["n"], "last": cur[-1]["n"],
                      "text": "\n\n".join(_text(e) for e in cur)})
    for e in items:
        cand = cur + [e]
        body_len = sum(len(_text(x)) + 2 for x in cand)
        if cur and (len(cand) > per_page or body_len > limit - 200):
            flush()
            cur = []
        cur.append(e)
    flush()
    out = []
    for k, p in enumerate(pages, 1):
        head = "Storyboard cards %d/%d (shots %d-%d)" \
               % (k, len(pages), p["first"], p["last"])
        tail = footer if k == len(pages) else "(continued in part %d)" % (k + 1)
        out.append({"n": k, "of": len(pages), "shots": p["shots"],
                    "first": p["first"], "last": p["last"],
                    "text": "%s\n\n%s\n\n%s" % (head, p["text"], tail)})
    return out


def build(shots, contracts, stills, method=False, lock_token=None,
          breakthrough_s=None, platform_row=None):
    """Approval package, shots in song order: card + still for every shot.

    stills: {shot_id: image file path}. Raises ApprovalError when any card
    fact is missing or any still file does not exist (fail closed).
    ``method`` also requires the story beat / music cue / state card facts,
    ``lock_token`` runs the Transformation Lock, ``platform_row`` checks the
    safe zones; each is off unless the caller passes it.

    Returns items/images/message as always, plus ``sheets`` (numbered contact
    sheets), ``pages`` (numbered card pages) and ``large`` (True when the
    plan is presented as sheets + pages instead of one message).
    """
    ordered = sorted(shots or [], key=lambda s: (s["song_start"], s["song_end"]))
    if not ordered:
        raise ApprovalError("STORYBOARD_EMPTY", "no shots to approve")
    bad = SM.check_cards(ordered, contracts, method=method, platform_row=platform_row)
    if bad["findings"]:
        raise ApprovalError(bad["reason_code"], "; ".join(
            "%s: %s" % (f["shot_id"], f["detail"]) for f in bad["findings"]))
    if lock_token or breakthrough_s is not None:
        lock = SM.transformation_lock(ordered, contracts, lock_token, breakthrough_s)
        if lock["findings"]:
            raise ApprovalError(lock["reason_code"], "; ".join(
                "%s: %s" % (f["shot_id"], f["detail"]) for f in lock["findings"]))
    gone = [s["shot_id"] for s in ordered
            if not os.path.isfile((stills or {}).get(s["shot_id"]) or "")]
    if gone:
        raise ApprovalError(STILL_MISSING, "no still image for: " + ", ".join(gone))
    items = [_entry(i, s, contracts.get(s["shot_id"]), stills[s["shot_id"]])
             for i, s in enumerate(ordered, 1)]
    message = ("Storyboard: %d shots. Nothing is made into video until you say go.\n\n%s\n\n%s"
               % (len(items), "\n\n".join(_text(e) for e in items), FOOTER))
    sheets = contact_sheets(items)
    pages = card_pages(items)
    large = len(items) > PAGE_MAX_CARDS or len(message) > PAGE_LIMIT
    return {"items": items, "images": [e["still"] for e in items],
            "message": message, "sheets": sheets, "pages": pages,
            "large": large}


def shot_dependencies(shots, contracts):
    """Declared derivation edges: {shot_id: set(shot_ids it derives from)}.

    A shot derives from another when its 14.3 ``change_from_prior`` names that
    shot's id, its 14.2 ``continuity_constraints`` name that shot's id, or its
    ``change_from_prior`` is non-empty and the other shot is its immediate
    predecessor in song order (the statement is about that shot by
    definition). Nothing else couples two shots: an unrelated shot is never
    dragged into a revision.
    """
    ordered = sorted(shots or [], key=lambda s: (s["song_start"], s["song_end"]))
    ids = [s["shot_id"] for s in ordered]
    deps = {sid: set() for sid in ids}

    def _text_of(v):
        if isinstance(v, (list, tuple)):
            return " ".join(str(x) for x in v)
        return str(v or "")

    for i, s in enumerate(ordered):
        sid = s["shot_id"]
        contract = (contracts or {}).get(sid) or {}
        prior = ids[i - 1] if i else None
        change = _text_of(contract.get("change_from_prior")).strip()
        named = _text_of(contract.get("change_from_prior")) + " " \
            + _text_of(s.get("continuity_constraints"))
        for other in ids:
            if other != sid and other in named.split():
                deps[sid].add(other)
        if change and prior:
            deps[sid].add(prior)
    return deps


def descendants(shots, contracts, shot_ids):
    """Every transitive descendant of ``shot_ids`` (excludes the inputs):
    shots whose declared facts derive from a revised shot."""
    deps = shot_dependencies(shots, contracts)
    out, queue, seen = set(), list(shot_ids), set(shot_ids)
    while queue:
        cur = queue.pop()
        for sid, ds in deps.items():
            if cur in ds and sid not in seen:
                seen.add(sid)
                out.add(sid)
                queue.append(sid)
    return sorted(out)


def affected_by_revision(shots, contracts, revised_ids):
    """(affected, kept): selective invalidation. The revised shots plus every
    descendant are affected; every other shot keeps its standing (and its
    approval)."""
    revised = [s for s in (revised_ids or [])]
    desc = descendants(shots, contracts, revised)
    affected = sorted(set(revised) | set(desc))
    all_ids = [s["shot_id"] for s in sorted(
        shots or [], key=lambda s: (s["song_start"], s["song_end"]))]
    kept = [sid for sid in all_ids if sid not in affected]
    return affected, kept


def shot_revision(shot, contract, still_path):
    """Stable revision identity for one shot's approval binding: the contract
    and shot record bytes plus the still bytes (the spec's revision/hash
    binding — an approval survives only while this digest holds)."""
    h = hashlib.sha256()
    h.update(json.dumps({"shot": shot, "contract": contract},
                        sort_keys=True, ensure_ascii=True,
                        default=str).encode("utf-8"))
    try:
        with open(still_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except OSError:
        h.update(b"missing-still")
    return h.hexdigest()


def approval_entries(shots, contracts, stills, at=None):
    """Per-shot approval records: {shot_id: {status, revision, still_sha256}}.

    ``status`` is "pending" until the client approves; the runner flips it to
    "approved" and back to "invalidated" on a scoped revision."""
    out = {}
    for s in sorted(shots or [], key=lambda x: (x["song_start"], x["song_end"])):
        sid = s["shot_id"]
        still = (stills or {}).get(sid) or ""
        out[sid] = {"status": "pending",
                    "revision": shot_revision(s, (contracts or {}).get(sid), still),
                    "still_sha256": _file_sha(still)}
    return out


def _file_sha(path):
    try:
        with open(path, "rb") as f:
            h = hashlib.sha256()
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
            return h.hexdigest()
    except OSError:
        return ""


def artifact_records(run_id, shots, contracts, stills, stale=()):
    """Shared artifact-schema records (core/contracts/artifact-schema.json)
    for every storyboard artifact: one image record per still and one json
    record for the shot contracts. Selective revision flips ``stale`` on the
    affected records only (stale-flag invalidation, schema section 22).

    Named contract consumers of this shared schema: S75-W05 (story_coverage
    measurement records) and S75-W03 (channel_send/intake_card typed envelope
    and durable delivery outbox). Keep this shape additive-only so both
    consumers keep reading the same record.
    """
    stale = set(stale or ())
    recs = []
    for s in sorted(shots or [], key=lambda x: (x["song_start"], x["song_end"])):
        sid = s["shot_id"]
        still = (stills or {}).get(sid) or ""
        sha = _file_sha(still)
        if sha:
            recs.append({"schema_version": "1.0.0",
                         "artifact_id": "storyboard.still.%s" % sid,
                         "run_id": str(run_id),
                         "stage": "storyboard", "kind": "image",
                         "path": str(still), "sha256": sha,
                         "version": 1, "stale": sid in stale,
                         "supersedes": None})
    recs.append({"schema_version": "1.0.0",
                 "artifact_id": "storyboard.contracts",
                 "run_id": str(run_id),
                 "stage": "storyboard", "kind": "json",
                 "path": "storyboard/contracts.json",
                 "sha256": hashlib.sha256(json.dumps(
                     contracts or {}, sort_keys=True, ensure_ascii=True,
                     default=str).encode("utf-8")).hexdigest(),
                 "version": 1,
                 "stale": bool(stale), "supersedes": None})
    return recs


#: Public alias: the runner composes revision messages from the same card
#: text the package renders (one format, never two).
card_text = _text


def approve(shots, contracts, stills, method=False, lock_token=None,
            breakthrough_s=None, platform_row=None):
    """Stamp every shot storyboard_approved, only if the full package builds."""
    build(shots, contracts, stills, method=method, lock_token=lock_token,
          breakthrough_s=breakthrough_s, platform_row=platform_row)
    return [dict(s, status="storyboard_approved") for s in shots]


def revise_shot(shots, contracts, stills, shot_id, changes, make_still,
                method=False, lock_token=None, breakthrough_s=None, platform_row=None):
    """Client edit to one shot: apply ``changes`` to its contract, call
    ``make_still(shot_id, card)`` for THAT shot only, return
    (contracts, stills, message) where message re-sends only that shot.
    The client then approves again; only approve() stamps shots.
    """
    if shot_id not in {s["shot_id"] for s in shots}:
        raise ApprovalError("SHOT_UNKNOWN", shot_id)
    contracts = dict(contracts, **{shot_id: dict(contracts.get(shot_id) or {}, **changes)})
    shot = next(s for s in shots if s["shot_id"] == shot_id)
    stills = dict(stills, **{shot_id: make_still(shot_id, SM.shot_card(shot, contracts[shot_id]))})
    pkg = build(shots, contracts, stills, method=method, lock_token=lock_token,
                breakthrough_s=breakthrough_s, platform_row=platform_row)
    e = next(i for i in pkg["items"] if i["shot_id"] == shot_id)
    return contracts, stills, "Updated shot %d.\n\n%s\n\n%s" % (e["n"], _text(e), FOOTER)
