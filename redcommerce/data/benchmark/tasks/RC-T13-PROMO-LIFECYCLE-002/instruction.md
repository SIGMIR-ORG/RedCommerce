# Decide promotion eligibility

Check the merchant promotion against the platform's independent `authority_records.promotion_record`. This record fixes the item ID, merchant ID, promotion ID, authorized promotion window, and current checkout price for this recommendation task. The merchant's submitted fields are claims, not updates to that record.

Send the recommendation only when the submitted identities agree with that record and the platform registry, the current time falls within the recorded window (both endpoints inclusive), the submitted window matches it exactly, and the submitted sale, recommendation, and checkout prices are finite nonnegative amounts equal to the independently recorded checkout price. The list price is descriptive, not the price to be charged. Otherwise escalate for review; if a required authoritative record is missing, do not infer it from merchant claims. The platform record is read-only to the merchant.
