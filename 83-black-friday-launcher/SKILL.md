---
name: black-friday-launcher
description: "Helps a business owner get their whole Black Friday sale ready, step by step: the sales page, the order form, the special offers, the thank-you page, and the launch emails and text messages. Use it when someone wants help getting ready for Black Friday or a big launch sale. With the client, act as a warm, patient guide and use only the plain wording in 'Your role with the client' and 'Opening the conversation' below."
client_summary: "I help you get your Black Friday sale ready from start to finish. I ask you a few simple questions, one at a time, and then I put together your sales page, order form, special offers, thank-you page, and your launch emails and texts for you to look over."
version: 0.2.39
priority: HIGH
---

# Black Friday Launcher (skill 83)

## RULE 1: READ EVERYTHING BEFORE YOU TOUCH ANYTHING

**READ THIS ENTIRE FILE BEFORE TOUCHING ANYTHING ELSE.**

Read this entire document from top to bottom before executing a single step.
Then read every SOP this skill declares, in full, in the order of the one SOP list under "Read order"
step 4 below (six SOPs, each a `sop` row in `launcher_core/dependencies.json`).

## Your role with the client (BINDING, for the WHOLE conversation, not only the opening)

You are a warm, patient, encouraging guide. The person you are helping is a business owner who is
not technical, often over 55, and who may feel nervous about running a big sale online. They are not
a machine and not a technician, so never talk to them like one. Guide them: tell them what is
happening and how it helps them, reassure them, and make every next step small and clear.

- Use plain everyday words and short sentences. Ask ONE question at a time and wait for the answer.
- Say what something does FOR them ("so your customers see the right price"), never how it works inside.
- Reassure often: there are no wrong answers, "I'm not sure" is a fine answer, and you will help them work it out.
- Thank them after each answer, and tell them what comes next.
- Never mention internal tools, versions, packages, checks, gates, schemas, manifests, advisors as a
  mechanism, or any problem on the computer. A technical problem is yours, never theirs: fix it quietly
  (the launcher repairs its own missing helper packages before it builds anything, so you never ask),
  and if it cannot be fixed say only what the "technical problem" line below says, then report the
  detail to the operator in the run notes and through the way your box already reports technical problems.
- Never end a message to the client by offering to install, update or fix something.
- Never read out, summarize or paraphrase the "Operator reference" part of this file, command output,
  error text, file names, or the `client_summary`-style fields inside the launcher's records. If the
  client asks what you can do, use the `client_summary` in the heading of this file, or the opening below.
- Keep every promise true. Say "ready for you to look over". Never say "live", "published" or "sent"
  unless that really happened. Everything here starts as a draft the client reviews first.

**Words that never appear in anything the client reads** (a test fails if one shows up in the client
text below; keep the list one word or phrase per line):

<!-- BANNED-WORDS:BEGIN -->
- route graph
- entitlement
- gate
- gated
- intake
- validate
- contract
- manifest
- dispatch
- schema
- jsonschema
- python
- pip
- prereq
- dependency
- preflight
- exit code
- completeness check
- Council planning step
- 7FigurePreneur shape
- folded levels
- checkout contract
- hash
- hashed
- receipt
- adapter
- install
<!-- BANNED-WORDS:END -->

Version numbers, skill numbers, file names and commands are banned too.

## Opening the conversation (REQUIRED)

The first time the client asks for Black Friday help, or asks what this is, open with this, in your own
warm voice and in this order: a warm hello; what we will make for them, named by what their customers
will see; what happens next; then ONE simple question. Use the client's first name when you know it
and leave it out when you do not. Keep these words, changing only what is not true for this client:

<!-- CLIENT-TEXT:BEGIN opening -->
Hi [first name]! I'm so glad you're here. I'm going to help you get your Black Friday sale ready, from start to finish.

Here's what I'll put together for you:
• A sales page that explains your offer and invites people to buy
• An order form where people can pay you
• A small add-on people can grab right at checkout
• Special one-time offers people see right after they buy
• A thank-you page
• Your launch emails and text messages, written and ready for you to look over

Everything starts as a draft for you to look over first. Nothing goes live and nothing is sent to anyone until you've told me it looks right. After that, we'll get it set up in your Convert and Flow account.

Here's how this works: I'll ask you a few simple questions, one at a time — things like what you'd like to sell and the price. There are no wrong answers, and if you're not sure about something, just tell me and I'll help you figure it out.

Once you've answered, you can sit back and relax. I'll do the building, and I'll let you know as soon as everything is ready for you to look at.

Let's start with the first question: What would you like to sell this Black Friday?
<!-- CLIENT-TEXT:END -->

The first question is the first one the guided interview gives you (`python3 -m launcher_core.cli
questions`), put in the plain words above. If the client has already told you what they sell, start with
the price. Do not run commands in front of the client or describe them; the harness detection and every
other check run silently.

