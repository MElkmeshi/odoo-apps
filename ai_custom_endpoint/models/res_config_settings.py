import json

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError

# The gateway lists everything it can route, including models that are not
# chat completions. Odoo's agent dropdown only makes sense for chat models.
# Matched as substrings, so this is a heuristic: what it drops is always
# reported back to the user rather than silently discarded.
NON_CHAT_HINTS = ('image', 'embedding', 'whisper', 'tts', 'audio', 'moderation')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # config_parameter fields read and write ir.config_parameter directly, so
    # these are the same settings the rest of the module reads - editing them
    # here and editing System Parameters are interchangeable.
    ai_custom_endpoint_enabled = fields.Boolean(
        string="Use a custom AI endpoint",
        compute='_compute_ai_custom_endpoint_enabled',
        readonly=False,
        groups='base.group_system',
    )
    ai_openai_base_url = fields.Char(
        string="OpenAI-compatible base URL",
        config_parameter='ai.openai_base_url',
        readonly=False,
        groups='base.group_system',
        help="Replaces https://api.openai.com/v1. The gateway must serve the "
             "OpenAI Responses API (POST /responses) for agents, and POST "
             "/embeddings for RAG sources. The API key above is sent to this "
             "host, so a wrong address hands it to whoever answers.",
    )
    ai_custom_llm_models = fields.Char(
        string="Extra models",
        config_parameter='ai.custom_llm_models',
        readonly=False,
        groups='base.group_system',
        help="Comma-separated code:Label pairs added to the agent's model list, "
             "e.g. claude-opus-5:Claude Opus 5, llama-3.3-70b:Llama 3.3. They "
             "are sent to the OpenAI-compatible base URL above.",
    )

    def _compute_ai_custom_endpoint_enabled(self):
        for record in self:
            record.ai_custom_endpoint_enabled = bool(record.ai_openai_base_url)

    def action_fetch_ai_models(self):
        """Fill the model list from the gateway's own ``GET /models``.

        Deliberately does *not* call ``execute()``. That would save every
        unsaved setting on the whole Settings page, and it installs or
        uninstalls the modules behind ``module_`` checkboxes - which the ORM
        requires to happen last in the transaction (res_config.py:362). This
        method makes a network call afterwards, and a failing call would roll
        an install back mid-flight. Only the parameters this feature owns are
        written, from the values currently in the form.
        """
        self.ensure_one()
        base_url = (self.ai_openai_base_url or '').strip().rstrip('/')
        if not base_url:
            raise UserError(_("Set the OpenAI-compatible base URL first."))

        api_key = self.openai_key or self.env['ir.config_parameter'].sudo().get_param('ai.openai_key')
        if not api_key:
            raise UserError(_("Set the API key first."))

        payload = self._fetch_models_payload(base_url, api_key)
        entries = [e for e in payload.get('data') or [] if isinstance(e, dict) and e.get('id')]
        model_ids = sorted(
            e['id'] for e in entries
            if not any(hint in e['id'] for hint in NON_CHAT_HINTS)
        )
        skipped = sorted({e['id'] for e in entries} - set(model_ids))
        if not model_ids:
            raise UserError(_(
                "%(url)s returned no chat models%(detail)s.",
                url=base_url,
                detail=_(" (skipped as non-chat: %s)", ", ".join(skipped)) if skipped else "",
            ))

        ICP = self.env['ir.config_parameter'].sudo()
        # Only this feature's own parameters, so the button cannot commit
        # unrelated settings the user has open elsewhere on the page.
        ICP.set_param('ai.openai_base_url', base_url)
        # Stored bare: the parser treats a code with no label as its own label,
        # and inventing prettier names would only hide the real model id.
        ICP.set_param('ai.custom_llm_models', ', '.join(model_ids))

        return self._models_fetched_notification(model_ids, skipped)

    def _fetch_models_payload(self, base_url, api_key):
        """GET {base_url}/models, surfacing the endpoint's own error text.

        raise_for_status alone reports "400 Client Error" and discards the body
        that says why, which is the only part worth reading.
        """
        try:
            response = requests.get(
                f"{base_url}/models",
                headers={'Authorization': f"Bearer {api_key}"},
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.RequestException as error:
            raise UserError(_(
                "Could not read models from %(url)s: %(error)s",
                url=base_url, error=self._http_error_detail(error),
            ))
        except ValueError as error:  # JSON decode
            raise UserError(_(
                "%(url)s did not return JSON: %(error)s", url=base_url, error=error))

        if not isinstance(payload, dict):
            raise UserError(_(
                "%(url)s returned %(type)s, expected an OpenAI model list.",
                url=base_url, type=type(payload).__name__,
            ))
        return payload

    def _http_error_detail(self, error):
        """Pull the message out of an error body, mirroring llm_api_service."""
        response = getattr(error, 'response', None)
        if response is None:
            return repr(error)
        try:
            body = response.json()
        except ValueError:
            return response.text or repr(error)
        if isinstance(body, list) and body:
            body = body[0]
        if isinstance(body, dict):
            message = body.get('error')
            if isinstance(message, dict):
                message = message.get('message')
            if message:
                return message
        return json.dumps(body, indent=2)

    def _models_fetched_notification(self, model_ids, skipped):
        """Report what was stored, what was filtered, and what this broke."""
        messages = [_("Pick one on each AI agent under its LLM Model field.")]
        if skipped:
            messages.append(_(
                "Not added, treated as non-chat models: %s.", ", ".join(skipped)))

        # A different endpoint can drop a model an agent is already using. The
        # value stays in the database but is no longer a valid selection: the
        # field renders empty and the agent raises at request time.
        Agent = self.env['ai.agent'].sudo()
        available = {code for code, _label in Agent._get_llm_model_selection()} | set(model_ids)
        orphaned = Agent.search([('llm_model', 'not in', list(available))])
        notification_type = 'success'
        if orphaned:
            notification_type = 'warning'
            messages.append(_(
                "These agents still point at a model this endpoint does not "
                "offer and will fail until you change them: %s.",
                ", ".join(f"{a.name} ({a.llm_model})" for a in orphaned),
            ))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': notification_type,
                'title': _("%s models available", len(model_ids)),
                'message': " ".join(messages),
                'sticky': bool(orphaned),
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }
