from . import test_params
from . import test_periods
from . import test_adapters

try:
    from . import test_engine_odoo
except ImportError:
    # odoo not available when running pure pytest outside an Odoo environment
    pass
