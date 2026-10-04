# Market Sentinel 产品化审计（M0 Audit）

> 生成日期：2026-10-04 · 审计对象：`master @ ec9f502`（v0.6.5）· 312 个 tracked 文件
> 性质：只读审计，不包含代码修改。后续 Milestone（M1–M9）在本文档获得确认后执行。

---

## 0. TL;DR

1. **项目本体已经是可用的产品内核**：确定性主链（Provider → Feature → Event → Signal → MarketState）、可选 LLM sidecar、Protocol v1 JSONL daemon、Cursor 扩展、Telemetry/Feedback/Evaluation/Tuning 全部已实现且有测试（基线 649 passed / coverage 90.61%，见 §9）。
2. **离"陌生开发者可用的开源项目"差的是外壳**：缺 LICENSE / CONTRIBUTING / SECURITY / CI / demo / doctor；README 是开发日志体；docs/ 以中文 roadmap 历史为主，没有 integration 文档；无 examples。
3. **集成判断已可下结论**：ZCode 与 DeepSeek Harness (DSH) 都原生支持 **MCP stdio**，且工具命名约定相同（`mcp__<server>__<tool>`）。**MCP 值得作为共同协议**，但只暴露 tools（DSH 不桥接 resources/prompts）；现有 Cursor daemon 协议保持不变；CLI 作为最低公共兜底。
4. **仓库卫生状况良好**：无 secrets、无 .env 提交史、无本地绝对路径；遗留项仅 1 个未跟踪脚本（`tools/resume_benchmark.py`）与 git 历史中的个人 QQ 邮箱（见 §4.3）。
5. **最重要的架构红线全部维持**：LLM 不进高频主链、Core/Host 解耦、Agent 集成只读。集成层通过新增 `capabilities`（稳定能力边界）+ `mcp` server 模块实现，Core 现有模块不动。

---

## 1. 当前项目到底是什么（产品视角）

### 1.1 用户与使用方式

| 用户 | 安装 | 运行 | 得到什么 |
|---|---|---|---|
| 个人开发者/研究型用户（当前定位） | `git clone` + `uv sync`（+ Node/pnpm 仅扩展需要） | `uv run market-sentinel ...` CLI | Watchlist 监控、事件/Signal 观察、Replay、Telemetry 报告、Offline Tuning |
| Cursor / VS Code Desktop 用户 | 本地构建 VSIX（`pnpm package:vsix`）后 Install from VSIX | 扩展自动 spawn Core daemon | StatusBar 报价、Hover、Details Webview、Alert badge、Watchlist 命令 |
| （规划中）ZCode / DSH 等 Agent 用户 | 配置 MCP server / CLI | Agent 会话内调用 tools | 只读市场状态、Signal、Feed 健康、Replay、评估结果 |

### 1.2 概念定义（与代码一一对应）

| 概念 | 代码位置 | 说明 |
|---|---|---|
| **Core** | `src/market_sentinel/` | 纯 Python 包，无宿主依赖；确定性主链 + Intelligence sidecar + telemetry |
| **Provider** | `providers/`（base/factory/fake/replay/longbridge） | `MarketProvider` Protocol，单方法 `fetch_quotes(symbols)`；`fake` 默认、`replay` 读 JSONL、`longbridge` 需 `--extra live` + 3 个环境变量；`http` 是**故意保留的 stub**（选择即抛错） |
| **Host** | `apps/cursor-extension/`（TS） | 目前唯一的宿主实现；通过 `uv run --directory <coreRoot> market-sentinel --provider X daemon` 拉起 Core |
| **IPC** | `ipc/`（Protocol v1） | stdin/stdout JSONL：9 条 host→core 命令（hello/start/pause/resume/set_watchlist/get_state/host_interaction/user_feedback/shutdown）、6 类 core→host 消息（ready/ack/state/alert/shutdown_ack/error）；严格 request_id + 超时 |
| **Intelligence** | `intelligence/` | 可选异步 sidecar；`IntelligenceProvider.complete(payload, timeout_s)` Protocol；默认 DashScope（OpenAI-compatible HTTP，`DASHSCOPE_API_KEY`，默认模型 `qwen3.7-max-2026-06-08`，max_tokens 150）；deterministic router + episode budget(1) + 11 类 fallback 原因 + fail-open；输出结构化 JSON 并**拒绝交易建议**（中英 regex fail-closed） |
| **Telemetry/Evaluation/Tuning** | `telemetry/` `evaluation/` `tuning/` | 本地 append-only JSONL（`%LOCALAPPDATA%/MarketSentinel` 或 XDG）；评估只读聚合；tuning snapshot immutable（schema v2）且**无 apply/promote/deploy**，仅 before/after 对比 |
| **Extension** | `apps/cursor-extension/` | 10 commands、11 settings、 vitest 21 个 spec + VS Code electron smoke、VSIX 审计脚本；Python 不进 VSIX |
| **Dev tools** | `tools/live_probe/` | Tencent/Sina/Longbridge 探针（`python -m tools.live_probe ...`），dev-only 但被 7 个单测文件与 2 个 live 集成测试依赖，**不可删** |

