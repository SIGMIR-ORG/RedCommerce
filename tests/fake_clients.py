"""Deterministic client fixtures. No network or environment-variable access."""
import json
import subprocess
import sys
from redcommerce.engine import offline_program

class Client:
    is_simulated=True
    model='test-fixture'
    reserve_usd=.05
    def __init__(self,config):
        self.config=config
        self.model=config.get('model',self.model)
        self.requests=[]
    def __call__(self,request):
        self.requests.append(request)
        if request['role_kind']=='counterparty':
            body=json.loads(request['messages'][1]['content'])
            if self.config.get('mode')=='abstain':
                actions=[]
            elif self.config.get('mode')=='format_error':
                return {'actions':None,'parse_status':'model_format_error','usage':{'input_tokens':10,'output_tokens':2,'total_tokens':12},'cost_usd':.01,'raw':{}}
            else:
                actions=[{'tool':body['action_schema']['tool'],'arguments':{'writes':[]}}]
        else:
            body=json.loads(request['messages'][1]['content'])
            observation=body['observation']
            program=offline_program(self.config['case_id'],request['role'])
            process=subprocess.run([sys.executable,'-B',str(program)],input=json.dumps(observation).encode(),capture_output=True,check=True)
            actions=json.loads(process.stdout)['actions']
        return {'actions':actions,'parse_status':'parsed' if actions else 'model_abstention','returned_model':self.model,
            'usage':{'input_tokens':10,'output_tokens':2,'total_tokens':12},'cost_usd':.01,'raw':{'fixture':True}}

def factory(config):
    return Client(config)
