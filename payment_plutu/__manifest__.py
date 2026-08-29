# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Payment Provider: Plutu',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Payment Providers',
    'summary': "A payment provider for Plutu (Libya).",
    'description': """
Plutu Payment Provider
======================

Takes payments through Plutu, the Libyan payment aggregator. The customer is
sent to Plutu to pay by local bank card or T-Lync, and the order is confirmed
from Plutu's signed callback.
""",
    'author': 'Mohamed Elkmeshi',
    'support': 'elkmeshi2002@gmail.com',
    'website': 'https://plutu.ly/',
    'depends': ['payment'],
    'data': [
        'views/payment_plutu_templates.xml',
        'views/payment_provider_views.xml',
        'data/payment_method_data.xml',
        'data/payment_provider_data.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'payment_plutu/static/src/js/payment_form.js',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'application': False,
    'installable': True,
    'license': 'LGPL-3',
}
