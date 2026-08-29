# Part of Odoo. See LICENSE file for full copyright and licensing details.

import hashlib
import hmac

from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, tagged

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.tests.common import PaymentCommon
from odoo.addons.payment_moamalat import const


# Test values only; both must be valid hex because they are used as HMAC keys.
SECURE_KEY = '39303338303235303538'
NOTIFICATION_KEY = '31323334353637383930'


@tagged('post_install', '-at_install')
class TestPaymentMoamalat(PaymentCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.moamalat = cls._prepare_provider('moamalat', update_values={
            'moamalat_merchant_id': '10081014649',
            'moamalat_terminal_id': '99179395',
            'moamalat_secure_key': SECURE_KEY,
            'moamalat_notification_key': NOTIFICATION_KEY,
        })
        cls.provider = cls.moamalat

    def _sign(self, key_hex, values):
        """Sign values the way Moamalat does, independently of the module."""
        signing_string = '&'.join(f'{k}={values[k]}' for k in sorted(values))
        return hmac.new(
            bytes.fromhex(key_hex), signing_string.encode(), hashlib.sha256
        ).hexdigest()

    def _notification(self, **overrides):
        data = {
            'Amount': '10000',
            'Currency': '434',
            'DateTimeLocalTrxn': '241120120000',
            'MerchantId': self.moamalat.moamalat_merchant_id,
            'TerminalId': self.moamalat.moamalat_terminal_id,
            'MerchantReference': self.reference,
            'ActionCode': const.ACTION_CODE_APPROVED,
            'TxnType': const.TXN_TYPE_SALE,
            'SystemReference': 'SYS-1',
        }
        data.update(overrides)
        data['SecureHash'] = self._sign(NOTIFICATION_KEY, {
            k: data[k] for k in
            ('Amount', 'Currency', 'DateTimeLocalTrxn', 'MerchantId', 'TerminalId')
        })
        return data

    # === SIGNING === #

    def test_request_hash_matches_an_independent_hmac(self):
        """The request signature must be the HMAC Moamalat itself would compute."""
        result = self.moamalat._moamalat_generate_secure_hash(
            amount=10000, merchant_reference='TEST-1', datetime_local=1700000000,
        )
        expected = self._sign(SECURE_KEY, {
            'Amount': 10000,
            'DateTimeLocalTrxn': 1700000000,
            'MerchantId': self.moamalat.moamalat_merchant_id,
            'MerchantReference': 'TEST-1',
            'TerminalId': self.moamalat.moamalat_terminal_id,
        })
        self.assertEqual(result['secure_hash'], expected)

    def test_valid_notification_signature_is_accepted(self):
        self.assertTrue(
            self.moamalat._moamalat_verify_notification_hash(self._notification())
        )

    def test_tampered_amount_is_rejected(self):
        """Changing the amount after signing must invalidate the notification."""
        data = self._notification()
        data['Amount'] = '1'  # Signed for 10000.
        self.assertFalse(self.moamalat._moamalat_verify_notification_hash(data))

    def test_missing_signature_is_rejected(self):
        data = self._notification()
        del data['SecureHash']
        self.assertFalse(self.moamalat._moamalat_verify_notification_hash(data))

    # === STATE TRANSITIONS === #

    def test_signed_approval_sets_the_transaction_done(self):
        tx = self._create_transaction(flow='direct')
        tx._apply_updates(self._notification())
        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.provider_reference, 'SYS-1')

    def test_declined_action_code_sets_the_transaction_error(self):
        tx = self._create_transaction(flow='direct')
        tx._apply_updates(self._notification(ActionCode='05', Message="Declined"))
        self.assertEqual(tx.state, 'error')

    def test_void_sets_the_transaction_canceled(self):
        tx = self._create_transaction(flow='direct')
        tx._apply_updates(self._notification(TxnType=const.TXN_TYPE_VOID_SALE))
        self.assertEqual(tx.state, 'cancel')

    def test_transaction_is_found_by_merchant_reference(self):
        tx = self._create_transaction(flow='direct')
        found = self.env['payment.transaction']._search_by_reference(
            'moamalat', self._notification()
        )
        self.assertEqual(found, tx)

    def test_unknown_reference_is_refused(self):
        with self.assertRaises(ValidationError):
            self.env['payment.transaction']._search_by_reference(
                'moamalat', self._notification(MerchantReference='NOPE')
            )

    def test_full_processing_path_settles_the_transaction(self):
        """Drive `_process`, not just `_apply_updates`.

        `_process` also runs Odoo's amount check, which needs
        `_extract_amount_data`. Testing only `_apply_updates` leaves that hook
        unexercised, and every real webhook 500s.
        """
        tx = self._create_transaction(flow='direct', amount=10.0)
        amount_minor = payment_utils.to_minor_currency_units(tx.amount, tx.currency_id)
        data = self._notification(
            Amount=str(amount_minor),
            Currency=const.CURRENCY_MAPPING[tx.currency_id.name],
        )
        self.env['payment.transaction']._process('moamalat', data)
        tx.invalidate_recordset()
        self.assertEqual(tx.state, 'done')

    def test_amount_mismatch_is_refused(self):
        """A correctly signed notification for the wrong amount must not settle."""
        tx = self._create_transaction(flow='direct', amount=10.0)
        data = self._notification(
            Amount='1', Currency=const.CURRENCY_MAPPING[tx.currency_id.name],
        )
        self.env['payment.transaction']._process('moamalat', data)
        tx.invalidate_recordset()
        self.assertEqual(tx.state, 'error')

    # === CONFIGURATION === #

    def test_non_hex_key_is_refused(self):
        """A non-hex key would raise deep in the payment flow; refuse it on save."""
        with self.assertRaises(ValidationError):
            self.moamalat.write({'state': 'test', 'moamalat_secure_key': 'not-hex-at-all'})

    def test_unsupported_currency_is_filtered_out(self):
        supported = self.moamalat._get_supported_currencies()
        self.assertTrue(all(c.name in const.SUPPORTED_CURRENCIES for c in supported))
        self.assertIn('LYD', supported.mapped('name'))


