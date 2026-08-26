# AGENTS.md

本文件定义 Market Sentinel 仓库内所有开发 Agent 必须长期遵守的工程规则。

---

## 1. 项目定位

Market Sentinel 是一个低干扰、低延迟的市场监控核心。

当前路线：

```text
Market Data
    ↓
Feature
    ↓
Event
    ↓
Signal
    ↓
Optional Intelligence
    ↓
Host Adapter
```

目标宿主包括：

```text
Cursor
DeepSeek Harness
ZCode
其他未来终端
```

核心业务逻辑必须独立于宿主。

---

## 2. 当前优先级

当前优先级从高到低：

```text
1. Correctness
2. Testability
3. Observability
4. Low Latency
5. Simplicity
6. Extensibility
7. UI Polish
```

状态栏视觉优化不是当前第一优先级。

---

## 3. 当前版本边界

当前开发以 Roadmap 中明确指定的版本为准。

如果用户没有明确要求进入下一版本：

> 不允许主动跨版本开发。

特别是 v0.1 阶段不要提前实现：

```text
LLM
News Agent
Multi-Agent
复杂 Event Engine
复杂 Cursor UI
DSH Adapter
ZCode Adapter
MCP
自动交易
买卖建议
```

---

## 4. 多语言 Monorepo

本项目不是纯 Python 项目。

### Python

用于：

```text
Market Core
Provider
Market State
Ring Buffer
Scheduler
Feed Health
Feature Engine
Event Engine
Signal Engine
Intelligence Router
CLI
```

使用：

```text
Python 3.12+
uv
pyproject.toml
uv.lock
pytest
ruff
```

### TypeScript / Node

用于：

```text
Cursor Extension
DSH Adapter
ZCode Adapter
Host UI
Host Lifecycle
IPC Client
```

使用：

```text
Node.js
pnpm
package.json
pnpm-lock.yaml
pnpm-workspace.yaml
TypeScript
```

### Git

整个 Monorepo 统一由 Git 管理。

---

## 5. 不使用 Conda

不要为了统一 Python 与 Node 环境引入 Conda。

Python 依赖：

```text
uv
```

Node 依赖：

```text
pnpm
```

工具链版本未来如需统一，可考虑：

```text
mise
.node-version
.python-version
```

但除非有明确需求，不要主动增加环境管理层。

---

## 6. Python 依赖规则

禁止新增：

```text
requirements.txt
Pipfile
poetry.lock
setup.py
environment.yml
```

除非项目明确决定迁移。

Python 依赖统一写入：

```text
pyproject.toml
```

并更新：

```text
uv.lock
```

---

## 7. Node 依赖规则

TypeScript / Node 模块统一使用 pnpm。

不要混用：

```text
npm install
yarn
bun
```

除非某个宿主明确要求且已得到确认。

不要手动编辑：

```text
pnpm-lock.yaml
```

---

## 8. Core 与 Host 解耦

Python Core 不得依赖：

```text
VS Code API
Cursor API
DeepSeek Harness API
ZCode API
WebView
StatusBar
```

宿主代码不得复制 Core 的：

```text
行情计算
技术指标
Event Rule
Signal Priority
Scheduler 业务逻辑
```

宿主只负责：

```text
Lifecycle
IPC
UI Mapping
Settings Mapping
Notification Mapping
```

---

## 9. Host Adapter 原则

长期目标：

```text
Core
 ├── Cursor Adapter
 ├── DSH Adapter
 ├── ZCode Adapter
 └── CLI Adapter
```

宿主应消费统一协议，例如：

```text
MarketUIState
Signal
MarketState
```

禁止每个宿主重新定义一套业务模型。

---

## 10. IPC 原则

当 Python Core 与 TypeScript Host 开始通信时，优先：

```text
stdin/stdout
JSON Lines
```

除非明确证明需要，否则不要优先引入：

```text
FastAPI
HTTP Server
WebSocket Server
Redis
数据库
后台守护服务
```

协议必须：

```text
versioned
可测试
可记录
可向后兼容演进
```

