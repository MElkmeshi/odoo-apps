# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import pprint

from werkzeug.exceptions import Forbidden

from odoo import _, http
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.tools import consteq, hmac as hmac_tool



_logger = logging.getLogger(__name__)


class PlutuController(http.Controller):
    _return_url = '/payment/plutu/return'
    _webhook_url = '/payment/plutu/webhook'
    _otp_send_url = '/payment/plutu/otp/send'
    _otp_confirm_url = '/payment/plutu/otp/confirm'

    @staticmethod
    def _get_otp_transaction(reference, access_token):
        """Resolve the transaction behind a one-time-code request.

        The token is checked before anything else. These routes are public and
        `_plutu_otp_send` makes Plutu send a real SMS, so without it a stranger
        who guessed a reference could have a customer's phone buzzed at will --
        and could burn the merchant's SMS allowance doing it.

        :param str reference: The transaction reference.
        :param str access_token: The token issued with the processing values.
        :return: The transaction, as sudo.
        :rtype: payment.transaction
        :raise Forbidden: If the token does not match the reference.
        """
        expected = hmac_tool(request.env(su=True), 'plutu_otp_flow', reference)
        if not access_token or not consteq(access_token, expected):
            _logger.warning("Plutu code request for %s with a bad token.", reference)
            raise Forbidden()

        tx_sudo = request.env['payment.transaction'].sudo().search([
            ('reference', '=', reference),
            ('provider_code', '=', 'plutu'),
        ], limit=1)
        if not tx_sudo:
            raise Forbidden()
        return tx_sudo

    @http.route(_otp_send_url, type='json', auth='public')
    def plutu_otp_send(self, reference, access_token, mobile_number, birth_year=None, **kwargs):
        """Ask Plutu to text the customer a one-time code.

        Errors come back in the payload rather than as exceptions so the inline
        form can show them and let the customer correct a typo without losing
        the page.

        :param str reference: The transaction reference.
        :param str access_token: The token issued with the processing values.
        :param str mobile_number: The mobile number the customer typed.
        :param str birth_year: The birth year, for Sadad.
        :return: The code length, or an error message.
        :rtype: dict
        """
        tx_sudo = self._get_otp_transaction(reference, access_token)
        try:
            code_length = tx_sudo._plutu_otp_send(mobile_number, birth_year=birth_year)
        except ValidationError as e:
            return {'error': str(e)}
        except Exception:
            _logger.exception("Plutu code request failed for %s", reference)
            return {'error': _("The code could not be sent. Please try again.")}
        return {'code_length': code_length}

    @http.route(_otp_confirm_url, type='json', auth='public')
    def plutu_otp_confirm(self, reference, access_token, code, **kwargs):
        """Spend the one-time code and settle the payment.

        :param str reference: The transaction reference.
        :param str access_token: The token issued with the processing values.
        :param str code: The code the customer typed.
        :return: Where to send the customer, or an error message.
        :rtype: dict
        """
        tx_sudo = self._get_otp_transaction(reference, access_token)
        try:
            tx_sudo._plutu_otp_confirm(code)
        except ValidationError as e:
            return {'error': str(e)}
        except Exception:
            _logger.exception("Plutu confirmation failed for %s", reference)
            return {'error': _("The payment could not be confirmed. Please try again.")}
        return {'redirect_url': '/payment/status'}

    @http.route(_return_url, type='http', methods=['GET'], auth='public')
    def plutu_return_from_payment(self, **data):
        """Handle the customer coming back from Plutu.

        :param dict data: The signed return data.
        """
        _logger.info("Handling redirection from Plutu with data:\n%s", pprint.pformat(data))
        self._plutu_process('return', data)
        return request.redirect('/payment/status')

    @http.route(_webhook_url, type='http', methods=['GET', 'POST'], auth='public', csrf=False)
    def plutu_webhook(self, **data):
        """Handle the server-to-server notification from Plutu.

        Plutu calls this with GET and the same query string as the redirect;
        POST is accepted too so a change of transport does not silently drop
        confirmations.

        :param dict data: The signed notification data.
        :return: An empty acknowledgement.
        :rtype: Response
        """
        _logger.info("Notification received from Plutu with data:\n%s", pprint.pformat(data))
        self._plutu_process('callback', data)
        return request.make_json_response('')

    @staticmethod
    def _plutu_process(channel, data):
        """Verify a Plutu callback and apply it to its transaction.

        The transaction is looked up before the signature is checked, because
        the signature can only be rebuilt once the gateway is known and the
        gateway comes from the transaction's payment method. `gateway` does
        arrive in the query string, but it is attacker-controlled until the
        signature is verified, and T-Lync does not even sign it on the return.

        Looking the provider up from the transaction also keeps this correct on
        a multi-company database, where a blind search for the Plutu provider
        returns more than one record.

        :param str channel: Either `return` or `callback`.
        :param dict data: The callback parameters.
        :raise Forbidden: If the signature does not verify.
        """
        tx_sudo = request.env['payment.transaction'].sudo()\
            ._get_tx_from_notification_data('plutu', data)

        gateway = tx_sudo.payment_method_id.code
        if not tx_sudo.provider_id._plutu_verify_signature(gateway, channel, data):
            _logger.warning(
                "Received a Plutu %s for %s with an invalid signature.",
                channel, tx_sudo.reference,
            )
            raise Forbidden()

        tx_sudo._handle_notification_data('plutu', data)
