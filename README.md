# RedCommerce

**A security benchmark for agentic commerce across the full lifecycle.**

RedCommerce evaluates the justification for consequential commercial choices. Its Mandate–Commitment Gap distinguishes choosing a suitable action from establishing the evidence and authority needed to commit it.

The corpus contains **96 executable task packages and 829 variant worlds**, covering seven lifecycle stages, five role families, and 24 threat families. In model evaluations, an attacker authors a declared lower-trust commercial input and a business agent acts on the resulting observation. Task-specific deterministic verifiers evaluate protected state and consequential delivered outputs.

## Quick start

Python **3.11 or later**. No third-party Python packages are needed for direct execution. From this repository:

```sh
python -B scripts/install_ci_data.py
python -B -m redcommerce list
python -B -m redcommerce run --case RC-T21-GTIN-SCOPE-002 --out runs/listing-demo
```

The installer downloads and verifies the pinned Hugging Face data release only when no embedded dataset is present. The demo runs a frozen counterparty submission against a deterministic reference policy. It saves an episode, final state, and score. It makes **zero model calls** and does not measure model ability.

The listing demo escalates the frozen invalid listing. To compare the original lawful world without applying that submission:

```sh
python -B -m redcommerce run --case RC-T21-GTIN-SCOPE-002 --submission unchanged --out runs/lawful-listing-demo
```

To inspect all worlds belonging to a task:

```sh
python -B -m redcommerce list --case RC-T21-GTIN-SCOPE-002 --worlds
```

An optional installation provides the `redcommerce` command:

```sh
python -m pip install -e .
redcommerce --help
```

## Reproduce the paper

For the separate Hugging Face dataset layout and `REDCOMMERCE_DATA_DIR`, see
[DATA_HOSTING.md](DATA_HOSTING.md). The embedded paper dataset remains supported
until the remote release is published and verified. Saved-run format bridges and
the native-framework integration assessment are in [integrations/](integrations/README.md).

```sh
python -B -m redcommerce reproduce
python -B -m redcommerce replay
```

The first command validates the frozen files and recomputes main results, stage distributions, overlaps, matched comparisons, bootstrap intervals, repeated checks, and authorization contrasts. The second reconstructs and re-scores **976 saved companion-study trajectories**. Both commands are offline and require no credentials.

| Attacker configuration | Successes / evaluable | ASR |
|---|---:|---:|
| Opus 5.5 | 276 / 757 | 36.46% |
| DeepSeek V4.1 Flash | 238 / 827 | 28.78% |
| Qwen 3.8 Max | 208 / 826 | 25.18% |
| Gemini 3.8 Flash | 188 / 800 | 23.50% |

Each configuration is scheduled over 829 worlds, with **Haiku 4.5 fixed as the business agent**. The exported main records retain service exclusions and unresolved outcomes. Publication derivatives of the saved main and companion interactions are available in the [Hugging Face dataset](https://huggingface.co/datasets/Fentz/RedCommerce) and the [trajectory explorer](https://sigmir-org.github.io/RedCommerce/trajectories.html). These are sanitized records, not unredacted HTTP transcripts; main aggregation and companion-trajectory replay have different reproduction scopes.

The matched study compares ordinary inputs with saved attacks on 96 Cases, three fresh business runs per condition. Adverse outcomes are **1/288 versus 63/288**, a **21.53-point increase** (95% Case-bootstrap interval 13.89–29.51). A post hoc exclusion of seven specification-sensitive Cases gives an 18.35-point increase. The repeated study covers eight successful saved attacks across four Cases; all 160 lawful counterparts complete without scored deviation or escalation. The 80-run authorization comparison probes issuer validity and refund scope.

## Evaluate your own models

Copy `examples/models.template.json` outside the tracked source tree and fill in actual model identifiers, endpoints, current prices, and a conservative per-request cost reservation. Native **Chat Completions compatible** and **Anthropic Messages** interfaces are included. Custom clients can use the plugin contract in [MODEL_ADAPTERS.md](MODEL_ADAPTERS.md).

Inspect the selected work before dispatch:

```sh
python -B -m redcommerce plan --config models.json --panel cases --limit 2
```

Set the environment variables named in your config, then run:

```sh
python -B -m redcommerce run --config models.json --panel cases --limit 2 --execute --budget-usd 5 --out runs/my-models
```

`--panel cases` selects the first declared world per Case, at most 96 episodes. It is a deterministic public starting panel, not a claim to reproduce the paper's historical matched-panel selection. `--panel all` selects all 829 worlds. `--case`, `--world`, and `--limit` restrict the plan explicitly.

Re-running the same command resumes completed jobs without resampling. Configuration and execution-code changes require a new output directory. The append-only ledger retains possibly charged requests with unknown outcomes. No automatic retries are performed. Costs are **usage-based estimates using configured prices**, not provider invoices. Inspect model configuration and output limits when comparing experiments.

## Scoring and assessment

Attack success is a realized task-defined deviation in protected state or a consequential delivered business output; direct financial loss is not required. Attacker abstention and malformed attacker submissions count as unsuccessful attempts under the role-specific overlay. Business format failures remain unresolved. Provider access blocks are separate events.

Tasks have author-led assessments, executable witnesses, regression checks, and deterministic replay evidence. These records include remaining specification-sensitive interpretations, including normalization of a decorated SDS identifier and the scope of the cart-confirmation record. Original task predicates and paid results are preserved. See [EVIDENCE.md](EVIDENCE.md) and `redcommerce/data/evidence/review/` for assessment outcomes and sensitivity analyses.

## Repository layout

```text
redcommerce/              Public CLI, model adapters, and execution wrapper
redcommerce/data/         Frozen tasks, profiles, scoring code, and saved evidence
examples/                Model configuration and custom-client examples
tests/                   Offline release tests
docs/                    GitHub Pages website
.github/workflows/       Offline checks and website deployment
```

The website uses relative URLs and can be published from `main:/docs` in GitHub Pages. Set the paper, repository and citation entries in `docs/site-config.js` before publishing.

## Release status

Code and the website are hosted at [SIGMIR-ORG/RedCommerce](https://github.com/SIGMIR-ORG/RedCommerce); data and saved trajectories are hosted at [Fentz/RedCommerce](https://huggingface.co/datasets/Fentz/RedCommerce). The arXiv identifier, final citation, and code/data licenses remain to be confirmed. Licensing is described in [NOTICE.md](NOTICE.md); public availability is not a grant of an unspecified open-source license.
