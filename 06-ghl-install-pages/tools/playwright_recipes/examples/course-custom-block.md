# Inactive course-theme Custom Blocks

`courses.configure_ui` can compile to the dedicated `native_course_blocks`
action with `payload` equal to the full inputs shown in the JSON example.
Validate using `course_blocks.validate_inputs`; execute with
`course_blocks.configure(page, step)` under the existing runner's tenant guard,
write-intent journal and lease. Bind replay to `configuration_hash(inputs)`,
exact inactive course/template editor, and
`COURSE_BLOCKS_SAVED_AND_REOPENED`. Keep `functional_verified:false` and
`activation_performed:false`; source/synthetic verification does not prove a
native Python job or learner behavior.

The native Body sidebar inventory is an exact ordered list of `.sortable-item`
IDs/types. The current supported list contains one `categoryBlock` of type
`Category Block` and UUID entries of type `Custom Block`, `Text Block` or
`Image Block`. Text/Image siblings are independently read and preserved;
their authoring has separate dedicated actions. Video Block types remain
capture-pending and cause refusal before authoring. Inventories must come from the native course/template,
not an inferred name or copied example.

`custom_blocks.append` contains fully authored plain text, button URL and radio
settings. The handler clicks the captured Add Block > Custom Block controls,
reads the generated native UUID, proves all sibling IDs/type/order are preserved,
then edits that UUID. It never invents a native ID or repeatedly adds a block to
recover an uncertain Save.

`custom_blocks.updates` contains exact existing native IDs, all seven previous
values in `expected`, the explicit edited subset in `changes`, and
`plain_text_content:true`. That acknowledgement permits authored plain text to
replace rich Content when Content is changed. Unrequested rich HTML, images and
all sibling custom blocks are preserved. Every target is checked before the
first edit. The inspector is compared with its UUID-bound preview, and the exact
course inventory is independently reopened after Save to check all blocks and
protected template text/palette/fonts. The active theme must stay unchanged.

Supported fields: `heading`, `content`, `button_text`, `button_url`,
`button_visibility` (`show`/`hide`), `button_type` (`solid`/`link`), and
`button_alignment` (`left`/`center`/`right`). New button destinations must be
credential-free HTTPS; empty URL is explicit. Native limits are Heading 2500,
Button Text 300 and URL 1000 characters. The local plain Content limit is 50,000.
Media upload, block deletion, activation and publication are outside this action.

This example contains placeholder IDs/title and an example URL. Replace them
from approved inputs before execution. The default inventory is not a claim
that the target has no other blocks.
