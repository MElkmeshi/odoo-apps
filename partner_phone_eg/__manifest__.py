{
    'name': 'Partner Phone (Egypt)',
    'author': 'Mohamed Elkmeshi',
    'support': 'elkmeshi2002@gmail.com',
    'version': '19.0.1.0.0',
    'summary': 'Normalise Egyptian mobile numbers, keep them unique, and search contacts by number',
    'description': """
Partner Phone (Egypt)
=====================

Egyptian mobile numbers are stored in one canonical form, ``01XXXXXXXXX``, so
that ``+20 100 123 4567``, ``00201001234567`` and ``0100-123-4567`` are
recognised as the same number.

On top of that single form:

* **Uniqueness** — a second contact cannot be created with a number an active
  contact already holds. Enforced by a partial unique index, so concurrent
  saves cannot both slip through.
* **Search** — typing a number in any format finds the contact, anywhere a
  contact is selected.

Contacts without an Egyptian mobile (landlines, foreign numbers) are left
alone and are not covered by the uniqueness rule.
""",
    'category': 'Contacts',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['base'],
    'installable': True,
    'application': False,
}
