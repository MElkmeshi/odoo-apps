from odoo import fields, models

STATE_SELECTION = [
    ("done", "Done"),
    ("assigned", "Partially Available"),
    ("waiting", "Waiting Availability"),
    ("confirmed", "Waiting Another Move"),
    ("draft", "New"),
    ("cancel", "Cancelled"),
]

SAFE_DOMAIN_FIELDS = {
    "state", "date", "company_id", "warehouse_id", "location_id",
    "location_dest_id", "product_id", "product_tmpl_id", "product_uom",
    "picking_type_id", "rule_id",
}


class ForecastReport(models.Model):
    _name = "forecast.report"
    _description = "Stock Demand Forecast Report"

    name = fields.Char(required=True, default="Delivery stats")
    active = fields.Boolean(default=True)
    interval = fields.Selection(
        [("day", "Daily"), ("week", "Weekly"), ("month", "Monthly"),
         ("quarter", "Quarterly"), ("year", "Yearly")],
        required=True, default="month")
    period_start = fields.Date()
    period_end = fields.Date()
    horizon = fields.Integer(string="Forecast Periods", required=True, default=3)

    # move-state checkbox bag, e.g. {"done": true, "cancel": false}
    state_flags = fields.Json(string="States",
                              default=lambda s: {"done": True})

    company_ids = fields.Many2many("res.company")
    warehouse_ids = fields.Many2many("stock.warehouse")
    location_src_ids = fields.Many2many(
        "stock.location", relation="fr_loc_src_rel",
        domain=[("usage", "=", "internal")])
    location_dst_ids = fields.Many2many(
        "stock.location", relation="fr_loc_dst_rel",
        domain=[("usage", "=", "internal")])
    product_ids = fields.Many2many("product.product")
    template_ids = fields.Many2many("product.template")
    category_ids = fields.Many2many("product.category")
    uom_ids = fields.Many2many("uom.uom")
    picking_type_ids = fields.Many2many(
        "stock.picking.type", string="Operation Types")
    rule_ids = fields.Many2many("stock.rule", string="Stock Rules")
    extra_domain = fields.Json(string="Extra Filters", default=list)

    group_by_field = fields.Selection(
        [("variant", "Variant"), ("template", "Product Template"),
         ("category", "Category"), ("uom", "Unit of Measure"),
         ("src_location", "Source Location"),
         ("dst_location", "Destination Location"),
         ("warehouse", "Warehouse"), ("operation_type", "Operation Type"),
         ("rule", "Stock Rule"), ("company", "Company"),
         ("none", "No Grouping")],
        required=True, default="variant")
    model_ids = fields.Many2many("stats.model")

    show_stats_info = fields.Boolean(default=True)
    hypothesis_testing = fields.Boolean()
    shorten_figures = fields.Boolean(default=True)

    SERIES_FIELDS = {
        "variant": ["product_id"],
        "template": ["product_tmpl_id"],
        "uom": ["product_uom"],
        "src_location": ["location_id"],
        "dst_location": ["location_dest_id"],
        "warehouse": ["warehouse_id"],
        "operation_type": ["picking_type_id"],
        "rule": ["rule_id"],
        "company": ["company_id"],
        "none": [],
    }

    def get_series_field_specs(self):
        """Return [(dotted_path, kind)] describing series key components.

        Paths are resolvable against a stock.move search_read dict where
        m2o values arrive as (id, name) tuples.
        """
        self.ensure_one()
        g = self.group_by_field
        if g == "category":
            return [("product_tmpl_id.categ_id", "m2o")]
        specs = []
        for fname in self.SERIES_FIELDS[g]:
            kind = "m2o" if self.env["stock.move"]._fields[fname].type == "many2one" else "raw"
            specs.append((fname, kind))
        return specs

    def _sanitize_extra_domain(self):
        """Validate user-built extra domain against SAFE_DOMAIN_FIELDS."""
        domain = list(self.extra_domain or [])
        i = 0
        while i < len(domain):
            term = domain[i]
            if isinstance(term, str) and term in ("&", "|", "!"):
                i += 1
                continue
            if not isinstance(term, (list, tuple)) or len(term) != 3:
                raise ValueError(f"Invalid domain term: {term!r}")
            field_name = str(term[0]).split(".")[0].split(":")[0]
            if field_name not in SAFE_DOMAIN_FIELDS:
                raise ValueError(f"Field not allowed in extra filters: {field_name!r}")
            i += 1
        return domain

    def get_base_domain(self):
        self.ensure_one()
        domain = []
        states = [k for k, v in (self.state_flags or {}).items() if v]
        if states:
            domain.append(("state", "in", states))
        else:
            domain.append(("state", "=", "done"))
        if self.period_start:
            domain.append(("date", ">=", fields.Datetime.to_datetime(self.period_start)))
        if self.period_end:
            end_dt = fields.Datetime.to_datetime(self.period_end)
            domain.append(("date", "<=", end_dt.replace(hour=23, minute=59, second=59)))
        if self.company_ids:
            domain.append(("company_id", "in", self.company_ids.ids))
        if self.warehouse_ids:
            domain.append(("warehouse_id", "in", self.warehouse_ids.ids))
        if self.location_src_ids:
            domain.append(("location_id", "in", self.location_src_ids.ids))
        if self.location_dst_ids:
            domain.append(("location_dest_id", "in", self.location_dst_ids.ids))
        if self.template_ids:
            domain.append(("product_tmpl_id", "in", self.template_ids.ids))
        elif self.product_ids:
            domain.append(("product_id", "in", self.product_ids.ids))
        if self.category_ids:
            domain.append(("product_tmpl_id.categ_id", "in", self.category_ids.ids))
        if self.uom_ids:
            domain.append(("product_uom", "in", self.uom_ids.ids))
        if self.picking_type_ids:
            domain.append(("picking_type_id", "in", self.picking_type_ids.ids))
        if self.rule_ids:
            domain.append(("rule_id", "in", self.rule_ids.ids))
        extra = self._sanitize_extra_domain()
        if extra:
            domain = ["&"] + domain + extra
        return domain
