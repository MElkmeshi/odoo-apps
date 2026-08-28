from . import controllers
from . import models

from odoo.addons.payment import setup_provider, reset_payment_provider

from .const import ONEPAY_CODES


def post_init_hook(env):
    # One provider record per brand: they share this implementation and differ
    # only in credentials and in the identity card prefix.
    for code in ONEPAY_CODES:
        setup_provider(env, code)


def uninstall_hook(env):
    for code in ONEPAY_CODES:
        reset_payment_provider(env, code)
