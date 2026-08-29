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

    def _send_refund_request(self):
        """Override of `payment` to refund the transaction through Moamalat.

        In 19 this runs on the refund transaction itself, whose amount is
        negative and whose `source_transaction_id` carries the provider
        reference of the payment being reversed.

        Note: `self.ensure_one()` from `_refund`

        :return: None
        """
        super()._send_refund_request()
        if self.provider_code != 'moamalat':
            return

        amount = payment_utils.to_minor_currency_units(-self.amount, self.currency_id)
        response = self.provider_id._moamalat_refund_transaction(
            amount=amount,
            system_reference=self.source_transaction_id.provider_reference,
        )
        _logger.info(
            "Refund response for transaction %s:\n%s", self.reference, pprint.pformat(response)
        )

        if response.get('Success'):
            self.provider_reference = response.get('RefNumber')
            self._set_done()
        else:
            self._set_error("Moamalat: " + (response.get('Message') or _("The refund failed.")))

    def _search_by_reference(self, provider_code, payment_data):
        """Override of `payment` to find the transaction from Moamalat data.

        :param str provider_code: The code of the provider that handled the transaction.
        :param dict payment_data: The payment data sent by the provider.
        :return: The transaction, if found.
        :rtype: payment.transaction
        """
        tx = super()._search_by_reference(provider_code, payment_data)
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

    def _extract_amount_data(self, payment_data):
        """Override of `payment` to let Odoo check Moamalat's amount against ours.

        Without this override `_process` raises `KeyError: 'amount'` on every
        notification, because the base implementation returns an empty dict.

        Moamalat reports the amount in minor units and the currency as its ISO
        4217 number, so both are converted back before the comparison.

        :param dict payment_data: The payment data sent by the provider.
        :return: The amount data, or None to skip the check.
        :rtype: dict|None
        """
        if self.provider_code != 'moamalat':
            return super()._extract_amount_data(payment_data)

        amount = payment_data.get('Amount')
        currency_code = payment_data.get('Currency')
        if amount is None or currency_code is None:
            return None

        return {
            'amount': payment_utils.to_major_currency_units(float(amount), self.currency_id),
            'currency_code': const.CURRENCY_CODE_TO_NAME.get(
                str(currency_code), self.currency_id.name
            ),
        }

    def _apply_updates(self, payment_data):
        """Override of `payment` to update the transaction from Moamalat data.

        Only ever reached through `_process`, which the webhook calls after the
        notification's signature has been verified. Nothing that arrives via the
        customer's browser reaches this method.

        Note: `self.ensure_one()` from `_process`

        :param dict payment_data: The payment data sent by the provider.
        :return: None
        """
        super()._apply_updates(payment_data)
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
