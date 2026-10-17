"""Re-execute all saved companion actions and compare original deterministic scores.

Only six source modules plus task drivers/verifiers are imported. No provider,
credentials or model generation. The evaluated view builder is extracted verbatim.
"""
import argparse
import copy
import json
from pathlib import Path
import socket
import sys

ROOT=Path(__file__).resolve().parents[1]
BENCH=ROOT/'benchmark'
sys.path.insert(0,str(BENCH/'parallel/20260915-outcome-scoring'))
sys.path.insert(0,str(BENCH))
sys.dont_write_bytecode=True


def no_network(*args,**kwargs):raise RuntimeError('This reproduction command is offline-only')


socket.create_connection=no_network
socket.socket.connect=no_network
socket.socket.connect_ex=no_network
import scorer
import evaluated_views


def read(path):return json.loads(Path(path).read_text('utf-8'))


class ViewDriver:
    def __init__(self,driver,bundle,cell,condition):self.driver,self.bundle,self.cell,self.condition=driver,bundle,cell,condition
    def __getattr__(self,name):return getattr(self.driver,name)
    def view(self,world,state,role):
        before=copy.deepcopy(world)
        roles=self.bundle.raw['agent'].get('roles') or [self.bundle.raw['case']['commit_agent']]
        value=evaluated_views.observation(self.bundle,world,self.driver,roles,state,role,self.condition)['observation']
        assert world==before,'view mutated execution world'
        return value
    def build_observation(self,world,instruction):return self.view(world,None,self.bundle.raw['case']['commit_agent'])
    def build_role_observation(self,world,state,instruction,role):return self.view(world,state,role)


StudyView=evaluated_views.make_study_view(ViewDriver)


def main():
    a=argparse.ArgumentParser();a.add_argument('--study',choices=['all','matched96','mechanism-repeats','authorization-comparison'],default='all')
    args=a.parse_args();rows=read(ROOT/'evidence/replay-index.json');passed=0;problems=[]
    rows=[r for r in rows if args.study=='all' or r['study']==args.study]
    for row in rows:
        path=ROOT/row['directory'];job=read(path/'job.json');profile=read(path/'profile.json')
        original=scorer.replay.load_driver
        scorer.replay.load_driver=lambda b:StudyView(original(b),b,job['cell_id'],job['condition'])
        try:
            actual=scorer.score_migration(profile,path/'episode')
            expected=read(path/'score.json')
            assert actual==expected,[(k,actual.get(k),expected.get(k)) for k in set(actual)|set(expected) if actual.get(k)!=expected.get(k)]
            passed+=1
        except Exception as error:
            problems.append({'id':row['id'],'error':str(error)[:1500]})
        finally:scorer.replay.load_driver=original
        if (passed+len(problems))%100==0:print(f'Replayed {passed+len(problems)}/{len(rows)}; differences={len(problems)}',flush=True)
    print(json.dumps({'status':'PASS' if not problems else 'FAIL','saved_episodes':len(rows),
        'scores_equal':passed,'differences':problems,'network_calls':0,
        'scope':'Reconstructed observations, actions, state and original scores. Pending remains pending; no resampling.'},indent=2))
    return 0 if not problems else 1


if __name__=='__main__':raise SystemExit(main())
