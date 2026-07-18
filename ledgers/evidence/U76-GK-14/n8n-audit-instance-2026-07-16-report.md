# n8n Security Audit Report
Generated: 2026-07-16T16:10:52.395Z | Instance: https://main.blackceoautomations.com

## Summary
| Severity | Count |
|----------|-------|
| Critical | 25 |
| High | 141 |
| Medium | 324 |
| Low | 8 |
| **Total** | **498** |

Workflows scanned: 286 | Scan duration: 41.3s

- Built-in audit failed (no response from n8n): No response from n8n server

---

## Findings by Workflow

### "1MLT Speaker Quiz - Contact + Email" (id: FLTASpOvJelzbI3H) — 6 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-003 | Critical | Hardcoded jwt_token detected | Mark Email Sent in Supabase | Auto-fix |
| CRED-001 | High | Hardcoded bearer_token detected | Create GHL Contact | Auto-fix |
| CRED-002 | High | Hardcoded bearer_token detected | Send GHL Email | Auto-fix |
| CRED-004 | High | Hardcoded bearer_token detected | Mark Email Sent in Supabase | Auto-fix |
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Quiz Webhook" | Quiz Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "1MLT Speaker Quiz - Contact + Email" | — | Review |

### "1MLT Speaker Quiz - Contact + Email" (id: NorcPNC4T3dCYjhF) [ACTIVE] — 6 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-003 | Critical | Hardcoded jwt_token detected | Mark Email Sent | Auto-fix |
| CRED-001 | High | Hardcoded bearer_token detected | Create GHL Contact | Auto-fix |
| CRED-002 | High | Hardcoded bearer_token detected | Send GHL Email | Auto-fix |
| CRED-004 | High | Hardcoded bearer_token detected | Mark Email Sent | Auto-fix |
| WEBHOOK-001 | High | Unauthenticated webhook: "Quiz Webhook" | Quiz Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "1MLT Speaker Quiz - Contact + Email" | — | Review |

### "1MLT Speaker Quiz - Contact + Email" (id: ggfDH6BuPM88AoQj) — 6 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-003 | Critical | Hardcoded jwt_token detected | Mark Email Sent in Supabase | Auto-fix |
| CRED-001 | High | Hardcoded bearer_token detected | Create GHL Contact | Auto-fix |
| CRED-002 | High | Hardcoded bearer_token detected | Send GHL Email | Auto-fix |
| CRED-004 | High | Hardcoded bearer_token detected | Mark Email Sent in Supabase | Auto-fix |
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Quiz Webhook" | Quiz Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "1MLT Speaker Quiz - Contact + Email" | — | Review |

### "1MLT Speaker Quiz - Contact + Email" (id: w0ggoGsVrEr8jiNa) — 6 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-003 | Critical | Hardcoded jwt_token detected | Mark Email Sent in Supabase | Auto-fix |
| CRED-001 | High | Hardcoded bearer_token detected | Create GHL Contact | Auto-fix |
| CRED-002 | High | Hardcoded bearer_token detected | Send GHL Email | Auto-fix |
| CRED-004 | High | Hardcoded bearer_token detected | Mark Email Sent in Supabase | Auto-fix |
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Quiz Webhook" | Quiz Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "1MLT Speaker Quiz - Contact + Email" | — | Review |

### "All In One Sales Page Assets" (id: szAK4uQ34hNhPDHP) [ACTIVE] — 5 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-003 | Critical | Hardcoded anthropic_key detected | Claude Copy | Auto-fix |
| CRED-001 | High | Hardcoded bearer_token detected | Image Generation (OpenAI Image 1) | Auto-fix |
| WEBHOOK-001 | High | Unauthenticated webhook: "GHL Trigger" | GHL Trigger | Auto-fix |
| CRED-002 | Medium | Hardcoded phone detected | ImgBB Upload | Review |
| ERR-001 | Medium | No error handling in workflow "All In One Sales Page Assets" | — | Review |

### "All In One Sales Page Assets PiAPI" (id: PZjOMYDhAMWDHfIB) [ACTIVE] — 4 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Critical | Hardcoded anthropic_key detected | Claude Copy | Auto-fix |
| CRED-002 | High | Hardcoded bearer_token detected | Image Generation (OpenAI Image 1) | Auto-fix |
| WEBHOOK-001 | High | Unauthenticated webhook: "GHL Trigger2" | GHL Trigger2 | Auto-fix |
| CRED-003 | Medium | Hardcoded phone detected | ImgBB Upload2 | Review |

### "Branch 00 - Sales Page Assets Image/Claude Branch" (id: NcgzLyL38rHsNSbG) — 5 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-003 | Critical | Hardcoded anthropic_key detected | Claude Copy | Auto-fix |
| CRED-001 | High | Hardcoded bearer_token detected | Image Generation (OpenAI Image 1) | Auto-fix |
| CRED-002 | Medium | Hardcoded phone detected | ImgBB Upload | Review |
| WEBHOOK-001 | Medium | Unauthenticated webhook: "GHL Trigger" | GHL Trigger | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Branch 00 - Sales Page Assets Image/Claude Branch" | — | Review |

### "GHL API Test" (id: m7ccEmtzi4vhoZlb) — 11 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Critical | Hardcoded jwt_token detected | LocationID from Email | Auto-fix |
| CRED-004 | Critical | Hardcoded jwt_token detected | All Location IDs | Auto-fix |
| CRED-006 | Critical | Hardcoded jwt_token detected | HTTP Request | Auto-fix |
| CRED-002 | High | Hardcoded bearer_token detected | LocationID from Email | Auto-fix |
| CRED-005 | High | Hardcoded bearer_token detected | All Location IDs | Auto-fix |
| CRED-007 | High | Hardcoded bearer_token detected | HTTP Request | Auto-fix |
| CRED-008 | High | Hardcoded bearer_token detected | HTTP Request1 | Auto-fix |
| CRED-009 | High | Hardcoded bearer_token detected | HTTP Request2 | Auto-fix |
| CRED-003 | Medium | Hardcoded email detected | LocationID from Email | Review |
| CRED-010 | Medium | Hardcoded email detected | HighLevel1 | Review |
| ERR-001 | Medium | No error handling in workflow "GHL API Test" | — | Review |

### "Image Branch 1A Sales Page Assets PiAPI" (id: PfjXx6Cy1v5DQVLf) — 4 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Critical | Hardcoded anthropic_key detected | Claude Copy | Auto-fix |
| CRED-002 | High | Hardcoded bearer_token detected | Image Generation (OpenAI Image 1) | Auto-fix |
| CRED-003 | Medium | Hardcoded phone detected | ImgBB Upload2 | Review |
| WEBHOOK-001 | Medium | Unauthenticated webhook: "GHL Trigger2" | GHL Trigger2 | Auto-fix |

### "Image Branch 1A Sales Page Assets PiAPI UPD" (id: hwSmVpxGXrbC71hw) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Critical | Hardcoded anthropic_key detected | Claude Copy | Auto-fix |
| WEBHOOK-001 | High | Unauthenticated webhook: "GHL Trigger2" | GHL Trigger2 | Auto-fix |

### "Image Branch 1A Sales Page Assets PiAPI UPD copy" (id: wbKGfGHcizepLj1A) — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Critical | Hardcoded anthropic_key detected | Claude Copy | Auto-fix |
| WEBHOOK-001 | Medium | Unauthenticated webhook: "GHL Trigger2" | GHL Trigger2 | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Image Branch 1A Sales Page Assets PiAPI UPD copy" | — | Review |

