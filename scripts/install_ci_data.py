"""CI-only optional installation for a code-only checkout; no model API calls."""
import os
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
if not (root/'redcommerce/data/FILES.json').exists():
    url = os.environ.get('REDCOMMERCE_DATA_URL', '')
    digest = os.environ.get('REDCOMMERCE_DATA_SHA256', '')
    if not url and not digest and (root/'DATA_RELEASE.json').exists():
        release = json.loads((root/'DATA_RELEASE.json').read_text('utf-8'))
        url, digest = release['archive_url'], release['archive_sha256']
    if not url or not digest:
        raise SystemExit('Code-only checkout: set the repository REDCOMMERCE_DATA_URL and REDCOMMERCE_DATA_SHA256 Actions variables to the published pinned dataset release.')
    raise SystemExit(subprocess.call([sys.executable,'-B',str(root/'scripts/download_dataset.py'),
                                    '--url',url,'--sha256',digest,'--dest',str(root/'redcommerce/data')]))
