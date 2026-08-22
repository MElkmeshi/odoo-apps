from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class BaseParams(BaseModel):
    """Base for per-method parameter schemas; subclasses may override from_record."""

    @classmethod
    def from_record(cls, vals):
        return cls(**vals)


class AutoRegParams(BaseParams):
    lags: int = Field(default=2, ge=1)
    trend: Literal["n", "c", "t", "ct"] = "c"
    seasonal: bool = False


class ARDLParams(BaseParams):
    p: int = Field(default=1, ge=0)
    q: int = Field(default=1, ge=0)
    maxlag: Optional[int] = Field(default=None, ge=0)
    trend: Literal["n", "c", "t", "ct"] = "c"


class ArimaParams(BaseParams):
    order: tuple[int, int, int] = (1, 1, 1)
    trend: Optional[Literal["n", "c", "t", "ct"]] = None

    @model_validator(mode="after")
    def _check_order(self):
        if any(v < 0 for v in self.order):
            raise ValueError("ARIMA order values must be >= 0")
        return self


class SarimaxParams(BaseParams):
    order: tuple[int, int, int] = (1, 1, 1)
    seasonal_order: tuple[int, int, int, int] = (0, 0, 0, 0)
    trend: Optional[Literal["n", "c", "t", "ct"]] = None
    enforce_stationarity: bool = True
    enforce_invertibility: bool = True
    concentrate_scale: bool = False
    measurement_error: bool = False
    time_varying_regression: bool = False
    simple_differencing: bool = False
    hamilton_representation: bool = False

    @model_validator(mode="after")
    def _check_orders(self):
        if any(v < 0 for v in self.order + self.seasonal_order):
            raise ValueError("SARIMAX orders must be >= 0")
        return self

    @classmethod
    def from_record(cls, vals):
        vals = dict(vals)
        order = (vals.pop("p", 1), vals.pop("d", 1), vals.pop("q", 1))
        sorder = (vals.pop("sp", 0), vals.pop("sd", 0),
                  vals.pop("sq", 0), vals.pop("seasonal_periods", 0))
        return cls(order=order, seasonal_order=sorder, **vals)


class HwesParams(BaseParams):
    trend: Literal["add", "mul"] = "add"
    damped: bool = False
    seasonal: Optional[Literal["add", "mul"]] = None
    seasonal_periods: Optional[int] = Field(default=None, ge=2)

    @model_validator(mode="after")
    def _check_season(self):
        if self.seasonal and not self.seasonal_periods:
            raise ValueError("seasonal requires seasonal_periods")
        return self


class SesParams(BaseParams):
    smoothing_level: Optional[float] = Field(default=None, ge=0, le=1)
    optimized: bool = True


MODEL_PARAMS = {
    "autoreg": AutoRegParams,
    "ardl": ARDLParams,
    "arima": ArimaParams,
    "sarimax": SarimaxParams,
    "hwes": HwesParams,
    "ses": SesParams,
}
