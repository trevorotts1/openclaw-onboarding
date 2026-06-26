# Test Fixtures (B5 — Golden Page Blobs)

This directory holds small golden reference blobs captured from known-good
rendered GoHighLevel pages.  The blobs are used by `test_ghl_rest_canvas.py`
(the B6 new_page_blob tests) to verify that the production builder produces
structurally equivalent output.

**Populated by:** Bucket B5 (references / golden blobs).

**Expected files:**
- `golden_page_blob_website.json` — a real website page blob from a known-good render.
- `golden_page_blob_funnel.json` — a real funnel page blob from a known-good render.

Until B5 lands these files, the tests that reference them are automatically
skipped (via `pytest.skip`).  No test fails as a result of a missing fixture;
they simply skip and run once B5 provides the files.

**Shape both files must have:**
```json
{
  "defaultSettings": {
    "colors": { ... non-empty dict ... }
  },
  "sections": [
    {
      "rows": [
        {
          "columns": [
            {
              "elements": [
                {
                  "type": "customCode",
                  "extra": {
                    "customCode": {
                      "value": {
                        "rawCustomCode": "..."
                      }
                    }
                  }
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```
