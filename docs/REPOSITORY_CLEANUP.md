# Repository Cleanup 记录（M1）

> 日期：2026-10-04 · 基线：`master @ ec9f502`（v0.6.5）
> 本文档记录产品化 M1（Repository Cleanup + Open Source Foundation）中每一个文件处置决策。
> 范围约束：不改 Core 业务逻辑、不改 Protocol v1、不重排 runtime 目录、不重写 git history。
> 前置审计见 [PRODUCTIZATION_AUDIT.md](PRODUCTIZATION_AUDIT.md)。

## 1. 决策总表

### MOVED — docs 归位（20 个文件，全部 `git mv`，内容不变）

**归入 `docs/architecture/`（当前契约，改语义名）：**

| 原路径 | 新路径 | 理由 |
|---|---|---|
| docs/01_任务书_Market_Sentinel.md | docs/architecture/charter.md | 架构基准任务书，仍是当前契约 |
| docs/09_Roadmap_v1.0_MultiHost.md | docs/architecture/multihost-spec.md | 多宿主目标架构规格（未实现的前瞻规格） |
| docs/10_v0.4_Provider_Source_Audit.md | docs/architecture/provider-source-audit.md | 数据源审计 + 冻结的 MarketSnapshot 契约，外部开发者需要 |
| docs/14_v0.5_Intelligence_Contract.md | docs/architecture/intelligence-contract.md | 冻结的 Intelligence 契约，改 intelligence 层前必读 |
| docs/16_v0.6_Metrics_Contract.md | docs/architecture/metrics-contract.md | 冻结的 metrics 契约，改 telemetry/evaluation 前必读 |

**归入 `docs/integrations/`：**

| 原路径 | 新路径 | 理由 |
|---|---|---|
| docs/12_v0.4_Longbridge_Provider_Setup.md | docs/integrations/longbridge.md | 唯一的 provider 接入指南，归入 integrations；后续 ZCode / DeepSeek Harness / MCP 文档将加入此目录 |

**归入 `docs/history/`（保留原文件名，内容一字未改）：**

| 文件 | 类型 |
|---|---|
| 02_Roadmap_v0.1_Core.md | 已完成的 v0.1 roadmap |
| 03_Roadmap_v0.2_Event_Engine.md | 已完成的 v0.2 roadmap（含冻结语义记录） |
| 04_Roadmap_v0.3_Cursor_MVP.md | 已完成的 v0.3 roadmap |
| 05_Roadmap_v0.4_to_v1.0_Overview.md | 跨版本总览（历史基线为主） |
| 06_Roadmap_v0.4_Live_Market_Data.md | 已完成的 v0.4 roadmap |
| 07_Roadmap_v0.5_Market_Intelligence.md | 已完成的 v0.5 roadmap |
| 08_Roadmap_v0.6_Feedback_and_Tuning.md | 已完成的 v0.6 roadmap |
| 11_v0.4_M1a_Live_Semantics_Bakeoff.md | 历史实验记录（探针对比实测） |
| 13_v0.4_Release_Candidate.md | v0.4 RC 停止报告（v0.4 未单独发版，有文档记录） |
| 15_v0.5_Release_Candidate.md | v0.5 RC 记录 |
| 17_v0.6_Release_Candidate.md | v0.6 RC 记录 |
| 18_v0.6.5_UX_Polish.md | v0.6.5 实现记录 |
| 19_v0.6.5_Release_Candidate.md | v0.6.5 发布记录 |
| CURSOR_开发总指令.md | v0.1 前 agent bootstrap 指令，已被根目录 AGENTS.md 取代 |

> 原则：**不因"旧"而删除**。history/ 内的版本边界与待办状态不反映当前现实，`docs/README.md` 索引中已注明。

### ADDED — 新增

