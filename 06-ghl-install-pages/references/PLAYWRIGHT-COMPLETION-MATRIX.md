# Skill 6 implementation acceptance matrix

Owner scope reviewed: November 8, 2026. This is the completion contract, not a
claim that these rows have passed. The private owner brief remains private.

## Current source checkpoint — November 9, 2026

Batch 1 merged in PR #2877. The next reviewed source batch has 33 catalog
operations and 542 tests discovered (535 passed, seven optional browser skips).
Native form scheduling, twelve simple field property paths and existing draft
course outline API edits now have concrete handlers. This expands the applicable
rows; it does not close their complete feature or functional acceptance criteria.
Final native Python execution, payment journeys and all required client receipts
remain necessary. An operation count must not be reported as a completion ratio.

## What counts as complete

A catalog name, implementation flag, fake-browser test, captured screen, API
handoff or successful Save click alone does not close a requirement. Each
requirement needs a real executable path from the supported host entry point,
validated inputs, recorded object identity, and the persisted or functional
read-back stated below. A screen capture proves controls existed; an offline
test proves the tested contract; neither proves a client build succeeded.

Completion evidence must name the source commit, operation, client-bound run,
host OS, input fingerprint, created/reused object IDs, exact checks and outcomes,
and remaining verification. Keep client evidence in protected client run storage,
not in the public repository. An uncertain write stops subsequent writes until
its outcome is reconciled. Existing approval gates still apply.

Status vocabulary: **WRITTEN** means executable code exists; **CAPTURED** means
actual controls were inspected; **OFFLINE PASS** means tests ran without a real
client operation; **LIVE PASS** means the actual final script ran and the stated
read-back passed; **BLOCKED** names the missing access/input/capture. Report
those separately, never add them together as completed scripts.

## Required operations and exact closure evidence

