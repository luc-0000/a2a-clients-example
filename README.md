# Agent Client Template

这个项目提供两类客户端，用来调用远端 Agent 并取回结果：

- `Deep Research Agent`：拿研究报告，最终下载 ZIP 报告包
- `Trading Agent`：拿交易结果，同时下载报告 ZIP

适合两种使用者：

- `OpenClaw` 这类 agent：按命令逐步执行即可
- 人类开发者：看完下面 3 分钟内可以跑通

## 1. 先决条件

- Python 3.10+
- 可访问的 Agent 服务
- 有效的 `FINTOOLS_ACCESS_TOKEN`

安装依赖：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

配置环境变量：

```bash
export FINTOOLS_ACCESS_TOKEN=your-token-here
```

`FINTOOLS_ACCESS_TOKEN` 的获取方式：

- 先在 Fintools 平台注册账号
- 登录后进入 `User Profile` 页面
- 在页面里复制你的 `FINTOOLS_ACCESS_TOKEN`

也可以写入项目根目录 `.env`：

```dotenv
FINTOOLS_ACCESS_TOKEN=your-token-here
```

## 2. OpenClaw 最短执行路径

OpenClaw 建议严格按这个顺序执行：

1. 进入项目目录
2. 激活虚拟环境并安装依赖
3. 设置 `FINTOOLS_ACCESS_TOKEN`
4. 运行目标 client
5. 等待任务结束
6. 读取终端输出里的结果摘要
7. 到 `downloaded_reports/` 找 ZIP 报告

成功标志：

- 终端出现 `执行完成` 或 `任务最终结果`
- `downloaded_reports/` 下出现新的 `.zip` 文件

## 3. 拿 report

运行 Deep Research streaming client：

```bash
python -m agents_client.streaming.dr_agent_client_stream 600519
```

说明：

- `600519` 是股票代码，可替换
- 该命令会：
  - 发起分析任务
  - 实时打印 Agent 状态
  - 列出报告
  - 自动下载 ZIP 报告到 `downloaded_reports/`

产出位置：

```bash
downloaded_reports/
```

## 4. 拿 trading results

最直接的方式是运行 Trading streaming client：

```bash
python -m agents_client.streaming.trading_agent_client_stream 600519 http://127.0.0.1:8000/api/v1/agents/69/a2a/
```

说明：

- 第一个参数是股票代码
- 第二个参数是 Trading Agent 的 `a2a` 地址
- 命令执行后：
  - 终端会持续输出交易任务状态
  - 最后会列出并下载报告 ZIP

你通常会在终端里拿到两类信息：

- `status-update` 文本：交易过程和最终结果摘要
- `artifact-update` 文本：生成的文件提示

报告仍然会下载到：

```bash
downloaded_reports/
```

## 5. 需要可恢复轮询时

如果你的 Trading Agent 走数据库轮询模式，使用：

```bash
python -m agents_client.db_polling.trading_agent_client_db
```

这个模式适合任务很长、需要恢复执行的情况。它会：

- 先创建任务
- 定期轮询任务状态
- 打印最终 `result`
- 任务成功后自动下载报告 ZIP

默认脚本内置了 agent URL 和股票代码；如果你要改目标地址或股票，直接修改 [agents_client/db_polling/trading_agent_client_db.py](/Users/lu/development/fintools_all/templates/agent-client-template/agents_client/db_polling/trading_agent_client_db.py) 里的 `agent_url` 和 `stock_code` 即可。

## 6. 输出位置和含义

- 终端输出：任务状态、错误信息、结果摘要
- `downloaded_reports/*.zip`：报告压缩包

如果是 DB polling 模式，还会看到：

- `Task ID`
- 每次轮询的 `状态 / 进度 / 心跳 / 更新时间`
- 最终 `result` 或 `error`

## 7. 常见问题

`未设置 FINTOOLS_ACCESS_TOKEN`

- 说明没加载到环境变量或 `.env`

`404 No reports available yet`

- 任务还没完成，或者报告已过期

`410 Server has been shut down`

- Agent 服务已停止，报告无法再下载

## 8. 对 OpenClaw 的执行建议

如果你的目标只是“拿到 report 和 trading results”，优先使用这两条命令：

```bash
python -m agents_client.streaming.dr_agent_client_stream 600519
python -m agents_client.streaming.trading_agent_client_stream 600519 http://127.0.0.1:8000/api/v1/agents/69/a2a/
```

判断任务成功时，不要只看退出码，还要同时检查：

- 终端中是否出现成功完成信息
- `downloaded_reports/` 是否生成新的 ZIP

如果需要更强的稳定性和恢复能力，再切到 DB polling 模式。
