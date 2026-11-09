# Exact inactive-theme Custom Block image

Compile `courses.configure_ui` with `custom_block_image` to action
`native_course_block_media`, carrying the full inputs in `payload`.
Use `course_block_media.validate_inputs`, `configuration_hash` and
`configure(page, step)` under the existing native runner's lease, tenant guard
and write-intent journal. Bind receipt/replay to exact course/template/block ID,
hash and `COURSE_BLOCK_MEDIA_SAVED_AND_REOPENED`; keep
`functional_verified:false` and `activation_performed:false`.

The operation edits one existing native Custom Block UUID. Its complete ordered
Category/Custom Block inventory, previous image URL and approved local PNG/hash
must come from inventory. Other block types still require their own captures.
The exact selected `.custom-block[data-active=true]` preview UUID must own the
inspector. The inspector's Offer poster and that UUID's Image block preview must
agree before the captured Upload Image control is used.

This reuses the native Upload File dialog from the Background Image operation,
including its actual single-image input, accepted type inventory, selected
filename/size/MIME check and enabled Upload button. The PNG is smaller than
10 MiB and copied to a private immutable file before selection. Success requires
the dialog to close and the same UUID to expose a newly observed HTTPS image
URL. All block text, rich HTML, radio/button settings, sibling images/IDs/order
and captured template text/palette/fonts remain unchanged.

Native Save is followed by reopening the exact existing inactive template and
checking its observed image URL, selected UUID and all protected state. The
active theme cannot change. Uncertain writes retain the parent runner's journal
and require reconciliation rather than another upload. Source/synthetic checks
do not establish native Python or learner acceptance.

Replace every example path/hash/identity/title/URL from approved inventory.
The example does not prove the target has only the two shown blocks.