### "Image Branch 1A Sales Page Assets PiAPI UPD copy 2" (id: Egqu5u0QkN9kxPMO) — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Critical | Hardcoded anthropic_key detected | Claude Copy | Auto-fix |
| WEBHOOK-001 | Medium | Unauthenticated webhook: "GHL Trigger2" | GHL Trigger2 | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Image Branch 1A Sales Page Assets PiAPI UPD copy 2" | — | Review |

### "Image Branch 1A Sales Page Assets PiAPI UPD copy 3" (id: t7hF656a7uhVXPI7) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Critical | Hardcoded anthropic_key detected | Claude Copy | Auto-fix |
| WEBHOOK-001 | Medium | Unauthenticated webhook: "GHL Trigger2" | GHL Trigger2 | Auto-fix |

### "Image Branch 1A Sales Page Assets PiAPI UPD copy 4" (id: H3az5X572iB3p0bK) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Critical | Hardcoded anthropic_key detected | Claude Copy | Auto-fix |
| WEBHOOK-001 | Medium | Unauthenticated webhook: "GHL Trigger2" | GHL Trigger2 | Auto-fix |

### "Image Branch 1A Sales Page Assets PiAPI UPD NEW Docs" (id: 88rfHnmP8N91gqs0) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Critical | Hardcoded anthropic_key detected | Claude Copy | Auto-fix |
| WEBHOOK-001 | Medium | Unauthenticated webhook: "GHL Trigger2" | GHL Trigger2 | Auto-fix |

### "Image Branch 1A Sales Page Assets PiAPI UPD No Clean" (id: 4murSds8XQMSw1SO) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Critical | Hardcoded anthropic_key detected | Claude Copy | Auto-fix |
| WEBHOOK-001 | Medium | Unauthenticated webhook: "GHL Trigger2" | GHL Trigger2 | Auto-fix |

### "LinkedIn Custom Scraper" (id: QZDtI0OrH6oG07mz) [ACTIVE] — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Critical | Hardcoded google_api_key detected | Search Google | Auto-fix |
| WEBHOOK-001 | High | Unauthenticated webhook: "On form submission" | On form submission | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "LinkedIn Custom Scraper" | — | Review |

### "OLD Sales Page Assets BR PiAPI" (id: HYkB18Hhv6hvDWYq) — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-002 | Critical | Hardcoded anthropic_key detected | Claude Copy | Auto-fix |
| CRED-001 | Medium | Hardcoded email detected | Gmail | Review |
| WEBHOOK-001 | Medium | Unauthenticated webhook: "GHL Trigger" | GHL Trigger | Auto-fix |

### "Quiz Landing Page - GitHub Pages + GHL Custom Values" (id: zcoeE62zRQSzsWij) [ACTIVE] — 4 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Critical | Hardcoded url_with_auth detected | copy Set Node 1 (4-Image Path) | Auto-fix |
| CRED-002 | Critical | Hardcoded url_with_auth detected |  copy Set Node 2 (6-Image Path) | Auto-fix |
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Quiz Landing Page - GitHub Pages + GHL Custom Values" | — | Review |

### "Quiz Landing Page Generator v2" (id: dFQzKX41ZHM20tpO) [ACTIVE] — 4 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Critical | Hardcoded url_with_auth detected | Set Node 2 (6-Image Path) | Auto-fix |
| CRED-002 | Critical | Hardcoded url_with_auth detected | Set Node 1 (4-Image Path) | Auto-fix |
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Quiz Landing Page Generator v2" | — | Review |

### "TREVORS LinkedIn EMAIL scraper" (id: zb0KliQmcSkxg7tF) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Critical | Hardcoded google_api_key detected | Search Google | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "TREVORS LinkedIn EMAIL scraper" | — | Review |

### "🎯 Trevor Speaks Bot - Welcome + Alerts" (id: AjKob0e5T8aEn09o) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Telegram Events" | Telegram Events | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "🎯 Trevor Speaks Bot - Welcome + Alerts" | — | Review |

### "🔐 n8n Self-Backup -> Google Drive (nightly)" (id: EmtrZVxg0Ok59x77) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Backup Ready (from host script)" | Backup Ready (from host script) | Auto-fix |
| RETENTION-001 | Low | Excessive data retention in workflow "🔐 n8n Self-Backup -> Google Drive (nightly)" | — | User action |

### "01-Social media in a box main orchestrator" (id: S8rFFVv6OE5fKhPo) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook Trigger" | Webhook Trigger | Auto-fix |

### "4x3x3 w Book Writer" (id: KF6PCxzSzKWeOwN6) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | High | Hardcoded bearer_token detected | Image Generation (OpenAI Image 1) | Auto-fix |
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |

### "Abundance Broadcast System" (id: GrzxRlJzhBfQ9mR5) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Lovable Webhook" | Lovable Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Abundance Broadcast System" | — | Review |

### "Anthology Drive Broker (51-node, staged - GK-02)" (id: S8E6c41WfB8fAGiL) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook anthology-drive" | Webhook anthology-drive | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Anthology Drive Broker (51-node, staged - GK-02)" | — | Review |

### "Anthology Writer - [CLIENT]" (id: 62EeUqT5Da63U4Kh) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Anthology Writer - [CLIENT]" | — | Review |

### "Avatar Alchemist Brand Intelligence" (id: lEDCuz11DZMfzWyT) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook2" | Webhook2 | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Avatar Alchemist Brand Intelligence" | — | Review |

### "Avatar Quiz - Segments 1 and 2 Complete" (id: qdJGtJkqZEntz6Fx) [ACTIVE] — 5 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "N8N Form Trigger" | N8N Form Trigger | Auto-fix |
| WEBHOOK-002 | High | Unauthenticated webhook: "Webhook - GHL Convert and Flow" | Webhook - GHL Convert and Flow | Auto-fix |
| WEBHOOK-003 | High | Unauthenticated webhook: "Webhook - Loveable" | Webhook - Loveable | Auto-fix |
| CRED-001 | Medium | Hardcoded email detected | N8N Form Trigger | Review |
| ERR-001 | Medium | No error handling in workflow "Avatar Quiz - Segments 1 and 2 Complete" | — | Review |

### "BLACKCEO LIVE - Command Center Client Registration" (id: i0P3OWCEsXZxVo0N) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook: Client Registration" | Webhook: Client Registration | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "BLACKCEO LIVE - Command Center Client Registration" | — | Review |

### "Book Writer" (id: 4d50PNmVOyE9GJWz) [ACTIVE] — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | High | Hardcoded bearer_token detected | Image Generation (OpenAI Image 1) | Auto-fix |
| CRED-002 | High | Hardcoded bearer_token detected | Image Generation (OpenAI Image 1)1 | Auto-fix |
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook2" | Webhook2 | Auto-fix |

### "Bot-to-Bot Bridge (Stefanie ↔ Curtis)" (id: elLNGimbKoShrkCU) [ACTIVE] — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| CRED-001 | Medium | Hardcoded phone detected | Process Message | Review |
| ERR-001 | Medium | No error handling in workflow "Bot-to-Bot Bridge (Stefanie ↔ Curtis)" | — | Review |

### "Branch 1A - Sales Page Assets Gemini" (id: clIxY2Qvvvlgfmzs) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Branch 1A - Sales Page Assets Gemini" | — | Review |

### "Branch 1B - Sales Page Assets Upsell" (id: iKqzc1kjcfJbXV9y) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Branch 1B - Sales Page Assets Upsell" | — | Review |

