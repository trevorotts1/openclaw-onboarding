# Hight Ticket Product Overview Prompt

> BAKED for Skill 56 (Sales Page Assets) — PROVIDER-AGNOSTIC. Runtime uses the CLIENT's OWN
> configured providers/keys (NEVER Anthropic, NEVER the operator's accounts). Credential seams:
> `${CLIENT_TEXT_API_KEY}` / `${CLIENT_IMAGE_API_KEY}` (see prompts/PROMPT-SEAMS.md). Intake seams:
> `${INTAKE.*}`. Prior-client example HTML + image-host/Drive URLs + Airtable/webhook infra ids removed;
> model names generalized. The SACRED frameworks + word/section bands are preserved and are
> machine-enforced by the Skill 56 provers.

---



## System

Your job is to synthesize the product description so that we are able to explain it in a way that other people can get the gist of what the product is about. The name of the product is right. To basically shorten to create a short one-maximum two-paragraph description of the product with the necessary information that a person would need to understand it.

## User

Use the following variables to create a product overview description, not to exceed two paragraphs, ideally one paragraph.

## Assistant

Analyze this product description. Then, from there, I want you to create a concise overview of the product description. It needs to be under 200 words. The less words the better. It's just so that I have a clear, concise understanding of what the offer is about - who it's for, who it's not for, and what the person can expect to achieve and accomplish with this particular product. Label this as product overview. And then from there, give me the product overview.
