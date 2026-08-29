# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re
from datetime import date
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from odoo import _, fields, models
from odoo.tools import hmac as hmac_tool
from odoo.exceptions import ValidationError

from odoo.addons.payment_plutu import const


_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    plutu_process_id = fields.Char(
        string="Plutu Process ID",
        help="Returned by Plutu's `verify` call and spent by `confirm`. Only set"
             " while a one-time-code payment is in flight.",
        readonly=True,
    )

    # === BUSINESS METHODS: THE ONE-TIME-CODE FLOW === #

    def _plutu_otp_token(self):
        """Return the token that authorises the one-time-code routes.

        Odoo's `payment_utils.generate_access_token` is not used because its
        signature differs across series and, on 18, it reads `request.env`,
        which does not exist outside an HTTP request. Signing with the same
        underlying `hmac` tool keeps one implementation for both.

        :return: The token, bound to this transaction's reference.
        :rtype: str
        """
        self.ensure_one()
        return hmac_tool(self.env(su=True), 'plutu_otp_flow', self.reference)

    def _plutu_invoice_no(self):
        """Return a reference Plutu will accept.

        Plutu rejects an invoice number holding anything outside
        [A-Za-z0-9.-_], and Odoo happily produces references like
        "INV/2026/0001". Substituting rather than failing keeps those orders
        payable; the reference still round-trips because the callback echoes
        back whatever was sent and it stays unique.

        :return: The sanitised reference.
        :rtype: str
        """
        self.ensure_one()
        sanitised = re.sub(r'[^A-Za-z0-9.\-_]', '-', self.reference)
        if not re.match(const.INVOICE_NO_PATTERN, sanitised):
            raise ValidationError("Plutu: " + _("The reference %s cannot be sent to Plutu.",
                                                self.reference))
        return sanitised

    def _plutu_check_amount(self):
        """Refuse an amount Plutu cannot charge exactly.

        :raise ValidationError: If the amount needs more than two decimals.
        """
        self.ensure_one()
        if round(self.amount, 2) != round(self.amount, 6):
            raise ValidationError("Plutu: " + _(
                "Plutu accepts at most two decimal places, so %(amount)s cannot be charged"
                " exactly.", amount=self.amount,
            ))

    def _plutu_otp_send(self, mobile_number, birth_year=None):
        """Ask Plutu to text the customer a one-time code.

        Nothing is charged here. Plutu returns a process id that `confirm`
        spends, and the transaction is left pending until it does.

        :param str mobile_number: The customer's mobile number.
        :param str birth_year: The customer's birth year, for Sadad only.
        :return: The number of digits the code will have.
        :rtype: int
        :raise ValidationError: If the input is unusable or Plutu refuses.
        """
        self.ensure_one()
        gateway = self.payment_method_id.code
        rules = const.OTP_GATEWAY_RULES.get(gateway)
        if not rules:
            raise ValidationError("Plutu: " + _("This payment method has no code step."))

        self._plutu_check_amount()

        mobile_number = (mobile_number or '').strip().replace(' ', '')
        if not re.match(rules['mobile_pattern'], mobile_number):
            raise ValidationError("Plutu: " + _(
                "Enter a valid mobile number (%s).", rules['mobile_hint']
            ))

        payload = {'mobile_number': mobile_number, 'amount': f'{self.amount:.2f}'}

        if rules['requires_birth_year']:
            max_year = date.today().year - const.BIRTH_YEAR_MAX_OFFSET
            try:
                year = int(birth_year)
            except (TypeError, ValueError):
                raise ValidationError("Plutu: " + _("Enter your birth year."))
            if not const.BIRTH_YEAR_MIN <= year <= max_year:
                raise ValidationError("Plutu: " + _(
                    "Enter a birth year between %(low)s and %(high)s.",
                    low=const.BIRTH_YEAR_MIN, high=max_year,
                ))
            payload['birth_year'] = str(year)

        response = self.provider_id._plutu_make_request(gateway, 'verify', payload=payload)
        process_id = (response.get('result') or {}).get('process_id')
        if not process_id:
            _logger.warning(
                "Plutu returned no process id for transaction %s: %s", self.reference, response
            )
            raise ValidationError("Plutu: " + _("The code could not be sent. Please try again."))

        self.plutu_process_id = str(process_id)
        self._set_pending()
        return rules['code_length']

    def _plutu_otp_confirm(self, code):
        """Spend the one-time code and settle the transaction.

        Unlike the redirect gateways there is no signed callback here: the
        payment is settled from Plutu's direct response to a call this server
        made, which is why it can be trusted without a signature.

        :param str code: The code the customer typed.
        :return: None
        :raise ValidationError: If the code is unusable or Plutu refuses.
        """
        self.ensure_one()
        gateway = self.payment_method_id.code
        rules = const.OTP_GATEWAY_RULES.get(gateway)
        if not rules:
            raise ValidationError("Plutu: " + _("This payment method has no code step."))
        if not self.plutu_process_id:
            raise ValidationError("Plutu: " + _("Ask for a new code before confirming."))

        code = (code or '').strip()
        if not code.isdigit() or len(code) != rules['code_length']:
            raise ValidationError("Plutu: " + _(
                "The code is %s digits.", rules['code_length']
            ))

        response = self.provider_id._plutu_make_request(gateway, 'confirm', payload={
            'process_id': self.plutu_process_id,
            'code': code,
            'amount': f'{self.amount:.2f}',
            'invoice_no': self._plutu_invoice_no(),
        })

        transaction_id = (response.get('result') or {}).get('transaction_id')
        if not transaction_id:
            _logger.warning(
                "Plutu did not confirm transaction %s: %s", self.reference, response
            )
            raise ValidationError("Plutu: " + _("The payment was not completed."))

        # Spent: a process id is single-use, and leaving it set invites a retry
        # that Plutu would reject anyway.
        self.plutu_process_id = False
        self.provider_reference = str(transaction_id)
        self._set_done()

    def _get_specific_processing_values(self, processing_values):
        """Override of `payment` to describe the one-time-code step to the form.

        The token is what stops the code routes from being driven by anyone who
        can guess a reference: without it, a stranger could make Plutu text a
        real customer, over and over.

        Note: `self.ensure_one()` from `_get_processing_values`

        :param dict processing_values: The generic processing values.
        :return: The provider-specific processing values.
        :rtype: dict
        """
        res = super()._get_specific_processing_values(processing_values)
        gateway = self.payment_method_id.code
        if self.provider_code != 'plutu' or gateway not in const.OTP_GATEWAYS:
            return res

        rules = const.OTP_GATEWAY_RULES[gateway]
        return {
            'plutu_gateway': gateway,
            'plutu_code_length': rules['code_length'],
            'plutu_mobile_hint': rules['mobile_hint'],
            'plutu_requires_birth_year': rules['requires_birth_year'],
            'plutu_access_token': self._plutu_otp_token(),
        }

    def _get_specific_rendering_values(self, processing_values):
        """Override of `payment` to open the payment with Plutu and redirect.

        Note: `self.ensure_one()` from `_get_processing_values`

        :param dict processing_values: The generic processing values.
        :return: The provider-specific rendering values.
        :rtype: dict
        """
        res = super()._get_specific_rendering_values(processing_values)
        gateway = self.payment_method_id.code
        if self.provider_code != 'plutu' or gateway in const.OTP_GATEWAYS:
            return res

        base_url = self.provider_id.get_base_url()

        self._plutu_check_amount()

        payload = {
            'amount': f'{self.amount:.2f}',
            'invoice_no': self._plutu_invoice_no(),
            'return_url': f'{base_url}/payment/plutu/return',
            # Plutu accepts only 'ar' or 'en'. Passing through the customer's
            # language unclamped sends 'fr' or 'tr' for a partner whose language
            # is not one of the two, which Plutu has no reason to accept.
            'lang': 'ar' if (self.partner_lang or '').startswith('ar') else 'en',
        }

        if gateway in const.GATEWAYS_REQUIRING_MOBILE:
            # T-Lync will not open a payment without one, so fail here with
            # something the customer can act on rather than on Plutu's page.
            if not self.partner_id.phone:
                raise ValidationError("Plutu: " + _(
                    "T-Lync needs a mobile number. Add one to your contact details and retry."
                ))
            payload['mobile_number'] = self.partner_id.phone
            payload['callback_url'] = f'{base_url}/payment/plutu/webhook'

        response = self.provider_id._plutu_make_request(gateway, 'confirm', payload=payload)
        redirect_url = (response.get('result') or {}).get('redirect_url')
        if not redirect_url:
            _logger.warning(
                "Plutu returned no redirect URL for transaction %s: %s", self.reference, response
            )
            raise ValidationError("Plutu: " + _("The payment could not be started."))

        # A GET form drops the query string of its action URL, and Plutu's
        # redirect URL carries the payment token there. Splitting the query out
        # into hidden inputs is what puts it back on the wire.
        split = urlsplit(redirect_url)
        return {
            'api_url': urlunsplit((split.scheme, split.netloc, split.path, '', '')),
            'url_params': parse_qsl(split.query),
        }

    def _search_by_reference(self, provider_code, payment_data):
        """Override of `payment` to find the transaction from Plutu data.

        :param str provider_code: The code of the provider that handled the transaction.
        :param dict payment_data: The payment data sent by the provider.
        :return: The transaction, if found.
        :rtype: payment.transaction
        """
        tx = super()._search_by_reference(provider_code, payment_data)
        if provider_code != 'plutu' or len(tx) == 1:
            return tx

        reference = payment_data.get('invoice_no')
        if not reference:
            raise ValidationError("Plutu: " + _("Received data with missing reference."))

        tx = self.search([('reference', '=', reference), ('provider_code', '=', 'plutu')])
        if not tx:
            raise ValidationError(
                "Plutu: " + _("No transaction found matching reference %s.", reference)
            )
        return tx

    def _extract_amount_data(self, payment_data):
        """Override of `payment` to let Odoo check Plutu's amount against ours.

        :param dict payment_data: The payment data sent by the provider.
        :return: The amount data, or None to skip the check.
        :rtype: dict|None
        """
        if self.provider_code != 'plutu':
            return super()._extract_amount_data(payment_data)

        if payment_data.get('amount') is None:
            # T-Lync signs only `approved` and `invoice_no` on the return, so
            # there is no amount here to check. Skipping is right: the signature
            # already proves the message is Plutu's, and the callback -- which
            # does carry the amount -- is checked.
            return None

        return {
            'amount': float(payment_data['amount']),
            # Only MPGS echoes a currency back. For the others there is nothing
            # to compare against, so the transaction's own currency is used and
            # the currency half of the check is a no-op.
            'currency_code': payment_data.get('currency') or self.currency_id.name,
            # Compare at the two decimals Plutu works to, not LYD's three.
            'precision_digits': 2,
        }

    def _apply_updates(self, payment_data):
        """Override of `payment` to update the transaction from Plutu data.

        Only ever reached through `_process`, which the controllers call after
        the callback's signature has been verified.

        Note: `self.ensure_one()` from `_process`

        :param dict payment_data: The payment data sent by the provider.
        :return: None
        """
        super()._apply_updates(payment_data)
        if self.provider_code != 'plutu':
            return

        if payment_data.get('transaction_id'):
            self.provider_reference = payment_data['transaction_id']

        # Plutu sends `approved` only when the payment went through and
        # `canceled` only when the customer backed out, so absence is not a
        # verdict: it means the payment is still in flight.
        if str(payment_data.get('approved', '')) == '1':
            self._set_done()
        elif str(payment_data.get('canceled', '')) == '1':
            self._set_canceled()
        else:
            self._set_pending()
