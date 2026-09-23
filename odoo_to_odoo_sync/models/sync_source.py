import re
from concurrent.futures import ThreadPoolExecutor

from odoo import _, api, fields, models, release
from odoo.exceptions import UserError

from .client import SourceClient, SourceError
from .ordering import dependency_order
from .sync_model import DEFAULT_DOMAINS, is_syncable_model


class OdooSyncSource(models.Model):
    _name = 'odoo.sync.source'
    _description = 'Source Odoo database'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    url = fields.Char(string='URL', required=True, help="e.g. https://mycompany.odoo.com")
    database = fields.Char(required=True)
    login = fields.Char(required=True, help="Login of the user the API key belongs to.")
    api_key = fields.Char(
        string='API Key', required=True, groups='base.group_system',
        help="Created in the source database under Preferences > Account Security > New API Key.",
    )
    xmlid_module = fields.Char(
        string='External ID Prefix', readonly=True, copy=False,
        help="Records copied from this source get External IDs under this prefix, "
             "which is how a later run recognises them.",
    )
    batch_size = fields.Integer(default=200, required=True)
    sync_translations = fields.Boolean(string='Copy Translations', default=True)
    model_ids = fields.One2many('odoo.sync.model', 'source_id', string='Models', context={'active_test': False})
    run_ids = fields.One2many('odoo.sync.run', 'source_id', string='Runs')
    run_count = fields.Integer(compute='_compute_run_count')

    _sql_constraints = [
        ('xmlid_module_uniq', 'UNIQUE(xmlid_module)', "Two sources cannot share an External ID prefix."),
    ]

    @api.depends('run_ids')
    def _compute_run_count(self):
        for source in self:
            source.run_count = len(source.run_ids)

    @api.model_create_multi
    def create(self, vals_list):
        sources = super().create(vals_list)
        for source in sources:
            slug = re.sub(r'[^a-z0-9]+', '_', source.database.lower()).strip('_')
            source.xmlid_module = f'__sync_{source.id}_{slug}__'
        return sources

    def _client(self):
        self.ensure_one()
        return SourceClient(self.url, self.database, self.login, self.sudo().api_key)

    def action_test_connection(self):
        self.ensure_one()
        client = self._client()
        try:
            installed = client.call(
                'ir.module.module', 'search_read',
                domain=[('state', '=', 'installed')], fields=['name', 'latest_version'],
            )
        except SourceError as error:
            raise UserError(str(error)) from error
        source_modules = {module['name']: module['latest_version'] for module in installed}
        source_series = '.'.join((source_modules.get('base') or '').split('.')[:2])
        if source_series != release.major_version:
            raise UserError(_(
                "The source runs Odoo %(source)s and this database runs Odoo %(target)s. "
                "Both must be on the same series.",
                source=source_series or '?', target=release.major_version,
            ))
        local_modules = set(self.env['ir.module.module'].search([('state', '=', 'installed')]).mapped('name'))
        only_source = sorted(set(source_modules) - local_modules)
        message = _("Connected to %(db)s (Odoo %(series)s).", db=self.database, series=source_series)
        if only_source:
            message += ' ' + _(
                "Installed there but not here, so their data will not be copied: %s", ', '.join(only_source),
            )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Connection works"),
                'message': message,
                'type': 'warning' if only_source else 'success',
                'sticky': bool(only_source),
            },
        }

    def action_load_models(self):
        self.ensure_one()
        client = self._client()
        try:
            source_models = {
                model['model'] for model in client.call(
                    'ir.model', 'search_read', domain=[('transient', '=', False)], fields=['model'],
                )
            }
        except SourceError as error:
            raise UserError(str(error)) from error
        listed = set(self.with_context(active_test=False).model_ids.mapped('model'))
        candidates = sorted(
            name for name, model_class in self.env.registry.items()
            if not model_class._abstract and not model_class._transient and model_class._auto
            and name in source_models and name not in listed and is_syncable_model(name)
        )

        def count(name):
            try:
                return name, client.call(
                    name, 'search_count', domain=DEFAULT_DOMAINS.get(name, []), context={'active_test': False},
                )
            except SourceError:
                return name, None

        with ThreadPoolExecutor(max_workers=8) as executor:
            counts = dict(executor.map(count, candidates))
        SyncModel = self.env['odoo.sync.model']
        SyncModel.create([
            SyncModel._default_values(self, name, counts[name]) for name in candidates if counts[name]
        ])
        self.action_order_models()
        unreadable = sorted(name for name in candidates if counts[name] is None)
        if not unreadable:
            return True
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Some models could not be read"),
                'message': _(
                    "The API key's user has no access to: %s. Give that user full access "
                    "(e.g. Settings > Users, all Administrator rights and every company), then load again.",
                    ', '.join(unreadable),
                ),
                'type': 'warning',
                'sticky': True,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def action_order_models(self):
        for source in self:
            lines = source.with_context(active_test=False).model_ids
            by_model = {line.model: line for line in lines}
            with_reference = {
                name for name in by_model
                if any(field.type == 'many2one_reference' for field in self.env[name]._fields.values())
            }
            depends, required = {}, {}
            for name, line in by_model.items():
                fields_map = self.env[name]._fields
                depends[name], required[name] = set(), set()
                for field in fields_map.values():
                    if (
                        field.type in ('many2one', 'many2many') and field.store
                        and not (field.compute and field.readonly) and field.comodel_name in by_model
                    ):
                        depends[name].add(field.comodel_name)
                        if field.required or field.name in self.env[name]._inherits.values():
                            required[name].add(field.comodel_name)
                for field_name in line.match_field_ids.mapped('name'):
                    field = fields_map.get(field_name)
                    if field is not None and field.type in ('many2one', 'many2many') and field.comodel_name in by_model:
                        depends[name].add(field.comodel_name)
                        required[name].add(field.comodel_name)
                if name in with_reference:
                    depends[name] |= set(by_model) - with_reference
                else:
                    depends[name] -= with_reference - required[name]
                depends[name].discard(name)
                required[name].discard(name)
            for index, name in enumerate(dependency_order(depends, required), start=1):
                by_model[name].sequence = index * 10
        return True

    def _start(self, incremental):
        self.ensure_one()
        if self.run_ids.filtered(lambda run: run.state in ('queued', 'running')):
            raise UserError(_("A sync from this source is already in progress."))
        if not self.model_ids:
            raise UserError(_("Add the models to copy first, or use Load Models."))
        run = self.env['odoo.sync.run'].create({'source_id': self.id, 'incremental': incremental})
        self.env.ref('odoo_to_odoo_sync.ir_cron_process_runs')._trigger()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'odoo.sync.run',
            'res_id': run.id,
            'view_mode': 'form',
        }

    def action_start_full(self):
        return self._start(incremental=False)

    def action_start_incremental(self):
        return self._start(incremental=True)

    def action_view_runs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Runs"),
            'res_model': 'odoo.sync.run',
            'view_mode': 'list,form',
            'domain': [('source_id', '=', self.id)],
            'context': {'default_source_id': self.id},
        }
