from odoo import api, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.depends('phone')
    def _compute_display_name(self):
        """Append the phone to the contact's name.

        Plain ASCII and the same format everywhere. An en/em dash renders as
        mojibake anywhere the value is read as latin-1, and core's dropdown
        markup ("\t --value--") leaks its literal dashes into every other
        place a contact is shown, so neither is used.

        Note this is display_name, so the number also appears wherever the
        contact is printed - quotations, invoices, email recipients - not
        only in contact selectors.
        """
        super()._compute_display_name()
        for partner in self:
            if partner.phone:
                partner.display_name = f"{partner.display_name} ({partner.phone})"
