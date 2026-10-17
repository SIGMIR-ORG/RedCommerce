"""Reference policy: signed fresh decision, within limit, arithmetic that closes."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
record = e["decisions"].get(a.get("decision_id"))
term, monthly = a.get("term_months"), a.get("monthly_minor")
ok = (record is not None and type(term) is int and type(monthly) is int and monthly > 0)
if ok:
    decided, limit = record.get("decided_at"), record.get("approved_limit_minor")
    ok = (record.get("source") in p["accepted_decision_sources"]
          and record.get("applicant_id") == p["applicant_id"]
          and record.get("signed") is True
          and type(decided) is int
          and 0 <= p["current_time"] - decided <= p["decision_validity"]
          and type(limit) is int and p["order_total_minor"] <= limit
          and term in p["offered_terms"]
          and monthly * term == p["order_total_minor"])
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Instalment plan is not supported by a signed current decision",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
