# WaterExpert 前端迁移方案：采用 Square UI `dashboard-3` 基座

## 1. 当前共识

本次迁移的目标不是重做 `WaterExpert` 的研究原型，也不是把项目改成一个新产品，而是在现有 `/Users/mac/Project/WaterExpert` 仓库内继续开发 `WaterExpert Software`：

- 继续复用现有 `backend/app/` 服务层、`src/water_ai/` 算法核心、`scripts/` 脚本入口、`outputs/` 既有产物和 `var/` 运行态数据。
- 淘汰当前 `frontend/` 下的静态 HTML/CSS/JS 前端。
- 使用 `vendor/square-ui/templates-baseui/dashboard-3` 的前端设计和组件体系作为新的 `frontend/` 基座。
- 新前端目录仍叫 `frontend/`，不要另起 `frontend-new`、`new-ui`、`dashboard3-ui` 之类目录名。
- 界面默认中文，支持切换英文。
- 事实边界必须保留：吴淞口单站点、多模态、日尺度原型；经验阈值；raster 派生代理边界标签；scenario triage、playbook、Sobol、counterfactual 均为原型级诊断/推理支撑，不是治理验证策略。

模板源码已经克隆到：

```text
vendor/square-ui/
```

需要采用的模板子目录：

```text
vendor/square-ui/templates-baseui/dashboard-3/
```

## 2. 技术路线

推荐将 `frontend/` 从静态站点迁移为 Next 应用：

```text
frontend/
├── app/
├── components/
├── hooks/
├── lib/
├── public/
├── store/
├── package.json
├── pnpm-lock.yaml
├── next.config.ts
├── postcss.config.mjs
├── tsconfig.json
└── components.json
```

采用模板的技术栈：

- Next 16 App Router
- React 19
- TypeScript
- Tailwind CSS v4
- Base UI / shadcn 风格组件
- Recharts
- Zustand
- Hugeicons

推荐运行方式：

- 开发态：FastAPI 运行在 `http://127.0.0.1:8000`，Next 运行在 `http://127.0.0.1:3000`。
- 交付态：Next 静态导出到 `frontend/out`，FastAPI 挂载 `frontend/out` 到 `/ui`。

不要把算法调用、CSV/JSON 读取逻辑移到 Next 服务端。前端只消费 `backend/app/main.py` 暴露的 API。

## 3. 目录迁移策略

### 3.1 保留不动

这些目录不参与前端替换：

```text
backend/
configs/
data/
docs/
outputs/
scripts/
src/
tests/
var/
```

### 3.2 替换 `frontend/`

旧前端需要淘汰的内容包括：

```text
frontend/*.html
frontend/styles.css
frontend/js/
```

迁移时先完整记录这些文件承载的功能，再用新的 React 页面和组件复刻功能。确认新前端可运行后，再删除旧静态页面和旧 JS。

可以复用的旧资产：

```text
frontend/assets/login-background.png
```

如果新登录页继续使用该图片，应移动到：

```text
frontend/public/assets/login-background.png
```

## 4. 后端接入调整

当前后端通过 `StaticFiles(directory=settings.frontend_root)` 挂载 `/ui`，且根路由跳转到 `/ui/login.html`。迁移后建议调整为：

- `backend/app/config.py`
  - `frontend_root` 指向 `PROJECT_ROOT / "frontend" / "out"`。
- `backend/app/main.py`
  - `app.mount("/ui", StaticFiles(directory=settings.frontend_root, html=True), name="ui")`
  - 根路由跳转到 `/ui/login`
  - 404/500 页面由 Next 导出页面承接，或者保留后端最小错误响应。

开发态不依赖 FastAPI 静态挂载，可以直接访问 Next：

```bash
cd frontend
pnpm install
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 pnpm dev
```

交付态：

```bash
cd frontend
pnpm build
```

若采用静态导出，需要在 `next.config.ts` 中设置：

```ts
const nextConfig = {
  output: "export",
  basePath: "/ui",
  images: { unoptimized: true },
};

export default nextConfig;
```

## 5. API 映射

新前端必须继续消费现有 API，不要改动算法层输出结构。

