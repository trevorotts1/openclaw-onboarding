# PD-921 — an unbound provenance binding refuses instead of passing

- Unit: PD-921
- Lane: FL17
- Branch: `pd/fl17-phase-checks`
- Finding source: PD-099a builder, reported from outside this lane.
- Fix commit: `cb8028e0456d6a65fec3aa3d464aa116fd34e2b9`
- Parent (pre-fix) branch head: `10cedc4ec5df16eb10c061b23ec61afa24391eff`

## The defect

`phase_verifiers.py`, `_intake_provenance_refusal`:

    if _rf109 is None:
        return None

`_rf109` is `presentation_job.runfacts`, bound at import under `try/except
ImportError`. When that import fails, the helper returned `None`. Every caller
reads `None` as "no refusal", and `verify()` treats that as PASS. So a verifier
that could not bind verified nothing and passed. The engine door
(`phases.PhaseExecutor._check_intake_provenance`, phases.py:2545-2560) already
refuses that exact state with AF-INTAKE-PROVENANCE, which is why this was never
a live exploit — but pass was the wrong answer for it, and the funnel disagreed
with the door.

## The change

`phase_verifiers.py` — the unbound branch returns a named refusal whose prefix is
the door's own line, verbatim, so the two surfaces are textually tied:

    AF-INTAKE-PROVENANCE: runfacts unavailable — refusing to run without the
    intake provenance check (fail-closed). [PD-921 funnel:
    presentation_job.runfacts could not be loaded, so this verifier cannot bind
    and cannot verify]

The unbound branch is placed BEFORE the producer exemption, because the door's
import failure is a module-load gate with no producer exemption — it blocks
P-CONVERTER / P0A-INTAKE / P-SP-CLAIM too. Placing it after would have left the
funnel and the door disagreeing on producer phases. A bound run cannot reach the
branch at all, so bound behaviour is unchanged by construction and by proof
below.

`phases.py` was NOT touched. The door's behaviour is the invariant this unit
aligns to, not something it edits.

`tests/test_intake_provenance.py` — three checks added inside
`test_engine_doors_refuse`: `2c2` the unbound funnel refuses and names the
unloaded binding, `2c2b` it refuses a producer phase too (door parity), `2c3` the
binding is restored so the bound assertions 2d/2e stay meaningful. The file's
own docstring already claimed "Both fail CLOSED when runfacts cannot be imported"
(point 2); the code did not honour it until now.

## Proof

Probe: `evidence/PD-921/probe_pd921.py` (sha256
`7d0e6f5d0d76d45c487034dfb3f8e200bdae8904dc37f157f3d80431c99cf69f`). It loads
one `phase_verifiers.py` by path inside the real scripts dir, so HEAD bytes and
fixed bytes are exercised in the same import context, differing only in the file
under test. Three sections: UNBOUND, BOUND, DOOR.

### 1. Unbound run — before and after

HEAD (`44458288157d02c59e89249ddb352e4b45e9644cf2c68bd4e17a76d1e75c353b`):

    unbound.refusal[P4-COPY]=None
    unbound.refusal[P0A-INTAKE]=None
    unbound.refusal[P-CONVERTER]=None
    unbound.verify[P4-COPY]=(False, ['working/copy/slides_copy.md: file not found — phase artifact missing'])
    unbound.verify[P0A-INTAKE]=(True, [])

The last line is the defect: intake.json is present, so the phase PASSED with no
provenance verification at all.

Fixed (`0d4282a232d7f6d364f5180afd45de52a904a99c69463be5a9a5dea46715cc5e`):

    unbound.refusal[P4-COPY]='AF-INTAKE-PROVENANCE: runfacts unavailable — refusing to run without the intake provenance check (fail-closed). [PD-921 funnel: presentation_job.runfacts could not be loaded, so this verifier cannot bind and cannot verify]'
    unbound.refusal[P0A-INTAKE]=<same line>
    unbound.refusal[P-CONVERTER]=<same line>
    unbound.verify[P4-COPY]=(False, [<same line>])
    unbound.verify[P0A-INTAKE]=(False, [<same line>])

P0A-INTAKE flipped `(True, [])` → `(False, [refusal])`: pass became refusal.

### 2. Bound run — unchanged

The BOUND section is byte-identical between HEAD bytes and fixed bytes:
`diff -u` on the section prints nothing (`BOUND_IDENTICAL`):

    bound.refusal[P4-COPY]=None
    bound.refusal[P0A-INTAKE]=None
    bound.refusal[P-CONVERTER]=None
    bound.verify[P4-COPY]=(False, ['working/copy/slides_copy.md: file not found — phase artifact missing'])
    bound.verify[P0A-INTAKE]=(True, [])

