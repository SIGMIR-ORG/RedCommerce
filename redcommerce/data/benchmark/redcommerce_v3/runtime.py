from __future__ import annotations

import json
import hashlib
import importlib.util
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from .schema import TaskBundle, deep_merge, stable_run_id
from .provenance import task_provenance


@dataclass(frozen=True)
class RunResult:
    run_id: str
    run_dir: Path
    final_state: dict[str, Any]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_driver(bundle: TaskBundle) -> ModuleType:
    relative = str(bundle.raw["environment"].get("driver", "environment/driver.py"))
    path = (bundle.root / relative).resolve()
    module_name = "redcommerce_task_driver_" + bundle.case_id.replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load task driver: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_agent(command: list[str], observation: dict[str, Any], *, timeout_sec: int,
               workspace: Path) -> dict[str, Any]:
    workspace.mkdir(parents=True, exist_ok=True)
    # Keep the agent environment intentionally narrow, but retain the Windows
    # process variables required by Python's socket/Winsock initialization.
    # No credentials, API keys, or benchmark paths are forwarded.
    passthrough = (
        "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP",
        "LANG", "NO_PROXY",
    )
    env = {key: os.environ[key] for key in passthrough if key in os.environ}
    env.update({"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    try:
        completed = subprocess.run(
            command,
            input=json.dumps(observation, ensure_ascii=False),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_sec,
            cwd=workspace,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "actions": [],
            "agent_error": {
                "kind": "timeout",
                "timeout_sec": timeout_sec,
                "stdout": str(exc.stdout or "")[-2000:],
                "stderr": str(exc.stderr or "")[-2000:],
            },
        }
    if completed.returncode != 0:
        return {
            "actions": [],
            "agent_error": {
                "kind": "nonzero_exit",
                "returncode": completed.returncode,
                "stderr": completed.stderr[-2000:],
            },
        }
    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {
            "actions": [],
            "agent_error": {
                "kind": "invalid_json",
                "detail": str(exc),
                "stdout": completed.stdout[-2000:],
            },
        }
    if not isinstance(response, dict) or not isinstance(response.get("actions"), list):
        return {"actions": [], "agent_error": {"kind": "invalid_response_schema"}}
    return response


def run_local_task(bundle: TaskBundle, variant_id: str,
                   agent_command: list[str] | dict[str, list[str]], *,
                   agent_id: str, output_root: str | Path, intervention: str = "none",
                   control_layer: str = "none",
                   seed: int = 0, repeat_index: int = 0,
                   runtime_mode: str = "local-process",
                   agent_timeout_sec: int | None = None,
                   run_metadata: dict[str, Any] | None = None,
                   condition_fingerprint: str = "") -> RunResult:
    if variant_id not in bundle.variants:
        raise KeyError(f"unknown variant_id={variant_id}")
    if not isinstance(intervention, str) or not intervention:
        raise ValueError("intervention must be a non-empty string")
    if not isinstance(control_layer, str) or not control_layer:
        raise ValueError("control_layer must be a non-empty string")
    if runtime_mode not in {"local-process", "container-agent-process"}:
        raise ValueError(f"unsupported runtime_mode={runtime_mode}")
    if run_metadata is not None and not isinstance(run_metadata, dict):
        raise TypeError("run_metadata must be a mapping or None")
    variant = bundle.variants[variant_id]
    effective_agent_timeout_sec = (
        int(agent_timeout_sec) if agent_timeout_sec is not None
        else int(bundle.raw["agent"]["timeout_sec"]))
    if effective_agent_timeout_sec < 1:
        raise ValueError("agent_timeout_sec must be >= 1")
    world = deep_merge(bundle.base_world, variant.world_patch)
    driver = _load_driver(bundle)
    if intervention != "none":
        apply_intervention = getattr(driver, "apply_intervention", None)
        if not callable(apply_intervention):
            raise ValueError(
                f"{bundle.case_id} does not implement intervention={intervention}")
        world = apply_intervention(world, intervention=intervention, seed=seed)
        if not isinstance(world, dict):
            raise TypeError("task driver apply_intervention must return a mapping")
    if control_layer != "none":
        configure_control_layer = getattr(driver, "configure_control_layer", None)
        if not callable(configure_control_layer):
            raise ValueError(
                f"{bundle.case_id} does not implement control_layer={control_layer}")
        world = configure_control_layer(
            world, control_layer=control_layer, seed=seed)
        if not isinstance(world, dict):
            raise TypeError("task driver configure_control_layer must return a mapping")
    source_provenance = task_provenance(bundle)
    effective_fingerprint = hashlib.sha256(json.dumps(
        [condition_fingerprint, source_provenance["source_sha256"]]).encode()).hexdigest()
    run_id = stable_run_id(
        bundle.case_id, variant_id, agent_id, intervention=intervention,
        control_layer=control_layer, seed=seed, repeat_index=repeat_index,
        condition_fingerprint=effective_fingerprint,
    )
    run_dir = Path(output_root).resolve() / run_id
    if run_dir.exists():
        raise FileExistsError(f"run directory already exists: {run_dir}")
    for relative in ("agent", "state", "verifier"):
        (run_dir / relative).mkdir(parents=True, exist_ok=False)
    agent_mode = bundle.raw["agent"].get("mode", "single")
    roles: list[str] = []
    if agent_mode == "single":
        if not isinstance(agent_command, list):
            raise TypeError("single-agent task requires one command")
        for name in ("build_observation", "execute_actions"):
            if not callable(getattr(driver, name, None)):
                raise TypeError(f"single-agent task driver missing callable {name}")
        observation = driver.build_observation(world, bundle.instruction)
        if not isinstance(observation, dict):
            raise TypeError("task driver build_observation must return a mapping")
        _write_json(run_dir / "agent" / "observation.json", observation)
        response = _run_agent(
            agent_command,
            observation,
            timeout_sec=effective_agent_timeout_sec,
            workspace=run_dir / "agent" / "workspace",
        )
        _write_json(run_dir / "agent" / "response.json", response)
        final_state, events = driver.execute_actions(
            world, response, intervention=intervention, seed=seed)
    elif agent_mode == "multi-agent-sequential":
        roles = [str(role) for role in bundle.raw["agent"].get("roles", [])]
        if not roles or not isinstance(agent_command, dict) or set(agent_command) != set(roles):
            raise TypeError("multi-agent task requires one command for every declared role")
        required = ("initialize_state", "build_role_observation", "apply_role_response")
        if any(not callable(getattr(driver, name, None)) for name in required):
            raise TypeError(f"multi-agent task driver must implement {required}")
        state = driver.initialize_state(world)
        events = []
        for role_index, role in enumerate(roles):
            observation = driver.build_role_observation(
                world, state, bundle.instruction, role)
            if not isinstance(observation, dict):
                raise TypeError(f"{role}: observation must be a mapping")
            role_dir = run_dir / "agent" / role
            _write_json(role_dir / "observation.json", observation)
            response = _run_agent(
                agent_command[role], observation,
                timeout_sec=effective_agent_timeout_sec,
                workspace=role_dir / "workspace",
            )
            _write_json(role_dir / "response.json", response)
            state, role_events = driver.apply_role_response(
                world, state, role, response, intervention=intervention, seed=seed)
            for event_index, event in enumerate(role_events):
                event = dict(event)
                event.setdefault("sequence", role_index + (event_index + 1) / 10)
                event["agent_role"] = role
                events.append(event)
        finalize = getattr(driver, "finalize_state", None)
        final_state = finalize(world, state) if callable(finalize) else state
    else:
        raise ValueError(f"unsupported agent.mode={agent_mode}")
    if not isinstance(final_state, dict) or not isinstance(events, list):
        raise TypeError("task driver must produce (mapping, list)")
    _write_json(run_dir / "state" / "initial_world.json", world)
    _write_json(run_dir / "state" / "final_state.json", final_state)
    (run_dir / "state" / "events.jsonl").write_text(
        "".join(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )
    _write_json(run_dir / "manifest.json", {
        "schema_version": "0.2",
        "run_id": run_id,
        "case_id": bundle.case_id,
        "variant_id": variant_id,
        "agent_id": agent_id,
        "intervention": intervention,
        "control_layer": control_layer,
        "seed": seed,
        "repeat_index": repeat_index,
        "runtime_mode": runtime_mode,
        "agent_timeout_sec": effective_agent_timeout_sec,
        "agent_mode": agent_mode,
        "agent_roles": roles,
        "variant_analysis": {
            "analysis_role": variant.analysis_role,
            "paired_with": variant.paired_with,
            "pair_design": variant.pair_design,
            "controlled_axes": variant.controlled_axes,
            "completion_intervention": variant.completion_intervention,
        },
        "run_metadata": run_metadata or {},
        "source_provenance": source_provenance,
        "condition_fingerprint": effective_fingerprint,
    })
    return RunResult(run_id, run_dir, final_state)


def python_command(script: Path) -> list[str]:
    return [sys.executable, str(script.resolve())]
