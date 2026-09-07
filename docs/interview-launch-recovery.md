# Fresh client interview launch and post-interview recovery

First-time onboarding requires the client/ZHC owner name and company name before resources are created. Collect both with `scripts/onboarding-identity.py` (see `Start Here.md`); reuse the saved intake and existing company IDs on retries. Never substitute the owner name for the company name.

Paired releases: onboarding v25.0.9 / Command Center v7.1.4. Skill 32 v13.1.5, Skill 37 v13.1.2 and Skill 05 v7.0.1.

## Expected order

1. Run the existing install entry point on the client's own machine. The launch helper atomically initializes missing pending state and stable company, tenant, installation and build identities. It records the actual operator invocation for the default standard-first preparation; existing recorded lane/operator choices remain authoritative. No answers or completion flags are invented.
2. Provision the client's service environment and registry. Resolve and export that installation's absolute `DATABASE_PATH`, run the real Command Center schema migrations successfully, verify the required tables, and only then bind the canonical company. A failed migration stops this stage before foundation or invitation readiness. Prepare the standard foundation using the canonical workforce engine. Each expected department must have company artifacts and an active same-company board workspace. A hash receipt protects the readiness claim; stored status alone cannot prove it.
3. Bring up the client's locked Command Center and its own Cloudflare origin. Provisioning stores a candidate origin; only an authenticated exact-host/identity readiness receipt makes it a verified interview origin. Ambiguous tunnel requests are reconciled using their stable request identity instead of blindly requesting another tunnel.
4. The sender verifies readiness, resolves the client's owner destination and requests a signed one-use enrollment ticket from CC. It uses supported OpenClaw `--message --json` delivery. The browser opens `/interview#enroll=...`, redeems the ticket and loads that client's interview. New tickets expire after 24 hours; the message reports the exact server-issued expiry, including when an older issuer still uses 15 minutes. A fresh invitation restores access to the same saved interview.
5. Every accepted Q/A persists under the client interview identity. Retrying an answer operation does not duplicate it. Restart/resume restores the saved interview; reference export includes that client's questions and answers. A valid same-client authenticated browser can reopen its saved interview even from a previously used link; the ticket cannot authenticate a second browser again. Another client's session cannot access the interview.
6. Completing Q/A requests the existing authenticated build handoff. An unavailable receiver stays pending. The standard-first diff personalizes the existing foundation, adds/archives approved departments and proceeds through persona/runtime registration and build checks. An interview completion flag alone is not evidence that those later steps finished.
7. Skill 37 builds the closeout documents and verifies delivery through the existing closeout gates. The interview Q/A remains separately saved and downloadable through the authenticated interview reference export. Notion requires the client's own token plus explicit client-bound parent. Root/page/section lookup stays within that verified hierarchy. Without those resources, documents remain staged locally and the missing step stays recoverable; no agency or foreign workspace is substituted.

## One supported recovery command

Update both paired releases, then run the Skill32 orchestrator **inside the client's
actual runtime**, using the same validated Command Center checkout:

```bash
bash "/absolute/client/openclaw-root/skills/32-command-center-setup/scripts/run-full-install.sh" \
  --resume --app-dir "/absolute/client/command-center"
```

Replace both example paths with this installation's existing paths. In a source
checkout, use `32-command-center-setup/scripts/run-full-install.sh` from that
checkout instead of the installed `skills` path. For a nonstandard root that is
not already selected by the existing runtime configuration, pin
`OPENCLAW_ROOT` to that same client root for the command. Preserve existing
workspace pins; do not point the command at another client's directory.

The same command supports a missing checkout, a clone that never finished setup,
an interrupted installation and a configured installation. It validates the
checkout, inspects state/database evidence and resumes the missing phases in
place. A bare clone does not count as an installed Command Center. Failure-only
metadata can resume identity initialization while retaining its diagnostics;
unknown identity or interview-bearing state cannot be silently replaced.

Do not reconstruct recovery by running migration, company binding, department
seeding, prebuild or invitation scripts individually with improvised exports.
The orchestrator loads the saved company UUID, tenant, installation, company root,
workspace, lane and service configuration together. It resolves the configured
absolute database path **before** every migration call, including update/resume.
A conflicting ambient database path is rejected before touching the database.
The binding helper must not fabricate a minimal schema to get past an error.

A UUID company ID is valid. Never convert it to a slug, delete interview state,
clear the tenant registry, skip standard-first prebuild or mark interview/build
completion to bypass a failed prerequisite. Company names and slugs are labels;
the existing canonical identity and saved answers survive retries.

