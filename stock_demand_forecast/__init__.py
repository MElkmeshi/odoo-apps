try:
    from . import models
    from . import controllers
except ImportError:
    # odoo not available when running pure pytest outside an Odoo environment;
    # the schemas/services subpackages remain importable on their own
    pass
