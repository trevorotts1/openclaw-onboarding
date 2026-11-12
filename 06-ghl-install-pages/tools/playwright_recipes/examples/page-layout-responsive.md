# Native page layout and responsive width

Use exact IDs observed in the current funnel builder. Each object below is an
independent recipe input and also needs the same `location_id`, `location_name`,
and `start_url` as the target account. A row operation saves and independently
reopens the editor before returning the new row and column IDs.

Insert into an empty section on a page with multiple sections:

```json
{"layout":{"section_id":"section-example","columns":2}}
```

For an occupied section, insert immediately after a specific existing row:

```json
{"layout":{"section_id":"section-example","after_row_id":"row-existing","columns":3}}
```

Pass these to `pages.layout`; use its returned `row_id` and `column_ids` for
later placements. The row presets support one through six columns.

Set a captured native row width with `pages.responsive`:

```json
{"responsive":{"profile":"funnel_row_width_v1","section_id":"section-example","row_id":"row-existing","device":"tablet","width_percent":85}}
```

This profile controls the native **Width** input for desktop or tablet,
integer 30–100 percent. It independently reopens the saved editor and checks
both the requested value and the other device's retained value. The observed
mobile editor does not expose the row width control. Layout Containers were
not exposed by the observed tenant; do not replace native checkout elements or
simulate those controls with custom code.
