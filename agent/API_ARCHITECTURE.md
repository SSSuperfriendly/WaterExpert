# Web API 架构设计与集成指南

## 概述

本文档描述 Water AI REST API 的架构设计，以及如何与现有多智能体系统集成。重点是**模块化、可扩展**的设计，支持后续的优化和改进。

## 整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                          客户端层（前端/移动/第三方）               │
├─────────────────────────────────────────────────────────────────────┤
│  ▲                                                                   │
│  │ HTTP/REST                                                         │
│  ▼                                                                   │
├─────────────────────────────────────────────────────────────────────┤
│                   API 层（FastAPI 服务器）                          │
│                                                                     │
│  路由层                                                             │
│  ├─ POST   /api/strategy      ┐                                    │
│  ├─ GET    /api/strategy/{id} ├─→ 任务调度（JobManager）         │
│  ├─ GET    /api/jobs          ┘                                    │
│  ├─ GET    /api/health                                             │
│  ├─ GET    /api/status                                             │
│  ├─ GET    /api/scenarios                                          │
│  └─ ...                                                             │
├─────────────────────────────────────────────────────────────────────┤
│           业务逻辑层（Orchestrator + 多智能体系统）                 │
│                                                                     │
│  ┌─ Orchestrator ─────────────────────────────────────────────┐   │
│  │                                                             │   │
│  │  Stage 1: Diagnosis                                         │   │
│  │  ├─ MSCIMAgent        (✓ 可优化: 模型更新)                  │   │
│  │  ├─ CMFBEAgent        (✓ 可优化: 参数调优)                  │   │
│  │  └─ KBAgent           (✓ 可优化: 知识库扩展)                │   │
│  │                                                             │   │
│  │  Stage 2: Planning                                          │   │
│  │  └─ AquaTurbGPTAgent  (✓ 可优化: DeepSeek 参数)             │   │
│  │                                                             │   │
│  │  Stage 3: Execution                                         │   │
│  │  └─ RL-TGRRAgent      (✓ 可优化: 策略更新、模型重训练)      │   │
│  │                                                             │   │
│  │  Stage 4: Safety                                            │   │
│  │  └─ SafetyAgent       (✓ 可优化: 约束条件)                  │   │
│  │                                                             │   │
│  │  Stage 5: Metrics                                           │   │
│  │  └─ KPICalculator     (✓ 可优化: 权重调整)                  │   │
│  │                                                             │   │
│  │  Stage 6: Report                                            │   │
│  │  └─ ReportGenerator   (✓ 可优化: 报告格式)                  │   │
│  │                                                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│                      数据层（Data Loader）                          │
│                                                                     │
│  ├─ CSV 加载器  (19,186 行历史数据)                               │
│  ├─ 实时数据接口 (✓ 可扩展: 数据库)                              │
│  └─ 缓存层      (✓ 可优化: Redis)                                │
└─────────────────────────────────────────────────────────────────────┘
```

## 核心设计原则

### 1. 解耦架构

**API 层与后端系统完全解耦**：
- API 层：处理 HTTP 请求/响应
- 业务逻辑层：独立的 Orchestrator 和代理系统
- 数据层：可插拔的数据源

**优势**：
- API 可以独立扩展（多进程、分布式部署）
- 后端优化无需修改 API 代码
- 易于单元测试

### 2. 异步任务设计

```python
# 用户请求流程
POST /api/strategy
  ├─ 1. 验证请求
  ├─ 2. 创建任务（JobManager）
  ├─ 3. 立即返回 job_id（status: queued）
  └─ 4. 后台执行
      ├─ 初始化代理
      ├─ 调用 Orchestrator
      ├─ 生成报告
      └─ 更新 job_id 的结果

# 客户端轮询
GET /api/strategy/{job_id}
  ├─ status: queued      → 等待
  ├─ status: running     → 处理中
  ├─ status: completed   → 返回结果
  └─ status: failed      → 返回错误
