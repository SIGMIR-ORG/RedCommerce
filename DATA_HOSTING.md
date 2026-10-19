# Code, data and trajectory hosting

The split is **GitHub for code and the static site; a Hugging Face Dataset for frozen task packages, saved research data and trajectories**. The public dataset is [Fentz/RedCommerce](https://huggingface.co/datasets/Fentz/RedCommerce), pinned in `DATA_RELEASE.json` to commit `7e7d73a7a0fc321fb9e946a3d2de8b5f75168ebe`. Existing embedded data is retained as a compatibility fallback; this release does not delete it.

## Dataset contents

- `benchmark-data.zip`: original runtime layout, all 96 tasks / 829 worlds, 3,316 main outcome records and 976 companion trajectories; original frozen SHA256 manifest retained.
- `trajectories/index.json`: every planned main outcome and companion-study record, with evidence availability and original scoring status.
- `trajectories/records/`: per-trial publication JSON, fetched only when a visitor opens a trial.
- `tables/main.jsonl`, `tables/companion.jsonl`, `tables/tasks.jsonl`: small, independently loadable Dataset Viewer configurations.
- `FILES.json`, `RELEASE.json`: checksums, counts, export coverage and redaction totals.

Public trajectory JSON contains saved model inputs, answer/tool content, actions, state witnesses and scores. Raw HTTP headers, account/billing metadata, personal paths, credential patterns and private reasoning blocks are excluded. A metadata-only row does not claim a complete rollout. No original task or score is rewritten, and no model is sampled during export.

## Download and use an external dataset

Pin the Hugging Face dataset **commit**, not a moving `main` revision. The archive SHA256 is recorded in that release's `RELEASE.json`. For a code-only checkout, `python -B scripts/install_ci_data.py` installs the checked-in `DATA_RELEASE.json` automatically without authentication. If embedded data is present, it leaves it unchanged.

```sh
python scripts/download_dataset.py --url "https://huggingface.co/datasets/Fentz/RedCommerce/resolve/7e7d73a7a0fc321fb9e946a3d2de8b5f75168ebe/benchmark-data.zip" --sha256 70405f65035f02c738750fb5737e41d8c5e581a4ad2f92ed1b9d78a5366468c0 --dest ../redcommerce-data
```

Or download the archive separately and pass `--archive`. The installer verifies the ZIP hash, original 14,983-file manifest and added ledger module, rejects path traversal and refuses to overwrite an existing directory.

PowerShell:

```powershell
$env:REDCOMMERCE_DATA_DIR = (Resolve-Path ../redcommerce-data).Path
python -B -m redcommerce list
python -B -m redcommerce reproduce
python -B -m redcommerce replay
```

Linux/macOS:

```sh
export REDCOMMERCE_DATA_DIR="$(realpath ../redcommerce-data)"
python -B -m redcommerce list
```

## Connect the website

In `docs/site-config.js`, set:

```javascript
trajectoryDataBase: 'https://huggingface.co/datasets/Fentz/RedCommerce/resolve/7e7d73a7a0fc321fb9e946a3d2de8b5f75168ebe/trajectories/'
```

The browser reads `index.json` and downloads a single detail file on demand, verifying its SHA256 against the index. No API key belongs in browser code. A public dataset is needed for anonymous visitors. The existing benchmark landing page does not depend on the new dataset being online.

## Complete migration only after publication

1. Record the author-approved code/data licenses; no license is currently specified.
2. The prepared dataset has been uploaded; its immutable commit is recorded above.
3. Test downloads and anonymous website loading against that commit.
4. CI installs the pinned dataset when embedded data is absent. Optional `REDCOMMERCE_DATA_URL` / `REDCOMMERCE_DATA_SHA256` variables can override the default as a pair.
5. In a separate commit, stop tracking the embedded `redcommerce/data` directory. Do not rewrite existing repository history or delete local source evidence as part of this change.

Until the migration passes cloud checks, the current GitHub dataset remains a compatibility fallback. Publishing files without a specified license does not grant general reuse rights.
