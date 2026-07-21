# Agnes Image 2.1 Flash - Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

---

## AGENTS.md - UPDATE REQUIRED

Add:

```
## Agnes Image 2.1 Flash
- Synchronous text-to-image + image-to-image on Agnes AI. Key: AGNES_AI_API_KEY (existing fleet credential).
- Model: agnes-image-2.1-flash. Endpoint: POST https://apihub.agnes-ai.com/v1/images/generations
- Required: model, prompt, size (1K/2K/3K/4K). ratio optional (16:9, 9:16, 1:1, 3:4, 4:3, 2:3, 3:2, 21:9).
- response_format lives in extra_body (NOT top level); image-to-image needs no tags.
- The IMAGE endpoint is synchronous — the response holds the image (data[0].url or data[0].b64_json). No polling.
- Full reference: 63-agnes-image/agnes-image-full.md
```

---

## TOOLS.md - UPDATE REQUIRED

Add:

```
## Agnes Image API
- Auth: Bearer <AGNES_AI_API_KEY>
- POST https://apihub.agnes-ai.com/v1/images/generations (synchronous, one request → one image)
- Model: agnes-image-2.1-flash
- Size tiers: 1K / 2K / 3K / 4K crossed with ratio (16:9 2K = 2624x1472)
- Output: data[0].url (URL) or data[0].b64_json (Base64); response_format in extra_body
- Image-to-image: extra_body.image[] (URL or Data-URI Base64), no tags
- Rate limits by account tier; treat 429 as the live ceiling. Currently $0/image.
- Full reference: 63-agnes-image/agnes-image-full.md
```

---

## MEMORY.md - UPDATE REQUIRED

Add:

```
## Agnes Image 2.1 Flash - Installed [DATE]
- Existing AGNES_AI_API_KEY (same key as the agnes / agnes-2.0-flash model)
- Synchronous image endpoint: POST /v1/images/generations — no task polling
- response_format in extra_body; image-to-image via extra_body.image, no tags
- Full reference: 63-agnes-image/agnes-image-full.md
```

---

## IDENTITY.md - NO UPDATE NEEDED

---

## HEARTBEAT.md - NO UPDATE NEEDED

---

## USER.md - NO UPDATE NEEDED

---

## SOUL.md - NO UPDATE NEEDED
