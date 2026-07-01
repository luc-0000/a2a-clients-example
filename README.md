# FinTools A2A Client Template

Call FinTools task agents (trading / deep research / data) and download the report ZIP.

## Setup

```bash
git clone https://github.com/luc-0000/a2a-clients-example.git
cd a2a-clients-example
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
echo 'FINTOOLS_ACCESS_TOKEN=your-token-here' > .env
```

Get your token from FinTools → User Profile → `FINTOOLS_ACCESS_TOKEN`.

## Use

```bash
# Trading agent
python -m agents_client.streaming.trading_agent_client_stream \
    000001 \
    http://127.0.0.1:8000/api/v1/agents/1/a2a/

# Deep research agent
python -m agents_client.streaming.dr_agent_client_stream \
    600519 \
    http://127.0.0.1:8000/api/v1/agents/82/a2a/
```

Args: `stock_code` `agent_url` `[report_output_dir]`

## What happens

```
POST /agents/{id}/a2a/              → run_id (task accepted, Pod starts)
GET  /agents/{id}/tasks/{run_id}    → poll status (pending → running → completed)
GET  /agents/{id}/reports/zip       → download ZIP (after completed)
```

The client polls every 5s and prints status transitions inline. When `status=completed`, the report ZIP is downloaded to `agents_client/streaming/downloaded_reports/`.

## Example output

```
[submitted] run_id=a7ce6287-c6cc-4d76-85d2-780949d7843c
[status]    (start) → pending
[status]    pending → running
[status]    running → completed
[result]    status=completed
            result=buy
[reports]   downloading ZIP...
[reports]   saved to agents_client/streaming/downloaded_reports/reports_xxx.zip
```

## Cloud vs local

Point `agent_url` at whichever FinTools deployment you want:

| Env | `agent_url` |
|---|---|
| Local backend | `http://127.0.0.1:8000/api/v1/agents/{id}/a2a/` |
| Production | `https://fin-meta.net/api/v1/agents/{id}/a2a/` |

Use the matching token for each environment.

## Common errors

| Error | Cause | Fix |
|---|---|---|
| `FINTOOLS_ACCESS_TOKEN not set` | env not loaded | check `.env` is in repo root, `source .venv/bin/activate` |
| `401 Invalid token` | token wrong/expired | re-copy from User Profile |
| `403 Run access denied` | agent not open to you | use owner's token, or pick a `run_policy=public` agent |
| `410 Server shut down` | Pod TTL-expired and cleaned up | report ZIP is still on OSS — see `[result]` output URL |
| Stuck on `pending` forever | Pod didn't start, image may not be built | check FinTools admin for build/deploy status |

## Notes

- Backend runs all task agents in **job-mode**: `POST /a2a/` returns `{run_id, job_name, status:"job_started"}` immediately, no SSE stream. The Pod runs `main.py` and exits.
- This client is named "streaming" because the UX is streaming-like (incremental status prints). Internally it polls. See `agents_client/streaming/base_client.py`.
