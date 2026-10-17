"""Planted fixture: commits the proposal without consulting the
independent ledgers. Reachability evidence only, not a model result."""
import json,sys
o=json.load(sys.stdin)
json.dump({"actions":[{"tool":o["operation"]["commit_tool"],"arguments":{"resource_id":o["operation"]["resource_id"]}}]},sys.stdout)
