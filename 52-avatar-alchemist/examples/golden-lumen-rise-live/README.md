# Golden — Lumen Rise (LIVE / repairs OFF, default mode)

This is the **default-mode** reference run for Skill 52 (FIX-AVATAR-04): the same
fictional client as `../golden-lumen-rise/` (**Lumen Rise Collective**, founder
**Amara Vale**, offer **The Visible Founder Accelerator**) built with
`build_golden.py --no-repairs` — i.e. **faithful to Trevor's original LIVE n8n
workflow**, with the source repairs R1–R6 **OFF** (the client-run default; see
`../../REPAIRS.md`).

## Why it exists

The flagship `golden-lumen-rise/` is built with `--apply-repairs` (R4 category
signatures on, etc.). Before this run existed there was **no checked-in
reference for what a DEFAULT (repairs-OFF) client run actually produces**, so the
default path shipped its known live-fidelity gaps *unobserved and un-regressed*.
This run closes that: the default output is now **regression-covered** (it clears
every deterministic content invariant in `aa_build_check.py`) **and visibly
graded** (its independent semantic certificate scores it **below** the repairs-ON
flagship while still clearing the 8.5 delivery floor).

## What "repairs OFF" ships (known live-fidelity gaps)

These are reproduced on purpose — they are what the live workflow does, and the
lower semantic grade makes them visible rather than hidden:

- **Ad sets** follow the source category wiring rather than the R4 *restored*
  per-set category signatures (the live "frozen on category 2" behavior; R4 off).
- **Blended-tone (R1)**, **cheat-sheet / 7-Tier reference (R3)**, the
  **product/offer line (R5)**, the **Solution-Aware pt2 upstream (R2)**, and the
  **Answer-9 hero doc (R6)** are left as the source passed them — no repair applied.

`RUN-LEDGER.json` records `"apply_repairs": false`; `QC-SEMANTIC.json` records
`run_id: golden-lumen-rise-live` with the lower (but passing) semantic score.

## Regenerate

```
python3 ../golden-lumen-rise/build_golden.py --no-repairs \
    --out run --deliver delivery/Amara_Vale-FINAL
```

`verify.sh` (section 3) re-checks this run's content invariants and asserts it is
repairs-OFF + visibly graded.

## Open decision (separate, not decided here)

**RULING R3** — "should the client-run DEFAULT flip to `--apply-repairs`?" — is a
Trevor decision and is deliberately **out of scope** for this reference build. If
ratified, it is a one-line default change in `intake/INTAKE-TEMPLATE.md` + the
gate, keeping `--no-repairs` available for fidelity runs. Until then, this run is
the authoritative picture of the default the client actually receives.
