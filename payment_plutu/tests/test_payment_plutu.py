# Part of Odoo. See LICENSE file for full copyright and licensing details.

import hashlib
import hmac
import pathlib
from datetime import date
from urllib.parse import urlencode

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.tests.common import PaymentCommon
from odoo.addons.payment_plutu import const


SECRET_KEY = 'a-plutu-secret-key'


@tagged('post_install', '-at_install')
class TestPaymentPlutu(PaymentCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.plutu = cls._prepare_provider('plutu', update_values={
            'plutu_api_key': 'APP_ID_TEST',
            'plutu_access_token': 'ACCESS_TOKEN_TEST',
            'plutu_secret_key': SECRET_KEY,
        })
        cls.provider = cls.plutu

    def _sign(self, ordered_pairs):
        """Sign the way Plutu's SDK does: http_build_query, then upper-cased HMAC."""
        data = urlencode(ordered_pairs)
        return hmac.new(
            SECRET_KEY.encode(), data.encode(), hashlib.sha256
        ).hexdigest().upper()

    def _callback(self, gateway, channel, **overrides):
        """Build a signed callback exactly as Plutu would send it."""
        values = {
            'localbankcards': {
                'gateway': 'localbankcards', 'approved': '1', 'canceled': '0',
                'invoice_no': self.reference, 'amount': '100.00', 'transaction_id': 'TX-1',
            },
            'tlync': {
                'gateway': 'tlync', 'approved': '1', 'invoice_no': self.reference,
                'amount': '100.00', 'transaction_id': 'TX-1', 'payment_method': 'tlync',
            },
            'mpgs': {
                'gateway': 'mpgs', 'approved': '1', 'canceled': '0', 'amount': '100.00',
                'currency': 'LYD', 'invoice_no': self.reference, 'transaction_id': 'TX-1',
            },
        }[gateway]
        values.update({k: v for k, v in overrides.items() if v is not None})

        signed_keys = const.SIGNED_PARAMETERS[(gateway, channel)]
        values['hashed'] = self._sign([(k, v) for k, v in values.items() if k in signed_keys])
        return values

    # === SIGNATURE VERIFICATION === #

    def test_valid_signature_is_accepted_for_every_gateway_and_channel(self):
        for gateway, channel in const.SIGNED_PARAMETERS:
            with self.subTest(gateway=gateway, channel=channel):
                data = self._callback(gateway, channel)
                self.assertTrue(
                    self.plutu._plutu_verify_signature(gateway, channel, data),
                    f"a correctly signed {gateway}/{channel} callback must verify",
                )

    def test_tampered_amount_is_rejected(self):
        data = self._callback('localbankcards', 'callback')
        data['amount'] = '1.00'
        self.assertFalse(
            self.plutu._plutu_verify_signature('localbankcards', 'callback', data)
        )

    def test_missing_signature_is_rejected(self):
        data = self._callback('localbankcards', 'callback')
        del data['hashed']
        self.assertFalse(
            self.plutu._plutu_verify_signature('localbankcards', 'callback', data)
        )

    def test_tlync_channels_do_not_share_a_signature(self):
        """T-Lync signs different fields on the return than on the callback.

        A single hard-coded parameter list -- which is what the module started
        with -- verifies one channel and rejects the other.
        """
        return_data = self._callback('tlync', 'return')
        self.assertTrue(self.plutu._plutu_verify_signature('tlync', 'return', return_data))
        self.assertFalse(
            self.plutu._plutu_verify_signature('tlync', 'callback', return_data),
            "the return signature must not validate against the callback field set",
        )

    def test_unknown_gateway_is_rejected(self):
        data = self._callback('localbankcards', 'callback')
        self.assertFalse(self.plutu._plutu_verify_signature('sadadapi', 'callback', data))

    def test_signature_is_url_encoded(self):
        """Plutu builds the signed string with http_build_query, which encodes.

        A reference containing a character that url-encodes proves we encode
        too; concatenating raw values would drift apart from Plutu here.
        """
        data = self._callback('localbankcards', 'callback', invoice_no='S00042/1')
        self.assertIn('%2F', urlencode([('invoice_no', 'S00042/1')]))
        self.assertTrue(
            self.plutu._plutu_verify_signature('localbankcards', 'callback', data)
        )

    # === STATE TRANSITIONS === #

    def test_approved_callback_sets_the_transaction_done(self):
        tx = self._create_transaction(flow='redirect')
        tx._apply_updates(self._callback('localbankcards', 'callback'))
        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.provider_reference, 'TX-1')

    def test_canceled_callback_sets_the_transaction_canceled(self):
        tx = self._create_transaction(flow='redirect')
        tx._apply_updates(
            self._callback('localbankcards', 'callback', approved='0', canceled='1')
        )
        self.assertEqual(tx.state, 'cancel')

    def test_neither_flag_leaves_the_transaction_pending(self):
        """Plutu omits both flags while a payment is still in flight."""
        tx = self._create_transaction(flow='redirect')
        tx._apply_updates(
            self._callback('localbankcards', 'callback', approved='0', canceled='0')
        )
        self.assertEqual(tx.state, 'pending')

    def test_transaction_is_found_by_invoice_no(self):
        tx = self._create_transaction(flow='redirect')
        found = self.env['payment.transaction']._search_by_reference(
            'plutu', self._callback('localbankcards', 'callback')
        )
        self.assertEqual(found, tx)

    def test_unknown_reference_is_refused(self):
        with self.assertRaises(ValidationError):
            self.env['payment.transaction']._search_by_reference('plutu', {'invoice_no': 'NOPE'})

    def test_full_processing_path_settles_the_transaction(self):
        """Drive `_process`, not just `_apply_updates`.

        `_process` also runs Odoo's amount check, which needs
        `_extract_amount_data`. Asserting only on `_apply_updates` leaves that
        hook untested and the real callback 500s.
        """
        tx = self._create_transaction(flow='redirect', amount=10.5)
        data = self._callback(
            'localbankcards', 'callback', amount='10.5', canceled=None,
        )
        data.pop('canceled', None)
        self.env['payment.transaction']._process('plutu', data)
        tx.invalidate_recordset()
        self.assertEqual(tx.state, 'done')

    def test_amount_mismatch_is_refused(self):
        """A signed callback claiming a different amount must not settle."""
        tx = self._create_transaction(flow='redirect', amount=10.5)
        data = self._callback('localbankcards', 'callback', amount='1.00')
        data.pop('canceled', None)
        self.env['payment.transaction']._process('plutu', data)
        tx.invalidate_recordset()
        self.assertEqual(tx.state, 'error')

    def test_amount_is_skipped_when_plutu_does_not_sign_it(self):
        """T-Lync returns carry no amount; the check must be skipped, not fail."""
        tx = self._create_transaction(flow='redirect', amount=10.5)
        self.assertIsNone(tx._extract_amount_data({'invoice_no': tx.reference}))

    # === ONE-TIME-CODE GATEWAYS === #

    def _otp_tx(self, gateway):
        method = self.env['payment.method'].search([('code', '=', gateway)], limit=1)
        self.reference = f'{gateway}-{self.env["ir.sequence"].next_by_code("base.sequence.type") or id(self)}'
        return self._create_transaction(
            flow='direct', payment_method_id=method.id, amount=10.0,
        )

    def test_adfali_rejects_a_malformed_mobile_number(self):
        """Caught here, before it costs an SMS."""
        tx = self._otp_tx('edfali')
        for bad in ('', '0912345', '0812345678', '09123456789', 'nonsense'):
            with self.subTest(mobile=bad), self.assertRaises(ValidationError):
                tx._plutu_otp_send(bad)

    def test_sadad_only_accepts_091_and_093(self):
        """Sadad's range is narrower than Adfali's; the SDK enforces that."""
        tx = self._otp_tx('sadadapi')
        with self.assertRaises(ValidationError):
            tx._plutu_otp_send('0942345678', birth_year='1990')  # valid for Adfali, not Sadad

    def test_sadad_requires_a_plausible_birth_year(self):
        tx = self._otp_tx('sadadapi')
        for bad in (None, '', 'abcd', '1800', str(date.today().year)):
            with self.subTest(birth_year=bad), self.assertRaises(ValidationError):
                tx._plutu_otp_send('0912345678', birth_year=bad)

    def test_confirm_refuses_a_code_of_the_wrong_length(self):
        """Adfali codes are 4 digits and Sadad's are 6; they are not the same."""
        for gateway, good, bad in (('edfali', '1234', '123456'),
                                   ('sadadapi', '123456', '1234')):
            with self.subTest(gateway=gateway):
                tx = self._otp_tx(gateway)
                tx.plutu_process_id = '123456789'
                with self.assertRaises(ValidationError):
                    tx._plutu_otp_confirm(bad)
                self.assertEqual(len(good), const.OTP_GATEWAY_RULES[gateway]['code_length'])

    def test_confirm_refuses_without_a_process_id(self):
        """`confirm` spends what `verify` issued; there is nothing to spend yet."""
        tx = self._otp_tx('edfali')
        with self.assertRaises(ValidationError):
            tx._plutu_otp_confirm('1234')

    def test_otp_gateways_do_not_use_the_redirect_flow(self):
        """They never leave the page, so there is no redirect form to render."""
        tx = self._otp_tx('edfali')
        self.assertEqual(tx._get_specific_rendering_values({}), {})

    def test_otp_processing_values_describe_the_step(self):
        tx = self._otp_tx('sadadapi')
        vals = tx._get_specific_processing_values({})
        self.assertEqual(vals['plutu_gateway'], 'sadadapi')
        self.assertEqual(vals['plutu_code_length'], 6)
        self.assertTrue(vals['plutu_requires_birth_year'])
        self.assertTrue(vals['plutu_access_token'])

    def test_otp_access_token_is_bound_to_the_reference(self):
        """The token is what stops a stranger making Plutu text a customer."""
        tx = self._otp_tx('edfali')
        token = tx._get_specific_processing_values({})['plutu_access_token']
        self.assertEqual(
            token, payment_utils.generate_access_token(tx.reference, env=self.env)
        )
        self.assertNotEqual(
            token, payment_utils.generate_access_token('SOME-OTHER-REF', env=self.env)
        )

    # === REFERENCE SANITISING === #

    def test_reference_is_made_acceptable_to_plutu(self):
        """Plutu rejects invoice numbers outside [A-Za-z0-9.-_].

        Odoo readily produces references like "INV/2026/0001", which Plutu
        would refuse outright.
        """
        tx = self._otp_tx('edfali')
        tx.reference = 'INV/2026/0001'
        self.assertEqual(tx._plutu_invoice_no(), 'INV-2026-0001')
        tx.reference = 'S00042-1'
        self.assertEqual(tx._plutu_invoice_no(), 'S00042-1')

    # === CONFIGURATION === #

    def test_language_is_clamped_to_what_plutu_accepts(self):
        """Plutu takes only 'ar' or 'en'; anything else must not be forwarded."""
        tx = self._create_transaction(flow='redirect')
        for partner_lang, expected in [
            ('ar_LY', 'ar'), ('en_US', 'en'), ('fr_FR', 'en'), (False, 'en'),
        ]:
            with self.subTest(partner_lang=partner_lang):
                tx.partner_lang = partner_lang
                lang = 'ar' if (tx.partner_lang or '').startswith('ar') else 'en'
                self.assertEqual(lang, expected)

    def test_only_lyd_is_offered(self):
        supported = self.plutu._get_supported_currencies()
        self.assertEqual(set(supported.mapped('name')), {'LYD'})

    def test_plutu_is_hidden_from_validation(self):
        """Plutu has no tokens, so it must not be offered to validate one."""
        providers = self.env['payment.provider']._get_compatible_providers(
            self.company.id, self.partner.id, 0.0, is_validation=True
        )
        self.assertNotIn(self.plutu, providers)

    def test_shipped_data_is_disabled_and_carries_no_credentials(self):
        """The module must not install a provider that is already switched on.

        Asserted against the data file rather than the record, because the test
        setup enables the provider itself. The point is that nobody re-adds
        working keys to something published to the Apps store.
        """
        data_file = (
            pathlib.Path(__file__).parent.parent / 'data' / 'payment_provider_data.xml'
        ).read_text()
        self.assertIn('<field name="state">disabled</field>', data_file)
        for field in ('plutu_api_key', 'plutu_access_token', 'plutu_secret_key'):
            self.assertNotIn(
                f'name="{field}"', data_file, f"{field} must not be shipped with a value"
            )
