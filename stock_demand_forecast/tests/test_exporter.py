import io
import zipfile

try:
    from stock_demand_forecast.models.services.exporter import build_xlsx
except ImportError:
    from odoo.addons.stock_demand_forecast.models.services.exporter import (
        build_xlsx,
    )

PAYLOAD = {
    "meta": {"shorten": True},
    "labels": ["October 2025", "November 2025"],
    "forecast_labels": ["December 2025"],
    "series": [{
        "key": "s1",
        "label": "[abs-xyz] Acoustic Bloc Screens / H1 (AutoReg, 2, c)",
        "history": [100.0, 120.0],
        "forecast": [130.5],
        "stats": {},
        "error": None,
    }],
}


def test_xlsx_is_valid_container_with_expected_rows():
    data = build_xlsx(PAYLOAD)
    zf = zipfile.ZipFile(io.BytesIO(data))
    sheet = next(n for n in zf.namelist() if n.startswith("xl/worksheets/"))
    xml = zf.read(sheet).decode()
    # header row + 2 history rows + 1 forecast row
    assert xml.count("<row ") >= 4


def test_empty_payload_still_builds():
    empty = {"meta": {}, "labels": [], "forecast_labels": [], "series": []}
    data = build_xlsx(empty)
    assert len(data) > 0
