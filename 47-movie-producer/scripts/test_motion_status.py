#!/usr/bin/env python3
"""
test_motion_status.py: offline, network-free proof of the MG-046
motion_status bridge contract. Zero third-party deps. Exit 0 = all
behaviors hold, exit 1 = a contract violation.

The board is an in-process double that replaces cc_board._request:
it keeps campaigns in memory, enforces the legal transition map
server-side (an illegal jump is a 409), and is idempotent on job_id
for campaign creation, exactly as the real board contract states.

Proves:
  * FAIL-THEN-RESUME IDEMPOTENCE: a board failure mid-sync (the
    create lands, the first move fails) followed by a resume sync
    produces exactly ONE campaign create POST, no duplicate
    attestation, and the stage still reaches its target.
  * LEGAL PATH: the recorded PATCH sequence never contains an
    in_progress -> done jump; done is reached through review.
  * DONE GATING: a status document claiming DELIVERED with a
    mandatory artifact missing is blocked BY NAME (poster, delivery
    receipt) and the stage stops at review.
  * PARENT RETURN: an insert's sync creates NO campaign; its stage
    moves on the parent job's campaign.
  * FAIL-SOFT: with the board disabled, sync still attests and
    exits 0.
  * PARENT READER VISIBILITY: the bridge's attestation records
    land under the phase_attestations key executive_producer
    .attest_phase writes, so executive_producer's own readers
    (_attestations, _attested_phase_ids) see them.
"""

import json
import sys
import tempfile
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cc_board  # noqa: E402
import executive_producer  # noqa: E402
import motion_status  # noqa: E402

ENV = {"MISSION_CONTROL_URL": "http://board-double.invalid", "MC_API_TOKEN": "t"}


class BoardDouble:
    """In-memory Command Center board. campaigns: job_id ->
    {stage_slug: status}. Every request is recorded."""

    def __init__(self):
        self.campaigns = {}
        self.requests = []          # (method, job_id_or_None, payload)
        self.landed = []            # statuses of PATCHes that actually landed
        self.fail_next_patch = False

    def request(self, method, url, payload, cfg):
        path = url[len(cfg["base_url"]):]
        parts = [p for p in path.split("/") if p]
        job_id = parts[-1] if method in ("GET", "PATCH") else None
        self.requests.append((method, job_id, payload))
        if method == "POST":
            job = payload["job_id"]
            if job in self.campaigns:
                return 200, {"campaign_id": job, "created": False,
                             "stages": list(self.campaigns[job])}
            self.campaigns[job] = {
                s["slug"]: "backlog" for s in payload.get("stages") or []}
            return 201, {"campaign_id": job, "created": True,
                         "stages": list(self.campaigns[job])}
        if method == "GET":
            cards = [{"stage_slug": slug, "status": status}
                     for slug, status in self.campaigns.get(job_id, {}).items()]
            return 200, {"cards": cards}
        if method == "PATCH":
            if self.fail_next_patch:
                self.fail_next_patch = False
                raise urllib.error.URLError("injected board failure")
            slug = payload["stage_slug"]
            target = payload["status"]
            current = self.campaigns[job_id][slug]
            if target not in cc_board._LEGAL.get(current, set()):
                return 409, {"error": "illegal transition %s->%s" % (current, target)}
            self.campaigns[job_id][slug] = target
            self.landed.append(target)
            return 200, {}
        return 405, {}

    def count(self, method):
        return sum(1 for r in self.requests if r[0] == method)

    def patch_sequence(self):
        return [r[2]["status"] for r in self.requests if r[0] == "PATCH"]


def _run(fails, cond, msg):
    if not cond:
        fails.append(msg)


def status_doc(job_id="job-motion-1", origin="own", board_job=None, parent=None):
    return {
        "schemaVersion": "1.0",
        "item": "MG-046",
        "identity": {
            "jobId": job_id,
            "companyId": "company-1",
            "taskId": (parent or {}).get("task_id") or job_id,
            "taskOrigin": origin,
            "parentJobId": (parent or {}).get("job_id"),
            "parentTaskId": (parent or {}).get("task_id"),
            "boardJobId": board_job or job_id,
            "stageSlug": "motion-%s" % job_id,
        },
        "mode": "vsl_desktop" if origin == "parent" else "powerpoint_graphic",
        "executionContext": "production",
        "diagnostic": False,
        "phase": "CREATED",
        "productionStatus": None,
        "releaseStatus": None,
        "missingMandatory": ["mp4", "poster"],
    }


