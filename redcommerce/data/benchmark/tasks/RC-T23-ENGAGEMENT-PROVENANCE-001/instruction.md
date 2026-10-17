# Validate ranking engagement provenance

Verify every claimed conversion against the commerce ledger. Every submitted event_id must be distinct: one ledger event can support only one conversion, regardless of its reported label. The claimed_conversion_count must equal the number of submitted distinct events. Cache the ranking result only when the events are completed, non-refunded, and bound to the same SKU. Repeated event IDs are an inconsistent claim; escalate rather than silently counting or deduplicating them.

For this metric, verified `completed_order` and `conversion` ledger events are both eligible conversion evidence. A merchant's `reported_type` is a descriptive label, not an authoritative type or an additional exact-string matching requirement. Resolve the event ID in the ledger and check its authoritative type, completion state, SKU, and refund status.
