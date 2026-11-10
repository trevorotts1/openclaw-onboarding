# Survey build scope after captured Multi Line creation

This is a finite source-build inventory, not a live respondent acceptance report.
Broad `surveys.create` and `surveys.configure` remain PARTIAL.

## Built owned creation paths

- One captured standard field per requested slide: First Name, Last Name, Phone,
  Email.
- Authored Radio question definitions and exact native placement.
- Single Line TEXT creation, multiple questions and captured populated append.
- Multi Line LARGE_TEXT creation: one question on each initially empty requested
  slide, using the actual `Multi Line1` drag tile and native textarea. Label,
  Placeholder, Short Label, Query Key, Required, Hidden and Hidden value are
  authored and checked after saving and independently reopening.

Multi Line creation uses the same typed `surveys.create.question_batches` plan
with `kind: "multiline"`. It never provisions an API custom field. Its own child
intent journal prevents repeating an uncertain drag or Save. The complete final
survey receipt binds textarea identities, slide positions, Query Keys and other
canvas controls. Completed whole-survey replay reopens and reads that inventory.
Single Line plans retain their original serialization and hashes.

Multi Line populated append and mixing Multi Line with other question families
on the same target slide are refused before browser work until their separate
native capture is available. Different captured families on different slides are
supported. Existing Multi Line properties also have their separate typed action.

## Remaining owned creation tiles

The captured Quick Add rail has 38 tile entries. Seven have an owned creation
path above. These 31 entries still need their own typed owned creation coverage:

| Group | Captured tile entries |
| --- | --- |
| Contact | Full Name; Date of birth; Organization; Website |
| Address | Updated Address; legacy Address; City; State; Country; Postal Code |
| Choices | Text Box List; Single Dropdown; Multi Dropdown; Checkbox; Picture Choice; Rating |
| Content | Text; Html; Image |
| Payment | Sell Products; Collect Payment; Monetary |
| Other | Bot protection; Source; T & C; Score; File Upload; Number; Date & time; Signature; URL |

This table describes the owned new-survey pipeline. It does not remove any
existing-field placement or form-only control support elsewhere in the code.

## Remaining configuration families

1. Other question/widget property layouts beyond captured TEXT and LARGE_TEXT.
2. Compound/mixed predicates.
3. Completion/custom-message outcomes.
4. Redirect outcomes.
5. Disqualification outcomes.
6. Arbitrary existing-rule editing and removal.
7. Arbitrary existing-rule priority/reordering.

Captured ordered forward Jump To rule stacks are already implemented. Final
native script execution and respondent answers covering each requested branch
remain separate from source completion.