@tagged('post_install', '-at_install')
class TestPaymentMoamalatRoutes(PaymentCommon, HttpCase):
    """The public routes, exercised over HTTP as an anonymous caller."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.moamalat = cls._prepare_provider('moamalat', update_values={
            'moamalat_merchant_id': '10081014649',
            'moamalat_terminal_id': '99179395',
            'moamalat_secure_key': SECURE_KEY,
            'moamalat_notification_key': NOTIFICATION_KEY,
        })
        cls.provider = cls.moamalat

    def test_client_callback_cannot_mark_a_transaction_paid(self):
        """An anonymous caller must not be able to settle an order.

        The Lightbox reports its result through the customer's browser, so this
        route is reachable by anyone who can guess a reference. If it were
        trusted, that POST alone would confirm the order without money moving.
        """
        tx = self._create_transaction(flow='direct')

        response = self.opener.post(
            f'{self.base_url()}/payment/moamalat/callback',
            json={
                'jsonrpc': '2.0',
                'method': 'call',
                'params': {
                    'reference': tx.reference,
                    'status': 'success',
                    'data': {'Message': 'Approved', 'SystemReference': 'FORGED'},
                },
            },
        )
        self.assertEqual(response.status_code, 200)

        tx.invalidate_recordset()
        self.assertNotEqual(tx.state, 'done', "an unsigned client claim must never settle a payment")
        self.assertNotEqual(tx.provider_reference, 'FORGED')

    def test_webhook_with_a_forged_signature_changes_nothing(self):
        tx = self._create_transaction(flow='direct')
        state_before = tx.state

        response = self.opener.post(
            f'{self.base_url()}/payment/moamalat/webhook',
            json={
                'MerchantId': self.moamalat.moamalat_merchant_id,
                'TerminalId': self.moamalat.moamalat_terminal_id,
                'MerchantReference': tx.reference,
                'Amount': '10000',
                'Currency': '434',
                'DateTimeLocalTrxn': '241120120000',
                'ActionCode': '00',
                'TxnType': '1',
                'SecureHash': 'deadbeef' * 8,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['Success'])

        tx.invalidate_recordset()
        self.assertEqual(tx.state, state_before, "a forged signature must not move the transaction")
