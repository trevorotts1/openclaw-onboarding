# CATEGORY RULES — Personal Photo Shoot (PS-)
**Read _system/PHOTO-SHOOT-SOP.md before ANY work in this category. This file holds only the category constraints.**

## Folder layout
```
personal photo shoot/
├── _RULES.md                          ← this file
├── PS-{NNN}_{shoot-concept}.md        ← reusable client-agnostic Shoot Cards
└── {client-slug}/
    ├── IDENTITY.md                    ← the client's identity profile (schema in PHOTO-SHOOT-SOP §3)
    └── shoots/                        ← optional per-shoot records
```

## Hard rules
- Identity Lock Block (PHOTO-SHOOT-SOP §4) in EVERY prompt involving a real person. No exceptions.
- Skin tone preservation is a hard rule; lightened skin = automatic fail, never deliver.
- Consent verified per PHOTO-SHOOT-SOP §1 before first generation for any new client.
- Retouching: one change per pass; Seedream 4.5 Edit primary (the only true surgical editor in the roster).
- All outputs route through the producer.

## Formats & resolution
- Portrait deliverables 3:4 or 4:5; scene deliverables per destination category rules.
- Drafts 1K → deliverables 2K → print/retouch finals 4K. Client choice governs; default 2K.

## Model routing
- New scenes with identity refs → Nano Banana 2 (multi-ref) or GPT-Image 2 I2I (ref + LONG spec).
- Surgical edits on real photos → Seedream 4.5 Edit.
- Style-card-driven editorial shoots → GPT-Image 2 I2I.
- Concept drafts without identity → Wan 2.7 n=4.
