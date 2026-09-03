# Changelog - ghl-mcp-setup (Skill 36)

All notable changes to this skill are documented here.

---

## [v1.4.4] - 2026-09-03 — contact write routing: generic add/save defaults to upsert

### Changed
- **CONTACT WRITE ROUTING policy in INSTRUCTIONS.md + CORE_UPDATES.md.** Generic
  add/save routes to Tier 0 `caf contacts upsert` first (explicit-new only to
  `create`, known-ID to `update` with non-tag fields); same rule binds Tier 1 MCP
  (`contacts_upsert-contact` vs `contacts_create-contact`) and Tier 3 raw API.
  (v1.4.2–v1.4.3: QC script maintenance bumps with no changelog entry.)

## [v1.4.1] - 2026-08-03 — Reconciled with the GHL API currency work

No behaviour change in this skill. Two parallel branches both touched skill 36 on
the same day and this entry records the merge, so the version history reads
straight instead of appearing to skip a release.

- The **v1.3.2** entry below now exists. `skill-version.txt` had been stamped
  `v1.3.2` for the `wire.sh` M2 verification change without a matching CHANGELOG
  entry; the API-currency branch supplied that heading and folded in the CI guard
  fix its own documentation required.
- The `qc-static.yml` vendor-URL carve-out described there is what keeps this
  skill able to document HighLevel's `/mcp/anthropic/v2` orchestrator URL without
  turning the "no banned model tokens" guard red. Verified against the live guard
  pattern after the merge: `36-ghl-mcp-setup/SKILL.md` and this CHANGELOG are both
  clean, and a real provider-prefixed model slug is still caught.

---

## [v1.4.0] - 2026-08-03 — The pin gets a repository we control, and the verdict gets teeth

### Why

Two things were true at once and neither was visible from the repo.

**The pin was coincidental, not durable.** Upstream force-pushes rewritten
history (it carries an automated `codex/daily-ghl-api-refresh` branch) and
publishes zero tags and zero releases. Verified: upstream `main`'s HEAD *was*
the pinned SHA. It resolved because it happened to be the branch tip. The moment
`main` moves past it the object is garbage-collected — existing boxes survive on
their local clone, but `git fetch origin <sha>` from a **fresh** clone fails and
**every new client provisioning breaks permanently** with `PIN_MISMATCH`.