### 1.3 production vs development/experiment

- **production**：`src/market_sentinel/*`（含 `health/`、`watchlist/`——它们是核心功能不是实验代码）、`apps/cursor-extension/src/**`（非测试部分）、`tests/fixtures/*.jsonl`（replay corpus，tuning 依赖）。
- **development-only**：`tools/live_probe/`、`tools/resume_benchmark.py`（未跟踪）、`tests/fixtures/generate_v02_replay.py`（fixture 生成器）。
- **experiment/历史**：`docs/` 20 个文件中约 13 个是历史 roadmap/RC 记录（见 §3.2）。
- **stub**：provider `http`（选择即抛 ValueError，错误信息指向 fake/replay/longbridge）。

---

## 2. 当前运行路径

### 2.1 主链（每个 tick，全部确定性代码）

```text
Provider (fake | replay | longbridge)
  → normalize_snapshot 校验（symbol/price/OHLC/volume/market_timestamp）
  → RingBuffer（乱序抑制、重复时间戳计数）
  → FeatureEngine（1m/5m/15m change、volume ratio、EMA5/20、RSI14、VWAP、session high/low）
  → EventDetector（6 规则：rapid_move / volume_spike / price_volume_expansion
                   / day_high_breakout / day_low_breakout / vwap_cross）
  → Dedupe → Cluster/Composer（episode）→ Cooldown（alert candidate）
  → WarmingPolicy（COLD/WARM/HOT 请求）→ AdaptiveScheduler（dwell + anti-flapping）
  → MarketStateStore（price/features/level/feed_status/latency/active_signals）
  → 出口：CLI 渲染 | Protocol v1 (state + alert) → Cursor Host | Telemetry
```

### 2.2 Intelligence sidecar（可选，异步，不阻塞 tick）

```text
SignalPipeline 结果 → IntelligenceCoordinator.observe_tick()（同步，压缩输入）
  → RouterPolicy（priority ≥ IMPORTANT / 价格+量+突破收敛 / ≥3 事件类型）
  → EpisodeCallBudget（每 episode 1 次，升级才允许 recall）
  → asyncio.Queue(8)（满则 drop + dropped_backpressure）→ 1 worker
  → Provider.complete(timeout 8s) → parse_model_output（结构校验 + 交易建议 fail-closed）
  → AnnotationRegistry（stale work 丢弃）→ Protocol v1 `intelligence` 字段
  失败路径：timeout/transport/malformed/rate_limited/unavailable/cancelled/stale_work/policy
  → FALLBACK（不产生 annotation，Rule Signal 不受影响）
```

### 2.3 观测闭环（低频，与主链解耦）

```text
Telemetry（18 种事件 + 4 种 feedback label，本地 JSONL，1MB×5 轮转，fail-open）
  → TelemetryReader → evaluate()（funnel/noise/host/intelligence/market-time/feedback 指标，
    "unavailable" 哨兵而非 0）→ `telemetry report`
UserFeedback（CLI daemon `user_feedback` / Cursor "Signal Feedback" 命令）→ feedback.jsonl
Tuning：`tuning snapshot`（baseline/candidate，7 个受证据支持参数）→
  `tuning compare`（固定 replay corpus 上跑 before/after/delta）→ 人工决策（不自动 apply）
```

### 2.4 时间语义（可测试性基线）

`clock.py` 定义 `Clock` Protocol（`wall_time`/`monotonic_time`），`SystemClock`/`FakeClock` 全量注入 engine、scheduler、health、cooldown、coordinator、providers；tuning replay 用 `FakeClock.set_wall()` 驱动整个引擎。AGENTS.md 第 15 条要求已满足。

