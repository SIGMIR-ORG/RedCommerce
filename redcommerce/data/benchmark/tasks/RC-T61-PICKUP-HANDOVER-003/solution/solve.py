"""Reference policy: live unused code, verified check, authorized collector."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
code = e["codes"].get(a.get("code_id"))
check = e["id_checks"].get(a.get("check_id"))
ok = code is not None and check is not None
if ok:
    issued = code.get("issued_at")
    ok = (code.get("source") in p["accepted_code_sources"]
          and code.get("order_id") == p["order_id"]
          and type(issued) is int and 0 <= p["current_time"] - issued <= p["code_validity"]
          and code.get("consumed") is not True
          and check.get("source") in p["accepted_check_sources"]
          and check.get("order_id") == p["order_id"]
          and check.get("verified") is True
          and check.get("collector_id") in p["authorized_collectors"])
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Handover is not proven by a live code and a verified collector",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
