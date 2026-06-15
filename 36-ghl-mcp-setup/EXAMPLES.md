# GHL MCP Setup — Real Examples

All examples assume:
- `$GOHIGHLEVEL_API_KEY` (the PIT) is in your environment
- `$GOHIGHLEVEL_LOCATION_ID` is in your environment
- `$GHL_COMMUNITY_MCP_URL` resolves to `http://localhost:8765` (or whichever port was assigned)

## Tier 1 — Official MCP Examples

### Get location info

```bash
curl -sS -X POST "https://services.leadconnectorhq.com/mcp/" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "locationId: $GOHIGHLEVEL_LOCATION_ID" \
  -H "Version: 2021-07-28" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"locations_get-location\",\"arguments\":{\"locationId\":\"$GOHIGHLEVEL_LOCATION_ID\"}}}" \
  | grep "^data:" | head -1 | sed 's/^data: //' | python3 -m json.tool
```

Expected: JSON with `success:true` and a `data.location` object including name, address, email, phone.

Disclosure on agent reply: `[GHL tier used: 1 — locations_get-location]`

### Search contacts

```bash
curl -sS -X POST "https://services.leadconnectorhq.com/mcp/" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "locationId: $GOHIGHLEVEL_LOCATION_ID" \
  -H "Version: 2021-07-28" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"contacts_get-contacts","arguments":{"limit":5}}}' \
  | grep "^data:" | head -1 | sed 's/^data: //' | python3 -m json.tool
```

### Send an SMS

```bash
curl -sS -X POST "https://services.leadconnectorhq.com/mcp/" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "locationId: $GOHIGHLEVEL_LOCATION_ID" \
  -H "Version: 2021-07-28" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params":{
      "name":"conversations_send-a-new-message",
      "arguments":{
        "type":"SMS",
        "contactId":"CONTACT_ID_HERE",
        "message":"Hello from the agent"
      }
    }
  }'
```

### Create a blog post

```bash
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

## Tier 2 — Community MCP Examples

The community MCP also supports a plain REST `/execute` endpoint that bypasses the streaming MCP protocol — useful for debugging and one-shot calls.

### List products

```bash
curl -sS -X POST $GHL_COMMUNITY_MCP_URL/execute \
  -H "Content-Type: application/json" \
  -d '{"name":"ghl_list_products","arguments":{"limit":3}}' \
  | python3 -m json.tool
```

Disclosure: `[GHL tier used: 2 — ghl_list_products]`

### List recurring invoice schedules

```bash
curl -sS -X POST $GHL_COMMUNITY_MCP_URL/execute \
  -H "Content-Type: application/json" \
  -d '{"name":"list_invoice_schedules","arguments":{"limit":50}}' \
  | python3 -m json.tool
```

Look at `result.data.schedules` for the active list (filter `status:"active"` and `deleted:false`).

### Create a product with price

```bash
# Step 1: create the product
curl -sS -X POST $GHL_COMMUNITY_MCP_URL/execute \
  -H "Content-Type: application/json" \
  -d '{
    "name":"ghl_create_product",
    "arguments":{
      "name":"My New Product",
      "description":"Description",
      "productType":"DIGITAL",
      "availableInStore":true
    }
  }'

# Step 2: attach a price (capture productId from step 1 response)
curl -sS -X POST $GHL_COMMUNITY_MCP_URL/execute \
  -H "Content-Type: application/json" \
  -d '{
    "name":"ghl_create_price",
    "arguments":{
      "productId":"PRODUCT_ID_FROM_STEP_1",
      "name":"Monthly",
      "type":"recurring",
      "currency":"USD",
      "amount":4700,
      "recurring":{"interval":"month","intervalCount":1}
    }
  }'
```

### Send an invoice

```bash
# 1. Create the invoice
curl -sS -X POST $GHL_COMMUNITY_MCP_URL/execute \
  -H "Content-Type: application/json" \
  -d '{
    "name":"create_invoice",
    "arguments":{
      "contactId":"CONTACT_ID",
      "name":"Invoice #001",
      "items":[{"name":"Service","price":100,"qty":1}]
    }
  }'

# 2. Send it (capture invoiceId from response above)
curl -sS -X POST $GHL_COMMUNITY_MCP_URL/execute \
  -H "Content-Type: application/json" \
  -d '{
    "name":"send_invoice",
    "arguments":{
      "invoiceId":"INVOICE_ID_FROM_STEP_1",
      "type":"email"
    }
  }'
