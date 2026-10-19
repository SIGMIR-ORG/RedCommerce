"""Install an explicitly selected public dataset ZIP after SHA256 verification."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import urlopen, Request
from zipfile import ZipFile

MANIFEST_SHA256 = '0d8ffb47b70ba444c4d512b6aef46bb8915b8ad6996ea46f1b3d95fa0b424a69'
PROVIDER_SHA256 = 'f795ee99a458600491a60893818709544465c34e8921d622b1242e8859375c7b'


def _commit_verified_directory(staging, destination):
    # Windows indexing / antivirus can briefly retain handles after extraction.
    # Retry only the atomic rename; never overwrite or partially copy a target.
    for attempt in range(8):
        try:
            staging.rename(destination)
            return
        except PermissionError:
            if destination.exists() or attempt == 7:
                raise
            time.sleep(0.25 * (attempt + 1))


def install(archive, destination, expected):
    if not re.fullmatch(r'[0-9a-f]{64}', expected):
        raise ValueError('A pinned lowercase SHA256 is required')
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('Destination already exists; choose a new directory. Existing data will not be overwritten.')
    if hashlib.sha256(Path(archive).read_bytes()).hexdigest() != expected:
        raise ValueError('Archive SHA256 mismatch; no dataset installed')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='rc-install-') as temporary:
        staging = Path(temporary) / 'data'
        staging.mkdir()
        with ZipFile(archive) as bundle:
            size = 0
            for info in bundle.infolist():
                parts = Path(info.filename.replace('\\','/')).parts
                if info.filename.startswith(('/', '\\')) or '..' in parts or ':' in info.filename or stat.S_ISLNK(info.external_attr >> 16):
                    raise ValueError('Unsafe dataset archive member')
                size += info.file_size
            if size > 2_000_000_000:
                raise ValueError('Archive exceeds the supported dataset size')
            bundle.extractall(staging)
        manifest = staging / 'FILES.json'
        if hashlib.sha256(manifest.read_bytes()).hexdigest() != MANIFEST_SHA256:
            raise ValueError('Unexpected dataset version')
        for name, digest in json.loads(manifest.read_text('utf-8')).items():
            if hashlib.sha256((staging / name).read_bytes()).hexdigest() != digest:
                raise ValueError('Dataset byte mismatch: ' + name)
        provider = staging / 'benchmark/parallel/20260913-live-migration/provider.py'
        if hashlib.sha256(provider.read_bytes()).hexdigest() != PROVIDER_SHA256:
            raise ValueError('Persistent-ledger module mismatch')
        _commit_verified_directory(staging, destination)
    return destination


def main():
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--url', help='Pinned HTTPS Hugging Face dataset resolve URL')
    source.add_argument('--archive', type=Path, help='Previously downloaded local ZIP')
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--dest', type=Path, required=True)
    args = parser.parse_args()
    if args.url:
        url = urlsplit(args.url)
        if url.scheme != 'https' or url.hostname != 'huggingface.co' or url.username or url.password or url.query or '/resolve/' not in url.path:
            raise ValueError('Use a public HTTPS huggingface.co dataset resolve URL, without credentials or query parameters')
        with tempfile.TemporaryDirectory(prefix='rc-download-') as directory:
            archive = Path(directory) / 'benchmark-data.zip'
            with urlopen(Request(args.url, headers={'User-Agent':'RedCommerce-dataset-loader/1'}), timeout=120) as response, archive.open('wb') as output:
                shutil.copyfileobj(response, output)
            installed = install(archive, args.dest, args.sha256)
    else:
        installed = install(args.archive, args.dest, args.sha256)
    print('Verified dataset installed at: ' + str(installed))
    print('Set REDCOMMERCE_DATA_DIR to this directory before using the CLI.')


if __name__ == '__main__':
    main()
