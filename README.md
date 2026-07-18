# Agent X-Ray — Phase 1 experiment core

Agent X-Ray measures whether generate → self-critique → revise → majority-vote earns its cost on GSM8K. It runs component ablations and same-model CoT/self-consistency baselines, logs every model call, and produces a machine-readable result plus a Markdown report.

## Setup

Python 3.12 or newer is recommended. From the repository root:

```bash
pip install -r requirements.txt
# run from repository root
```

## Run

The deterministic mock is offline, uses simulated model behavior and GSM-style fixtures, and should finish in well under one minute:

```bash
python -m core.run --mock
```

Run a smaller smoke test or change the fixed sampling seed:

```bash
python -m core.run --mock --n 10 --seed 42
```

For the live experiment, put `GEMINI_API_KEY=...` in the repository-root `.env`, then run:

```bash
python -m core.run --live
```

If a live run stops at the daily quota, aggregate the completed checkpoint without loading credentials, downloading data, or calling Gemini:

```bash
python -m core.run --live --n 50 --aggregate-only
```

The live path uses `gemini-3.1-flash-lite` at temperature 0.7 with a 2,048-token output cap, downloads the GSM8K test split from Hugging Face using plain HTTPS, caches it under `data/`, and sleeps four seconds between successful calls by default. Override pacing with `--sleep SECONDS`. Calls are sequential; 429 and 5xx failures use exponential backoff with jitter for at most six retries.

Both modes checkpoint each completed problem/variant in `results/checkpoint_<mode>_n<N>_seed<SEED>.jsonl`. Re-running the same configuration resumes unfinished work without allowing checkpoints from another sample to leak in. Raw call accounting uses the matching `ledger_...jsonl` name; these JSONL artifacts are gitignored.

Final outputs are:

- `results/results.json`
- `results/REPORT.md`

## Test

From the repository root:

```bash
pytest poc/agent-xray/tests/
```

Tests never access the network or the Gemini API.