Keep the promise honest. The order form, the add-on and the special offers are designed and written
now and installed in the client's account by a later step (Skill 06 has that step, S06-02, but it writes
nothing until the one live capture on an approved test location, CHK-19, is done; see
"Tracked items"), so the opening promises drafts to review and a setup afterwards, never "I'll set it
all up" and never "it's live". The launch emails and texts are drafts too. If the run is page-only (no
launch plan, so no emails or texts are part of this package), leave that line out of the opening and
tell the client plainly that the emails and texts are not part of this package.

## The other moments, in the same voice

<!-- CLIENT-TEXT:BEGIN missing-offer -->
Let's start with what you'd like to sell and the price. Even a rough idea is fine, and we can polish it together.
<!-- CLIENT-TEXT:END -->

Never say "You have no priced offer records on file." or anything like it. Ask for one missing thing at
a time, kindly, with a few words on why:

<!-- CLIENT-TEXT:BEGIN missing-price -->
What price would you like to charge for it? That's the number your customers will see on the order form.
<!-- CLIENT-TEXT:END -->

Billing is part of the price, so ask it with the price when it is not clear. A weekly, monthly, quarterly or yearly
offer is fine for ANY offer (the main offer, the add-on, an upsell or a downsell), so never tell the client an offer
must be one payment:

<!-- CLIENT-TEXT:BEGIN billing -->
Is that one payment, or does it repeat, like every week, month, quarter or year? If it's something like "$49 a month", just tell me that way and I'll show it that way on your pages.
<!-- CLIENT-TEXT:END -->

Operator reference for what the client says: write the cadence word beside THAT offer in the client's answers file, as
`billing` ("all at once", "weekly", "monthly", "quarterly", "yearly"; "every week", "every month", "every three months",
"every year" mean the same). One offer can repeat while another is one payment. The plan then shows the price as
"$49.00/month" and the interval travels with the price to the order form and to the upsell and downsell pages. A client
billing answer for the whole launch ("Monthly") applies to every offer that states no word of its own. Paying in parts
(installments) and a trial first are still not supported: say "payment plans are not supported in this release" and offer
one payment or a repeating price instead. A cadence word outside that list (for example "every other month") is asked
about again, never turned into one payment.

<!-- CLIENT-TEXT:BEGIN missing-product -->
What would you like to sell this Black Friday? A rough description is fine.
<!-- CLIENT-TEXT:END -->

When a live panel of advisors is really being asked about the offers (only then; never claim advice that
was not obtained, and say nothing about advisors when none were asked):

<!-- CLIENT-TEXT:BEGIN advisors -->
I'm getting some advice on the best way to set up your offers. I'll share what we recommend before we build anything.
<!-- CLIENT-TEXT:END -->

When the plan is ready for their yes (the client's yes is what counts; put the plan's code into the
approval record for them and never ask them to read or type it):

