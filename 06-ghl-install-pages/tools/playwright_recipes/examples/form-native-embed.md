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
and Popover require Left/Right and authored button text. The optional button appearance object below authors captured button properties;
color and icon identity are preserved.

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


## Button corners, font, type and size

`integration.appearance` has nonempty `expected` and `changes` objects with the
same property keys. The separate example `form-embed-button-appearance.json`
uses the exact captured defaults; replace them with actual current inventory.

Supported properties are `corner_radii` (all four integer `tl`, `tr`, `bl`, `br`
values), integer `font_size`, boolean `linked`, `button_type` (`text`, `textIcon`,
`icon`) and `button_size` (`small`, `medium`, `large`). The type choices map to
native Text, Icon + text and Icon only. The captured Chat icon must remain
`buttonIcon: chat`; no other icon is selected. Standard embeds have no button
appearance controls, and layout changes require a separate inventoried job.

The script bounds radii to 0–1000 and font size to 1–256 as conservative script
limits. The captured native inputs expose no min/max; these are not claims of
platform limits. Different per-corner values require `linked: false`. The
writer temporarily detaches corner linking while filling explicit values, then
restores the desired local link state; linked corners must all be equal.

A native export is read before the appearance edits to protect every unrequested
layout property, including button color and icon. The two final native exports
must contain the exact authored `data-layout.cornerRadius`, `fontSize`,
`buttonType` and `buttonSize`. Button corner metadata is distinct from the
iframe's unchanged `style` border radius. The local link affordance is read back
in the editor; it is not claimed as a serialized embed property.

The receipt retains validated `appearance_settings` on initial execution and
replay. No global color-palette Add/Save operation is used. The same pending
installation, publication and behavior boundaries remain in force.


## Existing palette color and captured icon catalog

`appearance` also supports `button_color` and `button_icon`; see
`form-embed-button-color-icon.json`. Color accepts opaque six-digit HEX or native
RGBA8 ending in `FF`, in either case. The plan/receipt normalizes this to lowercase
RGB6 while retaining the exact native exported code bytes (including native
RGBA8 spelling). The selected color must identify exactly one existing swatch in
the captured Default Colors palette. An absent or ambiguous swatch returns
`NEEDS_PALETTE_COLOR`. This operation never creates, edits or saves a palette entry.
Transparent colors and arbitrary new palette values are outside this captured contract.

Icons use exact captured material codes such as `chat`, `mail`, `email` and
`arrow_forward`, mapped to their native accessible labels and selected through
Icon search. Unknown codes refuse. Icon controls are visible only for `textIcon`
or `icon` button types. A Text-to-icon job must explicitly author that type change.
The prior hidden icon is bound to the before-export metadata before any edits;
it is never inferred from an absent icon selector. Unrequested color/icon/layout
properties remain protected. Existing five-property appearance jobs and receipts
keep their original contract and hashes.

Native capture confirmed color `#188BF6FF` and icon `mail` in the generated code;
a fresh tab restored default local options. These are per-export artifacts,
not saved form settings. The writer reads the code twice, retains exact bytes and
revalidates them during receipt replay. It performs no form Save, palette Save,
installation, publication or functional submission.
