# Email Engine — PROCESS CERTIFICATE

- **Sequence:** `sequence-landing-page-10-promo` (`landing_page_10`)
- **Emails:** 10
- **Founder signature:** Jordan Marsh
- **All phases pass:** True
- **Deploy mode:** DRAFT-ONLY (nothing sends without explicit human approval)
- **Certificate SHA:** `6f9a350763e582616264c796dc122bc10636ba0423a2ffc17f9dac541d463f57`
- **Certified at:** 2026-07-21T11:05:29.849906+00:00

| Phase | Name | Verified |
|---|---|---|
| P1-SELECT | Select | yes |
| P2-GENERATE | Generate | yes |
| P3-QC | QC (fail-closed floor prover) | yes |
| P4-DEPLOY | Deploy (DRAFT-ONLY) | yes |

Issued by `run_email_engine.py` after a full P1->P4 pass through `email-engine-entry.sh`. The P3 gate is `tools/prove-email.py` (fail-closed). This certificate attests the governed pipeline ran in order; it does not authorize a send.
