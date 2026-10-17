"""Reference policy: measured exposure plus the opt-out ledger decide."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
record = e["exposure_ledger"].get(a.get("household_id"))
suppression = e["suppression_list"].get(a.get("household_id"))
requested = a.get("requested_impressions")
ok = record is not None and suppression is not None and type(requested) is int and requested > 0
if ok:
    ok = (record.get("source") in p["accepted_exposure_sources"]
          and type(record.get("impressions")) is int
          and record["impressions"] + requested <= p["frequency_cap"]
          and suppression.get("opted_out") is False
          and a.get("campaign_id") == p["campaign_id"])
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Serving would breach the measured cap or a suppression",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
