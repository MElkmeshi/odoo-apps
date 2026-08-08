{
    'name': 'Phone in Contact Name',
    'author': 'Mohamed Elkmeshi',
    'support': 'elkmeshi2002@gmail.com',
    'version': '19.0.1.0.0',
    'summary': "Show a contact's phone number next to their name",
    'description': """
Partner Phone in Display Name
=============================

Appends the phone number to a contact's display name, so people picking a
contact can tell two similarly named records apart by number.

This is ``display_name``, so the number appears wherever a contact is shown
or printed — selectors, but also quotations, invoices and email recipients.
That is intentional; install it only if you want the number everywhere.

Independent of any normalisation module: it shows whatever is stored in the
contact's phone field.
""",
    'category': 'Contacts',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['base'],
    'installable': True,
    'application': False,
}
