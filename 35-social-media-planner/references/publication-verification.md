# Publication evidence handoff

A completed worker task proves that worker finished its task. It does not prove
that a post exists on a social platform. Command Center independently reconciles
publication after the production task, separately for each connected account.

1. Obtain canonical `company_id`, `queue_id`, and production task ID from the
   dispatch task. Never derive them from a display name or another client.
2. Write `publish-receipts.json` inside that task's approved artifact directory.
   Register it through the existing `POST /api/tasks/:taskId/deliverables` flow
   before finishing the task; preserve the captured SHA. A file left only in a
   private staging directory is not registered evidence.
3. The production receipt carries `company_id`, `queue_id`, `planned_posts`,
   `created_posts`, and `posts`. Each post identifies `platform`, `account_id`,
   and actual `post_id`; keep URL, schedule and readback evidence when available.
   For a fully created batch, planned_posts must match the complete post
   inventory. Uncreated/failed planned work stays explicit and incomplete;
   never lower the count to make a partial batch look finished.
4. On `verification_required`, the canonical verification task performs
   **readback only**: query the provider for the original IDs. Do not create,
   resend, duplicate, delete or reschedule posts while verifying them.
5. Register the verification task's own `publish-receipts.json` through its
   normal deliverables endpoint. Include `company_id`, `queue_id`,
   `source_receipt_sha256`, `planned_posts`, `created_posts`, and per-post
   `platform`, `account_id`, `post_id`, `url`, optional `scheduled_at`, and
   `readback: {id, account_id, status, checked_at}`. Status is actual provider
   `published` or `scheduled`; checked_at is a real ISO timestamp from the
   readback. IDs/counts must match the registered production inventory.
6. Use the company's actual connected accounts. A generic platform label or a
   missing account ID never grants permission to accept another client's post.
   A scheduled post remains scheduled until its due time and a later readback.
7. Missing credentials, incomplete inventory, expired links, mismatched hashes
   or unreadable artifacts remain visible verification/repair work. Continue
   independent healthy accounts. The scheduler owns bounded retries and
   escalation; a worker must not declare success just to clear the card.

Legacy production receipts may omit company/queue only when the existing
queue-to-task and task-to-company database ownership independently binds them.
Explicit conflicting identities are rejected. Do not rewrite old evidence or
invent a hash to fit a new receipt; register new verified evidence instead.
