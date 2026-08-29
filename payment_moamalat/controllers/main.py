# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import pprint

from odoo import http
from odoo.http import request


_logger = logging.getLogger(__name__)


class MoamalatController(http.Controller):
    _return_url = '/payment/moamalat/return'
    _webhook_url = '/payment/moamalat/webhook'
    _callback_url = '/payment/moamalat/callback'

    @http.route(_return_url, type='http', methods=['GET', 'POST'], auth='public', csrf=False)
    def moamalat_return(self, **data):
        """Send the customer back to the payment status page.

        Deliberately does not touch the transaction. Whatever arrives here comes
        through the customer's browser, so it is a claim about a payment, not
        evidence of one. Only `_webhook_url` -- which Moamalat signs and we
        verify -- is allowed to move a transaction's state.

        :param dict data: The return data, logged but not trusted.
        """
        _logger.info("Moamalat return with data:\n%s", pprint.pformat(data))
        return request.redirect('/payment/status')

    @http.route(_callback_url, type='jsonrpc', auth='public', methods=['POST'])
    def moamalat_callback(self, reference, **data):
        """Acknowledge the Lightbox result reported by the customer's browser.

        The Lightbox reports its outcome client-side, so this endpoint is
        reachable by anyone who can guess a transaction reference. It therefore
        records that the customer finished the flow and nothing more: the
        transaction is left pending until the signed webhook confirms it.

        Marking the transaction paid from here would let an anonymous request
        settle an order without money moving.

        :param str reference: The transaction reference.
        :param dict data: The Lightbox result, logged but not trusted.
        :return: The URL to send the customer to.
        :rtype: dict
        """
        _logger.info(
            "Moamalat client callback for reference %s:\n%s", reference, pprint.pformat(data)
        )

        tx_sudo = request.env['payment.transaction'].sudo().search([
            ('reference', '=', reference),
            ('provider_code', '=', 'moamalat'),
        ], limit=1)

        # Say nothing about whether the reference exists: this route is public,
        # so answering would turn it into a reference oracle.
        if tx_sudo and tx_sudo.state == 'draft':
            tx_sudo._set_pending()

        return {'redirect_url': '/payment/status'}

    @http.route(_webhook_url, type='http', methods=['POST'], auth='public', csrf=False)
    def moamalat_webhook(self):
        """Process a signed transaction notification from Moamalat.

        This is the only path that may change a transaction's state, and it does
        so only after the notification's HMAC has been checked against the
        provider's notification key.

        :return: An acknowledgement for Moamalat.
        :rtype: Response
        """
        try:
            data = request.get_json_data()
        except Exception:  # noqa: BLE001 - Moamalat may post form-encoded instead.
            data = dict(request.httprequest.form)

        _logger.info("Moamalat webhook received:\n%s", pprint.pformat(data))

        merchant_id = data.get('MerchantId')
        terminal_id = data.get('TerminalId')

        if not data.get('MerchantReference'):
            _logger.warning("Moamalat webhook without MerchantReference")
            return request.make_json_response({'Message': 'Missing MerchantReference',
                                               'Success': False})

        provider_sudo = request.env['payment.provider'].sudo().search([
            ('code', '=', 'moamalat'),
            ('moamalat_merchant_id', '=', merchant_id),
            ('moamalat_terminal_id', '=', terminal_id),
        ], limit=1)
        if not provider_sudo:
            _logger.warning(
                "Moamalat webhook: no provider for MID=%s, TID=%s", merchant_id, terminal_id
            )
            return request.make_json_response({'Message': 'Provider not found', 'Success': False})

        if not provider_sudo._moamalat_verify_notification_hash(data):
            # Refused before `_process`, so an unsigned body can never reach the
            # transaction. Passing a "verified" flag inwards instead would put
            # the check one forgotten branch away from being bypassed.
            _logger.warning(
                "Moamalat webhook with an invalid signature for reference %s; ignored.",
                data.get('MerchantReference'),
            )
            return request.make_json_response({'Message': 'Invalid signature', 'Success': False})

        try:
            request.env['payment.transaction'].sudo()._process('moamalat', data)
        except ValueError:
            _logger.exception("Unable to process the Moamalat webhook data.")
            return request.make_json_response({'Message': 'Unknown transaction', 'Success': False})

        return request.make_json_response({'Message': 'Success', 'Success': True})
