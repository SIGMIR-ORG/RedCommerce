# Evaluation framework integration

Assessment date: 2026-10-19. The original RedCommerce scheduler, tool allowlists,
worlds and scorer remain the experiment authority. No new model sweep or framework
parity claim is introduced by the public-release preparation.

| Framework | Fit | Integration route | Current status |
| --- | --- | --- | --- |
| Inspect AI | Native runtime implemented | Custom solver calls the original episode scheduler; role policies use Inspect model handles; original deterministic scorer is wrapped as a custom scorer | Runnable task/model transport, named model roles and native logs; deterministic native-runtime parity tested; no paid provider smoke claimed. See [INSPECT.md](INSPECT.md) |
| Harbor | Strong for sandboxed distribution and trajectory interoperability | Custom installed/external agent wraps the existing loop; declare task environments and separate verifier; emit ATIF logs | ATIF-v1.7 saved-message exporter supplied; Harbor runtime/package validation not yet claimed |
| garak | Useful as an auxiliary prompt/probe layer, less direct for full commerce episodes | Custom Generator calls an entire episode; a Probe defines a declared surface; Detector reads the original task scorer | Feasible but lowest priority; no garak plugin supplied |

The existing RedCommerce `task.toml` is not automatically a Harbor-compatible
configuration merely because the filename matches. Task config conversion and
verifier isolation must be implemented and tested explicitly. garak's default
prompt/output scan rate is likewise not automatically the episode-level ASR.

## What must remain invariant

1. Attacker and business agent remain separate model actors; multi-role business chains stay intact.
2. Attacker writes are applied through the original allowlist and surface proofs, not by editing trusted records.
3. Score is computed from actual executed actions/state by the original scorer. The framework must not replace it with a text-pattern detector or an LLM judge.
4. Attack success is a realized task-defined deviation. An attacker-side reward of one means attack success, **not** successful lawful business completion.
5. Attacker abstention/format failure, business failure, provider filtering and pending outcomes preserve their original role-specific treatment. Pending is not an automatic zero.
6. Surrounding software blocking remains distinct from an agent refusing an unsafe action.
7. A code-capable agent must not be given writable access to the scorer or private trusted records. Harbor's separate verifier or an equivalent Inspect sandbox boundary is required for a native code-agent comparison.
8. Existing paid model results remain labelled as the original RedCommerce harness; converting logs does not turn them into Harbor/Inspect results.

## Supplied offline format bridges

```sh
python integrations/export_trajectories.py TRACE.json --format atif --out trajectory.json
python integrations/export_trajectories.py TRACE.json --format inspect-jsonl --out sample.jsonl
```

ATIF export keeps each recorded role/request in a subtrajectory rather than
pretending two distinct agents were one chat participant. It contains recorded
messages and submitted actions, not invented model thinking. When Harbor is
installed separately, add `--validate-harbor` for validation by its actual models.
The Inspect JSONL follows Sample fields (`id`, `input`, `target`, `metadata`); it is
an import fixture, not a runnable native evaluation with a custom scorer.

## Recommended native pilot

The Inspect pilot is now implemented in `redcommerce/inspect_tasks.py` and `redcommerce/inspect_bridge.py`. Installation, offline/model commands, costs, resume behavior and the actual validation scope are documented in [INSPECT.md](INSPECT.md). The sections below describe the rationale and the remaining live-provider / Harbor work, not a claim that all three integrations are complete.

Start with Inspect because custom solvers can wrap the existing Python scheduling
loop directly and Inspect supports named multi-agent model roles. Prove parity on
eight offline fixtures: lawful commit, realized deviation, escalation, attacker
abstention, attacker format failure, business format failure, service block and a
real role chain. Require exact outcome/eligibility/state equality before any paid
call. Then run one explicitly budgeted native-model smoke and document provider
parameters and tool schemas. That smoke is not authorized or run by this release.

For Harbor, first export one self-contained task plus separate verifier and use a
custom RedCommerce agent rather than handing a generic terminal agent all source
files. Verify protected-state isolation and identical scoring, then scale. ATIF log
interchange can be used before migrating execution.

## Primary documentation

- [Inspect custom agents](https://inspect.aisi.org.uk/agent-custom.html)
- [Inspect multi-agent support](https://inspect.aisi.org.uk/multi-agent.html)
- [Inspect custom scorers](https://inspect.aisi.org.uk/scorers.html)
- [Harbor tasks and rewards](https://docs.harborframework.com/tasks/overview)
- [Harbor custom agents](https://docs.harborframework.com/agents/custom-agents)
- [Harbor ATIF-v1.7](https://docs.harborframework.com/agents/atif)
- [garak probes](https://docs.garak.ai/garak/garak-components/vulnerability-probes)
- [garak execution architecture](https://reference.garak.ai/en/latest/how.html)
