# S44 L4 completion record — CR-S82-002 five checks, BCEO Client Sandbox

Date: 2026-10-16. Location: BCEO Client Sandbox, location ID
`XCgFTEA1oDvsPnTqqgoB` — the named test location only. Authority:
Trevor's rulings relayed by MAIN — read-back proof in a named test
location (2026-10-16 ~07:50 EDT), then TEST PAYMENTS ALLOWED IN THE
SANDBOX ONLY (2026-10-16 ~09:48 EDT): test mode only, no real
charges, no client location, nothing outside the sandbox. Run 1 of
this L4 work (state-absent inventory) is recorded in
`L4-RUN-2026-10-16.md`; this file completes the record. All claims
below were verified firsthand by S44 through native read-backs.

## How purchase state was built (mapping disclosure)

- The sandbox has **zero payment providers integrated**
  (list-integration-providers: providers [], total 0), so no card
  checkout surface exists. There is **no create-order operation** and
  **no refund operation** anywhere in the connector/API registry
  (refund searched repeatedly; `refund-transaction` is not in the
  registry). Product creation was not usable (create-product's
  productType enum rejected every value tried with 422; the product
  list read empty at build time).
- Purchases were therefore built from the API-creatable purchase
  family: a test contact + invoices whose items are self-describing
  (name/currency/amount/qty; productId optional) + payments recorded
  against the invoices, which produce native transactions. Every
  object is test mode (`liveMode: false`). This is the native
  purchase state the platform itself maintains for these objects;
  the pipeline consumed the platform's own read-backs, never
  hand-written substitutes.

## Native objects (all BCEO Client Sandbox, all test mode)

- Buyer 1 contact `QzIXSs3mnrIuR4agE6R2` (s44-l4-buyer@example.com)
- Invoice A `6ad22df3baae1b6f9b2d5674` (INV-000001): main item
  `6ad22df3baae1b6f9b2d5675` $49 + bump item `6ad22df3baae1b6f9b2d5676`
  $17 = $66, paid. Transaction A `6ad22e7c4caebbd2beeb917e`,
  succeeded, 2026-10-16T14:02:36.458Z.
- Invoice B `6ad22ecd07479c1eab71d70f` (INV-000002): extra item
  `6ad22ecd07479c1eab71d710` $97, status draft, amountPaid 0 — no
  transaction exists for B.
- Invoice C `6ad22ed49e6698d9aff95154` (INV-000003): extra item
  `6ad22ed49e6698d9aff95155` $97, paid. Transaction C
  `6ad22f56f8acee4bc57a26c2`, succeeded 2026-10-16T14:06:14.774Z,
  later refunded (check 4).
- Buyer 2 contact `Hf63k0vcefn3MNmlGYri` (s44-l4-buyer2@example.com);
  Invoice A2 `6ad2388cd63d90c6ba4263bf` (INV-000004) $49 paid;
  Transaction A2 `6ad238d157d447970c871671` succeeded
  2026-10-16T14:46:41.199Z.

Pipeline: S44's real normalizer / processor / store / fulfillment-map
producer ran against these read-backs. Durable store:
`l4-store.sqlite` (tenant `bceo-client-sandbox`, launch
`signature-launch-l4`). Drivers: `run_l4_pipeline.py`,
`run_l4_resume.py`, `run_l4_resume2.py`, `run_l4_check3.py`,
`run_l4_refund.py`. Results: `l4-pipeline-results.json`,
`l4-check3-results.json` (pre-send snapshot; the store and the
native conversation are the ground truth for the send's final
state), `l4-refund-results.json`.

## Platform behaviors observed (disclosed, not worked around)

- Every paid invoice auto-generates, in the buyer's conversation, a
  type-27 "Payment received" activity and a type-3 "PAYMENT IS
  SUCCESSFUL!" email. Those are platform invoice receipts, distinct
  from S44's confirmation send; the platform emails show status
  failed because the test addresses are at example.com, a reserved
  domain that accepts no mail. S44's confirmation sends land in the
  same conversation and are identifiable by subject/body.
- A transaction refund does **not** flip the invoice's status:
  after the refund, get-invoice C still reads status "paid",
  amountPaid 97. The refund is recorded on the transaction
  (status "refunded", amountRefunded 97). Any consumer keying off
  invoice status alone would miss a refund on this platform.

## Check verdicts

