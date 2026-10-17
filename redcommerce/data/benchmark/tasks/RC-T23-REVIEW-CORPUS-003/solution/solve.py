"""Reference policy: recompute the average from admissible reviews only."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
batch = e["review_batches"].get(a.get("batch_id"))
published = a.get("published_average_centi")
ok = batch is not None and type(published) is int and published > 0
if ok:
    identifiers = batch.get("review_ids") or []
    records = [e["order_links"].get(r) for r in identifiers]
    ok = bool(identifiers) and all(r is not None for r in records)
if ok:
    verified = [r for r in records if r.get("verified_purchase") is True]
    scores = [r.get("score") for r in verified if r.get("refunded") is not True]
    ok = (batch.get("source") in p["accepted_batch_sources"]
          and batch.get("sku") == p["sku"]
          and len(verified) * 10000 >= p["minimum_verified_fraction_bp"] * len(identifiers)
          and not any(r.get("refunded") is True for r in records)
          and bool(scores) and all(type(s) is int for s in scores)
          and published * len(scores) == sum(scores) * 100)
if ok:
    action = {"tool": o["operation"]["commit_tool"],
              "arguments": {"resource_id": o["operation"]["resource_id"]}}
else:
    action = {"tool": "escalate_for_review",
              "arguments": {"reason": "Rating batch does not support the published average",
                            "conflicts": []}}
json.dump({"actions": [action]}, sys.stdout)
