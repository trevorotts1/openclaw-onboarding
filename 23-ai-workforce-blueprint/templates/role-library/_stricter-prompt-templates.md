# Stricter-Prompt Templates (Per Dimension)

Used by QC sub-agents when issuing FORCE_REWRITE_WITH_STRICTER_PROMPT. Append the matching dimension-specific block(s) to the writer's standard prompt. Only include overrides for dimensions that failed (scored <6.5).

## Dimension 1 stricter prompt

```
PRIOR DRAFT FAILED Dimension 1 (Structural Completeness).
On this rewrite:
- Verify all 19 sections are present in correct order BEFORE submitting
- Section headers MUST match `^## \d+\.` regex
- No "TODO", no "to be determined", no empty placeholders
- Self-check: run `grep -c "^## [0-9]" yourfile.md` — must return 19
```

## Dimension 2 stricter prompt

```
PRIOR DRAFT FAILED Dimension 2 (Persona Deferral Integrity).
On this rewrite:
- Section 2 MUST contain the verbatim {role.is_ceo ? "CEO" : "Standard"} variant deferral clause
- Copy the clause from `_token-reference.md` "Canonical Deferral Clauses" section
- Do NOT modify a single word
```

## Dimension 3 stricter prompt

```
PRIOR DRAFT FAILED Dimension 3 (Tier-1 Research Citation, need {min_tier1_citations}+ URLs).
On this rewrite:
- Run these Perplexity queries explicitly:
    "site:mckinsey.com {role_title}"
    "site:hbr.org {role_title}"
    "site:ibisworld.com {role.dept_slug}"
    "site:statista.com {role.dept_slug}"
- Section 16 MUST list ≥{min_tier1_citations} URLs across these domains
- Reference ≥2 of these in body (Section 7 OR Section 8 OR Section 17)
- If McKinsey thin for this niche role, try fallback queries:
    "site:mckinsey.com industry insights {role.dept_slug}"
    "site:mckinsey.com our people {role_title}"
- Final option: IBISWorld + Statista count as 2 toward minimum
```

## Dimension 4 stricter prompt

```
PRIOR DRAFT FAILED Dimension 4 (SOP Atomicity).
On this rewrite:
- Section 9 MUST contain ≥{min_sops} SOPs
- Each SOP MUST have ALL 6 sub-fields:
    **When to run:** {trigger}
    **Frequency:** {daily/weekly/on-demand}
    **Inputs:** {what you need to start}
    **Steps:** 1. ... 2. ... 3. ...
    **Outputs:** {what you produce}
    **Hand to:** {next role or "complete"}
    **Failure mode:** {what to do if step breaks; who to escalate to}
- Each step MUST be ATOMIC. Forbidden phrases:
    "use your judgment", "as appropriate", "based on context",
    "review and decide", "consider whether"
- UNACCEPTABLE example: "Review the customer's profile and adjust the strategy."
- ACCEPTABLE example: "Open the customer record in GoHighLevel. Read the
  'Last Contact' field. If date >30 days ago, set Status=Stale and add tag
  'reactivation-needed'. If <30 days, skip to step 3."
```

## Dimension 5 stricter prompt

```
PRIOR DRAFT FAILED Dimension 5 (KPI Revenue Linkage).
On this rewrite:
- Section 7 MUST have ≥1 Primary KPI using revenue cascade tokens:
  {{YEARLY_GOAL}}, {{QUARTERLY_TARGET}}, {{MONTHLY_TARGET}}, {{WEEKLY_TARGET}}, {{DAILY_TARGET}}
- ≥2 Primary KPIs have numeric targets (not "track X" or "monitor Y")
- Example: "Target: ≥95% inbox placement rate, contributing
  {{ROLE_REV_PERCENT}}% of {{MONTHLY_TARGET}} in monthly revenue"
```

## Dimension 6 stricter prompt

```
PRIOR DRAFT FAILED Dimension 6 (Concrete Examples).
On this rewrite:
- Section 13 MUST have ≥2 examples
- Each is LITERAL SAMPLE OUTPUT — the actual text/work the role would produce
- NOT descriptions like "A good email would be persuasive and personalized"
- INSTEAD: write the actual email body the role would send, 100-300 words
- For each example: include "Why this is good" with 3 specific reasons
```

## Dimension 7 stricter prompt

```
PRIOR DRAFT FAILED Dimension 7 (Edge Case Rigor, need {min_edge_cases}+).
On this rewrite:
- Section 17 MUST have ≥{min_edge_cases} edge cases
- Each MUST have: **Trigger:** / **Action:** / **Escalate to:**
- Each MUST be SPECIFIC. Forbidden: "if something goes wrong"
- Brainstorm prompts: What breaks when traffic doubles? When a tool API fails?
  When the owner is unavailable? When upstream data is bad? When budget is cut
  by 50%? When a competitor releases the same feature? When a key vendor goes down?
```

## Dimension 8 stricter prompt

```
PRIOR DRAFT FAILED Dimension 8 (Template Token Correctness).
On this rewrite:
- ALL required tokens MUST appear: {manifest.required_template_tokens}
- NO literal client data anywhere ("Trevor", "BlackCEO", "ZeroHumanCompany")
- Token format: `{{TOKEN_NAME}}` (double braces, uppercase, underscores)
- If you need to reference the company, use `{{COMPANY_NAME}}` not "BlackCEO"
- See `_token-reference.md` for the canonical token list
```

## Dimension 9 stricter prompt

```
PRIOR DRAFT FAILED Dimension 9 (Industry-Agnostic + Role-Specific).
On this rewrite:
- DO NOT hard-code any single industry. Use `{{INDUSTRY_VERTICAL}}` token
- DO write role-specific procedures that could NOT apply to a different role
- A Director of Marketing's SOPs should NOT also apply to a Director of Sales
- A Brand Positioning Specialist's procedures should NOT be cut-and-pasteable
  to any other role
```

## Dimension 10 stricter prompt

```
PRIOR DRAFT FAILED Dimension 10 (Section 19 Micro-Specialist Extensibility).
On this rewrite:
- Section 19 MUST list ≥3 named sub-specialists
- Each MUST have:
    | Sub-specialist | When to spawn | Example task | Typical duration |
    | ... | trigger | concrete task | minutes/hours |
- Include the Python spawn snippet (from `_section-19-template.md`)
- Include the persona-inheritance paragraph
- Include the >10-spawns-in-30-days promotion rule
```

## Dimension 11 stricter prompt

```
PRIOR DRAFT FAILED Dimension 11 (Ollama Compliance).
This dimension is decided by the orchestrator based on call logs, NOT by your output.
- Indicates the prior generation used >20% OpenRouter fallback (Ollama unavailable)
- On retry: orchestrator will check Ollama health first
- If still unavailable, doc may be marked PENDING_REWRITE for next library version
```

## Multi-dimension stricter prompt (when 3+ dims fail)

Prepend to writer's prompt:

```
PRIOR DRAFT FAILED MULTIPLE DIMENSIONS: {failed_dims}.
This is a deep rewrite. Re-read the universal template, the rubric, and the
specific overrides below. EACH dimension override must be addressed.
```

Then concatenate each individual dim's stricter prompt.
