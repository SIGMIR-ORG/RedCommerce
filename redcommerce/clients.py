"""Provider adapters. Credentials are loaded only immediately before dispatch."""
from __future__ import annotations
import copy
import importlib
import json
import math
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

class ClientError(RuntimeError):
    def __init__(self,message,response=None):
        super().__init__(message)
        self.response=response

class NotDispatched(ClientError):
    pass

def strict_json(text):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key]=value
        return result
    def constant(value):
        raise ValueError('non-finite JSON value')
    return json.loads(text,object_pairs_hook=pairs,parse_constant=constant)

def standard_schema(value):
    if not isinstance(value,dict):
        return copy.deepcopy(value)
    result=copy.deepcopy(value)
    nullable=result.pop('nullable',False)
    for key in ('properties',):
        if key in result:
            result[key]={k:standard_schema(v) for k,v in result[key].items()}
    if isinstance(result.get('items'),dict):
        result['items']=standard_schema(result['items'])
    for key in ('oneOf','anyOf'):
        if key in result:
            result[key]=[standard_schema(v) for v in result[key]]
    return {'anyOf':[result,{'type':'null'}]} if nullable else result

def normalize_request(request):
    result=copy.deepcopy(request)
    schema=result['response_contract']
    schema.setdefault('properties',{}).setdefault('actions',{}).update(minItems=0,maxItems=1)
    if result['role_kind']=='counterparty':
        body=json.loads(result['messages'][1]['content'])
        options=[{'type':'object','required':['path','value'],'properties':{
            'path':{'const':surface['path']},'value':standard_schema(surface['schema'])},
            'additionalProperties':False} for surface in body['writable_surface']]
        tool=body['action_schema']['tool']
        schema['properties']['actions']['items']={'type':'object','required':['tool','arguments'],
            'properties':{'tool':{'const':tool},'arguments':{'type':'object','required':['writes'],
            'properties':{'writes':{'type':'array','items':{'oneOf':options}}},'additionalProperties':False}},
            'additionalProperties':False}
    schema['additionalProperties']=False
    return result

def valid_schema(value,schema):
    if 'const' in schema and value!=schema['const']:
        return False
    if 'enum' in schema and value not in schema['enum']:
        return False
    if 'oneOf' in schema and sum(valid_schema(value,s) for s in schema['oneOf'])!=1:
        return False
    if 'anyOf' in schema and not any(valid_schema(value,s) for s in schema['anyOf']):
        return False
    kind=schema.get('type')
    types={'object':dict,'array':list,'string':str,'integer':int,'number':(int,float),'boolean':bool,'null':type(None)}
    if kind in types and not isinstance(value,types[kind]):
        return False
    if kind in ('number','integer') and (isinstance(value,bool) or not math.isfinite(value)):
        return False
    if isinstance(value,dict):
        if any(k not in value for k in schema.get('required',[])):
            return False
        properties=schema.get('properties',{})
        if schema.get('additionalProperties') is False and any(k not in properties for k in value):
            return False
        if any(not valid_schema(v,properties[k]) for k,v in value.items() if k in properties):
            return False
    if isinstance(value,list):
        if len(value)<schema.get('minItems',0) or len(value)>schema.get('maxItems',len(value)):
            return False
        if 'items' in schema and any(not valid_schema(v,schema['items']) for v in value):
            return False
    return True

def parse_envelope(value,request):
    try:
        if isinstance(value,str):
            value=re.sub(r'\s*</invoke>\s*$','',value)
            fence=re.fullmatch(r'\s*```(?:json)?\s*\n([\s\S]*?)\n```\s*',value)
            value=strict_json(fence.group(1) if fence else value)
        if isinstance(value,dict) and isinstance(value.get('actions'),str):
            value=copy.deepcopy(value)
            value['actions']=strict_json(re.sub(r'\s*</invoke>\s*$','',value['actions']))
        if not isinstance(value,dict) or not isinstance(value.get('actions'),list):
            raise ValueError('missing action envelope')
        if not valid_schema(value,request['response_contract']):
            raise ValueError('action does not match the declared schema')
        return value['actions'],'parsed' if value['actions'] else 'model_abstention'
    except (ValueError,TypeError,KeyError):
        return [],'model_format_error'

