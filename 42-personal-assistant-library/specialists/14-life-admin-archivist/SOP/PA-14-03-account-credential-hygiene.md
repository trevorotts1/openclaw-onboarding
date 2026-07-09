# PA-14-03 — Account & Credential Hygiene

**Department:** Life-Admin Archivist  
**SOP ID:** PA-14-03  
**Owner:** {{TOKEN}}  
**Version:** 1.0.0  
**Last Updated:** 2026-06-02  
**DMAIC Phase:** 3 — Analyze & Design  

---

## Purpose

To maintain a complete, secure, and current inventory of all accounts, subscriptions, and services used by {{TOKEN}} — tracking what exists, who can access it, and how to recover it — without ever storing secrets in plain text.

## Scope

Covers all digital accounts: email, financial, social media, SaaS subscriptions, cloud services, development platforms, domain registrars, hosting providers, and any service that requires authentication.

---

## Procedure

### 1. The Account Inventory (Single Source of Truth)

Maintain one master ledger — a spreadsheet or Notion database — with these columns for every account:

| Field | Example | Notes |
|---|---|---|
| Service Name | Google Workspace | Official product name |
| Account Email/ID | {{OWNER_EMAIL}} | The login identifier |
| Account Type | Business / Personal / Shared | Ownership context |
| Subscription Tier | Business Standard | If paid |
| Monthly Cost | $18.00 | Recurring amount |
| Billing Method | {{PAYMENT_CARD_REF}} | Which card/PayPal |
| Renewal Date | 2026-09-15 | Annual or monthly |
| 2FA Method | Authenticator app | SMS / App / YubiKey / None |
| Recovery Email | {{OWNER_RECOVERY_EMAIL}} | Backup access path |
| Credential Pointer | `~/.openclaw/secrets/.env` → `GCP_SERVICE_ACCOUNT` | **Never the actual secret** — just where it lives |
| Notes | Service account w/ domain-wide delegation, impersonates {{OWNER_EMAIL}} | Context for future retrieval |

### 2. Pointer Hygiene (Critical Rule)

**NEVER store passwords, API keys, tokens, or secrets in the account inventory or any document under `{{WORKSPACE_PATH}}/`.**

Instead, store a *pointer* — a description of where the credential lives:
- `~/.openclaw/secrets/.env` → `STRIPE_API_KEY_MAIN`
- `1Password` → "Google Workspace Admin"
- `macOS Keychain` → "{{KEYCHAIN_ACCOUNT}}"
- `~/.openclaw/secrets/gcp-service-account.json` → `{{GCP_SERVICE_ACCOUNT}}`

The pointer tells you *exactly where to find it* without exposing the value.

### 3. Monthly Account Audit (5th of Every Month)

Run through the inventory and flag:

- **Ghost accounts:** services you're paying for but no longer using. Cancel or downgrade.
- **Weak 2FA:** any account using SMS 2FA where app-based or hardware key is available. Plan the upgrade.
- **Shared credentials:** any account where the password is known to more people than necessary. Rotate.
- **Missing recovery paths:** accounts without a recovery email or backup method. Add one.
- **Billing surprises:** any price increase not previously noted. Investigate.

### 4. Onboarding a New Account

When {{TOKEN}} signs up for a new service:

1. Add it to the inventory immediately — don't wait for the monthly audit.
2. Enable 2FA during setup, not "later."
3. Save the credential to the designated secrets store (`.env` or password manager).
4. Record the pointer in the inventory.
5. Set a calendar reminder for the renewal date (see PA-14-05).

### 5. Offboarding an Account

When closing or abandoning a service:

1. Export data if needed.
2. Cancel the subscription (confirm cancellation email received).
3. Revoke API keys / OAuth grants.
4. Remove from inventory — or mark as `CLOSED` with the closure date for audit trail.
5. Delete the credential from secrets store.

### 6. Emergency Access Protocol

Maintain a sealed emergency-access document (physical or encrypted digital) that answers: "If {{TOKEN}} is incapacitated, how does a trusted person access critical accounts?" This document lives outside the daily system and is updated quarterly.

---

## Tools

| Tool | Purpose |
|---|---|
| 1Password / Bitwarden | Password management |
| macOS Keychain | System-level credential storage |
| `~/.openclaw/secrets/.env` | API keys and service tokens |
| Notion / Google Sheets | Account inventory ledger |

---

## CTQ Checks (Critical-to-Quality)

- [ ] Account inventory reviewed within last 30 days
- [ ] Zero accounts with SMS-only 2FA where app-based is available
- [ ] Every account has a recovery path documented
- [ ] Zero plain-text secrets found in any document under `{{WORKSPACE_PATH}}/`
- [ ] Emergency access document updated within last 90 days
- [ ] All closed accounts marked with closure date, not deleted

---

## Warm Reminder

Account hygiene is the least-glamorous admin task — and the one that saves you when everything else goes wrong. A forgotten subscription drains money. A lost recovery path locks you out forever. A leaked secret is a disaster. Fifteen minutes a month on this SOP prevents all three. You are not the vault — you are the map to the vault.

---

## Definition of Done

Every account {{TOKEN}} owns is in the ledger with a credential pointer, the monthly audit is clean, and zero plain-text secrets exist in any document.

## Tone & Persona Note

Account hygiene is invisible until it isn't — and when it fails, it fails catastrophically. You're not the vault; you're the map to the vault. Approach monthly audits with the calm diligence of someone who knows that 15 minutes now prevents a 15-hour disaster later. For Black women professionals managing personal AND business accounts, the mental load of "which login is this?" is real — your ledger carries that weight so she doesn't have to. Never store a secret; always store the pointer.

## Escalation

- Plain-text credential discovered in any document → redact immediately; move value to secrets store; update pointer in ledger; flag to {{TOKEN}} via Specialist 09 (Daily Check-In) with confirmation of remediation
- Account with missing recovery path after 2 audit cycles → escalate to {{TOKEN}} via Specialist 09 (Daily Check-In); recovery path is non-negotiable for critical accounts
- SMS-only 2FA on account where app-based is available → flag for upgrade plan; escalate to {{TOKEN}} via Specialist 09 (Daily Check-In) if account is financial/email/business-critical
- Paid subscription with zero usage in 90+ days → flag to Specialist 11's PA-11-02 (Subscription Audit) for cancellation evaluation
- Emergency access document not updated in 90+ days → escalate to {{TOKEN}} via Specialist 09 (Daily Check-In) for review

*Generated by Life-Admin Archivist | Department 14 | {{TOKEN}}*
