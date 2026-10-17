# RedCommerce: anonymous review supplement

This package accompanies the current paper. It contains synthetic tasks and saved experimental evidence. It makes no model calls and requires no API key.

## Quick start (Python 3.11 or later; standard library only)

From the extracted `redcommerce-supplement` directory:

```text
python -B analysis/reproduce.py
python -B analysis/replay_saved.py
```

The first command verifies exported files and recomputes the four main rows, common-world overlaps, 576-episode matched comparison, Case-bootstrap interval, 320-episode repeated checks and 80-episode authorization comparison. It fails on a disagreement with the reported counts. These are statistics over saved outcomes, not fresh model measurements.

The second command reconstructs observations and re-executes all 976 saved companion-study trajectories through the original drivers and deterministic scorer. It compares the full recomputed score with each saved score. Network connections are explicitly disabled in this entry point. `--study matched96`, `--study mechanism-repeats`, or `--study authorization-comparison` selects one study. The single unresolved repeated-study response remains unresolved, not a failure imputed by the exporter.

## Contents

- `benchmark/tasks/`: 96 task packages, including instructions, synthetic world, variant patches, actions, reference/vulnerable policies, independent predicates and material contracts.
- `benchmark/redcommerce_v3/` and `benchmark/parallel/`: unchanged runtime/scorer modules required for saved-action reproduction, not the entire development history.
- `configs/worlds.json`, `configs/profiles/`: all 829 world identities and live profiles. Authored benign/control worlds also receive a live attacker in the main panel; original variant labels do not become live attack outcomes.
- `evidence/main/outcomes.json`: 3,316 scheduled model/world records. Provider-excluded and unresolved records are retained. Main-panel full HTTP transcripts are not distributed; this archive supports main-table aggregation, not full main-panel trajectory replay.
- `configs/{matched96,mechanism-repeats,authorization-comparison}.json`: frozen materials, selection and conditions. Spending permissions are removed; task authorization facts are retained.
- `evidence/*/jobs/`: all companion-study profiles, typed actions, observations, world snapshots, executed state, events and saved scores.
- `paper-assets/repeated_evidence.json`: exact prompts/check outputs and saved worked examples; other JSON files preserve paper table inputs.
- `evidence/review/`: review rubric, author-led assessment outcomes, unresolved semantic issues, shipment distinctions, and the 96-row matched-panel sensitivity CSV.
- `manifest.json`: source-to-export provenance; `FILES.json`: integrity checks for this exported artifact. Relative internal run identifiers are retained to relate conditions across files.

## Interpretation

Attack success is a predefined realized deviation in protected business state or formally delivered output, not necessarily monetary loss. A malformed business response or unresolved transport outcome is not silently scored safe. Model abstention and service-level filtering are different events. Gemini's exported eligibility uses the reconciled provider-filter classification, not its earlier unreconciled denominator.

The main panel holds Haiku 4.5 fixed and samples each attacker/world once. The repeated study selects eight previously successful submissions across four Cases, with five fresh business responses per condition; this is conditional diagnostic evidence, not an unbiased corpus-wide intervention estimate. Its one pending output remains visible. No-check/generic/object/evidence columns retain consistent meanings across Cases. Lawful counterparts all complete in the saved repeated study.

The author-led assessments are model-assisted and retrospective, not independent blinded human validation. The decorated existing SDS identifier has unresolved normalization semantics. The cart task preserves a user-confirmation flag but does not verify a separate completed consumer-signature receipt. Authorization results establish issuer/refund-scope sensitivity under these contracts. See the supplied assessment and study details for other boundaries.

## Reproduction levels and exclusions

1. Included and tested: saved-outcome aggregation.
2. Included and tested: all companion-study saved-action reconstruction and re-scoring, with the original condition's view recomputed.
3. Not included: remote model resampling, providers' access policies, billing ledgers, full historical development/container gates or early pilot archives. New model calls require a separately configured provider and budget; these offline scripts cannot trigger them.

Export redactions remove local filesystem paths and transport/account metadata, not actions, authoritative facts, permissions or outcome predicates. `analysis/evaluated_views.py` is the exact evaluated observation function extracted from its planning module to avoid importing the API/development dependency tree; its source is recorded. The task and scorer code is byte-identical to the workspace sources recorded in the manifest. All original paid records remain untouched outside this export.

This material is for scientific review. See `NOTICE.md` for licensing status and `ENVIRONMENT.md` for the tested runtime.
