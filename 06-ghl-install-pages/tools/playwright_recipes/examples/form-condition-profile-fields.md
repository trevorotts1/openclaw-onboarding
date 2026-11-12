# Typed condition fields

`field_bindings` identifies every relevant widget by its exact canvas label and
native type. Existing text, long-text, number, monetary, score, URL, time, Date and
Date & time profiles use their visible `query_key`. File upload, signature,
text-box list and multi-dropdown profiles use their `contact.`-prefixed
`unique_key`. Rating is queryless and is identified by its unique label and
typed canvas preview. Show/Hide targets can use any bound profile; the native
picker must offer the exact label at runtime.

Text and URL use text operators; number, monetary and score use numeric
operators; file upload, signature, text-box list and rating are limited
to empty/filled; time comparisons use `HH:MM` or an ordered inclusive pair; choice fields use their captured option operators. Consent sources `TnC1` and `TnC2` support `Is Checked` and `Is Not Checked` without a value. The
requested source and operator must appear uniquely in the native picker or the
operation stops without saving. This means schema acceptance does not assert
that every account or widget is offered by the platform. Date & time comparison
format and inclusive ranges are described in `form-condition-date-time.md`.
