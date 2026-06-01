# GHL Conditions and If/Else Reference -- Skill 41

Primary source: https://help.gohighlevel.com/support/solutions/articles/155000002471-workflow-action-if-else
Appointment filters: https://help.gohighlevel.com/support/solutions/articles/155000004050-if-else-workflow-action-appointment-filter-options

The If/Else action is the most important filtering tool in GHL. It is how one workflow serves many
kinds of contacts instead of duplicating workflows. The agent must treat If/Else design as a
first-class part of every build, not an afterthought.

## What If/Else does

If/Else evaluates contact-specific data at the moment a contact reaches the step and routes that
contact down the matching branch. Each branch is a separate path with its own actions. This is
real-time evaluation: it reads the contact's current data, tags, appointment, pipeline, or a live
dynamic value, then decides the path. Because it reads live data, placing a Wait step before an
If/Else (wait for reply, wait for booking, or a timeout) is the standard pattern so the condition is
checked at the right moment.

## How to build it (the steps the agent must follow)

1. Add the action: in the workflow, click + and select If / Else.
2. Choose a logic setup method:
   - Build My Own: define conditions by hand. This is the default the agent should use for full control.
   - Scenario Recipe: one of GHL's prebuilt condition templates (about 10 recipe types) for common
     cases. Use only if a recipe matches the need exactly; otherwise use Build My Own.
3. Name the action as a QUESTION. Because the action is conditional, naming it as the question it
   answers makes the workflow readable, for example "Did the customer reschedule?" or "Has the contact
   opened the email?" The agent must always name If/Else actions and branches this way.
4. Configure the first branch with one or more condition rows.
   - Add Segment adds another condition row.
   - AND / OR controls how rows in the branch are grouped. AND requires all rows true; OR requires any
     row true. Group carefully: mixing AND and OR changes the result.
5. Add additional branches with Add Branch. You can create as many branches as the logic needs, each
   with its own condition group and its own downstream actions. Branches are evaluated top to bottom;
   the first branch whose conditions are met wins.
6. Configure the None (Else) branch. GHL auto-creates a None branch for contacts that match no other
   branch. It cannot hold conditions and cannot be deleted; it can only be renamed. Always put a
   sensible fallback under None (a default message, a tag, or an internal notification) so contacts
   that fall through are never silently dropped.

## Condition types (left-hand side)

- Contact details: first name, last name, email, phone, address, date fields.
- Tags: has tag, does not have tag. The cleanest, most reliable branching signal.
- Custom fields: any standard or custom field value.
- Appointments: status, start date, end date, rescheduled flag. Only available when the workflow uses
  an appointment trigger (Customer Booked Appointment or Appointment Status). Only ONE appointment
  filter is allowed per If/Else condition; for multiple appointment checks, use multiple branches or
  multiple If/Else actions.
- Opportunities/Pipelines: stage, status, lead value.
- Workflow/Campaign status: in workflow, not in workflow, completed.
- Form/Survey answers: specific submitted values.
- Events with a preceding Wait: email opened, link clicked, replied (evaluate after a Wait step).

## Operators

is, is not, contains, does not contain, starts with, greater than, less than, is empty, is not empty.
Numeric and date comparisons use greater/less than; text matching uses is, contains, and starts with.
Time comparison operators are also available for date/time logic, comparing the current day of week, day of
month, month, year, or hour against a value, which is useful for business-hours and scheduling branches.

## Dynamic custom values (compare against live values)

The right-hand side of a condition can be a Dynamic Custom Value instead of a hard-typed value, so the
condition compares against a live value from an earlier step or a stored field. Reference syntax is
{{custom_values.<name>}}. Supported field types include numeric, date, monetary, and select. For
Select or Dropdown fields, compare against the stored option ID, not the display name. This avoids hard-coding and removes
duplicate logic. Reminder: the Workflow AI Builder inserts the placeholder syntax but does not create
the custom value, so the dependency-first step must create it first.

## Filtering patterns the agent should reach for (use cases)

- Has-email vs no-email: contacts with an email go down an email-follow-up branch; contacts without an
  email go down a call-or-SMS branch.
- Geography: branch by city, state, or postal code to send region-specific offers or route to a local rep.
- Engagement: after a Wait, branch on email opened vs not opened to send a different next touch.
- Appointment outcome: branch on no-show vs showed to re-engage no-shows and thank attendees.
- Pipeline stage or tag: branch by stage or by a ZHC- tag to run the right sequence for each segment.
- Stop on conversion: branch on "booked an appointment" or "purchased" to remove the contact from
  further nurture, preventing over-messaging.

## Verification of If/Else (the agent must check)

- Every branch, including None, has downstream actions or an intentional dead end.
- AND vs OR grouping matches the stated intent.
- Branch order is correct, since the first matching branch wins.
- Any dynamic value referenced exists (created in the dependency-first step).
- The action and branches are named as questions and outcomes for readability.
