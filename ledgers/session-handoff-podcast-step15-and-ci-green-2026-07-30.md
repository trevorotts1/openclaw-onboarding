# Session handoff — Skill 58 Step-15 publish docs + turning `main` green (2026-07-30)

Written so a session lost to a context/usage limit can be resumed without re-deriving anything.

**FRESHNESS CONTRACT.** Every SHA, tag, and check result below was verified live against `git` and
the GitHub API at the time of writing. `main` is a fast-moving merge train — it moved four times
during the work recorded here. **Re-verify liveness before acting on any claim in this file.** The
one-liner that reproduces the whole state:

```bash
cd <onboarding-repo> && git fetch origin --tags
git rev-parse --short origin/main && git show origin/main:version
gh api repos/<owner>/<repo>/commits/$(git rev-parse origin/main)/check-runs --paginate \
  -q '.check_runs[]|select(.conclusion=="failure")|.name' | sort -u
```

State at time of writing: `origin/main` = `a4153ef2`, version **v21.4.29**.

---

## 1. What started this

A client's assistant, provisioning the Podcast Production Engine (Skill 58), was told by the
skill's own shipped docs that the client needed her own n8n instance plus the operator's Podbean
OAuth application credentials, and escalated a blocker. **Both were false.**

Root cause: Skill 58 shipped **two contradictory answers** for what Step 15 (publish to Podbean)
uses as its transport.

- **The code was already correct.** `scripts/podbean_publish.sh` implements precedence
  **PROXY > BROKER > LOCAL**. Proxy mode posts the contract-v2 payload with the shared header token
  straight to the operator's n8n `/webhook/podbean-publish`, which performs the entire publish
  server-side and returns the permalink synchronously. Landed at tag `v20.0.67`.
- **The docs were stale** and still described the abandoned Podbean **credential broker** as the
  fleet default, instructing a manual workflow import that nobody needs.

The operator-side n8n was verified complete and healthy before any repo change was made: the
publish workflow is active and already speaks contract v2 (standing/identity gate, idempotency
ledger, media preflight), and a separate standing-check webhook is active on the same header
credential. A no-spend live probe of the standing gate returned `{"ok":true,"good_standing":true}`.
**No n8n change was needed or made.**

## 2. Shipped

| Tag | What |
|---|---|
| `v21.4.18` | Skill 58 docs corrected: die message, SKILL.md credentials section, `config/n8n/README.md` banner + provisioning recipe, removed the self-drifting pinned `versionId` |
| `v21.4.19` | `install.sh` — the provisioning path still called the retired broker "PREFERRED"; four text sites corrected |
| `v21.4.20` | CI: G3 regression + Task-Mode load step (22 role files) + stale department guides + a renamed constant a test still referenced |
| `v21.4.21` | sync_check + universal-sops manifest drift exposed by the above |
| `v21.4.23` / `v21.4.24` | Presentation autofail-gate coverage; **two of those gates were real no-ops, not merely untested** |
| `v21.4.25` | Skill 38 `INSTALL.md` self-contradicting counts |
| `v21.4.26` | Presentations doctrine residuals (Guard B: 107 → 0) |
| `v21.4.27` | Skill 38 script-count drift **plus the missing tripwire** that let it drift |
| `v21.4.28` | 104 dangling doctrine citations repointed |
| `v21.4.29` | `bump-version.sh` version-collision guard |

**Net effect on CI:** `main` went from **five failing checks to zero**.

### The Skill 58 correction, stated once so it cannot rot again

A client box needs exactly **five** values for Step 15. It never needs its own n8n, and never needs
a Podbean OAuth application credential:

```
PODBEAN_PUBLISH_WEBHOOK_URL   the operator's n8n publish webhook (not a secret)
PODBEAN_PUBLISH_TOKEN         shared webhook header token (NOT a Podbean credential)
PODBEAN_PODCAST_ID            the client's Podbean Channel ID (not a secret)
PODCAST_CLIENT_LAST_NAME      half of the roster identity key
PODCAST_CLIENT_EMAIL          half of the roster identity key
```

