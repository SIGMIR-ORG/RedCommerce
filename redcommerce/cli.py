from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys

from . import __version__
from .engine import DATA,offline_episode,read,reproduce,runtime,scored_outcome,task_catalog,worlds,write

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def validate_config(config):
    for role in ('attacker','business'):
        value=config.get(role)
        if not isinstance(value,dict) or value.get('backend') not in ('chat-completions','anthropic','plugin'):
            raise ValueError(f'{role} needs a supported backend config')
        if not value.get('model') or type(value.get('reserve_usd')) not in (int,float) or not math.isfinite(value['reserve_usd']) or value['reserve_usd']<=0:
            raise ValueError(f'{role} needs a model identifier and positive reserve_usd')
        if value['backend']=='plugin':
            if ':' not in value.get('factory',''):
                raise ValueError('plugin factory must be module:function')
        else:
            if not value.get('endpoint') or not value.get('api_key_env') or not value.get('prices_per_million'):
                raise ValueError(f'{role} requires endpoint, api_key_env, and configured prices_per_million')
            categories=('input','output','cache_read','cache_write') if value['backend']=='anthropic' else ('input','output','cache_read')
            for category in categories:
                rate=value['prices_per_million'].get(category)
                if type(rate) not in (int,float) or not math.isfinite(rate) or rate<0:
                    raise ValueError(f'{role} needs a finite nonnegative price for {category} before dispatch')
            if value['backend']=='anthropic' and (type(value.get('max_output_tokens')) is not int or value['max_output_tokens']<=0):
                raise ValueError(f'{role}: Anthropic requires explicit max_output_tokens')
            if value.get('max_output_tokens') is not None and (type(value['max_output_tokens']) is not int or value['max_output_tokens']<=0):
                raise ValueError(f'{role}: output limit must be a positive integer when specified')
        forbidden={'api_key','key','authorization','password','token'}
        if forbidden & {k.lower() for k in value}:
            raise ValueError('Do not put credentials in a config; use environment variable names')
    return config

