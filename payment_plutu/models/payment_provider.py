# Part of Odoo. See LICENSE file for full copyright and licensing details.

import hashlib
import hmac
import logging
import pprint
from urllib.parse import urlencode

import requests
from werkzeug.urls import url_join

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment_plutu import const


_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('plutu', "Plutu")],
        ondelete={'plutu': 'set default'},
    )
    plutu_api_key = fields.Char(
        string="Plutu API Key",
        required_if_provider='plutu',
        groups='base.group_system',
    )
    plutu_access_token = fields.Char(
        string="Plutu Access Token",
        required_if_provider='plutu',
        groups='base.group_system',
    )
    plutu_secret_key = fields.Char(
        string="Plutu Secret Key",
        help="Used to verify that callbacks really came from Plutu.",
        required_if_provider='plutu',
        groups='base.group_system',
    )

    # === COMPUTE METHODS === #

    def _compute_feature_support_fields(self):
        """Override of `payment` to enable additional features."""
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == 'plutu').update({
            # The customer pays on Plutu's own page and nothing comes back that
            # could be charged again, so none of these are claimable.
            'support_tokenization': False,
            'support_express_checkout': False,
            'support_manual_capture': False,
        })

    # === BUSINESS METHODS === #

    @api.model
    def _get_compatible_providers(self, *args, is_validation=False, **kwargs):
        """Override of `payment` to hide Plutu from validation operations.

        Validation charges a token, and Plutu has no tokens.
        """
        providers = super()._get_compatible_providers(*args, is_validation=is_validation, **kwargs)
        if is_validation:
            providers = providers.filtered(lambda p: p.code != 'plutu')
        return providers

    def _get_supported_currencies(self):
        """Override of `payment` to return the currencies Plutu settles in."""
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'plutu':
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    def _get_default_payment_method_codes(self):
        """Override of `payment` to return the default payment method codes."""
        default_codes = super()._get_default_payment_method_codes()
        if self.code != 'plutu':
            return default_codes
        return const.DEFAULT_PAYMENT_METHODS_CODES

    def _plutu_make_request(self, gateway, action, payload=None):
        """Make a request to the Plutu API.

        :param str gateway: The Plutu gateway, e.g. `localbankcards`.
        :param str action: The action on that gateway, e.g. `confirm`.
        :param dict payload: The request payload.
        :return: The JSON content of the response.
        :rtype: dict
        :raise ValidationError: If the request fails.
        """
        self.ensure_one()
        url = url_join('https://api.plutus.ly/api/v1/', f'transaction/{gateway}/{action}')
        headers = {
            'Accept': 'application/json',
            'X-API-KEY': self.sudo().plutu_api_key,
            'Authorization': f'Bearer {self.sudo().plutu_access_token}',
        }
        try:
            # Form-encoded, not JSON: Plutu's own SDK posts `form_params` and
            # their docs use `curl --form`. Some endpoints tolerate JSON, but
            # the one-time-code ones reject it.
            response = requests.post(url, data=payload, headers=headers, timeout=60)
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            _logger.warning(
                "Plutu refused the request at %s with data:\n%s\nResponse: %s",
                url, pprint.pformat(payload), response.text,
            )
            raise ValidationError("Plutu: " + self._plutu_error_message(response))
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            _logger.exception("Unable to reach the Plutu API at %s", url)
            raise ValidationError("Plutu: " + _("Could not establish the connection to the API."))
        return response.json()

    @staticmethod
    def _plutu_error_message(response):
        """Return something the customer can act on, from Plutu's error body.

        Plutu answers with a short `message` such as "Not subscribed to the
        service", which is far more use at the checkout than a generic failure.
        Anything longer or unparseable is dropped rather than shown, since the
        body is Plutu's and may name internals.

        :param requests.Response response: The refused response.
        :return: The message to show.
        :rtype: str
        """
        try:
            message = (response.json() or {}).get('message')
        except ValueError:
            message = None
        if isinstance(message, str) and 0 < len(message) <= 200:
            return message
        return _("The payment could not be started.")

    def _plutu_verify_signature(self, gateway, channel, parameters):
        """Return whether a Plutu callback carries a valid signature.

        Rebuilds the signed string the way Plutu's SDK does: the signed
        parameters, url-encoded, **in the order they arrived**, joined with `&`.
        The order comes from the request rather than from the list because the
        SDK filters the incoming array and PHP's `array_filter` keeps the
        original key order.

        :param str gateway: The Plutu gateway that sent the callback.
        :param str channel: Either `return` or `callback`.
        :param dict parameters: The callback parameters.
        :return: Whether the signature matches.
        :rtype: bool
        """
        self.ensure_one()

        signed_keys = const.SIGNED_PARAMETERS.get((gateway, channel))
        if signed_keys is None:
            _logger.warning("No Plutu signature definition for %s/%s.", gateway, channel)
            return False

        secret_key = (self.sudo().plutu_secret_key or '').strip()
        if not secret_key:
            _logger.warning("The Plutu secret key is not configured.")
            return False

        received_hash = parameters.get('hashed') or ''
        if not received_hash:
            _logger.warning("Received a Plutu callback with no signature.")
            return False

        signing_string = urlencode(
            [(k, v) for k, v in parameters.items() if k in signed_keys]
        )
        expected_hash = hmac.new(
            secret_key.encode(), signing_string.encode(), hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected_hash.upper(), received_hash.upper())
