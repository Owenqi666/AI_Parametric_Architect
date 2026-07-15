# AI Parametric Architect Studio 使用指南

本指南面向第一次运行项目的用户。默认流程完全离线，不需要 OpenAI API key、数据库
或手工生成 fixture。

## 1. 运行环境

需要：

- Python 3.12 或 3.13；
- `uv`；
- Node.js 22.13.0 或更高版本；
- npm；
- macOS、Linux 或 WSL2。原生 Windows 尚未验证。

先确认版本：

```bash
python3 --version
uv --version
node --version
npm --version
```

## 2. 克隆并启动

```bash
git clone https://github.com/Owenqi666/AI_Parametric_Architect.git
cd AI_Parametric_Architect
make showcase
```

也可以直接运行：

```bash
./scripts/run_showcase.sh
```

首次冷启动可能需要访问 Python 和 npm 软件包仓库。依赖已经安装或缓存后，Showcase
本身可以离线运行。

终端出现以下就绪信息后再打开浏览器：

- Uvicorn：`Application startup complete`；
- Studio：Vite 输出 `Local: http://127.0.0.1:3000/`。

默认地址：

| 服务 | 地址 |
| --- | --- |
| Studio | `http://127.0.0.1:3000` |
| FastAPI | `http://127.0.0.1:8000` |
| Health | `http://127.0.0.1:8000/health` |
| Capabilities | `http://127.0.0.1:8000/v1/capabilities` |

按 `Ctrl+C` 会同时停止前后端进程。

### 端口被占用

```bash
SHOWCASE_BACKEND_PORT=8010 SHOWCASE_FRONTEND_PORT=3010 make showcase
```

如需修改绑定地址，可同时设置 `SHOWCASE_BACKEND_HOST` 和 `SHOWCASE_FRONTEND_HOST`。
将服务绑定到非 loopback 地址不代表它已适合公网部署。

## 3. Design Studio

Design Studio 是默认首页，包含输入区、可观测 Pipeline、Proposal/World Model viewport、
结构化 Inspector 和执行证据。

### Family House

1. 选择 `South-facing family house`。
2. 保持 `Recorded showcase replay` 或选择 `Offline deterministic`。
3. 点击 **Run planning**。
4. 在 Parsed DesignIntent 中查看面积、朝向、房间和空间约束。
5. 选择 Kitchen 或 Living 房间，查看邻接关系及 solved placement。

Proposal viewport 必须始终显示：

- `Detached Proposal`；
- `Not committed to World Model`；
- `Advisory planning output`。

这些矩形不是已提交建筑几何。

### Compact Apartment

选择 `Compact apartment` 并运行。底部证据区展示 baseline 与 CP-SAT 的空间效率、
constraint satisfaction、circulation proxy 和稳定性。Circulation 只是中心距离 proxy，
不是建筑规范或人类偏好评分。

### Constraint Conflict

选择 `Conflicting spatial constraints` 并运行。预期结果为：

- DesignIntent 成功解析；
- Constraint Planning 失败；
- 稳定错误码 `PLANNING_SOLVER_FAILED`；
- 不创建 Proposal；
- 不静默回退，也不伪造结果。

### 编辑自然语言

Showcase 只承认三个已提交离线场景。编辑为未收录文本后会返回
`SHOWCASE_INPUT_NOT_RECORDED`。这是有意的失败关闭行为，并不表示浏览器正在运行
新的 LLM 或 solver。

## 4. Benchmark Lab

打开 `http://127.0.0.1:3000/benchmark`。

- **End-to-end**：Requirement → parser → planner；
- **Oracle intent**：直接使用外部 reference intent，只隔离 planner 行为。

页面展示 metric coverage、sample count、失败分母、runtime、逐案例结果、失败码分布
和 Proposal digest。N/A 不会被伪装成零分。

### 生成并导入报告

```bash
uv run ai-architect-benchmark \
  benchmarks/datasets/planning-core-1.0.0.json \
  benchmarks/annotations/planning-core-reference-1.0.0.json \
  planning-benchmark-report.json \
  --trials 2
```

生成后在 Benchmark Lab 点击 **Import report**，选择
`planning-benchmark-report.json`。浏览器会通过严格的 `BenchmarkReport 1.0.0` 合同验证；
版本、字段、引用、预算或数值不合法时会拒绝显示。

Benchmark 指标只是评估证据，不是 World Model commit authority。

## 5. World Model Explorer

打开 `http://127.0.0.1:3000/world-model`。

- 使用左侧搜索框查找 entity ID 或名称；
- 选择房间、墙、门或窗，右侧 Inspector 会显示 validated properties；
- 使用 **All floors / Ground Floor / Upper Floor** 切换可见楼层；
- 使用 **Isometric、Top、Fit** 控制相机；
- 使用 **Preview SVG floor plan** 查看确定性平面投影；
- 可下载 SVG 和 Render IR 调试衍生物。

该页面是只读 Explorer，没有 Patch、编辑或 commit 控件。Three.js scene 是 Render IR 的
可丢弃衍生视图，不是另一个 World Model。

## 6. Architecture & Safety

打开 `http://127.0.0.1:3000/architecture`，可查看完整信任链：

```text
Natural Language
  → Typed DesignIntent
  → Constraint Solver
  → Detached Proposal
  → PatchProposal
  → Authorization
  → Validation
  → CAS Revision
  → World Model
  → Render IR
  → Three.js
```

只有持久化 JSON Revision 是权威 World Model。Evaluation、Proposal、Benchmark、Render IR
和浏览器状态都没有提交权限。

## 7. 可选 OpenAI 模式

默认 Studio 没有 OpenAI live 控件，也不会根据 API key 自动启用网络调用。现有真实适配器
只能执行 requirement → `DesignIntent`，需要在受控 Python composition 或显式 benchmark
命令中 opt-in。

`.env.example` 只是变量名称参考；`run_showcase.sh` 不会自动 source 该文件。需要时应通过
受控 secret channel 或当前 shell 显式 export 变量，不要提交真实凭据。

详细配置和边界见 [SHOWCASE.md](SHOWCASE.md) 与
[Security.md](../Security.md)。

## 8. 常见问题

### 3D 画布为空

确认浏览器支持 WebGL，并检查：

```bash
curl -I http://127.0.0.1:3000/examples/showcase-house.render-ir.json
```

不要跳过 Render IR admission parser。

### Fixture 或 BenchmarkReport 被拒绝

恢复受信任 checkout 中的生成文件，或使用仓库生成脚本重新生成，然后运行相关测试。
不要通过删除字段校验或放宽版本合同来绕过准入。

### OpenAI 选项没有出现

这是当前 Showcase 的正常行为。Capabilities endpoint 是诊断元数据，不是 UI 开关或
授权令牌。

## 9. 开发者验证

后端：

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --cov=ai_parametric_architect --cov-report=term-missing
uv run coverage json -o coverage.json
uv run python scripts/verify_branch_coverage.py
```

前端：

```bash
cd frontend
npm ci
npm run typecheck
npm run lint
npm test
npm run build
```

## 10. 已知边界

- 不声称建筑规范合规或自动建筑正确性；
- 不把 AI、solver 或 benchmark 输出作为权威几何；
- 默认 repository/audit 为进程内实现；
- WebGL 可用性取决于浏览器和硬件；
- 公网部署仍需要独立的认证、租户隔离、速率限制、持久化和运维安全设计。
