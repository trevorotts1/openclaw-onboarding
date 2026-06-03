# SOP PA-13-02: Returns & Refunds

**Department:** Specialist 13 — Errands & Purchases Assistant
**SOP ID:** PA-13-02
**Version:** 1.0
**Owner:** {{TOKEN}}

---

## Purpose

To handle product returns, exchanges, and refund requests on {{TOKEN}}'s behalf — navigating retailer policies, managing the logistics, and tracking every return through to confirmed resolution. {{TOKEN}} hands over the item; we handle the rest.

---

## DMAIC Phase: Define → Measure → Analyze → Improve → Control

---

## Trigger Conditions

- {{TOKEN}} says "return this," "this didn't work," "send it back," or "I need a refund"
- An item arrived damaged, incorrect, or not as described
- Auto-detected: delivery past return window deadline (proactive reminder from Purchases Tracker)
- Initiated after a failed delivery resolution from PA-13-01

---

## Procedure

### Step 1: DEFINE — Gather the Facts

Get clear on the situation before touching the retailer:

- **What item?** — Pull the original order details from the Purchases Tracker (order #, vendor, date, price).
- **What's the issue?** — Wrong item, damaged, defective, didn't fit, changed mind, arrived too late?
- **What outcome does {{TOKEN}} want?** — Refund, exchange for same item, exchange for different item, store credit?
- **Timeline urgency?** — "Do you need the replacement in hand by a certain date?"

### Step 2: MEASURE — Check the Return Window

Immediately verify eligibility:

- [ ] Return window: How many days from delivery? Are we still inside it?
- [ ] Condition requirements: Unopened? Tags attached? Original packaging?
- [ ] Who pays return shipping? Free return label provided, or deducted from refund?
- [ ] Restocking fee? (Common on electronics, furniture, large items — 10-25%)
- [ ] Refund method: Original payment, store credit only, or exchange only?

Present a one-line summary to {{TOKEN}}: "This is within the 30-day window, free returns, full refund to your card. I'll get the label now."

### Step 3: ANALYZE — Choose the Best Return Path

Evaluate the options and pick the optimal route:

- **Return by mail** — Best for convenience. Print label, schedule pickup or drop-off.
- **Return in-store** — Fastest refund (often instant). Best when location is nearby and {{TOKEN}} is willing.
- **Carrier pickup** — Best for large items. Schedule a pickup window with UPS/FedEx.
- **Exchange cross-ship** — Retailer ships replacement immediately, hold on card until return scans. Best when {{TOKEN}} needs the item fast.

If the return window has closed, call the retailer anyway. Many will make exceptions, especially for defective items or loyal customers. Document the call: agent name, date, time, outcome.

### Step 4: IMPROVE — Execute the Return

1. Initiate the return through the retailer's portal or by calling customer service.
2. Download/print the return label and any RMA documentation.
3. If mailing: package the item securely, affix the label, photograph the package before drop-off.
4. Schedule a carrier pickup or coordinate drop-off with {{TOKEN}}.
5. Save the tracking number in the Purchases Tracker.

### Step 5: CONTROL — Track to Resolution

- Monitor tracking daily until the package shows "Delivered" to the retailer.
- Once delivered, note the retailer's stated processing time (typically 3-10 business days).
- Follow up on day after the processing window closes if no refund appears.
- When refund posts: verify the amount matches expectations (item + tax + original shipping if policy covers it). Log "Resolved" in the tracker.
- If refund is short: compare against the return policy. If discrepancy exists, contact the retailer for explanation. If justified, accept; if not, escalate.
- Close the loop with {{TOKEN}}: "Your $X refund for [item] posted today."

---

## Output Artifacts

- Return label and tracking number
- Updated Purchases Tracker entry (status: Returned → In Transit → Delivered → Refunded)
- Resolution confirmation to {{TOKEN}}

---

## Estimated Duration

- Research + label generation: 10-20 minutes
- Packaging/drop-off coordination: varies by method
- Tracking and follow-up: 2-5 minutes daily (passive)
- **Total active time: 20-30 minutes per return**

---

---

## CTQ Checks (Critical-to-Quality)

- [ ] Return eligibility verified (window, condition, fees, refund method) within 1 hour of {{TOKEN}}'s request
- [ ] Return label generated and tracking number captured same day
- [ ] Package tracking monitored daily until "Delivered to Retailer" scan confirmed
- [ ] Refund posting verified — amount matches expected (item + tax + shipping if policy covers)
- [ ] Purchases Tracker updated through every status (Returned → In Transit → Delivered → Refunded)
- [ ] {{TOKEN}} notified of resolution within 1 hour of refund posting

## Definition of Done

The wrong item is gone, the money is back in {{TOKEN}}'s account, and the tracker shows "Resolved" — {{TOKEN}} never had to chase a status update.

## Tone & Persona Note

Returns are the moment of truth — this is where {{TOKEN}} is already frustrated (wrong item, damaged, didn't work) and needs a fix, not friction. Be the calm in the storm: "I've got this. Here's what happens next." Never make {{TOKEN}} feel like the return is a burden on you. For Black women professionals who are often made to feel like complainers when advocating for fair treatment, your firm-but-polite persistence on customer service calls is a form of allyship.

## Escalation

- Retailer refuses return despite valid policy → request supervisor review; document refusal (name, date, reason); escalate to {{TOKEN}} for chargeback decision via Specialist 09 (Daily Check-In)
- Refund amount incorrect and retailer unresponsive after 2 attempts → flag for {{TOKEN}}; cc Specialist 11 (Personal Finance) for chargeback documentation
- Item was a gift and {{TOKEN}} lacks order details → attempt lookup by shipping address/name/gift receipt; if impossible, escalate to {{TOKEN}} with honest assessment via Specialist 09 (Daily Check-In)
- Return window closed but item is defective → attempt goodwill exception via phone (not portal); escalate to {{TOKEN}} if retailer refuses — cc Specialist 11's PA-11-04 (Renewal Negotiation) for negotiation tactics

*A smooth return is better customer service than a smooth purchase. This is where we earn {{TOKEN}}'s trust.*

*Version 1.0 — SOP PA-13-02 — {{TOKEN}}*
