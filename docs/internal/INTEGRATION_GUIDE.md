# WaterExpert Agent 接入文档

## 概述

WaterExpert 是一个基于多智能体的水质治理决策系统，提供标准的 REST API 接口，可以轻松集成到任何外部系统中。

---

## 接入信息

### 基础信息

- **API 基础地址**: `http://your-server-ip:8000/api`
- **在线文档**: `http://your-server-ip:8000/docs` (Swagger UI)
- **ReDoc 文档**: `http://your-server-ip:8000/redoc`
- **协议**: HTTP/REST
- **数据格式**: JSON
- **编码**: UTF-8

### 服务能力

- ✅ 水质场景诊断（4种场景）
- ✅ 智能策略生成（基于深度学习+强化学习）
- ✅ 多维度指标评估
- ✅ 异步任务处理
- ✅ 实时状态查询

---

## 核心API端点

### 1. 健康检查

**用途**: 检查服务是否正常运行

```bash
GET /api/health
```

**响应示例**:
```json
{
  "status": "healthy",
  "timestamp": "2026-08-31T12:00:00",
  "agents": {
    "MSCIM": "ready",
    "CMFBE": "ready",
    "KnowledgeBase": "ready",
    "AquaTurbGPT": "ready",
    "RL-TGRR": "ready",
    "Safety": "ready"
  }
}
```

---

### 2. 获取可用场景

**用途**: 查看系统支持的所有水质治理场景

```bash
GET /api/scenarios
```

**响应示例**:
```json
[
  {
    "code": "S1",
    "name": "External Input Type",
    "description": "外源输入型 - 降水增加导致通过支流输入大量悬浮物和营养盐"
  },
  {
    "code": "S2",
    "name": "Internal Release Type",
    "description": "内源释放型 - 低流速条件下底泥营养盐释放"
  },
  {
    "code": "S3",
    "name": "Algae Bloom Type",
    "description": "藻类暴发型 - 高温低流速条件下藻类快速增殖"
  },
  {
    "code": "S4",
    "name": "Chronic Combo Type",
    "description": "慢性综合型 - 多因素长期作用"
  }
]
```

---

### 3. 生成治理策略（核心功能）

**用途**: 根据当前水质状态生成治理策略

```bash
POST /api/strategy
Content-Type: application/json
```

**请求体**:
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
  "backend": "api"
}
```

**参数说明**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| scenario | string | 是 | 场景代码: s1_external_input, s2_internal_release, s3_algae_bloom, s4_chronic_combo |
| state.date | string | 是 | 日期 (YYYY-MM-DD) |
| state.turbidity | number | 是 | 浊度 (NTU) |
| state.flow_rate | number | 是 | 流量 (m³/s) |
| state.temperature | number | 否 | 温度 (°C) |
| state.ph | number | 否 | pH值 (0-14) |
| state.dissolved_oxygen | number | 否 | 溶解氧 (mg/L) |
| state.chlorophyll_a | number | 否 | 叶绿素a (μg/L) |
| state.rainfall_3d | number | 否 | 3天累计降雨 (mm) |
| state.rainfall_7d | number | 否 | 7天累计降雨 (mm) |
| episodes | number | 否 | 运行次数 (1-10，默认1) |
| backend | string | 否 | 后端类型 (api/local，默认api) |

**响应示例**:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "scenario": "s1_external_input",
  "created_at": "2026-08-31T12:00:00",
  "message": "Strategy generation queued"
}
```

---

### 4. 查询策略结果

**用途**: 查询策略生成任务的结果

```bash
GET /api/strategy/{job_id}
```

**响应示例（处理中）**:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "scenario": "s1_external_input",
  "created_at": "2026-08-31T12:00:00"
}
```

**响应示例（完成）**:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "scenario": "s1_external_input",
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
  "completed_at": "2026-08-31T12:00:15"
}
```

**状态说明**:
- `queued`: 已排队等待处理
- `running`: 正在处理中
- `completed`: 处理完成
- `failed`: 处理失败

---

## 接入示例代码

### Python 示例

