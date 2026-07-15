# AI Parametric Architect 工业级架构审查报告

> **Historical review snapshot.** 本文记录 2026-07-15 安全硬化之前的审查结论，
> 不是当前 release status。其 P1 项已在后续阶段按 `Security.md` 与回归测试收口；
> 当前架构、作品集展示边界与已知限制请以 `README.md`、`architecture.md`、
> `Security.md` 和 `docs/` 为准。保留本文用于展示审查到修复的可追溯性。

审查日期：2026-07-15  
审查角色：Principal AI Systems Engineer、AI Agent Infrastructure Reviewer、Software Architect、Security Reviewer、Open Source Maintainer

## 1. 审查目标与范围

本次审查判断当前项目是否达到：

> Production-oriented AI Agent Framework Prototype

审查范围包括：

- JSON-first World Model、Schema、语义与几何校验
- SVG Renderer 与 FastAPI
- JSON Patch、Revision、CAS、Undo/Redo、Audit
- Requirement、Planner、Constraint Reasoning、Patch Generator Agents
- Typed LLM Provider、Mock Provider、Prompt boundary
- Evaluation Framework 与 Detached Patch Validation
- Agent Trace
- 测试、覆盖率、CI、wheel、发布与开源治理

本次只进行代码审查、配置核查和对抗性运行验证，没有实现新功能。

## 2. 最终结论

当前项目暂不满足完整的 Production-oriented AI Agent Framework Prototype 标准。

更准确的定位是：

> 高质量、Mock 驱动、具备 production-oriented 架构基础的 AI-ready / evaluatable framework prototype。

确定性内核、模块边界和测试纪律明显超过普通 MVP，但仍存在会破坏 JSON 权威性、Revision 完整性、Agent 授权和审计可信度的 P1 问题。

当前系统不是 production-ready service。

## 3. 成熟度判定

| 维度 | 判定 |
| --- | --- |
| 模块化与 ports/adapters | 通过 |
| 单进程 Patch/Revision/CAS | 通过 |
| 测试与构建质量 | 强 |
| JSON 权威性 | 阻断 |
| Renderer/API 数值安全 | 阻断 |
| Agent 意图授权 | 阻断 |
| 审计身份可信度 | 阻断 |
| LLM 数据治理 | Mock 阶段可接受，真实接入阻断 |
| Evaluation 发布资格 | 不足 |
| 持久化与运维 | 不具备 |
| 开源治理 | 不具备 |

## 4. P0 问题

未发现远程代码执行、确定性大规模数据破坏等 P0 问题。

## 5. P1 问题

### P1-1 Validation 与 Revision 对有效 JSON 的结论不一致

相关位置：

