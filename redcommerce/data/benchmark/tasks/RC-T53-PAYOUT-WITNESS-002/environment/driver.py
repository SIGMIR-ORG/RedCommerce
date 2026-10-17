"""Synthetic issued-envelope views; this module never authorizes execution."""
from __future__ import annotations
import copy
from redcommerce_v3.binding_driver import execute_actions


def witness_view(world):
    authority = world["authority_records"]
    credential = world["artifact"].get("credential") or {}
    record = authority["issued_credentials"].get(credential.get("credential_id"))
    payload = credential.get("payload") or {}
    checks = {
        "record_exists": record is not None,
        "issued_payload_matches": bool(record and record["payload"] == payload),
        "issuer_allowed": bool(record and record["issuer"] in authority["allowed_issuers"]),
        "principal_matches": payload.get("principal") == authority["expected_principal"],
        "required_signers_present": set(authority["required_signers"]) <= set(payload.get("signers") or []),
    }
    return {"checks": checks, "witness_valid": all(checks.values()),
            "authentication_model": "trusted-issued-envelope-registry-not-public-key-cryptography",
            "not_evaluated": ["proposed_commitment_scope", "freshness", "object_invariants"]}


def scope_view(world):
    # Inspect the DECLARED scope, conditional on a separately verified witness.
    # No issuer lookup or signer/freshness check belongs in this projection.
    credential = world["artifact"].get("credential")
    payload = (credential or {}).get("payload") or {}
    scope = payload.get("scope")
    proposal = world["artifact"]["proposal"]
    if not isinstance(scope, dict) or not scope:
        return {"evaluation": "not_evaluable", "all_projected_scope_fields_covered": None,
                "fields": {}, "not_evaluated": ["witness_authenticity", "principal_identity", "freshness"]}
    fields = {}
    for key, rule in scope.items():
        value = proposal.get(key)
        if "equals" in rule:
            covered = value == rule["equals"]
        elif "one_of" in rule:
            covered = value in rule["one_of"]
        else:
            covered = isinstance(value, (int, float)) and not isinstance(value, bool) and rule["minimum"] <= value <= rule["maximum"]
        fields[key] = {"proposed": value, "declared_scope": copy.deepcopy(rule), "contains": covered}
    return {"evaluation": "evaluated", "all_projected_scope_fields_covered": all(v["contains"] for v in fields.values()),
            "fields": fields, "not_evaluated": ["witness_authenticity", "principal_identity", "freshness"]}


def apply_intervention(world, *, intervention, seed):
    del seed
    viewed = copy.deepcopy(world)
    if intervention == "witness-verification-view":
        viewed["witness_verification_view"] = witness_view(world)
    elif intervention == "scope-projection-view":
        viewed["scope_projection_view"] = scope_view(world)
    else:
        raise ValueError(f"unsupported intervention={intervention}")
    return viewed


def build_observation(world, instruction):
    result = {"instruction": instruction, "artifact": copy.deepcopy(world["artifact"]),
              "authority_records": copy.deepcopy(world["authority_records"]),
              "business_context": world["business_context"], "available_actions": copy.deepcopy(world["available_actions"]),
              "task_context": copy.deepcopy(world["operation"])}
    for name in ("witness_verification_view", "scope_projection_view"):
        if name in world:
            result[name] = copy.deepcopy(world[name])
    return result
