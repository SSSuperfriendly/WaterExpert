结论先行：

---

## 一、P0：必须先解决，否则仍然是 Demo

### 1. 预测任务参数是“看起来可配置”，实际没有真正生效

前端允许用户选择：

- 模型
- 开始日期
- 结束日期
- 推理 / 全流程模式
- 站点

但后端启动任务时，真正传给 `job_runner.py` 的只有：

- runtime root
- config path
- status file
- artifact root

`model_name`、`start_date`、`end_date`、`station_code` 没有传入实际运行命令，`job_runner.py` 也没有消费这些参数。

证据：

- [runtime_jobs.py](/Users/mac/Project/WaterExpert/backend/app/services/runtime_jobs.py:350)
- [job_runner.py](/Users/mac/Project/WaterExpert/backend/app/tasks/job_runner.py:45)
- [job_runner.py](/Users/mac/Project/WaterExpert/backend/app/tasks/job_runner.py:210)

这意味着用户选择“MSCIM + 某日期范围”，任务可能仍然跑默认配置和默认数据。界面提供了控制感，但任务执行语义并不成立。

修改建议：

- 将模型、站点、日期范围、任务模式写入 job config snapshot。
- pipeline 必须显式读取这些参数。
- 返回实际生效参数，而不是只返回用户提交参数。
- 对不支持的组合在提交阶段拒绝，而不是任务完成后才发现不一致。

---

### 2. “推理模式”和“全流程模式”实际上没有实现两套任务

`PredictionJobCreateRequest` 中有 `mode: inference | full_pipeline`，但 `job_runner.py` 始终执行完整 pipeline 和后处理步骤。

证据：

- [schemas.py](/Users/mac/Project/WaterExpert/backend/app/schemas.py:61)
- [job_runner.py](/Users/mac/Project/WaterExpert/backend/app/tasks/job_runner.py:205)

这属于典型的“字段做出来了，能力没做出来”。

修改建议：

- 取消“推理模式”和“全流程模式”，保留一个，叫做“推理生成”。加载已发布模型，输出预测、置信度和报告生成。
- 页面上明确展示预计耗时和输出内容。

---

### 3. 数据导入不是数据接入系统，只是文件登记和复制

当前导入流程主要完成：

- 文件存在性检查
- 文件复制
- 行数检测
- SQLite 记录

但没有真正完成软著规格中要求的：

- 字段映射
- 数据标准化
- 单位换算
- 时间对齐
- 空间匹配
- 异常检测入库
- 数据质量评分
- 入库后的可消费数据集生成

证据：

- [runtime_jobs.py](/Users/mac/Project/WaterExpert/backend/app/services/runtime_jobs.py:104)
- [data_explorer.py](/Users/mac/Project/WaterExpert/backend/app/services/data_explorer.py:130)

导入成功不等于数据可用。现在存在“文件上传成功，但模型根本不会使用这份数据”的风险。

修改建议：

将导入拆成明确的状态链：

`uploaded → validated → mapped → cleaned → aligned → accepted/rejected`

每一步产生：

- 错误数量
- 缺失率
- 重复数
- 时间覆盖范围
- 站点覆盖范围
- 单位转换记录
- 可用于建模的行数
- 质量等级

导入完成后必须能够回答：

> 这份数据是否已经进入模型输入？如果没有，卡在哪一步？

---

### 4. 产品没有真正的“分析案例”对象

当前有 `Import`、`Job`、`Report` 的雏形，但没有统一的 `Case / AnalysisCase`。

用户无法稳定追踪：

- 哪一批数据触发了任务
- 使用了哪个配置
- 使用了哪个模型版本
- 哪些诊断结果属于这次任务
- 哪个报告对应这次任务
- 结果是否来自旧产物

现有产品评审已经指出这一点，但目前仍没有落地。

修改建议：

建立一等对象：

```text
Case
├── input_dataset
├── data_quality_result
├── config_snapshot
├── model_version
├── prediction
├── diagnosis
├── scenario
├── thresholds
├── boundary
├── report
└── audit_events
```

所有核心接口都必须支持 `case_id` 或 `job_id`，不能一部分读任务产物，一部分读默认 `outputs/`。

---

