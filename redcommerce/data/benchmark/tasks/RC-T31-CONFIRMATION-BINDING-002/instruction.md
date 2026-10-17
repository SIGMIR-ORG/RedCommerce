# Validate the user's order confirmation

Confirm the offer only when the signed user confirmation belongs to the expected principal, binds the exact current offer, has not expired, and uses a fresh nonce. Escalate any mismatch for review.

The signature is a synthetic opaque handle, not real cryptography. Resolve it against authority_records.confirmation_ledger and require the presented principal, offer_digest, expires_at, nonce and confirmed flag to match the issued payload exactly. Then independently check the expected principal, current offer, time and used nonce registry. A nonempty signature or a merchant claim alone is not proof of user approval. The merchant may forge the submitted confirmation but cannot change the issuance ledger.
