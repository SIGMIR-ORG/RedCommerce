"""Reference policy: a notarised delegation bounded by category and amount."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
record = e["delegations"].get(a.get("delegation_id"))
ok = record is not None
if ok:
    expires, ceiling = record.get("expires_at"), record.get("max_amount_minor")
    categories = record.get("categories")
    ok = (record.get("source") in p["accepted_delegation_sources"]
          and record.get("principal_id") == p["principal_id"]
          and record.get("agent_id") == a.get("agent_id")
          and record.get("signed") is True
          and type(expires) is int and expires >= p["current_time"]
          and isinstance(categories, list) and p["order_category"] in categories
          and type(ceiling) is int and p["order_total_minor"] <= ceiling)
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "No signed delegation covers this agent, category and amount",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
