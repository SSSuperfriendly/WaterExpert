from __future__ import annotations

from typing import Any

from .message_bus import MessageBus
from .kpi import KPICalculator
from .feedback_loop import FeedbackLoop


class Orchestrator:
    """
    Multi-agent orchestrator for water quality management.
    
    Coordinates diagnosis → planning → execution → synchronization workflow.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.bus = MessageBus()
        self.kpi = KPICalculator()
        self.feedback = FeedbackLoop()
        self.episode_count = 0

    def run(
        self,
        agents: dict[str, Any],
        state: dict[str, Any],
        scenario_key: str = "unknown",
        on_stage: Any = None,
        knowledge_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Run one episode of multi-agent decision-making.

        Args:
            agents: Dictionary of agent instances
            state: Current environmental state (from DataLoader)
            scenario_key: Scenario identifier for routing
            on_stage: Optional callback(stage_name) for progress tracking
            knowledge_context: Graph evidence the platform retrieved for this
                request, or ``None``. Kept as a *separate parameter* rather than
                merged into ``state`` on purpose: ``state`` is handed to MSCIM
                and CMFBE, whose checkpoint runners index it by feature name, and
                an unexpected key there is a much worse failure than an extra
                argument here.
        """
        self.episode_count += 1

        def _notify(stage: str):
            if on_stage:
                on_stage(stage)

        # Stage 1: Diagnosis (parallel)
        _notify("mscim")
        diagnosis_reports = self._run_diagnosis_stage(
            agents, state, scenario_key, _notify, knowledge_context
        )

        # Stage 2: Planning (sequential with diagnosis results)
        _notify("gpt")
        planning_report = self._run_planning_stage(
            agents, diagnosis_reports, state, scenario_key, knowledge_context
        )

        # Stage 3: Execution
        _notify("rl")
        action_report = self._run_execution_stage(agents, planning_report, state)

        # Stage 4: Safety screening
        _notify("safe")
        safe_action_report = self._run_safety_stage(agents, action_report, state)

        # Stage 5: KPI calculation
        _notify("output")
        metrics = self.kpi.compute(safe_action_report.get("safe_action", {}), state)

        # Stage 6: Feedback & synchronization
        feedback = self.feedback.update(state, safe_action_report, metrics)

        # Build agent traces for visualization
        agent_traces = {
            "mscim": {
                "input": {"turbidity": state.get("turbidity"), "flow_rate": state.get("flow_rate"),
                          "rainfall_3d": state.get("rainfall_3d"), "temperature": state.get("temperature"),
                          "chlorophyll_a": state.get("chlorophyll_a"), "dissolved_oxygen": state.get("dissolved_oxygen")},
                "output": diagnosis_reports.get("mscim", {}),
            },
            "cmfbe": {
                "input": {"turbidity": state.get("turbidity"), "rainfall_3d": state.get("rainfall_3d"),
                          "rainfall_7d": state.get("rainfall_7d"), "flow_rate": state.get("flow_rate"),
                          "chlorophyll_a": state.get("chlorophyll_a")},
                "output": diagnosis_reports.get("cmfbe", {}),
            },
            "kb": {
                "input": {
                    "scenario": scenario_key,
                    # Surfaced in the trace so the lab page can show whether
                    # this round's recommendation rested on graph evidence or on
                    # the curated dictionary — the difference is invisible in
                    # the output alone.
                    "knowledge_context_available": bool(knowledge_context),
                    "knowledge_context_query": (knowledge_context or {}).get("query", ""),
                },
                "output": diagnosis_reports.get("knowledge_base", {}),
            },
            "gpt": {
                "input": {"scenario": scenario_key, "knowledge_context_available": bool(knowledge_context), "diagnosis_summary": {
                    "mscim_prediction": diagnosis_reports.get("mscim", {}).get("prediction", {}),
                    "cmfbe_net_change": diagnosis_reports.get("cmfbe", {}).get("net_change"),
                    "kb_recommendations": diagnosis_reports.get("knowledge_base", {}).get("recommendations", []),
                }},
                "output": planning_report,
            },
            "rl": {
                "input": {"state_obs": {"turbidity": state.get("turbidity"), "rainfall_3d": state.get("rainfall_3d"),
                                        "chlorophyll_a": state.get("chlorophyll_a"), "dissolved_oxygen": state.get("dissolved_oxygen")},
                          "plan_strategy": planning_report.get("strategy", {})},
                "output": action_report,
            },
            "safety": {
                "input": {"proposed_action": action_report.get("action", {})},
                "output": safe_action_report,
            },
        }

        # Publish to message bus
        episode_result = {
            "episode": self.episode_count,
            "scenario": scenario_key,
            "timestamp": state.get("date", "unknown"),
            "diagnosis": diagnosis_reports,
            "planning": planning_report,
            "execution": action_report,
            "safety_check": safe_action_report,
            "metrics": metrics,
            "feedback": feedback,
            "agent_traces": agent_traces,
        }
        episode_result["reports"] = diagnosis_reports
        episode_result["safe_action"] = safe_action_report.get("safe_action", {})

        self.bus.publish(episode_result)

        return episode_result

    def _run_diagnosis_stage(
        self,
        agents: dict[str, Any],
        state: dict[str, Any],
        scenario_key: str = "unknown",
        _notify=None,
        knowledge_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Stage 1: Diagnosis experts analyze current conditions."""
        diagnosis = {}

        # MSCIM: Turbidity prediction & attribution
        if "MSCIMAgent" in agents:
            if _notify:
                _notify("mscim")
            try:
                mscim_result = agents["MSCIMAgent"].act(state)
                diagnosis["mscim"] = mscim_result
            except Exception as e:
                diagnosis["mscim"] = {"error": str(e)}

        # CMFBE: Process decomposition
        if "CMFBEAgent" in agents:
            if _notify:
                _notify("cmfbe")
            try:
                # The context goes in as a second argument, never merged into
                # ``state`` (see ``run``'s note). CMFBE is the one diagnosis
                # agent that reads it: the thresholds it screens against are the
                # platform graph's, not a copy of them kept in the agent.
                cmfbe_result = agents["CMFBEAgent"].act(state, knowledge_context)
                diagnosis["cmfbe"] = cmfbe_result
            except Exception as e:
                diagnosis["cmfbe"] = {"error": str(e)}

        # Knowledge Base: Candidate techniques (needs scenario_key)
        if "KnowledgeBaseAgent" in agents:
            if _notify:
                _notify("kb")
            try:
                kb_input = {**state, "scenario_type": scenario_key}
                if knowledge_context is not None:
                    kb_input["knowledge_context"] = knowledge_context
                kb_result = agents["KnowledgeBaseAgent"].act(kb_input)
                diagnosis["knowledge_base"] = kb_result
            except Exception as e:
                diagnosis["knowledge_base"] = {"error": str(e)}

        return diagnosis

    def _run_planning_stage(
        self,
        agents: dict[str, Any],
        diagnosis_reports: dict[str, Any],
        state: dict[str, Any],
        scenario_key: str,
        knowledge_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Stage 2: High-level planner (AquaTurb-GPT) synthesizes diagnosis
        and generates strategy.

        Invokes:
        - AquaTurbGPTAgent: DeepSeek inference for scenario classification
          and constraint interpretation
        """
        if "AquaTurbGPTAgent" not in agents:
            return {"error": "AquaTurbGPTAgent not available"}

        try:
            # Construct planning prompt with diagnosis summary
            planning_input = {
                "state": state,
                "diagnosis": diagnosis_reports,
                "scenario": scenario_key,
                "knowledge_context": knowledge_context,
            }

            planning_result = agents["AquaTurbGPTAgent"].act(planning_input)
            return planning_result

        except Exception as e:
            return {"error": str(e)}

    def _run_execution_stage(
        self,
        agents: dict[str, Any],
        planning_report: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Stage 3: Execution agent (RL-TGRR) converts high-level plan
        to concrete control actions.
        
        Invokes:
        - RLTGRRAgent: Safe-SAC policy + MPC for action refinement
        """
        if "RLTGRRAgent" not in agents:
            return {"action": {}, "error": "RLTGRRAgent not available"}

        try:
            execution_input = {
                "state": state,
                "plan": planning_report,
            }

            execution_result = agents["RLTGRRAgent"].act(execution_input)
            return execution_result

        except Exception as e:
            return {"action": {}, "error": str(e)}

    def _run_safety_stage(
        self,
        agents: dict[str, Any],
        action_report: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Stage 4: Safety agent screens actions against constraints.
        
        Invokes:
        - SafetyAgent: Rule-based constraint checker
        """
        if "SafetyAgent" not in agents:
            # No safety agent, pass through
            return {
                "safe_action": action_report.get("action", {}),
                "safety_passed": True,
            }

        try:
            safety_input = {
                "state": state,
                "proposed_action": action_report.get("action", {}),
            }

            safety_result = agents["SafetyAgent"].act(safety_input)
            return safety_result

        except Exception as e:
            # On safety agent error, pass through
            return {
                "safe_action": action_report.get("action", {}),
                "safety_warning": str(e),
            }

    def status(self) -> dict[str, Any]:
        """Get orchestrator status."""
        return {
            "episodes_run": self.episode_count,
            "message_bus_size": len(self.bus.messages),
        }
