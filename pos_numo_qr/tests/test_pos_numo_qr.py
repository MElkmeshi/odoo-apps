from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import TestPoSCommon
from odoo.addons.pos_numo_qr import const


@tagged('post_install', '-at_install')
class TestPosNumoQr(TestPoSCommon):

    def setUp(self):
        super().setUp()
        self.valid_vals = {
            'name': "NUMO QR",
            # `use_payment_terminal` is only reachable in the UI once the
            # integration is set to Terminal; an onchange clears it otherwise.
            'payment_method_type': 'terminal',
            'use_payment_terminal': 'numo_qr',
            'numo_account_name': "Hajat Market",
            'numo_iban': "LY19024007010118519020701",
            'numo_bank': '024',
            'numo_merchant_name': "Hajat Market",
            'numo_city': "Tripoli",
            'company_id': self.env.company.id,
        }

    def _create(self, **overrides):
        return self.env['pos.payment.method'].create({**self.valid_vals, **overrides})

    def test_valid_configuration_saves(self):
        method = self._create()
        self.assertEqual(method.use_payment_terminal, 'numo_qr')
        self.assertEqual(method.numo_mcc, '9999', "MCC should default to the catch-all code")

    def test_numo_qr_is_offered_as_a_terminal(self):
        codes = [code for code, _label in self.env['pos.payment.method']
                 ._get_payment_terminal_selection()]
        self.assertIn('numo_qr', codes)

    def test_config_fields_reach_the_browser(self):
        fields = self.env['pos.payment.method']._load_pos_data_fields(self.basic_config)
        for name in ('numo_iban', 'numo_bank_code', 'numo_merchant_name', 'numo_city',
                     'numo_auto_print'):
            self.assertIn(name, fields, "%s must be loaded into the POS session" % name)

    def test_missing_required_field_is_refused(self):
        with self.assertRaises(ValidationError):
            self._create(numo_iban=False)

    def test_malformed_iban_is_refused(self):
        with self.assertRaises(ValidationError):
            self._create(numo_iban="GB33BUKB20201555555555")

    def test_malformed_bank_code_is_refused(self):
        """Only reachable through Other now: a picked bank cannot be malformed."""
        with self.assertRaises(ValidationError):
            self._create(numo_bank=const.BANK_OTHER, numo_bank_code="24")

    def test_malformed_mcc_is_refused(self):
        with self.assertRaises(ValidationError):
            self._create(numo_mcc="541")

    def test_other_terminals_are_not_constrained(self):
        """A method that is not NUMO must not be forced to carry NUMO fields."""
        method = self.env['pos.payment.method'].create({
            'name': "Cash",
            'company_id': self.env.company.id,
        })
        self.assertFalse(method.numo_iban)

    def test_auto_print_defaults_to_off(self):
        """Paper costs money, and most tills let the customer see the screen."""
        self.assertFalse(self._create().numo_auto_print)

    def test_a_cash_journal_is_refused(self):
        """NUMO settles into the bank after the session closes, never the drawer.

        Booking it as cash tells the cashier to count money that is not there.
        """
        cash_journal = self.env['account.journal'].search(
            [('type', '=', 'cash'), ('company_id', '=', self.env.company.id)], limit=1
        )
        self.assertTrue(cash_journal, "the test company should have a cash journal")
        with self.assertRaises(ValidationError):
            self._create(journal_id=cash_journal.id)

    def test_a_bank_journal_is_accepted(self):
        bank_journal = self.env['account.journal'].search(
            [('type', '=', 'bank'), ('company_id', '=', self.env.company.id)], limit=1
        )
        self.assertTrue(bank_journal, "the test company should have a bank journal")
        method = self._create(journal_id=bank_journal.id)
        self.assertEqual(method.journal_id, bank_journal)

    def test_a_cash_journal_is_fine_on_a_non_numo_method(self):
        """The constraint must not leak onto every other payment method."""
        cash_journal = self.env['account.journal'].search(
            [('type', '=', 'cash'), ('company_id', '=', self.env.company.id)], limit=1
        )
        method = self.env['pos.payment.method'].create({
            'name': "Cash",
            'journal_id': cash_journal.id,
            'company_id': self.env.company.id,
        })
        self.assertEqual(method.journal_id, cash_journal)

    def test_picking_a_bank_fills_in_its_code(self):
        """The code is what lands in tag 30, so the picker has to set it."""
        method = self._create(numo_bank='013')
        self.assertEqual(method.numo_bank_code, '013', "Aman Bank is code 013")

    def test_changing_the_bank_changes_the_code(self):
        method = self._create()
        self.assertEqual(method.numo_bank_code, '024')
        method.numo_bank = '005'
        self.assertEqual(method.numo_bank_code, '005', "the code must follow the bank")

    def test_other_lets_an_unlisted_code_through(self):
        """A newly licensed bank must not be a blocker until the next release."""
        method = self._create(numo_bank=const.BANK_OTHER, numo_bank_code="099")
        self.assertEqual(method.numo_bank_code, '099')

    def test_other_still_rejects_a_malformed_code(self):
        with self.assertRaises(ValidationError):
            self._create(numo_bank=const.BANK_OTHER, numo_bank_code="99")

    def test_other_requires_a_code(self):
        with self.assertRaises(ValidationError):
            self._create(numo_bank=const.BANK_OTHER, numo_bank_code=False)

    def test_missing_bank_is_refused(self):
        with self.assertRaises(ValidationError):
            self._create(numo_bank=False, numo_bank_code=False)

    def test_every_listed_bank_has_a_three_digit_code(self):
        """A typo here would silently send money to the wrong institution."""
        for code, name in const.LIBYAN_BANKS:
            self.assertRegex(code, r'^\d{3}$', "%s has a malformed code" % name)
        self.assertEqual(
            len(const.BANK_CODES), len(const.LIBYAN_BANKS), "duplicate bank code"
        )
