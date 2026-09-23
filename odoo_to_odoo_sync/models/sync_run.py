import logging
import time
from datetime import timedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

from .client import SourceError
from .engine import SyncEngine

_logger = logging.getLogger(__name__)

CHUNK_SECONDS = 240
INCREMENTAL_MARGIN = timedelta(minutes=5)


class OdooSyncRun(models.Model):
    _name = 'odoo.sync.run'
    _description = 'Sync run'
    _order = 'id desc'

    name = fields.Char(compute='_compute_name')
    source_id = fields.Many2one('odoo.sync.source', required=True, ondelete='cascade', index=True)
    incremental = fields.Boolean(readonly=True, help="Only records changed in the source since the last run.")
    state = fields.Selection([
        ('queued', "Queued"),
        ('running', "Running"),
        ('done', "Done"),
        ('failed', "Failed"),
        ('cancelled', "Cancelled"),
    ], default='queued', required=True, readonly=True)
    phase = fields.Selection([
        ('count', "Counting"),
        ('copy', "Copying records"),
        ('relink', "Restoring links"),
        ('done', "Finished"),
    ], default='count', required=True, readonly=True)
    current_line_id = fields.Many2one('odoo.sync.model', string='Current Model', readonly=True, ondelete='set null')
    cursor = fields.Integer(readonly=True)
    relink_line_ids = fields.Many2many('odoo.sync.model', string='Models to Relink', readonly=True)
    started_at = fields.Datetime(readonly=True)
    finished_at = fields.Datetime(readonly=True)
    total = fields.Integer(readonly=True)
    processed = fields.Integer(readonly=True)
    created = fields.Integer(readonly=True)
    updated = fields.Integer(readonly=True)
    relinked = fields.Integer(readonly=True)
    skipped = fields.Integer(readonly=True)
    failed = fields.Integer(readonly=True)
    progress = fields.Float(compute='_compute_progress')
    error = fields.Text(readonly=True)
    log_ids = fields.One2many('odoo.sync.log', 'run_id', string='Log')

    @api.depends('source_id', 'started_at')
    def _compute_name(self):
        for run in self:
            run.name = f"{run.source_id.name} #{run.id}"

    @api.depends('processed', 'total', 'phase')
    def _compute_progress(self):
        for run in self:
            if run.phase == 'done':
                run.progress = 100
            else:
                run.progress = min(100.0, 100.0 * run.processed / run.total) if run.total else 0

    def action_cancel(self):
        self.filtered(lambda run: run.state in ('queued', 'running')).write({
            'state': 'cancelled', 'finished_at': fields.Datetime.now(),
        })

    def action_resume(self):
        for run in self:
            if run.state not in ('failed', 'cancelled'):
                raise UserError(_("Only a failed or cancelled run can be resumed."))
            if run.source_id.run_ids.filtered(lambda other: other.state in ('queued', 'running')):
                raise UserError(_("Another sync from this source is already in progress."))
        self.write({'state': 'queued', 'error': False, 'finished_at': False})
        self.env.ref('odoo_to_odoo_sync.ir_cron_process_runs')._trigger()

    @api.model
    def _cron_process(self):
        deadline = time.monotonic() + CHUNK_SECONDS
        run = self.search([('state', 'in', ('queued', 'running'))], order='id', limit=1)
        if not run:
            return
        run._process(deadline)
        if self.search_count([('state', 'in', ('queued', 'running'))]):
            self.env.ref('odoo_to_odoo_sync.ir_cron_process_runs')._trigger()

    def _process(self, deadline):
        self.ensure_one()
        if self.state == 'queued':
            self.write({'state': 'running', 'started_at': self.started_at or fields.Datetime.now()})
        engine = SyncEngine(self, self.source_id._client())
        try:
            while self.state == 'running':
                self._step(engine)
                remaining = self._save(engine)
                self.invalidate_recordset(['state'])
                if self.phase == 'done' or remaining <= 0 or time.monotonic() > deadline:
                    break
        except Exception as error:
            self.env.cr.rollback()
            _logger.exception("Sync run %s failed", self.id)
            message = str(error) if isinstance(error, SourceError) else f"{type(error).__name__}: {error}"
            self.write({'state': 'failed', 'error': message, 'finished_at': fields.Datetime.now()})
            self.env.cr.commit()

    def _save(self, engine):
        if engine.logs:
            self.env['odoo.sync.log'].create(engine.logs)
            engine.logs.clear()
        stats = dict(engine.stats)
        engine.stats.clear()
        self.write({
            name: self[name] + stats.get(name, 0)
            for name in ('processed', 'created', 'updated', 'relinked', 'skipped', 'failed')
        })
        pending = 0 if self.state in ('done', 'failed', 'cancelled') else max(self.total - self.processed, 0) + 1
        return self.env['ir.cron']._commit_progress(
            stats.get('processed', 0) + stats.get('relinked', 0), remaining=pending,
        )

    def _lines(self):
        return self.source_id.model_ids.sorted(lambda line: (line.sequence, line.id))

    def _since(self, line):
        if self.incremental and line.last_sync_date and 'write_date' in self.env[line.model]._fields:
            return fields.Datetime.to_string(line.last_sync_date - INCREMENTAL_MARGIN)
        return False

    def _next_line(self, lines, line):
        if not line:
            return lines[:1]
        position = list(lines).index(line) if line in lines else -1
        return lines[position + 1:position + 2]

    def _step(self, engine):
        if self.phase == 'count':
            self._count(engine)
            lines = self._lines()
            self.write({
                'phase': 'copy',
                'current_line_id': lines[:1].id,
                'cursor': 0,
                'relink_line_ids': [Command.set(lines.filtered('late_field_ids').ids)],
            })
            return
        if self.phase == 'copy':
            line = self.current_line_id
            if not line:
                self.write({
                    'phase': 'relink',
                    'current_line_id': self._lines().filtered(lambda l: l in self.relink_line_ids)[:1].id,
                    'cursor': 0,
                })
                return
            last_id, needs_relink = engine.copy_batch(line, self.cursor, self._since(line))
            if needs_relink and line not in self.relink_line_ids:
                self.relink_line_ids = [Command.link(line.id)]
            if last_id is None:
                self.write({'current_line_id': self._next_line(self._lines(), line).id, 'cursor': 0})
            else:
                self.cursor = last_id
            return
        if self.phase == 'relink':
            line = self.current_line_id
            if not line:
                self._finish()
                return
            last_id = engine.relink_batch(line, self.cursor, self._since(line))
            if last_id is None:
                pending = self._lines().filtered(lambda l: l in self.relink_line_ids)
                self.write({'current_line_id': self._next_line(pending, line).id, 'cursor': 0})
            else:
                self.cursor = last_id

    def _count(self, engine):
        total = 0
        for line in self._lines():
            domain = line._get_domain()
            since = self._since(line)
            if since:
                domain.append(('write_date', '>=', since))
            count = engine.client.call(line.model, 'search_count', domain=domain, context={'active_test': False})
            line.source_count = count
            total += count
        self.total = total

    def _finish(self):
        self._lines().write({'last_sync_date': self.started_at})
        self.write({
            'phase': 'done',
            'state': 'done',
            'current_line_id': False,
            'finished_at': fields.Datetime.now(),
        })


class OdooSyncLog(models.Model):
    _name = 'odoo.sync.log'
    _description = 'Sync log line'
    _order = 'id'

    run_id = fields.Many2one('odoo.sync.run', required=True, ondelete='cascade', index=True)
    level = fields.Selection([
        ('info', "Info"),
        ('warning', "Warning"),
        ('error', "Error"),
    ], required=True)
    model = fields.Char()
    source_id = fields.Integer(string='Source ID')
    record_id = fields.Integer(string='Record ID')
    message = fields.Text()
