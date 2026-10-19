# GHL MCP Setup — Real Examples

Two retained routes are documented here:

- **Official MCP connection** — client-specific OAuth **v2** endpoints. The documented catalog is
  exactly four tools: `list_locations`, `search_operations`, `describe_operation`, `execute_operation`.
  See `INSTALL.md` → "Action 3".
- **Public REST API** — `https://services.leadconnectorhq.com`, location PIT bearer, and the
  `Version` frozen **per operation** in `evidence/W01/GU-004-CONTRACT-FREEZE.md` §5.

The self-hosted community MCP (`ghl-community-mcp`, the old "Tier 2") is **RETIRED**. It is not
installed by a fresh install, not a fallback, and not a route. Updated boxes must verify it is off
(full checklist in `INSTALL.md` → "Action 5"):

```bash
openclaw mcp list | grep -w ghl-community-mcp && echo "STILL REGISTERED" || echo "registration: absent"
openclaw config get env.vars.GHL_COMMUNITY_MCP_URL 2>&1 | grep -q "http" && echo "ENV VAR STILL SET" || echo "env var: absent"
```

The community examples further down are kept only as **historical migration notes**, each with the
live replacement. Do not call them.

All REST examples assume:
- `$GOHIGHLEVEL_API_KEY` (the PIT) is in your environment
- `$GOHIGHLEVEL_LOCATION_ID` is in your environment

## Official MCP — the documented catalog

Register the documented endpoint for the client the box actually runs (`INSTALL.md`):

```bash
# Claude Code / Claude MCP client (OAuth)
claude mcp add --transport http leadconnector https://services.leadconnectorhq.com/mcp/anthropic/v2
```

| Client | Documented endpoint |
|---|---|
| Claude Code / Claude MCP client | `https://services.leadconnectorhq.com/mcp/anthropic/v2` |
| ChatGPT / Codex / OpenAI clients | `https://services.leadconnectorhq.com/mcp/openai/v2/` |

Authentication is **OAuth**. A PIT bearer sent to an MCP endpoint is an unverified compatibility
mode, never an equivalent auth path.

### List the locations this connection can see

```text
list_locations {}
```

Save the returned location ids; every operation below is scoped to one. No version header is used
by `list_locations`.

### Discover and inspect an operation before executing it

```text
search_operations  {"query": "list products"}
describe_operation {"operationId": "products.list"}
```

`search_operations` is the only lawful discovery source for catalog ids. `describe_operation` is
the schema capture — never call `execute_operation` from a guessed body.

### Execute a discovered operation

```text
execute_operation {
  "operationId": "products.list",
  "arguments": { /* exactly the schema describe_operation returned */ }
}
```

`execute_operation` is a write-capable, per-operation approval-gated tool. Never use it as a
fallback after an unknown REST write.

### Transitional `/mcp/` registration — not the documented catalog

A box that still carries the OpenClaw `ghl-mcp` registration points at the original `/mcp/`
endpoint with a PIT bearer. That surface is **transitional**: per-operation tool names observed
there are **UNVERIFIED** as the v2 catalog and never prove entitlement. Use it as a reachability
probe only (`INSTALL.md` → "Action 4"):

```bash
curl -sS -X POST "https://services.leadconnectorhq.com/mcp/" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "locationId: $GOHIGHLEVEL_LOCATION_ID" \
  -H "Version: 2021-07-28" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | grep "^data:" | head -1 | sed 's/^data: //' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('transitional /mcp/ tools:', [t.get('name') for t in d.get('result',{}).get('tools',[])])"
```

Record the names. Anything beyond the four documented tools is a legacy surface. Do not gate setup
on a count.

## Public REST — concrete tasks

### Search contacts

Freeze: `contacts.search` — `POST /contacts/search`, `Version: v3`. Body tenant is `body.locationId`
(`B-FILTER-SCHEMA`: verify the filter schema with `describe_operation` or the vendor docs before
relying on filter fields).

```bash
curl -sS -X POST "https://services.leadconnectorhq.com/contacts/search" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: v3" \
  -H "Content-Type: application/json" \
  -d '{"locationId":"'"$GOHIGHLEVEL_LOCATION_ID"'","query":"client@email.com","limit":1}' \
  | python3 -m json.tool
```

Expected: a `contacts` array. For one known contact id, `contacts.get` is
`GET /contacts/{contactId}` at `Version: v3`.

Disclosure on agent reply: `[GHL tier used: 3 — contacts.search]`

### Send an SMS

Freeze: `conversations.messages.send` — `POST /conversations/messages`, `Version: v3`,
approval-gated (`B-SEND-STATUS`: verify the send status on the response).

```bash
curl -sS -X POST "https://services.leadconnectorhq.com/conversations/messages" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: v3" \
  -H "Content-Type: application/json" \
  -d '{
    "type":"SMS",
    "contactId":"CONTACT_ID_HERE",
    "message":"Hello from the agent"
  }'
```

