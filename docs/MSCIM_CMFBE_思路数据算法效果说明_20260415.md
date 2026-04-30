# MSCIM-CMFBE 原型思路、数据、算法与效果说明

## 1. 这份文档是干什么的

这份文档用于说明我当前已经完成的原型工作，重点回答 4 个问题：

1. 我是怎么做的
2. 我用了哪些数据
3. 我用了哪些算法
4. 当前效果怎么样

需要先说明一个关键口径：

- `全站数据库` 已经扩展到 `20` 个主库站点
- `模型原型` 当前仍以 `吴淞口` 作为目标水质站做增强建模
- 水动力增强当前使用的是 `松浦大桥` 和 `黄渡` 两个参考水动力站

也就是说，当前工作是“全站基础库 + 单站增强原型”的组合，而不是“20 个站全部完成同等级水动力增强建模”。

---

## 2. 我的整体思路

整体思路可以概括为 4 步：

### 第一步：先把数据库底座搭起来

先不急着直接训练模型，而是先把各类原始数据统一成可以对齐、可以追溯、可以继续扩展的标准化数据库。

这一层我做了两件事：

- 做出了 `全站水质综合数据库`
- 做出了 `吴淞口单站增强原型数据集`

### 第二步：把多源数据统一到同一个时间主键

对于建模来说，最关键的不是“数据多不多”，而是“能不能按同一时间轴对齐”。

因此我把：

- 水质数据
- 天气数据
- 水动力数据
- 知识先验数据

统一到 `date` 这个日尺度主键上，再做特征工程和训练。

### 第三步：把模型分成两个层次

我没有把所有目标都塞进同一个模型里，而是按功能拆成两个模型：

- `MSCIM`
  主要负责时空预测和致因诊断
- `CMFBE-ST-GCN`
  主要负责机理约束和过程模拟

这样的好处是：

- `MSCIM` 更适合做“预测 + 诊断”
- `CMFBE-ST-GCN` 更适合做“过程拆解 + 情景模拟”

### 第四步：不仅看预测值，还做诊断和解释

我没有只停留在“R² 有多少”，而是继续做了两类解释：

- `MSCIM` 的主导致浊因子诊断
- `CMFBE-ST-GCN` 的致浊源项 / 去浊汇项过程分解

这样后续汇报时就不只是“模型分数”，而是能回答：

- 为什么会变浑
- 为什么会恢复变清
- 哪些因子最值得优先治理

---

## 3. 我用了哪些数据

这里要分成 `建库层` 和 `建模层` 两部分来说。

## 3.1 建库层数据

### 3.1.1 全站水质综合数据库

我已经做出的全站数据库位于：

- `G:\AI4S\全站水质综合数据库_20260415_完整版`

这套库的统计口径是：

- 原始站点文件：`23` 个
- 主库站点：`20` 个
- 排除站点：`3` 个
- 主库总记录数：`31099` 条日尺度记录
- 时间范围：`2014-04-03` 到 `2025-10-31`

当前全站库已经统一好的维度包括：

- 水质
- 透明度代理指标 `secchi_depth_sd_m`
- 天气

其中透明度代理指标使用的换算公式为：

`SD = 1.5 / NTU^0.7`

这套库的意义是：它已经构成了后续多源建模的数据库底座。

### 3.1.2 全站库中的主要字段

全站库目前已经包含的主要字段有：

- 水质：`water_temp`, `ph`, `dissolved_oxygen`, `conductivity`, `turbidity`, `codmn`, `nh3_n`, `tp`, `tn`
- 透明度代理指标：`secchi_depth_sd_m`
- 天气：`pressure`, `air_temp`, `humidity`, `precipitation`, `wind_speed`, `wind_dir`

当前还没有全站统一补进去的内容包括：

- 全站水动力
- 全站 NDTI
- 全站遥感反演
- 全站治理事件结构化表

---

## 3.2 建模层数据

当前真正进入模型原型训练的数据，不是全站 20 站统一训练，而是 `吴淞口单站增强原型`。

### 3.2.1 水质数据

原始文件：

- `G:\AI4S\上海市_宝山区_太湖流域_黄浦江_吴淞口_2586.csv`

数据情况：

- 目标站点：`吴淞口`
- 原始记录数：`7789`
- 聚合后日尺度记录数：`1550`
- 时间范围：`2020-12-17` 到 `2025-10-31`