| 文件 | 理由 |
|---|---|
| docs/README.md | 文档索引：三类目录的定位 + history 清单，陌生开发者的入口 |
| docs/REPOSITORY_CLEANUP.md | 本文档 |
| docs/PRODUCTIZATION_AUDIT.md | M0 审计报告（所有者要求的决策依据） |
| CONTRIBUTING.md | 开源基础文件：环境、命令、项目不变量、commit 规范 |
| SECURITY.md | 开源基础文件：数据/凭据边界、漏洞报告渠道 |
| tools/benchmark_full_session.py | 由未跟踪的 tools/resume_benchmark.py KEEP 而来（见 §2） |

### KEPT — 保留（含曾经是删除候选的项）

| 文件/目录 | 理由 |
|---|---|
| tools/live_probe/ | dev-only 探针，但被 7 个单测文件（tests/unit/live_probe/）与 2 个 live 集成测试 import，是**事实上的测试依赖**，删除会破坏测试 |
| tests/fixtures/generate_v02_replay.py | fixture 生成器，保证 replay corpus 可复现 |
| AGENTS.md | 工程规则仍有效且与 pyproject 一致；§3 的 v0.1 时代版本边界已过时，按约束 M1 不改内容，留待 M7 随文档重写一并更新 |
| CHANGELOG.md | 现有 per-version 条目真实准确（不伪造历史），仅格式非 Keep-a-Changelog 标准；整理留给 M7，M1 不动 |
| README.md | 按约束 M1 只做引用路径修复，产品化重写留给 M7 |
| `http` provider stub（src/market_sentinel/providers/factory.py） | 故意保留的显式 stub：选择即抛错并提示可用 provider；是有意行为而非死代码 |

### IGNORED — 核实为本地状态，.gitignore 已覆盖，无需改动

`.venv/ .coverage .pytest_cache/ .ruff_cache/ .tmp/ data/ node_modules/ dist/ out/ *.vsix .vscode-test/ __pycache__/` —— 全部已在 .gitignore 中，`git status` 无未预期产物。

### DELETED — 无

本次没有删除任何 tracked 文件。

### PENDING — 需所有者决策

| 项 | 状态 |
|---|---|
| LICENSE | **未创建**。仓库现有内容中没有 license 声明或意向（docs/19 仅记录了 vsce 因缺 LICENSE 的警告）。按约定不替所有者选择许可证类型；所有者确定后新建 LICENSE 文件即可，无其他文件需要联动（当前无 CI / package metadata 引用许可证）。注意：未加 LICENSE 前按 GitHub 默认条款，他人无权复用/分发本仓库代码 |

## 2. tools/resume_benchmark.py 处置

- 原状态：**未跟踪**，不在 git 中；内容是完整的确定性全 session 基准脚本（合成一个 A 股交易日、10 标的、注入 surge/wobble 窗口，跑完整 MarketEngine + Fake Intelligence，输出 quote/event/signal 计数、tick 延迟 avg/p50/p95/max、LLM 触发占比、检测延迟），输出写到 gitignored 的 `.tmp/`。
- 安全检查：无 secrets、无网络、无绝对个人路径（`REPO` 由脚本自身位置推导）。
- 决策：**KEEP**。它是当前 API 下可复现的性能基准，对公开项目有展示价值。处理：重命名为 `tools/benchmark_full_session.py`（原名 "resume benchmark" 是个人语境），`ruff format` 修复其格式问题（该文件是全仓库唯一 format 不合规文件），docstring 微调。不改任何引擎调用语义。

## 3. 引用修复清单

代码（py/ts/json/toml/yaml）对 docs/ **零引用**（grep 确认），docs 移动只涉及 markdown 互引。已修复：

