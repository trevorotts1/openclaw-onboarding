# U3 UI checks

Four runnable checks, no framework, no network, standard library only.

```bash
bash checks/run-all.sh        # exit 0 = all passed, 2 = one failed
```

| Check | Proves | Exit |
|---|---|---|
| `ui-contract.mjs` | The version-0 surface exists in the shipped modules: five pages, eight questions, five looks, three song versions, the QR surface, and all nine U2 service entrypoints. Also exercises the download verifier's accept and refuse paths with no network. | 0 pass / 2 fail |
| `a11y-check.mjs` | The accessibility floor: 32 rules, including WCAG contrast computed from the real tokens for light and dark, label/input pairing, source-order focus, reduced-motion guard, and no `innerHTML`. | 0 pass / 2 fail |
| `qr-roundtrip.mjs` | The QR the page draws is a real QR: the shipped encoder's matrix is rendered to a PNG with `zlib` only and decoded back by an **independent** decoder (`zbarimg`). Three payloads, three versions. | 0 pass / 2 fail |
| `download-bytes-check.mjs` | A link yields real file bytes only under the full contract, and every failure mode is refused. | 0 pass / 2 fail |

## The download-bytes check, case by case

| Case | Route | Required outcome |
|---|---|---|
| POSITIVE | `/delivery/master.mp4` — 200, `attachment`, `Content-Length`, real bytes | **pass** |
| NEG A | `/share/master` — 302 to a landing page | **fail** |
| NEG B | `/share/to-file` — 302 to the real file (the bytes exist, behind a redirect) | **fail** |
| NEG C | `/nodisposition/master.mp4` — 200 with bytes, no `Content-Disposition` | **fail** |
| NEG D | `/lying-length/master.mp4` — `Content-Length` says 200024, body is 100 | **fail** |

NEG B is the point of the unit: **a redirect is not an actual download**, even
when it leads to a file that does exist. NEG D is the second half: a declared
length that does not match what arrives is not a file either.

## What these checks do NOT do

They do not open a browser and they do not run a screen reader. `a11y-check.mjs`
is static analysis plus contrast computed from the stylesheet; it cannot certify
a screen reader, and it does not claim to. `qr-roundtrip.mjs` needs an
independent decoder on the box (`zbarimg`); where none exists it fails loudly
rather than skipping quietly — a check that cannot run is not a check.
