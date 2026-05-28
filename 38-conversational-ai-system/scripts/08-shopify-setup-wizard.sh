#!/usr/bin/env bash
# 08-shopify-setup-wizard.sh — Skill 38 / Step 9.31 (Shopify Integration, v5.12)
# OPERATOR OPT-IN. GraphQL-first per v5.14 research. Idempotent.

set -euo pipefail
SECRETS_ENV="${OPENCLAW_SECRETS_ENV:-$HOME/.openclaw/secrets/.env}"

echo "[skill 38] Shopify Integration setup wizard (Step 9.31)"
echo "  This is OPERATOR OPT-IN. Skip if you do not use Shopify."
echo "  Skill 38 uses Shopify's GraphQL Admin API (REST is deprecating)."

if grep -qE "^SHOPIFY_ADMIN_API_TOKEN=" "$SECRETS_ENV" 2>/dev/null; then
  echo "[skill 38] SHOPIFY_ADMIN_API_TOKEN already set — preserving."
else
  read -r -p "Shopify shop subdomain (e.g. mystore for mystore.myshopify.com) [skip]: " shop
  if [ -n "${shop:-}" ]; then
    read -r -p "Shopify Admin API token (shpat_...): " tok
    if [ -n "${tok:-}" ]; then
      mkdir -p "$(dirname "$SECRETS_ENV")"
      echo "SHOPIFY_SHOP=$shop"   >> "$SECRETS_ENV"
      echo "SHOPIFY_ADMIN_API_TOKEN=$tok" >> "$SECRETS_ENV"
      chmod 600 "$SECRETS_ENV"
      echo "[skill 38] Shopify creds saved (mode 600)."
    fi
  else
    echo "[skill 38] Shopify setup skipped (no shop entered)."
  fi
fi
echo "[skill 38] See protocols/shopify-integration-protocol.md + references/shopify-graphql-reference.md."