Send is a write: approval required, and confirm the returned message id / status.

### Create a blog post — historical example, no frozen REST operation

The frozen registry (`GU-004` §5) has **no blog row**. On a box that still carries the transitional
`/mcp/` registration, the old per-operation name `blogs_create-blog-post` exists, but it is
**UNVERIFIED** as current catalog (`INSTRUCTIONS.md`). Do not present it as the documented v2
catalog and do not invent a REST operation id for it.

```bash
# TRANSITIONAL /mcp/ SURFACE ONLY — UNVERIFIED tool name, not the v2 catalog
curl -sS -X POST "https://services.leadconnectorhq.com/mcp/" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "locationId: $GOHIGHLEVEL_LOCATION_ID" \
  -H "Version: 2021-07-28" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params":{
      "name":"blogs_create-blog-post",
      "arguments":{
        "blogId":"BLOG_ID",
        "title":"Post Title",
        "rawHTML":"<p>Body HTML</p>",
        "urlSlug":"post-slug",
        "status":"PUBLISHED"
      }
    }
  }'
```

## Retired community MCP — historical calls with live replacements

The community MCP's `/execute` endpoint is retired. Each section keeps the old call shape as
history and gives the live route.

### List products — was `ghl_list_products`

Live: `products.list` — `GET /products/`, `Version: v3` (permitted rollback literal `2021-07-28`),
query tenant `locationId`.

```bash
curl -sS "https://services.leadconnectorhq.com/products/?locationId=$GOHIGHLEVEL_LOCATION_ID" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: v3" \
  | python3 -m json.tool
```

Historical: `POST $GHL_COMMUNITY_MCP_URL/execute {"name":"ghl_list_products",...}` — retired.

### List recurring invoice schedules — was `list_invoice_schedules`

**No audited operation id exists.** `list_invoice_schedules`, `get_invoice_schedule`, and
`update_invoice_schedule` are all **UNMAPPED** in the freeze; only `invoices.schedules.create` is
audited. Do not invent one. Run `search_operations` for a live catalog id; if none exists, report a
capability gap.

Historical: `POST $GHL_COMMUNITY_MCP_URL/execute {"name":"list_invoice_schedules",...}` — retired.
Its `result.data.schedules` shape describes the retired tool, not a contract.

### Create a product with price — was `ghl_create_product` + `ghl_create_price`

Live: `products.create` — `POST /products/`, `Version: v3`, approval-gated
(`B-PRODUCT-422`: account availability is not verified). Then `products.prices.create` —
`POST /products/{productId}/price`, `Version: v3`, approval-gated (`B-PRICE-KEY`).

```bash
# Step 1: create the product (body tenant is body.locationId)
curl -sS -X POST "https://services.leadconnectorhq.com/products/" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: v3" \
  -H "Content-Type: application/json" \
  -d '{
    "locationId":"'"$GOHIGHLEVEL_LOCATION_ID"'",
    "name":"My New Product",
    "description":"Description",
    "productType":"DIGITAL",
    "availableInStore":true
  }'

# Step 2: attach a price (capture productId from step 1 response)
curl -sS -X POST "https://services.leadconnectorhq.com/products/PRODUCT_ID_FROM_STEP_1/price" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: v3" \
  -H "Content-Type: application/json" \
  -d '{
    "locationId":"'"$GOHIGHLEVEL_LOCATION_ID"'",
    "name":"Monthly",
    "type":"recurring",
    "currency":"USD",
    "amount":4700,
    "recurring":{"interval":"month","intervalCount":1}
  }'
```

The body shape is carried from the retired tool. Verify it with `describe_operation` or the vendor
docs before writing; do not treat it as a frozen schema.

Historical: `POST $GHL_COMMUNITY_MCP_URL/execute {"name":"ghl_create_product",...}` — retired.

### Send an invoice — was `create_invoice` + `send_invoice`

Live: `invoices.create` — `POST /invoices/`, `Version: v3`, approval-gated
(`B-INVOICE-SCHEMA`: the public schema differs from the retired tool). Then `invoices.send` —
`POST /invoices/{invoiceId}/send`, `Version: v3`, approval-gated.

```bash
# 1. Create the invoice (tenant is body.altId + altType=location)
curl -sS -X POST "https://services.leadconnectorhq.com/invoices/" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: v3" \
  -H "Content-Type: application/json" \
  -d '{
    "altId":"'"$GOHIGHLEVEL_LOCATION_ID"'",
    "altType":"location",
    "name":"Invoice #001",
    "items":[{"name":"Service","price":100,"qty":1}]
  }'

# 2. Send it (capture invoiceId from the response above)
curl -sS -X POST "https://services.leadconnectorhq.com/invoices/INVOICE_ID_FROM_STEP_1/send" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: v3" \
  -H "Content-Type: application/json" \
  -d '{
    "altId":"'"$GOHIGHLEVEL_LOCATION_ID"'",
    "altType":"location",
    "type":"email"
  }'
```

