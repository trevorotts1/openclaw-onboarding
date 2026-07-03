# SOP-SIGPRES-00: THE SIGNATURE PRESENTATION LAW (the deck-type north star)

**Cluster:** Signature Presentation Doctrine (Skill 51 — the SACRED Trevor Otts method, run THROUGH the Presentations engine).
**Doctrine parent:** none — this is the root of the SIGPRES family (SOP-SIGPRES-00…06). Method authority: `51-signature-presentation/MASTERDOC.md` (Prime Directives 1–14).
**Owning roles at write time:** Signature Presentation Architect (`signature-presentation-architect.md`) owns intake→structure lock; QC Specialist (Signature Presentations) (`qc-specialist-signature-presentations.md`) grades independently. Front door: Brainstorming Buddy (signature mode) via `23-ai-workforce-blueprint/scripts/deck-intake-driver.py --signature`.
**Enforced at the gate by:** three fail-closed provers wired as manifest phases — `prove_sp_intake.py` (**P-SP-INTAKE**), `prove_sp_structure.py` (**P-SP-STRUCTURE**), `prove_sp_no_pitch.py` (**P-SP-P3-HYGIENE**) — via the `_chk_sp_intake` / `_chk_sp_structure` / `_chk_sp_no_pitch` preflight wrappers in `scripts/build_deck.py`, all of which **DEFER for every non-signature deck type**.
**Status:** Doctrine SOP. Encodes MASTERDOC Prime Directives 1–14 and the SACRED-structure contract `51-signature-presentation/structure/sp_structure.json`. This value is a FLOOR, never a cap — never floor, cap, reorder, or reinterpret it.

---

## 1. THE RULE

> "A Signature Presentation is a deck TYPE, not a new pipeline. It owns the IP and the gates; the Presentations department owns execution. It never forks `build_deck.py`."

A **Signature Presentation** is the Trevor Otts four-phase, minimum-100-slide signature talk (**Avatar → Signature Story → Transformational Teaching → Purpose Pitch**) added to the Presentations department as the governed deck type `deck_type: signature_presentation`. Setting that one field in `working/copy/intake.json` is the single switch that activates every SP gate. For every other deck type the `_chk_sp_*` wrappers defer, so non-signature decks are wholly unaffected — the SP method is strictly **additive**.

The method captured in the MASTERDOC is SACRED. Every rule below is machine-enforced by a fail-closed prover — never advisory, never a soft target.

---

## 2. THE SACRED SHAPE (what SIGPRES-01…06 detail)

| # | Phase | Slide band (per-phase FLOOR) | Doctrine doc |
|---|---|---|---|
| Intake | 8 Questions + frame — asked ONE at a time, recorded as ONE atomic block | before any slide is written | **SOP-SIGPRES-01** |
| 1 | **Avatar Section** — "Mastering the Audience Avatar" | 1–11 (≥ 11) | **SOP-SIGPRES-02** |
| 2 | **Signature Story** — "Crafting Your Personal Story" | 12–24 (≥ 13) | **SOP-SIGPRES-03** |
| 3 | **Transformational Teaching** — NO PITCHING | 25–60 (≥ 36) | **SOP-SIGPRES-04** |
| 4 | **Purpose Pitch** — not a profit pitch | 61–100 (≥ 40) | **SOP-SIGPRES-05** |
| — | Frames, hook doctrine, structure gate | deck-wide | **SOP-SIGPRES-06** |

The bands are **contiguous FLOORS starting at slide 1**, not fixed spans: when a phase expands to reach the ≥ 100 floor (Directive 11), the later phases shift by the same amount while staying contiguous and in order (avatar → story → teaching → pitch). Non-contiguity or a wrong order is `AF-SP-PHASE-ORDER`; a phase under its floor is `AF-SP-PHASE-RANGE`.

---

## 3. THE ≥ 100-SLIDE FLOOR AND THE MODE-A CARVE-OUT

The default minimum is **100 slides** (Prime Directives 3 + 11). Two things are true at once:

