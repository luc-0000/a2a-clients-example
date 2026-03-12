---
name: fintools-agent-client
description: Run the Fintools remote agent clients from this repository with a temporary isolated workspace, Python runtime selection, and persistent output export. Use when Codex needs to execute the local `agent-client-template` project for Deep Research or Trading tasks, choose between streaming and polling modes, validate required inputs, create a temporary work directory, fall back to a conda environment if Python 3.10+ is unavailable, and preserve reports/results for the user.
---

# Fintools Agent Client

## Overview

Use this skill to run the repository's Deep Research or Trading client with a predictable workflow:

- Validate the required inputs
- Create or reuse a parent run directory
- Reuse a shared Python environment when possible
- Fall back to a shared conda environment only when no compatible Python exists
- Use only files bundled inside this skill directory
- Execute the selected mode
- Preserve the outputs for the user and report where they were written

## Quick Start

Run the wrapper script instead of calling the repository modules directly:

```bash
python3 fintools-agent-client/scripts/run_agent_client.py \
  --agent-type trading \
  --mode streaming \
  --stock-code 600519 \
  --agent-url http://127.0.0.1:8000/api/v1/agents/69/a2a/
```

Use a single user-facing directory concept: `--work-dir`. Treat it as the parent directory for all runs, create a dedicated run subdirectory for each execution, and keep shared environments under that parent directory.
Store `FINTOOLS_ACCESS_TOKEN` in the parent directory after the first successful run so later runs can reuse it without asking again.
If you run the optional streaming probe, keep its output under the same parent directory in `probe/`.

## Required Inputs

- `--agent-type`: `deep_research` or `trading`
- `--mode`: `streaming` or `polling`
- `--stock-code`
- `--agent-url`
- `FINTOOLS_ACCESS_TOKEN` in the environment, or `--access-token`

Optional:

- `--work-dir`: user-specified parent directory for all runs
- `--task-id`: resume an existing polling task
- `--cleanup`: delete only the current run subdirectory after the run finishes; never delete the parent directory

Fail fast when any required input is missing. Do not rely on hard-coded default stock codes or agent URLs.
User-facing prompts should say "streaming（实时模式）" and "polling（轮询模式）".

## Mode Selection

- Streaming mode: `streaming`
  Use when the user wants continuous event updates.
- Polling mode: `polling`
  Explain it as: "轮询模式：不是一直保持连接，而是隔一段时间查一次任务进度，适合长时间任务。"

Current repository support:

- `deep_research + streaming`: supported
- `trading + streaming`: supported
- `trading + polling`: supported
- `deep_research + polling`: not implemented in this repository; say so clearly and stop instead of inventing a fallback

## Execution Workflow

1. Determine the working directory.
2. If `--work-dir` is provided, use it as the parent directory for runs.
3. Otherwise use `/tmp/fintools-agent-client-runs/` when available.
4. If `/tmp` is unavailable, fall back to the system temp root.
5. Create a unique run subdirectory such as `run-trading-600519-streaming-20260312-120000`.
   If the same name already exists within the same second, append a sequence suffix such as `-002`.
6. Print both the parent directory and the current run directory immediately.
7. Check whether the current Python satisfies 3.10+.
8. Validate that the skill directory already contains bundled `agents_client/` and `requirements.txt`.
9. Fail immediately if the bundled runtime files are missing.
10. Read `FINTOOLS_ACCESS_TOKEN` from the CLI or environment; if absent, reuse the cached token stored in the parent directory.
11. Cache the token in the parent directory after the first successful lookup.
12. If yes, create or reuse a shared `venv` under the parent directory.
13. If not, search for `python3.10+` on the machine and create or reuse a shared `venv`.
14. If no compatible interpreter exists, create or reuse a shared `conda-env` under the parent directory.
15. Treat a shared environment as reusable only when its `.ready` marker exists.
16. Guard shared environment creation with a lock so concurrent runs do not initialize the same environment at once.
17. Execute the selected client mode through the wrapper script.
18. Stream intermediate results to stdout as they are produced.
19. Run the child Python process in unbuffered mode so hosts such as OpenClaw can see progress immediately.
20. Write a `summary.json` file in the current run directory.
21. Write `run.log` in the current run directory while still showing the same output in the terminal.
22. Keep reports, summary, logs, and runtime artifacts under the same run directory.
23. Only delete the current run directory when the user explicitly requested cleanup.
24. Never delete the parent directory automatically.

## Output Contract

Always tell the user:

- Which runtime was used: `venv` or `conda`
- Which working directory was used
- Whether it was user-specified or auto-created
- Whether reports were downloaded
- Whether outputs were persisted elsewhere
- Whether cleanup happened

The working directory should contain at least:

- `summary.json`
- `run.log`
- `downloaded_reports/` when a report was downloaded

Use `--work-dir` as the only user-facing directory parameter. Do not make the user choose separate runtime and output locations.
Default auto-created parent directories should prefer `/tmp/fintools-agent-client-runs/`, with each run stored under its own `run-*` subdirectory.
Keep shared environments under the parent directory as well, for example `shared-envs/venv-.../` or `shared-envs/conda-.../`.
Keep optional probe output under `probe/` in the same parent directory instead of creating unrelated temp directories.
Cache the access token in the parent directory so the user normally provides it only once per parent directory.
This skill must remain runnable even if the original `agent-client-template/` repository is removed, so all runtime code and `requirements.txt` stay bundled inside `fintools-agent-client/`.

## Host Agent Suggestion

If the host agent cannot display subprocess stdout in real time, suggest reading the current run directory's `run.log`.

Recommended behavior for OpenClaw or similar hosts:

- Start the skill normally.
- Read the printed run directory path.
- Optionally poll `<run-dir>/run.log` for new content and show appended lines to the user.
- Still treat terminal stdout as the primary output when the host supports live streaming.

This is only a compatibility suggestion for hosts with buffered subprocess output. It is not required for hosts that already support live stdout/stderr streaming.

## Resources

- Script runner: [scripts/run_agent_client.py](./scripts/run_agent_client.py)
- Streaming probe: [scripts/stream_probe.py](./scripts/stream_probe.py)
- Runtime details and current limitations: [references/runtime-contract.md](./references/runtime-contract.md)

## Examples

Trading, streaming mode:

```bash
python3 fintools-agent-client/scripts/run_agent_client.py \
  --agent-type trading \
  --mode streaming \
  --stock-code 600519 \
  --agent-url http://127.0.0.1:8000/api/v1/agents/69/a2a/ \
  --work-dir /tmp/fintools-agent-client-runs
```

Trading, polling mode with an explicit working directory:

```bash
python3 fintools-agent-client/scripts/run_agent_client.py \
  --agent-type trading \
  --mode polling \
  --stock-code 600519 \
  --agent-url http://127.0.0.1:8000/api/v1/agents/69/a2a/ \
  --work-dir /tmp/my-agent-runs
```
