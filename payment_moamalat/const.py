# Part of Odoo. See LICENSE file for full copyright and licensing details.

# Moamalat identifies currencies by their ISO 4217 numeric code.
CURRENCY_MAPPING = {
    'LYD': '434',  # Libyan Dinar
    'USD': '840',  # US Dollar
    'EUR': '978',  # Euro
}

# The currencies the provider is offered for. Anything outside this set is
# filtered out of `available_currency_ids`, so the provider never appears at
# checkout in a currency Moamalat would reject.
SUPPORTED_CURRENCIES = list(CURRENCY_MAPPING)

# The payment methods enabled on the provider by default.
DEFAULT_PAYMENT_METHOD_CODES = ['card']

# Transaction types.
TXN_TYPE_SALE = '1'
TXN_TYPE_REFUND = '2'
TXN_TYPE_VOID_SALE = '3'
TXN_TYPE_VOID_REFUND = '4'

# The only action code that means the transaction was approved.
ACTION_CODE_APPROVED = '00'
