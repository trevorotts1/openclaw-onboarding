# No-Pitch Policy — Skill 82 (S82-01)

**Scope:** the terminal Signature Launch thank-you page (page role
`thank_you`). This page confirms and delivers a completed purchase. It is
not a sales page.

## 1. The launch-mode rule

The final thank-you page carries **no new pitch**. Specifically prohibited:

- any unsolicited new offer, whether or not it has a price;
- any call to action that initiates a new charge, including a hidden or
  "one-click" purchase action;
- any unpurchased product presented as a recommendation, upgrade,
  "complete your setup" step, or "one more thing";
- manipulative urgency/scarcity copy aimed at a further purchase.

Allowed — and, where they identify a completed purchase, **required**:

- the actual purchased product names;
- the actual unit amount of each purchased item;
- the actual order total, order number, and currency;
- the billing schedule and recurring terms of purchased items
  (interval, trial terms, next charge where the verified snapshot carries
  them);
- per-item payment status (paid / pending / failed), stated honestly;
- access, download, login, and scheduling actions for benefits the
  customer actually purchased;
- support contact and manage-purchase actions (receipts, billing portal,
  subscription management);
- approved noncommercial next steps that are part of the approved
  fulfillment plan (e.g. joining an included community at a supplied,
  valid destination).

An action for a purchased benefit is not a pitch. A button that initiates
a new paid offer is. The test is the action's effect, not its wording:
"Continue" that charges is a new-charge CTA; "Access your course" that
opens a purchased destination is an `access` CTA.

A pending purchase must never be presented as confirmed: no
"You are all set" headline for unconfirmed access. If only an extra is
pending while the base is paid, the base is confirmed and the extra is
labeled pending separately. Valid base access is never withheld because
an optional charge is unresolved (acceptance A20).

## 2. Structured CTA classification

Every CTA on the page must be classified as exactly one of:

| Classification | Meaning | May initiate a charge? |
|---|---|---|
| `access` | Open a purchased membership / course / protected destination | No |
| `download` | Download a purchased deliverable | No |
| `manage_purchase` | Receipts, billing portal, subscription management for an existing purchase | No (manages, never starts, a purchase) |
| `support` | Contact support / help path | No |
| `schedule_included_service` | Book a service already included in a purchased item | No |
| `noncommercial_next_step` | An approved noncommercial step in the fulfillment plan | No |

Any CTA outside this set, any CTA flagged `initiates_new_charge: true`,
and any CTA referencing an offer that is not in the verified purchased
set fails validation (`scripts/validate_thank_you.py`).

Classification alone is not sufficient: the validator also requires that
every displayed item carry verified order provenance (a native line
reference and event identity from the verified normalized purchase
snapshot), and the spec requires an independent semantic review pass to
catch promotional copy that a structural allowlist misses.

## 3. Migration mapping — Skill 49 legacy no-pitch validator

R49's `prove_sf_no_pitch.py` enforces, for the legacy Skill 49 funnel's
thank-you page: **no offer name, no price, no sale CTA** on the final
thank-you page at all.

| Behavior | Legacy mode (Skill 49) | Launch mode (Skill 82) |
|---|---|---|
| Purchased product name displayed | **Rejected** | **Allowed and required** |
| Purchased unit amount / total displayed | **Rejected** | **Allowed and required** |
| Order number / billing schedule displayed | **Rejected** (any price-like detail fails) | **Allowed and required** |
| Sale CTA for a new offer | Rejected | Rejected |
| Access/download CTA for a purchased benefit | Not modeled (any CTA is suspect) | Allowed, under a CTA classification |
| Unpurchased product shown as recommendation | Rejected (as a name/price) | Rejected (as an unprovenanced / unpurchased display item) |
| Enforcement mechanism | Token blacklist (names, amounts) | Structured checks: provenance, purchased-set equality, CTA classification, no-new-charge |

Rules of the migration:

1. Legacy behavior remains in legacy mode only, explicitly labeled. The
   Skill 49 prover is not weakened for legacy funnels.
2. In launch mode the token blacklist is **replaced**, not patched with
   exceptions: a broad regex must never strip useful order information
   (names, amounts, totals, schedules) that the buyer is entitled to see.
3. The conflict and migration tests live with R49/S49 (packet doc 19,
   conflict register item "R49 prohibits any offer name/price on final
   thank-you", owners S49 + S82). S82 supplies the launch-mode positive
   fixtures (real purchased-name/amount pass cases) and negative fixtures
   (new-offer rejection cases) exercised by this skill's tests.
4. Mode is a property of the launch/page request, never inferred from
   page content. A page that opens with "thank you" and then pitches is
   an upsell page (Skill 80) in both modes — opening words do not make
   it this terminal page.

## 4. Authority: where purchase truth comes from

- Purchase truth comes only from the verified normalized purchase
  snapshot (packet purchase-event shape) and the S44 entitlement state.
- Query-string values (`vip=true`, customer names, email addresses) are
  never authority and never grant, upgrade, or reveal access.
- Displayed entitlements must equal the verified purchased entitlement
  set exactly (`scripts/validate_entitlements.py`): nothing unpurchased
  appears, nothing purchased is silently dropped.
- S44 owns granting entitlements and operational messages; this page
  consumes that state. Fulfillment does not depend on reaching this page.
