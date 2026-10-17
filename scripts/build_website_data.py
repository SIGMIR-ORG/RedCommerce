"""Build public website data from the exported, offline paper evidence."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = ROOT / 'artifact/build/redcommerce-supplement'
STAGES = ['Awareness', 'Discovery', 'Engagement', 'Decision', 'Transaction', 'Fulfillment', 'Service']
MODELS = ['Opus 5.5', 'DeepSeek V4.1 Flash', 'Qwen 3.8 Max', 'Gemini 3.8 Flash']

def read(relative):
    return json.loads((SOURCE / relative).read_text(encoding='utf-8'))

def rates(rows):
    eligible = [r for r in rows if r['eligible'] and type(r['attack_success']) is bool]
    successes = sum(r['attack_success'] for r in eligible)
    return {'successes': successes, 'eligible': len(eligible), 'asr': successes / len(eligible) if eligible else None}

def main():
    rows = read('evidence/main/outcomes.json')
    worlds = read('configs/worlds.json')
    assert len(rows) == 3316 and len(worlds['rows']) == 829
    assert len({r['case_id'] for r in worlds['rows']}) == 96
    recorded = read('paper-assets/results.json')['all829']
    models = []
    for name in MODELS:
        model_rows = [r for r in rows if r['model'] == name]
        assert len(model_rows) == len({r['world_id'] for r in model_rows}) == 829
        result = rates(model_rows)
        reference = recorded[name]
        assert result['successes'] == reference['successes']
        assert result['eligible'] == reference['eligible']
        per_case = defaultdict(list)
        for r in model_rows:
            per_case[r['case_id']].append(r)
        case_rates = [rates(v)['asr'] for v in per_case.values()]
        case_rates = [v for v in case_rates if v is not None]
        result.update(name=name, planned=829, macro_asr=sum(case_rates)/len(case_rates),
            service_excluded=reference['refusals'], unresolved=829-result['eligible']-reference['refusals'],
            stages=[rates([r for r in model_rows if int(r['case_id'][4]) == i]) for i in range(1,8)])
        models.append(result)
    case_worlds = Counter(r['case_id'] for r in worlds['rows'])
    cases = []
    for task in sorted((SOURCE / 'benchmark/tasks').iterdir()):
        if not task.is_dir():
            continue
        instruction = (task / 'instruction.md').read_text(encoding='utf-8').strip()
        lines = instruction.splitlines()
        has_heading = lines[0].startswith('# ')
        title = lines[0].lstrip('# ').strip() if has_heading else ' '.join(task.name.split('-')[2:-1]).capitalize()
        cases.append({'id': task.name, 'title': title,
            'instruction': '\n'.join(lines[1:]).strip() if has_heading else instruction, 'stage': int(task.name[4]),
            'worlds': case_worlds[task.name]})
    repeated = read('paper-assets/repeated_results.json')
    authorization = read('paper-assets/authorization_results.json')
    data = {'corpus': {'cases':96, 'worlds':829, 'stages':STAGES, 'roles':5, 'threat_families':24},
        'business_model':'Haiku 4.5', 'main':models, 'cases':cases,
        'matched':repeated['controls'], 'authorization':authorization,
        'source_sha256':hashlib.sha256((SOURCE/'evidence/main/outcomes.json').read_bytes()).hexdigest()}
    dest = HERE / 'assets'
    dest.mkdir(exist_ok=True)
    (dest/'data.json').write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    # A classic script lets this preview work both through HTTP and by opening index.html.
    (dest/'data.js').write_text('window.RED_COMMERCE_DATA = '+json.dumps(data,ensure_ascii=False)+';\n',encoding='utf-8')
    print(f'Website data: {len(models)} models, {len(cases)} Cases, {len(worlds["rows"])} worlds')

if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=SOURCE)
    parser.add_argument('--output',type=Path,default=HERE)
    args=parser.parse_args()
    SOURCE=args.source.resolve()
    HERE=args.output.resolve()
    main()
