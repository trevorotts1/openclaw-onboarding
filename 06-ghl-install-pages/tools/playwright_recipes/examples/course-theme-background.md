# Inactive course-theme Background Image

Compile `courses.configure_ui` with `background_image` to action
`native_course_theme_media`, `payload` equal to the full inputs. Validate through
`course_theme_media.validate_inputs`; run `configure(page, step)` under the
existing native runner's tenant guard, lease and write-intent journal. Bind
replay to `configuration_hash(inputs)`, exact inactive course/template editor and
`COURSE_THEME_MEDIA_SAVED_AND_REOPENED`. The source sets
`functional_verified:false`, `activation_performed:false`: native Python and
learner acceptance remain pending.

This separately captured native template control uses Layout > Background Image
> Upload Image > Upload File. It is distinct from product/lesson media API
attachment. The handler accepts an approved local PNG smaller than 10 MiB with
an explicit SHA256 and exact previous preview URL. It preflights the source,
makes a private immutable copy, selects that file through the native input and
checks the selected filename/size/MIME before clicking Upload. No file URL,
download, existing-browser file or source hash is invented.

After Upload, the dialog must close and that same Background Image preview must
expose a newly observed credential-free HTTPS URL. The handler preserves native
Transparency fill/handle style attributes verbatim without authoring a slider
value. It saves the inactive template, independently reopens the exact native
template and proves that observed URL persisted. Current active theme, captured
text/palette/fonts, Body inventory and supported custom-block content/media must
remain unchanged. A different/unreadable result stops for reconciliation; the
runner's retained uncertain journal prevents another upload.

This covers native Layout Background Image only. Header/Hero/Instructor and
custom-block image upload, other custom block types, arbitrary body content and
community branding require their own captured controls. Additional Body block
types outside Category/Custom cause a preflight refusal. Native guidance
recommends 1280x720; this script does not invent a hard dimension requirement.

Replace every example path/hash/identity/title/URL from approved inventory. The
example does not contain a real file or usable approval.
