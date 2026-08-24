# WaterExpert Software 环境方向快速上手

这份说明面向第一次接触仓库的环境、水务或交叉团队同学。目标不是二次开发，而是先把软件跑起来、看到界面、理解当前能看什么。

## 1. 获取最新代码

建议直接克隆当前产品分支，而不是默认主分支：

```powershell
git clone -b software/waterturbidity-app https://github.com/SSSuperfriendly/WaterExpert.git
cd WaterExpert
```

如果已经克隆过仓库，再执行：

```powershell
git checkout software/waterturbidity-app
git pull origin software/waterturbidity-app
```

## 2. 创建本地 Python 环境

仓库当前推荐使用项目根目录下的 `.ai4s` 虚拟环境。

**Windows（PowerShell）**

```powershell
python -m venv .ai4s
.\.ai4s\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

如果本机已经有 `.ai4s`，只需要激活并安装依赖：

```powershell
.\.ai4s\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux（Homebrew + uv）**

```bash
brew install uv
uv python install 3.12
uv venv .ai4s --python 3.12
uv pip install --python .ai4s/bin/python -r requirements.txt
```

以后直接运行 `./scripts/dev/start_local.sh` 即可自动完成「建环境 + 装依赖 + 启动」三步。

## 3. 启动软件

前端是 Next.js 应用，需要先构建出静态产物（`frontend/out/`）后，后端才能在 `/ui` 下提供页面。构建需要 Node.js 与 npm：

```powershell
cd frontend
npm install
npm run build
cd ..
```

然后启动后端：

```powershell
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

浏览器打开：

- `http://127.0.0.1:8000/`（会自动跳转到 `/ui/login`）

健康检查接口：

- `http://127.0.0.1:8000/healthz`

如果看到 `{"status":"ok"}`，说明后端已正常读取当前仓库内置产物。

## 4. 进入后先看什么

默认登录账号：用户名 `2510709`，密码 `AI4S666`（登录页有「一键填入」按钮）。

建议按下面顺序看：

1. `系统总览`
2. `可视化分析`
3. `浊度/清澈度预测`
4. `致浑因子诊断`
5. `经验阈值检索`
6. `边界变化代理识别`
7. `场景 Triage` 与 `响应 Playbook`
8. 右上角 `导出报告`

当前软件已经支持：

- 读取已有研究产物
- 展示预测结果与关键诊断
- 展示场景 triage
- 展示经验阈值检索
- 展示边界识别摘要
- 展示 Sobol 敏感性与反事实原型
- 展示实时验证摘要
- 导出 HTML、Markdown、JSON、PDF 报告
- 界面默认简体中文，可在侧边栏切换英文

## 5. 当前展示的是什么

当前仓库不是从零训练模型，而是直接复用了 `WaterExpert` 研究原型代码、脚本和已产生产物，在其上封装出软件层。

当前展示的核心是：

- 吴淞口单站点多模态日尺度原型
- 预测与诊断一体化查看
- 研究产物的软件化读取与报告化输出

## 6. 必须理解的边界

为了避免误解，展示时请始终带上这几条：

- 当前系统是吴淞口单站点多模态日尺度原型，不是全流域多站点生产系统。
- 阈值是当前原型中的经验阈值，不是二维水动力物理控制阈值。
- 边界标签是 raster 派生代理标签，不是人工治理边界标注。
- 响应建议是经验型 playbook，不是强化学习控制策略。

## 7. 如果只想快速验证软件是否可用

激活环境后执行：

```powershell
python -m pytest -q
```

如果测试通过，再启动：

```powershell
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

## 8. 如何查看导出报告

在界面右上角使用导出功能，选择格式后下载即可。

报告会基于当前查看的数据生成，支持：

- `HTML`
- `Markdown`
- `JSON`
- `PDF`

运行时导出的文件会写到本地 `var/` 目录下，这些内容不会提交到仓库。

## 9. 如果要看代码入口

主要目录：

- `backend/`: FastAPI 后端服务
- `frontend/`: Next.js 前端（构建产物在 `frontend/out/`，由后端在 `/ui` 下提供）
- `src/water_ai/`: 研究算法与运行时基础
- `outputs/`: 当前仓库已提交的基线研究产物
- `var/`: 本地运行状态、job 产物和导出报告

后端入口：

- `backend/app/main.py`

## 10. 常见问题

### 为什么 clone 下来就能看到结果

因为仓库已经提交了当前原型所需的基线 `outputs/` 产物，软件优先读取这些结果做展示，而不是强制重新训练。

### 为什么不是先跑训练

当前软件展示的重点是软件化封装、结果可视化、诊断与报告导出，不是现场重训练。

### 如果页面打不开

先检查：

```powershell
http://127.0.0.1:8000/healthz
```

如果健康检查失败，通常是依赖未装完整，或者当前目录不在仓库根目录。
