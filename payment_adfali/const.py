from odoo import _


# The SOAP namespace and methods exposed by the gateway.
SOAP_NAMESPACE = 'http://tempuri.org/'
METHOD_INITIATE = 'DoPTrans'
METHOD_CONFIRM = 'OnlineConfTrans'

# `DoPTrans` answers with one of these codes on failure, or the session id on
# success. Anything not listed here is treated as a session id.
INITIATE_ERRORS = {
    'PW1': lambda: _("The Adfali service password is incorrect."),
    'PW': lambda: _("The Adfali merchant PIN is incorrect."),
    'LIMIT': lambda: _("The amount exceeds the transaction limits of your wallet."),
    'ACC': lambda: _("No Adfali account was found for this mobile number."),
    'BAL': lambda: _("The payment failed. Please check your wallet balance."),
}

# The only `OnlineConfTrans` result that means the payment went through.
CONFIRM_SUCCESS = 'OK'

# The length of the PIN the customer receives by SMS.
OTP_LENGTH = 4

# Libyan country calling code, prepended to customer mobile numbers.
COUNTRY_CALLING_CODE = '+218'

# Currencies supported by the gateway.
SUPPORTED_CURRENCIES = ('LYD',)
