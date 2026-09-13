"""DeepSeek reasoning process visualization module.

This module captures and visualizes the DeepSeek-V4 model's reasoning tokens
to show the LLM's "thinking process" in an interactive format.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class ReasoningVisualizer:
    """Generate interactive visualization of DeepSeek reasoning tokens."""

    def __init__(self, output_dir: Path | None = None) -> None:
        self.output_dir = Path(output_dir or "outputs/visualization")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def create_reasoning_viz(
        self,
        scenario: str,
        reasoning_tokens: str,
        thinking_process: list[dict[str, Any]] | None = None,
        output_name: str = "reasoning_trace.html",
    ) -> str:
        """Create interactive HTML visualization of reasoning tokens.

        Args:
            scenario: Scenario name (e.g., "s1_external_input")
            reasoning_tokens: Raw reasoning token string from DeepSeek
            thinking_process: Optional structured thinking steps
            output_name: Output HTML filename

        Returns:
            Path to generated HTML file
        """
        # Parse thinking process if provided
        steps = thinking_process or self._parse_reasoning(reasoning_tokens)

        # Generate HTML
        html_content = self._generate_html(scenario, steps, reasoning_tokens)

        # Save file
        output_path = self.output_dir / output_name
        output_path.write_text(html_content, encoding="utf-8")

        return str(output_path)

    def _parse_reasoning(self, reasoning_tokens: str) -> list[dict[str, Any]]:
        """Parse reasoning tokens into structured thinking steps.

        Args:
            reasoning_tokens: Raw reasoning string

        Returns:
            List of thinking steps with metadata
        """
        steps = []
        lines = reasoning_tokens.split("\n")

        current_step = {"phase": "analysis", "content": "", "confidence": 0.8}

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Detect phase keywords
            if any(kw in line.lower() for kw in ["诊断", "分析", "identify", "analyze"]):
                if current_step["content"]:
                    steps.append(current_step)
                current_step = {"phase": "diagnosis", "content": line, "confidence": 0.8}
            elif any(kw in line.lower() for kw in ["规划", "建议", "recommend", "plan"]):
                if current_step["content"]:
                    steps.append(current_step)
                current_step = {
                    "phase": "planning",
                    "content": line,
                    "confidence": 0.75,
                }
            elif any(kw in line.lower() for kw in ["约束", "限制", "constraint"]):
                if current_step["content"]:
                    steps.append(current_step)
                current_step = {"phase": "constraint", "content": line, "confidence": 0.85}
            else:
                current_step["content"] += " " + line

        if current_step["content"]:
            steps.append(current_step)

        return steps if steps else [{"phase": "thinking", "content": reasoning_tokens, "confidence": 0.7}]

    def _generate_html(
        self, scenario: str, steps: list[dict[str, Any]], raw_tokens: str
    ) -> str:
        """Generate interactive HTML visualization.

        Args:
            scenario: Scenario name
            steps: Thinking steps
            raw_tokens: Raw reasoning tokens

        Returns:
            HTML string
        """
        # Color mapping for phases
        phase_colors = {
            "diagnosis": "#FF6B6B",
            "planning": "#4ECDC4",
            "constraint": "#FFE66D",
            "analysis": "#95E1D3",
            "thinking": "#C7CEEA",
        }

        # Build step HTML
        steps_html = ""
        for i, step in enumerate(steps, 1):
            phase = step.get("phase", "thinking")
            color = phase_colors.get(phase, "#CCCCCC")
            content = step.get("content", "")[:200]  # Truncate for readability
            confidence = step.get("confidence", 0.7)

            steps_html += f"""
    <div class="step" style="border-left: 4px solid {color};">
        <div class="step-header">
            <span class="step-num">{i}</span>
            <span class="phase-label" style="background-color: {color}; color: white;">{phase.upper()}</span>
            <span class="confidence">置信度: {confidence:.1%}</span>
        </div>
        <div class="step-content">{content}...</div>
    </div>"""

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DeepSeek 推理可视化 - {scenario}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 28px;
            margin-bottom: 10px;
        }}
        
        .header p {{
            font-size: 14px;
            opacity: 0.9;
        }}
        
        .content {{
            padding: 40px;
        }}
        
        .section-title {{
            font-size: 18px;
            font-weight: 600;
            color: #333;
            margin: 30px 0 20px 0;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }}
        
        .steps-container {{
            display: flex;
            flex-direction: column;
            gap: 15px;
        }}
        
        .step {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            transition: all 0.3s ease;
            cursor: pointer;
        }}
        
        .step:hover {{
            background: #e9ecef;
            transform: translateX(5px);
        }}
        
        .step-header {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 10px;
        }}
        
        .step-num {{
            display: flex;
            align-items: center;
            justify-content: center;
            width: 28px;
            height: 28px;
            background: #667eea;
            color: white;
            border-radius: 50%;
            font-weight: bold;
            font-size: 12px;
        }}
        
        .phase-label {{
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
        }}
        
        .confidence {{
            margin-left: auto;
            font-size: 12px;
            color: #666;
            background: #e9ecef;
            padding: 4px 8px;
            border-radius: 4px;
        }}
        
        .step-content {{
            font-size: 13px;
            line-height: 1.6;
            color: #555;
            padding-left: 40px;
        }}
        
        .raw-tokens {{
            background: #272822;
            color: #f8f8f2;
            padding: 15px;
            border-radius: 8px;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            overflow-x: auto;
            max-height: 300px;
            overflow-y: auto;
            margin-top: 10px;
        }}
        
        .footer {{
            background: #f8f9fa;
            border-top: 1px solid #dee2e6;
            padding: 20px 40px;
            font-size: 12px;
            color: #666;
            text-align: center;
        }}
        
        .stat {{
            display: inline-block;
            margin: 0 15px;
        }}
        
        .stat-value {{
            font-weight: 600;
            color: #667eea;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🧠 DeepSeek-V4 推理过程可视化</h1>
            <p>场景: {scenario} | 推理步骤: {len(steps)} | 生成时间: 2026-05-28</p>
        </div>
        
        <div class="content">
            <div class="section-title">推理步骤流程</div>
            <div class="steps-container">
{steps_html}
            </div>
            
            <div class="section-title">原始推理文本</div>
            <div class="raw-tokens">{raw_tokens[:1000]}{'...' if len(raw_tokens) > 1000 else ''}</div>
        </div>
        
        <div class="footer">
            <div class="stat"><span class="stat-value">{len(steps)}</span> 推理步骤</div>
            <div class="stat">平均置信度: <span class="stat-value">{sum(s.get('confidence', 0.7) for s in steps) / len(steps):.1%}</span></div>
            <div class="stat">支持模型: DeepSeek-V4 (长上下文)</div>
        </div>
    </div>
</body>
</html>"""
        return html

    def add_reasoning_to_report(self, report_md: str, reasoning_viz_path: str) -> str:
        """Add reasoning visualization link to markdown report.

        Args:
            report_md: Existing markdown content
            reasoning_viz_path: Path to reasoning HTML file

        Returns:
            Updated markdown with visualization link
        """
        viz_section = f"""
### 🧠 DeepSeek 推理过程追踪

点击下方链接查看 LLM 的完整思考过程（推理 tokens）：

**[查看推理可视化]({reasoning_viz_path})**

> 该可视化展示了 DeepSeek-V4 在生成策略时的逐步推理过程，包括诊断、规划和约束检查等阶段。

---

"""
        return report_md.replace("## 决策链路", "## 决策链路\n" + viz_section, 1)
