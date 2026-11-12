# Date & time conditions

Bind the existing Date or Date & time widget by its exact label, `DATE` or `DATE_TIME` type and
native Query Key in the complete `field_bindings` inventory. The captured
source supports `Is Empty`, `Is Filled`, `Is Equal To`, `Is Not Equal To`,
`Before`, `After` and `Between`. Date comparison values use `YYYY-MM-DD`; Date & time comparison values use
the local calendar and clock text `YYYY-MM-DD HH:MM` without timezone conversion. The writer
selects the date in the native calendar and fills the native time input, then
checks both values and the resulting condition summary. Calendar navigation is
bounded to 240 months. For `Between`, provide two ordered date/time strings as the value array. Both
native endpoint inclusion checkboxes must remain checked.
