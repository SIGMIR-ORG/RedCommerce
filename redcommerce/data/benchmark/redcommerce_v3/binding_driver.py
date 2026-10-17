"""Generic visible environment for single-commit commerce binding tasks.

The driver deliberately enforces only tool syntax.  Whether a syntactically valid
commit is authorized is the agent's task and the independent verifier's job.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from redcommerce_v3.control_layers import (
    authorize_binding_commitment,
    configure_world,
)


STATE_FRESHNESS_INTERVENTION = "state-freshness-view"
SCOPE_PROJECTION_INTERVENTION = "scope-projection-view"


def _digest(value: Any) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _three_ds_freshness_view(world: dict[str, Any]) -> dict[str, Any]:
    artifact = world["artifact"]
    authority = world["authority_records"]
    authentication_id = (artifact.get("three_ds") or {}).get("authentication_id")
    record = (authority.get("authentication_ledger") or {}).get(authentication_id)
    current_time = int(authority["current_time"])
    nonce = record.get("nonce") if record else None
    consumed = bool(record and record.get("consumed"))
    nonce_used = bool(nonce and nonce in authority.get("used_authentication_nonces", []))
    expired = bool(record and int(record.get("expires_at", 0)) < current_time)
    return {
        "artifact_type": "three_ds_authentication",
        "artifact_id": authentication_id,
        "record_exists": record is not None,
        "current_time": current_time,
        "expires_at": record.get("expires_at") if record else None,
        "consumed": consumed,
        "nonce_used": nonce_used,
        # Freshness is deliberately state-only. Transaction, merchant and amount
        # binding remain M5/M2 questions and are not folded into this M6 view.
        "fresh": bool(record is not None and not consumed and not nonce_used and not expired),
        "reason_codes": [
            reason for reason, active in (
                ("record_missing", record is None),
                ("artifact_consumed", consumed),
                ("nonce_already_used", nonce_used),
                ("artifact_expired", expired),
            ) if active
        ],
    }


def _address_freshness_view(world: dict[str, Any]) -> dict[str, Any]:
    artifact = world["artifact"]
    authority = world["authority_records"]
    label = authority["label_record"]
    address_digest = _digest(artifact.get("address") or {})
    label_bound = bool(
        artifact.get("order_id") == label.get("order_id")
        and int(artifact.get("address_version", -1))
        == int(label.get("address_version", -2))
        and address_digest == label.get("address_digest")
    )
    token = (artifact.get("reauthorization") or {}).get("token")
    record = (authority.get("reauthorization_ledger") or {}).get(token)
    current_time = int(authority["current_time"])
    consumed = bool(record and record.get("consumed"))
    token_used = bool(token and token in authority.get("used_reauthorization_tokens", []))
    expired = bool(record and int(record.get("expires_at", 0)) < current_time)
    fresh_reauthorization = bool(
        record is not None and not consumed and not token_used and not expired)
    fresh = bool(label_bound or fresh_reauthorization)
    return {
        "artifact_type": "shipping_address_authorization",
        "artifact_id": token,
        "label_bound": label_bound,
        "reauthorization_required": not label_bound,
        "record_exists": record is not None,
        "current_time": current_time,
        "expires_at": record.get("expires_at") if record else None,
        "consumed": consumed,
        "token_used": token_used,
        # Order, address-version and address-value binding are intentionally not
        # decided here. The view exposes only continuity/freshness state.
        "fresh": fresh,
        "reason_codes": [
            reason for reason, active in (
                ("reauthorization_missing", not label_bound and not token),
                ("record_missing", not label_bound and bool(token) and record is None),
                ("artifact_consumed", consumed),
                ("token_already_used", token_used),
                ("artifact_expired", expired),
            ) if active
        ],
    }


def _discount_scope_view(world: dict[str, Any]) -> dict[str, Any]:
    artifact = world["artifact"]
    authority = world["authority_records"]
    proposed = float(artifact.get("discount_pct", -1))
    role_limit = float(authority["role_discount_limit_pct"])
    standing_contains = 0 <= proposed <= role_limit
    nonce = (artifact.get("approval") or {}).get("nonce")
    record = (authority.get("approval_ledger") or {}).get(nonce)
    exception_checks = {
        "record_exists": record is not None,
        "resource_contains": bool(
            record and record.get("quote_id") == artifact.get("quote_id")),
        "value_contains": bool(
            record and abs(float(record.get("discount_pct", -1)) - proposed) <= 1e-6),
    }
    exception_contains = all(exception_checks.values())
    return {
        "projection_type": "discount_authority_scope",
        "projected_fields": ["discount_pct"],
        "not_evaluated": ["principal_identity", "approver_role", "witness_authenticity", "freshness", "object_invariants"],
        "principal_role": authority.get("sales_role"),
        "proposed_fields": {
            "discount_pct": {
                "value": proposed,
                "standing_scope": {
                    "minimum_inclusive": 0.0,
                    "maximum_inclusive": role_limit,
                    "contains": standing_contains,
                },
                "presented_exception_scope": {
                    "artifact_id": nonce,
                    **exception_checks,
                    "contains": exception_contains,
                    "freshness_evaluated": False,
                },
                "covered_by_declared_scope": bool(
                    standing_contains or exception_contains),
            }
        },
        "all_projected_scope_fields_covered": bool(
            standing_contains or exception_contains),
    }


def _cart_scope_view(world: dict[str, Any]) -> dict[str, Any]:
    artifact = world["artifact"]
    authority = world["authority_records"]
    mandate = authority["user_mandate"]

    total = float(artifact.get("total", -1))
    budget_cap = float(mandate["budget_cap"])
    total_contains = 0 <= total <= budget_cap

    refund_days = int(artifact.get("refund_period", -1))
    standing_minimum = mandate.get("min_refund_days")
    standing_refund_contains = bool(
        standing_minimum is not None and refund_days >= int(standing_minimum))
    clarification = authority.get("fresh_clarification")
    clarification_minimum = (
        clarification.get("min_refund_days") if clarification else None)
    clarification_checks = {
        "record_exists": clarification is not None,
        "resource_contains": bool(
            clarification and clarification.get("resource_id") == artifact.get("cart_id")),
        "value_contains": bool(
            clarification_minimum is not None
            and refund_days >= int(clarification_minimum)),
    }
    clarification_contains = all(clarification_checks.values())
    refund_contains = bool(standing_refund_contains or clarification_contains)

    return {
        "projection_type": "cart_mandate_scope",
        "projected_fields": ["total", "refund_period"],
        "not_evaluated": ["principal_identity", "witness_authenticity", "confirmation_requirement", "freshness", "object_invariants"],
        "principal": authority.get("expected_principal"),
        "proposed_fields": {
            "total": {
                "value": total,
                "standing_scope": {
                    "minimum_inclusive": 0.0,
                    "maximum_inclusive": budget_cap,
                    "contains": total_contains,
                },
                "covered_by_declared_scope": total_contains,
            },
            "refund_period": {
                "value": refund_days,
                "standing_scope": {
                    "minimum_inclusive": standing_minimum,
                    "determined": standing_minimum is not None,
                    "contains": standing_refund_contains,
                },
                "presented_exception_scope": {
                    "minimum_inclusive": clarification_minimum,
                    **clarification_checks,
                    "contains": clarification_contains,
                    "principal_and_freshness_evaluated": False,
                },
                "covered_by_declared_scope": refund_contains,
            },
        },
        # Object-semantic invariants (labels, line sums) are deliberately absent:
        # those are M2, not scope-containment questions.
        "all_projected_scope_fields_covered": bool(total_contains and refund_contains),
    }


def _scope_projection_view(world: dict[str, Any]) -> dict[str, Any]:
    artifact = world.get("artifact") or {}
    authority = world.get("authority_records") or {}
    if "discount_pct" in artifact and "role_discount_limit_pct" in authority:
        return _discount_scope_view(world)
    if "cart_id" in artifact and "user_mandate" in authority:
        return _cart_scope_view(world)
    raise ValueError("scope-projection-view is not implemented for this binding world")


def apply_intervention(world: dict[str, Any], *, intervention: str,
                       seed: int) -> dict[str, Any]:
    """Add a canonical state/freshness projection without changing authority.

    The raw artifact, principal, scope and authority ledgers are preserved. This
    is a view intervention: it makes a state relation explicit at the commitment
    point and never creates a new authorization witness.
    """
    del seed
    view = copy.deepcopy(world)
    if intervention == STATE_FRESHNESS_INTERVENTION:
        artifact = view.get("artifact") or {}
        authority = view.get("authority_records") or {}
        if "three_ds" in artifact and "authentication_ledger" in authority:
            freshness = _three_ds_freshness_view(view)
        elif "address_version" in artifact and "reauthorization_ledger" in authority:
            freshness = _address_freshness_view(view)
        else:
            raise ValueError(
                "state-freshness-view is not implemented for this binding world")
        view["state_freshness_view"] = freshness
    elif intervention == SCOPE_PROJECTION_INTERVENTION:
        view["scope_projection_view"] = _scope_projection_view(view)
    else:
        raise ValueError(f"unsupported intervention={intervention}")
    return view


def configure_control_layer(world: dict[str, Any], *, control_layer: str,
                            seed: int) -> dict[str, Any]:
    del seed
    artifact = world.get("artifact") or {}
    if "user_confirmation" in artifact and "offer" in artifact:
        policy_type = "confirmation_binding"
    elif "cart_id" in artifact and "items" in artifact:
        policy_type = "cart_mandate"
    else:
        raise ValueError(
            "commitment controls are not yet implemented for this binding Case")
    return configure_world(
        world, control_layer=control_layer, policy_type=policy_type)


def build_observation(world: dict[str, Any], instruction: str) -> dict[str, Any]:
    observation = {
        "instruction": instruction,
        "business_context": world["business_context"],
        "artifact": world["artifact"],
        "authority_records": world["authority_records"],
        "available_actions": world["available_actions"],
        "operation_contract": {
            "commit_tool": world["operation"]["commit_tool"],
            "resource_id": world["operation"]["resource_id"],
        },
    }
    if "state_freshness_view" in world:
        observation["state_freshness_view"] = copy.deepcopy(
            world["state_freshness_view"])
    if "scope_projection_view" in world:
        observation["scope_projection_view"] = copy.deepcopy(
            world["scope_projection_view"])
    return observation


def execute_actions(world: dict[str, Any], response: dict[str, Any], *,
                    intervention: str, seed: int) -> tuple[dict, list[dict]]:
    del intervention, seed
    operation = world["operation"]
    state: dict[str, Any] = {"commits": [], "escalations": [], "rejected_actions": []}
    events: list[dict[str, Any]] = []
    for index, action in enumerate(response.get("actions", [])):
        tool = action.get("tool") if isinstance(action, dict) else None
        arguments = action.get("arguments", {}) if isinstance(action, dict) else {}
        event = {"sequence": index + 1, "event": "tool_call", "tool": tool,
                 "arguments": arguments}
        if (tool == operation["commit_tool"]
                and arguments.get("resource_id") == operation["resource_id"]):
            # The public commit interface is idempotent per resource.  This is an
            # environment invariant, not an Agent safety judgment: repeating the
            # same tool call must not create duplicate charges, shipments, or
            # other commercial effects.
            if state["commits"]:
                state["rejected_actions"].append({
                    "tool": tool,
                    "arguments": arguments,
                    "reason": "duplicate_resource_commit",
                })
                event["status"] = "rejected"
                event["reason"] = "duplicate_resource_commit"
                events.append(event)
                continue
            decision = authorize_binding_commitment(
                world, artifact=world["artifact"])
            event.update(decision.event_fields())
            if decision.allowed:
                record = {
                    "tool": tool,
                    "resource_id": operation["resource_id"],
                    "artifact": copy.deepcopy(world["artifact"]),
                    "status": "committed",
                }
                state["commits"].append(record)
                event["status"] = "committed"
            else:
                rejected = {
                    "tool": tool,
                    "arguments": arguments,
                    "reason": "control_layer_blocked",
                    "control_layer": decision.layer,
                    "reason_codes": list(decision.reason_codes),
                }
                state["rejected_actions"].append(rejected)
                event["status"] = "rejected"
                event["reason"] = "control_layer_blocked"
        elif tool == "escalate_for_review" and arguments.get("reason"):
            state["escalations"].append({
                "reason": str(arguments["reason"]),
                "conflicts": list(arguments.get("conflicts") or []),
                "status": "awaiting_review",
            })
            event["status"] = "accepted"
        else:
            state["rejected_actions"].append({
                "tool": tool, "arguments": arguments, "reason": "invalid action",
            })
            event["status"] = "rejected"
            event["reason"] = "invalid action"
        events.append(event)
    return state, events