| 页面/组件 | 后端接口 | 主要用途 |
| --- | --- | --- |
| 登录页 | `GET /api/v1/auth/hint`, `POST /api/v1/auth/login` | demo 登录、用户信息 |
| 应用外壳 | `GET /api/v1/meta`, `GET /api/v1/stations` | 范围说明、站点信息、guardrails |
| 系统总览 | `GET /api/v1/dashboard`, `GET /api/v1/predictions`, `GET /api/v1/scenario-triage` | 模型摘要、高优先事件、预测快照 |
| 水质综合数据库 | `GET /api/v1/database/summary`, `GET /api/v1/database/stations`, `GET /api/v1/database/query` | 数据库统计、站点列表、记录检索 |
| 数据上传 | `POST /api/v1/data/upload`, `POST /api/v1/data/import`, `GET /api/v1/data/imports` | 文件上传、路径导入、导入记录 |
| 数据预处理 | `GET /api/v1/preprocess/summary` | 缺失、异常、标准化摘要 |
| 数据可视化 | `GET /api/v1/visualization/summary` | 趋势、指标范围、相关性 |
| 预测任务 | `POST /api/v1/prediction-jobs`, `GET /api/v1/prediction-jobs`, `GET /api/v1/prediction-jobs/{job_id}` | 创建任务、列表、轮询 |
| 预测结果 | `GET /api/v1/predictions`, `GET /api/v1/prediction-jobs/{job_id}/series` | 实测/预测曲线、模型切换 |
| 致因诊断 | `GET /api/v1/diagnostics` | 主导因子、过程分解、领域归因 |
| 场景分诊 | `GET /api/v1/scenario-triage`, `GET /api/v1/response-playbook` | 高优先日期、经验场景、建议脚手架 |
| 阈值与边界 | `GET /api/v1/thresholds`, `GET /api/v1/boundary` | 经验阈值、边界代理识别摘要 |
| 敏感性与反事实 | `GET /api/v1/sensitivity` | Sobol、单因子与联合反事实摘要 |
| 报告导出 | `POST /api/v1/report/export`, `GET /api/v1/report/files/{filename}` | HTML/Markdown/JSON/PDF 报告导出 |
| 实时检验 | `GET /api/v1/realtime-validation` | 最新国控数据验证摘要 |

前端建议新增统一 API 客户端：

```text
frontend/lib/api/client.ts
frontend/lib/api/contracts.ts
```

`client.ts` 负责 `fetch`、错误解析、`NEXT_PUBLIC_API_BASE_URL`、query 参数拼接。`contracts.ts` 放前端使用的 TypeScript 类型，优先按当前响应字段做宽松类型，不要过早强约束后端内部结构。

## 6. 页面信息架构

沿用当前产品含义，采用 `dashboard-3` 的 sidebar、header、card、table、chart 视觉体系。

### 6.1 路由

```text
/login
/                         系统总览
/database                 水质综合数据库
/upload                   数据上传
/preprocess               数据预处理
/visualization            数据可视化
/prediction               透明度预测与致因诊断
```

导出到 `/ui` 后，对应访问路径：

```text
/ui/login
/ui/
/ui/database
/ui/upload
/ui/preprocess
/ui/visualization
/ui/prediction
```

如需兼容旧路径，可在 FastAPI 增加轻量重定向：

```text
/ui/login.html -> /ui/login
/ui/index.html -> /ui/
/ui/database.html -> /ui/database
/ui/upload.html -> /ui/upload
/ui/preprocess.html -> /ui/preprocess
/ui/visualization.html -> /ui/visualization
/ui/prediction.html -> /ui/prediction
```

### 6.2 导航命名

中文默认：

- 系统总览
- 水质综合数据库
- 数据上传
- 数据预处理
- 数据可视化
- 透明度预测与致因诊断

英文：

- Overview
- Water Quality Database
- Data Upload
- Preprocessing
- Visualization
- Prediction & Diagnosis

### 6.3 组件映射

从模板迁入并改造：

