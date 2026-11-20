# Prompt 13 — Carousel Image Repair Prompts (SeedDream 4.5 Edit + Fallback)

- **Source workflow:** `part6-carousel-image` (Social media in a box part 6: Carousel Image Creator)
- **Model at export time:** kie.ai `seedream/4.5-edit`
- **Model id check (2026-10-05):** `seedream/4.5-edit` is the model enum in the live KIE docs request schema (docs.kie.ai/market/seedream/4-5-edit; `4-5-edit` is only the docs URL slug, which Skill 66 models.json currently records as the id). Kept as is. Deliberate pin: Seedream 4.5 Edit is the surgical-edit repair model.
- **Purpose:** Repair pass: QC feedback becomes the edit prompt (with Instagram center-crop safety instruction). If the edited image fails QC again, the fallback strips ALL text from the image.
- **Anonymization:** verified clean — no client names or secrets in this prompt text. Client-identifying data in this workflow family lives ONLY in raw-export `pinData` (see ANALYSIS.md `client_name_locations`); it is excluded here.

## KIE file upload (free)

KIE FILE UPLOAD (free): KIE.ai has its own file upload service that costs NOTHING (no credits). It turns a local picture, audio or video file into a public https link that any KIE model (GPT Image, MiniMax H3, Kling, Suno, etc.) can read. Three ways: POST https://kieai.redpandaai.co/api/file-base64-upload (JSON {base64Data, uploadPath, fileName}, best for files under about 10 MB), /api/file-url-upload (copy from a web link, up to about 100 MB), /api/file-stream-upload (large files). Auth: Authorization: Bearer $KIE_API_KEY. The link is in data.downloadUrl. Files are DELETED after 24 hours, so upload right before the job and never use it as storage. Use this instead of uploading working files to a client's GoHighLevel media library. Source: https://docs.kie.ai/file-upload-api/quickstart

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
