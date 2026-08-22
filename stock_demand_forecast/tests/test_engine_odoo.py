import datetime as dt

from odoo import fields
from odoo.tests import TransactionCase, tagged

try:
    from stock_demand_forecast.models.services import engine
except ImportError:
    from odoo.addons.stock_demand_forecast.models.services import engine


@tagged("post_install", "-at_install")
class TestEngine(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.prod = cls.env["product.product"].create({"name": "Desk"})
        cls.stats = cls.env["stats.model"].create({
            "reference": "H1", "method": "autoreg", "lags": 2})
        cls.report = cls.env["forecast.report"].create({
            "name": "Test", "interval": "month", "horizon": 2,
            "state_flags": {"done": True}, "group_by_field": "variant",
            "model_ids": [(6, 0, cls.stats.ids)],
            "product_ids": [(6, 0, cls.prod.ids)],
        })

    def _mk_move(self, qty, months_ago):
        date = fields.Datetime.now() - dt.timedelta(days=30 * months_ago)
        picking_type = self.env.ref("stock.picking_type_out")
        return self.env["stock.move"].create({
            "product_id": self.prod.id,
            "product_uom_qty": qty, "quantity": qty,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id":
                self.env.ref("stock.stock_location_customers").id,
            "picking_type_id": picking_type.id,
            "date": date,
        })

    def _mark_done(self, move):
        move.state = "done"

    def test_display_name_format(self):
        self.assertEqual(self.stats.display_name, "H1 (AutoReg, 2, c)")

    def test_build_series_buckets_months(self):

        for i in range(14):  # 14 distinct months of history
            move = self._mk_move(qty=10 + i, months_ago=i)
            self._mark_done(move)
        df = engine.build_series(self.report)
        self.assertGreaterEqual(len(df.columns), 1)
        self.assertGreater(df.iloc[:, 0].sum(), 0)

    def test_run_forecast_payload_shape(self):

        for i in range(14):
            move = self._mk_move(qty=50 + i * 3, months_ago=i)
            self._mark_done(move)
        payload = engine.run_forecast(self.report)
        self.assertEqual(payload["meta"]["interval"], "month")
        self.assertEqual(len(payload["forecast_labels"]), 2)
        series = payload["series"][0]
        self.assertIsNone(series["error"])
        self.assertEqual(len(series["forecast"]), 2)
        self.assertIn("H1 (AutoReg", series["label"])

    def test_hypothesis_testing_splits_history(self):

        for i in range(16):
            move = self._mk_move(qty=50 + i * 3, months_ago=i)
            self._mark_done(move)
        self.report.hypothesis_testing = True
        payload = engine.run_forecast(self.report)
        series = payload["series"][0]
        # 14 train periods + 2 held-out actuals shown as history
        self.assertEqual(len(series["history_pre"]), 14)
        self.assertEqual(series["history"], [53.0, 50.0])
        self.assertEqual(series["actuals"], [53.0, 50.0])

    def test_extra_domain_whitelist_rejects_bad_field(self):
        self.report.extra_domain = [("user_id", "=", 1)]
        with self.assertRaises(ValueError):
            self.report.get_base_domain()

    def test_insufficient_history_yields_error_entry(self):

        move = self._mk_move(qty=5, months_ago=1)
        self._mark_done(move)
        payload = engine.run_forecast(self.report)
        series = payload["series"][0]
        self.assertIsNotNone(series["error"])
