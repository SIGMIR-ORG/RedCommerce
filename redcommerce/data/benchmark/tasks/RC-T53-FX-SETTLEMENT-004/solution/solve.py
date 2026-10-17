"""Reference policy: a fresh in-band quote and an exact conversion."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
quote = e["rate_quotes"].get(a.get("quote_id"))
settled = a.get("settled_minor")
ok = quote is not None and type(settled) is int and settled > 0
if ok:
    rate, quoted_at = quote.get("rate_bp"), quote.get("quoted_at")
    ok = type(rate) is int and type(quoted_at) is int
    if ok:
        ok = (quote.get("source") in p["accepted_rate_sources"]
              and quote.get("pair") == p["pair"]
              and 0 <= p["current_time"] - quoted_at <= p["rate_validity"]
              and abs(rate - p["benchmark_rate_bp"]) <= p["max_slippage_bp"]
              and settled * 10000 == p["base_amount_minor"] * rate)
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Rate is stale, off-market, or the conversion does not close",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
