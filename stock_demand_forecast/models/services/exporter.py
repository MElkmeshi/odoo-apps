import io

import xlsxwriter

FORECAST_BG = "#BBDEFB"


def build_xlsx(payload):
    """Build the demand-forecast workbook: Date column + one column per
    series/model; forecast rows highlighted blue like the reference app."""
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    bold = wb.add_format({"bold": True})
    blue = wb.add_format({"bg_color": FORECAST_BG})

    ws = wb.add_worksheet("Forecast")
    series = payload.get("series") or []
    labels = payload.get("labels") or []
    forecast_labels = payload.get("forecast_labels") or []

    ws.write_row(0, 0, ["Date"] + [s["label"] for s in series], bold)

    for i, label in enumerate(labels, start=1):
        ws.write(i, 0, label)
        for j, s in enumerate(series, start=1):
            hist = s.get("history") or []
            if i - 1 < len(hist):
                ws.write_number(i, j, round(float(hist[i - 1]), 2))

    offset = len(labels) + 1
    for k, label in enumerate(forecast_labels):
        r = offset + k
        ws.write(r, 0, label)
        for j, s in enumerate(series, start=1):
            fc = s.get("forecast") or []
            if k < len(fc):
                ws.write_number(r, j, round(float(fc[k]), 2), blue)

    # per-series stats block under the table (like Show Stats Info)
    if any(s.get("stats") for s in series):
        row = offset + len(forecast_labels) + 2
        stat_order = ["count", "mean", "std", "min", "25%", "50%",
                      "75%", "max"]
        ws.write(row, 0, "Stats", bold)
        for j, s in enumerate(series, start=1):
            st = s.get("stats") or {}
            col_row = row
            for key in stat_order:
                col_row += 1
                ws.write(col_row, 0, key)
                if key in st:
                    ws.write_number(col_row, j, round(float(st[key]), 2))
                elif j == 1:
                    ws.write(col_row, j, "-")

    ws.set_column(0, 0, 18)
    if series:
        ws.set_column(1, len(series), 42)
    wb.close()
    return buf.getvalue()
