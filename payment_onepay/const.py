# The provider codes served by this module. They all speak the same API and
# differ only in credentials and in the identity card prefix below.
ONEPAY_CODES = ('onepay', 'musrefy_pay', 'yussor_online', 'sahara_pay')

# Human-readable names, used for the `code` selection and the data records.
ONEPAY_BRANDS = {
    'onepay': "OnePay",
    'musrefy_pay': "Musrefy Pay",
    'yussor_online': "Yussor Online",
    'sahara_pay': "Sahara Pay",
}

# Prefix prepended to a 7-digit identity card number, per brand. Cards of 9 or
# more characters are already complete and pass through untouched.
BRAND_PREFIXES = {
    'musrefy_pay': '11',
    'yussor_online': '33',
    'sahara_pay': '66',
}

# Default API endpoint paths, taken from blueline's `config/payments.php`.
# Overridable per provider record, because the gateway hands out different
# paths to different merchants.
DEFAULT_SIGNIN_PATH = 'api/OnlinePaymentServices/Signin'
DEFAULT_INIT_PATH = 'api/OnlinePaymentServices/OpenSession'
DEFAULT_COMPLETE_PATH = 'api/OnlinePaymentServices/CompleteSession'
DEFAULT_REPORT_PATH = 'api/OnlinePaymentServices/AccountReport'

# The gateway defaults this to 0 when unset, so it is not a required field.
DEFAULT_AUTH_USER_TYPE = 0

# The length of the one-time password the customer receives by SMS.
OTP_LENGTH = 6

# Response `type` values returned by the gateway.
RESPONSE_TYPE_SUCCESS = 1
RESPONSE_TYPE_ERROR = 2

# Currencies supported by the gateway.
SUPPORTED_CURRENCIES = ('LYD',)

# How far either side of the transaction's creation time to search the
# transaction report when reconciling. Mirrors the blueline implementation.
REPORT_WINDOW_HOURS = 5

# Bounds for the reconciliation cron. The lower bound avoids racing a customer
# who is still typing their OTP; the upper bound keeps the sweep from growing
# without limit.
RECONCILE_MIN_AGE_MINUTES = 10
RECONCILE_MAX_AGE_HOURS = 24