```

**优势**：
- 支持长期运行的任务
- 不会超时
- 支持并发请求

### 3. 参数化设计

所有配置都通过 API 参数传递，无需修改代码：

```json
{
  "scenario": "s1_external_input",      // 可选择任何场景
  "state": {...},                        // 动态输入数据
  "episodes": 5,                         // 可调整运行次数
  "backend": "api"                       // 支持多种后端
}
```

## 模块化设计

### API 层模块

```
src/water_ai/api/
├── main.py                # FastAPI 应用主文件
├── schemas.py             # Pydantic 数据模型（输入/输出）
├── job_manager.py         # 任务管理和状态跟踪
└── routes/
    ├── __init__.py
    ├── health.py          # 健康检查端点
    ├── strategy.py        # 策略生成端点
    └── scenarios.py       # 场景信息端点
```

**每个模块的责任**：
- `main.py`: 创建 FastAPI 应用，配置中间件、异常处理
- `schemas.py`: 定义所有 API 输入/输出数据结构
- `job_manager.py`: 管理后台任务的生命周期
- `routes/*.py`: 实现具体的 HTTP 端点

### 业务逻辑层模块（保持现状）

```
src/water_ai/
├── data/
│   └── loader.py          # 数据加载（可扩展为数据库）
├── agents/                # 6 个多智能体
├── orchestrator/          # 6 阶段编排
├── visualization/         # DeepSeek 可视化
└── llm/                   # 大模型集成
```

## 如何支持后续优化

### 优化方向 1：MSCIMAgent 模型更新

**当前**：使用预训练的浊度预测模型

**优化流程**：
```python
# 1. 在 job_manager.py 中添加模型版本
class JobManager:
    def create_job(..., model_version="v1.0"):
        job["model_version"] = model_version
        
# 2. 在 strategy.py 中使用版本
response = requests.post("/api/strategy", json={
    "scenario": "s1_external_input",
    "state": {...},
    "model_version": "v2.0"  # 新的改进版本
})

# 3. Agent 加载指定版本的模型
agent = MSCIMAgent(model_version=version)
```

### 优化方向 2：RL-TGRR 策略更新

**当前**：使用预训练的 SAC 策略

**优化流程**：
```python
# 1. 在 AquaTurbGPTAgent 中添加策略选择
agent = AquaTurbGPTAgent(
    strategy_version="v1.0",  # 当前
    # 可升级到 v2.0, v3.0
)

# 2. API 中暴露策略版本选择
response = requests.post("/api/strategy", json={
    "strategy_version": "v2.0"  # 使用新的学习策略
})

# 3. 后台加载对应版本
rl_agent = RLTGRRAgent(strategy_version=version)
```

### 优化方向 3：DeepSeek 参数调优

**当前**：固定的推理参数

**优化流程**：
```python
# 1. 在 schemas.py 中添加参数
class StrategyRequest(BaseModel):
    deepseek_temperature: float = 0.7
    deepseek_top_p: float = 0.95
    max_reasoning_tokens: int = 8000

# 2. API 传递给代理
agent = AquaTurbGPTAgent(
    config={
        "deepseek": {
            "temperature": request.deepseek_temperature,
            "top_p": request.deepseek_top_p,
            "max_reasoning_tokens": request.max_reasoning_tokens
        }
    }
)
```

### 优化方向 4：KPI 权重调整

**当前**：硬编码的权重

**优化流程**：
```python
# 1. 在 schemas.py 中添加权重配置
class StrategyRequest(BaseModel):
    kpi_weights: dict = {
        "turbidity_reduction": 0.4,
        "cost": 0.3,
        "stability": 0.3
    }

# 2. 传递给 KPI 计算器
metrics = kpi_calc.compute(
    action=result["safe_action"],
    state=state,
    weights=request.kpi_weights  # 动态权重
)
```

## 扩展性设计

### 1. 添加新的端点

```python
# 在 src/water_ai/api/routes/new_feature.py 中
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["new_feature"])

@router.post("/new-endpoint")
async def new_endpoint(request: NewRequest) -> NewResponse:
    # 实现
    pass

# 在 src/water_ai/api/main.py 中注册
from .routes import new_feature
app.include_router(new_feature.router)
```

### 2. 集成数据库

```python
# 修改 job_manager.py，添加数据库后端
class JobManager:
    def __init__(self, backend="memory"):  # 或 "postgres"
        if backend == "postgres":
            self.store = PostgresStore()
        else:
            self.store = MemoryStore()
```

### 3. 添加认证

```python
# 在 main.py 中添加中间件
from fastapi.security import HTTPBearer
from fastapi import Depends

security = HTTPBearer()

@app.post("/api/strategy", dependencies=[Depends(security)])
async def generate_strategy(...):
    # 需要有效的令牌
    pass
```

### 4. 支持批量请求

```python
# 在 routes/strategy.py 中添加
@router.post("/batch-strategy", response_model=list[StrategyResponse])
async def batch_strategy(requests: list[StrategyRequest]):
    job_ids = []
    for req in requests:
        job_id = job_manager.create_job(...)
        job_ids.append(job_id)
    return [StrategyResponse(job_id=jid, status="queued") for jid in job_ids]
```

## 集成检查清单

### ✅ 已完成

- [x] 数据模型（schemas.py）
- [x] 任务管理（job_manager.py）
- [x] 路由实现（routes/）
- [x] FastAPI 应用（main.py）
- [x] API 文档（API_GUIDE.md）
- [x] 测试脚本（test_api.py）
- [x] 启动脚本（run_api_server.py）

### ⏭️ 后续优化

- [ ] 数据库集成（PostgreSQL）
- [ ] 缓存层（Redis）
- [ ] 认证系统（JWT）
- [ ] 监控和日志（Prometheus/ELK）
- [ ] WebSocket 支持（实时进度）
- [ ] 移动端 SDK
- [ ] Docker 容器化
- [ ] Kubernetes 部署

## 性能指标

### 当前系统

| 指标 | 值 |
|------|-----|
| API 响应时间 | <100ms |
| 后台任务时间 | 2-5s（取决于 DeepSeek） |
| 并发请求处理 | 单进程多请求 |
| 任务队列 | 内存存储 |

### 生产部署建议

| 指标 | 目标 |
|------|-----|
| QPS | 100+ (水平扩展) |
| 平均延迟 | <500ms |
| P95 延迟 | <2s |
| 可用性 | 99.9% |
| 任务持久化 | PostgreSQL + 消息队列 |

## 与现有系统的兼容性

### ✅ 完全兼容

现有的 CLI 和 Python 脚本保持不变：

```bash
# CLI 仍然可用
PYTHONPATH=src:$PYTHONPATH python scripts/run_closed_loop.py --scenario 1

# Python 脚本仍然可用
from src.water_ai.orchestrator.coordinator import Orchestrator
orchestrator = Orchestrator()
```

### 共享代码

API 直接使用现有的代理和编排器：

```python
# api/routes/strategy.py
from ..agents import MSCIMAgent, AquaTurbGPTAgent, ...
from ..orchestrator.coordinator import Orchestrator
from ..orchestrator.report_generator import ReportGenerator

# 完全相同的逻辑，只是通过 HTTP 接口暴露
```

## 迁移路径

### 阶段 1：API 基础（当前 ✓）
- ✓ FastAPI 服务
- ✓ 基本路由
- ✓ 任务管理（内存）

### 阶段 2：数据库集成（P3）
- [ ] PostgreSQL 集成
- [ ] 数据持久化
- [ ] 历史查询

### 阶段 3：分布式系统（P4）
- [ ] Celery + Redis
- [ ] 消息队列
- [ ] 水平扩展

### 阶段 4：高级特性（P5）
- [ ] WebSocket 实时更新
- [ ] 用户认证
- [ ] 监控和告警
- [ ] Kubernetes 部署

---

**架构设计完成日期**：2026-05-29  
**最后更新**：2026-05-29  
**维护者**：WaterExpert Team

## 快速参考

### 启动 API 服务
```bash
PYTHONPATH=src:$PYTHONPATH python scripts/run_api_server.py --host 0.0.0.0 --port 8000
```

### 测试 API
```bash
python test_api.py
```

### 查看文档
- API 文档: [API_GUIDE.md](API_GUIDE.md)
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 关键文件
- API 入口: `src/water_ai/api/main.py`
- 数据模型: `src/water_ai/api/schemas.py`
- 任务管理: `src/water_ai/api/job_manager.py`
- 路由: `src/water_ai/api/routes/`
