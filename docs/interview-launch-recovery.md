# Fresh client interview launch and post-interview recovery

Paired releases: onboarding v25.0.5 / Command Center v7.1.2. Skill 32 v13.1.3 and Skill 37 v13.1.1.

## Expected order

1. Run the existing install entry point on the client's own machine. The launch helper atomically initializes missing pending state and stable company, tenant, installation and build identities. It records the actual operator invocation for the default standard-first preparation; existing recorded lane/operator choices remain authoritative. No answers or completion flags are invented.
2. Provision the client's service environment and registry, bind the actual Command Center database company, and prepare the standard foundation using the canonical workforce engine. Each expected department must have company artifacts and an active same-company board workspace. A hash receipt protects the readiness claim; stored status alone cannot prove it.
3. Bring up the client's locked Command Center and its own Cloudflare origin. Provisioning stores a candidate origin; only an authenticated exact-host/identity readiness receipt makes it a verified interview origin. Ambiguous tunnel requests are reconciled using their stable request identity instead of blindly requesting another tunnel.
4. The sender verifies readiness, resolves the client's owner destination and requests a signed one-use enrollment ticket from CC. It uses supported OpenClaw `--message --json` delivery. The browser opens `/interview#enroll=...`, redeems the ticket and loads that client's interview. Tickets expire after 15 minutes; request a fresh invitation to renew access to the same saved interview.
5. Every accepted Q/A persists under the client interview identity. Retrying an answer operation does not duplicate it. Restart/resume restores the saved interview; reference export includes that client's questions and answers. Reusing an enrollment ticket or presenting another client's session cannot access it.
6. Completing Q/A requests the existing authenticated build handoff. An unavailable receiver stays pending. The standard-first diff personalizes the existing foundation, adds/archives approved departments and proceeds through persona/runtime registration and build checks. An interview completion flag alone is not evidence that those later steps finished.
7. Skill 37 builds the closeout documents and verifies delivery through the existing closeout gates. The interview Q/A remains separately saved and downloadable through the authenticated interview reference export. Notion requires the client's own token plus explicit client-bound parent. Root/page/section lookup stays within that verified hierarchy. Without those resources, documents remain staged locally and the missing step stays recoverable; no agency or foreign workspace is substituted.

## Recovery and honest readiness

- Resume the same client state, company root and checkout. Do not create a new company ID or copy a different client's environment to repair a failure.
- A missing required resource is a specific recoverable blocker, not permission to mark launch/build/closeout complete.
- An uncertain Telegram result requires checking the stored receipt and actual provider delivery before resending. Force does not bypass an unknown delivery outcome.
- Never put bearer tokens, enrollment fragments or client credentials in diagnostic output.
- The launch receipt verifies local configuration and foundation evidence; `providerLiveness` remains `unverified`. Only a real client acceptance run can prove Cloudflare ingress, Telegram receipt, provider answers and external closeout delivery on that installation.

## Acceptance before calling a client live

On an isolated test client, verify install → public readiness → actual Telegram link → browser enrollment → two saved answers → close/reopen/resume → Q/A export → finish interview → received build handoff → approved department/persona changes on the same board → runtime activation → client-owned Notion documents and verified final delivery. Try a second client/session and confirm it cannot read or write the first client's interview. Keep identity and receipt evidence with access secrets redacted.