---

## 3. 目录与文件处置

### 3.1 总体判断：**不需要大重排**

`src/ + tests/ + apps/cursor-extension/ + tools/` 的结构与 pnpm workspace、hatch 打包、vitest/pytest 路径配置深度耦合，重命名目录（如 `apps/cursor-extension → extension/`）收益低、破坏面大（workspace yaml、5 个 pnpm script、audit-vsix 路径、20+ 测试内的相对路径）。**建议保留现有目录，只做增补与 docs 收纳。**

### 3.2 docs/ 处置（19 个编号文档 + 1 个指令文件）

新外部开发者真正需要的只有 7 份；其余是历史记录。建议：

| 目标位置 | 文件 | 处置 |
|---|---|---|
| `docs/architecture/` | 01 任务书、10 Provider Source Audit、14 Intelligence Contract、16 Metrics Contract、09 MultiHost Spec | MOVE（09 标注 "not yet implemented"） |
| `docs/integrations/` | 12 Longbridge Setup → `longbridge.md`；新增 `cursor.md`、`zcode.md`、`deepseek-harness.md`、`mcp.md`（M4/M5/M7 产出） | MOVE + 新建 |
| `docs/development/` | 11 的探针用法提炼成 `live-probes.md`；发布检查清单（从 19 §提炼） | 新建 |
| `docs/history/` | 02、03、04、05、06、07、08、11、13、15、17、18、19、`CURSOR_开发总指令.md` | MOVE（保留原文，加一行 README 索引说明"历史记录"） |

> 注：`CURSOR_开发总指令.md` 是 v0.1 时代的 agent bootstrap 指令，引用了不存在的文件名（第 17 行），内容已被 AGENTS.md 取代——归档即可，不必删除。

### 3.3 根目录与其余文件处置

| File/Dir | Action | Reason |
|---|---|---|
| `LICENSE` | **CREATE**（缺，vsce 已警告；M1 补，类型待确认，默认建议 MIT） | 公开发布前置条件 |
| `CONTRIBUTING.md` / `SECURITY.md` | **CREATE**（M7/M8） | GitHub 开源标准 |
| `.github/workflows/` | **CREATE**（当前完全没有 CI） | M8 |
| `README.md` | **REWRITE**（M7） | 现为开发日志体（含发布状态叙述、验收流程、v0.6.5 边界自述），需改为陌生开发者视角 |
| `AGENTS.md` | **UPDATE** | §3"当前版本边界"停留在 v0.1 时代（"不要提前实现 LLM/Cursor UI…"，与 v0.6.5 现实矛盾）；其余工程规则仍有效，保留 |
| `CHANGELOG.md` | KEEP + 轻度规范化 | 有 per-version 条目，但混入大量 milestone dev-log 与 Unreleased 段 |
| `tools/live_probe/` | KEEP（dev-only，被 tests 依赖） | 见 §1.3 |
| `tools/resume_benchmark.py`（未跟踪） | **DECISION**：重命名为 `tools/benchmark_full_session.py` 并提交 + 文档化（推荐），或保持未跟踪/删除 | 内容是完整的确定性全 session 基准（写 `.tmp/`，无 secrets，API 用法与 v0.6.5 兼容）；名字 "resume benchmark" 表明是个人简历素材，是否进公开 repo 由所有者定 |
| `tests/fixtures/generate_v02_replay.py` | KEEP（fixture 生成器，标注 dev-only） | replay corpus 可复现性 |
| `.gitignore` | 扩展（加 `*.pyc` 已有、`.vscode-test/` 已有、考虑 `dist/` 已有——基本够用，M1 复核一遍） | — |
| `.coverage .venv .tmp dist node_modules __pycache__ *.vsix .vscode-test` | 已正确 IGNORE，勿提交 | 本地状态/构建产物 |
| `data/`（watchlist 本地状态） | 已 IGNORE，保持 | 用户本地数据 |
| **secrets 检查** | **干净** | tracked 文件中无 key/secret 模式命中；`git log --all` 从未提交过 `.env`/credential 文件；Longbridge 凭据仅以环境变量名出现在文档与代码中，且 TS 测试断言凭据不进 argv/env/settings |
| **本地绝对路径检查** | **干净** | 仅 `D:\path\to\...` 模板占位符（README:221、docs/19:254）；`/Users/me/proj` 是 telemetry denylist 测试固件 |

