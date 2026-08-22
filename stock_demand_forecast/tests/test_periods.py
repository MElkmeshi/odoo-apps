import datetime as dt

try:
    from stock_demand_forecast.models.services.periods import (
        FREQ_MAP, bucket_key, next_period, period_label,
    )
except ImportError:
    from odoo.addons.stock_demand_forecast.models.services.periods import (
        FREQ_MAP, bucket_key, next_period, period_label,
    )


def test_freq_map_covers_intervals():
    assert set(FREQ_MAP) == {"day", "week", "month", "quarter", "year"}


def test_bucket_key():
    d = dt.date(2025, 11, 7)
    assert bucket_key(d, "month") == "2025-11"
    assert bucket_key(d, "year") == "2025"
    assert bucket_key(d, "quarter") == "2025-Q4"
    assert bucket_key(d, "day") == "2025-11-07"
    assert bucket_key(d, "week") == "2025-11-03"  # Monday of that week


def test_period_label():
    assert period_label(dt.date(2025, 11, 30), "month") == "November 2025"
    assert period_label(dt.date(2025, 2, 3), "quarter") == "Q1 2025"
    assert period_label(dt.date(2025, 1, 1), "year") == "2025"


def test_next_period_month_end():
    assert next_period(dt.date(2025, 11, 30), "month") == dt.date(2025, 12, 31)
    assert next_period(dt.date(2025, 1, 31), "month") == dt.date(2025, 2, 28)
    assert next_period(dt.date(2025, 1, 15), "year") == dt.date(2026, 12, 31)
    assert next_period(dt.date(2025, 9, 30), "quarter") == dt.date(2025, 12, 31)
