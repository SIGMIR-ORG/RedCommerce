# Model adapters

The frozen scheduler receives a callable for the counterparty and a callable for each business role. The public wrapper constructs model requests from each role's own observation. Clients receive **messages, role identity, and response schema**; they receive no private verifier truth, authored labels, or scorer results.

## Native clients

`chat-completions` sends a standard function tool named `emit_actions` to a configured HTTPS Chat Completions endpoint. `anthropic` sends an `emit_actions` tool through Messages. Tool choice is `auto`; an empty action array remains a possible model decision.

Provider-specific settings such as thinking, reasoning effort, and sampling parameters belong in the model config's `parameters`. These cannot override the model, messages, tools, or tool choice. There is **no shared hardcoded output-token cap**. Chat endpoints receive no output limit when `max_output_tokens` is omitted. Anthropic requires this field, so the researcher must specify the desired provider-supported value. Every configured limit is retained in the plan.

Set `allowed_returned_models` explicitly for provider aliases and snapshots. A reply with an unexpected model identifier is saved and stops the run. Native usage is measured from the provider response. Missing prices for any used token category, unknown usage, and charges above a reservation stop the run.

The public interface is versioned separately from historical transport code. Native-tool formatting can affect model behavior; new samples should be reported with their public-interface version and config. Historical saved evidence is replayed through its original observation builders.

Protocol references: [Claude Messages](https://platform.claude.com/docs/en/api/messages/create) and [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion). Native transport is validated with mocked replies in this release; no new paid provider smoke test was performed during packaging.

## Custom client contract

A config with `backend: "plugin"` names a factory as `package.module:function`. The module must be importable in the evaluator's Python environment. The factory receives its role config and returns a callable object with:

```python
model: str
reserve_usd: float
is_simulated: bool  # False for a real model

def __call__(self, request: dict) -> dict:
    return {
        "actions": [{"tool": "DECLARED_TOOL", "arguments": {}}],
        "parse_status": "parsed",
        "returned_model": self.model,
        "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        "cost_usd": 0.001,
        "raw": {},
    }
```

These numbers are illustrative interface values, not provider pricing. A well-formed empty envelope has `actions: []` and `parse_status: "model_abstention"`. A malformed output has `parse_status: "model_format_error"`. An explicit service restriction can return `failure: "provider_access_blocked"` after reporting any billed usage.

A client may raise `redcommerce.clients.NotDispatched` only if it knows that no request left. Other exceptions retain the reservation as an unknown outcome. Usage and finite nonnegative cost must be returned for every dispatched request that completes. Plugins should not log credentials or automatically retry a model request.

## Costs and recovery

Each run has one persistent ledger shared by both sides and every chain role. It reserves before dispatch and settles exactly once. A completed response is saved before settlement. Unknown usage or transport outcomes retain the reservation and stop further calls.

Completed jobs are reused only under an identical plan. An episode saved before a crash can be re-scored without another model call. A partially dispatched job cannot be silently restarted; use the saved request evidence to reconcile it. This release performs one worker per run directory; its lock prevents concurrent writers.

Keep a single run's configured pricing fixed. A larger `--budget-usd` can extend the cumulative budget for the same output directory without forgetting prior commitments. Published cost totals should identify the price table and distinguish estimates from invoiced amounts.