### 3.4 版本与历史完整性

- tags：v0.1.0 / v0.2.0 / v0.3.0 / v0.6.5。**v0.4.0、v0.5.0、v0.6.0 从未打 tag——这是文档化的有意行为**（CHANGELOG 与 RC 文档明确 "not tagged"），不是事故，不建议补 tag。
- remote：`https://github.com/vagabond-zzz/MarketSentinel.git`（README 第 16 行已写明）。v0.6.5 已推送并在 GitHub 上建了 release。
- **隐私残留**：所有 commit 的 author 使用了个人 QQ 邮箱（`git log` 可见）。已在公开历史中，改写需要 force-push 重写历史（破坏 clone 兼容）。建议：**接受现状**，不在本次产品化中重写历史；后续 commit 可换 noreply 邮箱。（待所有者确认，默认不动。）

---

## 4. 现状测试与质量基线

- Python：`uv run pytest` 默认排除 `live` marker；`integration` marker 默认参与（全部离线）；coverage gate `fail_under = 85`；v0.6.5 记录为 649 passed / coverage 90.61%。
- TS：`pnpm test`（vitest，含可跳过的真实 python 集成测试：uv 可用则真跑 daemon 握手）、`pnpm typecheck`、`pnpm lint`、`pnpm build`、`pnpm test:extension-host`（VS Code electron，非真实 Cursor）。
- live 测试分两类：Longbridge smoke（无凭据即 skip）、Tencent gate（**fail-closed**，选中即真联网）。
- 本次审计实测基线：见 §9 附录（后台运行结果回填）。

---

## 5. Proposed Public API（M2 目标形态）

### 5.1 CLI（第一等入口）

保持现有命令不破坏，新增两个：

```text
market-sentinel demo      # 无需任何 key：fake provider 驱动一段固定脚本，
                          # 依次呈现 features → events → signals → intelligence(mock) → 输出
market-sentinel doctor    # 环境诊断（见 §5.3）
```

现有 `watchlist / run / daemon / telemetry / tuning` 全部保持。`daemon` 继续作为 Cursor Host 专用协议入口，**不**作为 Agent 通用入口。

### 5.2 Capability 边界（新增 `market_sentinel.capabilities`，稳定、只读）

不直接暴露内部 Python 类给集成层；DTO 复用 Protocol v1 的 wire 模型（`ipc/dto.py` 的 `WireMarketState/WireSignal/...`），避免出现第三套模型：

```text
get_market_state() -> WireMarketState
get_symbol_state(symbol) -> WireSymbolState
get_active_signals() -> list[WireSignal]
get_signal(signal_id) -> WireSignal          # 含 intelligence annotation 视图
get_feed_health() -> {status, per-symbol}
get_recent_events(limit) -> [...]
run_replay(fixture, symbols?) -> ReplaySummary      # 有界、同步返回摘要
evaluate(data_dir?, run_id?) -> EvaluationReport    # 只读聚合
```

语义约束：全部 read-only；无 threshold/config/credentials 写路径；无交易；timeout 有界；错误映射到 protocol `ErrorCode` 风格的稳定错误码。

### 5.3 doctor 检查项

Python 版本、uv、依赖安装（wheel import）、watchlist 文件可写、默认 data dir 可写、provider 配置（Longbridge 凭据存在性只报 ⚠ 不读取值）、Intelligence 配置（key 环境变量是否存在，不发真实请求；`fake` provider 自检）、Replay fixture 目录可发现、MCP server 可启动（`--probe` 时实际拉起一次握手）、ZCode/DSH 配置探测（只读检查 config 文件是否存在该 server 条目）。

---

## 6. Proposed Integration Architecture（M3–M6）

```text
                    ┌──────────────────────────────────────────┐
                    │            Market Sentinel Core           │
                    │  runtime / signals / intelligence / ...   │
                    └───────────────┬──────────────────────────┘
                                    │ （唯一边界，read-only）
                    ┌───────────────▼───────────────┐
                    │   market_sentinel.capabilities │   ← 稳定能力层（M2/M3）
                    └──────┬──────────────┬─────────┘
                           │              │
              ┌────────────▼───┐   ┌──────▼───────────────┐
              │ MCP stdio server│   │ CLI（demo/doctor/run）│
              │ market_sentinel │   └──────────────────────┘
              │      .mcp       │
              └─┬──────────┬────┘
                │          │        （都是纯配置，无代码适配）
        ┌───────▼───┐  ┌───▼──────────────┐
        │   ZCode   │  │ DeepSeek Harness  │   （+ 未来的 Claude Code 等）
        │ mcp.servers│  │ dsh-mcp-client    │
        └───────────┘  └──────────────────┘

  Cursor/VS Code 维持现状：专有 Protocol v1 daemon（不迁移到 MCP，UI 低延迟需求不同）
```