### 3.2.2 天气数据

原始文件：

- `G:\AI4S\daily_version_A_keep_missing.csv`

匹配结果：

- 当前与吴淞口匹配到的最优气象站：`宝山站`
- 重叠天数：`1550`
- 站点距离约：`15.11 km`

### 3.2.3 水动力数据

原始文件：

- `G:\AI4S\上海水域环境发展有限公司资料提供.xls`

其中包含 4 个分表：

1. `苏州河黄渡流量`
2. `苏州河黄渡日均水位`
3. `黄浦江松浦大桥流量`
4. `黄浦江松浦大桥日均水位`

预处理后得到：

- `G:\AI4S\mscim_cmfbe_prototype\outputs\hydrodynamics_preprocessed\shanghai_hydrodynamics_daily_long.csv`
- `G:\AI4S\mscim_cmfbe_prototype\outputs\hydrodynamics_preprocessed\shanghai_hydrodynamics_daily_wide.csv`

水动力数据情况：

- 参考站点：`松浦大桥`、`黄渡`
- 变量：`flow`, `water_level`
- 时间范围：`2022-01-01` 到 `2024-12-31`
- 自然日总数：`1096` 天

### 3.2.4 融合后可直接训练的数据

我把水质、天气、水动力按 `date` 做 `inner join` 后，形成了当前真正可直接训练的数据集：

- `G:\AI4S\mscim_cmfbe_prototype\outputs\intermediate\multimodal_daily_dataset_with_hydrodynamics.csv`

融合后的关键口径是：

- 可训练样本数：`891` 天
- 时间范围：`2022-01-01` 到 `2024-12-31`

也就是说：

- 不是所有已有数据都能直接同时入模
- 当前真正能用于多源联合训练的交集样本是 `891` 天

### 3.2.5 当前进入模型的特征

当前原型一共用了 `56` 个输入特征，主要包括 4 类：

#### 水质基础特征

- `water_temp`
- `ph`
- `dissolved_oxygen`
- `conductivity`
- `turbidity`
- `codmn`
- `nh3_n`
- `tp`
- `tn`

#### 天气特征

- `pressure`
- `air_temp`
- `humidity`
- `precipitation`
- `wind_speed`
- `wind_dir_sin`
- `wind_dir_cos`

#### 派生环境特征

- `precipitation_3d`
- `precipitation_7d`
- `pressure_drop`
- `resuspension_index`
- `runoff_proxy`
- `nutrient_risk_index`
- `self_purification_index`
- `mixing_proxy`
- `settling_index`
- `hydrodynamic_intensity`
- `conductivity_anomaly`
- `water_air_temp_gap`
- `dayofyear_sin`
- `dayofyear_cos`

#### 水动力与派生特征

- `songpu_flow_m3s`
- `songpu_water_level_m`
- `huangdu_flow_m3s`
- `huangdu_water_level_m`
- `songpu_flow_m3s_abs`
- `songpu_flow_m3s_reverse_flag`
- `songpu_flow_m3s_3d_mean`
- `songpu_flow_m3s_7d_mean`
- `huangdu_flow_m3s_abs`
- `huangdu_flow_m3s_reverse_flag`
- `huangdu_flow_m3s_3d_mean`
- `huangdu_flow_m3s_7d_mean`
- `songpu_water_level_m_1d_diff`
- `songpu_water_level_m_3d_mean`
- `huangdu_water_level_m_1d_diff`
- `huangdu_water_level_m_3d_mean`
- `songpu_flow_level_coupling`
- `huangdu_flow_level_coupling`
- `songpu_flow_m3s_1d_diff`
- `huangdu_flow_m3s_1d_diff`
- `songpu_flow_rise_flag`
- `huangdu_flow_rise_flag`
- `songpu_tidal_pumping_proxy`
- `songpu_resuspension_potential`
- `songpu_flushing_potential`
- `runoff_sediment_pulse`

### 3.2.6 当前未纳入建模的高缺失字段

由于缺失率过高，目前暂时没有纳入训练的字段有：

- `toc`
- `chlorophyll_a`
- `algae_density`

---

## 4. 我用了哪些算法

当前算法分成 5 层。

## 4.1 数据预处理与特征工程

