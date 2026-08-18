# WaterExpert Software API Reference

本文档描述 `software/waterturbidity-app` 分支上 `WaterExpert Software` 产品层 FastAPI 服务的 HTTP 契约。接口实现在 [backend/app/main.py](../../backend/app/main.py)，请求体与枚举定义在 [backend/app/schemas.py](../../backend/app/schemas.py)。

> 本文档只描述软件服务层的 API 契约，不覆盖 `scripts/pipeline/` 等研究运行时的命令行入口。

## 基础约定

- **Base URL**：本地启动后为 `http://127.0.0.1:8000`。
- **版本前缀**：所有业务接口统一以 `/api/v1/` 开头。
- **字符编码**：全部请求/响应文本为 **UTF-8**。`text/html`、`text/plain`、`text/markdown` 响应均显式携带 `charset=utf-8`；JSON 响应由 FastAPI 以 UTF-8 编码返回。仓库内所有文本文件遵循 UTF-8（无 BOM 亦可），编辑器请参照 `.editorconfig` 的 `charset = utf-8`。
- **CORS**：已开启 `allow_origins=["*"]`，便于前端跨端口联调。

### 错误模型

| HTTP 状态码 | 含义 | 说明 |
| --- | --- | --- |
| `400` | 请求参数/负载不合法 | 如不支持的 `data_type`、`config_path` 不存在、非法 `model`/`split` |
| `401` | 登录凭据错误 | 用户名或密码不匹配 |
| `404` | 资源不存在 | 预测任务不存在、报告文件不存在、跨模态媒体文件不存在 |
| `409` | 状态冲突 | 任务尚未完成、产物尚未就绪 |
| `500` | 产物损坏或内部错误 | 产物存在但无法解析（`ArtifactReadError`） |
| `503` | 产物缺失 | 所需产物文件不存在（`FileNotFoundError`） |

API 路径下的错误统一返回 `{"detail": "<message>"}`。

---

## 认证

### `POST /api/v1/auth/login`

登录（演示认证）。

**请求体**（`LoginRequest`）：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `username` | string | 1–64 字符 |
| `password` | string | 1–128 字符 |

**响应**（200）：

```json
{ "username": "2510709", "display_name": "AI4S Demo User", "role": "reviewer" }
```

默认演示凭据可通过环境变量覆盖（见下文「环境变量」）。

### `GET /api/v1/auth/hint`

返回当前演示凭据提示（用户名与密码），供前端登录页展示。响应：

```json
{ "username": "2510709", "password": "AI4S666" }
```

---

## 健康与元信息

### `GET /healthz`

健康检查。产物源就绪时返回 `{"status": "ok"}`，否则按错误模型返回 `503`。

### `GET /api/v1/meta`

返回运行元信息。查询参数 `job_id` 可选；提供时读取指定任务的元信息（要求任务已完成）。

### `GET /api/v1/stations`

返回集成产物中的站点清单（`list[dict]`）。

---

## 数据导入

### `POST /api/v1/data/import`

通过服务器本地路径导入数据文件（复制到 `data/imports/<data_type>/`）。

**请求体**（`DataImportRequest`）：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `data_type` | enum | `water_quality` / `weather` / `hydrodynamics` / `water_control` / `boundary_labels` / `spatial` |
| `source_name` | string | 1–120 字符 |
| `file_path` | string | 非空，本地源文件路径 |
| `time_granularity` | string | 默认 `daily` |
| `station_code` | string \| null | 默认 `2586` |

响应为一条导入记录（`import_id`、`status`、`stored_path` 等）。

### `POST /api/v1/data/upload`

浏览器 multipart 上传。表单字段：`data_type`（必填）、`station_code`（默认 `2586`）、`time_granularity`（默认 `daily`）、`files`（一个或多个，支持 `.csv`/`.xls`/`.xlsx`/`.json`）。响应：

```json
{ "uploaded_count": 1, "records": [ ... ] }
```

### `GET /api/v1/data/imports`

返回全部导入记录（按创建时间倒序）。

---

## 水质数据库

数据源：`data/full_station_database/station_catalog.csv` 与 `data/full_station_database/water_quality_daily_all_stations_with_secchi.csv`。

### `GET /api/v1/database/summary`

返回站点总数、记录总数、日期范围与关键指标列表。

### `GET /api/v1/database/stations`

返回站点清单（`list[dict]`），每个元素为 `station_code`、`station_name`、`province`、`city`、`basin`、`river`、经纬度、起止日期、可用性等。

### `GET /api/v1/database/query`

多条件查询。查询参数：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `station_code` | string \| null | — | 按站点编码过滤 |
| `keyword` | string \| null | — | 在站点名/城市/河流/流域中模糊匹配 |
| `start_date` / `end_date` | string \| null | — | 日期范围（`YYYY-MM-DD`） |
| `limit` | int | 200 | 1–1000 |
| `offset` | int | 0 | ≥ 0 |

响应包含 `filters`、`matched_rows`、`returned_rows`、`rows`、`pagination`、`summary`（站点数、日期范围、平均浊度、平均透明度）。

---

## 预处理与可视化

### `GET /api/v1/preprocess/summary`

查询参数 `station_code`（默认 `2586`）。返回逐特征缺失率、异常值、统计量与标准化建议。

### `GET /api/v1/visualization/summary`

查询参数：`station_code`（默认 `2586`）、`indicator`（默认 `turbidity`，可取 `water_temp`/`ph`/`dissolved_oxygen`/`conductivity`/`turbidity`/`tp`/`tn`/`secchi_depth_sd_m`）、`limit`（默认 180，30–720）。返回时间序列、统计量与相关性。

