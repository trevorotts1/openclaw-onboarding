# Publisher sub-modes — `syndicate` (DEFERRED to v0.4.0, merge plan C9)

`syndicate` is the flag-gated family of **non-GHL add-on publishers** — the ONLY sanctioned
non-GHL posters. It is **DEFERRED to v0.4.0** and ships **off by default**, so no client is ever
blocked meanwhile (their GHL-direct week runs unchanged).

Requesting `--mode syndicate` today fails **CLOSED** with a clear "deferred to v0.4.0" message
(`AF-SM-DEFERRED`, phase `P-SYNDICATE-DEFER`, `scripts/defer_stub.py --capability syndicate`) — never
a silent no-op. These stubs document the intended contract so v0.4.0 is a wiring job, not a design
job.

| Sub-mode | Channel | v0.4.0 note |
|---|---|---|
| `wordpress`     | WordPress REST | routes the `blog` fold (C5) when the client is on WordPress instead of GHL blog |
| `medium`        | Medium API     | long-form cross-post |
| `substack`      | Substack       | newsletter cross-post (boundary vs C4 GHL Campaigns) |
| `youtube-direct`| YouTube Data API | direct upload (organic; distinct from the GHL YouTube channel) |

**Each requires an explicit BYPASS-SCAN allow-list carve-out** when it lands — the entry-gate
BYPASS-SCAN forbids hand-rolled posters, so every sanctioned non-GHL poster must be named
individually, never blanket-allowed. All return the same normalized publish-result contract
(`AF-SM-PUBLISH-RESULT`). Until then: `wordpress`/`medium`/`substack`/`youtube-direct` platform
specialists get NO role wiring (advertising a mode that does not exist is forbidden).