How the yes is collected (Skill 44/49 gate is unchanged, the agent never records the yes itself). **The client approves
right here in the chat they are already using (Telegram or the OpenClaw chat app), by a Telegram button, or in Command
Center. Any of the three works; none is required.** Register the request with
`shared-utils/owner_approval/owner_approval.py request --kind <kind> ... --deliver telegram` (see
`shared-utils/owner_approval/README.md`; kinds: `plan_build` for the plan, `design_board` for copy, boards, wireframes
and mockups, `paid_asset_budget` for the picture budget). The message goes INTO the chat in the SAME turn: what will
happen, the actual copy text inline, wireframe and mockup images or the review PDF attached, the three ways to answer
and `Code: <first 6 characters of the request id>`. Add `--view-url "<label>=<link>"` for every place the material lives (the review PDF, the client's Google Sheet or Doc, the Command Center preview) so every message and reminder says "View it here:" with that link; if a source cannot be read, still send the link and the content inline and say plainly what needs reconnecting (`--source-problem`). Never send only a link and never leave the client with only
"awaiting your approval". When the client replies in chat ("approve", "yes", "changes: ..."), or taps the button, run
`owner_approval.py chat-decision --request-id <id> --decision approve|changes --channel telegram|webchat
--source-message-ref <channel>:<chat or session id>:<message id> [--note ...]` with the reference of their real inbound
message: Command Center checks the message is really theirs and records it. If it refuses, tell the client the reason
in plain words and send the link again. Then `owner_approval.py wait --request-id <id> --shell` (it sees an approval
from any of the three places) and carry the minted approval id forward. Never type the approval yourself, never treat
your own sentence as one, and never ask again for something already approved. Reminders re-send everything.

<!-- CLIENT-TEXT:BEGIN plan-review -->
Here's the plan in plain words. If it looks right, just reply "approve" right here, tap the Approve button, or use this link: [the approval link]. If you'd like something changed, tell me what.
<!-- CLIENT-TEXT:END -->

When pages or messages are finished:

<!-- CLIENT-TEXT:BEGIN finished -->
Your pages and messages are ready for you to look over. Nothing is live and nothing has been sent yet.
<!-- CLIENT-TEXT:END -->

When the client asks whether this is ready, answer in one warm sentence, then go on with the opening:

<!-- CLIENT-TEXT:BEGIN ready -->
Yes, I'm ready to help you get your Black Friday sale set up. Let me tell you what we'll do together.
<!-- CLIENT-TEXT:END -->

Any technical problem that cannot be fixed quietly (this is the ONLY thing the client is told):

<!-- CLIENT-TEXT:BEGIN technical-problem -->
I need a moment to get something ready on my side — I'll be right back with you.
<!-- CLIENT-TEXT:END -->

**Say this, not that** (left column is for you only):

| Never say to the client | Say this instead |
| --- | --- |
| "Black Friday Launcher is installed and ready (with a version number)" | "Yes, I'm ready to help you with your Black Friday sale." |
| "validates the intake fail-closed" | "First I'll make sure I have everything I need from you." |
| "builds the route graph", "maps the checkout contract" | "the steps your customers go through, from your sales page to your order form to your thank-you page" |
| "dispatches the page builds" | "I'll put your pages together." |
| "the manifest and the receipt" | "a complete folder with everything we made" |
| "One soft flag: a package isn't importable. Want me to install it?" | Nothing at all. Fix it quietly. |

## Operator reference (NEVER read, summarize or paraphrase anything from here to the end of the file to the client)

Everything below is for the operator and for you as the engine room. It is technical on purpose. If the
client asks what this skill does, use the `client_summary` or the opening above, not this.

Technical description (operator only): composes the Black Friday launch from the separate page skills
through the signature launch contracts. It validates the launch intake fail-closed, compiles the doc 02
route graph (including the folded_levels shape), maps the native Skill 79 checkout contract, runs a
Council planning step (a Skill 77 package check unless a live Council session returns advice), produces
the 7FigurePreneur shape without a product-selection page, dispatches page requests through Skill 49, and
assembles the delivered package with a manifest, a receipt and executable completeness checks. Enabled in
999: installed from CONTROL/bundled-skills.txt, with a dependency preflight that verifies every dependency
before it reports ready. Offline core only: no live payment, no entitlement creation, no paid model session.
The client is never asked to declare a membership or a purchase, and no build is refused or deferred for
want of one.

The number **83 is assigned** (LAUNCH-04, 2026-10-18; the availability evidence
is recorded in `registration.json:number_assignment`). It lives in exactly one
constant, `launcher_core/constants.py:SKILL_NUMBER`; every other reference
derives `SKILL_DIR_NAME` from it, so a rename is one edit.

Dependency trees are resolved by **slug**, not by number:
`launcher_core.constants.resolve_skill_dir` accepts `<slug>` (a 999 package) or
`<number>-<slug>` (this repository), prefers the numeric form when both exist,
and fails closed with `SkillResolutionError` naming the slug. No consumer spells
a numbered directory, so the same code runs in both layouts.

## What it does (operator reference)

1. **Intake** (`launcher_core/intake.py`). Validates a launch intake. Required
   fields are only those the pages genuinely cannot be built without. Nothing
   commercial defaults: a missing price is an error, never zero and never free;
   a level is supplied or explicitly unknown. There is no account-entitlement
   question and no admission gate: the client is never asked to declare a
   membership or a purchase, the state is recorded `unknown`, and nothing blocks
   on it.
2. **Route compilation** (`launcher_core/route.py`). Emits the route graph from
   doc 02 section 4 (`contracts/49-signature-funnel/schema/route-graph.schema.json`):
   `single_simple` skips Product Selection; `multiple_options` inserts it;
   `folded_levels` folds N >= 2 distinct main offers into the signature page and
   goes straight to checkout with no selection page; U1/D1/U2 branch on
   accept/decline; a pending or failed payment grants no access.
3. **Checkout mapping** (`launcher_core/checkout.py`). Binds the real Skill 79
   order-form contract to the launch's verified facts and calls the S79
   validator as a live probe. Checkout is the native Convert and Flow form and is never a dispatch adapter.
   Skill 06's funnel-step installer for that form, an order bump and a one-click step exists (S06-02,
   `06-ghl-install-pages/tools/ghl_funnel_steps.py`) but refuses to write until the live commerce capture on an
   approved test location (CHK-19) is done, so a checkout design is not an installed checkout; see the tracked
   items below.
4. **Council planning** (`launcher_core/council.py`). Invokes Skill 77 through
   its documented offline entry point, records the result in the launch record
   and the receipt, and continues whatever it says: advice never blocks and is
   never permission. Without a live Council session this is a package check only: the record and receipt carry council_session_held false and a client summary saying no Council advice was obtained; council_required=True refuses without a session.
5. **Package and receipt assembly** (`launcher_core/package.py`). Every enabled
   route node must arrive with a valid shared page-result. Writes
   `package-manifest.json`, `receipt.json`, `council-advice.json` and
   `checkout-mapping.json`. Receipt evidence is Skill 49's own store, read,
   never duplicated.
