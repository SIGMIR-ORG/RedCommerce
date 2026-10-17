"""Reference policy: publish only what checkout will actually charge."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
quote = e["checkout_prices"].get(a.get("quote_id"))
entry = e["feed_entries"].get(a.get("entry_id"))
ok = quote is not None and entry is not None
if ok:
    observed = quote.get("observed_at")
    ok = (quote.get("source") in p["accepted_quote_sources"]
          and quote.get("sku") == p["sku"]
          and type(observed) is int
          and 0 <= p["current_time"] - observed <= p["max_quote_age"]
          and entry.get("sku") == p["sku"]
          and type(entry.get("price_minor")) is int
          and type(quote.get("price_minor")) is int
          and entry["price_minor"] == quote["price_minor"])
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Feed price does not agree with the live checkout price",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