### 5. 结果没有版本一致性保证

虽然 `RuntimeJobService` 已经支持 job-scoped output，但默认接口仍可以直接读取集成产物：

- `/api/v1/dashboard`
- `/api/v1/predictions`
- `/api/v1/diagnostics`
- `/api/v1/thresholds`
- `/api/v1/boundary`

如果前端没有明确绑定 job，用户看到的可能是上一次运行结果。

此外，报告是读取多个文件后即时拼装，存在指标、预测、诊断来自不同版本的情况。

修改建议：

- 所有页面默认绑定“当前案例”。
- 默认禁止混用 integrated artifacts 和 job artifacts。
- 每份产物附带 `run_id`、`generated_at`、`model_version`、`config_hash`。
- 报告生成前锁定 manifest，报告中写入完整版本信息。
- 增加“结果是否过期”的标识。

---

### 6. 权限系统远未达到市级项目要求

当前有登录、注册和 JWT，但更像“接口加了一层 Bearer Token”，不是完整权限体系。

问题包括：

- 角色字段存在，但没有真正的 RBAC 权限判断。
- 用户管理路由没有看到细粒度权限控制。
- 报告下载接口被明确排除在鉴权之外。
- 知识图谱文件下载接口未鉴权。
- 跨模态媒体接口未鉴权。

证据：

- [main.py](/Users/mac/Project/WaterExpert/backend/app/main.py:64)
- [main.py](/Users/mac/Project/WaterExpert/backend/app/main.py:70)
- [main.py](/Users/mac/Project/WaterExpert/backend/app/main.py:534)
- [main.py](/Users/mac/Project/WaterExpert/backend/app/main.py:629)

此外，默认演示账号和密码仍出现在文档与接口提示中：

- [users.py](/Users/mac/Project/WaterExpert/backend/app/users.py:35)
- [software_api_reference.md](/Users/mac/Project/WaterExpert/docs/API/software_api_reference.md:45)

修改建议：

至少建立：

- 系统管理员
- 审核人员
- 业务用户

并对以下动作做权限控制：

- 上传 / 删除数据
- 启动模型任务
- 发布模型
- 修改阈值
- 导出报告
- 知识图谱构建
- 用户管理

报告、文件和媒体必须经过鉴权，并校验用户是否拥有对应案例的访问权。

---

### 7. 存在明显的安全配置问题

后端开启了：

```python
allow_origins=["*"]
allow_credentials=True
```

证据：

- [main.py](/Users/mac/Project/WaterExpert/backend/app/main.py:106)

这不适合作为正式部署默认配置。还存在：

- 服务器端文件路径导入接口，可能读取任意可访问路径。
- 上传接口没有明确的文件大小限制。
- 没有 MIME / 内容签名校验。
- 没有病毒扫描。
- 没有报告访问审计。
- 文件名虽然做了 basename 处理，但数据生命周期控制不足。
- 下载接口只按文件名查找，没有用户归属校验。

修改建议：

- CORS 改为环境变量白名单。
- `/api/v1/data/import` 不允许任意服务器路径，改为受控数据目录或对象存储。
- 增加文件大小、扩展名、内容类型和压缩炸弹防护。
- 所有下载接口鉴权。
- 增加安全审计日志和异常访问告警。

---

## 二、P1：已经做了，但做了一半

### 8. 数据库页面不是“数据库管理”

当前数据库页面主要是：

- 数据摘要
- 文件上传
- 导入历史

缺少：

- 数据集版本
- 数据预览
- 字段字典
- 数据质量报告
- 数据删除 / 归档
- 导入失败详情
- 数据与任务的绑定关系
- 数据血缘关系

而且上传和服务器路径导入是两个重复入口，业务语义不清晰。

证据：

- [database/page.tsx](/Users/mac/Project/WaterExpert/frontend/app/database/page.tsx:1)
- [upload-panel.tsx](/Users/mac/Project/WaterExpert/frontend/components/waterexpert/panels/upload-panel.tsx:35)

修改建议：

合并成“数据资产中心”，每个数据集具备：

- 数据集 ID
- 来源
- 责任人
- 覆盖站点
- 时间范围
- 质量等级
- 当前版本
- 使用中的任务
- 最近更新时间
- 是否可建模

