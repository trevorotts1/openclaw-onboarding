# SOP-FBAD-01: TAKE IN THE JOB AND START THE CAMPAIGN

**Cluster:** FB/IG Ad-Craft Rules (`universal-sops/fb-ad-craft/`)
**Master authority:** `AD-PIPELINE-MANIFEST.json` (the pipeline + dependency map) + `MASTER-AD-QC-AUTOFAIL-RULESET.md` (Section 6 auto-fail table)
**Owning role:** Facebook & Instagram Ad-Run Producer (the conductor)
**Stage:** S0-INTAKE — `depends_on: []`
**Produces:** `working/job-manifest.json` + `working/checkpoints/ad_run_ledger.json`
**Gates this stage satisfies:** AF-FBAD-BRIEF-INCOMPLETE, AF-FBAD-COST-CEILING, AF-FBAD-RECEIPT-NAMESPACE (+ Phase-0 AF-FBAD-KIE-BALANCE)

---

## 0. WHY THIS SOP EXISTS

A batch started on a thin brief, an un-priced run, or a run with no receipt-number is
the batch that re-charges the client, double-uploads, or dies mid-run. Intake is the
precondition for everything: the two inputs, the money ceiling, and the unique run-id
are locked here before a single overlay is written.

---

## 1. THE TWO INPUTS (read by file reference)

| Input | Required | What it is |
|---|---|---|
| Show / product bio | Yes | Name + tagline, ~10 hook angles, ~17 power adjectives, "who it's best for." Feeds copy. |
| Audience profile | Yes | The ~22-question profile (demographics, income, needs, goals, objections). Feeds copy AND targeting. |
| Targeting doc | Optional | Named groups with three layers of real Meta interests. If absent, S6 derives targeting from the audience profile. |

The client drops these into the Telegram chat with their CEO agent, or into the
agent's intake folder. Sanity-check them: if a required input is missing or thin,
return the **gap list** to the owner and STOP — never guess at a missing input.

## 2. THE FAST DOC (a 4-line interview when an input is thin)

If the bio or audience profile is incomplete, ask the owner only the missing pieces,
in one message: (1) the one-line mission ("recruit guests for the show", not "sell"),
(2) the single audience sentence in the client's own words, (3) the destination URL,
(4) the money ceiling. Carry the client's audience sentence **verbatim** into the
brief — S1 will preserve it word-for-word (AF-FBAD-AUDIENCE-WORDING).

## 3. THE RECEIPT-NUMBER + MONEY CEILING

1. Mint a unique **run-id** (the receipt-number). It becomes the `job_id`, the ledger
   `run_id`, and the board `campaign_id` — one run-id = one campaign = one ledger,
   forever.
2. **Estimate cost up front:** `10 images x per-image price x a small re-do allowance`.
   Announce it to the owner ("10 images ≈ $X — approve") and set
   `cost_estimate_approved: true` only after the owner approves.
3. Set the **per-job ceiling** (`money_ceiling_usd`). The estimate must be ≤ the
   ceiling BEFORE any spend (AF-FBAD-COST-CEILING).

## 4. OPEN THE CAMPAIGN ON THE BOARD

`POST /api/ad-campaigns` with the run-id (idempotent — a second call returns the
existing campaign and creates zero cards). It inserts one parent (epic) card + seven
stage cards, all sharing the `campaign_id`. If the box's Command Center predates this
endpoint, degrade gracefully: file ungrouped cards on the marketing board and note it.

---

## 5. ATTESTATION APPEND (replaces any prose "do not skip")

This stage is not done because you say so — it is done when it writes the two receipts
the foreman reads. **Write, do not describe.**

`working/job-manifest.json`:
```json
{
  "brief_complete": true,
  "job_id": "<run-id>",
  "show_name": "<show/product name>",
  "audience_profile_ref": "working/inputs/audience.md",
  "money_ceiling_usd": 5.0,
  "estimated_cost_usd": 0.65,
  "cost_estimate_approved": true,
  "owner": "<owner name>"
}
```

`working/checkpoints/ad_run_ledger.json`:
```json
{ "run_id": "<run-id>", "spent_usd": 0.0, "events": [] }
```

The foreman validates these with `_chk_brief_complete`, `_chk_cost_ceiling`, and
`_chk_run_ledger`; a missing field, an over-ceiling estimate, or a run_id that does not
equal the job_id HARD-FAILS the stage. The Phase-0 `kie_balance_preflight` runs once
here for a paid job (AF-FBAD-KIE-BALANCE).
