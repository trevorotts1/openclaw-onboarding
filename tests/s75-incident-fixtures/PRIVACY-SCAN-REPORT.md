# Privacy scan report — unit S75-W01-U2

Date: 2026-10-22. Scanner: `privacy/scan.py` (this repository).
Spec basis: Skill_75_Universal_Repair_Spec_v1.1 sections 2.1, 4.3, 17.8, 17.10.

## Method

Classes scanned: person and run identities (runtime name denylist), home
directories, SSH aliases, chat IDs, access-bearing URLs, run/host identity
shapes, one-off overrides. Technical failure descriptions pass untouched: the
scanner reports CLASSES AND LOCATIONS ONLY, never matched values — echoing a
private value into a report would leak the very thing being scanned for.
Name matching is case-sensitive against a 37-term denylist supplied at scan
time from private scratch; the denylist is not part of any shared artifact.
Known limitation: a case-insensitive sweep would false-positive on ordinary
technical vocabulary that is also a person name, so names are matched with
their capitalization; a lowercase spelling inside prose would not be caught
by the name class alone.

## Scope A — shared artifacts touched by this unit: PASS

23 text artifacts under the unit work directory (fixtures, harness, tests,
documentation, this report, run logs, receipt). Findings: none — 0 in every
class (final pre- and post-receipt scans identical).
The fixture suite depends on no real client, run, host or chat identity: all
identity fields use the `*-synth-*` namespace and all runtime paths are
injected placeholders (asserted by `tests/test_fixture_suite.py`).

## Scope B — pending PR titles and bodies: PASS

Scanned the live titles and bodies of the two open recovery pull requests
(the onboarding continuity/recovery PR and the 999 parity PR) via their
published metadata. Findings: none — 0 in every class, including the name
denylist. No PR metadata edit was made or needed.

## Scope C — release notes: findings recorded as advisories

Scanned the two distribution CHANGELOGs read-only. They were NOT touched by
this unit. Findings (values withheld):

| Class | Hits | Location |
| --- | --- | --- |
| person_or_run_name | 54 | both CHANGELOGs, scattered lines (e.g. first lines at 73, 75, 190) |
| chat_id | 4 | both CHANGELOGs (numeric identity shapes) |
| home_directory | 2 | both CHANGELOGs |

These are exactly the "incident-person references" section 2.1 requires the
shared-artifact cleanup to remove while keeping the technical failure
descriptions. Ownership: the units that edit release notes / shared
documentation; this report is the recorded scan they can re-run.

## Additional advisory observations (outside this unit's touch scope)

The skill's own source and profile data in both distributions carry a personal
first name inside a comment/data note and a real campaign name inside a
reliability comment. Values withheld; file locations handed to the S75-W01
finding map. This unit touched no product source (verified: the 999 tree
status is byte-identical before and after the run, and the pending-head
worktree is clean), so per the scan scope they are advisories, not findings
against touched artifacts.

## Transcript handling

The supplied incident transcript was kept as private diagnostic evidence
only. No transcript content was copied into any artifact of this unit; the
fixtures reproduce the recorded failure patterns from their documented
specification rows (17.4, 17.8, 17.10) with synthetic identities.

## Re-run

```
python3 privacy/scan.py --scope shared-artifacts --denylist <private-file> .
```

exit 0 and zero findings is the pass condition for every touched shared
artifact.
