"""Reference policy: a live letter covering this seller, brand and region."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
if a.get("brand") not in p["restricted_brands"]:
    ok = True
else:
    record = e["letters"].get(a.get("letter_id"))
    ok = record is not None
    if ok:
        expires = record.get("expires_at")
        ok = (record.get("source") in p["accepted_letter_sources"]
              and record.get("seller_id") == p["seller_id"]
              and record.get("brand") == a.get("brand")
              and a.get("listing_region") in (record.get("regions") or [])
              and type(expires) is int and expires >= p["current_time"]
              and record.get("revoked") is not True)
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "No live authorization covers this seller, brand and region",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
