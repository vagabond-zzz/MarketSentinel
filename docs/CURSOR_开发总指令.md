# Market Sentinel — Cursor 开发总指令

你现在是 **Market Sentinel** 项目的主要开发 Agent。

请把本文件视为当前开发阶段的执行指令，把仓库中的产品任务书和 Roadmap 视为产品与架构基准。

---

## 一、先阅读这些文档

开始任何实现前，先完整阅读：

- `docs/01_任务书_Market_Sentinel.md`
- `docs/02_Roadmap_v0.1_Core.md`
- `docs/03_Roadmap_v0.2_Event_Engine.md`
- `docs/04_Roadmap_v0.3_Cursor_MVP.md`
- `docs/05_Roadmap_v0.4_Intelligence_and_v1.0_MultiHost.md`
- `AGENTS.md`

如果这些文件当前不在 `docs/` 下，请先找到实际位置并整理到 `docs/`，但不要修改原意。

---

# 二、当前版本范围

当前只开发：

```text
v0.1 — Core Foundation
```

当前目标：

```text
最多 10 只股票
    ↓
Market Provider
    ↓
Snapshot Normalize
    ↓
Ring Buffer
    ↓
Market State
    ↓
Adaptive Scheduler
    ↓
Feed Health
    ↓
CLI / Diagnostics
```

当前运行时必须满足：

```text
LLM Token = 0
```

暂时不要实现：

- v0.2 完整 Feature Engine
- v0.2 完整 Event Engine
- Signal 聚合系统
- News Agent
- LLM Agent
- 多 Agent
- 自动交易
- 买卖建议
- Cursor 最终状态栏 UI
- WebView 最终 UI
- DSH Adapter
- ZCode Adapter
- MCP Server
- 数据库
- Redis
- 消息队列
- FastAPI / HTTP Server
- Docker 化
- 微服务化

可以为后续版本保留必要接口，但不要提前实现复杂逻辑。

---

# 三、项目技术栈

本项目是 **多语言 Monorepo**。

不要尝试用 Conda 统一管理整个项目。

## Python Core

使用：

```text
Python 3.12+
uv
pyproject.toml
pytest
pytest-cov
ruff
```

可选：

```text
pytest-asyncio
mypy
```

Python 环境和依赖必须统一由：

```text
uv + pyproject.toml + uv.lock
```

管理。

禁止额外创建：

```text
requirements.txt
Pipfile
poetry.lock
setup.py
environment.yml
```

除非未来有明确迁移决定。

常用命令：

```bash
uv sync
uv run pytest
uv run pytest --cov=market_sentinel
uv run ruff check .
uv run ruff format --check .
```

---

## TypeScript / Node 宿主层

使用：

```text
Node.js 20+ 或 22+
pnpm
TypeScript
```

使用：

```text
package.json
pnpm-lock.yaml
pnpm-workspace.yaml
```

管理 Node / TypeScript 依赖。

不要使用 Conda 管理 Node 依赖。

后续 Cursor / DSH / ZCode Adapter 默认放在 pnpm workspace 中。

---

# 四、推荐仓库结构

优先采用：

```text
market-sentinel/
│
├── AGENTS.md
├── README.md
├── .gitignore
│
├── pyproject.toml
├── uv.lock
│
├── package.json
├── pnpm-lock.yaml
├── pnpm-workspace.yaml
│
├── docs/
│   ├── 01_任务书_Market_Sentinel.md
│   ├── 02_Roadmap_v0.1_Core.md
│   ├── 03_Roadmap_v0.2_Event_Engine.md
│   ├── 04_Roadmap_v0.3_Cursor_MVP.md
│   └── 05_Roadmap_v0.4_Intelligence_and_v1.0_MultiHost.md
│
├── src/
│   └── market_sentinel/
│       ├── __init__.py
│       │
│       ├── domain/
│       │   ├── models.py
│       │   └── enums.py
│       │
│       ├── providers/
│       │   ├── base.py
│       │   └── ...
│       │
│       ├── market_data/
│       │   ├── normalizer.py
│       │   ├── ring_buffer.py
│       │   └── state.py
│       │
│       ├── scheduler/
│       │   ├── scheduler.py
│       │   └── policy.py
│       │
│       ├── health/
│       │   └── feed_health.py
│       │
│       ├── watchlist/
│       │   └── watchlist.py
│       │
│       └── cli/
│           └── main.py
│
├── apps/
│   ├── cursor-extension/
│   ├── dsh-plugin/
│   └── zcode-plugin/
│
├── packages/
│   └── protocol-ts/
│
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/
```