要点：

1. **Core 不出现任何 `if zcode / if deepseek` 分支**。ZCode/DSH 接入 = 两个宿主各自的 JSON 配置块 + 一份文档，零宿主代码进 Core。
2. Cursor 适配器（现有 TS 扩展）保持专有 daemon 协议——它是唯一需要亚秒推送与双向命令的宿主；Agent 宿主是拉取式只读场景，需求不同，不强行统一。
3. MCP server 默认**离线模式**（fake/replay provider、telemetry 关闭 NoOp、独立于 daemon 进程），避免双写 telemetry JSONL 与双开行情进程的冲突；live provider 由使用者显式配置 env 开启。
4. AGENTS.md §3 现行"不要实现 ZCode Adapter / MCP"是 v0.1 边界，本次由所有者指令解禁；M7 更新 AGENTS.md 使文档与现实一致。

---

## 7. ZCode 集成选项（已核实，非猜测）

**ZCode 原生支持 MCP**（官方文档 zcode.z.ai/en/docs/mcp-services + 本机 plugin 文档双重确认）：

- 配置位置：用户级 `~/.zcode/cli/config.json` 或工作区级 `<repo>/.zcode/config.json` 的 `mcp.servers`；entry = `{type:"stdio", command, args[], env, timeoutMs}`；session 启动自动连接。
- 工具命名：`mcp__<server>__<tool>`。
- 备选集成点：plugin（`.zcode-plugin/plugin.json` 可捆绑 mcpServers/skills/commands，走 marketplace 安装）、skills、hooks——都真实存在。

| Option | 方案 | 评估 |
|---|---|---|
| **A（推荐）** | MCP stdio server + `docs/integrations/zcode.md` 提供可粘贴配置 | 零宿主代码；与 DSH 共用同一 server；先跑通再考虑 B |
| B | ZCode plugin（bundling MCP server + 使用 skill） | 适合 MCP 稳定后的分发形态；有 manifest/marketplace 维护成本；**M6 之后的可选项** |
| C | 纯 CLI 适配（shell tool 调 `market-sentinel ...`） | 始终可用的兜底；失去 schema/发现性；作为文档中的 fallback 而非主推 |

---

## 8. DeepSeek Harness 集成选项（已核实）

**DSH 是真实产品**：2026-08-13 发布的 developer preview（npm `@deepseek-ai/dsh`，基于 Cordis 插件框架，Node 22+，model-agnostic）。注意：**developer preview，官方明示可能有破坏性变更**——文档必须让用户 pin 版本。

- MCP：官方插件 `@deepseek-ai/dsh-mcp-client`，支持 **stdio 与 Streamable HTTP**，配置字段 `serverName/transport/command/args/env`；工具同样呈现为 `mcp__<serverName>__<tool>`；**只桥接 tools，不桥接 resources/prompts**。
- 其他集成面：JSON-RPC over stdio 的 SDK（`packages/sdk`，用于嵌入式驱动整个 DSH runtime——对本项目是反向需求，不需要）；`--profile headless` 单任务子进程模式。

| Option | 方案 | 评估 |
|---|---|---|
| **A（推荐）** | 与 ZCode 共用 MCP stdio server，经 `dsh-mcp-client` 接入 | 同一 server 双端复用；文档给 YAML/JSON 配置片段并标注 preview 风险与版本 pin |
| B | JSON-RPC SDK 嵌入 | 过重，否 |
| C | headless CLI 子进程 | 兜底可用，不作主推 |

---

## 9. MCP 是否值得作为共同协议 —— **是**

判定依据：

1. 两宿主均为**一等支持**且约定一致（stdio transport、`command/args/env`、`mcp__server__tool` 命名）。
2. 一次实现，未来 Claude Code / Cursor(AGENTS) 等宿主零边际成本。
3. 与 AGENTS.md §10 IPC 原则兼容（stdio JSON、无 HTTP 服务），且 MCP server 是**独立可选模块**（建议 optional dependency extra `[mcp]`，官方 `mcp` Python SDK），不进核心依赖树、不进高频主链。

