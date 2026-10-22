# Council of Wise Elders (77): Changelog

## v1.0.51: Council: nine seat emblems and a cover emblem land as assets/seats art, and the branch folds in upstream main (W74-ASSETS)

In plain English: every seat now has its own painted emblem - the council cover gets one too - so the rendered artifact page (W74-B's `render-counsel-artifact.mjs`, which defaults its asset source to `assets/seats/cover.png`) has the art it points at, in-repo.

- New `assets/seats/` with ten PNG files: nine seat emblems (one per elder seat) plus `cover.png`, all generated as painted heraldic medallion emblems (navy and antique gold, ornate filigree border, symbolic objects only - no human faces, no likenesses of real people, no text in any image).
- Branch merges upstream main (the W73 BUILD entry lands as v1.0.45 below this one), the W74-C/B/A/D entries renumber to v1.0.47 through v1.0.50, and this entry is the new top at v1.0.51.
- Repository markers (SKILL.md frontmatter version, skill-version.txt, version file) agree at 1.0.51; manifest and archive regenerated with `scripts/build-bundles.mjs`.

## v1.0.50: Council: one convene flow wires the brief-builder, the deliberation, the close protocol and the artifact - on both doors (W74-D)

In plain English: a council now runs as one flow. The brief the elders read is assembled first from the client's permitted memory files, the council deliberates and reaches its verdict, the sitting closes itself (the soft-close question, or the client's own "that's all"), and the finished counsel page arrives in the reply beside the chamber link. The same flow serves both doors: the client's OpenClaw agent and claude-nine / Claude Code (999) - the client only asks for the council, whichever side they are on.

