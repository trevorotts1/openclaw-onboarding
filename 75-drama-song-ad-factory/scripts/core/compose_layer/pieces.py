"""Piece render and clean join (row N-75, section 10B stage 10).

The timeline is cut into pieces at PLAIN CUTS ONLY -- never through a
crossfade or a designed transition. Each piece is rendered with the same
settings, side by side as a fresh memory reading allows, and the pieces are
joined WITHOUT re-encoding them (the concat demuxer, stream copy). The song
is laid on ONCE across the whole join, so there is no audio seam.

If the pieces cannot be joined cleanly the master is rendered once, start to
end; that is the fallback, not the failure.

Stdlib only; every argv is data for the renderer.
"""
from __future__ import annotations

from .render_lock import MASTER_FPS, PIX_FMT

TOOL_NAME = "compose_pieces"
TOOL_VERSION = "1.0.0"

PIECE_CUT_THROUGH_TRANSITION = "PIECE_CUT_THROUGH_TRANSITION"
PIECE_TOO_SHORT = "PIECE_TOO_SHORT"
JOIN_NOT_CLEAN = "JOIN_NOT_CLEAN"
MASTER_LENGTH_MISMATCH = "MASTER_LENGTH_MISMATCH"

#: A segment shorter than 3 frames is folded into its neighbour (3D.6).
MIN_FRAMES = 3
#: Planned master length is asserted exactly before the join.
LENGTH_TOLERANCE_S = 1.0 / MASTER_FPS


class PieceError(RuntimeError):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


def _frame(seconds):
    return int(round(float(seconds) * MASTER_FPS))


def cut_points(shots, transitions=()):
    """Cut only at plain cuts; a piece boundary through a transition is refused.

    ``shots``: [{"id", "in", "out"}] in timeline order, seconds.
    ``transitions``: [{"at_s", "duration_s"}] designed or crossfaded joins.
    """
    spans = []
    for at in transitions:
        centre = float(at.get("at_s", 0))
        half = float(at.get("duration_s", 0)) / 2.0
        spans.append((centre - half, centre + half))

    def inside_a_transition(t):
        return any(lo < t < hi for lo, hi in spans)

    points = []
    for left, right in zip(shots, shots[1:]):
        boundary = float(left["out"])
        next_in = float(right["in"])
        gap = boundary - next_in            # positive when an xfade overlaps
        if gap > LENGTH_TOLERANCE_S:
            # A recorded transition explains the overlap: those two shots
            # share frames and cannot be split there. Anything else is a
            # timeline that does not join.
            covered = any(lo - LENGTH_TOLERANCE_S <= next_in
                          and boundary <= hi + LENGTH_TOLERANCE_S
                          for lo, hi in spans)
            if not covered:
                raise PieceError(JOIN_NOT_CLEAN,
                                 "shots %s and %s overlap with no transition"
                                 % (left.get("id"), right.get("id")))
            points.append({"at_s": boundary, "ok": False,
                           "why": "crossfade joins these two shots"})
            continue
        if -gap > LENGTH_TOLERANCE_S:
            raise PieceError(JOIN_NOT_CLEAN,
                             "shots %s and %s do not meet at a cut"
                             % (left.get("id"), right.get("id")))
        if inside_a_transition(boundary):
            points.append({"at_s": boundary, "ok": False,
                           "why": "inside a transition"})
        else:
            points.append({"at_s": boundary, "ok": True})
    return points


def plan_pieces(shots, transitions=(), target_seconds=90.0):
    """Group shots into pieces at plain cuts; fold 1-2 frame segments."""
    folded = fold_short_shots(shots)
    points = cut_points(folded, transitions)
    pieces, current = [], []
    for index, shot in enumerate(folded):
        current.append(shot)
        at_end = index == len(folded) - 1
        boundary = (not at_end and points[index]["ok"]
                    and float(shot["out"]) >= float(current[0]["in"]) + 1e-9)
        long_enough = (sum(float(s["out"]) - float(s["in"]) for s in current)
                       >= target_seconds)
        if at_end or (boundary and long_enough):
            pieces.append(_piece(len(pieces), current))
            current = []
    return {"pieces": pieces, "piece_count": len(pieces),
            "join": "concat-demuxer-stream-copy", "reencode": False}


