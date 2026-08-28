import logging
from datetime import timedelta

from odoo import _, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment_onepay_ly import const


_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    onepay_session_id = fields.Char(
        string="OnePay Session Token",
        help="The short-lived bearer token returned by the gateway when the payment was "
             "initiated. It authenticates the OTP confirmation call.",
        groups='base.group_system',
        copy=False,
        readonly=True,
    )

    # === BUSINESS METHODS === #

    def _onepay_init(self, identity_card):
        """Initiate the payment and trigger the OTP SMS to the customer.

        Leaves the transaction in `draft` if the gateway refuses, so the
        customer can correct their identity card number and try again.

        :param str identity_card: The identity card number typed by the customer.
        :return: The length of the OTP the customer should expect.
        :rtype: int
        :raise ValidationError: If the gateway refuses the request.
        """
        self.ensure_one()

        if not identity_card:
            raise ValidationError(_("Please enter your identity card number."))
        if self.state != 'draft':
            raise ValidationError(_("This payment has already been initiated."))

        provider = self.provider_id
        bearer = provider._onepay_sign_in()
        data = provider._onepay_make_request(
            provider.onepay_init_path,
            {
                'amount': self.amount,
                'identityCard': provider._onepay_normalize_identity_card(identity_card),
                'transactionId': self.reference,
                'onlineOperation': 1,
            },
            bearer=bearer,
        )

        content = data.get('content')
        if not isinstance(content, dict) or not content.get('value') or not content.get('validTo'):
            if data.get('type') == const.RESPONSE_TYPE_ERROR:
                raise ValidationError(provider._onepay_get_error_message(
                    data, _("The payment could not be initiated.")
                ))
            _logger.error(
                "OnePay init returned no session token for transaction %s", self.reference
            )
            raise ValidationError(_("The payment could not be initiated."))

        self.sudo().onepay_session_id = content['value']
        self._set_pending()
        return const.OTP_LENGTH

    def _onepay_confirm(self, otp):
        """Confirm the payment with the OTP the customer received.

        :param str otp: The one-time password typed by the customer.
        :return: None
        :raise ValidationError: If the transaction is not awaiting an OTP.
        """
        self.ensure_one()

        if not otp:
            raise ValidationError(_("Please enter the one-time password."))
        session_id = self.sudo().onepay_session_id
        if not session_id:
            raise ValidationError(_("This payment has not been initiated yet."))
        if self.state != 'pending':
            raise ValidationError(_("This payment is no longer awaiting confirmation."))

        provider = self.provider_id
        data = provider._onepay_make_request(
            provider.onepay_complete_path, {'otp': otp}, bearer=session_id
        )

        if data.get('type') == const.RESPONSE_TYPE_SUCCESS:
            trace_id = data.get('traceId')
            if isinstance(trace_id, str):
                self.provider_reference = trace_id
            self._set_done()
        else:
            self._set_error(provider._onepay_get_error_message(
                data, _("The payment was declined.")
            ))

        # The session token is single-use; drop it once it has been spent.
        self.sudo().onepay_session_id = False

    def _onepay_check(self):
        """Reconcile a pending transaction against the gateway's report.

        Used when the customer abandoned the page after the OTP was sent, so
        no confirmation ever arrived. A transaction that cannot be matched is
        left pending rather than being failed, because the gateway's report is
        not authoritative about absence.

        :return: Whether the transaction was matched and set done.
        :rtype: bool
        """
        self.ensure_one()

        if self.state != 'pending':
            return False

        provider = self.provider_id
        bearer = provider._onepay_sign_in()
        created_at = self.create_date or fields.Datetime.now()
        window = timedelta(hours=const.REPORT_WINDOW_HOURS)
        data = provider._onepay_make_request(
            provider.onepay_report_path,
            {
                'fromDate': (created_at - window).isoformat(),
                'toDate': (created_at + window).isoformat(),
                'transactionType': 0,
                'providerTransactionId': self.reference,
                'page': 0,
            },
            bearer=bearer,
        )

        content = data.get('content')
        transactions = content.get('transactionList') if isinstance(content, dict) else None
        if not isinstance(transactions, list):
            transactions = []

        currency = self.currency_id
        for transaction in transactions:
            if not isinstance(transaction, dict):
                continue
            reported_amount = transaction.get('amount')
            if reported_amount is None:
                continue
            try:
                reported_amount = float(reported_amount)
            except (TypeError, ValueError):
                continue
            if currency.compare_amounts(reported_amount, self.amount) == 0:
                self._set_done()
                self.sudo().onepay_session_id = False
                return True

        self._log_message_on_linked_documents(
            _("No matching OnePay transaction was found for reference %s.", self.reference)
        )
        return False

    def action_onepay_check(self):
        """Reconcile the selected transactions from the backend form view."""
        for tx in self.filtered(lambda t: t.provider_code in const.ONEPAY_CODES):
            tx._onepay_check()

    def _cron_onepay_reconcile_pending(self):
        """Sweep pending OnePay transactions against the gateway's report.

        Transactions younger than `RECONCILE_MIN_AGE_MINUTES` are skipped to
        avoid racing a customer who is still typing their OTP. Transactions
        older than `RECONCILE_MAX_AGE_HOURS` are skipped so the sweep stays
        bounded.
        """
        now = fields.Datetime.now()
        transactions = self.search([
            ('provider_code', 'in', list(const.ONEPAY_CODES)),
            ('state', '=', 'pending'),
            ('create_date', '<=', now - timedelta(minutes=const.RECONCILE_MIN_AGE_MINUTES)),
            ('create_date', '>=', now - timedelta(hours=const.RECONCILE_MAX_AGE_HOURS)),
        ])
        for tx in transactions:
            try:
                tx._onepay_check()
            except Exception:
                # One unreachable gateway must not abort the whole sweep.
                _logger.exception(
                    "Could not reconcile OnePay transaction %s", tx.reference
                )
            else:
                self.env.cr.commit()
