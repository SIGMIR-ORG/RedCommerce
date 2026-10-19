"""Native Inspect tasks. Requires the optional `inspect` dependency extra."""
from __future__ import annotations
import asyncio
import json
import math
from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput, get_model
from inspect_ai.scorer import Score, SampleScore, metric, scorer
from inspect_ai.solver import solver

from redcommerce.cli import RunLock, code_fingerprint
from redcommerce.clients import ModelPolicy
from redcommerce.engine import DATA, offline_episode, read, runtime, scored_outcome, worlds, write
from redcommerce.inspect_bridge import InspectClient, validate_inspect_config


def _model_episode(row, directory, clients, modules, ledger, seed):
    profile = read(DATA/'configs'/row['profile'])
    write(directory/'profile.json', profile)
    roles = profile['business_role'].get('role_chain') or [profile['business_role']['name']]
    common = dict(ledger=ledger, profile=profile, out=directory/'requests', modules=modules)
    policies = {role: ModelPolicy(client=clients['business'], role=role, kind='business', **common) for role in roles}
    business = policies if profile['business_role']['agent_mode'] != 'single' else policies[roles[0]]
    attack = ModelPolicy(client=clients['attacker'], role=profile['counterparty']['name'], kind='counterparty', **common)
    episode = modules['scheduler'].run_episode(profile, row['world_id'], business, attack,
        arm='adversarial', out_dir=directory/'episode', route_id=row['route_id'], seed=seed)
    raw = modules['scorer'].score_migration(profile, directory/'episode')
    score = scored_outcome(raw, episode)
    status = 'complete' if score.get('attack_denominator_eligible') and type(score.get('attack_success')) is bool else 'pending'
    if any('provider_access_blocked' in f.get('failure', '') for f in episode.get('protocol_failures', [])):
        status = 'provider_excluded'
    result = {'case_id': row['case_id'], 'world_id': row['world_id'], 'backend': 'inspect',
              'model_participation': not any(c.is_simulated for c in clients.values()),
              'terminal': episode['terminal'], 'status': status, 'score': score}
    write(directory/'raw-score.json', raw)
    write(directory/'result.json', result)
    return result


@metric(scores='unreduced')
def redcommerce_rates():
    def calculate(scores: list[SampleScore]):
        rows = [s.score.metadata['record'] for s in scores]
        eligible = [r for r in rows if r['score'].get('attack_denominator_eligible')
                    and type(r['score'].get('attack_success')) is bool]
        successes = sum(r['score']['attack_success'] for r in eligible)
        simulated = sum(not r['model_participation'] for r in rows)
        return {'attack_successes': successes, 'attack_evaluable': len(eligible),
                'asr': successes/len(eligible) if eligible and not simulated else None,
                'provider_excluded': sum(r['status'] == 'provider_excluded' for r in rows),
                'pending': sum(r['status'] == 'pending' for r in rows),
                'escalated': sum(r['terminal'] == 'escalated' for r in rows),
                'business_goal_completed': sum(r['score'].get('goal_completion', {}).get('completed') is True for r in rows),
                'business_goal_evaluable': sum(type(r['score'].get('goal_completion', {}).get('completed')) is bool for r in rows),
                'simulated_runs': simulated}
    return calculate


@scorer(metrics=[redcommerce_rates()])
def original_outcome():
    async def score(state, target):
        directory = Path(state.metadata['redcommerce_directory'])
        record = read(directory/'result.json')
        modules = runtime()
        raw = modules['scorer'].score_migration(read(directory/'profile.json'), directory/'episode')
        episode = read(directory/'episode/episode.json')
        actual = scored_outcome(raw, episode) if record['backend'] == 'inspect' else raw
        if actual != record['score']:
            raise ValueError('Re-scored outcome differs from saved result')
        result = actual.get('attack_success') if actual.get('attack_denominator_eligible') else None
        return Score(value={'attack_success': result,
                            'attack_evaluable': bool(actual.get('attack_denominator_eligible'))},
                     answer=record['terminal'], metadata={'record': record, 'original_raw_score': raw},
                     explanation='Original deterministic scorer over executed actions/state; not an LLM judge.')
    return score


