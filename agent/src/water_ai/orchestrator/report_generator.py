"""
Report generator for scenario evaluation and multi-agent orchestration.

Generates markdown reports with:
- KPI comparison tables
- Decision chain tracking
- Scenario metrics summary
- Visual recommendations
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ReportGenerator:
    """Generate comprehensive reports for water quality management scenarios."""

    def __init__(self, output_base: str = "outputs/scenarios") -> None:
        """
        Initialize report generator.

        Args:
            output_base: Base directory for report output
        """
        self.output_base = Path(output_base)
        self.output_base.mkdir(parents=True, exist_ok=True)

    def generate_scenario_report(
        self,
        scenario_key: str,
        scenario_data: dict[str, Any],
        agents_info: dict[str, Any],
    ) -> Path:
        """
        Generate comprehensive report for a scenario.

        Args:
            scenario_key: Scenario identifier (e.g., "s1_external_input")
            scenario_data: Aggregated scenario results
            agents_info: Status of all agents

        Returns:
            Path to generated report
        """
        # Create scenario output directory
        scenario_dir = self.output_base / scenario_key
        scenario_dir.mkdir(parents=True, exist_ok=True)

        # Build report content
        report_lines = []
        report_lines.append(f"# WaterExpert 场景分析报告：{self._scenario_title(scenario_key)}\n")
        report_lines.append(f"生成时间：{datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Section 1: 场景概述
        report_lines.extend(self._generate_scenario_overview(scenario_key, scenario_data))

        # Section 2: KPI 汇总表
        report_lines.extend(self._generate_kpi_table(scenario_data))

        # Section 3: 决策链路追踪
        report_lines.extend(self._generate_decision_chain(scenario_data))

        # Section 4: 智能体状态
        report_lines.extend(self._generate_agent_status(agents_info))

        # Write report
        report_path = scenario_dir / "report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines))

        # Also save JSON data
        json_path = scenario_dir / "data.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(scenario_data, f, indent=2, ensure_ascii=False, default=str)

        return report_path

    def generate_summary_report(self, all_results: dict[str, Any]) -> Path:
        """
        Generate cross-scenario summary report.

        Args:
            all_results: Results from all scenarios

        Returns:
            Path to summary report
        """
        report_lines = []
        report_lines.append("# WaterExpert 多场景协同治理总结报告\n")
        report_lines.append(f"生成时间：{datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Cross-scenario comparison
        report_lines.append("## 1. 四场景性能对比\n")
        report_lines.append("| 场景 | 浊度削减率 | 成本节约 | 能源成本(¥) | 稳定度 | 运行集数 |")
        report_lines.append("|------|-----------|----------|-----------|--------|---------|")

        for scenario_key, scenario_data in all_results.items():
            metrics = scenario_data.get("metrics_summary", {})
            report_lines.append(
                f"| {self._scenario_title(scenario_key)} | "
                f"{metrics.get('avg_turbidity_reduction_ratio', 0):.1%} | "
                f"{metrics.get('avg_cost_saving_ratio', 0):.1%} | "
                f"¥{metrics.get('avg_energy_cost', 0):.2f} | "
                f"{metrics.get('avg_stability', 0):.1%} | "
                f"{metrics.get('total_episodes', 0)} |"
            )

        # Key insights
        report_lines.append("\n## 2. 核心发现\n")
        best_scenario = max(
            all_results.items(),
            key=lambda x: x[1].get("metrics_summary", {}).get("avg_turbidity_reduction_ratio", 0),
        )
        report_lines.append(
            f"- **最高效场景**：{self._scenario_title(best_scenario[0])}"
            f"，浊度削减率达 {best_scenario[1].get('metrics_summary', {}).get('avg_turbidity_reduction_ratio', 0):.1%}\n"
        )

        lowest_cost_scenario = min(
            all_results.items(),
            key=lambda x: x[1].get("metrics_summary", {}).get("avg_energy_cost", float("inf")),
        )
        report_lines.append(
            f"- **最低成本场景**：{self._scenario_title(lowest_cost_scenario[0])}"
            f"，平均成本 ¥{lowest_cost_scenario[1].get('metrics_summary', {}).get('avg_energy_cost', 0):.2f}\n"
        )

        most_stable = max(
            all_results.items(),
            key=lambda x: x[1].get("metrics_summary", {}).get("avg_stability", 0),
        )
        report_lines.append(
            f"- **最稳定场景**：{self._scenario_title(most_stable[0])}"
            f"，稳定度 {most_stable[1].get('metrics_summary', {}).get('avg_stability', 0):.1%}\n"
        )

        # Recommendations
        report_lines.append("\n## 3. 治理建议\n")
        report_lines.append("### 当前优先级顺序\n")
        report_lines.append(
            "1. **外源输入型**(S1)：应急响应为主，大流量冲刷 → 浊度快速下降\n"
        )
        report_lines.append("2. **内源释放型**(S2)：精细控制为主，低强度曝气 + 沉淀 → 平缓降低\n")
        report_lines.append("3. **藻华主导型**(S3)：生物处理为主，曝气增氧 + 生物制剂 → 多日见效\n")
        report_lines.append("4. **慢性复合型**(S4)：长期调理，基础设施升级 → 需数周稳定\n")

        # Write summary report
        summary_path = self.output_base / "SUMMARY.md"
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines))

        return summary_path

    def _scenario_title(self, scenario_key: str) -> str:
        """Get Chinese title for scenario."""
        titles = {
            "s1_external_input": "外源输入型",
            "s2_internal_release": "内源释放型",
            "s3_algae_bloom": "藻华主导型",
            "s4_chronic_combo": "慢性复合型",
        }
        return titles.get(scenario_key, scenario_key)

    def _generate_scenario_overview(
        self, scenario_key: str, scenario_data: dict[str, Any]
    ) -> list[str]:
        """Generate scenario overview section."""
        lines = []
        lines.append("## 1. 场景概述\n")
        lines.append(f"**场景类型**：{self._scenario_title(scenario_key)}\n")

        scenarios = {
            "s1_external_input": "外源输入驱动。特征：3日累积降雨>36mm，上游冲刷"
            "，悬浮沙粒入水。推荐干预：增加放水冲刷 + 加大沉淀池反冲。",
            "s2_internal_release": "内源释放驱动。特征：沉积物撤离强度高，底泥翻动释放"
            "营养盐和悬浮物。推荐干预：精细化流量控制 + 原位曝气。",
            "s3_algae_bloom": "藻华主导。特征：叶绿素-a>8μg/L，光照充足。"
            "推荐干预：曝气增氧 + 生物制剂。",
            "s4_chronic_combo": "慢性复合。特征：基础浊度>3 NTU 连续7天。"
            "推荐干预：长期低强度调理 + 生态修复。",
        }

        lines.append(f"**特征**：{scenarios.get(scenario_key, '未知场景')}\n")
        lines.append(
            f"**集数**：{scenario_data.get('metrics_summary', {}).get('total_episodes', 0)}\n\n"
        )

        return lines

    def _generate_kpi_table(self, scenario_data: dict[str, Any]) -> list[str]:
        """Generate KPI comparison table."""
        lines = []
        lines.append("## 2. 关键性能指标(KPI) 汇总\n")

        metrics = scenario_data.get("metrics_summary", {})

        lines.append("| 指标 | 平均值 | 目标 | 达成度 |")
        lines.append("|------|--------|------|--------|")

        reduction_ratio = metrics.get("avg_turbidity_reduction_ratio", 0)
        lines.append(
            f"| 浊度削减率 | {reduction_ratio:.1%} | ≥30% | {'✓' if reduction_ratio >= 0.30 else '✗'} |"
        )

        cost = metrics.get("avg_energy_cost", 0)
        cost_saving = metrics.get("avg_cost_saving_ratio", 0)
        lines.append(f"| 成本节约 | {cost_saving:.1%} | ≥25% | {'✓' if cost_saving >= 0.25 else '✗'} |")
        lines.append(f"| 能源成本 | ¥{cost:.2f} | 参考值 | - |")

        # Stability
        stability = metrics.get("avg_stability", 0)
        lines.append(f"| 稳定度 | {stability:.1%} | ≥85% | {'✓' if stability >= 0.85 else '✗'} |")

        # Response time
        response_time = metrics.get("avg_response_time_hours", 1.0)
        lines.append(f"| 响应时间 | {response_time:.2f}h | <2h | {'✓' if response_time < 2 else '✗'} |")

        lines.append("\n")
        return lines

    def _generate_decision_chain(self, scenario_data: dict[str, Any]) -> list[str]:
        """Generate decision chain tracking section."""
        lines = []
        lines.append("## 3. 决策链路追踪\n")

        lines.append("### 多智能体协同流程\n")
        lines.append("```")
        lines.append("[水质数据]")
        lines.append("   ↓")
        lines.append("[MSCIM 诊断] → 浊度预测 + 主导因子")
        lines.append("   ↓")
        lines.append("[CMFBE 分析] → 过程分解 + 阈值响应")
        lines.append("   ↓")
        lines.append("[KB 检索] → 技术库匹配")
        lines.append("   ↓")
        lines.append("[AquaTurb-GPT 🧠] → 场景分类 + 约束释义 + 策略草案")
        lines.append("   ↓")
        lines.append("[RL-TGRR] → 低层控制 + MPC + 行为克隆")
        lines.append("   ↓")
        lines.append("[SafetyAgent] → 安全屏蔽 + 约束检查")
        lines.append("   ↓")
        lines.append("[执行] → 放水/曝气/药物投加")
        lines.append("```\n")

        # Add reasoning visualization if available
        reasoning_viz = scenario_data.get("reasoning_viz_path")
        if reasoning_viz:
            lines.append("### 🧠 DeepSeek 推理过程可视化\n")
            # Convert absolute path to relative for markdown link
            from pathlib import Path
            try:
                viz_relative = Path(reasoning_viz).relative_to(Path("outputs/scenarios"))
                lines.append(f"**[查看 LLM 推理思考过程]({viz_relative})**\n")
                lines.append("> 点击上方链接查看 DeepSeek-V4 生成策略时的完整推理过程，包括诊断、规划和约束检查等阶段。\n\n")
            except ValueError:
                # If relative path fails, use absolute
                lines.append(f"**[查看 LLM 推理思考过程]({reasoning_viz})**\n")
                lines.append("> 点击上方链接查看 DeepSeek-V4 生成策略时的完整推理过程。\n\n")

        lines.append("### 样本决策\n")
        if scenario_data.get("episodes"):
            first_episode = scenario_data["episodes"][0]
            input_state = first_episode.get("state") or first_episode.get("feedback", {}).get("state", {})
            lines.append(
                f"**第1集输入**：{json.dumps(input_state, indent=2, ensure_ascii=False)}\n"
            )
            lines.append(
                f"**诊断输出**：{json.dumps(first_episode.get('diagnosis', {}), indent=2, ensure_ascii=False, default=str)}\n"
            )
            lines.append(
                f"**执行动作**：{json.dumps(first_episode.get('execution', {}), indent=2, ensure_ascii=False)}\n"
            )

        lines.append("\n")
        return lines

    def _generate_agent_status(self, agents_info: dict[str, Any]) -> list[str]:
        """Generate agent status section."""
        lines = []
        lines.append("## 4. 智能体系统状态\n")

        lines.append("| 智能体 | 状态 | 配置 |")
        lines.append("|------|------|------|")

        for name, info in agents_info.items():
            status = info.get("type", "unknown")
            config_summary = str(info.get("config", {}))[:50]
            lines.append(f"| {name} | {status} | {config_summary}... |")

        lines.append("\n")
        return lines
