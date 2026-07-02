# Golden Daybreak — Signature Funnel PROCESS-CERTIFICATE (specimen)

Signed proof that every phase of the Signature Funnel pipeline ran, **in order**, and
passed its fail-closed gate. Minted by the canonical no-skip orchestrator
(`run_signature_funnel.py`); the JSON alongside is the machine-verifiable artifact.

- **Certificate kind:** `signature-funnel-process-certificate`
- **Run id:** `run-golden-daybreak`
- **Funnel type / size:** `signature_funnel` / **7-step**
- **Skill version:** `1.0.0`
- **Issued at:** `2026-07-02T12:39:25Z`
- **All phases pass:** **True**
- **Nonce fingerprint:** `19dd9294004d6460` (specimen nonce `golden-daybreak-nonce-v1`)
- **HMAC signature:** `e638428d45b76b66f0077bfec7a4ac246ab5f8faa83d8573bcea7e4820abdb50`
- **Delivery:** preview-only; publishing requires explicit human approval (PRD §7 gate 7).

## Phase spine (attested in order)

| Order | Phase | Gate / delegate | Status |
|---|---|---|---|
| 0 | `P0-INTAKE` | `prove_sf_intake.py` | PASS |
| 1 | `P1-COPY` | `prove_sf_copy.py` | PASS |
| 2 | `P2-PROMPTS` | `prove_sf_prompt_floor.py` | PASS |
| 3 | `P3-IMAGES` | `kie_image.py` | PASS |
| 4 | `P4-MEDIA` | `ghl_media.py` | PASS |
| 5 | `P5-HTML` | `html_assembly` | PASS |
| 6 | `P6-COMPOSE` | `funnel_graph` | PASS |
| 7 | `P7-BUILD` | `ghl_rest_canvas.py` | PASS |
| 8 | `P8-DERIVE` | `derived_pages` | PASS |
| 9 | `P9-CERTIFY` | `prove_sf_no_pitch.py` | PASS |

## Verify

```bash
python3 49-signature-funnel/scripts/prove_sf_cert.py \
  --cert 49-signature-funnel/examples/golden-daybreak/delivery/golden-daybreak-FINAL/PROCESS-CERTIFICATE.json \
  --nonce golden-daybreak-nonce-v1      # PASS (exit 0)
```

No certificate — or a tampered one — means the funnel is NOT done
(`AF-FUN-PROCESS-INTEGRITY`).
