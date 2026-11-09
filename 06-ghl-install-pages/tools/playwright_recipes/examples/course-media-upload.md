# Course product media upload

`course_media.run_media(inputs, evidence_root, capability=..., transport=...)`
uploads approved PNG files through the existing `ghl_media.upload_media` rail,
then attaches the returned HTTPS URLs through the documented Courses API.
The production uploader uses Skill 44's existing write approval/allowlist gate.
It never opens a browser upload dialog or publishes a course.

Supported destinations are product `posterImage`, and customization `logoImage`,
`heroImage`, `favicon`, `instructorHeadshot`. Every asset supplies its absolute
local path, approved SHA256, authored media-library name, and exact current URL.
Use `null` for an absent current value. Supply the successful course GET's exact
`updatedAt` and a current, same-location capability receipt proving
`courses.readonly`, `courses.write`, and `medias.write`.

All files and old values are checked before any upload. The implementation
copies the approved bytes to private temporary files to prevent a later local
file change from replacing the uploaded content. Existing customization siblings
are preserved; a second complete course read immediately before PUT rejects
concurrent author edits. A separate GET proves the saved URL and protected
customizations. Receipt status remains `API_STEPS_COMPLETE` with
`verification_required:true` and `functional_verified:false`; the host keeps
`NEEDS_VERIFICATION` on execution and replay. Learner/native visual proof remains separate.

`delivery-state.json` records intent before every upload and course PUT. If a
response is uncertain, the journal retains any observed media IDs and URLs and
refuses another execution. Reconcile the course and uploaded media instead of
deleting the journal or blindly uploading again. An exact completed replay does
not upload or write again.

This supports product-level API appearance fields. Inactive theme media pickers,
custom content blocks and community branding/associations remain separate native
builder features. The example deliberately contains invalid placeholder identity,
path/hash/version values: replace every placeholder from approved inventory.

## Host integration

Route `courses.update` jobs containing `media_assets` to this runner, using the
same proven public API/Skill 44 location route as ordinary `courses.update`.
Before execution call `validate_inputs`, validate the route's operation/location/
version, and require the three scopes above. Do not combine `media_assets` with
`course_changes` in one job; separate those into independently checkpointed jobs.
For `--check`, call only the pure validator and capability check. Pass trusted
in-process uploader/transport capabilities only; JSON flags are not upload proof.

The shared host routes this input through `course_media.course_executor`,
validates the exact operation/location/v3 contract in check mode, and preserves
the shared provider lease and pending-proof replay contract.
