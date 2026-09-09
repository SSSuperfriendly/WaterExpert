# Water AI REST API 完整指南

## 概述

Water AI API 是一个 **RESTful Web 服务**，允许用户通过 HTTP 请求调用多智能体水质治理系统。支持实时策略生成、后台任务处理、异步结果查询。

## 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     前端应用（React/Vue/移动端）            │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTP/REST
┌────────────────────▼────────────────────────────────────────┐
│                 FastAPI Web 服务器 (localhost:8000)          │
├─────────────────────────────────────────────────────────────┤
│  路由层                                                      │
│  ├─ POST   /api/strategy          (策略生成)               │
│  ├─ GET    /api/strategy/{id}     (查询结果)               │
│  ├─ GET    /api/health            (健康检查)               │
│  ├─ GET    /api/scenarios         (场景列表)               │
│  └─ GET    /api/jobs              (任务列表)               │
├─────────────────────────────────────────────────────────────┤
│  业务逻辑层                                                  │
│  └─ Orchestrator (6 阶段编排)                               │
├─────────────────────────────────────────────────────────────┤
│  多智能体系统                                                │
│  ├─ MSCIMAgent        (浊度预测)                            │
│  ├─ CMFBEAgent        (过程分解)                            │
│  ├─ KnowledgeBaseAgent (技术库)                            │
│  ├─ AquaTurbGPTAgent  (DeepSeek 推理) ← 可优化              │
│  ├─ RLTGRRAgent       (低层控制)     ← 可优化              │
│  └─ SafetyAgent       (约束检查)                            │
└─────────────────────────────────────────────────────────────┘
```

## 快速启动

### 1. 安装依赖

```bash
pip install -r requirements-api.txt
```

### 2. 设置 DeepSeek API 密钥

```bash
export DEEPSEEK_API_KEY="sk-your-api-key-here"
```

### 3. 启动 API 服务器

```bash
PYTHONPATH=src:$PYTHONPATH python scripts/run_api_server.py --host 0.0.0.0 --port 8000
```

输出：
```
🚀 Starting Water AI API Server
   Host: 0.0.0.0
   Port: 8000
   Reload: False

📖 API Documentation: http://0.0.0.0:8000/docs
📊 ReDoc: http://0.0.0.0:8000/redoc
```

### 4. 在浏览器中打开

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API 端点详解

### 1. 健康检查

#### GET /api/health

检查 API 和系统组件状态。

**请求**：
```bash
curl http://localhost:8000/api/health
```

**响应** (200 OK)：
```json
{
  "status": "healthy",
  "timestamp": "2026-05-29T12:00:00",
  "agents": {
    "MSCIM": "ready",
    "CMFBE": "ready",
    "KnowledgeBase": "ready",
    "AquaTurbGPT": "ready",
    "RL-TGRR": "ready",
    "Safety": "ready"
  },
  "database": "not_configured",
  "deepseek": "configured"
}
```

---

### 2. 系统状态

#### GET /api/status

获取详细的系统状态信息。

**请求**：
```bash
curl http://localhost:8000/api/status
```

**响应** (200 OK)：
```json
{
  "version": "1.0.0",
  "status": "healthy",
  "agents": [
    {
      "name": "MSCIM",
      "type": "specialist",
      "status": "ready",
      "version": "1.0.0",
      "last_used": "2026-05-29T12:00:00"
    },
    ...
  ],
  "data_loader": {
    "status": "ready",
    "total_rows": 19186,
    "date_range": {
      "start": "2020-12-17",
      "end": "2025-10-31"
    }
  },
  "deepseek_backend": "api",
  "timestamp": "2026-05-29T12:00:00"
}
```

---

### 3. 列出场景

#### GET /api/scenarios

获取所有可用的水质治理场景。

**请求**：
```bash
curl http://localhost:8000/api/scenarios
```

**响应** (200 OK)：
```json
[
  {
    "code": "S1",
    "name": "External Input Type",
    "description": "外源输入型 - 降水增加导致通过支流输入大量悬浮物和营养盐",
    "characteristics": [
      "3-day cumulative rainfall > 36 mm",
      "High upstream erosion",
      "Suspended sediment influx",
      "Turbidity spike within 24h"
    ],
    "recommended_actions": [
      "Increase water release for flushing",
      "Enhanced sedimentation",
      "Monitor upstream stations",
      "Adjust flow control parameters"
    ]
  },
  ...
]
```

---

### 4. 获取单个场景

#### GET /api/scenarios/{scenario_code}

获取特定场景的详细信息。

**请求**：
```bash
curl http://localhost:8000/api/scenarios/s1_external_input
```

**响应** (200 OK)：
```json
{
  "code": "S1",
  "name": "External Input Type",
  "description": "外源输入型 - ...",
  "characteristics": [...],
  "recommended_actions": [...]
}
```

---

### 5. 生成策略（核心功能）

#### POST /api/strategy

生成水质治理策略。**这是异步操作** — 立即返回 job_id，实际处理在后台进行。

**请求体** (Content-Type: application/json)：
```json
{
  "scenario": "s1_external_input",
  "state": {
    "date": "2025-10-31",
    "turbidity": 25.5,
    "flow_rate": 28.5,
    "temperature": 18.2,
    "ph": 7.5,
    "dissolved_oxygen": 8.3,
    "chlorophyll_a": 5.2,
    "rainfall_3d": 45.3,
    "rainfall_7d": 120.5
  },
  "episodes": 1,
  "backend": "api",
  "request_id": "optional-external-id"
}
```

**响应** (200 OK)：
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "scenario": "s1_external_input",
  "created_at": "2026-05-29T12:00:00",
  "message": "Strategy generation queued. Job ID: 550e8400-e29b-41d4-a716-446655440000"
}
```