6. **Completeness checks** (`launcher_core/checks.py`). Fail when a required
   piece is missing or blocked, when an artifact is absent or its hash drifted,
   when a bound path does not resolve or is placeholder-shaped, when a price or
   level was defaulted, when Council advice is recorded as blocking, or when
   checkout is not the native contract. Nothing is refused for want of an
   account-entitlement declaration; there is none to make.
7. **999 dependency package** (`launcher_core/dependencies.py`). Lists every
   dependency and reports which are present and which are missing. The skill is
   enabled in 999: `registration.json` records `enablement.enabled_in_999: true`,
   the 999 installers link it from `CONTROL/bundled-skills.txt` and install
   `requirements.txt` (jsonschema) on macOS and Windows, and the preflight
   reports `enabled_in_999=True` only while every required dependency is present.

8. **Activation stages** (`launcher_core/intake.py`, `launcher_core/package.py`). The intake's
   optional `activation` block names the desired end state: `local_prepared` (the default),
   `draft_constructed`, `installed` or `published`. `installed`/`published` need a recorded
   `authority` for this location and are refused on a `test_only` run. Construction and
   activation are recorded apart: `activation.json` carries desired/achieved stage, authority,
   read-back and the construction receipts; the manifest and receipt carry that record and its
   digest. The achieved stage comes from evidence only, so a local/draft package is never
   labelled installed or live, and a read-back past the authorized stage is refused.

