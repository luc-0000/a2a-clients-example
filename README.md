# FinTools A2A Client Template

调用 FinTools 平台上的 task agent（trading / deep research / data 等），实时看 status 变化，跑完后下载报告 ZIP。

## 1. 调用流程

FinTools 的 task agent 跑法是「Job 模式」——你 POST 一次任务，backend 在云端起一个 Pod 跑 `main.py`，跑完写报告到 OSS。这个 template 把整套流程包装成一条命令：

```
POST /agents/{id}/a2a/                     →  拿到 run_id（任务立刻被 accept）
GET  /agents/{id}/tasks/{run_id}           →  轮询 status：pending → running → completed
GET  /agents/{id}/reports/zip              →  下载报告 ZIP（仅 status=completed 后）
```

client 默认每 5 秒 poll 一次，每次 status 变化会增量打印一行（伪 streaming 体验）。

## 2. 先决条件

- Python 3.9+
- FinTools 账号 + 一份有效的 `FINTOOLS_ACCESS_TOKEN`
- 目标 task agent 的 URL（FinTools agent 详情页能看到，形如 `https://fin-meta.net/api/v1/agents/{id}/a2a/`）

### 拿 token

1. 登录 FinTools（本地 `http://localhost` 或线上 `https://fin-meta.net`）
2. 右上角头像 → **User Profile**
3. 复制 `FINTOOLS_ACCESS_TOKEN` 字段

token 等同于你的账号凭证，**不要提交到 git**。本仓库 `.gitignore` 已排除 `.env`。

## 3. 安装

```bash
git clone https://github.com/luc-0000/a2a-clients-example.git
cd a2a-clients-example

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

配置 token（二选一）：

```bash
# 方式 A：写入 .env（推荐，长期使用）
echo 'FINTOOLS_ACCESS_TOKEN=your-token-here' > .env

# 方式 B：当前 shell export（临时）
export FINTOOLS_ACCESS_TOKEN=your-token-here
```

## 4. 调用 trading agent

```bash
python -m agents_client.streaming.trading_agent_client_stream \
    000001 \
    http://127.0.0.1:8000/api/v1/agents/1/a2a/
```

参数顺序：
1. `stock_code` — 比如 `000001`（平安银行）、`600519`（贵州茅台）、`00700`（腾讯）
2. `agent_url` — task agent 的 a2a URL
3. `report_output_dir`（可选）— ZIP 保存目录，默认 `agents_client/streaming/downloaded_reports/`

预期输出：

```
============================================================
Trading Agent Client
============================================================
Agent URL:    http://127.0.0.1:8000/api/v1/agents/1/a2a
股票代码:     000001
A2A Token:    2fe71dbebe...
轮询间隔:     5.0s
心跳超时:     300.0s
============================================================

[submitted] run_id=6b4387d0-18b6-439e-951c-6ed771b49443
            job=agent-1-jv3xteqj-1782889534
[status]    (start) → pending
[status]    pending → running
[status]    running → completed

[result]    status=completed
            result=buy

[reports]   downloading ZIP...
[reports]   saved to agents_client/streaming/downloaded_reports/reports_xxx.zip
```

成功标志：
- 终端出现 `[status]    ... → completed`
- `downloaded_reports/` 下出现新的 `.zip` 文件

## 5. 调用 deep research agent

完全一样，换 client 名字 + agent_url：

```bash
python -m agents_client.streaming.dr_agent_client_stream \
    600519 \
    http://127.0.0.1:8000/api/v1/agents/82/a2a/
```

deep research 的 `result` 是研究报告的文本摘要，ZIP 里是完整的 markdown / pdf。

## 6. 调云端 vs 调本地

`agent_url` 决定调哪里的 FinTools：

| 环境 | `agent_url` 示例 |
|---|---|
| 本地 backend | `http://127.0.0.1:8000/api/v1/agents/{id}/a2a/` |
| 线上 FinTools | `https://fin-meta.net/api/v1/agents/{id}/a2a/` |

token 跟着环境走——本地用本地的 token，线上用线上的 token。

## 7. 中途中断 / 恢复

client 没有内置恢复——一旦 Ctrl+C，client 进程退出。但**云端任务不会停**，Pod 会继续跑。

要恢复：把之前的 `run_id` 拿出来直接调 backend：

```bash
curl -H "Authorization: Bearer $FINTOOLS_ACCESS_TOKEN" \
     http://127.0.0.1:8000/api/v1/agents/1/tasks/<run_id>
```

返回里有 `status`、`result`、`artifacts.report_url`（OSS signed URL，可直接下载报告）。

## 8. 常见问题

| 报错 | 原因 | 处理 |
|---|---|---|
| `未设置 FINTOOLS_ACCESS_TOKEN` | env 没加载到 | 检查 `.env` 是否在仓库根目录、是否 `source .venv/bin/activate` |
| `401` / `Invalid token` | token 错或过期 | 重新去 User Profile 复制 |
| `403 Run access denied` | 这个 agent 不对你开放 | 用 owner 自己的 token，或换 `run_policy=public` 的 agent |
| `404 No task found` | run_id 不对，或者 task 不是你提交的 | 检查 run_id，每个 run_id 只能查提交者本人 |
| `410 Server has been shut down` | Pod 已经 TTL 过期清理掉了 | 任务已经完成过、报告 ZIP 还在 OSS（看 `[result]` 输出里的 URL） |
| 一直 `[status] pending → pending` 不变 | Pod 没起来，可能镜像没 build | 上 FinTools 后台看 build/deploy 状态 |
| `[reports] no ZIP available` | Pod 已退出，HTTP 报告端点不可达 | 走 OSS signed URL（见 §7） |

## 9. 项目结构

```
agents_client/
├── utils.py                                  # ReportDownloader（POST 完成后下 ZIP）
└── streaming/
    ├── base_client.py                        # StreamingAgentClient（核心：submit + poll + emit）
    ├── trading_agent_client_stream.py        # trading agent 入口
    └── dr_agent_client_stream.py             # deep research agent 入口
```

`base_client.py` 里所有逻辑都跟 FinTools backend 的 `a2a_plane.py` 路由一一对应：

| client 方法 | backend endpoint | backend 代码位置 |
|---|---|---|
| `submit()` | `POST /agents/{id}/a2a/` | `a2a_plane.py:1052` |
| `poll_once()` | `GET /agents/{id}/tasks/{run_id}` | `a2a_plane.py:171` |
| `ReportDownloader.download_zip()` | `GET /agents/{id}/reports/zip` | `a2a_plane.py:207` |

要扩展支持其他 task agent（data agent、hk_ai_agent 等），复制一份 `trading_agent_client_stream.py` 改 `DEFAULT_AGENT_URL` 和 client 名字就行，逻辑不动。

## 10. 关于"streaming"这个名字

backend 对所有 task agent 都是 **job-mode**——POST `/a2a/` 立即返回 `{run_id, job_name, status:"job_started"}`，不返回 SSE 流（Pod 跑 main.py 后退出，没有 long-running HTTP server）。

这个 client 命名为 streaming 是因为**用户体验**是 streaming-like：每次 status 变化增量打印一行，看起来像在流式接收事件。底层实现是 polling。

如果未来 FinTools 加了真正的 SSE 流式 agent，把 `base_client.py` 的 `stream_until_terminal()` 换成 a2a-sdk 的 `send_message_streaming` 即可，外部接口不变。
