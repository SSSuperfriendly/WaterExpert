# WaterExpert Software — 产品经理前端设计反馈报告

> **审计日期**：2026-06-25  
> **审计范围**：全部 6 个前端页面 + 18 个 JS 模块 + 1758 行 CSS  
> **审计人角色**：产品经理（参考 GPT、Figma、Vercel 等顶级产品设计标准）  
> **目标受众**：前端开发团队  

---

## 总体评价

产品数据层扎实，API 设计清晰，后端返回的数据结构丰富且有领域深度。前端在**信息架构和功能完整性**上达到了可用水平，但在**视觉设计精致度、交互细节、信息降噪和用户引导**四个维度上，距离"让人愿意推荐给同行使用的专业产品"还有显著差距。

以下按**严重程度（P0 > P1 > P2 > P3）** 组织，每条附具体改进建议。

---

## P0 — 阻碍核心体验，必须立刻修复

### P0-1. 登录页面硬编码了明文账号密码

**文件**: [frontend/login.html:30-34](frontend/login.html#L30-L34)

```html
<input id="loginUsername" type="text" value="2510709" ...>
<input id="loginPassword" type="password" value="AI4S666" ...>
```

**问题**: 任何人打开登录页面就能看到预填的账号密码。这在评审演示时是便利，但作为正式产品交付物，这违反基本安全常识。即使这是一个 Demo 系统，这种做法也会让评审专家对团队的专业性产生负面第一印象。

**建议**:  
- 移除 `value` 属性中的硬编码值  
- 保留 `/api/v1/auth/hint` 接口在页面上展示提示（已经在做），但不应直接填充到表单  
- 如果确实需要演示便利，加一个"一键填充演示账号"按钮，通过 JS 动态填充

---

### P0-2. 登录失败后没有任何视觉反馈过渡

**文件**: [frontend/js/login.js:22-23](frontend/js/login.js#L22-L23)

**问题**: 登录失败时 `loginError` 突然出现红色文字，没有过渡动画。成功时 `window.location.replace` 直接跳转，页面瞬间消失——没有 loading spinner、没有"登录成功，正在跳转"的过渡态。用户不知道系统是在处理中还是卡死了。

**建议**:  
- 点击登录后按钮进入 loading 态（显示 spinner + disabled）  
- 成功时加 300ms 过渡动画再跳转  
- 失败时 `loginError` 加 fade-in 动画  
- 输入框在错误时应有红色边框高亮

---

### P0-3. 所有页面的数据加载没有骨架屏或 Loading 态

**覆盖范围**: 全部 6 个页面

**问题**: 用户进入首页/数据库页/预测页时，看到的是"空壳"——大片的空白 panel，然后数据突然 pop-in。这不是 2024 年产品的标准体验。

**建议**:  
- 每个数据驱动的区域（stats-grid、table-wrap、chart SVG）在初次加载时展示 skeleton/shimmer 占位  
- 数据到达后做 200ms fade-in 过渡  
- 表头和 panel 标题可以立即渲染（它们不依赖异步数据），只有内容区域需要骨架占位

---

### P0-4. 缺少 404/500 错误页面

**问题**: 访问不存在的路由（如 `/ui/nonexistent.html`）时浏览器显示默认错误，没有任何品牌化错误页面。

**建议**:  
- 创建一个 `404.html`（可与登录页共享布局）  
- 后端 FastAPI 配置自定义 404/500 handler，重定向或返回品牌化错误页  

---

## P1 — 显著影响用户体验，应在本迭代修复

### P1-1. 导航信息架构混乱——"首页"不是 Dashboard

**文件**: [frontend/index.html](frontend/index.html)

**问题**:  
- 左侧导航第一个条目叫"首页"，但 URL 是 `/ui/index.html`，页面实际上是 Dashboard  
- 顶部 `<h1>` 写的是"首页"，但内容全是系统概览、预测快照、风险解释——这是典型的 Dashboard  
- 从数据库页、上传页回到"首页"时，用户看到的是完全不同的信息密度，认知跳跃大

**建议**:  
- 将"首页"重命名为"系统总览"或"Dashboard"  
- `<h1>` 改为"系统总览"  
- 或者，做一个真正的 Landing 首页（项目介绍、快速入口），把当前 index.html 的内容移到 `/ui/dashboard.html`

---

### P1-2. 预测页面的 Tab 切换无 URL 状态持久化

**文件**: [frontend/prediction.html:126-130](frontend/prediction.html#L126-L130)

```html
<button class="analysis-tab is-active" data-analysis-tab="diagnosis">诊断结论</button>
<button class="analysis-tab" data-analysis-tab="thresholds">阈值与边界</button>
<button class="analysis-tab" data-analysis-tab="response">分诊与行动</button>
```

**问题**: 用户在"阈值与边界"Tab 下刷新浏览器，Tab 重置回"诊断结论"。这导致分享链接时无法精确定位到具体视图。

**建议**:  
- Tab 切换时更新 `URLSearchParams`（如 `?tab=thresholds`）  
- 页面初始化时从 URL 读取并激活对应 Tab  
- 或用 `history.replaceState` 更新 URL

---

### P1-3. 数据可视化图表缺少交互

**文件**: [frontend/js/chart.js](frontend/js/chart.js), [frontend/js/visualization.js](frontend/js/visualization.js)

**问题**:  
- 预测图表（predictionChart）和可视化图表（visualChart）都是静态 SVG，没有 tooltip  
- 用户 hover 到数据点上无法看到具体数值、日期  
- 没有缩放、没有十字准线（crosshair）  
- 图表底部只有 3 个日期标签，无法精确对应数据点

**建议**:  
- 在 SVG 数据点上添加 invisible hit areas + hover tooltip（原生 SVG `<title>` 或 JS 实现的 tooltip div）  
- 添加竖线 crosshair 跟随鼠标  
- 底部 x 轴标签增加到至少 5-6 个  
- 考虑引入轻量级图表库（如 uPlot、Observable Plot 或 ECharts）替代手写 SVG——当前手写 SVG 路径已经 130 行，后续加交互会更难维护

---

### P1-4. 暗色模式的颜色语义混乱

**文件**: [frontend/styles.css:32-55](frontend/styles.css#L32-L55)

**问题**:  
- 暗色模式下 `--success` 变成了 `#f2bc6a`（金黄色），`--predicted` 也变成了 `#f2bc6a`，`--warning` 也是 `#f2bc6a`——三个不同语义的变量映射到了同一个颜色  
- 绿色（success）在浅色模式是 `#1d7a76`（蓝绿），暗色变成了金色——用户对"成功/正常"的直觉色是绿色，暗色下用金色会让用户困惑  
- `--actual` 在浅色模式是蓝色，`--predicted` 是绿色，暗色下变成了蓝色 vs 金色——线图图例失去跨主题一致性

**建议**:  
- 暗色模式下保持颜色语义一致：success 用偏绿、warning 用偏橙、risk 用偏紫  
- 浅色和暗色的色相（hue）应保持一致，只调整亮度（lightness）和饱和度  

---

### P1-5. 数据库查询结果表格缺少分页

**文件**: [frontend/database.html](frontend/database.html), [frontend/js/database.js](frontend/js/database.js)

**问题**: API 返回 `matched_rows: 31099`，但前端 `limit` 写死为 240（前端 `database.js:83` 中 `params.set("limit", "240")`）。用户无法翻页查看第 241 条之后的数据，也没有"显示更多"按钮。

**建议**:  
- 添加分页控件（上一页/下一页 + 页码）  
- 或使用 Intersection Observer 做无限滚动  
- 至少展示"当前显示 240 / 共 31099 条"并附带翻页按钮  

---

### P1-6. 文件上传没有进度指示

**文件**: [frontend/upload.html](frontend/upload.html), [frontend/js/upload.js](frontend/js/upload.js)

**问题**: `handleUpload` 使用 `fetchJson` 做 POST，大文件上传时没有任何进度反馈。上传多个大 CSV 文件时，用户只能干等。

**建议**:  
- 使用 `XMLHttpRequest` + `progress` 事件显示上传进度条  
- 或者用 Fetch API + `ReadableStream` 分段读取  
- 至少在上传按钮点击后显示"正在上传，请稍候…"并禁用按钮  

---

## P2 — 体验打磨，应在下一迭代优先处理

### P2-1. 首页 Entry Cards 只链接到页面没有展示实时数据

**文件**: [frontend/index.html:67-71](frontend/index.html#L67-L71)

**问题**: 5 个 home-entry-card 是纯静态链接，没有携带任何实时摘要。例如"数据库查询"卡片可以显示"当前覆盖 23 个站点 · 31,103 条记录"，让用户在点击前就获得信息价值。

**建议**: 每个卡片动态展示 1-2 个关键数字（从已有 API 获取，数据已在页面其他地方加载）。

---

### P2-2. 缺少面包屑导航

**问题**: 用户深层操作时（如在预测页面切换到"阈值与边界" Tab），没有面包屑告知当前位置层级。页面只有左侧导航高亮和顶部标题。

**建议**: 在 toolbar 的 eyebrow 位置或标题上方加面包屑：`系统总览 > 透明度预测与致因诊断 > 阈值与边界`

---

### P2-3. 导出报告功能没有格式预览

**文件**: [frontend/js/export.js](frontend/js/export.js)

**问题**: 点击"导出报告"弹出一个 dialog 选择 HTML/Markdown/JSON/PDF，但没有任何预览。用户不知道导出内容长什么样。

**建议**:  
- 至少展示每种格式的文件大小估计  
- 对 HTML 格式提供一个"新窗口预览"链接  
- Dialog 中列明报告包含哪些 section  

---

### P2-4. 预处理页面的"建议"是静态文本

**文件**: [frontend/preprocess.html](frontend/preprocess.html), [frontend/js/preprocess.js](frontend/js/preprocess.js)

**问题**: `recommendations` 来自后端返回的字符串数组，前端原样渲染成 `<li>`。但这些建议缺少可操作的入口——例如"建议先处理异常值，再进行标准化"这条建议，用户看完不知道该怎么操作。

**建议**:  
- 将建议做成 actionable chips：点击"查看异常值"跳转到可视化页并预设该指标  
- 或者在建议旁边加问号 icon，hover 展示更多上下文  

---

### P2-5. 侧边栏折叠后丢失所有上下文

**文件**: [frontend/styles.css:382-386](frontend/styles.css#L382-L386)

**问题**: 折叠侧边栏后，所有文字隐藏，只保留图标编号（01-06）——但编号本身没有文字提示，用户需要记住顺序才能导航。hover 时也没有 tooltip。

**建议**:  
- 折叠态下给每个 side-link 加 `title` 属性（tooltip）  
- 或 hover 时在旁边浮出文字标签  

---

### P2-6. h1 字体过大且 line-height 过小

**文件**: [frontend/styles.css:450-454](frontend/styles.css#L450-L454)

```css
h1 {
  font-size: clamp(2rem, 4vw, 3rem);
  line-height: 0.96;   /* < 1！文字可能被裁切 */
  letter-spacing: -0.05em;
}
```

**问题**: `line-height: 0.96` 在中文环境下会导致文字顶部/底部被裁切（中文字形比拉丁字母高）。在大屏幕上 h1 可达 48px+，line-height < 1 会让多行标题严重重叠。

**建议**:  
- 中文标题 minimum line-height 设为 1.15  
- 如果用负 letter-spacing，需要相应增加 line-height 补偿  

---

### P2-7. 预测任务创建表单过于技术化

**文件**: [frontend/prediction.html:85-118](frontend/prediction.html#L85-L118)

**问题**:  
- 模式选择直接暴露 `inference` / `full_pipeline`，没有解释两者区别  
- 模型名 `cmfbe_stgcn`、`mscim`、`mscim_no_kg` 对领域用户不友好  
- "优先复用现有产物" checkbox 的后果不清晰

**建议**:  
- 模式改为 radio group + 每项附带一句话描述：  
  - "仅推理（inference）——使用已有模型参数快速预测"  
  - "完整流水线（full_pipeline）——重新训练模型并预测"  
- 模型名使用 display name + 简短说明（如 "CMFBE-ST-GCN（机制感知混合模型，推荐）")

---

### P2-8. 缺少键盘快捷键

**问题**: 没有任何键盘导航支持。专业工具类产品应至少支持：
- `Ctrl+K` / `Cmd+K` 打开命令面板
- `Esc` 关闭 Dialog
- 侧边栏导航可通过数字键 1-6 快速切换

---

### P2-9. 没有响应式设计的断点测试迹象

**文件**: [frontend/styles.css](frontend/styles.css)

**问题**: 尽管 CSS 使用了 `clamp()` 和 `minmax(0, 1fr)`，但整个样式表没有 `@media` 查询（除了 mobile-only 的 display:none 逻辑）。在 768px-1024px 的平板宽度下，5 列 home-entry-grid 会严重挤压，dashboard-detail-grid 也会塌陷。

**建议**:  
- 至少在 768px 和 1024px 两个断点测试并添加 `@media` 规则  
- home-entry-grid 在平板下改为 2-3 列  
- 预测页面的 analysis-section-grid 在窄屏下改为单列  

---

## P3 — 长期优化，可纳入 backlog

### P3-1. 色彩系统缺乏数据可视化语义

当前图表中 actual/predicted/risk 三条线靠颜色区分，但 risk 用的是虚线——对色盲用户不友好。建议增加：
- 线条上添加不同形状的标记点（圆圈/方块/三角）
- 或使用不同线宽+虚线组合（已部分实现，但 risk 线和其余线对比度不足）

### P3-2. 统计卡片缺少趋势指示

`stats-grid` 中的 stat-card 只显示 label + value，没有与上一周期的对比（如"浊度 R² 0.748 ↑ 0.02"）。如果 API 返回了历史值，可以展示微型趋势箭头。

### P3-3. 缺少浏览器 Tab 通知

当后台轮询的预测任务完成时，如果用户正在其他 Tab 浏览，完全不知道任务已完成。建议：
- 任务完成时更新 `<title>` 前缀为 `[完成] WaterExpert | ...`
- 使用 Notification API 发送桌面通知（需用户授权）

### P3-4. 侧边栏宽度拖拽功能隐藏太深

代码中有 `SIDEBAR_DRAG_THRESHOLD_PX` 常量，暗示侧边栏宽度可拖拽调整，但实际使用中用户很难发现这个功能。建议在侧边栏右边缘加一个可见的拖拽手柄（grab handle），hover 时高亮。

### P3-5. 缺少用户 onboarding / 引导

新用户进入系统后没有任何引导提示。建议：
- 首次访问展示一个 3-step 的 tooltip 引导（"从这里查看数据库 → 上传你的数据 → 运行预测"）
- 或在首页 hero 区域加一个"快速开始"步骤向导

### P3-6. 代码组织上 main.js 职责过重

[frontend/js/main.js](frontend/js/main.js) 同时服务于 `index.html` 和 `prediction.html` 两个页面，通过 DOM 元素存在性判断（`if (getElement("exportReportButton"))`）来分支执行。这会导致：
- 两个页面的代码互相耦合
- 页面特定的逻辑散落在条件分支中

建议拆分为 `main-dashboard.js` 和 `main-prediction.js`。

### P3-7. 没有单元测试或 E2E 测试

前端 18 个 JS 模块没有任何测试文件。作为科学软件，数据渲染的正确性需要保证。建议至少对核心渲染函数（`renderPredictionChart`、`renderOverview`、`renderDiagnosticsDetailed`）编写 snapshot 测试。

---

## 优先级矩阵

| 优先级 | 数量 | 建议修复时间 | 影响范围 |
|--------|------|-------------|----------|
| P0 | 4 项 | **本周内** | 安全 + 基本可用性 |
| P1 | 6 项 | **本迭代** | 核心用户体验 |
| P2 | 9 项 | **下一迭代** | 品质打磨 |
| P3 | 7 项 | **Backlog** | 长期竞争力 |

---

## 做得好的地方（正面反馈）

在批评之外，以下设计决策值得肯定：

1. **侧边栏设计系统**：01-06 编号体系 + active 指示条 + 渐变高亮，在同类科学软件中算得上用心，视觉层次清晰。
2. **暗色模式基础设施**：CSS 变量体系设计合理（`data-theme="dark"` 切换），覆盖了背景、表面、线条、阴影等关键 token。
3. **优雅降级策略**：每个渲染函数都有空数据保护（如 `renderMutedMessage`、`drawChartPlaceholder`），不会因为 API 返回空数组而白屏。
4. **任务轮询机制**：`createJobPoller` 的设计干净，自动检测任务完成并刷新产物视图。
5. **预测图表三线设计**：实际值 + 预测值 + 风险概率的三线叠加，信息密度高且合理。
6. **API 返回结构**：后端返回的数据已经包含了 `recommended_agent_queries` 和 `guardrails` 等面向 agent 的字段，展现了良好的架构前瞻性。

---
