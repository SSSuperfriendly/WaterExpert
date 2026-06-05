# AGENTS.md

## 先读什么

进入本目录后，先按顺序阅读：

1. `README.md`
2. `docs/specs/software_spec_from_softcopyright.md`
3. `docs/handoffs/research_handoff.md`
4. `docs/architecture/software_architecture_and_interfaces.md`
5. `docs/reviews/2026-06-05-engineering-review.md`

## 工作目标

这里的目标不是重做研究原型，而是直接复用本仓库内已经跑通的算法代码、建模逻辑和既有产物，持续开发 `WaterExpert Software`。

优先承接的能力：

- 多源数据接入与清洗
- 浊度与清澈度预测
- 边界变化代理识别
- 致浑因子诊断
- 阈值与场景检索
- 报告导出

## 事实边界

- 当前系统仍是吴淞口单站点、多模态、日尺度原型。
- 当前阈值是经验阈值，不是二维水动力物理临界阈值。
- 当前边界标签是 raster 派生代理标签，不是人工精标治理边界。
- 当前 scenario triage、response playbook、Sobol 与 counterfactual 都是原型级诊断/推理支撑产物，不是经过治理验证的控制策略。

## 推荐执行方式

### 1. 先封装能力，再扩 UI

优先把研究原型封装成稳定的软件接口与可读前端，不要先重写算法本体。

### 2. 优先复用这些入口

- `scripts/pipeline/run_full_pipeline.py`
- `scripts/exports/export_agent_context.py`
- `scripts/exports/export_scenario_triage.py`
- `scripts/exports/export_response_playbook.py`
- `scripts/analysis/analyze_cmfbe_thresholds.py`
- `scripts/analysis/analyze_cmfbe_sobol_counterfactual.py`

### 3. 明确分层

- `src/water_ai/`: 研究与算法核心
- `backend/app/`: 软件服务层
- `frontend/`: 可视化界面
- `scripts/`: 运行、分析、导出、边界与预处理脚本入口
- `docs/`: 架构、规格、handoff、评审与内部说明
- `var/`: 软件运行态状态与报告

## 完成标准

一轮开发至少满足：

- 目录结构清晰，源码、脚本、文档、运行态分层明确
- 后端接口可运行
- 可以消费既有 `outputs/` 产物或直接调用研究脚本
- 有最小可用前端或可读接口文档
- `README`、架构文档和运行说明保持同步