```python
import requests
import time

class WaterExpertClient:
    def __init__(self, base_url="http://your-server-ip:8000/api"):
        self.base_url = base_url
    
    def check_health(self):
        """健康检查"""
        response = requests.get(f"{self.base_url}/health")
        return response.json()
    
    def get_scenarios(self):
        """获取场景列表"""
        response = requests.get(f"{self.base_url}/scenarios")
        return response.json()
    
    def generate_strategy(self, scenario, state, wait=True, timeout=60):
        """生成治理策略"""
        # 1. 提交任务
        response = requests.post(
            f"{self.base_url}/strategy",
            json={
                "scenario": scenario,
                "state": state,
                "episodes": 1,
                "backend": "api"
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"API错误: {response.text}")
        
        job_id = response.json()["job_id"]
        
        # 2. 如果需要等待结果
        if wait:
            start_time = time.time()
            while time.time() - start_time < timeout:
                result = requests.get(f"{self.base_url}/strategy/{job_id}")
                data = result.json()
                
                if data["status"] == "completed":
                    return data
                elif data["status"] == "failed":
                    raise Exception(f"任务失败: {data.get('error', '未知错误')}")
                
                time.sleep(1)
            
            raise TimeoutError(f"任务超时 ({timeout}秒)")
        
        # 3. 不等待，直接返回job_id
        return {"job_id": job_id, "status": "queued"}

# 使用示例
client = WaterExpertClient("http://your-server-ip:8000/api")

# 健康检查
health = client.check_health()
print(f"服务状态: {health['status']}")

# 生成策略
result = client.generate_strategy(
    scenario="s1_external_input",
    state={
        "date": "2025-10-31",
        "turbidity": 25.5,
        "flow_rate": 28.5,
        "temperature": 18.2,
        "ph": 7.5,
        "dissolved_oxygen": 8.3,
        "chlorophyll_a": 5.2,
        "rainfall_3d": 45.3,
        "rainfall_7d": 120.5
    }
)

print(f"策略: {result['strategy']}")
print(f"指标: {result['metrics']}")
```

---

### JavaScript/Node.js 示例

```javascript
const axios = require('axios');

class WaterExpertClient {
    constructor(baseUrl = 'http://your-server-ip:8000/api') {
        this.baseUrl = baseUrl;
    }

    async checkHealth() {
        const response = await axios.get(`${this.baseUrl}/health`);
        return response.data;
    }

    async getScenarios() {
        const response = await axios.get(`${this.baseUrl}/scenarios`);
        return response.data;
    }

    async generateStrategy(scenario, state, wait = true, timeout = 60000) {
        // 提交任务
        const response = await axios.post(`${this.baseUrl}/strategy`, {
            scenario,
            state,
            episodes: 1,
            backend: 'api'
        });

        const jobId = response.data.job_id;

        // 等待结果
        if (wait) {
            const startTime = Date.now();
            while (Date.now() - startTime < timeout) {
                const result = await axios.get(`${this.baseUrl}/strategy/${jobId}`);
                const data = result.data;

                if (data.status === 'completed') {
                    return data;
                } else if (data.status === 'failed') {
                    throw new Error(`任务失败: ${data.error || '未知错误'}`);
                }

                await new Promise(resolve => setTimeout(resolve, 1000));
            }
            throw new Error(`任务超时 (${timeout}ms)`);
        }

        return { job_id: jobId, status: 'queued' };
    }
}

// 使用示例
(async () => {
    const client = new WaterExpertClient('http://your-server-ip:8000/api');

    // 健康检查
    const health = await client.checkHealth();
    console.log('服务状态:', health.status);

    // 生成策略
    const result = await client.generateStrategy('s1_external_input', {
        date: '2025-10-31',
        turbidity: 25.5,
        flow_rate: 28.5,
        temperature: 18.2,
        ph: 7.5,
        dissolved_oxygen: 8.3,
        chlorophyll_a: 5.2,
        rainfall_3d: 45.3,
        rainfall_7d: 120.5
    });

    console.log('策略:', result.strategy);
    console.log('指标:', result.metrics);
})();
```