当前 v0.1 只需要真正实现：

```text
src/market_sentinel
tests
CLI
```

`apps/` 与 `packages/` 可以先建立骨架，也可以等后续版本再创建。

不要为了目录好看提前写空架构。

---

# 五、核心架构原则

## 1. Core 与宿主彻底解耦

Python Core 不得依赖：

```text
Cursor
VS Code
DeepSeek Harness
ZCode
WebView
StatusBar
```

宿主只是 Adapter。

---

## 2. Python Core 负责

当前及后续主要负责：

```text
Market Provider
Market State
Ring Buffer
Scheduler
Feed Health
Feature Engine
Event Engine
Signal Engine
Intelligence Router
```

---

## 3. TypeScript 宿主层负责

未来负责：

```text
Cursor Extension Lifecycle
StatusBar
Hover
WebView
Command
Host Settings
DSH UI Binding
ZCode UI Binding
```

宿主 UI 不得复制业务规则。

---

## 4. Python ↔ TypeScript 通信

v0.3 前不必实现。

后续 MVP 默认优先考虑：

```text
TypeScript Host
    ↕
stdin / stdout
JSON Lines
    ↕
Python Core Process
```

除非有明确理由，否则不要提前引入：

```text
HTTP
FastAPI
WebSocket Server
数据库
独立后台服务
```

---

# 六、Provider 抽象

行情源必须通过抽象接口访问。

例如：

```python
from typing import Protocol

class MarketProvider(Protocol):
    async def fetch_quotes(
        self,
        symbols: list[str],
    ) -> list["MarketSnapshot"]:
        ...
```

具体接口可调整。

业务逻辑不能直接绑定某一个行情 API。

Provider 必须能够被 FakeProvider / MockProvider 替换。

---

# 七、Domain Model

v0.1 至少需要：

```text
MarketSnapshot
MarketState
WatchItem
SchedulerLevel
FeedStatus
```

优先使用：

```text
dataclass
Enum
Protocol
```

不要无必要引入：

```text
Django
SQLAlchemy
Pydantic 大量模型层
复杂 DI Framework
```

如果某个小依赖确实能明显减少错误，可以先说明原因。

---

# 八、时间设计

Scheduler、Feed Health、TTL 等逻辑必须可测试。

不要把：

```python
time.time()
datetime.now()
```

散落在业务代码中。

优先设计可注入 Clock，例如：

```python
class Clock(Protocol):
    def now(self) -> float:
        ...
```

测试中使用 FakeClock。

---

# 九、异步设计

只在 IO 边界使用 async。

适合 async：

```text
Market Provider 网络请求
主调度循环
异步生命周期
```

不需要 async：

```text
Ring Buffer
普通状态计算
纯数据转换
规则判断
```

不要为了“全异步”增加复杂度。

---

# 十、Watchlist

v0.1：

```text
最多 10 只股票
```

至少支持：

```text
add
remove
list
enable
disable
```

要求：

- 重复添加有明确行为；
- 超过 10 只有明确错误；
- disabled 股票不参与正常刷新；
- 持久化保持简单。

第一版允许使用：

```text
JSON
TOML
```

不要引入数据库。

---

# 十一、Ring Buffer

每只股票独立维护滚动数据。

至少支持：

```python
append(...)
latest(...)
window(...)
since(...)
```

要求：

- 时间顺序可控；
- 明确处理 out-of-order 数据；
- 不无限增长；
- 支持时间窗口查询；
- 后续 Feature Engine 可以直接消费；
- 必须有完整单元测试。

---

# 十二、Scheduler

v0.1 实现：

```text
COLD
WARM
HOT
```

建议默认：

```text
COLD = 10s
WARM = 3s
HOT = 1s
```

必须可配置。

需要支持：

```text
minimum dwell
hysteresis 基础机制
```

v0.1 不需要复杂技术指标自动升档。

只需要保证：

```text
状态转换机制正确
时间逻辑正确
每只股票可独立维护 level
```

---

# 十三、Feed Health

实现：

```text
LIVE
DELAYED
STALE
DISCONNECTED
```

记录：

```text
market_timestamp
received_timestamp
```

至少能得到：

```text
feed_latency
last_update_age
```

必须覆盖：

```text
正常
延迟
过期
断流
恢复
```

---

# 十四、CLI / Diagnostics

v0.1 必须有一个简单 CLI。

它不是最终产品 UI，而是 Core 的调试与验收工具。

至少展示：

