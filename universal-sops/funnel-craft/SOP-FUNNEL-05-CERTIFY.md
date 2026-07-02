# SOP-FUNNEL-05: NO-PITCH + CERTIFICATE + PREVIEW/APPROVE + 10-EMAIL OFFER

**Cluster:** Funnel-Craft Rules (`universal-sops/funnel-craft/`)
**Master authority:** `49-signature-funnel/MASTERDOC.md` §5 (QC gates)
**Owning role:** Signature Funnel Specialist → owner (human approval)
**Stage:** P9-CERTIFY + P10-EMAIL
**Produces:** `PROCESS-CERTIFICATE.json`, a labeled `~/Downloads/` bundle, optional 10 promo emails
**Provers:** `49-signature-funnel/scripts/prove_sf_no_pitch.py` + `prove_sf_cert.py`

---

## 0. WHY THIS SOP EXISTS

A funnel is "done" only when the Thank-You page is clean AND a signed certificate proves every phase ran
in order. No certificate = the card never reaches Complete. A self-attested "all passed" is never
trusted — the provers read the artifacts and the HMAC.

## 1. NO-PITCH GATE (Thank-You is clean)

`prove_sf_no_pitch.py` asserts the Thank-You page carries **no offer name, no price, and no sale CTA**
(AF-FUN-TY-PITCH / AF-FUN-TY-PRICE / AF-FUN-TY-CTA), that a Thank-You page exists (AF-FUN-TY-MISSING),
that the offer ledger is non-empty (AF-FUN-OFFER-LEDGER-MISSING), and that every image has a real Kie
taskId resolving to a GHL media host. **After Downsell 2 the funnel never pitches again.**

## 2. THE SIGNED CERTIFICATE

`prove_sf_cert.py` emits `PROCESS-CERTIFICATE.json` ONLY when the phase ledger is contiguous and
in-order (AF-FUN-CERT-PHASE-GAP), every phase passed (AF-FUN-CERT-PHASE-FAIL), and the HMAC is valid
against the run-scoped 0600 nonce (AF-FUN-CERT-SIGNATURE). A missing certificate is AF-FUN-CERT-MISSING;
a broken chain is AF-FUN-PROCESS-INTEGRITY.

```
python3 49-signature-funnel/scripts/prove_sf_no_pitch.py <run-dir>
python3 49-signature-funnel/scripts/prove_sf_cert.py     <run-dir>
```

## 3. PUBLISH GUARD (human approval)

The pipeline STOPS at `/preview/<pageId>` URLs + a labeled `~/Downloads/<slug>-signature-funnel/`
bundle (all copy, prompts, PNGs, HTML fragments, `brief.json`, preview URLs, certificate). **Going live
is an explicit human approval** — the owner approves in the Review lane; the engine never auto-publishes.
Reporting is operator-verbose, never client-facing noise.

## 4. P10 — THE 10-EMAIL OFFER (handoff)

After the downsell is approved, offer: *"Want the 10 landing-page promo emails for this funnel?"* On
yes, hand the locked `brief.json` + final copy bundle to the **Email Engine (Skill 50)** via
`universal-sops/email-craft/` (sequence `landing-page-10-promo`); receive 10 emails and include them in
the Downloads bundle. Email generation is out of scope for Skill 49 — the contract is hand off brief +
copy, receive 10 emails.

## 5. DEFINITION OF DONE

Certificate present + valid, Thank-You clean, every `<img>` on the GHL media host, funnel-build QC ≥ 8.5,
preview URLs delivered, Downloads bundle labeled with the `<client>__<funnel>__<stage>__<type>__vNN`
grammar, and (if accepted) the 10 emails attached. Anything short of this is NOT done.