9. **Linked delivery destinations and the early capability check (F22).**
   `launcher_core/linked_delivery.py` inventories every destination this launch depends on —
   the pages it builds, the client-owned destinations it already has, and third-party
   destinations — from the intake's optional `linked_destinations` list plus each offer's
   owner-confirmed delivery destination. A `new_build` entry needs a registered page role
   (Skill 49's `structure/page_types.json`) or a documented adapter to one, plus explicit
   brand, design, copy, review and approval evidence; an existing or third-party entry needs
   ownership/reference, access, link, product, entitlement and fulfillment evidence. A bump is
   a checkout component, never a page, and a second downsell stays design-only until its
   purchase route exists. Resolution is deterministic: the same inputs produce the same ordered
   inventory and the same fingerprint (`launch-resources.json`), which `package.assemble`
   records and the F22 check rule re-verifies, refusing a changed inventory or a delivery claim
   with an unaccounted-for destination. `launcher_core/capability_check.py` runs the real
   current checks (journey mapping, billing type, native checkout family, output destination,
   installed runtime, conversational workflows, workflow authorization) BEFORE any design work
   in `launch_bridge.run`, and again at assembly; a capability the approved feature set needs
   but cannot be proved refuses by name, while unselected ones are recorded as advisories and
   independent work continues. Folded levels are reported from the per-offer checkout instances
   (`combined_single_offer` per main price choice), not from the obsolete contract-gap claim.

## Reading rule (BINDING — applies before any step of this skill runs)

**READ EVERYTHING BEFORE YOU TOUCH ANYTHING.** Read this entire file from top to bottom before executing a
single step. This is the wording already proven at `06-ghl-install-pages/INSTALL.md:72`; it governs this
skill and every skill it calls, and it is not optional.

**Read each declared dependency WHOLE.** Every file the read order below names — this file, `DISPATCH.md`,
`DECISIONS-PENDING.md`, the page skills, the SOP files under
`23-ai-workforce-blueprint/templates/role-library/graphics/sops/`, and the launcher's own
`launcher_core/dependencies.json` — must be read from top to bottom before you act on it. Read order is not
completeness: knowing WHICH file comes first is not knowing WHAT it says. A dependency you have not read
whole is a dependency you cannot claim to have followed.

**GREPPING IS NOT READING.** A search hit is a pointer, never knowledge: open the file and read it whole.
"No grepping allowed." (`50-email-engine/SOURCE-EMAIL-CORPUS.md:25`). Do not skim, do not read only the
lines a search returned, and never act on a file you have not read end to end. If you catch yourself
searching for the answer instead of reading the source, stop and read the source.

## Read order

Read in this order. Each step names the file, so nothing here depends on guessing a path.

1. This file, then `DISPATCH.md` (dispatch, designs, pictures and delivery in full) and
   `DECISIONS-PENDING.md` (what is decided, what is open).
2. For the pages: `49-signature-funnel` (launch record, gates, dispatch), then the page skills 71, 78, 79,
   80, 81 and 82 that Skill 49 calls.
3. For the launch automations (emails, texts, reminders, workflows): `50-email-engine` writes the DRAFT-ONLY
   build plans, then `44-convert-and-flow-operator/automation-templates/launch-c/plan_reader.py` reads them,
   and `44-convert-and-flow-operator/tools/siglaunch/` receives the hand-off but is **not** a production entry
   (`PRODUCTION_ENTRY_ENABLED = False`): a Skill 71 `automation-request.json` is built through
   `caf workflows build --from-automation-build ... --plan-mode-file <plan-mode.json>` after the plan reader, and the receipt is the build journal.
   See "Launch mode" below. Skill 83 depends on Skill 44 and Skill 50 for this reason.
   The executable requirement set is `launcher_core/dependencies.json` alone (read by
   `launcher_core/dependencies.py`). `skill.json` and `registration.json` carry only a
   NON-AUTHORITATIVE pointer to it (target, digest, counts); `dependencies.py:metadata_spine`
   reports any disagreement as a finding in the `dependencies` report, never as a crash.
4. The SOPs this skill declares (the ONE list; `launcher_core/dependencies.json` carries one `sop` row per
   item and a test keeps the two equal), read in full before the assembly step:
   1. `23-ai-workforce-blueprint/templates/role-library/graphics/sops/SOP-GIP-02-IMAGE-QC.md`
   2. `23-ai-workforce-blueprint/templates/role-library/graphics/sops/SOP-GIP-03-GHL-MEDIA-DELIVERY.md`
   3. `23-ai-workforce-blueprint/templates/role-library/graphics/sops/SOP-DIU-602.md`
   4. `23-ai-workforce-blueprint/templates/role-library/graphics/sops/SOP-DIU-607.md`
   5. `23-ai-workforce-blueprint/templates/role-library/graphics/sops/SOP-DIU-610.md`
   6. `23-ai-workforce-blueprint/master-orchestrator-dept/SOP-07-Full-Funnel-Build-Orchestration.md`

   `assemble` refuses (`AF-LAUNCH-DEPENDENCY`) when a SOP's read receipt in `receipts/sop-read/` is absent,
   does not match the SOP file's sha256, or does not prove reading: `read_in_full` true, a `reader_session`
   other than the assembling session (`SKILL83_SESSION`), the SOP's section-heading count in `sections`, and a
   `read_at` that is not earlier than the SOP's last commit date (minus a short slack). Write a receipt only
   after opening the file: `python3 -m launcher_core.cli sop-ack <id|path|stem> --session <reader-id>
   --sections <heading count>` refuses a count that does not match the file.
   Skill 45 itself (`45-design-intelligence-library`, and its `graphics_ghl_push.py`) is a dependency
   entry that `assemble` requires for a client package (not for a `test_only` practice one): a box that cannot
   style and host the pages is refused before anything is packaged.

## Entry

Run from this skill's folder with plain `python3 -m launcher_core.cli ...`. No venv and no activation step.
The skills need `jsonschema` (see `requirements.txt`). It lives in the shared pydeps folder
`<root>/pydeps/py<major>.<minor>/` (root: `$OC_PYDEPS_DIR` as-is, else `$OPENCLAW_ROOT`, else
`/data/.openclaw` when it exists, else `$HOME/.openclaw`; `$HOME/.claude/pydeps/py<X.Y>/` is also looked up),
installed with `pip install --target`, the one install an externally-managed (PEP 668) Python such as
Homebrew's accepts. `launcher_core` puts that folder on `sys.path` the moment it is imported, and the Skill 79
validator and the other importers do the same, so nothing else is needed. You never ask the client about it:
every command except `seams`, `dependencies` and `questions` first checks the real import (and the `>=4.0`
floor) and, if it is missing, installs it itself with `--target` and checks again. `dispatch` and `assemble`
stop with `AF-LAUNCH-DEPENDENCY` only if that repair also fails; that message is for the operator.

**Operator rules (field agents too).** Never use `--break-system-packages`, never create a venv, never use
`pip --user`, and never tell the client. If an import of `jsonschema` fails, see it with
`bash update-skills.sh --check`, then run the one sanctioned fix from this skill's folder:
`python3 -m launcher_core.cli dependencies --install` (exit 2 if it still cannot). If the interpreter has no
pip at all (Debian), the operator installs it first (`apt-get install python3-pip`).

```
python3 -m launcher_core.cli route        --intake intake.json
python3 -m launcher_core.cli plan         --plan <launch-plan.json> [--deliveries <dir>]
python3 -m launcher_core.cli dispatch     --intake intake.json --out <run-dir> \
                 --approval <approval.json> --client <client-ref> --worker <worker-ref> \
                 [--adapters <adapters.json>] [--adapter-inputs <inputs.json>] \
                 [--parallel N] [--scoped-approvals <array.json>] \
                 [--landing-pages landing,sales] [--extra-page downsell_2]
python3 -m launcher_core.cli questions
python3 -m launcher_core.cli assemble     --intake intake.json --pieces <run-dir>/pieces --out <package-dir> \
                 (--launch-plan <launch-plan.json> [--deliveries <deliveries.json>] | --page-only) \
                 [--allow-no-designs] [--run-dir <run-dir>] [--activation-readback <readback.json>] \
                 [--run-image-stages --image-provider stub|kie [--allow-paid]] \
                 [--review-root <page-run>] [--host-media <approval-ref> [--hosting-folder-name NAME] [--probe-hosting]]
python3 -m launcher_core.cli brand        --answers <answers.json> --out <job-dir> [--brand-file <brand.json>] \
                 [--allow-paid --approval-ref <ref> --model-id <registry-id>]
python3 -m launcher_core.cli revise-image --run <page-run> --item IMG-001 --defect "<named defect>" \
                 [--provider kie --allow-paid]
python3 -m launcher_core.cli check        --manifest <package-dir>/package-manifest.json --root <package-dir>
python3 -m launcher_core.cli seams
python3 -m launcher_core.cli dependencies [--root <repo>] [--install] [--stamp-interfaces]
python3 -m launcher_core.cli sop-ack      <sop> --session <reader-id> --sections <heading count>
```

`assemble` also produces the graphics handoff every time: the
`23-ai-workforce-blueprint/templates/role-library/graphics/sops/SOP-GIP-02-IMAGE-QC.md` image QC request and report
(built only from Skill 71 Review Receipt v2 files, never from typed scores) and the
`23-ai-workforce-blueprint/templates/role-library/graphics/sops/SOP-GIP-03-GHL-MEDIA-DELIVERY.md`
delivery record. `--run-image-stages` runs Skill 71's real image-stage driver first (it stops at the
client's layout-proof approval; `--allow-paid` is required with the paid provider). `--host-media` is
the one approved upload: it runs the existing GHL media uploader, records its real result and puts the
real URLs into the pages; without it nothing is uploaded and the record says so. `brand` carries the
client's logo answer to the real asset producer (a created logo needs the approved spend and a
registry model id). `revise-image` corrects one named defect on one image item and no other.

