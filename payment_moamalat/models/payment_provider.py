# Part of Odoo. See LICENSE file for full copyright and licensing details.

import hashlib
import hmac
import json
import logging
import time

import requests
from werkzeug.urls import url_join

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment_moamalat import const


_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('moamalat', "Moamalat")],
        ondelete={'moamalat': 'set default'},
    )
    moamalat_merchant_id = fields.Char(
        string="Merchant ID (MID)",
        help="The Merchant ID provided by Moamalat.",
        required_if_provider='moamalat',
    )
    moamalat_terminal_id = fields.Char(
        string="Terminal ID (TID)",
        help="The Terminal ID provided by Moamalat.",
        required_if_provider='moamalat',
    )
    moamalat_secure_key = fields.Char(
        string="Secure Key",
        help="The key used to sign payment requests. Provided by Moamalat as a hex string.",
        required_if_provider='moamalat',
        groups='base.group_system',
    )
    moamalat_notification_key = fields.Char(
        string="Notification Key",
        help="The key used to verify the webhook notifications Moamalat sends back. "
             "Payments cannot be confirmed without it, so it is required.",
        required_if_provider='moamalat',
        groups='base.group_system',
    )

    # === CONSTRAINT METHODS === #

    @api.constrains('state', 'moamalat_secure_key', 'moamalat_notification_key')
    def _check_moamalat_keys_are_hex(self):
        """Reject keys that are not valid hex.

        Both keys are converted with `bytes.fromhex` when signing. A key that is
        not hex raises deep inside the payment flow, at the worst possible
        moment; catching it on save turns that into an ordinary form error.
        """
        for provider in self.filtered(lambda p: p.code == 'moamalat' and p.state != 'disabled'):
            for field_name, label in (
                ('moamalat_secure_key', _("Secure Key")),
                ('moamalat_notification_key', _("Notification Key")),
            ):
                value = provider.sudo()[field_name] or ''
                try:
                    bytes.fromhex(value)
                except ValueError:
                    raise ValidationError(_(
                        "The Moamalat %s must be a hexadecimal string.", label
                    ))

    # === COMPUTE METHODS === #

    def _compute_feature_support_fields(self):
        """Override of `payment` to enable additional features."""
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == 'moamalat').update({
            'support_express_checkout': False,
            'support_manual_capture': False,
            'support_refund': 'partial',
            'support_tokenization': False,
        })

    # === BUSINESS METHODS === #

    def _get_supported_currencies(self):
        """Override of `payment` to return the currencies Moamalat settles in."""
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'moamalat':
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    def _get_default_payment_method_codes(self):
        """Override of `payment` to return the default payment method codes."""
        default_codes = super()._get_default_payment_method_codes()
        if self.code != 'moamalat':
            return default_codes
        return const.DEFAULT_PAYMENT_METHOD_CODES

    def _moamalat_get_api_url(self):
        """Return the API base URL for the provider's state.

        :return: The API URL.
        :rtype: str
        """
        self.ensure_one()
        if self.state == 'enabled':
            return 'https://npg.moamalat.net'
        return 'https://tnpg.moamalat.net'

    def _moamalat_get_lightbox_url(self):
        """Return the URL of the Lightbox script for the provider's state.

        :return: The Lightbox script URL.
        :rtype: str
        """
        self.ensure_one()
        return f'{self._moamalat_get_api_url()}:6006/js/lightbox.js'

    def _moamalat_calculate_signature(self, key_field, values):
        """Return the HMAC-SHA256 of `values` under the named key.

        Moamalat signs an `&`-joined `Key=Value` string whose fields are ordered
        alphabetically, so the ordering is applied here rather than trusted to
        each caller.

        :param str key_field: The field holding the hex key to sign with.
        :param dict values: The values to sign.
        :return: The signature, hex-encoded.
        :rtype: str
        """
        self.ensure_one()
        signing_string = '&'.join(f'{k}={values[k]}' for k in sorted(values))
        key = bytes.fromhex(self.sudo()[key_field] or '')
        return hmac.new(key, signing_string.encode(), hashlib.sha256).hexdigest()

    def _moamalat_generate_secure_hash(self, amount, merchant_reference, datetime_local=None):
        """Sign a payment request.

        :param int amount: The amount, in minor units.
        :param str merchant_reference: The transaction reference.
        :param int datetime_local: The local transaction timestamp; defaults to now.
        :return: The signature and the timestamp it covers.
        :rtype: dict
        """
        self.ensure_one()
        if datetime_local is None:
            datetime_local = int(time.time())

        secure_hash = self._moamalat_calculate_signature('moamalat_secure_key', {
            'Amount': amount,
            'DateTimeLocalTrxn': datetime_local,
            'MerchantId': self.moamalat_merchant_id,
            'MerchantReference': merchant_reference,
            'TerminalId': self.moamalat_terminal_id,
        })
        return {'secure_hash': secure_hash, 'datetime_local': datetime_local}

    def _moamalat_verify_notification_hash(self, notification_data):
        """Return whether a webhook notification carries a valid signature.

        :param dict notification_data: The raw notification.
        :return: Whether the signature matches.
        :rtype: bool
        """
        self.ensure_one()

        received_hash = notification_data.get('SecureHash') or ''
        try:
            expected_hash = self._moamalat_calculate_signature('moamalat_notification_key', {
                'Amount': notification_data.get('Amount'),
                'Currency': notification_data.get('Currency'),
                'DateTimeLocalTrxn': notification_data.get('DateTimeLocalTrxn'),
                'MerchantId': notification_data.get('MerchantId'),
                'TerminalId': notification_data.get('TerminalId'),
            })
        except ValueError:
            _logger.warning("The Moamalat notification key is not valid hex.")
            return False

        # Constant-time: a plain `==` on a signature leaks its bytes through
        # timing to anyone allowed to retry, and this route is public.
        return hmac.compare_digest(expected_hash.lower(), received_hash.lower())

    def _moamalat_get_inline_form_values(self, amount, currency, partner_id, **kwargs):
        """Return the values needed to render the inline form, as JSON.

        Everything here is published to the browser, so it holds no secrets:
        the request signature is added later, per transaction, in
        `_get_specific_processing_values`.

        :param float amount: The amount in major units.
        :param res.currency currency: The transaction currency.
        :param int partner_id: The transaction partner.
        :return: The JSON-serialised values.
        :rtype: str
        """
        self.ensure_one()
        return json.dumps({
            'merchant_id': self.moamalat_merchant_id,
            'terminal_id': self.moamalat_terminal_id,
            'lightbox_url': self._moamalat_get_lightbox_url(),
            'currency_code': const.CURRENCY_MAPPING.get(currency.name),
            'is_production': self.state == 'enabled',
        })

    def _moamalat_make_request(self, endpoint, payload=None):
        """Make a request to the Moamalat API.

        :param str endpoint: The endpoint to reach.
        :param dict payload: The request payload.
        :return: The JSON response.
        :rtype: dict
        """
        self.ensure_one()
        url = url_join(self._moamalat_get_api_url(), f'/cube/paylink.svc/api/{endpoint}')
        try:
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError:
            _logger.exception("Unable to reach Moamalat at %s", url)
            raise ValidationError("Moamalat: " + _("Could not establish the connection."))
        except requests.exceptions.HTTPError:
            _logger.exception("Invalid API request at %s with data:\n%s", url, payload)
            raise ValidationError("Moamalat: " + _("An error occurred when communicating."))

    def _moamalat_refund_transaction(self, amount, system_reference=None, network_reference=None):
        """Ask Moamalat to refund a transaction.

        :param int amount: The amount to refund, in minor units.
        :param str system_reference: The system reference of the original transaction.
        :param str network_reference: The network reference of the original transaction.
        :return: The API response.
        :rtype: dict
        """
        self.ensure_one()
        datetime_local = int(time.time())
        payload = {
            'TerminalId': self.moamalat_terminal_id,
            'MerchantId': self.moamalat_merchant_id,
            'DateTimeLocalTrxn': datetime_local,
            'AmountTrxn': amount,
            'SecureHash': self._moamalat_calculate_signature('moamalat_secure_key', {
                'DateTimeLocalTrxn': datetime_local,
                'MerchantId': self.moamalat_merchant_id,
                'TerminalId': self.moamalat_terminal_id,
            }),
        }
        if system_reference:
            payload['SystemReference'] = system_reference
        if network_reference:
            payload['NetworkReference'] = network_reference

        return self._moamalat_make_request('RefundTransaction', payload)
