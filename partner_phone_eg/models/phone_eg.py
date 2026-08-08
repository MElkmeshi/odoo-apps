"""Egyptian mobile number normalisation.

Kept in its own module because both res.partner and crm.lead need it, and
because uniqueness is only meaningful once every number has a single canonical
form: 01001234567, +20 100 123 4567 and 00201001234567 are the same person.
"""

import re

# 01 + operator digit (0,1,2,5) + 8 subscriber digits = 11 digits total.
EG_MOBILE_RE = re.compile(r'^01[0125]\d{8}$')


def normalize_eg_phone(raw):
    """Return the canonical ``01XXXXXXXXX`` form of `raw`, or None.

    None means "not an Egyptian mobile" - a landline, a foreign number or
    junk. Callers decide whether that is an error or simply a number that
    uniqueness does not apply to.
    """
    if not raw:
        return None
    digits = re.sub(r'\D', '', raw)             # drop spaces, dashes, parens, +
    for prefix in ('0020', '20'):               # country code, with or without 00
        if digits.startswith(prefix) and len(digits) > len(prefix):
            digits = digits[len(prefix):]
            break
    digits = digits.lstrip('0')                 # strip trunk 0 before re-adding it
    candidate = '0' + digits
    return candidate if EG_MOBILE_RE.match(candidate) else None
