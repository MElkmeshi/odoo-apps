import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


# The institution code is 3 digits (e.g. 024 for Al Nuran Bank).
BANK_CODE_RE = re.compile(r'^\d{3}$')
# Merchant category code, ISO 18245. 9999 is the catch-all.
MCC_RE = re.compile(r'^\d{4}$')
# Libyan IBANs are LY followed by 23 digits.
IBAN_RE = re.compile(r'^LY\d{23}$')


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    numo_account_name = fields.Char(
        string="Account Holder Name",
        help="Name on the receiving account, as registered with the bank. Goes in tag 27.",
    )
    numo_iban = fields.Char(
        string="IBAN",
        help="The receiving account. Spaces are ignored. Goes in tag 29.",
    )
    numo_bank_code = fields.Char(
        string="Bank Code",
        help="The 3-digit institution code issued by the Central Bank of Libya, "
             "e.g. 024 for Al Nuran Bank. Goes in tag 30.",
    )
    numo_merchant_name = fields.Char(
        string="Merchant Name",
        help="The shop name the customer sees in their banking app. Goes in tag 59.",
    )
    numo_city = fields.Char(
        string="City",
        help="Merchant city. Goes in tag 60.",
    )
    numo_mcc = fields.Char(
        string="Merchant Category Code",
        default='9999',
        help="ISO 18245 category code, e.g. 5411 for supermarkets. 9999 means "
             "uncategorised and is accepted. Goes in tag 52.",
    )
    numo_merchant_account = fields.Char(
        string="Merchant Account Number",
        help="Optional merchant number issued by the acquirer. Goes in tag 02. "
             "Leave empty unless your bank told you to fill it in.",
    )

    # === CONSTRAINT METHODS === #

    @api.constrains(
        'use_payment_terminal', 'numo_iban', 'numo_bank_code', 'numo_mcc',
        'numo_account_name', 'numo_merchant_name', 'numo_city',
    )
    def _check_numo_fields(self):
        """Reject an unusable NUMO configuration at save time.

        A malformed IBAN or bank code still produces a scannable QR: it just
        encodes the wrong destination, and nobody finds out until a customer
        has paid someone else. Catching it here is the whole point.
        """
        required = {
            'numo_account_name': _("Account Holder Name"),
            'numo_iban': _("IBAN"),
            'numo_bank_code': _("Bank Code"),
            'numo_merchant_name': _("Merchant Name"),
            'numo_city': _("City"),
        }
        for method in self:
            if method.use_payment_terminal != 'numo_qr':
                continue

            missing = [label for name, label in required.items() if not method[name]]
            if missing:
                raise ValidationError(
                    _("NUMO QR needs these fields filled in: %s", ", ".join(missing))
                )
            if not IBAN_RE.match((method.numo_iban or '').replace(' ', '').upper()):
                raise ValidationError(
                    _("The IBAN must be LY followed by 23 digits.")
                )
            if not BANK_CODE_RE.match(method.numo_bank_code or ''):
                raise ValidationError(
                    _("The bank code must be exactly 3 digits, e.g. 024.")
                )
            if method.numo_mcc and not MCC_RE.match(method.numo_mcc):
                raise ValidationError(
                    _("The merchant category code must be exactly 4 digits, e.g. 5411.")
                )

    # === BUSINESS METHODS === #

    def _get_payment_terminal_selection(self):
        """Override of `point_of_sale` to offer NUMO QR as a terminal."""
        return super()._get_payment_terminal_selection() + [('numo_qr', "NUMO QR")]

    @api.model
    def _load_pos_data_fields(self, config):
        """Override of `point_of_sale` to ship the NUMO config to the browser.

        The payload is built client-side so the till keeps working without a
        connection, which means these fields have to travel with the session.
        None of them are secret: every one of them ends up in the QR code the
        customer scans.
        """
        return super()._load_pos_data_fields(config) + [
            'numo_account_name', 'numo_iban', 'numo_bank_code',
            'numo_merchant_name', 'numo_city', 'numo_mcc', 'numo_merchant_account',
        ]