```text
Feed Status
Watchlist Count
Symbol
Latest Price
Scheduler Level
Last Update Age
Feed Latency
```

例如：

```text
MARKET SENTINEL

Feed: LIVE
Watchlist: 10

00700.HK   602.50   WARM   age=0.8s
600519.SH  1482.30  COLD   age=1.1s
```

---

# 十五、测试策略

测试是强制要求。

原则：

> 每完成一个 Core 模块，同时完成对应 tests。

禁止：

> 所有功能做完以后再补测试。

---

## Unit Tests

### Ring Buffer

至少：

```text
append
latest
window
since
boundary
out-of-order input
capacity / expiry
```

### Scheduler

至少：

```text
COLD → WARM
WARM → HOT
HOT → WARM
minimum dwell
invalid transition
independent symbols
```

### Feed Health

至少：

```text
LIVE
DELAYED
STALE
DISCONNECTED
recovery
```

### Watchlist

至少：

```text
add
remove
duplicate
limit = 10
enable
disable
```

### Domain / Normalizer

至少：

```text
valid input
missing field
invalid timestamp
invalid symbol
```

---

## Provider Tests

Unit test 不访问真实网络。

必须使用：

```text
FakeProvider
Mock
Fixture
```

真实行情接口测试只能放：

```text
tests/integration/
```

并且：

```text
默认 uv run pytest
```

不能依赖互联网才能通过。

---

# 十六、质量检查

每个 Milestone 完成后至少运行：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

如果启用了 coverage：

```bash
uv run pytest --cov=market_sentinel
```

如果启用了 mypy：

```bash
uv run mypy src
```

Node 项目在真正开始开发后，再加入对应：

```bash
pnpm test
pnpm lint
pnpm typecheck
```

---

# 十七、Git 管理

如果仓库未初始化：

```bash
git init
```

`.gitignore` 至少覆盖：

```text
# Python
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
.mypy_cache/
.coverage
htmlcov/
*.egg-info/

# Node
node_modules/
dist/
out/
*.vsix

# System
.DS_Store
```

必须提交：

```text
pyproject.toml
uv.lock
package.json
pnpm-lock.yaml
pnpm-workspace.yaml
tests/
docs/
AGENTS.md
```

如果某些 Node 文件当前尚未实际使用，可以在真正初始化 Node workspace 时再生成，不要伪造 lockfile。

---

# 十八、Git Commit 规则

不要把 v0.1 做成一个巨大 commit。

建议按 Milestone 拆分。

示例：

```text
chore: initialize project foundation

feat: add market domain models

feat: add market provider abstraction

feat: implement market ring buffer

feat: add adaptive scheduler foundation

feat: implement feed health tracking

feat: add watchlist management

feat: add core diagnostics cli

test: expand core integration coverage

docs: update v0.1 implementation status
```

实际名称以代码内容为准。

每次 commit 前必须：

1. 查看 `git status`；
2. 查看 `git diff`；
3. 运行相关 tests；
4. 确认无意外生成文件；
5. 不提交 failing tests；
6. 不提交 `.venv` / `node_modules` 等环境目录。

---

# 十九、开发顺序

第一步不要直接大量编码。

先执行：

1. 阅读全部 docs；
2. 阅读 `AGENTS.md`；
3. 检查已有代码；
4. 检查 Git 状态；
5. 检查 Python / uv 是否可用；
6. 检查 Node / pnpm 是否可用；
7. 对照 v0.1 Roadmap；
8. 输出 implementation plan。

Plan 必须包含：

```text
Milestone
涉及文件
核心接口
测试策略
验收条件
Git commit 边界
```

如果发现：

```text
文档与现有代码冲突
环境问题
架构冲突
```

请明确指出。

不要自行改变产品目标。

---

# 二十、v0.1 推荐 Milestone

建议：

```text
M0 Project Foundation

M1 Domain Models + Provider Contract

M2 Ring Buffer + Market State

M3 Watchlist

M4 Scheduler

M5 Feed Health

M6 CLI / Diagnostics

M7 Integration Tests + Cleanup
```

可以小幅调整，但不要跨入 v0.2。

---

# 二十一、当前任务

现在请：

1. 完整阅读项目文档与 `AGENTS.md`；
2. 检查当前仓库；
3. 暂时不要大规模修改代码；
4. 输出 v0.1 Implementation Plan；
5. 输出建议目录树；
6. 输出测试策略；
7. 输出预计 Git Commit 划分；
8. 指出你发现的任何风险或需要确认的技术决策。

在我确认 Plan 之前，不要继续实现 v0.1。
