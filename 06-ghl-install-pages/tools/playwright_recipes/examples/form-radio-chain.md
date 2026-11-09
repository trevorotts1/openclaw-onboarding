# Authored Radio questions on an existing form

`form_radio_chain.build_form_questions(inputs, evidence_root, page=managed_page,
capability=measured_receipt)` joins the maintained Radio dependency fallback to
the real `forms.configure` native placement recipe. Reuse the current signed-in
managed Page; this function does not create another login or browser.

Inputs have exactly `location_id`, `location_name`, `start_url`,
`expected_form_name`, and `questions`. The existing form URL must identify its
exact `/form-builder-v2/<FORM_ID>` editor. Each question uses the same authored
Radio definition contract as `radio_dependencies`: exact `name`, `field_key`,
`data_type:"RADIO"`, ordered `options`, `expected_id`, and explicit
`allow_creation`. Creation requires expected absence; reuse requires the actual
existing field ID. Names and keys are approved inputs, never inferred from a
similar native field label.

The complete native form identity and its actual owner canvas are checked
before global contact-field schemas can be created. The existing measured
same-location Skill44 API capability and write gate still apply. A changed form
name or canvas after dependency provisioning stops before native insertion.

The chain preserves separate API and native journals, plus an intake binding to
the exact form/name/question plan. A completed native job keeps its original GET
timestamp so a later fresh dependency read cannot trigger another placement.
Uncertain API or native intents require reconciliation. No blind retry,
duplicate schema creation, form creation, publication or submission is added.

The result remains `NEEDS_VERIFICATION`; the native writer independently reopens
the saved form, but respondent behavior and contact submission are not claimed.
Other native widget types continue to require their own captured placement rail.
