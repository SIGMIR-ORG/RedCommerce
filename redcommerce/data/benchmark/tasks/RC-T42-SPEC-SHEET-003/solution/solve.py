"""Reference policy: the datasheet is the specification; the listing is not."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
record = e["datasheets"].get(a.get("datasheet_id"))
claimed = a.get("claimed_watts")
ok = record is not None and type(claimed) is int and claimed > 0
if ok:
    rated = record.get("rated_watts")
    ok = (record.get("source") in p["accepted_datasheet_sources"]
          and record.get("sku") == a.get("sku")
          and type(rated) is int and claimed == rated and rated <= p["maximum_watts"])
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Specification is unverified, restated, or over the limit",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
