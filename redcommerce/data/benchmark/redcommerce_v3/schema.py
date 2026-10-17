from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ANALYSIS_ROLES = {"benign_control", "primary_attack", "counterfactual_control"}
BENIGN_ANALYSIS_ROLES = {"benign_control", "counterfactual_control"}
PAIR_DESIGNS = {"unpaired", "controlled_contrast", "strict_single_factor"}
MANDATE_STATUSES = {"explicit", "standing-policy", "unspecified"}
WITNESS_STATUSES = {
    "not-required",
    "absent",
    "invalid-stale",
    "invalid-scope",
    "invalid-replayed",
    "valid-standing-policy",
    "valid-explicit-constraint",
    "valid-fresh-principal",
    "valid-independent-authority",
    "valid-principal",
}
EVIDENCE_SOURCES = {
    "principal", "standing-policy", "delegated-principal",
    "independent-authority", "platform-ledger", "counterparty",
    "upstream-agent", "open-web", "none",
}


@dataclass(frozen=True)
class VariantSpec:
    variant_id: str
    challenge_mode: str
    is_benign: bool
    analysis_role: str
    paired_with: str | None
    pair_design: str
    controlled_axes: dict[str, Any]
    completion_intervention: dict[str, Any]
    changed_factor: str
    invariants: tuple[str, ...]
    world_patch: dict[str, Any]


@dataclass(frozen=True)
class TaskBundle:
    root: Path
    raw: dict[str, Any]
    instruction: str
    base_world: dict[str, Any]
    variants: dict[str, VariantSpec]

    @property
    def case_id(self) -> str:
        return str(self.raw["case"]["case_id"])

    @property
    def benign_variant(self) -> str:
        return str(self.raw["case"]["benign_variant"])


def deep_merge(base: Any, patch: Any) -> Any:
    """Return a new value with mapping patches recursively applied.

    Lists and scalar values are replaced atomically. That rule keeps a Variant's
    changed factor explicit and avoids surprising list-index mutation semantics.
    """
    if isinstance(base, dict) and isinstance(patch, dict):
        merged = {key: deep_merge(value, {}) if isinstance(value, dict) else value
                  for key, value in base.items()}
        for key, value in patch.items():
            merged[key] = deep_merge(merged[key], value) if key in merged else value
        return merged
    return patch


