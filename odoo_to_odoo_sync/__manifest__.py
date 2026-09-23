{
    'name': 'Odoo to Odoo Sync',
    'author': 'Mohamed Elkmeshi',
    'support': 'elkmeshi2002@gmail.com',
    'version': '19.0.1.0.0',
    'summary': 'Copy and merge records from another Odoo database, matched by External ID',
    'description': """
Odoo to Odoo Sync
=================

Pulls records from another Odoo database of the same series into this one and
merges them with what is already here.

* Records are matched by External ID, so the standard data both databases share
  (companies, currencies, taxes, units...) is never duplicated, and running the
  sync again updates instead of creating.
* Models are copied in dependency order, lines included, and links that point
  forward are restored in a second pass.
* Runs in the background in resumable chunks, safe for Odoo.sh time limits.
* Every run keeps a log of what was created, updated and why a record failed.
""",
    'category': 'Administration',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/sync_source_views.xml',
        'views/sync_run_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
}