def write_status(run_dir: Path, doc, events):
    cp = run_dir / "working" / "checkpoints"
    cp.mkdir(parents=True, exist_ok=True)
    (cp / "motion-status.json").write_text(json.dumps(doc, indent=2) + "\n")
    (cp / "motion-status-events.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events))


def write_receipt(run_dir: Path, kinds=("mp4", "poster")):
    cp = run_dir / "working" / "checkpoints"
    receipt = {
        "schema_version": "1.0", "item": "MG-046",
        "artifacts": [{"kind": k, "path": "renders/final.mp4",
                       "sha256": "0" * 64, "bytes": 10} for k in kinds],
        "missing_mandatory": [],
    }
    (cp / "delivery-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


def event(seq, kind, status=None, phase=None):
    return {"seq": seq, "at": "2026-10-15T00:00:0%dZ" % seq, "kind": kind,
            "jobId": "job-motion-1", "taskId": "job-motion-1",
            "phase": phase, "productionStatus": status,
            "detail": {"phase": phase} if phase else {}}


def main() -> int:
    fails = []
    double = BoardDouble()
    original_request = cc_board._request
    cc_board._request = double.request
    try:
        # ---- FAIL-THEN-RESUME: one campaign, no duplicates --------
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            doc = status_doc()
            doc["phase"] = "SCENES_READY"
            events = [event(0, "phase_transition", phase="CREATED"),
                      event(1, "phase_transition", phase="SCENES_READY")]
            write_status(run_dir, doc, events)
            double.fail_next_patch = True
            code1, report1 = motion_status.sync(run_dir, env=ENV)
            _run(fails, code1 == 0, "first sync should exit 0 (fail-soft), got %s" % code1)
            _run(fails, report1["board"]["created_campaign"] is True,
                 "first sync should create the campaign")
            _run(fails, report1["board"]["ok"] is False,
                 "first sync board move should report the injected failure")
            code2, report2 = motion_status.sync(run_dir, env=ENV)
            _run(fails, code2 == 0 and report2["board"]["ok"] is True,
                 "resume sync should succeed, got %s" % (report2,))
            _run(fails, double.count("POST") == 1,
                 "fail-then-resume must create exactly ONE campaign; POSTs=%d"
                 % double.count("POST"))
            _run(fails, len(double.campaigns) == 1,
                 "board must hold exactly one campaign, got %s" % list(double.campaigns))
            stage = double.campaigns["job-motion-1"]["motion-job-motion-1"]
            _run(fails, stage == "in_progress",
                 "stage should be in_progress after resume, got %s" % stage)
            # Attestation idempotence across the two syncs.
            manifest = json.loads(
                (run_dir / "working" / "checkpoints" / "video_process_manifest.json")
                .read_text())
            _run(fails, len(manifest["phase_attestations"]) == 2,
                 "two events attested exactly once across fail+resume; got %d "
                 "attestations" % len(manifest["phase_attestations"]))
            _run(fails, manifest["phase_attestations"][0]["phase_id"] == "MG-CREATED",
                 "attestation carries the phase id, got %s"
                 % manifest["phase_attestations"][0])
            _run(fails,
                 manifest["phase_attestations"][0]["owning_role"] == "skill72-motion",
                 "attestation carries the bridge owning role, got %s"
                 % manifest["phase_attestations"][0])
            _run(fails, "phases" not in manifest,
                 "bridge records land under phase_attestations, not a phases key")
            _run(fails, "finalized" not in manifest,
                 "motion attestation never finalizes the parent manifest")
            # The parent's OWN readers see the bridge's records:
            # _attestations feeds executive_producer's phase
            # precondition checks, and _attested_phase_ids its plan.
            seen = executive_producer._attestations(run_dir)
            _run(fails, len(seen) == 2,
                 "executive_producer._attestations sees the bridge records; got %d"
                 % len(seen))
            seen_ids = executive_producer._attested_phase_ids(run_dir)
            _run(fails, seen_ids == {"MG-CREATED", "MG-SCENES_READY"},
                 "executive_producer._attested_phase_ids sees both bridge "
                 "phases; got %s" % seen_ids)

            # ---- Lifecycle to done through the legal path -----------
            doc["productionStatus"] = "RENDERED"
            doc["phase"] = "FINAL_RENDERED"
            doc["missingMandatory"] = ["poster"]
            write_status(run_dir, doc, events)
            motion_status.sync(run_dir, env=ENV)
            stage = double.campaigns["job-motion-1"]["motion-job-motion-1"]
            _run(fails, stage == "review",
                 "RENDERED should move the stage to review, got %s" % stage)

            patches_before = len(double.patch_sequence())
            doc["productionStatus"] = "DELIVERED"
            doc["phase"] = "DELIVERED"
            doc["missingMandatory"] = []
            write_status(run_dir, doc, events)
            write_receipt(run_dir)
            code3, report3 = motion_status.sync(run_dir, env=ENV)
            stage = double.campaigns["job-motion-1"]["motion-job-motion-1"]
            _run(fails, code3 == 0 and stage == "done",
                 "complete DELIVERED should reach done, got stage=%s report=%s"
                 % (stage, report3))
            _run(fails, report3["board"]["done_blocked"] == [],
                 "nothing should block done on a complete receipt")
            seq = double.patch_sequence()[patches_before:]
            _run(fails, seq == ["done"] or seq[-1] == "done",
                 "final approach to done recorded, got %s" % seq)
            # No illegal jump among the transitions that actually
            # landed (the injected failure never landed server-side).
            statuses = ["backlog"] + double.landed
            legal = all(
                b in cc_board._LEGAL.get(a, set())
                for a, b in zip(statuses, statuses[1:]))
            _run(fails, legal,
                 "every landed PATCH transition must be legal; sequence=%s" % statuses)
            _run(fails, double.count("POST") == 1,
                 "still exactly one campaign after the full lifecycle")

        # ---- DONE GATING: missing mandatory artifact blocks by name -
        double2 = BoardDouble()
        cc_board._request = double2.request
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            doc = status_doc(job_id="job-motion-2")
            doc["productionStatus"] = "DELIVERED"
            doc["phase"] = "DELIVERED"
            doc["missingMandatory"] = ["poster"]
            write_status(run_dir, doc, [event(0, "phase_transition", phase="CREATED")])
            code, report = motion_status.sync(run_dir, env=ENV)
            _run(fails, code == 0, "gated sync exits 0, got %s" % code)
            _run(fails, "poster" in report["board"]["done_blocked"],
                 "done must be blocked by name (poster); got %s"
                 % report["board"]["done_blocked"])
            _run(fails, "delivery_receipt" in report["board"]["done_blocked"],
                 "done must be blocked by name (delivery_receipt); got %s"
                 % report["board"]["done_blocked"])
            stage = double2.campaigns["job-motion-2"]["motion-job-motion-2"]
            _run(fails, stage == "review",
                 "a blocked stage stops at review, got %s" % stage)
            _run(fails, "done" not in double2.patch_sequence(),
                 "no PATCH to done may be issued while blocked")

        # ---- PARENT RETURN: no second campaign for an insert --------
        double3 = BoardDouble()
        cc_board._request = double3.request
        double3.campaigns["parent-job-9"] = {"motion-insert-1": "backlog"}
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            doc = status_doc(
                job_id="insert-1", origin="parent", board_job="parent-job-9",
                parent={"job_id": "parent-job-9", "task_id": "parent-task-9"})
            doc["identity"]["stageSlug"] = "motion-insert-1"
            doc["phase"] = "SCENES_READY"
            write_status(run_dir, doc, [event(0, "phase_transition", phase="CREATED")])
            code, report = motion_status.sync(run_dir, env=ENV)
            _run(fails, code == 0, "insert sync exits 0, got %s" % code)
            _run(fails, double3.count("POST") == 0,
                 "an insert must never create a campaign; POSTs=%d" % double3.count("POST"))
            _run(fails, report["board"]["insert"] is True,
                 "report should mark the insert")
            stage = double3.campaigns["parent-job-9"]["motion-insert-1"]
            _run(fails, stage == "in_progress",
                 "the insert stage moves on the PARENT campaign, got %s" % stage)
            _run(fails, not (run_dir / "working" / "checkpoints" / "cc-board.created").exists(),
                 "no campaign marker is written for an insert")

        # ---- FAIL-SOFT: board disabled, attestation still lands -----
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            doc = status_doc(job_id="job-motion-3")
            write_status(run_dir, doc, [event(0, "phase_transition", phase="CREATED")])
            code, report = motion_status.sync(run_dir, env={})
            _run(fails, code == 0, "board-disabled sync exits 0, got %s" % code)
            _run(fails, report["board"]["enabled"] is False,
                 "report should state the board is disabled")
            _run(fails, report["attested_new"] == 1,
                 "attestation lands even with the board disabled")
    finally:
        cc_board._request = original_request

    if fails:
        print("=== test_motion_status: FAILURES ===", file=sys.stderr)
        for f in fails:
            print(f"  FAIL: {f}", file=sys.stderr)
        return 1
    print("=== test_motion_status: ALL BEHAVIORS HOLD "
          "(fail-then-resume one campaign, legal path only, done gated by name, "
          "parent return without a second campaign, fail-soft) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
