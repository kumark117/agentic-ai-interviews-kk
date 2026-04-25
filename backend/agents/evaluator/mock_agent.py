from dataclasses import dataclass

from app.models.models import Confidence, EvaluationSource


@dataclass
class MockEvaluationResult:
    score: float
    feedback: str
    confidence: Confidence
    fallback_flag: bool
    source: EvaluationSource


class MockEvaluatorAgent:
    def _build_feedback(self, question_text: str, answer_text: str, score: float) -> str:
        text = answer_text.lower()
        qtext = question_text.lower()
        has_tradeoff = any(token in text for token in ["tradeoff", "trade-off", "pros", "cons", "versus", "vs"])
        has_scale = any(token in text for token in ["scale", "latency", "throughput", "bottleneck", "load"])
        has_reliability = any(token in text for token in ["failure", "retry", "fallback", "timeout", "resilience"])

        if score < 5.5:
            return "Needs clearer structure and concrete implementation details; explain the flow step-by-step."
        if "react" in qtext and "virtual dom" not in text:
            return "Covers the idea, but mention virtual DOM diffing and key usage to make the React explanation complete."
        if not has_tradeoff:
            return "Solid baseline answer; add explicit tradeoffs and why one approach is better under specific constraints."
        if has_tradeoff and not has_scale:
            return "Good tradeoff discussion; extend it with performance and scale implications to improve the score."
        if has_scale and not has_reliability:
            return "Strong technical depth; include failure handling and recovery strategies for production readiness."
        return "Strong answer with clear tradeoffs and systems thinking; minor improvement: add measurable success criteria."

    async def evaluate(self, question_text: str, answer_text: str, previous_score: float | None = None) -> MockEvaluationResult:
        if len(answer_text.strip()) < 20:
            return MockEvaluationResult(
                score=5 if previous_score is None else previous_score,
                feedback="Answer is too brief to score reliably.",
                confidence=Confidence.LOW,
                fallback_flag=False,
                source=EvaluationSource.llm,
            )

        score = min(10.0, max(0.0, 6.0 + min(len(answer_text) / 120.0, 3.0)))
        score = round(score, 1)
        return MockEvaluationResult(
            score=score,
            feedback=self._build_feedback(question_text, answer_text, score),
            confidence=Confidence.HIGH,
            fallback_flag=False,
            source=EvaluationSource.llm,
        )
