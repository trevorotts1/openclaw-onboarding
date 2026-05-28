# Typed Knowledge Bases Protocol

Four purpose-specific knowledge bases the agent queries based on
conversation context. All four use the same architecture; what differs
is the SCOPE of content each holds and WHEN the agent queries each.

## The four bases

### business/
What the company IS. Mission, values, team, services overview, history,
brand voice guidelines, business hours, locations, contact info, legal
disclaimers, refund policy, terms of service.

Queried by: EVERY conversation (light touch for context).
Built from: operator-provided docs + web scrape of company website
(Feature 39, when shipped).

### products/
What the company SELLS. Product registry, prices, FAQs, sales pages,
ad copy, ad images URLs, upsells/downsells/bumps, payment processor
IDs (Stripe product/price IDs, GHL product IDs, Shopify IDs).

Queried by: sales conversations PRIMARILY, plus any customer asking
about specific products.
Built from: operator product onboarding flow + sales page scraping
(Feature 39).

### sales/
How the company SELLS. Best practices specific to this business,
objection scripts that work, competitive intel, success stories,
testimonials, case studies, ICP (ideal customer profile) definitions,
sales-specific tone guidelines.

Queried by: sales conversations.
Built from: operator-provided sales content + competitive site scrapes
(Feature 39) + Sales Brain (Feature 26) general patterns.

### conversations/
What the company LEARNS. Distilled patterns from past conversations
(built up by Dreaming over time): what works, what doesn't, common
questions, surprising customer concerns, language customers actually
use vs language the business uses internally.

Queried by: any conversation, especially when current conversation has
unclear signals.
Built from: Dreaming consolidation (per O.6) over time. Starts empty
and grows as Dreaming runs.

## Querying by context

The agent decides which base(s) to query based on conversation context:

| Conversation type | Primary base | Secondary bases |
|---|---|---|
| Inbound sales (pricing inquiry, etc.) | sales/ | products/, business/ |
| Customer support (problem) | business/ | products/, conversations/ |
| Customer service (informational) | business/ | products/ |
| Generic / unclear | conversations/ | business/ |
| Existing customer follow-up | products/, conversations/ | business/ |

Querying is via OpenClaw's `memory_search` with a base-scope parameter:

```
memory_search(query: "pricing objections for high-ticket coaching", scope: "knowledgebases/sales")
```

The agent passes the `scope` parameter to limit the search to the
relevant base. If a query returns nothing from the scoped base, the
agent can expand scope to secondary bases.

## Adding entries

The agent adds entries by writing markdown files into the appropriate
base folder. Each entry has YAML frontmatter (title, tags,
last_updated, source) and content body.

After writing the file, the agent updates the base's `registry.md`
with a new row.

The agent also triggers a re-index so memory_search picks up the new
content:

```
openclaw memory index --path "<MASTER_FILES_DIR>/KnowledgeBases"
```

## Migration from old Knowledge Sources (Feature 12)

If `<MASTER_FILES_DIR>/knowledge-sources/` exists from a prior v5.1+
setup, the agent migrates content during this step:

1. Read existing `knowledge-sources/registry.md`
2. For each registered source, categorize it:
   - Sales pages / product info → products/
   - Mission / about / team docs → business/
   - Testimonials / case studies / objection scripts → sales/
   - Customer pattern docs (if any) → conversations/
   - Ambiguous → ask operator
3. Move each source file to the target base folder
4. Update each base's `registry.md`
5. Archive the old `knowledge-sources/` folder by renaming it
   `knowledge-sources--migrated-YYYY-MM-DD/` — don't delete in case
   the operator needs to verify the migration

## Always inside the master files folder

The KnowledgeBases folder ALWAYS lives at
`<MASTER_FILES_DIR>/KnowledgeBases/`. The agent uses the
`MASTER_FILES_DIR` variable resolved during O.2 — never hardcodes
a path. On Mac Mini this typically resolves to
`~/Downloads/OpenClaw Master Files/KnowledgeBases/`; on VPS it might
be `/data/openclaw-master-files/KnowledgeBases/`.

If MASTER_FILES_DIR isn't set (which shouldn't happen if O.2 completed),
the agent stops and re-runs O.2 rather than guessing at a path.
```

**D. Update AGENTS.md Step 1.7** to query the typed bases instead of the old single Knowledge Sources folder:

```markdown
### Step 1.7 — Query the appropriate Typed Knowledge Base

Based on conversation context, query the appropriate typed knowledge
base via memory_search with the relevant scope.

Routing table:
- Sales conversation → scope: "knowledgebases/sales", fall back to
  "knowledgebases/products" and "knowledgebases/business"
- Support conversation → scope: "knowledgebases/business", fall back
  to "knowledgebases/products" and "knowledgebases/conversations"
- Service conversation → scope: "knowledgebases/business", fall back
  to "knowledgebases/products"
- Unclear → scope: "knowledgebases/conversations", fall back to
  "knowledgebases/business"

If the primary scope returns no relevant results, expand to fallback
bases before declaring no knowledge available.

See typed-knowledge-bases-protocol.md for full routing details.
```

**E. Migrate existing Knowledge Sources (if present)**

```bash
OLD_KS="$MASTER_FILES_DIR/knowledge-sources"
if [ -d "$OLD_KS" ]; then
  echo "Found existing Knowledge Sources from v5.1+. Migrating..."
  # For each file, the agent reads the content and categorizes it
  # (this requires the agent to actually process each file, not a blind copy)
  # After migration, archive the old folder
  TS=$(date +%Y-%m-%d)
  mv "$OLD_KS" "$MASTER_FILES_DIR/knowledge-sources--migrated-$TS"
fi
```

**F. Append to MEMORY.md design principles**

Add Rule 7:

```markdown
### Rule 7 — Use Typed Knowledge Bases by context

The agent has four typed knowledge bases at <MASTER_FILES_DIR>/KnowledgeBases/:
business/, products/, sales/, conversations/. Query the appropriate
base based on conversation context (sales → sales/, support → business/,
etc.). Never query all four bases by default — that's wasteful and
makes results noisier.

See typed-knowledge-bases-protocol.md for the full routing table.
```

**G. Append to Run Manifest:**

```markdown