---

## 11. Token 原则

行情刷新绝不能直接调用 LLM。

核心原则：

```text
High-frequency data = deterministic code
Low-frequency reasoning = optional intelligence
```

未来 Token 成本应接近：

```text
Significant Event 数量
×
单次分析 Token
```

而不是：

```text
股票数量
×
刷新频率
×
运行时间
```

---

## 12. Agent 原则

不要为了“Multi-Agent”概念引入多个 LLM。

逻辑模块可以叫：

```text
Price Agent
Volume Agent
Technical Agent
```

但只要普通程序能完成，就实现为 deterministic module。

只有真正需要语义推理的少量事件才允许进入 LLM。

---

## 13. 数据模型原则

Domain Model 优先使用：

```text
dataclass
Enum
Protocol
Typed structure
```

模型必须清晰区分：

```text
Snapshot
Feature
Event
Signal
UI State
```

不要把这些概念混成一个大型 dict。

---

## 14. Event 与 Signal 必须分离

`Event`：

> 客观发生的市场事实。

例如：

```text
5 分钟涨幅异常
成交量放大
突破日内高点
```

`Signal`：

> 系统决定展示给用户的提醒。

Event 可以很多。

Signal 必须经过：

```text
dedupe
cluster
cooldown
priority
```

后尽量少而有价值。

---

## 15. 时间必须可测试

任何依赖时间的核心逻辑：

```text
Scheduler
Feed Health
Cooldown
TTL
Dwell Time
```

都应该支持注入 Clock 或等价时间源。

不要把：

```python
time.time()
datetime.now()
```

散落在核心业务逻辑里。

---

## 16. 测试规则

每个 Core 功能必须配套 tests。

禁止：

> 先把全部功能写完，最后再补测试。

优先：

```text
Unit Test
→ Integration Test
→ Real Provider Manual Test
```

默认测试必须离线可运行。

---

## 17. 网络测试规则

默认：

```bash
uv run pytest
```

不能因为没有互联网而失败。

真实行情接口测试必须：

```text
放在 integration test
明确标记
默认可跳过
```

Unit Test 必须使用：

```text
FakeProvider
Mock
Fixture
FakeClock
```

---

## 18. Python 质量检查

每个 Milestone 完成后至少运行：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

如果项目启用 coverage：

```bash
uv run pytest --cov=market_sentinel
```

如果项目启用 mypy：

```bash
uv run mypy src
```

---

## 19. TypeScript 质量检查

当 TypeScript 模块开始开发后，至少提供：

```text
test
lint
typecheck
build
```

对应 pnpm scripts。

例如：

```bash
pnpm test
pnpm lint
pnpm typecheck
pnpm build
```

实际工具按宿主生态选择。

---

## 20. Git 规则

所有重要开发必须通过 Git 管理。

每次修改前先查看：

```bash
git status
```

每个逻辑完整 Milestone 尽量形成独立 commit。

不要创建一个包含整个版本的大型 commit。

---

## 21. Commit 规范

优先使用 Conventional Commit 风格：

```text
feat:
fix:
test:
refactor:
docs:
chore:
perf:
```

示例：

```text
feat: implement market ring buffer
test: cover scheduler dwell transitions
fix: recover feed health after provider timeout
```

不要为了格式而拆得过碎。

目标是：

> 每个 commit 都可以被独立理解和审阅。

---

## 22. Commit 前检查

每次 commit 前必须：

1. `git status`
2. `git diff`
3. 运行相关 tests
4. 运行 lint
5. 确认无 secrets
6. 确认无 `.venv`
7. 确认无 `node_modules`
8. 确认没有意外生成文件

失败测试不能提交为“完成”。

---

## 23. 不提交的内容

至少忽略：

```text
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
.mypy_cache/
.coverage
htmlcov/
node_modules/
dist/
out/
*.vsix
.DS_Store
```

不要提交：

```text
API Keys
Tokens
Passwords
个人账户信息
```

---

## 24. Lockfile 规则

需要提交：

```text
uv.lock
pnpm-lock.yaml
```

