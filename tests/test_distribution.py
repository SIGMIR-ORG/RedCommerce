import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from integrations.export_trajectories import atif, inspect_sample
from redcommerce.cli import code_fingerprint
from redcommerce.engine import DATA

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dataset_installer', ROOT/'scripts/download_dataset.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class DistributionTests(unittest.TestCase):
    def test_verified_directory_rename_retries_transient_windows_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            staging = Path(temp)/'staging'
            staging.mkdir()
            destination = Path(temp)/'installed'
            rename = Path.rename
            calls = []
            def transient(path, target):
                calls.append(path)
                if len(calls) == 1:
                    raise PermissionError('Synthetic transient Windows lock')
                return rename(path, target)
            with patch.object(Path, 'rename', transient), patch.object(installer.time, 'sleep') as delay:
                installer._commit_verified_directory(staging, destination)
            self.assertTrue(destination.is_dir())
            self.assertEqual(len(calls), 2)
            delay.assert_called_once_with(0.25)

    def test_installer_rejects_wrong_archive_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); archive=root/'data.zip'
            with ZipFile(archive,'w') as bundle: bundle.writestr('data.txt','fixture')
            with self.assertRaisesRegex(ValueError,'SHA256 mismatch'):
                installer.install(archive,root/'installed','0'*64)
            self.assertFalse((root/'installed').exists())

    def test_installer_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); archive=root/'data.zip'
            with ZipFile(archive,'w') as bundle: bundle.writestr('../escaped.txt','fixture')
            digest=hashlib.sha256(archive.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'Unsafe'):
                installer.install(archive,root/'installed',digest)
            self.assertFalse((root/'escaped.txt').exists())

    def test_external_data_selection_and_stable_lock_keys(self):
        env=dict(os.environ,REDCOMMERCE_DATA_DIR=str(DATA))
        code='from redcommerce.engine import DATA; from redcommerce.cli import code_fingerprint; import json; print(json.dumps({"path":str(DATA),"keys":list(code_fingerprint())}))'
        output=subprocess.check_output([sys.executable,'-B','-c',code],cwd=ROOT,env=env,text=True,encoding='utf-8')
        result=json.loads(output)
        self.assertEqual(Path(result['path']),DATA)
        self.assertEqual(set(result['keys']),set(code_fingerprint()))
        self.assertIn('data/FILES.json',result['keys'])

    def test_saved_trace_bridges_keep_separate_roles(self):
        trace={'meta':{'id':'fixture','model':'recorded'},'task':{'instruction':'Synthetic task'},
               'outcome_record':{'eligible':False,'attack_success':None},'provenance':[],
               'requests':[{'role':'merchant','role_kind':'counterparty',
                            'request':{'messages':[{'role':'user','content':'Saved input'}]},
                            'decision':{'model_id':'recorded-model','raw_response':{'actions':[]}}}]}
        result=atif(trace)
        self.assertEqual(result['schema_version'],'ATIF-v1.7')
        self.assertEqual(result['steps'][0]['source'],'user')
        child=result['subagent_trajectories'][0]
        self.assertEqual(child['extra']['role_kind'],'counterparty')
        self.assertEqual([s['step_id'] for s in child['steps']],[1,2])
        self.assertEqual(json.loads(child['steps'][-1]['message']),{'actions':[]})
        self.assertIsNone(result['extra']['outcome_record']['attack_success'])
        sample=inspect_sample(trace,'fixture.json')
        self.assertEqual(sample['metadata']['trajectory_file'],'fixture.json')
        self.assertEqual(sample['target'],'')


if __name__=='__main__': unittest.main()
