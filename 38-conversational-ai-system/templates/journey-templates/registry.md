# Customer Journey Templates Library — Registry

This library defines what a "complete" customer journey looks like for
different business types. The Business-Logic Workflow Suggestions
feature (Step 9.29) reads from this library to identify gaps in the
operator's existing workflows.

## Available business-type templates

Each template lives in its own folder. Inside each folder, there is a
`journey.md` file defining the complete customer journey for that
business type, plus optional supporting files (sample workflow scaffolds,
recommended messaging tone, timing conventions).

| Business Type | Folder | Description |
|---|---|---|
| Coach | `coach/` | 1:1 or group coaching engagements |
| E-commerce | `e-commerce/` | Physical/digital product sales |
| SaaS | `saas/` | Software subscriptions |
| Service Provider | `service-provider/` | Done-for-you services |
| Course Creator | `course-creator/` | Online courses, masterclasses, cohorts |
| Real Estate | `real-estate/` | Buyer/seller agents |
| Consulting | `consulting/` | Strategic engagements, retainers |
| Wellness | `wellness/` | Health practitioners, fitness, mental health |

## How business type is determined

The agent infers business type from the Business Brain knowledge base
(`<MASTER_FILES_DIR>/KnowledgeBases/business/`) — specifically from the
company description, services offered, and how the operator describes
what they sell. If ambiguous, the agent asks operator: "What type of
business best describes you?" with the 8 options.

Operator can override the inferred type at any time.

## Custom templates

If none of the 8 default types fit, operator can request a custom
template. Agent walks the operator through defining their own customer
journey, then saves it as a new template type in this library.