| 模板组件 | WaterExpert 用法 |
| --- | --- |
| `components/dashboard/sidebar.tsx` | 改成产品导航、站点范围、语言切换入口、退出登录 |
| `components/dashboard/header.tsx` | 改成页面标题、更新时间、刷新、导出报告、主题切换 |
| `components/dashboard/stats-cards.tsx` | 改成模型指标、站点样本、高优先日期、场景类别 |
| `components/dashboard/financial-flow-chart.tsx` | 改成浊度/清澈度实测预测曲线 |
| `components/dashboard/employees-table.tsx` | 改成数据库记录、任务列表、阈值表、Sobol 表等通用表格 |
| `components/dashboard/alert-banner.tsx` | 改成科学 guardrails、接口错误、运行态警示 |
| `components/ui/*` | 保留为基础 UI 组件库 |
| `store/dashboard-store.ts` | 改成 `app-store.ts`，存储主题、语言、活跃任务、布局密度、用户 session |

建议新增领域组件：

```text
frontend/components/waterexpert/
├── guardrail-banner.tsx
├── metric-cards.tsx
├── prediction-chart.tsx
├── scenario-feed.tsx
├── driver-diagnosis.tsx
├── threshold-browser.tsx
├── boundary-summary.tsx
├── report-export-menu.tsx
├── job-runner-panel.tsx
└── data-table.tsx
```

## 7. 中英双语方案

默认语言必须是中文。英文作为可切换语言存在。

推荐自维护轻量 i18n，不引入复杂路由级国际化：

```text
frontend/lib/i18n/
├── messages.ts
├── provider.tsx
└── use-t.ts
```

语言状态：

- 默认：`zh-CN`
- 可选：`en-US`
- 存储：`localStorage["waterexpert.locale"]`
- 切换入口：header 右侧或 sidebar footer 的下拉菜单

所有界面固定文案必须通过字典取值。不要在组件里直接写英文模板文案。

动态业务标签要做集中翻译：

```text
external_input -> 外源输入 / External Input
internal_release -> 内源释放 / Internal Release
algal_dominant -> 藻类主导 / Algal Dominant
chronic_composite -> 复合慢性压力 / Chronic Composite
high -> 高风险 / High Risk
heightened -> 偏高风险 / Heightened Risk
watch -> 关注 / Watch
```

科学 guardrails 的中文文案必须默认可见，英文切换时提供对应翻译。不要删掉 guardrails。

## 8. 功能迁移清单

### 8.1 登录

- 用模板视觉重做 `/login`。
- 调用 `GET /api/v1/auth/hint` 显示 demo 提示。
- 调用 `POST /api/v1/auth/login` 登录。
- session 可先沿用 localStorage，后续再接正式权限。
- 登录后进入 `/`。

### 8.2 系统总览

- 加载 `meta`、`dashboard`、`predictions`、`scenario-triage`、`realtime-validation`。
- 展示最佳模型、清澈度模型、高优先日期数、场景类别数。
- 展示吴淞口站点基础信息。
- 展示高优先事件 feed。
- 展示小型预测曲线。
- 展示 guardrails。

### 8.3 数据库

- 加载数据库摘要和站点列表。
- 支持站点、关键词、日期、limit 查询。
- 用模板 table 风格替代旧表格。
- 保留空状态、加载状态、错误状态。

### 8.4 上传与导入

- 支持浏览器文件上传到 `POST /api/v1/data/upload`。
- 支持本地路径导入到 `POST /api/v1/data/import`。
- 展示 `GET /api/v1/data/imports` 的导入记录。
- 对文件类型、站点编号、日尺度范围给出中文表单标签。

### 8.5 预处理

- 加载 `GET /api/v1/preprocess/summary`。
- 展示缺失值、异常值、行数、字段标准化摘要。
- 当前是原型摘要页，不要伪装成完整 ETL 编排平台。

### 8.6 可视化

- 加载 `GET /api/v1/visualization/summary`。
- 指标选择用 select。
- 趋势图用 Recharts。
- 保留相关性、范围、近期序列等当前页面能力。

### 8.7 预测与诊断

- 加载 predictions、diagnostics、scenario-triage、thresholds、boundary、playbook、sensitivity、realtime-validation。
- 顶部保留模型选择和任务产物视图选择。
- 任务创建表单继续支持 `inference` 与 `full_pipeline`。
- 运行中任务必须轮询 `GET /api/v1/prediction-jobs/{job_id}`。
- 图表、诊断、阈值、边界、响应建议可以继续用 tabs，但视觉改成模板风格。

### 8.8 报告导出

