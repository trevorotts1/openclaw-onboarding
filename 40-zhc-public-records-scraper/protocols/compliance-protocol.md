# Compliance Protocol (enforced, not advisory)

Runs BEFORE any live fetch. Enforced by `scripts/lib-records.sh` and machine-
checked by `scripts/qc-compliance.sh`.

## 1. robots.txt is binding

Before fetching any target path, fetch + parse the target's `robots.txt`. If the
path is disallowed for our user-agent (a global `User-agent: *` Disallow that
prefixes our path), the target is a **Tier-4 honest gap** (`compliance_block`,
reason `robots_disallow`). Never override robots.txt, never spoof a user-agent
to evade it. No robots.txt present → allowed by convention.

## 2. ToS reference per target

Every Tier-1 config and every operator Tier-3 config carries a `tos_url`. The
operator must acknowledge the target's Terms of Service before live use. An
unacknowledged target → `compliance_block`, reason `tos_unacknowledged`. Skill 40
does not interpret the ToS; it references it and requires acknowledgement.

## 3. Attribution — source + timestamp on every record

Every retrieved record is stamped `source` (the target slug/portal) and
`retrieved_at` (UTC timestamp). The router refuses to return an unattributed
record. A record without provenance is not a record.

## 4. Permissible-purpose use (operator's responsibility)

Public-records use can be restricted by law (e.g. FCRA for consumer-report use,
DPPA for DMV data, and various state-level limits on bulk public-records use).
Skill 40 SURFACES this reminder; it does not give legal advice and does not
police the operator's use. The operator is responsible for lawful, permissible-
purpose use of any retrieved record.

## 5. Rate + cost respect (see cost-cap-protocol.md)

Compliance includes being a good citizen of the target: per-target rate limits
and a global daily cap are enforced so the skill never hammers a public portal.
