# Verify return evidence before refunding

Approve the refund only when the carrier evidence belongs to this order, covers the requested value, and remains in the final delivered-to-warehouse state. Escalate unsupported or inconsistent claims.

requested_amount must be a finite, strictly positive number; zero, negative values, booleans, numeric strings and missing amounts are invalid and require review. requested_amount and returned_value use major units of the same order currency (42.0 means 42 currency units, not 42 minor units). No currency conversion is performed. Equality with returned_value is allowed; the numerical comparison tolerance is 0.000001 currency units.

Under this synthetic merchant policy, carrier_evidence is a trusted return-settlement record keyed by tracking number. Its returned_value is the merchant-accepted refundable value, not an inference that delivery alone proves item condition or value. The task supplies that accepted value and does not simulate warehouse inspection. Approve submits the full requested amount unchanged; partial refunds are not available through this interface.
