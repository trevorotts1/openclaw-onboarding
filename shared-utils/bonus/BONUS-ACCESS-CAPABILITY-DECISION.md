# Bonus membership / access — capability decision (T-14)

**Task:** T-14 · `bonus-access-capability-decision` · PBB-112 · 2026-10-24
**Requirement:** R-13 — "Actual optional access grant, credential, SMS, return and recovery"
**Checks:** C-14 (focused artifact) · C-F07 (original gift while bonus unavailable)
**Decision:** **BLOCKED** for every automated route. Supported path is **assisted/operator**.
**Code:** `shared-utils/bonus/access_capability.py` · `shared-utils/bonus/tests/test_access_capability.py`

This is a capability decision, not an adapter. Nothing here calls a provider; nothing
here carries a URL, a verb or a path. `supported_route()` returns `api: None` on
purpose and the suite pins that `None`. The suite also scans the returned surface,
the module and this document for the API shapes it enumerates (scheme URL, verb plus
path spaced or glued, bare or identifier-prefixed path, a trailing path segment with no
segment after it, schemeless host plus path; dotted operation ids on the returned surface
only), so an edit that adds one of those shapes fails the suite. Two exemptions are closed
world. File provenance passes only when the token resolves to a real file in this tree; a
reviewed prose token passes only inside the exact sentence it was reviewed in. A new token,
or a reviewed token outside that sentence, fails until a human reviews it. It is a pattern
scan, not a proof: a fabrication in a shape the scan does not enumerate is not caught.

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
- In the **frozen v3 production spec** the public interface cannot create, update,
  publish or delete a workflow definition at all — but it is not read-only either.
  The registry carries three v3 workflow rows: a read, plus contact enrollment and
  unenrollment against an **existing** workflow, which is neither authoring nor a
  membership grant (`workflows.list`, `workflows.enroll`, `workflows.remove`,
  documented level `D`, in
  `44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py`).
  Definition authoring — create, update, publish, delete and definition read —
  appears only as v4 rows documented at **staging-doc** level (`S`), which the tenant
  receipt does not verify. Every automation build therefore routes through the
  internal engine, which requires the location's **Firebase refresh token**, not the
  PIT
  (`44-convert-and-flow-operator/automation-templates/launch-ghl-probe/GHL-CAPABILITY-NOTE.md`,
  which scopes its own ceiling to the v2 and v3 specs and admits the enrollment row
  is "enrollment only, not authoring").
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
| CAF CLI / internal engine | PIT for standard operations; **location Firebase refresh token** for workflow build writes | Only `membership_grant_offer` as a workflow action type; no workflow authoring in the frozen v3 production spec — the public workflow rows there are a read plus contact enrollment and unenrollment against an existing workflow |
| Managed browser | Gated singleton builder, one session, capture-locked anchors | Memberships area is UI; capture-pending anchors stop a live build |
| Community MCP | **RETIRED** — absence is the required state | Never a route and never a fallback |
| CUA | Approval-gated, bundled owner approval only | Not used |

**Tenant reality:** the installed capability receipt (`recorded_at: 2026-10-19`, tenant
`Mct54Bwi1KlNouGXQcDX`) contains six verified reads —
`locations.get`, `contacts.list`, `contacts.search`, `custom_fields.list`,
`pipelines.list`, `media.files.list`. **No membership, course, community or workflow
operation is tenant-verified.** An unverified route is reported incomplete, never as
done.

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
| Workflow authoring ceiling | `44-convert-and-flow-operator/.../GHL-CAPABILITY-NOTE.md` | The API-ceiling table already pinned it, scoped there to the v2 and v3 specs |

No guard is reimplemented: the fabricated-API scan is specific to this module's route
surface and source, and it is a test, not a second production guard. It catches every
known smuggle shape — scheme URL, verb plus path in any case, a bare operation path, a
schemeless host with a path, and a dotted operation id — and its own table pins both
that each of those is caught and that ordinary repo paths and prose are not.

---

## 7. Proof

Suite: `shared-utils/bonus/tests/test_access_capability.py` — **39 tests, OK**. The repair
round added 12 tests to the original 27; the test file changed by **231 insertions and 0
deletions**, so no existing assertion was weakened, changed or deleted.

