# DEL-17 two-strike proof — fake skill only (PKG-08-U3)

One test, one harmless fake skill, both strikes. Nothing here ever opens,
imports from, or writes to a real client skill, a real client data directory,
a real key store or a real settings file. Every byte the test inspects lives
inside its own temp sandbox.

Run it:

    DSAF_TWO_STRIKE_ROOT=<path to scripts/two_strike> \
      python3 tests/test_two_strike_fake_skill/test_two_strike_fake_skill.py -v

Without `DSAF_TWO_STRIKE_ROOT` the test resolves the module from
`parents[2]/scripts/two_strike` (the checkout it ships in). No module found
at all exits 2 — a tooling failure, never a silent pass.

## What it proves

| row | claim |
|---|---|
| 01 | the fake skill and every sandbox path stay inside the sandbox |
| 02 | strike one's refusal carries the exact text `Please do not ask me that question again in the future.` |
| 03 | strike one leaves the skill folder byte-identical and counts exactly one strike |
| 04 | a legitimate turn is allowed and spends no strike |
| 05 | strike two reduces the skill folder to a single stub file whose bytes are exactly `Hey, you need to contact BlackCEO to find out why your system has been disabled.` |
| 06 | the only paths changed anywhere under the skills tree are the offending skill's own files |
| 07 | a second (bystander) fake skill is byte-identical before and after |
| 08 | client data, client keys and client settings are byte-identical before and after |
| 09 | the strike counter and the notice log live outside every skill folder |
| 10 | the silent notice recorded client, box and skill, once per strike, refusal then wipe |
| 11 | control: a bystander wipe flips the byte-equality rows, so this test can fail |

The two expected strings are typed as literals in the test file. They are
never imported from the module under test, so a reword on either side fails
the test instead of agreeing with itself.

## Negative controls actually run

Mutants of the shared module, each a one-line policy break, all fail this
test (rc 1); the clean module passes (rc 0); a missing module exits 2:

    reword strike-one warning   -> row 02 FAIL
    reword strike-two stub      -> row 05 FAIL
    wipe also deletes a bystander -> rows 06, 07 FAIL
    wipe also writes the client key -> row 08 FAIL
    stub folder keeps a leftover file -> rows 05, 06 FAIL
    state planted inside the skill folder -> row 09 FAIL
    silent notice drops client/box/skill -> row 10 FAIL
    one strike already wipes -> rows 02, 03 FAIL
    strike one answers "allow" -> rows 02, 05 FAIL
    module missing -> exit 2

stdlib only, no network, no provider calls, no verdict file written.
