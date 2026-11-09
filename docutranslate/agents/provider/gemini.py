from docutranslate.agents.thinking.base import ReasoningAdapter, reasoning_decision
from docutranslate.agents.thinking.capability import ReasoningDecision, ThinkingIntent


class GoogleAdapter(ReasoningAdapter):
    def decide(self, model_id: str, intent: ThinkingIntent) -> ReasoningDecision:
        model = model_id.lower()
        mandatory = "gemini-3" in model or (
            "gemini-2.5-pro" in model and "flash" not in model
        )
        unsupported = any(
            marker in model
            for marker in ("gemini-1", "gemini-2.0", "embedding", "imagen")
        )
        if intent == "default":
            support = "unsupported" if unsupported else (
                "mandatory" if mandatory else "optional"
            )
            return reasoning_decision(support, "none")
        if unsupported:
            return reasoning_decision(
                "unsupported",
                "none",
                warning=f"Mô hình {model_id} không hỗ trợ chế độ suy nghĩ có thể cấu hình, đã bỏ qua {intent}.",
            )
        if mandatory and intent == "disable":
            return reasoning_decision(
                "mandatory",
                "effort",
                warning=f"Mô hình {model_id} không cho phép tắt suy nghĩ, đã dùng hành vi mặc định của mô hình.",
            )
        value = "medium" if intent == "enable" else "none"
        return reasoning_decision(
            "mandatory" if mandatory else "optional",
            "effort",
            {"reasoning_effort": value},
            efforts=("none", "minimal", "low", "medium", "high"),
        )
