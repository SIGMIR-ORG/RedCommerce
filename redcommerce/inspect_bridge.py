"""Optional Inspect model transport; execution and scoring stay in RedCommerce."""
from __future__ import annotations
import asyncio
import copy
import math

from inspect_ai.model import ChatMessageSystem, ChatMessageUser, GenerateConfig
from inspect_ai.tool import ToolInfo, ToolParams

from .clients import ClientError, parse_envelope, usage_cost


def validate_inspect_config(value):
    if not isinstance(value, dict) or set(value) != {'attacker', 'business'}:
        raise ValueError('Inspect config must contain only attacker and business role settings')
    for name, role in value.items():
        allowed = {'model', 'reserve_usd', 'prices_per_million', 'allowed_returned_models', 'generation'}
        if not isinstance(role, dict) or set(role)-allowed:
            raise ValueError(f'{name}: unsupported setting; never store credentials in this file')
        if not isinstance(role.get('model'), str) or '/' not in role['model']:
            raise ValueError(f'{name}: use a provider/model Inspect identifier')
        reserve = role.get('reserve_usd')
        if type(reserve) not in (int, float) or not math.isfinite(reserve) or reserve <= 0:
            raise ValueError(f'{name}: a positive finite per-request reservation is required')
        prices = role.get('prices_per_million', {})
        for key in ('input', 'output', 'cache_read', 'cache_write'):
            rate = prices.get(key)
            if type(rate) not in (int, float) or not math.isfinite(rate) or rate < 0:
                raise ValueError(f'{name}: supply current nonnegative {key} pricing')
        returned = role.get('allowed_returned_models')
        if not isinstance(returned, list) or not returned or any(not isinstance(m, str) or not m for m in returned):
            raise ValueError(f'{name}: declare allowed_returned_models explicitly')
        generation = role.get('generation', {})
        if not isinstance(generation, dict) or set(generation)-{'temperature', 'top_p', 'top_k', 'seed', 'max_tokens', 'timeout'}:
            raise ValueError(f'{name}: generation cannot override prompts, tools, retries or model identity')
        GenerateConfig(**generation)
    return copy.deepcopy(value)


class InspectClient:
    """Sync scheduler callback -> native async Inspect Model.generate()."""
    def __init__(self, model, config, loop):
        self.native_model, self.config, self.loop = model, config, loop
        self.model = str(model)
        self.reserve_usd = config['reserve_usd']
        self.is_simulated = model.api.__class__.__module__ == 'inspect_ai.model._providers.mockllm'
        if self.model != config['model']:
            raise ValueError('Resolved Inspect model differs from its priced role configuration')
        if model.config.system_message:
            raise ValueError('Extra Inspect system messages are not allowed; keep the declared role prompts')

    async def generate(self, request):
        messages = [ChatMessageSystem(content=m['content']) if m['role'] == 'system'
                    else ChatMessageUser(content=m['content']) for m in request['messages']]
        if any(m['role'] not in ('system', 'user') for m in request['messages']):
            raise ValueError('Unexpected role in the frozen request renderer')
        messages[0].content += ('\nReturn zero or one available action using the supplied schema. '
            'Empty actions records abstention. Do not invent tools or arguments.')
        tool = ToolInfo(name='emit_actions',
            description='Submit the role decision, including an empty actions array for abstention.',
            parameters=ToolParams.model_validate(request['response_contract']))
        settings = GenerateConfig(**self.config.get('generation', {}), max_retries=0, num_choices=1)
        output = await self.native_model.generate(messages, tools=[tool], tool_choice='auto',
                                                  config=settings, cache=False)
        raw = output.model_dump(mode='json', exclude_none=True)
        if output.usage is None:
            raise ClientError('Inspect provider usage unavailable', response=raw)
        # Inspect 0.3.281 reports full-rate input separately from cache read/write.
        u = output.usage
        usage, cost = usage_cost({'usage': {'input_tokens': u.input_tokens,
            'output_tokens': u.output_tokens, 'cache_read_input_tokens': u.input_tokens_cache_read or 0,
            'cache_creation_input_tokens': u.input_tokens_cache_write or 0}},
            {'backend': 'anthropic', 'prices_per_million': self.config['prices_per_million']})
        failure = None
        if output.model not in self.config['allowed_returned_models']:
            failure = 'returned_model_mismatch'
        if len(output.choices) != 1:
            envelope, status = None, 'model_format_error'
            truncated = False
        else:
            choice = output.choices[0]
            calls = choice.message.tool_calls or []
            if calls:
                envelope = calls[0].arguments if len(calls) == 1 and calls[0].function == 'emit_actions' and not calls[0].parse_error else None
            else:
                envelope = choice.message.text
            truncated = choice.stop_reason in ('max_tokens', 'model_length')
            if choice.stop_reason == 'content_filter':
                failure = 'provider_access_blocked'
            # Explicit provider refusal is not inferred from free-text content.
            details = choice.stop_details
            if details and details.type == 'refusal':
                failure = 'provider_access_blocked'
            _, status = parse_envelope(envelope, request)
        actions, parsed = parse_envelope(envelope, request)
        if truncated:
            actions, status = [], 'model_format_error'
        elif parsed == 'model_format_error':
            status = parsed
        return {'actions': actions, 'parse_status': status, 'returned_model': output.model,
                'usage': usage, 'cost_usd': cost, 'raw': raw, 'failure': failure,
                'truncated': truncated, 'cost_basis': 'Inspect reported usage times configured prices',
                'provider_invoice_usd': None}

    def __call__(self, request):
        return asyncio.run_coroutine_threadsafe(self.generate(request), self.loop).result()
