from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
required = ("shipment_wave_id", "carrier_scac", "service_level", "lane_id", "origin_facility_id", "destination_facility_id")
actions = ([{"tool": "create_shipment", "arguments": {"resource_id": a["shipment_wave_id"]}}]
           if all(a.get(field) for field in required) else [])
json.dump({"actions": actions}, sys.stdout)
