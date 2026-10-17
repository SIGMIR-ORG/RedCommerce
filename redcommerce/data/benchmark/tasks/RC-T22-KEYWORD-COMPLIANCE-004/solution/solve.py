"""Reference policy: blocklist, owned verified destination, live bound offer."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
keyword = a.get("keyword")
destination = e["destinations"].get(a.get("destination_id"))
offer = e["offers"].get(a.get("offer_id"))
ok = isinstance(keyword, str) and destination is not None and offer is not None
if ok:
    ok = (keyword.strip().lower() not in p["trademark_blocklist"]
          and destination.get("source") in p["accepted_destination_sources"]
          and destination.get("advertiser_id") == p["advertiser_id"]
          and destination.get("verified") is True
          and destination.get("offer_id") == a.get("offer_id")
          and offer.get("active") is True)
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Keyword or destination fails ad-compliance checks",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
