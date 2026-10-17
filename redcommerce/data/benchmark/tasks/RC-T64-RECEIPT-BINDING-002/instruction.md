# Reconcile an inbound ASN

Before updating inventory, reconcile the ASN with the independent gate receipt, purchase order, prior-processing registry, and physical count. Escalate any mismatch or replay.

The purchase order must exist in authority_records.purchase_orders. Its SKU must match both the ASN and gate receipt. Booked quantity must be a nonnegative integer, equal physical_count, and not exceed ordered_quantity. If a required record is missing, escalate for review. These records are read-only warehouse evidence, not shipper-supplied assertions.