def usage_cost(body,config):
    usage=body.get('usage')
    if not isinstance(usage,dict):
        raise ClientError('provider usage unavailable')
    if config['backend']=='anthropic':
        values={k:usage.get(k,0) for k in ('input_tokens','output_tokens','cache_read_input_tokens','cache_creation_input_tokens')}
        if 'input_tokens' not in usage or 'output_tokens' not in usage:
            raise ClientError('provider usage unavailable')
        categories={'input':values['input_tokens'],'output':values['output_tokens'],
            'cache_read':values['cache_read_input_tokens'],'cache_write':values['cache_creation_input_tokens']}
    else:
        if 'prompt_tokens' not in usage or 'completion_tokens' not in usage:
            raise ClientError('provider usage unavailable')
        cached=(usage.get('prompt_tokens_details') or {}).get('cached_tokens',usage.get('prompt_cache_hit_tokens',0))
        if type(cached) is not int or cached<0 or type(usage['prompt_tokens']) is not int or cached>usage['prompt_tokens']:
            raise ClientError('invalid cached usage')
        categories={'input':usage['prompt_tokens']-cached,'cache_read':cached,'output':usage['completion_tokens']}
    if any(type(v) is not int or v<0 for v in categories.values()):
        raise ClientError('invalid token usage')
    prices=config.get('prices_per_million') or {}
    cost=0.0
    for category,count in categories.items():
        if not count:
            continue
        rate=prices.get(category)
        if type(rate) not in (int,float) or not math.isfinite(rate) or rate<0:
            raise ClientError(f'Missing valid configured price for {category}')
        cost += count*rate/1_000_000
    return {'input_tokens':sum(v for k,v in categories.items() if k!='output'),
        'output_tokens':categories['output'],'total_tokens':sum(categories.values()),
        'provider_usage':usage},cost

class NativeClient:
    is_simulated=False
    def __init__(self,config):
        self.config=copy.deepcopy(config)
        self.model=config['model']
        if config['backend'] not in ('chat-completions','anthropic'):
            raise ValueError('Unknown native backend')
        self.reserve_usd=float(config['reserve_usd'])
        if not math.isfinite(self.reserve_usd) or self.reserve_usd<=0:
            raise ValueError('A positive per-request reservation is required')
        if not str(config['endpoint']).startswith('https://'):
            raise ValueError('Native endpoint must use HTTPS')
        self.timeout=float(config.get('timeout_seconds',180))

    def payload(self,request):
        messages=copy.deepcopy(request['messages'])
        contract=copy.deepcopy(request['response_contract'])
        suffix='Return zero or one available action using the supplied schema. Empty actions records abstention. Do not invent tools or arguments.'
        if self.config['backend']=='anthropic':
            maximum=self.config.get('max_output_tokens')
            if type(maximum) is not int or maximum<=0:
                raise NotDispatched('Anthropic requires an explicit positive max_output_tokens in the model config')
            system='\n\n'.join(m['content'] for m in messages if m['role'] in ('system','developer'))+'\n'+suffix
            value={'model':self.model,'system':system,'messages':[m for m in messages if m['role'] not in ('system','developer')],
                'max_tokens':maximum,'stream':False,'tool_choice':{'type':'auto'},
                'tools':[{'name':'emit_actions','description':'Submit the role decision, including an empty actions array for abstention.','input_schema':contract}]}
        else:
            messages[0]['content']+='\n'+suffix
            value={'model':self.model,'messages':messages,'stream':False,
                'tools':[{'type':'function','function':{'name':'emit_actions','description':'Submit the role decision, including an empty actions array for abstention.','parameters':contract}}],
                'tool_choice':'auto'}
            if self.config.get('max_output_tokens') is not None:
                value['max_tokens']=self.config['max_output_tokens']
        extras=self.config.get('parameters') or {}
        protected={'model','messages','system','tools','tool_choice','stream','max_tokens','max_completion_tokens'}
        if any(k in protected for k in extras):
            raise NotDispatched('parameters cannot override identity, prompts, tools, or output limit')
        value.update(copy.deepcopy(extras))
        return value

    def __call__(self,request):
        payload=self.payload(request)
        variable=self.config['api_key_env']
        key=os.environ.get(variable)
        if not key:
            raise NotDispatched(f'Environment variable {variable} is not set')
        headers={'Content-Type':'application/json'}
        if self.config['backend']=='anthropic':
            headers.update({'x-api-key':key,'anthropic-version':'2023-06-01'})
        else:
            headers['Authorization']='Bearer '+key
        wire=urllib.request.Request(self.config['endpoint'],data=json.dumps(payload,allow_nan=False).encode(),headers=headers,method='POST')
        try:
            with urllib.request.urlopen(wire,timeout=self.timeout) as response:
                raw=response.read(8_000_001)
        except urllib.error.HTTPError as error:
            # No automatic replay. The reservation remains until actual usage is known.
            raise ClientError(f'provider_http_{error.code}') from None
        except Exception as error:
            raise ClientError(f'transport_{type(error).__name__}') from None
        if len(raw)>8_000_000:
            raise ClientError('provider response exceeded the byte limit')
        body=strict_json(raw.decode('utf-8').replace(key,'[REDACTED]'))
        try:
            usage,cost=usage_cost(body,self.config)
        except ClientError as error:
            error.response=body
            raise
        blocked=self.config['backend']=='anthropic' and body.get('stop_reason')=='refusal' and (body.get('stop_details') or {}).get('type')=='refusal'
        failure=None
        returned=body.get('model')
        allowed=self.config.get('allowed_returned_models') or [self.model]
        if returned not in allowed:
            failure='returned_model_mismatch'
        try:
            if self.config['backend']=='anthropic':
                blocks=body.get('content',[])
                calls=[b for b in blocks if b.get('type')=='tool_use']
                if calls:
                    if len(calls)!=1 or calls[0].get('name')!='emit_actions':
                        raise ValueError('ambiguous native tool call')
                    envelope=calls[0]['input']
                elif body.get('stop_reason')=='refusal':
                    envelope={'actions':[]}
                else:
                    envelope=''.join(b.get('text','') for b in blocks if b.get('type')=='text')
                truncated=body.get('stop_reason')=='max_tokens'
            else:
                choice=body['choices'][0]
                if len(body['choices'])!=1:
                    raise ValueError('multiple choices')
                message=choice['message'];calls=message.get('tool_calls') or []
                if calls:
                    if len(calls)!=1 or calls[0]['function']['name']!='emit_actions':
                        raise ValueError('ambiguous native tool call')
                    envelope=calls[0]['function']['arguments']
                elif message.get('refusal'):
                    envelope={'actions':[]}
                else:
                    envelope=message.get('content')
                truncated=choice.get('finish_reason')=='length'
            actions,status=parse_envelope(envelope,request)
            if truncated:
                actions,status=[],'model_format_error'
        except (KeyError,ValueError,TypeError,IndexError):
            actions,status=[], 'model_format_error';truncated=False
        if blocked:
            failure='provider_access_blocked'
        return {'actions':actions,'parse_status':status,'returned_model':returned,'usage':usage,'cost_usd':cost,
            'raw':body,'truncated':truncated,'failure':failure,'cost_basis':'reported usage times user-configured prices',
            'provider_invoice_usd':None}

