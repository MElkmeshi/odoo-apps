import logging
from xml.sax.saxutils import escape

import requests
from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment_adfali import const


_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('adfali', "Adfali")],
        ondelete={'adfali': 'set default'},
    )
    adfali_base_url = fields.Char(
        string="API Base URL",
        help="The URL of the Adfali SOAP endpoint.",
        required_if_provider='adfali',
    )
    adfali_merchant_mobile = fields.Char(
        string="Merchant Mobile",
        help="The mobile number of the merchant wallet, as registered with Adfali.",
        required_if_provider='adfali',
    )
    adfali_merchant_pin = fields.Char(
        string="Merchant PIN",
        help="The PIN of the merchant wallet.",
        required_if_provider='adfali',
        groups='base.group_system',
    )
    adfali_service_password = fields.Char(
        string="Service Password",
        help="The service password issued by Adfali for API access.",
        required_if_provider='adfali',
        groups='base.group_system',
    )

    # === COMPUTE METHODS === #

    def _compute_feature_support_fields(self):
        """Override of `payment` to enable additional features."""
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == 'adfali').update({
            'support_express_checkout': False,
            'support_manual_capture': False,
            'support_refund': False,
            'support_tokenization': False,
        })

    # === BUSINESS METHODS === #

    def _get_supported_currencies(self):
        """Override of `payment` to limit Adfali to the currencies it accepts."""
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'adfali':
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    def _get_default_payment_method_codes(self):
        """Override of `payment` to return the default payment method codes."""
        default_codes = super()._get_default_payment_method_codes()
        if self.code != 'adfali':
            return default_codes
        return ['adfali_wallet']

    @api.model
    def _adfali_normalize_mobile(self, mobile):
        """Convert a locally-written mobile number to international format.

        `091XXXXXXX` and `91XXXXXXX` both become `+21891XXXXXXX`. A number that
        already carries the country code is left alone.

        :param str mobile: The mobile number as typed by the customer.
        :return: The mobile number in international format.
        :rtype: str
        """
        digits = (mobile or '').strip().replace(' ', '')
        if digits.startswith(const.COUNTRY_CALLING_CODE):
            return digits
        return const.COUNTRY_CALLING_CODE + digits.lstrip('0')

    def _adfali_build_envelope(self, method, params):
        """Build the SOAP 1.1 envelope for a gateway call.

        :param str method: The SOAP method name.
        :param dict params: The method parameters, in the order the gateway expects.
        :return: The serialized envelope.
        :rtype: str
        """
        fields_xml = ''.join(
            f'<{key}>{escape(str(value))}</{key}>' for key, value in params.items()
        )
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
            ' xmlns:xsd="http://www.w3.org/2001/XMLSchema"'
            ' xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            '<soap:Body>'
            f'<{method} xmlns="{const.SOAP_NAMESPACE}">{fields_xml}</{method}>'
            '</soap:Body>'
            '</soap:Envelope>'
        )

    def _adfali_make_request(self, method, params):
        """Call a SOAP method and return the text of its result element.

        :param str method: The SOAP method name.
        :param dict params: The method parameters.
        :return: The text content of the `<methodResult>` element.
        :rtype: str
        :raise ValidationError: If the gateway is unreachable or answers unusably.
        """
        self.ensure_one()

        envelope = self._adfali_build_envelope(method, params)
        try:
            response = requests.post(
                self.adfali_base_url.rstrip('/'),
                data=envelope.encode(),
                headers={
                    'Content-Type': 'text/xml; charset=utf-8',
                    'SOAPAction': f'{const.SOAP_NAMESPACE}{method}',
                },
                timeout=30,
            )
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            _logger.exception("Unable to reach the Adfali API for method %s", method)
            raise ValidationError(_("Could not establish a connection to the Adfali API."))
        except requests.exceptions.HTTPError:
            # The body can echo merchant credentials, so it is logged but never shown.
            _logger.exception("Invalid Adfali API request for method %s", method)
            raise ValidationError(_("An error occurred when communicating with the Adfali API."))

        return self._adfali_extract_result(response.content, f'{method}Result')

    def _adfali_extract_result(self, body, result_tag):
        """Pull the named result element out of a SOAP response.

        :param bytes body: The raw response body.
        :param str result_tag: The name of the result element.
        :return: The stripped text content of the element.
        :rtype: str
        :raise ValidationError: If the body is not parseable or lacks the element.
        """
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        try:
            tree = etree.fromstring(body, parser=parser)
        except etree.XMLSyntaxError:
            _logger.exception("Adfali returned an unparseable response")
            raise ValidationError(_("The Adfali API returned an unreadable response."))

        nodes = tree.xpath(f"//*[local-name()='{result_tag}']")
        if not nodes:
            _logger.error("Adfali response carried no <%s> element", result_tag)
            raise ValidationError(_("The Adfali API returned an unreadable response."))
        return (nodes[0].text or '').strip()

    def _adfali_initiate(self, customer_mobile, amount):
        """Start a payment and trigger the PIN SMS to the customer.

        :param str customer_mobile: The customer's mobile number, already normalized.
        :param float amount: The amount to charge.
        :return: The gateway's session id.
        :rtype: str
        :raise ValidationError: If the gateway refuses the payment.
        """
        self.ensure_one()

        provider_sudo = self.sudo()
        result = self._adfali_make_request(const.METHOD_INITIATE, {
            'Mobile': provider_sudo.adfali_merchant_mobile,
            'Pin': provider_sudo.adfali_merchant_pin,
            'Cmobile': customer_mobile,
            'Amount': amount,
            'PW': provider_sudo.adfali_service_password,
        })

        error = const.INITIATE_ERRORS.get(result.upper())
        if error:
            raise ValidationError(error())
        if not result:
            raise ValidationError(_("The payment could not be initiated."))
        return result

    def _adfali_confirm(self, session_id, customer_pin):
        """Finalize a payment with the PIN the customer received.

        :param str session_id: The session id returned when the payment was initiated.
        :param str customer_pin: The PIN typed by the customer.
        :return: Whether the payment was accepted.
        :rtype: bool
        """
        self.ensure_one()

        provider_sudo = self.sudo()
        result = self._adfali_make_request(const.METHOD_CONFIRM, {
            'Mobile': provider_sudo.adfali_merchant_mobile,
            'Pin': customer_pin,
            'sessionID': session_id,
            'PW': provider_sudo.adfali_service_password,
        })
        return result == const.CONFIRM_SUCCESS
