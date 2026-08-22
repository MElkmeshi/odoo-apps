import json
import logging

from odoo.http import Controller, request, route

_logger = logging.getLogger(__name__)

GROUP = "stock_demand_forecast.group_stock_demand_forecast"

CONFIG_JSON_FIELDS = (
    "name", "interval", "horizon", "state_flags", "extra_domain",
    "group_by_field", "show_stats_info", "hypothesis_testing",
    "shorten_figures", "period_start", "period_end",
)
CONFIG_M2M_FIELDS = (
    "company_ids", "warehouse_ids", "location_src_ids", "location_dst_ids",
    "product_ids", "template_ids", "category_ids", "uom_ids",
    "picking_type_ids", "rule_ids", "model_ids",
)


def _check_group():
    if not request.env.user.has_group(GROUP):
        raise request.not_found()


def _config_to_vals(config):
    """Translate UI config payload into forecast.report create/write vals.

    m2m fields arrive as [{id, display_name}] -> [(6, 0, [ids])].
    """
    vals = {k: config[k] for k in CONFIG_JSON_FIELDS if k in config}
    for key in CONFIG_M2M_FIELDS:
        if key in config:
            ids = [r["id"] for r in (config[key] or [])
                   if isinstance(r, dict) and r.get("id")]
            vals[key] = [(6, 0, ids)]
    return vals


def _report_from_payload(config):
    Report = request.env["forecast.report"]
    report_id = config.get("report_id")
    vals = _config_to_vals(config)
    if report_id:
        report = Report.browse(report_id).exists()
        if report:
            report.write(vals)
            return report
    return Report.new(vals)


class ForecastController(Controller):

    @route("/stock_demand_forecast/data", type="json", auth="user")
    def data(self, **kwargs):
        _check_group()
        from odoo.addons.stock_demand_forecast.models.services.engine \
            import run_forecast
        report = _report_from_payload(kwargs.get("config") or {})
        try:
            return run_forecast(report)
        except ValueError as exc:  # bad extra domain etc.
            return {"error": str(exc), "series": [], "labels": [],
                    "forecast_labels": [],
                    "meta": {"interval": report.interval or "month"}}

    @route("/stock_demand_forecast/export", type="http", auth="user",
           methods=["POST"], csrf=False)
    def export(self, config_json=None):
        _check_group()
        from odoo.addons.stock_demand_forecast.models.services.engine \
            import run_forecast
        from odoo.addons.stock_demand_forecast.models.services.exporter \
            import build_xlsx
        config = json.loads(config_json or "{}")
        report = _report_from_payload(config)
        payload = run_forecast(report)
        content = build_xlsx(payload)
        filename = "%s.xlsx" % (payload["meta"].get("filename")
                                or "demand_forecast")
        headers = [
            ("Content-Type",
             "application/vnd.openxmlformats-officedocument"
             ".spreadsheetml.sheet"),
            ("Content-Disposition", 'attachment; filename="%s"' % filename),
            ("Content-Length", str(len(content))),
        ]
        return request.make_response(content, headers=headers)
