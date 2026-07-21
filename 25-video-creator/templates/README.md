# Video Templates

Use a validated JSON data file with `template_video.py`:

```bash
python scripts/template_video.py TEMPLATE_NAME \
  --data client-data.json \
  --output final-video.mp4
```

`--output` is honored as the final output path. Unknown fields, missing required fields, missing media files, and unavailable requested music fail before rendering.

The bundled JSON files are illustrative legacy samples, not ready-to-render assets. Copy one, remove any fields not listed in the exact schemas below, and replace every sample media path with an existing local client-owned file before running it.

## Exact validated schemas

### `product_showcase`

- Required: `product_name` (string), `images` (non-empty list of existing image paths), `features` (non-empty list of strings)
- Optional: `tagline`, `price`, `call_to_action`, `duration`, `music`
- `music`, when present, must be an existing local audio file path.

### `social_post`

- Required: `headline` (string)
- Optional: `subheadline`, `platform`, `duration`, `music`
- `platform` must be `instagram`, `tiktok`, `reels`, `youtube`, `twitter`, or `linkedin`.
- `music`, when present, must be an existing local audio file path.

### `tutorial`

- Required: `title` (string), `sections` (non-empty list)
- Every section requires only `heading` (string), `content` (string), and `duration` (positive number).
- Optional top-level fields: `instructor`, `music`
- `music`, when present, must be an existing local audio file path.

### `testimonial`

- Required: `quote`, `author`
- Optional: `title`, `company`, `duration`

### `podcast_clip`

- Required: `audio_file` (existing local audio file path)
- Optional: `quote_text`, `speaker`, `podcast_name`, `duration`

### `event_promo`

- Required: `event_name`, `date`, `location`, `description`
- No optional fields are currently accepted.

### `announcement`

- Required: `title`, `message`
- Optional: `duration`

Only `product_showcase`, `social_post`, and `tutorial` accept `music`. A genre name is not a media file and is rejected; supply an existing local audio path.
