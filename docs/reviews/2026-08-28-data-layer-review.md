# WaterExpert 数据层评审：整理现有数据并统一纳入 dataset/version

## 结论

当前 `data/` 最大的问题不是缺少数据，而是现有文件没有统一登记和管理：有些是原始输入，有些是加工结果，有些是代理数据，有些是专项实验结果，还有些只是模板或目录说明。同一类数据还存在多份宽表。

现在新增上传已经有 `DatasetService`、`dataset`、`dataset version`、质量报告、标准化数据和血缘记录，但仓库里已有的数据还没有全部迁入这条链路。结果是：新数据走正式登记，旧数据仍被脚本或查询服务直接读取，形成两套数据来源。

本轮工作的正确目标应当收敛为：

> 先把当前 `data/` 中真正有用的数据逐项登记为正式 dataset/version；完成校验、迁移和引用切换后，删除不再需要的原始文件和重复文件；以后所有数据的增删改查、版本管理、质量检查和任务引用均走 dataset/version 链路。

不需要先建立更多抽象的数据平台名词，也不需要先重做算法。

---

## 1. 当前数据文件应如何处理

### 1.1 `data/raw`

| 文件 | 当前情况 | 处理意见 |
| --- | --- | --- |
| `wusongkou_water_quality_2586.csv` | 吴淞口水质原始文件，主 pipeline 使用 | 登记为水质 dataset 的初始 version；确认标准化数据可用后删除原文件 |
| `shanghai_weather_daily.csv` | 多气象站逐日数据，主 pipeline 和张家浜代理链路使用 | 登记为气象 dataset 的初始 version；切换引用后删除原文件 |
| `shanghai_hydrodynamics.xls` | 黄渡、松浦流量和水位 Excel 透视表 | 先预处理并登记标准化 version；确认标准化结果可重建后删除 Excel 原文件 |
| `wusongkou_boundary_labels.csv` | 吴淞口边界变化代理标签 | 登记为边界标签 dataset version；保留标签来源和质量字段 |
| `wusongkou_boundary_labels_template.csv` | 填写模板，不是业务数据 | 不登记为 dataset；移到文档或模板位置，确认无引用后删除 |
| `zhangjiabang_field_monitoring.xlsx` | 张家浜现场监测原始 Excel | 登记为张家浜现场监测 dataset version；标准化完成后删除原 Excel |
| `zhangjiabang_uav/` | 当前目录不存在，只有部分加工结果 | 不能把加工结果当作完整数据；补回原始媒体或明确该批数据不可重建 |

### 1.2 `data/full_station_database`

该目录已经包含 20 个可用站点、3 个排除站点和 31,099 条日记录，是最重要的现有数据资产，但目前只是静态交付目录，不是正式的数据资产管理对象。

| 文件 | 当前情况 | 处理意见 |
| --- | --- | --- |
| `station_catalog.csv` | 站点信息和覆盖范围 | 登记为站点数据 dataset/version，作为后续站点校验依据 |
| `water_quality_daily_all_stations.csv` | 全站水质加工表 | 登记为全站水质 dataset version |
| `water_quality_daily_all_stations_with_secchi.csv` | 水质加透明度公式结果 | 不再作为第二份独立事实源；登记为带透明度的派生 version，或由水质 version 重新生成 |
| `multimodal_daily_all_stations_with_weather.csv` | 水质、透明度、天气融合宽表 | 登记为一次融合结果 version；不得与原始水质和气象并列作为可修改事实源 |
| `multimodal_daily_all_stations_modality_summary.csv` | 各站模态覆盖统计 | 作为 dataset/version 的质量与覆盖摘要保存，不能只保留静态 CSV |
| `station_weather_match_summary.csv` | 水质站与气象站匹配结果 | 保存到 version 的处理结果和 lineage 中，记录匹配规则和生成时间 |
| `excluded_station_files.csv` | 被排除站点及原因 | 登记为站点质量记录；不能只靠人工查看 |
| `delivery_summary.json` | 目录摘要 | 迁移为 dataset/version 元数据，完成后可删除 |
| `file_inventory.csv` | 手工文件清单 | 迁移完成后删除，改由 dataset/version 列表提供清单 |

### 1.3 `data/proxy/zhangjiabang_proxy`

