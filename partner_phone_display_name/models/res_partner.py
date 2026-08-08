from odoo import api, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.depends('phone')
    def _compute_display_name(self):
        """Append the phone to the contact's name.

        Note this is display_name, so the number also appears wherever the
        contact is printed — quotations, invoices, email recipients — not
        only in contact selectors.
        """
        super()._compute_display_name()
        for partner in self:
            if not partner.phone:
                continue
            if partner.env.context.get('formatted_display_name'):
                # Matches how core renders extra info in dropdowns.
                partner.display_name = f"{partner.display_name} \t --{partner.phone}--"
            else:
                partner.display_name = f"{partner.display_name} — {partner.phone}"
