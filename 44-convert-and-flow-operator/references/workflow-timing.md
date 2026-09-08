# Timing intelligence: decide what the clock is measured from

Read during PLAN MODE for any time-based workflow, including matched templates,
full-funnel handoffs, and edits to an existing schedule. Apply the same reasoning
when building by API or through the managed browser. The agent interprets intent;
the helper below checks the resulting contract. It is not a natural-language parser.

## Decide before choosing nodes

| Client intent | Clock | Build decision |
|---|---|---|
| Four days after registration; seven days after registration | That registration instance's timestamp | Set event start time from the registration source, then Wait until +4 days and +7 days from that SAME start |
| One day before the webinar | The scheduled webinar occurrence | Set event start time from that occurrence, then Wait until -1 day |
| Two hours after the previous message | Reaching the preceding step | Ordinary duration Wait; no event-start node |
| Four days later, with no clear referent | Unresolved | Use the surrounding approved brief; if still ambiguous ask what starts the clock |
| Seven days after purchase/booking/renewal | The specified transaction/appointment/renewal | Resolve that exact occurrence, then use an event anchor |

Do this automatically when relevant; do not ask the owner whether the technical
Set event start time node should be added. Preserve approved business rules and
existing publish/re-entry authorization. Do not add an event-start node to every
workflow. A template is a starting point, not evidence its timing is correct.

Registration time is NOT contact creation time, workflow build time, handoff `ts`,
re-entry time, or webinar start time. An existing contact can register today.
Resolve the actual trigger/form and the date field/trigger value in THIS location.
If the trigger does not expose a durable registration timestamp, arrange to capture
it at registration into the correctly scoped source BEFORE dependent Waits run.
Do not invent merge tokens or use a shared hardcoded timestamp for all contacts.
A date-only field is insufficient when the brief promises elapsed hours or a precise
time: verify the field's precision and the platform's timezone interpretation.

## Produce and execute the outline

1. Identify each timing instruction's event reference or relative-delay basis.
   Inspect existing fields, trigger filters and the approved brief before asking
   for missing business information. An unresolved source is not permission to guess.
2. For each event reference record the verified source, IANA timezone, late-entry
   policy (`skip`, `continue`, or `exit`) and registration/re-entry policy (`once`
   or `separate_registration`). Honor the existing business decision. For multiple
   simultaneous registrations, use a separate instance/occurrence source; never
   overwrite a contact field still read by an earlier active sequence. If the chosen
   mechanism cannot isolate registrations, resolve that before enabling re-entry.
3. Write `timing` into each workflow plan as shown below. Run the helper for EACH
   execution path. Its nodes are a semantic UI outline, **not GHL API payloads**.
   Interleave the approved messages/actions at the corresponding Wait IDs.
4. For event timing, automatically place **Set event start time** before the first
   dependent Wait on EVERY reachable branch. Configure its source, then use the
   native event-relative Wait mode with the signed offset (before/after). Reuse the
   start for later waits on the same event; reset it when a path changes to a different
   event. If paths rejoin with different active starts, explicitly set the intended
   start again before their next event Wait. Ordinary delays do not reset the start.
5. Use the available verified execution route. The current internal API builder
   only verifies duration Wait payloads; it rejects an event timing contract before
   creating anything. Do not remove the contract to bypass that refusal. Continue
   with the Skill 6 managed browser gateway, observing the actual UI and configuring
   the full native sequence. The `ghl_workflow_builder.py` single-action helper is
   NOT a multi-step builder; do not use its saved-ID result as completion evidence.
   Follow the managed browser instructions and observed controls; do not invent API
   enums, merge tokens or selectors. If actual access/configuration is unavailable,
   report that specific unfinished dependency and retain the outline for resumption.
6. Read back/export the saved draft and compare every start source and Wait mode,
   offset, branch placement, timezone and late-entry policy with the outline. A
   screenshot of a node label alone proves neither configuration nor execution.
   Pass WF-9/16/17 before reporting the workflow complete or publishing it.

Native GHL now also offers a single Wait that directly reads a custom date field.
Our default for event-based workflows is the explicit **Set event start time**
sequence requested by the owner. If the client's UI only offers the direct-date
method, use it only with verified equivalent source/offset behavior and record the
actual method. Do not add a decorative event-start node that the waits never use.

## Machine-readable timing contract

```json
{
  "requirements": [
    {"id": "day4", "kind": "event", "anchor": "registration", "offset": 4, "unit": "days"},
    {"id": "day7", "kind": "event", "anchor": "registration", "offset": 7, "unit": "days"}
  ],
  "anchors": {
    "registration": {
      "source": "REPLACE with verified registration timestamp field/trigger binding",
      "timezone": "America/New_York",
      "past_due": "skip",
      "reentry": "once"
    }
  }
}
```

The policies above are examples, not defaults. Offsets are numeric: negative means
before, positive means after. Units: minutes, hours, days, weeks. A delay requirement
uses `kind: "delay"`, no anchor, and a nonnegative offset. IDs match intended Wait
IDs; for API duration plans they must match actual template IDs. Preserve this
object under the workflow's `timing` key or the Skill 6 task's `timing` key. The funnel
handoff carries it with `location_id` and the original `timing_brief`; Skill 44 must
review the brief even when the contract is absent and derive the timing if needed.

Run from the skill directory (standard Python 3.9+, no network):

```bash
python3 tools/engine/cli_anything/gohighlevel/utils/workflow_timing.py timing.json
```

## QC scenarios

- Registration on September 8: day 4 September 12, day 7 September 15, NOT day 11.
- Two contacts registering on different dates get different schedules; no shared clock.
- An existing contact registering today uses today's registration, not its creation date.
- A webinar reminder uses the selected webinar occurrence, not registration time.
- A two-hour delay after a previous message does not add an event-start action.
- Missing source, timezone or late-entry policy is resolved before building.
- Pause/resume and duplicate enrollment do not silently reset the original start.
- Branches, late enrollment, send windows and daylight-saving changes respect the
  chosen calendar-day versus elapsed-time behavior. Document any send-window shift;
  do not claim an exact send time when a window intentionally postpones delivery.

The offline helper tests verify outline construction and refusal behavior. Real
schedule execution still requires a controlled test registration in the target
location; do not send to real contacts merely to test this repository update.

## Sources checked September 8, 2026

- [HighLevel: Set Event Start Date](https://help.gohighlevel.com/support/solutions/articles/48001202723-workflow-action-set-event-start-date)
- [HighLevel: Wait action](https://help.gohighlevel.com/support/solutions/articles/155000002470-action-wait)
- [HighLevel: Wait action revamp](https://ideas.gohighlevel.com/changelog/wait-action-major-revamp)
