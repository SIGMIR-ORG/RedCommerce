"""Run real Inspect evaluations with deterministic, network-free ModelAPI fixtures.

Compares against a separately executed original scheduler/ModelPolicy path.
No provider credentials are used and no model-performance result is produced.
"""
from __future__ import annotations
import argparse
import copy
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from inspect_ai import eval as inspect_eval
from inspect_ai.log import read_eval_log
from inspect_ai.model import ModelOutput, ModelUsage, get_model
from redcommerce.clients import ModelPolicy, parse_envelope
from redcommerce.engine import DATA, offline_program, read, runtime, worlds, write
from redcommerce.inspect_tasks import _model_episode, redcommerce

LISTING = 'RC-T21-GTIN-SCOPE-002'


class Fixture:
    def __init__(self, row, mode, role):
        self.row, self.mode, self.role = row, mode, role
        self.profile = read(DATA/'configs'/row['profile'])
        self.calls = []

    def envelope(self, request):
        self.calls.append(copy.deepcopy(request))
        body = json.loads(request['messages'][1]['content'])
        if self.role == 'attacker':
            if self.mode == 'attacker_format':
                return 'not a JSON decision'
            if self.mode in ('attacker_abstain', 'provider_block'):
                return {'actions': []}
            writes = [] if self.mode in ('lawful', 'role_chain') else self.profile['arms']['fixed']['fixed_content_writes']
            return {'actions': [{'tool': body['action_schema']['tool'], 'arguments': {'writes': writes}}]}
        if self.mode == 'business_format':
            return 'not a JSON decision'
        program = offline_program(self.row['case_id'], request['role'],
                                  'vulnerable' if self.mode == 'deviation' else 'reference')
        process = subprocess.run([sys.executable, '-B', str(program)],
            input=json.dumps(body['observation']).encode(), capture_output=True, check=True)
        return json.loads(process.stdout)

    def inspect_output(self, messages, tools, tool_choice, config):
        assert len(tools) == 1 and tools[0].name == 'emit_actions'
        assert tool_choice == 'auto' and config.max_retries == 0
        # No output-token limit was injected by the adapter's default configuration.
        request = {'role': json.loads(messages[1].text).get('role', self.profile['business_role']['name']),
                   'messages': [{'role': 'system', 'content': messages[0].text},
                                {'role': 'user', 'content': messages[1].text}]}
        if self.role == 'business':
            request['role'] = messages[0].text.split('You are acting as: ', 1)[1].split('.', 1)[0]
        else:
            request['role'] = self.profile['counterparty']['name']
        envelope = self.envelope(request)
        name = f'rc-{self.role}'
        if self.mode == 'provider_block' and self.role == 'attacker':
            output = ModelOutput.from_content(name, 'Synthetic provider filter', stop_reason='content_filter')
        elif isinstance(envelope, dict):
            output = ModelOutput.for_tool_call(name, 'emit_actions', envelope)
        else:
            output = ModelOutput.from_content(name, envelope)
        output.usage = ModelUsage(input_tokens=10, output_tokens=2, total_tokens=12)
        return output


class DirectClient:
    is_simulated = True
    reserve_usd = .05
    def __init__(self, fixture):
        self.fixture = fixture
        self.model = 'mockllm/rc-'+fixture.role
    def __call__(self, request):
        actions, status = parse_envelope(self.fixture.envelope(request), request)
        return {'actions': actions, 'parse_status': status, 'returned_model': 'rc-'+self.fixture.role,
                'usage': {'input_tokens': 10, 'output_tokens': 2, 'total_tokens': 12}, 'cost_usd': 0,
                'failure': 'provider_access_blocked' if self.fixture.role == 'attacker' and self.fixture.mode == 'provider_block' else None,
                'raw': {'fixture': True}}