def fold_short_shots(shots):
    """A shot shorter than 3 frames joins its neighbour at plan time."""
    out = []
    for shot in shots:
        frames = _frame(float(shot["out"]) - float(shot["in"]))
        if frames < MIN_FRAMES and out:
            prev = dict(out.pop())
            prev["out"] = shot["out"]
            prev.setdefault("id", shot.get("id"))
            prev["folded"] = list(prev.get("folded", [])) + [shot.get("id")]
            out.append(prev)
        elif frames < MIN_FRAMES:
            # A lone short first shot has no earlier neighbour: keep it and
            # let the next shot absorb it.
            out.append(dict(shot))
        else:
            out.append(dict(shot))
    if len(out) > 1:
        first = out[0]
        if _frame(float(first["out"]) - float(first["in"])) < MIN_FRAMES:
            out.pop(0)
            out[0] = dict(out[0])
            out[0]["in"] = first["in"]
            out[0]["folded"] = [first.get("id")] + list(out[0].get("folded", []))
    return out


def _piece(index, shots):
    start = float(shots[0]["in"])
    end = float(shots[-1]["out"])
    return {"index": index, "shots": [s.get("id") for s in shots],
            "in_s": start, "out_s": end,
            "frames": _frame(end) - _frame(start),
            "duration_s": round(end - start, 6)}


def piece_render_argv(source, output, encoder="libx264", quality=18):
    """Same settings on every piece so the join can stream-copy."""
    return ["ffmpeg", "-y", "-ss", "{in_s}", "-to", "{out_s}", "-i", source,
            "-c:v", encoder, "-crf", str(quality), "-r", str(MASTER_FPS),
            "-pix_fmt", PIX_FMT, "-an", output]


def parallel_batches(piece_count, browser_cap):
    """Pieces run side by side, up to the cap; the join waits for all."""
    if piece_count <= 0:
        return []
    cap = max(1, int(browser_cap))
    return [list(range(start, min(start + cap, piece_count)))
            for start in range(0, piece_count, cap)]


def assert_length(pieces, planned_seconds):
    """The planned master length is asserted exactly before the join."""
    total = sum(piece["duration_s"] for piece in pieces)
    if abs(total - float(planned_seconds)) > LENGTH_TOLERANCE_S * len(pieces):
        raise PieceError(MASTER_LENGTH_MISMATCH,
                         "pieces total %.3fs, master is %.3fs"
                         % (total, planned_seconds))
    return round(total, 6)


def concat_list(piece_paths):
    if not piece_paths:
        raise PieceError(JOIN_NOT_CLEAN, "no pieces to join")
    return "\n".join("file '%s'" % path.replace("'", "'\\''")
                     for path in piece_paths)


def join_argv(piece_paths, video_only_out, list_path):
    """Join WITHOUT re-encoding: concat demuxer, stream copy."""
    if len(piece_paths) < 1:
        raise PieceError(JOIN_NOT_CLEAN, "no pieces to join")
    return ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
            "-c", "copy", video_only_out]


def lay_song_argv(video_only, song, output):
    """The song is laid on ONCE across the whole join: one audio input."""
    return ["ffmpeg", "-y", "-i", video_only, "-i", song,
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
            "-c:a", "aac", "-shortest", output]


def fallback_single_render(reason):
    """The one-render fallback, as a plan the assembler understands."""
    return {"mode": "single-render", "reason": reason,
            "why": "pieces could not be joined cleanly"}


def join_or_fallback(result):
    """Choose the clean join or the single render; never a silent re-encode."""
    if result.get("joined") and not result.get("reencoded"):
        return {"mode": "piece-join", "reencode": False}
    raise PieceError(JOIN_NOT_CLEAN,
                     "piece join needs a re-encode; use the single render")