@solver
def run_redcommerce(mode, out, config, budget_usd, business, submission, seed):
    serial = asyncio.Lock()
    root = Path(out).resolve()
    modules = runtime()
    async def solve(state, generate):
        async with serial:
            with RunLock(root/'.inspect.lock'):
                clients = None
                if mode == 'model':
                    loop = asyncio.get_running_loop()
                    clients = {kind: InspectClient(get_model(role=kind, required=True), config[kind], loop)
                               for kind in ('attacker', 'business')}
                plan = {'integration': 'inspect-native-v1', 'mode': mode, 'config': config,
                        'source_lock': code_fingerprint(), 'business': business, 'submission': submission,
                        'seed': seed, 'budget_usd': budget_usd}
                if (root/'inspect-plan.json').exists():
                    if read(root/'inspect-plan.json') != plan:
                        raise ValueError('Inspect configuration/source changed; use a new output directory')
                else:
                    if any(p.name != '.inspect.lock' for p in root.iterdir()):
                        raise ValueError('Output is not empty and contains no Inspect run plan')
                    write(root/'inspect-plan.json', plan)
                row = state.metadata['redcommerce_world']
                directory = root/'jobs'/f'{state.sample_id}-e{state.epoch}'
                if (directory/'result.json').exists():
                    result = read(directory/'result.json')
                    if result['case_id'] != row['case_id'] or result['world_id'] != row['world_id']:
                        raise ValueError('Saved Inspect sample identity mismatch')
                elif directory.exists():
                    # Never retry a possibly charged incomplete request automatically.
                    raise ValueError('Incomplete sample directory exists; reconcile before resuming')
                elif (root/'halt.json').exists():
                    raise ValueError('Run halted after provider/budget failure; reconcile the saved evidence before new dispatch')
                elif mode == 'offline':
                    result = await asyncio.to_thread(offline_episode, row, directory, business, submission, seed)
                    result['status'] = 'complete' if result['score'].get('score_eligible') else 'pending'
                    write(directory/'result.json', result)
                else:
                    ledger = modules['provider'].PersistentLedger(root/'costs.jsonl', total_cap_usd=budget_usd)
                    work = asyncio.create_task(asyncio.to_thread(_model_episode, row, directory, clients, modules, ledger, seed))
                    try:
                        result = await asyncio.shield(work)
                    except asyncio.CancelledError:
                        # Keep the run lock until a dispatched request is recorded.
                        # Cancellation must not permit a second process to resample it.
                        try:
                            await asyncio.shield(work)
                        finally:
                            write(root/'halt.json', {'reason': 'Inspect sample cancelled; reconcile saved requests before new dispatch'})
                        raise
                    episode = read(directory/'episode/episode.json')
                    if any(f.get('stage') == 'budget' for f in episode.get('protocol_failures', [])):
                        write(root/'halt.json', {'reason': 'Provider/budget stop; no automatic retry'})
                state.metadata['redcommerce_directory'] = str(directory)
                state.metadata['redcommerce_mode'] = mode
                state.output = ModelOutput.from_content(model='redcommerce/scheduler',
                    content=json.dumps({'source': 'scheduler summary, not a model answer', **result}, ensure_ascii=False))
                state.completed = True
                return state
    return solve


@task
def redcommerce(mode='offline', case=None, world=None, panel='cases', limit=1,
               out='runs/inspect', config=None, execute=False, budget_usd=None,
               business='reference', submission='fixed', seed=0):
    """Run an original RedCommerce episode inside Inspect; offline by default."""
    if mode not in ('offline', 'model') or business not in ('reference', 'vulnerable') or submission not in ('fixed', 'unchanged'):
        raise ValueError('Invalid mode, offline business policy or submission')
    root = Path(out).resolve()
    if root == DATA or DATA in root.parents:
        raise ValueError('Inspect output must be outside frozen data')
    selected = worlds(case=case, world=world, panel=panel)
    if limit is not None:
        if type(limit) is not int or limit <= 0:
            raise ValueError('limit must be a positive integer')
        selected = selected[:limit]
    settings = None
    model_roles = None
    if mode == 'model':
        if execute is not True or type(budget_usd) not in (int, float) or not math.isfinite(budget_usd) or budget_usd <= 0 or not config:
            raise ValueError('Model mode requires execute=True, config path and a positive finite budget_usd')
        settings = validate_inspect_config(read(config))
        model_roles = {kind: settings[kind]['model'] for kind in ('attacker', 'business')}
    elif execute or config or budget_usd is not None:
        raise ValueError('Offline mode does not accept model-dispatch settings')
    samples = [Sample(id=r['world_id'], input=(DATA/'benchmark/tasks'/r['case_id']/'instruction.md').read_text('utf-8'),
                      metadata={'redcommerce_world': r}) for r in selected]
    return Task(name='redcommerce', dataset=samples,
                solver=run_redcommerce(mode, str(root), settings, budget_usd, business, submission, seed),
                scorer=original_outcome(), model='mockllm/model', model_roles=model_roles,
                metadata={'harness': 'RedCommerce scheduler/scorer; Inspect native model transport',
                          'historical_results_migrated': False}, version='1')
