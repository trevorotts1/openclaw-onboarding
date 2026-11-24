"""route_source.py: F-ROUTE-SRC -- one route source, derived from the shot.

The storyboard's own ``lip_sync`` flag is the ONLY source of a shot's route:

  * ``lip_sync`` true (a talking or singing shot) -> the lip-sync route
    (``kling_lipsync`` in the storyboard vocabulary; the MODEL is
    ``omnihuman-2-0`` from model_lock, section 3C.1a -- the route NAME is not
    the model);
  * ``lip_sync`` false -> a story route (H3 image-to-video), never the lip
    route.

The plan builder derives every shot's route from that flag and refuses a plan
whose stored route disagrees with the flag -- ``ROUTE_SOURCE_MISMATCH`` --
BEFORE any spend. A mismatch at assembly is too late; it fails at plan build.

This is the plan side of F-ROUTE-SRC. The evidence join in
``scripts/core/lipsync_evidence.py`` (``check_plan`` / ``LIPSYNC_ROUTE_CHANGED``)
belongs to U-LIPGATE and is unchanged here; a note carries the join forward.
Stdlib only, no network, no spend.
"""
from __future__ import annotations

#: Storyboard's route vocabulary for a lip-sync shot. The NAME is the data
#: vocabulary; the actual model is omnihuman-2-0 (model_lock, section 3C.1a).
ROUTE_LIPSYNC = "kling_lipsync"
#: Any route that is not the lip route (H3 story animation and its kin).
ROUTE_STORY_DEFAULT = "h3_i2v"

ROUTE_SOURCE_MISMATCH = "ROUTE_SOURCE_MISMATCH"
ROUTE_SOURCE_OK = "ROUTE_SOURCE_OK"


def _flag(shot):
    v = shot.get("lip_sync") if isinstance(shot, dict) else None
    return v is True                     # only a real true flag mints lip route


def derive_route(shot):
    """The route one shot MUST carry, from its own ``lip_sync`` flag.

    True -> ``kling_lipsync``; False -> the shot's existing story route, or
    ``h3_i2v`` when it names none. The flag is the one source; the stored
    ``route`` never overrides it.
    """
    if _flag(shot):
        return ROUTE_LIPSYNC
    route = shot.get("route") if isinstance(shot, dict) else None
    if isinstance(route, str) and route.strip() and route != ROUTE_LIPSYNC:
        return route.strip()
    return ROUTE_STORY_DEFAULT


def check_route_source(shots):
    """Refuse a plan whose stored routes disagree with the lip_sync flag.

    shots: [{shot_id, lip_sync, route}]. A shot with ``lip_sync`` true MUST
    carry the lip route; a shot with it false MUST NOT. Returns
    ``{'pass', 'reason_code', 'rows', 'failed'}``. ``reason_code`` is
    ROUTE_SOURCE_MISMATCH when any row disagrees, so the plan builder stops
    before any paid job.
    """
    if not isinstance(shots, list) or not shots:
        return {"pass": False, "reason_code": ROUTE_SOURCE_MISMATCH,
                "rows": [], "failed": [],
                "detail": "no shots to check routes on"}
    rows = []
    for sh in shots:
        sid = sh.get("shot_id") if isinstance(sh, dict) else None
        flag = _flag(sh)
        stored = sh.get("route") if isinstance(sh, dict) else None
        derived = derive_route(sh)
        if flag:
            ok = stored == ROUTE_LIPSYNC
        else:
            ok = stored != ROUTE_LIPSYNC
        rows.append({"shot_id": sid, "lip_sync": flag,
                     "stored_route": stored, "derived_route": derived,
                     "ok": ok,
                     "reason_code": None if ok else ROUTE_SOURCE_MISMATCH})
    failed = [r for r in rows if not r["ok"]]
    return {"pass": not failed,
            "reason_code": ROUTE_SOURCE_OK if not failed
            else ROUTE_SOURCE_MISMATCH,
            "rows": rows, "failed": failed,
            "detail": "; ".join("%s lip_sync=%s route=%r (must be %r)"
                                % (r["shot_id"], r["lip_sync"],
                                   r["stored_route"], r["derived_route"])
                                for r in failed)}


def build_plan_routes(shots, strict=True):
    """Derive each shot's route from its flag and return the aligned plan.

    With ``strict`` (the default) a shot whose stored route disagrees with its
    flag is refused: a dict ``{'pass': False, 'reason_code':
    ROUTE_SOURCE_MISMATCH, ...}``. With ``strict=False`` the derived route is
    written onto a copy of each shot. Never mutates the caller's records.
    """
    chk = check_route_source(shots)
    if strict and not chk["pass"]:
        return chk
    out = []
    for sh in shots:
        rec = dict(sh)
        rec["route"] = derive_route(sh)
        out.append(rec)
    return {"pass": True, "reason_code": ROUTE_SOURCE_OK,
            "shots": out, "rows": chk["rows"]}
