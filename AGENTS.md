# AGENTS.md

## 先读什么

进入这个目录后，不要直接开工写代码。先按下面顺序阅读：

1. `README.md`
2. `docs/software_spec_from_softcopyright.md`
3. `docs/waterexpert_research_handoff.md`
4. `docs/software_architecture_and_interfaces.md`
5. `docs/next_assistant_execution_plan.md`

## 工作目标

这里的目标不是重复训练一个研究原型，而是基于同级目录 `G:\AI4S\WaterExpert`，开发“基于多模态数据融合的水体浊度预测系统”软件。

软件应优先承接以下已存在能力：

- 多源数据接入与清洗
- 浊度/清澈度预测
- 边界变化状态识别
- 致浊因子诊断
- 阈值与场景检索
- 报告导出

## 事实边界

- `WaterExpert` 当前是吴淞口单站点多模态日尺度原型。
- 当前阈值是经验阈值，不是二维水动力物理临界阈值。
- 当前边界标签是真实 raster 派生代理标签，不是人工精标治理边界。
- 当前场景 triage、response playbook、Sobol 与反事实是原型级 agent 支撑产物，不是经过治理验证的策略系统。

## 推荐执行方式

### 1. 先包接口，再做 UI

优先把 `WaterExpert` 脚本和 `outputs/` 产物封装为后端接口，不要一开始就重做算法。

### 2. 研究代码尽量复用

优先复用这些入口：

- `G:\AI4S\WaterExpert\scripts\run_full_pipeline.py`
- `G:\AI4S\WaterExpert\scripts\export_agent_context.py`
- `G:\AI4S\WaterExpert\scripts\export_scenario_triage.py`
- `G:\AI4S\WaterExpert\scripts\export_response_playbook.py`
- `G:\AI4S\WaterExpert\scripts\analyze_cmfbe_thresholds.py`
- `G:\AI4S\WaterExpert\scripts\analyze_cmfbe_sobol_counterfactual.py`

### 3. 明确产品分层

- 研究层：训练、推理、诊断、阈值分析脚本
- 服务层：API、任务调度、模型服务、数据服务
- 应用层：前端页面、报表、用户权限、日志

## gstack 技能路由

本机已安装 Codex 技能。建议按任务类型调用：

- `/office-hours`: 拆产品需求、定义 MVP、梳理角色与使用场景
- `/plan-eng-review`: 审查系统架构、接口设计、模块边界
- `/review`: 在提交前做代码审查
- `/cso`: 做安全与敏感信息检查
- `/qa`: 在前端页面或接口完成后做体验验证
- `/ship`: 需要提交、推送、建 PR 时再用

## 完成标准

一轮开发至少要满足：

- 有清晰的软件目录结构
- 有可运行的后端接口入口
- 能消费 `WaterExpert` 现有产物或直接调用其推理脚本
- 有最小可用的前端页面或接口文档
- 有 README、接口说明和运行说明
