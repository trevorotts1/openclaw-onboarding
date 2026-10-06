# Module 12 - Documents (Episode Package and Speech Script)

**Pipeline position:** Step 12 of the canonical 18-step run, between AUDIO (Step 11)
and BOOK TEASER (Step 13). It runs inside the audio-to-publishing window; the module
itself records no state (podcast_state.py is the sole writer and owns every
transition). This module is part of the asset-production slice alongside the cover
finalizer (scripts/generate_cover.sh, Step 10).

**Renderer:** scripts/render_documents.py (pure Python standard library, no model, no
MCP, no external API, fully testable in isolation).

---

## What Step 12 produces

Two deliverables per episode, always both:

1. **Episode Package** - rich and fully rendered, with NO font below 12 point. It
   carries the client-facing episode context: title (woven as a heading, never
   preceded by the word Title), style and mode, honest runtime and spoken word count,
   thesis, show notes, key takeaways, power statements, verified case studies with
   their sources, supporting findings, sources, and the asset links (cover file,
   Podbean episode). It never contains operator-only material; the delivery report
   with rubric scores and model substitutions is a separate operator-channel artifact.
2. **Speech Script** - clean text only. It is the pure speakable script and nothing
   else. It carries no markup, no labels, no HTML, no fences, and no em dashes.

The renderer writes both to disk first (the local artifacts are the durable base),
then emits a destination action plan the agent executes to publish them.

---

## Destination detection (Google first, then Notion, then plain text)

Detection is by tooling and credential PRESENCE only. The renderer reports SET or NOT
SET and never reads or prints a credential value.

1. **Google** is chosen when the client's gws CLI is on PATH, OR any Google Workspace
   signal is set (GOOGLE_WORKSPACE_ENABLED, GWS_ACCOUNT, GOOGLE_APPLICATION_CREDENTIALS,
   or GOOGLE_WORKSPACE_TOKEN). Google is the preferred destination.
2. **Notion** is chosen when a Notion token (NOTION_API_KEY or NOTION_TOKEN) AND a
   parent page (NOTION_PARENT_PAGE_ID or NOTION_PODCAST_PARENT) are both set. A Notion
   page cannot be created without a parent, so both signals are required.
3. **Plain text (local)** is the last resort and is always available: the rendered
   HTML package and the clean-text script on disk are the deliverables.

Override with --force-destination google|notion|local. When a destination is forced
but its credentials are NOT SET, the plan is still emitted with ready:false and a
warning, so the agent fails cleanly instead of guessing.

---

## Font floor and sharing rules

- **Font floor:** every font size the renderer emits is expressed in points and is at
  or above 12pt (body 14pt, section headings 18pt, title 26pt, the smallest meta and
  footer text exactly 12pt). The renderer self-verifies the produced file before
  declaring success and refuses to ship a package that fails the floor.
- **Google sharing:** anyone with the link can edit, expressed as a Drive permission
  role=writer, type=anyone, applied to BOTH the package doc and the speech doc. This
  rule is Google-specific. Notion has no identical concept; its plan carries a
  share-to-web note to be handled per the client's Notion policy, and local has no
  external sharing.

---

## Renderer contract

Subcommands:

    render        --manifest <json> --out-dir <dir> [--force-destination X]
                  [--speech-script-file <f>]
    detect        [--json]
    check         --package <html-file>       verify the 12pt font floor
    check-script  --script <txt-file>         verify the script is clean text

Manifest fields (title required; a speech script required via speech_script,
speech_script_file, or --speech-script-file):

    title, client, mode (interview|personal), style, guest_first_name, thesis,
    runtime_minutes, word_count, description, cover_path, podbean_url,
    research: { key_takeaways[], power_statements[], case_studies[{title,summary,source}],
                findings[], sources[] }

Outputs written to --out-dir, named from a slug of client and title:

    <slug>-episode-package.html      the rich Episode Package
    <slug>-speech-script.txt         the clean Speech Script
    <slug>-documents-plan.json       the destination action plan

Exit codes: 0 ok; 2 bad arguments or input (missing manifest, missing script, invalid
JSON); 3 render or self-check failure (font floor or clean-text). Every render
self-verifies both deliverables and fails closed on any violation.

---

