import ast

from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError

EXCLUDED_MODEL_PREFIXES = (
    'ir.', 'base.', 'bus.', 'res.users.', 'res.device', 'res.config', 'auth', 'iap.',
    'web_tour.', 'web_editor.', 'html_editor.', 'digest.', 'onboarding.', 'report.',
    'odoo.sync.', 'mail.mail', 'mail.notification', 'mail.guest', 'mail.presence',
    'discuss.channel.rtc', 'website.visitor', 'website.track', 'spreadsheet.revision',
    'publisher_warranty', 'res.lang', 'res.groups', 'mail.alias',
)
INCLUDED_MODELS = {'ir.attachment'}

DEFAULT_DOMAINS = {
    'ir.attachment': [
        ('res_model', '!=', False),
        ('res_model', 'not in', ['ir.ui.view', 'ir.ui.menu', 'ir.module.module', 'res.lang']),
        ('type', '=', 'binary'),
    ],
}

DEFAULT_MATCH_FIELDS = {
    'res.users': ['login'],
    'res.company': ['name'],
    'product.template.attribute.line': ['product_tmpl_id', 'attribute_id'],
    'product.template.attribute.value': ['attribute_line_id', 'product_attribute_value_id'],
    'product.product': ['product_tmpl_id', 'product_template_attribute_value_ids'],
    'stock.warehouse': ['company_id', 'code'],
    'stock.location': ['company_id', 'complete_name'],
    'stock.picking.type': ['company_id', 'warehouse_id', 'sequence_code'],
    'account.journal': ['company_id', 'code'],
    'mail.followers': ['res_model', 'res_id', 'partner_id'],
    'properties.base.definition': ['properties_field_id'],
    'account.move.line': ['move_id', 'account_id', 'balance'],
    'discuss.channel.member': ['channel_id', 'partner_id'],
    'account.tax.repartition.line': ['tax_id', 'document_type', 'repartition_type', 'sequence'],
    'resource.calendar.attendance': ['calendar_id', 'dayofweek', 'day_period', 'week_type', 'hour_from', 'hour_to'],
}

DEFAULT_LATE_FIELDS = {
    'res.partner': ['active'],
    'account.move': ['state'],
    'account.payment': ['state'],
    'sale.order': ['state'],
    'purchase.order': ['state'],
}


def is_syncable_model(name):
    return name in INCLUDED_MODELS or not name.startswith(EXCLUDED_MODEL_PREFIXES)


class OdooSyncModel(models.Model):
    _name = 'odoo.sync.model'
    _description = 'Model to synchronize'
    _order = 'sequence, id'

    source_id = fields.Many2one('odoo.sync.source', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    model_id = fields.Many2one('ir.model', string='Model', required=True, ondelete='cascade')
    model = fields.Char(string='Technical Name', related='model_id.model', store=True)
    domain = fields.Char(default='[]', required=True, help="Only source records matching this domain are copied.")
    match_field_ids = fields.Many2many(
        'ir.model.fields', 'odoo_sync_model_match_field_rel', 'sync_model_id', 'field_id',
        string='Match On', domain="[('model_id', '=', model_id)]",
        help="When a source record has no External ID known here, look for an existing record "
             "with the same values in these fields before creating a new one.",
    )
    excluded_field_ids = fields.Many2many(
        'ir.model.fields', 'odoo_sync_model_excluded_field_rel', 'sync_model_id', 'field_id',
        string='Never Copy', domain="[('model_id', '=', model_id)]",
    )
    late_field_ids = fields.Many2many(
        'ir.model.fields', 'odoo_sync_model_late_field_rel', 'sync_model_id', 'field_id',
        string='Copy Last', domain="[('model_id', '=', model_id)]",
        help="Written after every model is copied, e.g. the state of a posted entry once its lines exist.",
    )
    source_count = fields.Integer(string='Source Records', readonly=True)
    last_sync_date = fields.Datetime(readonly=True, copy=False)

    _sql_constraints = [
        ('model_uniq', 'UNIQUE(source_id, model_id)', "Each model can only be listed once per source."),
    ]

    @api.constrains('domain')
    def _check_domain(self):
        for line in self:
            try:
                line._get_domain()
            except (ValueError, SyntaxError) as error:
                raise ValidationError(_("Invalid domain for %(model)s: %(error)s", model=line.model, error=error)) from error

    def _get_domain(self):
        self.ensure_one()
        domain = ast.literal_eval(self.domain or '[]')
        if not isinstance(domain, list):
            raise ValueError(_("a domain must be a list"))
        return domain

    @api.model
    def _default_values(self, source, model_name, count):
        IrModelFields = self.env['ir.model.fields']

        def field_ids(names):
            return [Command.set(IrModelFields.search([('model', '=', model_name), ('name', 'in', names or [])]).ids)]

        return {
            'source_id': source.id,
            'model_id': self.env['ir.model']._get_id(model_name),
            'domain': repr(DEFAULT_DOMAINS.get(model_name, [])),
            'match_field_ids': field_ids(DEFAULT_MATCH_FIELDS.get(model_name)),
            'late_field_ids': field_ids(DEFAULT_LATE_FIELDS.get(model_name)),
            'source_count': count,
        }