def make_client(config):
    if config['backend']=='plugin':
        module,attribute=config['factory'].split(':',1)
        return getattr(importlib.import_module(module),attribute)(copy.deepcopy(config))
    return NativeClient(config)

class ModelPolicy:
    owns_cost_ledger=True
    def __init__(self,*,client,ledger,role,kind,profile,out,modules):
        self.client,self.ledger,self.role,self.kind,self.profile,self.out,self.modules=client,ledger,role,kind,profile,Path(out),modules
        self.is_language_model=not bool(getattr(client,'is_simulated',False))
        self.out.mkdir(parents=True,exist_ok=True)

    def describe(self):
        return {'kind':'provider_policy','role':self.role,'role_kind':self.kind,'model':self.client.model,
            'is_language_model':self.is_language_model,'is_simulated':not self.is_language_model,'protocol':'public-model-interface-v1'}

    def __call__(self,observation):
        from .engine import clarify,write
        if any(self.ledger.summary()[k] for k in ('open_reservations','unknown_outcomes','unknown_usage_events','invalid_cost_events','reservation_insufficient_events')):
            raise self.modules['backend'].BudgetStop('unresolved budget ledger')
        value=clarify(self.profile['case_id'],observation) if self.kind=='business' else copy.deepcopy(observation)
        request=normalize_request(self.modules['provider'].render_request(value,role=self.role,role_kind=self.kind))
        if hasattr(self.client,'payload'):
            self.client.payload(request)  # Check configuration before a reservation or credential read.
        rid=self.ledger.reserve(role=self.role,reserved_usd=self.client.reserve_usd,detail={'model':self.client.model,'role_kind':self.kind})
        path=self.out/(rid+'.json')
        write(path,{'request':request,'status':'reserved'})
        try:
            reply=self.client(request)
        except NotDispatched as error:
            self.ledger.release(rid,reason=str(error))
            raise self.modules['backend'].BudgetStop('request was not dispatched') from None
        except Exception as error:
            if getattr(error,'response',None) is not None:
                write(path,{'request':request,'response':error.response,'status':'usage_unresolved'})
            self.ledger.mark_unknown_outcome(rid,reason=type(error).__name__,raw_reference=str(path))
            raise self.modules['backend'].BudgetStop('request outcome unknown; reservation retained') from None
        write(path,{'request':request,'response':reply,'status':'response_received'})
        self.ledger.settle(rid,cost_usd=reply.get('cost_usd'),usage=reply.get('usage'),raw_reference=str(path))
        if reply.get('failure'):
            raise self.modules['backend'].BudgetStop(reply['failure'])
        actions,status=parse_envelope({'actions':reply.get('actions')},request)
        status=reply.get('parse_status',status) if status!='model_format_error' else status
        adapter={'policy_kind':'provider_policy','is_simulated':not self.is_language_model,'cost_known':True,
            'cost_usd':reply['cost_usd'],'tokens':reply['usage']['total_tokens'],'request_id':rid,
            'model':reply.get('returned_model',self.client.model),'parse_status':status}
        if status=='model_format_error' or (self.kind=='counterparty' and status=='model_abstention'):
            adapter['failure']=status
        return {'actions':actions,'_adapter':adapter}
