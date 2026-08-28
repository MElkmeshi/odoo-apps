from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.payment.tests.common import PaymentCommon


def soap_response(tag, value):
    """Build a SOAP response body carrying `value` in a `<tag>` element."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        '<soap:Body>'
        f'<{tag}Response xmlns="http://tempuri.org/">'
        f'<{tag}Result>{value}</{tag}Result>'
        f'</{tag}Response>'
        '</soap:Body>'
        '</soap:Envelope>'
    ).encode()


@tagged('post_install', '-at_install')
class TestAdfali(PaymentCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.adfali = cls._prepare_provider('adfali', update_values={
            'adfali_base_url': 'https://adfali.test/service.asmx',
            'adfali_merchant_mobile': '0911111111',
            'adfali_merchant_pin': '1234',
            'adfali_service_password': 'secret',
        })
        cls.provider = cls.adfali
        cls.currency = cls._prepare_currency('LYD')

    def _patch_results(self, results):
        """Patch the SOAP layer to return `results` in order."""
        calls = []

        def _make_request(provider, method, params):
            calls.append((method, params))
            return results[len(calls) - 1]

        patcher = patch.object(
            type(self.env['payment.provider']), '_adfali_make_request', _make_request
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls

    # === MOBILE NORMALIZATION === #

    def test_mobile_normalization(self):
        normalize = self.env['payment.provider']._adfali_normalize_mobile
        self.assertEqual(normalize('0911234567'), '+218911234567')
        self.assertEqual(normalize('911234567'), '+218911234567')
        self.assertEqual(normalize('+218911234567'), '+218911234567')
        self.assertEqual(normalize(' 0911234567 '), '+218911234567')

    # === SOAP ENVELOPE === #

    def test_envelope_carries_the_method_and_params(self):
        envelope = self.adfali._adfali_build_envelope('DoPTrans', {'Mobile': '091', 'Amount': 5.0})
        self.assertIn('<DoPTrans xmlns="http://tempuri.org/">', envelope)
        self.assertIn('<Mobile>091</Mobile>', envelope)
        self.assertIn('<Amount>5.0</Amount>', envelope)

    def test_envelope_escapes_parameter_values(self):
        envelope = self.adfali._adfali_build_envelope('DoPTrans', {'PW': 'a&b<c'})
        self.assertIn('<PW>a&amp;b&lt;c</PW>', envelope)

    def test_result_extraction(self):
        body = soap_response('DoPTrans', 'SESSION-1')
        self.assertEqual(self.adfali._adfali_extract_result(body, 'DoPTransResult'), 'SESSION-1')

    def test_unparseable_response_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.adfali._adfali_extract_result(b'<not xml', 'DoPTransResult')

    def test_missing_result_element_is_rejected(self):
        body = soap_response('DoPTrans', 'SESSION-1')
        with self.assertRaises(ValidationError):
            self.adfali._adfali_extract_result(body, 'SomethingElseResult')

    # === INIT === #

    def test_init_stores_session_and_sets_pending(self):
        tx = self._create_transaction(flow='direct')
        calls = self._patch_results(['SESSION-1'])

        otp_length = tx._adfali_init('0911234567')

        self.assertEqual(otp_length, 4)
        self.assertEqual(tx.state, 'pending')
        self.assertEqual(tx.sudo().adfali_session_id, 'SESSION-1')
        self.assertEqual(calls[0][1]['Cmobile'], '+218911234567')

    def test_init_maps_each_gateway_error_code(self):
        for index, (code, fragment) in enumerate((
            ('PW1', "service password"),
            ('PW', "merchant PIN"),
            ('LIMIT', "exceeds the transaction limits"),
            ('ACC', "No Adfali account"),
            ('BAL', "check your wallet balance"),
        )):
            # References are unique per transaction, so each case needs its own.
            tx = self._create_transaction(flow='direct', reference=f'adfali-error-{index}')
            with patch.object(
                type(self.env['payment.provider']),
                '_adfali_make_request',
                lambda provider, method, params, _code=code: _code,
            ):
                with self.assertRaisesRegex(ValidationError, fragment):
                    tx._adfali_init('0911234567')
            self.assertEqual(tx.state, 'draft')

    def test_init_requires_a_mobile_number(self):
        tx = self._create_transaction(flow='direct')
        with self.assertRaises(ValidationError):
            tx._adfali_init('')

    # === CONFIRM === #

    def test_confirm_success_sets_done(self):
        tx = self._create_transaction(flow='direct')
        tx.sudo().adfali_session_id = 'SESSION-1'
        tx._set_pending()
        calls = self._patch_results(['OK'])

        tx._adfali_confirm('1234')

        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.provider_reference, 'SESSION-1')
        self.assertEqual(calls[0][1]['Pin'], '1234')
        self.assertEqual(calls[0][1]['sessionID'], 'SESSION-1')

    def test_confirm_rejection_sets_error(self):
        tx = self._create_transaction(flow='direct')
        tx.sudo().adfali_session_id = 'SESSION-1'
        tx._set_pending()
        self._patch_results(['NOK'])

        tx._adfali_confirm('9999')

        self.assertEqual(tx.state, 'error')

    def test_confirm_leaves_transaction_pending_on_transport_failure(self):
        tx = self._create_transaction(flow='direct')
        tx.sudo().adfali_session_id = 'SESSION-1'
        tx._set_pending()

        def _fail(provider, method, params):
            raise ValidationError("Could not establish a connection to the Adfali API.")

        with patch.object(
            type(self.env['payment.provider']), '_adfali_make_request', _fail
        ):
            with self.assertRaises(ValidationError):
                tx._adfali_confirm('1234')

        # Retryable: the gateway may never have seen this payment.
        self.assertEqual(tx.state, 'pending')

    def test_confirm_requires_an_initiated_transaction(self):
        tx = self._create_transaction(flow='direct')
        with self.assertRaises(ValidationError):
            tx._adfali_confirm('1234')