这一层主要做的是：

- 水质数据日尺度聚合
- 天气数据站点匹配
- 水动力数据标准化预处理
- 多源数据按日期对齐
- 派生特征构造

关键做法包括：

- 用最近且重叠天数最优原则匹配气象站
- 对流量保留负值，并构造 `reverse_flag`
- 构造 `3d_mean`、`7d_mean`、`1d_diff`、`flow_level_coupling` 等水动力派生特征
- 构造 `runoff_proxy`、`resuspension_index`、`self_purification_index` 等机理代理特征

## 4.2 知识增强与因果先验构建

这一层的目的，是把“知识”真正转成模型输入，而不是停留在文本层面。

我用到的主要方法有：

### 4.2.1 GraphRAG 关系先验

配置文件中使用的知识工件目录是：

- `G:\AI4S\rag_project\graph_people_demo\ragtest\inputs\artifacts`

程序会读取关系表，把领域关系转成因子图先验。

### 4.2.2 专家规则边

我在代码里手工加入了一批专家规则边，例如：

- `precipitation -> runoff_proxy`
- `wind_speed -> resuspension_index`
- `runoff_proxy -> turbidity`
- `songpu_flow_m3s_abs -> turbidity`
- `songpu_flushing_potential -> clearness_proxy`

### 4.2.3 PCMCI 因果发现

我使用了 `Tigramite` 的 `PCMCI` 方法，对训练集做时滞因果发现。

当前配置：

- `tau_max = 3`
- `pc_alpha = 0.2`
- `alpha_level = 0.05`

输出文件：

- `G:\AI4S\mscim_cmfbe_prototype\outputs\intermediate\pcmci_discovered_edges.csv`

最终把：

- GraphRAG 关系
- 专家规则
- PCMCI 发现结果

合并成一个特征图邻接矩阵，用于后续 MSCIM 的知识增强传播。

## 4.3 MSCIM 算法

`MSCIM` 的源码在：

- `G:\AI4S\mscim_cmfbe_prototype\src\water_ai\models\mscim.py`

核心结构包括：

### 4.3.1 FeatureGraphBlock

先根据知识图邻接矩阵做特征传播，相当于把因果先验注入输入特征。

### 4.3.2 TransformerEncoder

对时间序列做编码，学习：

- 季节性
- 滞后性
- 突变特征
- 长期依赖

### 4.3.3 Causal Scorer

对每个特征学习一个因果显著性权重，用于后续做致因诊断。

### 4.3.4 多头输出

当前输出包括：

- `turbidity_pred`
- `clearness_pred`
- `boundary_logits`

其中：

- 浊度预测是主任务
- 清澈度 proxy 预测是辅助任务
- 边界识别头目前保留接口，但由于缺少栅格标签，暂未真正训练到空间边界任务

### 4.3.5 MSCIM-NoKG 消融

我还专门做了一个 `MSCIM-NoKG`，即不用知识图邻接矩阵，只保留单位阵，作为知识增强消融组。

这样可以证明知识增强到底有没有真实效果。

## 4.4 CMFBE-ST-GCN 算法

`CMFBE-ST-GCN` 的源码在：

- `G:\AI4S\mscim_cmfbe_prototype\src\water_ai\models\cmfbe_stgcn.py`

它不是从零单独起模型，而是建立在 `MSCIM backbone` 之上，再加入显式机理过程项。

### 4.4.1 水动力代理项

先构造两个关键代理量：

- `velocity_proxy`
  把流量和水位转换成类似日尺度“速度强度”的代理信号
- `bed_shear_proxy`
  把速度、风速、水位突变组合成“床面剪切应力代理量”

### 4.4.2 致浊源项

我显式建模了 4 类 source terms：

- `runoff_source`
- `erosion_source`
- `tidal_source`
- `phytoplankton_source`

对应含义分别是：

- 径流输入
- 再悬浮
- 潮汐滞留
- 生态增殖

### 4.4.3 去浊汇项

我显式建模了 3 类 sink terms：

- `krone_deposition_sink`
- `flushing_sink`
- `purification_sink`

对应含义分别是：

- 沉降絮凝
- 冲刷外输
- 自净恢复

### 4.4.4 物理平衡思想

模型内部遵循一个显式过程平衡思想：

