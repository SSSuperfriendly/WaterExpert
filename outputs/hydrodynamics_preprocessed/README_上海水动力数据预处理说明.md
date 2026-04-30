# 上海水动力数据预处理说明

## 1. 数据来源

- 原始文件：`G:\AI4S\上海水域环境发展有限公司资料提供.xls`
- 预处理脚本：`C:\Users\dell\Desktop\AI4S\mscim_cmfbe_prototype\scripts\preprocess_shanghai_hydrodynamics.py`

## 2. 原始数据包含内容

该 Excel 共有 4 个工作表，分别对应 2 个站点、2 类水动力变量：

1. `苏州河黄渡流量`
2. `苏州河黄渡日均水位`
3. `黄浦江松浦大桥流量`
4. `黄浦江松浦大桥日均水位`

可用时间范围为 `2022-01-01` 至 `2024-12-31`，共 `1096` 天。

其中：

- `黄渡` 代表苏州河方向的辅助水动力站点
- `松浦大桥` 代表黄浦江方向的主水动力站点
- `流量` 单位为 `m3/s`
- `日均水位` 单位为 `m`

## 3. 为什么不能直接入模

水位表本身已经接近日尺度整洁表，但流量表仍是按年份分块、按日历交叉排布的宽格式，存在以下问题：

- 2022、2023、2024 三年放在同一张表内
- 行列布局适合人工查看，不适合程序按日期直接关联
- 不能直接与现有水质、遥感或人工采样数据按日期对齐

因此必须先统一成“按日期索引”的标准表结构。

## 4. 已完成的预处理结果

脚本已生成以下 3 份结果：

1. `G:\AI4S\mscim_cmfbe_prototype\outputs\hydrodynamics_preprocessed\shanghai_hydrodynamics_daily_long.csv`
2. `G:\AI4S\mscim_cmfbe_prototype\outputs\hydrodynamics_preprocessed\shanghai_hydrodynamics_daily_wide.csv`
3. `G:\AI4S\mscim_cmfbe_prototype\outputs\hydrodynamics_preprocessed\summary.json`

结果概况：

- 长表行数：`4384`
- 宽表行数：`1096`
- 日期范围：`2022-01-01` 至 `2024-12-31`
- 当前无缺失日期
- 当前无重复 `(date, station_name, variable)` 记录

## 5. 建议统一的数据标准

### 5.1 长表标准

适合做主数据仓、溯源和后续扩展：

| 字段名 | 含义 |
|---|---|
| `date` | 日期 |
| `station_name` | 站点名称 |
| `river_name` | 河道名称 |
| `station_code` | 站点编码 |
| `variable` | 变量名，如 `flow` / `water_level` |
| `value` | 数值 |
| `unit` | 单位 |
| `source_sheet_index` | 来源工作表编号 |

### 5.2 宽表标准

适合直接送入机器学习或时空模型：

| 字段名 | 含义 |
|---|---|
| `date` | 日期主键 |
| `songpu_flow_m3s` | 松浦大桥流量 |
| `songpu_water_level_m` | 松浦大桥水位 |
| `huangdu_flow_m3s` | 黄渡流量 |
| `huangdu_water_level_m` | 黄渡水位 |

在此基础上，已额外生成一批可直接用于建模的派生特征。

## 6. 模型建议保留的特征

### 6.1 基础特征

- `songpu_flow_m3s`
- `songpu_water_level_m`
- `huangdu_flow_m3s`
- `huangdu_water_level_m`

### 6.2 建议重点保留的派生特征

- `*_abs`
  说明流量绝对强度
- `*_reverse_flag`
  标记是否出现反向流
- `*_3d_mean`
  反映短期平滑趋势
- `*_7d_mean`
  反映周尺度背景水动力
- `*_1d_diff`
  反映水位突变
- `*_flow_level_coupling`
  反映流量与水位的耦合作用

## 7. 预处理时要特别注意的点

### 7.1 负流量不能直接删

流量中出现负值，不一定是脏数据，更可能代表回流、顶托或潮汐反向影响。  
对清澈度诊断来说，这类现象反而很重要，因为它可能影响泥沙再悬浮、污染滞留和浑浊输移。

因此建议：

- 保留原始有符号流量
- 同时增加 `abs(flow)` 和 `reverse_flag`
- 不要简单把负值截断为 0

### 7.2 必须统一时间主键

后续要和以下数据统一到同一日尺度主键：

- 吴淞口水质监测数据
- 遥感反演清澈度或浊度数据
- 气象、雨量、风速等外源驱动数据
- 人工采样、治理事件、工程调度数据

统一后建议采用 `date` 作为主键做左连接或外连接。

### 7.3 单位和命名要固定

建议所有变量列名都写成：

`站点_变量_单位`

例如：

- `songpu_flow_m3s`
- `songpu_water_level_m`

这样后面做特征工程、训练、画图和解释性分析都会更稳定。

## 8. 当前模型的优先接入建议

如果只先接一套水动力驱动，建议优先接入：

- `songpu_flow_m3s`
- `songpu_water_level_m`
- 以及它们的 `3d/7d` 滚动统计、`reverse_flag`、`coupling` 特征

原因是当前已有水质站点位于 `黄浦江吴淞口`，从河道关联性来看，`松浦大桥` 比 `黄渡` 更适合作为第一阶段主驱动站点。

`黄渡` 建议作为辅助站点保留，用于增强上游来水或横向对照信息。

## 9. 对 MSCIM / CMFBE-ST-GCN 的意义

这份新增数据最重要的价值在于：它补上了“水动力驱动层”。

可直接服务于两部分工作：

1. `MSCIM`
   用于清澈度/浊度预测、致浊因子识别、重点治理区诊断
2. `CMFBE-ST-GCN`
   用于输移、自净、阈值与瓶颈环节分析

它尤其适合和已有水质数据一起构建：

- `水质状态`
- `水动力驱动`
- `时序变化`
- `因果诊断`

这一整套联合建模框架。

## 10. 已生成的融合版数据

为了方便直接进入现有原型，我已额外生成：

- `G:\AI4S\mscim_cmfbe_prototype\outputs\intermediate\multimodal_daily_dataset_with_hydrodynamics.csv`
- `G:\AI4S\mscim_cmfbe_prototype\outputs\intermediate\multimodal_hydrodynamics_merge_summary.json`

该文件是在现有 `水质 + 气象` 日尺度数据基础上，按 `date` 与本次水动力宽表做 `inner join` 得到的。

融合后结果：

- 可直接训练样本数：`891`
- 融合后时间范围：`2022-01-01` 至 `2024-12-31`
- 对应完整自然日范围覆盖率约为 `81.3%`

这也说明当前真正的限制不在于新水动力数据缺失，而在于“现有多源数据交集天数”还没有填满全部日历天。
