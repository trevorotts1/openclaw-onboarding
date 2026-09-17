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

## Drive delivery

Google delivery is PERFORMED by this step, not merely planned, whenever the box
holds the client's own Google Workspace credentials. The prerequisite is Skill 14
(`14-google-workspace-integration`) installed with the client's own service account.
Resolution uses Skill 14's own names and invents none:

- **Service-account key:** `GOOGLE_APPLICATION_CREDENTIALS`, else
  `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE`, else the Skill 14 default location
  `~/clawd/secrets/gcp-service-account.json`.
- **Impersonated Workspace user:** `GCP_IMPERSONATE_USER`, else `GWS_ACCOUNT`.
- **Destination folder (optional):** `PODCAST_DRIVE_ROOT_FOLDER_ID`. Unset, the
  documents land in the impersonated user's own Drive root.

Both the key and the user are required. With either missing, Step 12 keeps today's
intent-only behavior, logs exactly one line reading `drive delivery skipped: Skill 14
Google Workspace credentials not configured on this box (see
14-google-workspace-integration/INSTALL.md)`, and the episode continues. A Drive API
error is recorded on the plan under `delivery.errors` and never fails the episode.
Neither path changes the exit code. `--no-deliver` forces the intent-only path.

When delivery runs, each rendered document is uploaded and converted to a Google Doc,
the anyone-with-the-link-can-edit permission is applied, every executed intent is
stamped `performed: true` with its `file_id` and `link`, and the links are written to
`plan["links"].package_doc` and `plan["links"].speech_doc` so Step 16 LINK BACK writes
real document links into GHL. The plan file on disk is Step 12's own record of what it
delivered; this step still writes NO engine state, because podcast_state.py remains
the sole writer.

**gws safety:** delivery speaks the Drive REST API directly with the client's service
account and NEVER invokes the gws binary, not even to test for credentials. A bare gws
call in a headless shell cannot unlock its keyring and gws's own failure mode then
rewrites the default credential store to `credential_source: "none"`, wiping every
account on the box. Step 12 runs headless by definition. Only the full Drive scope is
requested; domain-wide delegation rejects the narrow drive.file and drive.readonly
scopes for this grant.

Report readiness with `render_documents.py detect`, which prints a `drive delivery:`
line reporting SET or NOT SET by label and never a value.

---

## Data-plane doctrine: the agent executes the rest of the plan

The renderer calls no model and no MCP tool, and its only external surface is the
Drive delivery described above. Notion publishing still happens in the podcast agent's
OWN turn over direct REST, using the client's own credentials. Sub-agents get no MCP
injection, so no MCP tier is ever used for this step. The plan is machine-readable
intent:

- **Google actions:** upload-and-convert the package HTML to a Google Doc
  (application/vnd.google-apps.document), upload-and-convert the speech text to a
  Google Doc, then set each doc's permission to role=writer, type=anyone, and capture
  both document links back into the episode record (links.package_doc,
  links.speech_doc). Step 12 PERFORMS these itself over Drive REST when the client's
  Skill 14 credentials resolve; see "Drive delivery" above.
- **Notion actions:** create a page per deliverable under the parent page via REST
  (never MCP), then capture both page URLs into the episode record.
- **Local actions:** none; the on-disk files are the deliverables.

**gws safety:** never invoke a bare gws call in headless mode. A bare headless gws
call self-wipes the default credential. Always pass an explicit account and
subcommand. The renderer never calls gws; this warning binds the agent turn that
executes the Google plan.

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