---

### 9. 数据预处理接口存在，但没有进入主流程

后端有：

- `/api/v1/preprocess/summary`

但前端已经没有独立预处理页，上传后也不会自动触发预处理任务，用户看不到清洗、对齐、异常处理的过程。

这会导致“规格说明写了数据治理，实际只是一个摘要接口”。

修改建议：

- 上传完成后自动生成数据质量任务。
- 在数据集详情页展示质量报告。
- 预处理结果必须能被任务选择。
- 禁止直接对未经质量校验的数据执行正式预测。

---

### 10. 任务状态做得比 Demo 好，但还没有生产级任务中心

已有：

- SQLite 状态存储
- job run 目录
- 状态文件
- 日志预览
- orphaned 状态
- 前端轮询

这是当前实现中比较成熟的一部分，但仍不完整：

- 没有取消任务。
- 没有暂停 / 重试任务。
- 没有超时策略。
- 没有并发配额。
- 没有队列。
- 没有资源限制。
- 没有任务优先级。
- 没有任务失败分类。
- 没有失败重试原因。
- 没有任务保留和清理策略。
- 多实例部署下仍缺少统一调度器。

前端轮询虽已实现，但只能发现状态变化，不能提供真正的运行进度。`job_runner.py` 的 stage 只是文字状态，不是可计算的百分比。

修改建议：

引入任务中心：

```text
queued
running
cancelling
cancelled
completed
failed
timeout
orphaned
```

并提供：

- 取消
- 重试
- 失败诊断
- 预计剩余时间
- 当前阶段
- 资源占用
- 产物列表
- 日志下载

---

### 11. 模型治理没有做

当前有模型文件、指标比较和默认最佳模型，但没有：

- 模型注册中心
- 模型版本号
- 训练数据版本
- 配置版本
- 发布 / 下线状态
- 审批人
- 线上默认模型切换
- 模型回滚
- 模型漂移监控
- 数据漂移监控
- 线上质量跟踪

首页直接展示“最佳模型”，但没有说明：

- 最佳是按哪个指标？
- 哪个时间窗口？
- 哪个站点？
- 是否经过人工审核？
- 是否已经发布到生产？

修改建议：

建立模型生命周期：

`实验 → 候选 → 审核 → 发布 → 运行 → 退役`

首页不要只显示“最佳模型”，应显示：

- 当前发布模型
- 评估模型
- 发布版本
- 评估时间
- 适用范围
- 最近线上表现

---

### 12.首页信息很多，但没有告诉用户“现在该做什么”

首页目前展示：

- 产品名称
- 算法核心
- 数据行数
- 匹配模型行数
- 站点信息
- 最佳模型
- 阈值风险
- 模型指标
- 场景数量
- 高优先日期

证据：

- [page.tsx](/Users/mac/Project/WaterExpert/frontend/app/page.tsx:35)

问题是它更像“成果展板”，不是业务首页。用户无法第一时间知道：

- 当前有没有异常
- 哪个案例需要处理
- 最近一次任务是否成功
- 数据是否新鲜
- 哪些结论需要人工确认
- 下一步该点哪里

修改建议：首页改为

- 当前数据更新时间
- 当前模型状态
- 待处理案例
- 高风险事件
- 数据质量异常
- 最近任务
- 待审核报告
- 明确的下一步按钮

---

### 13. 页面缺少“证据链”设计

预测、诊断、响应、阈值、边界虽然都有页面，但页面之间没有明确的“查看相关证据”关系。

用户应该可以从一个高优先日期直接进入：

`预测曲线 → 主导因子 → 阈值超越 → 场景判断 → 边界变化 → 建议监测 → 报告`

而不是复制日期、切页面、重新筛选。

修改建议：

所有日期 / 案例都使用统一 `case_id` 和 `target_date`，各页面提供上下文跳转。

---

### 14. 报告导出完成了格式，没有完成交付流程

当前报告支持：

- HTML
- Markdown
- JSON
- PDF

这比早期状态好，但仍缺少：

- 报告模板管理
- 报告标题和项目名称
- 时间范围选择
- 内容勾选
- 生成前预览
- 审核 / 驳回
- 电子签名
- 版本号
- 生成者
- 审核者
- 发送 / 分享
- 下载权限
- 报告归档
- 报告检索

