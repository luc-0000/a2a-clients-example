# Runtime Contract

## Purpose

This skill wraps the repository's existing client modules so another agent does not need to:

- manually pick a Python interpreter
- manually create a working directory
- manually switch between streaming and polling code paths
- manually preserve outputs for the user

## Working Directory Rules

- Use the provided `work_dir` when present.
- Otherwise create an auto-named temporary directory with the skill name in the prefix.
- Write the environment, `summary.json`, and `downloaded_reports/` into that directory.
- Do not delete a user-provided working directory automatically.
- Delete an auto-created directory only when:
  - the user explicitly requested cleanup
  - outputs were already copied to `persist_dir`

## Runtime Selection Rules

1. Prefer the current interpreter when it is Python 3.10+.
2. Otherwise search for `python3.10`, `python3.11`, `python3.12`, or `python3.13`.
3. Only if none exist, fall back to `conda create -p <work-dir>/conda-env python=3.10`.
4. If conda is unavailable, fail with a direct error.

## Supported Combinations

- `deep_research + streaming`
- `trading + streaming`
- `trading + polling`

Unsupported:

- `deep_research + polling`

Do not silently substitute another mode for an unsupported combination.

## Persistence Rules

- If `persist_dir` is set, copy `summary.json` there.
- If `downloaded_reports/` exists, copy it there as well.
- If `persist_dir` is not set, keep the outputs in the working directory and report that path to the user.

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
- `work_dir_source`
- `persist_dir`
- `report_path`
- `success`
- `cleanup_requested`
- `cleanup_performed`
- `error`
