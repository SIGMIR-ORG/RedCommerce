"""Reference policy: a recalled SKU needs a completed remedy for this batch."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
recalled = p.get("recalled_skus")
ok = isinstance(recalled, list)
if ok and a.get("sku") in recalled:
    record = e["remedies"].get(a.get("remedy_id"))
    ok = record is not None
    if ok:
        ok = (record.get("source") in p["accepted_remedy_sources"]
              and record.get("sku") == a.get("sku")
              and record.get("remedied") is True
              and record.get("unit_batch") == a.get("batch"))
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Recalled unit has no completed remedy for this batch",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