The corrected environment writer preserves structured JSON and literal characters
through the actual Next and PM2 loaders. Let the orchestrator repair its owned
configuration and verify the running host binding; do not source an environment
file as shell code or hand-unescape it. It neither borrows credentials nor changes
client ownership to make a hostname pass.

Fresh migration-created Podcast, Anthology and Presentations placeholders are
bound only when they are unchanged and unused, under the explicit client ID.
Their row IDs and generated agent references are preserved, with a transactional
backup. Existing tasks/history, customization, runtime-bound agents or foreign
ownership prevent automatic adoption. Such a diagnostic requires investigation
of that specific queue; never bulk-update every `company_id='default'` row.
Convergence preserves an already repaired client binding rather than forcing it
back to `default`.

See [Mac and Linux VPS installation behavior](portable-onboarding-platforms.md)
for native Linux, existing `/data` roots, Docker hosts and containers, including
Hostinger and Contabo. The provider name does not identify the runtime topology.
On a Docker-backed client, recover **inside the selected existing container**;
do not start a second host installation or assume the user is always `node`.
Native VPS installations do not require Docker. Mac persona generation works
with stock Bash; tools that explicitly require modern Bash retain that prerequisite.

## Recovery and honest readiness

- Resume the same client state, company root and checkout. Do not create a new company ID or copy a different client's environment to repair a failure.
- A missing required resource is a specific recoverable blocker, not permission to mark launch/build/closeout complete.
- An uncertain Telegram result requires checking the stored receipt and actual provider delivery before resending. Force does not bypass an unknown delivery outcome.
- Never put bearer tokens, enrollment fragments or client credentials in diagnostic output.
- The launch receipt verifies local configuration and foundation evidence; `providerLiveness` remains `unverified`. Only a real client acceptance run can prove Cloudflare ingress, Telegram receipt, provider answers and external closeout delivery on that installation.

## Acceptance before calling a client live

On an isolated test client, verify install → public readiness → actual Telegram link → browser enrollment → two saved answers → close/reopen/resume → Q/A export → finish interview → received build handoff → approved department/persona changes on the same board → runtime activation → client-owned Notion documents and verified final delivery. Try a second client/session and confirm it cannot read or write the first client's interview. Keep identity and receipt evidence with access secrets redacted.

## Expired link or client request to resume

When the client tells their Telegram assistant **“resume my interview”** (or says the link expired), run the sender on that client's installation, from the installed Skill 23 directory:

```bash
bash scripts/send-interview-link.sh --renew
```

Keep the existing `OPENCLAW_ROOT` and workspace pins. The sender resolves those pins using the same platform contract as installation, verifies public readiness and company/tenant/installation/owner identity, then issues a fresh sign-in link through the acknowledged client gateway. `--renew` bypasses only the accepted-send cooldown and chooses resume wording; it does not bypass uncertain delivery or mismatched identities. `--resume` retains the normal cooldown. If delivery is uncertain, reconcile the recorded send rather than clearing its receipt or trying a direct Bot API fallback.

The invitation's one-use sign-in ticket lasts up to **24 hours**. Once signed in, the client can bookmark the stable **`https://<their-verified-host>/interview`** page. Newly created Command Center browser sessions last up to **30 days** in the paired resume release; old sessions and outer Cloudflare Access rules may require authentication sooner. The bookmark requires a valid login and does not itself grant access. If authentication has expired, ask the same client's Telegram assistant for a fresh invitation.

Saved questions, answers and the interview identity are not deleted when a ticket or login expires. Resume the same record; do not reset state, change UUIDs, run initial prebuild again, or use the workforce-build/Skill 37 closeout resume worker to fix an expired sign-in link. Confirm answer-save acknowledgement before telling a client their latest answer is saved. After completion, show the existing build/closeout status instead of restarting the interview.

Ordinary installer and cron replays do not repeatedly renew acknowledged invitations. A fresh invitation is sent in response to the client's request, not merely because an old ticket's deadline passed. It does not authorize answers, interview completion, or any new Option B choice.

## Noninteractive invitations and browser verification

The invitation sender resolves OpenClaw before minting a ticket: an explicit
absolute executable `OPENCLAW_BIN` pin takes precedence, followed by the selected
runtime's PATH, that user's npm/local bins, and standard native installation
bins. An invalid explicit pin is a precise pending result; it never switches to
another executable. The sender invokes the resolved absolute path and retains
this client's gateway/configuration environment. It does not source login
profiles or scan other users' installations.

