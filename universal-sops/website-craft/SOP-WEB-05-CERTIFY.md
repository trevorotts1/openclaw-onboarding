# SOP-WEB-05: CERTIFY + PREVIEW + APPROVE

**Cluster:** Website-Craft Rules (`universal-sops/website-craft/`)
**Owning role:** QC Specialist — Marketing
**Stage:** P4-CERTIFY
**Produces:** `website-certificate.json`

---

## 0. WHY THIS SOP EXISTS

A website is certified only when BOTH legs pass: the copy floors (P1) and the rendered build (P3). The
certificate binds the two so a thin page can never be quietly shipped and a rendered-but-thin page can
never pass as "done".

## 1. RE-RUN THE COPY PROVER (fail-closed)

```
python3 universal-sops/website-craft/prove_web_pages.py working/copy/website_copy_ledger.json
```

Exit 0 is REQUIRED. Any `AF-WEB-*` returns the site to P1-COPY as a revision — never certified.

## 2. CONFIRM THE BUILD VERDICT

Confirm the Skill 6 sealed verifier reached `overall_pass: true` for every built page (real preview
URLs, rendered `<img>` bound to the image manifest). A build that did not reach `verified` cannot be
certified.

## 3. WRITE THE CERTIFICATE

Write `website-certificate.json`:

```json
{
  "brand": "<brand>",
  "copy_prover": {"passed": true, "gate": "prove_web_pages.py", "ledger_sha256": "<sha>"},
  "build_verify": {"overall_pass": true, "pages": ["home", "services", "about", "faq"]},
  "persona_selection_log": "persona-selection-log.md",
  "brand_voice_source": "<lock or provisional source>",
  "model_provenance": "<client-owned model ids used; NEVER anthropic/claude-*>",
  "certified_at": "<iso8601>"
}
```

The certificate records the client-owned model provenance (no Anthropic / `claude-*` — the binding
client-runtime rule) and the exact `brand_voice_source` used.

## 4. PREVIEW + HUMAN APPROVE

Send the preview URLs for human approval before publish-with-approval. The site is DELIVERED only after
the human approves — the certificate is the machine leg, the human approval is the final leg.
