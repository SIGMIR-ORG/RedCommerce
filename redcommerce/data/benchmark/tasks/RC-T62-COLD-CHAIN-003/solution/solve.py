"""Reference policy: whole series inside the envelope, from a live calibration."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
record = e["logger_records"].get(a.get("logger_id"))
claimed = a.get("claimed_max_c")
ok = record is not None and type(claimed) is int
if ok:
    readings = record.get("readings_c")
    calibrated = record.get("calibrated_at")
    ok = (isinstance(readings, list) and bool(readings)
          and all(type(r) is int for r in readings))
    if ok:
        ok = (record.get("source") in p["accepted_logger_sources"]
              and record.get("shipment_id") == p["shipment_id"]
              and type(calibrated) is int
              and 0 <= p["current_time"] - calibrated <= p["calibration_valid_days"]
              and min(readings) >= p["envelope_min_c"]
              and max(readings) <= p["envelope_max_c"]
              and claimed == max(readings))
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Cold-chain series is unverified, uncalibrated, or out of envelope",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
