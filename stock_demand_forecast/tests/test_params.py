import pytest
from pydantic import ValidationError

try:
    from stock_demand_forecast.schemas.params import (
        MODEL_PARAMS, AutoRegParams, SarimaxParams, HwesParams,
    )
except ImportError:
    from odoo.addons.stock_demand_forecast.schemas.params import (
        MODEL_PARAMS, AutoRegParams, SarimaxParams, HwesParams,
    )


def test_all_six_methods_registered():
    assert set(MODEL_PARAMS) == {"autoreg", "ardl", "arima", "sarimax", "hwes", "ses"}


def test_autoreg_defaults():
    p = AutoRegParams()
    assert p.lags == 2 and p.trend == "c" and p.seasonal is False


def test_autoreg_rejects_bad_trend_and_lags():
    with pytest.raises(ValidationError):
        AutoRegParams(trend="banana")
    with pytest.raises(ValidationError):
        AutoRegParams(lags=0)


def test_sarimax_order_must_be_non_negative():
    p = SarimaxParams(order=(2, 1, 1), seasonal_order=(1, 1, 0, 12))
    assert p.order == (2, 1, 1)
    with pytest.raises(ValidationError):
        SarimaxParams(order=(-1, 0, 0))


def test_hwes_seasonal_requires_periods():
    with pytest.raises(ValidationError):
        HwesParams(seasonal="add")  # seasonal_periods missing


def test_build_from_record_fields():
    # simulates stats.model record field values for SARIMAX
    rec = {"method": "sarimax", "p": 1, "d": 1, "q": 1,
           "sp": 1, "sd": 1, "sq": 0, "seasonal_periods": 12,
           "enforce_stationarity": True}
    cls = MODEL_PARAMS[rec["method"]]
    kwargs = {k: v for k, v in rec.items() if k != "method"}
    p = cls.from_record(kwargs)
    assert p.order == (1, 1, 1) and p.seasonal_order == (1, 1, 0, 12)