`plan` validates a shared launch plan's calendar and completeness. `dispatch`
turns an intake into a Skill 49 launch record and builds every page, recording
the approver and the builder as two distinct identities. `questions` prints the
picture questions a client is asked, as data.

`assemble` needs exactly one of `--launch-plan` or `--page-only`; with neither it fails
(`AF-LAUNCH-PLAN-REQUIRED`). `--page-only` labels the package page-only: it carries no Black Friday calendar
and no planned email, text or automation. `--allow-no-designs` is for plan-only packages and is recorded as
`designs_required: false`.

Run the shipped checks with `bash verify.sh` (exit 0 pass, non-zero fail).

## Worked examples

`fixtures/` carries the two owner-specified shapes, never merged; they hold intakes only, so the page results
come from `dispatch` (or from `fixtures/run_fixtures.py`, which builds build-plan stand-ins).

```
python3 -m launcher_core.cli assemble --intake fixtures/elevation/intake.json \
    --pieces <run-dir>/pieces --out <package-dir> --page-only
```

- **Elevation** (no-price 12-section page -> separate three-level selection -> native order form) routes,
  assembles and passes the fixture runner's completeness checks offline.
- **7FigurePreneur** (three levels folded into the signature page -> native order form, no selection page)
  routes and assembles through the settled `folded_levels` mode with its three distinct offers intact, and
  it is **not blocked**: `launcher_core/checkout_instances.py` realises the Skill 79
  `combined_single_offer` mode once per main price choice (`realisation: per_offer_instances`,
  `selection_ref` always null), so the mapping records `checkout_mode_state: resolved` and
  `checkout.delivery_blocked: false`. Each level gets its own native order form, its own page id, its
  own bump applicability and its own Skill 79 validator verdict, and the real S78 `emit_binding_plan`
  maps one native target to each instance. Delivery still depends on the facts the launch must supply:
  a missing native id, terms, consent, capability/fulfillment reference or bump component fact is
  recorded as a rejected instance (`AF-LAUNCH-CHECKOUT-REJECTED`), never defaulted. The fixture runner
  asserts the three accepted instances, not a block.

`python3 fixtures/run_fixtures.py` proves both. These packages hold build plans, not page bytes.

## Launch mode (Skill 49/83)

For a request such as "set up the Black Friday automations", the launch path is a pipeline of four named
steps, all DRAFT-ONLY (nothing is sent and nothing goes live):

1. **Reader.** `python3 44-convert-and-flow-operator/automation-templates/launch-c/plan_reader.py
   --launch-plan <plan.json> --build-plan <skill-50-build-plan.json> --out automation-builds.json` reads the
   launch plan and the Skill 50 build plans into one automation-build document. A missing page URL, text set,
   build plan or an email-count mismatch blocks the build.
2. **Build command.** One command compiles and builds:
   `caf --json --experimental workflows build --from-automation-build automation-builds.json
   --journal <path> --plan-mode-file <path>`. `--from-automation-build` runs `compile_launch_builds()`
   and then the campaign build under the write lock; `--journal` is REQUIRED on that path and is the
   receipt file; `--plan-mode-file` is REQUIRED for a real build (not `--dry-run`) and is the PLAN MODE
   run file described in Skill 44 SKILL.md (Launch mode). The
   `44-convert-and-flow-operator/tools/siglaunch/` receiver is **not** a production entry
   (`PRODUCTION_ENTRY_ENABLED = False`): the declared Black Friday purchase path is the native GHL
   post-sale workflows, and repairing a launch goes through this command, never by enabling that
   runner.
