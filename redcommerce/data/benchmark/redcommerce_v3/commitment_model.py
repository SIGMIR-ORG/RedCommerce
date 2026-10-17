"""Load and validate verifier-side mandate-commitment research contracts.

The contract is deliberately separate from task observations and runtime world
state.  It describes the research construct used to analyse a task; it is not a
policy prompt and must not be mounted into an evaluated agent container.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "0.2"
RESEARCH_CONSTRUCT = "mandate-commitment-gap"
COMPLETION_REQUIREMENTS = {"information", "preference", "authorization"}
MANDATE_STATUSES = {"explicit", "standing-policy", "unspecified"}
MANDATE_DETERMINATIONS = {"exact", "bounded", "open"}
SOURCE_CLASSES = {
    "principal", "standing-policy", "delegated-principal",
    "independent-authority", "platform-ledger", "counterparty",
    "upstream-agent", "open-web", "none",
}
AUTHORITY_BINDINGS = {
    "principal", "action", "resource", "field-scope", "value-scope", "time", "nonce",
}
BUSINESS_BINDINGS = {"B-AUTH", "B-EVID", "B-MAND", "B-TERM", "B-STATE", "B-EXCH"}
REVERSIBILITY = {"advisory-only", "reversible", "costly-reversible", "irreversible"}
COMMITMENT_KINDS = {
    "ranking-allocation", "commercial-recommendation", "order-confirmation",
    "payment", "fulfillment-state-change", "refund", "data-disclosure",
}
EFFECT_CLASSES = {"advisory", "economically-binding", "legally-binding"}
PATH_PATTERN = re.compile(r"^(world|truth|final_state|events)(\.[A-Za-z0-9_*\[\]-]+)+$")
PREDICATE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


@dataclass(frozen=True)
class MandateCommitmentContract:
    path: Path
    raw: dict[str, Any]

    @property
    def case_id(self) -> str:
        return str(self.raw["case_id"])

    @property
    def material_predicates(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.raw["material_predicates"])


def _require_string(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} must be a non-empty string")


def _require_unique_string_list(value: Any, label: str, errors: list[str], *,
                                nonempty: bool = False,
                                allowed: set[str] | None = None) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        errors.append(f"{label} must be a list of strings")
        return []
    items = list(value)
    if nonempty and not items:
        errors.append(f"{label} must not be empty")
    if len(items) != len(set(items)):
        errors.append(f"{label} contains duplicates")
    if allowed is not None:
        invalid = sorted(set(items) - allowed)
        if invalid:
            errors.append(f"{label} has invalid values: {invalid}")
    return items


def _validate_path(value: Any, label: str, errors: list[str], *,
                   world: dict[str, Any], truth: dict[str, Any]) -> None:
    if not isinstance(value, str) or not PATH_PATTERN.fullmatch(value):
        errors.append(f"{label} is not a valid research path: {value!r}")
        return
    root, top, *_ = value.split(".")
    if root == "world" and top not in world:
        errors.append(f"{label} references missing world key: {top}")
    if root == "truth" and top not in truth:
        errors.append(f"{label} references missing truth key: {top}")


def validate_contract(raw: Any, *, task_raw: dict[str, Any], case_id: str,
                      world: dict[str, Any], truth: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(raw, dict):
        return ["contract root must be a mapping"]

    expected_root = {
        "schema_version", "case_id", "research_construct", "principal", "mandate",
        "commitment", "material_predicates", "pilot_hypotheses",
    }
    if set(raw) != expected_root:
        errors.append(f"contract root keys differ: {sorted(set(raw) ^ expected_root)}")
    if raw.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if raw.get("research_construct") != RESEARCH_CONSTRUCT:
        errors.append(f"research_construct must be {RESEARCH_CONSTRUCT}")
    if raw.get("case_id") != case_id:
        errors.append(f"case_id mismatch: {raw.get('case_id')} != {case_id}")

    principal = raw.get("principal")
    if not isinstance(principal, dict) or set(principal) != {"source_path", "description"}:
        errors.append("principal must contain exactly source_path and description")
    else:
        _validate_path(principal["source_path"], "principal.source_path", errors,
                       world=world, truth=truth)
        _require_string(principal["description"], "principal.description", errors)

    mandate = raw.get("mandate")
    if not isinstance(mandate, dict) or set(mandate) != {
            "source_paths", "completeness", "description"}:
        errors.append("mandate must contain exactly source_paths, completeness, description")
    else:
        source_paths = _require_unique_string_list(
            mandate["source_paths"], "mandate.source_paths", errors, nonempty=True)
        for index, path in enumerate(source_paths):
            _validate_path(path, f"mandate.source_paths[{index}]", errors,
                           world=world, truth=truth)
        if mandate["completeness"] != "partial-open-world":
            errors.append("mandate.completeness must be partial-open-world")
        _require_string(mandate["description"], "mandate.description", errors)

    commitment = raw.get("commitment")
    commitment_keys = {
        "commit_agent", "commit_tool", "state_path", "kind", "effect_class", "reversibility",
    }
    if not isinstance(commitment, dict) or set(commitment) != commitment_keys:
        errors.append(f"commitment must contain exactly {sorted(commitment_keys)}")
    else:
        case_raw = task_raw.get("case", {})
        if commitment["commit_agent"] != case_raw.get("commit_agent"):
            errors.append("commitment.commit_agent differs from task.toml")
        if commitment["commit_tool"] != case_raw.get("commit_tool"):
            errors.append("commitment.commit_tool differs from task.toml")
        _validate_path(commitment["state_path"], "commitment.state_path", errors,
                       world=world, truth=truth)
        if commitment["kind"] not in COMMITMENT_KINDS:
            errors.append(f"invalid commitment.kind: {commitment['kind']}")
        if commitment["effect_class"] not in EFFECT_CLASSES:
            errors.append(f"invalid commitment.effect_class: {commitment['effect_class']}")
        if commitment["reversibility"] not in REVERSIBILITY:
            errors.append(f"invalid commitment.reversibility: {commitment['reversibility']}")

    task_bindings = {
        task_raw.get("taxonomy", {}).get("primary_binding"),
        *task_raw.get("taxonomy", {}).get("secondary_bindings", []),
    }
    predicates = raw.get("material_predicates")
    if not isinstance(predicates, list) or not predicates:
        errors.append("material_predicates must be a non-empty list")
        predicates = []
    predicate_ids: list[str] = []
    predicate_keys = {
        "predicate_id", "commitment_path", "description", "completion_requirements",
        "mandate_status", "mandate_determination", "mandate_paths", "evidence",
        "authorization", "bindings", "verifier_reason_codes", "consequence",
    }
    for index, predicate in enumerate(predicates):
        label = f"material_predicates[{index}]"
        if not isinstance(predicate, dict) or set(predicate) != predicate_keys:
            errors.append(f"{label} must contain exactly {sorted(predicate_keys)}")
            continue
        predicate_id = predicate["predicate_id"]
        if not isinstance(predicate_id, str) or not PREDICATE_PATTERN.fullmatch(predicate_id):
            errors.append(f"{label}.predicate_id is invalid: {predicate_id!r}")
        else:
            predicate_ids.append(predicate_id)
        _validate_path(predicate["commitment_path"], f"{label}.commitment_path", errors,
                       world=world, truth=truth)
        _require_string(predicate["description"], f"{label}.description", errors)
        _require_unique_string_list(
            predicate["completion_requirements"], f"{label}.completion_requirements",
            errors, nonempty=True, allowed=COMPLETION_REQUIREMENTS)
        status = predicate["mandate_status"]
        if status not in MANDATE_STATUSES:
            errors.append(f"{label}.mandate_status is invalid: {status}")
        determination = predicate["mandate_determination"]
        if determination not in MANDATE_DETERMINATIONS:
            errors.append(
                f"{label}.mandate_determination is invalid: {determination}")
        if status == "unspecified" and determination != "open":
            errors.append(
                f"{label}.mandate_determination must be open when unspecified")
        mandate_paths = _require_unique_string_list(
            predicate["mandate_paths"], f"{label}.mandate_paths", errors)
        for path_index, path in enumerate(mandate_paths):
            _validate_path(path, f"{label}.mandate_paths[{path_index}]", errors,
                           world=world, truth=truth)
        if status in {"explicit", "standing-policy"} and not mandate_paths:
            errors.append(f"{label}.mandate_paths must not be empty for {status}")
        if status == "unspecified" and mandate_paths:
            errors.append(f"{label}.mandate_paths must be empty when unspecified")

        evidence = predicate["evidence"]
        evidence_keys = {"observed_sources", "admissible_sources", "adversary_influence_sources"}
        if not isinstance(evidence, dict) or set(evidence) != evidence_keys:
            errors.append(f"{label}.evidence must contain exactly {sorted(evidence_keys)}")
        else:
            _require_unique_string_list(
                evidence["observed_sources"], f"{label}.evidence.observed_sources",
                errors, nonempty=True, allowed=SOURCE_CLASSES)
            _require_unique_string_list(
                evidence["admissible_sources"], f"{label}.evidence.admissible_sources",
                errors, nonempty=True, allowed=SOURCE_CLASSES)
            _require_unique_string_list(
                evidence["adversary_influence_sources"],
                f"{label}.evidence.adversary_influence_sources", errors,
                allowed=SOURCE_CLASSES)

        authorization = predicate["authorization"]
        authorization_keys = {"required", "accepted_witness_sources", "required_bindings"}
        if not isinstance(authorization, dict) or set(authorization) != authorization_keys:
            errors.append(
                f"{label}.authorization must contain exactly {sorted(authorization_keys)}")
        else:
            required = authorization["required"]
            if not isinstance(required, bool):
                errors.append(f"{label}.authorization.required must be boolean")
            witnesses = _require_unique_string_list(
                authorization["accepted_witness_sources"],
                f"{label}.authorization.accepted_witness_sources", errors,
                allowed=SOURCE_CLASSES)
            authority_bindings = _require_unique_string_list(
                authorization["required_bindings"],
                f"{label}.authorization.required_bindings", errors,
                allowed=AUTHORITY_BINDINGS)
            if required and (not witnesses or not authority_bindings):
                errors.append(f"{label}.authorization requires witnesses and bindings")
            if not required and (witnesses or authority_bindings):
                errors.append(f"{label}.authorization metadata must be empty when not required")

        reason_codes = _require_unique_string_list(
            predicate["verifier_reason_codes"], f"{label}.verifier_reason_codes",
            errors, nonempty=True)
        invalid_reason_codes = [
            code for code in reason_codes if not re.fullmatch(r"[a-z][a-z0-9_]*", code)]
        if invalid_reason_codes:
            errors.append(
                f"{label}.verifier_reason_codes has invalid values: "
                f"{invalid_reason_codes}")

        bindings = _require_unique_string_list(
            predicate["bindings"], f"{label}.bindings", errors,
            nonempty=True, allowed=BUSINESS_BINDINGS)
        undeclared = sorted(set(bindings) - task_bindings)
        if undeclared:
            errors.append(f"{label}.bindings not declared in task taxonomy: {undeclared}")

        consequence = predicate["consequence"]
        if not isinstance(consequence, dict) or set(consequence) != {"reversibility", "description"}:
            errors.append(f"{label}.consequence must contain reversibility and description")
        else:
            if consequence["reversibility"] not in REVERSIBILITY:
                errors.append(
                    f"{label}.consequence.reversibility is invalid: "
                    f"{consequence['reversibility']}")
            _require_string(consequence["description"], f"{label}.consequence.description", errors)

    if len(predicate_ids) != len(set(predicate_ids)):
        errors.append("material_predicates contains duplicate predicate_id values")

    _require_unique_string_list(
        raw.get("pilot_hypotheses"), "pilot_hypotheses", errors, nonempty=True)
    return errors


def load_contract(task_root: str | Path, *, task_raw: dict[str, Any],
                  world: dict[str, Any], truth: dict[str, Any]) -> MandateCommitmentContract:
    root = Path(task_root).resolve()
    path = root / "research" / "mandate_commitment.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_contract(
        raw, task_raw=task_raw, case_id=root.name, world=world, truth=truth)
    if errors:
        raise ValueError(f"invalid mandate-commitment contract: {path}\n  " + "\n  ".join(errors))
    return MandateCommitmentContract(path=path, raw=raw)
