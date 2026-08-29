from odoo.addons.pos_numo_qr import const


def migrate(cr, version):
    """Point the new Bank selector at whatever code the method already holds.

    Without this, an install that has been happily encoding 024 since 1.0.0
    reopens with an empty required dropdown, and the merchant has to work out
    which bank 024 was. A code the list does not know becomes 'Other', which
    leaves the code itself untouched.

    Written in SQL on purpose. pos.payment.method.write() refuses any change
    while a POS session is open, and an upgrade cannot require every shop on
    the database to have closed its till first.
    """
    cr.execute(
        """
        UPDATE pos_payment_method
           SET numo_bank = CASE
                   WHEN numo_bank_code IN %s THEN numo_bank_code
                   ELSE %s
               END
         WHERE use_payment_terminal = 'numo_qr'
           AND numo_bank IS NULL
           AND COALESCE(TRIM(numo_bank_code), '') <> ''
        """,
        (tuple(sorted(const.BANK_CODES)), const.BANK_OTHER),
    )