但前提是对应生态已真正初始化。

不要创建假的空 lockfile。

---

## 25. 不过度设计

当前规模：

```text
10 只股票
```

因此默认不要引入：

```text
Kafka
Redis
PostgreSQL
微服务
Kubernetes
复杂 Event Bus Framework
复杂 DI Framework
分布式 Scheduler
```

第一阶段以内存、清晰接口和可测试性为主。

---

## 26. 可观测性原则

系统必须能够回答：

```text
数据什么时候产生？
什么时候收到？
什么时候检测？
什么时候提醒？
```

重要时间：

```text
market_timestamp
received_timestamp
detected_timestamp
notified_timestamp
```

后续分别计算：

```text
Feed Latency
Detection Latency
Agent Latency
Total Latency
```

不要只记录一个“总耗时”。

---

## 27. Feed Health 必须是一等功能

核心必须明确区分：

```text
LIVE
DELAYED
STALE
DISCONNECTED
```

如果行情已经 stale：

> UI 不得继续表现为数据正常。

恢复连接后应自动恢复状态。

---

## 28. Scheduler 原则

第一阶段：

```text
COLD
WARM
HOT
```

刷新频率应配置化。

必须考虑：

```text
minimum dwell
hysteresis
anti-flapping
```

不要让状态在临界值附近高频切换。

---

## 29. Provider 原则

业务逻辑只能依赖：

```text
MarketProvider abstraction
```

不要直接依赖某个行情厂商。

Provider 必须能被：

```text
FakeProvider
TestProvider
AlternativeProvider
```

替换。

---

## 30. 错误处理

原则：

```text
单只股票异常
≠
整个系统退出
```

网络错误、解析错误、无效 symbol 等必须有明确处理。

不要大量使用：

```python
except Exception:
    pass
```

如果确实捕获宽泛异常：

- 必须记录；
- 必须说明边界；
- 不得静默吞错。

---

## 31. 日志

日志应该用于：

```text
Provider Error
Scheduler Transition
Feed Health Transition
Lifecycle
Unexpected State
```

不要默认把每个高频行情 tick 都写 INFO 日志。

避免日志本身成为性能问题。

---

## 32. 性能优化原则

优化顺序：

```text
先测量
再定位
再优化
```

不要因为未来可能支持 1000 只股票，就提前引入复杂架构。

当前优先保证：

```text
10 symbols stable
low latency
low CPU
bounded memory
```

---

## 33. 文档同步

当实现改变以下内容时：

```text
公开接口
目录结构
启动命令
测试命令
架构决策
```

需要同步更新 README 或对应 docs。

不要随意修改产品任务书和 Roadmap 原意。

如果 Roadmap 需要调整：

> 先说明原因，再修改。

---

## 34. 开发 Agent 工作方式

收到大任务时：

1. 先读相关 docs；
2. 检查现有实现；
3. 检查 tests；
4. 检查 git diff；
5. 给出实现计划；
6. 按小 Milestone 开发；
7. 边实现边测试；
8. 完成后运行完整检查；
9. 总结改动；
10. 对照验收条件。

---

## 35. 不要假装完成

如果：

```text
测试失败
依赖缺失
行情 Provider 未验证
某个 Milestone 未完成
```

必须明确说明。

不要因为主体代码已经写完就声明版本完成。

---

## 36. 当前项目最重要的三个长期约束

```text
1. 行情更新不调用 LLM

2. Core 与 Host 完全解耦

3. 每个 Core 模块必须可测试、可观测
```

如果某项设计违反这三条，默认需要重新考虑。

---

## 37. 最终设计方向

长期希望形成：

```text
                  Market Core
                       │
         ┌─────────────┼─────────────┐
         │             │             │
      Cursor          DSH          ZCode
      Adapter        Adapter       Adapter
```

未来 Intelligence 层：

```text
Event
  ↓
Router
  ├── Rule Signal
  └── Optional LLM
```

而不是：

```text
所有行情
  ↓
LLM
```

这是整个项目的核心工程方向。
