# 全站水质综合数据库说明

## 1. 数据库定位
`20260415_完整版数据库` 是一套面向全站点整理的水质综合数据库底座。

## 2. 数据来源与统计
当前数据库来源于：
- `水质数据.zip`：上海重点流域断面水质原始 CSV
- `daily_version_A_keep_missing.csv`：上海多站点日尺度气象数据

本次交付统计如下：
- 原始站点数：23
- 主库站点数：20
- 排除站点数：3
- 主库日尺度记录数：31099
- 主库时间范围：2014-04-03 到 2025-10-31

## 3. 主库纳入规则
- `监测时间` 可正常解析
- 原始记录数不少于 30 条
- 不属于撤销站点

## 4. 核心文件
- `01_预处理数据/station_catalog.csv`
  每个站点一行，记录站名、流域、河流、经纬度、时间范围、数据量、是否可用
- `01_预处理数据/water_quality_daily_all_stations.csv`
  所有主库站点统一成日尺度水质表
- `01_预处理数据/water_quality_daily_all_stations_with_secchi.csv`
  在上表基础上增加 `secchi_depth_sd_m`
- `01_预处理数据/multimodal_daily_all_stations_with_weather.csv`
  文件为“全站水质-透明度-天气多维度融合日表”
- `01_预处理数据/multimodal_daily_all_stations_modality_summary.csv`
  文件为“全站维度覆盖摘要表”
- `02_说明文档/README_数据库说明.md`
  本说明文件，说明字段、公式、来源、可用范围与使用边界

## 5. 其余辅助文件
- `01_预处理数据/station_catalog_main.csv`
  仅主库 20 个有效站点
- `01_预处理数据/station_catalog_all.csv`
  全部 23 个站点的总目录，含纳入/排除状态
- `01_预处理数据/excluded_station_files.csv`
  3 个未纳入主库的异常/撤销/补充站点说明
- `01_预处理数据/station_weather_match_summary.csv`
  每个主库站与气象站的匹配关系
- `01_预处理数据/per_station_daily_with_secchi/`
  每个主库站点的单独日尺度结果

## 6. `station_catalog.csv` 字段说明
- `station_code`：站点编码，取自原始文件名尾部编号
- `station_name`：站点名称
- `province`, `city`, `basin`, `river`：省份、城市、流域、河流
- `longitude`, `latitude`：站点经纬度
- `start_date`, `end_date`：该站在主表中的时间范围
- `raw_rows`：原始小时级或次级观测记录条数
- `daily_rows`：聚合成日尺度后的记录条数
- `is_available`：是否纳入当前主库
  `True` 表示纳入主库，可直接参与后续全站数据库构建
  `False` 表示不纳入主库，单独列为异常/撤销/补充站点
- `availability_note`：站点可用性说明
  当前可能值包括：
  `main_database`：已纳入主库
  `withdrawn_station`：撤销站点，不纳入主库
  `too_few_observations`：观测过少，暂不纳入主库
- `source_file`：原始文件在压缩包中的路径

## 7. 排除站点清单
当前排除的 3 个站点如下：
- `3787` 明星路桥（撤销）
  文件名已明确标注“撤销”，不纳入主库
  压缩包中另有 `2587` 明星路桥有效站点，已纳入主库
- `3788` 青草沙进水口
  原始记录仅 1 条，暂不纳入主库
- `6377` 闵行西界
  原始记录仅 7 条，聚合后仅 2 个日尺度记录，暂不纳入主库

对应清单见：
- `01_预处理数据/excluded_station_files.csv`

## 8. 天气匹配规则与说明
`multimodal_daily_all_stations_with_weather.csv` 的含义是“全站水质-透明度-天气多维度融合表”，其构建规则为：
- 先对每个主库站点，统计其与每个气象站的日期重叠天数
- 按“重叠天数从高到低”排序
- 若多个候选气象站重叠情况相同，再按空间距离从近到远排序
- 选取排序最优的 1 个气象站作为该水质站的匹配站

对应结果说明文件：
- `01_预处理数据/station_weather_match_summary.csv`

其中主要字段含义为：
- `weather_station_id`, `weather_station_name`：匹配到的气象站编号与名称
- `weather_distance_km`：水质站与气象站的球面距离，单位 km
- `weather_overlap_days`：两者日期重叠天数
- `matched_weather_days`：真正并入融合表后的有效天气记录天数

## 9. 维度摘要字段说明
`multimodal_daily_all_stations_modality_summary.csv` 是“维度覆盖摘要表”，用于快速查看每个站当前具备哪些融合维度、还缺哪些维度。

其中：
- `available_modalities`：当前站点已具备的维度，以 `|` 分隔
- `missing_modalities`：当前站点缺失的维度，以 `|` 分隔
- `water_quality_days`：该站可用的水质日尺度天数
- `secchi_days`：该站可用的透明度换算天数
- `weather_days`：该站成功并入天气后的天数
- `secchi_coverage_ratio`：`secchi_days / water_quality_days`
- `weather_coverage_ratio`：`weather_days / water_quality_days`

这里的“维度”当前主要是：
- `water_quality`
- `secchi_proxy`
- `weather`

## 10. 字段与单位说明
### 10.1 水质字段
主表字段包括：
- 基础信息：`station_code`, `station_name`, `province`, `city`, `basin`, `river`, `longitude`, `latitude`, `date`
- 水质指标：`water_temp`, `ph`, `dissolved_oxygen`, `conductivity`, `turbidity`, `codmn`, `nh3_n`, `toc`, `tp`, `tn`, `chlorophyll_a`, `algae_density`
- 水质状态：`water_quality_class`, `station_status`

主要单位：
- `water_temp`：摄氏度（℃）
- `ph`：无量纲
- `dissolved_oxygen`：mg/L
- `conductivity`：μS/cm
- `turbidity`：NTU
- `codmn`：mg/L
- `nh3_n`：mg/L
- `toc`：mg/L
- `tp`：mg/L
- `tn`：mg/L
- `chlorophyll_a`：mg/L
- `algae_density`：cells/L

### 10.2 透明度换算字段
- 字段名：`secchi_depth_sd_m`
- 公式：`SD = 1.5 / NTU^0.7`
- 单位：m
- 说明：这是基于浊度换算得到的透明度代理指标，用于补充“清澈度”相关表征

### 10.3 气象字段
融合表新增：
- 气象站信息：`weather_station_id`, `weather_station_name`, `weather_district`, `weather_city`, `weather_distance_km`
- 气象变量：`pressure`, `air_temp`, `humidity`, `precipitation`, `wind_speed`, `wind_dir`

主要单位：
- `pressure`：hPa
- `air_temp`：℃
- `humidity`：%
- `precipitation`：mm
- `wind_speed`：m/s
- `wind_dir`：度（0-360）

## 11. 数据来源
- 水质数据：`G:\AI4S\水质数据.zip`
- 气象数据：`G:\AI4S\daily_version_A_keep_missing.csv`