# Bonus membership / access — capability decision (T-14)

**Task:** T-14 · `bonus-access-capability-decision` · PBB-112 · 2026-10-24
**Requirement:** R-13 — "Actual optional access grant, credential, SMS, return and recovery"
**Checks:** C-14 (focused artifact) · C-F07 (original gift while bonus unavailable)
**Decision:** **BLOCKED** for every automated route. Supported path is **assisted/operator**.
**Code:** `shared-utils/bonus/access_capability.py` · `shared-utils/bonus/tests/test_access_capability.py`

This is a capability decision, not an adapter. Nothing here calls a provider; nothing
here carries a URL, a verb or a path. `supported_route()` returns `api: None` on
purpose and the suite pins that absence, so a later edit cannot slip a fabricated
operation in.

---

## 1. What the capability actually needs

DEC-16 / R-13 define five separate questions. They are separate because each one can
fail alone, and a pass on one is not a pass on the next:

| Step | Question |
|---|---|
| `identity` | Can a member be identified **without an email address** (mobile-only)? |
| `grant` | Can the bonus offer be granted to that identity? |
| `credential` | Can the login credential be issued? |
| `return` | Can the member come back to the gated content **from an SMS message**? |
| `recovery` | Can a lost or expired credential be recovered? |

`identity` + `grant` + `credential` + `return` + `recovery` is the whole route. No
step is proved today.

---

## 2. The exact capability block

Every row below is frozen in the module (`EVIDENCE`) with the same provenance and
the same missing clause. States: `proved`, `unproved`, `retired_rail_only`, `ui_only`.
Only `proved` is routable.

### 2.1 `identity` — UNPROVED

No supported route establishes a member identity without an email address.

- The frozen public operation registry carries **no memberships or communities
  operation at all** (`44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py`,
  documentation fetch `2026-10-18`). The shared inventory answers this from its own
  data: `select_route(EXECUTE, resource="memberships")` returns `[]`
  (`shared-utils/ghl/capability_inventory.py`).
- The official MCP surface is a **dynamic catalog** (`list_locations`,
  `search_operations`, `describe_operation`, `execute_operation`) and this repository
  claims evidence levels 1–2 only; levels 3–4 (account grant, observed on the box) are
  explicitly **not held** (`shared-utils/ghl/capability_inventory.py`, `TRANSPORT_STATUS`).
- The Memberships area is a left-rail **UI** surface
  (`06-ghl-install-pages/references/form-click-map.md`; `spec §5`).

**Missing:** a documented memberships/communities operation in the frozen registry; a
recorded tenant success for it in the capability receipt; an observed member login that
completes with no email address.

### 2.2 `grant` — RETIRED_RAIL_ONLY

- `membership_grant_offer` and `membership_revoke_offer` exist **only as internal
  workflow action types** in Skill 44's engine
  (`44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/utils/workflow_builder.py`,
  `VERIFIED_ACTIONS`).
- The public interface cannot build or edit a workflow at all — its only workflow
  operation is the read-only list; every automation build routes through the internal
  engine, which requires the location's **Firebase refresh token**, not the PIT
  (`44-convert-and-flow-operator/automation-templates/launch-ghl-probe/GHL-CAPABILITY-NOTE.md`).
- The retired Tier-2 community MCP had the membership tool family (~15 courses /
  memberships tools) and its create/delete entries are documented as **possibly
  unverified shells** (`36-ghl-mcp-setup/ghl-mcp-setup-full.md`).

**Missing:** a verified supported-tier operation that grants a membership offer to an
identified member; a workflow-build route that does not require the internal Firebase
token.

### 2.3 `credential` — RETIRED_RAIL_ONLY

- Course creation appears only in the retired Tier-2 list; a live proof would be
  required before flipping any router to it
  (`06-ghl-install-pages/tools/SELECTORS-LIVE-course.md`).
- Community groups have **no delete on any known rail** — only Active↔Inactive — and
  the only identity tool is a slug validator
  (`06-ghl-install-pages/tools/SELECTORS-LIVE-community.md`).
- Membership/course surfaces are browser-executed through the gated managed builder,
  and capture-pending anchors make a live build stop and report rather than guess.

**Missing:** a live probe proving the course/credential create operations are real
endpoints; a supported tier that still exposes them (Tier 2 is retired, not a fallback).

### 2.4 `return` — UNPROVED

- The only verified SMS operation is a one-off message send
  (`shared-utils/ghl/capability_inventory.py`, `conversations.send_message`;
  `05-ghl-setup/INSTRUCTIONS.md`). Nothing resolves the SMS-bound person back to the
  same member record.
- The one-logical-SMS-ask contract (D-26: queued / dispatching / accepted /
  failed-not-sent / unknown / suppressed, one ask ID per sequence) is a **delivery**
  contract owned by T-15. It does not create a member-return route.

**Missing:** an operation that returns a member to gated content from an SMS identity;
receipt evidence that the SMS-bound person resolves to the same member record.

### 2.5 `recovery` — UNPROVED

- No credential-reset or recovery operation is documented anywhere in this repository
  (`44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py`).
- **An expired credential is not expired guides.** The module keeps the two questions
  on separate inputs: `resolve_member_state(credential_state, resource_authorized)`
  derives `resource_available` from `resource_authorized` alone, on every credential
  state (`valid`, `expired`, `absent`, `unknown`). The suite pins all eight
  combinations.

**Missing:** a documented credential recovery operation; a tenant observation of
recovery completing without an email address.

---

## 3. Current official route and tenant requirements

