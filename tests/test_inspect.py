"""Optional adapter tests; the base package still works without Inspect installed."""
import asyncio
import copy
import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace
import unittest

AVAILABLE = importlib.util.find_spec('inspect_ai') is not None
if AVAILABLE:
    from inspect_ai.model import GenerateConfig, ModelOutput, ModelUsage
    from inspect_ai.scorer import Score, SampleScore
    from inspect_ai.tool import ToolCall
    from redcommerce.clients import ClientError
    from redcommerce.engine import DATA
    from redcommerce.inspect_bridge import InspectClient, validate_inspect_config
    from redcommerce.inspect_tasks import redcommerce, redcommerce_rates


@unittest.skipUnless(AVAILABLE, 'Install the optional inspect extra to run native integration tests')
class InspectConfigTests(unittest.TestCase):
    def role(self):
        return {'model': 'mockllm/fixture', 'reserve_usd': .05,
                'allowed_returned_models': ['fixture'],
                'prices_per_million': dict(input=1, output=2, cache_read=.1, cache_write=1.25)}

    def test_model_execution_requires_explicit_opt_in(self):
        with self.assertRaisesRegex(ValueError, 'execute=True'):
            redcommerce(mode='model', config='not-read.json')

    def test_nonfinite_budget_is_rejected(self):
        with self.assertRaises(ValueError):
            redcommerce(mode='model', config='not-read.json', execute=True, budget_usd=math.nan)

    def test_frozen_output_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'outside frozen'):
            redcommerce(out=str(DATA/'inspect-test'))

    def test_credentials_and_prompt_override_are_rejected(self):
        config = dict(attacker=self.role(), business=self.role())
        for setting in ({'api_key': 'synthetic'}, {'generation': {'system_message': 'replace'}}):
            value = copy.deepcopy(config)
            value['attacker'].update(setting)
            with self.assertRaises(ValueError):
                validate_inspect_config(value)

    def test_unknown_price_is_rejected(self):
        config = dict(attacker=self.role(), business=self.role())
        config['attacker']['prices_per_million']['output'] = None
        with self.assertRaises(ValueError):
            validate_inspect_config(config)

    def test_metrics_preserve_denominator_and_offline_scope(self):
        def row(success, eligible, status='complete', simulated=False):
            record = {'score': {'attack_denominator_eligible': eligible, 'attack_success': success},
                      'model_participation': not simulated, 'terminal': 'protocol_failure', 'status': status}
            return SampleScore(score=Score(value={'attack_success': success}, metadata={'record': record}))
        result = redcommerce_rates()([row(True, True), row(False, True), row(None, False, 'pending'),
                                     row(None, False, 'provider_excluded')])
        self.assertEqual(result['asr'], .5)
        self.assertEqual(result['pending'], 1)
        self.assertEqual(result['provider_excluded'], 1)
        self.assertIsNone(redcommerce_rates()([row(True, True, simulated=True)])['asr'])


@unittest.skipUnless(AVAILABLE, 'Install the optional inspect extra')
class InspectTransportTests(unittest.IsolatedAsyncioTestCase):
    def request(self):
        return {'messages': [{'role': 'system', 'content': 'Declared role.'}, {'role': 'user', 'content': '{}'}],
                'response_contract': {'type': 'object', 'required': ['actions'], 'additionalProperties': False,
                    'properties': {'actions': {'type': 'array', 'minItems': 0, 'maxItems': 1,
                        'items': {'type': 'object', 'required': ['tool', 'arguments'], 'additionalProperties': False,
                            'properties': {'tool': {'const': 'commit'}, 'arguments': {'type': 'object'}}}}}}}

    def client(self, output):
        class Native:
            api = SimpleNamespace()
            config = GenerateConfig()
            def __str__(self): return 'mockllm/fixture'
            async def generate(self, messages, **kwargs):
                self.messages, self.kwargs = messages, kwargs
                return output
        model = Native()
        config = InspectConfigTests().role()
        return InspectClient(model, config, asyncio.get_running_loop())

    def output(self, envelope=None):
        result = ModelOutput.for_tool_call('fixture', 'emit_actions', envelope or {'actions': []})
        result.usage = ModelUsage(input_tokens=800, output_tokens=100,
                                 input_tokens_cache_read=200, input_tokens_cache_write=100, total_tokens=1200)
        return result

    async def test_usage_cache_accounting_and_native_tool(self):
        envelope = {'actions': [{'tool': 'commit', 'arguments': {}}]}
        client = self.client(self.output(envelope))
        reply = await client.generate(self.request())
        self.assertEqual(reply['actions'], envelope['actions'])
        self.assertEqual(reply['usage']['total_tokens'], 1200)
        self.assertAlmostEqual(reply['cost_usd'], .001145)
        self.assertEqual([t.name for t in client.native_model.kwargs['tools']], ['emit_actions'])

    async def test_no_injected_token_cap_or_retries_or_response_cache(self):
        client = self.client(self.output())
        original = self.request()
        await client.generate(original)
        self.assertEqual(original, self.request())
        cfg = client.native_model.kwargs['config']
        self.assertNotIn('max_tokens', cfg.model_fields_set)
        self.assertEqual(cfg.max_retries, 0)
        self.assertIs(client.native_model.kwargs['cache'], False)

    async def test_explicit_abstention_is_not_format_error(self):
        reply = await self.client(self.output()).generate(self.request())
        self.assertEqual(reply['parse_status'], 'model_abstention')

    async def test_free_text_refusal_does_not_invent_provider_filter(self):
        output = self.output()
        output.choices[0].message.tool_calls = []
        output.choices[0].message.content = 'I cannot do that.'
        reply = await self.client(output).generate(self.request())
        self.assertIsNone(reply['failure'])
        self.assertEqual(reply['parse_status'], 'model_format_error')

    async def test_provider_filter_remains_separate(self):
        output = self.output()
        output.choices[0].stop_reason = 'content_filter'
        reply = await self.client(output).generate(self.request())
        self.assertEqual(reply['failure'], 'provider_access_blocked')

    async def test_truncation_is_not_executed(self):
        output = self.output({'actions': [{'tool': 'commit', 'arguments': {}}]})
        output.choices[0].stop_reason = 'max_tokens'
        reply = await self.client(output).generate(self.request())
        self.assertEqual(reply['actions'], [])
        self.assertEqual(reply['parse_status'], 'model_format_error')

    async def test_multiple_or_wrong_native_tools_are_rejected(self):
        for calls in ([ToolCall(id='x', function='wrong', arguments={'actions': []})],
                      [ToolCall(id='x', function='emit_actions', arguments={'actions': []}),
                       ToolCall(id='y', function='emit_actions', arguments={'actions': []})]):
            output = self.output()
            output.choices[0].message.tool_calls = calls
            reply = await self.client(output).generate(self.request())
            self.assertEqual(reply['parse_status'], 'model_format_error')

    async def test_unknown_usage_retains_response(self):
        output = self.output()
        output.usage = None
        with self.assertRaises(ClientError) as error:
            await self.client(output).generate(self.request())
        self.assertIsNotNone(error.exception.response)

    async def test_model_identity_mismatch_is_excluded(self):
        output = self.output()
        output.model = 'other-model'
        reply = await self.client(output).generate(self.request())
        self.assertEqual(reply['failure'], 'returned_model_mismatch')


if __name__ == '__main__': unittest.main()