`log(1 + T_{t+1}) ≈ log(1 + T_t) + source_total - sink_total`

再和神经网络主干的预测做融合。

### 4.4.5 机理参数可导

这些机理系数不是手工写死的，而是作为可学习参数进入训练。

对应导出的参数文件为：

- `G:\AI4S\mscim_cmfbe_prototype\outputs\physics\physics_coefficients.json`

## 4.5 基线与训练设置

为了证明结果不是“只和自己比”，我还加了两个基线：

- `persistence_baseline`
  直接用上一时刻作为预测
- `ridge_window_baseline`
  用窗口展开后的 Ridge 回归

训练设置来自：

- `G:\AI4S\mscim_cmfbe_prototype\configs\prototype.yaml`

主要超参数为：

- 历史窗口：`21` 天
- 预测步长：`1` 天
- 训练 / 验证 / 测试：`70% / 15% / 15%`
- batch size：`32`
- epoch：`45`
- learning rate：`0.0007`
- weight decay：`0.0001`
- hidden_dim：`64`
- Transformer 层数：`2`
- 注意力头数：`4`
- dropout：`0.10`
- random seed：`42`

损失函数上，我同时考虑了：

- 浊度预测损失
- 清澈度预测损失
- 变化量损失
- 机理项损失

---

## 5. 当前效果怎么样

## 5.1 测试集性能对比

指标文件：

- `G:\AI4S\mscim_cmfbe_prototype\outputs\metrics\model_comparison.csv`

测试集结果如下：

| 模型 | 浊度 R² | 清澈度 proxy R² | 浊度 RMSE | 清澈度 RMSE |
|---|---:|---:|---:|---:|
| MSCIM | `0.7812` | `0.7434` | `25.1064` | `0.0383` |
| MSCIM-NoKG | `0.7395` | `0.6668` | `27.3918` | `0.0436` |
| CMFBE-ST-GCN | `0.7386` | `0.7097` | `27.4386` | `0.0407` |
| persistence baseline | `0.6881` | `0.6523` | `29.9769` | `0.0445` |
| ridge window baseline | `-0.5739` | `-1.2943` | `67.3339` | `0.1144` |

### 当前结论

- 当前 `MSCIM` 是预测效果最好的模型
- 当前 `CMFBE-ST-GCN` 略低于 `MSCIM`，但明显强于朴素基线
- `CMFBE-ST-GCN` 的优势不只是分数，而是机理解释能力更强

## 5.2 知识增强有没有用

知识增强效果文件：

- `G:\AI4S\mscim_cmfbe_prototype\outputs\metrics\knowledge_enhancement_summary.json`

与 `MSCIM-NoKG` 相比，`MSCIM` 在测试集上提升为：

- 浊度 `R² +0.0417`
- 清澈度 proxy `R² +0.0766`
- 浊度 `RMSE -2.2854`
- 清澈度 `RMSE -0.0053`

这说明知识增强不是“概念上有”，而是对结果有实质提升。

## 5.3 相对朴素基线提升

与 `persistence_baseline` 相比，`MSCIM` 的测试集提升为：

- 浊度 `R² +0.0931`
- 清澈度 proxy `R² +0.0912`

说明当前模型已经不是只比线性基线强，而是已经超过最强的朴素时序基线。

## 5.4 MSCIM 的因子诊断结果

诊断文件：

- `G:\AI4S\mscim_cmfbe_prototype\outputs\diagnosis\mscim_turbidity_factor_diagnosis_summary.md`

当前 `MSCIM` 给出的平均主导致浊因子 Top10 中，排名靠前的包括：

- `dayofyear_sin`
- `huangdu_water_level_m`
- `huangdu_flow_m3s_7d_mean`
- `songpu_flow_rise_flag`
- `songpu_flow_m3s_1d_diff`
- `songpu_resuspension_potential`
- `nh3_n`
- `air_temp`

这说明模型已经开始把：

- 季节性
- 水动力背景
- 再悬浮
- 营养盐
- 气象条件

这些因素纳入到致浊诊断中。

## 5.5 CMFBE 的过程分解结果

过程分解文件：

- `G:\AI4S\mscim_cmfbe_prototype\outputs\diagnosis\cmfbe_process_decomposition_summary.csv`
- `G:\AI4S\mscim_cmfbe_prototype\outputs\plots\cmfbe_process_decomposition.png`

