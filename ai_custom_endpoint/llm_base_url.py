"""Make the LLM endpoint configurable.

``LLMApiService.__init__`` hardcodes the base URL per provider, and every call
site builds the service directly (``LLMApiService(env, provider=...)`` in
ai_agent, ai_embedding, ai_fields, ir_actions_server, voip_ai, esg_csrd_ai...),
so there is no seam to inherit — patching the constructor is the only lever.

The URL is read from the environment on every instantiation rather than at
import time, so it stays per-database on a multi-database server.
"""

from odoo.addons.ai.utils import llm_api_service

# Provider name -> system parameter holding its base URL. Only the OpenAI one
# is exposed in Settings, since a gateway fronts everything through that slot;
# the Google entry stays available for anyone proxying Gemini separately, and
# is set through System Parameters.
BASE_URL_PARAMS = {
    'openai': 'ai.openai_base_url',
    'google': 'ai.google_base_url',
}


def _patch_llm_api_service():
    original_init = llm_api_service.LLMApiService.__init__

    # Odoo re-imports addons on registry reload; without this the wrapper would
    # wrap itself, growing a new layer per reload.
    if getattr(original_init, '_ai_custom_endpoint', False):
        return

    def __init__(self, env, provider='openai'):
        # Runs first: it validates the provider and sets the stock URL, which
        # stays in place when no override is configured.
        original_init(self, env, provider)
        param = BASE_URL_PARAMS.get(provider)
        if not param:
            return
        base_url = env['ir.config_parameter'].sudo().get_param(param)
        if base_url:
            # Endpoints are joined as f"{base_url}/{endpoint.strip('/')}", so a
            # trailing slash would produce a double slash.
            self.base_url = base_url.strip().rstrip('/')

    __init__._ai_custom_endpoint = True
    llm_api_service.LLMApiService.__init__ = __init__


_patch_llm_api_service()
