# api-generations.md — versions, generations and staging

> Evidence state: the five-version facts and the paths below are inherited from the contract freeze and the 2026-08-03 read-only probes, labelled historical. No page was refetched in this lane. Always take the literal from the registry row.

## Five supported versions

| Version | Released | Supported until |
|---|---|---|
| `v3` | June 11, 2026 | TBD |
| `2023-02-21` | February 21, 2023 | TBD |
| `2021-07-28` | July 28, 2021 | TBD |
| `2021-04-15` | April 15, 2021 | TBD |
| `legacy` | January 1, 2021 | TBD |

No version has a published retirement date. An older supported version is not a defect. Only a blanket "one value for everything" rule is wrong.

## `v4` is staging, not a sixth production version

Workflow definition rows carry `version: v4` and `blocker: B-V4-S`, classified **beta-gated**. Never add `v4` to `SUPPORTED_VERSIONS`, never send it as a generic upgrade, and never describe a v4 definition operation as production-available. Validation is non-persisting but consumes write quota.

## The value is per operation

The registry row is the authority. Examples of the reasons this matters (all inherited evidence):

- A v3 app spec can still declare `2021-07-28` for most of its operations.
- `phone-system-v3` names the parameter lowercase `version`; headers are case-insensitive.
- `store` declares no `Version` parameter.
- Some operations (OAuth token, marketplace billing, several funnel reads) declare none.
- Renamed/generation-gated paths hard-404 under the wrong literal: e.g. `/oauth/installed-locations` and `/brand-boards/.../brand-voices` require `v3`; the camelCase forms work more broadly.

Do not prepend `/v3` to every URL. Do not sweep a version string across a family.

## Historical live-probe evidence (do not over-read)

On 2026-08-03, read-only GETs against an operator-owned account showed:

- omitted header → 401 `version header was not found.`
- unpublished value → 401 `version header is invalid`
- `2021-07-28`, `2021-04-15`, `2023-02-21`, `v3` all returned 200 on `/contacts/`, `/users/`, `/calendars/`

That proves the header is mandatory and that established paths are lenient. It does **not** prove newer paths are lenient, and it is historical evidence, not a current guarantee.

## Spec repo lag (standing warning)

The public spec dump lags the live docs. A page-fetch failure or a spec absence is not proof an endpoint does not exist. Check the official docs and the registry row; keep a field `UNKNOWN` until evidence settles it.

## Decision rule

```text
1. Read the registry row: method, path, version, alternates, blocker.
2. Beta-gated (v4/staging or vendor beta) -> record beta_not_enabled + approved fallback.
3. Documented-unimplemented -> stop; use the labelled gap.
4. Implemented -> send exactly the row's version.
5. Never omit the header; never invent a value; never pair a v3 path form with an older literal.
```
