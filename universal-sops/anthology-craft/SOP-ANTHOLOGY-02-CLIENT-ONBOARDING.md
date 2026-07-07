# SOP-ANTHOLOGY-02: ANTHOLOGY CLIENT ONBOARDING (per-producer setup and go-live)

**Cluster:** Anthology-Craft Rules (`universal-sops/anthology-craft/`)
**Master authority:** SPEC.md Section 13.1 (the ten provisioning steps) and Section 13.2 (the T1 to T9 intake battery); PRD Section 14 (per-client credential needs) and Section 11.1 (department seeding)
**Owning role:** Operator. Every step here runs on the producer's OWN box against the producer's OWN credentials. The producer is never messaged by this SOP; client-facing communication, when any exists, rides the standard Convert and Flow workflow, never the engine.
**Enforcement pointer (binding):** `59-anthology-engine/scripts/provision-anthology-client.sh`, the provisioning gate whose ten ordered steps must ALL pass (the first nonzero step STOPS setup with an operator surface), plus `59-anthology-engine/scripts/verify-webhook-t1-t9.sh`, the T1 to T9 intake verification battery that must be EXECUTED AND OBSERVED on the canary, never asserted. This is the provisioning gate plus T1 to T9 referenced throughout this SOP. No pass, no go-live.
**Stage:** Runs once per producer, after the AI Workforce Interview gate and as part of Anthology Engine enablement.

---

## 0. WHY THIS SOP EXISTS, AND THE GATES

Onboarding is where isolation, funding, and reachability are proven BEFORE any participant depends on them. A false "onboarded" produces a producer whose first real submission dies mid-publish or writes into the wrong tenant. Independent verification rule: onboarding is not done until the T1 to T9 table has actually been executed and observed, end to end, on that box, with results noted in the setup record.

All credentials are documented by LABEL and LOCATION only; verification is always SET or NOT SET plus a behavior probe. No value is ever printed, echoed, grepped into a report, or pasted into chat. All credentials are the NAMED CLIENT'S OWN accounts; no operator, shared, agency, or other-client credential ever substitutes. Config writes run as the node user, never root, because a root-owned config freezes the gateway.

## 1. PRECONDITIONS

1. The AI Workforce Interview gate is complete for this producer.
2. The Anthology department does not yet exist on this producer's Command Center; provisioning SEEDS it via Skill 32's `add-department.sh` (equivalently `POST /api/departments` with `create:true`) and never creates a duplicate. This is mandatory, not optional: Skill 53's books department was never seeded and its cards fall to the CEO catch-all, and this engine does not repeat that defect.
3. A per-producer slug or id is chosen, stable for the life of the producer, used everywhere as a placeholder. The repo is fleet-wide: no real client name, hostname, or identifier is ever written into any repo file.

## 2. THE TEN PROVISIONING STEPS (`provision-anthology-client.sh`, idempotent)

1. `caf_credential_gate.py` resolves every PRD Section 14 credential by label across all three client env stores, live process environment first, with the pairing proof and the anti-commingling fingerprint (SET or NOT SET only, never a value).
2. Create or verify the PRD Section 6 custom fields by EXACT key: eight deliverable Doc/PDF field pairs (16 keys) plus three control fields (anthology_active_id, anthology_stage, anthology_rewrite_count), 19 keys total, resolved through `anthology_registry.py provision-fields`. A missing field STOPS setup with an operator surface (AF-AE-FIELD-MISSING); a server fieldKey that does not byte-equal its intended key is AF-AE-FIELD-KEY-MISMATCH. Runtime never silently creates a field.
3. AUTO-PROVISION the standard Anthology pipeline in the producer's OWN Convert and Flow account through the producer's OWN private integration token (prefix `pit-`): a write-scoped token is REQUIRED, create-feasibility is PROBED first, and an absent pipeline/opportunities write scope STOPS setup (AF-AE-PIT-SCOPE), never a silent fallback. Binding to a pre-existing pipeline is an explicit override only.
4. Register the universal and per-stage forms with their hidden-field and re-stamp contract: contact_id, anthology_id, and stage travel hidden on every form; keying is always by contact_id, never email.
5. Provision the Drive path under the operator's EXISTING shared root (Root, then Producer, then Anthology, then Participant); NEVER create a new root or a new service account (`drive-tree-provision.py`).
6. Bootstrap the ledger base and the local mirror schema (`anthology_state.py bootstrap`).
7. Generate the webhook route and its secret, label `ANTHOLOGY_INTAKE_HOOK_SECRET`, plus the participant token secret, label `ANTHOLOGY_GATE_TOKEN_SECRET`; both are generated only when NOT already SET, written 0600, and NEVER printed.
8. Register EXACTLY the one daily tick in the cron inventory, no heartbeat, ever, proven by `guard-cron-inventory.py`.
9. Run `verify-webhook-t1-t9.sh` (see Section 3 below).
10. Fire one smoke test: balance endpoints only, total spend at or under one cent (`anthology-smoke-test.py run`).

