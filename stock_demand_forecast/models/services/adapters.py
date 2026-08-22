import numpy as np

MIN_HISTORY = 8


class FitError(Exception):
    """Raised when a model cannot produce a usable forecast."""


def _fit_autoreg(y, horizon, p):
    from statsmodels.tsa.ar_model import AutoReg
    res = AutoReg(np.asarray(y, dtype=float), lags=p.get("lags", 2),
                  trend=p.get("trend", "c"), old_names=False).fit()
    return res.forecast(steps=horizon)


def _fit_ardl(y, horizon, p):
    from statsmodels.tsa.ardl import ARDL
    res = ARDL(np.asarray(y, dtype=float), lags=int(p.get("p", 1)),
               trend=p.get("trend", "c")).fit()
    return res.forecast(steps=horizon)


def _fit_arima(y, horizon, p):
    from statsmodels.tsa.arima.model import ARIMA
    res = ARIMA(np.asarray(y, dtype=float),
                order=tuple(p.get("order", (1, 1, 1)))).fit()
    return res.forecast(steps=horizon)


def _fit_sarimax(y, horizon, p):
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    res = SARIMAX(
        np.asarray(y, dtype=float),
        order=tuple(p.get("order", (1, 1, 1))),
        seasonal_order=tuple(p.get("seasonal_order", (0, 0, 0, 0))),
        trend=p.get("trend"),
        enforce_stationarity=p.get("enforce_stationarity", True),
        enforce_invertibility=p.get("enforce_invertibility", True),
        simple_differencing=p.get("simple_differencing", False),
        hamilton_representation=p.get("hamilton_representation", False),
        measurement_error=p.get("measurement_error", False),
        concentrate_scale=p.get("concentrate_scale", False),
    ).fit(disp=False)
    return res.forecast(steps=horizon)


def _fit_hwes(y, horizon, p):
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    seasonal = p.get("seasonal") or None
    periods = p.get("seasonal_periods")
    if seasonal and (not periods or len(y) < 2 * periods):
        raise FitError("HWES seasonal requires >= 2 seasonal cycles")
    res = ExponentialSmoothing(
        np.asarray(y, dtype=float),
        trend=p.get("trend", "add"), damped_trend=p.get("damped", False),
        seasonal=seasonal, seasonal_periods=periods,
    ).fit(optimized=True)
    return res.forecast(steps=horizon)


def _fit_ses(y, horizon, p):
    from statsmodels.tsa.holtwinters import SimpleExpSmoothing
    res = SimpleExpSmoothing(np.asarray(y, dtype=float)).fit(
        smoothing_level=p.get("smoothing_level"),
        optimized=p.get("optimized", True))
    return res.forecast(steps=horizon)


FIT_REGISTRY = {
    "autoreg": _fit_autoreg,
    "ardl": _fit_ardl,
    "arima": _fit_arima,
    "sarimax": _fit_sarimax,
    "hwes": _fit_hwes,
    "ses": _fit_ses,
}


def fit_series(method, history, cfg):
    """Fit `method` on history and forecast. cfg must include 'horizon'.

    Returns list[float] of length horizon; raises FitError on any failure.
    """
    cfg = dict(cfg)
    horizon = int(cfg.pop("horizon"))
    if len(history) < MIN_HISTORY:
        raise FitError(f"insufficient history: {len(history)} points")
    try:
        out = FIT_REGISTRY[method](list(history), horizon, cfg)
    except FitError:
        raise
    except Exception as exc:  # statsmodels raises many exception types
        raise FitError(str(exc)) from exc
    out = np.nan_to_num(np.asarray(out, dtype=float), nan=0.0)
    return out.tolist()
