# Native Inspect AI integration

Tested with **Inspect AI 0.3.281**, Python 3.12, Windows. The optional dependency is pinned in the `inspect` extra. The base RedCommerce CLI still has no third-party runtime dependencies.

This is a runnable Inspect task and model-transport adapter, not just JSONL conversion:

- Inspect manages native model calls, named `attacker` / `business` roles, usage events and `.eval` logs.
- The original RedCommerce scheduler applies allowlisted attacker writes, builds role observations, executes business actions and preserves sequential role chains.
- The custom scorer independently re-scores the saved episode with the original deterministic scorer. No text-pattern detector or LLM judge replaces it.
- Attack-side abstention/format outcomes retain their original denominator overlay; business-format failures stay pending. Explicit provider filters stay separate. Offline/mock runs have no reported model ASR.
- These are constrained commercial-action agents: no shell, arbitrary file-read or code-execution tools are exposed to a model. This is not an integration for unrestricted terminal agents.

## Install

From a repository checkout:

```sh
python -m pip install -e ".[inspect]"
python -B scripts/install_ci_data.py
```

The second command is unnecessary when the frozen embedded dataset already exists. For an external installation, `REDCOMMERCE_DATA_DIR` is also supported. Data is downloaded anonymously from the pinned Hugging Face release; no HF token is needed.

## Zero-model-call example

```sh
inspect eval redcommerce/inspect_tasks.py@redcommerce -T case=RC-T21-GTIN-SCOPE-002 -T out=runs/inspect-listing --log-dir logs/inspect-listing --max-samples 1
```

The default `mode=offline` uses the deterministic reference policy and a frozen submission. To keep the original lawful proposal, add `-T submission=unchanged` and choose a different output directory. Inspect's default mock model is not called in this mode. Inspect records an original-scorer result, not a model-performance measurement.

Open the generated logs with:

```sh
inspect view --log-dir logs/inspect-listing
```

## Native model evaluation

Copy `examples/inspect-models.template.json` to an untracked location. Fill both Inspect provider/model identifiers, allowed actual returned model IDs, current input/output/cache prices and conservative per-request USD reservations. Null template prices/reservations are deliberately not runnable. Configure provider credentials using Inspect's documented environment variables; do not put keys in JSON or CLI arguments.

Install the SDK required by the selected Inspect provider as well (for example, `python -m pip install anthropic` for Anthropic, or `python -m pip install openai` for OpenAI/OpenAI-compatible providers). See [Inspect's provider instructions](https://inspect.aisi.org.uk/providers.html). These SDKs are not needed for the zero-model-call example or deterministic parity tests.

```sh
inspect eval redcommerce/inspect_tasks.py@redcommerce -T mode=model -T execute=true -T config=inspect-models.json -T budget_usd=5 -T case=RC-T21-GTIN-SCOPE-002 -T out=runs/inspect-models --log-dir logs/inspect-models --max-samples 1
```

The task's named model roles are resolved from the priced configuration. Overrides must still match that configuration. The primary/default model is only a non-generating mock handle, not a third agent. `panel=cases` selects the first world of each Case; `panel=all` selects all worlds. The adapter defaults to **one sample**: set `-T limit=96` or `-T limit=829` explicitly to expand, and use the corresponding panel. This is the public harness's declared selection, not a reconstruction of a historical panel's model samples.

The adapter does not set an output-token limit by default. An explicit `generation.max_tokens` is optional; provider or Inspect defaults can still apply and the effective configuration is recorded in Inspect model events. A truncated decision is not executed as a valid action. Model-call retries and response caching are disabled by the adapter. Provider SDK/server behavior is separate from these settings; never assume that an interrupted request is free.

The cumulative persistent ledger gates dispatch. Usage is priced from Inspect's separate full-rate input, cache-read, cache-write and output counts, not treated as an invoice. Conservative reservations are required; an over-reservation-cost event or unknown usage stops subsequent dispatch. Since providers can charge requests with unknown outcomes, this is not a promise of a provider-enforced billing ceiling.

## Saved state, resume and outcomes

Each Inspect sample uses the original world ID; repeated epochs get separate `-eN` directories. `runs/.../inspect-plan.json` locks source/configuration and `jobs/` saves profiles, original episodes, request/response records, raw scores and final results. A completed sample can be re-scored/resumed without new calls. An incomplete sample directory is never automatically resampled.

Provider/budget stops and cancellation create `halt.json`. Inspect can still display the saved pending/excluded result, but new samples in that run are blocked until the evidence and ledger are reconciled. Do not delete halt/lock/ledger files merely to force a retry. This differs from a model explicitly escalating a commercial decision, which remains a normal task outcome.

The scorer exposes both original scores and denominator metadata. `redcommerce_rates` uses Inspect's unreduced per-epoch scores: repeated fresh runs retain their individual denominators rather than being collapsed to one Case mean. It reports attack successes/evaluable counts, ASR only for real-model runs, pending outcomes, provider exclusions, escalations and available business-goal completion counts. Business completion is not inferred merely from absence of harm. Inspect's displayed summary is never a substitute for the retained raw score.

Logs contain role-specific prompts, outputs and usage events. Scheduler summaries are explicitly labelled as software-generated, not model answers. Logs and sidecar requests are not automatically uploaded or published; use the separate publication exporter before making research transcripts public.

## Native offline parity validation

```sh
python -B integrations/validate_inspect.py --out runs/inspect-parity
python -B -m unittest discover -s tests -v
```

The validation script runs actual Inspect evaluations with its deterministic `mockllm` ModelAPI and compares them to a direct original-scheduler execution. It covers lawful commitment, realized deviation, escalation, attacker abstention, attacker format failure, business format failure, provider filtering and all four sequential role-chain Cases. It also tests resumption without resampling and budget stop before dispatch. Scores, final states, world hashes, allowlist proofs and role order must match; native model events must be present in `.eval` logs. Synthetic token counts/prices are test fixtures, not observed provider bills.

Local validation additionally executed all 96 Case entry worlds through the actual Inspect CLI in offline mode, with original re-scoring and no model events. This is an execution check, not a new main experiment. On Windows, Inspect 0.3.281 can warn that its optional control server lacks `AF_UNIX`; the evaluations and saved `.eval` logs still work. Linux runner parity is covered by the supplied CI workflow and must be checked after pushing, not assumed from Windows results.

This proves native-runtime compatibility for those contracts. **No paid provider smoke test or new benchmark model sweep is claimed.** The historical paper results remain results of the original RedCommerce harness, not retroactively Inspect results.

## References

- https://inspect.aisi.org.uk/models.html#model-roles
- https://inspect.aisi.org.uk/solvers.html#custom-solvers
- https://inspect.aisi.org.uk/scorers.html
