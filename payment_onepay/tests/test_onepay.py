# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import os
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.payment_onepay.tests.common import OnePayCommon


@tagged('post_install', '-at_install')
class TestOnePay(OnePayCommon):

    def _patch_requests(self, responses):
        """Patch the API layer to return `responses` in order."""
        calls = []

        def _make_request(provider, path, payload=None, bearer=None):
            calls.append((path, payload, bearer))
            return responses[len(calls) - 1]

        patcher = patch.object(
            type(self.env['payment.provider']), '_onepay_make_request', _make_request
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls

    # === IDENTITY CARD NORMALIZATION === #

    def test_identity_card_prefixed_per_brand(self):
        for code, expected in (
            ('musrefy_pay', '111234567'),
            ('yussor_online', '331234567'),
            ('sahara_pay', '661234567'),
        ):
            provider = self.onepay.copy({'code': code})
            self.assertEqual(provider._onepay_normalize_identity_card('1234567'), expected)

    def test_identity_card_unprefixed_for_base_brand(self):
        self.assertEqual(self.onepay._onepay_normalize_identity_card('1234567'), '1234567')

    def test_identity_card_long_passes_through(self):
        provider = self.onepay.copy({'code': 'musrefy_pay'})
        self.assertEqual(provider._onepay_normalize_identity_card('123456789'), '123456789')

    def test_identity_card_short_passes_through(self):
        provider = self.onepay.copy({'code': 'musrefy_pay'})
        self.assertEqual(provider._onepay_normalize_identity_card('12345'), '12345')

    def test_identity_card_is_stripped(self):
        self.assertEqual(self.onepay._onepay_normalize_identity_card('  123456789  '), '123456789')

    # === INIT === #

    def test_init_stores_session_and_sets_pending(self):
        tx = self._create_transaction(flow='direct')
        calls = self._patch_requests([self.signin_response(), self.init_response()])

        otp_length = tx._onepay_init('123456789')

        self.assertEqual(otp_length, 6)
        self.assertEqual(tx.state, 'pending')
        self.assertEqual(tx.sudo().onepay_session_id, 'session-bearer')
        # The init call is authenticated with the sign-in bearer.
        self.assertEqual(calls[1][2], 'signin-bearer')
        self.assertEqual(calls[1][1]['identityCard'], '123456789')
        self.assertEqual(calls[1][1]['transactionId'], tx.reference)

    def test_init_failure_leaves_transaction_draft(self):
        tx = self._create_transaction(flow='direct')
        self._patch_requests([
            self.signin_response(),
            {'type': 2, 'messages': ["Insufficient balance"]},
        ])

        with self.assertRaisesRegex(ValidationError, "Insufficient balance"):
            tx._onepay_init('123456789')

        self.assertEqual(tx.state, 'draft')
        self.assertFalse(tx.sudo().onepay_session_id)

    def test_init_requires_identity_card(self):
        tx = self._create_transaction(flow='direct')
        with self.assertRaises(ValidationError):
            tx._onepay_init('')

    # === CONFIRM === #

    def test_confirm_success_sets_done_and_records_trace_id(self):
        tx = self._create_transaction(flow='direct')
        tx.sudo().onepay_session_id = 'session-bearer'
        tx._set_pending()
        calls = self._patch_requests([{'type': 1, 'traceId': 'TRACE-1'}])

        tx._onepay_confirm('123456')

        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.provider_reference, 'TRACE-1')
        # The confirmation is authenticated with the session bearer, not the sign-in one.
        self.assertEqual(calls[0][2], 'session-bearer')
        # The single-use token is dropped once spent.
        self.assertFalse(tx.sudo().onepay_session_id)

    def test_confirm_failure_sets_error_with_gateway_message(self):
        tx = self._create_transaction(flow='direct')
        tx.sudo().onepay_session_id = 'session-bearer'
        tx._set_pending()
        self._patch_requests([{'type': 2, 'messages': ["Wrong OTP"]}])

        tx._onepay_confirm('000000')

        self.assertEqual(tx.state, 'error')
        self.assertIn("Wrong OTP", tx.state_message)

    def test_confirm_requires_an_initiated_transaction(self):
        tx = self._create_transaction(flow='direct')
        with self.assertRaises(ValidationError):
            tx._onepay_confirm('123456')

    # === RECONCILIATION === #

    def _pending_transaction(self):
        tx = self._create_transaction(flow='direct')
        tx.sudo().onepay_session_id = 'session-bearer'
        tx._set_pending()
        return tx

    def test_check_matches_on_amount_and_sets_done(self):
        tx = self._pending_transaction()
        self._patch_requests([
            self.signin_response(),
            {'content': {'transactionList': [
                {'amount': tx.amount + 1},
                {'amount': tx.amount},
            ]}},
        ])

        self.assertTrue(tx._onepay_check())
        self.assertEqual(tx.state, 'done')

    def test_check_without_match_leaves_transaction_pending(self):
        tx = self._pending_transaction()
        self._patch_requests([
            self.signin_response(),
            {'content': {'transactionList': [{'amount': tx.amount + 1}]}},
        ])

        self.assertFalse(tx._onepay_check())
        self.assertEqual(tx.state, 'pending')

    def test_check_tolerates_an_empty_report(self):
        tx = self._pending_transaction()
        self._patch_requests([self.signin_response(), {'content': {}}])

        self.assertFalse(tx._onepay_check())
        self.assertEqual(tx.state, 'pending')

    def test_check_ignores_non_pending_transactions(self):
        tx = self._create_transaction(flow='direct')
        self.assertFalse(tx._onepay_check())

    # === REQUEST CONSTRUCTION === #

    def _patch_post(self, payload):
        """Patch `requests.post` and capture the call it receives."""
        captured = {}

        class Response:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return payload

        def _post(url, **kwargs):
            captured['url'] = url
            captured.update(kwargs)
            return Response()

        patcher = patch('odoo.addons.payment_onepay.models.payment_provider.requests.post', _post)
        patcher.start()
        self.addCleanup(patcher.stop)
        return captured

    def test_sign_in_sends_numeric_credentials(self):
        # The gateway is a .NET service that expects JSON numbers here, not
        # strings; blueline casts all three to int before sending.
        captured = self._patch_post(self.signin_response())

        self.onepay._onepay_sign_in()

        payload = captured['json']
        self.assertIsInstance(payload['userId'], int)
        self.assertIsInstance(payload['providerId'], int)
        self.assertIsInstance(payload['authUserType'], int)
        self.assertEqual(payload['userId'], 100589)
        self.assertEqual(payload['providerId'], 2050)

    def test_request_url_preserves_the_base_path_segment(self):
        # The base URL carries a path segment (/YusorOnline) that a naive join
        # would discard, sending every call to the wrong host root.
        captured = self._patch_post(self.signin_response())

        self.onepay._onepay_sign_in()

        self.assertEqual(
            captured['url'],
            'https://gateway.test/YusorOnline/api/OnlinePaymentServices/Signin',
        )

    def test_request_sends_the_bearer_token(self):
        captured = self._patch_post(self.init_response())

        self.onepay._onepay_make_request('api/x', {}, bearer='abc')

        self.assertEqual(captured['headers']['Authorization'], 'Bearer abc')

    # === TLS === #

    def test_test_mode_sends_no_client_certificate(self):
        self.onepay.state = 'test'
        with self.onepay._onepay_certificate_files() as (cert, verify):
            self.assertIsNone(cert)
            self.assertTrue(verify)

    def test_enabled_mode_materializes_certificate_files(self):
        pem = b'-----BEGIN CERTIFICATE-----\nZmFrZQ==\n-----END CERTIFICATE-----\n'
        self.onepay.sudo().write({
            'state': 'enabled',
            'onepay_cert': base64.b64encode(pem),
            'onepay_key': base64.b64encode(pem),
            'onepay_ca_bundle': base64.b64encode(pem),
        })

        with self.onepay._onepay_certificate_files() as (cert, verify):
            cert_path, key_path = cert
            for path in (cert_path, key_path, verify):
                self.assertTrue(os.path.isfile(path))
                with open(path, 'rb') as f:
                    self.assertEqual(f.read(), pem)
            paths = (cert_path, key_path, verify)

        # Nothing survives the context manager.
        for path in paths:
            self.assertFalse(os.path.exists(path))

    def test_non_pem_material_is_rejected_on_save(self):
        with self.assertRaises(ValidationError):
            self.onepay.sudo().onepay_cert = base64.b64encode(b'not a certificate')
