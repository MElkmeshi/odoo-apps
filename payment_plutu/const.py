# Part of Odoo. See LICENSE file for full copyright and licensing details.

# The gateways this module implements. Both are redirect flows: Plutu returns a
# URL, the customer pays there, and Plutu reports the result back.
#
# Plutu's other two gateways, Sadad (`sadadapi`) and Adfali (`edfali`), are
# deliberately absent. They are not redirect flows: each needs a `verify` call
# that texts the customer a one-time code, then a `confirm` call carrying that
# code back. Listing them here without building that exchange would strand the
# customer after the first step.
DEFAULT_PAYMENT_METHODS_CODES = [
    'localbankcards',
    'tlync',
    'mpgs',
]

# Plutu settles in Libyan Dinar.
SUPPORTED_CURRENCIES = {
    'LYD',
}

# The parameters Plutu signs, per gateway and per channel.
#
# These are not interchangeable. Taken from Plutu's own PHP SDK
# (getplutu/plutu-php, `callbackHandler` and `returnHandler` on each service):
# T-Lync signs a different set on the return than on the callback, and unlike
# Local Bank Cards it does not sign `canceled` at all. Verifying a T-Lync
# return against the Local Bank Cards set fails every time.
SIGNED_PARAMETERS = {
    ('localbankcards', 'return'): [
        'gateway', 'approved', 'canceled', 'invoice_no', 'amount', 'transaction_id',
    ],
    ('localbankcards', 'callback'): [
        'gateway', 'approved', 'canceled', 'invoice_no', 'amount', 'transaction_id',
    ],
    ('tlync', 'return'): [
        'approved', 'invoice_no',
    ],
    ('tlync', 'callback'): [
        'gateway', 'approved', 'invoice_no', 'amount', 'transaction_id', 'payment_method',
    ],
    # MPGS is the only gateway that signs `currency`.
    ('mpgs', 'return'): [
        'gateway', 'approved', 'canceled', 'amount', 'currency', 'invoice_no', 'transaction_id',
    ],
    ('mpgs', 'callback'): [
        'gateway', 'approved', 'canceled', 'amount', 'currency', 'invoice_no', 'transaction_id',
    ],
}

# The gateways whose `confirm` call requires a mobile number and an explicit
# callback URL. The others reject neither, but Plutu's SDK does not send them.
GATEWAYS_REQUIRING_MOBILE = {'tlync'}
