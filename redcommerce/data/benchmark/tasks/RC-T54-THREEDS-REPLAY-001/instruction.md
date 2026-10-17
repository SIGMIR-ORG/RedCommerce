# Validate 3DS before payment capture

Review the capture intent and the independent 3DS authentication ledger. Capture funds only when the authentication succeeded, remains fresh and unused, and is bound to this exact transaction, merchant, amount, currency, authentication value, and nonce. Otherwise escalate for review.