| Route | Requirement | Status for this family |
|---|---|---|
| Public REST | Location Private Integration Token + per-operation `Version` header | No membership operation in the frozen registry |
| Official MCP | OAuth only; a PIT sent to an MCP endpoint is **not** an equivalent auth path | Dynamic catalog; account grant and on-box observation not held |
| CAF CLI / internal engine | PIT for standard operations; **location Firebase refresh token** for workflow build writes | Only `membership_grant_offer` as a workflow action type; workflows read-only on the public API |
| Managed browser | Gated singleton builder, one session, capture-locked anchors | Memberships area is UI; capture-pending anchors stop a live build |
| Community MCP | **RETIRED** — absence is the required state | Never a route and never a fallback |
| CUA | Approval-gated, bundled owner approval only | Not used |

**Tenant reality:** the installed capability receipt (`recorded_at: 2026-10-19`, tenant
`Mct54Bwi1KlNouGXQcDX`) contains six verified reads —
`locations.get`, `contacts.list`, `contacts.search`, `custom_fields.list`,
`pipelines.list`, `media.files.list`. **No membership, course or community operation is
tenant-verified.** An unverified route is reported incomplete, never as done.

---

## 4. The supported path (chosen)

`supported_route()` returns:

- `available: false`, `route: "assisted_operator"`, `api: null`
- `reason_code: "BONUS_ACCESS_CAPABILITY_BLOCKED"`
- `blocked_steps`: all five
- `missing_evidence`: the exact clauses from §2
- `advertised_bonus_ready: false`

The assisted path is one manual step for the operator: create the offer and the
member's access in the GHL Memberships area, record the member's identifier, confirm
here. `request_bonus_access(unattended=False)` returns `status: "awaiting-operator"`,
`receipt: null`, `system_claimed_grant: false`. There is no code path that returns
`granted: true`.

`request_bonus_access(unattended=True)` is **refused** — `route: "refused"`,
`reason_code` above, the five blocked steps named in the reason, and an explicit
assisted offer. No silent downgrade, no fake success.

---

## 5. C-F07 — original gift while the bonus is unavailable

`plan_fulfillment(original_ready=..., original_reason=..., bonus_requested=...)` returns
two independent lanes:

```
original: {route: "direct_chat", ready: <from its own inputs>, blocked_by_bonus: false,
           depends_on_bonus: false}
bonus:    {available: false, advertised_ready: false, blocked_steps: [all five]}
advertised_bonus_ready: false
continuation: "original_only" | "original_and_bonus" | "original_repair"
```

Pinned facts:

1. `original_ready=True` with the bonus unavailable → the original stays ready and the
   continuation is `original_only`.
2. A non-ready original must name **its own** reason; the plan never attributes it to
   the bonus, and a blank reason is refused.
3. Replacing the bonus route with a hypothetical proved one leaves the `original` dict
   byte-identical — proof of no coupling, not a promise.
4. `assert_original_not_gated_by_bonus()` raises `BonusCouplingError` on a plan whose
   original reports a bonus blocker or a bonus dependency, or that has no original lane.

This satisfies D-28: direct original fulfillment must not depend on an unproved
optional vendor, while **advertised bonus readiness still requires the capability**.

---

## 6. Reuse, not a second copy

| Need | Reused upstream module | Why not new code |
|---|---|---|
| "Is there a membership route?" | `shared-utils/ghl/capability_inventory.py` (`select_route`, `OpClass`, `Transport`) | One honest route table in the repo; `membership_inventory_routes()` reads it live and the test asserts `[]` |
| Workflow action vocabulary | `44-convert-and-flow-operator/.../workflow_builder.py` (`VERIFIED_ACTIONS`) | The `membership_grant_offer` fact lives there already |
| Read-only workflow ceiling | `44-convert-and-flow-operator/.../GHL-CAPABILITY-NOTE.md` | The API-ceiling table already pinned it |

No guard is reimplemented: the no-URL / no-verb-path scan is specific to this module's
route surface, and it is a test, not a second production guard.

---

## 7. Proof

Suite: `shared-utils/bonus/tests/test_access_capability.py` — **27 tests, OK**.

Mutation controls (each mutation applied to a throwaway copy, one thing at a time):

| Mutation | Result |
|---|---|
| Every step promoted to `proved` | **8 failures** |
| A fabricated membership URL returned as `api` | **4 failures** |
| Original readiness coupled to the bonus lane | **2 failures** |
| Restored control | **27 OK** |

Upstream suites re-run unchanged: `38-conversational-ai-system/scripts/qc-pb-contracts.sh`
and `qc-playbook-engine.sh` (counts in the task report). No existing assertion was
weakened or deleted.

---

## 8. Not done / owned elsewhere

- **T-15** — the real bonus access adapter (identity/grant/credential/SMS/resource
  authorization, failed-step resume, return access, email-later same member). It is
  blocked by this decision and must not fabricate the route.
- **T-13** — original direct fulfillment mechanics. This module only asserts the
  independence, it does not deliver.
- **D-26 reply-trace probes** — the one-logical-SMS-ask receipt states are T-15's
  contract; the module states the dependency instead of duplicating the state machine.
- **No live probe was run** against any GHL tenant. That is deliberate: a tenant claim
  needs a real success recorded in the capability receipt, and this task's authority is
  documentation plus the repo's own frozen evidence.
- **Unblocking** requires, in order: a documented membership operation in the frozen
  registry, a recorded tenant success, then an observed mobile-only login/credential/
  return/recovery. Only then does `SUPPORTED` become reachable — the module reports
  `verdict: "BLOCKED"` until that is true in code.