Producer exemption, consumer refusal and verifier dispatch all behave exactly as
before.

### 3. Door and funnel agree

The DOOR section exercises the real `Engine._check_intake_provenance` with
`presentation_job.runfacts` removed from `sys.modules` and from the package
attribute (either alone is a silent no-op and was caught doing nothing on the
first attempt). Both HEAD and fixed runs produce:

    door.rc=3
    door.reason='AF-INTAKE-PROVENANCE: runfacts unavailable — refusing to run without the intake provenance check (fail-closed).'

    HEAD  agreement.startswith_door_reason=False   (funnel returned None = pass)
    HEAD  agreement.funnel_refuses=False
    FIXED agreement.startswith_door_reason=True
    FIXED both_name_AF=True
    FIXED agreement.funnel_refuses=True

The funnel's refusal begins with the door's exact string, so the two surfaces
cannot drift apart in wording without the prefix assertion breaking.

### 4. Suite

`tests/test_intake_provenance.py`, same file, HEAD worktree vs fixed worktree:

| tree | pass | fail |
|---|---|---|
| HEAD `10cedc4ec` (detached worktree) | 38 | 7 |
| fixed `cb8028e04` | 41 | 7 |

The seven failures are identical strings in both trees (compared after stripping
detail brackets): 4b, 4c, 4f, 4g, 5z5, 5z6, 5a. They are pre-existing on this
branch and outside PD-921's scope. The delta is exactly the three added
assertions, all PASS.

    py_compile phase_verifiers.py tests/test_intake_provenance.py → OK

## Recomputing the digests

From the branch root:

    git rev-parse cb8028e0456d6a65fec3aa3d464aa116fd34e2b9
    git show cb8028e0456d6a65fec3aa3d464aa116fd34e2b9 --format='' | shasum -a 256
      → 4a1576e7853bd24adcbf2ef3fd7f1a922ba2fb8adbbac315ed31e414831c8d19
    git show cb8028e04:23-ai-workforce-blueprint/templates/role-library/presentations/scripts/phase_verifiers.py | shasum -a 256
      → 0d4282a232d7f6d364f5180afd45de52a904a99c69463be5a9a5dea46715cc5e
    git show cb8028e04:23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_intake_provenance.py | shasum -a 256
      → 403fdd0ba47926664d51bc7bac7bd537b5dd3601106d63a12089b3cc36477768
    shasum -a 256 evidence/PD-921/probe_pd921.py
      → 7d0e6f5d0d76d45c487034dfb3f8e200bdae8904dc37f157f3d80431c99cf69f

Transcript digests (probe output, ephemeral run dirs):

- HEAD  `5a2ce3a1bd36a09849c4bacb656adffdcfa4cef9b491f22dae027587eaa17d69`
- FIXED `fc812f2271f29dc8d4571ea02fbb7e598d615542d09ff33c11b9be21d5fd94a4`
- HEAD suite `e74763848d0b64671dcb9c52d2c976a2afd500338799ccb502a013ad1442c578`
- FIXED suite `4ab6cac2dec95c304116e9e355973010e82788bc57a5c4ab900cf9132dbf8684`

Transcripts are not committed (they embed ephemeral absolute run-dir paths); the
probe reproduces them exactly from the two file digests above.

## Receipt

- Model that built this unit: `deepseek-chain[1m]`.
- This unit's builder is the model above. This report is BUILDER-side proof, not
  a verdict: the checker for PD-921 is the judge lane assigned by the
  orchestration, a different model, which is neither this builder nor a repairer
  of this builder's work. No self-certification is offered or implied here.
- Head: `cb8028e0456d6a65fec3aa3d464aa116fd34e2b9` on `pd/fl17-phase-checks`,
  parent `10cedc4ec5df16eb10c061b23ec61afa24391eff`.
- Digest that recomputes: `git show cb8028e04 --format='' | shasum -a 256` →
  `4a1576e7853bd24adcbf2ef3fd7f1a922ba2fb8adbbac315ed31e414831c8d19`.

## Notes on untouched work

The six commits this branch already carried were read and left alone:
PD-206a `471fdae82`, PD-061 `f63ef6b0c`, PD-064 `200fa8630`, PD-910
`08a6cdcd7`/`021f74e24`, PD-915 `2d85e9d1b`/`76703417c`, PD-062v `10cedc4ec`.
No file outside the two named was modified; `phases.py` is untouched.
