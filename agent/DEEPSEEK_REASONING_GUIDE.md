# DeepSeek 推理可视化实现指南

## 概述

WaterExpert 现已集成 **DeepSeek-V4 推理令牌捕获** 和 **交互式推理过程可视化**，让用户能够看到 AI 在制定水质治理策略时的完整"思考过程"。

## 核心功能

### 1. 推理令牌捕获 (Reasoning Tokens)

**API 后端升级** (`src/water_ai/llm/backends/api_backend.py`)：
- ✅ 支持 DeepSeek-V4 API 端点
- ✅ 自动提取 `reasoning_content` 字段
- ✅ 兼容标准 OpenAI 格式
- ✅ 超时设置为 60 秒（长推理需要更多时间）

**请求体**：
```json
{
    "model": "deepseek-chat",
    "messages": [{"role": "user", "content": "..."}],
    "max_tokens": 2048,
    "temperature": 0.7,
    "top_p": 0.95
}
```

**响应体**：
```json
{
    "choices": [{
        "message": {
            "content": "策略JSON",
            "reasoning_content": "推理过程文本..."
        }
    }],
    "usage": {...}
}
```

### 2. 推理过程解析与可视化

**模块**：`src/water_ai/visualization/reasoning_viz.py`

**功能**：
- 自动解析推理文本，识别诊断 → 规划 → 约束检查三个阶段
- 为每个阶段计算置信度分数
- 生成交互式 HTML 可视化页面

**输出示例**：
```
outputs/visualization/
├── reasoning_s1_external_input.html      (外源输入型推理过程)
├── reasoning_s2_internal_release.html    (内源释放型推理过程)
├── reasoning_s3_algae_bloom.html         (藻华主导型推理过程)
└── reasoning_s4_chronic_combo.html       (慢性复合型推理过程)
```

### 3. 策略生成与集成

**代理升级** (`src/water_ai/agents/aquaturb_gpt_agent.py`)：

**前**：硬编码策略
```python
strategies = {"s1_external_input": {...}, ...}
return strategies.get(scenario)
```

**后**：DeepSeek 推理 + 可视化
```python
def act(self, planning_input):
    prompt = self._build_strategy_prompt(scenario, diagnosis)
    response = self.client.generate_with_fallback(prompt, fallback_strategy)
    
    if response.get("reasoning_tokens"):
        # 生成推理可视化
        viz_path = self.viz.create_reasoning_viz(...)
        strategy["reasoning_viz_path"] = viz_path
    
    return strategy
```

### 4. 报告集成

**报告生成器** (`src/water_ai/orchestrator/report_generator.py`)：

生成的 Markdown 报告会包含推理可视化链接：

```markdown
## 3. 决策链路追踪

### 🧠 DeepSeek 推理过程可视化

**[查看 LLM 推理思考过程](reasoning_s1_external_input.html)**

> 点击上方链接查看 DeepSeek-V4 生成策略时的完整推理过程...
```

## 使用指南

### 方案 A: 使用 DeepSeek API (推荐)

#### 1. 获取 API 密钥

