# Inactive course Text Blocks

The captured Body > Add Block > Text Block path supports authored plain Content
up to 2500 characters. Use `course_text_blocks.validate_inputs`, the
`native_course_text_blocks` step, and `configure(page, step)` under the runner's
tenant guard, intent journal and lease. Bind both fresh and replay receipts with
`validate_receipt(original_result, step)` before any generic filtering.

Supply the complete ordered sidebar UUID/type inventory, one `categoryBlock`
and captured Custom/Text/Image siblings only. Other block types currently refuse.
Each `append` is `{ "content": "Authored text" }`. Each existing `updates`
entry supplies `id`, `expected_content`, `content` and
`plain_text_content: true`; this explicitly permits replacing rich Content
with the authored plain text. An unchanged content request preserves its
existing rich markup without refilling it.

The native Text preview has no UUID. The handler maps every sidebar entry to
one direct preview wrapper under `#content-container > div.col-span-9`, checks
all types and their complete order, then clicks the exact sidebar UUID and
requires the uniquely active preview to occupy that same position. Identical
content in two Text Blocks does not establish identity. The Content editor
must agree with that order-bound rich-text preview. Colors are read and
preserved through the native preview style; no color controls are authored.

All target previous contents are checked before the first write. Custom/Text
sibling rich markup and media, full native IDs/order, inactive template text,
palette/fonts, and active theme remain protected. Each new ID is read from the
single native append delta. Save occurs once and an independent native reopen
must reproduce the complete desired state. An uncertain outer journal must be
reconciled before another append.

Receipts bind exact course/template editor, configuration hash, original and
new block IDs/order/count, and `independent_readback: VERIFIED`, while
`functional_verified` and `activation_performed` remain false. Source tests
are not native Python, learner or publication acceptance. The JSON example's
inventories and identities are placeholders, not proof about a real target.
