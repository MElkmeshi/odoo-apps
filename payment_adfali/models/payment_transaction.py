# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import _, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment_adfali import const


_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    adfali_session_id = fields.Char(
        string="Adfali Session ID",
        help="The session id returned by the gateway when the payment was initiated. It "
             "identifies the payment during PIN confirmation.",
        groups='base.group_system',
        copy=False,
        readonly=True,
    )

    # === BUSINESS METHODS === #

    def _adfali_init(self, mobile):
        """Initiate the payment and trigger the PIN SMS to the customer.

        Leaves the transaction in `draft` if the gateway refuses, so the
        customer can correct their mobile number and try again.

        :param str mobile: The mobile number typed by the customer.
        :return: The length of the PIN the customer should expect.
        :rtype: int
        :raise ValidationError: If the gateway refuses the request.
        """
        self.ensure_one()

        if not mobile:
            raise ValidationError(_("Please enter your mobile number."))
        if self.state != 'draft':
            raise ValidationError(_("This payment has already been initiated."))

        provider = self.provider_id
        session_id = provider._adfali_initiate(
            provider._adfali_normalize_mobile(mobile), self.amount
        )

        self.sudo().adfali_session_id = session_id
        self._set_pending()
        return const.OTP_LENGTH

    def _adfali_confirm(self, otp):
        """Confirm the payment with the PIN the customer received.

        :param str otp: The PIN typed by the customer.
        :return: None
        :raise ValidationError: If the transaction is not awaiting a PIN.
        """
        self.ensure_one()

        if not otp:
            raise ValidationError(_("Please enter the PIN sent to your mobile number."))
        session_id = self.sudo().adfali_session_id
        if not session_id:
            raise ValidationError(_("This payment has not been initiated yet."))
        if self.state != 'pending':
            raise ValidationError(_("This payment is no longer awaiting confirmation."))

        provider = self.provider_id
        # A transport failure is deliberately left to propagate: it leaves the
        # transaction pending and retryable, rather than failing a payment that
        # the gateway may never have seen. Only an answered-and-refused PIN is
        # an error state.
        accepted = provider._adfali_confirm(session_id, otp)

        if accepted:
            # Adfali returns no transaction identifier, so the session id is the
            # only handle support has for reconciling against the gateway.
            self.provider_reference = session_id
            self._set_done()
        else:
            self._set_error(_("The PIN was rejected. The payment was not completed."))
