# Actual n8n expression-parser regression

Run from this directory:

```sh
npm ci --ignore-scripts --no-audit --no-fund
npm test
```

The pinned manifest/lock installs n8n's actual Tournament expression parser. This test compiles every expression parameter in the real social-planner n8n exports, recursively including condition and resource-locator fields. Code-node JavaScript is excluded because it runs in a separate execution engine.

The regression reproduces the September 9 sandbox failure: nested adjacent JavaScript closing braces `}}` inside an interpolation prematurely close the expression. Node VM accepts that JavaScript and therefore cannot catch the deployment defect. Separating inner closing braces with whitespace (`} }`) preserves semantics and parses correctly. IIFEs/arrows themselves work and are explicitly tested. Basic safe bodies are also executed through Tournament, not Node VM.

An invalid real export or failed regression exits nonzero. This verifies parser compatibility against the pinned parser; deployed n8n sandbox execution is still required for HTTP node behavior, Google API requests, credentials and end-to-end acceptance. Match or add the deployed parser version when testing a different n8n version. Do not treat this offline check as live workflow acceptance.