当前测试集平均过程贡献为：

### 致浊源项

- 径流输入：`0.2953`
- 潮汐滞留：`0.2576`
- 再悬浮：`0.0775`
- 生态增殖：`0.0012`

### 去浊汇项

- 冲刷外输：`0.3855`
- 沉降絮凝：`0.2234`
- 自净恢复：`0.0455`

### 当前结论

当前阶段主要的致浊来源是：

- 径流输入
- 潮汐滞留

当前阶段主要的去浊过程是：

- 冲刷外输
- 沉降絮凝

这部分结果的价值在于：它能把“为什么变浑、为什么恢复变清”拆成过程分量，而不是只给一个黑箱输出值。

---

## 6. 我目前真正做成了什么

如果要压缩成一句话，我当前真正完成的是：

> 搭建了一套“全站数据库底座 + 吴淞口单站增强原型”的技术路线，并完成了 MSCIM 与 CMFBE-ST-GCN 两个模型的可运行原型、指标评估、因子诊断与过程分解。

更具体地说，我已经做成了：

1. 一套全站基础数据库
2. 一套吴淞口单站增强训练集
3. 一个知识增强版 MSCIM 原型
4. 一个显式机理约束版 CMFBE-ST-GCN 原型
5. 一套可直接汇报的图、指标、诊断和机理说明材料

---

## 7. 当前边界和下一步

当前还没有完全解决的问题有：

1. 当前增强建模还是以 `吴淞口` 为目标站，不是全站 20 站全部完成同等级增强
2. 当前缺少全站本地化水动力，不足以支撑真正的全站断面级增强建模
3. `chlorophyll_a`、藻密度、遥感反演等关键模态仍不完整
4. 边界识别头目前保留了接口，但因为缺少栅格标签，没有真正完成监督训练
5. `CMFBE-ST-GCN` 当前更强的是机理解释，不是全面压倒 `MSCIM` 的预测精度

下一步最值得继续补的数据包括：

- 遥感/NDTI
- 治理事件
- 工程调度
- 更细粒度断面水动力
- `chl-a`、藻密度、辐射/光照

---

## 8. 关键文件索引

### 数据库

- `G:\AI4S\全站水质综合数据库_20260415_完整版`

### 中间数据

- `G:\AI4S\mscim_cmfbe_prototype\outputs\intermediate\multimodal_daily_dataset_with_hydrodynamics.csv`
- `G:\AI4S\mscim_cmfbe_prototype\outputs\intermediate\multimodal_hydrodynamics_merge_summary.json`

### 指标

- `G:\AI4S\mscim_cmfbe_prototype\outputs\metrics\metrics.json`
- `G:\AI4S\mscim_cmfbe_prototype\outputs\metrics\model_comparison.csv`
- `G:\AI4S\mscim_cmfbe_prototype\outputs\metrics\knowledge_enhancement_summary.json`

### 预测与解释

- `G:\AI4S\mscim_cmfbe_prototype\outputs\predictions\predictions.csv`
- `G:\AI4S\mscim_cmfbe_prototype\outputs\interpretability\feature_importance.csv`
- `G:\AI4S\mscim_cmfbe_prototype\outputs\diagnosis\mscim_turbidity_factor_diagnosis_summary.md`
- `G:\AI4S\mscim_cmfbe_prototype\outputs\diagnosis\cmfbe_process_decomposition_summary.csv`

### 图

- `G:\AI4S\mscim_cmfbe_prototype\outputs\plots\mscim_logic_diagram_20260415_v2.png`
- `G:\AI4S\mscim_cmfbe_prototype\outputs\plots\cmfbe_framework_diagram_20260415_v2.png`
- `G:\AI4S\mscim_cmfbe_prototype\outputs\plots\cmfbe_process_decomposition.png`

### 机理说明

- `G:\AI4S\mscim_cmfbe_prototype\outputs\physics\physics_equations.md`
- `G:\AI4S\mscim_cmfbe_prototype\outputs\physics\physics_coefficients.json`

---

## 9. 一句话总结

我当前不是只做了一个“能跑的模型”，而是完成了：

> 从数据库底座、到单站增强原型、到知识增强预测、到机理过程分解、再到汇报材料的一整套可交付原型链条。
