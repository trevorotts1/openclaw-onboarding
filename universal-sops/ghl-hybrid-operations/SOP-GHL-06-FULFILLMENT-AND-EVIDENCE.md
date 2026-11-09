# SOP-GHL-06 — Fulfillment and Evidence

**Cluster:** `universal-sops/ghl-hybrid-operations/` · **Owner:** Launch fulfillment (Skills 49/83/+44) with Courses and Community delivery owners · **Revision:** 3.0 (2026-11-08)

**Trigger:** A purchase, grant, enrollment, or launch action must become real access to a course,
group, or offer in GHL.

**Inputs:**
- The commerce product/price and the offer/grant definition (they are separate objects).
- The buyer/student identity, the target course product and/or group, and the access policy.
- The launch/task record (`cc_task_id`, `run_id`) that requested fulfillment.

**Required pointers:**
- Skill 49 launch schemas and callers; Skill 83 delivery/bridge/checks; Skill 44 fulfillment
  operations; Skill 82 consumer for thank-you delivery.
- `universal-sops/ghl-hybrid-operations/SOP-GHL-03-COURSE-PRODUCTION.md` and SOP-GHL-04.
- Command Center receipt/Kanban handoff (scoped task id only).

**Ordered steps:**
1. Distinguish commerce objects (product, price) from access objects (offer, grant, enrollment,
   Learning association). Never treat one as proof of the other.
2. Verify the buyer identity and the target tenant/location.
3. Create or update the grant/enrollment only through the supported operation; keep it idempotent on
   `(buyer, offer, location)`.
4. Attach the course/group access through the separate association object (SOP-GHL-04).
5. Run an access test as the learner: sign-in path, course visibility, group membership, lesson
   access. Record the evidence.
6. Hand the verified result to the launch/Kanban projection with the receipt id; a 200/201 or a
   scheduled item is not delivery.
7. Emit the delivery receipt and, for pending states, the exact `next_action` and owner.

**Allowed route changes:**
- Public product/price and course/Community operations first; private fallback only for a documented
  gap; browser operations only for a proven UI-only control.
- Never re-grant access because a response was lost; read the grant back first.

**Required output / receipt:** grant/enrollment refs, access-test evidence, delivery receipt, Kanban
handoff reference, pending-state wording that names the missing step.

**Approval boundary:** charging a payment, creating a new offer, changing prices, and granting access
outside the purchased scope require an explicit owner decision. Reconciling an existing grant does not.

**Failures:**
- Recoverable: grant already exists → idempotent success; learner access behind propagation → record
  `processing` with a recheck command and time.
- Terminal: wrong buyer identity, wrong tenant, unknown product/offer → stop; never invent a grant;
  a draft shell or a 201 is not proof of delivery.
- Board outage: persist a board-outbox event and keep working; never repeat the GHL mutation.

**Acceptance:** the buyer actually has the purchased course/group access, proven by a learner-side
check; commerce, offer and association objects stay distinct; pending states are named, not dressed as
success.