If an operator's Playwright MCP shares a locked browser profile, launch that
operator test session with `--isolated` (a fresh profile) and restart the MCP
session so the option takes effect. This is operator test-tool configuration,
not a modification to the client's Command Center or personal browser profile.
Do not delete a client's browser data to clear a profile lock.

Use a separate test invitation for browser verification, not the one already
sent to the client. A ticket is single-use. Observe the page's own automatic
enrollment, save two answers, close/reopen and resume, and verify the reference
export. A successful manual POST from browser developer tools proves only that
the endpoint works; it does not prove that the page automatically redeems the
link or that the interview UI works without manual intervention.

## Empty closeout state and bounded installation checks

Resume/closeout verification must not create a build before client identity exists. The launcher recognizes only the exact historical empty pending-verification receipt (matching UUID, empty-input digest, unmet requirements and null ownership/artifact fields), preserves its build ID and initializes the actual client once. Any answers, identity or unknown fields retain the existing-state guard. Do not delete state or replace a UUID with a company name to get past verification.

Prebuild verifies active board rows within the selected company and normalizes both sides of the canonical department comparison, including `master-orchestrator` and `ceo`. It still requires the canonical workforce artifacts. Do not rewrite board slugs by hand to satisfy this check.

Each `openclaw skills info` process group is limited to 30 seconds and each skill QC process group to 180 seconds. Set `OBS_SKILLS_INFO_TIMEOUT_SECONDS` or `OBS_QC_TIMEOUT_SECONDS` to an integer from 1 through 3600 only when that installation needs a different finite limit. A timeout marks the skill `qc-failed` with `skills-info:timeout` or `qc-script:timeout`; checking other skills can continue, while final completion remains gated. The selected workspace contains private `.onboarding-qc-diagnostics/<phase>-*/stdout.log`, `stderr.log` and `status.json` receipts. Inspect them locally to distinguish a missing credential, failed provider response and deadline expiry; do not paste secrets into client chat.

## Stale CLI and Cloudflare Access recovery

The invitation sender checks the selected client's `openclaw.json` version metadata before using a CLI. It considers that root's `npm-global/bin/openclaw` and the current runtime user's native npm bins, avoiding a stale executable that shadows the current installation on a noninteractive PATH. `OPENCLAW_BIN` may explicitly pin an absolute current executable; an invalid or older pin stops before invitation issuance. Do not uninstall another CLI or restart/repoint a gateway to send an interview invitation.

For a public origin protected by Cloudflare Access, supply both `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET` in the selected client's bootstrap-pinned service environment or explicit sender environment. The service environment must match the stored company, tenant and installation. The sender passes this pair and `MC_API_TOKEN` as curl configuration through stdin for both readiness and ticket issuance. A partial pair is rejected before the request. Redirects to an Access sign-in page mean public authentication is required; they do not count as a readiness receipt. Never place credential values in command arguments, logs or client chat.

If Access permits email sign-in only and no service token is configured, an operator can use the Command Center's authenticated local recovery endpoint for a **pre-dispatch** public-readiness failure:

1. Read only this client's saved `launchBootstrap.serviceEnvPath` and the selected running app's service configuration. Verify the exact `PORT`, the canonical public hostname, and the same company, tenant and installation. Do not guess a port, scan other installations or source/dump the environment file. Check the shell sender's existing receipt first; a `sending` or `uncertain` receipt requires delivery reconciliation before switching send mechanisms.
2. Submit `POST http://127.0.0.1:<verified PORT>/api/interview/send-link` with JSON `{}`. Use `Host: <canonical public hostname>` and `Authorization: Bearer <selected MC_API_TOKEN>` through curl stdin configuration (`--config -`), never literal credentials in argv. For an explicit client-requested replacement of an acknowledged invitation, JSON `{"force":true}` bypasses the accepted-send cooldown only. Never use force for an uncertain attempt.
3. Accept success only when the response reports `ok: true`, `status: accepted`, and the expected company, tenant and installation, with the canonical authenticated `bookmark` and an `expiresAt` deadline. The endpoint resolves the saved owner and sends the private link itself; it does not return a ticket for manual forwarding. Pending/uncertain errors require reconciliation, not another send.

This explicit operator recovery proves the selected local app accepted and acknowledged delivery. It does **not** verify public Cloudflare availability or authorize bypassing the client's Access policy. The client must still pass Access and redeem the private invitation. Normal onboarding replay continues to use public authenticated readiness and does not silently switch to loopback.
