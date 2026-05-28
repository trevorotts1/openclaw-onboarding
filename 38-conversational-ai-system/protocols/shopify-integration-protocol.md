# Shopify Integration Protocol

GraphQL-first Shopify integration. REST endpoints are deprecated by
Shopify as of 2026 — use GraphQL exclusively.

## Capabilities

The agent can do these things via Shopify GraphQL (within allow-list):

1. **Read product catalog** — sync to products/ knowledge base
2. **Check order status** — for customer service inquiries
3. **Check inventory** — for sales conversations ("is X in stock?")
4. **Create draft orders** — for custom-priced or special orders
5. **Look up customer history** — for service/support conversations
6. **Subscribe to webhooks** — order events flow back into OpenClaw

## Common operations

### Look up an order by number

```graphql
query {
  orders(first: 1, query: "name:#1001") {
    edges {
      node {
        id name email displayFulfillmentStatus displayFinancialStatus
        totalPriceSet { shopMoney { amount currencyCode } }
        lineItems(first: 10) {
          edges {
            node { title quantity variant { id sku price } }
          }
        }
      }
    }
  }
}
```

### Check inventory for a product

```graphql
query($productId: ID!) {
  product(id: $productId) {
    title
    variants(first: 20) {
      edges {
        node {
          id title sku availableForSale
          inventoryQuantity
        }
      }
    }
  }
}
```

### Look up customer by email

```graphql
query($email: String!) {
  customers(first: 1, query: $email) {
    edges {
      node {
        id firstName lastName email phone
        numberOfOrders
        amountSpent { amount currencyCode }
      }
    }
  }
}
```

## Webhook setup

For real-time order awareness:

1. In Shopify Admin → Settings → Notifications → Webhooks → Create
2. Endpoint URL: `https://<PUBLIC_HOSTNAME>/hooks/shopify-events`
3. Format: JSON
4. API version: same as configured (2026-04 default)
5. Events to subscribe to:
   - `orders/create`
   - `orders/paid`
   - `orders/cancelled`
   - `orders/fulfilled`
   - `refunds/create`
   - `customers/create`
   - `checkouts/abandoned`

Add `shopify-events` to hooks.mappings in openclaw.json:

```json
{
  "id": "shopify-events",
  "messageTemplate": "Shopify event received: {{topic}}. Order: {{name}}. Customer: {{email}}. Amount: {{total_price}}. Full payload: {{json this}}",
  "sessionKey": "hook:shopify:{{email}}"
}
```

## Per-customer Shopify customer linkage

Link GHL contact ↔ Shopify customer via custom field `shopify_customer_id`
on the GHL contact. Agent looks up Shopify data using this link.

## Allow-list update

Per Step 9.15 allow-list, agent gains action 16:
"Read Shopify catalog, orders, customers within operator-approved
policies. Create draft orders with explicit operator approval per
order."
```

**E. Append to Run Manifest:**

```markdown
