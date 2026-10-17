import json, sys
o = json.load(sys.stdin)
json.dump({"actions": [{"tool": "apply_discount", "arguments": {"resource_id": o["operation"]["resource_id"]}}]}, sys.stdout)
