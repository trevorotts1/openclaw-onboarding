# Golden regression sample — `golden-landing-10`

A complete, corpus-faithful **fictional** 10-email landing-page promo sequence that
PASSES `tools/prove-email.py` end-to-end and drives a `PROCESS-CERTIFICATE`. It is
the Email Engine's regression anchor (mirrors `51-signature-presentation/examples/golden-quest/`).

- **Fictional subject / no PII.** Founder = `Jordan Marsh`; offer = `The Momentum Method` (a made-up 30-day system). No real client, name, or data appears.
- **Sequence:** `sequence-landing-page-10-promo` — the fixed E1-E10 framework map (E1-3 PASTOR-Solutions, E4 Features-to-Benefit, E5 6 W's, E6 BAB, E7 3-B Plan, E8 Million Dollar Sales, E9 AIDA, E10 PAS).
- Every email: 2 A/B subjects (8-12 words, `{{contact.first_name}}` in the first 40 chars, no pricing), 2 preview lines, 150-300 words (E7 the 3-B Plan is < 150), founder's real name in the close. E1-3 carry >=3 CTAs.

## Files
- `brief.json` — the locked intake brief (PASSES the prove-email intake gate).
- `emails.json` — the 10-email copy ledger (PASSES the prove-email sequence gate); carries a signed `process_certificate` authorizing the DRAFT-ONLY handoff.
- `working/` — the run-dir mirror: `copy/brief.json`, `copy/emails.json`, `deploy/approval.json` (human approval), `deploy/build-plan.json` (the emitted DRAFT-ONLY Skill-44 plan), `prover_results.json` (captured PASS), `checkpoints/process_manifest.json`.
- `delivery/PROCESS-CERTIFICATE.{json,md}` — issued by `run_email_engine.py` after the full P1->P4 pass.
- `working/checkpoints/.cert-hmac-key` — the run-scoped signing material for **this fixture's** certificate.

### Why the signing key ships with this example (T0-64)

The certificate is HMAC-signed against a key that a genuine run mints inside its
own run directory (`run_email_engine.py:_cert_key`), and `_verify_process_certificate`
fails closed when that key is absent. This example previously shipped **without**
either a signature or a key, so the artifact the skill offers as its reference proof
would have been **rejected by the skill's own deploy-time verifier** — and nothing in
the verification path ever checked it, which is why it survived.

`verify.sh` now authenticates this certificate through the same code path the deploy
gate uses (`run_email_engine.py --verify-certificate`), so a reference artifact that
drifts out of contract is caught. That check can only exist if the fixture's key ships
with the fixture.

`.cert-hmac-key` here is **fixture material, not a credential**: it is a random value
scoped to this example directory, it authenticates nothing outside it, it grants access
to no service, account, client or box, and no real run ever reads it. A real run mints
its own key, 0600, in its own run directory, and that key is never committed.
- `broken-variants/` — 5 deliberately-broken inputs, each tripping ONE distinct AF, with `REJECTION-RESULTS.json` capturing the fail-closed proof.

## Reproduce

```bash
cd 50-email-engine

# 1) the two fail-closed gates on the golden inputs (both PASS / exit 0)
python3 tools/prove-email.py examples/golden-landing-10/brief.json  --kind intake
python3 tools/prove-email.py examples/golden-landing-10/emails.json --kind sequence

# 2) the whole governed pipeline P1->P4 through the ONE sanctioned entry (issues the certificate)
python3 - <<'PY'  # refresh the run-dir mirror
import shutil, os
g = "examples/golden-landing-10"
os.makedirs(g + "/working/copy", exist_ok=True)
shutil.copyfile(g + "/brief.json",  g + "/working/copy/brief.json")
shutil.copyfile(g + "/emails.json", g + "/working/copy/emails.json")
PY
bash email-engine-entry.sh --run-dir examples/golden-landing-10   # -> CERTIFICATE ISSUED

# 3) the DRAFT-ONLY Skill-44 build plan (nothing sends)
python3 tools/emit_build_plan.py --brief examples/golden-landing-10/brief.json \
    --emails examples/golden-landing-10/emails.json --folder "The Momentum Method — Promo Drafts"

# 4) prove every broken variant is REJECTED (exit 2 + its distinct AF)
python3 tools/prove-email.py examples/golden-landing-10/broken-variants/wrong_length/emails.json --kind sequence   # AF-EMAIL-SEQUENCE-LENGTH
python3 tools/prove-email.py examples/golden-landing-10/broken-variants/framework_incomplete/email.json --kind email  # AF-EMAIL-FRAMEWORK-INCOMPLETE
python3 tools/prove-email.py examples/golden-landing-10/broken-variants/persona_named/email.json --kind email        # AF-EMAIL-PERSONA-NAMED
python3 tools/prove-email.py examples/golden-landing-10/broken-variants/missing_subject/email.json --kind email      # AF-EMAIL-SUBJECT-COUNT
python3 tools/prove-email.py examples/golden-landing-10/broken-variants/unapproved_deploy/emails.json --kind sequence # AF-PROCESS-INTEGRITY
```

Deploy is **DRAFT-ONLY**: `approval.json` records a human approval to EMIT the draft; it never authorizes a send. A human publishes the GHL draft separately after the Skill-44 `qc-built-workflow.sh` (>= 8.5) gate.
