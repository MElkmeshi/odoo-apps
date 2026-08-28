import logging

from odoo import _, http
from odoo.exceptions import ValidationError
from odoo.http import request


_logger = logging.getLogger(__name__)


class AdfaliController(http.Controller):
    _init_url = '/payment/adfali/init'
    _confirm_url = '/payment/adfali/confirm'

    def _get_transaction(self, reference):
        """Resolve the transaction the customer is paying.

        :param str reference: The transaction reference.
        :return: The transaction, as sudo.
        :rtype: recordset of `payment.transaction`
        :raise ValidationError: If no Adfali transaction matches the reference.
        """
        tx_sudo = request.env['payment.transaction'].sudo().search([
            ('reference', '=', reference),
            ('provider_code', '=', 'adfali'),
        ], limit=1)
        if not tx_sudo:
            raise ValidationError(_("No transaction found matching the reference."))
        return tx_sudo

    @http.route(_init_url, type='jsonrpc', auth='public')
    def adfali_init(self, reference, mobile, **kwargs):
        """Initiate the payment and trigger the PIN SMS.

        Errors are returned in the payload rather than raised, so the inline
        form can show them and let the customer retry without losing the page.

        :param str reference: The transaction reference.
        :param str mobile: The mobile number typed by the customer.
        :return: The PIN length on success, or an error message.
        :rtype: dict
        """
        try:
            tx_sudo = self._get_transaction(reference)
            otp_length = tx_sudo._adfali_init(mobile)
        except ValidationError as e:
            return {'error': str(e)}
        except Exception:
            _logger.exception("Adfali init failed for reference %s", reference)
            return {'error': _("The payment could not be initiated. Please try again.")}
        return {'otp_length': otp_length}

    @http.route(_confirm_url, type='jsonrpc', auth='public')
    def adfali_confirm(self, reference, otp, **kwargs):
        """Confirm the payment with the customer's PIN.

        :param str reference: The transaction reference.
        :param str otp: The PIN typed by the customer.
        :return: The route to land on, or an error message.
        :rtype: dict
        """
        try:
            tx_sudo = self._get_transaction(reference)
            tx_sudo._adfali_confirm(otp)
        except ValidationError as e:
            return {'error': str(e)}
        except Exception:
            _logger.exception("Adfali confirmation failed for reference %s", reference)
            return {'error': _("The payment could not be confirmed. Please try again.")}
        return {'redirect_url': '/payment/status'}