def validate(out):
    out = Path(out).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('Use an empty validation directory')
    out.mkdir(parents=True, exist_ok=True)
    modules = runtime()
    base = worlds(case=LISTING, panel='cases')[0]
    fixtures = [(name, base) for name in ('lawful', 'deviation', 'escalation',
                 'attacker_abstain', 'attacker_format', 'business_format', 'provider_block')]
    chains = [r for r in worlds(panel='cases') if read(DATA/'configs'/r['profile'])['business_role']['agent_mode'] != 'single']
    fixtures += [('role_chain', r) for r in chains]
    assert len(chains) == 4
    results = []
    first = None
    for index, (mode, row) in enumerate(fixtures):
        directory = out/f'f{index:02d}'
        direct = {kind: Fixture(row, mode, kind) for kind in ('attacker', 'business')}
        clients = {kind: DirectClient(fixture) for kind, fixture in direct.items()}
        ledger = modules['provider'].PersistentLedger(directory/'direct/costs.jsonl', total_cap_usd=1)
        expected = _model_episode(row, directory/'direct/job', clients, modules, ledger, 0)
        native = {kind: Fixture(row, mode, kind) for kind in ('attacker', 'business')}
        models = {kind: get_model('mockllm/rc-'+kind, custom_outputs=fixture.inspect_output, memoize=False)
                  for kind, fixture in native.items()}
        config = {kind: {'model': 'mockllm/rc-'+kind, 'reserve_usd': .05,
                  'allowed_returned_models': ['rc-'+kind],
                  'prices_per_million': dict(input=0, output=0, cache_read=0, cache_write=0)}
                  for kind in ('attacker', 'business')}
        write(directory/'config.json', config)
        task = redcommerce(mode='model', world=row['world_id'], config=str(directory/'config.json'),
                           execute=True, budget_usd=1, out=str(directory/'native'))
        logs = inspect_eval(task, model_roles=models, log_dir=str(directory/'logs'),
                            display='none', max_samples=1, retry_on_error=0)
        log = logs[0]
        assert log.status == 'success', repr(log.error)
        assert log.samples and len(log.samples) == 1
        sample = log.samples[0]
        actual_dir = Path(sample.metadata['redcommerce_directory'])
        actual = read(actual_dir/'result.json')
        assert actual['score'] == expected['score'], f'{mode}: score mismatch'
        assert actual['terminal'] == expected['terminal'] and actual['status'] == expected['status'], mode
        native_ep, direct_ep = read(actual_dir/'episode/episode.json'), read(directory/'direct/job/episode/episode.json')
        for field in ('final_state', 'final_world_sha256', 'surface_proofs', 'refused_writes'):
            assert native_ep[field] == direct_ep[field], f'{mode}: {field} mismatch'
        assert [d.get('role', 'business') for d in native_ep['decisions']] == [d.get('role', 'business') for d in direct_ep['decisions']]
        expected_roles = read(DATA/'configs'/row['profile'])['business_role']
        if mode == 'role_chain':
            assert [d['role'] for d in native_ep['decisions']] == expected_roles['role_chain']
        # Framework-native model events must be in the .eval log, not only sidecar JSON.
        model_events = [e for e in sample.events if e.event == 'model']
        assert len(model_events) == len(native['attacker'].calls)+len(native['business'].calls)
        assert model_events
        assert {e.role for e in model_events} == ({'attacker', 'business'} if native['business'].calls else {'attacker'})
        replay = read_eval_log(log.location)
        assert replay.samples[0].scores
        if mode == 'lawful':
            assert actual['terminal'] == 'committed' and not actual['score']['target_deviation_observed']
        if mode == 'deviation':
            assert actual['score']['attack_success'] is True
        if mode == 'escalation':
            assert actual['terminal'] == 'escalated'
        if mode in ('attacker_abstain', 'attacker_format'):
            assert actual['score']['attack_denominator_eligible'] and actual['score']['attack_success'] is False
        if mode == 'business_format':
            assert actual['status'] == 'pending'
        if mode == 'provider_block':
            assert actual['status'] == 'provider_excluded' and not actual['score']['attack_denominator_eligible']
        results.append({'fixture': mode, 'world_id': row['world_id'], 'pass': True,
            'terminal': actual['terminal'], 'status': actual['status'],
            'score_equal': True, 'state_equal': True, 'native_model_events': len(model_events),
            'inspect_log': log.location, 'model_participation': False})
        if index == 0:
            first = (task, models, native, directory, actual_dir)
        print(f'PASS {mode}: {row["case_id"]}', flush=True)
    task, models, native, first_dir, saved_dir = first
    before = {kind: len(f.calls) for kind, f in native.items()}
    saved = (saved_dir/'episode/episode.json').read_bytes()
    resumed = inspect_eval(task, model_roles=models, log_dir=str(first_dir/'resume-logs'),
                           display='none', max_samples=1, retry_on_error=0)[0]
    assert resumed.status == 'success'
    assert before == {kind: len(f.calls) for kind, f in native.items()}
    assert saved == (saved_dir/'episode/episode.json').read_bytes()
    assert not [e for e in resumed.samples[0].events if e.event == 'model']
    cap_root = out/'budget-stop'
    cap_task = redcommerce(mode='model', world=base['world_id'], config=str(first_dir/'config.json'),
                          execute=True, budget_usd=.01, out=str(cap_root))
    stopped = inspect_eval(cap_task, model_roles=models, log_dir=str(out/'budget-logs'),
                           display='none', max_samples=1, retry_on_error=0)[0]
    assert stopped.status == 'success' and (cap_root/'halt.json').exists()
    assert not [e for e in stopped.samples[0].events if e.event == 'model']
    assert before == {kind: len(f.calls) for kind, f in native.items()}
    blocked_record = read(Path(stopped.samples[0].metadata['redcommerce_directory'])/'result.json')
    assert blocked_record['status'] == 'pending' and not blocked_record['score']['attack_denominator_eligible']
    epoch_root = out/'two-epochs'
    epoch_task = redcommerce(mode='model', world=base['world_id'], config=str(first_dir/'config.json'),
                            execute=True, budget_usd=1, out=str(epoch_root))
    epochs = inspect_eval(epoch_task, model_roles=models, epochs=2, log_dir=str(out/'epoch-logs'),
                         display='none', max_samples=2, retry_on_error=0)[0]
    assert epochs.status == 'success' and len(epochs.samples) == 2
    assert len(list((epoch_root/'jobs').glob('*/result.json'))) == 2
    epoch_metrics = epochs.results.scores[0].metrics
    assert epoch_metrics['attack_evaluable'].value == 2
    assert epoch_metrics['simulated_runs'].value == 2
    assert 'asr' not in epoch_metrics
    report = {'pass': True, 'inspect_ai_version': importlib.metadata.version('inspect-ai'),
              'native_inspect_evaluations': len(results), 'role_chains': len(chains),
              'resume_without_resampling': True, 'budget_stop_before_dispatch': True,
              'epoch_denominator_preserved': True, 'additional_inspect_evaluations': 3,
              'fixtures': results, 'real_model_calls': 0, 'real_cost_usd': 0,
              'interpretation': 'Native Inspect runtime parity using deterministic ModelAPI fixtures; not model performance.'}
    write(out/'report.json', report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    validate(parser.parse_args().out)
