"""Content identity for new runs; never sent to the evaluated agent."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]

def task_provenance(bundle):
    paths = [p for p in bundle.root.rglob("*") if p.is_file()
             and "__pycache__" not in p.parts
             and (p.suffix in {".py", ".json", ".toml", ".md"} or p.name == "Dockerfile")]
    paths += list((PROJECT / "redcommerce_v3").glob("*.py"))
    paths.append(PROJECT / "agents" / "noop.py")
    hashes = {p.relative_to(PROJECT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(set(paths))}
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"task_version": bundle.raw["task"]["version"], "source_sha256": digest,
            "files": hashes}
