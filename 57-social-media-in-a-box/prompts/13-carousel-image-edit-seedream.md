# Prompt 13 — Carousel Image Repair Prompts (SeedDream 4.5 Edit + Fallback)

- **Source workflow:** `part6-carousel-image` (Social media in a box part 6: Carousel Image Creator)
- **Model at export time:** kie.ai `seedream/4.5-edit`
- **Purpose:** Repair pass: QC feedback becomes the edit prompt (with Instagram center-crop safety instruction). If the edited image fails QC again, the fallback strips ALL text from the image.
- **Anonymization:** verified clean — no client names or secrets in this prompt text. Client-identifying data in this workflow family lives ONLY in raw-export `pinData` (see ANALYSIS.md `client_name_locations`); it is excluded here.

## User (edit pass — API payload template)

_Source: node `SeedDream Edit 1` → jsonBody_

```
{
"model": "seedream/4.5-edit",
"input": {
"image_urls": [{{ JSON.stringify($json.failedImageUrl) }}],
"aspect_ratio": "3:4",
"quality": "basic",
"prompt": {{ JSON.stringify($json.qc1Feedback + " Keep all important content centered within the middle 1350px vertical space. Top and bottom 45px will be cropped for Instagram.") }}
}
}
```

## User (fallback pass — API payload template)

_Source: node `SeedDream Fallback` → jsonBody_

```
{
"model": "seedream/4.5-edit",
"input": {
"image_urls": [{{ JSON.stringify($json.failedSd1ImageUrl) }}],
"aspect_ratio": "3:4",
"quality": "basic",
"prompt": "Remove all text and words from this image. Keep all other visual elements exactly as they appear. Center important content within the middle area."
}
}
```