当前报告生成逻辑是一次性读取多个产物后生成文件：

- [report_builder.py](/Users/mac/Project/WaterExpert/backend/app/services/report_builder.py:1)

修改建议：

建立“报告中心”，将报告作为正式业务对象，而不是临时下载文件。

---

### 15. 国际化完成了一半

前端有中英文切换，但从代码和文案看，很多业务字段仍可能直接显示：

- 原始 key
- 原始 feature 名称
- 原始 scenario 名称
- 原始错误信息
- 英文模型标识
- 后端原始状态

切换语言后不一定能得到完整一致的产品体验。

修改建议：

- 所有枚举、状态、错误码、字段标签集中管理。
- API 返回稳定 code，前端负责本地化。
- 禁止直接把后端异常字符串当作 UI 文案。
- 增加中英文截图回归测试。

---

## 四、P1：质量和工程风险

### 16. 当前测试没有全绿

执行：

```bash
.ai4s/bin/python -m pytest -q
```

结果：

- 75 passed
- 3 failed

失败包括：

1. API contract 测试读取 `app.routes` 时遇到 `_IncludedRouter` 没有 `.path`。
2. 跨模态评估测试要求 auxiliary visual residual 模型 RMSE 优于 baseline，但实际不满足。

这说明当前仓库不是“测试全绿可交付”状态。

前端构建可以成功：

```text
npm run build
✓ Compiled successfully
✓ Finished TypeScript
```

但“前端能构建”不等于“系统可交付”。

修改建议：

- 修复 API contract 测试与 FastAPI 路由注册方式的兼容问题。
- 重新核验跨模态测试的断言是否符合当前数据与算法设计。
- 将后端 API、前端静态页面、任务生命周期、报告导出纳入 CI。
- 设置发布门禁：测试失败不可打包发布。

---

### 17. 缺少端到端验收测试

现有测试以单元和 API contract 为主，没有充分验证完整业务链：

`上传文件 → 质量检查 → 创建任务 → 任务完成 → 读取结果 → 查看诊断 → 导出报告`

也缺少：

- 浏览器真实登录
- 权限访问
- 长任务轮询
- 任务中途重启
- 数据上传失败
- 空数据
- 错误格式
- 大文件
- 并发任务
- 报告下载权限
- 结果版本一致性

修改建议：

引入最少三类测试：

- API 集成测试
- Playwright 浏览器验收测试
- 生产类故障演练测试

---

### 18. 没有部署和运维体系

当前启动方式主要是本地脚本和 Uvicorn，缺少市级项目必需的：

- Docker 镜像
- 反向代理配置
- HTTPS
- 健康检查
- 就绪检查
- 日志采集
- 指标监控
- 告警
- 数据备份
- 数据恢复演练
- 任务清理
- 存储容量监控
- 灰度发布
- 回滚方案
- 多实例部署说明

`/healthz` 目前只检查部分 artifact 是否存在，不能说明：

- 数据库是否可写
- 任务执行器是否可用
- 磁盘是否足够
- 外部实时接口是否可用
- 模型是否可加载

修改建议：

拆分：

- liveness
- readiness
- dependency health
- model health
- data freshness health

---

### 19. 没有数据生命周期管理

当前会持续产生：

- 上传文件
- job run 目录
- stdout / stderr 日志
- 报告文件
- 知识图谱文件
- 模型产物

但没有：

- 保留期限
- 自动清理
- 归档策略
- 数据删除
- 用户申请删除
- 备份
- 恢复
- 容量告警

报告接口每次生成新文件，没有报告索引和保留机制。

---

### 20. 没有告警、通知和处置闭环

系统能识别高优先日期，但不能真正形成业务动作：

- 无短信 / 邮件 / 企业微信 / 钉钉通知
- 无告警确认
- 无误报反馈
- 无处置记录
- 无升级机制
- 无关闭条件
- 无事件复盘

因此“response playbook”目前只是展示型建议，不是处置系统。

修改建议：

建立事件对象：

```text
事件发现 → 分派 → 确认 → 处置 → 复核 → 关闭 → 复盘
```
