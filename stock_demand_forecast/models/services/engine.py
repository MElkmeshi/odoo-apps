import logging

import pandas as pd

from . import adapters
from .periods import (
    bucket_key, key_to_date, next_period, period_end, period_label,
    period_start,
)

_logger = logging.getLogger(__name__)

AGG_FIELD = "quantity"


def build_series(report):
    """Wide DataFrame indexed by period bucket key, one column per series."""
    Move = report.env["stock.move"]
    specs = report.get_series_field_specs()
    fields_to_read = ["date", AGG_FIELD] + [p.split(".")[0] for p, _ in specs]
    rows = Move.search_read(report.get_base_domain(), fields=fields_to_read)

    data = {}
    labels = {}
    for mv in rows:
        d = mv["date"].date()
        col_parts = []
        for path, kind in specs:
            cur = mv
            for part in path.split("."):
                if isinstance(cur, tuple):
                    cur = cur[1]
                elif isinstance(cur, dict):
                    cur = cur.get(part)
                else:
                    cur = None
                if isinstance(cur, tuple):
                    cur = cur[1]
            if kind == "m2o" and isinstance(cur, str):
                pass
            cur = cur or "-"
            col_parts.append(str(cur))
        col = "|".join(col_parts) or "__all__"
        bk = bucket_key(d, report.interval)
        data.setdefault(col, {})
        data[col][bk] = data[col].get(bk, 0.0) + (mv[AGG_FIELD] or 0.0)
        labels[col] = col_parts

    if not data:
        return pd.DataFrame()
    all_keys = sorted({k for vals in data.values() for k in vals})
    frame = pd.DataFrame(
        {col: {k: vals.get(k, 0.0) for k in all_keys} for col, vals in data.items()})
    frame.index.name = "period"
    frame.attrs["labels"] = labels
    return frame


def _column_label(report, series_name):
    """`[ref] SeriesName / H1 (AutoReg, 2, c)` per stats.model record."""
    model = report.model_ids[:1]
    base = series_name.replace("|", " / ") if report.group_by_field != "none" \
        else "All"
    if model:
        return f"{base} / {model.display_name}"
    return base


def _describe(s: pd.Series):
    q = s.quantile([0.25, 0.5, 0.75]).tolist()
    return {
        "count": int(s.count()),
        "mean": float(s.mean()) if s.count() else 0.0,
        "std": float(s.std(ddof=1)) if s.count() > 1 else 0.0,
        "min": float(s.min()) if s.count() else 0.0,
        "25%": float(q[0]), "50%": float(q[1]), "75%": float(q[2]),
        "max": float(s.max()) if s.count() else 0.0,
    }


def run_forecast(report):
    """Aggregate + fit every (series x model) pair; never raises.

    Returns {meta, labels[], forecast_labels[], series[]}.
    """
    payload = {
        "meta": {"interval": report.interval,
                 "hypothesis": bool(report.hypothesis_testing),
                 "shorten": bool(report.shorten_figures),
                 "show_stats": bool(report.show_stats_info)},
        "labels": [], "forecast_labels": [], "series": [],
    }
    frame = build_series(report)
    if frame.empty:
        return payload

    hist_keys = list(frame.index)
    payload["labels"] = [
        period_label(key_to_date(k, report.interval), report.interval)
        for k in hist_keys]

    # future period axis
    last_hist_date = period_end(key_to_date(hist_keys[-1], report.interval),
                                report.interval)
    fut_dates = []
    cursor = next_period(last_hist_date, report.interval)
    for _ in range(max(int(report.horizon), 0)):
        fut_dates.append(cursor)
        cursor = next_period(period_end(period_start(cursor, report.interval),
                                        report.interval),
                             report.interval)
    payload["forecast_labels"] = [
        period_label(d, report.interval) for d in fut_dates]

    # hypothesis-testing window: hold back `horizon` periods as actuals
    n_hist = len(hist_keys)
    train_cutoff = n_hist
    if report.hypothesis_testing and n_hist > int(report.horizon) >= 1:
        train_cutoff = n_hist - int(report.horizon)

    models = list(report.model_ids) or [None]
    for col in frame.columns:
        y_full = [float(v) for v in frame[col].tolist()]
        y_train = y_full[:train_cutoff]
        held_out = y_full[train_cutoff:]
        for model in models:
            entry = {
                "key": col,
                "model_id": model.id if model else None,
                "label": _column_label(report, col),
                "history_pre": [],
                "history": [],
                "forecast": [],
                "actuals": held_out if report.hypothesis_testing else [],
                "stats": {},
                "error": None,
            }
            # history shown = the window after train_cutoff when backtesting,
            # otherwise the full history
            if report.hypothesis_testing:
                entry["history"] = y_full[train_cutoff:]
                entry["history_pre"] = y_full[:train_cutoff]
            else:
                entry["history_pre"] = []
                entry["history"] = y_full
            try:
                if model is None:
                    raise adapters.FitError("no statistical model selected")
                preds = adapters.fit_series(
                    model.method, y_train,
                    {**model._param_kwargs(), "horizon": int(report.horizon)})
                entry["forecast"] = preds
                if report.show_stats_info:
                    entry["stats"] = _describe(pd.Series(y_full))
            except Exception as exc:  # per-series failure isolation
                _logger.warning("forecast fit failed for %r: %s",
                                entry["label"], exc)
                entry["error"] = str(exc)
            payload["series"].append(entry)
    return payload
