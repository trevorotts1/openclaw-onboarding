# Signature Launch shared design components

**Owner room:** S71 · **Governing spec:** doc 16, *Shared Page
Components, Brand Fidelity and Production Quality* (Signature Launch
packet) · **Consumers:** S71 landing pages and, through the shared
contract, S78–S82 page skills and S50 where relevant (doc 16 §1).

A shared component has a version, owner, input schema, output/DOM
contract, accessibility expectations, events, dependency hashes and
tests (doc 16 §1). Each component folder below carries all of those:
`component.json` is the manifest, `README.md` the human contract, and
`tests/` the deterministic L1 test suite (stdlib unittest only).

| Component | Folder | Version | Implements |
|---|---|---|---|
| Design tokens | `tokens/` | 1.0.0 | doc 16 §1, §2 |
| Brand loader | `brand_loader/` | 1.0.0 | doc 16 §1, §2 |
| Branded interest popup | `interest_popup/` | 1.0.0 | doc 16 §1, §5, §6; doc 07 §4 |
| Trust/proof block | `trust_block/` | 1.0.0 | doc 16 §1, §8; doc 18 §6 |
| Deadline display | `deadline_display/` | 1.0.0 | doc 16 §1, §8 |

`design.css` holds the shared namespaced styles (doc 16 §6): every
class is `sl-`-prefixed and every brand value comes from the `--sl-*`
custom properties that `tokens.tokens_to_css()` emits from the
client's own brand file. There are no hardcoded brand colors or font
names in this package, and no broad resets.

## How a page consumes these

1. Load the launch's brand file with `brand_loader.load_brand_tokens()`
   and emit `tokens.tokens_to_css()` into the page. Missing brand data
   stays missing (named in the resolution's `missing` list); nothing
   is invented.
2. Include `design.css`.
3. Render components from launch data: the interest popup from the
   page config + the launch's approved consent statements, the trust
   block from supplied substantiated proof only, the deadline display
   from the launch's real deadline.

## Versioning

A change to a shared component increments its version in its module
and `component.json`, and lists the consumers needing retest
(doc 16 §9). Component versions here start at 1.0.0.

## Tests

From the repository root:

```bash
python3 -m unittest discover -s shared-utils/signature_launch/design -p "test_*.py" -v
```

Fixtures live in `tests/fixtures/` and are TEST ONLY: two complete
fictional brands (so nothing is hardcoded to one client, per doc 16
§10), an incomplete brand with `CLIENT_MUST_SUPPLY` sentinels, a
brand missing a required key, and a malformed file. Fixture brand IDs
are blocked from any production use by their `TEST-ONLY-*` ids and
fictional values.