Operator-side injection vars consumed by `install.sh`: `OPENCLAW_PODBEAN_PUBLISH_URL`,
`OPENCLAW_PODBEAN_PUBLISH_TOKEN`, `OPENCLAW_PODCAST_CLIENT_LAST_NAME`,
`OPENCLAW_PODCAST_CLIENT_EMAIL` (+ optional `_FIRST_NAME`). The Channel ID is per-client and
collected at provisioning, not injected from operator env.

**Setting `PODBEAN_BROKER_*` is a trap.** It puts the box into broker mode, which requires a broker
workflow that is not deployed. The variables are `PODBEAN_PUBLISH_*`.

## 3. Findings that outlived their tickets

- **Two presentation autofail gates were genuine no-ops**, not merely untested — their enforcing
  constants were dead, so decks could ship with overflowing text and unmeasured type while QC
  reported green. Fixed, and every new probe was mutation-proven (break the gate, watch the probe
  go red, restore).
- **A worked "PASS" example in a reviewer-facing doc cited a hook count the live gate vetoes** — it
  was actively teaching reviewers to approve failing work.
- **A role file contradicted itself four lines apart** — "there is no count floor anymore, there is
  a ceiling of 4", immediately followed by an order to pad to 7.
- **The prompt character floor is 9,000** (`prompt_gate.py`, `build_deck.py`). Docs citing 1,500 or
  5,000 are stale. Correct the DOC up to the CODE, never the reverse.
- **`bump-version.sh` computed the next version from the working tree, not `origin/main`.** Two PRs
  cut from one base both bumped to the same number; git auto-merged the byte-identical edit with no
  conflict, and a tag ended up pointing at a commit that did not contain the work it claimed. This
  was proven, not theorised: `git merge-base --is-ancestor <fix> <tag>` returned false. Guarded in
  `v21.4.29` — which then hit the same collision on its own way in and re-bumped to prove it.

## 4. OPEN — needs an operator decision, cannot be fixed unilaterally

1. **A client's name is in this repository's public git history.** `HEAD` is clean and verified,
   but the introducing commits are ancestors of `main` and this repository is public. Remediation
   options all have real cost: rewrite history (breaks every open branch on an active merge train
   and forces the fleet to re-clone), make the repository private, or accept it. **Undecided.**
2. **CI cannot scan for client names, structurally and by design.** The gate is roster-dependent;
   a bare runner has no roster, and client identifiers are deliberately never provisioned into CI
   secrets. It emits `CANNOT VERIFY (structural, CI — report-only)` and does **not** fail the
   build. **A green CI run is not evidence that no client name was committed.** Closing this needs
   either a roster in CI secrets (puts client data in GitHub) or a committed deny-list (puts the
   very names being hidden into the repo). Both are bad; **undecided**.
   - **Mitigation already applied:** the repository's `core.hooksPath` was set to `/dev/null`,
     which silently disabled `.githooks/pre-commit` — the only automated per-name backstop that can
     work. It is now set to `.githooks` and verified running. That is why the same name got
     committed twice in one day by two different authors with zero warnings.

## 5. OPEN — known work, deliberately not done

- **17 doctrine citations could not be resolved** and were left rather than guessed: 13 point at a
  section that does not exist in a file currently mid-build with duplicated headings (authoring it
  is restructuring, not citation repair), and 4 are genuinely ambiguous. Nothing was mass-labelled
  "historical" to force a green check.
- **The client box referenced in section 1 has not been provisioned.** Its operator-side tunnel is
  down (`websocket: bad handshake` — stale or absent connector), so it is unreachable from the
  operator box. This does **not** block the fix: all five values and the no-spend standing-check
  verification run box-local and need no tunnel. The token value must be supplied by the operator
  out of band; it is a secret and appears nowhere in this repository.
- **The fleet roll is the operator's**, deliberately not performed here. Note the operator box is a
  first-class member of the roll, not an exception.

## 6. How to verify the Skill 58 fix end to end, no spend, no publish

POST to the operator's `/webhook/podcast-standing-check` with header
`X-Podcast-Publish-Token: <token>` and body `{client_last_name, client_email, podcast_id}`.
Expect `{"ok":true,"good_standing":true}`. This exercises auth, routing, and the roster gate
without publishing anything or spending anything.
