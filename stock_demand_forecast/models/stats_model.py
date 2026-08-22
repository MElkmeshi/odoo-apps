from odoo import api, fields, models

METHOD_LABELS = [
    ("autoreg", "Autoregression (AutoReg)"),
    ("ardl", "Autoregressive Distributed Lag (ARDL)"),
    ("arima", "Autoregressive Integrated Moving Average (ARIMA)"),
    ("sarimax", "Seasonal Autoregressive Integrated Moving-Average (SARIMAX)"),
    ("hwes", "Holt Winter's Exponential Smoothing (HWES)"),
    ("ses", "Simple Exponential Smoothing (SES)"),
]

TREND_SELECTION = [("n", "No trend"), ("c", "Constant"), ("t", "Linear"),
                   ("ct", "Constant + Linear")]


class StatsModel(models.Model):
    _name = "stats.model"
    _description = "Forecast Statistical Model"

    method = fields.Selection(METHOD_LABELS, required=True, default="autoreg")
    reference = fields.Char(required=True, default="H1")

    # AutoReg / generic
    lags = fields.Integer(default=2)
    trend = fields.Selection(TREND_SELECTION, default="c")
    seasonal = fields.Boolean()

    # ARDL
    ardl_p = fields.Integer(string="P (own lags)", default=1)
    ardl_q = fields.Integer(string="Q (lagged exog)", default=1)
    maxlag = fields.Integer()

    # ARIMA / SARIMAX orders
    p = fields.Integer(string="P", default=1)
    d = fields.Integer(string="D", default=1)
    q = fields.Integer(string="Q", default=1)
    sp = fields.Integer(string="Seasonal P", default=0)
    sd = fields.Integer(string="Seasonal D", default=0)
    sq = fields.Integer(string="Seasonal Q", default=0)
    seasonal_periods = fields.Integer(string="s (Periodicity)", default=12)

    # SARIMAX advanced flags: enforce_stationarity, enforce_invertibility,
    # concentrate_scale, measurement_error, time_varying_regression,
    # simple_differencing, hamilton_representation
    sarimax_flags = fields.Json(string="Advanced Flags", default=dict)

    # HWES
    hwes_trend = fields.Selection(
        [("add", "Additive"), ("mul", "Multiplicative")], default="add")
    hwes_damped = fields.Boolean(string="Damped")
    hwes_seasonal = fields.Selection(
        [("none", "None"), ("add", "Additive"), ("mul", "Multiplicative")],
        default="none")

    # SES
    ses_smoothing_level = fields.Float(string="Smoothing Level (alpha)")
    ses_optimized = fields.Boolean(string="Optimized", default=True)

    @api.depends("reference", "method", "p", "d", "q", "lags",
                 "ardl_p", "ardl_q", "sp", "sd", "sq", "seasonal_periods",
                 "hwes_trend")
    def _compute_display_name(self):
        detail_fns = {
            "autoreg": lambda r: f"AutoReg, {r.lags}, {r.trend}",
            "ardl": lambda r: f"ARDL, ({r.ardl_p}, {r.ardl_q})",
            "arima": lambda r: f"ARIMA, ({r.p}, {r.d}, {r.q})",
            "sarimax": lambda r: (
                f"SARIMAX, ({r.p},{r.d},{r.q})x"
                f"({r.sp},{r.sd},{r.sq},{r.seasonal_periods})"),
            "hwes": lambda r: f"HWES, {r.hwes_trend}",
            "ses": lambda r: "SES",
        }
        for rec in self:
            detail = detail_fns[rec.method](rec)
            rec.display_name = f"{rec.reference} ({detail})"

    def _param_kwargs(self):
        """Map columns -> schema kwarg names per method."""
        self.ensure_one()
        m = self.method
        if m == "autoreg":
            return {"lags": max(self.lags, 1), "trend": self.trend,
                    "seasonal": self.seasonal}
        if m == "ardl":
            return {"p": max(self.ardl_p, 0), "q": max(self.ardl_q, 0),
                    "maxlag": self.maxlag or None, "trend": self.trend}
        if m == "arima":
            return {"order": (max(self.p, 0), max(self.d, 0), max(self.q, 0)),
                    "trend": None if self.trend == "n" else self.trend}
        if m == "sarimax":
            flags = dict(self.sarimax_flags or {})
            return {
                "p": max(self.p, 0), "d": max(self.d, 0), "q": max(self.q, 0),
                "sp": max(self.sp, 0), "sd": max(self.sd, 0),
                "sq": max(self.sq, 0),
                "seasonal_periods": max(self.seasonal_periods, 0),
                "trend": None if self.trend == "n" else self.trend,
                **flags,
            }
        if m == "hwes":
            return {"trend": self.hwes_trend, "damped": self.hwes_damped,
                    "seasonal": self.hwes_seasonal,
                    "seasonal_periods": self.seasonal_periods}
        return {"smoothing_level": self.ses_smoothing_level or None,
                "optimized": self.ses_optimized}
