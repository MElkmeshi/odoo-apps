from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain

from .phone_eg import normalize_eg_phone


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Typing a phone number in any contact selector must find the contact.
    # The base list is repeated because assigning the attribute replaces it.
    _rec_names_search = [
        'complete_name', 'email', 'ref', 'vat', 'company_registry',
        'phone', 'phone_normalized',
    ]

    # Enforced in the database, not only in Python, so two concurrent requests
    # cannot both pass the constraint and both insert. Partial: contacts without
    # an Egyptian mobile are unconstrained, and archived ones free their number.
    _phone_normalized_uniq = models.UniqueIndex(
        '(phone_normalized) WHERE phone_normalized IS NOT NULL AND active',
        "This phone number already belongs to another contact.",
    )

    phone_normalized = fields.Char(
        string='Normalised Phone',
        compute='_compute_phone_normalized',
        store=True,
        index=True,
        readonly=True,
        copy=False,
        help="Canonical 01XXXXXXXXX form of the phone, used to enforce uniqueness "
             "and to search by number regardless of how it was typed.",
    )

    def _search_display_name(self, operator, value):
        """Also match a phone typed in any format.

        _rec_names_search alone only does a literal ilike, so searching
        "+20 100 123 4567" finds nothing even though it is the stored
        01001234567 - the form users are most likely to type, since it is
        what appears on the contact's own screen.
        """
        domain = super()._search_display_name(operator, value)
        if operator.endswith('like') and isinstance(value, str):
            canonical = normalize_eg_phone(value)
            if canonical:
                return domain | Domain('phone_normalized', '=', canonical)
        return domain

    @api.depends('phone')
    def _compute_phone_normalized(self):
        for partner in self:
            partner.phone_normalized = normalize_eg_phone(partner.phone) or False

    @api.constrains('phone_normalized', 'active')
    def _check_phone_normalized_unique(self):
        """Duplicates the index check purely for the error message.

        The index alone raises a bare integrity error naming neither the
        number nor the contact already holding it.
        """
        for partner in self.filtered(lambda p: p.phone_normalized and p.active):
            duplicate = self.search([
                ('phone_normalized', '=', partner.phone_normalized),
                ('id', '!=', partner.id),
            ], limit=1)
            if duplicate:
                raise ValidationError(_(
                    "Phone number %(phone)s already belongs to %(name)s.",
                    phone=partner.phone_normalized,
                    name=duplicate.display_name,
                ))

    @api.model
    def _normalize_phone_in_vals(self, vals):
        """Store the canonical form in `phone` itself, so the UI stays consistent."""
        if vals.get('phone'):
            canonical = normalize_eg_phone(vals['phone'])
            if canonical:
                vals = dict(vals, phone=canonical)
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._normalize_phone_in_vals(vals) for vals in vals_list])

    def write(self, vals):
        return super().write(self._normalize_phone_in_vals(vals))