| 文件 | 修复数 | 说明 |
|---|---|---|
| **tests/unit/telemetry/test_metrics_contract.py** | 1 | **隐藏运行时依赖**：测试用 `"docs" / "16_v0.6_Metrics_Contract.md"` 程序化拼路径读取契约文档做内容断言（`docs/` 前缀的文本 grep 不可见），已改为 `"docs" / "architecture" / "metrics-contract.md"`。这是本次唯一一处代码级引用 |
| README.md | 9 | §3.9 阅读表、§3.5/§6.5 的 metrics contract 引用、§7.3 release audit 引用 |
| apps/cursor-extension/README.md | 1 | Longbridge 指南引用 |
| docs/architecture/provider-source-audit.md | 3 | 指向 05/06/11 的引用 |
| docs/architecture/metrics-contract.md | 1 | 指向 17 的引用 |
| docs/history/05_Roadmap_v0.4_to_v1.0_Overview.md | 4 | 裸文件名引用（06/07/08 → history，09 → architecture） |
| docs/history/06_Roadmap_v0.4_Live_Market_Data.md | 2 | 12 → integrations、13 → history |
| docs/history/07_Roadmap_v0.5_Market_Intelligence.md | 2 | 14 → architecture、15 → history |
| docs/history/08_Roadmap_v0.6_Feedback_and_Tuning.md | 3 | 16 ×2 → architecture、17 → history |
| docs/history/11_v0.4_M1a_Live_Semantics_Bakeoff.md | 1 | 13 → history |
| docs/history/13_v0.4_Release_Candidate.md | 5 | 06/10/11/12/13 引用 |
| docs/history/15_v0.5_Release_Candidate.md | 1 | 14 → architecture |
| docs/history/17_v0.6_Release_Candidate.md | 1 | 15 → history |
| docs/history/18_v0.6.5_UX_Polish.md | 1 | 19 → history |
| docs/history/CURSOR_开发总指令.md | 4 | 01/02/03/04 引用 |

保留不动：`docs/history/CURSOR_开发总指令.md:17` 引用的 `docs/05_Roadmap_v0.4_Intelligence_and_v1.0_MultiHost.md` —— 该文件**从未存在过**（审计已记录），属历史原文中的笔误；以及各文档内的 ASCII 目录树示意（历史原貌）。

## 3.1 隐藏依赖教训

移动前的引用审计覆盖了文本 grep（`docs/`、旧文件名、import、package scripts、pyproject/vitest/vsce 配置），但漏掉了**程序化路径拼接**——`test_metrics_contract.py` 用 `Path(...) / "docs" / "16_....md"` 读文档并在断言中校验其内容，该测试在移动后立即失败并被捕获修复。结论：docs 内的"契约文档"不完全是文档，部分被测试当作 fixture 消费；后续再移动 `docs/architecture/` 下的契约文件时，先 `git grep '"docs"'` 而不只是 `grep docs/`。

## 4. 卫生检查结果

- secrets 扫描（`git grep` key/secret/token/app_secret/access_token 模式）：**零命中**。
- `git log --all --diff-filter=A --name-only`：**从未提交过** `.env` / credential / key 类文件。
- 本地绝对路径：仅 `D:\path\to\...` 模板占位（README §3.3 示例、history/19）与 telemetry denylist 测试固件 `/Users/me/proj`，均非真实泄漏。
- git 提交历史的 author 使用个人 QQ 邮箱：按约定**不重写历史**；后续 commit 使用当前 Git identity，不在公开文档中强调。
- 版本 tag 断档（v0.4.0 / v0.5.0 / v0.6.0 未打 tag）是 CHANGELOG 与 RC 文档记录过的有意行为，不补 tag。

## 5. 验证结果

M1 完成时实测（2026-10-04，HEAD = 61885a9）：

| 检查 | 结果 |
|---|---|
| `uv run pytest` | **649 passed, 5 deselected**（live 排除），全绿 |
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 218 files already formatted |
| `pnpm lint` / `pnpm typecheck` / `pnpm build` | 全部通过 |
| `pnpm test`（vitest） | 21 files / 200 tests passed |
| `git diff --check` | 无空白错误 |
| `git status` | 工作区干净 |

提交拆分：

```text
a09468a docs: organize documentation into architecture, integrations, and history
8687b4e docs: add CONTRIBUTING and SECURITY guides
61885a9 chore: add deterministic full-session benchmark tool
```
