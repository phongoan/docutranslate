from docutranslate.agents.thinking.base import reasoning_decision
from docutranslate.agents.thinking.capability import ReasoningDecision, ThinkingIntent

from .openai import OpenAIAdapter


class OllamaAdapter(OpenAIAdapter):
    def decide(self, model_id: str, intent: ThinkingIntent) -> ReasoningDecision:
        model = model_id.lower()
        if intent == "default":
            return reasoning_decision("unknown", "none")
        if "gpt-oss" in model and intent == "disable":
            return reasoning_decision(
                "mandatory",
                "effort",
                warning=f"Mô hình Ollama {model_id} không thể tắt hoàn toàn suy nghĩ, đã dùng hành vi mặc định của mô hình.",
            )
        return reasoning_decision(
            "unknown",
            "effort",
            {"reasoning_effort": "medium" if intent == "enable" else "none"},
            efforts=("none", "low", "medium", "high"),
        )
