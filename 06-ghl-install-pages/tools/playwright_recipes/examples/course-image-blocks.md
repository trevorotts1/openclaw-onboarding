# Inactive course Image Blocks

`course_image_blocks` implements the captured Body > Add Block > Image Block
path and existing Image Block PNG/destination editing and explicit image removal. Compile `image_blocks`
into `native_course_image_blocks`; use `validate_inputs`, `configure(page,
step)` and `validate_receipt(original_result, step)` under the runner's exact
tenant guard, write-intent journal and lease.

Supply complete Category/Custom/Text/Image sidebar UUID/type/order inventory.
Each new `append` supplies `image: {file, sha256}` and an explicit `url`.
Each existing `updates` entry supplies its exact Image UUID, full `expected`
state `{inspector_url, preview_url, url}`, and `changes` containing an approved
`image`, explicit `url`, or `remove_image: {inspector_url, preview_url}`.
The two removal URLs must be the same inventoried native empty-placeholder URL,
distinct from both current image URLs. Removal and replacement cannot appear in
the same update. A removal may also set an explicit destination; otherwise the
old destination stays unchanged. Destinations are empty or credential-free HTTPS
within the conservative local 1000-character bound. Removing whole blocks,
Video Blocks and other builder controls are outside this action.

The exact sidebar UUID is mapped through complete direct-preview-wrapper
type/order and unique active selection. The selected preview must contain the
exact `img` alt `Image block UUID`. The unique Offer poster/Upload Image/Remove/
Go to URL inspector and Delete Block anchor are read only after this binding.
New blocks must match the captured empty destination and disabled Remove
defaults. Every PNG is checked by approved SHA256 before the editor opens,
then copied to a private immutable file. The known native Upload File dialog
accepts one PNG smaller than 10 MiB. A new matching inspector/rendered HTTPS
preview is required before Save; no toast or resulting media ID is invented.

Image removal clicks the already captured Remove control only after exact target
preflight. It requires the same positive empty-image shape as a new Image Block:
the inventoried inspector/rendered placeholder and disabled Remove. An absent
image, unexpected confirmation, changed placeholder or other new DOM shape stops
the operation before Save and leaves the outer uncertain-write journal for
reconciliation. Removal does not delete a block or infer an empty image from a
missing element. The complete empty state must survive independent reopen.
Use `course-image-remove.json` with actual before/empty inventories from the
requested inactive template. These URLs are observations, never guessed defaults.

All existing target previous states are preflighted before the first write.
Unrequested native image attributes, complete sibling contents/rich markup/
media/order and template settings remain protected. URL-only edits preserve
both old image URLs and all image attributes. Save occurs once, followed by an
independent native reopen and complete comparison. Uncertain outer journals
must be reconciled before another append/upload/removal.

The outcome binds exact course/template/editor/configuration, existing/new
block IDs and count, each target/source/image/destination hash, independent
readback and false functional/activation flags. Source tests do not establish
native Python or learner acceptance. Replace every example identity, inventory,
URL, file and hash from approved inputs; examples do not prove an empty target.
The removal transition uses captured controls and positive empty-image invariants;
final native removal execution remains a separate acceptance check.
