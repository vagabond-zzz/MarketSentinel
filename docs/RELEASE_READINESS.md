# Release Readiness（M6）

> 日期：2026-10-05 · 基线：`master @ b5d67a9` + M6 提交
> 性质：发布就绪审计，非营销材料。状态取值：`READY / PASS / UNKNOWN / BLOCKED / DEFERRED`。
> 不创建 GitHub Release / tag；下一步 narrative（M7）、CI（M8）、外部 clean-room 审计（M9）另行执行。

## 1. 状态矩阵

| Area | Status | 证据 |
|---|---|---|
| Core tests | PASS | `uv run pytest`：726 passed, 5 deselected（live 排除） |
| TypeScript tests | PASS | `pnpm lint / typecheck / test / build` 全绿（21 files / 200 tests，含 uv 可用时的真实 core 进程集成测试） |
| Ruff | PASS | `ruff check .` 与 `ruff format --check .` 全过（239 files） |
| Wheel build | PASS | `uv build` → `market_sentinel-0.6.5-py3-none-any.whl`（125 entries；`License-Expression: MIT`；含 capabilities / mcp_server / cli / data fixture；无 tests、无凭据、无本机路径） |
| sdist build | PASS | `market_sentinel-0.6.5.tar.gz`（346 entries；含 src/tests/docs/LICENSE；无 .venv / node_modules / 构建产物） |
| Fresh install | PASS | 全新 venv（无 PYTHONPATH、无 repo cwd）安装 wheel：`import market_sentinel.__file__` 指向 site-packages |
| CLI | PASS | 干净安装后 `--help` 及全部子命令 help 正常；`run/daemon/demo/doctor/mcp/telemetry/tuning` 语义无互相污染 |
| Demo | PASS | 干净安装后 `market-sentinel demo` 输出与 repo 运行完全一致（43 batches / 129 quotes / 55 events）——fixture 已随包分发 |
| Doctor | PASS | 干净安装后 `doctor` 正常；MCP extra 缺失时 `mcp` 命令给出可操作错误（exit 2，无 traceback） |
| MCP optional dependency | PASS | core 安装后 `import mcp` 失败（SDK 不入核心依赖树）；`pip install 'market-sentinel[mcp]'` 后 stdio 握手 + 6 tools + 干净退出（exit 0） |
| Live optional dependency | PASS | 无 SDK/凭据时 `--provider longbridge` fail-closed：可操作报错 + exit 2，值不打印 |
| Secret hygiene | PASS | tracked 文件扫描（api key / sk- / Bearer / password / app_secret 模式）零命中；仓库内只有环境变量**名**（DASHSCOPE_API_KEY / LONGBRIDGE_*） |
| Repository hygiene | PASS | `git ls-files` 无 .env / .zcode / DSH_HOME / 会话日志 / telemetry / feedback / tuning 产物；M4/M5 宿主验证数据未入库 |
| Documentation consistency | PASS | 宿主验证声明与实际一致（见 §3）；DSH 保留 developer preview 标注；无 trade/config-mutation 暗示；安装命令均经实际执行 |
| License | **READY** | **MIT — Status: READY — Decision: USER-APPROVED**。`LICENSE`（c）2026 MarketSentinel contributors；pyproject `license = "MIT"`（wheel METADATA `License-Expression: MIT`）；README 有 License 段；无双重许可表述 |
| Version | PASS（现状一致） | pyproject / METADATA / CHANGELOG / doctor 均为 0.6.5；M2–M6 记录于 CHANGELOG `Unreleased`（无版本 bump）。**下一发布版本号 = owner 决策（见 §4）** |
| CI | **VERIFIED**（2026-10-05） | 首次真实 Actions 运行全绿：run [37249350623](https://github.com/vagabond-zzz/MarketSentinel/actions/runs/37249350623)（commit 78f4a66）。python 两轮 pytest（713+2 skipped → 726）、ruff、typescript（19 files passed + 2 integration skipped）、package（artifact 检查 + fresh-install smoke + MCP/live 边界 + 握手）、hygiene 全部 PASS；logs 逐 job 审计。前两次运行暴露并修复两个 CI 配置问题（smoke 的 data-dir 假设、握手 pip 的相对 file:// URL），未触碰产品代码 |
| ZCode host | VERIFIED | 0.16.9，见 [integrations/zcode.md](integrations/zcode.md)（2026-10-05） |
| DSH host | VERIFIED | 0.2.0-rc.2，见 [integrations/deepseek-harness.md](integrations/deepseek-harness.md)（2026-10-05） |

M6 未修改 `mcp_server/` 实现（仅 demo fixture 与文档），因此 M4/M5 的宿主验证证据继续有效，未做伪造的"重新验证"。

## 2. 打包要点（本次修复）

1. **Demo 自包含**（M2 遗留 gap）：demo fixture 以包数据形式随 wheel 分发（`market_sentinel/data/multi_a_share_ui.jsonl`），干净安装不再依赖 repo 的 `tests/fixtures`；`--fixture` 仍可指定任意 replay JSONL。
2. **`.gitignore` 修复**：`data/` 规则未锚定根目录，会遮蔽包内 `src/market_sentinel/data/`；已改为 `/data/`。
3. **License 元数据**：PEP 639 SPDX 表达式，wheel 内含 `dist-info/licenses/LICENSE`。
4. hatchling 的 sdist 按 VCS 跟踪文件选择——新增包数据必须先 `git add` 再 build（已在流程中体现）。

## 3. 文档一致性声明

- `docs/integrations/mcp.md` 的 supported-vs-verified 矩阵只包含已实测的宿主版本；ZCode / DSH 均标注了具体版本与日期，未声称"所有未来版本支持"。
- DSH 相关内容保留 developer preview 标注与升级复验要求。
- 全部文档中的 MCP 表述维持"标准 MCP、六个只读工具"；SECURITY.md 的"不可交易/不改配置/不执行任意代码"边界未变。
- README 新增的只有 License 段（§二十.5 要求的一致性）；产品化 narrative 重写留给 M7。

## 4. Blockers / Unknowns / Deferred

### BLOCKED

无。License 决策已由 owner 给出（MIT）。

### UNKNOWN（不阻止发布）

- 未来 Python / ZCode / DSH 版本行为（各 integration 文档已标注验证版本）。
- ZCode GUI Settings→MCP 呈现、DSH GUI/Web profile、DSH reconnect 上限耗尽行为。

### DEFERRED（明确的后续 milestone）

| 项 | 去向 |
|---|---|
| CI 持续运行 | 已生效（push master / PR 触发）；host verification、live vendor、GUI 仍 out of band |
| README / 产品叙事重写（英文、架构图、Quick Start 打磨） | M7 |
| 外部视角 clean-room 全量审计（clone→install→verify 全链） | M9 |
| 创建 GitHub Release / tag | owner 批准后（M9 后） |
| **下一发布版本号**（0.6.5 之后如何容纳 M2–M6：0.7.0 / 0.6.6 / 1.0.0-rc 由 owner 决定） | owner 决策，不阻塞 M6 |
| PyPI 发布 | 未排期（当前分发路径 = clone + `uv sync`） |

## 5. 复现命令

```bash
uv run pytest                                   # 726 passed
uv run ruff check . && uv run ruff format --check .
pnpm lint && pnpm typecheck && pnpm test && pnpm build
uv build                                        # wheel + sdist
# 干净安装验证：
python -m venv <tmp>/venv && <tmp>/venv/Scripts/pip install dist/market_sentinel-0.6.5-py3-none-any.whl
<tmp>/venv/Scripts/market-sentinel --help && <tmp>/venv/Scripts/market-sentinel demo && <tmp>/venv/Scripts/market-sentinel doctor
<tmp>/venv/Scripts/market-sentinel mcp          # 无 extra：可操作报错 exit 2
pip install 'market-sentinel[mcp] @ file://<abs-path>/dist/market_sentinel-0.6.5-py3-none-any.whl'
<tmp>/venv/Scripts/market-sentinel mcp          # 握手 → 6 tools → stdin 关闭 exit 0
```
