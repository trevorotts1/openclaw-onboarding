# No-Offer-Pricing Gate (S71-03)

Signature Launch change order, packet doc 07 section 3; acceptance unit A06
("Landing has no offer pricing across public surfaces"), owners S71.

## Policy

The Signature Launch landing page (profile `signature_launch_landing`)
carries NO offer pricing on any public surface. Pricing lives on the
product-selection and order-form steps, never on the landing page. This
gate is the deterministic L1 check for that rule. It is semantic and
structural: pricing context, not the currency symbol, is what
incriminates a number. A dollar-sign-only test would both miss bare
figures ("the tuition is 1500") and false-flag legitimate numbers.

## Where it lives and how to run it

The gate is an extension of the existing public-copy validator, not a
second scanner: `scripts/validate_public_copy.py`, enabled per run with
the `--no-offer-pricing` flag (the `scan(..., no_offer_pricing=True)`
parameter in code). Off by default, so legacy profiles and all
pre-existing checks behave exactly as before; the flag is the profile
switch for `signature_launch_landing`.

```bash
python3 scripts/validate_public_copy.py --no-offer-pricing <file> [...]
```

Exit codes are the validator's own (0 pass, 1 fail, 2 usage/IO error).
When pricing is among the failures, the banner reads "FAIL: offer pricing
detected on a no-price public surface." and every finding names its
surface and signal class, with file and line, for example:
`offer price in image alt text: price anchor amount`.

Wiring the flag into the stage pipeline for the
`signature_launch_landing` profile is S71-02's integration work; this
gate provides the check itself.

## Surfaces checked

- visible copy (rendered text; for Markdown, the raw text including
  image alt syntax)
- image alt text (`alt` attributes)
- title attributes (`title="..."`)
- accessibility labels (`aria-label`, `aria-description`)
- page title (`<title>`)
- meta content (`<meta ... content="...">`, including descriptions)
- structured data (JSON-LD script blocks)

Rendered text inside images themselves (pixels) is not machine-readable
by this L1 gate; it is covered by the L2 visual/semantic review below.

## Pricing signals (each fails with the named reason)

- currency amount: `$497`, `USD 497`, `497 dollars`
- bare price figure: a number attached to a price word (price, cost,
  tuition, fee, investment, deposit, total, rate, payment), "only N",
  "pay N", or a structured `"price":` key
- per-period price: `199 per month`, `$99/mo`, `49 a year`
- installment amount: `3 payments of $199`, `payments of 199`
- discount amount: `save $500`, `$100 off`
- discount percentage: `50% off`, `50 percent off` (a percentage tied to
  "off" IS pricing, symbol or spelled out)
- price anchor amount: `worth $2,000`, `valued at`, `compare at $1,200`,
  `$2,000 value`
- spelled-out price: `five hundred dollars`

## Not pricing (never flagged by design, proven by fixtures)

- phone numbers: `(404) 545-4552`, `+1 917-415-2338`, `555-0134`
- calendar dates: `October 15, 2026`, `2026-10-15`, `03/03/2026`,
  month names and years in prose
- counts and durations: `12 live sessions`, `200 seats`, `48 hours`,
  `3 times per week`, `a total of 500 founders`
- non-price percentages: `92% of our graduates`, `Save 20% of your time`,
  and the same statistics spelled out (`98 percent`, `98 per cent`);
  suppression never turns on typography alone
- star ratings: `a satisfaction rate of 5 stars` (a rating denominated
  in stars is a statistic, not a rate price)
- deadline countdowns: `02:14:59`

Stated boundaries of the rule as implemented:

- A bare numeric rate construction (`199 per month`, `3 per week`) reads
  as pricing and IS flagged; prose cadence (`3 live calls every week`)
  is not.
- Bare "save N" with no currency marker is NOT flagged, to protect
  non-price savings claims ("save 20% of your time").
- `$0` IS flagged: a stated price of zero is still offer-price copy on a
  no-price surface; a free route is expressed without price copy.

## Evidence

This gate produces A06's L1 evidence: the validator run over the
landing output plus the fixture suite in `tests/test_no_offer_pricing.py`
(registered in `tests/run_tests.py`), covering every signal class on
every surface class (must fail with the named reason) and the tricky
clean cases above (must pass), with fixtures
`tests/fixtures/public-copy-noprice-valid.html`,
`tests/fixtures/public-copy-noprice-valid.md`, and
`tests/fixtures/public-copy-noprice-invalid.html`.

A06 also requires a full L2 visual/semantic review. That review is
S71-10's independent work (the reviewer is never the author) and is NOT
produced by this gate or this note.
