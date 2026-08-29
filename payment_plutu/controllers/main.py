# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import pprint

from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.http import request


_logger = logging.getLogger(__name__)


class PlutuController(http.Controller):
    _return_url = '/payment/plutu/return'
    _webhook_url = '/payment/plutu/webhook'

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
        tx_sudo = request.env['payment.transaction'].sudo()._search_by_reference('plutu', data)

        gateway = tx_sudo.payment_method_id.code
        if not tx_sudo.provider_id._plutu_verify_signature(gateway, channel, data):
            _logger.warning(
                "Received a Plutu %s for %s with an invalid signature.",
                channel, tx_sudo.reference,
            )
            raise Forbidden()

        request.env['payment.transaction'].sudo()._process('plutu', data)