### "Branch 1C - Sales Page Assets Upsell B" (id: j3aavSISsnWc9z8F) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Branch 1C - Sales Page Assets Upsell B" | — | Review |

### "Branch 1D - Sales Page Assets Downsell" (id: HbsKXYxqnKwnwXxg) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Branch 1D - Sales Page Assets Downsell" | — | Review |

### "Branch 1E - Sales Page Assets High Ticket" (id: vEcz5dNLWDL9A3E7) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Branch 1E - Sales Page Assets High Ticket" | — | Review |

### "Branch 1F - Sales Page Assets Bump Sale" (id: KGKwjJYCPQCuxoqG) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Branch 1F - Sales Page Assets Bump Sale" | — | Review |

### "Chapter Rewriter for [CLIENT]" (id: MD1TQHPm34KVi1X1) [ACTIVE] — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "chapter rewriter" | chapter rewriter | Auto-fix |
| CRED-001 | Medium | Hardcoded email detected | Send a message | Review |
| ERR-001 | Medium | No error handling in workflow "Chapter Rewriter for [CLIENT]" | — | Review |

### "Cinematic Car Ads Generator (VEO 3.1 + n8n)" (id: 7fxuZp0oLDIP7Lkp) [ACTIVE] — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "On form submission" | On form submission | Auto-fix |
| CRED-001 | Medium | Hardcoded email detected | Sticky Note1 | Review |
| ERR-001 | Medium | No error handling in workflow "Cinematic Car Ads Generator (VEO 3.1 + n8n)" | — | Review |

### "Client Data Extractor - Clients Bceo" (id: qFtysUwL2yw4NZzn) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Client Data Extractor - Clients Bceo" | — | Review |

### "Delete Social Media Posts" (id: nybi2MzHkige82jT) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Delete Social Media Posts" | — | Review |

### "everthing webinar system" (id: 0l0QRNbtjGS8ovLj) — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-002 | High | Hardcoded bearer_token detected | Update contact fields1 | Auto-fix |
| CRED-001 | Medium | Hardcoded email detected | Send a message | Review |
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook2" | Webhook2 | Auto-fix |

### "Facebook Workflow v14" (id: viHP0WVH29a2Ogjt) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |

### "Full Funnel STEP 00 Sales Page Writer Main" (id: ODWjW6NMvA8CkxpC) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "GHL Trigger2" | GHL Trigger2 | Auto-fix |
| CRED-001 | Medium | Hardcoded phone detected | ImgBB Upload1 | Review |

### "Girl, I Got You | [CLIENT]" (id: 9dmzvrHtGItUWIOo) [ACTIVE] — 13 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook2" | Webhook2 | Auto-fix |
| WEBHOOK-002 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| WEBHOOK-003 | High | Unauthenticated webhook: "Webhook3" | Webhook3 | Auto-fix |
| WEBHOOK-004 | High | Unauthenticated webhook: "Webhook4" | Webhook4 | Auto-fix |
| WEBHOOK-005 | High | Unauthenticated webhook: "Webhook5" | Webhook5 | Auto-fix |
| WEBHOOK-006 | High | Unauthenticated webhook: "Webhook6" | Webhook6 | Auto-fix |
| CRED-001 | Medium | Hardcoded email detected | Send a message | Review |
| CRED-002 | Medium | Hardcoded email detected | Send a message1 | Review |
| CRED-003 | Medium | Hardcoded email detected | Send a message2 | Review |
| CRED-004 | Medium | Hardcoded email detected | Send a message3 | Review |
| CRED-005 | Medium | Hardcoded email detected | Send a message4 | Review |
| CRED-006 | Medium | Hardcoded email detected | Send a message5 | Review |
| ERR-001 | Medium | No error handling in workflow "Girl, I Got You | [CLIENT]" | — | Review |

### "GitHub Pages - Push Quiz Landing Pages" (id: QBpbgWthVLLSjoLH) [ACTIVE] — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Form Trigger - Avatar Quiz Intake" | Form Trigger - Avatar Quiz Intake | Auto-fix |
| CRED-001 | Medium | Hardcoded email detected | Form Trigger - Avatar Quiz Intake | Review |
| ERR-001 | Medium | No error handling in workflow "GitHub Pages - Push Quiz Landing Pages" | — | Review |

### "High Ticket Manual" (id: jFJOfgZMEQJSIda5) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "On form submission" | On form submission | Auto-fix |

### "Image Branch 1B Sales Page Assets PiAPI" (id: Ua6aHyfLTJYcgJXM) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |

### "Image Branch 1C Sales Page Assets PiAPI" (id: 2ufZWUitI0DaAUdJ) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |

### "Image Branch 1D Sales Page Assets PiAPI" (id: qPQg2kngVyFc6tkl) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |

### "Image Test" (id: dmbwJVXUAE6GQJrF) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | High | Hardcoded bearer_token detected | Image Generation (OpenAI Image 1) | Auto-fix |
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook2" | Webhook2 | Auto-fix |

### "image to video with groq class" (id: QvBTvsARbchm2LAq) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "form" | form | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "image to video with groq class" | — | Review |

### "ImageMan Agent BR" (id: yMPaAd0zEA3VpYyi) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |

### "ImageMan2" (id: FuCJNphftSVsauYF) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "ImageMan2" | — | Review |

### "Midjourney Image  Creator part 1 FOR SLIDES AND AD LAST UPDATE DEC 10 2025" (id: 8yoZVqwMCuB6712s) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "On form submission" | On form submission | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Midjourney Image  Creator part 1 FOR SLIDES AND AD LAST UPDATE DEC 10 2025" | — | Review |

### "Midjourney prompt writer" (id: t3lIhaKbMMa7HPSr) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Midjourney prompt writer" | — | Review |

### "My workflow 2" (id: NBtPhHmuXTUoBmnM) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "My workflow 2" | — | Review |

### "My workflow 3" (id: nEofM8v2fgx7B7zN) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | High | Hardcoded bearer_token detected | HTTP Request | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "My workflow 3" | — | Review |

### "[CLIENT] Voice Ai part 1 Check calendar & book appointments" (id: hRJk1OvOzMObem7d) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Book appointment" | Book appointment | Auto-fix |
| WEBHOOK-002 | High | Unauthenticated webhook: "get a calendar availability" | get a calendar availability | Auto-fix |

### "[CLIENT] Voice Ai Part 2 the BCEO analysis system" (id: g41PwIB9uRJ54V7I) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "[CLIENT] Voice Ai Part 2 the BCEO analysis system" | — | Review |

### "Orientation Video Tracking - 30% & 75%" (id: JMnsK3O6wfFX7S3m) [ACTIVE] — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook 30% Watched" | Webhook 30% Watched | Auto-fix |
| WEBHOOK-002 | High | Unauthenticated webhook: "Webhook 75% Watched" | Webhook 75% Watched | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Orientation Video Tracking - 30% & 75%" | — | Review |

### "PowerPoint / slide creator part 2" (id: i4yDQzMS20dCGo3i) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "On form submission" | On form submission | Auto-fix |

### "Product bio, October 26, 2026" (id: nmzwhJfzlbpTE07X) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |

### "Rescue Rangers -- Trevor Group Inbound" (id: tIymOP0KtvfiqQgv) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Telegram Webhook Receiver" | Telegram Webhook Receiver | Auto-fix |
| CRED-001 | Medium | Hardcoded phone detected | Filter Trevor in RR Group | Review |

