# SOP-GHL-10 — Widget Installation

**Cluster:** `universal-sops/ghl-hybrid-operations/` · **Owner:** Skill 44 (provisioning) + Skill 6 (page installation) · **Revision:** 3.0 (2026-11-08)

**Trigger:** A request to create a chat widget, put it on a page/website, or change its inbox behavior —
including "put this native chat widget on my website".

**Inputs:** widget type and supported write type, allowed domains/origins, display settings, target
page/site inventory, inbox/assignment behavior, responder owner (SOP-GHL-08).

**Required pointers:** Skill 44 widget adapter/commands; Skill 6 widget-installation helper; the page
owner's build procedure; `SOP-GHL-08-NATIVE-AI.md` for the responder.

**Ordered steps:**
1. Confirm the requested widget type is supported by the documented write operation. Unknown write
   type → stop, do not guess.
2. Create the widget with the correct numeric body version; record the returned `_id`.
3. Read back: widget id, type, allowed origins, display settings, inbox target.
4. Install exactly ONE embed on the intended page/site through the page owner's build path.
5. Scan the target page for a duplicate embed (a second snippet is a blocker).
6. Verify the real communication path: open the page, send a test message, confirm thread creation,
   responder ownership, and inbox routing.
7. Bubble rendering alone is not proof of a working communication path.

**Allowed route changes:** Public widget operations first; Skill 6 page installation for the embed;
private fallback only for a documented gap. Never create a second widget to replace a lost response.

**Required output / receipt:** widget `_id`, type, body version, allowed origins, embed location,
duplicate-embed scan result, thread/responder/inbox evidence, receipt.

**Approval boundary:** enabling a widget on a public site, setting allowed domains, and routing to a
live inbox/responder require the site owner's approval. Draft widget creation does not.

**Failures:** Recoverable — embed already present → reuse, do not duplicate; allowed origin missing →
add with approval and re-verify. Terminal — unsupported write type, wrong body version, duplicate
embeds, or no inbox owner → stop and report. A widget that renders but opens no thread is not
installed.

**Acceptance:** one intended native widget, one embed, readback matches, and a real message produced a
thread with a known responder.
