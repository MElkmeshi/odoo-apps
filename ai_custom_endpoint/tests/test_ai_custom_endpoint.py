from unittest.mock import patch

import requests

from odoo.addons.ai.utils.llm_api_service import LLMApiService
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


class FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, payload=None, status=200, text=''):
        self._payload = payload
        self.status_code = status
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("No JSON object could be decoded")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.exceptions.HTTPError(f"{self.status_code} Client Error")
            error.response = self
            raise error


@tagged('post_install', '-at_install')
class TestAiCustomEndpoint(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ICP = cls.env['ir.config_parameter'].sudo()
        cls.Agent = cls.env['ai.agent']
        cls.stock_models = {code for code, _label in cls.Agent._get_llm_model_selection()}

    def _set_models(self, raw):
        self.ICP.set_param('ai.custom_llm_models', raw)

    # --- parsing -----------------------------------------------------------

    def test_parse_code_and_label(self):
        self._set_models('claude-opus-5:Claude Opus 5')
        self.assertEqual(self.Agent._get_custom_llm_models(), [('claude-opus-5', 'Claude Opus 5')])

    def test_parse_bare_code_is_its_own_label(self):
        self._set_models('claude-opus-5')
        self.assertEqual(self.Agent._get_custom_llm_models(), [('claude-opus-5', 'claude-opus-5')])

    def test_parse_tolerates_whitespace_and_empty_entries(self):
        self._set_models('  a:A , , b ,, c: C  ,')
        self.assertEqual(
            self.Agent._get_custom_llm_models(),
            [('a', 'A'), ('b', 'b'), ('c', 'C')],
        )

    def test_parse_unset_parameter(self):
        self.ICP.set_param('ai.custom_llm_models', '')
        self.assertEqual(self.Agent._get_custom_llm_models(), [])

    # --- selection ---------------------------------------------------------

    def test_selection_appends_custom_models(self):
        self._set_models('claude-opus-5:Claude Opus 5')
        selection = dict(self.Agent._selection_llm_model())
        self.assertEqual(selection.get('claude-opus-5'), 'Claude Opus 5')
        self.assertTrue(self.stock_models <= set(selection), "stock models must survive")

    def test_selection_does_not_duplicate_a_stock_model(self):
        stock_code = sorted(self.stock_models)[0]
        self._set_models(f'{stock_code}:Renamed')
        codes = [code for code, _label in self.Agent._selection_llm_model()]
        self.assertEqual(codes.count(stock_code), 1)

    def test_selection_is_visible_to_the_field(self):
        self._set_models('claude-opus-5:Claude Opus 5')
        selection = dict(self.Agent.fields_get(['llm_model'])['llm_model']['selection'])
        self.assertIn('claude-opus-5', selection)

    # --- provider routing --------------------------------------------------

    def test_custom_model_routes_to_openai(self):
        self._set_models('claude-opus-5:Claude Opus 5')
        agent = self.Agent.new({'llm_model': 'claude-opus-5'})
        self.assertEqual(agent._get_provider(), 'openai')

    def test_stock_model_keeps_its_own_provider(self):
        self._set_models('claude-opus-5:Claude Opus 5')
        agent = self.Agent.new({'llm_model': 'gemini-2.5-flash'})
        self.assertEqual(agent._get_provider(), 'google')

    def test_unknown_model_raises_without_a_custom_endpoint(self):
        self._set_models('')
        self.ICP.set_param('ai.openai_base_url', '')
        agent = self.Agent.new({'llm_model': 'never-configured'})
        with self.assertRaises(UserError):
            agent._get_provider()

    def test_dropped_model_stays_editable(self):
        """A model removed from the list must not lock the agent.

        Stock write() resolves the provider of the value already stored before
        writing the new one, so raising on an unknown model would leave no way
        to move an agent off a model the endpoint stopped offering.
        """
        agent = self.Agent.search([], limit=1)
        if not agent:
            self.skipTest("no ai.agent in this database")
        self.ICP.set_param('ai.openai_base_url', 'https://gateway.example/v1')
        self._set_models('retired-model')
        agent.llm_model = 'retired-model'

        self._set_models('claude-opus-5')
        agent.llm_model = 'claude-opus-5'  # must not raise
        self.assertEqual(agent.llm_model, 'claude-opus-5')

    # --- base URL patch ----------------------------------------------------

    def test_base_url_defaults_to_openai(self):
        self.ICP.set_param('ai.openai_base_url', '')
        self.assertEqual(LLMApiService(self.env, 'openai').base_url, 'https://api.openai.com/v1')

    def test_base_url_override_strips_trailing_slash(self):
        self.ICP.set_param('ai.openai_base_url', ' https://gateway.example/v1/ ')
        self.assertEqual(LLMApiService(self.env, 'openai').base_url, 'https://gateway.example/v1')

    def test_google_keeps_its_endpoint_when_only_openai_is_redirected(self):
        self.ICP.set_param('ai.openai_base_url', 'https://gateway.example/v1')
        self.ICP.set_param('ai.google_base_url', '')
        self.assertIn('googleapis.com', LLMApiService(self.env, 'google').base_url)

    def test_google_base_url_is_still_redirectable(self):
        """Not in Settings anymore, but the parameter still works."""
        self.ICP.set_param('ai.google_base_url', 'https://gemini-proxy.example/v1')
        self.assertEqual(
            LLMApiService(self.env, 'google').base_url, 'https://gemini-proxy.example/v1')

    # --- fetch button ------------------------------------------------------

    def _settings(self, base_url='https://gateway.example/v1'):
        self.ICP.set_param('ai.openai_key', 'test-key')
        settings = self.env['res.config.settings'].create({})
        settings.ai_openai_base_url = base_url
        return settings

    def _patched_get(self, response):
        return patch.object(requests, 'get', return_value=response)

    def test_fetch_stores_models_and_filters_non_chat(self):
        payload = {'data': [
            {'id': 'claude-opus-5'},
            {'id': 'gpt-image-2'},
            {'id': 'text-embedding-3-small'},
            {'id': 'gpt-5.5'},
        ]}
        with self._patched_get(FakeResponse(payload)):
            action = self._settings().action_fetch_ai_models()

        self.assertEqual(self.ICP.get_param('ai.custom_llm_models'), 'claude-opus-5, gpt-5.5')
        message = action['params']['message']
        self.assertIn('gpt-image-2', message, "filtered models must be reported, not dropped silently")
        self.assertIn('text-embedding-3-small', message)

    def test_fetch_does_not_save_unrelated_settings(self):
        """The button must not behave like Save: execute() would install modules."""
        payload = {'data': [{'id': 'claude-opus-5'}]}
        with self._patched_get(FakeResponse(payload)), \
             patch.object(type(self.env['res.config.settings']), 'execute') as execute:
            self._settings().action_fetch_ai_models()
        execute.assert_not_called()

    def test_fetch_warns_about_agents_left_on_a_missing_model(self):
        agent = self.Agent.search([], limit=1)
        if not agent:
            self.skipTest("no ai.agent to strand")
        self.ICP.set_param('ai.openai_base_url', 'https://gateway.example/v1')
        self._set_models('only-on-the-old-gateway')
        agent.llm_model = 'only-on-the-old-gateway'

        payload = {'data': [{'id': 'claude-opus-5'}]}
        with self._patched_get(FakeResponse(payload)):
            action = self._settings().action_fetch_ai_models()

        self.assertEqual(action['params']['type'], 'warning')
        self.assertIn(agent.name, action['params']['message'])

    def test_fetch_surfaces_the_endpoint_error_body(self):
        body = {'error': {'message': 'invalid api key for this gateway'}}
        with self._patched_get(FakeResponse(body, status=401)):
            with self.assertRaises(UserError) as caught:
                self._settings().action_fetch_ai_models()
        self.assertIn('invalid api key for this gateway', str(caught.exception))

    def test_fetch_reports_non_json_response(self):
        with self._patched_get(FakeResponse(None, text='<html>gateway</html>')):
            with self.assertRaises(UserError) as caught:
                self._settings().action_fetch_ai_models()
        self.assertIn('did not return JSON', str(caught.exception))

    def test_fetch_requires_a_base_url(self):
        with self.assertRaises(UserError):
            self._settings(base_url='').action_fetch_ai_models()

    def test_fetch_rejects_a_list_of_only_non_chat_models(self):
        with self._patched_get(FakeResponse({'data': [{'id': 'gpt-image-2'}]})):
            with self.assertRaises(UserError) as caught:
                self._settings().action_fetch_ai_models()
        self.assertIn('gpt-image-2', str(caught.exception))
