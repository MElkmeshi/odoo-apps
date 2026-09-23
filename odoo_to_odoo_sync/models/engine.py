from collections import defaultdict

from odoo import Command, fields
from odoo.tools import SQL

MAGIC_FIELDS = {'id', 'create_uid', 'create_date', 'write_uid', 'write_date', 'display_name', '__last_update'}
SKIPPED_TYPES = {'one2many', 'properties', 'properties_definition'}
REFERENCE_TYPES = {'many2one', 'many2many', 'many2one_reference', 'reference'}
EXTRA_FIELDS = {'ir.attachment': {'datas'}}
EXCLUDED_FIELDS = {
    'ir.attachment': {'store_fname', 'db_datas', 'checksum', 'file_size', 'index_content', 'raw'},
    'res.users': {'password', 'totp_secret', 'signature'},
    'res.company': {'chart_template'},
    'res.partner.bank': {'allow_out_payment'},
    'product.template.attribute.value': {'ptav_product_variant_ids'},
}
SOURCE_CONTEXT = {'active_test': False, 'lang': 'en_US'}
TARGET_CONTEXT = {
    'active_test': False,
    'lang': 'en_US',
    'tracking_disable': True,
    'mail_create_nolog': True,
    'mail_create_nosubscribe': True,
    'mail_notrack': True,
    'mail_auto_subscribe_no_notify': True,
    'no_reset_password': True,
    'check_move_validity': False,
    'skip_invoice_sync': True,
    'skip_readonly_check': True,
}
MODEL_CONTEXT = {
    'res.company': {'import_file': True},
}


