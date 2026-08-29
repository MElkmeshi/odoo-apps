# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Payment Provider: Moamalat',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Payment Providers',
    'summary': "A payment provider for Moamalat (Libya).",
    'description': """
Moamalat Payment Provider
=========================

Takes card payments through Moamalat's Lightbox, the hosted card form used by
Libyan banks on the Moamalat network. The customer pays without leaving the
checkout, and the order is confirmed from Moamalat's signed webhook.
""",
    'author': 'Mohamed Elkmeshi',
    'support': 'elkmeshi2002@gmail.com',
    'depends': ['payment'],
    'data': [
        'views/payment_provider_views.xml',
        'views/payment_moamalat_templates.xml',
        'data/payment_provider_data.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'assets': {
        'web.assets_frontend': [
            'payment_moamalat/static/src/js/payment_form.js',
        ],
    },
    'application': False,
    'installable': True,
    'license': 'LGPL-3',
}
