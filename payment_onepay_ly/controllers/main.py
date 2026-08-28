import logging

from odoo import _, http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.payment_onepay_ly import const


_logger = logging.getLogger(__name__)


class OnePayController(http.Controller):
    _init_url = '/payment/onepay_ly/init'
    _confirm_url = '/payment/onepay_ly/confirm'

    def _get_transaction(self, reference):
        """Resolve the transaction the customer is paying.

        :param str reference: The transaction reference.
        :return: The transaction, as sudo.
        :rtype: recordset of `payment.transaction`
        :raise ValidationError: If no OnePay transaction matches the reference.
        """
        tx_sudo = request.env['payment.transaction'].sudo().search([
            ('reference', '=', reference),
            ('provider_code', 'in', list(const.ONEPAY_CODES)),
        ], limit=1)
        if not tx_sudo:
            raise ValidationError(_("No transaction found matching the reference."))
        return tx_sudo

    @http.route(_init_url, type='json', auth='public')
    def onepay_init(self, reference, identity_card, **kwargs):
        """Initiate the payment and trigger the OTP SMS.

        Errors are returned in the payload rather than raised, so the inline
        form can show them and let the customer retry without losing the page.

        :param str reference: The transaction reference.
        :param str identity_card: The identity card number typed by the customer.
        :return: The OTP length on success, or an error message.
        :rtype: dict
        """
        try:
            tx_sudo = self._get_transaction(reference)
            otp_length = tx_sudo._onepay_init(identity_card)
        except ValidationError as e:
            return {'error': str(e)}
        except Exception:
            _logger.exception("OnePay init failed for reference %s", reference)
            return {'error': _("The payment could not be initiated. Please try again.")}
        return {'otp_length': otp_length}

    @http.route(_confirm_url, type='json', auth='public')
    def onepay_confirm(self, reference, otp, **kwargs):
        """Confirm the payment with the customer's OTP.

        :param str reference: The transaction reference.
        :param str otp: The one-time password typed by the customer.
        :return: The route to land on, or an error message.
        :rtype: dict
        """
        try:
            tx_sudo = self._get_transaction(reference)
            tx_sudo._onepay_confirm(otp)
        except ValidationError as e:
            return {'error': str(e)}
        except Exception:
            _logger.exception("OnePay confirmation failed for reference %s", reference)
            return {'error': _("The payment could not be confirmed. Please try again.")}
        return {'redirect_url': '/payment/status'}