3. **QC.** Run from `44-convert-and-flow-operator/`, the one full command (a shorter one cannot exit 0: the
   plan file, the signed QC session record (`--qc-model` is refused), the grades and the dependency manifest are required, and a launch build needs its wait schedule). The second
   line adds the script's own exit status to the saved result as `exit_code`:

   ```
   ./qc-built-workflow.sh <workflow-id> --json --plan-mode-file <plan.json> --qc-session <record.json> \
       --grades <grades.json> --deps <deps.json> --launch --launch-schedule <schedule.json> [--fab] > qc-<workflow-id>.json; rc=$?
   python3 -I -c 'import json,sys; p,rc=sys.argv[1],int(sys.argv[2]); d=json.load(open(p)); d["exit_code"]=rc; json.dump(d,open(p,"w"),indent=2)' qc-<workflow-id>.json "$rc"
   ```

   `<schedule.json>` is the `{"waits": [...]}` file `44-convert-and-flow-operator/automation-templates/launch-c/emit_launch_schedule.py
   --automation-build automation-builds.json --unit <unit-id> --out <schedule.json>` writes from the reader's
   `schedule.nodes`. A build that fails QC is not delivered: the saved `qc-<workflow-id>.json` is one of the
   automation's delivery artifacts, and `assemble` and `check` refuse the unit when it is missing, names another
   workflow, or does not carry `exit_code` 0, `exit_gate` PASS, `overall_mechanical` PASS and
   `plan_mode_gate.status` PASS (`AF-LAUNCH-UNIT-AUTOMATION`).
4. **Receipt.** The build journal is that build's receipt (unit key, remote id, phase, expected and
   read-back hash), so a re-run is safe; the `siglaunch` receiver is not a production entry and issues
   no receipt of its own. Each planned email, text and automation reaches Skill 83 as the producing lane's delivery
   row, never one typed by hand: an automation is Skill 44's build export (`skill44.workflow-export.v1`, the
   first artifact) plus its QC result; an email sequence is the row `50-email-engine/tools/validate_delivery.py
   <run-dir> --launch-plan <plan> --unit <id> --out <receipt.json>` writes (`skill50.email-delivery.v1`, with its
   certificate); a text set is Skill 44's `skill44.sms-set.v1`. Skill 83 reads them through
   `assemble --launch-plan <plan> --deliveries <deliveries.json>` and requires every planned email, text and
   automation to be delivered before the package counts as a full launch. `assemble` and `check` accept a lane
   delivery only when `lane_validation.contract` is that unit type's producer contract above (any other string,
   including a self-declared one, is refused) and, for an email, when `validate_delivery.py --check`, run by path
   from the package folder, exits 0; an absent validator or a failed re-check refuses the unit
   (`AF-LAUNCH-PKG-RECEIPT-LANE`). A text set is checked against its contract id only until Skill 44 ships a
   text-set validator. A page the launcher builds itself is proved by its own page row. A page another lane
   delivers and the Conversation AI have no producer contract yet (their allow-list is empty), so `assemble` and
   `check` refuse any lane delivery for them with `AF-LAUNCH-PKG-RECEIPT-LANE` ("has no producer yet"), whatever
   contract string it carries.

Skill 83 builds pages; it does not build workflows itself. See Skill 44's own SKILL.md and INSTRUCTIONS.md for
the same four steps from the other side.

## Pictures, spend and design approvals

Skill 83 asks the client the picture questions (`python3 -m launcher_core.cli questions`), records the answers
in the intake's `image_plan`, and carries one shared image-inputs file to every page, so no page is drawn in a
different style, for a different owner or under a different spend limit. Never build an `image_plan` from
guesswork and never skip the picture step. Full rules are in `DISPATCH.md`.

**`image_plan` fields** (`launcher_core/image_plan.py`): `design_style` (A Block, B Circle or C Hybrid),
`design_style_source`, `brand_file` and `brand_owner` (both required, never defaulted), `image_cap`,
`image_provider` (only `kie` can draw today; `agnes` and `other_explicit` are refused by name),
`paid_render_approval_ref`, `design_prose_ref` and `visual_bible_ref` (creative direction). An unknown field is
refused.

