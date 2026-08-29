# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import pprint

from odoo import _, models
from odoo.exceptions import ValidationError

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment_moamalat import const


_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _get_specific_processing_values(self, processing_values):
        """Override of `payment` to return the Moamalat-specific processing values.

        Note: `self.ensure_one()` from `_get_processing_values`

        :param dict processing_values: The generic processing values.
        :return: The provider-specific processing values.
        :rtype: dict
        """
        res = super()._get_specific_processing_values(processing_values)
        if self.provider_code != 'moamalat':
            return res

        amount = payment_utils.to_minor_currency_units(self.amount, self.currency_id)
        hash_data = self.provider_id._moamalat_generate_secure_hash(
            amount=amount, merchant_reference=self.reference,
        )
        return {
            'amount': amount,
            'merchant_reference': self.reference,
            'secure_hash': hash_data['secure_hash'],
            'datetime_local': hash_data['datetime_local'],
            'merchant_id': self.provider_id.moamalat_merchant_id,
            'terminal_id': self.provider_id.moamalat_terminal_id,
        }

    def _send_refund_request(self, amount_to_refund=None):
        """Override of `payment` to refund the transaction through Moamalat.

        In 18 `super()` creates and returns the refund transaction, and this
        method operates on that child rather than on `self`.

        Note: `self.ensure_one()`

        :param float amount_to_refund: The amount to refund.
        :return: The refund transaction.
        :rtype: payment.transaction
        """
        refund_tx = super()._send_refund_request(amount_to_refund=amount_to_refund)
        if self.provider_code != 'moamalat':
            return refund_tx

        amount = payment_utils.to_minor_currency_units(
            -refund_tx.amount,  # Refund transactions' amount is negative, inverse it.
            refund_tx.currency_id,
        )
        response = self.provider_id._moamalat_refund_transaction(
            amount=amount, system_reference=self.provider_reference,
        )
        _logger.info(
            "Refund response for transaction %s:\n%s", self.reference, pprint.pformat(response)
        )

        if response.get('Success'):
            refund_tx.provider_reference = response.get('RefNumber')
            refund_tx._set_done()
        else:
            refund_tx._set_error(
                "Moamalat: " + (response.get('Message') or _("The refund failed."))
            )
        return refund_tx

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """Override of `payment` to find the transaction from Moamalat data.

        :param str provider_code: The code of the provider that handled the transaction.
        :param dict notification_data: The notification data sent by the provider.
        :return: The transaction, if found.
        :rtype: payment.transaction
        """
        payment_data = notification_data
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != 'moamalat' or len(tx) == 1:
            return tx

        reference = payment_data.get('MerchantReference')
        if not reference:
            raise ValidationError(
                "Moamalat: " + _("Received data with missing merchant reference.")
            )

        tx = self.search([('reference', '=', reference), ('provider_code', '=', 'moamalat')])
        if not tx:
            raise ValidationError(
                "Moamalat: " + _("No transaction found matching reference %s.", reference)
            )
        return tx

    def _process_notification_data(self, notification_data):
        """Override of `payment` to update the transaction from Moamalat data.

        Only ever reached through `_handle_notification_data`, which the webhook
        calls after the notification's signature has been verified. Nothing that
        arrives via the customer's browser reaches this method.

        Note: `self.ensure_one()` from `_handle_notification_data`

        :param dict notification_data: The notification data sent by the provider.
        :return: None
        """
        payment_data = notification_data
        super()._process_notification_data(notification_data)
        if self.provider_code != 'moamalat':
            return

        action_code = payment_data.get('ActionCode')
        txn_type = payment_data.get('TxnType')

        self.provider_reference = (
            payment_data.get('SystemReference') or payment_data.get('NetworkReference')
        )

        _logger.info(
            "Applying Moamalat updates to transaction %s: ActionCode=%s, TxnType=%s",
            self.reference, action_code, txn_type,
        )

        if action_code != const.ACTION_CODE_APPROVED:
            self._set_error("Moamalat: " + (
                payment_data.get('Message') or _("The payment was declined.")
            ))
        elif txn_type in (const.TXN_TYPE_VOID_SALE, const.TXN_TYPE_VOID_REFUND):
            self._set_canceled()
        else:
            self._set_done()
