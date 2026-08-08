from odoo import api, fields, models
from odoo.exceptions import UserError

CUSTOM_MODELS_PARAM = 'ai.custom_llm_models'
BASE_URL_PARAM = 'ai.openai_base_url'


class AiAgent(models.Model):
    _inherit = 'ai.agent'

    # The stock field passes a *callable* as `selection`, and Odoo calls a
    # callable directly instead of dispatching it through the model
    # (odoo/orm/fields_selection.py:204), so overriding _get_llm_model_selection
    # would have no effect. `selection_add` is not an option either: it asserts
    # the inherited selection is a list. Redefining it with a method *name*
    # restores normal inheritance.
    llm_model = fields.Selection(selection='_selection_llm_model')

    @api.model
    def _selection_llm_model(self):
        selection = self._get_llm_model_selection()
        known = {code for code, _label in selection}
        return selection + [
            (code, label)
            for code, label in self._get_custom_llm_models()
            if code not in known
        ]

    @api.model
    def _get_custom_llm_models(self):
        """Parse ``ai.custom_llm_models``: ``code:Label, code:Label``.

        The label is optional; the code doubles as its own label. Entries are
        not validated against the gateway — a typo surfaces as an API error on
        first use, which is a clearer signal than a silently missing option.
        """
        raw = self.env['ir.config_parameter'].sudo().get_param(CUSTOM_MODELS_PARAM) or ''
        models_ = []
        for entry in raw.split(','):
            code, _sep, label = entry.partition(':')
            code, label = code.strip(), label.strip()
            if code:
                models_.append((code, label or code))
        return models_

    def _get_provider(self):
        """Route custom models over the OpenAI protocol.

        The stock implementation resolves the provider by looking the model up
        in the hardcoded PROVIDERS table and raises for anything absent from
        it. Custom models are absent by definition, and 'openai' is the right
        answer for them: it is the protocol the gateway speaks, and it is the
        provider whose base URL and API key the gateway replaces.
        """
        self.ensure_one()
        if self.llm_model in dict(self._get_custom_llm_models()):
            return 'openai'
        try:
            return super()._get_provider()
        except UserError:
            # The model list can shrink — a different endpoint, or one that
            # retired a model — which stock Odoo never has to handle. Its
            # write() resolves the *old* value before writing the new one
            # (ai/models/ai_agent.py:337), so raising here would make an
            # agent on a dropped model impossible to correct from the UI.
            # While a custom endpoint is configured, every model is reached
            # over the OpenAI protocol anyway, so this stays truthful: the
            # request goes out and the endpoint reports an unknown model.
            if self.env['ir.config_parameter'].sudo().get_param(BASE_URL_PARAM):
                return 'openai'
            raise
