---
name: fintools-agent-client
description: Run the Fintools remote agent clients from this repository with a temporary isolated workspace, Python runtime selection, and persistent output export. Use when Codex needs to execute the local `agent-client-template` project for Deep Research or Trading tasks, choose between streaming and polling modes, validate required inputs, create a temporary work directory, fall back to a conda environment if Python 3.10+ is unavailable, and preserve reports/results for the user.
---

# Fintools Agent Client

## Overview

Use this skill to run the repository's Deep Research or Trading client with a predictable workflow:

- Validate the required inputs
- Create or reuse a working directory
- Prefer a local Python 3.10+ virtual environment
- Fall back to a conda environment only when no compatible Python exists
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

Pass `--persist-dir <path>` when the user wants a permanent destination for reports and summaries.

## Required Inputs

- `--agent-type`: `deep_research` or `trading`
- `--mode`: `streaming` or `polling`
- `--stock-code`
- `--agent-url`
- `FINTOOLS_ACCESS_TOKEN` in the environment, or `--access-token`

Optional:

- `--work-dir`: user-specified working directory
- `--persist-dir`: copy outputs to a stable destination after execution
- `--task-id`: resume an existing polling task
- `--cleanup`: delete the auto-created work directory after outputs are safely persisted

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
2. If `--work-dir` is provided, use it and keep it by default.
3. Otherwise create an auto-named temporary directory and print the path immediately.
4. Check whether the current Python satisfies 3.10+.
5. If not, search for `python3.10+` on the machine.
6. If still unavailable, fall back to `conda create -p <work-dir>/conda-env python=3.10`.
7. Install repository requirements into the chosen environment.
8. Execute the selected client mode through the wrapper script.
9. Stream intermediate results to stdout as they are produced.
10. Run the child Python process in unbuffered mode so hosts such as OpenClaw can see progress immediately.
11. Write a `summary.json` file in the working directory.
12. If `--persist-dir` is provided, copy `summary.json` and `downloaded_reports/` there.
13. Only delete an auto-created working directory when the user explicitly requested cleanup and the outputs were already persisted.

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
- `downloaded_reports/` when a report was downloaded

## Resources

- Script runner: [scripts/run_agent_client.py](./scripts/run_agent_client.py)
- Runtime details and current limitations: [references/runtime-contract.md](./references/runtime-contract.md)

## Examples

Trading, streaming mode:

```bash
python3 fintools-agent-client/scripts/run_agent_client.py \
  --agent-type trading \
  --mode streaming \
  --stock-code 600519 \
  --agent-url http://127.0.0.1:8000/api/v1/agents/69/a2a/ \
  --persist-dir /tmp/fintools-output
```

Trading, polling mode with an explicit working directory:

```bash
python3 fintools-agent-client/scripts/run_agent_client.py \
  --agent-type trading \
  --mode polling \
  --stock-code 600519 \
  --agent-url http://127.0.0.1:8000/api/v1/agents/69/a2a/ \
  --work-dir /tmp/my-agent-run
```