### "Rescue Rangers Relay" (id: GdymshUbNb9eaOAC) [ACTIVE] — 4 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook (rescue-rangers)" | Webhook (rescue-rangers) | Auto-fix |
| CRED-001 | Medium | Hardcoded phone detected | Relay Brain | Review |
| CRED-002 | Medium | Hardcoded phone detected | — | Review |
| RETENTION-001 | Low | Excessive data retention in workflow "Rescue Rangers Relay" | — | User action |

### "retell template" (id: 2opQXZAhYIfBsMk6) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |

### "[CLIENT] Voice AI Dec 1 25 UPDATE" (id: TMgfzU6PYxODp8mL) [ACTIVE] — 8 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | High | Hardcoded bearer_token detected | HTTP Request retellai | Auto-fix |
| CRED-003 | High | Hardcoded credit_card detected | get transcript | Review |
| WEBHOOK-001 | High | Unauthenticated webhook: "trigger call in retellai.com" | trigger call in retellai.com | Auto-fix |
| WEBHOOK-002 | High | Unauthenticated webhook: "Book appointment" | Book appointment | Auto-fix |
| WEBHOOK-003 | High | Unauthenticated webhook: "get a calendar availability" | get a calendar availability | Auto-fix |
| WEBHOOK-004 | High | Unauthenticated webhook: "get transcript" | get transcript | Auto-fix |
| WEBHOOK-005 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| CRED-002 | Medium | Hardcoded phone detected | get transcript | Review |

### "Single Chapter Cover Image Gen" (id: nWdDNoGTvIhIhdiw) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | High | Hardcoded bearer_token detected | Image Generation (OpenAI Image 1) | Auto-fix |

### "Single Chapter Cover Image Gen CC" (id: irZy6pWKmYaX71nI) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | High | Hardcoded bearer_token detected | Image Generation (OpenAI Image 1) | Auto-fix |

### "Single Page STEP 00 Sales Page Writer Main SD" (id: z8spdUtYz6AhFUg7) — 4 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-003 | High | Hardcoded credit_card detected | Wait | Review |
| CRED-001 | Medium | Hardcoded phone detected | ImgBB Upload1 | Review |
| CRED-002 | Medium | Hardcoded phone detected | Wait | Review |
| WEBHOOK-001 | Medium | Unauthenticated webhook: "GHL Trigger2" | GHL Trigger2 | Auto-fix |

### "Single Page STEP 00 Sales Page Writer Main SD Image" (id: fyz7xmbkDISDUXOg) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "GHL Trigger2" | GHL Trigger2 | Auto-fix |

### "sms agent" (id: pGfCMGFEJbmG41Yf) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "sms agent" | — | Review |

### "SMS Workflow" (id: Ma1DlqrrSLdyhxKs) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |

### "Snapshot Provisioner (Podcast + Anthology)" (id: ol9YLeCpvYdNsbsg) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook — Receive Provision Request" | Webhook — Receive Provision Request | Auto-fix |
| RETENTION-001 | Low | Excessive data retention in workflow "Snapshot Provisioner (Podcast + Anthology)" | — | User action |

### "Social Media Planner - Sheet Creator" (id: INyGjT8jQ6JjrZSh) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook: Create Sheet" | Webhook: Create Sheet | Auto-fix |

### "social-planner-row-append" (id: myXde6jbIIkaG5zW) [ACTIVE] — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook: Append Row" | Webhook: Append Row | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "social-planner-row-append" | — | Review |
| RETENTION-001 | Low | Excessive data retention in workflow "social-planner-row-append" | — | User action |

### "sora video creator | [CLIENT]" (id: 9g6bB2VzGIts5CmV) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "C&F Webhook for Video Submission1" | C&F Webhook for Video Submission1 | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "sora video creator | [CLIENT]" | — | Review |

### "[CLIENT] auto webinar updater" (id: Vm4Q9XRRmS0m5TTW) [ACTIVE] — 8 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | High | Hardcoded bearer_token detected | Send a message | Auto-fix |
| CRED-003 | High | Hardcoded credit_card detected | Send a message | Review |
| CRED-004 | High | Hardcoded bearer_token detected | Update contact fields1 | Auto-fix |
| CRED-006 | High | Hardcoded credit_card detected | Update contact fields1 | Review |
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook2" | Webhook2 | Auto-fix |
| CRED-002 | Medium | Hardcoded phone detected | Send a message | Review |
| CRED-005 | Medium | Hardcoded phone detected | Update contact fields1 | Review |
| ERR-001 | Medium | No error handling in workflow "[CLIENT] auto webinar updater" | — | Review |

### "[CLIENT] Speaker Clinic Date Updater" (id: Oep5MSMbdLWAGTkX) [ACTIVE] — 4 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | High | Hardcoded bearer_token detected | Update Speaker Clinic Date in GHL | Auto-fix |
| CRED-003 | High | Hardcoded credit_card detected | Update Speaker Clinic Date in GHL | Review |
| CRED-002 | Medium | Hardcoded phone detected | Update Speaker Clinic Date in GHL | Review |
| ERR-001 | Medium | No error handling in workflow "[CLIENT] Speaker Clinic Date Updater" | — | Review |

### "[CLIENT] Voiceai Pt 1" (id: YgjqTE7eipf6rIeo) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "get a calendar availability" | get a calendar availability | Auto-fix |

### "[CLIENT] Voiceai pt 2" (id: Wu6WPJd98i9ywb5k) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Book appointment" | Book appointment | Auto-fix |

### "Status Update" (id: QHNr4LTxNPAzg8lY) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |

### "STEP 01A Make Branch Low Ticket B" (id: GT6lvuK0KQMeZAN7) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "STEP 01A Make Branch Low Ticket B" | — | Review |

### "STEP 01A Make Branch Low Ticket B Single Page" (id: PmdlnjGGYjgerDLY) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "STEP 01A Make Branch Low Ticket B Single Page" | — | Review |

### "Step 01B Make Branch Upsell A" (id: ApRnOUJ1p2NHRz7Z) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Step 01B Make Branch Upsell A" | — | Review |

### "Step 01C Make Branch Upsell B" (id: 37gYsFywmPUocD8f) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Step 01C Make Branch Upsell B" | — | Review |

### "STEP 01D Make Branch Downsell A" (id: 3U8Snl7TjaE9jpSW) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "STEP 01D Make Branch Downsell A" | — | Review |

### "STEP 01E Make Branch Downsell B" (id: 1vajIXqF8IS7aW4W) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "STEP 01E Make Branch Downsell B" | — | Review |

### "Step 01F Make Branch Bumpsell" (id: tUU56wTMCREECbpC) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Step 01F Make Branch Bumpsell" | — | Review |

### "Step 03A Branch High Ticket A" (id: QsAJGcijcSE6NJ9W) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Step 03A Branch High Ticket A" | — | Review |

### "STEP 03B Branch High Ticket B" (id: gYQpVorkOKQEoRct) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "STEP 03B Branch High Ticket B" | — | Review |

### "Super Bot Remix" (id: idsIpsmdIUB9ujPk) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |

### "Template social media posting" (id: uYkpV1F6qKOY1DSL) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |

### "template upload to convert and flow ghl" (id: k7OKMMPAungp2BJP) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | High | Hardcoded bearer_token detected | Get all folder in convert and flow media storage | Auto-fix |

### "tonya wise Voice AI Dec 1 25 UPDATE copy" (id: z7cMtZStiZzLEeAv) [ACTIVE] — 4 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Book appointment" | Book appointment | Auto-fix |
| WEBHOOK-002 | High | Unauthenticated webhook: "get a calendar availability" | get a calendar availability | Auto-fix |
| WEBHOOK-003 | High | Unauthenticated webhook: "get transcript" | get transcript | Auto-fix |
| WEBHOOK-004 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |

### "Transcript (Call End)" (id: WtDN3LRerlMyD00o) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |

### "Trevor/[CLIENT] Retell Book Appointment" (id: jttrrIIZzhZIKJKG) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |

### "Trevor/[CLIENT] Retell Get Slots" (id: gOksjBrIl9yOIUkS) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Trevor/[CLIENT] Retell Get Slots" | — | Review |

### "Ultimate Prompt Creator For Slides part 1" (id: y3yZuA79ebJpLo1b) [ACTIVE] — 4 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Prompt Request Form" | Prompt Request Form | Auto-fix |
| CRED-001 | Medium | Hardcoded email detected | Prompt Request Form | Review |
| CRED-002 | Medium | Hardcoded email detected | Send Prompts Email | Review |
| ERR-001 | Medium | No error handling in workflow "Ultimate Prompt Creator For Slides part 1" | — | Review |

### "UPD Pin Webhook" (id: 3eb8Xy5Almly4ZpL) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |

### "Validate user" (id: XAbzhH1Egzjyns0g) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Validate user" | — | Review |

### "Voice ai prompt creator" (id: Ywm2tMRW7NQci6xW) [ACTIVE] — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "On form submission" | On form submission | Auto-fix |
| WEBHOOK-002 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Voice ai prompt creator" | — | Review |

### "Voice Ai TEMPLATE part 1 Check calendar & book appointments JAN 8 2026" (id: b17VVFd5e9tigXys) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Book appointment" | Book appointment | Auto-fix |
| WEBHOOK-002 | High | Unauthenticated webhook: "get a calendar availability" | get a calendar availability | Auto-fix |

### "Webhook version of ImageMan 3 nano" (id: zgwCua2E0wF5PMFO) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | High | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Webhook version of ImageMan 3 nano" | — | Review |

### "⚠️ WALLET ALERT → Telegram (Trevor)" (id: 7ErmXvNM9c88Y4ID) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "⚠️ WALLET ALERT → Telegram (Trevor)" | — | Review |

### "👤 Trevor Speaks - Private Welcome (30s delay)" (id: dh5EPzTsS4A0n6ye) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Bot Start Webhook" | Bot Start Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "👤 Trevor Speaks - Private Welcome (30s delay)" | — | Review |

### "📢 Telegram Channel Join Alert → Trevor" (id: 6lcR8zqOX1fYeGvX) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Telegram Webhook" | Telegram Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "📢 Telegram Channel Join Alert → Trevor" | — | Review |

### "🤖 Trevor Speaks - All Events (Welcome + Join Alerts)" (id: YH4nkPgwI4HgtBPP) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Telegram Webhook" | Telegram Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "🤖 Trevor Speaks - All Events (Welcome + Join Alerts)" | — | Review |

### "01-Sub-Workflow - Image Quiz Image Generator v10" (id: qmFCHWuX2cZg6QTncV1PI) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "01-Sub-Workflow - Image Quiz Image Generator v10" | — | Review |

### "02-Combined Image Creator" (id: c5K1ihIUKXF1fNZClRrCP) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "02-Combined Image Creator" | — | Review |

### "02-Social Media in a Box Content Generator" (id: T2GNL2AS3qbcms8S) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "02-Social Media in a Box Content Generator" | — | Review |

### "17 - AI LinkedIn Responder" (id: ze93axxRd6OsBnlm) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "17 - AI LinkedIn Responder" | — | Review |

### "4x3x3 Test" (id: EX9eLB6GZ95Xv65U) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |

### "advanced grok video" (id: kECUDtMMwYWGsKV5) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "On form submission" | On form submission | Auto-fix |

### "Agent [CLIENT] Test" (id: Dz86rYCQZfSxUqrM) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Agent [CLIENT] Test" | — | Review |
| RETENTION-001 | Low | Excessive data retention in workflow "Agent [CLIENT] Test" | — | User action |

### "Agent [CLIENT] Test" (id: Ef1NBhbCrL66QDGT) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Agent [CLIENT] Test" | — | Review |
| RETENTION-001 | Low | Excessive data retention in workflow "Agent [CLIENT] Test" | — | User action |

### "Airtable Test" (id: UDnxApPYfCmtWkUZ) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Airtable Test" | — | Review |

### "Anthology Drive Broker" (id: F2X3SxZVhWRDxHOV) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook anthology-drive" | Webhook anthology-drive | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Anthology Drive Broker" | — | Review |

### "anthology writer" (id: LtCloLuM1SOi4wpU) — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "GoHighLevel Webhook" | GoHighLevel Webhook | Auto-fix |
| WEBHOOK-002 | Medium | Unauthenticated webhook: "Producer Approval" | Producer Approval | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "anthology writer" | — | Review |

### "Anthology Writer - [CLIENT] CC" (id: D3I9ylvwXIWRd7NE) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Anthology Writer - [CLIENT] CC" | — | Review |

### "Avatar Alchemist Test Flow" (id: kNA5M2xorQJXoGKD) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook2" | Webhook2 | Auto-fix |

### "Avatar Quiz Engagement System - Full" (id: QFkrQzSBpPSxRzC3) — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook Trigger" | Webhook Trigger | Auto-fix |
| WEBHOOK-002 | Medium | Unauthenticated webhook: "Webhook - Selections" | Webhook - Selections | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Avatar Quiz Engagement System - Full" | — | Review |

### "Avatar Quiz Engagement System v3" (id: NEOVLiBxOlyIyHDL) — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook Trigger - Quiz Intake" | Webhook Trigger - Quiz Intake | Auto-fix |
| WEBHOOK-002 | Medium | Unauthenticated webhook: "Webhook Trigger - Receive Selections" | Webhook Trigger - Receive Selections | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Avatar Quiz Engagement System v3" | — | Review |

### "BlackCEO voice AI system" (id: RxiPAKSpwXsartAh) — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Medium | Hardcoded email detected | HTTP Request | Review |
| CRED-002 | Medium | Hardcoded phone detected | HTTP Request | Review |
| ERR-001 | Medium | No error handling in workflow "BlackCEO voice AI system" | — | Review |

### "Book Writer Fail" (id: jrHCWGIxSSIPgtv1) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Medium | Hardcoded email detected | Gmail | Review |

### "CLASS LinkedIn EMAIL scraper copy" (id: o1o835CQNRNkjpyx) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "CLASS LinkedIn EMAIL scraper copy" | — | Review |

### "Class on AI agent" (id: myvk0G4ORN0gVtdS) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Class on AI agent" | — | Review |

### "Client Data Extractor - Clients Bceo" (id: JcxdLjFa5qmgKlLe) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Client Data Extractor - Clients Bceo" | — | Review |

### "Convert Avatar document into a beautiful PDF" (id: 1NujvcZyfmHgPxga) — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Medium | Hardcoded email detected | Upload file in Google Drive | Review |
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Convert Avatar document into a beautiful PDF" | — | Review |

### "copy slide Image Creator Part 3 copy" (id: Xc7CM7UMWmqCTYMT) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "copy slide Image Creator Part 3 copy" | — | Review |

### "create podcast episode from openclaw" (id: TkL0rn2SH3q32SeB) [ACTIVE] — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Medium | Hardcoded email detected | Gmail — Entry Guard Refused Notification | Review |
| CRED-002 | Medium | Hardcoded email detected | Gmail — Standing Identity Gate Refused Notification | Review |
| CRED-003 | Medium | Hardcoded email detected | Gmail — Media Preflight Refused Notification | Review |