## Document delivery: Google Drive, then Notion

Delivery is PERFORMED by this step, not merely planned, and it is a two-tier chain
so the documents reach the client wherever the box is provisioned:

1. **Google Drive**, through the client's own Skill 14 credentials.
2. **Notion**, the client's own workspace, when Skill 14 is not configured on this
   box or the Drive call delivered nothing. Nearly every client box already has
   Notion connected.
3. **Intent only**, when neither is configured: the existing plan record plus ONE
   log line naming both prerequisites.

Whichever tier delivers records its ids and links in the plan, and the chain is
summarized under `plan["delivery"]` with a per-tier record under
`plan["delivery"].tiers`. No tier can fail the episode or change the exit code.
`--no-deliver` forces the intent-only path.

### Tier 1: Google Drive

The prerequisite is Skill 14 (`14-google-workspace-integration`) installed with the
client's own service account. Resolution uses Skill 14's own names and invents none:

- **Service-account key:** `GOOGLE_APPLICATION_CREDENTIALS`, else
  `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE`, else the Skill 14 default location
  `~/clawd/secrets/gcp-service-account.json`.
- **Impersonated Workspace user:** `GCP_IMPERSONATE_USER`, else `GWS_ACCOUNT`.
- **Destination folder (optional):** `PODCAST_DRIVE_ROOT_FOLDER_ID`. Unset, the
  documents land in the impersonated user's own Drive root.

Both the key and the user are required. With either missing the Drive tier is
skipped and the chain falls through to Notion. A Drive API error is recorded under
`delivery.tiers.google_drive.errors` and also falls through to Notion.

When the Drive tier runs, each rendered document is uploaded and converted to a
Google Doc, the anyone-with-the-link-can-edit permission is applied, every executed
intent is stamped `performed: true` with its `file_id` and `link`, and the links are
written to `plan["links"].package_doc` and `plan["links"].speech_doc` so Step 16 LINK
BACK writes real document links into GHL. A permission that fails AFTER a successful
upload is partial, not a fallback trigger: the documents are already in the client's
Drive.

### Tier 2: Notion

The convention here is the repo's existing one, not a new one: the token, the
explicit parent page, the client-ownership guards and the block shapes all come from
`37-zhc-closeout/scripts/ensure-notion-parent-page.sh`,
`37-zhc-closeout/scripts/create-notion-closeout.sh` and the Skill 38 reference
`notion-client-doc-standard.md`.

- **Integration token:** `NOTION_API_TOKEN`, else `NOTION_API_KEY`, else
  `NOTION_TOKEN`. The CLIENT's own token.
- **Parent page:** `NOTION_PODCAST_PARENT`, else `NOTION_PARENT_PAGE_ID`, else
  `NOTION_WORKSPACE_ROOT_ID`. Explicit and client-owned.
- **API version (optional):** `NOTION_API_VERSION`, default `2022-06-28`.

**Client ownership is binding.** The page lives in the CLIENT's Notion under the
CLIENT's token. An explicit parent is required because ownership is never inferred
from a workspace-wide search, and the agency token (`ZHC_AGENCY_NOTION_TOKEN`) and
agency parent (`ZHC_AGENCY_NOTION_PARENT_PAGE_ID`) are both refused, exactly as
Skill 37 refuses them.

One `Podcast Episodes` page is created under the client's parent, once, and one page
per episode beneath it, keyed by the episode title. **Idempotent:** re-running Step
12 for the same episode clears that page's children and rewrites them, so it never
duplicates. Blocks are built from the same manifest the HTML renderer uses, through
`render_package_markdown` and `markdown_to_notion_blocks` (headings, paragraphs,
bullets, links), and appended in chunks of 100, the API's children-per-request limit.
Each page opens with an episode properties block (title, date, style, mode, runtime,
spoken words, guest). A page parented by a page cannot carry arbitrary Notion
properties, so these are page BLOCKS, which is what the API allows.

**No file upload.** The Notion API cannot upload a file. The published audio from
Step 15 is carried as a LINK, never an upload, and the rendered HTML and text files
on disk remain the durable base.

