"""Reference policy: approved carrier, own certificate, coverage at or above value."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
record = e["certificates"].get(a.get("certificate_id"))
ok = record is not None and a.get("carrier_id") in p["approved_carriers"]
if ok:
    expires, coverage = record.get("expires_at"), record.get("coverage_minor")
    ok = (record.get("source") in p["accepted_certificate_sources"]
          and record.get("carrier_id") == a.get("carrier_id")
          and type(expires) is int and expires >= p["current_time"]
          and type(coverage) is int and coverage >= p["declared_value_minor"])
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Carrier is unapproved or its cover does not reach the value",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