### "Custom Field Updater" (id: d8869A9AxcjMZpwb) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Custom Field Updater" | — | Review |

### "Document man slack" (id: R65mb0g2itI2pX4x) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Document man slack" | — | Review |

### "dummy" (id: tQhHDTCDTSqUQBlq) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "dummy" | — | Review |

### "error workflow" (id: QMNXZrNvXG0nn2U7) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Medium | Hardcoded email detected | Send a message | Review |
| CRED-002 | Medium | Hardcoded email detected | Send a message1 | Review |

### "Explore Growth - Social Media Content Generator v4 Cory and Andrea" (id: qoAuSsAfXPDxWeNJ) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Explore Growth - Social Media Content Generator v4 Cory and Andrea" | — | Review |

### "Gdrive To PineCone Template" (id: Cwb0Ax6kS5I3fgZ9) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Gdrive To PineCone Template" | — | Review |

### "Generate Video Ads with Gemini 2.5 Flash Images & FAL WAN Animation" (id: crW2sMAoZaodwHJ4) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Photo Upload Form" | Photo Upload Form | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Generate Video Ads with Gemini 2.5 Flash Images & FAL WAN Animation" | — | Review |

### "Get Appointment Slots - Black CEO (Template)" (id: khjgAqCUwyimk60Z) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |

### "GHL Agent" (id: yUT4FNIFRGN85qlY) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "GHL Agent" | — | Review |

### "GHL API Test V5" (id: mWOm62CCW0XmnOVo) [ACTIVE] — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Medium | Hardcoded email detected | 1. Validate User | Review |
| ERR-001 | Medium | No error handling in workflow "GHL API Test V5" | — | Review |

### "Google Doc HTML Render" (id: iKcW1lRxZEv2tJbc) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Google Doc HTML Render" | — | Review |

### "grok video" (id: mWUtV3kSQNms1huR) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "form" | form | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "grok video" | — | Review |

### "How to Generate UGC ads with Nano banana (The AI Edge)" (id: h5ez06NuEl70j4AM) — 4 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "T2I Trigger" | T2I Trigger | Auto-fix |
| WEBHOOK-002 | Medium | Unauthenticated webhook: "I2V Trigger" | I2V Trigger | Auto-fix |
| WEBHOOK-003 | Medium | Unauthenticated webhook: "I2I Trigger" | I2I Trigger | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "How to Generate UGC ads with Nano banana (The AI Edge)" | — | Review |

### "Ideogram Test" (id: g41PQXAZmPzwKnEq) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Medium | Hardcoded phone detected | HTTP Request7 | Review |
| ERR-001 | Medium | No error handling in workflow "Ideogram Test" | — | Review |

### "Image Man 3 Webhook version backup" (id: j71qEtQcBjj9zNdc) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Image Man 3 Webhook version backup" | — | Review |

### "Image Quiz Builder - Complete v39" (id: XdhU1YDmhKBU0ebGeYASZ) — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Medium | Hardcoded email detected | Form Trigger - Image Quiz Intake | Review |
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Form Trigger - Image Quiz Intake" | Form Trigger - Image Quiz Intake | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Image Quiz Builder - Complete v39" | — | Review |

### "Imageman 3 slack verion" (id: 2qx8eMXeb2gvgsv1) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Imageman 3 slack verion" | — | Review |

### "ImageMan Agent BR copy (attempt 2 fix errors) by trevor" (id: Nmzrz6gpPpT7XyPi) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |

### "Joke bot. Joke agent" (id: qQfkNGweT5dSNbBz) — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Medium | Hardcoded email detected | AI Agent1 | Review |
| ERR-001 | Medium | No error handling in workflow "Joke bot. Joke agent" | — | Review |
| RETENTION-001 | Low | Excessive data retention in workflow "Joke bot. Joke agent" | — | User action |

### "lead magnet generator" (id: BPLmsKak4tzssX7Y) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "lead magnet generator" | — | Review |

### "leanne pine cone" (id: Ly9324XxbrkTwQ5D) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "leanne pine cone" | — | Review |

### "main image workflow" (id: hMOLVmSnCperst59) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Get Request" | Get Request | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "main image workflow" | — | Review |

### "mark1" (id: 72X9nBwGkPO8TDdM) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "mark1" | — | Review |

### "MCP Test" (id: pe33WIv59XZoSmhM) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "MCP Test" | — | Review |

### "merge small video clips into one longer video (FFMPEG)" (id: rlpeWhj7KQTI7h08) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "On form submission" | On form submission | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "merge small video clips into one longer video (FFMPEG)" | — | Review |

### "Midjourney Image Creator" (id: O6MvuR8K5PuTlvjS) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "On form submission" | On form submission | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Midjourney Image Creator" | — | Review |

### "Midjourney Image Creator copy" (id: XyszlONKNKiVlmk1) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "On form submission" | On form submission | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Midjourney Image Creator copy" | — | Review |

### "midjourney Part 2 subworkflow image creator" (id: 0qtaTpe86MtOeThT) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "midjourney Part 2 subworkflow image creator" | — | Review |

### "Movie creator  New" (id: G7nekONkjmTReVJn) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Movie creator  New" | — | Review |

### "Movie creator  ver 2" (id: gHSxfCB2lT2fjL7D) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Movie creator  ver 2" | — | Review |

### "Movie creator  ver 3 copy" (id: 7hw3ZQv2CQVGPYPA) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Movie creator  ver 3 copy" | — | Review |

### "My workflow 11" (id: cuFd6pGDG2ydhuxe) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "My workflow 11" | — | Review |

### "My workflow 12" (id: CWtTZWWO35CD1QTZ) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "My workflow 12" | — | Review |

### "My workflow 15" (id: uIG6mJGw02XNEvNE) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "My workflow 15" | — | Review |

### "My workflow 17" (id: ou0646kpFxFteUdc) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Medium | Hardcoded phone detected | Analyze image | Review |

### "My workflow 18" (id: Xcfk6LqgkL2tOqOH) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "My workflow 18" | — | Review |

### "My workflow 20" (id: sIn72YZECmtRz1Zz) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "My workflow 20" | — | Review |

### "My workflow 21" (id: rdE69uffMSO5ggXF) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "My workflow 21" | — | Review |

### "My workflow 22" (id: Del5d7Rm8jWAhJsR) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Medium | Hardcoded email detected | Send a message | Review |
| ERR-001 | Medium | No error handling in workflow "My workflow 22" | — | Review |

### "My workflow 24" (id: cWBRtKI4WxQ5DlxI) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "My workflow 24" | — | Review |

### "My workflow 25" (id: codHgrgzi51SyXH4) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "On form submission" | On form submission | Auto-fix |

### "My workflow 26" (id: PEpwKjH7dpe47vI2) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "My workflow 26" | — | Review |

### "My workflow 27" (id: 1566VP5HDszafvn-HTZS8) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "My workflow 27" | — | Review |

### "My workflow 5" (id: bZczGYdcfdk6qctZ) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "My workflow 5" | — | Review |

### "My workflow 8" (id: Xiju5WvZslJjzkr3) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "My workflow 8" | — | Review |

### "My workflow 9" (id: ofyqM1AEJGG9b9vl) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "My workflow 9" | — | Review |

### "N8n Backup Program" (id: 3pavvSks7wjdNEER) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "N8n Backup Program" | — | Review |

### "n8n library updater V14 - Custom Chunk Iterator" (id: TGfLV5CUluvPzV45) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "n8n library updater V14 - Custom Chunk Iterator" | — | Review |