访问 [https://platform.deepseek.com/](https://platform.deepseek.com/) 获取 API 密钥。

#### 2. 配置环境变量

```bash
export DEEPSEEK_API_KEY="sk-your-api-key-here"
```

#### 3. 运行系统

```bash
# 完整系统（所有4个场景）
PYTHONPATH=src:$PYTHONPATH python scripts/run_closed_loop.py \
    --scenario all --episodes 5 --backend api

# 单个场景快速测试
PYTHONPATH=src:$PYTHONPATH python scripts/run_closed_loop.py \
    --scenario 1 --episodes 2 --backend api
```

#### 4. 查看结果

**报告位置**：
```
outputs/scenarios/
├── s1_external_input/report.md
├── s2_internal_release/report.md
├── s3_algae_bloom/report.md
├── s4_chronic_combo/report.md
└── SUMMARY.md
```

**推理可视化**：
```
outputs/visualization/
├── reasoning_s1_external_input.html
├── reasoning_s2_internal_release.html
├── reasoning_s3_algae_bloom.html
└── reasoning_s4_chronic_combo.html
```

在浏览器中打开 HTML 文件查看交互式推理过程。

### 方案 B: 本地 DeepSeek 部署

如需在本地部署 DeepSeek 权重，参考 `configs/deepseek/local.yaml`。

### 方案 C: Fallback 模式 (无 API 密钥)

系统会自动使用预定义的策略而不调用 API：

```bash
# 不设置 DEEPSEEK_API_KEY 的情况下运行
PYTHONPATH=src:$PYTHONPATH python scripts/run_closed_loop.py \
    --scenario 1 --episodes 2 --backend api
```

输出会显示：
- ✓ 系统正常运行
- ⚠ 使用 fallback 策略（无推理可视化）
- 📝 生成完整的报告和 KPI

## 演示脚本

运行演示脚本查看所有 4 个场景的推理过程：

```bash
PYTHONPATH=src:$PYTHONPATH python demo_reasoning_viz.py
```

输出示例：
```
================================================================================
DeepSeek Reasoning Visualization Demo
================================================================================

✓ DEEPSEEK_API_KEY found - Real API calls will be made

[s1_external_input] External Input Type (外源输入型)
  ✓ Reasoning visualization generated: outputs/visualization/reasoning_s1_external_input.html
  - Confidence: 92.0%
  - Actions: ['release_water']

...
```

## 技术架构

```
┌─ 数据层 ────────────────────────────────────────┐
│  WaterQualityDataLoader (19,186 rows)            │
│  → 水质、气象、水动力数据整合                    │
└──────────────────────────────────────────────────┘
                        ↓
┌─ 诊断层 (Stage 1) ───────────────────────────────┐
│  MSCIMAgent + CMFBEAgent + KBAgent               │
│  → 浊度预测、过程分解、技术建议                  │
└──────────────────────────────────────────────────┘
                        ↓
┌─ 规划层 (Stage 2) ───────────────────────────────┐
│  AquaTurbGPTAgent                                │
│  ├─ 调用 DeepSeek-V4 API                         │
│  ├─ 捕获推理令牌 (reasoning_tokens)              │
│  └─ 生成交互式可视化                             │
└──────────────────────────────────────────────────┘
                        ↓
┌─ 执行 + 安全 + KPI (Stages 3-5) ─────────────────┐
│  RL-TGRR + SafetyAgent + KPICalculator           │
└──────────────────────────────────────────────────┘
                        ↓
┌─ 报告生成 (Stage 6) ──────────────────────────────┐
│  ReportGenerator                                 │
│  ├─ Markdown 报告（含推理链接）                  │
│  ├─ 推理可视化 HTML                              │
│  └─ KPI 对比表                                   │
└──────────────────────────────────────────────────┘
```

## 推理可视化 HTML 页面特性

每个推理可视化 HTML 文件包含：

### 页面布局

```
┌─────────────────────────────────────────┐
│  Header: 推理过程可视化 (梯度背景)      │
├─────────────────────────────────────────┤
│ 推理步骤流程                             │
│ ┌─────────────────────────────────────┐ │
│ │ Step 1 [诊断] 置信度: 80%            │ │
│ │   → 分析当前浊度和主导因子...         │ │
│ ├─────────────────────────────────────┤ │
│ │ Step 2 [规划] 置信度: 75%            │ │
│ │   → 考虑多目标权衡...                 │ │
│ ├─────────────────────────────────────┤ │
│ │ Step 3 [约束] 置信度: 85%            │ │
│ │   → 检查操作限制...                   │ │
│ └─────────────────────────────────────┘ │
├─────────────────────────────────────────┤
│ 原始推理文本 (可折叠)                    │
├─────────────────────────────────────────┤
│ Footer: 统计数据                         │
│ • 3 推理步骤 • 平均置信度: 80% • ...     │
└─────────────────────────────────────────┘
```

### 交互特性

- 🎨 **颜色编码**：诊断(红) 规划(青) 约束(黄) 分析(绿)
- 📊 **置信度显示**：每步的 AI 置信度
- 🔍 **悬停高亮**：步骤卡片交互反馈
- 📝 **原始文本**：完整推理过程的文本展示

## 扩展选项

### 自定义推理提示

编辑 `AquaTurbGPTAgent._build_strategy_prompt()` 以调整：
- 诊断标准
- 目标权重
- 约束条件
- 输出格式

### 改进推理解析

编辑 `ReasoningVisualizer._parse_reasoning()` 以识别：
- 更多的推理阶段
- 关键词和短语
- 置信度信号

### 自定义 HTML 样式

修改 `ReasoningVisualizer._generate_html()` 中的 CSS 以调整：
- 颜色主题
- 字体和布局
- 动画和过渡

## 故障排除

### 问题 1: 没有生成推理可视化

**原因**：
- API 密钥未设置
- API 调用失败
- 响应格式不符

**解决**：
```bash
# 检查 API 密钥
echo $DEEPSEEK_API_KEY

# 查看演示脚本输出
PYTHONPATH=src:$PYTHONPATH python demo_reasoning_viz.py

# 启用调试（编辑代码添加日志）
```

### 问题 2: 报告中没有推理链接

**原因**：
- 报告生成时不找到推理可视化文件
- 文件路径错误

**解决**：
- 检查 `outputs/visualization/` 是否有文件
- 验证相对路径是否正确

### 问题 3: API 超时

**原因**：
- 推理过程较长（推理令牌 >8000）
- 网络延迟

**解决**：
- 增加超时时间（见 `APIBackend.send()` 中的 `timeout=60`）
- 减少 `reasoning_tokens` 参数
- 检查网络连接

## 下一步

1. ✅ P1 完成：DeepSeek 推理可视化集成
2. ⏭️ P2：完整系统文档和 CI/CD 流程
3. ⏭️ P3：性能优化和边界测试

## 参考

- **QUICKSTART.md** - 第 4 节：最终可视化产出形式
- **API 文档** - https://platform.deepseek.com/api-docs
- **Reasoning 文档** - https://platform.deepseek.com/reasoning