约束与注意：

- **只暴露 tools**（DSH 不桥接 resources/prompts）；MCP resources 以后可作为 ZCode-only 增量。
- 工具面最小化（不做全量暴露）：`get_market_state`、`get_active_signals`、`get_feed_health`、`explain_signal`、`run_replay`、`evaluate`。replay/evaluate 有界同步返回摘要，避免长调用撞 ZCode 默认 30s tool timeout。
- server 独立版本化（tool schema 版本随 Protocol v1 走，server 自身可独立 patch）。
- Windows 注意：`command` 用解释器绝对路径、`args` 数组、ZCode 配置 schema 严格（未知键静默丢弃 server）。

---

## 10. Risk List

| # | 风险 | 等级 | 缓解 |
|---|---|---|---|
| 1 | Protocol v1 在 Python（`ipc/dto.py`）与 TS（`protocol/types.ts`+`guards.ts`）**手工双写**，无 codegen/shared schema | 中 | M3 不动它；在 README 标注"改协议需双侧同步 + 现有 guards 测试兜底"；列为后续改进（codegen 或 shared JSON Schema） |
| 2 | MCP SDK 引入新依赖 | 低 | optional extra `[mcp]`；核心依赖树不变；无 SDK 时给出明确安装指引 |
| 3 | DSH 是 developer preview，可能有破坏性变更 | 中 | 文档标注 + 版本 pin；CLI 兜底路径始终存在；tool 面保持小而稳 |
| 4 | Agent 误触写路径（threshold/credentials/config） | 高（若发生） | capability 层只读；MCP server 不注册任何写工具；tuning 无 apply 通道（现状已保证） |
| 5 | MCP server 与 Cursor daemon 并存导致 telemetry 双写/资源竞争 | 中 | MCP 默认离线模式 + NoOp telemetry + 独立 data dir 默认；文档说明不要同时接同一 longbridge live 账号高频拉取 |
| 6 | 目录重排破坏 pnpm/hatch/vitest/audit 路径 | 中（若重排） | 已决定**不重排**运行时目录，仅收纳 docs 与新增顶层文件 |
| 7 | README 过度承诺 | 中 | M7 每条 feature 对照代码与 clean-room 验证结果；provider 状态如实标注（http=stub、longbridge=需凭据、tencent/sina=probe-only） |
| 8 | coverage gate 85% 与新模块 | 低 | capabilities/mcp/doctor 同 milestone 内带测试（现有习惯：90.61%） |
| 9 | git 历史含个人 QQ 邮箱 | 低 | 仅披露不改写（见 §3.4）；后续 commit 可换 noreply 邮箱 |
| 10 | AGENTS.md 版本边界与本次工作冲突 | 低 | 本次为所有者显式授权的新轨道；M7 更新 AGENTS.md 反映新边界（集成层规则固化：只读、不许宿主逻辑进 Core） |
| 11 | Windows 一等公民但 CI runner 差异 | 中 | M8 矩阵：`windows-latest` + `ubuntu-latest`；Windows 本机已验证命令均在 README 记录前实测 |
| 12 | `market-sentinel` PyPI 名称占用风险 | 低 | 本期不做 PyPI 发布（uv/clone 路径足够）；README 用 `uv sync` 而非 `pip install market-sentinel` |

---

## 11. Milestone Plan（待确认后执行）

