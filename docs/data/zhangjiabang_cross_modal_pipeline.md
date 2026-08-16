# 张家浜图像视频模态处理与跨模态融合说明

## 已完成能力

本项目已将张家浜 UAV 图片/视频与实地监测数据接入为可计算的跨模态数据产物。

处理入口：

```powershell
.\.ai4s\Scripts\python.exe scripts\preprocess\build_zhangjiabang_cross_modal_dataset.py
```

输入数据：

- UAV 原始素材：`data/raw/zhangjiabang_uav/`
- 实地监测数据：`data/raw/zhangjiabang_field_monitoring.xlsx`
- 张家浜代理气象数据：`data/proxy/zhangjiabang_proxy/zhangjiabang_proxy_daily.csv`

输出目录：

- `data/processed/zhangjiabang_cross_modal/`

## 输出产物

| 文件 | 说明 |
| --- | --- |
| `field_monitoring_summary.csv` | 从 Excel 各子表解析出的实地监测摘要，包含透明度、浊度、温度、pH、ORP、DO、EC、叶绿素等。 |
| `field_monitoring_replicates.csv` | 原始重复测量行，保留 `raw_replicate`、`mean`、`error` 行类型。 |
| `uav_asset_index.csv` | UAV 图片/视频资产索引，包含日期、类型、文件大小、视频帧数、时长、预览图路径。 |
| `uav_visual_daily_features.csv` | 按日期聚合的 UAV 视觉特征。 |
| `zhangjiabang_cross_modal_daily.csv` | 日期级跨模态融合表。 |
| `zhangjiabang_cross_modal_summary.json` | 跨模态处理摘要，供后端和前端读取。 |
| `thumbnails/` | UAV 图片缩略图。 |
| `video_frames/` | 视频代表帧。 |

## 融合逻辑

1. 实地监测侧读取 Excel 所有子表，解析采样日期、采样地点、指标值和误差。
2. UAV 侧按文件夹日期建立资产索引，图片直接提取视觉特征，视频用 OpenCV 抽取代表帧后提取视觉特征。
3. 视觉特征包括亮度、饱和度、RGB 均值、绿色指数、棕黄浊度代理、暗水体比例、强反光比例、植被相似比例、Laplacian 清晰度等。
4. 融合表以 UAV 日期为主键，匹配最近的张家浜实地监测记录：
   - `exact_same_day`：同日强监督样本。
   - `near_day`：±1 天近邻监督样本。
   - `same_week_context`：±7 天弱监督上下文样本。
   - `no_field_label`：仅 UAV 视觉样本。
5. 如果代理气象数据有同日期记录，则同时合并气压、气温、湿度、降水、风速、风向等字段。

## 当前结果

当前处理结果：

- 实地监测摘要：7 组。
- 张家浜实地监测摘要：3 组。
- 实地重复测量明细：40 行。
- UAV 素材：9 个，其中图片 5 张、视频 4 个。
- UAV 采集日期：6 个。
- 跨模态融合行：6 行。
- 监督/弱监督跨模态样本：4 行。
- 同日强监督样本：2 行。

这说明项目已经从“时序多源融合”推进到“实地监测 + UAV 图像视频 + 气象代理”的跨模态工程闭环。当前样本规模仍然较小，因此模型层使用时应区分强监督、近邻监督和弱监督上下文，避免把弱标签当成同日实测标签。

## 网站接入

后端接口：

- `GET /api/v1/cross-modal/zhangjiabang`
- `GET /api/v1/cross-modal/media?path=...`

前端位置：

- `frontend/visualization.html`
- `frontend/js/visualization.js`

页面展示内容：

- UAV 素材数量、图片数量、视频数量。
- 实地监测组数、融合样本数、同日强监督样本数。
- UAV 缩略图与视频代表帧。
- 每日跨模态融合表。
