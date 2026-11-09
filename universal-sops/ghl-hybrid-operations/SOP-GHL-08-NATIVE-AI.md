# SOP-GHL-08 — Native AI

**Cluster:** `universal-sops/ghl-hybrid-operations/` · **Owner:** Skill 38 (behavior/responder ownership) + Skill 44 (provisioning) · **Revision:** 3.0 (2026-11-08)

**Trigger:** A request to set up a native GHL voice/conversation agent, an AI receptionist, or to
promote/activate an AI responder — including "set up a native GHL Voice AI receptionist".

**Inputs:** approved behavior plan (goals, channels, tone, escalation, quiet hours, opt-out),
provider choice, agent/action definitions, phone assignment decision, tenant/location, budget.

**Required pointers:** Skill 38 central doctrine and single-responder policy; Skill 44 native
Voice/Conversation adapters and commands; `SOP-GHL-09-KNOWLEDGE-LIFECYCLE.md` for KB attachment.

**Ordered steps:**
1. Record the provider choice and the behavior plan. Behavior is Skill 38's authority; provisioning is
   Skill 44's.
2. Declare responder ownership: which system owns replies for this channel (native agent, local agent,
   or human takeover). Two responders may never send for one thread.
3. Create the native agent/action. Keep creation separate from phone assignment and from activation.
4. Assign a phone number only as its own step; read back the assignment.
5. Attach the approved KB/agent references (SOP-GHL-09) when used.
6. Promote/activate the version; record the active version id and effective prompt/channel mapping.
7. Run a controlled, budgeted test: one conversation/call, tenant-bound, rollback-safe. Record the
   attempt, latency/status, and the rollback used.
8. Emit receipts: agent created, phone assigned, version activated, responder verified — separately.

**Allowed route changes:** Public native-AI operations first; private fallback only for a documented
gap; browser only for a UI-only control. Never activate a second responder to "cover" a silent first.

**Required output / receipt:** agent/action id, version id, phone assignment, channel mapping, effective
prompt reference, activation state, controlled-test evidence, receipts naming the rail.

**Approval boundary:** activation, phone assignment, outbound calling, spend, and any customer-facing
test require explicit owner approval. Draft agent creation does not.

**Failures:** Recoverable — activation still propagating → `processing` with recheck; phone busy/porting
→ record and queue. Terminal — unsupported channel, missing authorization, or a responder conflict →
stop; never invent a channel or a capability. Absent microphone/camera/number is a recorded activation
limitation, never a fake pass.

**Acceptance:** native configuration exists, the active responder/version is proven, phone assignment is
real, exactly one responder owns a thread, and a controlled test is recorded with rollback.
