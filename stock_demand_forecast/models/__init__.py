try:
    from . import forecast_report
    from . import stats_model
    from .services import engine
except ImportError:
    # odoo not available when running pure pytest outside an Odoo environment;
    # pure submodules (services.periods, services.adapters) stay importable
    pass
