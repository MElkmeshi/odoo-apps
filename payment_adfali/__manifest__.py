{
    'name': 'Payment Provider: Adfali',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Payment Providers',
    'summary': "A payment provider for Adfali mobile wallet (Libya).",
    'description': """
Adfali Payment Provider
=======================
Integrates the Adfali mobile wallet with Odoo over its SOAP API.

The customer enters their mobile number, receives a 4-digit PIN by SMS, and
confirms the payment with it.
    """,
    'author': 'Mohamed Elkmeshi',
    'support': 'elkmeshi2002@gmail.com',
    'depends': ['payment'],
    'data': [
        'views/payment_adfali_templates.xml',
        'views/payment_provider_views.xml',
        'data/payment_method_data.xml',
        'data/payment_provider_data.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'assets': {
        'web.assets_frontend': [
            'payment_adfali/static/src/interactions/**/*',
        ],
    },
    'application': False,
    'installable': True,
    'license': 'LGPL-3',
}
