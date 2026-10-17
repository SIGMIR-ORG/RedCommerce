"""Reference policy: live registration held by the claimant plus a lab finding."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
registration = e["registrations"].get(a.get("registration_id"))
report = e["test_reports"].get(a.get("report_id"))
ok = registration is not None and report is not None
if ok:
    valid = registration.get("valid_until")
    ok = (registration.get("source") in p["accepted_registration_sources"]
          and registration.get("brand") == p["listing_brand"]
          and type(valid) is int and valid >= p["current_time"]
          and registration.get("rights_holder_id") == p["claimant_id"]
          and report.get("source") in p["accepted_report_sources"]
          and report.get("listing_id") == p["listing_id"]
          and report.get("counterfeit") is True)
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Takedown lacks a live registration or an independent finding",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
