import unittest

if __package__:
    from .native_payment_policy import payment_policy, validate_payment_inputs
    from .route import decide, recovery
    from .host import run_recipe
else:
    from native_payment_policy import payment_policy, validate_payment_inputs
    from route import decide, recovery
    from host import run_recipe


class NativePaymentPolicyTests(unittest.TestCase):
    def test_all_browser_lanes_and_recovery_preserve_policy(self):
        lanes = {
            'playwright': {'available': True},
            'openclaw_extension': {'available': True, 'current': True},
            'agent_browser': {'available': True},
            'computer_use': {'available': True, 'enabled': True},
        }
        probes = {'lanes': lanes}
        operation = 'checkout.configure_native'
        expected = payment_policy(operation)
        order = list(lanes)
        for index, lane in enumerate(order):
            result = decide(operation, 'loc', probes, failed_lanes=order[:index])
            self.assertEqual(result['lane'], lane)
            self.assertEqual(result['native_payment_policy'], expected)
            if index:
                self.assertEqual(recovery(operation, 'loc', probes, failed_lanes=order[:index])['native_payment_policy'], expected)

    def test_forms_route_and_recovery_keep_policy(self):
        probes = {'lanes': {'agent_browser': {'available': True}}}
        expected = payment_policy('forms.configure')
        self.assertIsNotNone(expected)
        self.assertEqual(decide('forms.configure', 'loc', probes)['native_payment_policy'], expected)
        self.assertEqual(recovery('forms.configure', 'loc', probes)['native_payment_policy'], expected)

    def test_explicit_replacements_refused_but_design_and_native_link_allowed(self):
        self.assertIsNotNone(validate_payment_inputs('pages.install_code', {'description': 'Build a custom payment form'}))
        self.assertIsNotNone(validate_payment_inputs('checkout.configure_native', {'payment_implementation': 'external'}))
        self.assertIsNone(validate_payment_inputs('pages.install_code', {'html': '<div class="design">Hello</div><a href="https://example.com/checkout">Pay</a>'}))
        self.assertIsNone(validate_payment_inputs('pages.install_code', {'html': '<p>Custom checkout design around native GHL checkout</p><a href="https://example.com/checkout">Pay</a>'}))
        self.assertIsNotNone(validate_payment_inputs('pages.install_code', {'html': '<iframe src="https://external.example/payment"></iframe>'}))
        self.assertIsNone(validate_payment_inputs('forms.configure', {'description': 'Contact us'}))
        self.assertIsNotNone(validate_payment_inputs('forms.configure', {'payment_implementation': 'external'}))

    def test_host_stops_before_any_provider(self):
        called = []
        result = run_recipe('checkout.configure_native', {'location_id': 'loc', 'description': 'use Stripe Elements'},
                            {'lanes': {'agent_browser': {'available': True}}}, '/tmp/unused-policy-test',
                            input_dir='.', executors={'agent_browser': lambda **kwargs: called.append(True)})
        self.assertEqual(result['status'], 'STOP_INVALID_INPUT')
        self.assertTrue(result['route']['native_payment_policy']['required'])
        self.assertFalse(called)


if __name__ == '__main__':
    unittest.main()
