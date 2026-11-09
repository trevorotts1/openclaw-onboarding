# SOP-GHL-09 — Knowledge Lifecycle

**Cluster:** `universal-sops/ghl-hybrid-operations/` · **Owner:** Skill 38 (policy) + Skill 44 (KB transport) · **Revision:** 3.0 (2026-11-08)

**Trigger:** A request to build, update, attach, or test a knowledge base — including "make a
knowledge base from these approved support files".

**Inputs:** approved source files (with rights), KB type and limits, crawl URLs (when crawling),
training decision, target agent, retrieval test questions, privacy/unknown-answer policy.

**Required pointers:** Skill 44 KB adapter/commands and typed multipart transport; Skill 38 policy for
answer behavior; `SOP-GHL-08-NATIVE-AI.md` for agent attachment.

**Ordered steps:**
1. Validate sources: approved, non-secret, in-scope, within KB type limits. Reject unapproved sources.
2. Create the KB; record the KB id and type.
3. Upload each safe file through the central multipart transport (typed request, redacted receipt);
   or start a crawl with an explicit allowlist and depth.
4. Record the ingestion job id and its state. `processing` is not `trained`.
5. Train the KB; record the job id and the resulting state.
6. Attach the KB to the target agent as a separate association; read back the attachment.
7. Retrieve: run explicit test questions and record answers, citations, unknown-answer behavior, and
   conflicts. A KB id alone is not a passing retrieval test.
8. Update: re-ingest/retrain on a source change; record a new job and version rather than editing in
   place.

**Allowed route changes:** Public KB operations with central multipart first; private fallback only for
a documented gap; browser only for a UI-only control. Never upload through a second transport because
the first response was lost — reconcile the ingestion job first.

**Required output / receipt:** KB id, source refs + digests, ingestion/training job ids and states,
agent attachment ref, retrieval test results, redacted multipart receipts.

**Approval boundary:** uploading client content, crawling an external site, attaching a KB to a live
agent, and deleting sources require explicit owner approval. Draft KB creation does not.

**Failures:** Recoverable — unsupported file type/size → convert or split and retry; job still running →
`processing` with recheck; retrieval mismatch → re-index the specific source. Terminal — unapproved or
sensitive source → stop; type/limit violation → stop; unauthorized deletion request → refuse and
escalate. Never claim training from a `processing` job.

**Acceptance:** source/job/agent identities are recorded, retrieval is tested with real answers, and
privacy/unknown-answer behavior is enforced without unauthorized deletion.
