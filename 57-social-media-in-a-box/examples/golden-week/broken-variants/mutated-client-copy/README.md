# broken-variant: mutated-client-copy

In client-copy (M3) mode the engine EDITED the client's words instead of only appending a
ctaLink. `build_manifest.py --run-dir run` must refuse the certificate with
**AF-SM-CLIENT-COPY-MUTATED** (exit 2). The engine may never rewrite the client's copy (I6).
