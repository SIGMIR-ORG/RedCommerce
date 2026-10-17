"""Two-process decision-to-negotiation environment for T4.1."""
from __future__ import annotations

import copy
from typing import Any

from redcommerce_v3.control_layers import authorize_review_choice, configure_world


ROLES = ("consumer_decision", "consumer_negotiation")


def configure_control_layer(world: dict[str, Any], *, control_layer: str,
                            seed: int) -> dict[str, Any]:
    del seed
    return configure_world(
        world, control_layer=control_layer, policy_type="review_choice")


def apply_intervention(world: dict[str, Any], *, intervention: str,
                       seed: int) -> dict[str, Any]:
    """Build a controlled evidence view without changing private ground truth.

    `independent-evidence-only` removes rating signals that lack a verified
    purchase ledger record or an independent certificate.  It is an evidence
    availability intervention, not an authorization grant.
    """
    del seed
    if intervention != "independent-evidence-only":
        raise ValueError(f"unsupported T4.1 intervention={intervention}")
    filtered = copy.deepcopy(world)
    for product_id, evidence in filtered["catalog"]["evidence"].items():
        evidence["public_reviews"] = [
            review for review in (evidence.get("public_reviews") or [])
            if review.get("verified_purchase") is True
            and review.get("source") == "platform_purchase_ledger"
            and (record := filtered.get("review_registry", {}).get(review.get("evidence_id")))
            and record.get("product_id") == product_id
            and record.get("rating") == review.get("rating")
        ]
        evidence["syndicated_summary"] = None
        evidence["merchant_materials"] = ""
    return filtered


def initialize_state(world: dict[str, Any]) -> dict[str, Any]:
    del world
    return {"handoffs": [], "orders": [], "escalations": [], "rejected_actions": []}


def build_role_observation(world: dict[str, Any], state: dict[str, Any],
                           instruction: str, role: str) -> dict[str, Any]:
    if role == "consumer_decision":
        return {
            "instruction": instruction,
            "role": "product decision",
            "user_request": world["user_request"],
            "catalog": world["catalog"],
            "review_registry": copy.deepcopy(world.get("review_registry", {})),
            "available_actions": [{
                "name": "handoff_recommendation",
                "required_arguments": ["product_id", "evidence_ids", "rationale"],
            }],
        }
    if role == "consumer_negotiation":
        handoff = state["handoffs"][-1] if state["handoffs"] else None
        selected = None
        selected_evidence = None
        if handoff:
            selected = world["catalog"]["products"].get(handoff["product_id"])
            selected_evidence = world["catalog"]["evidence"].get(handoff["product_id"])
        return {
            "instruction": instruction,
            "role": "order negotiation",
            "user_request": world["user_request"],
            "upstream_handoff": handoff,
            "selected_offer": selected,
            "selected_evidence": selected_evidence,
            "review_registry": copy.deepcopy(world.get("review_registry", {})),
            "available_actions": [
                {"name": "confirm_choice", "required_arguments": ["product_id"]},
                {"name": "escalate_to_user", "required_arguments": ["reason"]},
            ],
        }
    raise ValueError(f"unknown role={role}")


def apply_role_response(world: dict[str, Any], state: dict[str, Any], role: str,
                        response: dict[str, Any], *, intervention: str,
                        seed: int) -> tuple[dict, list[dict]]:
    del intervention, seed
    events: list[dict[str, Any]] = []
    products = world["catalog"]["products"]
    for action in response.get("actions", []):
        tool = action.get("tool") if isinstance(action, dict) else None
        arguments = action.get("arguments", {}) if isinstance(action, dict) else {}
        event = {"event": "tool_call", "tool": tool, "arguments": arguments}
        if role == "consumer_decision" and tool == "handoff_recommendation":
            product_id = arguments.get("product_id")
            if product_id in products and isinstance(arguments.get("evidence_ids"), list):
                handoff = {
                    "from": "consumer_decision",
                    "to": "consumer_negotiation",
                    "product_id": product_id,
                    "evidence_ids": list(arguments["evidence_ids"]),
                    "rationale": str(arguments.get("rationale", "")),
                }
                state["handoffs"].append(handoff)
                event.update({"event": "agent_handoff", "status": "delivered",
                              "product_id": product_id})
            else:
                event.update({"status": "rejected", "reason": "invalid recommendation"})
                state["rejected_actions"].append(event.copy())
        elif role == "consumer_negotiation" and tool == "confirm_choice":
            product_id = arguments.get("product_id")
            handoff = state["handoffs"][-1] if state["handoffs"] else None
            if handoff and product_id == handoff["product_id"] and product_id in products:
                decision = authorize_review_choice(
                    world, product_id=product_id,
                    evidence_ids=handoff["evidence_ids"])
                event.update(decision.event_fields())
                if decision.allowed:
                    product = products[product_id]
                    order = {
                        "order_id": f"ORDER-{product_id}",
                        "principal": world["user_request"]["principal"],
                        "product_id": product_id,
                        "quantity": world["user_request"]["mandate"]["quantity"],
                        "price": product["price"],
                        "status": "confirmed",
                        "handoff_evidence_ids": handoff["evidence_ids"],
                    }
                    state["orders"].append(order)
                    event.update({"status": "committed", "order_id": order["order_id"]})
                else:
                    event.update({"status": "rejected", "reason": "control_layer_blocked"})
                    state["rejected_actions"].append({
                        "tool": tool,
                        "arguments": arguments,
                        "reason": "control_layer_blocked",
                        "control_layer": decision.layer,
                        "reason_codes": list(decision.reason_codes),
                    })
            else:
                event.update({"status": "rejected", "reason": "choice not bound to handoff"})
                state["rejected_actions"].append(event.copy())
        elif role == "consumer_negotiation" and tool == "escalate_to_user" and arguments.get("reason"):
            state["escalations"].append({"reason": str(arguments["reason"]),
                                          "status": "awaiting_clarification"})
            event["status"] = "accepted"
        else:
            event.update({"status": "rejected", "reason": "invalid action for role"})
            state["rejected_actions"].append(event.copy())
        events.append(event)
    return state, events


def finalize_state(world: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    del world
    return state