The page id and url land in `delivery.tiers.notion.documents.episode_page` and in
`plan["links"].episode_page`. When the plan's primary destination was already Notion,
its `notion.create_page` intents are stamped `performed: true, channel: notion` with
the same page id and url, so the episode record reads the same whichever tier
delivered.

### Tier 3 and the exit code

With neither tier configured the plan stays intent-only and exactly one line is
logged, naming both prerequisites. The plan file on disk is Step 12's own record of
what it delivered; this step still writes NO engine state, because podcast_state.py
remains the sole writer.

**gws safety:** delivery speaks the Drive REST API directly with the client's service
account and NEVER invokes the gws binary, not even to test for credentials. A bare gws
call in a headless shell cannot unlock its keyring and gws's own failure mode then
rewrites the default credential store to `credential_source: "none"`, wiping every
account on the box. Step 12 runs headless by definition. Only the full Drive scope is
requested; domain-wide delegation rejects the narrow drive.file and drive.readonly
scopes for this grant.

Report readiness with `render_documents.py detect`, which prints a
`tier 1 drive delivery:` line and a `tier 2 notion delivery:` line, each SET or NOT
SET by label and never a value.

---

## Data-plane doctrine

The renderer calls no model and no MCP tool. Its only external surfaces are the two
delivery tiers above, both over direct REST with the client's own credentials.
Sub-agents get no MCP injection, so no MCP tier is ever used for this step. The plan
is machine-readable intent:

- **Google actions:** upload-and-convert the package HTML to a Google Doc
  (application/vnd.google-apps.document), upload-and-convert the speech text to a
  Google Doc, then set each doc's permission to role=writer, type=anyone, and capture
  both document links back into the episode record (links.package_doc,
  links.speech_doc). Step 12 PERFORMS these itself over Drive REST when the client's
  Skill 14 credentials resolve; see "Drive delivery" above.
- **Notion actions:** create a page per deliverable under the parent page via REST
  (never MCP), then capture both page URLs into the episode record. Step 12 PERFORMS
  these itself as tier 2 of the delivery chain; see "Document delivery" above.
- **Local actions:** none; the on-disk files are the deliverables.

**gws safety:** never invoke a bare gws call in headless mode. A bare headless gws
call self-wipes the default credential. The renderer never calls gws at all: its
Google tier speaks the Drive REST API directly with the client's service account.

Example (operator box, local last-resort run):

    python3 scripts/render_documents.py render \
      --manifest episode.json --out-dir ./out --force-destination local

---

## QC mapping and self-verification

Runtime matrix (QC-PROTOCOL-AND-MATRIX.md, Documents row): rendered rich formatting on
the Package, clean text only on the Script, sharing set, and font floors, proven by
this module's checks and reflected in the delivery report.

- check verifies every font-size in the package is at or above 12pt and fails on any
  relative unit that cannot be proven against the floor.
- check-script fails on an empty script, an em dash, a triple backtick fence, or any
  HTML tag, and warns on markdown-looking lines. qc-tier1-mechanical.py remains the
  authoritative full Tier 1 gate for the script content; check-script is a fast
  pre-persist sanity guard that never relaxes or replaces it.

This is loop engineering at the module level: render, self-check, fail closed, and
hand the agent a plan that is either ready or explicitly not ready. A missing tool or
credential produces a downgraded-but-honest destination, never a silent gap and never
a fabricated success.

---

## Binding rules (restated, non-negotiable)

- **Silence:** operator and agent output only. This step emits zero client-facing
  messages; customer messaging belongs to Convert and Flow.
- **Secrecy:** credentials are reported as SET or NOT SET by label only; no value is
  ever printed, echoed, or written to the plan.
- **No content-model provider** is invoked here; this is a pure rendering step, so the
  runtime routing policy and its deny list are untouched and no shipped runtime file in
  this slice references any denied provider or model id.
- **Zero em dash characters** anywhere, and **no triple backtick fences** in any
  produced JSON, HTML, or text output.
- **Named client credentials only:** the client's own Google or Notion account; no
  operator, shared, or other-client credential is ever substituted or commingled.

---

## Reuse note

Local-first rendering with the client's own Google credentials mirrors the Skill 57
planner posture (client-owned Google, detect-first, graceful downgrade). The engine
adds the Notion tier and the plain-text last resort so the step always succeeds with
the best destination the client box actually has.