def code_fingerprint():
    here=Path(__file__).resolve().parent
    files=sorted(here.glob('*.py'))+[here/'instruction_appendices.json', DATA/'FILES.json',
        DATA/'benchmark/parallel/20260913-live-migration/provider.py']
    return {str(p.relative_to(here)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}

def prepare(args):
    from .engine import verify_frozen_files
    verify_frozen_files()
    selected=worlds(args.case,args.world,args.panel)
    if args.limit is not None:
        if args.limit<=0:
            raise ValueError('--limit must be positive')
        selected=selected[:args.limit]
    config=validate_config(read(args.config)) if args.config else None
    return {'version':__version__,'backend':'model' if config else 'offline',
        'arm':'adversarial' if config else 'fixed','seed':args.seed,'offline_business':args.business,
        'offline_submission':args.submission,
        'model_config':config,'jobs':selected,'source_lock':code_fingerprint(),
        'selection':'All declared worlds, or the first declared world per Case for panel=cases; no filtering on historical outcome.',
        'prompts':'public-model-interface-v1 with evaluated public instruction amendments',
        'automatic_retries':0}

class RunLock:
    def __init__(self,path):
        self.path=Path(path)
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        try:
            fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        except FileExistsError:
            raise RuntimeError('Run lock exists. Confirm no process is running before removing the stale .run.lock file.') from None
        with os.fdopen(fd,'w') as file:
            file.write(str(os.getpid()))
        return self
    def __exit__(self,*args):
        self.path.unlink(missing_ok=True)

def summarize(plan,out,ledger=None):
    records=[]
    for job in plan['jobs']:
        path=out/'jobs'/job['world_id']/'result.json'
        if path.is_file():
            record=read(path)
            if record.get('world_id')!=job['world_id'] or record.get('case_id')!=job['case_id']:
                raise ValueError('Saved result identity does not match the run plan')
            records.append(record)
    eligible=[r for r in records if r['score'].get('attack_denominator_eligible') and type(r['score'].get('attack_success')) is bool]
    success=sum(r['score']['attack_success'] for r in eligible)
    is_simulated=any(r.get('model_participation') is False for r in records)
    result={'planned':len(plan['jobs']),'saved':len(records),'remaining':len(plan['jobs'])-len(records),
        'evaluated_attack_episodes':len(eligible),'attack_successes':success,
        'asr':success/len(eligible) if eligible and not is_simulated else None,
        'score_eligible':sum(bool(r['score'].get('score_eligible')) for r in records),
        'pending':sum(r.get('status')=='pending' for r in records),'simulated_or_offline':is_simulated,
        'provider_excluded':sum(r.get('status')=='provider_excluded' for r in records),
        'budget':ledger.summary() if ledger else {'real_api_calls':0,'cost_usd':0},
        'interpretation':'Offline/simulated policies are execution checks, not model performance.' if is_simulated else 'One sample per selected world with the configured attacker and business roles.'}
    write(out/'summary.json',result)
    return result

def run(args):
    from .clients import ModelPolicy,make_client
    plan=prepare(args)
    if plan['backend']=='model' and (not args.execute or args.budget_usd is None or not math.isfinite(args.budget_usd) or args.budget_usd<=0):
        raise ValueError('Model runs require --execute and a positive --budget-usd; use plan to inspect requests without dispatch')
    out=args.out.resolve()
    if out==DATA.resolve() or DATA.resolve() in out.parents:
        raise ValueError('Output must be outside the frozen dataset')
    if out.is_dir() and any(out.iterdir()) and not (out/'plan.json').is_file():
        raise ValueError('Output directory is not empty and contains no RedCommerce plan; choose a new directory')
    out.mkdir(parents=True,exist_ok=True)
    ledger=None;modules=None
    with RunLock(out/'.run.lock'):
        if (out/'plan.json').is_file():
            if read(out/'plan.json')!=plan:
                raise ValueError('Run configuration or source code changed; use a new output directory')
        else:
            write(out/'plan.json',plan)
        if plan['backend']=='model':
            modules=runtime()
            ledger=modules['provider'].PersistentLedger(out/'costs.jsonl',total_cap_usd=args.budget_usd)
            clients={kind:make_client(plan['model_config'][kind]) for kind in ('attacker','business')}
        for job in plan['jobs']:
            directory=out/'jobs'/job['world_id']
            if (directory/'result.json').is_file():
                continue
            if (directory/'episode/episode.json').is_file():
                # A crash after execution but before saving result must not trigger resampling.
                profile=read(directory/'profile.json');episode=read(directory/'episode/episode.json')
                modules=modules or runtime()
                raw=modules['scorer'].score_migration(profile,directory/'episode')
                result={'case_id':job['case_id'],'world_id':job['world_id'],
                    'backend':plan['backend'],'terminal':episode['terminal'],'recovered_saved_episode':True,
                    'model_participation':plan['backend']=='model' and all(not getattr(c,'is_simulated',False) for c in clients.values()),
                    'score':scored_outcome(raw,episode) if plan['backend']=='model' else raw}
                result['status']='complete' if result['score'].get('score_eligible') else 'pending'
                write(directory/'result.json',result)
                continue
            if directory.exists():
                raise ValueError('Incomplete job directory exists; reconcile its saved requests before resuming')
            if plan['backend']=='offline':
                result=offline_episode(job,directory,args.business,args.submission,args.seed)
                result['status']='complete' if result['score'].get('score_eligible') else 'pending'
                write(directory/'result.json',result)
            else:
                profile=read(DATA/'configs'/job['profile'])
                write(directory/'profile.json',profile)
                roles=profile['business_role'].get('role_chain') or [profile['business_role']['name']]
                policies={role:ModelPolicy(client=clients['business'],ledger=ledger,role=role,kind='business',profile=profile,out=directory/'requests',modules=modules) for role in roles}
                business=policies if profile['business_role']['agent_mode']!='single' else policies[roles[0]]
                attacker=ModelPolicy(client=clients['attacker'],ledger=ledger,role=profile['counterparty']['name'],kind='counterparty',profile=profile,out=directory/'requests',modules=modules)
                try:
                    episode=modules['scheduler'].run_episode(profile,job['world_id'],business,attacker,
                        arm='adversarial',out_dir=directory/'episode',route_id=job['route_id'],seed=args.seed)
                    raw=modules['scorer'].score_migration(profile,directory/'episode')
                    score=scored_outcome(raw,episode)
                    result={'case_id':job['case_id'],'world_id':job['world_id'],'backend':'model',
                        'model_participation':attacker.is_language_model and all(p.is_language_model for p in policies.values()),
                        'terminal':episode['terminal'],'score':score,
                        'status':'complete' if score.get('attack_denominator_eligible') and type(score.get('attack_success')) is bool else 'pending'}
                    if any('provider_access_blocked' in str(f.get('failure','')) for f in episode.get('protocol_failures',[])):
                        result.update(status='provider_excluded',exclusion_category='provider_access_blocked')
                    write(directory/'raw-score.json',raw)
                    write(directory/'result.json',result)
                except Exception as error:
                    write(directory/'halt.json',{'kind':type(error).__name__,'reason':str(error)})
                    summarize(plan,out,ledger)
                    raise
                if any(r.get('stage')=='budget' for r in episode.get('protocol_failures',[])):
                    summarize(plan,out,ledger)
                    raise RuntimeError('Run stopped at provider/budget failure; inspect saved episode and costs.jsonl')
            print(json.dumps({'world_id':job['world_id'],'terminal':result['terminal'],'status':result['status']}),flush=True)
        print(json.dumps(summarize(plan,out,ledger),indent=2))
    return 0

def main(argv=None):
    parser=argparse.ArgumentParser(prog='redcommerce',description='Run commercial tasks or reproduce saved paper evidence')
    parser.add_argument('--version',action='version',version=__version__)
    commands=parser.add_subparsers(dest='command',required=True)
    catalog=commands.add_parser('list',help='List available tasks or worlds')
    catalog.add_argument('--case');catalog.add_argument('--worlds',action='store_true');catalog.add_argument('--json',action='store_true')
    commands.add_parser('reproduce',help='Recompute paper tables from saved records, offline')
    replay=commands.add_parser('replay',help='Re-score saved companion trajectories, offline')
    replay.add_argument('--study',choices=['all','matched96','mechanism-repeats','authorization-comparison'],default='all')
    for name in ('plan','run'):
        command=commands.add_parser(name,help='Inspect selected jobs without dispatch' if name=='plan' else 'Execute selected task worlds')
        command.add_argument('--case');command.add_argument('--world')
        command.add_argument('--panel',choices=['all','cases'],default='cases')
        command.add_argument('--limit',type=int);command.add_argument('--seed',type=int,default=0)
        command.add_argument('--business',choices=['reference','vulnerable'],default='reference',help='Offline business policy')
        command.add_argument('--submission',choices=['fixed','unchanged'],default='fixed',help='Offline demo: apply the frozen submitted content, or keep the selected world unchanged')
        command.add_argument('--config',type=Path,help='Model configuration JSON; omitted means an offline demo')
        command.add_argument('--out',type=Path,default=Path('runs/demo'))
        command.add_argument('--execute',action='store_true',help='Enable dispatch for model configurations')
        command.add_argument('--budget-usd',type=float,help='Cumulative cost limit in this output directory')
    args=parser.parse_args(argv)
    try:
        if args.command=='list':
            rows=worlds(args.case) if args.worlds else task_catalog()
            if args.case and not args.worlds:
                rows=[r for r in rows if r['case_id']==args.case]
                if not rows:
                    raise ValueError('Unknown Case ID')
            if args.json:
                print(json.dumps(rows,indent=2,ensure_ascii=False))
            else:
                for row in rows:
                    print(row['world_id'] if args.worlds else f'{row["case_id"]}\t{row["worlds"]} worlds\t{row["business_role"]}')
            return 0
        if args.command in ('reproduce','replay'):
            return reproduce(args.command,getattr(args,'study','all'))
        if args.command=='plan':
            plan=prepare(args)
            print(json.dumps({'backend':plan['backend'],'jobs':len(plan['jobs']),
                'selected_worlds':[r['world_id'] for r in plan['jobs']], 'max_declared_role_calls':sum(r['maximum_role_calls'] for r in plan['jobs']),
                'model_config':plan['model_config'],'api_calls':0},indent=2))
            return 0
        return run(args)
    except (ValueError,RuntimeError) as error:
        print(f'Error: {error}',file=sys.stderr)
        return 1
