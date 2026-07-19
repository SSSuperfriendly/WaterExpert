# 张家浜东闸站代理数据接入说明

## 结论

当前仓库内没有检索到可直接用于张家浜东闸站的本地时序数据，也没有检索到张家浜无人机、遥感、水动力或闸门调度序列的可入模文件。

外部公开检索只能确认张家浜东闸站存在，未找到可直接下载的连续时序数据：

- 上海市水务局站网建设文件列出“张家浜东闸站”，河道为张家浜。
- 浦东新区公开 PDF 说明张家浜东闸水文站位于张家浜东水闸东侧，主要监测潮位、风速风向等水文要素。
- 720 云页面显示“张家浜-张家浜东闸站水质自动监测站”，但未提供可导出的历史序列。

参考入口：

- https://swj.sh.gov.cn/swyw/20220114/d7419c4404424695b1a5cbbb7de26f57.html
- https://www.pudong.gov.cn/zwgk/14482.gkml_ywl_slhygl/2024/258/332258/f67b82a9ba2e4cdf95aa149ea75ce600.pdf
- https://720yun.com/t/2cvkzq2lgrm?scene_id=82277716

已按当前可用数据生成张家浜东闸站代理数据集：

- 目标站点：张家浜东闸站。
- 水质代理站：上海市 / 浦东新区 / 太湖流域 / 川杨河 / 三甲港，站点编号 `2198`。
- 气象代理站：浦东站，站点编号 `58370`。
- 代理状态：`substitute_not_direct_measurement`，即替代站点数据，不是张家浜东闸站实测。

## 输出文件

- 代理日尺度数据：`data/proxy/zhangjiabang_proxy/zhangjiabang_proxy_daily.csv`
- 接入摘要：`data/proxy/zhangjiabang_proxy/zhangjiabang_proxy_summary.json`
- 构建脚本：`scripts/preprocess/build_zhangjiabang_proxy_dataset.py`

重新生成命令：

```powershell
.\.ai4s\Scripts\python.exe scripts\preprocess\build_zhangjiabang_proxy_dataset.py
```

如需更换站点，可显式传参：

```powershell
.\.ai4s\Scripts\python.exe scripts\preprocess\build_zhangjiabang_proxy_dataset.py --water-station-code 2198 --weather-station-id 58370
```

## 覆盖情况

本次生成结果：

- `2198` 水质数据：`1559` 条，日期范围 `2020-12-17` 至 `2025-10-31`。
- `58370` 气象数据：`1886` 条，日期范围 `2020-11-02` 至 `2025-12-31`。
- 合并后交集：`1559` 条，日期范围 `2020-12-17` 至 `2025-10-31`。
- 水质序列覆盖率：`100%`。
- 气象序列被使用比例：约 `82.66%`。
- 水质代理站与气象代理站直线距离：约 `22.77 km`。

## 可用字段

水质侧可用字段包括：

- 水温、pH、溶解氧、电导率、浊度、高锰酸盐指数、氨氮、总磷、总氮、水质类别。
- `secchi_depth_sd_m` 是由浊度推导的透明度代理值，不是现场透明度实测。

气象侧可用字段包括：

- 气压、平均气温、相对湿度、当天降水量、平均风速、平均风向。

## 缺口和限制

- 当前结果不能表述为“张家浜东闸站实测多模态数据”，只能表述为“张家浜东闸站代理数据接入”。
- 本地未发现张家浜无人机、遥感、水动力、闸门调度等模态文件。
- `2198` 使用的是三甲港断面水质，空间上可以作为川杨河/浦东近邻替代，但不能替代张家浜东闸站的精确站点水质。
- 当前模型仍以吴淞口为中心训练；张家浜代理数据可用于接入验证、数据质量检查和后续迁移/再训练准备，不应直接宣称现有模型已经完成张家浜站点验证。
