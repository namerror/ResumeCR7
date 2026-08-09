# Scripts

All scripts should be run from the repo root. Scripts that import from `app/` require `PYTHONPATH` to be set:

```bash
export PYTHONPATH=.
```

Or prefix each command: `PYTHONPATH=. python scripts/<script>.py`

---

## build_skill_pools.py

Builds `data/skill_pools/normalized/skill_pools.json` from raw text files in `data/skill_pools/raw/`.

```bash
python scripts/build_skill_pools.py
python scripts/build_skill_pools.py --raw-dir data/skill_pools/raw --output data/skill_pools/normalized/skill_pools.json
```

## bump_version.py

Bumps release metadata, commits the five release files, creates the release tag,
and pushes the current branch and tag. Prepare the matching
`docs/CHANGELOG.md` release section before running it. The script blocks
unrelated worktree changes, but allows pending changes in the release files.

```bash
python scripts/bump_version.py vX.Y.Z
python scripts/bump_version.py vX.Y.Z --no-push
python scripts/bump_version.py vX.Y.Z --dry-run
```

## eval_cases_generator.py

Generates eval case files from skill pools. Output goes to `data/eval_cases/generated/` with a unique filename per run.

```bash
python scripts/eval_cases_generator.py                        # defaults: 5 cases/role, no seed
python scripts/eval_cases_generator.py --seed 42              # reproducible
python scripts/eval_cases_generator.py --cases-per-role 10    # more cases
python scripts/eval_cases_generator.py --no-ranking           # alphabetical expected output (no core-before-nice)
python scripts/eval_cases_generator.py --min-relevant 4 --max-relevant 6 --min-noise 2 --max-noise 3
```

| Flag | Default | Description |
|------|---------|-------------|
| `--cases-per-role` | 5 | Number of cases per role profile |
| `--seed` | None | Random seed for reproducibility |
| `--min-relevant` / `--max-relevant` | 3 / 7 | Range of core+nice skills sampled per category |
| `--min-noise` / `--max-noise` | 1 / 3 | Range of exclude skills sampled per category |
| `--ranking` / `--no-ranking` | true | Order expected output core-before-nice |
| `--pools` | `data/skill_pools/normalized/skill_pools.json` | Skill pools file |
| `--output-dir` | `data/eval_cases/generated/` | Output directory |

## eval.py

Runs scoring evaluation against eval case datasets. Requires `PYTHONPATH=.`.

```bash
PYTHONPATH=. python scripts/eval.py                              # default: eval_cases_basic.json
PYTHONPATH=. python scripts/eval.py -f eval_cases_real.json      # specific file (looked up in data/eval_cases/)
PYTHONPATH=. python scripts/eval.py -f path/to/custom.json       # relative or absolute path
PYTHONPATH=. python scripts/eval.py --run-generated              # all files in data/eval_cases/generated/
SKILL_BASELINE_FILTER=true SKILL_METHOD=embeddings PYTHONPATH=. python scripts/eval.py
SKILL_METHOD=embeddings PYTHONPATH=. python scripts/eval.py --baseline-filter
```

| Flag | Description |
|------|-------------|
| `-f` / `--file` | Eval case file (filename, relative path, or absolute path) |
| `--run-generated` | Run all generated eval case files |
| `--baseline-filter` | Enable baseline pre-filtering for this eval run |
| `--no-baseline-filter` | Disable baseline pre-filtering for this eval run |

`-f` and `--run-generated` are mutually exclusive. With no flags, runs `eval_cases_basic.json`.
