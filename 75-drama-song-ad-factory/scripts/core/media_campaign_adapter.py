"""media_campaign_adapter.py — T12 optional Command Center campaign adapter.

probe -> create -> stage -> block -> complete over the durable cc_sync outbox.
Local first: every intent is persisted (pending) before any optional transport,
keyed tenant/workspace/run on this host, and acked only on the board's
idempotent replay. An unknown/cross-workspace or unbound-host projection is
refused (row stays pending, never sent); local creation continues while the
board is absent. Optional stays optional and disabled stays disabled: nothing
here enables a timer, a runner or an Option 3 gate.

Stdlib only: json, os, sys.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cc_sync  # noqa: E402


def open_outbox(workspace, run_id, db_path=None, base_url=None, sender=None,
                binding=None):
    """Durable outbox bound to tenant/workspace/run on this host. run_id is
    required: the adapter never lands intent in a shared 'default' run file."""
    if not (run_id or "").strip():
        raise cc_sync.BoardSyncError("run_id required (tenant/workspace/run outbox)")
    return cc_sync.Outbox(db_path=db_path, base_url=base_url,
                          workspace=workspace, sender=sender, run_id=run_id,
                          binding=binding)


def probe(outbox):
    """Local capability report (XR4/X09 step 1). Never contacts the board and
    never claims reachability it has not proven."""
    return dict(outbox.binding_state(),
                module="media_campaign_adapter", projection="optional",
                outbox_path=outbox.db_path,
                pending=len(outbox.pending_sync()),
                counts=outbox.counts())


def create(outbox, job_id, show_name, stages=None, **kw):
    return _row(outbox, outbox.enqueue_create(
        job_id, show_name, stages or [], workspace=outbox.workspace, **kw))


def stage(outbox, job_id, stage_slug, status, actor, **kw):
    return _row(outbox, outbox.enqueue_move(
        job_id, stage_slug, status, actor, workspace=outbox.workspace, **kw))


def block(outbox, job_id, stage_slug, actor, blocked_reason, ask, **kw):
    return stage(outbox, job_id, stage_slug, "blocked", actor,
                 blocked_reason=blocked_reason, ask=ask, **kw)


def complete(outbox, job_id, stage_slug, actor, reviewer, evidence, **kw):
    """Completion needs independent review + registered evidence; cc_sync
    enforces both and the CC PRECONDITION_EVIDENCE rule."""
    return stage(outbox, job_id, stage_slug, "done", actor,
                 reviewer=reviewer, evidence=evidence, **kw)


def flush(outbox):
    """Optional projection. A refused or degraded board leaves rows pending."""
    return outbox.flush()


def _row(outbox, row_id):
    r = outbox.db.execute(
        "SELECT id,kind,job_id,stage_slug,state,updated_at FROM outbox"
        " WHERE id=?", (row_id,)).fetchone()
    return {"id": r[0], "kind": r[1], "job_id": r[2], "stage_slug": r[3],
            "state": r[4], "updated_at": r[5], "outbox_path": outbox.db_path}
