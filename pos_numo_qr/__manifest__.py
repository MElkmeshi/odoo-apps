{
    'name': 'POS NUMO QR (Libya)',
    'version': '18.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'summary': "Show a NUMO / LYPay payment QR code on the POS payment screen.",
    'description': """
POS NUMO QR
===========
Adds a payment method that displays a NUMO QR code at the till. The customer
scans it with their Libyan banking app and pays; the cashier confirms.

NUMO is the national QR payment standard of the Central Bank of Libya, an
EMVCo-style Tag-Length-Value format used by LYPay.
    """,
    'author': 'Mohamed Elkmeshi',
    'support': 'elkmeshi2002@gmail.com',
    'depends': ['point_of_sale'],
    'data': [
        'views/pos_payment_method_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_numo_qr/static/src/**/*',
        ],
        'web.assets_unit_tests': [
            'pos_numo_qr/static/tests/**/*',
        ],
    },
    'application': False,
    'installable': True,
    'license': 'LGPL-3',
}
