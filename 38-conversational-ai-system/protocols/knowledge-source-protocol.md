# Knowledge Sources Protocol

Knowledge Sources are reference documents the agent consults LIVE
during conversations to answer customer questions from real data
rather than from training knowledge alone.

This is distinct from:
  - Communication Playbooks — teach voice/tone/escalation rules
  - Conversation Logs — capture past customer interactions
  - Agent Capabilities Playbook — defines what actions the agent can take

Knowledge Sources are the WHAT-THE-BUSINESS-KNOWS layer.

## Source registry

The active list of Knowledge Sources lives at
`<MASTER_FILES_DIR>/knowledge-sources/registry.md`. Each entry has:

```yaml
- id: <unique short id, e.g., "products-2026">
  name: <human-readable name>
  type: <google-sheet | google-doc | notion-page | notion-database |
         pdf | xlsx | csv | markdown | url>
  location: <URL or file path>
  description: <when to consult this source — keywords/topics it covers>
  last_indexed: <ISO timestamp; null if live-only>
  access_method: <live-fetch | indexed | both>
  refresh_cadence: <never | daily | hourly | on-each-query>
```

## Supported source types

| Type | How agent accesses it |
|---|---|
| google-sheet | Google Drive skill or `sheets.googleapis.com` API |
| google-doc | Google Drive skill or `docs.googleapis.com` API |
| notion-page | Notion skill or Notion API |
| notion-database | Notion skill (query-by-property supported) |
| pdf | Read from local file path, parse text |
| xlsx | Load with skill or openpyxl; agent reads sheet by sheet |
| csv | Direct file read |
| markdown | Direct file read |
| url | web_fetch (cache results for refresh_cadence window) |

## Live query flow (runs during AGENTS.md Step 1.7)

When the customer's message arrives:

1. Agent reads the customer's question.
2. Agent reads the registry and scores each source's relevance to the
   question based on the source's `description` field. Use the agent's
   own model with a brief prompt: "Given this customer question and
   these source descriptions, which sources (if any) should I consult
   before answering? Return source ids only, comma-separated, or 'none'."
3. For each relevant source:
   - If `access_method` includes `live-fetch`: fetch fresh data now
     (Google Sheets API for live spreadsheet rows, Notion API for live
     page content, etc.)
   - If `access_method` is `indexed` only: read the cached index from
     `<MASTER_FILES_DIR>/knowledge-sources/<id>.cache.md`
   - If `access_method` is `both`: use cached index but flag stale data
     if the cache is older than `refresh_cadence`
4. Pass the relevant source content to the reply-drafting step as
   additional context, with explicit marker: "Reference from <source
   name>: <relevant excerpt>"
5. Draft the reply incorporating the data from the source.
6. In the reply, when stating a fact from a source, the agent should
   internally verify the fact came from the source — if it can't find
   support, it should hedge ("I'll need to confirm that with the team")
   rather than fabricate.

## Indexed mode (for large or static sources)

For sources too large to fetch on every query (a 500-page PDF policy
doc, an enormous product catalog), use indexed mode:

1. At setup time (or on a refresh cadence), the agent reads the full
   source and creates a structured summary at
   `<MASTER_FILES_DIR>/knowledge-sources/<id>.cache.md`.
2. The cache is keyword-organized: topics → key facts → source page/row
   references.
3. Live queries hit the cache, not the source.
4. If cache is stale per `refresh_cadence`, agent re-indexes before
   answering.

## Adding sources later (post-setup)

Operator can add a source any time by telling the agent:

```
"Add knowledge source: <source type> at <location>. It covers <topics>.
Access: <live-fetch | indexed | both>. Refresh: <cadence>."
```

The agent appends the new entry to the registry and (if indexed)
performs the initial index.

## Operator override

Operator can disable a source temporarily by setting its `enabled:
false` flag in the registry, without removing it.

## Confidence interaction

When the agent answers from a Knowledge Source, confidence threshold
(Step 9.11) considers the source's freshness:
  - Live-fetched data → high confidence
  - Recently indexed cache → moderate confidence
  - Stale cache → reduced confidence; agent should flag it ("Based on
    last week's pricing — let me double-check current prices")

## Access permissions

For Google / Notion / etc. sources, the operator must share the
document with the OpenClaw agent's service account or provide a
personal access token. If access fails, agent reports the failure
to the operator (not to the customer) and falls back to training
knowledge with a hedging note in the reply.
```

**C. Create the knowledge sources folder + initial registry:**

```bash
mkdir -p "$MASTER_FILES_DIR/knowledge-sources"
```

If operator picked option 1, write the initial `registry.md` with their provided sources. If option 2 or 3, write an empty registry with a comment explaining how to add sources later.

**D. Insert into AGENTS.md** as Step 1.7 (between sentiment check at Step 1.6 and reply draft at Step 2):

```markdown
### Step 1.7 — Consult relevant Knowledge Sources

Before drafting a reply, check the Knowledge Sources registry at
<MASTER_FILES_DIR>/knowledge-sources/registry.md. Score each source's
relevance to the customer's question. For relevant sources, fetch
(live or cached per access_method) and incorporate the data into the
reply context.

When stating a fact in the reply, only state it if a Knowledge Source
or the conversation log supports it. Otherwise, hedge ("I'll need to
check with the team and get back to you") rather than fabricate.

If a Knowledge Source query fails (auth error, network error, doc
deleted), do NOT mention this to the customer. Reply using training
knowledge with a hedging note. Notify operator of the source failure
asynchronously.
```

**E. Update the operator question flow** — capture sources during setup:

If operator picked option 1, the subagent walks through each source:

```
For source #1:
  - What type? (Google Sheet / Google Doc / Notion / PDF / etc.)
  - What's the URL or file path?
  - In a sentence or two, what does it cover? (this helps me know when to
    consult it — "our 2026 product catalog with prices and inventory" is
    much better than "products")
  - Should I check it live every time (slower, always current) or index
    it now and refresh daily? (recommend live for prices/inventory, indexed
    for FAQs/policies)
  - Do I have access? If it's a Google or Notion doc, share it with
    <agent's service account email>.

Repeat for source #2, #3, etc., until operator says "no more sources."
```

**F. Append to Run Manifest:** "Step 9.14 complete — knowledge-source-protocol.md created, knowledge-sources folder + registry initialized with <N> source(s), AGENTS.md Step 1.7 inserted."

