#!/usr/bin/env python3
"""candidate_matrix: the 3x3 soundtrack matrix core (Skill 75 v3.0, C1/C3/C4).

Three materially different LYRIC CONCEPTS (rows 1..3) x three TREATMENTS each
(columns A..C), stable ids ``1A``..``3C``. This module owns the CONTRACT only:
build, validate, cost plan, selection, recovery. It never generates audio, never
prices a budget and never renders a UI.

Lineage rule: one concept -> three treatment cells share the SAME lyric hash;
the three treatment hashes differ. Completeness is SET EQUALITY with all nine
ids, never ``count == 9``.

The legacy one-concept/three-variant path in ``song_choices`` is untouched; a
three-option run is not relabelled as nine here.

Stdlib only. Treatment briefs are reused from ``variants.json`` through
``song_choices.variants_for`` so the existing complete-brief guards apply, and
every cell's provider style is composed by the SAME
``suno_recipe.brief_style_text`` the legacy three-variant path uses. A variant
marked ``revoices_lead`` (C2) therefore keeps the style's own dry/upfront lead
presence direction in the matrix cells too.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time

MATRIX_SCHEMA = "song_candidate_matrix/2"
SELECTION_SCHEMA = "song_candidate_selection/2"
CANDIDATE_MATRIX_VERSION = 2

CONCEPT_IDS = (1, 2, 3)
TREATMENT_CODES = ("A", "B", "C")
CANDIDATE_IDS = tuple("%d%s" % (n, t) for n in CONCEPT_IDS for t in TREATMENT_CODES)
CANDIDATE_ID_RE = re.compile(r"^[1-3][A-C]$")

CELL_STATES = ("pending", "submitted", "produced", "offerable", "failed")
#: Forward-only. A produced/offerable cell is never regenerated because another
#: cell failed; only an explicit authorized retake moves a failed cell back.
_ALLOWED_NEXT = {
    "pending": ("submitted", "failed"),
    "submitted": ("produced", "failed"),
    "produced": ("offerable", "failed"),
    "offerable": (),
    "failed": ("submitted",),
}

#: Typed refusal codes. Callers branch on the code, never on message text.
MATRIX_CONCEPTS_NOT_THREE = "MATRIX_CONCEPTS_NOT_THREE"
MATRIX_CONCEPT_ID_INVALID = "MATRIX_CONCEPT_ID_INVALID"
MATRIX_CONCEPT_LYRIC_MISSING = "MATRIX_CONCEPT_LYRIC_MISSING"
MATRIX_CONCEPT_LYRIC_DUPLICATE = "MATRIX_CONCEPT_LYRIC_DUPLICATE"
MATRIX_CONCEPT_NOT_DISTINCT = "MATRIX_CONCEPT_NOT_DISTINCT"
MATRIX_TREATMENTS_NOT_THREE = "MATRIX_TREATMENTS_NOT_THREE"
MATRIX_TREATMENT_NOT_DISTINCT = "MATRIX_TREATMENT_NOT_DISTINCT"
MATRIX_SCHEMA_UNSUPPORTED = "MATRIX_SCHEMA_UNSUPPORTED"
MATRIX_DIGEST_MISMATCH = "MATRIX_DIGEST_MISMATCH"
MATRIX_INCOMPLETE = "MATRIX_INCOMPLETE"
CANDIDATE_ID_UNKNOWN = "CANDIDATE_ID_UNKNOWN"
CANDIDATE_NOT_OFFERABLE = "CANDIDATE_NOT_OFFERABLE"
CELL_STATE_INVALID = "CELL_STATE_INVALID"

DIRNAME = "song-choices"
MATRIX_FILE = "candidate-matrix.json"
SELECTION_FILE = "candidate-selection.json"

#: Content-word overlap above this is a REWORD, not a new concept. Lexical only:
#: ponytail: it is a signal, never proof -- semantic editorial review is still
#: required before spend. Raise/lower only against real false positives.
NEAR_DUPLICATE_JACCARD = 0.80
_STOPWORDS = frozenset((
    "that", "this", "with", "from", "they", "them", "their", "what", "when",
    "have", "been", "will", "your", "just", "like", "into", "over", "then",
    "than", "only", "also", "were", "where", "there", "here", "because",
))


class MatrixError(ValueError):
    """A typed refusal. ``code`` is one of the module constants above."""

    def __init__(self, code, detail=""):
        self.code = code
        self.detail = detail
        super().__init__("%s: %s" % (code, detail) if detail else code)


# ---- small helpers ------------------------------------------------------

def _norm(text):
    return re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower()).split()


def _tokens(text):
    return {w for w in _norm(text) if len(w) >= 4 and w not in _STOPWORDS}


def _sha256_text(text):
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _digest(obj):
    return hashlib.sha256(_canonical(obj).encode("utf-8")).hexdigest()


def _jaccard(a, b):
    if not a and not b:
        return 1.0
    return len(a & b) / float(len(a | b))


def _gen_cost_cents():
    """Per-generation provider cost, reused from song_dispatch. No budget logic."""
    from song_dispatch import song_dispatch as _SD
    return int(_SD.GEN_COST_CENTS)


# ---- treatments (columns A..C) -----------------------------------------

def treatments_for(style_id):
    """The style's three authored treatment briefs, mapped to A/B/C.

    ``variants_for`` already refuses a missing/partial/duplicate set, an
    incomplete brief, a banned word and a genre substitution. This adds the
    column rule: each treatment must differ from every other in at least two of
    arrangement/vocals/palette, so a relabelled copy cannot pass as A/B/C.
    """
    from song_choices.song_choices import variants_for
    try:
        rows = variants_for(style_id)
    except Exception as exc:                      # noqa: BLE001
        raise MatrixError(MATRIX_TREATMENTS_NOT_THREE, str(exc))
    if len(rows) != 3:
        raise MatrixError(MATRIX_TREATMENTS_NOT_THREE, "got %d" % len(rows))
    out = []
    for code, row in zip(TREATMENT_CODES, rows):
        brief = row.get("brief") or {}
        rec = {
            "treatment": code,
            "variant_id": row.get("id"),
            "upbeat": bool(row.get("upbeat")),
            "revoices_lead": bool(row.get("revoices_lead")),
            "arrangement": brief.get("arrangement", ""),
            "vocals": brief.get("vocals", ""),
            "palette": brief.get("palette", ""),
        }
        # C2: the re-voicing flag is part of the treatment identity, so a matrix
        # built before and after the flag differ in digest.
        rec["treatment_hash"] = _digest({k: rec[k] for k in
                                         ("variant_id", "arrangement", "vocals",
                                          "palette", "revoices_lead")})
        out.append(rec)
    validate_treatments(out)
    return out


def validate_treatments(treatments):
    """Three treatments, unique signatures, and pairwise materially different."""
    if not isinstance(treatments, list) or len(treatments) != 3:
        raise MatrixError(MATRIX_TREATMENTS_NOT_THREE,
                          "three treatments are required")
    sigs = [(t.get("arrangement"), t.get("vocals"), t.get("palette"))
            for t in treatments]
    if len(set(sigs)) != 3:
        raise MatrixError(MATRIX_TREATMENT_NOT_DISTINCT,
                          "two treatments share arrangement/vocals/palette")
    for i in range(3):
        for j in range(i + 1, 3):
            same = sum(1 for a, b in zip(sigs[i], sigs[j]) if str(a) == str(b))
            if same >= 2:
                raise MatrixError(
                    MATRIX_TREATMENT_NOT_DISTINCT,
                    "treatments %s and %s differ in only %d of 3 facets"
                    % (TREATMENT_CODES[i], TREATMENT_CODES[j], 3 - same))
    return treatments


# ---- concepts (rows 1..3) ----------------------------------------------

def validate_concepts(concepts):
    """Three materially different lyric concepts. Refuses, never deduplicates."""
    if not isinstance(concepts, list) or len(concepts) != 3:
        raise MatrixError(MATRIX_CONCEPTS_NOT_THREE,
                          "exactly three lyric concepts are required")
    ids = [c.get("concept_id") if isinstance(c, dict) else None for c in concepts]
    if sorted(x for x in ids if isinstance(x, int)) != list(CONCEPT_IDS) \
            or len(set(ids)) != 3:
        raise MatrixError(MATRIX_CONCEPT_ID_INVALID, "concept ids are %r" % (ids,))
    seen_text, seen_title, seen_persp = {}, {}, {}
    for c in concepts:
        cid = c["concept_id"]
        lyrics = c.get("lyrics")
        if not isinstance(lyrics, str) or len(lyrics.strip()) < 20:
            raise MatrixError(MATRIX_CONCEPT_LYRIC_MISSING,
                              "concept %d carries no lyric text" % cid)
        title = (c.get("title") or "").strip()
        perspective = (c.get("perspective") or "").strip()
        if not title or not perspective:
            raise MatrixError(MATRIX_CONCEPT_NOT_DISTINCT,
                              "concept %d needs a title and a perspective" % cid)
        h = _sha256_text(lyrics.strip())
        if h in seen_text:
            raise MatrixError(MATRIX_CONCEPT_LYRIC_DUPLICATE,
                              "concepts %d and %d share identical lyrics"
                              % (seen_text[h], cid))
        seen_text[h] = cid
        for label, value, seen in (("title", tuple(_norm(title)), seen_title),
                                   ("perspective", tuple(_norm(perspective)),
                                    seen_persp)):
            if value in seen:
                raise MatrixError(MATRIX_CONCEPT_NOT_DISTINCT,
                                  "concepts %d and %d share the same %s"
                                  % (seen[value], cid, label))
            seen[value] = cid
    for i in range(3):
        for j in range(i + 1, 3):
            a, b = _tokens(concepts[i]["lyrics"]), _tokens(concepts[j]["lyrics"])
            score = _jaccard(a, b)
            if score >= NEAR_DUPLICATE_JACCARD:
                raise MatrixError(
                    MATRIX_CONCEPT_NOT_DISTINCT,
                    "concepts %d and %d overlap %.2f: a reword, not a new concept"
                    % (concepts[i]["concept_id"], concepts[j]["concept_id"], score))
    return concepts


# ---- matrix build -------------------------------------------------------

def cell_style(matrix, candidate_id, sheet=None, vocal_gender="f", pace_plan=None):
    """Compose ONE cell's provider style through the SAME composer the legacy
    three-variant path uses (``song_choices.build_requests`` ->
    ``suno_recipe.brief_style_text``), including the variant's C2
    ``revoices_lead`` flag. A harmonised/stacked lead therefore keeps the
    style's own dry/upfront presence direction in the matrix too.

    Read-only: builds text, sends nothing. ``sheet`` is forwarded unchanged.
    """
    if not isinstance(matrix, dict) or matrix.get("schema") != MATRIX_SCHEMA:
        raise MatrixError(MATRIX_SCHEMA_UNSUPPORTED, "not a v2 candidate matrix")
    cell = next((c for c in matrix.get("cells") or []
                 if c.get("candidate_id") == candidate_id), None)
    if cell is None:
        raise MatrixError(CANDIDATE_ID_UNKNOWN, repr(candidate_id))
    treatment = next((t for t in matrix.get("treatments") or []
                      if t.get("treatment") == cell.get("treatment")), None)
    if treatment is None:
        raise MatrixError(MATRIX_TREATMENTS_NOT_THREE,
                          "cell %s names no treatment column" % candidate_id)
    from song_choices.song_choices import variants_for, _brief_text
    row = next((r for r in variants_for(matrix["style_id"])
                if r.get("id") == treatment.get("variant_id")), None)
    if row is None:
        raise MatrixError(MATRIX_TREATMENTS_NOT_THREE,
                          "treatment %r no longer resolves in %r"
                          % (treatment.get("variant_id"), matrix.get("style_id")))
    import suno_recipe as _R
    sr = getattr(_R, "suno_recipe", _R)
    return sr.brief_style_text(
        matrix["style_id"], _brief_text(row, vocal_gender), sheet, vocal_gender,
        pace_plan, tail_clause=row["brief"]["arrangement"],
        revoices_lead=bool(row.get("revoices_lead")))


def _cell_digest(concept_id, treatment, lyric_hash, treatment_hash):
    return _digest({"concept_id": concept_id, "treatment": treatment,
                    "lyric_hash": lyric_hash, "treatment_hash": treatment_hash})


def _matrix_digest(matrix):
    """Content identity of the OFFERED matrix: concepts, treatments, nine cells.

    Recovery-only fields (state, counts, failures, missing, timestamps, run id)
    are excluded, so resuming a partially generated matrix does not move its
    digest; a different matrix does.
    """
    identity = {
        "schema": matrix.get("schema"),
        "candidate_matrix_version": matrix.get("candidate_matrix_version"),
        "style_id": matrix.get("style_id"),
        "concepts": [{"concept_id": c["concept_id"], "title": c["title"],
                      "perspective": c["perspective"],
                      "lyric_hash": c["lyric_hash"]} for c in matrix["concepts"]],
        "treatments": [{"treatment": t["treatment"],
                        "variant_id": t["variant_id"],
                        "treatment_hash": t["treatment_hash"]}
                       for t in matrix["treatments"]],
        "cells": [{"candidate_id": c["candidate_id"],
                   "lyric_hash": c["lyric_hash"],
                   "treatment_hash": c["treatment_hash"],
                   "cell_digest": c["cell_digest"]} for c in matrix["cells"]],
    }
    return _digest(identity)


def build_matrix(style_id, concepts, run_id=None, created_at=None):
    """Validate and return the nine-cell matrix. Raises before any spend."""
    validate_concepts(concepts)
    treatments = treatments_for(style_id)
    cost = _gen_cost_cents()

    rows = []
    for c in concepts:
        lyric_hash = _sha256_text(c["lyrics"].strip())
        thesis = (c.get("thesis") or "").strip()
        row = {
            "concept_id": c["concept_id"],
            "title": (c.get("title") or "").strip(),
            "perspective": (c.get("perspective") or "").strip(),
            "lyric_hash": lyric_hash,
            "lyrics": c["lyrics"].strip(),
        }
        if thesis:
            row["thesis"] = thesis
        if c.get("source_facts"):
            row["source_facts"] = c["source_facts"]
        rows.append(row)
    rows.sort(key=lambda r: r["concept_id"])

    cells = []
    for concept in rows:
        for treatment in treatments:
            cid = "%d%s" % (concept["concept_id"], treatment["treatment"])
            cells.append({
                "candidate_id": cid,
                "concept_id": concept["concept_id"],
                "treatment": treatment["treatment"],
                "lyric_hash": concept["lyric_hash"],
                "treatment_hash": treatment["treatment_hash"],
                "cell_digest": _cell_digest(concept["concept_id"],
                                            treatment["treatment"],
                                            concept["lyric_hash"],
                                            treatment["treatment_hash"]),
                "state": "pending",
                "audio": None,
                "duration_s": None,
                "provider": None,
                "cost": {"generations": 1, "gen_cost_cents": cost},
            })

    matrix = {
        "schema": MATRIX_SCHEMA,
        "candidate_matrix_version": CANDIDATE_MATRIX_VERSION,
        "run_id": run_id,
        "style_id": str(style_id),
        "created_at": created_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "concepts": rows,
        "treatments": treatments,
        "cells": cells,
        "cost_plan": {
            "cells": len(cells),
            "per_cell": {"generations": 1, "gen_cost_cents": cost},
            "total_generations": len(cells),
            "estimated_cents": len(cells) * cost,
        },
    }
    _finalize(matrix)
    return matrix


def _finalize(matrix):
    """Recompute counts/status/missing from the cells, then the digest.

    Status is derived, never trusted: a partial matrix cannot claim complete.
    """
    cells = matrix.get("cells") or []
    states = [c.get("state") for c in cells]
    ids = [c.get("candidate_id") for c in cells]
    offerable = {c.get("candidate_id") for c in cells
                 if c.get("state") == "offerable"}
    matrix["counts"] = {
        "requested": len(cells),
        "submitted": sum(1 for s in states if s in ("submitted", "produced", "offerable")),
        "produced": sum(1 for s in states if s in ("produced", "offerable")),
        "offerable": len(offerable),
        "failed": sum(1 for s in states if s == "failed"),
        "delivered": sum(1 for c in cells if c.get("delivered_at")),
    }
    matrix["missing"] = [i for i in CANDIDATE_IDS if i not in offerable]
    matrix["status"] = ("complete" if set(ids) == set(CANDIDATE_IDS)
                        and offerable == set(CANDIDATE_IDS) else
                        ("planned" if all(s == "pending" for s in states)
                         else "partial"))
    matrix["matrix_digest"] = _matrix_digest(matrix)
    return matrix


def require_complete(matrix):
    """Raise MATRIX_INCOMPLETE unless all nine ids are offerable in this digest."""
    if not isinstance(matrix, dict) or matrix.get("schema") != MATRIX_SCHEMA:
        raise MatrixError(MATRIX_SCHEMA_UNSUPPORTED, "not a v2 candidate matrix")
    if matrix.get("status") != "complete":
        raise MatrixError(MATRIX_INCOMPLETE,
                          "%d of 9 cells offerable; missing %r"
                          % (matrix.get("counts", {}).get("offerable", 0),
                             matrix.get("missing")))
    ids = {c.get("candidate_id") for c in matrix.get("cells") or []
           if c.get("state") == "offerable"}
    if ids != set(CANDIDATE_IDS):
        raise MatrixError(MATRIX_INCOMPLETE,
                          "completeness is set equality, got %r" % (sorted(ids),))
    if matrix.get("matrix_digest") != _matrix_digest(matrix):
        raise MatrixError(MATRIX_DIGEST_MISMATCH, "matrix content changed")
    return matrix


def pending_ids(matrix):
    """Resume plan: only the cells still owing work, in id order."""
    return [c["candidate_id"] for c in matrix.get("cells") or []
            if c.get("state") in ("pending", "failed")]


def record_cell(matrix, candidate_id, state, audio=None, duration_s=None,
                provider=None, delivered=False):
    """Record one cell's lifecycle. Refuses unknown ids and illegal regressions."""
    if not isinstance(candidate_id, str) or not CANDIDATE_ID_RE.match(candidate_id):
        raise MatrixError(CANDIDATE_ID_UNKNOWN, repr(candidate_id))
    cell = next((c for c in matrix.get("cells") or []
                 if c.get("candidate_id") == candidate_id), None)
    if cell is None:
        raise MatrixError(CANDIDATE_ID_UNKNOWN, candidate_id)
    if state not in CELL_STATES:
        raise MatrixError(CELL_STATE_INVALID, state)
    if state != cell.get("state") and state not in _ALLOWED_NEXT.get(
            cell.get("state"), ()):
        raise MatrixError(CELL_STATE_INVALID,
                          "%s: %s -> %s" % (candidate_id, cell.get("state"), state))
    if state == "offerable":
        if not audio or not str(audio).strip():
            raise MatrixError(CELL_STATE_INVALID,
                              "%s: an unmeasured output is not offerable" % candidate_id)
        if not isinstance(duration_s, (int, float)) or duration_s <= 0:
            raise MatrixError(CELL_STATE_INVALID,
                              "%s: an unmeasured duration is not offerable" % candidate_id)
    cell["state"] = state
    if audio is not None:
        cell["audio"] = audio
    if duration_s is not None:
        cell["duration_s"] = duration_s
    if provider is not None:
        cell["provider"] = provider
    if delivered:
        cell["delivered_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _finalize(matrix)
    return cell


def present(matrix):
    """The offer surface. A partial matrix is refused, never shown as complete."""
    require_complete(matrix)
    return [cell_receipt(matrix, cid) for cid in CANDIDATE_IDS]


# ---- selection ----------------------------------------------------------

def cell_receipt(matrix, candidate_id):
    """Lineage for one cell, with its concept group preserved. Never audio."""
    cell = next((c for c in matrix.get("cells") or []
                 if c.get("candidate_id") == candidate_id), None)
    if cell is None:
        raise MatrixError(CANDIDATE_ID_UNKNOWN, candidate_id)
    concept = next((c for c in matrix.get("concepts") or []
                    if c.get("concept_id") == cell["concept_id"]), {})
    treatment = next((t for t in matrix.get("treatments") or []
                      if t.get("treatment") == cell["treatment"]), {})
    return {
        "candidate_id": cell["candidate_id"],
        "concept": {"concept_id": concept.get("concept_id"),
                    "title": concept.get("title"),
                    "perspective": concept.get("perspective"),
                    "lyric_hash": cell["lyric_hash"]},
        "treatment": {"code": cell["treatment"],
                      "variant_id": treatment.get("variant_id"),
                      "treatment_hash": cell["treatment_hash"]},
        "cell_digest": cell["cell_digest"],
        "matrix_digest": matrix.get("matrix_digest"),
        "state": cell.get("state"),
        "audio": cell.get("audio"),
        "duration_s": cell.get("duration_s"),
        "cost": cell.get("cost"),
    }


def select(matrix, candidate_id, at=None):
    """The operator picks exactly ONE cell by its string id (``2B``)."""
    require_complete(matrix)
    if not isinstance(candidate_id, str) or not CANDIDATE_ID_RE.match(candidate_id):
        raise MatrixError(CANDIDATE_ID_UNKNOWN,
                          "%r is not a 1A-3C candidate id" % (candidate_id,))
    cell = next((c for c in matrix.get("cells") or []
                 if c.get("candidate_id") == candidate_id), None)
    if cell is None:
        raise MatrixError(CANDIDATE_ID_UNKNOWN,
                          "%s is not in matrix %s"
                          % (candidate_id, matrix.get("matrix_digest")))
    if cell.get("state") != "offerable":
        raise MatrixError(CANDIDATE_NOT_OFFERABLE,
                          "%s is %s" % (candidate_id, cell.get("state")))
    receipt = cell_receipt(matrix, candidate_id)
    return {
        "schema": SELECTION_SCHEMA,
        "candidate_matrix_version": CANDIDATE_MATRIX_VERSION,
        "candidate_id": candidate_id,          # always a string, never int()
        "concept": receipt["concept"],
        "treatment": receipt["treatment"],
        "cell_digest": receipt["cell_digest"],
        "matrix_digest": matrix["matrix_digest"],
        "style_id": matrix.get("style_id"),
        "run_id": matrix.get("run_id"),
        "audio": receipt["audio"],
        "duration_s": receipt["duration_s"],
        "status": "selected",
        "selected_at": at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def validate_selection(selection, matrix):
    """A selection is valid only against the matrix digest it came from."""
    if not isinstance(selection, dict) or selection.get("schema") != SELECTION_SCHEMA:
        raise MatrixError(MATRIX_SCHEMA_UNSUPPORTED, "not a v2 selection")
    if not isinstance(matrix, dict) or matrix.get("schema") != MATRIX_SCHEMA:
        raise MatrixError(MATRIX_SCHEMA_UNSUPPORTED, "not a v2 candidate matrix")
    if matrix.get("matrix_digest") != _matrix_digest(matrix):
        raise MatrixError(MATRIX_DIGEST_MISMATCH, "matrix content changed")
    if selection.get("matrix_digest") != matrix.get("matrix_digest"):
        raise MatrixError(MATRIX_DIGEST_MISMATCH,
                          "selection %s came from a different matrix"
                          % (selection.get("candidate_id"),))
    cid = selection.get("candidate_id")
    cell = next((c for c in matrix.get("cells") or []
                 if c.get("candidate_id") == cid), None)
    if cell is None:
        raise MatrixError(CANDIDATE_ID_UNKNOWN, repr(cid))
    if selection.get("cell_digest") != cell.get("cell_digest") \
            or (selection.get("concept") or {}).get("lyric_hash") != cell.get("lyric_hash") \
            or (selection.get("treatment") or {}).get("treatment_hash") \
            != cell.get("treatment_hash"):
        raise MatrixError(MATRIX_DIGEST_MISMATCH,
                          "%s lineage does not match this matrix" % cid)
    return selection


# ---- persistence --------------------------------------------------------

def _dir(run_dir, state_dir=None):
    return state_dir or os.path.join(run_dir, DIRNAME)


def save_matrix(run_dir, matrix, state_dir=None):
    """Write the matrix artifact. Status is re-derived first, so a caller cannot
    save a partial matrix as complete."""
    if matrix.get("schema") != MATRIX_SCHEMA:
        raise MatrixError(MATRIX_SCHEMA_UNSUPPORTED, "not a v2 candidate matrix")
    _finalize(matrix)
    target = os.path.join(_dir(run_dir, state_dir), MATRIX_FILE)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(matrix, f, indent=2, sort_keys=True)
    return target


def load_matrix(run_dir, state_dir=None):
    target = os.path.join(_dir(run_dir, state_dir), MATRIX_FILE)
    with open(target, encoding="utf-8") as f:
        matrix = json.load(f)
    if matrix.get("schema") != MATRIX_SCHEMA:
        raise MatrixError(MATRIX_SCHEMA_UNSUPPORTED, "not a v2 candidate matrix")
    return matrix


def save_selection(run_dir, selection, state_dir=None):
    target = os.path.join(_dir(run_dir, state_dir), SELECTION_FILE)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(selection, f, indent=2, sort_keys=True)
    return target


def load_selection(run_dir, state_dir=None):
    target = os.path.join(_dir(run_dir, state_dir), SELECTION_FILE)
    with open(target, encoding="utf-8") as f:
        return json.load(f)
