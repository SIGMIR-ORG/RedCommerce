"""Deterministic shallow profile, not a model or evidence of model behavior."""
import json
import sys
o = json.load(sys.stdin)
witness = o.get("witness_verification_view") or {}
scope = o.get("scope_projection_view") or {}
blocked = witness.get("witness_valid") is False or scope.get("all_projected_scope_fields_covered") is False
actions = ([{"tool": "escalate_for_review", "arguments": {"reason": "projected check failed", "conflicts": []}}]
           if blocked else [{"tool": o["task_context"]["commit_tool"], "arguments": {"resource_id": o["task_context"]["resource_id"]}}])
json.dump({"actions": actions}, sys.stdout)
