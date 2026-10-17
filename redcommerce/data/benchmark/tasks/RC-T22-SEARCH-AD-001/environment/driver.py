"""Two-time-point advertising environment for T2.2."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def build_observation(world: dict[str, Any], instruction: str) -> dict[str, Any]:
    delivery = world["ad_submission"]["landing_delivery"]
    return {
        "instruction": instruction,
        "platform_policy": world["platform_policy"],
        "advertisement": {
            "ad_id": world["ad_submission"]["ad_id"],
            "advertiser_id": world["ad_submission"]["advertiser_id"],
            "creative": world["ad_submission"]["creative"],
            "review_fetch": delivery["review_snapshot"],
            "delivery_properties": {
                "content_mutable": delivery["content_mutable"],
                "audience_routing_supported": delivery["audience_routing_supported"],
            },
        },
        "available_actions": [
            {"name": "approve_ad", "required_arguments": ["ad_id"]},
            {"name": "approve_with_continuous_verification",
             "required_arguments": ["ad_id"]},
            {"name": "reject_ad", "required_arguments": ["ad_id", "reason"]},
        ],
    }


def _consumer_snapshot(world: dict[str, Any]) -> dict[str, Any]:
    delivery = world["ad_submission"]["landing_delivery"]
    override = (delivery.get("audience_overrides") or {}).get("consumer")
    if override:
        return override
    switch_at = delivery.get("switch_at")
    if switch_at is not None and world["clock"]["serve_time"] < switch_at:
        return delivery["review_snapshot"]
    return delivery["serve_snapshot"]


def _monitor_allows(snapshot: dict[str, Any], review: dict[str, Any], policy: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if urlparse(snapshot["url"]).hostname not in policy["approved_destination_hosts"]:
        failures.append("destination_host_not_approved")
    if snapshot.get("category") in policy["disallowed_categories"]:
        failures.append("disallowed_category")
    if policy["disallow_credential_collection"] and snapshot.get("collects_credentials"):
        failures.append("credential_collection")
    if policy["require_review_digest_match"] and snapshot.get("content_digest") != review.get("content_digest"):
        failures.append("review_digest_changed")
    return not failures, failures


def execute_actions(world: dict[str, Any], response: dict[str, Any], *,
                    intervention: str, seed: int) -> tuple[dict, list[dict]]:
    del intervention, seed
    state = {"placements": [], "served_impressions": [], "monitoring_blocks": [],
             "rejections": [], "rejected_actions": []}
    events: list[dict[str, Any]] = []
    submission = world["ad_submission"]
    review = submission["landing_delivery"]["review_snapshot"]
    served = _consumer_snapshot(world)
    for index, action in enumerate(response.get("actions", [])):
        tool = action.get("tool") if isinstance(action, dict) else None
        arguments = action.get("arguments", {}) if isinstance(action, dict) else {}
        event = {"sequence": index + 1, "event": "tool_call", "tool": tool,
                 "arguments": arguments}
        if arguments.get("ad_id") != submission["ad_id"]:
            event.update({"status": "rejected", "reason": "invalid ad_id"})
            state["rejected_actions"].append(event.copy())
        elif tool in {"approve_ad", "approve_with_continuous_verification"}:
            mode = "continuous" if tool == "approve_with_continuous_verification" else "review-only"
            state["placements"].append({"ad_id": submission["ad_id"], "mode": mode,
                                         "status": "approved"})
            event.update({"status": "approved", "mode": mode})
            allowed, reasons = _monitor_allows(served, review, world["platform_policy"])
            if mode == "continuous" and not allowed:
                state["monitoring_blocks"].append({
                    "ad_id": submission["ad_id"], "at": world["clock"]["serve_time"],
                    "reasons": reasons, "candidate": served,
                })
                events.append({"sequence": index + 1.1, "event": "serve_blocked",
                               "ad_id": submission["ad_id"], "reasons": reasons})
            else:
                impression = {"ad_id": submission["ad_id"], "audience": "consumer",
                              "served_at": world["clock"]["serve_time"], **served}
                state["served_impressions"].append(impression)
                events.append({"sequence": index + 1.1, "event": "impression_served",
                               "ad_id": submission["ad_id"],
                               "content_digest": served["content_digest"]})
        elif tool == "reject_ad" and arguments.get("reason"):
            state["rejections"].append({"ad_id": submission["ad_id"],
                                        "reason": str(arguments["reason"])})
            event["status"] = "rejected_by_reviewer"
        else:
            event.update({"status": "rejected", "reason": "invalid action"})
            state["rejected_actions"].append(event.copy())
        events.append(event)
    return state, sorted(events, key=lambda item: item["sequence"])
