# core/contracts

Versioned JSON Schemas (draft 2020-12), `schema_version` = `1.0.0` on every record.

| File | Record | Source |
|---|---|---|
| `campaign-schema.json` | Canonical campaign record: brief copy, lyric lines with `critical` flags, target aspects | Directive 17.8, 21 |
| `artifact-schema.json` | Single artifact: stable ID, stage, sha256, provenance, `stale` flag, `supersedes` link | Directive 21, 22, 24.4 |
| `qc-schema.json` | Mandatory QC verdict: `PASS` / `FAIL` / `UNAVAILABLE`, evidence, checker version, independent reviewer | Directive 17.6, 17.8, 24.4 |
| `../acceptance-profile.json` | Versioned delivery thresholds (`profile_version` 1.0.0): export, timeline, lyrics, timing, audio, CTA | Directive 17.8 baseline |

Rules (17.8): `UNAVAILABLE` cannot become `PASS`. No aggregate average erases a critical
defect in identity, lyrics, offer, claim, product label or CTA. Threshold changes require a
documented decision before the affected qualification run.

Validate with stdlib only:

```bash
python3 -c "import json; [json.load(open(f)) for f in ['campaign-schema.json','artifact-schema.json','qc-schema.json','../acceptance-profile.json']]; print('schemas load OK')"
```
