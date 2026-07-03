# broken-variant: duplicate-post

An outgoing post carries the SAME (platform, content_sha256) already posted within the lookback
window. `ledger.py dedup-snapshot --input dedup.json` must BLOCK with **AF-SM-DOUBLE-POST**
(exit 2). Clearable ONLY by a logged owner re-post token (§4.4).