---

### Java 示例

```java
import com.google.gson.Gson;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.HashMap;
import java.util.Map;

public class WaterExpertClient {
    private final String baseUrl;
    private final HttpClient client;
    private final Gson gson;

    public WaterExpertClient(String baseUrl) {
        this.baseUrl = baseUrl;
        this.client = HttpClient.newHttpClient();
        this.gson = new Gson();
    }

    public String generateStrategy(String scenario, Map<String, Object> state) throws Exception {
        // 构建请求体
        Map<String, Object> requestBody = new HashMap<>();
        requestBody.put("scenario", scenario);
        requestBody.put("state", state);
        requestBody.put("episodes", 1);
        requestBody.put("backend", "api");

        String json = gson.toJson(requestBody);

        // 发送请求
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(baseUrl + "/strategy"))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(json))
            .build();

        HttpResponse<String> response = client.send(request, 
            HttpResponse.BodyHandlers.ofString());

        // 解析job_id
        Map<String, Object> result = gson.fromJson(response.body(), Map.class);
        String jobId = (String) result.get("job_id");

        // 轮询结果
        while (true) {
            HttpRequest statusRequest = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + "/strategy/" + jobId))
                .GET()
                .build();

            HttpResponse<String> statusResponse = client.send(statusRequest, 
                HttpResponse.BodyHandlers.ofString());

            Map<String, Object> statusResult = gson.fromJson(
                statusResponse.body(), Map.class);

            String status = (String) statusResult.get("status");

            if ("completed".equals(status)) {
                return statusResponse.body();
            } else if ("failed".equals(status)) {
                throw new Exception("任务失败: " + statusResult.get("error"));
            }

            Thread.sleep(1000);
        }
    }
}
```

---

## 典型集成流程

### 流程图

```
外部系统                              WaterExpert API
   │                                       │
   ├─────── 1. 健康检查 ────────────────>│
   │<────── 返回: healthy ────────────────┤
   │                                       │
   ├─────── 2. 查询场景列表 ─────────────>│
   │<────── 返回: 场景信息 ────────────────┤
   │                                       │
   ├─────── 3. 提交水质数据 ─────────────>│
   │<────── 返回: job_id ──────────────────┤
   │                                       │
   ├─────── 4. 轮询结果 (每秒1次) ───────>│
   │<────── status: running ───────────────┤
   │                                       │
   ├─────── 5. 再次查询 ────────────────>│
   │<────── status: completed, 返回策略 ───┤
   │                                       │
   └─────── 6. 应用策略到系统 ─────────────┘
```

---

## 性能参数

| 指标 | 值 | 说明 |
|------|-----|------|
| 平均响应时间 | 2-5秒 | 取决于场景复杂度 |
| 并发处理能力 | 10+ | 可通过增加worker扩展 |
| 可用性目标 | 99%+ | 建议使用监控 |
| 数据大小限制 | 1MB | 单次请求 |

---

## 错误码说明

| HTTP状态码 | 说明 | 处理建议 |
|-----------|------|---------|
| 200 | 成功 | - |
| 400 | 请求参数错误 | 检查请求格式和参数 |
| 404 | 资源不存在 | 检查URL和job_id |
| 500 | 服务器内部错误 | 联系技术支持 |
| 503 | 服务不可用 | 稍后重试 |

---

## 安全建议

1. **网络隔离**: 建议通过VPN或专线访问
2. **IP白名单**: 仅允许授权IP访问
3. **流量限制**: 避免频繁请求造成服务过载
4. **数据加密**: 生产环境建议使用HTTPS
5. **认证机制**: 可选配置API Key或JWT认证

---

## 技术支持

- **技术文档**: [API_GUIDE.md](API_GUIDE.md)
- **在线文档**: http://your-server-ip:8000/docs
- **问题反馈**: 联系方式

---

## 更新日志

### v1.0.0 (2026-08-31)
- ✅ 首次发布
- ✅ 支持4种水质场景
- ✅ REST API接口
- ✅ 异步任务处理
