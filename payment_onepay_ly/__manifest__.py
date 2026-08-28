{
    'name': 'Payment Provider: OnePay',
    'version': '17.0.1.0.0',
    'category': 'Accounting/Payment Providers',
    'summary': "A payment provider for OnePay mobile wallets (Libya).",
    'description': """
OnePay Payment Provider
=======================
Integrates the OnePay wallet gateway and its branded deployments
(Musrefy Pay, Yussor Online, Sahara Pay) with Odoo.

The customer enters their identity card number, receives a one-time password
by SMS, and confirms the payment with it. Pending transactions can be
reconciled against OnePay's transaction report.
    """,
    'author': 'Mohamed Elkmeshi',
    'support': 'elkmeshi2002@gmail.com',
    'depends': ['payment'],
    'data': [
        'views/payment_onepay_ly_templates.xml',
        'views/payment_provider_views.xml',
        'views/payment_transaction_views.xml',
        'data/payment_method_data.xml',
        'data/payment_provider_data.xml',
        'data/ir_cron_data.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'assets': {
        'web.assets_frontend': [
            'payment_onepay_ly/static/src/js/payment_form.js',
        ],
    },
    'application': False,
    'installable': True,
    'license': 'LGPL-3',
}
