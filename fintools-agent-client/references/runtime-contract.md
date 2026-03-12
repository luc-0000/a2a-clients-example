# Runtime Contract

## Purpose

This skill wraps the repository's existing client modules so another agent does not need to:

- manually pick a Python interpreter
- manually create a working directory
- manually switch between streaming and polling code paths
- manually preserve outputs for the user
- manually reconstruct anything from the original repository after copying the skill

## Working Directory Rules

- Use the provided `work_dir` as the parent directory when present.
- Otherwise use `/tmp/fintools-agent-client-runs/` as the default parent directory when available.
- If `/tmp` is unavailable, fall back to the system temp root.
- Keep shared environments under the parent directory, for example `shared-envs/`.
- Keep optional streaming probe output under the parent directory in `probe/`.
- Keep the cached access token in the parent directory as `.fintools_access_token`.
- Create a unique run subdirectory for each execution named like `fintools-agent-client-run-<agent_type>-<stock_code>-<mode>-<timestamp>`.
- If the same name already exists, append a numeric sequence such as `-002`.
- Write the environment, `summary.json`, `run.log`, and `downloaded_reports/` into that run subdirectory.
- Do not delete the parent directory automatically.
- Delete only the current run subdirectory when the user explicitly requested cleanup.

## Standalone Layout

- Bundle `agents_client/` inside the skill directory.
- Bundle `requirements.txt` inside the skill directory.
- Resolve all runtime paths relative to the skill directory itself.
- Fail clearly if the bundled runtime files are missing.

## Runtime Selection Rules

1. Prefer the current interpreter when it is Python 3.10+.
2. Otherwise search for `python3.10`, `python3.11`, `python3.12`, or `python3.13`.
3. Reuse a shared `venv` when a compatible interpreter exists.
4. If no compatible interpreter exists, reuse or create a shared `conda-env`.
5. Partition shared environments by Python version and dependency fingerprint.
6. Use a lock to avoid concurrent initialization of the same shared environment.
7. If conda is unavailable, fail with a direct error.

## Token Reuse Rules

1. Prefer `--access-token` when provided.
2. Otherwise read `FINTOOLS_ACCESS_TOKEN` from the environment.
3. Otherwise reuse `.fintools_access_token` from the parent directory.
4. After obtaining a token from CLI or environment, save it into the parent directory for later runs.

## Supported Combinations

- `deep_research + streaming`
- `trading + streaming`
- `trading + polling`

Unsupported:

- `deep_research + polling`

Do not silently substitute another mode for an unsupported combination.

## Persistence Rules

- Keep `summary.json`, `downloaded_reports/`, and runtime artifacts under the same run subdirectory.
- Mirror terminal stdout/stderr into `run.log` in the same run subdirectory.
- If the user wants a stable location, they should pass that path as `work_dir`.
- If `work_dir` is not set, keep the outputs under the auto-created parent directory and report the run subdirectory path to the user.

## User-Facing Labels

- `streaming`: "实时模式"
- `polling`: "轮询模式"

User-facing explanation for polling mode:

`轮询模式：不是一直保持连接，而是隔一段时间查一次任务进度，适合长时间任务。`

## Summary File

`summary.json` should contain at least:

- `agent_type`
- `mode`
- `stock_code`
- `agent_url`
- `runtime_type`
- `runtime_detail`
- `work_dir`
- `parent_dir_source`
- `run_dir`
- `log_path`
- `report_path`
- `success`
- `cleanup_requested`
- `cleanup_performed`
- `error`