| M | 内容 | 关键产出 | 验收 |
|---|---|---|---|
| **M1** | Repository Cleanup | LICENSE；`.gitignore` 复核；docs 收纳（§3.2/§3.3 表执行）；`docs/REPOSITORY_CLEANUP.md` 先行记录每个候选再执行；`resume_benchmark.py` 处置；`git status` 干净 | 全部测试绿；`git grep` 无 secrets/本地路径；README/docs 内部链接不因移动而断 |
| **M2** | Public API / CLI | `market_sentinel.capabilities`（含 DTO/错误码/timeout）；CLI `demo`、`doctor`；单测覆盖 | `market-sentinel demo` 无 key 5 分钟可跑通；doctor 输出 §5.3 清单；pytest + ruff 绿 |
| **M3** | Integration Layer | capability 边界冻结（文档 `docs/architecture/capabilities.md`）；MCP stdio server（optional extra `[mcp]`，tools-only，离线默认）；MCP 协议层测试（内存 client 驱动握手+每工具往返） | server 可被标准 MCP client 列出 6 个 tool；Core 无任何宿主分支；未装 extra 时给出明确报错 |
| **M4** | ZCode Adapter | `.zcode/config.json` 示例（examples/）+ `docs/integrations/zcode.md`（prereq/install/config/tools/example/failure modes/limitations）；本机真实 ZCode 会话 e2e 验证记录 | 在本机 ZCode 里实际调用 `mcp__market-sentinel__get_market_state` 等工具成功并有证据记录 |
| **M5** | DeepSeek Harness Adapter | `docs/integrations/deepseek-harness.md`（dsh-mcp-client 配置、preview 风险、版本 pin）；可验证的接入步骤；本机如可安装则 e2e，否则明确标注"按官方文档配置、未在本机验证"并如实写入 limitations | 文档如实；不夸大 |
| **M6** | MCP 加固 | 工具 schema/错误码版本化；负路径测试（坏 fixture、超时、未配置 provider）；（可选）ZCode plugin 打包评估 | MCP 工具面冻结并写入 `docs/integrations/mcp.md`；全测试矩阵绿 |
| **M7** | README / Docs | 重写 README（英文，含 Mermaid 架构图、Quick Start、Configuration、Providers、Intelligence、Integrations、Security、Roadmap）；CONTRIBUTING/SECURITY；AGENTS.md 边界更新；CHANGELOG 规范化 | §15 的 Clone/Understand/Run/Develop/Integrate/Trust 六项逐条自查通过 |
| **M8** | CI / Packaging | `.github/workflows/`：python（pytest+coverage+ruff，win+ubuntu 矩阵）、extension（pnpm test/typecheck/lint/build+vsix audit）、secret scan、clean-checkout job | CI 从全新 checkout 全绿；VSIX 审计在 CI 内执行 |
| **M9** | Final Verification | 干净 clone → 严格按 README 执行 §15 十二项验证清单；结果回写 README/docs | 12/12 通过；失败项修复后重跑 |

每个 M 结束：跑相关测试 → `git status`/`git diff` 自查 → 确认架构红线未破 → 更新 docs → 独立 commit（Conventional Commits）。建议整体在 `feat/productization` 分支进行，M9 后合并 master。

---

## 12. 待所有者确认的问题

1. **M1 开工确认**（本文档其余部分如有异议请一并指出）。
2. **LICENSE 类型**：MIT（默认建议）/ Apache-2.0 / 其他。
3. **README 语言**：英文（推荐，GitHub 公开项目惯例）/ 中英双语。
4. **`tools/resume_benchmark.py`**：重命名为 `tools/benchmark_full_session.py` 提交（推荐，是可复现的性能基准）/ 保持未跟踪 / 删除。
5. **git 历史中的 QQ 邮箱**：接受现状（推荐，不重写历史）/ 需要讨论。

---

## 附录 A：审计方法与证据来源

- 全量 tracked 文件清单（312 个）+ git log（69 commits）/tags/branches/remotes/`git status --ignored`。
- 四路并行深读：Python Core（CLI/runtime/ipc/providers/intelligence/telemetry/tuning/clock 全部源文件）、Cursor 扩展（package.json/extension/host/ipc/protocol/UI/测试/审计脚本）、docs+tests+仓库卫生（19 份文档逐一定性、live 测试门控、tools 审计、大文件/路径/secrets 扫描）、ZCode 与 DSH 平台调研（本机官方 plugin 文档 + zcode.z.ai 官方文档 + DSH 多源交叉验证）。
- secrets 扫描：`git grep`（key/secret/token 模式）零命中；`git log --all --diff-filter=A` 确认从未提交过 env/credential 类文件；绝对路径 grep 仅命中模板占位与测试固件。
- 实测基线见附录 B。

## 附录 B：本次审计实测基线（2026-10-04）

| 检查 | 结果 |
|---|---|
| `uv run pytest`（默认排除 live） | **649 passed, 5 deselected**（8.56s），全绿 |
| `pnpm test`（vitest，含 uv 可用时的真实 daemon 集成测试） | **21 files / 200 tests passed**，全绿 |
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 唯一不合格文件是**未跟踪的** `tools/resume_benchmark.py:121`；tracked 代码 215 个文件全部合规 |

结论：master @ ec9f502 出厂状态健康，M1 可以在干净基线上开始。
