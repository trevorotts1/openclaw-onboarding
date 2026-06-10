# State Disclosure Compliance Protocol (Skill 39)

A COMPLIANCE POINTER, not legal advice. The agent surfaces the disclosure
obligations that typically apply in a transaction so nothing is missed; it does
NOT render a legal opinion and always defers to the operator's broker/attorney.

## Cardinal rule
The agent NEVER tells a client a disclosure is "not required" or "you can skip
it." It surfaces what commonly applies and routes any uncertainty to the
operator's broker or legal counsel.

## Universal disclosure categories (surface these, verify locally)
- **Seller's property condition disclosure** — most U.S. states require the
  seller to disclose known material defects. A handful are "caveat emptor" with
  narrower duties; the agent flags that this varies and to confirm the
  state-specific form.
- **Lead-based paint disclosure** — FEDERAL: required for homes built before
  1978 (Title X). The agent always surfaces this for pre-1978 properties.
- **Natural hazard / environmental** — flood zone, wildfire, earthquake, radon,
  etc. — varies heavily by state and locality.
- **Material facts** — deaths, prior damage, HOA litigation, boundary disputes —
  treatment varies by state; surface, don't adjudicate.
- **Agency disclosure** — who represents whom; required in most states at first
  substantive contact.

## How the agent uses this
1. Detect the property's state (from the normalized address).
2. Surface the categories above as a checklist for the operator/seller.
3. Explicitly label it: "This is a reminder of disclosures that commonly apply —
   please confirm the exact forms with your broker/attorney for <state>."
4. For pre-1978 homes, ALWAYS surface lead-based paint.

## What this protocol does NOT do
- Does NOT ship a per-state legal table (that would go stale and become
  unauthorized legal advice). It surfaces the universal categories and routes
  specifics to the operator's broker/legal.
- Does NOT auto-generate or auto-file disclosure forms.

## Logging
No PII is logged. A disclosure-surfaced note may be added to the transaction
context, but the event log records only the property + the category checklist
fired, never client identity beyond the existing contact reference.
