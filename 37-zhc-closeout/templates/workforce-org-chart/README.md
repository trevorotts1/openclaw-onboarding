# Workforce Org Chart Template

This is the HTML + Playwright renderer for **Infographic #1** in Skill 37's
ZHC closeout pipeline. It produces a 1920x1080 PNG that visualizes the
client's entire AI workforce on a single card: company brand, owner, CEO
agent, and every department grouped into 4 visual clusters with per-dept
role counts.

## Why HTML + Playwright, not AI image generation

Text-heavy infographics break diffusion-style image models. GPT Image 2 and
Nano Banana cannot reliably render small labels like "Risk & Compliance"
or "2 roles" - they hallucinate fake letters, drop punctuation, mangle
emoji, or omit words entirely. This was learned from early fleet closeout
runs where v1 and v2 came back with garbled department names and v3 needed
a complete pipeline rebuild.

HTML + CSS + a headless Chromium screenshot is:

- **Deterministic** - same input always renders the same pixels.
- **Free per render** - no per-call API cost.
- **Perfect text** - every department name, role count, and footer line is
  real DOM text.
- **Brand-controllable** - colors, fonts, and layout are CSS, not prompt
  engineering.

AI image generation is reserved for **stylized or abstract** artwork where
text is decorative or absent. Infographic #2 (How Work Flows) keeps the
KIE.AI path because that diagram is mostly arrows + a few short labels, and
the artistic look benefits from a generative model.

## Layout

The chart is divided into 4 fixed clusters with brand-locked colors:

| Cluster | Color | Hex | Departments it holds |
|--------|------|-----|----------------------|
| Operations | navy | `#1B2A4E` | Executive Office, HR, Risk & Compliance, Accounting, Tax, Legal, OpenClaw Maintenance, etc. |
| Revenue | gold | `#C9A14B` | Sales, CRM, Marketing, Paid Ads, Government Contracting, etc. |
| Creative | teal | `#2E8B8B` | Graphics, Video, Audio, Social Media, Communications, etc. |
| Technology | burgundy | `#7B2D3A` | App Dev, Web Dev, Customer Support, Research, etc. |

Unmapped departments fall into Technology so nothing is silently dropped.
The full slug-to-cluster map lives in `cluster-classifier.js`.

## Usage

```bash
# from inside the template directory (or with an explicit --template path)
node render.mjs --input /tmp/inf1-input.json --output /tmp/infographic-1.png
```

### Input JSON shape

```json
{
  "companyName":     "Sample Company",
  "monogramLetter":  "S",
  "ownerName":       "{{ownerName}}",
  "ceoAgentName":    "{{agentName}}",
  "ceoAgentTagline": "Routes all work · Reports to {{ownerName}}",
  "departments": [
    { "slug": "marketing",   "name": "Marketing",        "roles": 2, "emoji": "📣" },
    { "slug": "sales",       "name": "Sales",            "roles": 2, "emoji": "💰" },
    { "slug": "video",       "name": "Video Production", "roles": 2, "emoji": "🎥" },
    { "slug": "web",         "name": "Web Development",  "roles": 2, "emoji": "🌐" }
  ]
}
```

Field notes:

- `monogramLetter` is optional; defaults to the first letter of `companyName`.
- `ceoAgentTagline` is optional; defaults to "Routes all work · Reports to <ownerName>".
- Each department needs at least `name` and `slug`. `roles` defaults to 0,
  `emoji` defaults to blank. The cluster is derived from `slug` via
  `cluster-classifier.js`.

### Output

- A single PNG at the path passed to `--output`.
- Exactly 1920x1080.
- Footer reads: `<N> Departments · <M> Specialist Roles · Zero Human Company`.
- Right footer reads: `Built by BlackCEO · 2026`.

## Install

```bash
cd templates/workforce-org-chart
npm install
npx playwright install chromium
```

On the fleet boxes, the v10.X.3 install/hot-patch step also runs `npx
playwright install chromium` inside each container so the renderer is ready
the moment the closeout fires.

## Files

| File | Purpose |
|------|---------|
| `index.html.template` | HTML + CSS source with `{{PLACEHOLDER}}` tokens |
| `cluster-classifier.js` | Maps department slugs to one of 4 visual clusters |
| `render.mjs` | CLI that fills the template + screenshots via Playwright |
| `package.json` | Declares the `playwright` dependency |
| `README.md` | You are here |
