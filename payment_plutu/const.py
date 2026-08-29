# Part of Odoo. See LICENSE file for full copyright and licensing details.

# The gateways that hand the customer to Plutu and report back with a signed
# callback.
REDIRECT_GATEWAYS = ['localbankcards', 'tlync', 'mpgs']

# The gateways that run entirely over the API: `verify` texts the customer a
# one-time code, `confirm` spends it. There is no redirect and no callback, so
# nothing is signed and the result is whatever `confirm` returns.
OTP_GATEWAYS = ['edfali', 'sadadapi']

DEFAULT_PAYMENT_METHODS_CODES = REDIRECT_GATEWAYS + OTP_GATEWAYS

# Per-gateway rules for the OTP flow, taken from Plutu's PHP SDK
# (`PlutuValidationTrait`). They genuinely differ: Adfali accepts any 09[1-6]
# number and a 4-digit code, Sadad only 091/093 and a 6-digit code, and Sadad
# alone asks for a birth year. Validating here means a mistyped number is
# caught before it costs an SMS.
OTP_GATEWAY_RULES = {
    'edfali': {
        'mobile_pattern': r'^09[1-6][0-9]{7}$',
        'mobile_hint': "09XXXXXXXX",
        'code_length': 4,
        'requires_birth_year': False,
    },
    'sadadapi': {
        'mobile_pattern': r'^09[13][0-9]{7}$',
        'mobile_hint': "091XXXXXXX or 093XXXXXXX",
        'code_length': 6,
        'requires_birth_year': True,
    },
}

# Sadad's accepted birth years, per the SDK: 1940 through this year minus 12.
BIRTH_YEAR_MIN = 1940
BIRTH_YEAR_MAX_OFFSET = 12

# Plutu rejects an invoice number containing anything outside this set, so a
# reference like "INV/2026/0001" has to be rewritten before it is sent.
INVOICE_NO_PATTERN = r'^[A-Za-z0-9.\-_]+$'

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
