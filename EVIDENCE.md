# Evidence and version boundaries

The dataset under `redcommerce/data` is the frozen exported artifact associated with the submitted paper. Its `FILES.json` verifies the exported source and evidence. `SOURCE_PROVENANCE.json` records the added persistent-ledger module and the origin of evaluated instruction amendments.

* 96 task packages and 829 world profiles.
* 3,316 scheduled main model/world outcome records, including exclusions and unresolved outcomes.
* 576 matched-input trajectories, 320 repeated-mechanism configurations, and 80 authorization trajectories.
* Per-Case author-led assessments, exact check outputs and worked examples, and specification sensitivity records.

The original predicates are distributed as evaluated, including known specification-sensitive behavior. Public runtime wrappers do not alter task drivers or scorers. The original review-package README and notice remain under `redcommerce/data` as provenance; this repository's README describes the added execution interface.

Main-table reproduction aggregates saved records. Companion-study replay reconstructs observations, world snapshots, actions, state and full deterministic scores. Remote resampling cannot guarantee identical model outputs. Offline reference/vulnerable policies and simulated clients are software checks, not empirical model performance.

Future task corrections should receive a dataset version and revised source manifest. They should be reported separately from the frozen paper results.
