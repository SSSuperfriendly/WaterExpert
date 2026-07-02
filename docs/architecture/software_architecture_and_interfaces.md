# 软件架构与接口设计建议

本文件给下一位助手一个明确的软件实现落点：不要重新发明模型层，而是把 `WaterExpert` 原型组织成可运行的软件系统。

## 1. 总体原则

- 研究原型与软件系统分层
- 先服务化，再前端化
- 先消费现有产物，再逐步做在线训练
- 所有“过度承诺”的科学表述都必须加 guardrails

## 2. 推荐架构

建议采用四层结构：

## 2.1 数据层

负责：

- 原始数据接入
- 数据清洗与标准化
- 任务输入缓存
- 产物索引

建议存储：

- 关系库：用户、站点、任务、模型版本、报告记录
- 文件存储：CSV、JSON、PNG、模型权重
- 可选时序库：连续监测序列

## 2.2 模型与分析层

直接复用 `WaterExpert/src/water_ai` 与 `WaterExpert/scripts`：

- 模型训练
- 模型推理
- 诊断导出
- 阈值分析
- 场景 triage
- response playbook
- Sobol / 反事实

## 2.3 服务层

建议拆成：

- Data Service
- Model Service
- Diagnosis Service
- Report Service
- Job Scheduler

## 2.4 应用层

建议做成 Web 前端，至少包含：

- 首页总览
- 数据管理
- 预测任务
- 结果对比
- 诊断与场景
- 边界识别
- 报告导出

## 3. 推荐软件目录

建议新软件仓库采用下面结构：

```text
WaterExpert Software/
├── README.md
├── AGENTS.md
├── docs/
├── backend/
│   ├── app/
│   ├── routers/
│   ├── schemas/
│   ├── services/
│   ├── tasks/
│   └── adapters/
├── frontend/
│   ├── src/
│   └── public/
├── src/
├── scripts/
├── configs/
├── data/
├── outputs/
├── data_contracts/
└── tests/
```

## 4. `WaterExpert` 到软件模块的映射

| `WaterExpert` 现有能力 | 软件模块 |
| --- | --- |
| `multimodal_builder.py` | 数据接入与特征构建服务 |
| `kg_priors.py` | 图谱先验构建服务 |
| `mscim.py` | 预测模型服务 |
| `cmfbe_stgcn.py` | 机理诊断模型服务 |
| `turbidity_diagnosis.py` | 诊断服务 |
| `agent_exports.py` | agent / 报告 / 检索导出服务 |
| `run_full_pipeline.py` | 训练与全流程任务调度 |
| `analyze_cmfbe_thresholds.py` | 阈值分析服务 |
| `analyze_cmfbe_sobol_counterfactual.py` | 敏感性与反事实服务 |
| `generate_real_raster_boundary_labels.py` | 边界标签预处理服务 |

## 5. 最小 API 设计

以下接口是最值得先做的第一批。

## 5.1 数据接口

### `POST /api/v1/data/import`

用途：

- 上传水质、气象、水文、水利或边界标签数据

建议请求字段：

```json
{
  "data_type": "water_quality",
  "source_name": "wusongkou_daily_csv",
  "file_path": "uploaded/or/staged/path",
  "time_granularity": "daily",
  "station_code": "2586"
}
```

### `GET /api/v1/stations`

用途：

- 返回站点基础信息

至少包括：

- station code
- station name
- river
- longitude
- latitude

## 5.2 预测任务接口

### `POST /api/v1/prediction-jobs`

用途：

- 创建训练或推理任务

建议请求字段：

```json
{
  "mode": "inference",
  "model_name": "cmfbe_stgcn",
  "station_code": "2586",
  "config_path": "configs/prototype_repo.yaml",
  "start_date": "2024-09-07",
  "end_date": "2024-12-31",
  "use_existing_artifacts": true
}
```

### `GET /api/v1/prediction-jobs/{job_id}`

用途：

- 返回任务状态、日志和产物位置

