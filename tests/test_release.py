import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from redcommerce.clients import NativeClient,ModelPolicy,NotDispatched,parse_envelope,usage_cost
from redcommerce.cli import validate_config
from redcommerce.engine import DATA,offline_episode,read,runtime,scored_outcome,worlds
from fake_clients import Client

CASE='RC-T21-GTIN-SCOPE-002'

class ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modules=runtime()
    def profile(self,case=CASE):
        row=worlds(case=case,panel='cases')[0]
        return row,read(DATA/'configs'/row['profile'])
    def request(self):
        return {'model':'fixture','role':'buyer','role_kind':'business','messages':[{'role':'system','content':'Use declared actions.'},{'role':'user','content':'{}'}],
            'response_contract':{'type':'object','required':['actions'],'additionalProperties':False,'properties':{
                'actions':{'type':'array','maxItems':1,'items':{'type':'object','required':['tool','arguments'],'properties':{'tool':{'const':'escalate_for_review'},'arguments':{'type':'object'}},'additionalProperties':False}}}}}
    def native(self,backend='chat-completions'):
        return NativeClient({'backend':backend,'model':'fixture','endpoint':'https://example.invalid/api',
            'api_key_env':'REDCOMMERCE_TEST_KEY','reserve_usd':1,'max_output_tokens':64000,
            'prices_per_million':{'input':1,'output':2,'cache_read':.1,'cache_write':1.25}})
    def test_inventory_and_panel(self):
        self.assertEqual(len(worlds()),829)
        self.assertEqual(len(worlds(panel='cases')),96)
        self.assertEqual(len({r['case_id'] for r in worlds()}),96)
    def test_unknown_world_rejected(self):
        with self.assertRaises(ValueError):worlds(world='not-a-world')
    def test_valid_and_empty_envelopes(self):
        request=self.request()
        self.assertEqual(parse_envelope({'actions':[]},request),([],'model_abstention'))
        self.assertEqual(parse_envelope({'actions':[{'tool':'escalate_for_review','arguments':{}}]},request)[1],'parsed')
    def test_bad_envelopes_are_not_abstention(self):
        for value in ('{"actions":','{"actions":[],"actions":[]}','{"actions":[]} extra',{'actions':None},{'actions':[{'tool':'not-declared','arguments':{}}]}):
            with self.subTest(value=value):self.assertEqual(parse_envelope(value,self.request())[1],'model_format_error')
    def test_lossless_native_string(self):
        self.assertEqual(parse_envelope('{"actions":"[]</invoke>"}',self.request()),([],'model_abstention'))
    def test_native_payloads_preserve_observation(self):
        for backend in ('chat-completions','anthropic'):
            request=self.request();original=copy.deepcopy(request)
            payload=self.native(backend).payload(request)
            self.assertEqual(request,original)
            self.assertEqual(payload['model'],'fixture')
            self.assertEqual(payload['tool_choice'],{'type':'auto'} if backend=='anthropic' else 'auto')
    def test_chat_has_no_implicit_token_limit(self):
        client=self.native();client.config.pop('max_output_tokens')
        self.assertNotIn('max_tokens',client.payload(self.request()))
    def test_missing_credential_does_not_dispatch(self):
        with patch.dict(os.environ,{},clear=True),patch('urllib.request.urlopen') as wire:
            with self.assertRaises(NotDispatched):self.native()(self.request())
            wire.assert_not_called()
    def test_price_template_cannot_dispatch(self):
        config=read(Path(__file__).resolve().parents[1]/'examples/models.template.json')
        with self.assertRaises(ValueError):validate_config(config)
    def test_usage_cache_arithmetic(self):
        usage,cost=usage_cost({'usage':{'prompt_tokens':1000,'completion_tokens':100,'prompt_tokens_details':{'cached_tokens':200}}},self.native().config)
        self.assertEqual(usage['total_tokens'],1100)
        self.assertAlmostEqual(cost,.00102)
        usage,cost=usage_cost({'usage':{'input_tokens':800,'output_tokens':100,'cache_read_input_tokens':200,'cache_creation_input_tokens':100}},self.native('anthropic').config)
        self.assertEqual(usage['total_tokens'],1200)
        self.assertAlmostEqual(cost,.001145)
    def test_unknown_usage_and_invalid_prices(self):
        with self.assertRaises(RuntimeError):usage_cost({},self.native().config)
        with self.assertRaises(RuntimeError):usage_cost({'usage':{'prompt_tokens':1,'completion_tokens':-1}},self.native().config)
    def test_offline_episode_uses_original_scorer(self):
        with tempfile.TemporaryDirectory() as temp:
            record=offline_episode(self.profile()[0],Path(temp)/'job')
            self.assertTrue(record['score']['replay_ok'])
            self.assertTrue(record['score']['score_eligible'])
            self.assertFalse(record['model_participation'])
    def test_unicode_cart_offline_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            row=worlds(case='RC-T51-CART-SEMANTICS-002',panel='cases')[0]
            record=offline_episode(row,Path(temp)/'job')
            self.assertNotEqual(record['terminal'],'protocol_failure')
            self.assertTrue(record['score']['replay_ok'])
    def test_lawful_demo_keeps_original_world(self):
        with tempfile.TemporaryDirectory() as temp:
            record=offline_episode(self.profile()[0],Path(temp)/'job',submission='unchanged')
            self.assertEqual(record['terminal'],'committed')
            self.assertFalse(record['score']['target_deviation_observed'])
    def test_two_roles_with_shared_ledger(self):
        row,profile=self.profile()
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)
            ledger=self.modules['provider'].PersistentLedger(directory/'ledger.jsonl',total_cap_usd=1)
            attack_client=Client({'model':'attack-fixture'})
            business_client=Client({'model':'business-fixture','case_id':CASE})
            kwargs={'ledger':ledger,'profile':profile,'out':directory/'requests','modules':self.modules}
            attack=ModelPolicy(client=attack_client,role=profile['counterparty']['name'],kind='counterparty',**kwargs)
            business=ModelPolicy(client=business_client,role=profile['business_role']['name'],kind='business',**kwargs)
            episode=self.modules['scheduler'].run_episode(profile,row['world_id'],business,attack,arm='adversarial',out_dir=directory/'episode',route_id=row['route_id'])
            self.assertEqual(len(attack_client.requests),1)
            self.assertGreaterEqual(len(business_client.requests),1)
            request=attack_client.requests[0]
            text=json.dumps(request)
            self.assertIn(profile['arms']['adversarial']['business_objective'],request['messages'][0]['content'])
            self.assertNotIn('private_ground_truth',text)
            self.assertNotIn('candidate_source_variants',text)
            self.assertEqual(request['role_kind'],'counterparty')
            self.assertEqual(business_client.requests[0]['role_kind'],'business')
            score=self.modules['scorer'].score_migration(profile,directory/'episode')
            self.assertTrue(score['score_eligible'])
            self.assertEqual(ledger.summary()['open_reservations'],0)
            self.assertAlmostEqual(ledger.committed_usd(),.01*(len(attack_client.requests)+len(business_client.requests)))
    def test_attacker_abstention_retains_denominator(self):
        row,profile=self.profile()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);ledger=self.modules['provider'].PersistentLedger(root/'costs.jsonl',total_cap_usd=1)
            client=Client({'model':'fixture','mode':'abstain'})
            attack=ModelPolicy(client=client,ledger=ledger,profile=profile,role=profile['counterparty']['name'],kind='counterparty',out=root/'requests',modules=self.modules)
            episode=self.modules['scheduler'].run_episode(profile,row['world_id'],lambda obs:None,attack,arm='adversarial',out_dir=root/'episode')
            score=scored_outcome(self.modules['scorer'].score_migration(profile,root/'episode'),episode)
            self.assertTrue(score['attack_denominator_eligible'])
            self.assertIs(score['attack_success'],False)
    def test_missing_dispatch_releases_reservation(self):
        row,profile=self.profile()
        class Absent(Client):
            def __call__(self,request):raise NotDispatched('fixture did not send')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);ledger=self.modules['provider'].PersistentLedger(root/'costs.jsonl',total_cap_usd=1)
            policy=ModelPolicy(client=Absent({}),ledger=ledger,profile=profile,role=profile['counterparty']['name'],kind='counterparty',out=root/'requests',modules=self.modules)
            observation={'role':profile['counterparty']['name'],'role_description':profile['counterparty']['role_description'],
                'arm_objective':profile['arms']['adversarial']['business_objective'],'task_brief':profile['counterparty']['task_brief'],
                'action_schema':profile['counterparty']['action_schema'],'writable_surface':profile['surface_allowlist'],'readable':{},'trigger':{}}
            with self.assertRaises(self.modules['backend'].BudgetStop):policy(observation)
            self.assertEqual(ledger.summary()['released'],1)
            self.assertEqual(ledger.committed_usd(),0)
    def test_unknown_dispatch_survives_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'costs.jsonl'
            ledger=self.modules['provider'].PersistentLedger(path,total_cap_usd=1)
            rid=ledger.reserve(role='business',reserved_usd=.5,detail={})
            ledger.mark_unknown_outcome(rid,reason='fixture timeout',raw_reference='fixture')
            restarted=self.modules['provider'].PersistentLedger(path,total_cap_usd=1)
            self.assertEqual(restarted.committed_usd(),.5)
            with self.assertRaises(self.modules['backend'].BudgetStop):restarted.reserve(role='business',reserved_usd=.1,detail={})
    def test_cap_stops_before_client(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger=self.modules['provider'].PersistentLedger(Path(temp)/'costs.jsonl',total_cap_usd=.01)
            with self.assertRaises(self.modules['backend'].BudgetStop):ledger.reserve(role='business',reserved_usd=.05,detail={})
            self.assertEqual(ledger.summary()['requests'],0)

    def test_all_four_role_chains_execute_separate_roles(self):
        chains=[r for r in worlds(panel='cases') if read(DATA/'configs'/r['profile'])['business_role']['agent_mode']!='single']
        self.assertEqual(len(chains),4)
        for row in chains:
            with self.subTest(case=row['case_id']), tempfile.TemporaryDirectory() as temp:
                root=Path(temp);profile=read(DATA/'configs'/row['profile'])
                ledger=self.modules['provider'].PersistentLedger(root/'costs.jsonl',total_cap_usd=1)
                kwargs={'ledger':ledger,'profile':profile,'out':root/'requests','modules':self.modules}
                client=Client({'model':'business-fixture','case_id':row['case_id']})
                roles=profile['business_role']['role_chain']
                policies={role:ModelPolicy(client=client,role=role,kind='business',**kwargs) for role in roles}
                counter=ModelPolicy(client=Client({'model':'attack-fixture'}),role=profile['counterparty']['name'],kind='counterparty',**kwargs)
                episode=self.modules['scheduler'].run_episode(profile,row['world_id'],policies,counter,arm='adversarial',out_dir=root/'episode',route_id=row['route_id'])
                actual=[r['role'] for r in client.requests]
                self.assertEqual(actual,roles,repr({'terminal':episode['terminal'],'failures':episode['protocol_failures'],'decisions':episode['decisions']}))
                self.assertNotEqual(episode['terminal'],'protocol_failure')
                self.assertTrue(self.modules['scorer'].score_migration(profile,root/'episode')['replay_ok'])
                self.assertTrue(episode['decisions'][0]['raw_response']['actions'])

    def test_native_chat_response_and_credential_redaction(self):
        body={'model':'fixture','choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[{'function':{'name':'emit_actions','arguments':'{"actions":[]}'}}]}}],
            'usage':{'prompt_tokens':100,'completion_tokens':20},'note':'fixture-secret'}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return json.dumps(body).encode()
        with patch.dict(os.environ,{'REDCOMMERCE_TEST_KEY':'fixture-secret'}),patch('urllib.request.urlopen',return_value=Response()) as wire:
            reply=self.native()(self.request())
            self.assertEqual(reply['parse_status'],'model_abstention')
            self.assertNotIn('fixture-secret',json.dumps(reply))
            self.assertEqual(wire.call_count,1)
            self.assertAlmostEqual(reply['cost_usd'],.00014)
    def test_native_anthropic_response_and_explicit_provider_block(self):
        body={'model':'fixture','stop_reason':'tool_use','content':[{'type':'tool_use','name':'emit_actions','input':{'actions':[]}}],
            'usage':{'input_tokens':100,'output_tokens':20}}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return json.dumps(body).encode()
        with patch.dict(os.environ,{'REDCOMMERCE_TEST_KEY':'fixture-secret'}),patch('urllib.request.urlopen',return_value=Response()):
            reply=self.native('anthropic')(self.request())
            self.assertEqual(reply['parse_status'],'model_abstention')
            self.assertIsNone(reply['failure'])
            body.update(stop_reason='refusal',stop_details={'type':'refusal'},content=[])
            self.assertEqual(self.native('anthropic')(self.request())['failure'],'provider_access_blocked')
    def test_native_unknown_usage_retains_raw_response(self):
        body={'model':'fixture','choices':[]}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return json.dumps(body).encode()
        with patch.dict(os.environ,{'REDCOMMERCE_TEST_KEY':'fixture-secret'}),patch('urllib.request.urlopen',return_value=Response()):
            with self.assertRaises(RuntimeError) as error:self.native()(self.request())
            self.assertEqual(error.exception.response,body)
    def test_cli_resume_keeps_episode_identity(self):
        from redcommerce.cli import main
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'run'
            args=['run','--case',CASE,'--out',str(out)]
            self.assertEqual(main(args),0)
            job=worlds(case=CASE,panel='cases')[0]
            episode_path=out/'jobs'/job['world_id']/'episode/episode.json'
            saved=episode_path.read_bytes()
            self.assertEqual(main(args),0)
            self.assertEqual(episode_path.read_bytes(),saved)
    def test_cli_recovers_saved_episode_without_resampling(self):
        from redcommerce.cli import main
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'run';args=['run','--case',CASE,'--out',str(out)]
            self.assertEqual(main(args),0)
            job=worlds(case=CASE,panel='cases')[0]
            directory=out/'jobs'/job['world_id'];saved=(directory/'episode/episode.json').read_bytes()
            (directory/'result.json').unlink()
            self.assertEqual(main(args),0)
            self.assertEqual((directory/'episode/episode.json').read_bytes(),saved)
            self.assertTrue(read(directory/'result.json')['recovered_saved_episode'])
    def test_nonfinite_budget_cannot_dispatch(self):
        from redcommerce.cli import main
        from redcommerce.engine import write
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);config=root/'models.json'
            role={'backend':'plugin','factory':'fake_clients:factory','model':'fixture','reserve_usd':.05}
            write(config,{'attacker':role,'business':role})
            with patch('redcommerce.clients.make_client') as factory:
                self.assertEqual(main(['run','--case',CASE,'--config',str(config),'--execute','--budget-usd','nan','--out',str(root/'run')]),1)
                factory.assert_not_called()

if __name__=='__main__':unittest.main()