- One wired flow (`runtime/src/flow/convene-flow.ts`) in the exact order the skill prescribes: brief-builder FIRST (permitted context through the door's adapter), deliberation, verdict, then session-close manages the sitting and finalize calls `renderArtifact(sessionRecord)` and returns the delivery (reply link + chamber).
- The render seam lands (`runtime/src/reports/artifact-renderer.ts`): the entry point the close protocol resolves by name, plus `assembleRenderRecord`, the projection from the stored session and the runtime rows (client name, model, question count, seat takes, verdict) into the renderer's fixed session record. Nothing is invented at the seam; the renderer's own validation still runs.
- Both doors wired and documented: the OpenClaw door uses the OpenClaw adapter (memory.md, agents.md, soul.md, user.md), the claude-nine / Claude Code (999) door its adapter (CLAUDE.md, AGENTS.md, memory/MEMORY.md). Harness markers select the door; the brief shape and the flow are identical either way. SKILL.md, INSTRUCTIONS.md and EXAMPLES.md now say exactly how a client triggers each door and carry the close question and the artifact delivery.
- New assert-style test `runtime/tests/convene-flow.test.ts` (no framework) proving the order on both doors - the deliberation leg receives the assembled brief, finalize really renders through the W74-B renderer, and the delivery carries the artifact link beside the chamber - plus the sitting cases (soft-close at 5m, close phrase finalizes, 10-minute auto-finalize).
- Manifest and archive regenerated with `scripts/build-bundles.mjs`; repository markers not rolled (skill-internal change).

## v1.0.49: Council: a sitting now closes itself - one soft-close question, an explicit close phrase finalizes at once, and ten quiet minutes never leave a session open (W74-A)

In plain English: a council sitting is one session and every sitting gets closed. Five minutes after the client's last interaction the council asks exactly once "Is that all, or are we still working?"; an explicit close phrase ("that's all", "we're done", "finalize", ...) finalizes immediately; no answer within ten minutes of the question finalizes automatically; and nothing hangs open.

- Session-close protocol in the runtime (`runtime/src/protocol/session-close.ts`): a 5-minute idle soft-close sends ONE question per quiet spell, an explicit close phrase finalizes immediately, and 10 minutes of silence after the question auto-finalizes. A client answer is a new interaction that restarts the quiet clock - never an auto-finalize over an answer.
- Finalize marks the session closed in the store, hands the session record to the artifact renderer's `renderArtifact(sessionRecord)` (W74-B contract: returns artifact path + link), and the reply carries the link. Idempotent: a closed sitting renders once and never re-marks.
- Close state derives from the store's own timestamps - the session's last journal event and the durable soft-close/close markers in the projection outbox - never from in-memory timers. A service restart continues the same quiet spell, loses nothing, and never sends a second soft-close question (proven over the real store in the test).
- New assert-style test `runtime/tests/session-close.test.ts` (no framework) proving the four cases: idle fires the soft-close at 5m, an explicit close phrase finalizes immediately, 10 minutes of silence after the question auto-finalizes, and restart-safe derivation.
- Skill instructions: "Closing a session" added to SKILL.md and INSTRUCTIONS.md. "Resolve existing sessions first, never create a duplicate" and one active session per client stay exactly as they were.
- Manifest and archive regenerated once with `scripts/build-bundles.mjs`; repository markers not rolled (skill-internal change).

## v1.0.48: Council: a finished sitting renders as one fixed counsel artifact page (W74-B)

In plain English: after a council sitting, the result now renders as one clean page: the decision and the overall consensus at the top, the nine elders with their seat emblems and their takes below, the action steps numbered, and a footer with the sitting facts. The page is print-ready and can produce a real PDF when the box has headless Chrome or cupsfilter; otherwise the client prints from the browser. The look is identical for every client and every sitting.

- renderArtifact(sessionRecord) is a pure function of the session record (assembled from the council.db cards and verdicts): one fixed deep-green and gold template, no per-client theming, writing council-data/artifacts/<session-id>/index.html plus copied assets referenced by relative paths only, and returning { path, link, pdf }.
- Five sections in fixed order: header (client name, date, the decision, slim cover band), overall consensus in large type, nine elder cards (seat emblem, name, lane, take), numbered action steps from the verdict record, footer (date, model used, question count in the sitting).
- Print-ready CSS always in the template (page-break rules per elder card). PDF is best effort only: headless Chrome or macOS cupsfilter when present, degrading gracefully to print-from-browser, never blocking and never faked.
- Artifacts are per-session folders bounded by the session count; the rotation note lives in the code.
- New runnable check scripts/tests/render-counsel-artifact.test.mjs: renders one synthetic fixture session (clearly labeled synthetic) and asserts the five sections in order, the nine seat images, and no absolute paths in the HTML; nine tests total.
- Manifest and archive regenerated once with `scripts/build-bundles.mjs`; repository markers not rolled (skill-scoped change only).

## v1.0.47: Council: the convene brief is now built by one shared permitted-context builder across both doors, with private detail excluded and a hard size cap (W74-C)

In plain English: before a council starts, the brief the elders read is now assembled by one shared builder that reads only the client's permitted memory files on whichever side the session runs - the OpenClaw door or the claude-nine door - and selects just the facts that bear on THIS decision. Private preferences stay in the private store, unknowns stay marked, pointer documents are followed at most one link deep, and the brief can never run past its word cap.

- One module (`runtime/src/brief/permitted-brief.ts`), two source adapters (OpenClaw: memory.md, agents.md, soul.md, user.md; 999: CLAUDE.md, AGENTS.md, memory/MEMORY.md), identical brief shape regardless of door.
- Permitted context only: the door's root files plus at most one hop of their pointer links; recursion never; a link can never escape the context root or touch a private path.
- Private preferences stay in the private store: private sections and `private:` lines are stripped, `private/` paths and `*.private.md` are never read, and the brief carries only the opaque `private_preference_ref`.
- Unknowns marked explicitly: unstated options or constraints and explicit "not yet known" markers land in `unknowns`, and items dropped by the cap are reported there too.
- Bloat protection: `BRIEF_WORD_CAP` = 2000 words, hard; facts selected decision-relevant first, newest first inside a relevance class.
- New runnable check `runtime/tests/brief-builder.test.ts` over fixture memory files: the decision-relevant fact is in the brief, the irrelevant private detail is out, the size cap holds, and unknowns are marked - proven on both doors.
- Manifest and archive regenerated once with `scripts/build-bundles.mjs`; repository markers not rolled (code fix only).
## v1.0.46: Council: the Chamber link line is the single link source (FIX W76)

In plain English: the client now gets exactly one link - the helper's `Chamber link:` line - and the raw `chamber_url` field is never sent on its own. This restores the fix that batch #2433 dropped when it merged the older #2431 snapshot instead of the later revision.

- SKILL.md: the helper's `Chamber link:` line is the single source of truth for the client's link; the command's `chamber_url` field feeds that line and is never sent to the client on its own.
- Both safety rules kept: never invent, guess, or build a link; never send a 127.0.0.1 link to a client.
- Version markers rolled to v1.0.46 (G3 requires the version marker with a skill content change); manifest and archive regenerated with `scripts/build-bundles.mjs`.

## v1.0.45: Council: the W73 chamber-visual package clears the QC gate and its version markers roll (BUILD W73)

In plain English: the W73 chamber-visual change (the Roast Room visual pops up on desktop and the chamber link rides every reply) is unchanged. This patch rolls the version markers and repackages the archive so the pull request's required G3 check sees the skill content change and the skill-version.txt bump together.

- skill-version.txt and version rolled from v1.0.44 to v1.0.45; SKILL.md frontmatter version rolled to match.
- Package files carry no em dash character (the QC gate that failed on the previous push now passes: doctor, verify-cohort-parity, verify-bundles, qc-council-of-wise-elders.sh all green; chamber-visual.test.sh 17/17).
- Manifest and archive regenerated once with `scripts/bump-version.sh` plus `scripts/build-bundles.mjs`.
## v1.0.44: Council: the Roast Room visual pops up and the chamber link rides every reply (BUILD W73)

In plain English: no matter how the client calls the elders — claude-nine terminal or chat — the chamber visual they see at the link shows up for them too: on a desktop box it opens in the browser on every convene, and the chamber link is always in the reply so phone and chat callers tap straight into the same visual.

- New `scripts/chamber-visual.sh`: prints exactly one `Chamber link: <url>` line — resolved at runtime from env `COUNCIL_PUBLIC_URL`, then `WISE_ELDERS_PUBLIC_ORIGIN`, then `public_origin` in the box's own `service.json`, then the loopback service origin — and opens that URL in the default browser when a desktop session exists. Fire-and-forget: it never blocks the reply, and a headless box (CI, cron, server) gets zero pops with the link still emitted.
- SKILL.md: new "The chamber visual on every call" — the `Chamber link:` line goes into every reply (terminal and chat alike), never rewritten or guessed; a local-only 127.0.0.1 link is never sent to a client.
- New tests `scripts/tests/chamber-visual.test.sh` (17 cases): GUI present invokes `open` exactly once with the right URL, headless invokes nothing and still emits the link, the link is always in the output, URL source order, and a failed pop never breaks a convene.
- Manifest and archive regenerated once with `scripts/build-bundles.mjs`; repository markers not rolled (skill change only).

## v1.0.43: Council: an existing council ingress rule keeps its own port (FIX W68)

In plain English: the provisioner used to force every council rule back to port 8787. Now it never rewrites an existing rule — the box's own port is authoritative — and only creates a missing rule at the default 8787. A box whose Council serves on 8788 (a client webhook owns 8787 there) is left byte-identical from now on.

- An existing council ingress rule (any port) is preserved byte-identical; the run reports it as preserved and names the box's own port.
- Only an absent council rule is created, and it is created on `COUNCIL_SERVICE` (http://127.0.0.1:8787).
- New regression tests: an existing rule at 8788 is never rewritten (zero PUTs, config byte-identical), a missing rule is created at 8787, an existing rule at 8787 stays.
- Manifest and archive regenerated once with `scripts/build-bundles.mjs`; repository markers not rolled (code fix only).

## v1.0.42: Council: an already-wired Council address is adopted instead of conflicting, the client exclude list is honored everywhere, and container-connector instructions only appear with container evidence

In plain English: when the Council address is already wired, the provisioner now adopts it instead of failing on a conflict; the client exclude list is honored everywhere; and container-connector instructions only appear with container evidence.

- The provisioner adopts an already-wired Council address, and the client exclude list is honored everywhere.
- Container-connector instructions only appear with container evidence.
- Manifest and archive regenerated once with `scripts/build-bundles.mjs`; repository markers rolled once with `scripts/bump-version.sh` (v27.1.63).

## v1.0.41: Council: container-host clients with a bridge-origin Command Center can now be provisioned on a dedicated tunnel with an in-container connector

In plain English: when the Command Center lives inside a container reached through a bridge, the Council provisioner now stands up a dedicated tunnel and an in-container connector instead of failing.

- The provisioner detects the container-host shape, creates a dedicated tunnel for it, and wires the in-container connector.
- Manifest and archive regenerated once with `scripts/build-bundles.mjs`; repository markers rolled once with `scripts/bump-version.sh` (v27.1.62).

## v1.0.40: Council: the Council login page now follows the Command Center login page, orphan records are skipped, and a Mac client can use its rescue tunnel for the Council address

In plain English: council: the Council login page now follows the Command Center login page, orphan records are skipped, and a Mac client can use its rescue tunnel for the Council address. The Council login list now matches the Command Center login list and never lets in someone the Command Center excludes; records for tunnels that no longer exist are skipped instead of failing the whole run; and a Mac client's Council address can ride its own rescue tunnel.

- Sync refuses (reports FAILED, writes nothing) when the Command Center allow policies carry exclude or require rules that differ, so a revoked person is never kept.
- The rescue-tunnel ride only picks a tunnel that has the rescue rule for this exact client, and a failed read after an edge-check failure no longer overwrites the rescue tunnel's ingress.
- A live Command Center on a healthy tunnel is never skipped as an orphan.
- Manifest and archive regenerated once with `scripts/build-bundles.mjs`; repository markers rolled once with `scripts/bump-version.sh` (v27.1.61).

## v1.0.39: Council: the new-address check no longer depends on a resolver cache, so a new client's address is not rolled back by a stale DNS miss

In plain English: the new-address check no longer depends on a resolver cache, so a new client's address is not rolled back by a stale DNS miss. After a new client's Council address is created, the check that it opens now asks the zone's own nameservers directly for the address instead of trusting a cached answer, so an earlier "no such name" lookup can no longer make a good setup get rolled back.

- The edge check asks the zone's authoritative nameservers on every try and connects to the answer it gets, then still requires the Cloudflare Access login redirect.
- If the lookup tool or nameservers are unavailable it falls back to the normal lookup; `COUNCIL_EDGE_RESOLVE=system` turns the new behavior off.
- Manifest and archive regenerated once with `scripts/build-bundles.mjs`; repository markers rolled once with `scripts/bump-version.sh` (v27.1.60).

## v1.0.38: Council: login pages always list the operator and every client email found in GoHighLevel, and no Council address is published before its connector is live

In plain English: Council: login pages always list the operator and every client email found in GoHighLevel, and no Council address is published before its connector is live. A client's Council login page now keeps the operator and each client email found in GoHighLevel, and the Council address is only published once its connector is running.

- The provisioner creates the Council address only after a connector shows as active, and says plainly when the connector is still pending or down.
- The login page rule is kept in sync with the operator and GoHighLevel client emails without removing anyone already allowed.
- A GoHighLevel contact is matched to a client only by a safe rule: a first name alone, a full name alone, or a contact with no name never gets added.
- Manifest and archive regenerated once with `scripts/build-bundles.mjs`; repository markers rolled once with `scripts/bump-version.sh` (v27.1.59).

## v1.0.37: Every client's Council address is now provisioned: legacy Command Centers, down tunnels and local tunnels are handled

In plain English: every client's Council address is now provisioned: legacy Command Centers, down tunnels and local tunnels are handled. The operator's access job now covers older Command Centers, tunnels that are down and tunnels managed on the operator's machine, and each client box runs its own Council connector without touching the Command Center tunnel.

- The provisioner finds the Command Center by what the tunnel serves, creates a dedicated Council tunnel when needed, and reports a down tunnel or a waiting connector instead of claiming done.
- The box Council connector runs with its own config and a blank inherited tunnel token, so it can never start the Command Center tunnel by mistake.
- The box check reports a missing or stopped connector plainly.
- Manifest and archive regenerated once with `scripts/build-bundles.mjs`; repository markers rolled once with `scripts/bump-version.sh` (v27.1.58).

## v1.0.36: A brand-new client's Council address now sets itself up with no human step

In plain English: a brand-new client's Council address now sets itself up with no human step. The operator's automatic access job first gives the new client's Command Center its login, then creates the Council address, and tells the operator plainly when it is still waiting for the client's email.

- The access job now runs `ensure-cc-access.sh` before `provision-council-access.sh` and records the result as `cc_access` in its receipt.
- A missing client email or a login that differs from the expected one is reported and retried on the next run; it never fails the run.
- Provisioning skips hosts that are not Command Centers and never reports a down connector as done.
- The installer passes the client's owner email through, and the tunnel request retries instead of failing early.
- Manifest and archive regenerated once with `scripts/build-bundles.mjs`; repository markers rolled once with `scripts/bump-version.sh` (v27.1.57).

## v1.0.35: The client Council link is now fully automatic for every client, new and existing

In plain English: the client Council link is now fully automatic for every client, new and existing. Every client gets a Command Center, so every client gets a link, even before the AI Workforce interview is done. The link is found when the Council is convened, and the operator's automatic access job keeps it working with no manual step.

- Manifest and archive regenerated once with `scripts/build-bundles.mjs`; repository markers rolled once with `scripts/bump-version.sh` (v27.1.56).

## v1.0.34: Clients only get a Council link that actually opens

In plain English: clients only get a Council link that actually opens. Before handing one over, setup now checks that the link answers from the public internet and drops it if it does not. If there is no working link, the Council says so plainly and tells the client what to do next instead of sending a dead address.

- Manifest and archive regenerated once with `scripts/build-bundles.mjs`; repository markers rolled once with `scripts/bump-version.sh` (v27.1.55).

## v1.0.33: The Council screen is back to the approved look

In plain English: the Council screen goes back to the look that was approved. There is no extra box above the room, Key Points are compact again, and no internal ids show on the page.

- Manifest and archive regenerated once with `scripts/build-bundles.mjs`; repository markers rolled once with `scripts/bump-version.sh` (v27.1.54).

## v1.0.32: Councils on claude-nine now finish; a blocked council shows the real reason

In plain English: a council run through claude-nine could stall or lose its settings partway through, and a blocked council said the chair was still working. Now every claude-nine call keeps its safety settings, a stuck call is stopped cleanly and tried once more if it never started, the deadline is decided in one place and written down, and a blocked council names the seats that are missing and why.

- Manifest and archive regenerated once with `scripts/build-bundles.mjs`; repository markers rolled once with `scripts/bump-version.sh` (v27.1.51).

## v1.0.31: clients can use the Council on their own box, and Claude Code routes are proven

In plain English: until now the Council worked end to end only on the operator's own machine. After the next fleet roll, every client box builds the Council engine itself, keeps it running, and gives the client a signed-in way to open the Roast Room. Nothing changes about the client's models, keys or settings.

- **Wiring on every box**: `wire.sh` builds the runtime the same way every time, starts the Council service, and restarts it after updates and reboots. Running it twice changes nothing.
- **A private address per client**: `provision-council-access.sh` gives a box its own `<name>-council` address behind the same sign-in and email list as the client's Command Center. A box without a Command Center still gets Council answers from its agent, just no Roast Room link.
- **Claude Code routes**: the Council now convenes through claude-nine and plain Claude Code, as well as a client's own configured provider such as DeepSeek. It uses the route the client already has and never switches it.
- **Repair and clearer reasons**: a stuck session is repaired and a blocked one says why in plain words.
- **Box check**: `verify-council-box.sh` reports whether a box is ready and names the exact missing step if not.
- Manifest and archive regenerated once with `scripts/build-bundles.mjs`; repository markers rolled once with `scripts/bump-version.sh` (v27.1.49).

## v1.0.30: the verdict says why, and Key Points show what the elders actually said

In plain English: two gaps found on the first real live council. The screen said "Verdict: Wait" and showed nine of nine votes for Option B, but never said why the answer was Wait. And the Key Points list held only phase headings. Nothing about how a council runs has changed; the screen now shows more of what the session already recorded, with no new model calls.

- **A short "Why" under the verdict**: what has to happen first (the conditions the elders attached), how strong the evidence is in plain words, how the vote went, and where the elders disagree (the strongest dissent, or the sharpest caution when nobody voted against).
- **Key Points show real content**: each elder's lead argument, the fault lines the chair found, the conditions attached to the resolution, the changes elders asked for and their dissent. Every line names the elder in full. The phase headings stay as small group labels, and long lines show a short version with "Read more".
- **Proof on real data**: the first live session (verdict Wait, Option B, 27 cards) is saved read-only as a test fixture, and new tests replay it.
- Manifest and archive regenerated once with `scripts/build-bundles.mjs`; repository markers rolled once with `scripts/bump-version.sh` (v27.1.47).

## v1.0.29: client polish on the live Council screen

In plain English: five small clean-ups on what a client sees, found while checking the live Council screen. Nothing about how a council runs has changed.

- **Plain wording in the New question window**: under the Convene button it now says "Convening starts the council now on the model you chose." It no longer talks about allowances or approval.
- **Friendly model names**: Google Gemini, Ollama, OpenRouter, Agnes, 9Router and OpenAI now show their own names instead of "the selected model". A model that cannot be used yet says "Not available for the council yet" instead of a raw code.
- **All six steps fit on a phone**: Brief, Openings, Fault lines, Debate, Vote and Verdict wrap onto two rows at phone width, so nothing hides off-screen in a sideways strip.
- **Status page tells the truth**: the service status page (/status) no longer says the Council screen is not packaged. When it is packaged, the page links to it.
- **Operator help cleaned up**: the command list no longer shows the old start/resume grant and authorization commands, and the recovery messages no longer send anyone to approve anything.
- **Changelog wording**: the v1.0.26 note now says that release shipped inside v27.1.45 (it first carried the number v27.1.42 on its branch).
- Manifest and archive regenerated once with `scripts/build-bundles.mjs`; repository markers rolled once with `scripts/bump-version.sh` (v27.1.46).

## v1.0.28: Roast-Room chamber screen (full reference structure, brand colors, Pixar portraits)

Eight Opus-passed pieces, integrated once on top of v1.0.26 (W29-U001). In plain English: the chamber page is rebuilt as the full Roast-Room screen. A sticky top bar, a decision header with live option bars, a room of nine seated advisors with typing bubbles and a round headline, a key-points rail, and a click-to-open advisor card, all in BlackCEO colors, with 3D Pixar-style portraits.

- **Page shell** (`patch/W29-A-shell`): top bar with the BlackCEO logo, a six-step progress strip (Brief, Openings, Fault lines, Debate, Vote, Verdict), and How it works, Past sessions and New question buttons. New question convenes a real council through the client-chosen model route. The front door now serves every new chamber file and the portrait images.
- **Decision header** (`patch/W29-B-decision`): the question and its options with a bar and count per option that fill in as advisors take positions, and a verdict badge at the end.
- **Room** (`patch/W29-C-room`): nine advisors in a shallow arc behind a table, a typing bubble over each, the active advisor highlighted, round label, timer, headline, "is weighing" line and progress bar. Clicking an advisor opens that advisor's card.
- **Key points** (`patch/W29-D-keypoints`): a running list of milestones on the right (or below on narrow screens).
- **Advisor card** (`patch/W29-E-seatcard`): portrait, role, the question that advisor owns, current position, and the plain "simulated advisor, not the person" note; closes with Escape, the backdrop or the Close button.
- **Advisor data and portraits** (`patch/W29-F-seatdata`): names, roles and weighing lines for all nine advisors plus cut-out Pixar-style portraits.
- **Brand theme** (`patch/W29-G-theme`): one set of BlackCEO color tokens (black, cream, gold) used everywhere; no navy.
- **Live state** (`patch/W29-H-state`): turns the live event stream into what the screen shows, keeps a clearly labelled demo replay, and adds card details to the stream so bars, lines and the advisor card come from real cards.
- **Full names and no model codes** (`W29-fullnames`): each advisor's name pill now shows the full name (Simon Sinek, Russell Brunson, Dennis Kimbro and so on; it wraps to two lines on narrow phones), and the screen shows a friendly model label such as "Sample replay" or "Claude Code" instead of an internal route code. On phones the front row of advisors now sits a little lower so a two-line full name never hides behind the row below.
- **No budget line on the client page**: the New question window no longer shows a "Budget: ..." line under each route (the service stopped sending budgets when the approval step was removed, so it always read "not listed"); the route-budget test now scans the chamber scripts too.
- Manifest and archive regenerated once with `scripts/build-bundles.mjs`; repository markers rolled once with `scripts/bump-version.sh` (v27.1.45).

## v1.0.26: live council (client-chosen model, service driver, Book-to-Persona elders)

Eight Opus-QC-passed patches, integrated once on top of v1.0.25 (W28-U001). In plain English: the client now picks the model for each council run, a convened session is actually deliberated end to end, and the elders speak from the client's own Book-to-Persona material with clearly labelled web research for current facts.

- **Client picks the model per run** (`patch/W28-route-choice`): the model route is resolved per session and passed to the harness as `--model`. With no choice the running harness decides: the claude-nine configured default on claude-nine, Sonnet on Claude Code direct, and the latest DeepSeek Flash on DeepSeek direct (resolved from the provider's model list at run time, today the alias `deepseek-flash`). QC verdict: PASS.
- **Token limits per route**: `config/route-budgets.json` ships the numbers measured so far (DeepSeek Flash); a route without measured numbers uses a conservative built-in default and the route's own window and answer limits, so it still convenes. `measure-route-bytes-per-token.mjs` remains an optional tool that refines the numbers. QC verdict: PASS.
- **Find the client's Book-to-Persona store** (`patch/W28-persona-root-inventory`): resolves the client's own persona store and adds a read-only live inventory (`inventory-live-personas.mjs`) that reports unreadable stores and never prints absolute paths. QC verdict: PASS.
- **Elder knowledge in three layers** (`patch/W28-elder-knowledge`): the live Book-to-Persona persona from the client's own store first; the shipped 2026-10-14 briefs as the per-elder fallback; and web research for current facts, stored apart from the books and shown under its own "From the web today" heading in the briefing and in the report. QC verdict: PASS.
- **A convened session is really deliberated** (`patch/W28-convening-driver`): the service driver takes a session through the rounds, runs the workers, and writes `council_events` for the live SSE stream. Convening is the approval: there is no blocking spend gate, and every run is still audited. QC verdict: PASS.
- **Service wiring** (`patch/W28-service-wiring`): binds the per-session route, the per-route token limits, elder knowledge and the driver into the service. Adds `GET /api/council/routes` and `POST /api/council/convene` behind the same fence as admissions, and removes the service-wide ROUTE_SELECTION_AMBIGUOUS failure (readiness is ready when one route can be composed). It keeps the W27 `GET /api/council/sessions` list route beside the new routes. QC verdict: PASS.
- **CLI and agent instructions** (`patch/W28-cli-convene-and-skill-docs`): `blackceo-council routes` and `blackceo-council convene --brief FILE|--sample` with `--route`, `--model`, `--harness` and `--fresh-facts FILE`, and SKILL.md rewritten so the agent asks which model to use, researches current facts with labelled sources, and tells the client which model is running. QC verdict: PASS.
- **Landing page notices tell the truth** (`patch/W27-landing-notices`): `/status` no longer shows "event stream not bound" and the unbound-route wording when the composition has bound them; the notices follow the real binding. This is the fix the live service already ran uncommitted. QC verdict: PASS.
- **Real-run fix: one paid answer per seat** (`patch/W30-single-executor`): only one live worker may hold a session at a time, so a second claim can no longer cut off a response that was already paid for; a fenced settle is now reported (stderr and a `worker_error` event) and its paid hold stays counted instead of lapsing to free. QC verdict: PASS.
- **Real-run fix: the model is told the card shape** (`patch/W30-response-schema`): every model request on the service path now carries the exact card response schema, so seats stop inventing their own card shape and failing validation. QC verdict: PASS.
- **Real-run fix: the journal shows which knowledge each seat used** (`patch/W30-knowledge-layer`): each seat's briefing records once per session whether it used the client's live Book-to-Persona persona, the shipped brief, or nothing, plus the web fact count. QC verdict: PASS.
- **A new install now convenes immediately; no approval step.** (`unit/W28-U001-live-council`): the first run on a fresh install is accepted on DeepSeek Flash and on any route without measured numbers; nothing is measured or approved first, and the routes list no longer carries an approval state.
- **Real-run acceptance fix round 1: the model is told the last two card rules, and an unfinished round stops the session** (`unit/W28-U001-live-council`): the card instructions now say that evidence reference arrays may hold only evidence manifest IDs (never the brief's fact, assumption, unknown or constraint IDs) and that `lenses_used` belongs to T. D. Jakes alone, so two seats no longer fail Round 1 and block the council. A round that ends with work still queued (the grant refused a repair) or, in full mode, a seat with no card, now stops the session as BLOCKED and resumable instead of planning the next round from a partial record, which had made every Round 3 call refuse as input drift and wasted paid Round 2 calls. The convening repair ceiling now fits all 27 operations (27 repairs, 62 requests). A real DeepSeek Flash council on a private test instance completed: 27 cards, a verdict, 29 model calls, 2 Round 2 repairs.
- Manifest and archive regenerated once with `scripts/build-bundles.mjs`; repository markers rolled once with `scripts/bump-version.sh` (first numbered v27.1.42 on its branch; this release shipped to main inside v27.1.45).

## v1.0.25: W27 hardening batch (status cold path, launcher, skill root, live chamber)

Four Opus-QC-passed patches, integrated once (W27-U001):

- **First `/status` is no longer cold** (`patch/W27-status-cold-path`): the front door runs one readiness pass at service start, so the first `GET /status` does not pay lazy-init and cold filesystem cost inside the request under macOS background QoS. Each request still re-observes live state. The focused test moved to `runtime/tests/service-status-cold-path.test.ts` so `npm test` actually collects it. QC verdict: PASS.
- **Upstreamed service launcher** (`patch/W27-launcher-upstream`): `runtime/scripts/service-launch.mjs` starts the front door through `startCouncilService`, so the event, admission and session adapters are bound (a bare front door answers 501 on events). Data dir comes from `COUNCIL_SERVICE_DATA_DIR` or the platform default. INSTALL.md documents the `runtime/node_modules/.bin/tsx` run command from the skill root; guard test `runtime/tests/service-launcher.test.ts`. QC verdict: PASS.
- **Installed binary finds its skill folder** (`patch/W27-skill-root-upstream`): `skillRootForAssets()` in `runtime/src/cli/dispatcher.ts` resolves the skill root from the install record (`skill_dir`), else the nearest ancestor holding SKILL.md, advisors/ and manifest.json; data-dir commands refuse when none is found. `scripts/install-runtime.mjs` now writes `releases/install-record.json` and heals prefixes installed without it. New `runtime/src/cli/skill-root.test.ts` covers both bundle layouts (`test:skill-root` npm script). QC verdict: PASS.
- **Live chamber view over real sessions** (`patch/W27-live-chamber-view`): read-only `GET /api/council/sessions` (501 `SESSION_LIST_NOT_BOUND` when no listing reader is bound), selected-session committed events over the existing SSE route, an honest "No council sessions yet" state, and the fixture kept only as a hidden, labelled sample. The list refreshes in place by `session_id`, keeping keyboard focus and announcing "Loading" only on first load or Refresh. New `chamber-live.js` ships in the `public/chamber` allowlist. QC verdict: PASS.
- Manifest and archive regenerated once with `scripts/build-bundles.mjs`; repository markers rolled once with `scripts/bump-version.sh` (v27.1.41).

## v1.0.24: the runtime test collection states the platform it actually runs on

- `runtime/tests/core.test.ts` asserted the XDG data-directory default unconditionally, so it failed on macOS and Windows where `src/cli/paths.ts` documents and implements a per-platform default. The test now asserts the contract for the running platform: `~/Library/Application Support/BlackCEO/WiseElders` on darwin (and that `XDG_DATA_HOME` does not steer it), `%LOCALAPPDATA%\BlackCEO\WiseElders` on win32, XDG elsewhere.
- `runtime/tests/cli.test.ts` ran a bare `doctor --json` and asserted the not-ready contract, which is false on a machine with configured harness roots. The case now injects `createLocalHost({ ...opts, discoverRoutes: false })`, pinning the not-ready contract instead of per-machine state. Real route composition stays covered by the rp0461 cases in `cli-route-composition.test.ts`.
- `runtime/tests/context-integration.test.ts` and `runtime/tests/export-adapter.test.ts` read the real CWE-011 export package, which is external data that is not in this repository and must never be fabricated. When it is genuinely absent they now SKIP naming the exact missing path (`CWE011_EXPORTS_DIR` can point at a real package) instead of erroring or passing on absent data. No assertion was weakened or deleted: the real-data assertions still run whenever the package is present.
- QC: `npx tsc --noEmit -p tsconfig.json` exit 0; `node scripts/doctor.mjs` PASS; `node scripts/verify-cohort-parity.mjs` PASS; manifest and archive regenerated with `scripts/build-bundles.mjs`.

## v1.0.23: the installable tarball carries the chamber assets (W25-U001 packaging)

- `runtime/package.json` limited npm's `files` allowlist to `["dist"]`, so an install from a built tarball carried no `public/chamber` and the front door answered `GET /chamber/` with 404. The allowlist is now `["dist","public/chamber"]`, the only asset tree `front-door.ts` resolves.
- `runtime/tests/package-contents.test.ts` asserts that allowlist, so dropping `public/chamber` again fails the suite instead of shipping an archive that cannot serve the chamber.
- `runtime/public/chamber/RECEIPT.md` no longer claims `files` is `["dist"]` or that shipping through `npm pack` remains a separate release step; the receipt now states the measured allowlist and the pack/install/probe proof.

## v1.0.22: the real backend is composed (W22-U001) and one composition binds the durable service (W25-U001 Lane E)

### One composition binds the durable service (W25-U001 Lane E)

- The measured gap was between "code exists" and "Start creates a session, workers produce output, SSE streams events": a composition root built the store, journal, outbox and workers, but nothing bound the front door's admission sink, event-stream adapter or session reader, and the CLI wrote canonical session rows into a database the service never read.
- `runtime/src/cli/authorization.ts` now opens the installation's ONE canonical database, `<dataDir>/council.db`, instead of a separate `council-authorization.db`. Evidence before the change: a CLI `create` left `council.db` with 1 local `sessions` row and no `council_*` tables, while `council-authorization.db` held 1 `council_sessions` row and 1 `council_events` row; the service reader over `council.db` answered `NULL` with 0 journal rows. After the change `council.db` holds both the local and canonical rows, the service reader answers `FOUND` with 1 journal row, and no authorization database is created. The two schemas share the file because their table names are disjoint.
- `runtime/src/service/events.ts` is the accepted W21 event/session adapter: `journalEventStreamAdapter` replays committed journal rows and follows new ones, `repositorySessionReader` reads the canonical repositories, and `formatCouncilEventFrame` is the existing Command Center SSE wire format.
- `composeCouncilService()` / `startCouncilService()` now bind, in one call: the durable admission sink over `DurableOperationProducer`, the journal event stream adapter, and the repository session reader over the same store/journal/outbox the workers use. Unknown ids answer `404 SESSION_NOT_FOUND` on both the session and events routes; with nothing bound a bare `CouncilFrontDoor` keeps the historical `200 ui: "not_bundled"`, `501 EVENT_STREAM_ADAPTER_NOT_BOUND` and `503 ADMISSION_SINK_UNBOUND` answers byte-for-byte.
- The admission sink maps `{session_id, operation_id, payload}` onto the canonical `AdmissionCommand`; the payload carries the granted run id, frozen route snapshot hash, input hash and reservation. A missing field is a typed refusal: the service never invents a grant, a hash, a reservation or a session.
- Deliberation host bindings: `resolvePrincipal` (standalone owner) and `loadSeatBriefing` (installed advisor packs) are bound; `resolveTransport` is bound when a real route resolved, using the configured harness or OpenAI-compatible endpoint and resolving the credential only at flight time. `catalog` stays null unless the host supplies an adapted Skill 22 export, and `routeBudget` stays null because route discovery publishes `contextWindowTokens` only and this runtime has no verified token-to-byte conversion — both are named rather than guessed.
- `runtime/tests/service-session-journey.test.ts` 3/3 proves: CLI-created session visible to the reader, unknown id 404 on both routes, an SSE frame that matches its committed `council_events` row, a complete admission persisting one `council_jobs` row plus its outbox intent, an incomplete admission refused with nothing written, restart-equivalent recomposition returning the same state and rows, and the unchanged unbound shape.

### The real backend is composed (W22-U001)

- W20 proved the honest-probe mechanism but left `store`, `route`, `routeCallable` and `worker` unbound on purpose, so the service still reported `usable: no` about a running process. The composition modules were merged and waiting; this entry binds them.
- `runtime/src/service/composition.ts` now opens one canonical SQLite handle at `<dataDir>/council.db`, applies the additive `council-0001` schema (all 18 Section 16.2 tables), records the standalone installation profile, and builds `CouncilRepositories` — which constructs the `EventJournal` and the `ProjectionOutbox` over that same handle.
- The supported route path is reused, not reinvented: the selected route id resolves read-only through `discoverConfiguredRoutes` / `resolveRouteForDispatch`; with no id, exactly one composable route is accepted and two or more is `ROUTE_SELECTION_AMBIGUOUS`. The guarded provider dispatch port is bound by the host launcher; offline readiness checks its presence and makes zero provider calls.
- `composeDeliberationService` composes the durable runner, jobs, budget ledger, grants and admission over the same handle, and one `startCouncilWorkers` supervisor runs over that runner. `stop()` stops the supervisor (awaiting in-flight work) and closes the handle exactly once; the timers are unref'd and no child process is spawned.
- Readiness observations now cite real state: `store` = 18/18 canonical tables present with journal and outbox bound; `route` = the selected route configured and its dispatch port bound; `worker` = supervisor running, poll generation observed and the durable budget ledger readable. `ui`, `discovery`, `executable` and `packs` are unchanged from W20. A bare `CouncilFrontDoor` keeps the byte-identical unbound shape.
- The four deliberation host bindings (material catalog, trusted-principal resolver, transport resolver, verified route budget) stay honestly unbound with their exact file and line recorded in the unit receipt; `DeliberationService.readiness()` therefore reports not-ready and no completed deliberation or live advisor turn is claimed. `GET /api/council/sessions/<id>/events` still answers `EVENT_STREAM_ADAPTER_NOT_BOUND`; the event stream is W21's unit.
- Advisors and book-persona mappings are byte-identical to the base commit; `front-door.ts`, `readiness.ts`, `sessions.ts`, `landing.test.ts` and `service.test.ts` are untouched.

## v1.0.21: a real event-stream adapter injection point, and a falsifiable session route

- The merged service answered `GET /api/council/sessions/<id>/events` with an unconditional `501 EVENT_STREAM_ADAPTER_NOT_BOUND`, and `GET /council/<id>` with `200 ui: "not_bundled"` for ANY id including `does-not-exist-123`, which made an earlier "real session URL" proof unfalsifiable.
- `runtime/src/service/front-door.ts`: `FrontDoorOptions` gains optional `eventsAdapter` and `sessionReader` injection points. With an adapter bound, the events route serves `200 text/event-stream` from committed frames only (replay plus optional follow) in the accepted Command Center SSE wire (`id: <sequence>` / `event: <type>` / `data: <json>`). Unbound, the exact `501 EVENT_STREAM_ADAPTER_NOT_BOUND` response is unchanged.
- With a session reader bound, `GET /council/<id>` answers `404 SESSION_NOT_FOUND` for an id the durable store does not know, and `200` with that session's data for one it does. With no reader injected, the historical `200 ui: "not_bundled"` body is preserved byte-for-byte.
- New `runtime/src/service/events.ts` supplies the injection contracts plus `journalEventStreamAdapter` (canonical `EventJournal.list` under an injected envelope) and `repositorySessionReader` (canonical `CouncilRepositories.getSession`). It opens no database, reads no credential and calls no network; a read failure is retried from the same cursor, never replaced by a synthetic frame.
- Cross-unit dependency recorded, not edited: `composition.ts` lives on `unit/W22-U001-composition-root`. That root must pass `eventsAdapter` and `sessionReader` to `CouncilFrontDoor` before these routes are live in the composed service.
- Base-vs-head loopback probe is byte-identical while unbound: `/` 302 `/chamber/`, `/status` 200, `/chamber/` 200, `/council/s1` 200 with `UI_NOT_BUNDLED`, `/api/council/sessions/s1/events` 501 `EVENT_STREAM_ADAPTER_NOT_BOUND`, `/nope` 404.
- QC: typecheck exit 0; new `front-door-events.test.ts` 6/6; `service.test.ts` + `landing.test.ts` 20/20; full runtime suite 430 tests / 423 pass / 7 fail with the failing names identical to a fresh detached worktree at the base commit.

## v1.0.20: the composition root moves into the repository (W20-U001, F5)

- The only working wiring of the front door lived outside the repository in a hand-written host launcher that called `new CouncilFrontDoor({ identity, host, ports })` and bound no readiness probe. `readiness.ts` honestly reports every unbound layer as `unknown` with `READINESS_PROBE_NOT_BOUND` (and `ui` as `blocked` with `UI_NOT_BUNDLED`), and `usable` is true only when every layer is `ready`, so the status page printed `usable: no` with six unbound layers about a service that was actually running. The real composition modules were merged but never wired into the front door.
- Adds `runtime/src/service/composition.ts`, the canonical composition root inside the repository. `composeCouncilService()` builds the identity, creates the durable data directory, binds the probes and the owning authority's `admissionSink` (when supplied), and returns the door without listening. `startCouncilService()` starts it exactly as the host launcher did, optionally installs SIGTERM/SIGINT shutdown, and returns a stop handle. The module imports no `child_process`, reads no `process.env`, makes no network call at module load and creates nothing until called.
- Binds only what this slice can observe truthfully, and each probe fails honestly instead of asserting ready: `ui` resolves the packaged asset `runtime/public/chamber/index.html` from the module's source or compiled layout; `discovery` makes a loopback-only `GET /api/council/service/identity` against the bound origin and requires a structurally valid, owner-matching document; `executable` observes `process.execPath` on disk plus the resolvable `tsx` CLI (`tsx/package.json` → `dist/cli.mjs`); `packs` resolves all nine advisor pack folders and their ten required files under the installed skill root. `store`, `route`, `routeCallable` and `worker` stay deliberately unbound: they need a real store, composed provider route and supervised worker. With this root a loopback probe reports discovery/executable/packs/ui `ready` and store/route/worker `unknown` with `READINESS_PROBE_NOT_BOUND`; `usable` stays `false` because a truthful unknown is never a ready.
- `runtime/src/service/index.ts` re-exports the root. `front-door.ts`, `readiness.ts`, `sessions.ts`, `service.test.ts` and `landing.test.ts` are byte-identical to the base commit; adding the root required no change to the front-door contract because `FrontDoorOptions.readiness` and `admissionSink` already accepted the composition.
- A deployment that has not adopted the root is unchanged: with no probes bound the readiness output keeps exactly the pre-change shape (six `unknown` layers with `READINESS_PROBE_NOT_BOUND`, `ui` `blocked` with `UI_NOT_BUNDLED`, `usable: false`). Identity and health routes keep identical status codes and bodies, proven against a bare front door on the same identity.
- `runtime/src/service/composition.test.ts` 5/5: the bound probe set, the unbound default shape, byte-identical identity/health routes, admission-sink delivery, and start/stop without signal handlers. Typecheck `npx tsc --noEmit -p tsconfig.json` exits 0. The full runtime suite keeps its control counts (430 tests / 423 pass / 7 known pre-existing failures with the same names as a worktree at the base commit). Events still answer 501 `EVENT_STREAM_ADAPTER_NOT_BOUND`: the event stream adapter and a live session journey are not claimed here.
## v1.0.19: the URL opens the Council chamber, not a status report

- The merged service served `GET /` as the developer status page while the packaged chamber sat unreferenced at `runtime/public/chamber/` — no link on that page reached it, so the URL Trevor opens showed identity hashes, six `READINESS_PROBE_NOT_BOUND` layers and three loopback links that are dead on a phone.
- `runtime/src/service/front-door.ts`: when the packaged chamber entry page resolves (`public/chamber/index.html`), `GET /` answers `302` with the relative `Location: /chamber/` — never an absolute loopback URL. The chamber itself is untouched; `/chamber/` still serves `index.html` with no `UI_NOT_BUNDLED` text.
- The previous diagnostics page moves unchanged to `GET /status`: same identity table, same readiness table, same `UI_NOT_BUNDLED` and `EVENT_STREAM_ADAPTER_NOT_BOUND` notices, same routes list. Nothing is lost; the report is simply no longer the front door.
- Without the packaged assets the root keeps the honest status page, so a build that has not shipped the chamber never breaks: `/` answers 200 diagnostics and `/chamber/` still falls through to the unchanged `SERVICE_ROUTE_NOT_FOUND` 404.
- Every other route is unchanged: `/api/council/service/identity` 200, `/council/<id>` 200 with `ui: "not_bundled"`, `/api/council/sessions/<id>/events` 501 `EVENT_STREAM_ADAPTER_NOT_BOUND`, unknown paths 404. The event stream remains unbound; that is the next unit's job and is not claimed here.
- `runtime/src/service/landing.test.ts` asserts the new contract: the 302 and its relative `Location`, `/chamber/` 200 without the diagnostics banner, `/status` 200 carrying the full diagnostics, the no-assets fallback (asset directory temporarily parked and restored inside the test), the byte-identical existing routes, and the unchanged unknown-path 404.

## v1.0.18: the Council chamber itself — WER-021 full packaging

- The merged service served `GET /` as a status report while the chamber did not exist: `GET /chamber/` returned `404 SERVICE_ROUTE_NOT_FOUND`, so an authenticated phone on the public origin landed on a report page instead of the Council. This entry ships the chamber.
- Adds `runtime/public/chamber/` — 25 self-contained files: `index.html` (nine seats, persistent fictional-sample labelling), `advisors.html` (nine seats, 11 `bibliographic_only` labels), `not-packaged.html`, three stylesheets and 18 advisor portrait SVGs. The three stylesheets are byte-identical to the Command Center council styles (16905 / 7384 / 5963 bytes, 3/3 match) and all 18 portraits byte-identical to the Command Center portraits (18/18 match). Zero `<script>`, zero `fetch(`, zero `url(`, zero `https://` in the directory; the only absolute URLs present are 18 SVG `xmlns="http://www.w3.org/2000/svg"` namespace declarations. No operator home path appears anywhere in them.
- `runtime/src/service/front-door.ts` gains a static-asset route under `/chamber/` (and `/chamber`), keeping the catch-all 404 for everything else. Traversal probes all refused with the unchanged catch-all: `/chamber/../package.json`, `/chamber/%2e%2e/package.json`, `/chamber/portraits/%2e%2e%2fpackage.json`, `/chamber/portraits/../../front-door.ts`.
- Every existing route is proven byte-identical in behaviour by a base-vs-head loopback probe against both worktrees: `GET /` 200 text/html, `/nope` 404 `SERVICE_ROUTE_NOT_FOUND`, `/api/council/service/identity` 200, `/council/s1` 200 with the `UI_NOT_BUNDLED` blocker, `/api/council/sessions/s1/events` 501 `EVENT_STREAM_ADAPTER_NOT_BOUND`.
- Pages that cannot ship without the Command Center database and its tenant gate are named with their exact blocking dependency in `runtime/public/chamber/RECEIPT.md` and are served as `not-packaged.html` rather than faked: `/council` (needs `resolveTenantContext` plus `src/lib/council/store.ts`), `/council/<sessionId>` (needs a persisted session and the durable event journal), the Command Center's own `/council/advisors` route (a static roster copy ships instead), `/council/history`, `/council/new`, `/council/settings`.
- QC: typecheck exit 0; `landing.test.ts` + `service.test.ts` 17/17 exit 0 with both files untouched; full runtime suite 430 tests / 423 pass / 7 fail, with the 7 failure names byte-identical to a fresh detached worktree at the base commit (all ENOENT on a pre-existing fixture), so the control, not the change, explains them.

## v1.0.17: a real landing page at GET / (WER-023 authenticated origin)

- The authenticated public origin returned a JSON 404 at `/` - observed live as `{"code":"SERVICE_ROUTE_NOT_FOUND","detail":"No service route for GET /."}` - because the merged WER-021 slice ships no UI and never had a root route.
- `runtime/src/service/front-door.ts` now serves `GET /` as a self-contained HTML status and session page: service identity and readiness from the data the service already holds, the routes that actually work as links, and an explicit `UI_NOT_BUNDLED` notice naming WER-021 full packaging as the path to the real chamber. The catch-all 404 is unchanged for every other unknown path, and all existing routes keep byte-identical behaviour (identity 200, session 200, events 501).
- The page loads **no external asset**: no `<script>`, no `<link>`, no CDN, no font, no network fetch - it renders offline. Independent QC injected a hostile readiness detail carrying an absolute operator home path and an external `evil.example.com` URL; both were redacted in the served HTML (path to `~`, URL to `[external-url-redacted]`), proving operator paths cannot reach the page.
- New suite `landing.test.ts` 4/4; `service.test.ts` still 13/13; typecheck 0.

## v1.0.16: WER-028 final cohort receipt, and a manifest-drift fix

- Records the WER-028 final integration receipt under `evidence/wer028/`: cohort presence proven by tree/blob comparison rather than ancestry (squash and merge-commit merges make ancestry the wrong test), all four version markers asserted equal, required-check state captured per repository with SKIPPED separated from pass, branch-protection state captured for all three repositories including the 999-setup 404, MALCOM's books/personas/portraits proven byte-identical against the pre-session baseline, Skill 76 proven untouched, cross-repository seam schema hashes compared on both sides, and a deferred list naming every item that remains unproven on this hardware.
- **Fixes a manifest drift this skill introduced on main.** The previous rebuild ran while untracked `evidence/wer028/` scratch files sat in the working tree, so `manifest.json` recorded 16 paths that were never committed: `doctor.mjs` and `verify-cohort-parity.mjs` both FAILED on a clean checkout of main (computed 569 files vs recorded 585). Those 16 paths are now genuinely committed, and every build is re-run only after `git status --porcelain` is empty. The rebuild procedure now carries that guard explicitly.

## v1.0.15: runnable supervisor driver and live crash/restart acceptance (WER-026)

- Adds `scripts/supervisor/runner.mjs`, the missing entry point. The merged supervisor was a pure reducer with no main: `supervisor.mjs` declared `NATIVE_ADAPTER_BINDING = {status: UNKNOWN, bound: false}` and `sweep-executor.mjs` took injected functions, so nothing could actually run - which is exactly why the scheduled-sweep and crash/restart receipts had never existed. The driver wires the existing modules with a durable data directory, an interval loop driving `executePlannedSweep` through an injected execute that only records receipts, a durable restart ledger, singleton/lease refusal for a second instance, atomic graceful drain on SIGTERM, and `--once` for deterministic tests. It imports no `child_process`, no network module and no credential, and reads no `process.env`.
- Fixes a **real defect found by independent QC**: the entry-point guard compared `import.meta.url` to `pathToFileURL(process.argv[1]).href`, which is false whenever the script is reached through a symlink - the process then exited 0 having done nothing, with no tick, no data dir and no output. Because macOS makes `/tmp` a symlink to `/private/tmp`, that was not a rare path. Both sides are now resolved with `realpathSync` (falling back to the lexical path when resolution fails), and a regression test invokes the runner through a symlink and asserts a real sweep happens.
- Records the live host acceptance under `evidence/wer026/host/`, independently reproduced by the reviewer from a fresh clone rather than accepted from the builder's artifacts: two completed sweep ticks; `kill -9` mid-tick (exit 137) followed by a restart that reconciled the pending action **exactly once** with `ledger_generation` 1 to 2 and `fencing_generation` 2 to 3; a second concurrent instance refused with `LEASE_HELD` at exit 3; SIGTERM draining to a valid `STOPPED` state file at exit 0; a temp-root snapshot proving zero writes outside the data directory; and `ps` proving no process left running.

Supervisor suite **113/113** with the pre-existing **99/99** preserved.

**Nothing here claims LaunchAgent registration, launchd firing or reboot persistence** - the launchd step is performed separately by the operator and is not proven by this entry.

## v1.0.14: RP-046-4 card-contract conveyance repair (DEFECT-046-C)

- Closes the D-021 canary Round 1 block where five of nine seats returned parseable JSON whose content still failed the card schema after the one permitted repair. The cause was conveyance, not validation: two format rules (`challenges_answered` entries must be opaque IDs; `conditions[].due_at` must be a UTC ISO 8601 timestamp or null) existed only as zod refinement messages, and the JSON Schema generated from the same definitions **drops refinements**, so in the schema the model actually receives those fields are plain strings — the rules reached the model nowhere. The complete required-field list existed only as the schema's `required` array buried in the input payload, and Round 1 issues no challenge IDs at all, so the model had to guess what `challenges_answered` should hold.
- Adds `runtime/src/cli/card-contract.ts`: the exact contract for *this* call, stated in prose, composed into the request and restated in full in the repair instruction. Required field names are read from the same generated JSON Schema the validator enforces, so the prose list can never drift from the enforced contract. Per-call challenge issuance is stated explicitly, and an advisor call with no issued challenges must return `challenges_answered: []` rather than guess.
- Repair instructions now carry **both** the verbatim validator errors and the original constraints, as Section 15.5 requires; previously only the error strings were forwarded, so every failed seat failed again in the same shape.
- Adds `runtime/tests/rp0464-card-conformance.test.ts` and the accepted-card fixtures under `runtime/tests/fixtures/rp0464/` (`accepted-brene-brown.json`, `accepted-dennis-kimbro.json`, `accepted-michelle-obama.json`, `accepted-russell-brunson.json`).
- Only what the model is *told* changed. The validator, the schemas, the single permitted repair, the ledger and the lease behavior are all unchanged: a non-conforming card still fails validation in exactly the same words as before. `runtime/src/cli/engine.ts` is modified only to compose the contract into the request and the repair.

## v1.0.13: Windows platform observers (WER-027 engineering half)

- Closes the deliberate Windows gap the platform adapter carried: `mounts.ts` previously returned `BLOCKED_PLATFORM` with "no mount table observer" on anything that is not Linux, and `identity.ts` marked Windows `unobservable`.
- Adds `runtime/src/platform/windows.ts`: persistent-versus-ephemeral volume classification using observable `statfs` facts and the drive letter, so a data directory under the Windows Temp root is **refused with a concrete reason naming the path and the rule**; a path resolving *through* a junction is judged by its resolved target, so a temp junction onto a real drive is classified by its destination and a real path reaching temp via a junction is still refused; an uncharacterizable or UNC network volume returns `BLOCKED_PLATFORM` rather than a silent pass; paths containing spaces and non-ASCII characters are handled exactly, with case-insensitive segment boundaries that never prefix-match a sibling (`C:\\Data2` is not inside `C:\\Data`).
- Service identity now records the observable `USERNAME` / `USERDOMAIN` / `COMPUTERNAME` values and keeps the honest `unobservable` marker when none resolve - a name is never invented. Unknown container state returns the explicit `BLOCKED_PLATFORM` path rather than assuming "not a container".
- New suite 14/14; the pre-existing platform suite is unchanged at 16/16 and Linux/macOS behavior is byte-for-byte preserved.

**Nothing here was executed on Windows.** No Windows host and no PowerShell exist on the authoring machine, so every behavior is proven by tests against injected facts, not by running on Windows. Real NTFS geometry, real fixed-versus-removable drive type (no native `GetDriveTypeW` without a shell or native addon), real junction/8.3 resolution, real Windows container detection and an end-to-end `win32` run remain **deferred to a real Windows host** and are not claimed.

## v1.0.12: WER-026 local acceptance receipts (install/update/rollback and 3-round journey)

- Records real acceptance evidence under `evidence/wer026/local/`: the actual installer run into an isolated prefix with staged immutable releases, a repeat install proven byte-identical (prefix diff 0 bytes over 1559 lines), a second build moving the activation pointer while the previous release stayed usable, rollback restoring the prior release, harness invocation from an unrelated working directory returning byte-identical results, no service registered, no launchd loaded and no process left behind, and a model probe reported honestly as `BLOCKED_ENVIRONMENT` (`probe` exits 3 `COUNCIL_FEATURE_NOT_READY` — the dispatcher route is unimplemented and no production code imports `model-probe.ts`).
- Records the create-to-verdict journey under `evidence/wer026/journey/`: three rounds completed with real session ids (`sess-w11u002-round1/2/3`), nine seats x three rounds x nine pack versions in real SQLite state, replay and export delta-0 across all 19 authorization tables, duplicate create refused with `COUNCIL_STATE_CONFLICT`, process restart preserving session ids, cross-round isolation (`COUNCIL_SESSION_NOT_FOUND` across data dirs) and byte-identical round-1 exports across repeats.
- Each receipt was independently re-run by the reviewer in its own scratch prefix rather than accepted from the builder's narrative.

## v1.0.11: platform adapter, remote Access identity, cohort-parity detector

- Adds the OpenClaw VPS/container platform adapter (`runtime/src/platform/`): persistent versus ephemeral mount detection that **refuses** a data directory on a replaceable tree with a concrete reason and an explicit unobserved/`virtiofs` state surfacing as `BLOCKED_PLATFORM` rather than a guess, container-vs-host loopback disambiguation that refuses to treat the current container's `127.0.0.1` as the host, UID/service-identity resolution instead of assuming `localhost`, free-port selection that reuses the WER-021 front door and **never kills** an unrelated listener, and a durable handoff (`wise-elders.platform-handoff/v1`) that restores sessions and reservations across a recreate with zero duplicates. Suite 16/16; the 7 pre-existing runtime failures are unchanged against a detached control worktree at base.
- Adds the WER-023 application-side remote identity adapter (`runtime/src/remote/`): RS256 verification of the Cloudflare Access JWT against an injectable JWKS source with `iss`/`aud`/`exp`/`nbf` enforcement, so **an arbitrary forwarded identity header never establishes identity** — it is read only after a JWT verifies. Exact allowed-origin set membership (never suffix matching), a single-owning-endpoint session URL resolver that can never emit two candidates, customer-disabled operation that keeps local/managed working, reauthentication that resumes the same session with **zero** billable Starts, connection loss that is never reinterpreted as cancellation, and cross-user refusal that leaks neither user nor session existence. Suite 13/13 with zero network calls asserted. Real device acceptance remains deferred to WER-026/027.
- Adds the read-only cohort-parity detector (`scripts/verify-cohort-parity.mjs`): recomputes the manifest tree hash exactly as `build-bundles.mjs` does, asserts all three version markers agree with the newest CHANGELOG entry, and catches the G3 condition (skill content moved without `skill-version.txt`). Exits nonzero naming the offending file and expected value; writes nothing and makes zero provider calls. Suite 9/9, script suite 35/35.

## v1.0.10: standalone Council front-door service

- Adds the standalone persistent service (`runtime/src/service/`): layered readiness with zero provider calls when offline, duplicate-start protection that reuses only a **verified matching** service and refuses an unrelated listener without killing it, true verified session URL return with browser-open failure preserving the URL, and graceful drain on stop.

## v1.0.9: waves 5-6 cohort (route discovery, durable budgets, capability probe, supervisor HYB-03/04)

- Discovers Council routes from the actual OpenClaw host layout (`runtime/src/cli/route-discovery.ts`): non-default config and state roots without any `~/.openclaw` assumption, JSON5 host configuration, named secret **references** that resolve only at flight time with the value asserted absent from errors, logs and receipts, explicit failure for unsupported API families and ambiguous model selection with no silent substitution, and freezing through the WER-006 snapshot contract so downstream transport consumes one shape.
- Adds durable budgets (`runtime/src/budgets/`) and wires them into the CLI host (`runtime/src/cli/local-host.ts`, `budget.ts`, `leases.ts`): the tightest applicable ceiling wins over runtime defaults, per-operation reservations commit before dispatch, lease fencing generation flows from the durable store rather than a process-local counter, unknown outcomes stay reserved while known-rejected ones release, and renewal adds capacity without erasing history. Two concurrent admissions against one bound produce exactly one winner across separate store instances.
- Adds the historically-unready bounded capability probe (`runtime/src/cli/model-probe.ts`): purpose-bound grant, route snapshot verified before any spawn, operation/attempt identity recorded before launch, and three distinct outcomes — attempted, answered, schema-qualified — so a refused, failed, malformed or timed-out probe can never set a callable success state. One token never qualifies a complete Council.
- Extends the engineering supervisor with HYB-03 and HYB-04 (`scripts/supervisor/`): deterministic health collection, staffing comparison with expiring underfill exceptions, an incident/action journal with counters that survive restart, a QC-backlog trigger, launchd plist and validated start/status/stop/restart command arrays as artifacts (nothing registered or loaded), an independent due+30s overdue detector that fires even with a live PID, and restart reconciliation over durable pending actions. Supervisor suite: 99/99 (47 original preserved).

## v1.0.8: wave-3 cohort (subprocess transport, approval front door)

- Adds the platform-safe bounded subprocess transport (`runtime/src/cli/`): a structured executable resolver handling native binaries, Windows `.cmd` shims and supported PowerShell invocation without assuming WSL, bash shebangs or symlinks; per-request model/effort and profile config pinned rather than read from a mutable global; prompt content delivered **only** on stdin and never interpolated into a shell string; bounded output, enforced deadlines, abort propagation and whole child-process-tree cleanup on cancellation. A Windows path containing spaces and non-ASCII characters resolves byte-intact in the simulated-resolver tests.
- Records `operationId` and `attemptId` **before** launching, so a timeout is recorded as potentially-dispatched rather than safe-to-retry. A route snapshot failing `verifyRouteSnapshotHash` is refused before any spawn.
- Adds the approval front door (`runtime/src/authorization/`): fingerprinting over the entire normalised approval command — ceilings, expiry, parent/renewal linkage and route options — so an exact retry returns the original committed receipt while a changed option under the same idempotency key conflicts **before** any write. Preview-to-session association is validated, so submitting one session's preview to another's approval URL performs zero grant, state or event writes even under the same owner. Revoked and expired authority both refuse without mutating. Reuses the existing grant service; Council spending authority stays distinct from development merge permission and from action-plan execution authority.

## 1.0.7 - 2026-10-18

Integrate four supplied Oprah and Les book mappings, partial source qualification and governance discovery. Publish the verified 105-persona index. Preserve the landed 1.0.5 queue/supervisor and 1.0.6 route-snapshot/installed-CLI implementations; regenerate the combined distributable.

## v1.0.6: wave-2 cohort (frozen route snapshot, installed-CLI bridge)

- Freezes the normalized route snapshot contract (`runtime/src/providers/`, schema `wise-elders.route-snapshot/v1`): session owner, route and account reference, host/config selection, API family, requested model or combination alias, permitted members and fallbacks, requested / supported / applied reasoning kept distinct, capability version, policy hash and rate/concurrency limits. Configured identity and transport-reported identity are separate fields, and an unreported provider member stays explicitly `UNKNOWN` rather than being assumed. The snapshot carries a stable hash that WER-007, WER-008 and WER-009 consume instead of inventing their own route shapes.
- Pins the member **set** while excluding per-member transport evidence from the pin body, so recording evidence later can never move the pin on a combination route. `withTransportReportedIdentity` now also recomputes authoritatively rather than re-asserting the stale published stamp.
- Resolves the installed Council CLI through the WER-004 release receipt (`runtime/src/bridges/`), independent of the current working directory or a checkout's `dist` folder, and propagates route-discovery diagnostics and the real route catalog through the bridge wrapper instead of swallowing them. A missing or invalid receipt fails with a concrete recovery action, and a failed browser open preserves the usable URL.
- Replaces a frozen `readdirSync` directory literal in the bridges test with a membership check that still fails on a missing module and on a stray file, so a deliberate addition no longer breaks it.

## v1.0.5: wave-1 repair cohort (supervisor, installer, durable producer)

- Adds the engineering supervisor bootstrap (`scripts/supervisor/`): a deterministic ~60s health observer, a 600s full-sweep planner written as a pure function over injected time, durable leader/fencing-generation state, and the STARTING/HEALTHY/DEGRADED/PAUSED/STOPPING/STOPPED machine with the explicit-stop fence. Policy ships as `wise-elders.hybrid-supervisor-policy/v2` with `binding_status: TEMPLATE_NOT_BOUND`. Native-adapter binding is deliberately left `UNKNOWN` rather than invented.
- Rewrites `scripts/install-runtime.mjs` so the exact-executable Node prerequisite probe (`node:sqlite` in-memory write/read/close plus an isolated persistent reopen) runs before any file is written, installs into a staged immutable external prefix, hashes protected SOURCE only — never `node_modules` or `dist` — and activates atomically while preserving the previous receipt.
- Adds the canonical durable operation producer (`runtime/src/queue/`): admission commits transition, job and event/outbox in one owning-store transaction, a QUEUED row without its job is rejected, `attemptOrdinal` survives restart and `leaseGeneration` is rechecked on every mutable commit. No second scheduler was introduced.

## v1.0.4: Russell retained-source intake

- Registers DotCom Secrets and Expert Secrets via Skill22 and binds ten original paraphrases to retained-source hashes and edition-specific locators.
- Records primary-teaching coverage for both Russell anchors without upgrading other seats, semantic evaluation, full-book certification or installed readiness.
- Preserves private-source exclusions and publishes the approved two-persona incremental index as prebuilt-index-v2.4.3 (101 personas / 1,441 rows), with every prior row unchanged.

## Unreleased: final packaging (CWE-039)

No version change: versions are taken at merge time only. This entry
records the final packaging of the complete package whose runtime and
nine advisor packs landed in their own units after the v1.0.0
scaffold.

- Runtime and packs: the deliberation runtime, the standalone CLI,
  and all nine advisor packs ship in this package. Every pack's
  qualification is bibliographic_only (CWE-042); config/advisors.json
  pack_status now reads built_bibliographic_only for all nine seats.
- Distributable archive: scripts/build-bundles.mjs now generates
  council-of-wise-elders.skill at packaging. The archived Brunson
  pack copy has the private_scope items removed and prose references
  to them scrubbed (CWE-012 acceptance condition 3); the source tree
  retains the private-scope record.
- Install path: scripts/install-runtime.mjs performs the real
  isolated pinned install plus build (INSTALL.md Step 4), and
  INSTALL.md Step 9 states the live-acceptance terms for the built
  package, including the INSTALLED_NOT_LIVE_VERIFIED record when no
  live run is authorized.
- Housekeeping: the Wave 6 roster comment in lib-onboarding-state.sh
  and the structural test banner no longer describe the package as a
  scaffold with an unbuilt runtime.

## v1.0.0: Initial canonical scaffold

- Adds the agentskills.io-conformant SKILL.md with the fixed nine-seat
  roster, the exact Section 7 profile label discipline, and the Section
  20.1 front-door phrases with existing-session control resolution.
- Ships the portable package structure: install guide in the literal
  installer-contract order, instructions, examples, core updates,
  prereqs, configuration defaults, references (protocol, scoring,
  source policy, model routing, report template, install matrix,
  troubleshooting), and QC rubric plus bundled QC scripts.
- Registers the skill with the onboarding installer: glob discovery
  counts the folder, the Wave 6 roster in lib-onboarding-state.sh gains
  an explicit entry, the skill-department-map gains the skill 77 entry,
  and the Council deliberation SOP registers in universal-sops.
- Update-flow safety: no council state is stored inside the skill
  folder, so wholesale folder replacement by the update sync cannot
  destroy sessions, briefs, verdicts, or client knowledge.
- Honest scope: the deliberation runtime (runtime/), the standalone
  CLI, the Skill 22 exporter, and the nine advisor knowledge packs are
  scaffolded and marked not-yet-built. They are owned by their own
  build units and are not simulated here. The front door reports the
  council as not ready until they land.
