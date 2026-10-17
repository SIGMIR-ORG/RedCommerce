# Contributing

Report a reproducible issue with a Case/world identifier, relevant action, expected behavior under the stated task rule, and actual score. Do not include API credentials, provider account information, or private billing logs.

Task changes need a lawful witness, a deviation witness, an appropriate escalation witness when applicable, and a regression that distinguishes the corrected behavior. Preserve the original evaluated corpus when changing rules or scoring. Source manifests and version identifiers must follow the changed dataset.

For provider adapters, test both business and counterparty observations, every role in chain tasks, valid actions, abstention, malformed output, usage, and uncertain transport outcomes. Use mocked clients for tests; CI should not call paid APIs.

Run the offline tests and reproduction commands before submitting a change. A change to a figure or the website does not require another model sweep.
