from odoo import api, SUPERUSER_ID

from odoo.addons.pos_numo_qr import const


def migrate(cr, version):
    """Point the new Bank selector at whatever code the method already holds.

    Without this, an install that has been happily encoding 024 since 1.0.0
    reopens with an empty required dropdown, and the merchant has to work out
    which bank 024 was. A code the list does not know becomes 'Other', which
    leaves the code itself untouched.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    methods = env['pos.payment.method'].search([('use_payment_terminal', '=', 'numo_qr')])
    for method in methods:
        code = (method.numo_bank_code or '').strip()
        if not code:
            continue
        method.numo_bank = code if code in const.BANK_CODES else const.BANK_OTHER