这是张家浜东闸站的代理数据，不是张家浜实测数据。当前使用三甲港 2198 作为水质代理、浦东气象站 58370 作为天气代理。

应登记为一个独立 dataset/version，并在记录中保留目标站点、实际来源站点、代理原因、代理距离、覆盖时间和代理标识。任何页面、任务和报告都必须显示“代理数据”。

### 1.4 `data/processed/zhangjiabang_cross_modal`

该目录包含现场监测汇总、重复样、UAV 资产索引、图片/视频帧、视觉特征、跨模态融合表、模型预测和模型评估结果。

建议分开登记：现场监测和 UAV 原始媒体作为数据 version；UAV 索引和特征、跨模态日表作为加工 version；模型比较和预测作为任务结果，不作为事实源。当前原始 UAV 目录缺失，因此必须标记来源不完整、不可完全重建。

### 1.5 `data/knowledge_graph`

`create_final_relationships.parquet` 是模型使用的知识图谱关系数据，应登记为知识图谱 dataset/version。登记时保存来源、生成时间、生成代码版本、关系数量、审核状态和被哪些任务使用。若原始文档缺失，应明确标记不能完全重建。

---

## 2. 当前最需要解决的问题

### 2.1 现有文件没有正式 dataset/version 身份

很多文件只有文件名，没有 dataset_id、version_id、负责人、来源、站点、时间范围、质量等级、生效状态和引用关系。没有这些信息，就无法安全回答“这份数据能不能删”或“这个结果由哪份数据算出来”。

### 2.2 现有基线数据没有走 DatasetService

新上传已经会经过“上传、校验、字段映射、清洗、时间对齐、质量判断、dataset version”，但主 pipeline、查询服务和专项脚本仍直接读取 `data/raw`、`data/full_station_database`、`data/proxy` 和 `data/processed`。

必须先完成现有文件登记，再把代码引用切换到 version 的标准化数据路径。切换完成前不能删除原文件。

### 2.3 同一事实有多份文件

全站水质原表、加透明度表、加天气表，以及张家浜代理和跨模态表中复制的字段，都可以作为处理结果存在，但不能都被当成“可以直接修改的事实数据”。必须记录来源 version、生成方式和是否可重新生成。

### 2.4 字段没有和使用场景对应起来

水质表中的 `codmn`、`nh3_n`、`toc`、`tp`、`tn`、`chlorophyll_a`、`algae_density` 等字段，没有在数据资产页面明确说明是模型输入、诊断输入、查询字段、暂未使用字段还是长期缺失字段。

建议在现有字段字典中增加“当前用途”和“是否必需”，不要让用户从 CSV 或代码猜测。

### 2.5 数据更新仍然以重新生成文件为主

上线后继续替换整个 CSV，会导致重复导入、历史修订不可追踪、旧任务和新数据混淆，以及无法判断报告使用的版本。

dataset/version 需要支持新建版本、追加新日期、修订历史记录、标记旧版本失效、归档和删除未使用版本。

---

## 3. 建议的整理顺序

### 第一步：建立现有数据登记表

先不要移动或删除文件。为每个需要保留的文件登记：dataset_id、version_id、data_type、source_name、source_path、站点或目标地点、覆盖时间、行数、质量等级、status、当前使用方、来源 version、是否允许删除原文件。

### 第二步：将基线文件导入现有 DatasetService

优先登记：

1. 吴淞口水质；
2. 上海气象；
3. 上海水动力；
4. 吴淞口边界标签；
5. 全站水质；
6. 站点目录；
7. 张家浜代理；
8. 张家浜现场和跨模态数据。

每次登记必须生成标准化数据、质量报告、字段字典、lineage、文件哈希和 dataset/version 记录。

### 第三步：切换所有读取路径

切换 `run_full_pipeline.py`、`DataExplorerService`、张家浜代理脚本、跨模态服务、水动力预处理、边界处理脚本、测试和文档。

切换后：主 pipeline 不再直接按固定文件名读取 `data/raw`；查询服务读取当前生效 version；任务记录实际使用的 version_id；派生结果记录来源 version_id；找不到有效 version 时明确报错，不回落到旧文件。

### 第四步：验证后删除原始和重复文件

只有在标准化 version 已生成、质量为 accepted、可以预览、任务可正常使用、原文件 SHA-256 已登记、关键结果前后对比完成且无代码继续引用旧路径后，才能删除原始文件。