```

### Live tool discovery

```bash
curl -sS $GHL_COMMUNITY_MCP_URL/tools | python3 -c "
import json,sys
tools=json.load(sys.stdin).get('tools',[])
print(f'Total: {len(tools)}')
# Find tools matching a keyword
import re
pattern=re.compile(r'invoice', re.IGNORECASE)
matches=[t['name'] for t in tools if pattern.search(t['name'])]
print(f'Matching invoice: {len(matches)}')
for n in matches[:20]: print(f'  - {n}')
"
```

## Cross-Tier Example — Contact lookup + payment history

```bash
# Tier 1: find the contact
CONTACT_ID=$(curl -sS -X POST "https://services.leadconnectorhq.com/mcp/" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "locationId: $GOHIGHLEVEL_LOCATION_ID" \
  -H "Version: 2021-07-28" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"contacts_search-contacts","arguments":{"query":"client@email.com","limit":1}}}' \
  | grep "^data:" | sed 's/^data: //' \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('result',{}).get('content',[{}])[0].get('text',''))" \
  | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('contacts',[{}])[0].get('id',''))")

# Tier 2: get their transactions
curl -sS -X POST $GHL_COMMUNITY_MCP_URL/execute \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"list_transactions\",\"arguments\":{\"contactId\":\"$CONTACT_ID\",\"limit\":10}}"
```

Disclosure: `[GHL tier used: 1+2 — contacts_search-contacts; list_transactions]`

## Tier 3 Fall-Through Example

When neither MCP has the tool (e.g., webhook delivery logs):

```bash
# 1. Try Tier 2
RESULT=$(curl -sS -X POST $GHL_COMMUNITY_MCP_URL/execute \
  -H "Content-Type: application/json" \
  -d '{"name":"get_webhook_logs","arguments":{}}')

# If 404 or "Tool not found", fall through to Tier 3 (direct API)
curl -sS "https://services.leadconnectorhq.com/hooks/?locationId=$GOHIGHLEVEL_LOCATION_ID" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-07-28"
```

Disclosure: `[GHL tier used: 3 (Tier 1 lacked tool: webhooks; Tier 2 returned 404) — raw API GET /hooks/]`

## Sub-Agent-Safe Contact Lookup

MCP tools are NOT available inside spawned sub-agents. Use `caf` (Tier 0 CLI) or
raw HTTPS instead. Never instruct a sub-agent to call `ghl-mcp__*` tools.

### Tier 0 (preferred — works in orchestrator AND sub-agent)

```bash
# Search by email — works from any process
caf contacts search "client@example.com"

# Get by ID
caf contacts get CONTACT_ID_HERE
```

### Sub-agent Tier 3 fallback (when caf is unavailable)

Note the MANDATORY dual Accept header — missing `text/event-stream` causes HTTP 406.
Also note: NO `grep -P` on macOS — use `python3` for parsing.

```bash
# CORRECT — dual Accept, python3 parsing, no grep -P
curl -sS -X POST "https://services.leadconnectorhq.com/mcp/" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "locationId: $GOHIGHLEVEL_LOCATION_ID" \
  -H "Version: 2021-07-28" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"contacts_get-contacts","arguments":{"limit":5}}}' \
  | grep "^data:" | head -1 | sed 's/^data: //' | python3 -m json.tool

# WRONG — missing text/event-stream → HTTP 406
# -H "Accept: application/json"   <-- this alone is WRONG

# WRONG on macOS — grep -P not supported by BSD grep
# | grep -P '"id"\s*:\s*"([^"]+)"'   <-- NEVER do this
```

### Orchestrator-to-sub-agent pattern

```bash
# Orchestrator: look up contact ID via MCP tool (safe here)
# [GHL tier used: 1 — contacts_search-contacts]
CONTACT_ID="<id returned by MCP>"

# Sub-agent receives CONTACT_ID, uses caf (no MCP needed)
caf contacts get "$CONTACT_ID"
```

## Smoke Test One-Liners

Save these for fast verification at any time:

```bash
# Tier 1 health
curl -sS -X POST "https://services.leadconnectorhq.com/mcp/" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "locationId: $GOHIGHLEVEL_LOCATION_ID" \
  -H "Version: 2021-07-28" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | grep "^data:" | head -1 | sed 's/^data: //' \
  | python3 -c "import json,sys; print('Tier 1:', len(json.load(sys.stdin).get('result',{}).get('tools',[])), 'tools')"

# Tier 2 health
curl -sS $GHL_COMMUNITY_MCP_URL/health | python3 -m json.tool

# Tier 2 process status (macOS)
launchctl print gui/$(id -u)/com.clawd.ghl-mcp | grep -E "state|pid"

# Tier 2 process status (Linux)
systemctl status ghl-mcp --no-pager
```