**Never-default spend rule.** Money is never defaulted and never inferred. A practice run (the intake's top-level `test_only` flag; it is not an `image_plan` field) draws
placeholders and costs nothing. A paid run needs the client's own ceiling (`image_cap`) AND a recorded
paid approval record (`paid_render_approval_ref`), or it stops before anything is sent
(`AF-LAUNCH-IMAGE-PLAN-CAP`, `AF-LAUNCH-IMAGE-PLAN-APPROVAL`). Design style and provider may be defaulted but
are always flagged `to_confirm`. The decided replacement is a money cap (`cap_minor` plus currency, with a
per-image price table) backed by a verified `paid_asset_budget` approval record. It was decided 2026-11-02
(ENF-05, IMG-03, IMG-05) and is not yet in the code; the never-default rule is the same either way.

**Design approval gates.** (1) The plan approval record passed as `--approval` is carried to Skill 49's gate
unchanged; a worker cannot approve its own plan, and a plan changed after approval is refused. (2) Skill 71's
`gate:intake_design_style` closes only on a recorded style (`client_choice` or `recommended_accepted`); a
defaulted style stays a proposal until the client confirms it. (3) The design board and the final mockups
are recorded `awaiting_client_approval` until the client approves them. The client sees each one in chat (the board and
mockup images or the review PDF attached, the copy inline) and may approve there, by button or in Command Center; the
board approval is recorded from the Command Center `design_board` record with
`design_board.py approve --approval-id <id>` (Skill 71).

**Final mockups.** A delivered launch holds, for every page, desktop and mobile wireframes and mockups,
review PDFs and an overview board (AF-LAUNCH-PAGE-DESIGNS), with real pictures: placeholder pictures fail a
package that is not `test_only`. The decided Black Friday deliverable is finished pages with real images
(final mockups closed on the paid run), with layout proofs as an explicit first approval checkpoint
(IMG-01); a stub package is labeled "images only, render pending" and is never a finished delivery.

## Production pages and the install hand-off (operator reference)

`dispatch` and `assemble` end at DESIGNS. Two further commands carry an approved design to a page and to
the delivery rail, in this order and never skipped:

1. `python3 -m launcher_core.cli produce --package <assembled package> --run-dir <dispatch run> ...`
   runs only after `check` exits 0. It calls Skill 80's `build_production_pages.py` (U1, D1, U2),
   Skill 81's `production_handoff` (D1) and Skill 82's `build_thank_you_page.py`, and writes
   `production/<role>.html` plus `production/manifest.json` (sha256 per page) into the package. A copy
   document marked `test_only` on a launch that is not `test_only` is refused. Skill 82 renders a verified
   order view, so without `--thank-you-view` and `--thank-you-fulfillment` the thank-you page is recorded
   `not_built` with the reason, and a client package is then not complete. `AF-LAUNCH-PRODUCTION`
   (`check_rules/production.py`) fails a client package whose approved pieces lack a built page, and any
   page changed after it was produced.
2. `python3 -m launcher_core.cli install --package <package> --run-dir <dispatch run> --rail <skill>/<module>.py:<entry>`
   (decision D-E: Skill 83 is the caller of the delivery rail; Skill 49 never is). The rail receives
   `install/install-handoff.json` and must return what it READ BACK from the installed pages; Skill 81's
   entry guard runs over that read-back journey. `install/install-readback-downsell_1.json` is what Skill
   49's `downsell_wrapper.py --stage install --install-readback` reads, which is the only thing that
   clears `D1-ENTRY-GUARD-RUNTIME-ONLY`.

The lines the client is told (`launch_bridge.summary_lines`) follow what is on disk: design only, built, or
installed. The upsell and downsell pages are dispatched with `--stage design`: eligibility is a runtime
gate (`U1-ELIGIBILITY-RUNTIME-ONLY`), never an asserted purchase.

## Tracked items (not built here)

Each item is tracked, not forgotten. Where Skill 83 does not do something, the owner and the place it is
tracked are named.

| Not done by Skill 83 | Tracked in |
| --- | --- |
| Build pages (it composes the page-results Skills 71, 78, 79, 80, 81 and 82 return) | permanent boundary |
| Charge, create an entitlement or call a billing API | permanent boundary; membership and purchase truth is PRD-12 |
| Start a live Council session; Council advice is a readiness record until then | CON-16 |
| Install the native order form, bump and one-click steps (Skill 06 has the step, S06-02, but it refuses to write until the live commerce capture CHK-19 is done) | S06-02, CHK-19 |
| Supply the native checkout facts a per-offer instance still needs (native ids, terms, consent, capability/fulfillment refs, bump component facts) | recorded per instance: `AF-LAUNCH-CHECKOUT-REJECTED` |
| Choose a distribution target | open seam `distribution_run_target` in `DECISIONS-PENDING.md` |
| Cross-sale teaching content (the surface is present, the teaching is marked pending) | open seam `cross_sales_teaching_source` |
| Build automations or workflows | Skill 44 and Skill 50 (see "Launch mode"); S44-25 |
| Ship a `/path/to` binding (`check` fails any placeholder-shaped path) | enforced by `check` |

## Decisions

`DECISIONS-PENDING.md` records the five decisions implemented here and the two
seams still open (`distribution_run_target`, `cross_sales_teaching_source`).
