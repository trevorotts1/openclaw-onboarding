# Shopify Admin GraphQL — Reference

> Deep-dive reference for `protocols/shopify-integration-protocol.md`. Consolidated from
> v5.14 playbook Step 9.31. See `references/v6.0-source-playbook.md` for the canonical block.

## API choice — GraphQL only

Shopify is deprecating the REST Admin API. Skill 38 uses GraphQL exclusively:

```
POST https://{store}.myshopify.com/admin/api/2026-04/graphql.json
X-Shopify-Access-Token: $SHOPIFY_ADMIN_API_TOKEN
Content-Type: application/json
```

## Capabilities the agent uses

- Query products (list, search, filter)
- Read product details (title, description, price, variants, images)
- Read inventory levels (in stock vs out of stock)
- Read collections (groupings)
- Create draft orders (for AI-assisted sales)
- Subscribe to webhooks (order.created, product.updated, etc.)

## Per-customer GHL ↔ Shopify linkage

Custom field `shopify_customer_id` on each GHL contact. Order webhooks fire OpenClaw's
`/hooks/shopify-events` mapping, which links the order to the contact and updates tags.

## Operator opt-in

Most Convert and Flow clients are service-based. Skill 38's `08-shopify-setup-wizard.sh`
is operator opt-in. The protocol file ships regardless so it can be activated later.