---

## 预测任务

### `POST /api/v1/prediction-jobs`

创建预测任务。

**请求体**（`PredictionJobCreateRequest`）：

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `mode` | enum | `inference` | `inference` / `full_pipeline` |
| `model_name` | enum | `cmfbe_stgcn` | `mscim` / `mscim_no_kg` / `cmfbe_stgcn` |
| `station_code` | string | `2586` | — |
| `config_path` | string \| null | — | 默认 `configs/prototype_repo.yaml` |
| `start_date` / `end_date` | string \| null | — | — |
| `use_existing_artifacts` | bool | `true` | `true` 时直接快照现有集成产物并完成；`false` 时启动子进程运行流水线 |

响应为任务记录（`job_id`、`status`、`artifact_root` 等）。

### `GET /api/v1/prediction-jobs`

列出全部预测任务（倒序，含日志预览）。

### `GET /api/v1/prediction-jobs/{job_id}`

刷新并返回单个任务状态（`status` 可能为 `running`/`completed`/`failed`/`orphaned`）。

### `GET /api/v1/prediction-jobs/{job_id}/series`

返回已完成任务的预测序列（复用 `/api/v1/predictions` 的 `test` 分片）。

---

## 诊断与预测产物

以下接口均支持可选 `job_id` 查询参数；提供时读取该任务的产物（要求已完成），否则读取集成产物。

| 接口 | 说明 |
| --- | --- |
| `GET /api/v1/dashboard` | 仪表盘聚合（站点画像、模型指标、高风险日、护栏说明） |
| `GET /api/v1/predictions` | 预测序列；参数 `model`（可选）、`split`（默认 `test`）、`job_id`（可选） |
| `GET /api/v1/diagnostics` | 主导因子与过程分解诊断 |
| `GET /api/v1/scenario-triage` | 经验场景分诊结果 |
| `GET /api/v1/response-playbook` | 场景化响应建议 |
| `GET /api/v1/thresholds` | 阈值检索；参数 `feature`（可选） |
| `GET /api/v1/boundary` | 边界识别摘要 |
| `GET /api/v1/sensitivity` | Sobol 敏感性摘要 |

---

## 实时验证

### `GET /api/v1/realtime-validation`

返回最新实时验证产物。产物路径 `var/realtime/latest_validation.json`。

- 产物缺失时：`{"status": "missing", "message": "..."}`（HTTP 200）
- 产物损坏时：`{"status": "error", "message": "..."}`（HTTP 200）
- 产物有效时：返回完整验证结果（`target_section`、`latest_observation`、`summary_metrics`、`live_prediction`、`success_estimate`、`true_success_rate` 等）

该产物由 `scripts/realtime/validate_latest_realtime.py` 生成。

---

## 跨模态（张家港）

数据源：`data/processed/zhangjiabang_cross_modal/`。

### `GET /api/v1/cross-modal/zhangjiabang`

返回跨模态融合摘要，含 `preview_assets`（前 12 条资产预览）、`daily_rows`、`model_evaluation` 与汇总字段。

### `GET /api/v1/cross-modal/media`

返回媒体文件（图片/视频帧）。查询参数 `path` 必填，为相对路径；仅允许位于跨模态根目录下的文件，否则 `404`。

---

## 报告导出

### `POST /api/v1/report/export`

生成诊断报告。查询参数：`job_id`（可选）、`format`（`html`/`md`/`json`/`pdf`，默认 `html`）。

响应：

```json
{
  "report_path": "var/reports/waterexpert-software-report-....html",
  "filename": "waterexpert-software-report-....html",
  "format": "html",
  "download_url": "/api/v1/report/files/waterexpert-software-report-....html"
}
```

### `GET /api/v1/report/files/{filename}`

下载已生成的报告文件。`Content-Type` 按格式设置（`text/html; charset=utf-8` / `text/markdown; charset=utf-8` / `application/json` / `application/pdf`）。

---

## 产物数据源总览

| 接口组 | 产物/数据源 |
| --- | --- |
| 健康/元信息/站点/诊断/预测/报告 | `outputs/`（集成运行时产物，`ArtifactRepository`） |
| 水质数据库 | `data/full_station_database/`（站点目录与日尺度全站表） |
| 跨模态 | `data/processed/zhangjiabang_cross_modal/` |
| 实时验证 | `var/realtime/latest_validation.json` |
| 导入文件 | `data/imports/<data_type>/` |
| 任务运行 | `var/state/job_runs/<job_id>/outputs/` |

---

## 环境变量

| 变量 | 用途 | 默认 |
| --- | --- | --- |
| `WATEREXPERT_RUNTIME_ROOT` / `WATERTURBIDITY_RUNTIME_ROOT` | 运行时根目录（`outputs/`、`data/` 相对此根） | 仓库根目录 |
| `WATEREXPERT_REALTIME_APPCODE` / `ALIYUN_APPCODE` | 实时国控数据接口 AppCode | 无（必需） |
| `WATEREXPERT_DEMO_USERNAME` | 演示登录用户名 | `2510709` |
| `WATEREXPERT_DEMO_PASSWORD` | 演示登录密码 | `AI4S666` |
| `WATEREXPERT_DEMO_DISPLAY_NAME` | 演示用户显示名 | `AI4S Demo User` |
| `WATEREXPERT_DEMO_ROLE` | 演示用户角色 | `reviewer` |

> 实时接口 AppCode 不再从 `docs/API/draft.txt` 等文件读取，必须通过 `WATEREXPERT_REALTIME_APPCODE`（或 `ALIYUN_APPCODE`）环境变量提供。
