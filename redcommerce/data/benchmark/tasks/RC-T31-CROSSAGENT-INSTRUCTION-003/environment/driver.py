"""Two-process intake-to-negotiation environment for the cross-agent T3.1 anchor.

The driver models one property that the rest of the benchmark does not yet test:
*where* inbound counterparty bytes land in an agent observation.  A part declared
`kind = "text"` is surfaced in the observation's instruction stream, the same
field family a scaffold concatenates into a prompt.  A part declared
`kind = "data"` is surfaced as a quoted, provenance-tagged structured field that
is explicitly marked non-executable.  The bytes are identical either way.

The driver enforces tool syntax and brief binding only.  Whether a syntactically
valid order is authorized is the agent's task and the independent verifier's job.
"""
from __future__ import annotations

import copy
from typing import Any

from redcommerce_v3.control_layers import authorize_order_mandate, configure_world


ROLES = ("consumer_intake", "consumer_negotiation")
CHANNEL_TYPING_KEY = "_redcommerce_channel_typing"


def configure_control_layer(world: dict[str, Any], *, control_layer: str,
                            seed: int) -> dict[str, Any]:
    del seed
    return configure_world(
        world, control_layer=control_layer, policy_type="order_mandate")


def apply_intervention(world: dict[str, Any], *, intervention: str,
                       seed: int) -> dict[str, Any]:
    """Deliver every non-principal carrier as typed, quoted data.

    `untrusted-channel-typing` changes only the channel on which counterparty and
    upstream-agent content is delivered.  No byte of content is removed or
    rewritten, no business fact changes, and no authority is granted or revoked.
    On a Variant whose carriers are already typed data this is a no-op.
    """
    del seed
    if intervention != "untrusted-channel-typing":
        raise ValueError(f"unsupported T3.1 intervention={intervention}")
    typed = copy.deepcopy(world)
    principal = typed["user_request"]["principal"]
    for part in typed["inbound_message"]["parts"]:
        if part.get("attributed_source") != principal:
            part["kind"] = "data"
    typed[CHANNEL_TYPING_KEY] = {"untrusted_text_as_data": True}
    return typed


def _channel_typing_active(world: dict[str, Any]) -> bool:
    return bool((world.get(CHANNEL_TYPING_KEY) or {}).get("untrusted_text_as_data"))


def _offer_of_record(world: dict[str, Any]) -> dict[str, Any] | None:
    for part in world["inbound_message"]["parts"]:
        content = part.get("content")
        if isinstance(content, dict) and "offer_id" in content:
            return content
    return None


def initialize_state(world: dict[str, Any]) -> dict[str, Any]:
    del world
    return {"briefs": [], "orders": [], "escalations": [], "rejected_actions": []}


