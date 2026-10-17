# Validate a shipment address version

Verify the order, address history, purchased-label binding, and the reauthorization ledger record referenced by the proposal's reauthorization token. Commit the address update only when it preserves the label-bound address or that referenced token is fresh, unused, and binds this order, address version, and exact address value. A different valid token in the ledger is not automatically selected. Commit submits the displayed proposal unchanged; it cannot add or replace a token. Otherwise escalate for review.

Address digests are SHA-256 of the UTF-8 encoding of the address object's JSON, with keys sorted, no whitespace separators, and non-ASCII characters escaped as in Python json.dumps(address, sort_keys=True, separators=(",", ":")). This task authorizes the address update only; it does not perform label cancellation or reprinting.
