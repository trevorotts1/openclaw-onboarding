# Native page builder capture

A read-only inspection of a duplicate editor tab observed the native row controls. No content was changed, saved, or published.

In the funnel-builder iframe, the add-elements button has selector `#hl-builder-add-elements-button`. Its **Rows** control opens a dialog containing the exact native preset labels:

- `1 Column`
- `2 Column`
- `3 Column`
- `4 Column`
- `5 Column`
- `6 Column`

The observed page hierarchy is `.c-section` (IDs beginning `section-`) containing `.c-row` (IDs beginning `row-`), containing `.c-column` (IDs beginning `col-`). Target the intended section, row, and column in that hierarchy; these observations alone do not prove a write or save workflow.

## Folders

The Funnels list has a `Create folder` button. Read-only inspection showed a dialog containing the text `Organize your funnels into folders`, a textbox named `Folder name`, and `Cancel` and `Confirm` buttons. Only `Cancel` was pressed; no folder was created. The create route, request body, response, and parent placement remain unverified. Funnel and website folders are distinct scopes. `tools/ghl_recipe_runner.py` provides `run_folder_recipe`, which reconciles a complete scoped inventory and can reuse an existing folder while the create gate is closed. Creation remains subject to the existing capture and review gate and readback.

`ghl_rest_canvas.funnel_create_body` currently supplies only `locationId`, `name`, and `type`; it does not supply a parent folder. Selecting or creating a folder therefore does not establish that a new funnel or website was placed inside it. Capture the native placement or move workflow and verify the resulting parent before claiming that placement succeeded.
