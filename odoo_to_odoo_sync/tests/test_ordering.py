from odoo.tests import TransactionCase, tagged

from ..models.ordering import dependency_order


@tagged('post_install', '-at_install')
class TestOrdering(TransactionCase):

    def _order(self, depends, required=None):
        required = required or {}
        return dependency_order(
            {name: set(deps) for name, deps in depends.items()},
            {name: set(required.get(name, ())) for name in depends},
        )

    def test_dependencies_come_first(self):
        order = self._order({'line': {'order', 'product'}, 'order': {'partner'}, 'product': set(), 'partner': set()})
        self.assertLess(order.index('partner'), order.index('order'))
        self.assertLess(order.index('order'), order.index('line'))
        self.assertLess(order.index('product'), order.index('line'))

    def test_cycle_follows_required_links(self):
        order = self._order(
            {'company': {'partner'}, 'partner': {'company'}},
            {'company': {'partner'}},
        )
        self.assertEqual(order, ['partner', 'company'])

    def test_model_outside_a_cycle_waits_for_the_whole_cycle(self):
        order = self._order({
            'tax': {'account'},
            'account': {'tax', 'company'},
            'company': {'account'},
            'repartition': {'tax'},
        })
        self.assertEqual(order[-1], 'repartition')
        self.assertEqual(sorted(order), ['account', 'company', 'repartition', 'tax'])
