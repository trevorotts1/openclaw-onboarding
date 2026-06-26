# Skill 48 — Examples

## Inspect the plan
```
python3 scripts/ad_director.py --run-dir ~/Downloads/my-show-campaign --plan
```
Prints each stage with its readiness (ATTESTED / READY / waiting), its `depends_on[]`,
whether it is a HUMAN-GATE, and its owning role.

## A full dry-run (no keys) using the bundled fixtures
```
bash test-fixtures/make-ad-fixtures.sh /tmp/adfix
# GOOD run attests every phase; BAD bypass run hard-aborts:
for ph in S0-INTAKE S1-OVERLAYS PICK-10 S2-PRIMARY-TEXT S3-HEADLINES \
          S4-IMAGE-PROMPTS S5-IMAGE-GEN S6-TARGETING S7-DELIVER PUBLISH; do
  python3 scripts/ad_director.py --run-dir /tmp/adfix/good-run --phase "$ph"
done
python3 scripts/ad_director.py --run-dir /tmp/adfix/bad-run --phase S5-IMAGE-GEN ; echo "exit $?"  # -> 2
```

## Run a single checker by hand
```
python3 scripts/ad_build_check.py /tmp/adfix/good-run _chk_image_model   # -> PASS
python3 scripts/ad_build_check.py /tmp/adfix/good-run                     # -> all checkers
```

## Capture the pick-10 reply
```
python3 scripts/ad_selection.py --run-dir <RUN> --reply "PICK: 3,7,12,18,22,31,40,55,61,68"
# checks count (10), de-dups, range, echoes the chosen lines, writes s1-selection.json once.
```

## Prove the model auto-adopts a future gpt-image version
The image-model gate accepts ANY id beginning `gpt-image-`:
```
python3 - <<'PY'
import sys; sys.path.insert(0, "scripts"); import ad_build_check as abc
for m in ("gpt-image-2-text-to-image", "gpt-image-3", "gpt-image-4-image-to-image"):
    print(m, "->", "accepted" if m.startswith(abc.GPT_IMAGE_MODEL_PREFIX) else "REJECTED")
PY
```
