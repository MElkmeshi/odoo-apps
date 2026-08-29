def migrate(cr, version):
    """Keep existing tills on the on-screen flow they already have.

    New installs default to putting the QR on the receipt, but an install that
    has been showing a dialog at the till since 1.0.0 must not silently start
    closing sales before the customer has paid. Changing how money is taken is
    not something an upgrade gets to decide.

    Written in SQL on purpose. pos.payment.method.write() refuses any change
    while a POS session is open, and an upgrade cannot require every shop on
    the database to have closed its till first.
    """
    cr.execute(
        """
        UPDATE pos_payment_method
           SET numo_qr_display = 'screen'
         WHERE use_payment_terminal = 'numo_qr'
        """
    )