| ID | Owner requirement | Evidence required to close |
| --- | --- | --- |
| R01 | Inspect and extend existing Skill 6 | Canonical Skill 6 entry point invokes maintained package; no disconnected second builder or duplicate credential system. |
| R02 | Choose API/MCP/Skill 44 first for supported operations | Fresh location/version/scope capability check selects and actually executes the supported provider; successful object read-back. An API route label or handoff is not execution. |
| R03 | Retain Skill 44 fallback for operations it supports | Exact operation dispatch reaches installed Skill 44; provider failure reported without silently changing tenant or identity. |
| R04 | Ready Playwright before AI browser control for UI work | Host trace selects the named reusable script and completes its requested steps without a model call between routine actions. |
| R05 | OpenClaw extension, then Agent Browser, then computer control | Fault injection exercises each available fallback and the host actually invokes it; uninstalled or outdated lanes are excluded. Missing lanes yield a typed stop. |
| R06 | Existing authentication from the custom extension/token flow | Final Mac and Linux runs use canonical resolver/auth bridge, confirm authenticated identity/location, and avoid interactive password/2FA prompts. No token in logs/archive. |
| R07 | One upfront intake | All required missing build inputs collected before first write; supplied answers and inventories reused; no fabricated legal, product or security values. |
| R08 | Named reusable scripts and use cases | Every catalog operation has a documented input schema, executable command/host dispatch, best use, limitations and evidence level. Unsupported functions cannot be advertised complete. |
| R09 | Create a funnel | Run creates one named container and initial step, saves their IDs, reopens them, and a retry/recovery does not duplicate either. |
| R10 | Add a funnel page | Exact existing funnel selected by identity; requested page name/path persisted; other pages unchanged; multiple existing pages supported. |
| R11 | Update an existing funnel page | Exact page and intended code element selected among multiple pages; updated content persists; old unrelated content unchanged. |
| R12 | Create a website | Final script creates one website and initial page; identities/path and saved content independently read back. |
| R13 | Add/update website pages | Exact website/page target works with multiple pages; saved path/content correct; no wrong global Edit click. |
| R14 | Native split-test pages | Native source/variant relation, both page IDs and intended traffic allocation read back after save; retry reconciles existing variant; zero extra duplicate variants. |
| R15 | Import approved AI/Skill 49/83 HTML | Both fragment and full-document input preserve approved content, CSS/scripts and intended code-block identity; final rendered marker/content checked. |
| R16 | Hosted app/Vercel embed | Receipt binds actual fragment hash and actual iframe/script URLs; target renders on desktop/mobile; embedding/authentication permission verified. URL alone is insufficient. |
| R17 | Insert code in the correct place | Explicit target section/row/column/element identity; existing multi-section page supported without changing unrelated sections; code order matches requested placement. |
| R18 | Full Width and entire-width rows | Script actually sets both settings when initially off, reopens them, and checks rendered desktop/mobile width. A class assertion that refuses non-full sections is not configuration. |
| R19 | Native order form surrounded by custom design | Before/native/after elements persist in exact order and preserve GHL payment fields; rendered layout checked at desktop/mobile. |
| R20 | Checkout products, prices, bumps and settings | Location-bound product/price dependencies verified; intended native component bindings and bump relation independently read back. Missing products stop before checkout completion. |
| R21 | Native one-click upsell | Correct source/upsell step and offer IDs, prior-payment contract and action binding verified; approved test-mode funnel journey proves acceptance/decline outcomes. No raw-card HTML. |
| R22 | Page SEO | Saved title/description/keywords/author/canonical/language match the approved values in rendered HTML; updates handle existing different values, not only an empty editor. |
| R23 | Create native forms | Required standard fields and explicit form identity persist after reopen; field validation and fixture submission verified. |
| R24 | Form field types and properties | Current builder feature inventory covers standard/custom fields, single/multi-line, choices, dates, numbers, files/signature/URL and other visible supported types; each requested field/property/choice persists. Dependencies created through supported API first. |
| R25 | Form required/hidden/default/label/options | Each supported property has a captured concrete path and reopened persisted read-back; invalid option combinations rejected before writes. |
| R26 | Form consent/legal/submit/redirect behavior | Exact supplied legal copy and destinations persist; fixture submissions prove message versus redirect and requested native behavior. No invented legal copy. |
| R27 | Form notifications/tracking/integrations | Native configured values and intended recipients/destination persist; authorized fixture event demonstrates behavior without contacting unintended recipients. |
| R28 | Form conditional logic | Requested conditions, operators, actions and targets persist; positive and negative fixture submissions take the expected branch. |
| R29 | Form CSS polish | Preserves existing client CSS; configured inputs/buttons look correct including inputs without type attributes; desktop/mobile computed styles checked after save. |
| R30 | Native form settings | Each explicit requested native switch persists after editor reopen. Scheduling includes dates, time zone and outside-window messages, not only a switch. |
| R31 | Native survey creation and questions | Requested slides, question types, labels/choices/required states persist; fixture submission reaches expected completion. |
| R32 | Survey branches and outcomes | Actual conditional jumps, destinations and completion rules persist; fixture answers exercise each requested branch. |
| R33 | Marketing/lead quiz creation | Uses the marketing quiz builder, distinct from survey and course quizzes; requested questions/categories/answer values persist. |
| R34 | Marketing quiz scoring/results | Actual scoring/weights/categories/result pages and thresholds persist; fixture submissions prove boundary scores and each requested outcome. |
| R35 | Community creation | Named native group created/reused once with requested visibility and access; saved identity and portal link read back. |
| R36 | Community channels/settings/branding/course links | Authenticated portal path executes requested channel and setting changes; independent portal read-back proves each. An expired-password screen is a blocker, not completion. |
| R37 | Course creation via supported API | Real course API request executes through existing transport; returned course ID independently fetched; duplicate prevention/reconciliation tested. |
| R38 | Course sections/lessons/content/access | Requested outline/content and access configuration persist using API first where supported; delivery view checked with intended authorized role. |
| R39 | Course lesson quizzes | Actual documented course-quiz API executes; questions/answers/grading persist; fixture attempt proves expected result. Do not use marketing quiz UI. |
| R40 | Genuinely UI-only course settings | Captured concrete settings path executes only where API does not support exact operation; reopen/read-back proves requested state. |
| R41 | Meeting Room research and provisioning | Current official sources identified; per-location capability check precedes concrete create/update; named room and intended reusable link independently read back. Do not start a meeting as proof of setup. |
| R42 | Meeting security and co-host choices | Explicit waiting/guest/open-room choices persist. Co-host identity resolved before any authorized access change; generated secrets stay private. |
| R43 | Meeting calendar/community/course integration | Intended native association and room link persist in each requested integration surface; event/booking delivery uses the expected room. A text link alone is not a native association. |
| R44 | Mac and VPS compatibility | Final installed Python scripts run on both Mac and Linux VPS with supported browser lifecycle; dependencies, headless behavior, clean teardown and host imports pass. |
| R45 | Resume without losing work | Source remotely committed; dated Downloads checkpoint verifies its manifest; new chat reads ledger and current code; interrupted write is reconciled by saved IDs before resume, not blindly retried. |
| R46 | Lower repeated AI/token work and faster execution | Scripts perform routine sequences without model calls; comparable representative fixture captures wall time and model-call/token counts. Do not claim measured savings without measurements. |
| R47 | Final Skill 6 integration | New entry points, router, documentation, version/changelog and required package generation agree; appropriate checks pass; unverified status retained through installed host/reporting. |