**cURL 示例**：
```bash
curl -X POST http://localhost:8000/api/strategy \
  -H "Content-Type: application/json" \
  -d '{
    "scenario": "s1_external_input",
    "state": {
      "date": "2025-10-31",
      "turbidity": 25.5,
      "flow_rate": 28.5
    },
    "episodes": 1,
    "backend": "api"
  }'
```

**Python 示例**：
```python
import requests
import json
import time

# 发送请求
response = requests.post(
    "http://localhost:8000/api/strategy",
    json={
        "scenario": "s1_external_input",
        "state": {
            "date": "2025-10-31",
            "turbidity": 25.5,
            "flow_rate": 28.5,
            "temperature": 18.2,
            "ph": 7.5,
            "dissolved_oxygen": 8.3,
            "chlorophyll_a": 5.2,
            "rainfall_3d": 45.3,
            "rainfall_7d": 120.5
        },
        "episodes": 1,
        "backend": "api"
    }
)

job_id = response.json()["job_id"]
print(f"Job ID: {job_id}")

# 轮询结果
while True:
    result = requests.get(f"http://localhost:8000/api/strategy/{job_id}")
    status = result.json()["status"]
    
    if status == "completed":
        print("✓ Strategy ready!")
        print(json.dumps(result.json(), indent=2))
        break
    elif status == "failed":
        print(f"✗ Job failed: {result.json()['error']}")
        break
    else:
        print(f"Status: {status}...")
        time.sleep(1)
```

---

### 6. 查询策略结果

#### GET /api/strategy/{job_id}

获取策略生成的结果。

**请求**：
```bash
curl http://localhost:8000/api/strategy/550e8400-e29b-41d4-a716-446655440000
```

**响应** (200 OK)：
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "scenario": "s1_external_input",
  "status": "completed",
  "strategy": {
    "release_rate": 8.5,
    "aeration_intensity": 0.3,
    "chemical_dosage": 0
  },
  "metrics": {
    "turbidity_reduction": 5.2,
    "turbidity_reduction_ratio": 0.18,
    "energy_cost": 2450.5,
    "cost_saving_ratio": 0.408,
    "stability": 0.968,
    "response_time_hours": 1.0
  },
  "reasoning_viz_path": "/outputs/visualization/reasoning_s1_external_input.html",
  "error": null,
  "completed_at": "2026-05-29T12:00:15"
}
```

---

### 7. 列出任务

#### GET /api/jobs

列出所有任务，支持过滤。

**查询参数**：
- `status`: 过滤状态 (queued, running, completed, failed)
- `scenario`: 过滤场景
- `limit`: 最大返回数量 (默认 100)

**请求**：
```bash
curl "http://localhost:8000/api/jobs?status=completed&limit=10"
```

**响应** (200 OK)：
```json
[
  {
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "scenario": "s1_external_input",
    "status": "completed",
    "created_at": "2026-05-29T12:00:00",
    "completed_at": "2026-05-29T12:00:15",
    "has_error": false
  },
  ...
]
```

---

### 8. 取消任务

#### DELETE /api/jobs/{job_id}

取消一个任务（仅限于未完成的任务）。

**请求**：
```bash
curl -X DELETE http://localhost:8000/api/jobs/550e8400-e29b-41d4-a716-446655440000
```

**响应** (200 OK)：
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "cancelled",
  "message": "Job cancelled"
}
```

---

## 数据模型参考

### WaterQualityState

```typescript
{
  "date": string,              // ISO 8601: "2025-10-31"
  "turbidity": number,         // 0-500 NTU
  "flow_rate": number,         // 0-100 m³/s
  "temperature": number?,      // 0-50 °C
  "ph": number?,               // 0-14
  "dissolved_oxygen": number?, // 0-15 mg/L
  "chlorophyll_a": number?,    // 0-100 μg/L
  "rainfall_3d": number?,      // mm (3-day cumulative)
  "rainfall_7d": number?       // mm (7-day cumulative)
}
```

### StrategyRequest

```typescript
{
  "scenario": "s1_external_input" | "s2_internal_release" | "s3_algae_bloom" | "s4_chronic_combo",
  "state": WaterQualityState,
  "episodes": number,   // 1-10
  "backend": "api" | "local",
  "request_id": string? // 可选的外部 ID
}
```