### "old version prompt creator  dec14   2025" (id: 1fiJ4yGTsLdxn16f) — 4 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Medium | Hardcoded email detected | Prompt Request Form | Review |
| CRED-002 | Medium | Hardcoded email detected | Send Prompts Email | Review |
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Prompt Request Form" | Prompt Request Form | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "old version prompt creator  dec14   2025" | — | Review |

### "OpenRouter HTTP template" (id: v8LT0AHDTn0xCJFX) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "OpenRouter HTTP template" | — | Review |

### "OUTDATED midjourney Part 2 subworkflow image creator" (id: Ev44c9vyiFSyW8eX) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "OUTDATED midjourney Part 2 subworkflow image creator" | — | Review |

### "Page Mockup Generator v1" (id: RTnr2qvnIeiQIybv) — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Medium | Hardcoded email detected | Form Trigger | Review |
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Form Trigger" | Form Trigger | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Page Mockup Generator v1" | — | Review |

### "Part 2 Kie.ai VEO3 fast image to video subworkflow" (id: Ucj8YNTBPbE9iJTH) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Part 2 Kie.ai VEO3 fast image to video subworkflow" | — | Review |

### "Part 3 Fal.ai ffmpeg merge videos" (id: Ii2R8R06ZHxg2JaZ) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Part 3 Fal.ai ffmpeg merge videos" | — | Review |

### "Part 4 - Google Slides Creator" (id: 8I3G8pU9oz62KYME) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Part 4 - Google Slides Creator" | — | Review |

### "Part 5 - Timeout Watcher" (id: tLGKFFIu2liA65Fu) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Part 5 - Timeout Watcher" | — | Review |

### "Part 6 - Weekly Cleanup" (id: 5yGydhzBsupnTJcn) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Part 6 - Weekly Cleanup" | — | Review |

### "Path B - Safe Bulk SMS via GHL (TEMPLATE)" (id: 7A1k5hCA3MmKnwm8) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook - Campaign Request" | Webhook - Campaign Request | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Path B - Safe Bulk SMS via GHL (TEMPLATE)" | — | Review |

### "PiAPI Image Gen." (id: QOxUM4qs8SXPe0bP) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "PiAPI Image Gen." | — | Review |

### "Pinecone Part 1 New Files Processor" (id: fs4mQTkcNA5yxY7u) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Pinecone Part 1 New Files Processor" | — | Review |

### "Pinned Webhook Sales Page Creator" (id: L72LuKYAqsHD7qSR) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "GHL Trigger" | GHL Trigger | Auto-fix |

### "Podbean - GET CLIENT CHANNEL ID" (id: BqRLOn8TP1wPaAzn) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Podbean - GET CLIENT CHANNEL ID" | — | Review |

### "Presentation and ad man" (id: KNl4C9NEy6PYoBuB) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Presentation and ad man" | — | Review |

### "Retell AI" (id: 3o7pvNypvlEFFEaG) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Medium | Hardcoded email detected | HTTP Request | Review |
| CRED-002 | Medium | Hardcoded phone detected | HTTP Request | Review |

### "[CLIENT] Social Media in a Box" (id: RYBmX3frEBRDHdy5) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "[CLIENT] Social Media in a Box" | — | Review |

### "Send Remaining Christmas Emails" (id: 7xbitHJ8STaTTdVq) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Send Remaining Christmas Emails" | — | Review |

### "[CLIENT] Social Media in a Box [CLIENT]" (id: SEX9M1dL1D9eZYo4) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "[CLIENT] Social Media in a Box [CLIENT]" | — | Review |

### "Single Page STEP 00 Sales Page Writer Main" (id: wmb53gbRt7bAb93Y) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Medium | Hardcoded phone detected | ImgBB Upload1 | Review |
| WEBHOOK-001 | Medium | Unauthenticated webhook: "GHL Trigger2" | GHL Trigger2 | Auto-fix |

### "Slack ID Sync Updater" (id: UXtDy9hpsHLfb6xq) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Slack ID Sync Updater" | — | Review |

### "slackbot byclaude code doc updater" (id: NkDmD8oE3xCL6MUv) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "slackbot byclaude code doc updater" | — | Review |

### "slide Image Creator Part 3" (id: wb2OhPgDdvFe8BV2) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "slide Image Creator Part 3" | — | Review |

### "Social media in a box part 3 Content Writer" (id: w6w48NI48EkcdPg2) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Social media in a box part 3 Content Writer" | — | Review |

### "Social media in a box part 5 fb/ig carousel creator" (id: PnCHOzl1eQdReMIe) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Social media in a box part 5 fb/ig carousel creator" | — | Review |

### "Social media in a box part 6: Carousel Image Creator" (id: JKK3wVqurjlBK0tt) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Social media in a box part 6: Carousel Image Creator" | — | Review |

### "Social media in a box part 7: LinkedIn Carousel" (id: beu3SatkuetT1di2) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Social media in a box part 7: LinkedIn Carousel" | — | Review |

### "Social Media In A Box Part 9: podcast Image Creator" (id: UJkGg13KsY4ZwLfh) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Social Media In A Box Part 9: podcast Image Creator" | — | Review |

### "Social media in a box. Agency version. Template - FIXED v3" (id: 1w3pPmH3QzVQ0rfa) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Social media in a box. Agency version. Template - FIXED v3" | — | Review |

### "sora 15 sec version and 25 sec video chainer" (id: TZvWkuxt2Bn8C3mL) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "sora 15 sec version and 25 sec video chainer" | — | Review |

### "sora video creator" (id: csq7nQq0qZGdT1mb) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "sora video creator" | — | Review |

### "sora video creator class version" (id: jHMYxzzoW5sMrx8C) — 4 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| WEBHOOK-002 | Medium | Unauthenticated webhook: "C&F Webhook for Video Submission1" | C&F Webhook for Video Submission1 | Auto-fix |
| WEBHOOK-003 | Medium | Unauthenticated webhook: "Webhook1" | Webhook1 | Auto-fix |
| WEBHOOK-004 | Medium | Unauthenticated webhook: "On form submission" | On form submission | Auto-fix |

### "[CLIENT] VoiceAi Pt 3" (id: KT0LNuY2lC6dwqmy) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "[CLIENT] VoiceAi Pt 3" | — | Review |

### "STEP 02 High Ticket Images APIFRAME" (id: qXtT00ktXlfrvtrs) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook1" | Webhook1 | Auto-fix |

### "STEP 02 High Ticket Images PiAPI" (id: baWn3i6GVfNAycUz) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook1" | Webhook1 | Auto-fix |

### "STEP 03C Branch High Ticket C" (id: rJHCYKbHizJUQ8Jg) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "STEP 03C Branch High Ticket C" | — | Review |

### "[CLIENT] Book Rewriter" (id: XbqMuPB6g547Uwmj) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "[CLIENT] Book Rewriter" | — | Review |

### "STUFF IM TESTING" (id: IMuMSGWhtdPU1I7J) — 6 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Medium | Hardcoded email detected | Set Email | Review |
| CRED-002 | Medium | Hardcoded email detected | Google Workspace Agent | Review |
| CRED-003 | Medium | Hardcoded email detected | Create an event in Google Calendar | Review |
| CRED-004 | Medium | Hardcoded email detected | Get many events in Google Calendar | Review |
| CRED-005 | Medium | Hardcoded email detected | Get availability in a calendar in Google Calendar | Review |
| ERR-001 | Medium | No error handling in workflow "STUFF IM TESTING" | — | Review |