### Check 1 — base entitlement granted when the buyer closes the tab right after checkout: PROVEN (L4)
Invoice A's native read-back was ingested and processed by the
pipeline alone: ent-main and ent-bump granted, fulfillment actions
completed, and the verified-purchase tag applied — the buyer's
native contact read-back carries tags exactly
`["s44-l4-verified-purchase"]`. No page visit, thank-you page, or
browser session exists anywhere in this flow; the grant derives
from the verified payment event only. (A20's tab-close property.)

### Check 2 — a later extra-offer failure leaves the base grant intact: PROVEN (L4), failure form disclosed
Invoice B's event processed to `no_grant:unknown` with zero actions
created; the active entitlement set stayed exactly
[ent-bump, ent-main] and ent-extra was never granted. The failure
form is "payment never completed" (invoice draft, amountPaid 0, no
transaction): the sandbox has no payment provider, so no
declined-charge transaction can be produced there. After all later
steps including the check-4 refund, Invoice A still reads paid
(get-invoice traceId `4c4b6165-4400-4251-b580-0ece350f4013`).

### Check 3 — exactly one onboarding/confirmation send: PROVEN (L4) on clean re-run; run 1 duplicated by operator error, disclosed
Run 1 (buyer 1): the store's send action was claimed exactly once,
but the operator (S44) re-executed through a second channel while
the first channel's outcome was unverified (it was invisibly
pending connector approval); both executions landed when the shared
approval was granted, producing **2** native confirmation messages
(`wMjb8Fl3sTiYZERYQRXf` 14:35:16.294Z and `EHe6iQGiMuVCgBDJYIM4`
14:35:18.970Z, both delivery-failed at the reserved domain). One
logical claim, two native sends — an operator recovery error,
recorded here and in `l4-pipeline-results.json`, not hidden. The
pipeline itself never re-sent: the second claim path returned
already-claimed.
Clean re-run (buyer 2): the send action was claimed fresh and
executed through ONE channel only (messageId
`KT9zxj56FqEzzvDFbmGD`, conversation `kVYJVdi7IuCNMN05R3LP`,
connector approval granted). Native conversation read-back: 3
messages total — the platform payment activity, the platform
payment-success email, and **exactly 1** S44 confirmation send
(14:58:31.366Z). Ledger action marked done against that evidence;
the page-observation path's second claim returned
already-claimed, no second send.

### Check 4 — refund of the extra only revokes the extra; the original purchase is untouched: PROVEN (L4)
No refund operation exists in the API surface, so the refund was
executed in the sandbox web UI (S44's own browser): Payments >
Transactions > transaction C's menu > "Refund" > modal amount
97.00 USD > confirm; toast "Refund request successfully
processed". The transaction details page then showed status
"Refunded", TEST MODE, with a Refunds section entry: Oct 16
11:10 AM EDT, $97.00, Status "Succeeded" (Ref Id blank — the
platform issues no refund object ID here). Independent API
read-back (list-transactions traceId
`ae3b4863-d9d5-4b47-b6ea-f3d5023096a4`): transaction C status
"refunded", amountRefunded 97, updatedAt 2026-10-16T15:10:22.096Z;
transaction A still "succeeded", amountRefunded 0.
The refund read-back (native_event_kind "refund", payment_status
"refunded", invoice C's line only; event identity composed only
from provider-supplied fields — transaction ID + the transaction's
own updatedAt at the refunded state, since no refund object ID
exists) was ingested and processed by the real pipeline:
`refund_applied`. Result: active set [ent-bump, ent-main];
fulfillment map shows ent-extra **revoked / manage_purchase** with
ent-main and ent-bump still **granted / access**; a redelivery of
the identical refund state deduped ("duplicate") instead of
re-applying. Buyer 1's native tags unchanged
(`["s44-l4-verified-purchase"]`, get-contact traceId
`2d15f4ec-00cd-4de4-99ca-0ff6dbd6e081`); Invoice A still paid.
One incidental browser event, disclosed: while invoice C's row
menu was open, a click opened an unsaved "Convert to Template"
form; it was abandoned without saving — no template or any other
object was created or altered.

### Check 5 — the entitlement_version source S44 supplies: ANSWERED, values produced from native state
`Store.entitlement_version` (ev1 spec, independently reviewed
2026-10-16) computed over a book fed exclusively by these native
events:
- Buyer 1 after purchase C: `ev1:e89acbc8f9bf257668fcc7144d6891676af3e6809aef326948dbf48b10d81c09`
- Buyer 1 after the check-4 refund: `ev1:0dc979c3eae0e95d46daf2b25220b65bc642b428a0ecf8806097cc9a7966d59a`
- Buyer 2 after purchase A2: `ev1:139be695a6624c756dc346dbb18b34ef454a5d208d0ae83746908a177b0e75ed`
The version changed exactly when the underlying native state
changed (grant of the extra, then its refund) and for no other
reason.
