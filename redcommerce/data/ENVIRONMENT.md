# Offline environment

- Tested platform: Windows, Python 3.12.14. Python 3.11+ is required by the standard-library interface; other Python versions/platforms were not exercised in this packaging check.
- Required Python modules: standard library only (`json`, `tomllib`, `hashlib`, `pathlib`, `statistics`, `random`, `importlib`, etc.). No pip installation, model download, credentials, Docker or network connection is required for the two public reproduction commands.
- Extract to a short local path if the operating system has a legacy 260-character path limit.
- Run from a fresh extraction, with no project-specific `PYTHONPATH`. Both scripts locate the extracted root from their own path. Use `-B` to avoid adding bytecode files to the manifest-checked tree.
- Task Dockerfiles are retained as task definitions, but container construction and the historical full release gates are outside this compact artifact's reproduction claim.
- UTF-8 source and data. Python 3.11 is the minimum because task manifests use `tomllib`.
