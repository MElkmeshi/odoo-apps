import numpy as np
import pytest

try:
    from stock_demand_forecast.models.services.adapters import (
        FIT_REGISTRY, FitError, fit_series,
    )
except ImportError:
    from odoo.addons.stock_demand_forecast.models.services.adapters import (
        FIT_REGISTRY, FitError, fit_series,
    )


@pytest.fixture
def seasonal_series():
    # 48 months: level 100 + upward trend + monthly seasonality + noise
    rng = np.random.default_rng(42)
    t = np.arange(48)
    return 100 + t * 2 + 20 * np.sin(2 * np.pi * t / 12) + rng.normal(0, 2, 48)


def test_registry_has_six_methods():
    assert set(FIT_REGISTRY) == {"autoreg", "ardl", "arima",
                                 "sarimax", "hwes", "ses"}


def _params_for(method):
    return {
        "autoreg": {"lags": 2},
        "ardl": {"p": 1, "q": 1},
        "arima": {"order": (1, 1, 1)},
        "sarimax": {"order": (1, 1, 1), "seasonal_order": (1, 0, 0, 12)},
        "hwes": {"trend": "add"},
        "ses": {},
    }[method]


def test_each_method_returns_n_steps(seasonal_series):
    for method in FIT_REGISTRY:
        out = fit_series(method, seasonal_series.tolist(),
                         {**_params_for(method), "horizon": 6})
        assert len(out) == 6, method
        assert all(np.isfinite(out)), method


def test_fit_error_on_short_history():
    with pytest.raises(FitError):
        fit_series("arima", [1.0, 2.0], {"order": (3, 2, 2), "horizon": 4})


def test_hwes_seasonal_needs_two_cycles(seasonal_series):
    with pytest.raises(FitError):
        fit_series("hwes", seasonal_series[:10].tolist(),
                   {"trend": "add", "seasonal": "add",
                    "seasonal_periods": 12, "horizon": 3})