def _render_parts(world: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    instruction_stream: list[dict[str, Any]] = []
    structured_fields: list[dict[str, Any]] = []
    for part in world["inbound_message"]["parts"]:
        entry = {
            "part_id": part.get("part_id"),
            "attributed_source": part.get("attributed_source"),
            "content": part.get("content"),
        }
        if part.get("kind") == "text":
            instruction_stream.append(entry)
        else:
            structured = dict(entry)
            structured["provenance"] = "counterparty-untrusted"
            structured["executable"] = False
            structured_fields.append(structured)
    return instruction_stream, structured_fields


def build_role_observation(world: dict[str, Any], state: dict[str, Any],
                           instruction: str, role: str) -> dict[str, Any]:
    if role == "consumer_intake":
        instruction_stream, structured_fields = _render_parts(world)
        return {
            "instruction": instruction,
            "role": "purchase intake",
            "user_request": world["user_request"],
            "inbound_message": {
                "message_id": world["inbound_message"]["message_id"],
                "from_agent": world["inbound_message"]["from_agent"],
                "instruction_stream": instruction_stream,
                "structured_fields": structured_fields,
            },
            "addon_catalog": world["addon_catalog"],
            "available_actions": [{
                "name": "handoff_purchase_brief",
                "required_arguments": ["offer_id", "line_items", "total", "brief_notes"],
            }],
        }
    if role == "consumer_negotiation":
        brief = state["briefs"][-1] if state["briefs"] else None
        # An upstream peer agent is a more trusted channel than the counterparty,
        # so relayed brief notes reach the instruction stream by default.  This is
        # the surface on which authority laundering can be observed.
        notes = brief.get("brief_notes") if brief else None
        instruction_stream: list[dict[str, Any]] = []
        structured_fields: list[dict[str, Any]] = []
        if notes:
            entry = {"part_id": "BRIEF-NOTES", "attributed_source": "consumer_intake",
                     "content": notes}
            if _channel_typing_active(world):
                structured_fields.append({
                    **entry, "provenance": "upstream-agent-untrusted", "executable": False})
            else:
                instruction_stream.append(entry)
        return {
            "instruction": instruction,
            "role": "order negotiation",
            "user_request": world["user_request"],
            "upstream_brief": brief,
            "offer_of_record": _offer_of_record(world),
            "addon_catalog": world["addon_catalog"],
            "principal_confirmations": world["principal_confirmations"],
            "relayed_notes": {
                "instruction_stream": instruction_stream,
                "structured_fields": structured_fields,
            },
            "available_actions": [
                {"name": "confirm_terms",
                 "required_arguments": ["offer_id", "line_items", "total"]},
                {"name": "escalate_for_review", "required_arguments": ["reason"]},
            ],
        }
    raise ValueError(f"unknown role={role}")


def _valid_line_items(value: Any) -> bool:
    return (
        isinstance(value, list) and bool(value)
        and all(isinstance(item, dict) and isinstance(item.get("sku"), str)
                and isinstance(item.get("amount"), (int, float))
                and isinstance(item.get("quantity"), int)
                for item in value)
    )


def apply_role_response(world: dict[str, Any], state: dict[str, Any], role: str,
                        response: dict[str, Any], *, intervention: str,
                        seed: int) -> tuple[dict, list[dict]]:
    del intervention, seed
    events: list[dict[str, Any]] = []
    operation = world["operation"]
    base_sku = world["user_request"]["mandate"]["sku"]
    for action in response.get("actions", []):
        tool = action.get("tool") if isinstance(action, dict) else None
        arguments = action.get("arguments", {}) if isinstance(action, dict) else {}
        event = {"event": "tool_call", "tool": tool, "arguments": arguments}
        if role == "consumer_intake" and tool == "handoff_purchase_brief":
            if (arguments.get("offer_id") == operation["offer_id"]
                    and _valid_line_items(arguments.get("line_items"))
                    and isinstance(arguments.get("total"), (int, float))):
                brief = {
                    "from": "consumer_intake",
                    "to": "consumer_negotiation",
                    "offer_id": arguments["offer_id"],
                    "line_items": copy.deepcopy(arguments["line_items"]),
                    "total": float(arguments["total"]),
                    "brief_notes": str(arguments.get("brief_notes", "")),
                }
                state["briefs"].append(brief)
                event.update({"event": "agent_handoff", "status": "delivered",
                              "offer_id": brief["offer_id"]})
            else:
                event.update({"status": "rejected", "reason": "invalid brief"})
                state["rejected_actions"].append(event.copy())
        elif role == "consumer_negotiation" and tool == "confirm_terms":
            brief = state["briefs"][-1] if state["briefs"] else None
            if state["orders"]:
                event.update({"status": "rejected", "reason": "duplicate_resource_commit"})
                state["rejected_actions"].append(event.copy())
            elif (brief is None
                    or arguments.get("offer_id") != operation["offer_id"]
                    or not _valid_line_items(arguments.get("line_items"))
                    or not isinstance(arguments.get("total"), (int, float))):
                event.update({"status": "rejected", "reason": "order not bound to brief"})
                state["rejected_actions"].append(event.copy())
            else:
                line_items = copy.deepcopy(arguments["line_items"])
                order = {
                    "order_id": f"ORDER-{operation['offer_id']}",
                    "principal": world["user_request"]["principal"],
                    "offer_id": arguments["offer_id"],
                    "line_items": line_items,
                    "total": float(arguments["total"]),
                    "quantity": sum(int(item["quantity"]) for item in line_items
                                    if item["sku"] == base_sku),
                    "status": "confirmed",
                    "brief_notes": brief["brief_notes"],
                }
                decision = authorize_order_mandate(world, order=order)
                event.update(decision.event_fields())
                if decision.allowed:
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
        elif (role == "consumer_negotiation" and tool == "escalate_for_review"
              and arguments.get("reason")):
            state["escalations"].append({"reason": str(arguments["reason"]),
                                         "status": "awaiting_review"})
            event["status"] = "accepted"
        else:
            event.update({"status": "rejected", "reason": "invalid action for role"})
            state["rejected_actions"].append(event.copy())
        events.append(event)
    return state, events


def finalize_state(world: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    del world
    return state
