# Email Superlibrary — `email-library/`

The reusable Email IP as a tagged, retrievable catalog. **36 entries**, each shipped
as a paired `<id>.json` (machine spec) + `<id>.md` (how-to / purpose / use-cases /
detailed example / keyword tags), grouped by type:

| Group dir | type | count |
|---|---|---|
| `frameworks/` | `framework` | 13 |
| `buyer-types/` | `buyer-type` | 4 |
| `objectives/` | `objective` | 4 |
| `persona-styles/` | `persona-style` | 12 |
| `sequences/` | `sequence` | 3 |

Retrieval is **tags-first + optional semantic**:
- **Lexical (wired, proven):** `catalog-index.json` (list-shaped: `id/type/name/tags/length/best_for/file`) is normalised into `catalog-built-index.json` and scored by `tools/email_matcher.py` (`email_matcher_cli.py --match "<text>"`). Deterministic, stdlib-only, never blocks the user's explicit desire.
- **Semantic (embed-once):** the shared prebuilt Gemini index under `../index/` (`EMAIL-INDEX-MANIFEST.json`). Client boxes DOWNLOAD sha256-verified vectors — they NEVER re-embed. Hooks in through `email_matcher.EmbeddingReranker`.

## STEP-0 wiring
1. `EMAIL_LIBRARY_CATALOG` -> this directory; `EMAIL_LIBRARY_INDEX` -> `catalog-built-index.json` (box-local paths, written at install/update).
2. Any front door (Skill 38 request, Skill 49 post-Downsell trigger, Command Center task ingest) that needs an email calls `email_matcher_cli.py --match` FIRST to route the brief to a framework / buyer-type / objective / persona-style / sequence.
3. The matched entry's `<id>.md` is the authoring guide; its `<id>.json` `rules{}` block mirrors exactly what `tools/prove-email.py` enforces for that entry (frameworks: structure + `enforced_part_count` + `word_band`; sequences: `framework_map` + `preview_count` + `subject_mode` + `cta_rules` + `disruptive_required`; persona-styles: `never_named_or_quoted`).
4. After authoring, `tools/prove-email.py` is the fail-closed gate; nothing advances to the DRAFT-ONLY Skill-44 deploy without a PASS + explicit human approval.

## Entry `<id>.json` schema (per file)
```json
{
  "id": "framework-pas",
  "type": "framework",
  "name": "PAS (Problem-Agitate-Solution)",
  "tags": ["pain-point", "..."],
  "length": "150-300 words",
  "best_for": ["humanistic", "abandoned-cart", "..."],
  "file": "framework-pas.md",
  "rules": { "kind": "framework", "framework_id": "pas", "enforced_part_count": 3, "...": "..." }
}
```

## Rebuild / verify
- Rebuild the lexical built index: `python3 ../tools/email_matcher_cli.py --build-index`
- Route corpus examples: `python3 ../tools/email_matcher_cli.py --selftest`
- Register / coverage check: `python3 register.py --check` (every catalog entry has paired on-disk files + valid `rules{}`; the set fully covers the prover's 13 frameworks / 12 personas / 4 objectives / 4 buyer-types / 3 sequences).

The structures, counts, names and rules are **SACRED** (see `../MASTERDOC.md`). Ports may sharpen the how-to and examples; they never floor, reorder, rename or reinterpret the IP.
