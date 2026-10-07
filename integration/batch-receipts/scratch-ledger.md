2026-10-07T06:25:30Z | QC-RECORD unit=W501U1-A judge=independent-checker model=sonnet | gate=combined-candidate tests=pass | writer=ledger.sh
verdict=PASS
outcome=CLIENT-ACCEPTED
2026-10-07T06:25:30Z | QC-RECORD unit=W501U1-B judge=independent-checker model=sonnet | deps=unit/W501U1-A closed-in-batch | writer=ledger.sh
verdict=PASS
outcome=CLIENT-ACCEPTED
2026-10-07T06:25:30Z | QC-RECORD unit=W501U1-C judge=independent-checker model=sonnet | reason=red-gate | writer=ledger.sh
verdict=FAIL
outcome=REJECTED
2026-10-07T06:27:28Z | MERGE-TRAIN BATCH | repo=factory-scratch 2 unit(s) onto main: unit/W501U1-A unit/W501U1-B | gate=test -f cand-a.txt && test -f cand-b.txt | writer=ledger.sh
2026-10-07T06:27:28Z | LANDED: unit=unit/W501U1-A commit=410c7b9ce1a40fd15abc57d7c3fe7d399993fae8 tests=pass | writer=ledger.sh
2026-10-07T06:27:28Z | LANDED: unit=unit/W501U1-B commit=915730d60c47887a727f3e09dbffcb36a4eaca1e tests=pass | writer=ledger.sh
2026-10-07T06:27:28Z | MERGED: unit=unit/W501U1-A commit=410c7b9ce1a40fd15abc57d7c3fe7d399993fae8 trunk=origin/main repo=factory-scratch | writer=ledger.sh
2026-10-07T06:27:28Z | MERGED: unit=unit/W501U1-B commit=915730d60c47887a727f3e09dbffcb36a4eaca1e trunk=origin/main repo=factory-scratch | writer=ledger.sh
2026-10-07T06:27:28Z | CLEANED: unit=unit/W501U1-A repo=factory-scratch worktree=none branch=deleted remote-branch=none | writer=ledger.sh
2026-10-07T06:27:29Z | CLEANED: unit=unit/W501U1-B repo=factory-scratch worktree=none branch=deleted remote-branch=none | writer=ledger.sh
2026-10-07T06:27:48Z | QC-RECORD unit=W501U1-D judge=independent-checker model=sonnet | arrived after BATCH-W501U1-1 closed | writer=ledger.sh
verdict=PASS
outcome=CLIENT-ACCEPTED