删除顺序建议：模板和静态目录清单；已被标准化 version 替代的原始 Excel/CSV；重复派生宽表；无来源、无任务引用、无法解释用途的临时文件。

不要删除仍被 Case、Job 或 Report 引用的 version 文件。

---

## 4. dataset/version 需要补齐的管理能力

当前已有能力继续沿用，不另起一套概念。

### 查询

- 按 dataset、version、data_type、站点和时间范围查询；
- 查看当前生效版本；
- 查看字段字典；
- 查看质量报告；
- 查看标准化数据预览；
- 查看来源和被哪些任务使用。

### 更新

- 上传新增文件生成新 version；
- 追加日期数据不覆盖旧 version；
- 修订历史数据生成修订 version；
- 重新处理时记录输入 version 和处理原因。

### 归档与删除

- 旧 version 标记 archived；
- 当前生效 version 只能有一个；
- archived version 仍可供历史任务和报告追溯；
- 未被 Case、Job 或 Report 引用的数据才允许删除；
- 删除前显示引用列表，删除动作写审计记录。

### 任务引用

任务提交时必须传入或自动确定 dataset/version，并记录实际使用的 version_id、质量等级、时间范围、站点范围、代理标识和生成时间。不允许任务执行时重新扫描目录并自行选择最新文件。

---

## 5. 必须明确标记的数据

- 张家浜代理数据：显示来源站点和“代理数据”。
- 边界标签：显示为栅格派生的边界变化代理标签，不是人工治理边界。
- 透明度：显示为由浊度公式计算得到的代理值，不是直接测得的透明度。
- NDTI：当前配置支持，但仓库没有 `data/ndti` 实际数据，没有数据时不能显示为已接入。
- 水利调度：schema 已支持 `water_control`，但当前没有闸门开度、泵站状态和排水量等数据，没有数据时只能显示未接入。
- UAV：已有衍生特征，但原始 UAV 目录缺失，应显示来源不完整。

---

## 6. 最终整改清单

### P0

1. 给现有需要保留的数据建立 dataset/version 登记表。
2. 将吴淞口水质、上海气象、水动力和边界标签导入 DatasetService。
3. 将全站数据库登记为正式 dataset/version，不再只作为静态交付目录。
4. 让主 pipeline 和查询服务读取 dataset/version。
5. 为每个 version 保存质量报告、字段字典、哈希和 lineage。
6. 切换完成前禁止删除原始文件；切换完成后删除已替代文件。

### P1

1. 登记张家浜代理和跨模态数据，并强制保留代理标识。
2. 将水动力 Excel 转为可持续更新的标准化 version。
3. 删除模板、静态清单和重复宽表，前提是确认无引用。
4. 增加当前生效 version、归档 version 和删除前引用检查。
5. 增加按 dataset/version 的数据查询和预览。

### P2

1. 支持增量追加和历史修订生成新 version。
2. 支持数据版本影响范围查询，能找到受影响的 Case、Job 和 Report。
3. 对站点、字段、代理关系和匹配规则进行统一维护。
4. 再考虑多站点模型和实时数据接入，不要在事实源未统一前继续增加目录和文件。

---

## 7. 验收标准

- `data/` 中每个保留文件都有明确 dataset/version 身份；
- 新旧数据使用同一套 DatasetService；
- 主 pipeline 不再直接读取未登记的原始文件；
- 每个 version 都能查看标准化数据、质量报告和 lineage；
- 同一文件重复导入不会产生重复事实；
- 新增数据和历史修订通过生成新 version 完成，不覆盖旧 version；
- 每个任务都记录实际使用的 dataset/version；
- 代理数据、公式数据和边界代理标签都有明确标识；
- 删除前可以检查引用关系，删除后历史任务仍可追溯；
- 模板、静态文件清单和重复宽表不再承担业务事实源职责；
- 数据资产页面可以完成查询、预览、归档和删除等基本操作。

## 最终判断

当前最合理的路线不是重新设计一套复杂的数据平台，而是把现有文件逐个纳入已经存在的 `dataset/version` 能力，并完成代码引用切换。

只要做到：

`登记 → 校验 → 生成 version → 切换引用 → 验证 → 删除旧文件`

数据层就能从“目录里的研究文件”变成“可维护的数据资产”。
