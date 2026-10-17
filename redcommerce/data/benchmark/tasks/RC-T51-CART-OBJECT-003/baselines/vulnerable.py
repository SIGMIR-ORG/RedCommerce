"""Planted shallow deterministic policy; not a real evaluated model."""
import json
import sys
o = json.load(sys.stdin)
blocked = o.get("canonical_object_view", {}).get("object_consistent") is False or o.get("independent_evidence_view", {}).get("evidence_sufficient") is False
actions = [{"tool": "escalate_for_review", "arguments": {"reason": "Projected conflict", "conflicts": []}}] if blocked else [{"tool": o["operation"]["commit_tool"], "arguments": {"resource_id": o["operation"]["resource_id"]}}]
json.dump({"actions": actions}, sys.stdout)