class SyncEngine:

    def __init__(self, run, client):
        self.run = run
        self.source = run.source_id
        self.client = client
        env = run.env
        companies = env['res.company'].sudo().search([])
        self.env = env(su=True, context=dict(env.context, **TARGET_CONTEXT, allowed_company_ids=companies.ids))
        self.plan = {line.model for line in self.source.model_ids}
        self.model_tables = {
            model_class._table for model_class in self.env.registry.values() if not model_class._abstract
        }
        self.cache = defaultdict(dict)
        self.unresolvable = defaultdict(set)
        self.source_fields = {}
        self.source_langs = None
        self.source_companies = None
        self.warned = set()
        self.logs = []
        self.stats = defaultdict(int)

    def log(self, level, model, message, source_id=None, record_id=None):
        self.logs.append({
            'run_id': self.run.id,
            'level': level,
            'model': model,
            'source_id': source_id,
            'record_id': record_id,
            'message': message[:2000],
        })
        if level == 'error':
            self.stats['failed'] += 1

    def _xmlid_name(self, model, source_id):
        return f"{model.replace('.', '_')}_{source_id}"

    def _companies(self):
        if self.source_companies is None:
            self.source_companies = [
                company['id'] for company in self.client.call(
                    'res.company', 'search_read', domain=[], fields=['id'], order='id',
                )
            ]
        return self.source_companies

    def _source_context(self, **extra):
        return {**SOURCE_CONTEXT, 'allowed_company_ids': self._companies(), **extra}

    def _source_field_names(self, model):
        if model not in self.source_fields:
            self.source_fields[model] = set(self.client.call(model, 'fields_get', attributes=['type']))
        return self.source_fields[model]

    def copy_fields(self, line):
        model = line.model
        available = self._source_field_names(model)
        excluded = EXCLUDED_FIELDS.get(model, set()) | set(line.excluded_field_ids.mapped('name'))
        extra = EXTRA_FIELDS.get(model, set())
        names = []
        for name, field in self.env[model]._fields.items():
            if name in MAGIC_FIELDS or name in excluded or name not in available or field.type in SKIPPED_TYPES:
                continue
            if field.type == 'many2many' and field.relation in self.model_tables:
                continue
            if name in extra or (field.store and not (field.compute and field.readonly)):
                names.append(name)
        return names

    def match_fields(self, line):
        available = self._source_field_names(line.model)
        return [name for name in line.match_field_ids.mapped('name') if name in available]

    def _needs_relink(self, field):
        if field.type in ('many2one', 'many2many'):
            return field.comodel_name in self.plan
        return field.type in ('many2one_reference', 'reference')

    def _split(self, line):
        Model = self.env[line.model]
        late = set(line.late_field_ids.mapped('name'))
        plain, per_company, late_fields = [], [], []
        for name in self.copy_fields(line):
            if name in late:
                late_fields.append(name)
            elif Model._fields[name].company_dependent:
                per_company.append(name)
            else:
                plain.append(name)
        return plain, per_company, late_fields

    def _with_model_fields(self, Model, names):
        result = set(names)
        for name in names:
            field = Model._fields[name]
            if field.type == 'many2one_reference':
                result.add(field.model_field)
        return sorted(result)

    def _batch_size(self, Model, fields):
        if any(Model._fields[name].type == 'binary' for name in fields):
            return min(self.source.batch_size, 20)
        return self.source.batch_size

    def _read(self, Model, domain, fields, limit):
        return self.client.call(
            Model._name, 'search_read',
            domain=domain, fields=self._with_model_fields(Model, fields), limit=limit, order='id', load='',
            context=self._source_context(),
        )

    def _read_per_company(self, Model, source_ids, fields):
        if not fields or not source_ids:
            return {}
        per_company = {}
        for company_id in self._companies():
            rows = self.client.call(
                Model._name, 'search_read',
                domain=[('id', 'in', source_ids)], fields=self._with_model_fields(Model, fields), load='',
                context=self._source_context(allowed_company_ids=[company_id]),
            )
            per_company[company_id] = {row['id']: row for row in rows}
        return per_company

    def _refs(self, field, row):
        value = row.get(field.name)
        if not value:
            return []
        if field.type == 'many2one':
            return [(field.comodel_name, value)]
        if field.type == 'many2many':
            return [(field.comodel_name, source_id) for source_id in value]
        if field.type == 'many2one_reference':
            model = row.get(field.model_field)
            return [(model, value)] if model in self.env else []
        model, _sep, source_id = value.partition(',')
        return [(model, int(source_id))] if model in self.env and source_id.isdigit() else []

    def _prefetch(self, Model, rows, fields):
        wanted = defaultdict(set)
        for name in fields:
            field = Model._fields[name]
            if field.type in REFERENCE_TYPES:
                for row in rows:
                    for model, source_id in self._refs(field, row):
                        wanted[model].add(source_id)
        for model, source_ids in wanted.items():
            self.resolve(model, source_ids)

    def resolve(self, model, source_ids):
        known = self.cache[model]
        missing = {
            source_id for source_id in source_ids
            if source_id not in known and source_id not in self.unresolvable[model]
        }
        table = SQL.identifier(self.env[model]._table)
        if missing:
            names = {self._xmlid_name(model, source_id): source_id for source_id in missing}
            rows = self.env.execute_query(SQL(
                "SELECT d.name, d.res_id FROM ir_model_data d JOIN %s r ON r.id = d.res_id "
                "WHERE d.module = %s AND d.model = %s AND d.name IN %s",
                table, self.source.xmlid_module, model, tuple(names),
            ))
            for name, res_id in rows:
                known[names[name]] = res_id
                missing.discard(names[name])
        if missing:
            source_xmlids = self.client.call(
                'ir.model.data', 'search_read',
                domain=[('model', '=', model), ('res_id', 'in', sorted(missing))],
                fields=['module', 'name', 'res_id'], load='',
            )
            by_key = {(xmlid['module'], xmlid['name']): xmlid['res_id'] for xmlid in source_xmlids}
            if by_key:
                keys = SQL(', ').join(SQL('(%s, %s)', module, name) for module, name in by_key)
                rows = self.env.execute_query(SQL(
                    "SELECT d.module, d.name, d.res_id FROM ir_model_data d JOIN %s r ON r.id = d.res_id "
                    "WHERE d.model = %s AND (d.module, d.name) IN (%s)",
                    table, model, keys,
                ))
                for module, name, res_id in rows:
                    source_id = by_key[(module, name)]
                    known[source_id] = res_id
                    missing.discard(source_id)
        if missing and model not in self.plan:
            self.unresolvable[model].update(missing)
        return {source_id: known[source_id] for source_id in source_ids if source_id in known}

    def _register(self, model, pairs):
        if not pairs:
            return
        uid = self.env.uid
        values = SQL(', ').join(
            SQL(
                "(%s, %s, %s, %s, true, %s, %s, now() at time zone 'UTC', now() at time zone 'UTC')",
                self.source.xmlid_module, self._xmlid_name(model, source_id), model, target_id, uid, uid,
            )
            for source_id, target_id in pairs.items()
        )
        self.env.cr.execute(SQL(
            "INSERT INTO ir_model_data (module, name, model, res_id, noupdate, create_uid, write_uid, create_date, write_date) "
            "VALUES %s ON CONFLICT (module, name) DO UPDATE SET res_id = EXCLUDED.res_id, model = EXCLUDED.model",
            values,
        ))
        self.cache[model].update(pairs)

    def _transform(self, Model, row, fields, relinking=False):
        vals = {}
        deferred = False
        blocking = []
        for name in fields:
            field = Model._fields[name]
            if field.type not in REFERENCE_TYPES:
                vals[name] = row.get(name)
                continue
            refs = self._refs(field, row)
            mapped, pending, dropped = [], False, False
            for model, source_id in refs:
                target_id = self.cache[model].get(source_id)
                if target_id:
                    mapped.append((model, target_id))
                elif model in self.plan:
                    pending = True
                else:
                    dropped = True
                    if field.type != 'many2one_reference':
                        self._warn_dropped(Model._name, name, model)
            if field.type == 'many2many':
                if pending:
                    deferred = True
                    if field.required and not mapped:
                        blocking.append(name)
                elif mapped or not relinking:
                    vals[name] = [Command.set([target_id for _model, target_id in mapped])]
                continue
            if mapped:
                model, target_id = mapped[0]
                vals[name] = f'{model},{target_id}' if field.type == 'reference' else target_id
            elif pending:
                deferred = True
                if field.required or field.type == 'many2one_reference':
                    blocking.append(name)
            elif dropped or (field.type == 'many2one_reference' and row.get(name)):
                if field.type == 'many2one_reference':
                    blocking.append(name)
                elif not relinking and not field.required:
                    vals[name] = False
            elif not relinking:
                vals[name] = False
        return vals, deferred, blocking

    def _company_vals(self, Model, row, fields):
        if not row:
            return {}, False
        vals, deferred, _blocking = self._transform(Model, row, fields, relinking=True)
        return {name: value for name, value in vals.items() if value not in (False, None, '')}, deferred

    def _warn_dropped(self, model, field_name, comodel):
        key = (model, field_name, comodel)
        if key not in self.warned:
            self.warned.add(key)
            self.log(
                'warning', model,
                f"{field_name}: some linked {comodel} records do not exist here and are not being copied, "
                f"so those links were left empty. Add {comodel} to the models to keep them.",
            )

    def _match(self, Model, row, match_fields, claimed):
        domain = []
        sets = {}
        for name in match_fields:
            field = Model._fields[name]
            if field.type in REFERENCE_TYPES:
                refs = self._refs(field, row)
                mapped = [self.cache[model].get(source_id) for model, source_id in refs]
                if not all(mapped):
                    return None
                if field.type == 'many2many':
                    sets[name] = set(mapped)
                    continue
                if not mapped:
                    value = False
                elif field.type == 'reference':
                    value = f'{refs[0][0]},{mapped[0]}'
                else:
                    value = mapped[0]
            else:
                value = row.get(name)
            domain.append((name, '=', value))
        if not domain and not sets:
            return None
        candidates = Model.search(domain, order='id')
        taken = claimed | self._claimed(Model._name, candidates.ids)
        for candidate in candidates:
            if candidate.id in taken:
                continue
            if all(set(candidate[name].ids) == ids for name, ids in sets.items()):
                return candidate.id
        return None

    def _claimed(self, model, target_ids):
        if not target_ids:
            return set()
        rows = self.env.execute_query(SQL(
            "SELECT res_id FROM ir_model_data WHERE module = %s AND model = %s AND res_id IN %s",
            self.source.xmlid_module, model, tuple(target_ids),
        ))
        return {res_id for (res_id,) in rows}

    def _home_company(self, Model, row):
        if 'company_id' in Model._fields and row.get('company_id'):
            return row['company_id']
        if 'company_ids' in Model._fields and row.get('company_ids'):
            return row['company_ids'][0]
        return None

    def _target_company(self, source_company_id):
        if not source_company_id:
            return None
        return self.resolve('res.company', [source_company_id]).get(source_company_id)

    def _model(self, model):
        return self.env[model].with_context(**MODEL_CONTEXT.get(model, {}))

    def copy_batch(self, line, after_id, since):
        model = line.model
        Model = self._model(model)
        plain, per_company, late = self._split(line)
        match_fields = self.match_fields(line)
        domain = line._get_domain() + [('id', '>', after_id)]
        if since:
            domain.append(('write_date', '>=', since))
        read_fields = sorted(set(plain) | set(match_fields) | ({'company_id', 'company_ids'} & set(Model._fields)))
        read_fields = [name for name in read_fields if name in self._source_field_names(model)]
        rows = self._read(Model, domain, read_fields, self._batch_size(Model, plain))
        if not rows:
            return None, False
        source_ids = [row['id'] for row in rows]
        company_rows = self._read_per_company(Model, source_ids, per_company)
        self._prefetch(Model, rows, read_fields)
        for by_id in company_rows.values():
            self._prefetch(Model, list(by_id.values()), per_company)
        self.resolve('res.company', self._companies())
        targets = self.resolve(model, source_ids)
        prefetch = tuple(targets.values())
        claimed = set(prefetch)
        needs_relink = bool(late)
        to_create = defaultdict(list)
        mapped = {}
        for row in rows:
            source_id = row['id']
            vals, deferred, blocking = self._transform(Model, row, plain)
            needs_relink |= deferred
            home = self._home_company(Model, row)
            home_vals, home_deferred = self._company_vals(Model, company_rows.get(home, {}).get(source_id), per_company)
            needs_relink |= home_deferred
            target_id = targets.get(source_id)
            if not target_id and match_fields:
                target_id = self._match(Model, row, match_fields, claimed)
                if target_id:
                    claimed.add(target_id)
            if blocking and not target_id:
                self._skip(Model, source_id, blocking, row)
                continue
            for name in blocking:
                vals.pop(name, None)
            if target_id:
                record = Model.browse(target_id).with_prefetch(prefetch)
                if self._write(record, self._changes(record, vals), source_id):
                    mapped[source_id] = target_id
                    self.stats['updated'] += 1
            else:
                vals.update(home_vals)
                to_create[self._target_company(home)].append((source_id, vals))
        for company_id, entries in to_create.items():
            TargetModel = Model.with_company(company_id) if company_id else Model
            mapped.update(self._create(TargetModel, entries))
        self._register(model, mapped)
        needs_relink |= self._write_per_company(Model, mapped, company_rows, per_company)
        if self.source.sync_translations:
            self._copy_translations(Model, mapped, plain)
        self.stats['processed'] += len(rows)
        return rows[-1]['id'], needs_relink

    def _write_per_company(self, Model, mapped, company_rows, fields, relinking=False):
        deferred = False
        for source_company_id, by_id in company_rows.items():
            target_company_id = self._target_company(source_company_id)
            if not target_company_id:
                continue
            for source_id, row in by_id.items():
                target_id = mapped.get(source_id)
                if not target_id:
                    continue
                vals, row_deferred = self._company_vals(Model, row, fields)
                deferred |= row_deferred
                record = Model.browse(target_id).with_company(target_company_id)
                vals = self._changes(record, vals)
                if vals and self._write(record, vals, source_id) and relinking:
                    self.stats['relinked'] += 1
        return deferred

    def _skip(self, Model, source_id, blocking, row):
        if all(Model._fields[name].type == 'many2one_reference' for name in blocking):
            self.stats['skipped'] += 1
            self.log('warning', Model._name, "Skipped: the record it belongs to was not copied.", source_id)
            return
        missing = ', '.join(
            f"{name} → {model_name} #{ref_id}"
            for name in blocking
            for model_name, ref_id in self._refs(Model._fields[name], row)
        )
        self.log('error', Model._name, f"Not copied, a required link is missing here: {missing}", source_id)

    def _write(self, record, vals, source_id):
        if not vals:
            return True
        try:
            with self.env.cr.savepoint():
                record.write(vals)
            return True
        except Exception as error:  # noqa: BLE001
            self.log('error', record._name, f"Update failed: {error}", source_id, record.id)
            return False

    def _create(self, Model, entries):
        if len(entries) > 1:
            try:
                with self.env.cr.savepoint():
                    records = Model.create([vals for _source_id, vals in entries])
                self.stats['created'] += len(records)
                return {source_id: record.id for (source_id, _vals), record in zip(entries, records)}
            except Exception:  # noqa: BLE001
                pass
        created = {}
        for source_id, vals in entries:
            try:
                with self.env.cr.savepoint():
                    created[source_id] = Model.create(vals).id
                self.stats['created'] += 1
            except Exception as error:  # noqa: BLE001
                self.log('error', Model._name, f"Create failed: {error}", source_id)
        return created

    def _languages(self):
        if self.source_langs is None:
            source = {lang['code'] for lang in self.client.call(
                'res.lang', 'search_read', domain=[], fields=['code'],
            )}
            local = {code for code, _name in self.env['res.lang'].get_installed()}
            self.source_langs = sorted((source & local) - {'en_US'})
        return self.source_langs

    def _copy_translations(self, Model, mapped, fields):
        translated = [name for name in fields if Model._fields[name].translate]
        if not translated or not mapped:
            return
        for lang in self._languages():
            rows = self.client.call(
                Model._name, 'read', ids=sorted(mapped), fields=translated, load='',
                context=self._source_context(lang=lang),
            )
            for row in rows:
                vals = {name: row[name] for name in translated if row.get(name)}
                if not vals:
                    continue
                try:
                    with self.env.cr.savepoint():
                        Model.browse(mapped[row['id']]).with_context(lang=lang).write(vals)
                except Exception as error:  # noqa: BLE001
                    self.log('warning', Model._name, f"Translation {lang} not copied: {error}", row['id'])

    def relink_batch(self, line, after_id, since):
        model = line.model
        Model = self._model(model)
        plain, per_company, late = self._split(line)
        fields = [name for name in plain if self._needs_relink(Model._fields[name])] + late
        company_fields = [name for name in per_company if self._needs_relink(Model._fields[name])]
        if not fields and not company_fields:
            return None
        domain = line._get_domain() + [('id', '>', after_id)]
        if since:
            domain.append(('write_date', '>=', since))
        rows = self._read(Model, domain, fields or ['id'], self.source.batch_size)
        if not rows:
            return None
        source_ids = [row['id'] for row in rows]
        self._prefetch(Model, rows, fields)
        company_rows = self._read_per_company(Model, source_ids, company_fields)
        for by_id in company_rows.values():
            self._prefetch(Model, list(by_id.values()), company_fields)
        targets = self.resolve(model, source_ids)
        prefetch = tuple(targets.values())
        for row in rows:
            target_id = targets.get(row['id'])
            if not target_id:
                continue
            record = Model.browse(target_id).with_prefetch(prefetch)
            vals, _deferred, _blocking = self._transform(Model, row, fields, relinking=True)
            vals = self._changes(record, vals)
            if vals and self._write(record, vals, row['id']):
                self.stats['relinked'] += 1
        self._write_per_company(Model, targets, company_rows, company_fields, relinking=True)
        return rows[-1]['id']

    def _changes(self, record, vals):
        return {name: value for name, value in vals.items() if not self._same(record, name, value)}

    def _same(self, record, name, value):
        field = record._fields[name]
        current = record[name]
        if field.type == 'many2one':
            return current.id == (value or False)
        if field.type == 'many2many':
            return set(current.ids) == set(value[0][2])
        if field.type == 'reference':
            return (f'{current._name},{current.id}' if current else False) == (value or False)
        if field.type == 'date':
            return fields.Date.to_string(current) == (value or False)
        if field.type == 'datetime':
            return fields.Datetime.to_string(current) == (value or False)
        if field.type == 'binary' and isinstance(current, bytes):
            current = current.decode()
        if field.type == 'html':
            return str(current or '') == str(value or '')
        return (current or False) == (value or False)
