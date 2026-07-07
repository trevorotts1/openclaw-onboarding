# Webhook intake fixtures (SPEC 13.2, T1-T9)

Synthetic Convert and Flow form-submission payloads that exercise the intake
verification battery. All data is fabricated: no client PII, no secret values,
no Anthropic identifiers, no credential-shaped payload keys (the legacy `api_key`
body field is abolished, SPEC Appendix B). The route secret always rides the
`Authorization` header at the transport, never the body.

`expected.json` is the source of truth that binds each fixture to its T-id, auth
posture, HTTP ack contract, and ledger-side outcome. Both
`scripts/verify-webhook-t1-t9.sh` and `tests/test_webhook.py` read it.

| Fixture | Test | What it proves |
|---|---|---|
| (none) | T1 | route registered on the gateway (mapping `anthology-intake` present) |
| `t4-valid-intake.json` (no auth) | T2 | request without the route secret is refused (401) |
| `t3-malformed-empty.json`, `t3-malformed-notjson.txt`, `t3b-missing-ids.json` | T3 | malformed / unroutable payload lands in Exceptions (`unroutable_missing_ids`), never a crash |
| `t4-valid-intake.json` | T4 | valid submission acks in under 2s and creates the participant |
| `t5-duplicate-intake.json` | T5 | byte-identical duplicate is a no-op acknowledge (same fingerprint as T4) |
| `t6-wrong-tenant.json` | T6 | `location` != registry binding lands in Exceptions (`tenant_mismatch`) |
| `t7-stage-mismatch.json` | T7 | stage form vs ledger cursor disagree lands in Exceptions (`stage_mismatch`) |
| `t4-valid-intake.json` (public URL) | T8 | real public URL via the named Cloudflare Tunnel accepts end to end (canary, W5.3) |
| (none) | T9 | gateway restart preserves the route and pending state (canary, W5.3) |

Tenant fixtures share `anthology_id` `ANTHsynthetic0001`. The registry is bound to
`registry_bound_location` = `LOCsyntheticAnthologyAAA` (expected.json), so
`t4`/`t5`/`t7` match the tenant and `t6` (`LOCwrongTenantZZZ`) does not.

T1-T9 are EXECUTED AND OBSERVED on the operator canary at W5.3 after
provisioning. Pre-provisioning, the verifier self-validates structure and reports
the live battery as not-yet-executable.
