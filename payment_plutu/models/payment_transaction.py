# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from odoo import _, models
from odoo.exceptions import ValidationError

from odoo.addons.payment_plutu import const


_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _get_specific_rendering_values(self, processing_values):
        """Override of `payment` to open the payment with Plutu and redirect.

        Note: `self.ensure_one()` from `_get_processing_values`

        :param dict processing_values: The generic processing values.
        :return: The provider-specific rendering values.
        :rtype: dict
        """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'plutu':
            return res

        gateway = self.payment_method_id.code
        base_url = self.provider_id.get_base_url()

        # Plutu accepts at most two decimal places. LYD carries three in Odoo, so
        # an amount like 10.555 is not merely a formatting problem: Plutu cannot
        # charge it. Refusing beats quietly rounding the customer's total.
        if round(self.amount, 2) != round(self.amount, 6):
            raise ValidationError("Plutu: " + _(
                "Plutu accepts at most two decimal places, so %(amount)s cannot be charged"
                " exactly.", amount=self.amount,
            ))

        payload = {
            'amount': f'{self.amount:.2f}',
            'invoice_no': self.reference,
            'return_url': f'{base_url}/payment/plutu/return',
            'lang': (self.partner_lang or 'en')[:2],
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

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """Override of `payment` to find the transaction from Plutu data.

        :param str provider_code: The code of the provider that handled the transaction.
        :param dict notification_data: The notification data sent by the provider.
        :return: The transaction, if found.
        :rtype: payment.transaction
        """
        payment_data = notification_data
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
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

    def _process_notification_data(self, notification_data):
        """Override of `payment` to update the transaction from Plutu data.

        Only ever reached through `_handle_notification_data`, which the
        controllers call after the callback's signature has been verified.

        Note: `self.ensure_one()` from `_handle_notification_data`

        :param dict notification_data: The notification data sent by the provider.
        :return: None
        """
        payment_data = notification_data
        super()._process_notification_data(notification_data)
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
