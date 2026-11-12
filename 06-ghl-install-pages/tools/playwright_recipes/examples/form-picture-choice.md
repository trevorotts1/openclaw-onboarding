# Form Picture Choice

Use `forms.configure` with the complete `widget_fields.expected_fields` inventory of supported widgets already on the form. `index` is the existing one-based canvas position; `null` creates a widget. Replace every account, form, URL, catalog button name, label and alt value below with the exact approved values for the target account. These are illustrative URLs, not existing catalog assets.

For creation, supply exactly three options. Each option requires its exact HTTPS `image_url`, its expected native image `alt`, and the exact Media Storage button name in `media_button_name`:

```json
{
  "location_id": "LOC",
  "location_name": "Example Account",
  "start_url": "https://app.convertandflow.com/v2/location/LOC/form-builder-v2/FORM",
  "widget_fields": {
    "expected_form_name": "Example Form",
    "expected_fields": [],
    "fields": [{
      "kind": "picture_choice", "index": null,
      "desired": {
        "label": "Choose a design", "placeholder": "", "short_label": "",
        "query_key": "choose_design", "width": 100, "required": false, "hidden": false,
        "options": [
          {"label": "One", "image_url": "https://example.com/one.png", "alt": "First design", "media_button_name": "First design catalog tile"},
          {"label": "Two", "image_url": "https://example.com/two.png", "alt": "Second design", "media_button_name": "Second design catalog tile"},
          {"label": "Three", "image_url": "https://example.com/three.png", "alt": "Third design", "media_button_name": "Third design catalog tile"}
        ]
      }
    }]
  }
}
```

For a replacement, inventory the existing widget and all its current options exactly. Supply `media_button_name` for each changed image; retain URL and alt for unchanged options. Option count is preserved, and alt follows the selected catalog image:

```json
{
  "location_id": "LOC",
  "location_name": "Example Account",
  "start_url": "https://app.convertandflow.com/v2/location/LOC/form-builder-v2/FORM",
  "widget_fields": {
    "expected_form_name": "Example Form",
    "expected_fields": [{
      "kind": "picture_choice", "index": 1,
      "properties": {
        "label": "Choose a design", "placeholder": "", "short_label": "",
        "query_key": "choose_design", "width": 100, "required": false, "hidden": false,
        "options": [
          {"label": "One", "image_url": "https://example.com/one.png", "alt": "First design"},
          {"label": "Two", "image_url": "https://example.com/two.png", "alt": "Second design"},
          {"label": "Three", "image_url": "https://example.com/three.png", "alt": "Third design"}
        ]
      }
    }],
    "fields": [{
      "kind": "picture_choice", "index": 1,
      "desired": {
        "label": "Choose a design", "placeholder": "", "short_label": "",
        "query_key": "choose_design", "width": 100, "required": false, "hidden": false,
        "options": [
          {"label": "One", "image_url": "https://example.com/new-one.png", "alt": "New first design", "media_button_name": "New first design catalog tile"},
          {"label": "Two", "image_url": "https://example.com/two.png", "alt": "Second design"},
          {"label": "Three", "image_url": "https://example.com/three.png", "alt": "Third design"}
        ]
      }
    }]
  }
}
```

The executor checks the selected catalog tile and resulting canvas URL and alt, then saves and independently reopens the form. This describes the implemented path; live Form creation and replacement acceptance remain to be verified.
