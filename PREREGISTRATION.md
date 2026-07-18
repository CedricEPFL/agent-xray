# Preregistration — Does Agentic Workflow Structure Earn Its Cost on MATH-500?

**Author:** Cédric (CedricEPFL). **Date:** 2026-07-18. **Status:** FROZEN at git tag `prereg-v1`. No confirmatory data had been collected at tag time; a small GSM8K pilot (n=11, reported separately as pilot) and a 20-item cost-only calibration procedure (defined below) are the only prior model interactions for this study.

## Background and pilot

Automated agentic-workflow papers report accuracy gains over single-call baselines, typically without matching inference budgets, without variance estimates, and on benchmarks with known label defects. In our GSM8K pilot (n=11), a generate→critique→revise→vote workflow at 16× the cost of one CoT call produced zero accuracy gain, and the single item on which all systems "failed" turned out to carry an erroneous gold label. This study is the confirmatory, budget-matched test on a harder benchmark.

## Primary hypothesis (confirmatory)

**H1 (two-sided):** On MATH-500 difficulty levels 4–5, the accuracy of the structured workflow (`full`: 3× generate → critique each → revise each → LLM majority vote) differs from the accuracy of dollar-matched sequential self-consistency (`sc@budget`: N independent CoT samples + majority vote, N fixed by the calibration procedure below).

Directional expectation from the pilot: we expect NO significant difference or a deficit for `full`; the test is two-sided regardless.

## Design

- **Model:** `gemini-3.1-flash-lite` (Google AI API), temperature 0.7, max output 2048 tokens per call. Endpoint version strings logged per call.
- **Dataset:** HuggingFaceH4/MATH-500, all 500 items, fixed seed 42. Primary analysis stratum: levels 4–5 as labeled by the dataset. Levels 1–3, GSM8K (n=100 anchor), and AIME 2024–25 (n=60, contamination-flagged) are secondary/exploratory strata.
- **Systems (all same model):** `cot@1`, `sc@3`, `sc@9`, `sc@budget`, `full`, `escalate_structure` (SC@3 → full workflow when the 3 answers are not unanimous), `escalate_sc` (SC@3 → additional CoT samples of equal incremental budget when not unanimous).
- **Budget matching:** `sc@budget`'s N is fixed so its mean realized dollar cost (list price × usage-metadata tokens) is nearest to `full`'s, measured on the first 20 sampled items (cost-only calibration; accuracy is not inspected during calibration). `escalate_sc`'s extra sample count matches `escalate_structure`'s mean incremental escalation cost from the same calibration.
- **Prompts:** written during the GSM8K pilot, unchanged for MATH-500. Neither the workflow nor the baselines receive benchmark-specific tuning (equal-effort freeze).
- **Repeats:** primary analysis uses repeat 0 only. Repeats 1–2 are run for `full` and `sc@budget` to report run-to-run variance; they do not enter the primary test.

## Analysis plan (code in `core/analysis.py` at this tag)

- **Primary test:** exact two-sided McNemar on discordant pairs, α = 0.05, on level-4–5 items, repeat 0, `full` vs `sc@budget`.
- **Effect estimate:** accuracy difference with 95% item-level paired-bootstrap CI (10,000 resamples, seed 42).
- **Scoring:** sympy-based mathematical equivalence with normalized-string fallback; scoring method logged per item. Items where BOTH systems' scoring method is `failed` are excluded from the primary test and their count reported.
- **Missingness:** API failures/safety blocks/truncations are reported per system and scored as incorrect (conservative), with a sensitivity analysis excluding them.
- **Secondary (S1, escalation):** on items where SC@3 was not unanimous, paired comparison of `escalate_structure` vs `escalate_sc` (same McNemar + bootstrap machinery). This isolates structure from added compute at the decision point.
- **Everything else** (per-level breakdowns, Pareto frontiers, GSM8K/AIME strata, cost-per-success, label-audit results) is exploratory and will be labeled as such.

## Power / minimum detectable effect (stated limitation)

With ~220–250 level-4–5 pairs and an assumed discordance rate q ≈ 0.10, the MDE at α=.05, power .80 is ≈ 6 percentage points. Effects of 0.5–3pp — the magnitude many workflow papers report — are NOT detectable by this study (nor, at published sample sizes, by most of those papers; that observation is part of the point).

## Label-integrity audit (secondary, method fixed here)

Candidate label errors = items where ALL systems produce the same answer AND it disagrees with gold (consensus screen; acknowledged as verification-biased) PLUS a uniform random sample of 50 items. All candidates and the random sample are manually reviewed by the author, blind to system identity, ruling: gold correct / model correct / ambiguous. The random sample yields an unbiased error-rate bound; the screen yields confirmed instances only.

## Budget and stopping

Hard spend guards enforced in code before every API call: warn $60, stop $80, absolute $100. If the stop triggers, analysis proceeds on all completed items (problem-major execution keeps all systems covered on completed items) and the truncation is reported.

## Deviations

Any deviation from this document will be reported in a "Deviations from preregistration" section of the final report.
