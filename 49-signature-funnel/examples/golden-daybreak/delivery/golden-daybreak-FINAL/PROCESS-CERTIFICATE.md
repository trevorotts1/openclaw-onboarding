# Golden Daybreak — Signature Funnel PROCESS-CERTIFICATE (specimen)

Signed proof that every phase of the Signature Funnel pipeline ran, **in order**, and
passed its fail-closed gate. Minted by the canonical no-skip orchestrator
(`run_signature_funnel.py`); the JSON alongside is the machine-verifiable artifact.

- **Certificate kind:** `signature-funnel-process-certificate`
- **Run id:** `run-golden-daybreak`
- **Funnel type / size:** `signature_funnel` / **7-step**
- **Skill version:** `1.0.5`
- **Issued at:** `2026-07-05T15:03:11Z`
- **All phases pass:** **True**
- **Nonce fingerprint:** `19dd9294004d6460` (specimen nonce `golden-daybreak-nonce-v1`)
- **HMAC signature:** `f728de0482cfbc46b35e75c66c1036b1535e8b2eb58b88dd630d619231734cad`
- **Delivery:** preview-only; publishing requires explicit human approval (PRD §7 gate 7).

## Phase spine (attested in order)

| Order | Phase | Gate / delegate | Status |
|---|---|---|---|
| 0 | `P0-INTAKE` | `prove_sf_intake.py` | PASS |
| 1 | `P1-COPY` | `prove_sf_copy.py` | PASS |
| 2 | `P2-PROMPTS` | `prove_sf_prompt_floor.py` | PASS |
| 3 | `P3-IMAGES` | `kie_image.py` | PASS |
| 4 | `P4-MEDIA` | `ghl_media.py` | PASS |
| 5 | `P5-HTML` | `html_fragments` | PASS |
| 6 | `P6-COMPOSE` | `prove_sf_graph.py` | PASS |
| 7 | `P7-BUILD` | `prove_sf_build.py` | PASS |
| 8 | `P8-DERIVE` | `derived_pages_ledger` | PASS |
| 9 | `P9-CERTIFY` | `prove_sf_no_pitch.py` | PASS |

## Verify

```bash
python3 49-signature-funnel/scripts/prove_sf_cert.py \
  --cert 49-signature-funnel/examples/golden-daybreak/delivery/golden-daybreak-FINAL/PROCESS-CERTIFICATE.json \
  --nonce golden-daybreak-nonce-v1      # PASS (exit 0)
```

No certificate — or a tampered one — means the funnel is NOT done
(`AF-FUN-PROCESS-INTEGRITY`).