- [validation/service.py:74](src/ai_parametric_architect/validation/service.py#L74)
- [backend/api.py:57](src/ai_parametric_architect/backend/api.py#L57)
- [model-1.0.0.schema.json:79](src/ai_parametric_architect/contracts/schemas/model-1.0.0.schema.json#L79)
- [application/editing.py:55](src/ai_parametric_architect/application/editing.py#L55)

ModelValidator 没有在共享验证入口统一执行严格 JSON-tree guard。FastAPI 将解析后的字典直接传入验证器，metadata 内部值又不受 Schema 递归约束。

已复现：

- metadata 包含 NaN 时，POST /v1/models/validate 返回 200 和 valid: true。
- Python 调用可以让 datetime、set、tuple 等非 JSON 值通过 validation。
- 同一模型进入 EditingService.initialize 时会被 ensure_json_value 拒绝。

影响：

- validation 通过不等价于可以成为权威 JSON Revision。
- 破坏 JSON 是唯一世界状态来源的核心合同。
- Validate API、Render API 和 Revision 写入边界采用不同的有效性定义。

建议门槛：

- 在共享 Validator 入口对防御性快照执行严格 JSON-tree guard。
- FastAPI 严格拒绝 NaN、Infinity 和非标准 JSON。
- 添加 API、application 和 library 三层一致性测试。

### P1-2 有限输入的派生计算可溢出

相关位置：

- [model-1.0.0.schema.json:315](src/ai_parametric_architect/contracts/schemas/model-1.0.0.schema.json#L315)
- [validation/rules.py:397](src/ai_parametric_architect/validation/rules.py#L397)
- [validation/rules.py:578](src/ai_parametric_architect/validation/rules.py#L578)
- [renderer/svg.py:312](src/ai_parametric_architect/renderer/svg.py#L312)
- [domain/precision.py:59](src/ai_parametric_architect/domain/precision.py#L59)
- [backend/api.py:68](src/ai_parametric_architect/backend/api.py#L68)

Schema 主要验证单个数值有限或大于零，没有合理的建筑域上界，也没有全面检查派生计算结果是否仍然有限。

已复现：

- wall.thickness = 1.7e308 可以通过完整 validation。
- SVG 输出包含 stroke-width="inf"。
- 极大 opening 参数使 ValidationIssue.details 包含 inf。
- Validate API 将 inf 静默序列化为 null。
- Render API 的错误响应路径返回 500 Internal Server Error。

影响：

- 有效 Revision 不保证可以安全渲染。
- SVG 数值合同被破坏。
- FastAPI 错误结果不再稳定或机器可读。

建议门槛：

- 为坐标、尺寸、面积和数量定义可配置的建筑域预算。
- 每个派生几何计算完成后验证结果有限。
- ValidationIssue.details 强制标准 JSON。
- Renderer 在序列化前拒绝所有非有限派生值。

### P1-3 Revision 初始化存在 TOCTOU

相关位置：

- [application/editing.py:55](src/ai_parametric_architect/application/editing.py#L55)
- [domain/revisions.py:49](src/ai_parametric_architect/domain/revisions.py#L49)

EditingService.initialize 先验证调用者提供的可变字典，随后才由 ModelRevision 复制。如果另一个线程在验证完成后、复制前修改模型，保存的快照可能不是已经验证的快照。

已通过线程屏障复现：

- 线程 A 完成 validation。
- 线程 B 在 Revision 复制前删除 floors。
- initialize 成功。
- 保存后的 Revision 再验证时出现 BUILDING_HAS_NO_FLOORS、ROOM_FLOOR_NOT_FOUND 和 WALL_FLOOR_NOT_FOUND。

影响：

- 破坏所有权威 Revision 都经过完整验证的核心保证。

建议门槛：

- 进入 initialize 后立即取得一个严格 JSON 防御性快照。
- validation、identity extraction 和 ModelRevision 构造必须使用同一个快照。

### P1-4 几何有效被误当成符合意图且已授权

相关位置：

- [agents/patch_agent.py:73](src/ai_parametric_architect/agents/patch_agent.py#L73)
- [evaluation/runner.py:155](src/ai_parametric_architect/evaluation/runner.py#L155)
- [evaluation/runner.py:284](src/ai_parametric_architect/evaluation/runner.py#L284)
- [test_evaluatable_ai_agent_system.py:132](tests/integration/test_evaluatable_ai_agent_system.py#L132)
- [application/planning.py:124](src/ai_parametric_architect/application/planning.py#L124)

DetachedPatchValidator 检查：

- model/revision binding
- protected paths
- Schema、semantic、Shapely validation
- affected entity IDs

但它不检查 Patch 是否真正实现输入 FloorPlanProposal，也不代表用户已经授权该语义修改。

已复现：

- 输入需求是 Create a 60 sqm one bedroom house。
- LLM Patch 实际将房间 usage 修改为 restricted_lab，并加入攻击者 extension。
- intent extraction accuracy、plan validity、patch validation success rate 全部为 100%。
- Patch 随后通过通用 EditingService 成功提交。

影响：

- Prompt injection 可以形成结构合法、几何合法、但与用户意图无关的修改。
- Evaluation success 被误用为 commit authorization。

现有正确控制：

- ArchitecturePlanningService 会独立重建并精确比较允许的 Patch 操作。

建议门槛：

- 所有 AI Proposal 必须强制通过 ArchitecturePlanningService 或等价的 Policy/Authorization Gateway。
- Evaluation 结果只能作为质量证据，不能作为提交授权。
- Generic EditingService 不应直接接收未经授权策略核对的 Agent Proposal。

### P1-5 LLM 可以伪造审计主体

相关位置：

- [llm/provider.py:121](src/ai_parametric_architect/llm/provider.py#L121)
- [application/planning.py:211](src/ai_parametric_architect/application/planning.py#L211)
- [application/editing.py:131](src/ai_parametric_architect/application/editing.py#L131)
- [domain/audit.py:69](src/ai_parametric_architect/domain/audit.py#L69)

PatchProposal 中的 provenance 和 rationale 只要求非空，随后会原样写入 Audit Log。

已复现 LLM 输出：

- provenance = human:chief-architect
- rationale = Approved by chief architect.

该 Proposal 通过 ArchitecturePlanningService，并以该人类身份出现在 audit 中。

影响：

- 审计归属不可信。
- 无法区分认证人类行为、Agent 建议和系统自动动作。
- Audit Log 不具备不可抵赖性。

建议门槛：

- Audit actor/provenance 由认证后的可信应用层生成。
- LLM 只能提供明确标记为 untrusted 的 rationale。
- Audit 绑定 authenticated subject、provider、model、prompt version、run ID 和 trace ID。

### P1-6 API 没有资源预算

相关位置：

- [model-1.0.0.schema.json:140](src/ai_parametric_architect/contracts/schemas/model-1.0.0.schema.json#L140)
- [model-1.0.0.schema.json:507](src/ai_parametric_architect/contracts/schemas/model-1.0.0.schema.json#L507)
- [validation/rules.py:503](src/ai_parametric_architect/validation/rules.py#L503)
- [validation/rules.py:613](src/ai_parametric_architect/validation/rules.py#L613)
- [backend/api.py:57](src/ai_parametric_architect/backend/api.py#L57)

问题包括：

- Polygon ring 没有 maxItems。
- Entity registry 没有 maxProperties。
- Room overlap 和 opening overlap 使用成对组合，最坏复杂度为 O(n²)。
- API 没有 body、vertex、entity、并发、速率或计算超时限制。

影响：

- 匿名超大请求可能耗尽线程、Shapely CPU 和内存。

建议门槛：

- Gateway 与应用双层 body size 限制。
- Model complexity policy：entity、room、opening、vertex、hole 和 Patch operation 上限。
- 请求超时、并发配额、速率限制。
- 最大规模 fixture、benchmark、fuzz、load 和 soak tests。

### P1-7 真实 Provider 接入前的数据与 Trace 安全不成立

相关位置：

- [llm/prompts.py:68](src/ai_parametric_architect/llm/prompts.py#L68)
- [agent_trace/hashing.py:11](src/ai_parametric_architect/agent_trace/hashing.py#L11)
- [agent_trace/recorder.py:25](src/ai_parametric_architect/agent_trace/recorder.py#L25)

Patch prompt 会无差别发送完整 revision.document，没有字段 allowlist、脱敏、数据分类、大小限制或存储型 prompt injection 防护。

Agent Trace 使用无密钥、确定性的 SHA-256。低熵需求可以通过候选字典恢复，相同输入也可以跨用户或租户关联。

影响：

- 接入外部 Provider 后可能发生敏感数据外发、供应商留存和 token/cost DoS。
- 当前 Trace 只能视为 content fingerprint，不能视为匿名化或安全审计证据。

建议门槛：

- 最小化发送给 Provider 的世界模型投影。
- 字段 allowlist、数据分类、脱敏和 tenant policy。
- Prompt injection threat model。
- Trace 使用带 key ID、租户隔离和输入/输出域分离的 HMAC；或者明确声明其不提供隐私保护。

## 6. P2 问题

### P2-1 只有进程内 Revision Repository

默认组合使用 [InMemoryRevisionRepository](src/ai_parametric_architect/repositories/in_memory.py#L33)。

其单进程 CAS、Undo/Redo 和 Audit 原子性实现正确，但存在：

- 进程重启丢失全部 Revision 和 Audit。
- 多 worker 状态分叉。
- 历史无限增长。
- Audit 无分页、归档和 retention。

这是已文档化的成熟度缺口，不是当前单进程实现错误。

### P2-2 Evaluation 只有机制测试

当前 Evaluation 能证明 runner、typed boundary 和 detached validation 正常工作，但不能作为真实 AI 发布门禁。

缺少：

- 独立、版本化、人工标注的场景语料。
- 对抗 prompt、模糊需求和多语言场景。
- 数据集 hash、provider/model、sampling config、prompt version 和 run ID。
- 分层指标、失败分类、置信区间和最低发布阈值。
- 基线对比和漂移监控。

### P2-3 PROMPT_VERSION 没有进入执行证据

相关位置：

- [llm/prompts.py:14](src/ai_parametric_architect/llm/prompts.py#L14)
- [llm/base.py:31](src/ai_parametric_architect/llm/base.py#L31)
- [evaluation/runner.py:133](src/ai_parametric_architect/evaluation/runner.py#L133)
- [agent_trace/models.py:82](src/ai_parametric_architect/agent_trace/models.py#L82)

修改 Prompt 后，同一个 Agent version 的 EvaluationReport 和 AgentTrace 无法区分执行配置。

### P2-4 OpenAPI 与真实 HTTP 契约不一致

[backend/api.py](src/ai_parametric_architect/backend/api.py#L57) 使用宽泛 dict 和 Response，没有显式 response models。

生成的 OpenAPI：

- 将 Render SVG 的 200 描述为 application/json。
- 将自定义 ValidationReport 422 描述为默认 HTTPValidationError。

这会破坏生成客户端、API gateway validation 和契约兼容性。

### P2-5 Agent/LLM Protocol 不是权限沙箱

Architecture tests 可以约束仓库内代码的静态 import，但 Python structural Protocol 不能阻止第三方 Provider 自己持有 repository、network client 或 commit 能力。

真实 Provider 必须视为可信适配器，并通过受控 composition、网络策略和必要的进程隔离限制能力。

### P2-6 Legacy raw Mapping LLM 接口仍公开

相关位置：

- [ports/planning.py:25](src/ai_parametric_architect/ports/planning.py#L25)
- [ports/__init__.py:8](src/ai_parametric_architect/ports/__init__.py#L8)
- [planning/adapter_parser.py:15](src/ai_parametric_architect/planning/adapter_parser.py#L15)

该路径最终会转换为 DesignIntent，因此不是直接验证绕过，但形成第二条缺少统一 Prompt、version 和 trace 策略的公共 LLM 接入路径。

### P2-7 ValidationIssue 只有浅层不可变性

[domain/issues.py:23](src/ai_parametric_architect/domain/issues.py#L23) 的 details 可以包含可变或非 JSON 的嵌套值。

未来 L3/L4 插件可能导致：

- ValidationReport 在创建后变化。
- 非标准 JSON 进入 API 错误响应。
- Issue 排序和序列化结果不稳定。

### P2-8 缺少生产可观测性

当前没有：

- request/run/correlation ID
- 结构化日志
- metrics
- OpenTelemetry
- Trace sink
- readiness
- SLO 与告警
- 脱敏和 retention policy

AgentTraceRecorder 只返回内存对象，没有形成端到端诊断闭环。

### P2-9 CI 缺少安全供应链门禁

现有 [.github/workflows/ci.yml](.github/workflows/ci.yml#L17) 没有：

- 依赖漏洞审计
- SBOM
- License policy
- Secret scanning
- Artifact signing
- Build provenance/attestation

actions/checkout 和 setup-uv 使用可移动的 major tag，没有 pin 到完整 commit SHA。

## 7. P3 与维护性问题

- pyproject.toml 与 package __init__.py 分别维护版本号，存在漂移风险。
- CI 没有 timeout-minutes、PR concurrency cancellation 和制品留存策略。
- Wheel 隔离测试只验证 Schema loader，没有验证 CLI、FastAPI 和 composition smoke。
- CI 只测试 lock 中的当前解析，没有最低依赖版本和 fresh-resolution compatibility job。
- 默认最大 linear_tolerance 会把部分正的 presentation stroke 格式化为零。
- Affected entity 推导硬编码 planning extension，未来扩展的 entity binding 不可组合。
- README 的唯一服务器启动示例使用 --reload，缺少生产部署配置和 runbook。

## 8. 已验证的强项

### Deterministic Core

- JSON Patch 在深拷贝上原子执行。
- RFC 6901 Pointer 解析严格。
- Patch 与 Revision 绑定 model_id 和 base revision。
- 完整 validation 后才进入 repository CAS。
- Affected entity IDs 从 before/after JSON 独立推导并精确核对。
- 正常数值范围内 SVG 具备稳定排序、固定格式、稳定 viewBox、无 timestamp 和 entity ID binding。

### Revision 与 Audit

- Revision 快照和 Audit 返回防御性副本。
- RLock 覆盖单进程事务。
- Snapshot、head、undo/redo stack 和 audit 在同一个锁内更新。
- Patch 和 restoration 均执行二次 CAS。
- Undo/Redo 使用单调递增的补偿 Revision。
- Restoration 会复核 stack top、preview snapshot 和 candidate snapshot。
- 已拒绝操作不会留下半提交状态。

### Agent Architecture

- In-tree Agent、Planning、Reasoning 和 LLM 层没有 repository/commit dependency。
- Typed LLM output union 封闭为 DesignIntent、FloorPlanProposal 和 PatchProposal。
- Patch Agent 多层复核 model/revision binding 和 affected IDs。
- ArchitecturePlanningService 会独立重建允许的语义操作。
- Constraint Reasoner 当前只产生不可执行的符号 Plan。
- Detached Evaluation 不接触 repository。
- Trace 不保存正文、tool arguments/results 或 chain-of-thought。

### 模块边界

- Domain 不依赖 FastAPI、Shapely 或 SVG。
- Shapely 对象没有越过 geometry_engine。
- Validation、Renderer、Editing 和 Agent dependency direction 有 architecture tests。
- 未使用 broad exception 隐藏未知实现错误。

### 文档诚实性

README 明确说明：

- 当前只有 Mock Provider。
- 没有真实网络 LLM。
- 没有 Patch HTTP endpoint。
- InMemoryRevisionRepository 只适合单进程测试和开发。
- 当前不包含 Multi-Agent、自动修复、Three.js、DXF、IFC 或规范 RAG。

## 9. 实际运行结果

本次审查实际执行：

| 命令 | 结果 |
| --- | --- |
| uv sync --dev --locked | 通过 |
| uv run ruff check . | 通过 |
| uv run ruff format --check . | 165 files already formatted |
| uv run mypy | 165 source files，0 issues |
| Python 3.13 pytest | 884 passed |
| Python 3.12 isolated pytest | 884 passed |
| Branch coverage gate | 1115/1166，95.63% |
| Coverage.py 综合覆盖率 | 97.70% |
| Wheel build | 通过 |
| Wheel Schema verification | 两份 Schema 均存在 |
| Isolated wheel installation | 两份 Schema 均可加载 |

Statement coverage 为 98.32%，branch coverage 为 95.63%。

### 对抗性验证

本次额外复现：

1. metadata 中 NaN 被 Validate API 判为有效。
2. 非 JSON Python 值可以通过公共 ModelValidator。
3. 极大 wall thickness 生成 stroke-width="inf"。
4. 极大 opening 使 Render error path 返回 HTTP 500。
5. 并发修改 initialize 输入可保存未验证的 Revision。
6. 与输入 Plan 无关的 Patch 获得三项 100% Evaluation 指标并成功提交。
7. LLM 自报的人类 provenance 原样进入 Audit Log。
8. 无密钥 Trace hash 可对低熵需求进行候选字典恢复。

## 10. CI 与仓库治理状态

当前 main 分支没有任何 commit，所有项目文件均为 untracked。

因此：

- 现有 CI 配置只能视为已经设计好的门禁。
- 当前没有可审计的 GitHub Actions 执行证据。
- 本报告中的通过结果均为本机实际复现。

另外：

- [pyproject.toml](pyproject.toml#L11) 标记为 Proprietary。
- 当前没有 LICENSE、SECURITY、CONTRIBUTING、CODE_OF_CONDUCT、CHANGELOG、CODEOWNERS 或 issue/PR templates。
- 当前项目不能称为 open-source-ready。

## 11. 建议准入门槛

### 达到 Production-oriented AI Agent Framework Prototype 前

必须关闭：

1. 统一严格 JSON 验证边界。
2. 修复派生数值溢出和错误响应 500。
3. 修复 initialize 的可变输入 TOCTOU。
4. 强制所有 AI Patch 经过意图和授权策略核对。
5. 将可信 audit actor 与 LLM 自报 provenance 分离。
6. 增加模型复杂度和 API 资源预算。
7. 最小化 Provider 输入并建立数据分类与脱敏策略。
8. 修正 Trace 的隐私定位或改为 keyed HMAC。
9. 为以上问题加入对抗性、并发和 API 回归测试。

### 达到 Production-ready 前

还必须完成：

1. Durable multi-process CAS repository。
2. Migration、backup/restore、retention、archive 和 audit pagination。
3. Authentication、tenant isolation、authorization 和 approval policy。
4. 正确且版本化的 OpenAPI/response contracts。
5. Structured logging、metrics、distributed tracing、readiness、SLO 和 alerts。
6. 真实 Provider 的 schema codec、timeout、retry、cancellation、rate/token/cost budget。
7. 独立版本化 Evaluation corpus、发布阈值、基线和 drift monitoring。
8. Dependency audit、SBOM、artifact signing 和 build provenance。
9. Wheel/CLI/FastAPI/真实 Uvicorn smoke、fuzz、load 和 soak tests。
10. Production deployment configuration、runbook 和 incident response。

## 12. 总结

项目最有价值的部分是：

- JSON-first 权威模型
- 确定性 validation/rendering
- Copy → Validate → CAS Commit 事务链
- 强 ArchitecturePlanningService 操作合同
- 清晰的 ports/adapters 依赖方向
- 高测试覆盖率和架构测试

当前最主要的问题不是代码数量不足，而是部分边界把：

- validation 当成授权
- caller/LLM 声明当成可信身份
- content hash 当成隐私保护
- Mock wiring success 当成真实 AI 质量证据

关闭本报告列出的 P1 问题后，项目可以升级为名副其实的 Production-oriented AI Agent Framework Prototype。完成持久化、认证授权、可观测性、Evaluation 发布门禁和供应链治理后，才应进入 production-ready 评估。
