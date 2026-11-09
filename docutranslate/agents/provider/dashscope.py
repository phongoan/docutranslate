from docutranslate.agents.thinking.base import ReasoningAdapter, reasoning_decision
from docutranslate.agents.thinking.capability import ReasoningDecision, ThinkingIntent


class DashScopeAdapter(ReasoningAdapter):
    def decide(self, model_id: str, intent: ThinkingIntent) -> ReasoningDecision:
        model = model_id.lower()
        mandatory = "thinking" in model or "deepseek-r1" in model or model.endswith("r1")
        if intent == "default":
            return reasoning_decision("mandatory" if mandatory else "optional", "none")
        if mandatory and intent == "disable":
            return reasoning_decision(
                "mandatory",
                "boolean",
                warning=f"Mô hình {model_id} là mô hình bắt buộc suy nghĩ, đã bỏ qua yêu cầu tắt.",
            )
        return reasoning_decision(
            "mandatory" if mandatory else "optional",
            "boolean",
            {"enable_thinking": intent == "enable"},
        )
