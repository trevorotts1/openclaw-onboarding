# Signature grade gold set (Skill 71, Item 8)

This folder holds the known-good images that calibrate the Signature
grade screen (`scripts/validate_image_grade.py`). The floors the screen
enforces are derived from these images, never invented.

## Status

EMPTY on purpose. Trevor supplies 5 to 10 accepted images that define
the look (plus, if handy, 3 to 5 known-bad ones, which live OUTSIDE this
folder and are passed to the calibrator with `--bad`). Until the images
land and Trevor approves the proposed floors, the brand file's grade
thresholds stay null and production image stages cannot close (that
block is the gate's Item 8 close rule, requested in
GATE-CHANGE-REQUESTS.md at the repo root of this change set).

## Manifest format: gold-set.json

`gold-set.json` sits in this folder and lists every gold image:

```json
{
  "images": [
    {
      "file": "gold-01-hero.png",
      "source_page": "Name or URL of the accepted page this image ran on",
      "approved_by": "Trevor Otts",
      "date": "2026-10-13"
    }
  ]
}
```

Rules for entries:

- `file`: the image's filename inside this folder. PNG, JPG, or WebP.
- `source_page`: where the image was accepted (page name or public URL),
  so a future reader can see the context the approval happened in.
- `approved_by`: who approved it as gold. Calibration gold is approved
  by Trevor Otts; an image nobody approved does not belong here.
- `date`: the approval date, ISO format (YYYY-MM-DD).

The file currently in this folder is the empty format scaffold:
`{"images": []}`. `scripts/calibrate_grade.py` refuses to calibrate
from an empty manifest and says why.

## Calibrating

```
python3 scripts/calibrate_grade.py \
  --brand assets/brand/blackceo-brand.json \
  --gold assets/brand/gold-set \
  [--bad <folder of known-bad images>]
```

The script measures every gold image with the exact code the grade
screen runs, prints the table, and proposes each floor as the gold
set's 5th percentile x 0.95. It proposes only; it never writes the
brand file. Trevor approves or adjusts the numbers, and only then are
they written into `assets/brand/blackceo-brand.json` by hand, with the
calibration date and this manifest's SHA-256 recorded in the brand
file's calibration documentation (see `assets/brand/brand.schema.json`,
grade block).

## Changing the gold set

Adding or removing a gold image changes what the floors mean. Any
change here requires a fresh calibration run and Trevor's approval of
the new floors, recorded the same way. Do not quietly swap an image.
