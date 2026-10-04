# Documentation

Market Sentinel 的文档按用途分为三类。新读者建议从根目录 [README](../README.md)（英文产品概览）开始；操作细节见 [usage.zh.md](usage.zh.md)（中文使用手册）。

## architecture/ — 当前架构契约与规格

修改对应模块前必读；这些是冻结的契约文档，改动需要同步评审。

| 文件 | 内容 |
|---|---|
| [charter.md](architecture/charter.md) | 项目任务书：目标、核心管线、数据协议基线、性能目标（v0.1 时期制定，仍是架构基准） |
| [provider-source-audit.md](architecture/provider-source-audit.md) | 行情数据源审计：Tencent / Sina / Longbridge / Tushare 对比、`MarketSnapshot` 冻结契约、数据源选型证据规则 |
| [intelligence-contract.md](architecture/intelligence-contract.md) | Intelligence 契约：输入/输出类型、model payload 白名单、episode budget、fallback 语义、交易建议 fail-closed 解析 |
| [metrics-contract.md](architecture/metrics-contract.md) | Metrics 契约：TelemetryEvent / UserFeedback / TuningSnapshot 类型、Host 与 Core 的所有权边界、存储规则（`measurement != mutation`） |
| [multihost-spec.md](architecture/multihost-spec.md) | v1.0 多宿主规格（尚未实现）：HostAdapter 契约、wire protocol 与 host adapter 的关系、跨宿主 parity 测试 |

## integrations/ — 接入指南

| 文件 | 内容 |
|---|---|
| [longbridge.md](integrations/longbridge.md) | Longbridge live 行情接入：安装策略、环境变量、SDK 生命周期、错误码分类、字段映射 |
| [mcp.md](integrations/mcp.md) | MCP stdio server：standalone runtime、6 个只读 tools、错误码、客户端配置、宿主验证状态矩阵 |
| [zcode.md](integrations/zcode.md) | ZCode 宿主接入与验证记录（0.16.9）：配置、工具发现与调用、错误传播、troubleshooting |
| [deepseek-harness.md](integrations/deepseek-harness.md) | DeepSeek Harness 宿主接入与验证记录（0.2.0-rc.2）：Cordis entry 配置、discovery/调用/重连/生命周期验证 |

## history/ — 历史记录（不再更新）

已完成的 roadmap、Release Candidate 记录与开发日志。保留它们是为了理解决策脉络；其中的版本边界、待办状态**不反映当前现实**，当前状态以 `README.md` 和 `CHANGELOG.md` 为准。

| 文件 | 时期 | 内容 |
|---|---|---|
| 02_Roadmap_v0.1_Core.md | v0.1 | Provider / Ring Buffer / Scheduler / CLI 路线 |
| 03_Roadmap_v0.2_Event_Engine.md | v0.2 | 事件引擎路线 + dedupe/cluster/cooldown 冻结语义 |
| 04_Roadmap_v0.3_Cursor_MVP.md | v0.3 | Cursor 扩展 MVP 路线 + VSIX 身份 |
| 05_Roadmap_v0.4_to_v1.0_Overview.md | v0.4+ | 跨版本总览：基线、八条冻结原则、版本阶梯 |
| 06_Roadmap_v0.4_Live_Market_Data.md | v0.4 | live 数据语义：volume/timestamp 契约、session 重置、secrets 政策 |
| 07_Roadmap_v0.5_Market_Intelligence.md | v0.5 | Intelligence 路线：router 输入、budget、隐私范围 |
| 08_Roadmap_v0.6_Feedback_and_Tuning.md | v0.6 | telemetry / feedback / offline tuning 路线与边界 |
| 11_v0.4_M1a_Live_Semantics_Bakeoff.md | v0.4 | Longbridge / Tencent 探针对比实测记录 |
| 13_v0.4_Release_Candidate.md | v0.4 | v0.4 RC 停止报告（v0.4 未单独发版） |
| 15_v0.5_Release_Candidate.md | v0.5 | v0.5 RC 修复与验证记录 |
| 17_v0.6_Release_Candidate.md | v0.6.0 | v0.6 RC 记录（v0.6.0 未打 tag） |
| 18_v0.6.5_UX_Polish.md | v0.6.5 | v0.6.5 Host / CLI UX 实现记录 |
| 19_v0.6.5_Release_Candidate.md | v0.6.5 | v0.6.5 发布记录：测试、VSIX、privacy / mutation audit、已知边界 |
| CURSOR_开发总指令.md | v0.1 前 | 最早的 agent bootstrap 指令（已被根目录 AGENTS.md 取代） |

## 根目录下的过程文档

| 文件 | 内容 |
|---|---|
| [PRODUCTIZATION_AUDIT.md](PRODUCTIZATION_AUDIT.md) | M0 产品化审计：现状盘点、集成方案调研（ZCode / DeepSeek Harness / MCP）、风险与里程碑计划 |
| [usage.zh.md](usage.zh.md) | 中文使用手册：安装、Provider、Cursor 使用、CLI 参考、配置总表、数据语义、隐私边界、测试流程、工程 backlog |
| [REPOSITORY_CLEANUP.md](REPOSITORY_CLEANUP.md) | M1 清理记录：每个 MOVE / KEEP / ADD / IGNORE 决策及理由、引用修复清单、验证结果 |
| [RELEASE_READINESS.md](RELEASE_READINESS.md) | M6 发布就绪报告：打包/安装/依赖边界/卫生/许可 状态矩阵与 Blockers/Unknowns/Deferred |
