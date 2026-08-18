# 张家浜图像视频模态处理与跨模态融合说明

## 处理入口

```powershell
.\.ai4s\Scripts\python.exe scripts\preprocess\build_zhangjiabang_cross_modal_dataset.py
.\.ai4s\Scripts\python.exe scripts\analysis\evaluate_zhangjiabang_cross_modal_models.py
```

## 输入数据

- UAV 原始素材：`data/raw/zhangjiabang_uav/`
- 实地监测数据：`data/raw/zhangjiabang_field_monitoring.xlsx`
- 张家浜东闸站代理历史序列：`data/proxy/zhangjiabang_proxy/zhangjiabang_proxy_daily.csv`
- 新增辅助素材来源：`陈行基地旁三鲁河段.zip`，已解压到忽略提交的 `data/raw/zhangjiabang_uav/7.31` 和 `data/raw/zhangjiabang_uav/8.3`

## 输出产物

| 文件 | 说明 |
| --- | --- |
| `field_monitoring_summary.csv` | 从 Excel 子表解析的实地监测摘要。 |
| `field_monitoring_replicates.csv` | 原始重复测量明细。 |
| `uav_asset_index.csv` | 单个图片/视频的索引、预览图、视觉统计和 Transformer 表征。 |
| `uav_visual_daily_features.csv` | 按日期聚合的 UAV 视觉特征。 |
| `zhangjiabang_cross_modal_daily.csv` | 日期级跨模态融合表。 |
| `cross_modal_model_comparison.*` | 模型加入跨模态前后的评估结果。 |

## 当前数据规模

- 实地监测摘要：`7` 组。
- 张家浜目标实测摘要：`3` 组。
- UAV 素材：`13` 个，其中图片 `7` 张、视频 `6` 个。
- UAV 采集日期：`8` 天。
- 跨模态融合行：`8` 行。
- 张家浜目标评估样本：`4` 行。
- 陈行基地旁三鲁河段辅助训练样本：`2` 行。

## 融合逻辑

1. UAV 图片直接提取视觉统计和轻量 Transformer 表征。
2. UAV 视频先用 OpenCV 抽取代表帧，再按图片流程提取视觉统计和 Transformer 表征。
3. 预处理脚本通过 `sample_site_role` 区分张家浜目标样本和三鲁河辅助样本。
4. 标签匹配优先按站点角色匹配：张家浜 UAV 匹配张家浜实测，三鲁河 UAV 匹配陈行/三鲁河实测。
5. `2198` 三甲港水质和 `58370` 浦东气象没有 2026 同日重叠，因此不伪造同日值，而是生成同月上/中/下旬历史代理统计特征。
6. 评估时只在张家浜目标样本上留一验证；三鲁河样本只进入跨模态视觉残差训练池。

## 当前最佳路线

当前最优不是高维直接拼接，而是 `cross_modal_auxiliary_visual_residual`：

- 非视觉 baseline 使用日期上下文 + 2198/58370 历史代理特征。
- 视觉分支只做保守残差校正。
- 三鲁河段样本作为相近河段辅助训练样本，不进入张家浜目标评估集。

该路线在当前小样本上相对强 baseline 仍有正收益：浊度 RMSE 降低 `0.36%`，透明度 RMSE 降低 `0.24%`。

## 网站接入

- 后端接口：`GET /api/v1/cross-modal/zhangjiabang`
- 媒体接口：`GET /api/v1/cross-modal/media?path=...`
- 前端位置：`frontend/visualization.html`、`frontend/js/visualization.js`

页面展示内容包括 UAV 素材计数、实地监测计数、融合样本、媒体预览、每日融合表和模型前后对比指标。
