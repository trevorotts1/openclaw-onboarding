# Inactive course Hero and Instructor PNG media

Use `course_section_media.validate_inputs`, `native_course_section_media`,
`configure(page, step)` and `validate_receipt(original_result, step)` under the
existing tenant guard, intent journal and lease. The template must be inactive.
The `theme_images` key requires all previous Hero/Instructor inspector and
rendered-preview URLs, plus unique authored `hero`/`instructor` PNG replacements.
Native placeholder URLs may differ between the inspector and rendered preview;
neither is inferred from the other. Every source is approved by SHA256 and all
sources are validated before the editor opens, then privately copied.

The captured Hero Appearance panel is the direct parent of the custom
`#show-hero-checkbox`, with native `h-full w-full text-gray-800` classes. Hero
must already be shown in Image mode. The active rendered image belongs to
`.welcome-hero-image[isediting=true]`. Show/overlay checkbox states, image/color
radios, its one color swatch and exact native slider style strings are read and
preserved. No visibility, mode, overlay or transparency is authored implicitly.

The Instructor inspector is `div.w-full.p-2:has(> button#ins-sync-data)`; Sync is
never clicked. The exact active `.instructor-card[data-active=true]` binds
`img#instructor-headshot`. A DIV duplicates this ID, so an unqualified ID
selector is insufficient. The instructor and headshot must already be shown.
All four text fields, visibility/headshot radios and five color swatches remain
unchanged. Upload Image and Offer poster are scoped to the exact inspector.

The known native Upload File dialog selects one approved PNG smaller than
10 MiB. A successful new preview must replace both previous URLs with the same
new credential-free HTTPS URL before Save. All other section controls, the
other image, full Body inventory/content/media and template/active-theme
settings remain protected. Save occurs once, followed by an independent native
reopen and complete comparison. Unexpected native dialogs, mismatched previews,
unreadable controls or uncertain upload/save stop without another upload.

The outcome binds exact course/template editor, configuration hash and each
section/source/new-preview hash. It retains `functional_verified:false` and
`activation_performed:false`; source tests do not establish native Python,
learner, publication or image-generation acceptance. Replace all example
identities, URLs, file and hash with approved inventoried inputs.
