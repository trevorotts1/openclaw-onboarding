<!-- Verbatim carry of the Purple Billboard client-system build document of the same name (spec version 2.1, policy dates 2026-10-24). Only one owner-identifier token was removed from DEC-20. This is the behavior contract for skill 84: where any other file in this skill differs, this one wins. Settled policy does not mean implemented behavior; runtime status is in ../wiring-map.md. -->

# Guided setup, runtime and upgrades
## Responsibilities
The skill must discover, prepare, set up permitted objects, run the approved process and recover bounded failures. It is not a manual for clients to wire integrations.
Bootstrap: DISCOVER → PLAN_DIFF → OWNER_ACTIONS → PROVISION_ALLOWED → VERIFY_CONFIG → START_SUPPORTED_RUNTIME → OWNER_PROOF → ACTIVATE_AUTHORIZED.
Persist object IDs, operation keys, revisions, prior values, step receipts and resume cursor. Reuse existing supported objects; do not duplicate workflows or overwrite customizations. Missing permission/API/entitlement produces an exact prepared owner action, not an invented endpoint.

## Synthetic installation walkthrough — never a live deployment
Fixture client is “Acorn Studio,” tenant fixture_acorn. All IDs, approvals, messages and receipts below are synthetic expectations. No GHL objects, phone messages, accounts, appointments or services are created. Expected receipt names start SYN-* and are not E-* product proof.
The client wants a useful consultation checklist and a relevant call offer. It initially has no master-guide collection.

| Stage | Inputs and expected output | Expected receipt / checks |
|---|---|---|
| S0 Business discovery | Existing voice/offer profile plus missing audience/capacity questions → approved acquisition brief, truthful claims and handoff owner | SYN-BRIEF, C-06 |
| S1 Asset inventory | One original checklist, no bonus collection → verify original and draft a useful second worksheet for review; do not advertise nonexistent guides | SYN-ASSETS, C-07/C-13 |
| S2 Existing-object discovery | Fixture location/Page/IG/calendar/phone bindings → current object map and capability exceptions | SYN-DISCOVERY, C-01/C-02/C-03/C-36 |
| S3 Plan and authorization | Desired routes, existing custom workflows and named setup scope → field-level diff, reused IDs and explicit owner sign-in/permission steps | SYN-PLAN, C-09/C-10/C-36 |
| S4 Original fulfillment route | Immutable original version plus accessible fixture resource → independent direct-delivery adapter, even if bonus access remains unresolved | SYN-ORIGINAL, C-13/C-F07 |
| S5 Bonus capability | Investigate supported member/grant/credential/phone-only return route → selected verified adapter or precise unresolved capability | SYN-BONUS-DECISION, C-14 |
| S6 Permitted provisioning | Authorized configuration only → idempotent workflow/field/knowledge/asset-route receipts; retry resumes failed operation key | SYN-CONFIG, C-15/C-19/C-36/C-37 |
| S7 Host service | Supported supervisor, persistent state and approved process paths → installed then running receipts, separately | SYN-HOST, C-38 |
| S8 Joined monthly review | 30 exact packs, real assets, CTA/keywords and conversation paths → approval manifest with allowed spares | SYN-APPROVAL, C-23/C-24 |
| S9 Owner proof | Named test contacts/channels/actions only → ordinary-reader event/reply/original/access/help trace | SYN-LIVE-PLAN only; C-48 remains DEFERRED_AUTH here |
| S10 Activation | Named client/host/channels/operator/cohort authorization → per-client activation receipt | SYN-ROLLOUT-PLAN only; C-49 remains DEFERRED_AUTH |

The included fixtures/client-acorn folder contains actual harmless synthetic resource text and staged inputs. They demonstrate asset/version shapes; they are not customer-approved production assets. If S5 is blocked, S4, helpful inbound behavior and other safe setup work can still be built. The complete advertised bonus-access product stays not ready.

## Synthetic run walkthrough
1. An approved scheduled post uses the public-placement envelope, with no dummy contact. Verify manifest/account/schedule; publish and record actual parent receipt before reveal comments. C-23/C-24/C-25.
2. A fixture personal reader sends the stable keyword. Page/IG comment readers instead need their independently supported opener and qualifying customer interaction. C-20/C-21/C-F08.
3. Map the trusted event to fixture_acorn's canonical person; serialize shared FB/IG/SMS sequence and dedupe. C-11/C-12.
4. Resolve the exact original item. Queue direct resource through the person gate. Accepted/sent is not falsely labeled delivered. C-13.
5. Offer actual extras after successful continuation criteria. If permission/grant succeeded but credential issue failed, resume credential issue only. No second grant or false “pass sent.” C-15/C-F11.
6. After a real pass is ready, collect/reuse mobile and send one logical SMS email ask. A reply on another channel does not create a second budget. C-16/C-17/C-F02/C-F06.
7. Answer the person's relevant need, recommend an appropriate real next step, verify a booking at commit or hand off with an accepted owner. C-27/C-28/C-29.
8. Attribute the request to the observed keyword; if exact post/ref is unknown, report unknown. A booking is not a sale. C-30/C-34.
9. Final/declined capture remains stopped when another giveaway arrives. Serve the new explicit resource request without restarting capture. C-18/C-F05.

## Mac and headless differences
Mac: verify the actual supported service, availability/sleep behavior, auth ingress, durable store and restart. A signed-in browser can only supply a specifically proved capability.
VPS/Docker: verify that host's supervisor, durable volumes, secrets boundary and restart. Do not assume the Mac browser or mount path exists. Remote engineering work requires its actual approved external/bind mount identity; otherwise storage-dependent work pauses.
This build's worktrees, scratch, project temporary files, test/build outputs and supported caches stay on the portable-drive root with explicit process environment. Future client-runtime data/temp storage is a separate named deployment contract; this package does not declare a server's internal /tmp compliant by assumption. Docker anonymous-volume fallback is prohibited where external persistence is required.
Engineering closure never stops the separately owned client scheduler.

## Synthetic upgrade and failure-resume walkthrough
Starting fixture: package A/schema1; config revision11; two reminders accepted; one SMS action unknown; old keyword points to original version1; active human handoff.
Upgrade plans A→B/schema2 with expected config11. The client independently fixes its calendar, producing revision12. Compare-and-swap fails: preserve revision12 and prepare a field-level forward repair. Do not roll back the client's fix.
Before retry, preserve contacts, consent, original links/content, entitlement, human fence, reminder count2 and unknown action. Resume from migration checkpoint; reconcile the unknown send before any new attempt. Code rollback never restores old contact facts or undoes sent effects. C-39/C-F12.
Disconnect/rebind/relevant adapter upgrade invalidates only affected readiness proof. Install/running/access/live states remain separate. C-40.

## Client prerequisites and scope
Discover actual plan entitlements, channels, sender/registration, email domain, model/host/storage, asset rights, calendar capacity and human support ownership. Record who pays and who repairs disconnections. Organic does not mean no operating cost.
Rollout authorization names clients, hosts, channels/accounts, provisioning actions, test recipients/messages, activation window, operator, support and rollback limits. Repository merge authority is not client deployment authority.