Exit codes (house convention, propagated faithfully by every child collaborator): 0 the gate passed, including an idempotent no-op; 1 unexpected error; 2 validation or guard refusal (a missing credential label, a missing field, running as root, a hard prerequisite unmet); 3 a dependency unavailable or held (Convert and Flow, Drive, the gateway, or the Command Center unreachable, or a sibling collaborator not yet wired); 4 an enforced violation (credential commingling, a provider unreachable or unfunded at the smoke test); 5 a data or read-back mismatch (a field-key mismatch, a department read-back failure). A nonzero exit STOPS setup with an operator surface; there is no silent continue.

## 3. THE T1 TO T9 INTAKE VERIFICATION BATTERY (all nine executed and OBSERVED before go-live)

| # | Test | Expected |
|---|---|---|
| T1 | The intake route is registered on the gateway | route present and mapped to this producer's session key |
| T2 | Requests without the route secret | refused |
| T3 | A malformed payload | lands in the Exceptions queue with a typed reason, never a crash |
| T4 | A valid synthetic submission | acknowledges in under 2 seconds; creates the participant |
| T5 | Duplicate delivery of the same submission | a fingerprint no-op acknowledge, no second participant, no second run |
| T6 | A wrong-tenant payload (a different location_id) | lands in the Exceptions queue, reason tenant_mismatch |
| T7 | A stage-mismatched form submission | lands in the Exceptions queue, reason stage_mismatch |
| T8 | The T4 case through the REAL public URL, the named Cloudflare Tunnel | accepts end to end, same result as T4 |
| T9 | A gateway restart | preserves the route and the pending state; the ledger stays intact, no lost event |

T1 through T7 exercise the loopback path; T8 proves the tunnel and the edge, not just local wiring; T9 proves the route and any in-flight state survive a restart, exercised through the fleet MASTER-only kickstart-then-stop restart doctrine on a Mac box, never a bare `openclaw gateway restart` over SSH. `verify-webhook-t1-t9.sh` structurally self-validates before the canary is available (route-template.json, the webhook fixtures, expected.json) and reports the live battery as deferred, which is not a failure; the live battery is EXECUTED AND OBSERVED on the operator canary once the box is reachable, before this producer is marked onboarded.

## 4. SILENCE, SECRECY, ISOLATION

Zero client-facing messages from any onboarding step. Never print a secret value; report SET or NOT SET only. Never commingle producers; the named producer's own keys only. Config writes as the node user, never root. Operator-verbose: every provisioning run writes a ledger entry and posts a full step-by-step report to the operator, including the T1 to T9 results.

## 5. DEFINITION OF DONE FOR ONBOARDING

Onboarding is done only when: the credential gate passed (SET across all three env stores, pairing proof, anti-commingling fingerprint); the 19 custom fields exist and byte-equal their intended keys; the standard Anthology pipeline is auto-provisioned and bound into the registry; the Anthology department is seeded and read back; the Drive path is provisioned under the existing shared root; the ledger base and mirror bootstrap; the webhook route and both secrets are in place; exactly one daily tick exists in the cron inventory; T1 through T9 were executed and observed, including T8 through the real public URL and T9 through a gateway restart; and the smoke test passed at or under one cent. The setup record carries every LOCATION and every observed result. Anything less is not onboarded.