## Feature inventory and final proof rules

"All options" means reconcile the actual current builder feature inventory against
the supported schema and executable actions. List each observed option as supported,
API-owned, access-blocked or unsupported with a concrete reason. A generic options
executor alone cannot establish coverage of unseen controls.

For every named job run the final script on a fixture through its supported host
entry point, then inspect the persisted result independently. The operator must
retain the receipt even when a script reports success. Page/form builders also
need desktop/mobile checks; conditional assessments need functional submissions;
payment behavior needs the existing authorized test-mode payment contract.

The completion report must separately state: files written, named operations,
offline test counts, Mac live passes, VPS live passes, functional passes and
blocked requirements. Never replace those with one combined completion count.

## Initial verification findings for integration

These findings describe the inspected recovery baseline, not an assessment of
later sibling changes before they are integrated and rerun:

1. `full_width` toggles entire-width rows but only checks section Full Width;
   it cannot yet turn a non-full section into a full one.
2. `install_html` refuses multi-section pages; `ensure_page` refuses an existing
   target when multiple global Edit buttons are present. These limits are safe
   but leave R11/R13/R17/R18 open.
3. The baseline host returned API/fallback handoffs without executing them. This
   leaves R02/R03/R05/R37 open until concrete provider adapters run.
4. The baseline central executor promoted incomplete handler statuses to editor
   completion and continued later writes. A missing handler result triggered an
   uncaught final AttributeError. `test_acceptance_contract.py` reproduces both.
5. Historical UI-path exercises were not final Python runs on Mac and VPS. Do
   not upgrade their evidence level until those final runs are recorded.

## Verification during parallel continuation

- Central result validation now accepts recognized outcomes rather than a
  blacklist. Ten acceptance-boundary tests pass: nine incomplete/no-op status
  cases, missing outcomes, pending read-back, meeting-update creation refusal
  named HTML updates preserving their native element/section identity, direct CLI helper refusals and shared direct/package exception identity.
- At the latest independently reviewed snapshot, `python3 -m unittest discover
  -s 06-ghl-install-pages/tools/playwright_recipes -p 'test_*.py'` discovered
  262 tests: 255 passed and the seven opt-in real-browser tests were explicitly
  skipped. Exit 0. This is an offline result, not 262 browser passes. Re-run
  after any later integration changes; it is not a final native release verdict.
- Course execution, assessment models, native checkout adapter and Meeting Room
  components now have offline tests. Required host callbacks, captured adapters,
  native associations and actual live fixture behavior still require their own
  evidence. Module tests cannot close those live requirements by themselves.

## Mac/Linux GitHub Actions fixture proof

The portability workflow and seven real-browser fixtures are implemented in
`.github/workflows/skill6-recipes-portability.yml` and
`tools/playwright_recipes/test_browser_fixture.py`. At checkpoint `d86983`, the
Mac and Linux portability jobs each passed 178 tests, including the four actual
Chromium fixtures. That proves the tested synthetic browser behavior on those
runners, not live GHL or client installation. The separate lifecycle guard caught
the fixture's browser-launch form. It is now corrected to one suite-owned
headless persistent context with a temporary profile, per-test page teardown,
context shutdown and profile cleanup. The unchanged lifecycle guard passes
locally; the corrected source still needs its next CI rerun. A Chromium download
failure on the development host is a real environment limit, not a successful
local browser check.

