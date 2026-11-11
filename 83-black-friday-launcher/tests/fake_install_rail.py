"""A stand-in delivery rail for the install-stage tests: it reads every handed-off page "back" the way a
real rail would after installing it. It installs nothing and calls nothing; it only returns data."""

JOURNEY = {"main_purchased_verified": True, "u1_event": "explicit_decline", "u1_accepted": False}


def rail(handoff):
    return {"pages": {
        row["role"]: {"page_id": row["page_id"], "installed_url": "https://pages.example.test/" + row["role"],
                      "route_guard_binding": {"journey": dict(JOURNEY), "observed_at": "2026-11-10T12:00:00-05:00",
                                              "evidence_ref": "rail-readback-" + row["role"]}}
        for row in handoff["pages"]}}


def rail_with_no_main_purchase(handoff):
    out = rail(handoff)
    for got in out["pages"].values():
        got["route_guard_binding"]["journey"]["main_purchased_verified"] = False
    return out


def rail_that_reads_nothing_back(handoff):
    return {"pages": {}}