def stable_run_id(case_id: str, variant_id: str, agent_id: str, *,
                  intervention: str, seed: int, repeat_index: int,
                  control_layer: str = "none",
                  condition_fingerprint: str = "") -> str:
    conditions = {
        "case_id": case_id,
        "variant_id": variant_id,
        "agent_id": agent_id,
        "intervention": intervention,
        "control_layer": control_layer,
        "seed": seed,
        "repeat_index": repeat_index,
    }
    if condition_fingerprint:
        conditions["condition_fingerprint"] = condition_fingerprint
    digest = hashlib.sha256(
        json.dumps(conditions, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    return f"RC3-RUN-{digest}"


def load_task(task_dir: str | Path) -> TaskBundle:
    root = Path(task_dir).resolve()
    raw = tomllib.loads((root / "task.toml").read_text(encoding="utf-8"))
    instruction = (root / "instruction.md").read_text(encoding="utf-8").strip()
    base_world = json.loads((root / "environment" / "world.json").read_text(encoding="utf-8"))
    variants: dict[str, VariantSpec] = {}
    for path in sorted((root / "variants").glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        items = document if isinstance(document, list) else [document]
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"{path}: every Variant must be a mapping")
            variant = VariantSpec(
                variant_id=str(item["variant_id"]),
                challenge_mode=str(item["challenge_mode"]),
                is_benign=bool(item["is_benign"]),
                analysis_role=str(item.get("analysis_role") or (
                    "benign_control" if bool(item["is_benign"]) else "primary_attack")),
                paired_with=(str(item["paired_with"])
                             if item.get("paired_with") is not None else None),
                pair_design=str(item.get("pair_design") or (
                    "controlled_contrast" if item.get("paired_with") is not None
                    else "unpaired")),
                controlled_axes=item.get("controlled_axes") or {},
                completion_intervention=item.get("completion_intervention") or {},
                changed_factor=str(item["changed_factor"]),
                invariants=tuple(str(value) for value in item.get("invariants", [])),
                world_patch=item.get("world_patch") or {},
            )
            if variant.variant_id in variants:
                raise ValueError(f"duplicate variant_id: {variant.variant_id}")
            variants[variant.variant_id] = variant
    bundle = TaskBundle(root, raw, instruction, base_world, variants)
    errors = validate_task(bundle)
    if errors:
        raise ValueError("invalid task bundle:\n  " + "\n  ".join(errors))
    return bundle


def validate_task(bundle: TaskBundle) -> list[str]:
    errors: list[str] = []
    required_sections = {"task", "taxonomy", "case", "agent", "verifier", "environment"}
    missing = required_sections - set(bundle.raw)
    if missing:
        return [f"task.toml missing sections: {sorted(missing)}"]
    if bundle.root.name != bundle.case_id:
        errors.append(f"directory name must equal case_id={bundle.case_id}")
    if not re.fullmatch(r"RC-T\d{2}-[A-Z0-9-]+-\d{3}", bundle.case_id):
        errors.append(f"invalid case_id: {bundle.case_id}")
    lifecycle = bundle.raw["taxonomy"].get("lifecycle")
    if not isinstance(lifecycle, list) or len(lifecycle) != 4:
        errors.append("taxonomy.lifecycle must contain planting/ingress/commit/harm")
    elif any(not isinstance(value, int) or not 1 <= value <= 7 for value in lifecycle):
        errors.append("taxonomy.lifecycle values must be integers in [1, 7]")
    elif lifecycle != sorted(lifecycle):
        errors.append("taxonomy.lifecycle must be monotonic")
    if not bundle.variants:
        errors.append("task must declare at least one Variant")
    designated = bundle.variants.get(bundle.benign_variant)
    if designated is None or not designated.is_benign:
        errors.append("case.benign_variant must reference a benign Variant")
    primary_controls = [
        variant.variant_id for variant in bundle.variants.values()
        if variant.analysis_role == "benign_control"
    ]
    if primary_controls != [bundle.benign_variant]:
        errors.append(
            "exactly one benign_control must match case.benign_variant; "
            f"found {primary_controls}")
    for variant in bundle.variants.values():
        if not variant.changed_factor:
            errors.append(f"{variant.variant_id}: changed_factor is empty")
        if not variant.invariants:
            errors.append(f"{variant.variant_id}: invariants are empty")
        if variant.analysis_role not in ANALYSIS_ROLES:
            errors.append(
                f"{variant.variant_id}: unsupported analysis_role={variant.analysis_role}")
        if variant.is_benign != (variant.analysis_role in BENIGN_ANALYSIS_ROLES):
            errors.append(
                f"{variant.variant_id}: analysis_role disagrees with is_benign")
        if variant.paired_with == variant.variant_id:
            errors.append(f"{variant.variant_id}: paired_with cannot reference itself")
        if variant.paired_with is not None and variant.paired_with not in bundle.variants:
            errors.append(
                f"{variant.variant_id}: paired_with target is absent: {variant.paired_with}")
        if variant.pair_design not in PAIR_DESIGNS:
            errors.append(
                f"{variant.variant_id}: unsupported pair_design={variant.pair_design}")
        if (variant.paired_with is None) != (variant.pair_design == "unpaired"):
            errors.append(
                f"{variant.variant_id}: pair_design must be unpaired exactly when "
                "paired_with is null")
        if (not isinstance(variant.controlled_axes, dict)
                or any(not isinstance(key, str) or not isinstance(value, str)
                       for key, value in variant.controlled_axes.items())):
            errors.append(f"{variant.variant_id}: controlled_axes must map strings to strings")
        if not isinstance(variant.completion_intervention, dict):
            errors.append(f"{variant.variant_id}: completion_intervention must be a mapping")
        elif variant.completion_intervention:
            required_intervention_keys = {"target_predicates", "variable", "level"}
            optional_intervention_keys = {"predicate_context"}
            actual_intervention_keys = set(variant.completion_intervention)
            if (not required_intervention_keys <= actual_intervention_keys
                    or actual_intervention_keys - (
                        required_intervention_keys | optional_intervention_keys)):
                errors.append(
                    f"{variant.variant_id}: completion_intervention must contain "
                    f"{sorted(required_intervention_keys)} with optional "
                    f"{sorted(optional_intervention_keys)}")
            targets = variant.completion_intervention.get("target_predicates")
            if (not isinstance(targets, list) or not targets
                    or any(not isinstance(value, str) or not value for value in targets)
                    or len(targets) != len(set(targets))):
                errors.append(
                    f"{variant.variant_id}: target_predicates must be unique non-empty strings")
            for field in ("variable", "level"):
                value = variant.completion_intervention.get(field)
                if not isinstance(value, str) or not value:
                    errors.append(
                        f"{variant.variant_id}: completion_intervention.{field} is empty")
            predicate_context = variant.completion_intervention.get("predicate_context", {})
            if not isinstance(predicate_context, dict):
                errors.append(
                    f"{variant.variant_id}: completion_intervention.predicate_context "
                    "must be a mapping")
            else:
                unknown_context = sorted(set(predicate_context) - set(targets or []))
                if unknown_context:
                    errors.append(
                        f"{variant.variant_id}: predicate_context contains non-targets: "
                        f"{unknown_context}")
                required_context_keys = {
                    "mandate_status", "mandate_paths", "evidence_sources", "witness_status",
                }
                for predicate_id, context in predicate_context.items():
                    label = (
                        f"{variant.variant_id}: predicate_context[{predicate_id}]")
                    if not isinstance(context, dict) or set(context) != required_context_keys:
                        errors.append(
                            f"{label} must contain exactly "
                            f"{sorted(required_context_keys)}")
                        continue
                    if context["mandate_status"] not in MANDATE_STATUSES:
                        errors.append(
                            f"{label}.mandate_status is invalid: "
                            f"{context['mandate_status']}")
                    mandate_paths = context["mandate_paths"]
                    if (not isinstance(mandate_paths, list)
                            or any(not isinstance(path, str) or not path
                                   for path in mandate_paths)
                            or len(mandate_paths) != len(set(mandate_paths))):
                        errors.append(f"{label}.mandate_paths must be unique strings")
                    elif (context["mandate_status"] == "unspecified") != (
                            len(mandate_paths) == 0):
                        errors.append(
                            f"{label}.mandate_paths must be empty exactly when unspecified")
                    evidence_sources = context["evidence_sources"]
                    if (not isinstance(evidence_sources, list) or not evidence_sources
                            or any(source not in EVIDENCE_SOURCES
                                   for source in evidence_sources)
                            or len(evidence_sources) != len(set(evidence_sources))):
                        errors.append(
                            f"{label}.evidence_sources must be unique known sources")
                    if context["witness_status"] not in WITNESS_STATUSES:
                        errors.append(
                            f"{label}.witness_status is invalid: "
                            f"{context['witness_status']}")
    verifier_entrypoint = str(bundle.raw["verifier"].get("entrypoint", "tests/verify.py"))
    driver_entrypoint = str(bundle.raw["environment"].get("driver", "environment/driver.py"))
    required_files = [
        verifier_entrypoint, "tests/private_ground_truth.json",
        driver_entrypoint, "environment/Dockerfile", "tests/Dockerfile",
    ]
    agent_mode = bundle.raw["agent"].get("mode", "single")
    if agent_mode == "single":
        required_files.append("solution/solve.py")
    elif agent_mode == "multi-agent-sequential":
        roles = [str(role) for role in bundle.raw["agent"].get("roles", [])]
        if len(roles) < 2 or len(roles) != len(set(roles)):
            errors.append("multi-agent-sequential requires at least two unique roles")
        for profile_name in ("reference", "vulnerable"):
            profile = (bundle.raw.get("profiles") or {}).get(profile_name)
            if not isinstance(profile, dict) or set(profile) != set(roles):
                errors.append(f"profiles.{profile_name} must map every declared role")
            else:
                required_files.extend(str(profile[role]) for role in roles)
    else:
        errors.append(f"unsupported agent.mode={agent_mode}")
    for relative in required_files:
        if not (bundle.root / relative).is_file():
            errors.append(f"missing required file: {relative}")
    leaked_terms = ("threat_id", "variant_id", "oracle", "harm_landed", "attack_success")
    lower_instruction = bundle.instruction.lower()
    for term in leaked_terms:
        if term in lower_instruction:
            errors.append(f"instruction leaks evaluation metadata: {term}")
    return errors
