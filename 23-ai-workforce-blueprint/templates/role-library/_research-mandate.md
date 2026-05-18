# Research Mandate — Tier 1/2/3/4 Sources

Every writer sub-agent MUST cite from the following tiers. The QC rubric Dimension 3 enforces this — a doc with fewer than the required Tier-1 citations cannot pass.

## Tier 1 — Authoritative Strategic Sources (REQUIRED, every doc, ≥3 distinct URLs)

| Source | URL pattern | Best for |
|---|---|---|
| **McKinsey Global Institute** | `mckinsey.com/mgi/our-research/...` | Productivity benchmarks, market sizing, role strategic context |
| **McKinsey & Company** | `mckinsey.com/industries/.../our-insights/...` | Industry-specific best practices for this role |
| **Harvard Business Review** | `hbr.org/...` | Management frameworks, role design, KPI methodology |
| **IBISWorld** | `ibisworld.com/.../industry/...` | Industry data, role staffing benchmarks, market trends |
| **Statista** | `statista.com/statistics/...` | Quantitative benchmarks for KPI targets |

### Tier-1 enforcement rules

- Every doc cites ≥3 Tier-1 URLs (or ≥`manifest.min_tier1_citations` if higher)
- URLs appear in Section 16 (Research Sources)
- AT LEAST 2 Tier-1 sources are referenced inline in the body (Section 7 KPIs, Section 8 Tools, Section 9 SOPs, or Section 17 Edge Cases)
- If McKinsey returns nothing for this niche role: IBISWorld + Statista count as 2 toward minimum

## Tier 2 — Live Web Research (REQUIRED, 5 standard Perplexity Sonar Pro queries per role)

Writer MUST run these queries before writing:

1. `"{role_title} responsibilities in {current_year}"`
2. `"KPIs for {role_title}"`
3. `"best tools for {role_title}"`
4. `"common mistakes {role_title} make"`
5. `"how does a {role_title} hand off work to the next role in the workflow"`

Plus 4 Tier-1 site-restricted queries:

6. `"site:mckinsey.com {role_title}"`
7. `"site:hbr.org {role_title}"`
8. `"site:ibisworld.com {role.dept_slug}"`
9. `"site:statista.com {role.dept_slug}"`

Plus any role-specific extras from manifest `research_extras` field.

## Tier 3 — Trade/Vendor Sources (REQUIRED for role-relevant content)

| Type | Examples |
|---|---|
| Trade publications | MarTech.org, AdAge, MailChimp/SendGrid blogs for Email Deliverability, TubeFilter for Video |
| Official vendor docs | GoHighLevel docs, Google Postmaster Tools docs, Meta Business Suite, OpenAI Cookbook |
| Academic/peer-reviewed | MIT Sloan Management Review for strategy roles |

## Tier 4 — Competitive Context (REQUIRED)

| Source | Used for |
|---|---|
| LinkedIn | How top-tier companies structure this role and the KPIs they publicize |
| Crunchbase | Team composition / role count benchmarks at successful companies |
| Glassdoor | Typical role responsibilities and skill expectations |

## Citation Format in Section 16

Every doc's Section 16 organizes sources by Tier:

```markdown
## 16. Research Sources

### Tier 1 — Authoritative Strategic
- [McKinsey, "Role of X in 2026"](https://mckinsey.com/...)
- [HBR, "Y Framework"](https://hbr.org/...)
- [IBISWorld, "{industry} report"](https://ibisworld.com/...)

### Tier 2 — Trade & Vendor
- [GoHighLevel Email Deliverability Guide](https://help.gohighlevel.com/...)

### Tier 3 — Competitive Context
- [Indeed Job Posting: {role} at Fortune 500](https://indeed.com/...)
```

## What QC enforces

Dimension 3 (Tier-1 Research Citation) auto-fail triggers:
- <3 Tier-1 URLs cited → cap dimension score at 5 (likely doc fail)
- <`manifest.min_tier1_citations` for flagship roles → cap at 5
- Tier-1 URLs in Section 16 but not referenced in body → cap at 7
