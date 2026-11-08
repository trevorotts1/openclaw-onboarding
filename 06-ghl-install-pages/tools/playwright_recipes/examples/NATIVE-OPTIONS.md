# Native form, survey and marketing quiz options

These inputs extend the shared runner. Replace example IDs, names, labels and
counts with the actual client inventory. The executor checks the exact location
and current editor. A successful native save/read-back is separate from contact
submission, branch behavior and full-funnel QC.

## Approved custom form CSS

Run `forms.style` with `custom_css` text. `form-custom-css.json` is a complete
placeholder input example. `css_key` identifies only this script's owned CSS
block. A later run with the same key replaces that block and preserves all
other client CSS. No external CSS imports or asset URLs are generated.

```bash
python3 06-ghl-install-pages/tools/playwright_recipes/recipe_cli.py \
  --recipe forms.style --inputs /ABSOLUTE/CLIENT-RUN/form-custom-css.json
```

If `radius` is also supplied, the existing rounded-input recipe runs first.
`expect_styles` checks only the supplied CSS selectors, exact element counts and
computed property values in the native Preview. The four-input example applies
to the default four-field form; update the count for the actual form.

## Standard form field properties

`forms.configure` accepts `fields` for the captured First Name, Last Name,
Phone and Email fields. Each item can edit `label`, `placeholder`, `short_label`,
`query_key`, `width_pct`, `required`, `hidden` and `hidden_value`.

```json
{
  "fields": [{
    "field": "Last Name",
    "label": "Family Name",
    "placeholder": "Enter family name",
    "width_pct": 50,
    "required": false,
    "hidden": true,
    "hidden_value": "Approved default"
  }]
}
```

Required and Hidden cannot both be true. A hidden value requires explicit
`hidden:true`. The hidden field remains selectable inside the editor; the
executor verifies its sixth property input after reopening. For a previously
customized field, provide both `current_placeholder` and `current_query_key`.
Unknown properties and ambiguous placeholder identities are refused.

## Native form conditions

`forms.conditions` accepts a `condition` object. The captured effect is
`Hide Field`; use the `effect` key, since `action` identifies executor steps.

```json
{
  "condition": {
    "if_field": "First Name",
    "operator": "Is Filled",
    "target": "Last Name",
    "effect": "Hide Field"
  }
}
```

Unary operators omit `value`; comparisons such as Contains require it. The
executor saves the rule, drawer and form separately. Matching existing rules
are reused. Unary persisted cards have an independently reopened check. Binary
card read-back still requires its additional captured layout.

## Native quiz authoring and scoring

`quizzes.configure` accepts `configuration`. Every edited question requires its
canvas index, total expected question count, current question text, current query
key and all existing option labels in order. Option categories and scores are
explicit. Authored text/choice changes require `shared_field_change_ack:true`
because the native builder warns that the field may be shared elsewhere.

```json
{
  "configuration": {
    "expected_question_count": 1,
    "categories": ["ZHC Segment"],
    "questions": [{
      "index": 0,
      "expected_question": "CURRENT QUESTION TEXT",
      "expected_query_key": "CURRENT QUERY KEY",
      "question": "Which service do you need?",
      "shared_field_change_ack": true,
      "options": [
        {"label":"Option 1","new_label":"Coaching","category":"ZHC Segment","score":10},
        {"label":"Option 2","category":"Overall Only","score":0},
        {"label":"Option 3","category":"Overall Only","score":0}
      ],
      "append_options": [
        {"label":"Consulting","category":"ZHC Segment","score":5}
      ]
    }]
  }
}
```

No existing option is removed. Appending is guarded against the captured two
Add option controls and a blank new label. Scores must be finite numbers; no
invented 0-to-10 maximum is imposed. Three result tiers can be configured with
`expected_tier_labels` and three `{label,from,to}` entries covering integer
percentages 0 through 100 without gaps or overlaps. Tier count/color changes
and per-option Jump To behavior need their own captured implementation.

## Native survey Jump To rules

`surveys.configure` accepts `configuration`:

```json
{
  "configuration": {
    "expected_slide_count": 3,
    "source_slide": 1,
    "target_slide": 3,
    "slide_labels": ["P1 - Slide 1","P2 - Slide 2","P3 - Slide 3"],
    "if_field": "Email",
    "operator": "Contains",
    "value": "@example.com"
  }
}
```

The executor verifies actual slide count, names and source-field ownership.
Previously customized source inputs can provide `source_placeholder`. Only
forward jumps between existing slides are accepted. It saves all three native
levels and verifies the independently reopened exact rule card and target.
The independent preview/submission check must still exercise both outcomes.
