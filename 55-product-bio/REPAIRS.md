# Product Bio Engine — REPAIRS register (faithful-or-repaired)

The two prompts ship **byte-identical** (sha256-pinned). Every defect the source
25-node n8n workflow carried is explicitly dispositioned KEEP / REPAIR / DROP —
never silently changed (PRD §3.5, G3). Plumbing residue is DROPPED; the IP text
is untouched; the one prompt inconsistency is KEPT verbatim and RESOLVED at the
gate.

| # | Source defect | Disposition | Where |
|---|---|---|---|
| D1 | Code node names its file `Book-titles-N.html`; its docstring says "cleaned_titles" (it reads `clean_html`) | **DROP** — n8n plumbing, not IP. The local file is named for the product (`Product-Bio-<slug>.html`) | delivery naming |
| D2 | Drive upload literally named **"HTML Test 3"** | **DROP** — deliverable named `Product-Bio-<slug>.html` | delivery naming |
| D3 | Level-2 folder search node named **"Book ID Folder"** (clone residue) | **DROP** — plumbing residue; no folder ladder at all (local-only) | delivery |
| D4 | Hardcoded Slack channel `C07FG2V4E0H` | **REPAIR** — no hardcoded channels; any push is per-client config through the client's own gateway, client-silent by default | P6-DELIVER |
| D5 | Dormant `phone` field (referenced by nothing in the LLM path) | **KEEP** — captured as OPTIONAL for handoff parity only (PRD O7); never required | intake schema |
| D6 | §10 teaches **20** close styles but the tracker demands **24** ("must write all 24") | **KEEP prompt verbatim; ENFORCE 24** — the tracker + anti-truncation rule are the stricter, later law (PRD O3) | `prove_pb_sections.py` (AF-PB-CLOSES) |
| D7 | Final Google-Doc name unverifiable (redacted `/copy` body in the digest) | **REPAIR** — deterministic local naming; the Drive `/copy` step is dropped entirely (the HTML file IS the importable artifact) | delivery |

## What the source fought with prose, this skill enforces

~40% of prompt 01 is anti-truncation scolding plus a self-reported word count. A
model reporting "6,500 words" proves nothing. Those prose rules are KEPT verbatim
in the baked prompt (they still steer the model) but the TRUTH is decided by
deterministic gates that MEASURE the stripped text:

- word band → `prove_pb_wordcount.py` (AF-PB-WORDCOUNT) — self-report ignored.
- completion block presence → `prove_pb_wordcount.py` (AF-PB-VERIFY-BLOCK).
- 10 sections in order → `prove_pb_sections.py` (AF-PB-SECTION).
- 24 closes → `prove_pb_sections.py` (AF-PB-CLOSES).
- per-section floors + StoryBrand beats → `prove_pb_sections.py` (AF-PB-COUNTS).
- HTML envelope battery → `prove_pb_html.py` (AF-PB-HTML-*).
