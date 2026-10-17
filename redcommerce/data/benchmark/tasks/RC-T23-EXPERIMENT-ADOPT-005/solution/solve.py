"""Reference policy: the pre-registered metric, enough exposure, a positive lift."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
readout = e["readouts"].get(a.get("readout_id"))
adopted = a.get("adopted_metric")
ok = readout is not None and isinstance(adopted, str)
if ok:
    exposures, lift = readout.get("exposures"), readout.get("lift_bp")
    ok = (readout.get("source") in p["accepted_readout_sources"]
          and readout.get("experiment_id") == p["experiment_id"]
          and adopted == p["preregistered_metric"]
          and readout.get("metric") == adopted
          and type(exposures) is int and exposures >= p["minimum_exposures"]
          and type(lift) is int and lift > 0)
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Readout does not show a pre-registered, powered, positive win",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
