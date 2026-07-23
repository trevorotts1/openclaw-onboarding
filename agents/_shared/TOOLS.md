# agents/_shared/TOOLS.md — Shared Tool Registry

> Canonical inventory of integrations, credential types, and allowed capabilities
> shared across all agents on this box. Every agent reads this file at session start.
> Tools are documented by credential type and capability boundary only — never by value.

---

## Podbean (podcast hosting and distribution)

| Field | Value |
|---|---|
| **Integration** | Podbean podcast hosting and distribution platform |
| **Purpose** | Upload, publish, host, and distribute podcast episodes via RSS |
| **Credential type** | `PODBEAN_CLIENT_ID` (string), `PODBEAN_CLIENT_SECRET` (secret), `PODBEAN_CHANNEL_ID` (string) |
| **Allowed capability** | `podcast:episode:publish` — create and publish a podcast episode; `podcast:episode:upload` — upload audio media; `podcast:episode:query` — read episode metadata, permalink, and status |
| **Operating boundary** | The Podbean integration is accessed ONLY through the n8n Podbean Broker (`podbean-broker.workflow.json`) which mints Channel-scoped access tokens. The client box holds only the broker webhook URL, a shared token, and the `PODBEAN_CHANNEL_ID`. Podbean app credentials (`client_id`/`client_secret`) never leave the n8n instance. Direct Podbean API calls from the client box are FORBIDDEN — all Podbean operations route through the broker. |
| **Used by** | Skill 58 — Podcast Production Engine; Step 15 (publish) and Step 16 (enroll permalink) |
| **See also** | `58-podcast-production-engine/config/n8n/README.md` — broker workflow documentation |
