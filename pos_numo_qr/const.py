# Institution codes issued by the Central Bank of Libya, used in NUMO tag 30.
#
# The list is deliberately not exhaustive of every number in the range: the
# gaps (001, 003, 008, 009, 011, 019, 022) belong to banks that have merged or
# lost their licence. A merchant whose bank is not here picks "Other" and types
# the code their bank gave them.
LIBYAN_BANKS = [
    ('002', "Jumhouria Bank"),
    ('004', "National Commercial Bank"),
    ('005', "Wahda Bank"),
    ('006', "Sahara Bank"),
    ('007', "North Africa Bank"),
    ('010', "Bank of Commerce & Development"),
    ('012', "Waha Bank"),
    ('013', "Aman Bank"),
    ('014', "National Union Bank"),
    ('015', "Tadhamun Bank"),
    ('016', "Alwafa Bank"),
    ('017', "United Bank for Commerce and Investment"),
    ('018', "Mediterranean Bank"),
    ('020', "Assaray Bank"),
    ('021', "First Gulf Libyan Bank"),
    ('023', "Development Bank"),
    ('024', "Nuran Bank"),
    ('025', "Libyan Islamic Bank"),
    ('026', "Yaqeen Bank"),
    ('027', "Andalus Bank"),
]

# Picked when the Central Bank licenses a bank this module has not caught up
# with yet. Keeps a new bank from being a blocker until the next release.
BANK_OTHER = 'other'

BANK_SELECTION = [
    (code, "%s — %s" % (code, name)) for code, name in LIBYAN_BANKS
] + [(BANK_OTHER, "Other")]

BANK_CODES = {code for code, _name in LIBYAN_BANKS}
