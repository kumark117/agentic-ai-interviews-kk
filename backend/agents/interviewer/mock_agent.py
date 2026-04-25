import hashlib
import uuid

from app.models.models import Difficulty, QuestionSource
from app.schemas.api import GeneratedQuestion


class MockInterviewerAgent:
    async def generate_next_question(
        self, current_difficulty: Difficulty, asked_question_texts: list[str] | None = None
    ) -> GeneratedQuestion:
        asked_question_texts = asked_question_texts or []
        question_bank = {
            Difficulty.easy: [
                "Can you explain this concept with a simple example?",
                "How would you explain this to a junior engineer?",
                "What is the simplest way to implement this correctly?"
            ],
            Difficulty.medium: [
                "What tradeoffs would you consider when implementing this?",
                "How would you balance performance and maintainability here?",
                "What edge cases would you prioritize first in this design?"
            ],
            Difficulty.hard: [
                "How would this approach behave under high load or at scale?",
                "What failure modes would you expect in production and how would you mitigate them?",
                "How would you redesign this for reliability across distributed systems?"
            ]
        }

        candidates = [q for q in question_bank[current_difficulty] if q not in asked_question_texts[-4:]]
        if not candidates:
            candidates = question_bank[current_difficulty]

        # Deterministic rotation based on session history length for predictable tests.
        index_seed = f"{current_difficulty.value}:{len(asked_question_texts)}"
        index = int(hashlib.sha256(index_seed.encode("utf-8")).hexdigest(), 16) % len(candidates)
        chosen_text = candidates[index]

        return GeneratedQuestion(
            question_id=f"q_{uuid.uuid4().hex[:8]}",
            text=chosen_text,
            difficulty=current_difficulty,
            topic="general_system_design",
            source=QuestionSource.fallback_bank,
        )