Historical: `POST $GHL_COMMUNITY_MCP_URL/execute {"name":"create_invoice",...}` and
`{"name":"send_invoice",...}` — retired.

### Live tool discovery — was `$GHL_COMMUNITY_MCP_URL/tools`

Live: official MCP `search_operations` (above). There is no parity check against a retired tool
count; the documented catalog is four tools.

Historical: `curl $GHL_COMMUNITY_MCP_URL/tools` — the service is retired. Do not probe it.

## Contact lookup + payment history

```bash
# contacts.search — Version: v3, body tenant locationId
CONTACT_ID=$(curl -sS -X POST "https://services.leadconnectorhq.com/contacts/search" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: v3" \
  -H "Content-Type: application/json" \
  -d '{"locationId":"'"$GOHIGHLEVEL_LOCATION_ID"'","query":"client@email.com","limit":1}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('contacts',[{}])[0].get('id',''))")

# transactions.list — Version: v3, tenant query altId + altType=location
curl -sS "https://services.leadconnectorhq.com/payments/transactions?altId=$GOHIGHLEVEL_LOCATION_ID&altType=location&limit=50" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: v3" \
  | python3 -c "
import json,sys
rows=json.load(sys.stdin).get('transactions',[])
print(json.dumps([r for r in rows if r.get('contactId')=='$CONTACT_ID'][:10], indent=2))
"
```

Freeze row `transactions.list` fixes the tenant query (`altId` + `altType=location`); it does not
freeze a contact filter, so the filter is applied client-side here. Do not invent query parameters.

Disclosure: `[GHL tier used: 3 — contacts.search; transactions.list]`

## Capability-gap example — webhook delivery logs

The retired community MCP's `get_webhook_logs` is **UNMAPPED**, and the frozen registry has no
webhook-log operation. Do not invent one and do not call an undocumented endpoint:

```bash
# 1. Look for a live catalog id first
#    search_operations {"query": "webhook"}
# 2. If none exists, report a capability gap to the owner.
```

Historical: `POST $GHL_COMMUNITY_MCP_URL/execute {"name":"get_webhook_logs",...}` — retired.

## Sub-Agent-Safe Contact Lookup

MCP tools are NOT available inside spawned sub-agents. Use `caf` (Tier 0 CLI) or public REST
instead. Never instruct a sub-agent to call an MCP tool.

### Tier 0 (preferred — works in orchestrator AND sub-agent)

```bash
# Search by email — works from any process
caf contacts search "client@example.com"

# Get by ID
caf contacts get CONTACT_ID_HERE
```

### Sub-agent REST fallback (when caf is unavailable)

`Version` is per operation — `contacts.search` is `v3`. There is no dual-Accept requirement on
REST; the dual Accept rule belongs to the transitional `/mcp/` JSON-RPC surface only. Also note:
NO `grep -P` on macOS — use `python3` for parsing.

```bash
# CORRECT — per-operation Version, python3 parsing, no grep -P
curl -sS -X POST "https://services.leadconnectorhq.com/contacts/search" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: v3" \
  -H "Content-Type: application/json" \
  -d '{"locationId":"'"$GOHIGHLEVEL_LOCATION_ID"'","limit":5}' \
  | python3 -m json.tool

# WRONG — grep -P not supported by BSD grep
# | grep -P '"id"\s*:\s*"([^"]+)"'   <-- NEVER do this
```

### Orchestrator-to-sub-agent pattern

```bash
# Orchestrator: look up contact ID via the official MCP catalog (safe here)
# search_operations -> describe_operation -> execute_operation {operationId:"contacts.search"}
# [GHL tier used: 1 — execute_operation contacts.search]
CONTACT_ID="<id returned by the operation>"

# Sub-agent receives CONTACT_ID, uses caf (no MCP needed)
caf contacts get "$CONTACT_ID"
```

## Smoke Test One-Liners

```bash
# Official MCP registration (documented endpoint)
claude mcp list | grep -w leadconnector

# Retired community MCP must be ABSENT
openclaw mcp list | grep -w ghl-community-mcp && echo "STILL REGISTERED" || echo "registration: absent"
openclaw config get env.vars.GHL_COMMUNITY_MCP_URL 2>&1 | grep -q "http" && echo "ENV VAR STILL SET" || echo "env var: absent"
launchctl print gui/$(id -u)/com.clawd.ghl-mcp >/dev/null 2>&1 && echo "LAUNCHD JOB STILL LOADED" || echo "launchd: not loaded"
systemctl is-enabled ghl-mcp 2>/dev/null | grep -qx enabled && echo "SYSTEMD UNIT STILL ENABLED" || echo "systemd: not enabled"

# REST reachability — products.list, Version: v3
curl -sS "https://services.leadconnectorhq.com/products/?locationId=$GOHIGHLEVEL_LOCATION_ID" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: v3" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('products:', len(d.get('products',[])))"
```
