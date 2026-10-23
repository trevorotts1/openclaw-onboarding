# Batch-8c compatibility evidence

Two proofs that the batch's merged behaviour holds where it matters. Both are
re-runnable at the batch head; neither needs a network, a provider, or a paid
call. Round-3 QC should **run** these rather than read them.

```
python3 tests/w10-canary/evidence/B8C/proof_recap_hold.py     # expect exit 0
python3 tests/w10-canary/evidence/B8C/proof_c2_presence.py    # expect exit 0
```

`RECEIPTS.txt` is the captured output of both scripts at the batch head,
including the exact `factory.py next --run-dir …` invocations and the
`PRODUCTION_GO_MISSING` refusals.

## proof_recap_hold.py — B7's Gate-4 hold precedes both handout paths

Same run shape twice (`video-generation`, storyboard approved): once with an
Agnes `answer=yes` receipt (Agnes segment-job handout), once without (KIE
runbook-row handout). With `control/production-go.json` present, `next` returns
`ok` and hands out a command. Deleting **only** that file makes both paths
return `outcome=rejected`, `reason_code=PRODUCTION_GO_MISSING`, `command=None`.

That code is emitted by `final_recap.hold` through `_recap_hold`, so the
refusal itself proves the hold executes before either handout.

**Correction kept in the evidence:** the first assertion expected a
`FINAL_RECAP_*` code. No such code exists on this path; the real one is
`PRODUCTION_GO_MISSING`. The behaviour was right, the expectation was wrong.

## proof_c2_presence.py — C2's presence line on the composed payload

Builds real requests through the shipped composer
`song_choices.build_requests` and inspects `req["input"]["style"]`, the text the
provider receives. Per style: every `revoices_lead` variant carries the style's
own presence clause (matched by `suno_recipe._LEAD_PRESENCE_RE`, e.g. "close
dry upfront vocal") exactly once; every non-re-voicing variant carries it zero
times; forcing the flag off drops it.

**Correction kept in the evidence:** the first probe counted `style_parts[0]`
(the groove/palette line) and failed 7 checks. The composer inserts only the
presence clause, not that whole line; the probe now uses the code's own regex.

## Scope note

C2 arrives in this batch **by ancestry** (`a07add3109be` is an ancestor of
`origin/main 7b9aaa884` through the C1 matrix lineage), not by a merge in this
branch. Presence-by-ancestry is not presence-in-the-built-payload, which is why
the payload is inspected here.
