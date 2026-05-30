# State Disclosure Compliance Protocol

Surfaces the right disclosure POINTER for a property's state from
`references/state-disclosure-matrix.md`. **This is a pointer matrix, not legal
advice.** The actual disclosure decision always escalates to the licensed agent/
broker.

## When this protocol activates

- A listing is being taken (seller side) — what the seller must disclose.
- A showing/offer is scheduled (buyer side) — what disclosures the buyer should
  expect/receive.
- Pre-foreclosure outreach — cooling-off / consultant-disclosure pointers.

## Steps

1. **Resolve the state** from the geocode result (`state`) or the operator.
2. **Look up the pointer** in `references/state-disclosure-matrix.md` for that
   state/DC: the typical required disclosures and WHERE the authoritative form/
   statute lives (e.g. the state real-estate commission, the standard transfer
   disclosure form).
3. **Surface the pointer** to the agent/operator in plain language.
4. **ESCALATE the decision.** Skill 39 does not decide what must be disclosed,
   does not fill disclosure forms, and does not give legal advice — it points to
   the authoritative source and hands the decision to the licensed professional.
5. **Emit** a `disclosure_surfaced` event with `state` and `matrix_pointer_id`.

## Honesty floors

- Never state a disclosure requirement as legal fact — frame it as "typically
  required; confirm with your broker / the state form".
- Never fill or sign a disclosure on the client's behalf.
- The matrix is a CONVENIENCE POINTER and may lag statute changes; the
  authoritative source named in the matrix governs.
