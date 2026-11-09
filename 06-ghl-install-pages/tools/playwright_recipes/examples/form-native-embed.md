# Native form Integrate embed export

Use `forms.configure` with one separate `integration` job. Replace every example
identity, old value and provider origin with actual native inventory. An empty
`expected`/`changes` pair exports the existing configuration without changing it.
The handler binds the form title, exact editor/form ID and inventoried HTTPS
embed/loader origins before retaining generated native code.

Supported captured layouts are Sidebar, Popover, Popup and Standard. Layout
changes require all five General keys (`layout`, `position`, `width`, `height`,
`button_label`) in both the expected and changes objects. Popup has no position
(`null`); Standard has neither position nor button label (both `null`). Sidebar
and Popover require Left/Right and authored button text. Other appearance
settings are preserved, not authored by this handler.

Nondefault width authoring is proven in the native export for Popup and Standard
through `data-layout.formWidth`. Explicit height authoring is supported for
Popup through `data-modal-height`. The Standard builder displays a height input
but its generated code ignores explicit height; this handler refuses that
request. Nondefault Sidebar/Popover width exports need a separate capture.
Intrinsic `data-height` is derived by the platform and is not substituted for an
authored modal height.

Advanced choices use the exact native values: activation `activateOnVisit` or
`alwaysActivated`; trigger `showOnScrolling`, `showAfter` or `alwaysShow`;
deactivation `deactivateAfter`, `leadCollected` or `neverDeactivate`.
The corresponding positive integer fields are `activation_visits`,
`scroll_percentage` (1–100), `delay_seconds` and `deactivation_views`. A numeric
edit must select its corresponding active choice in the complete desired state.
`respect_cookie_consent` takes an explicit boolean. Auto-detect is the only
captured provider; its native selector disappears when the consent switch is off.

The code comes from the native **Embed code → Embed in webpage** displayed
CodeMirror lines, without the clipboard. It is read twice through separate
code-dialog openings, validated as exactly one native iframe and loader script,
and hashed without rewriting. The receipt retains exact native `embed_code`,
its SHA256, form ID, configuration hash and complete `export_settings`.
Replay must revalidate those bindings through `validate_receipt`.

Integrate options configure a per-embed artifact. This operation does not click
form Save, claim that integration settings persist, install code on a website,
publish a form/page or send a submission. Its receipt keeps
`settings_persisted`, `installation_verified`, `behavior_verified` and
`submission_verified` false. Native functional execution remains separate.
