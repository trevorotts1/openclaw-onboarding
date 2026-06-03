# SOP Index — Errands & Purchases

**Department:** Errands & Purchases (13-errands-purchases)  
**Total SOPs:** 4  
**Format:** DMAIC (Define, Measure, Analyze, Improve, Control)  
**Last updated:** {{GENERATION_DATE}}  

---

## SOP Quick Reference

| SOP ID | Name | Frequency | Trigger | Page |
|--------|------|-----------|---------|------|
| PA-13-01 | Order & Purchase Execution | On-demand, 1-10x weekly | {{OWNER_NAME}} says "order," "buy," "grab," or sends a product link | [PA-13-01](PA-13-01-order-purchase-execution.md) |
| PA-13-02 | Returns & Refunds | On-demand, 1-5x monthly | Item arrives damaged, wrong, or {{OWNER_NAME}} wants to return | [PA-13-02](PA-13-02-returns-refunds.md) |
| PA-13-03 | Comparison Shopping | On-demand, 2-8x monthly | {{OWNER_NAME}} wants pricing research before committing to buy | [PA-13-03](PA-13-03-comparison-shopping.md) |
| PA-13-04 | Home & Service-Appointment Scheduling | On-demand, 2-6x monthly | {{OWNER_NAME}} needs a plumber, cleaner, installer, or personal service | [PA-13-04](PA-13-04-home-service-appointment-scheduling.md) |

---

## SOP Taxonomy

### Core Execution (Triggered by {{OWNER_NAME}} Request)
- **PA-13-01 — Order & Purchase Execution:** The primary workflow. Every purchase flows through this SOP — clarify the need, verify the details, scan for red flags, execute the order, and track through delivery. Estimated 10-15 minutes per purchase.
- **PA-13-02 — Returns & Refunds:** The resolution workflow. When a purchase goes wrong, this SOP handles everything from return-policy research to label generation to refund verification. Estimated 20-30 minutes per return.

### Research & Decision Support (Triggered Before Purchase)
- **PA-13-03 — Comparison Shopping:** The research workflow. Before {{OWNER_NAME}} commits to a purchase, this SOP casts a wide net across retailers, builds a weighted comparison, and presents the top 3 options with a clear recommendation. Estimated 30-45 minutes per comparison.

### Coordination & Logistics (Triggered by Service Need)
- **PA-13-04 — Home & Service-Appointment Scheduling:** The provider management workflow. From researching and vetting service providers to booking appointments and following through to completion. Estimated 40-60 minutes per appointment.

---

## SOP Dependency Map

```
PA-13-03 (Comparison Shopping) ──── feeds into ────▶ PA-13-01 (Purchase Execution)
                                                              │
                                                              │ (if purchase fails: wrong/damaged/late)
                                                              ▼
                                                     PA-13-02 (Returns & Refunds)

PA-13-04 (Service Appointments) ──── independent workflow ──── uses Provider Registry
```

### Key Cross-References
- **PA-13-01 → PA-13-02:** When a delivery is wrong, damaged, or late → escalate to Returns & Refunds
- **PA-13-03 → PA-13-01:** When {{OWNER_NAME}} selects an option from the comparison → execute purchase immediately
- **PA-13-04:** Independent of the purchase SOPs but shares the Provider Registry and calendar integration
- **All SOPs → Purchases Tracker:** Every order, return, and appointment is logged in the central tracker

---

## Reading Order for New Errands & Purchases Specialists

1. **PA-13-01 — Order & Purchase Execution** (the core workflow — read this first; everything else connects to it)
2. **PA-13-02 — Returns & Refunds** (the fix-it workflow — paired with PA-13-01; most purchases go well, but when they do not, this is how you recover)
3. **PA-13-03 — Comparison Shopping** (the research workflow — read before handling any "find me the best X" request)
4. **PA-13-04 — Home & Service-Appointment Scheduling** (the coordination workflow — distinct from purchasing but equally high-stakes; someone is coming to {{OWNER_NAME}}'s home)

---

## Shared Tracking Systems

| System | What It Tracks | Updated By |
|--------|---------------|------------|
| **Purchases Tracker** | Every order: date, item, vendor, price, order #, ETA, status, return window | PA-13-01, PA-13-02 |
| **Provider Registry** | Every service provider: company, contact, rating, license status, {{OWNER_NAME}}'s feedback | PA-13-04 |
| **Comparison Archive** | Past shopping research: item, date, options compared, {{OWNER_NAME}}'s choice, notes | PA-13-03 |

---

## Quality Gates Per SOP

### PA-13-01 — Before clicking "Place Order":
- [ ] {{OWNER_NAME}} approved the total price (item + shipping + tax + fees)
- [ ] Return policy checked (especially for purchases over $50)
- [ ] Seller legitimacy scan passed (no counterfeit, fake-review, or subscription-trap red flags)
- [ ] Payment method confirmed
- [ ] Shipping address confirmed (home, office, or gift recipient)
- [ ] Delivery ETA matches {{OWNER_NAME}}'s timeline

### PA-13-02 — Before initiating the return:
- [ ] Return window is still open — verified against delivery date in Purchases Tracker
- [ ] Condition requirements met (unopened, tags, original packaging)
- [ ] Return shipping cost disclosed (free label, or deducted from refund)
- [ ] Restocking fee checked
- [ ] Refund method identified (original payment, store credit, exchange)
- [ ] Best return path chosen (mail, in-store, pickup, cross-ship)

### PA-13-03 — Before presenting options to {{OWNER_NAME}}:
- [ ] At least 3 retailers checked (major retailer, brand-direct, and one alternative)
- [ ] Price history reviewed for big-ticket items
- [ ] Exactly 3 options presented with a clear #1 recommendation
- [ ] Each option includes: total price, delivery ETA, return policy summary
- [ ] Recommendation includes a one-sentence rationale

### PA-13-04 — Before booking the appointment:
- [ ] Provider vetted: 1-star + 3-star reviews read, license verified, phone call completed
- [ ] Pricing confirmed in writing (flat rate or hourly, trip charge, minimum hours, materials)
- [ ] Availability window confirmed as compatible with {{OWNER_NAME}}'s schedule
- [ ] Access details confirmed (address, door code, gate, parking, pets)
