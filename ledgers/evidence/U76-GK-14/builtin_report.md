# n8n Security Audit Report — Built-in categories (isolated re-run)
Generated: 2026-07-16T16:14:16.386Z | Instance: https://main.blackceoautomations.com

## Summary
| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 1606 |
| **Total** | **1606** |

Workflows scanned: 0 | Scan duration: 4.7s

---

## n8n Built-in Audit Results

### Credentials Risk Report
- **Credentials not used in any workflow:** Affected: 22 items
- **Credentials not used in any active workflow:** Affected: 33 items
- **Credentials not used in recently executed workflows (90d):** Affected: 67 items

### Nodes Risk Report
- **Official risky nodes** (may run arbitrary code, e.g. Code/HTTP Request node TYPE, not a specific exploited instance): Affected: 1386 items
- **Community nodes** (unvetted, full host access): Affected: 8 items

### Instance Risk Report
- **Unprotected webhooks in instance** (Authentication=None, no inline validation node): Affected: 78 items
- **Outdated instance:** n8n server version 2.29.10, missing 2 updates (2.30.6, 2.29.11 available)
- **Security settings:** communityPackagesEnabled=true, versionNotificationsEnabled=true, templatesEnabled=true, publicApiEnabled=true; nodesExclude=executeCommand,localFileTrigger,e2eTest,dynamicCredentialCheck; telemetry=true

### Filesystem Risk Report
- **Nodes that interact with the filesystem:** Affected: 12 items

---

## Remediation Playbook
### Requires your action
**Outdated instance**: Update n8n to latest version.
**Community nodes** (8): Review installed community packages.

Scan performance: built-in 4678ms | fetch 0ms | custom 0ms
