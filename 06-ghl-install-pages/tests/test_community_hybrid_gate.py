"""WF09 — the community QC gate's hybrid checks (A12/A13).

Runs the real bash gate against synthetic evidence roots: a healthy run passes; a
detach that claims the course was deleted fails; a reused group reported deleted fails;
a deactivation without residue coordinates fails; an attach with no separate
relationship receipt fails.
"""
import json
import os
import subprocess
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(SKILL_DIR, "qc-built-community.sh")


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def _root(tmp, *, assoc=None, cleanup=None, receipts=None):
    tmp = str(tmp)
    _write(os.path.join(tmp, "routing", "community-built.json"), {
        "community_name": "ZHC Founders", "community_url": "https://p.example/x",
        "verify": {"http": 200, "marker_in_rendered_dom": True, "render_errors": [],
                   "community_url": "https://p.example/x"}})
    recs = receipts if receipts is not None else [
        {"object_type": "community", "slug": "zhc_founders", "action": "created",
         "verify": {"ok": True}, "created": True, "ts": "2026-11-08T00:00:00Z"},
        {"object_type": "learning_association", "slug": "zhc_launch", "action": "created",
         "verify": {"ok": True}, "created": True, "ts": "2026-11-08T00:00:00Z"},
    ]
    for r in recs:
        _write(os.path.join(tmp, "ecosystem", f"{r['object_type']}-{r['slug']}.json"), r)
    if assoc is not None:
        _write(os.path.join(tmp, "routing", "learning-association.json"), assoc)
    if cleanup is not None:
        _write(os.path.join(tmp, "routing", "cleanup.json"), cleanup)
    return tmp


def _run(root):
    cp = subprocess.run(["bash", GATE, root, "--json"], capture_output=True, text=True,
                        timeout=120)
    return cp.returncode, cp.stdout + cp.stderr


GOOD_CLEANUP = {"cleanup_primitive": "inactivate", "deleted": False, "inactivated": True,
                "status": "inactive", "residue": "group remains; set Inactive",
                "group_url": "https://p.example/communities/groups/zhc-founders/home"}


def test_gate_passes_a_healthy_attach_with_inactive_residue(tmp_path):
    root = _root(tmp_path, assoc={"operation": "attach", "same_location": True,
                                  "verify": {"ok": True}}, cleanup=GOOD_CLEANUP)
    rc, out = _run(root)
    assert rc == 0, out


def test_gate_fails_detach_that_claims_course_deleted(tmp_path):
    root = _root(tmp_path, assoc={"operation": "detach", "same_location": True,
                                  "verify": {"course_deleted": True,
                                             "course_still_present": True}},
                 cleanup=GOOD_CLEANUP)
    rc, out = _run(root)
    assert rc == 1, out
    assert "detach claims the COURSE was deleted" in out


def test_gate_fails_detach_without_course_presence_proof(tmp_path):
    root = _root(tmp_path, assoc={"operation": "detach", "same_location": True,
                                  "verify": {"course_deleted": False}},
                 cleanup=GOOD_CLEANUP)
    rc, out = _run(root)
    assert rc == 1, out
    assert "did not prove the course still exists" in out


def test_gate_fails_attach_without_a_separate_relationship_receipt(tmp_path):
    root = _root(tmp_path, assoc={"operation": "attach", "same_location": True,
                                  "verify": {"ok": True}},
                 cleanup=GOOD_CLEANUP,
                 receipts=[{"object_type": "community", "slug": "zhc_founders",
                            "action": "created", "verify": {"ok": True},
                            "created": True, "ts": "2026-11-08T00:00:00Z"}])
    rc, out = _run(root)
    assert rc == 1, out
    assert "no separate learning_association receipt" in out


def test_gate_fails_cross_location_association(tmp_path):
    root = _root(tmp_path, assoc={"operation": "attach", "same_location": False,
                                  "verify": {"ok": True}}, cleanup=GOOD_CLEANUP)
    rc, out = _run(root)
    assert rc == 1, out
    assert "not same-location" in out


def test_gate_fails_reused_group_reported_deleted(tmp_path):
    root = _root(tmp_path, assoc={"operation": "attach", "same_location": True,
                                  "verify": {"ok": True}},
                 cleanup={"cleanup_primitive": "preserve", "deleted": True})
    rc, out = _run(root)
    assert rc == 1, out


def test_gate_fails_inactivation_without_residue_coordinates(tmp_path):
    bad = dict(GOOD_CLEANUP)
    bad["group_url"] = ""
    root = _root(tmp_path, assoc={"operation": "attach", "same_location": True,
                                  "verify": {"ok": True}}, cleanup=bad)
    rc, out = _run(root)
    assert rc == 1, out
    assert "group URL" in out


def test_gate_selftest_exit_zero():
    cp = subprocess.run(["bash", GATE, "--selftest"], capture_output=True, text=True,
                        timeout=120)
    assert cp.returncode == 0, cp.stderr
