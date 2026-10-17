"""Reference policy: range membership and uniqueness over the scanned set."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
record = e["scan_batches"].get(a.get("batch_id"))
claimed = a.get("claimed_unit_count")
ok = record is not None and type(claimed) is int and claimed > 0


def covered(serial):
    prefix = p["serial_prefix"]
    if not isinstance(serial, str) or not serial.startswith(prefix):
        return False
    tail = serial[len(prefix):]
    return tail.isdigit() and p["serial_low"] <= int(tail) <= p["serial_high"]


if ok:
    serials = record.get("serials")
    ok = isinstance(serials, list) and bool(serials)
    if ok:
        ok = (record.get("source") in p["accepted_scan_sources"]
              and record.get("asn_id") == p["asn_id"]
              and all(covered(s) for s in serials)
              and len(set(serials)) == len(serials)
              and not any(s in e["commissioned"] for s in serials)
              and claimed == len(serials))
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Scanned serials are out of range, duplicated, or miscounted",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