- 在 header 或页面动作区提供导出按钮。
- 调用 `POST /api/v1/report/export?format=...`。
- 根据 `download_url` 触发下载。
- 支持当前后端已有的 html、md、json、pdf。

## 9. 视觉迁移原则

- 保留 `dashboard-3` 的整体骨架：左侧 sidebar、顶部 header、内容滚动区、紧凑卡片、表格和图表。
- 移除模板中的 HR/Payroll/Employees 等业务概念。
- 不做营销式首页，第一屏直接是系统总览和可操作入口。
- 控件使用模板已有 button、select、dropdown、table、card、badge、tooltip。
- 图表优先用 Recharts，避免继续手写 SVG 路径。
- 页面应偏工作台风格：密度适中、信息可扫描、中文标签清晰。
- 不使用大面积单一蓝紫渐变，不保留模板里与 WaterExpert 无关的升级卡片。

## 10. 淘汰旧前端的执行步骤

建议按这个顺序执行，避免功能丢失：

1. 将 `vendor/square-ui/templates-baseui/dashboard-3` 的文件复制到临时工作区外检查依赖。
2. 清空旧 `frontend/` 的 HTML/CSS/JS 文件，保留必要图片资产。
3. 把模板的 `app/`、`components/`、`hooks/`、`lib/`、`store/`、`public/`、配置文件迁入 `frontend/`。
4. 删除模板业务 mock：`mock-data/employees.ts` 和 HR 相关组件内容。
5. 新增 WaterExpert API client、i18n、session store、领域组件。
6. 按页面逐个迁移功能，先总览和登录，再数据库/上传/预处理/可视化，最后预测诊断。
7. 调整 FastAPI 静态挂载到 `frontend/out`。
8. 更新 README、架构文档、运行说明和测试。
9. 确认旧路径重定向可用后，删除旧静态测试或改写为 Next 构建产物测试。

## 11. 验收标准

迁移完成后至少满足：

- `cd frontend && pnpm install && pnpm build` 成功。
- FastAPI 后端可启动，`GET /healthz` 返回 ok。
- 开发态 Next 能通过 `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 pnpm dev` 访问所有页面。
- 交付态 FastAPI 能通过 `/ui` 访问新前端。
- 中文是默认界面语言。
- 切换英文后导航、按钮、表格标题、状态标签、guardrails 均变为英文。
- 登录、刷新、报告导出、模型切换、阈值筛选、任务创建、任务轮询均可用。
- 当前现有功能不减少：数据库、上传、预处理、可视化、预测、诊断、场景、阈值、边界、敏感性、报告导出都能从界面访问。
- 不改动算法事实边界，不新增“物理临界阈值”“治理验证控制策略”等过度承诺文案。

## 12. 推荐测试更新

后端测试继续保留：

```bash
python -m pytest tests/backend
```

前端静态测试需要从“检查 HTML 文件 charset”改为：

- 检查 `frontend/package.json` 存在。
- 检查 `frontend/app/layout.tsx` 默认语言或 i18n provider 存在。
- 检查 `frontend/lib/i18n/messages.ts` 同时包含 `zh-CN` 与 `en-US`。
- 检查 `frontend/out` 构建后存在入口文件。

建议新增：

```bash
cd frontend
pnpm lint
pnpm build
```

如果环境允许，再加 Playwright smoke：

- `/ui/login` 能打开。
- 登录后进入 `/ui/`。
- sidebar 出现中文导航。
- 切换英文后导航出现英文。
- `/ui/prediction` 图表区域非空。

## 13. 下一位助手的最短执行路径

1. 先读 `AGENTS.md` 指定的五份文档。
2. 读本文件。
3. 检查 `vendor/square-ui/templates-baseui/dashboard-3`。
4. 备份旧 `frontend/` 功能映射，不保留旧视觉实现。
5. 用模板替换 `frontend/`，但目录名仍为 `frontend`。
6. 写 API client 和 i18n。
7. 逐页迁移当前功能。
8. 修改 FastAPI `/ui` 挂载和根路由。
9. 更新 README、架构文档和运行说明。
10. 跑后端测试、前端 lint/build，启动本地服务验证。

这份方案的核心判断是：`dashboard-3` 是视觉和组件基座，`WaterExpert` 的业务、算法、接口和科学边界仍然是主线。