### "Sub workflow to create videos using veo" (id: tDD6PDVRXEkTnzGu) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Sub workflow to create videos using veo" | — | Review |

### "Subworkflow: Edit Image using Seed Dream or Nano Banana" (id: 4u2cdQduqGfZViP6) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Subworkflow: Edit Image using Seed Dream or Nano Banana" | — | Review |

### "SUPERBOT FOR CLASS" (id: x91WGueVZ54bIua8) [ACTIVE] — 5 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Medium | Hardcoded email detected | Create an event in Google Calendar | Review |
| CRED-002 | Medium | Hardcoded email detected | Get availability in a calendar in Google Calendar | Review |
| CRED-003 | Medium | Hardcoded email detected | Get many events in Google Calendar | Review |
| CRED-004 | Medium | Hardcoded email detected | bceo system email address | Review |
| ERR-001 | Medium | No error handling in workflow "SUPERBOT FOR CLASS" | — | Review |

### "Superbot Multi-Agent v3.0" (id: ou8jGf0iltfy6Nau) — 6 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Medium | Hardcoded email detected | Set Email | Review |
| CRED-002 | Medium | Hardcoded email detected | Google Workspace Agent | Review |
| CRED-003 | Medium | Hardcoded email detected | Create an event in Google Calendar | Review |
| CRED-004 | Medium | Hardcoded email detected | Get many events in Google Calendar | Review |
| CRED-005 | Medium | Hardcoded email detected | Get availability in a calendar in Google Calendar | Review |
| ERR-001 | Medium | No error handling in workflow "Superbot Multi-Agent v3.0" | — | Review |

### "Template - Google sheet updates" (id: GOjDtPwm1SZQ027Z) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Template - Google sheet updates" | — | Review |

### "Template - Gotenberg pdf creator" (id: z1c2SdLnkclDFTax) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook Trigger" | Webhook Trigger | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Template - Gotenberg pdf creator" | — | Review |

### "Template - NCA Toolkit" (id: R5rT2TH7Na3isFHi) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Template - NCA Toolkit" | — | Review |

### "Template - NCA Toolkit with ffmpeg video and audio template" (id: OnIlGaZeOmPaayIW) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Template - NCA Toolkit with ffmpeg video and audio template" | — | Review |

### "template Easiest way to generate images with nano banana pro" (id: u9KmifQJ1Ybg9ONc) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "On form submission" | On form submission | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "template Easiest way to generate images with nano banana pro" | — | Review |

### "Template Voiceai Pt 1" (id: iy888GgBYmze0nYg) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "get a calendar availability" | get a calendar availability | Auto-fix |

### "Template Voiceai pt 2" (id: 2gd2aao8nFma9JaV) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Book appointment" | Book appointment | Auto-fix |

### "Template VoiceAi Pt 3" (id: J20x65Ta4WzdFVmY) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Template VoiceAi Pt 3" | — | Review |

### "template-ffmpeg test" (id: 6FIxaCq5sBhRKizl) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "template-ffmpeg test" | — | Review |

### "test 2" (id: w5rwXMA303LdrQRp) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "test 2" | — | Review |

### "TEST Make Test" (id: vuzXoYtMLn8a8fVn) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "GHL Trigger" | GHL Trigger | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "TEST Make Test" | — | Review |

### "TREVORS PINECONE CREATOR AND DATABASE / INDEX UPDATER" (id: 4J3SnDf76y3PaqJd) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "TREVORS PINECONE CREATOR AND DATABASE / INDEX UPDATER" | — | Review |

### "Trevors Pinecone creator and updater" (id: I9bZu4o2QaXu9JoK) [ACTIVE] — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Trevors Pinecone creator and updater" | — | Review |

### "Trevors SUPERBOT Part 1  not ready no telegram" (id: ggqcH0xP8LhZC3nY) — 5 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Medium | Hardcoded email detected | Append row in sheet in Google Sheets | Review |
| CRED-002 | Medium | Hardcoded email detected | Create an event in Google Calendar | Review |
| CRED-003 | Medium | Hardcoded email detected | Get availability in a calendar in Google Calendar | Review |
| CRED-004 | Medium | Hardcoded email detected | Get many events in Google Calendar | Review |
| ERR-001 | Medium | No error handling in workflow "Trevors SUPERBOT Part 1  not ready no telegram" | — | Review |

### "Trevors Superbot Part 2 THE TOOL BOX" (id: aRQRSKgSYQz1r50t) — 5 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Medium | Hardcoded email detected | Append row in sheet in Google Sheets | Review |
| CRED-002 | Medium | Hardcoded email detected | Create an event in Google Calendar | Review |
| CRED-003 | Medium | Hardcoded email detected | Get availability in a calendar in Google Calendar | Review |
| CRED-004 | Medium | Hardcoded email detected | Get many events in Google Calendar | Review |
| ERR-001 | Medium | No error handling in workflow "Trevors Superbot Part 2 THE TOOL BOX" | — | Review |

### "ultimate gmail agent outdated" (id: 9Um9vvMNX4e9dbv2) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "ultimate gmail agent outdated" | — | Review |

### "Ultimate Sales Ai" (id: J9jrE2ZjigZ2BOQP) — 2 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Ultimate Sales Ai" | — | Review |

### "Update Your RAG Database" (id: UnSUty49tLGjMgBP) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| ERR-001 | Medium | No error handling in workflow "Update Your RAG Database" | — | Review |

### "video and audio merger FFMPEG" (id: jGyACQePgUA5Crjc) — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Merge Video" | Merge Video | Auto-fix |
| WEBHOOK-002 | Medium | Unauthenticated webhook: "Merge Audio" | Merge Audio | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "video and audio merger FFMPEG" | — | Review |

### "Video Merge - Native Nodes Only" (id: KdSUx4GX9l2CtZSm) — 3 findings

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| CRED-001 | Medium | Hardcoded email detected | Sticky Note | Review |
| WEBHOOK-001 | Medium | Unauthenticated webhook: "Webhook" | Webhook | Auto-fix |
| ERR-001 | Medium | No error handling in workflow "Video Merge - Native Nodes Only" | — | Review |

### "n8n-mcp Test Workflow" (id: QaWYmA1OSxZGkaAN) — 1 finding

| ID | Severity | Finding | Node | Fix |
|----|----------|---------|------|-----|
| RETENTION-001 | Low | Excessive data retention in workflow "n8n-mcp Test Workflow" | — | User action |

---

## n8n Built-in Audit Results

No issues found by n8n built-in audit.

---

## Remediation Playbook

### Auto-fixable by agent

**Hardcoded secrets** (59 across 32 workflows):
Steps: `n8n_get_workflow` -> extract value -> `n8n_manage_credentials({action: "create"})` -> `n8n_update_partial_workflow({operations: [{type: "updateNode"}]})` to reference credential.

**Unauthenticated webhooks** (172 across 145 workflows):
Steps: `n8n_manage_credentials({action: "create", type: "httpHeaderAuth"})` with random secret -> `n8n_update_partial_workflow` to set `authentication: "headerAuth"` and assign credential.

### Requires review
**Error handling gaps** (179 workflows): Add Error Trigger nodes or set continueOnFail on critical nodes.
**PII in parameters** (80 findings): Review whether hardcoded PII (emails, phones) is necessary or should use expressions.

### Requires your action
**Data retention** (8 workflows): Configure execution data pruning in n8n Settings -> Executions.

---

Scan performance: built-in 30005ms | fetch 11102ms | custom 238ms