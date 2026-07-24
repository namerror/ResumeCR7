# Agentic Testing

This directory contains a compact dataset and guide for agent-led testing of ResumeCR7 API results.

- `dataset.json` defines the compact test dataset for skill selection and project selection.
- `agent-testing-guide.md` explains how an agent should run the dataset and critique results.
- `run_agentic_dataset.py` runs selected dataset requests against a local API and writes JSON results.
- `requests.http` provides REST Client requests for the full dataset variant matrix.

The dataset is intentionally small to keep model-backed testing affordable: two input sets for `/select-skills` and two input sets for `/select-projects`.
