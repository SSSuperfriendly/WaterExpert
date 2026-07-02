# WaterExpert 研究原型交接说明

本文件把当前仓库根目录下的 `WaterExpert` 研究原型，翻译成软件开发可以直接复用的能力清单。

## 1. 原型目标

`WaterExpert` 当前不是单纯做“已有浊度值的外推”，而是围绕以下目标构建：

- 预测水体浊度和清澈度代理
- 诊断主导致浊因子
- 评估自净失效和浊度突增风险
- 提取经验阈值
- 形成场景 triage 与 agent 检索产物
- 补齐边界变化监督链路

## 2. 当前已实现的代码结构

### 2.1 核心源码

`src/water_ai/` 已经包含：

- `data/`
  - `dataset.py`
  - `kg_priors.py`
  - `hydrodynamics.py`
  - `multimodal_builder.py`
  - `ndti.py`
- `models/`
  - `mscim.py`
  - `cmfbe_stgcn.py`
- `physics/`
  - `equations.py`
  - `cmfbe_surrogate.py`
- `interpretability/`
  - `turbidity_diagnosis.py`
  - `agent_exports.py`
- `utils/`
  - `io.py`
  - `metrics.py`

### 2.2 核心脚本入口

当前主要脚本包括：

- `scripts/pipeline/run_full_pipeline.py`
- `scripts/preprocess/preprocess_shanghai_hydrodynamics.py`
- `scripts/analysis/plot_cmfbe_process_decomposition.py`
- `scripts/exports/export_mscim_driver_overview.py`
- `scripts/analysis/analyze_cmfbe_thresholds.py`
- `scripts/exports/export_threshold_knowledge_graph.py`
- `scripts/exports/export_scenario_triage.py`
- `scripts/exports/export_response_playbook.py`
- `scripts/exports/export_agent_context.py`
- `scripts/boundary/create_boundary_label_template.py`
- `scripts/boundary/generate_real_raster_boundary_labels.py`
- `scripts/analysis/analyze_cmfbe_sobol_counterfactual.py`

## 3. 当前数据与运行范围

### 3.1 运行范围

- 主站点：吴淞口，站点号 2586
- 匹配气象站：宝山
- 水动力参考：松浦大桥、黄渡
- 当前训练就绪重叠样本：891 行
- 当前测试窗口：2024-09-07 至 2024-12-31，92 天

### 3.2 数据输入

当前原型已接入：

- 水质监测数据
- 上海日尺度气象数据
- 上海水动力数据
- 轻量关系表/知识图谱先验
- raster 派生边界代理标签

### 3.3 配置入口

主配置文件为：

- `configs/prototype_repo.yaml`

其中已经定义：

- 数据根目录
- 原始文件路径
- 水动力预处理路径
- 边界标签路径
- 因果发现参数
- 历史窗口与预测步长
- batch size、epoch、learning rate
- 多任务损失权重
- 模型超参数

## 4. 当前模型能力

## 4.1 MSCIM

当前 `MSCIM` 是主预测与诊断模型，包含：

- 特征图先验混合
- 时间位置编码
- Transformer 时序编码
- 注意力汇聚
- 浊度与清澈度联合预测
- 风险输出
- 边界状态分类 head
- 因果显著性/driver attribution 导出

软件侧可以直接复用的能力：

- 预测时间序列
- 关键驱动因子解释
- 风险概率输出
- 边界变化概率输出

## 4.2 MSCIM-NoKG

这是去掉知识图谱先验的消融模型，主要价值是：

- 向软件界面展示“知识图谱增强是否有效”
- 用于科研演示和模型对比

它不是产品主推模型，但可保留为“模型对比页”的一个选项。

## 4.3 CMFBE-ST-GCN

当前 `CMFBE-ST-GCN` 是机理增强原型，已显式导出：

- 冲刷/再悬浮 source
- 径流输入 source
- 潮汐输运 source
- 生物增长 source
- 沉降 sink
- 外输 sink
- 自净 sink
- 净过程压力

软件侧可以直接复用的能力：

- 过程分解图
- 机理诊断结果
- 阈值分析基础
- 场景 triage 与阈值检索

## 5. 当前输出产物

`WaterExpert/outputs/` 已经是一套很强的软件后端原始产物，可以直接作为接口原型。

### 5.1 预测与指标

