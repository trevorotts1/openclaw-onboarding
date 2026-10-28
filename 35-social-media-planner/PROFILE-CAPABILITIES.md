# T-22 — Personal-Profile Capability and Assisted Contract

**Machine-readable single source:** `config/profile-capabilities.json`
**Consumer:** `shared-utils/personal_profile_capability.py`
**Operator CLI:** `scripts/profile_capability.py`

Ordinary personal profiles have no supported public posting or comment API. Pretending
they do is the failure this contract exists to prevent. Every channel and account type
is declared in exactly one of three honest modes:

| Mode | Meaning |
|---|---|
| `unattended` | The system performs the action without a human step, through the named path. |
| `assisted` | The system prepares the exact placement and hands it to the operator for one manual step. The operator's confirmation is the receipt. |
| `unavailable` | The system cannot do it and offers no assisted route. |

A personal profile is **always** `assisted` or `unavailable`, never `unattended`.
That is enforced mechanically when the declaration loads; a personal profile that
lists any unattended action fails validation.

---

## Declaration at a glance

| Channel | Account type | Mode | Path |
|---|---|---|---|
| Facebook | Page (business) | unattended | GHL social planner |
| Facebook | Personal profile | **assisted** | operator manual |
| Instagram | Business | unattended | GHL social planner |
| Instagram | Creator | unattended | GHL social planner |
| Instagram | Personal profile | **assisted** | operator manual |
| LinkedIn | Company page | unattended | GHL social planner |
| LinkedIn | Personal profile | **assisted** | operator manual |
| X | Brand/business account | unattended | GHL social planner |
| X | Personal account | **assisted** | operator manual |
| TikTok | Business | unattended (video only) | GHL social planner |
| TikTok | Personal | **assisted** | operator manual |
| Pinterest | Business | unattended (pins only) | GHL social planner |
| Pinterest | Personal | **assisted** | operator manual |
| YouTube | Channel (brand/creator) | unattended (video only) | YouTube Data API |
| YouTube | Personal channel | **assisted** | operator manual |
| Threads | Professional account | **assisted** (no verified adapter yet) | operator manual |
| Threads | Personal profile | **assisted** | operator manual |
| Google Business Profile | Business | unattended | GHL social planner |
| Google Business Profile | Personal Google account | **unavailable** | none |

Each record also carries the exact action buckets (`unattended`, `operator_action`,
`unavailable`), the operator instruction for the one manual step, `checked_at`, and
the official `source_urls` used to verify the declaration. Refresh the record when a
source changes; never guess a capability into existence.

---

## Assisted contract

1. **Prepare the exact placement.** `prepare_assisted_placement` requires all five
   fields: `text`, `asset`, `keyword`, `cta`, `timing`. Missing or empty fields raise;
   nothing is handed off half-prepared.
2. **Hand off one step.** The package contains `operator_action.instruction` — the
   single manual action the operator performs in the native app.
3. **Status starts truthful.** The package is `awaiting-operator` with `receipt: null`
   and `published_by_system: false`.
4. **Record the receipt.** `record_operator_confirmation` requires a named operator
   and an explicit confirmation. It sets `operator-confirmed` and writes the receipt
   (`placement_id`, `operator`, `confirmed_at`, `method`, optional `evidence`).
   It also refuses anything it could not honestly attest: a package with no
   `placement_id`, a package that is not a prepared placement, a `confirmed_at` that
   is not an ISO-8601 timestamp, and a package that already claims publication —
   a claim is never laundered into a receipt. The record it returns must pass its
   own truth check before it is handed back.
5. **Never claim system publication.** `published-by-system` and bare `published` are
   forbidden statuses for an assisted placement.

The system never confirms on the operator's behalf, and an empty operator name is
refused.

## Refusal path

An unattended request on a personal profile returns a refusal, not a quiet reroute:

```json
{
  "ok": false,
  "refused": true,
  "route": "refused",
  "reason_code": "unattended_not_supported",
  "reason": "Ordinary personal profiles have no supported public posting or comment API. This system cannot publish or comment on a personal profile unattended. It can prepare the exact placement (text, asset, keyword, call to action and timing) and hand it to you for one manual step, then record your confirmation as the receipt.",
  "offer": {
    "route": "assisted",
    "message": "The assisted route is available: the system prepares the exact placement and gives you a one-step instruction. After you perform it and confirm, the system records an operator-confirmed receipt. It never claims the post was published by the system.",
    "next": "prepare_assisted_placement"
  },
  "no_silent_downgrade": true
}
```

A request for a truly unavailable capability (for example a personal Google account
with no Business Profile) refuses with `capability_unavailable` and `offer: null`.

## Truthful status surface

`status_surface(record)` returns the status from the declaration's own vocabulary:

| Route | Allowed status | Claim |
|---|---|---|
| assisted | `awaiting-operator` | nothing-posted |
| assisted | `operator-confirmed` | operator-confirmed |
| unattended | `published-by-system` | published-by-system |

Any assisted record that reports `published-by-system`, `published`, or
`operator-confirmed` without a valid receipt raises `UntruthfulPublication`. A
personal profile record on the `unattended` route is refused here too — the status
surface never renders that claim.

## Truth guard

`assert_truthful_publication(record)` fails closed when:

- an assisted or personal record claims `published-by-system`, `published`, or
  `published_by_system: true`;
- `operator-confirmed` has no valid receipt bound to that placement;
- `awaiting-operator` carries a receipt;
- a personal profile record uses the unattended route at all.

The status surface and the truth guard are ONE code path: both call
`_truth_of()`, and the personal-profile/unattended rule lives in one place
(`_reject_personal_on_unattended`). One record therefore gets one verdict and one
exception, in both directions — the read path can never bless a claim the guard
refuses, and the guard can never bless a claim the read path refuses. The matrix
in `tests/social-planner/test_t22_status_guard_matrix.py` proves it over every
combination of route, account type, personal flag, status and receipt.

Command Center can consume `capability_summary()` (or read the JSON directly); both
come from the same file, so the declaration has one source of truth.

---

## CLI

```bash
# Show the declaration (optionally filtered)
python3 scripts/profile_capability.py capabilities --channel facebook

# Refused: unattended personal-profile posting (exit 3)
python3 scripts/profile_capability.py request --channel facebook \
  --account-type personal --action post --placement placement.json --unattended

# Assisted: prepare the exact placement (exit 0, status awaiting-operator)
python3 scripts/profile_capability.py request --channel facebook \
  --account-type personal --action post --placement placement.json

# Record the operator's confirmation and print the status surface
python3 scripts/profile_capability.py confirm --package package.json \
  --operator "Operator Name"

# Guard a record (exit 4 = untruthful publication claim)
python3 scripts/profile_capability.py guard --record record.json
```

`placement.json` must contain `text`, `asset`, `keyword`, `cta` and `timing`.

## Tests

```bash
python3 -m unittest tests/social-planner/test_t22_profile_capability.py -v
```

The suite proves: unattended personal-profile requests are refused with a clear
reason; a receipt exists only after operator confirmation; a system-claimed
publication without a receipt fails the guard; and the capability data round-trips
as the single source consumed by the status surface.