**The vetting verdict was inert.** `GHL_MCP_PIN_VETTED_VERDICT` was sourced into
the environment by three scripts and read by none of them, nor by the QC gate,
nor by CI — whose only check was that the SHA is 40 hex characters. The rule that
was supposed to protect it ("any change to `GHL_MCP_VETTED_COMMIT` MUST reset the
fields to PENDING") was a comment addressed to a human. And the obvious repair is
worse than nothing: a CI check that reads `VERDICT == CLEAN` is defeated by
editing one word, and it *trains* whoever bumps the pin to type CLEAN, because
that is what makes the build go green.

### Added — an org-controlled mirror, which turned out to be a security fix too

`trevorotts1/ghl-community-mcp-mirror` carries the full upstream history.
`main` is **byte-identical** to upstream and is never patched — identical commit
SHAs are what let the tree be cross-referenced against upstream to detect
tampering, and a single local commit on `main` would destroy that. A repository
ruleset blocks force-push and deletion; both were attempted and refused rather
than assumed.

It is load-bearing for **security**, not only for pinning. Upstream hardcodes
`app.listen(port, '0.0.0.0')` in **both** HTTP entry points with no environment
variable to change it, serves `GET /tools` unauthenticated, and answers a
disallowed `Origin` with **500** instead of the **403** the MCP specification
requires — on a process holding a CRM private-integration token, where the
endpoint *is* the credential. Because the installer rebuilds `dist/` from the
pinned source, a `dist/`-level fix is destroyed by the next build. The patch has
to live in source, on a branch that survives rebuilds: `openclaw-patched` carries
`GHL_MCP_BIND_HOST` (default `127.0.0.1`), `Origin` validation returning 403, and
an opt-in bearer gate, with 19 assertions proving it and `PATCHES.md` indexing
every divergence. Upstream PR #9 is open so the divergence can retire.

Existing clones are migrated: `ensure_repo_at_pin` / `pin_mcp_checkout` repoint
`origin` before fetching, so a box provisioned against upstream moves to the
mirror on its next run instead of silently staying on a force-pushing source.

### Added — a vetting record that fails closed

`GHL_MCP_PIN_VETTED_DIGEST` is a sha256 over a labelled, domain-separated join of
`{commit, verdict, date, reviewer, deps-lockfile-sha256, repo URL}`. Change any
bound value by hand and the digest stops recomputing, and CI, the pre-push hook
and the box-side installer all refuse. **Forgetting to re-vet produces refusal.**

The repository URL is bound because a SHA names an *object*, never the host that
serves it: unbound, a mirror swap would leave the verdict, the SHA and the digest
all checking out while every executed byte changed. Operational knobs (profile,
port, log rotation) are deliberately **not** bound — forcing a re-vet to widen a
log file is how a gate gets switched off.

It is **not a signature and does not pretend to be**: unkeyed, public canonical
form, recomputable by anyone with write access — but only *deliberately*, by
running the tool. It closes the accident, not the attack.

- `scripts/ghl-mcp-vet-pin.sh` — the only thing that writes the record. Resolves
  the candidate against the mirror, prints the four review dimensions
  mechanically, requires an explicit `--verdict` with no default, and on seal
  rewrites the record **and both built-in fallback constants** so a split-brain
  pin cannot open.
- `scripts/ghl-mcp-check-pin-digest.sh` — the one implementation of the canonical
  form, shared by every consumer. It *parses* the pin file rather than sourcing
  it: a gate that executes the file it judges can be made to lie about its own
  result.
- `scripts/qc-assert-ghl-mcp-pin-gate.sh`, `scripts/qc-assert-ghl-mcp-pin-resolvers.py`,
  and CI job `ghl-mcp-pin-gate` (the workflow's `paths:` filters are gone — a
  path-filtered workflow can never be a required status check).
- `tests/unit/ghl-mcp-pin-digest.test.sh` — 26 mutation proofs.

**A legitimate pin bump is now two commands** — review, then seal — against the
previous three-file hand-edit plus a remembered rule. The enforcement mechanism
is also the ergonomics; one that costs more than what it replaces gets disabled.

### Fixed

- `ghl-mcp-setup-full.md` carried a **third** pin (`3dd9006a`) inside
  copy-pasteable `git clone` commands pointed at **upstream** — the same
  three-places-disagree failure `config/ghl-mcp-pin.env` was created to end,
  except this copy walked straight past the vetting gate while looking approved.
  A documented bypass is a larger hole than an undocumented one. Replaced with
  the executed entry point and a command that reads the live record rather than
  trusting the prose on the page.

- **`GHL_MCP_PIN_OVERRIDE` was still on the v1 tuple — a split canonical form on
  the primary fleet-roll path.** The pin *file* moved to `ghl-mcp-pin-v2`, which
  binds the repository URL. The *override* path did not: both launch scripts
  hand-reimplemented the six-field v1 tuple inline, so an override — by the
  installer's own comment, "the primary path a fleet roll would use to change a
  pin" — validated a commit without binding where it is fetched from. A mirror
  swap would have ridden in through the most-used path while every digest still
  checked out, which is the exact hole v2 was introduced to close.

  Both paths now bind `GHL_MCP_REPO_URL` and, more importantly, **stop
  reimplementing the algorithm at all**: the override is materialised as a
  pin-shaped record and handed to `scripts/ghl-mcp-pin-digest.sh`, the one
  canonical implementation. The second inline copy is *why* the drift happened
  and was survivable — deleting the copy is the durable fix, not re-syncing it.
  An override can change which commit is built, never where it is fetched from,
  and an override supplied on a box without the digest tool is now refused
  rather than trusted. Proven by `(J3)` (a digest bound to a different repo URL
  is refused) and `(J4)` (a stale v1 six-field digest is refused).

### Still open — needs a ruling, not a fix

`main` on the onboarding repo has no required status checks and no rulesets, so
this CI job is **loud, not blocking**. Making it blocking forces a pull request
for every merge; the exact command and the trade-offs are in the workflow header.
Until then the layer that actually protects a client machine is the box-side
refusal in the installer, which runs on paths CI never sees.

---

## [v1.3.2] - 2026-08-03 — Tier 1 now points at the v2 MCP orchestrator (+ the CI guard fix it required)

### Added
- **`SKILL.md` gained a "Which official MCP endpoint" section.** HighLevel publishes two
  official MCP endpoints and they are not equivalent. The per-client orchestrator
  `https://services.leadconnectorhq.com/mcp/anthropic/v2` is HighLevel's **recommended**
  path, is live today for Claude, exposes **6 unified meta-tools** (`search`, `fetch`,
  `search_operations`, `describe_operation`, `execute_operation`, `list_locations`) over
  "hundreds of operations across 40 domains", supports OAuth **or** PIT, and lets an agency
  connect once and work across many sub-accounts. Since every box in this fleet runs Claude,
  it is now the documented default for Tier 1.

### Changed
- Tier 2 (self-hosted community MCP) **stays in the chain** — it is a deliberate
  architecture decision. What changed is its *justification*: the capabilities it was
  documented as uniquely providing (products, invoices, billing, subscriptions, estimates,
  store, coupons, Voice AI, Phone System, Agent Studio) are now inside the v2 orchestrator's
  ~40 domains. Documented as redundancy and self-hosted control rather than the only door.
- **`GHL-LOOKUP-SOP.md` Version-header table corrected.** `payments` was listed under
  `2021-04-15`; `payments.json` declares `2021-07-28`. The table now states the real rule —
  `2021-07-28` is the default, seven named apps use `2021-04-15`, and `v3` exists.

### Accuracy notes recorded in the skill so they are not restated wrong
- HighLevel does **not** label `/mcp/` "legacy" or "deprecated". Its published wording is
  "the original endpoint"; it remains supported and is still the right choice for any
  non-Claude MCP client.
- HighLevel publishes **no fixed tool count** for the original endpoint, so "36 tools" is
  no longer stated as fact in the new section — verify live with `tools/list`.
- The dual-`Accept` requirement is documented for the original endpoint only; it is not
  assumed to transfer to the v2 orchestrator.

### Unchanged
- `GHL-LOOKUP-SOP.md`'s workflow guidance is untouched: the public API at `/workflows/` is
  GET-only in both the v2 and v3 specs. That wording was verified correct.

**Source:** `https://marketplace.gohighlevel.com/docs/other/mcp` (verified 2026-08-03).

### Fixed — CI
- **`qc-static.yml` "no banned model tokens" guard turned red on `main`** when this skill
  started documenting `services.leadconnectorhq.com/mcp/anthropic/v2`. The guard's
  vendor-slug alternative matched the `.../mcp/anthropic/v2` **URL path segment**, which is
  not a model slug. Fixed with the narrowest possible carve-out — a `(?<!/mcp/)` negative
  lookbehind anchored to that exact token — so a genuine provider-prefixed Claude slug
  anywhere else, **including elsewhere on the same line**, is still caught. Not a blanket
  `anthropic` allow,
  and the URL stays documented. New mutation proof both directions:
  `tests/unit/ghl-mcp-vendor-url-exemption.test.sh`, wired into `qc-static.yml` as its own
  step so the exemption cannot be silently widened.

---

## [v1.3.0] - 2026-08-03 — Installer hardening: pinned + profiled + crash-only + build-verified + liveness-probed (fleet outage 2026-08-01/02)

### Why
For two days every agent init on the fleet blocked the full 30s
`connectionTimeoutMs` against a GHL community MCP that was UP. The compiled
`dist/main.js` on the boxes predated upstream's `await server.connect(transport)`
— the socket accepted the connection and the MCP handshake was answered by
nobody. Nothing detected it: launchd/pm2 watch the PROCESS (alive), `lsof`
watches the SOCKET (open), and `GET /health` is served by express BEFORE the MCP
transport is wired, so a deaf server cheerfully returns
`{"status":"healthy","tools":N}`. Five installer defects produced and hid it.

### Fixed
- **D1 — stale-dist deafness.** `scripts/ghl-mcp-autostart.sh` used to
  `git pull --ff-only` and then build ONLY when `dist/main.js` was ABSENT, so a
  pull that advanced the source left the old compiled dist in place forever.
  Rebuild is now keyed to the pinned commit + a `.ghl-mcp-build.json` stamp + a
  literal artifact assertion (`dist/main.js` MUST contain `connect(transport)`).
- **D2 — 858 tools in every init.** The server's default `GHL_TOOL_PROFILE` is
  `full` (`src/tool-registry.ts:509`). `GHL_TOOL_PROFILE` is now set explicitly
  in EVERY launch surface (launchd plist, pm2 ecosystem, systemd unit, the
  server `.env`, the fallback supervisor loop), defaulting to `curated`
  (43 tools measured live). Additionally the autostart no longer REGISTERS
  `ghl-community-mcp` in `mcp.servers` — it had been re-registering the server
  seconds after `wire.sh` migration M2 removed it, contradicting the skill's own
  on-demand-curl doctrine and `qc-ghl-mcp-setup.sh` Section D, and putting the
  whole tool catalogue back into every session's init.
- **D3 — latent 10s crash loop.** `main.js` calls `process.exit(1)` when GHL
  rejects the PIT at boot, so any unconditional restart policy turns a rotated
  token into an endless relaunch. A generated `.ghl-mcp-launch.sh` wrapper now
  does a bounded credential preflight and exits CLEANLY (0) on a 401/403;
  restart policy is crash-only everywhere (launchd `KeepAlive` dict with
  `SuccessfulExit=false` + `Crashed=true`, pm2 `stop_exit_codes:[0]`, systemd
  `Restart=on-failure` + `StartLimitBurst`, and the fallback loop breaks on 0).
  `ThrottleInterval` raised 10 → **300**, matching the canonical crash-only
  plist shape already verified on a fleet box.
- **D4 — build crash from orphaned `node_modules` in `src/`.** Upstream's
  `scripts/build-server.mjs` `rmSync(dist)` FIRST and then transpiles every `.ts`
  found by walking `src/` recursively, so a `node_modules` tree that ever landed
  under `src/` (the operator box had `src/ui/react-app/node_modules`) fails the
  build AFTER dist was deleted. Builds now run against a `git archive` of the
  pinned commit in a temp dir and swap into `dist/` only after the artifact
  verifies; the previous dist is kept as `dist.bak-prev`. Any orphaned
  `src/**/node_modules` in the working tree is quarantined.
- **D5 — no liveness proof.** New `scripts/ghl-mcp-probe.sh` POSTs a real
  JSON-RPC `initialize` to `/mcp` and requires a `serverInfo` response within N
  seconds (exit 3 = DEAF). It runs post-install and every 15 minutes
  (`com.clawd.ghl-mcp-probe` on Mac, `*/15` cron on VPS), self-heals once, and
  reports through the repo's existing signed Command Center helper — operator
  visibility only, never a client channel.

### Added
- **Log rotation — the sixth gap.** Nothing in the fleet had ever rotated this
  server's logs: `~/Library/Logs/ghl-mcp/stderr.log` was 5.4 MB on the operator
  box and 2.2 MB on a second fleet box, both growing since May. The generated
  `.ghl-mcp-launch.sh` now copytruncates the MCP logs at every (re)start and
  `ghl-mcp-probe.sh` repeats it every 15 minutes, so a process that stays up for
  months is covered too. Rotation is copytruncate (copy, then truncate IN PLACE)
  because launchd/pm2 hold an open fd — renaming would leave the server writing
  to an orphaned inode and the visible log frozen. Best-effort platform rotation
  is layered on top when it needs no interactive sudo: `newsyslog.d` on Mac,
  `pm2-logrotate` + `/etc/logrotate.d/ghl-mcp` on VPS, plus the documented
  Docker `json-file` `max-size`/`max-file` cap. Defaults: 10 MB, keep 3.
- `config/ghl-mcp-pin.env` — ONE source of truth for the vetted commit, the tool
  profile, the port, the probe timeout and the log-rotation caps. The pin must be a FULL 40-char SHA;
  the installer refuses to build or start otherwise. It carries the
  `GHL_MCP_PIN_VETTED_*` provenance fields that gate a fleet roll.
- `scripts/ghl-mcp-probe.sh`, `tests/unit/ghl-mcp-probe.test.sh` (six cases
  against stub servers, including the exact deaf-but-healthy signature).

### Changed
- `INSTALL.md` §5.2/§5.3/§5.5/§5.6, Action 6 and "Done When" now document the
  pinned archive build, the tool profile, crash-only supervision and the
  JSON-RPC liveness test. The old "`/tools` returns >= 500" expectation is
  replaced by a profile-aware band — a correctly configured `curated` box serves
  ~43 tools, and the old check would have flagged that as broken while a
  mis-set `full` box passed.
- `qc-ghl-mcp-setup.sh` — Section 0 gains offline regression locks (pin file
  shape, no `git pull`, plist profile, crash-only KeepAlive, artifact
  assertion, probe present); Section D gains the JSON-RPC liveness assert, the
  profile-band assert and a crash-only plist assert. The SK1-69 lock now tracks
  `GHL_MCP_VETTED_COMMIT`.

### Supply-chain vetting gate: CLOSED, verdict CLEAN
The pinned commit `bfc2bbe` was security-vetted on 2026-08-03 and recorded
`GHL_MCP_PIN_VETTED_VERDICT="CLEAN"` in `config/ghl-mcp-pin.env`: credential
layer byte-identical to the previously trusted tree, no new outbound hosts, all
245 generated endpoints verified to build relative paths against the configured
API base, dependency graph unchanged. The gate stays a gate for the next pin —
changing `GHL_MCP_VETTED_COMMIT` must reset the `GHL_MCP_PIN_VETTED_*` fields to
`PENDING` until the new commit is re-vetted.

### Risk
Low-to-moderate and bounded. The rebuild is triggered on the first run after
merge for every box whose build stamp does not match the pin; it happens in a
temp dir, and a failed build leaves the running `dist/` untouched. Boxes with a
bad PIT will now deliberately NOT run the server (instead of crash-looping) and
say so in the STATUS line.

---

## [v1.2.15] - 2026-07-12 — P3-08 QC-fix: RULE 6 Tier-4 no longer routes to a missing file — the gated builder is now IMPLEMENTED

### Changed
- **RULE 6 BUILD-path implementation status corrected.** The Tier-4 cell routes to `06-ghl-install-pages/tools/ghl_workflow_builder.py`, which now EXISTS as a built, unit-tested harness (drives the Automations UI through the `browser_manager.sh` singleton gateway; refuses with `MissingGateError` rather than freehand-navigate). Removed the "until then, Skill 41 Layer 0 is the fallback" hedge that implied the designated path was unbuilt. The Automations step selectors ship `status: runtime` (role/name find hints resolved against the live DOM, per Skill 6's no-invented-CSS law); the live-captured selectors in `SELECTORS-LIVE-automations.md` are the ordinary runtime-gate hardening follow-on. Runnable proof cited: `--selftest` + `tests/test_ghl_workflow_builder.py`.

---

## [v1.2.14] - 2026-07-11 — P3-08: RULE 6 BUILD-path Tier-4 workflow-build routes through Skill 6's GATED managed builder (not bare agent-browser); token-circularity encoded

### Changed
- **RULE 6 BUILD-path table (`GHL-LOOKUP-SOP.md`).** Tier-4 workflow BUILD no longer routes to bare "agent-browser → Playwright at app.gohighlevel.com" freehand (which violates Skill 6's no-invented-CSS law). It now routes to Skill 6's GATED, MANAGED Automations builder (`06-ghl-install-pages/tools/ghl_workflow_builder.py` via the `browser_manager.sh` singleton gateway, selectors from `tools/gates.json` / `SELECTORS-LIVE-automations.md`).
- **Token-circularity routing encoded in RULE 6.** Tier 4 helps ONLY when the Firebase token is unread/misconfigured (the browser session is seeded from the same token). A genuinely dead/revoked/expired token routes to `ghl_auth.py` Tier-2 email-2FA self-heal, NOT Tier 4. The decision table and summary block reflect this. Cross-references `44-convert-and-flow-operator/SKILL.md`.

---

## [v1.2.11] - 2026-07-05 — Version drift: wire.sh / qc script read the live version from skill-version.txt (FIX-XC-13a)

### Fixed (FIX-XC-13a — doc/code version drift)
- `wire.sh` reported a stale hardcoded `SKILL_VERSION="v1.1.0"` in its final `STATUS:` line while the
  skill had moved on to v1.2.10. It now reads the live version from the sibling `skill-version.txt`
  at runtime (mirroring `25-video-creator/wire.sh`) so the reported version can never drift again.
- The two `wire.sh` migration markers (`M1` soul-relocation, `M2` tier2-deregister) are now keyed to a
  dedicated **frozen** `MIGRATION_TAG="v1.1.0"` constant — decoupled from the live version. These
  markers are one-time idempotency keys already written into `AGENTS.md` on migrated boxes; tying them
  to the live version would have made every completed migration look un-applied and re-run on each
  bump. Idempotency across version bumps is now explicit and preserved.
- `qc-ghl-mcp-setup.sh` no longer hardcodes `v1.0.0` in its header comment and result banner — it reads
  the live version from `skill-version.txt` and prints it in the `Final QC (<version>)` banner.

---

## [v1.2.10] - 2026-07-05 — Command Center emit helper (fail-soft) + Tier-0 presence-check path fix

### Added (FIX-S36-01)
- `scripts/cc-task.sh` — a graceful-degrading Command Center Kanban helper (modeled byte-for-byte
  on Skill 38's `scripts/cc-task.sh`) that IMPLEMENTS the previously doc-only "emit" moments in
  INSTRUCTIONS.md. `start` creates-or-reuses the Skill-36 install card and moves it to
  `in_progress`; `review` moves it to `review` on QC pass. It never self-grades review→done (the
  independent CC auto-scorer is the only authority) and never fails the caller — with no
  `MC_API_TOKEN` / unreachable board it prints one operator-only stderr note and exits 0.
- Wired: `INSTALL.md` Autonomous Setup Execution (new Pre-Action 0.5) invokes
  `cc-task.sh start … || true`; the `qc-ghl-mcp-setup.sh` PASS branch invokes
  `cc-task.sh review || true`. INSTRUCTIONS.md's "Command Center hooks" section now names the
  helper as the implementing mechanism (config: `MC_API_TOKEN`, `MISSION_CONTROL_URL`, optional
  `MC_SKILL36_AGENT_ID` / `MC_SKILL36_SOP_ID`).

### Fixed (FIX-S36-02 — qc-ghl-mcp-setup.sh)
- Section H Tier-0 presence check no longer looks in a **sibling of** master-files
  (`$(dirname "$MASTER_FILES_DIR")/44-…`), which never matched → the Tier-0 `caf` asserts
  silently downgraded to warn-only on every real box. Now checks
  `$MASTER_FILES_DIR/44-convert-and-flow-operator` **OR** `$SKILLS_DIR_DEFAULT/44-convert-and-flow-operator`
  **OR** `~/.openclaw/tools/convert-and-flow-cli`, so an installed Skill 44 is actually detected and
  the `caf` PATH / `caf doctor` checks assert (not warn) as intended.

---

## [v1.2.9] - 2026-07-05 — fix: secret-printing greps → existence-only (FIX-XC-07); model prescription → cheapest non-metered on-box (FIX-XC-09g)

### Security (FIX-XC-07 — no secret VALUES in transcripts/logs)
- `INSTALL.md` Pre-Action 2 credential hunt: every credential check is now EXISTENCE-ONLY.
  The canonical/legacy secrets-file scans became per-key `grep -qE '^(export )?KEY=' && echo "KEY=SET"`
  loops; the live-env and home-dotfile scans strip the value with `cut -d= -f1` BEFORE grep (key NAMES
  only); the repo/master-files scans use `grep -rilE` (matching FILE names only); the config env.vars
  Python prints `{name}=SET` instead of a truncated value.
- `ghl-mcp-setup-full.md` Section 1 discovery block: same treatment — per-key existence loop, `cut`-first
  name-only live/dotfile scans, `grep -rilE` file-name-only repo/master-files scans, and a names-only
  config Python block. No check prints a secret value anymore.

### Changed (FIX-XC-09g — no hardcoded model prescription)
- `SKILL.md` "Critical Things to Know" item 10 and `INSTRUCTIONS.md` anti-pattern: replaced the hardcoded
  `deepseek-v4-flash (direct)` lookup-inference prescription with "the cheapest non-metered model
  configured on THIS box" + a provider preflight (inspect the client's configured model list and pick the
  lowest-cost free/local model they genuinely have — never hardcode a specific model id, since provisioned
  providers differ per box).

### Notes
- Repo-level: a new deterministic shipped gate `scripts/qc-assert-no-secret-printing-grep.sh`
  (wired into `qc-static.yml`) fails any secret-pattern grep in the 36/38 SOPs that lacks `-q`/`-l`/`-L`.

## [v1.2.8] - 2026-07-05 — docs: Command Center card moves to review, never done (board review-skip root fix)

### Changed (FIX-XC-01b — Command Center card moves to review, never done)
- `INSTRUCTIONS.md` "Command Center hooks" — the **Install complete** hook now moves the card to
  **review** (never straight to `done`), with the QC result as the note ("certified — awaiting QC
  promotion; …"). A producer never self-promotes to `done`: the independent auto-scorer is the ONLY
  authority that moves a card `review -> done`. Prose carrier for the shared `mc_board` review-skip
  root fix (FIX-XC-01b); aligns Skill 36 with Skill 6's `cc_board`, Skill 41's `cc_move_task`, and the
  Skill 32 move-task Done-Gate.

## [v1.2.7] - 2026-07-01 — docs: GHL PIT alias cross-ref + canonicalize-once guidance

### Changed
- `SKILL.md` gains the GHL PIT-aliases banner (cross-ref to `TERMINOLOGY.md`'s 11-alias canonical
  set) and an expanded "Aliases" section lead-in stating the GHL = Convert & Flow = Go High Level
  platform identity.
- Item 5 under "Critical Things to Know" rewritten: Tier 1 now explicitly sends `Authorization:
  Bearer $GOHIGHLEVEL_API_KEY`; Tier 2's `GHL_API_KEY` env var is documented as one of the 10
  aliases the unified resolver normalizes to `$GOHIGHLEVEL_API_KEY` — with a "canonicalize once at
  session start, never re-resolve mid-session" rule that points at skill 29's 11-alias resolver.

---

## [v1.2.6] - 2026-06-30 — Tier 2 fork pinned to a verified commit SHA; QC script bug-fixes; stale full-doc/QC.md reconciled; runtime missing-cred grace; disclosure scoped operator-only; Command Center hooks

### Fixed (qc-ghl-mcp-setup.sh)
- **BUG-1:** `$URL` was used by the Tier 2 `/tools` assert one line BEFORE its own assignment → `URL: unbound variable` under `set -u` → spurious Section D FAIL every run. URL is now resolved at the top of Section D, before any use.
- **BUG-2:** the URL capture was `URL=$(command -v openclaw && openclaw config get ...)`, which prepended the `openclaw` binary path onto the URL → all Tier 2 probes hit a broken URL → spurious FAIL. `openclaw` presence is now guarded by a separate `command -v` test.
- **BUG-3 / D5-ii:** the VPS service check was `systemctl is-active ghl-mcp` only, which FAILS on a Hostinger Docker VPS (no systemd) even when pm2 correctly runs the server. Now checks `pm2 jlist | grep ghl-community-mcp` first, systemd as fallback.
- Tool-count asserts are now range-based: Tier 1 `>= 36` (was exact `= 36`), Tier 2 `>= 500` — so a single GHL tool add/remove no longer trips QC.

### Changed (pin the Tier 2 community fork — reproducibility / drift protection)
- `INSTALL.md` §5.2 and `ghl-mcp-setup-full.md` §6.2 now clone the BusyBee3333 fork and `git checkout` a **pinned commit** (`GHL_MCP_PIN_SHA=3dd9006ac5242762612e6d22b9a51a0a17aeca79`, 2026-05-15) instead of tracking `main`. That commit is the state this skill was verified against (`package.json main=dist/main.js`, `src/main.ts:55` PORT-before-MCP_SERVER_PORT precedence, `GET /health`+`GET /tools`+`POST /execute`). `main` HEAD (2026-06-11+) adds `mcp-apps` / an "easy setup" flow / a curated tool-profile that changes the default `/tools` surface; a re-run now re-pins instead of drifting. Bumping the pin requires re-running the QC script.
- Verified `ghl_create_workflow` / `ghl_update_workflow_actions` DO exist in the fork (`src/tools/workflow-builder-tools.ts` + `workflow-builder-client.ts`) but wrap an undocumented internal endpoint and remain unverified/likely non-functional — hardened the Tier 2 Workflows row (INSTRUCTIONS.md) and GHL-LOOKUP-SOP.md RULE 6 so they are never mistaken for a build path (build stays Tier 0 / Skill 44 Build API).

### Fixed (reconcile the stale long-form reference to the post-v1.1.0 canonical model)
- `ghl-mcp-setup-full.md`: §6.7 no longer instructs `openclaw mcp set ghl-community-mcp` — Tier 2 is documented as ON-DEMAND curl (not registered in `mcp.servers`), matching INSTALL.md §5.7, wire.sh M2, and qc.sh. §8.1 flipped to "SOUL.md — NO UPDATE NEEDED" (the Tier Escalation Protocol lives in AGENTS.md); §8.2 tier order gains Tier 0, marks Tier 2 on-demand, and Tier 4 = agent-browser-first; §8.4 MEMORY.md, the master checklist, and §11.A QC items flipped off the "Tier 2 registered" / "add to SOUL.md" / exact-count claims.
- `QC.md`: file manifest corrected to the real 14 package files (was "10"); "ghl-community-mcp registered" → "NOT registered (on-demand)"; "SOUL.md contains the protocol" → "AGENTS.md contains it; SOUL.md unchanged"; platform detection and VPS supervisor descriptions corrected (uname; pm2-first).
- `ghl-mcp-setup-full.md` §6.5 launchd plist + §6.6 systemd unit now pin BOTH `PORT` and `MCP_SERVER_PORT` (the supervision fix already in INSTALL.md); §6.6 notes pm2 is the canonical VPS supervisor.

### Fixed (D5-i — quoted-tilde platform detection in the full doc)
- Replaced `if [ -d "~/.openclaw" ]` (tilde does not expand inside quotes → always "desktop") with `uname -s` detection at all four sites, and switched the broken quoted-`"~/..."` path assignments to `$HOME/...`. Removed two dead quoted-tilde entries from the master-files locator ROOTS array.

### Added (runtime grace + silence + Command Center)
- **Runtime missing-credential grace** (GHL-LOOKUP-SOP.md RULE 5 + CORE_UPDATES.md token-routing): an empty `GOHIGHLEVEL_API_KEY` / `GOHIGHLEVEL_LOCATION_ID` at runtime now BLOCKS with a named, client-facing remediation (how to create the PIT + find the Location ID), mirroring the Firebase-token nudge — never a silent no-op. (A 429 still STOPs and surfaces the reset time; it does not ask for credentials.)
- **Disclosure header scoped OPERATOR-CHANNEL ONLY** (INSTRUCTIONS.md + CORE_UPDATES.md): the `[GHL tier used: N — tool]` header is the operator's audit trail and MUST be stripped from client-facing replies (WE MOVE IN SILENCE).
- **Command Center hooks** (INSTRUCTIONS.md): skill 36 emits status to Skill 32's existing board ingestion at install start/complete and on tier incidents (429 lockout, missing credential) — best-effort, operator-only, no parallel board (uses Skill 32's documented ingestion; skipped if Skill 32 absent).

## [v1.2.5] - 2026-06-21 — Tier 4 realigned to agent-browser-first; page/funnel building delegated to Skill 06 (no parallel path)

### Changed
- `ghl-mcp-setup-full.md` Tier 4 section: PRIMARY browser engine is now **agent-browser** (Vercel Labs, Skill 03), headless + isolated `--session`; Playwright is the scripted fallback only (still `launchPersistentContext`, never `launch()`).
- Removed the stale **"Browser MUST be Playwright + Kimi K2.5 model"** line (no longer the primary path).
- Auth now prefers the seeded Firebase refresh token (logged-in session, no typing); `GHL_AGENCY_EMAIL` / `GHL_AGENCY_PASSWORD` documented as fallback only.
- Login URL corrected to the white-label **root** (the login form mounts at `/`, not `/login`).
- **Funnel / Website / Page building is explicitly owned by Skill 06 (`ghl-install-pages`)** — points at Skill 06's `ghl-browser-builder-full.md` (v3.0) + `tools/`; no parallel page-builder path is maintained in Skill 36.

## [v1.2.1] - 2026-06-11 — 5-tier → 6-tier label sweep (Tier 0 = Skill 44) across QC/INSTRUCTIONS/full doc

### Fixed
- Four stale "5-tier" labels survived from before Tier 0 (Convert and Flow CLI, skill 44) became the PRIMARY first stop; SKILL.md/INSTALL.md/CORE_UPDATES.md already said 6-tier, but these lagged. Corrected — no behavior change, the routing logic was already 6-tier:
  - `QC.md` §1 Purpose — "5-tier" → "6-tier" with Tier 0 named.
  - `INSTRUCTIONS.md` intro — "5-tier" → "6-tier"; the preference-order sentence now leads with Tier 0 (Convert and Flow CLI, skill 44).
  - `ghl-mcp-setup-full.md` §"access chain you are setting up" — added the missing **Tier 0 row** to the chain table (it only listed Tiers 1-5); header + "try in numerical order" rule updated to start at Tier 0; Tier 4 corrected to agent-browser-first per the canonical SKILL.md.
  - `ghl-mcp-setup-full.md` §8 Phase 7 heading — "5-TIER CHAIN" → "6-TIER CHAIN".

## [v1.2.0] - 2026-06-11 — GHL_AI_LAYERS cross-reference added; MCP scope clarified vs Build API

### Why
The 6-tier chain (Skill 36) installs GHL MCP access. Multiple operators conflated the
MCP tier (read/write contacts, conversations, calendar via public API) with Skill 44's
internal Build API (workflow create/edit). GHL_AI_LAYERS.md now documents the full
picture; Skill 36 cross-references it so operators reading the tier chain know MCP and
the Build API are orthogonal surfaces.

### Changes
- Cross-reference to `38-conversational-ai-system/references/GHL_AI_LAYERS.md` added to
  SKILL.md and INSTRUCTIONS.md with a one-line clarification: "MCP tools (Tiers 1-2)
  cover contacts/conversations/calendar/tags reads and writes. They do NOT build GHL
  workflows. Workflow builds use Skill 44's internal Build API (Tier 0) or the
  Build-with-AI manual paste. These are orthogonal surfaces. See GHL_AI_LAYERS.md."
- skill-version.txt bumped to v1.2.0.

## [v1.1.1] - 2026-06-11 — SOUL.md tier-protocol removal regex fix (D-1)

### Changes
- wire.sh SOUL.md tier-protocol removal regex now matches header suffix variants (D-1).

## [v1.1.0] - 2026-06-10

### Skill 44 era — 6-tier overhaul (edits a-m)

- Added Tier 0 (Convert and Flow CLI, skill 44) as the new first stop in the access chain across all files. 6-tier chain replaces 5-tier throughout SKILL.md, INSTALL.md, CORE_UPDATES.md, INSTRUCTIONS.md, qc-ghl-mcp-setup.sh.
- SOUL.md section flipped to NO UPDATE NEEDED; GHL Tier Escalation Protocol relocated to AGENTS.md (operating law, not identity). QC assertions updated accordingly (Section E + new Section H).
- Appendix-B tier table with Owning skill column written into CORE_UPDATES.md AGENTS.md block.
- Token-aware routing rule and 429/rate-limit carve-out added to AGENTS.md block.
- Disclosure header format gains Tier 0 examples; AGENTS.md disclosure line updated.
- Anti-patterns block gains two Tier-0-skip entries (CORE_UPDATES.md + INSTRUCTIONS.md).
- Tier 2 (Community MCP) changed to ON-DEMAND via curl — no native mcp.servers registration. Context overhead measurement: 588 tool schemas in standing context added ~18k tokens per session on representative workloads; decision = SHIP the de-registration. QC Section D assertion flipped to assert NOT registered + service responds on /tools.
- Tier 4 updated to agent-browser-first (skill 03) in INSTRUCTIONS.md + CORE_UPDATES.md.
- Skill 35 cross-reference corrected: skill 35's 15+6 pipeline is exempt from tier routing; only AD-HOC interactive requests follow the chain (SKILL.md + INSTRUCTIONS.md).
- wire.sh added with migration units M1 (SOUL relocation), M2 (Tier 2 de-register): marker-bounded, backed up, idempotent.

## [v1.0.0] - May 13, 2026

### Initial Release

- **New skill 36** that installs the 5-tier GHL access chain
- **Tier 1:** Official GHL MCP registration via `openclaw mcp set ghl-mcp` — 36 tools, stateless protocol
- **Tier 2:** Community GHL MCP (BusyBee3333 2026 fork) — 588 tools across 44 categories including Voice AI, Phone System, Agent Studio, Proposals
- **`$GHL_COMMUNITY_MCP_URL` env var** added to prevent port-hardcoding failures
- **launchd plist (macOS)** OR **systemd unit (Linux/VPS)** lifecycle — no Docker dependency
- **Platform auto-detection** — single skill, same files in both Mac and VPS repos, conditional logic inside for `/data/...` vs `~/...` paths
- **🔴 Tier Escalation Protocol** added to SOUL.md as cardinal behavioral rule
- **Canonical state block** added to AGENTS.md to override stale session memory
- **Tier-skip enforcement** with named anti-patterns from documented past failures (2026-05-12: skipping Tier 2 for products; hardcoded port 8000)
- **Disclosure header protocol** — every GHL response must prefix with `[GHL tier used: N — tool_name]`
- **20-assertion QC script** (`qc-ghl-setup.sh`) covering platform detection, credentials, both MCPs, core file wiring, and security
- **Cross-references** to skills 05 (foundation), 29 (Tier 3 reference), and 35 (which now routes through MCPs first)
- **Credential canonical path migration:** moved from `~/clawd/secrets/.env` (legacy skill 05 location) to `~/.openclaw/secrets/.env` (current AGENTS.md canonical)

## [v2.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
