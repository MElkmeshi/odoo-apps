import calendar
import datetime as dt

FREQ_MAP = {
    "day": "D",
    "week": "W-SUN",
    "month": "MS",
    "quarter": "QS-JAN",
    "year": "YS",
}

_MONTHS = [dt.date(2000, m, 1).strftime("%B") for m in range(1, 13)]


def month_last_day(y: int, m: int) -> dt.date:
    return dt.date(y, m, calendar.monthrange(y, m)[1])


def bucket_key(d: dt.date, interval: str) -> str:
    if interval == "day":
        return d.isoformat()
    if interval == "week":
        monday = d - dt.timedelta(days=d.weekday())
        return monday.isoformat()
    if interval == "month":
        return f"{d.year}-{d.month:02d}"
    if interval == "quarter":
        return f"{d.year}-Q{(d.month - 1) // 3 + 1}"
    return str(d.year)


def period_start(d: dt.date, interval: str) -> dt.date:
    if interval == "week":
        return d - dt.timedelta(days=d.weekday())
    if interval == "month":
        return d.replace(day=1)
    if interval == "quarter":
        return d.replace(day=1, month=((d.month - 1) // 3) * 3 + 1)
    if interval == "year":
        return d.replace(day=1, month=1)
    return d


def next_period(d: dt.date, interval: str) -> dt.date:
    """Given any date in a period, return the LAST day of the NEXT period."""
    y, m = d.year, d.month
    if interval == "day":
        return d + dt.timedelta(days=1)
    if interval == "week":
        return d + dt.timedelta(days=7)
    if interval == "month":
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        return month_last_day(ny, nm)
    if interval == "quarter":
        q = (m - 1) // 3 + 1
        nq = q + 1
        return month_last_day(y + (nq == 5), ((nq - 1) % 4) * 3 + 3)
    if interval == "year":
        return dt.date(y + 1, 12, 31)
    raise ValueError(f"unknown interval {interval!r}")


def period_end(d: dt.date, interval: str) -> dt.date:
    if interval == "day":
        return d
    if interval == "week":
        return d + dt.timedelta(days=6 - d.weekday())
    if interval == "month":
        return month_last_day(d.year, d.month)
    if interval == "quarter":
        q = (d.month - 1) // 3 + 1
        return month_last_day(d.year, q * 3)
    return dt.date(d.year, 12, 31)


def period_label(d: dt.date, interval: str) -> str:
    if interval == "day":
        return d.strftime("%d %B %Y")
    if interval == "week":
        monday = d - dt.timedelta(days=d.weekday())
        return f"Week of {monday.strftime('%d %B %Y')}"
    if interval == "month":
        return f"{_MONTHS[d.month - 1]} {d.year}"
    if interval == "quarter":
        return f"Q{(d.month - 1) // 3 + 1} {d.year}"
    return str(d.year)


def key_to_date(key: str, interval: str) -> dt.date:
    """Inverse of bucket_key for label generation."""
    if interval == "year":
        return dt.date(int(key), 6, 30)
    if interval == "quarter":
        y, q = key.split("-Q")
        return dt.date(int(y), (int(q) - 1) * 3 + 2, 15)
    if interval == "month":
        y, m = key.split("-")
        return dt.date(int(y), int(m), 28)
    return dt.date.fromisoformat(key[:10])