### 7.1 Repair round — before and after, per defect

Independent QC reviewed the committed bytes at `2d5942e28` and returned FAIL on one scope
clause plus five attack findings. The scope clause is resolved by the ledger owner's
corrected wording: `38-conversational-ai-system/CHANGELOG.md` and `skill-version.txt` are
repository-mandated release bookkeeping, carried in the same commit by every prior task
commit in this repo. The five findings below were genuine defects and are repaired here.
Each proof test runs against the pre-change bytes and fails there.

| Defect | Before (bytes at `2d5942e28`) | After | Proof test (fails before) |
|---|---|---|---|
| **D1 — a broken reuse path looked like a capability block.** `membership_inventory_routes()` swallowed `ImportError` and returned `[]`. | With `ghl` blocked at `sys.meta_path`, the call returned `[]`. The pinning test passed both with `shared-utils/ghl` present and with it removed — a broken reuse path and a real block were indistinguishable. | `BonusCapabilityError`, failing closed. The pinning test now carries an instrument control: the same call path returns 2 routes for the `workflows` family, so the memberships zero is discriminating. | `test_a_broken_reuse_path_fails_closed_and_is_never_a_capability_block` |
| **D2 — the no-fabricated-API scan was evadable.** It pinned only "no scheme URL and no UPPER verb+path". | 2 of 6 smuggle shapes caught. Uncaught: a lowercase verb plus path, a bare quoted operation path, a schemeless host with a path, and a dotted operation id. | `_fabricated_api_hits` catches **6 of 6** and flags none of 10 legitimate strings (repo provenance paths, filenames, a shebang, an f-string path continuation, plain prose). | `test_the_scan_catches_every_known_smuggle_shape`, `test_the_scan_leaves_legitimate_text_alone` |
| **D3 — the coupling guard leaked the wrong exception.** | `assert_original_not_gated_by_bonus(None / [] / "plan" / 1)` raised `AttributeError: 'X' object has no attribute 'get'`. | `BonusCapabilityError: plan must be a dict, got X`; a well-formed plan still returns `True`. | `test_the_guard_refuses_a_malformed_plan_with_the_domain_error` |
| **D4 — a non-ready reason was silently coerced.** | `original_reason=None` accepted and stored the literal `"None"`; `original_reason=12345` stored `"12345"`. | Both refused with `BonusCapabilityError: original_reason must be a str`; a real reason still plans and is stored verbatim, padding trimmed. | `test_a_not_ready_original_reason_must_be_a_real_string` |
| **D5 — the workflow ceiling was overstated.** Section 2.2 stated the ceiling as an absolute: that the public interface cannot build or edit a workflow, and that its only workflow operation is a read. The module claim called workflows read-only. | Both contradicted the registry they cite as authority: three v3 workflow rows exist (a read plus contact enrollment and unenrollment against an existing workflow) and five authoring rows sit at staging-doc level. | Both scoped to the **frozen v3 production spec**, with the enrollment rows named as not authoring and the authoring rows named as staging-doc level, which the tenant receipt does not verify. The `grant` step stays `retired_rail_only` — scoping the wording does not soften the block. | `test_the_evidence_doc_does_not_overstate_the_workflow_ceiling`, `test_the_module_claim_is_scoped_the_same_way`, `test_the_scoped_ceiling_does_not_change_the_block` |

Mutation controls, each applied to one throwaway copy built with `git archive` (never inside
a worktree), one mutation at a time, and refused unless the target string occurs the expected
number of times:

| Mutation | Shape | Result |
|---|---|---|
| Every step promoted to `proved` | `state=UNPROVED,` / `state=RETIRED_RAIL_ONLY,` → `state=PROVED,` (5 sites) | **9 failures** |
| A fabricated membership URL returned as `api` | `"api": None,` → the vendor membership URL | **7 failures** |
| Original readiness coupled to the bonus lane | `"blocked_by_bonus": False,` → `bool(route["blocked_steps"])` | **6 errors** — the coupling guard firing |
| Restored control | — | **39 OK** |

Upstream suites re-run unchanged and green: `38-conversational-ai-system/scripts/qc-pb-contracts.sh`
**42 tests OK**, `qc-playbook-engine.sh` **44 tests OK**.

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
