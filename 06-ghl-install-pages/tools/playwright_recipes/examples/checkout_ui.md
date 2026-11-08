# Native checkout UI example

`checkout_ui.json` demonstrates `checkout.configure_ui`. Replace the location,
visible account name, exact editor URL, native order-form element ID and section
ID with the current inventory. `expected_name` must match the selected native
Element name property. Do not infer element identity from a page title alone.

The recipe configures the captured native order-form controls:

- Mode: `One-step`, `Two-step`, or `Split`.
- Products display: images, quantity, product description, price description,
  multiple-product selection and coupon codes.
- Checkout options: Sticky contact, create a new contact per purchase, disposable
  email validation, and postal code on the payment form. The two Terms switches
  accept explicit `false` only; enabling them is refused until the approved legal
  copy editor is supported. No legal copy is generated.
- Inputs theme: `appearance` is `Box` or `Line`; `labels` is `Above`, `Floating`
  or `Hidden`. Numeric borders/radii are not part of this operation.
- Content: 37 exact native textboxes across the six captured accordion groups;
  use the keys below and supply approved nonempty strings. Placeholder text is
  preserved verbatim.
- Contact fields: Full Name, Email, Phone, Company, Address, Country, State, City
  and Zip Code. Set `required` and/or `visible` explicitly. Native Full Name and
  Email remain mandatory and visible. Field width and Add Field are not handled.

Omitted settings remain unchanged. Product display options do not create or bind
products. For native product/price binding, bumps and upsell actions use the
separate `checkout.configure_native` operation with its verified contract and
captured native adapter. This example does not execute a purchase or publish.

Validate without opening a browser:

```bash
python3 06-ghl-install-pages/tools/playwright_recipes/recipe_cli.py \
  --recipe checkout.configure_ui \
  --inputs 06-ghl-install-pages/tools/playwright_recipes/examples/checkout_ui.json
```

For host execution, supply the actual current probe report and an isolated,
authenticated Playwright page through `host.run_recipe`. The normal host CLI is:

```bash
python3 06-ghl-install-pages/tools/playwright_recipes/host.py \
  --operation checkout.configure_ui \
  --inputs /ABSOLUTE/CLIENT-RUN/checkout_ui.json \
  --probes /ABSOLUTE/CLIENT-RUN/probes.json \
  --evidence-root /ABSOLUTE/CLIENT-RUN/evidence
```

The host validates before navigation, applies the requested settings, saves the
draft, reopens the exact editor URL and compares persisted mode, switch and field
states. An actual persisted result is
`NATIVE_CHECKOUT_UI_READBACK_VERIFIED`. The overall runner keeps checkout/payment
verification pending as `NEEDS_VERIFICATION`; this is not a payment or funnel QC
PASS. An interrupted run must be reconciled from its state before replay.

These controls were captured live. Python/UI execution remains separate from the
offline tests and must be receipted on the target host before rollout.

## Content keys

| Native group | Supported keys |
| --- | --- |
| Headlines | `step_1_headline`, `step_2_headline`, `shipping_section_heading` |
| Products & summary | `products_heading`, `subheadline`, `product_item_column`, `product_price_column`, `summary_quantity_column`, `subtotal_label`, `total_label`, `savings_message`, `gift_card_summary_label`, `sold_out_label`, `no_products_message` |
| Validation messages | `full_name_validation_error`, `email_validation_error`, `phone_validation_error`, `required_field_error`, `maximum_quantity_error`, `not_enough_stock_error` |
| Coupon | `coupon_input_placeholder`, `apply_coupon_button`, `remove_coupon_button`, `coupon_applied_message`, `coupon_link_text` |
| Payment & CTA | `payment_block_title`, `order_button_text`, `order_button_subtext`, `footer_text`, `mixed_currency_error` |
| Two-step chrome | `continue_button_text`, `back_link_text`, `step_1_label`, `step_2_label`, `step_1_footer_text`, `step_1_subtitle`, `step_2_subtitle` |

Checkout option keys are `sticky_contact`, `new_contact_every_purchase`,
`validate_disposable_email`, `postal_code_on_payment_form`,
`terms_and_conditions`, and `terms_and_conditions_step_2`. The last two may only
be explicitly disabled by this script. All values must be actual JSON booleans.
