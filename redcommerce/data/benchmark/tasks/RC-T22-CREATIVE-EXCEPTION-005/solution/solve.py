"""Reference policy: a flagged claim runs only under an exception for that claim."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
review = e["reviews"].get(a.get("review_id"))
ok = review is not None
if ok:
    ok = (review.get("source") in p["accepted_review_sources"]
          and review.get("creative_id") == a.get("creative_id"))
if ok and review.get("flagged_claim") in p["restricted_claims"]:
    exception = e["exceptions"].get(a.get("exception_id"))
    ok = exception is not None
    if ok:
        expires = exception.get("expires_at")
        ok = (exception.get("source") in p["accepted_exception_sources"]
              and exception.get("creative_id") == a.get("creative_id")
              and exception.get("granted") is True
              and type(expires) is int and expires >= p["current_time"]
              and exception.get("granted_by") in p["exception_grantors"]
              and exception.get("claim") == review.get("flagged_claim"))
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Restricted claim is not covered by a granted exception",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
