# Safety boundaries (binding)

These come from `spec/SPEC.md`, `spec/DATA-CONTRACTS.md`, `spec/DECISIONS.md` and the evidence states in `playbook/06-dm-door-and-agreed-flow.md` and `playbook/07-posting-routes-approvals-and-30-day-plan.md`. If any playbook text conflicts with a line here, this file wins.

## Nothing goes out except through the common gate

1. Every outbound action passes the common dispatch gate's correct variant: public publication, original gifts, ordinary replies, pass and email asks, reminders, retries. No exceptions, including the original gift and the final reminder. Module: `38-conversational-ai-system/tools/outbound_gate.py`. The gate is fresh on every dispatch and every retry (verdicts `ALLOW`, `WAIT_UNTIL`, `SUPPRESSED`, `QUARANTINED`, `RECONCILE_UNKNOWN`). A queued `ALLOW` is not an `ALLOW` at send time.
2. In a live conversation the only send door is `38-conversational-ai-system/tools/pb_send.py` (`admit`, then `reply`). Do not post to the Conversations API yourself. Its default transport only writes a local file; a live send needs `--transport ghl` plus the owner's written authorization (rule 5). Drafted is not sent; a message id is the proof.
3. A `SUPPRESSED`, `QUARANTINED` or `WAIT_UNTIL` result means do not send, and never work around it.
4. Public placements use the public-placement envelope with no contact. A reply to a particular reader is person-directed even when its transport is public. Never put a dummy contact on a public placement, and never put a canonical contact on one.

## No activation, no live effect, without the owner's written authorization

5. Installing, merging or running this skill is not authorization to touch an account. Activation requires a written authorization naming the client, host, channels and accounts, provisioning actions, test recipients and messages, the activation window, the operator, support and rollback limits (DEC-19, `spec/DEPLOYMENT.md`).
6. Do not create credentials. Do not change provider or model configuration. `bootstrap_engine.py` refuses both even if told to.
7. No customer message is sent to prove a test. Owner tests use named test contacts and named actions only.
8. Missing permission, API or entitlement is an exact prepared owner action, not an invented endpoint.
9. A client is never the canary for another client. Each client has separate accounts, contacts, senders, assets, knowledge, consent and state. Never merge contacts by display name or across tenants.

## Approval

10. Never post content the owner has not approved. One monthly approval covers 30 exact dated packs; a change invalidates only the changed placement (`shared-utils/manifest/monthly_manifest.py`).
11. Never post a pack whose Bonus comment still carries a placeholder where a link belongs.
12. An approval tap approves a kind of action from an account, once. It is not a standing rule about a person.
13. Verify on a fresh load. An action receipt alone is not proof that something posted.

## Personal profile publishing is unproved

14. A personal profile is assisted or unavailable, never unattended (`35-social-media-planner/config/profile-capabilities.json`). Prepare the exact placement and hand over one manual step; the owner's confirmation is the receipt. Never report an assisted placement as published by the system.
15. Unattended monthly operation on a personal profile has not been run. One reported browser test is not a month-long service. Ongoing replies on a personal profile's public thread are unproved. The Page Messenger bridge does not answer the profile's public thread.
16. Muse is currently document cleanup only (SPEC.md). Do not describe it as a posting service.

## Fulfillment and access are separate, truthful states

17. Deliver the actual original item directly in the eligible chat first. Optional membership, capture or a list signup never gates it.
18. Accepted or sent is not delivered without a receipt. A later failure pauses capture continuation and repairs the promise.
19. A 200 admission, a model completion, a send, an access grant and a sale are five different states. Report the one that happened.
20. An advertised bonus stays "not ready" while its capability is unresolved. Never say a pass was sent without the SMS receipt. A login token's expiry is not guide expiry.
21. Immutable promises: a keyword or link stays tied to the promise it was first used for and is never recycled. A retired mapping keeps a truthful tombstone; it never silently substitutes another item.

## Consent, refusal and reminders

22. Delivery consent is not marketing consent. Precedence: wrong binding or stale fence blocks everything; global stop; channel opt-out; sequence refusal; human ownership; field refusal. Unknown refusal scope is not permission.
23. The initial invitation is separate from at most three shared reminders. Replies, restarts and new giveaways never reset the budget. Active conversation pauses reminders. No catch-up burst, no false expiry, no false window extension.
24. The reminder timing (2h / 8h / 20h, 30-minute quiet interval) is PROPOSED and not activated. Adopt an exact policy version first (`ReminderStateMachine.adopt_policy`); until then no timed capture runs.
25. A comment alone is not a normal DM window. Do not drip to an ignored opener. Outbound and cross-channel messages do not refresh Facebook or Instagram eligibility.
26. A new explicit request is served without restarting rejected capture.

## Do not claim what is not built or not proven

27. Link attribution is NOT PROVEN. Never report a Bonus link click as attributed to a post. Report keyword attribution, multi-touch, or unknown; never invent exact post causality.
28. A booking is claimed only with a persisted receipt after rechecking live availability at commit. A booking is not a sale. Attendance and sales need authoritative or labeled owner evidence.
29. No poller and no ongoing comment monitor exists in this repository for Purple Billboard, and no dashboard code lives here: the Command Center is a separate repository (`trevorotts1/blackceo-command-center`, pinned in `cc-compat.json`). Its views exist only as listed in the pointer table in `SKILL.md` ("Command Center views"), with the gaps stated there: fulfillment pause, retry and handoff are a library with no screen yet, and bookings and outcomes show UNKNOWN until their producers exist. The account binding, call to action and keyword of a placement that the Command Center view cannot prove stay UNKNOWN, never approved. Do not describe a view, a poller or a monitor that is not in that table.
30. Do not create fictional collections, fictional token endpoints or fictional customer outcomes. Every statistic and research claim you repeat must come from the playbook's cited sources or be dropped.

## Where the playbook and the spec differ (the spec wins)

| Topic | Playbook text | Governing rule |
|---|---|---|
| Color | Purple, never black | The client's consistent brand color; the black exception is an open owner decision (DEC-17) |
| Who posts on a personal profile | A posting helper posts the pack each day | Unproved; assisted only (rules 14 and 15) |
| Reminder timing | 2h / 8h / 20h stated as the standard | Proposed, not activated (rule 24) |
| Comment count | "Seven comments" | Default six teaching comments plus the unnumbered Bonus; five promised means five plus the Bonus; never more than eight authored |
| Conversation build | Native Convert and Flow workflows catch comments and open the DM (Build Plan) | A design for review, not an installed capability. Skill 38 is the brain; Skill 44 is the transport; no native-only replacement is introduced silently |
| Bonus membership | Door 1 and door 2 presented as live | Door links are real only when the owner supplies them; membership-pass delivery is blocked until the capability decision clears |
| Cadence | One billboard a day | Scheduling is owned by Skills 35 and 57 only |

## Engineering rules that are not client rules

The build was run under separate engineering rules (external storage for build scratch, workflow and agent caps, batch merge). They are recorded in `spec/DECISIONS.md` for completeness (DEC-09 to DEC-14, DEC-20). They are not client runtime rules and this skill does not enforce them.
