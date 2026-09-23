from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSyncModel(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = cls.env['odoo.sync.source'].create({
            'name': 'Remote', 'url': 'https://example.com', 'database': 'Prod-DB', 'api_key': 'key',
        })

    def test_xmlid_prefix_is_unique_per_source(self):
        self.assertEqual(self.source.xmlid_module, f'__sync_{self.source.id}_prod_db__')

    def test_domain_must_be_a_list(self):
        with self.assertRaises(ValidationError):
            self.env['odoo.sync.model'].create({
                'source_id': self.source.id,
                'model_id': self.env['ir.model']._get_id('res.partner'),
                'domain': "{'bad': 1}",
            })

    def test_order_puts_parents_before_children(self):
        SyncModel = self.env['odoo.sync.model']
        lines = SyncModel.create([
            SyncModel._default_values(self.source, name, 1)
            for name in ('res.partner.bank', 'res.partner', 'res.bank')
        ])
        self.source.action_order_models()
        sequence = {line.model: line.sequence for line in lines}
        self.assertLess(sequence['res.partner'], sequence['res.partner.bank'])
        self.assertLess(sequence['res.bank'], sequence['res.partner.bank'])
