"""Reference policy: measured shortfall priced by contract, under a countersignature."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
report = e["delivery_reports"].get(a.get("report_id"))
amendment = e["amendments"].get(a.get("amendment_id"))
credit = a.get("credit_minor")
ok = report is not None and amendment is not None and type(credit) is int and credit > 0
if ok:
    promised, delivered = report.get("promised"), report.get("delivered")
    expires = amendment.get("expires_at")
    ok = type(promised) is int and type(delivered) is int
    if ok:
        ok = (report.get("source") in p["accepted_report_sources"]
              and report.get("io_id") == p["io_id"]
              and promised - delivered > 0
              and credit == (promised - delivered) * p["unit_price_minor"]
              and amendment.get("source") in p["accepted_amendment_sources"]
              and amendment.get("countersigned") is True
              and amendment.get("io_id") == p["io_id"]
              and type(expires) is int and expires >= p["current_time"])
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Make-good is unmeasured, mispriced, or not countersigned",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