1. **The 90-slide Mode-A ceiling is explicitly N/A for this deck type.** The Director's duration target/cap table (SOP 9.4) does NOT apply to `deck_type: signature_presentation`; its length comes from the four phase floors (11 / 13 / 36 / 40 → ≥ 100). See `director-of-presentations.md` SOP 9.4 step 2a and the MASTERDOC §3.2.1 exemption. This carve-out is scoped to the signature deck type ONLY; every other deck type keeps the 90 hard maximum.
2. **A client-exact count still wins, exactly.** If the client states an EXACT slide count, the client's number is honored EXACTLY (fleet-wide `AF-SLIDE-COUNT-EXACT` law): the ≥ 100 floor is skipped ONLY when `client_overrode_slide_floor: true` and `client_exact_slide_count` are logged in `sp_intake.json`, and the override is surfaced on the process certificate. Phase `min_slides` floors still apply.

Both are enforced fail-closed by `prove_sp_structure.py` / `AF-SP-SLIDE-FLOOR`, which waives the floor only on the logged override and otherwise requires ≥ 100.

---

## 4. RUNS THROUGH THE ENGINE — NEVER A SECOND BUILD PATH

The Architect authors `slides.json` and the machine ledgers, then hands off to the department's ONE sanctioned build command:

```
bash 23-ai-workforce-blueprint/scripts/presentation-canonical-entry.sh \
    --run-dir <RUN_DIR> --slides slides.json --out <OUT>.pptx
```

That entry runs the fail-closed gates and then `run_signature_deck.py` → `build_deck.py` (kie.ai image render, every word baked into the image, zero native on-slide text, the full phase-attestation chain, the delivery-blocking process certificate). Writing or running a per-deck driver (`python3 working/*.py`) is the **ungoverned path and is FORBIDDEN** (`AF-CANONICAL-RENDER-BYPASS` / `AF-LOCAL-CANVAS`). The three SP provers add ONLY the sacred-method rules on top of the engine's existing auto-fail battery (hook, one-big-idea, density, typography, logo, canonical-render, image-QC) and the 9,000–18,000-char rich-prompt floor.

---

## 5. ENFORCEMENT NOTE (for the lockstep)

- **Intake gate** — `prove_sp_intake.py` → `AF-SP-8Q-MISSING`, `AF-SP-8Q-SPLIT`, `AF-SP-FRAME-UNSET`, `AF-SP-TYPE-MISMATCH`, `AF-SP-OFFER-UNDECLARED`. Detail: SOP-SIGPRES-01.
- **Structure gate** — `prove_sp_structure.py` → `AF-SP-SLIDE-FLOOR`, `AF-SP-PHASE-RANGE`, `AF-SP-PHASE-ORDER`, `AF-SP-PHASE-LABEL`, `AF-SP-IMG-SUGGESTION`, `AF-SP-CASESTUDY-CAP`, `AF-SP-TEACH-STEPS`, `AF-SP-HOOK`, `AF-SP-QUADRANT`, `AF-SP-MMM`. Detail: SOP-SIGPRES-06.
- **Phase-3 hygiene gate** — `prove_sp_no_pitch.py` → `AF-SP-PITCH-IN-TEACH`, `AF-SP-PRICE-IN-TEACH`, `AF-SP-CTA-IN-TEACH`, `AF-SP-BRIDGE`. Detail: SOP-SIGPRES-04.
- Any change to the SACRED law wires through all four SOP-SLIDE-06 lockstep steps (manifest entry + `_chk_sp_*` in `build_deck.py` + a Section-5 row mirrored into `SOP-SLIDE-00` + a `test_preflight.py` fixture). Re-running the lockstep is the ONLY sanctioned way to change the wiring; there is no separate `wire.sh`.

---

## 6. CLIENT-PROVIDER RULE (binding)

On a client box the method uses the **client's own configured providers and keys** — never the operator's, never Anthropic model ids. Role files and SOPs name client-provider tiers only (e.g. the department pins client-side QC to `qwen3-vl:235b-cloud` primary with a DeepSeek fallback on the client's own keys). This doctrine is provider-neutral by construction.

---

## 7. CROSS-REFERENCES
- **SOP-SIGPRES-01** — the 8-Questions-in-ONE-block intake + frame selection (the gate that unlocks writing).
- **SOP-SIGPRES-02 / -03 / -04 / -05** — Phases 1–4, one doc each.
- **SOP-SIGPRES-06** — the four frames, the hook doctrine, and the structure gate.
- **SOP-MODE-00** — the three creation modes (the signature deck type is additive to the mode decision).
- `51-signature-presentation/MASTERDOC.md` — the anonymized canonical methodology.
- `51-signature-presentation/examples/golden-quest/` — the Quest golden regression sample (plus the Rulebook / Vault / Original goldens).
