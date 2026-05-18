# 11-Dimension Rubric for QC Sub-Agents

Each dimension scored 0-10. **PASS = total ≥85 AND no dimension <6.5.**

## Scoring bands (apply per dimension)

| Score | Criteria |
|---:|---|
| 10 | Exemplary; all required elements present + extras |
| 8-9 | Strong; minor gaps |
| 6-7 | Adequate (PASS minimum: 6.5) |
| 4-5 | Weak; one required element missing or borderline |
| 0-3 | Severe failure |

## Dimensions

### Dimension 1: Structural Completeness
- 10: All 19 sections present in correct order. Headers match `^## \d+\.` regex. No "TODO" / "to be determined" / empty placeholders.
- 6-7: 18 sections present, 1 missing OR all 19 but 1 has placeholder
- 0-3: <16 sections
- **Auto-fail trigger:** <16 numbered sections detected

### Dimension 2: Persona Deferral Integrity
- 10: Section 2 contains the appropriate clause (Standard or CEO variant) VERBATIM
- 6-9: Clause present, 1-2 word-level modifications (acceptable but flagged)
- 0-5: Clause missing OR substantially modified OR wrong variant
- **Auto-fail trigger:** Wrong variant used OR clause missing entirely → score = 0

### Dimension 3: Tier-1 Research Citation
- 10: ≥4 Tier-1 URLs, ≥3 distinct domains (mckinsey/hbr/ibisworld/statista), all in Section 16, all referenced in body
- 8-9: ≥3 Tier-1 URLs, ≥2 distinct domains
- 6-7: ≥3 Tier-1 URLs but only 1 domain OR all in Section 16 but not in body
- 4-5: 2 Tier-1 URLs
- 0-3: <2 Tier-1 URLs
- **Auto-fail trigger:** manifest.min_tier1_citations set higher and doc has fewer → cap at 5

### Dimension 4: SOP Atomicity
- 10: ≥manifest.min_sops SOPs. Each has all 6 sub-fields. Steps atomic, executable, specific.
- 8-9: Min SOPs met, 90%+ steps atomic
- 6-7: Min SOPs met but 1-2 missing a sub-field OR 10-20% steps vague
- 4-5: Min SOPs met but multiple missing sub-fields
- 0-3: <Min SOPs OR most steps say "use your judgment"
- **Auto-fail trigger:** ANY step contains "use your judgment" / "as appropriate" / "based on context" → cap at 5

### Dimension 5: KPI Revenue Linkage
- 10: ≥1 Primary KPI explicitly uses revenue cascade tokens. ≥2 Primary KPIs have numeric targets.
- 8-9: Tokens present in ≥1 KPI. Numeric targets on most.
- 6-7: Tokens as text reference OR numeric targets but no token linkage
- 4-5: Tokens missing but KPIs have numeric targets
- 0-3: No tokens AND no numeric targets

### Dimension 6: Concrete Examples
- 10: Section 13 has ≥2 examples, each is LITERAL SAMPLE OUTPUT (actual text the role produces), 100-300 words each, with "Why this is good" reasoning
- 8-9: ≥2 examples, mostly concrete
- 6-7: 1-2 examples but 1 too short or descriptive
- 4-5: Examples are descriptions of what good looks like, not literal samples
- 0-3: No examples OR generic

### Dimension 7: Edge Case Rigor
- 10: ≥manifest.min_edge_cases edge cases. Each has Trigger + Action + Escalate To. Each is specific scenario.
- 8-9: Min met. All have 3 sub-fields.
- 6-7: Min met but 1 missing a sub-field
- 4-5: Below min by 1, OR generic phrasing
- 0-3: <half of min

### Dimension 8: Template Token Correctness
- 10: All required tokens from manifest present. No literal client data. Correct `{{NAME}}` format.
- 8-9: All required present, 1 minor formatting issue
- 6-7: 1 required token missing
- 4-5: 2-3 required missing OR 1 instance of literal client data
- 0-3: Multiple missing OR multiple instances of literal data
- **Auto-fail trigger:** "BlackCEO" / "Trevor" / "ZeroHumanCompany" appears as literal (not token) → cap at 3

### Dimension 9: Industry-Agnostic + Role-Specific
- 10: Uses `{{INDUSTRY_VERTICAL}}` token (industry-agnostic). Procedures specific to this role (could not be cut-and-pasted to another role).
- 8-9: Industry-agnostic. Role-specific in most places, 1-2 generic SOPs.
- 6-7: Industry-agnostic but role procedures could apply to any role of this seniority
- 4-5: Industry-locked (hard-codes "real estate"/"SaaS") OR role-generic
- 0-3: Both industry-locked AND role-generic

### Dimension 10: Micro-Specialist Extensibility (Section 19)
- 10: ≥3 named sub-specialists. Each has name + when-trigger + example task + duration. Spawn snippet present. Persona-inheritance paragraph. Promotion rule.
- 8-9: ≥3 sub-specialists. Spawn mechanism present. 1 sub-spec missing a sub-field.
- 6-7: ≥3 sub-specialists. Spawn mechanism present but minimal.
- 4-5: 1-2 sub-specialists OR spawn mechanism missing
- 0-3: Section 19 missing or empty

### Dimension 11: Ollama Compliance
- 10: Doc generated 100% via Ollama primary (writer + QC both used Ollama models, no fallback triggered)
- 8-9: Doc via Ollama writer; QC had 1 fallback to OpenRouter mid-evaluation
- 6-7: Writer had 1 OpenRouter fallback call but recovered to Ollama
- 4-5: Writer had multiple OpenRouter fallback calls (>20% of generation tokens via OpenRouter)
- 0-3: Writer ran majority via OpenRouter due to Ollama unavailability

## Total score → verdict (see also: orchestrator script's `decide_verdict()`)

| Total | Min Dim | Regen Cycle | Verdict |
|---:|---:|---:|---|
| ≥85 | ≥6.5 | any | PASS |
| ≥85 | 4-5 | any | ACCEPT_WITH_WEAKNESS_FLAG → moved to `_pending_rewrite/` (NOT main library per v2.9 hygiene rule) |
| 65-79 | ≥4 | any | ACCEPT_WITH_WEAKNESS_FLAG → `_pending_rewrite/` |
| <65 OR <4 | any | 0 or 1 | FORCE_REWRITE_WITH_STRICTER_PROMPT |
| <65 OR <4 | any | 2 (final) | PENDING_REWRITE → `_pending_rewrite/` (regen_exhausted: true) |

**v2.9 rule: ONLY PASS (≥85, no dim <6.5) ships to `templates/role-library/[dept]/[role].md`. Everything else goes to `_pending_rewrite/`.**
