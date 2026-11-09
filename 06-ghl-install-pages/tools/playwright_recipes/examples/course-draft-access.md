# Existing draft hierarchy and access preconfiguration

Use `courses.lessons` with common location inputs, a fresh Courses v3 capability,
and the exact previous `updatedAt` of every edited target. The accompanying JSON
contains synthetic inventory placeholders and is not a runnable customer job.

`category_changes[].changes` supports `parentCategory` (an existing draft parent
or null), `dripDays`, `metadata` with `dripUnit` and nullable `dripDate`, `lockedBy`
and `lockedByCategory`, in addition to the existing content fields. A new drip
metadata object requires both keys; updates preserve an existing sibling value.

`lesson_changes[].category_id` is the inventoried source parent. To move the draft
lesson, set `changes.categoryId` to its existing draft destination. Lesson changes
also support `lockedByPost` and `lockedByCategory`. Both parent IDs are recorded
in the exact host receipt and independently checked before the update.

All hierarchy chains are read before the first PUT, including a proposed parent
changed elsewhere in the same plan; cycles are refused. Unlock references must
be published resources in the same product; an unlock lesson must have a published
parent module. Self-unlock and a module unlocked by its own lesson are refused.
Read-only dependencies are rechecked before writes. Module moves are scheduled
against both current and proposed ancestor inventories, so moving a parent below
its former child first detaches that child. Every individual PUT remains
cycle-free; the final receipt retains the original authored target order. Moving
a lesson also inventories its destination module ancestry before any write.

Targets and destination/parent modules remain drafts. This configures inactive
access metadata; it does not enable locked/drip visibility, publish a course or
enroll a learner. Those changes retain their separate approval and execution rails.
No optional local or live tests were run for this extension at the owner's request.
