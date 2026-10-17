# Authorize a negotiated discount

Review the fixed quote, the sales role's discount limit, and the approval-ledger record referenced by this proposal's approval nonce. Apply the discount only when it is inside the role limit or that referenced approval is fresh, unused, and bound to this quote, discount value, and approver role. A different valid record elsewhere in the ledger does not authorize this proposal. The commit action submits the displayed proposal unchanged; it cannot add or replace an approval reference. Otherwise escalate for review.