### StrategyResult

```typescript
{
  "job_id": string,
  "scenario": string,
  "status": "queued" | "running" | "completed" | "failed",
  "strategy": {
    "release_rate": number,        // m³/s
    "aeration_intensity": number,  // 0-1
    "chemical_dosage": number      // kg/day
  },
  "metrics": {
    "turbidity_reduction": number,
    "turbidity_reduction_ratio": number,
    "energy_cost": number,
    "cost_saving_ratio": number,
    "stability": number,
    "response_time_hours": number
  },
  "reasoning_viz_path": string?,
  "error": string?
}
```

## 集成指南

### 场景 1：React 前端

```javascript
import axios from 'axios';

// 生成策略
async function generateStrategy(waterState) {
  const response = await axios.post('/api/strategy', {
    scenario: 's1_external_input',
    state: waterState,
    episodes: 1,
    backend: 'api'
  });
  
  const jobId = response.data.job_id;
  
  // 轮询结果
  const result = await pollResult(jobId);
  return result;
}

async function pollResult(jobId, maxAttempts = 30) {
  for (let i = 0; i < maxAttempts; i++) {
    const response = await axios.get(`/api/strategy/${jobId}`);
    
    if (response.data.status === 'completed') {
      return response.data;
    } else if (response.data.status === 'failed') {
      throw new Error(response.data.error);
    }
    
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  
  throw new Error('Timeout waiting for result');
}
```

### 场景 2：移动应用（Flutter）

```dart
import 'package:http/http.dart' as http;
import 'dart:convert';

Future<String> generateStrategy(Map<String, dynamic> state) async {
  final response = await http.post(
    Uri.parse('http://api.example.com/api/strategy'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({
      'scenario': 's1_external_input',
      'state': state,
      'episodes': 1,
      'backend': 'api'
    }),
  );
  
  if (response.statusCode == 200) {
    final json = jsonDecode(response.body);
    return json['job_id'];
  } else {
    throw Exception('Failed to generate strategy');
  }
}
```

### 场景 3：Python 后端

```python
import requests
from typing import Dict, Any

class WaterAIClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
    
    def generate_strategy(self, scenario: str, state: Dict[str, Any], wait: bool = True):
        """生成策略，可选择等待结果"""
        response = requests.post(
            f"{self.base_url}/api/strategy",
            json={
                "scenario": scenario,
                "state": state,
                "episodes": 1,
                "backend": "api"
            }
        )
        
        job_id = response.json()["job_id"]
        
        if wait:
            return self.wait_for_result(job_id)
        else:
            return {"job_id": job_id, "status": "queued"}
    
    def wait_for_result(self, job_id: str, timeout: int = 60):
        """等待策略生成完成"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            response = requests.get(f"{self.base_url}/api/strategy/{job_id}")
            result = response.json()
            
            if result["status"] == "completed":
                return result
            elif result["status"] == "failed":
                raise Exception(f"Job failed: {result['error']}")
            
            time.sleep(1)
        
        raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")
```

## 生产部署

### Docker 部署

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY src/ /app/src/
COPY scripts/ /app/scripts/

ENV PYTHONPATH=/app/src:$PYTHONPATH
ENV DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}

EXPOSE 8000

CMD ["python", "-m", "scripts.run_api_server", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose

```yaml
version: '3.8'

services:
  water-ai-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      DEEPSEEK_API_KEY: ${DEEPSEEK_API_KEY}
    volumes:
      - ./outputs:/app/outputs
    restart: always
```

## 故障排除

### API 无法启动

```
✗ 错误：ModuleNotFoundError: No module named 'fastapi'
```

**解决**：安装依赖
```bash
pip install -r requirements-api.txt
```

### 策略生成超时

**原因**：
- 后端任务繁重
- DeepSeek API 响应慢

**解决**：
- 增加轮询超时时间
- 检查 DeepSeek API 状态
- 查看服务器日志

### 任务失败

```bash
curl http://localhost:8000/api/strategy/{job_id}
# status: "failed"
# error: "..."
```

**检查**：
1. DeepSeek API 密钥是否正确
2. 数据加载器是否能读取 CSV 文件
3. 代理系统是否正常

## 性能优化建议

1. **后台任务队列**：用 Celery + Redis 替代简单的后台任务
2. **缓存**：添加 Redis 缓存常见查询
3. **数据库**：用 PostgreSQL 存储历史结果
4. **并发**：增加 Uvicorn worker 数量
5. **监控**：集成 Prometheus + Grafana

## 下一步

- ✅ P1: DeepSeek 推理可视化
- ✅ P2: Web API 开发（当前）
- ⏭️ P3: React Web 前端
- ⏭️ P4: 数据库集成
- ⏭️ P5: 生产部署和监控

---

**API 版本**: 1.0.0  
**最后更新**: 2026-05-29  
**维护者**: WaterExpert Team
