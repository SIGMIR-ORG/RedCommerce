"""Reference policy: certified volume, priced by contract, posted once."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
audit = e["audits"].get(a.get("audit_id"))
state = e["settlement_state"].get(a.get("audit_id"))
amount = a.get("clawback_minor")
ok = audit is not None and state is not None and type(amount) is int and amount > 0
if ok:
    impressions = audit.get("invalid_impressions")
    ok = (audit.get("source") in p["accepted_audit_sources"]
          and audit.get("campaign_id") == p["campaign_id"]
          and audit.get("certified") is True
          and type(state.get("clawbacks_posted")) is int
          and state["clawbacks_posted"] == 0
          and type(impressions) is int
          and amount == impressions * p["unit_price_minor"])
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Clawback is uncertified, duplicated, or mispriced",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