- `outputs/predictions/predictions.csv`
- `outputs/metrics/metrics.json`
- `outputs/metrics/model_comparison.csv`
- `outputs/run_summary.md`

### 5.2 诊断

- `outputs/diagnosis/mscim_turbidity_factor_diagnosis_summary.json`
- `outputs/diagnosis/mscim_turbidity_domain_diagnosis.csv`
- `outputs/diagnosis/cmfbe_process_decomposition_summary.csv`

### 5.3 阈值与知识图谱

- `outputs/thresholds/cmfbe_threshold_summary.csv`
- `outputs/thresholds/cmfbe_threshold_report.md`
- `outputs/thresholds/mechanism_parameter_threshold_kg.json`

### 5.4 agent 检索产物

- `outputs/agent/agent_context.json`
- `outputs/agent/scenario_triage.json`
- `outputs/agent/response_playbook.json`
- `outputs/agent/cmfbe_mechanism_intervention_digest.json`

### 5.5 边界监督

- `outputs/boundary/boundary_detection_summary.json`
- `outputs/boundary/boundary_predictions.csv`
- `outputs/boundary/boundary_label_generation_summary.json`

### 5.6 敏感性与反事实

- `outputs/sensitivity/cmfbe_sobol_indices.csv`
- `outputs/counterfactual/cmfbe_counterfactual_summary.csv`
- `outputs/counterfactual/cmfbe_joint_counterfactual_summary.csv`
- `outputs/counterfactual/cmfbe_sobol_counterfactual_report.md`

## 6. 软件能直接消费哪些结构化结果

### 6.1 `agent_context.json`

适合做：

- 首页总览
- 模型表现摘要
- 高风险日期列表
- 推荐问答入口

其中已经包含：

- best model summary
- test metrics
- threshold risk snapshot
- scenario counts
- high priority days
- recommended agent queries

### 6.2 `scenario_triage.json`

适合做：

- 风险事件列表页
- 情景分类页
- 时间轴回放页
- 阈值证据解释卡片

其中已经包含：

- scenario definitions
- thresholds used
- high priority days
- daily records

### 6.3 `response_playbook.json`

适合做：

- 场景对应建议页
- 监测建议与 follow-up 数据提示
- guardrail 控制

### 6.4 `boundary_detection_summary.json`

适合做：

- 边界头训练状态页
- 边界监督质量摘要
- 模型间边界识别对比页

## 7. 当前实测到的关键结果

### 7.1 主任务表现

当前测试集代表性结果：

- `MSCIM`: turbidity R² 约 0.7291，clearness R² 约 0.6937
- `MSCIM-NoKG`: turbidity R² 约 0.5817，clearness R² 约 0.4995
- `CMFBE-ST-GCN`: turbidity R² 约 0.7481，clearness R² 约 0.7016
- `Persistence baseline`: turbidity R² 约 0.6881，clearness R² 约 0.6523

### 7.2 边界头

当前边界监督已经有真实 raster 派生代理标签支持，测试集代表性结果：

- `CMFBE-ST-GCN`: accuracy 约 0.9130，F1 约 0.3333
- `MSCIM`: accuracy 约 0.8152，F1 约 0.2609

注意：当前正样本很少，所以不能只看 accuracy。

### 7.3 经验阈值

当前代表性经验阈值包括：

- 3 日累计降水：49.1 mm
- 7 日累计降水：141.6 mm
- Songpu flushing potential：3.6456
- 黄渡绝对流量：22.9 m3/s

## 8. 软件开发时必须保留的 guardrails

- 不能把当前阈值说成二维水动力物理临界阈值。
- 不能把当前场景 triage 说成经过治理验证的事件分类体系。
- 不能把 response playbook 说成强化学习控制器。
- 不能把 Sobol 与反事实说成已校准治理策略模拟器。
- 不能把当前系统说成完整多站点生产系统。

## 9. 从研究原型到软件的最短路径

建议优先走下面这条路径：

1. 封装 `WaterExpert` 的训练、推理、导出脚本为后端任务接口。
2. 直接消费 `outputs/agent/*.json`、`outputs/metrics/*.json` 和 `outputs/boundary/*.json`。
3. 做数据导入、预测任务、诊断结果、阈值事件、报告导出五个产品模块。
4. 再决定是否把在线训练、权限体系和数据库完全产品化。
