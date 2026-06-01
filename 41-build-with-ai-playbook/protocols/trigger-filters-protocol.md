# Trigger Filters Protocol -- Skill 41

Sources:
- https://help.gohighlevel.com/support/solutions/articles/155000002288-getting-started-with-workflows
- https://help.gohighlevel.com/support/solutions/articles/155000003499-workflow-trigger-opportunity-created
- https://help.gohighlevel.com/support/solutions/articles/155000002477-workflow-trigger-contact-changed
- https://help.gohighlevel.com/support/solutions/articles/155000002673-workflow-trigger-contact-dnd

A trigger decides WHO enters the workflow. Filters on that trigger decide WHICH of those entries
actually qualify. Filters are optional in GHL but the agent must treat them as expected on almost
every build: a trigger with no filter fires for everyone, which causes runaway sends, wrong-audience
messages, and wasted spend. Setting filters correctly is a required part of generating any Build With
AI prompt, and the generated prompt must state the trigger filters explicitly.

## How trigger filters work

- After selecting a trigger, give it a clear, descriptive name that states its purpose. A well-named
  trigger is easier to manage across many workflows.
- Click Add filters to add a filter. Each filter is a field plus an operator plus a value.
- Click Add filters again to add more. Multiple filters on the same trigger generally combine with AND
  logic: all must be satisfied for the trigger to fire. Some triggers expose richer multi-select
  operators on specific fields (see Tag below), and some triggers, such as Contact Changed, are
  designed to watch several change types at once.
- The available filter fields are SPECIFIC TO EACH TRIGGER. The agent must use the filter set that the
  chosen trigger actually exposes, never a generic set. Examples:
  - Opportunity Created / Pipeline Stage Changed: Pipeline (In Pipeline), Stage, Assigned To, Lead
    Value, Tag.
  - Contact DND: DND Status (enabled/disabled or Specific Channel), Channel, Direction (inbound/outbound),
    Tag. The Channel filter only appears after choosing Specific Channel in DND Status.
  - Contact Changed: which field changed (tag added, custom field updated, DND changed); multiple
    filters can track several change types simultaneously.
  - Subscription: Global Product, Status (active, failed, trial, expired).
  - Appointment triggers: Calendar, Appointment Type/Status.

## Tag filters and multi-select operators

Tag filters support multi-select operators: Equals to, Not equals to, Any of, None of. The agent uses
these to express include/exclude logic precisely, and can add multiple Tag filters for advanced rules
(for example include one tag while excluding another). Prefer "Any of" for an OR-style tag set and
"None of" for exclusions, rather than stacking many separate filters.

## Rules the agent must follow when generating a trigger

1. Always name the trigger after its purpose, not the default.
2. Always propose filters that scope the trigger to the intended audience. If the operator truly wants
   everyone, say so explicitly in the prompt rather than leaving filters blank by omission. GHL itself
   surfaces a no-filters warning on triggers such as Contact Tag, confirming that an unfiltered trigger
   fires for every add or remove across all contacts; treat that warning as a stop sign unless all
   contacts is the explicit, stated intent.
3. Use the trigger's own filter fields, confirmed against the catalog. Do not invent a filter the
   trigger does not expose; if unsure, report the honest gap and offer the manual path.
4. For tag scoping, use Any of / None of instead of many stacked equals filters.
5. Guard against re-firing. Because a change-based trigger can fire repeatedly, pair it with one or
   more of: a qualifying filter, an early If/Else that checks whether the action already ran (for
   example "does the contact already have ZHC-welcome-sent?"), or a Wait/delay. To act on a removed tag, use the Contact Tag trigger with the
   Removed filter; the Contact Tag trigger fires on both add and remove, and with no filter it fires for
   both. The Contact Changed trigger watches additions and updates to the specific fields you select.
6. State every trigger filter explicitly in the generated Build With AI prompt (field, operator,
   value), so the builder and the operator can see exactly who qualifies.

## Verification (carried into the post-build checklist)

- The trigger is named after its purpose.
- The intended filters exist, with the correct field, operator, and value.
- Tag include/exclude logic uses Any of / None of as intended.
- Multiple filters combine the way the intent requires (AND across filters).
- A re-fire guard is present where the trigger can fire repeatedly.