| Layer | Runner and trigger | Required execution | What it proves |
| --- | --- | --- | --- |
| Offline contracts | `macos-latest` and `ubuntu-latest`, pull requests touching this package | Install the declared Python dependencies, run package imports and the complete unittest suite, record Python/OS versions and actual counts. | Both platforms can import and execute the tested contracts. No client operation is claimed. |
| Real browser fixtures | Same two runner OSs, isolated local fixture servers | Install Playwright and its Chromium build; serve shell and builder on different loopback origins; exercise the actual maintained form-settings executor. Seven cases cover save/reload of seven settings with scheduling off and already on, protected branding preservation, row/count/branding drift and Save clicks that lose their data. Selected tests fail when browser launch fails. | Real Playwright frames, switch clicks, selector ambiguity, save/reopen, cross-origin isolation and cleanup work in the fixture. This still does not prove GHL live behavior. |
| Native client smoke | Explicit manual dispatch to separate client-controlled Mac and Linux VPS workers | Use client-local secret resolver and existing browser lifecycle, exact location/account binding and named fixture objects. Run final installed scripts, then independently fetch/reopen each persisted result. | Actual native script execution on each required host. Record each operation separately. |
| Functional journey | Explicit fixture-run scope with existing payment/message approvals | Submit form/survey/quiz fixtures and use the existing authorized test-payment contract for checkout and upsell. Prove branch boundaries, accept/decline and correct native associations. | Requested functional behavior, beyond editor saves. |

Additional browser fixtures still must include initially non-full sections, multiple pages and
sections, existing code targets, inputs without type attributes, changed selector
counts, delayed saves, failed reads, uncertain writes and duplicate object names.
Payment fixtures use synthetic data only; native payment execution uses the
existing approved test-mode flow. Do not put client tokens in hosted workflow
inputs, public artifacts or raw Playwright traces. Retain only sanitized test
summaries in public CI; client-bound proof stays in protected client run storage.

Acceptance requires both OS jobs to succeed, no skipped required browser checks,
clean session teardown, no later mutation after uncertain results, and source
commit/manifest correspondence. Automated CI setup must use the repository's
existing dependency/runner conventions rather than introduce another auth rail.

Local validation: fixture Python AST and workflow YAML structure pass. Ordinary
local discovery explicitly skips the seven opt-in browser cases. An explicit
`SKILL6_BROWSER_FIXTURE=1` run fails in setup because Chromium is unavailable;
it does not silently skip or report a browser pass. CI enables that variable
for both operating systems and installs Chromium before discovery.

## Latest integrated implementation review

The following advances were inspected in source during the parallel continuation.
They describe implemented capabilities and tested contracts. Native final-script
execution, functional journeys and platform evidence still close the matrix rows.

| Requirements | Integrated advance | Evidence boundary or remaining work |
| --- | --- | --- |
| R02, R37-R39 | Courses v3 create/update and existing-lesson quiz executors use the existing Skill 44 resolver and write gate; schema-only host checks, location/version/scope checks, root leases, intent, safe IDs and read-back are implemented. | Fake-transport tests verify exact requests and failures; final client API executions and learner behavior remain separate evidence. |
| R17-R18 | Named HTML update inputs preserve native element/section IDs; exact target inventory is available. Full Width now selects Full and verifies the class plus entire-width row toggle on the intended section. | A known native code target can be updated on a multi-section page. Uninventoried/ambiguous targets still stop; final rendered desktop/mobile checks remain required. |
| R20 | Captured native checkout UI supports mode, product-display switches and guarded native contact required/visible states; enclosing function saves, reopens and compares. Separate native binding adapter supports verified product/price/bump/action identities. | UI appearance configuration is distinct from native binding and payment proof. Binding requires a location/page-specific captured adapter map and product/price contract. One-click payment behavior is not proven by these tests. |
| R24-R25 | Native standard-field property edits validate current query/placeholder identities, containing property rows, counts and planned anchor uniqueness, then save and reopen. | Other/custom field types still require their concrete captured paths. Hidden-field writes are refused until a valid hidden-field reopen anchor is captured. |
| R28 | Native Hide Field condition logic has separate rule/drawer/form saves and persisted-card identity checks; matching existing rules are reused. | Supported unary rule persistence has concrete read-back; unsupported/binary behavior and actual positive/negative submissions must retain their stated verification status. |
| R31-R32 | Native forward survey Jump To rules verify actual slide containers, ordered names, condition-field ownership, target, all save levels and reopened summary cards; matching rules do not duplicate. | Native rule persistence is distinct from actual submission routing. Backward/self/dangling jumps and conflicting existing targets stop. |
| R33-R34 | Native marketing quiz category creation, option category/score edits and captured three-tier result ranges verify question/query/option identities and independently reopen saved controls. | Current builder shape is captured, not all possible quiz types/templates. Authored scoring oracle and actual quiz submissions still need comparison; no live Python functional result is inferred from fake-page tests. |
| R41-R42 | Meeting setup/update now have a concrete native reader, sourced empty-state handling, canonical room-link identity, explicit creation permission, expected update identity and saved-security read-back. Unknown recording/transcription/access requests are refused. | The canonical URL is a natural identity, not a claimed backend UUID. Final created/updated native-room execution receipts remain required. |
| R43 | Static calendar association now has a canonical registered Skill 44 calendar-update operation, guarded dispatcher and GET/PUT/GET read-back. Clean room identity and optional private Invite link are kept distinct; private query is not written to source or receipts. | This is static permanent-room integration, not native per-appointment dynamic room generation or community/course event association. Normal capability default-deny and write approvals remain binding. |
| R44 | Real Chromium synthetic fixtures and Mac/Linux portability workflow are implemented with explicit browser installation and mandatory fixture selection in CI; both OS jobs passed the earlier 178-test checkpoint. | Local Chromium cannot launch because its executable is absent. The persistent-context lifecycle correction needs the next CI rerun; actual Mac/VPS native client runs remain unverified. |

