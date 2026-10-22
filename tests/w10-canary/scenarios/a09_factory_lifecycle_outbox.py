#!/usr/bin/env python3
"""a09_factory_lifecycle_outbox.py — acceptance row A09 (weight 8).

Condition (tests/w10-canary/receipt-mapping.json, row A09, verbatim):
    "factory lifecycle + adapter/outbox + completion-guard proofs (S75-W10-U1)"

Three parts, all against the tree under test:

  factory lifecycle
    * an accepted event enqueues THIS run's next eligible action durably
      (control/continuation-queue.json), and the queue reads back;
    * a second event appends without losing the first (the queue is a durable
      log, not a last-write-wins slot).

  completion guard
    * all-parked, all-failed and empty terminal runs are NEVER delivered;
    * an all-COMPLETE stage table with no approvals / independent final QC /
      artifacts / delivery receipts is still NOT delivered, and each missing
      fact is named;
    * the same stage table WITH those facts IS delivered — the guard is not a
      blanket refusal;
    * the on-disk collector path agrees (a bare run dir with complete stages
      but no artifacts is not delivered).

  adapter/outbox
    * an envelope is PREPARED with a deterministic idempotency key; enqueueing
      moves its pieces to QUEUED (prepared is not sent);
    * resume sends each piece once and a second resume SKIPS every
      already-acknowledged piece (no duplicate client send);
    * a dispatch with no channel receipt leaves the piece UNCERTAIN, never sent;
    * a piece cannot be marked sent without a receipt;
    * a sender error is retryable failure, never a silent drop.

Nothing is sent: the outbox sender is a local stub. No provider, no channel.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "a09"
TITLE = "factory lifecycle + adapter/outbox + completion-guard"


def main(argv=None):
    args = H.add_args(description=__doc__).parse_args(argv)
    core = H.resolve_core(args)
    F = H.load_pkg(core, "intake_preflight.factory")
    # delivery_outbox imports stdlib only: load it by file so the outbox proof
    # never depends on the intake card's live model-registry resolution.
    DO = H.load_file(core / "choice_card" / "intake_card" / "delivery_outbox.py",
                     "a09_delivery_outbox")
    c = H.Checks(ROW, TITLE)
    print("A09 %s — tree %s" % (TITLE, core))

    stages = list(F.CANONICAL_STAGES)

    with H.Scratch() as run_dir:
        run_dir = str(run_dir)

        # ---- factory lifecycle: durable next-action queue -----------------
        act = F.continuation_enqueue(run_dir, "approval",
                                     got={"research": "COMPLETE"})
        c.check("a09:event-enqueues-next-eligible-action",
                act.get("verdict") == "runnable"
                and act.get("next_stage") == "creative-strategy"
                and bool(act.get("wake_event")),
                "verdict=%s next=%s wake=%s"
                % (act.get("verdict"), act.get("next_stage"),
                   act.get("wake_event")))

        F.continuation_enqueue(run_dir, "provider-completion",
                               got={"research": "COMPLETE",
                                    "creative-strategy": "COMPLETE"})
        queue = F.drain_continuation(run_dir)
        c.check("a09:continuation-queue-is-durable-log",
                isinstance(queue, list) and len(queue) == 2
                and queue[0].get("event") == "approval"
                and queue[1].get("next_stage") == "script-lyrics",
                "entries=%d first=%s second=%s"
                % (len(queue), (queue[0].get("event") if queue else None),
                   (queue[1].get("next_stage") if len(queue) > 1 else None)))

        # ---- completion guard: terminal shapes are never delivered --------
        parked = {s: "PARKED" for s in stages}
        d_parked, r_parked = F.evaluate_completion(run_dir, parked)
        c.check("a09:completion-guard-all-parked-not-delivered",
                d_parked is False and bool(r_parked.get("reasons")),
                "delivered=%s reasons=%d"
                % (d_parked, len(r_parked.get("reasons") or [])))

        failed = {s: "FAILED_BLOCKED" for s in stages}
        d_failed, r_failed = F.evaluate_completion(run_dir, failed)
        c.check("a09:completion-guard-all-failed-not-delivered",
                d_failed is False and bool(r_failed.get("reasons")),
                "delivered=%s reasons=%d"
                % (d_failed, len(r_failed.get("reasons") or [])))

        d_empty, r_empty = F.evaluate_completion(
            run_dir, {}, evidence={"required": [], "stage_states": {}})
        c.check("a09:completion-guard-empty-run-not-delivered",
                d_empty is False
                and any("empty-run" in r for r in r_empty.get("reasons") or []),
                "delivered=%s reasons=%s"
                % (d_empty, (r_empty.get("reasons") or [])[:2]))

        complete = {s: "COMPLETE" for s in stages}
        d_bare, r_bare = F.evaluate_completion(run_dir, complete)
        named = " | ".join(r_bare.get("reasons") or [])
        c.check("a09:completion-guard-names-each-missing-fact",
                d_bare is False
                and "approvals not current" in named
                and "independent final QC not PASS" in named
                and "required artifacts missing" in named
                and "delivery receipts" in named,
                named[:260])

        full = {"required": ["music"], "stage_states": {"music": "complete"},
                "approvals_current": True, "final_qc_independent_pass": True,
                "artifacts_present": True, "delivery_receipts_ok": True}
        d_full, r_full = F.evaluate_completion(run_dir, {}, evidence=full)
        c.check("a09:completion-guard-delivers-complete-run",
                d_full is True and r_full.get("reasons") == [],
                "delivered=%s reasons=%s"
                % (d_full, r_full.get("reasons")))

        # ---- adapter / outbox --------------------------------------------
        origin = {"tenant_id": "tenantA09", "channel": "canary",
                  "conversation_id": "convA09", "thread_id": "t0"}
        env = DO.build_envelope("runA09", "tenantA09", "script", "script", 1,
                                origin,
                                text="Here is the script. Nothing is made "
                                     "until you approve it.")
        c.check("a09:envelope-prepared-not-sent",
                env["delivery"]["state"] == DO.PREPARED
                and bool(env["delivery"]["idempotency_key"])
                and env["delivery"]["message_ids"] == [],
                "state=%s key=%s"
                % (env["delivery"]["state"],
                   env["delivery"]["idempotency_key"]))

        box = DO.Outbox(run_dir)
        pieces = box.enqueue(env)
        c.check("a09:outbox-enqueue-moves-pieces-to-queued",
                bool(pieces) and all(p["state"] == DO.QUEUED for p in pieces)
                and len(box.pending()) == len(pieces),
                "pieces=%d pending=%d"
                % (len(pieces), len(box.pending())))

        receipts = {}

        def sender(piece):
            receipts[piece["piece_id"]] = "receipt-%d" % len(receipts)
            return receipts[piece["piece_id"]]

        sent = box.resume(sender)
        again = box.resume(sender)
        c.check("a09:outbox-resume-sends-each-piece-once",
                len(sent.get("sent") or []) == len(pieces)
                and sent.get("failed") == []
                and (again.get("sent") or []) == []
                and len(again.get("skipped") or []) == len(pieces),
                "first_sent=%d second_sent=%d skipped=%d"
                % (len(sent.get("sent") or []), len(again.get("sent") or []),
                   len(again.get("skipped") or [])))

        env2 = DO.build_envelope("runA09", "tenantA09", "lyrics", "lyrics", 2,
                                 origin, text="Here are the lyrics.")
        box2 = DO.Outbox(str(Path(run_dir) / "second"))
        p2 = box2.enqueue(env2)
        unsure = box2.resume(lambda _p: None)
        c.check("a09:outbox-no-receipt-is-uncertain",
                len(unsure.get("uncertain") or []) == len(p2)
                and (unsure.get("sent") or []) == []
                and all(box2.get(pid)["state"] == DO.UNCERTAIN
                        for pid in unsure.get("uncertain") or []),
                "uncertain=%d sent=%d"
                % (len(unsure.get("uncertain") or []),
                   len(unsure.get("sent") or [])))

        refused = None
        try:
            box2.mark(p2[0]["piece_id"], DO.SENT)
        except DO.OutboxError as exc:
            refused = str(exc)
        c.check("a09:outbox-refuses-sent-without-receipt",
                bool(refused), str(refused)[:160])

        env3 = DO.build_envelope("runA09", "tenantA09", "storyboard",
                                 "storyboard", 1, origin, text="Storyboard.")
        box3 = DO.Outbox(str(Path(run_dir) / "third"))
        p3 = box3.enqueue(env3)

        def boom(_piece):
            raise RuntimeError("channel unreachable")

        broke = box3.resume(boom)
        c.check("a09:outbox-sender-error-is-retryable-failure",
                len(broke.get("failed") or []) == len(p3)
                and all(box3.get(pid)["state"] == DO.RETRYABLE_FAILURE
                        for pid in broke.get("failed") or []),
                "failed=%d" % len(broke.get("failed") or []))

        return c.finish(args.out)


if __name__ == "__main__":
    sys.exit(main())
