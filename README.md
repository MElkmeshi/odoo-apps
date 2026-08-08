# Odoo Apps

Odoo modules published to the [Odoo Apps Store](https://apps.odoo.com).

One folder per app at the root of the repository, as the store requires. The
branch name is the Odoo series the modules target - `19.0`.

| Module | What it does |
|---|---|
| [`partner_phone_eg`](partner_phone_eg) | Stores Egyptian mobile numbers in one canonical form (`01XXXXXXXXX`), keeps them unique across contacts, and finds a contact by number typed in any format. |
| [`partner_phone_display_name`](partner_phone_display_name) | Shows a contact's phone next to their name, so similarly named contacts are told apart at a glance. |
| [`ai_custom_endpoint`](ai_custom_endpoint) | Points Odoo's AI features at any OpenAI-compatible gateway instead of the hardcoded OpenAI and Google endpoints. |

## Installing

Copy the module folder into your Odoo addons path, update the app list, and
install it from **Apps**. No other steps.

## Versions

Each series lives on its own branch, named after it (`19.0`, `18.0`, ...), with
the module keeping the same technical name across versions.

## License

LGPL-3. See [LICENSE](LICENSE).

## Support

elkmeshi2002@gmail.com