Important remaining limits include full builder feature inventory coverage,
uninventoried custom fields, schedule/notification variants, full native split
creation/allocation, community portal access/settings, native dynamic Meeting
Room integrations, approved payment journeys and final native host runs. A
concrete refusal is safer than guessed clicks but does not close that requirement.

## Scheduler-aware ordinary form settings correction

The native builder exposes eight switches when scheduling is off and nine when
scheduling is already on: Agency branding is inserted after the scheduler, so
all seven ordinary-setting indices shift. The executor now validates the local
scheduler row label/state and expected count, validates the inserted Agency
branding row, derives ordinary indices and recomputes those guards after reopen.
Neither scheduling nor branding is clicked or configured; their states must
remain unchanged. Dates and outside-window pages remain outside this operation.

Six fake-browser/schema tests pass, including both shapes, branding on/off,
malformed branding, shape/state disagreement and scheduler drift after saving.
Three additional real Chromium fixtures cover the scheduled shape, wrong-branding
refusal and lost-save read-back. They require the next CI run. Direct CLI native
checkout validator errors are normalized into the canonical Stop class, with no
traceback or second package-specific exception class. The unchanged lifecycle
guard passes all five sections after these edits.

## Final 32-operation integration check

The catalog now contains 32 named operations. This is an operation count, not a
count of final native Python passes. The newest independent package run discovered
262 tests: 255 passed, seven opt-in Chromium fixtures skipped, exit 0. The workflow
still targets the actual package directory and requires those browser fixtures
on both Mac and Linux. The newest source needs its corresponding CI results.

- `forms.submission` compiles into the validated `form_submission` action and
  registered handler. Message/HTTPS redirect values are authored, mode/value
  and conditional precedence are independently reopened, and receipt content is
  hashed. Order Confirmation remains on the native payment-contract rail.
- `forms.notifications` compiles into `form_notifications` with canonical tenant
  context. Enabled cards require complete authored settings; recipient replacement
  uses a complete expected-recipient inventory handshake, inner card Save, outer
  form Save and reopened exact values. Receipts contain only configuration hash,
  recipient count, enabled flags and verification status, not addresses or copy.
- Native checkout Terms require explicit caller-approved plain text for each
  enabled first/second-step Terms switch. The actual editor content is read back;
  unsupported markup/links or missing legal content are refused. This is not a
  generated legal document or payment verification.
- Native Hide/Show condition persistence checks scope the effect and target to
  the correct condition card. Selected-effect validation uses captured visible
  rendered labels, not hidden component state. Functional submissions remain
  separate proof.

Final review found and fixed two missing recognized statuses: saved submission
and notification results previously would have been misreported as recovery
after their successful save/read-back. The central executor now recognizes both
and preserves `behavior_verified: false`, `submission_verified: false`,
`payment_verified: false`, `functional_verified: false` or explicit required
behavior/read-back as NEEDS_VERIFICATION. Ordinary false settings such as
meeting-not-started and discovery-disabled do not create fake pending proofs.
Ten acceptance-boundary tests cover these outcomes. Direct CLI malformed-input
checks for both new operations return structured exit 2 without a traceback.
