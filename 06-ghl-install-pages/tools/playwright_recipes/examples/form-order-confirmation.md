# Payment-owned form Order Confirmation

Use a separate `forms.submission` job with `submission.mode` set to
`Order Confirmation`. This uses the dedicated `native_order_confirmation`
handler. The plain message/redirect handler continues to refuse payment-owned
outcomes. Replace every placeholder and example price with actual approved
same-form inventory; the example's deliberately stale observation time must
never be replaced with a fabricated successful read.

The native On Submit dropdown permits Order Confirmation even on an ordinary
form with no payment field. Its canned John Doe/order totals preview therefore
proves neither a product binding nor successful payment. This handler requires
exactly one native payment element and one configured product row. It reads the
native checkbox's matching ID/name/value, exact product name, displayed monthly
amount and existing checked state without clicking that checkbox.

The current native form DOM exposes a product ID but no price ID or stable
payment-element ID. No payment-element ID is invented. The handler reuses the
existing Skill44 client and canonical shared ProductsPricesAdapter for
read-only product, price and complete price-list GETs. It requires exactly one
catalog price, matching every approved native price term, so the DOM's missing
price ID has one unambiguous possible identity. Multiple-price products
(including a monthly/annual pair), truncated lists and unknown totals are
refused. A caller's PASS dictionary alone cannot enable the writer.

The captured display subset is one USD monthly recurring product without trial,
installments, discounts or additional product rows. Broader billing formats and
direct native price identity need further captured implementation. API
401/403 refusals are terminal authorization stops and do not authorize a
browser/credential switch.

Before changing the outcome, the script verifies its exact editor/form name,
expected previous On Submit mode, current native product and approved catalog.
Conditional-precedence warnings require the explicit boolean acknowledgment.
It preserves the captured scheduler/ordinary Settings switches and product
checkbox, saves only the outcome once, independently reopens the exact form,
and rechecks mode, notice, product, Settings and canonical catalog.

The result distinguishes saved versus reused configuration. It records
`price_identity: UNIQUE_CATALOG_PRICE` rather than claiming the form directly
exposed a price ID. `payment_verified`, `submission_verified` and
`behavior_verified` stay false. No product/price is created, no checkbox is
selected, and no payment, submission, preview journey or publication is run.
The first real staging product captured in this pass had two prices; it remains
refused by this narrow handler. Unit fixtures establish code behavior and are
not native acceptance proof.