### `GET /api/v1/prediction-jobs/{job_id}/series`

用途：

- 返回预测时间序列

建议响应字段：

```json
{
  "model": "cmfbe_stgcn",
  "split": "test",
  "series": [
    {
      "target_date": "2024-09-20",
      "actual_turbidity": 123.4,
      "predicted_turbidity": 117.8,
      "actual_clearness": 0.34,
      "predicted_clearness": 0.37
    }
  ]
}
```

## 5.3 指标与诊断接口

### `GET /api/v1/metrics/latest`

直接读取或包装：

- `outputs/metrics/metrics.json`
- `outputs/metrics/model_comparison.csv`

### `GET /api/v1/diagnosis/latest`

直接读取或包装：

- `outputs/diagnosis/mscim_turbidity_factor_diagnosis_summary.json`
- `outputs/diagnosis/cmfbe_process_decomposition_summary.csv`

### `GET /api/v1/scenario-triage/latest`

直接读取或包装：

- `outputs/agent/scenario_triage.json`

### `GET /api/v1/response-playbook/latest`

直接读取或包装：

- `outputs/agent/response_playbook.json`

### `GET /api/v1/agent-context/latest`

直接读取或包装：

- `outputs/agent/agent_context.json`

## 5.4 边界识别接口

### `GET /api/v1/boundary/latest`

直接读取：

- `outputs/boundary/boundary_detection_summary.json`
- `outputs/boundary/boundary_predictions.csv`

建议响应包括：

- model metrics
- labeled sample count
- positive rate
- prediction series

## 5.5 阈值与反事实接口

### `GET /api/v1/thresholds/latest`

直接读取：

- `outputs/thresholds/cmfbe_threshold_summary.csv`
- `outputs/thresholds/cmfbe_threshold_report.md`

### `GET /api/v1/sensitivity/latest`

直接读取：

- `outputs/sensitivity/cmfbe_sobol_indices.csv`

### `GET /api/v1/counterfactual/latest`

直接读取：

- `outputs/counterfactual/cmfbe_counterfactual_summary.csv`
- `outputs/counterfactual/cmfbe_joint_counterfactual_summary.csv`

## 6. 页面设计最小集

建议第一版至少做六页：

1. 首页总览
2. 数据管理页
3. 预测任务页
4. 预测结果页
5. 场景与诊断页
6. 边界识别与阈值页

## 7. 首页应展示什么

首页可以直接从 `agent_context.json` 组织出：

- 当前最佳模型
- test 集 R² / RMSE
- self-purification risk snapshot
- scenario counts
- 高优先级日期
- 推荐问题入口

## 8. “结果页”与 “诊断页” 的拆分建议

### 8.1 结果页

面向“看预测对不对”：

- 实测-预测曲线
- MAE / RMSE / R²
- 模型对比
- 边界预测概览

### 8.2 诊断页

面向“为什么这样”：

- 主导致浊因子
- 机理分解
- scenario triage
- 阈值证据
- response playbook

## 9. 当前最值得复用的结构化产物

软件开发优先复用：

- `metrics.json`
- `agent_context.json`
- `scenario_triage.json`
- `response_playbook.json`
- `boundary_detection_summary.json`
- `cmfbe_threshold_summary.csv`
- `cmfbe_sobol_indices.csv`

它们已经足够支持第一版后台接口。

## 10. 应暂缓的内容

第一版不建议一开始就做：

- 完整在线训练平台
- 多用户复杂权限矩阵
- 多站点二维水动力联算
- 强化学习控制器
- 生产级时空地图编辑器

这些都不是当前最短交付路径。

## 11. 最小可运行实现建议

如果下一位助手需要快速交付一个可演示软件，建议先做：

1. 后端封装 `WaterExpert` 现有输出和脚本
2. 前端读取 JSON/CSV 结果展示
3. 提供“重新运行分析”的按钮
4. 支持导出图表与诊断报告

这样能最快把研究原型转成可展示的软件系统。
