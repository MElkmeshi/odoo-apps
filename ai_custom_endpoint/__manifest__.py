{
    'name': 'AI Custom Endpoint',
    'author': 'Mohamed Elkmeshi',
    'support': 'elkmeshi2002@gmail.com',
    'version': '19.0.1.0.0',
    'summary': 'Point the AI module at an OpenAI-compatible gateway',
    'description': """
AI Custom Endpoint
==================

Odoo hardcodes the LLM endpoints (``utils/llm_api_service.py``), so the AI
module can only ever talk to OpenAI or Google. This module reads them from
system parameters instead, which is enough to run the whole AI stack against
any OpenAI-protocol gateway — a self-hosted proxy, LiteLLM, vLLM, OpenRouter,
Azure OpenAI, or a private mirror.

Configured under **Settings > AI > Providers**, or through the underlying
system parameters (all optional, nothing changes until one is set):

``ai.openai_base_url``
    Replaces ``https://api.openai.com/v1``.

``ai.google_base_url``
    Replaces Gemini's OpenAI-compatible URL. Not shown in Settings — a gateway
    normally fronts every model through the endpoint above — so it is set from
    System Parameters when Gemini is proxied separately.

``ai.custom_llm_models``
    Comma-separated ``code:Label`` pairs adding models to the agent's LLM
    dropdown, e.g. ``claude-opus-5:Claude Opus 5, llama-3.3-70b:Llama 3.3``.
    They are routed as OpenAI-protocol requests to ``ai.openai_base_url``.

The API key is Odoo's own ``ai.openai_key`` parameter — set it to the
gateway's key.

Note that Odoo drives chat through the OpenAI **Responses** API
(``POST /responses``), not ``/chat/completions``, and RAG embeddings through
``POST /embeddings``. A gateway must serve those exact routes.
""",
    'category': 'Productivity/Discuss',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['ai'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
}
